import argparse
import os
import m5

if __package__:
    from .network_accel import (
        PartitionPlan,
        PartitionStrategyError,
        PartitionStrategyResult,
        RouterPartition,
        TopologyExtractionError,
        build_topology_auto_partition_plan,
        extract_topology,
        format_partition_summary_lines,
        summarize_partition_plan,
    )
else:
    from network_accel import (
        PartitionPlan,
        PartitionStrategyError,
        PartitionStrategyResult,
        RouterPartition,
        TopologyExtractionError,
        build_topology_auto_partition_plan,
        extract_topology,
        format_partition_summary_lines,
        summarize_partition_plan,
    )


_AUTO_WORKERS = "auto"


def _parse_positive_int(value):
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be >= 1")
    return parsed


def _parse_requested_workers(value):
    if value == _AUTO_WORKERS:
        return value
    return _parse_positive_int(value)


def add_network_accel_options(parser):
    parser.add_argument(
        "--network-accel-mode",
        "--parallel-noc-mode",
        dest="network_accel_mode",
        default="off",
        choices=["off", "serial_batched", "parallel"],
        help="Network acceleration execution mode.",
    )
    parser.add_argument(
        "--network-accel-workers",
        "--parallel-noc-workers",
        dest="network_accel_workers",
        type=_parse_requested_workers,
        default=1,
        help="Requested worker count for network acceleration or 'auto'.",
    )
    parser.add_argument(
        "--network-accel-max-workers",
        dest="network_accel_max_workers",
        type=_parse_positive_int,
        default=None,
        help="Optional upper bound for the effective worker count.",
    )
    parser.add_argument(
        "--network-accel-partitioner",
        dest="network_accel_partitioner",
        default="manual",
        choices=["manual", "topology_auto"],
        help=(
            "Partitioner strategy surface for Ruby/Garnet acceleration. "
            "Phase 1 keeps topology_auto on an explicit manual fallback "
            "until topology extraction lands."
        ),
    )
    parser.add_argument(
        "--network-accel-auto-shape",
        dest="network_accel_auto_shape",
        default="mesh_blocks",
        choices=["mesh_blocks", "mesh_strips", "graph_bfs", "router_chunks"],
        help="Requested topology-auto partitioning shape.",
    )
    parser.add_argument(
        "--network-accel-report-partitions",
        dest="network_accel_report_partitions",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Print compact partitioner summary lines.",
    )


def _set_subtree_eventq(obj, eventq_index):
    for child in obj.descendants():
        child.eventq_index = eventq_index
    obj.eventq_index = eventq_index


def _sorted_routers(system):
    return sorted(
        list(system.ruby.network.routers),
        key=lambda router: int(router.router_id),
    )


def _resolve_worker_cap(requested_workers, max_workers):
    if requested_workers == _AUTO_WORKERS:
        if hasattr(os, "sched_getaffinity"):
            try:
                host_cpus = len(os.sched_getaffinity(0))
            except OSError:
                host_cpus = 0
        else:
            host_cpus = 0
        if host_cpus < 1:
            host_cpus = os.cpu_count() or 1
        effective_workers = max(host_cpus - 1, 1)
    else:
        effective_workers = requested_workers
    if max_workers is not None:
        effective_workers = min(effective_workers, max_workers)
    return effective_workers


def _indexed_ruby_children(ruby_system, prefix):
    children = []
    for name in dir(ruby_system):
        if not name.startswith(prefix):
            continue
        suffix = name[len(prefix) :]
        if suffix.isdigit():
            children.append((int(suffix), getattr(ruby_system, name)))
    return [child for _, child in sorted(children)]


def _balanced_slices(total, parts):
    base, remainder = divmod(total, parts)
    slices = []
    start = 0
    for index in range(parts):
        size = base + (1 if index < remainder else 0)
        stop = start + size
        slices.append((start, stop))
        start = stop
    return tuple(slices)


