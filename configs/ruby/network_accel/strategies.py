from __future__ import annotations

from dataclasses import dataclass
from collections import deque

from .partition_model import PartitionPlan, RouterPartition, TopologyExtraction


@dataclass(frozen=True)
class PartitionStrategyResult:
    plan: PartitionPlan
    strategy: str
    reason: str


class PartitionStrategyError(RuntimeError):
    pass


def _balanced_slices(total, parts):
    if parts < 1:
        raise PartitionStrategyError("partition count must be >= 1")
    if parts > total:
        raise PartitionStrategyError(
            f"cannot split {total} items into {parts} non-empty partitions"
        )

    base, remainder = divmod(total, parts)
    slices = []
    start = 0
    for index in range(parts):
        size = base + (1 if index < remainder else 0)
        stop = start + size
        slices.append((start, stop))
        start = stop
    return tuple(slices)


def _router_weight(router):
    return (
        1
        + len(router.cpu_indices)
        + len(router.cpu_port_indices)
        + len(router.ext_link_indices)
        + len(router.netif_indices)
        + len(router.controller_labels)
        + len(router.mem_ctrl_indices)
    )


def _partition_score(topology, plan):
    router_to_queue = {}
    partition_weights = []
    partition_members = []
    for queue, partition in plan.queue_assignments:
        for router_id in partition.router_ids:
            router_to_queue[router_id] = queue
        partition_members.append(partition.router_ids)

        weight = 0
        router_lookup = {router.router_id: router for router in topology.routers}
        for router_id in partition.router_ids:
            weight += _router_weight(router_lookup[router_id])
        partition_weights.append(weight)

    cut_edges = 0
    for link in topology.internal_links:
        if router_to_queue[link.src_router_id] != router_to_queue[link.dst_router_id]:
            cut_edges += 1

    max_weight = max(partition_weights) if partition_weights else 0
    weight_spread = (
        max(partition_weights) - min(partition_weights)
        if partition_weights
        else 0
    )
    membership_summary = tuple(partition_members)
    return (cut_edges, max_weight, weight_spread, membership_summary)


def _mesh_router_positions(topology):
    if topology.mesh_rows is None or topology.mesh_cols is None:
        raise PartitionStrategyError("Mesh_XY topology is missing dimensions")

    router_ids = topology.router_ids
    if len(router_ids) != topology.mesh_rows * topology.mesh_cols:
        raise PartitionStrategyError(
            "Mesh_XY router count does not match the declared dimensions"
        )

    return {
        router_id: divmod(index, topology.mesh_cols)
        for index, router_id in enumerate(router_ids)
    }


def _plan_from_groups(groups):
    queue_assignments = tuple(
        (queue, RouterPartition(router_ids=tuple(router_ids)))
        for queue, router_ids in groups
        if router_ids
    )
    if not queue_assignments:
        raise PartitionStrategyError("partition plan has no routers")
    return PartitionPlan(queue_assignments=queue_assignments)


def _mesh_grid_candidates(topology, partition_count):
    router_positions = _mesh_router_positions(topology)
    rows = topology.mesh_rows
    cols = topology.mesh_cols

    candidates = []
    for row_parts in range(1, min(rows, partition_count) + 1):
        if partition_count % row_parts != 0:
            continue
        col_parts = partition_count // row_parts
        if col_parts < 1 or col_parts > cols:
            continue

        row_slices = _balanced_slices(rows, row_parts)
        col_slices = _balanced_slices(cols, col_parts)
        groups = []
        queue = 1
        for row_start, row_stop in row_slices:
            for col_start, col_stop in col_slices:
                router_ids = [
                    router_id
                    for router_id, (row, col) in router_positions.items()
                    if row_start <= row < row_stop and col_start <= col < col_stop
                ]
                groups.append((queue, tuple(sorted(router_ids))))
                queue += 1
        candidates.append(_plan_from_groups(groups))

    return tuple(candidates)


def _strip_candidates(topology, partition_count):
    router_positions = _mesh_router_positions(topology)
    rows = topology.mesh_rows
    cols = topology.mesh_cols

    candidates = []
    if partition_count <= rows:
        row_slices = _balanced_slices(rows, partition_count)
        groups = []
        for queue, (row_start, row_stop) in enumerate(row_slices, start=1):
            router_ids = [
                router_id
                for router_id, (row, _col) in router_positions.items()
                if row_start <= row < row_stop
            ]
            groups.append((queue, tuple(sorted(router_ids))))
        candidates.append(_plan_from_groups(groups))

    if partition_count <= cols:
        col_slices = _balanced_slices(cols, partition_count)
        groups = []
        for queue, (col_start, col_stop) in enumerate(col_slices, start=1):
            router_ids = [
                router_id
                for router_id, (_row, col) in router_positions.items()
                if col_start <= col < col_stop
            ]
            groups.append((queue, tuple(sorted(router_ids))))
        candidates.append(_plan_from_groups(groups))

    return tuple(candidates)