def _build_router_chunks_partition_plan(router_ids, partition_count):
    if partition_count < 2:
        raise PartitionStrategyError(
            "parallel network acceleration requires at least two workers"
        )
    if partition_count > len(router_ids):
        raise PartitionStrategyError(
            "cannot assign more workers than routers"
        )
    router_ids = tuple(sorted(int(router_id) for router_id in router_ids))
    slices = _balanced_slices(len(router_ids), partition_count)
    queue_assignments = tuple(
        (
            queue,
            RouterPartition(router_ids=tuple(router_ids[start:stop])),
        )
        for queue, (start, stop) in enumerate(slices, start=1)
    )
    return PartitionPlan(queue_assignments=queue_assignments)


def _build_manual_partition_plan(system, effective_workers):
    routers = _sorted_routers(system)
    if len(routers) < 2:
        raise RuntimeError(
            "Parallel network acceleration requires at least two routers."
        )
    if effective_workers < 2:
        raise RuntimeError(
            "Parallel network acceleration requires at least two active workers."
        )

    queue_members = {queue: [] for queue in range(1, effective_workers + 1)}
    for router in routers:
        queue = 1 + (int(router.router_id) % effective_workers)
        queue_members[queue].append(int(router.router_id))

    queue_assignments = tuple(
        (
            queue,
            RouterPartition(router_ids=tuple(router_ids)),
        )
        for queue, router_ids in sorted(queue_members.items())
        if router_ids
    )

    # Phase 1 keeps queue placement conservative and deterministic until the
    # topology-aware strategies land.
    return PartitionPlan(
        queue_assignments=queue_assignments,
    )


def _validate_phase_one_scope(plan, l1_ctrls, dir_ctrls):
    router_count = plan.router_count
    if l1_ctrls and len(l1_ctrls) != router_count:
        raise RuntimeError(
            "Phase-1 network acceleration expects one L1 controller per router."
        )
    if dir_ctrls and len(dir_ctrls) != router_count:
        raise RuntimeError(
            "Phase-1 network acceleration expects one directory controller per "
            "router."
        )


def _apply_partition_plan(root, system, plan, topology=None):
    queue_for_router = plan.queue_for_router
    if topology is None:
        router_id_for_index = plan.router_id_for_index
        l1_ctrls = _indexed_ruby_children(system.ruby, "l1_cntrl")
        dir_ctrls = _indexed_ruby_children(system.ruby, "dir_cntrl")
        _validate_phase_one_scope(plan, l1_ctrls, dir_ctrls)

        for router in system.ruby.network.routers:
            _set_subtree_eventq(router, queue_for_router(int(router.router_id)))

        for i, cpu in enumerate(system.cpu):
            _set_subtree_eventq(cpu, queue_for_router(router_id_for_index(i)))

        for i, ctrl in enumerate(system.ruby._cpu_ports):
            _set_subtree_eventq(ctrl, queue_for_router(router_id_for_index(i)))

        for i, ctrl in enumerate(l1_ctrls):
            _set_subtree_eventq(ctrl, queue_for_router(router_id_for_index(i)))

        for i, ctrl in enumerate(dir_ctrls):
            _set_subtree_eventq(ctrl, queue_for_router(router_id_for_index(i)))

        for i, mem_ctrl in enumerate(system.mem_ctrls):
            _set_subtree_eventq(mem_ctrl, queue_for_router(router_id_for_index(i)))

        for i, netif in enumerate(system.ruby.network.netifs):
            _set_subtree_eventq(netif, queue_for_router(router_id_for_index(i)))

        for i, ext_link in enumerate(system.ruby.network.ext_links):
            _set_subtree_eventq(ext_link, queue_for_router(router_id_for_index(i)))

        for int_link in system.ruby.network.int_links:
            src_queue = queue_for_router(int(int_link.src_node.router_id))
            dst_queue = queue_for_router(int(int_link.dst_node.router_id))
            _set_subtree_eventq(int_link.network_link, src_queue)
            _set_subtree_eventq(int_link.src_net_bridge, src_queue)
            _set_subtree_eventq(int_link.src_cred_bridge, src_queue)
            _set_subtree_eventq(int_link.dst_net_bridge, dst_queue)
            _set_subtree_eventq(int_link.credit_link, dst_queue)
            _set_subtree_eventq(int_link.dst_cred_bridge, dst_queue)
            int_link.eventq_index = src_queue
    else:
        router_queue = {
            int(router.router_id): queue_for_router(int(router.router_id))
            for router in topology.routers
        }
        mem_ctrls = list(getattr(system, "mem_ctrls", []))
        netifs = list(getattr(system.ruby.network, "netifs", []))
        ext_links = list(getattr(system.ruby.network, "ext_links", []))
        cpu_ports = list(getattr(system.ruby, "_cpu_ports", []))

        for router in system.ruby.network.routers:
            _set_subtree_eventq(router, router_queue[int(router.router_id)])

        for extracted_router in topology.routers:
            queue = router_queue[extracted_router.router_id]
            for cpu_index in extracted_router.cpu_indices:
                if cpu_index < len(system.cpu):
                    _set_subtree_eventq(system.cpu[cpu_index], queue)
            for cpu_port_index in extracted_router.cpu_port_indices:
                if cpu_port_index < len(cpu_ports):
                    _set_subtree_eventq(cpu_ports[cpu_port_index], queue)
            for ext_index in extracted_router.ext_link_indices:
                if ext_index < len(ext_links):
                    _set_subtree_eventq(ext_links[ext_index], queue)
                    _set_subtree_eventq(ext_links[ext_index].ext_node, queue)
            for netif_index in extracted_router.netif_indices:
                if netif_index < len(netifs):
                    _set_subtree_eventq(netifs[netif_index], queue)
            for mem_index in extracted_router.mem_ctrl_indices:
                if mem_index < len(mem_ctrls):
                    _set_subtree_eventq(mem_ctrls[mem_index], queue)

        for int_link in system.ruby.network.int_links:
            src_queue = router_queue[int(int_link.src_node.router_id)]
            dst_queue = router_queue[int(int_link.dst_node.router_id)]
            _set_subtree_eventq(int_link.network_link, src_queue)
            _set_subtree_eventq(int_link.src_net_bridge, src_queue)
            _set_subtree_eventq(int_link.src_cred_bridge, src_queue)
            _set_subtree_eventq(int_link.dst_net_bridge, dst_queue)
            _set_subtree_eventq(int_link.credit_link, dst_queue)
            _set_subtree_eventq(int_link.dst_cred_bridge, dst_queue)
            int_link.eventq_index = src_queue

    root.sim_quantum = 1
    m5.activateParallelNetworkAcceleration(plan.partition_count)