def _bfs_order(topology):
    adjacency = {router.router_id: set() for router in topology.routers}
    for link in topology.internal_links:
        adjacency[link.src_router_id].add(link.dst_router_id)
        adjacency[link.dst_router_id].add(link.src_router_id)

    remaining = set(adjacency)
    order = []
    while remaining:
        start = min(remaining)
        queue = deque([start])
        remaining.remove(start)
        while queue:
            router_id = queue.popleft()
            order.append(router_id)
            for neighbor in sorted(adjacency[router_id]):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
    return tuple(order)


def _connected(topology):
    if not topology.routers:
        return False
    if not topology.internal_links:
        return len(topology.routers) == 1

    adjacency = {router.router_id: set() for router in topology.routers}
    for link in topology.internal_links:
        adjacency[link.src_router_id].add(link.dst_router_id)
        adjacency[link.dst_router_id].add(link.src_router_id)

    seen = set()
    queue = deque([topology.routers[0].router_id])
    while queue:
        router_id = queue.popleft()
        if router_id in seen:
            continue
        seen.add(router_id)
        for neighbor in sorted(adjacency[router_id]):
            if neighbor not in seen:
                queue.append(neighbor)
    return len(seen) == len(topology.routers)


def _chunks_from_order(router_ids, partition_count):
    slices = _balanced_slices(len(router_ids), partition_count)
    groups = []
    for queue, (start, stop) in enumerate(slices, start=1):
        groups.append((queue, tuple(router_ids[start:stop])))
    return _plan_from_groups(groups)


def _select_best_candidate(topology, candidates, strategy, reason):
    if not candidates:
        raise PartitionStrategyError(f"{strategy} could not build any candidates")

    scored = [
        (_partition_score(topology, plan), plan)
        for plan in candidates
    ]
    scored.sort(key=lambda item: item[0])
    return PartitionStrategyResult(
        plan=scored[0][1],
        strategy=strategy,
        reason=reason,
    )


def build_mesh_blocks_plan(topology, partition_count):
    candidates = _mesh_grid_candidates(topology, partition_count)
    return _select_best_candidate(
        topology,
        candidates,
        strategy="mesh_blocks",
        reason="mesh_xy_rectangular",
    )


def build_mesh_strips_plan(topology, partition_count):
    candidates = _strip_candidates(topology, partition_count)
    return _select_best_candidate(
        topology,
        candidates,
        strategy="mesh_strips",
        reason="mesh_xy_strips",
    )


def build_graph_bfs_plan(topology, partition_count):
    if not _connected(topology):
        raise PartitionStrategyError("router graph is disconnected")
    router_ids = _bfs_order(topology)
    plan = _chunks_from_order(router_ids, partition_count)
    return PartitionStrategyResult(
        plan=plan,
        strategy="graph_bfs",
        reason="graph_connected",
    )


def build_router_chunks_plan(topology, partition_count):
    router_ids = tuple(sorted(topology.router_ids))
    plan = _chunks_from_order(router_ids, partition_count)
    return PartitionStrategyResult(
        plan=plan,
        strategy="router_chunks",
        reason="conservative_router_chunks",
    )


def useful_partition_count(topology, worker_cap):
    if worker_cap < 2:
        raise PartitionStrategyError(
            "parallel network acceleration requires at least two workers"
        )
    return min(worker_cap, len(topology.router_ids))


def build_topology_auto_partition_plan(
    topology,
    *,
    requested_shape,
    worker_cap,
):
    partition_count = useful_partition_count(topology, worker_cap)

    if topology.topology_name == "Mesh_XY":
        if requested_shape == "mesh_blocks":
            try:
                return build_mesh_blocks_plan(topology, partition_count)
            except PartitionStrategyError:
                try:
                    return build_mesh_strips_plan(topology, partition_count)
                except PartitionStrategyError:
                    pass
        elif requested_shape == "mesh_strips":
            try:
                return build_mesh_strips_plan(topology, partition_count)
            except PartitionStrategyError:
                try:
                    return build_mesh_blocks_plan(topology, partition_count)
                except PartitionStrategyError:
                    pass
        elif requested_shape == "graph_bfs":
            try:
                return build_graph_bfs_plan(topology, partition_count)
            except PartitionStrategyError:
                pass
        elif requested_shape == "router_chunks":
            return build_router_chunks_plan(topology, partition_count)

    if _connected(topology):
        try:
            return build_graph_bfs_plan(topology, partition_count)
        except PartitionStrategyError:
            pass
    return build_router_chunks_plan(topology, partition_count)