def configure_network_accel(
    root,
    system,
    requested_mode,
    requested_workers,
    *,
    partitioner="manual",
    auto_shape="mesh_blocks",
    max_workers=None,
):
    topology = None
    requested_runtime_workers = 1
    effective_workers = 1
    if requested_mode == "parallel":
        worker_cap = _resolve_worker_cap(requested_workers, max_workers)
        requested_runtime_workers = worker_cap
        if partitioner == "topology_auto":
            try:
                topology = extract_topology(system)
            except TopologyExtractionError as error:
                raise RuntimeError(
                    "topology_auto partitioner could not extract a deterministic "
                    f"Ruby/Garnet ownership graph: {error}"
                ) from error
            selection = build_topology_auto_partition_plan(
                topology,
                requested_shape=auto_shape,
                worker_cap=worker_cap,
            )
            effective_workers = selection.plan.partition_count
        else:
            effective_workers = min(
                worker_cap, len(system.ruby.network.routers)
            )
    elif requested_workers != _AUTO_WORKERS:
        requested_runtime_workers = requested_workers

    m5.setNetworkAcceleration(requested_mode, requested_runtime_workers)
    if requested_mode != "parallel":
        return None

    if partitioner == "manual":
        selection = PartitionStrategyResult(
            plan=_build_manual_partition_plan(
                system,
                effective_workers=effective_workers,
            ),
            strategy="manual",
            reason="as_requested",
        )

    _apply_partition_plan(root, system, selection.plan, topology=topology)
    return summarize_partition_plan(
        selection.plan,
        requested_partitioner=partitioner,
        strategy=selection.strategy,
        auto_shape=auto_shape,
        requested_workers=str(requested_workers),
        effective_workers=selection.plan.partition_count,
        reason=selection.reason,
        topology=topology,
    )


__all__ = [
    "PartitionPlan",
    "RouterPartition",
    "add_network_accel_options",
    "configure_network_accel",
    "format_partition_summary_lines",
]
