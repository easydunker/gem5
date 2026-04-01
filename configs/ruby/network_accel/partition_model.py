from dataclasses import dataclass


@dataclass(frozen=True)
class RouterPartition:
    router_ids: tuple[int, ...]

    def __post_init__(self):
        normalized = tuple(sorted({int(router_id) for router_id in self.router_ids}))
        if not normalized:
            raise ValueError("RouterPartition requires at least one router")
        object.__setattr__(self, "router_ids", normalized)


@dataclass(frozen=True)
class PartitionPlan:
    queue_assignments: tuple[tuple[int, RouterPartition], ...]

    def __post_init__(self):
        assignments = []
        seen_queues = set()
        seen_routers = set()
        for queue, partition in self.queue_assignments:
            queue = int(queue)
            if queue in seen_queues:
                raise ValueError(f"duplicate queue assignment for queue {queue}")
            overlap = seen_routers.intersection(partition.router_ids)
            if overlap:
                raise ValueError(
                    f"router assigned to multiple partitions: {sorted(overlap)}"
                )
            seen_queues.add(queue)
            seen_routers.update(partition.router_ids)
            assignments.append((queue, partition))

        object.__setattr__(
            self,
            "queue_assignments",
            tuple(sorted(assignments, key=lambda assignment: assignment[0])),
        )

    @property
    def ordered_router_ids(self):
        return tuple(
            sorted(
                router_id
                for _, partition in self.queue_assignments
                for router_id in partition.router_ids
            )
        )

    @property
    def router_count(self):
        return len(self.ordered_router_ids)

    @property
    def partition_count(self):
        return len(self.queue_assignments)

    def queue_for_router(self, router_id):
        router_id = int(router_id)
        for queue, partition in self.queue_assignments:
            if router_id in partition.router_ids:
                return queue
        raise KeyError(f"router {router_id} not found in partition plan")

    def router_id_for_index(self, index):
        router_ids = self.ordered_router_ids
        if not router_ids:
            raise IndexError("partition plan has no routers")
        return router_ids[index % len(router_ids)]

    def queue_map(self):
        return tuple(
            (queue, partition.router_ids)
            for queue, partition in self.queue_assignments
        )


@dataclass(frozen=True)
class ExtractedInternalLink:
    src_router_id: int
    dst_router_id: int
    link_id: int

    def __post_init__(self):
        object.__setattr__(self, "src_router_id", int(self.src_router_id))
        object.__setattr__(self, "dst_router_id", int(self.dst_router_id))
        object.__setattr__(self, "link_id", int(self.link_id))


@dataclass(frozen=True)
class ExtractedRouter:
    router_id: int
    controller_labels: tuple[str, ...] = ()
    ext_link_indices: tuple[int, ...] = ()
    netif_indices: tuple[int, ...] = ()
    cpu_indices: tuple[int, ...] = ()
    cpu_port_indices: tuple[int, ...] = ()
    mem_ctrl_indices: tuple[int, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "router_id", int(self.router_id))
        object.__setattr__(
            self,
            "controller_labels",
            tuple(sorted({str(label) for label in self.controller_labels})),
        )
        for field_name in (
            "ext_link_indices",
            "netif_indices",
            "cpu_indices",
            "cpu_port_indices",
            "mem_ctrl_indices",
        ):
            values = getattr(self, field_name)
            object.__setattr__(
                self,
                field_name,
                tuple(sorted({int(value) for value in values})),
            )

    @property
    def owner_tokens(self):
        tokens = []
        tokens.extend(f"cpu:{index}" for index in self.cpu_indices)
        tokens.extend(
            f"cpu_port:{index}" for index in self.cpu_port_indices
        )
        tokens.extend(f"ctrl:{label}" for label in self.controller_labels)
        tokens.extend(f"ext:{index}" for index in self.ext_link_indices)
        tokens.extend(f"mem:{index}" for index in self.mem_ctrl_indices)
        tokens.extend(f"netif:{index}" for index in self.netif_indices)
        return tuple(tokens)


@dataclass(frozen=True)
class TopologyExtraction:
    topology_name: str
    routers: tuple[ExtractedRouter, ...]
    internal_links: tuple[ExtractedInternalLink, ...]
    mesh_rows: int | None = None
    mesh_cols: int | None = None

    def __post_init__(self):
        normalized_routers = tuple(
            sorted(self.routers, key=lambda router: router.router_id)
        )
        router_ids = [router.router_id for router in normalized_routers]
        if len(set(router_ids)) != len(router_ids):
            raise ValueError("duplicate router IDs in topology extraction")

        normalized_links = tuple(
            sorted(
                self.internal_links,
                key=lambda link: (
                    link.src_router_id,
                    link.dst_router_id,
                    link.link_id,
                ),
            )
        )
        router_id_set = set(router_ids)
        for link in normalized_links:
            if link.src_router_id not in router_id_set:
                raise ValueError(
                    f"unknown source router {link.src_router_id} in topology"
                )
            if link.dst_router_id not in router_id_set:
                raise ValueError(
                    f"unknown destination router {link.dst_router_id} in topology"
                )

        if (self.mesh_rows is None) != (self.mesh_cols is None):
            raise ValueError(
                "mesh_rows and mesh_cols must both be set or both be None"
            )
        if self.mesh_rows is not None and self.mesh_rows < 1:
            raise ValueError("mesh_rows must be >= 1")
        if self.mesh_cols is not None and self.mesh_cols < 1:
            raise ValueError("mesh_cols must be >= 1")

        object.__setattr__(self, "topology_name", str(self.topology_name))
        object.__setattr__(self, "routers", normalized_routers)
        object.__setattr__(self, "internal_links", normalized_links)

    @property
    def router_ids(self):
        return tuple(router.router_id for router in self.routers)


@dataclass(frozen=True)
class PartitionSummary:
    requested_partitioner: str
    strategy: str
    reason: str
    auto_shape: str
    requested_workers: str
    effective_workers: int
    router_count: int
    partition_count: int
    queue_to_router_map: tuple[tuple[int, tuple[int, ...]], ...]
    topology: object = None


def summarize_partition_plan(
    plan,
    *,
    requested_partitioner,
    strategy,
    reason,
    auto_shape,
    requested_workers,
    effective_workers,
    topology=None,
):
    return PartitionSummary(
        requested_partitioner=requested_partitioner,
        strategy=strategy,
        reason=reason,
        auto_shape=auto_shape,
        requested_workers=requested_workers,
        effective_workers=effective_workers,
        router_count=plan.router_count,
        partition_count=plan.partition_count,
        queue_to_router_map=plan.queue_map(),
        topology=topology,
    )


def format_partition_map(queue_to_router_map):
    return ";".join(
        f"{queue}:[{','.join(str(router_id) for router_id in router_ids)}]"
        for queue, router_ids in queue_to_router_map
    )


def format_topology_links(topology):
    return ",".join(
        f"{link.src_router_id}>{link.dst_router_id}"
        for link in topology.internal_links
    )


def format_topology_owners(topology):
    return ";".join(
        f"{router.router_id}:[{','.join(router.owner_tokens)}]"
        for router in topology.routers
    )


def format_partition_summary_lines(summary):
    lines = [
        "PARALLEL_NOC_PARTITIONER "
        f"requested={summary.requested_partitioner} "
        f"strategy={summary.strategy} "
        f"reason={summary.reason} "
        f"auto_shape={summary.auto_shape} "
        f"requested_workers={summary.requested_workers} "
        f"effective_workers={summary.effective_workers} "
        f"routers={summary.router_count} "
        f"partitions={summary.partition_count}",
        "PARALLEL_NOC_PARTITION_MAP "
        f"queues={format_partition_map(summary.queue_to_router_map)}",
    ]
    if (
        summary.requested_partitioner == "topology_auto"
        and summary.strategy == "router_chunks"
        and summary.auto_shape in {"mesh_blocks", "mesh_strips"}
    ):
        lines.append(
            "PARALLEL_NOC_NOTE "
            f"requested={summary.requested_partitioner} "
            f"auto_shape={summary.auto_shape} "
            "fallback=router_chunks "
            "reason=non_mesh_topology"
        )
    if summary.topology is not None:
        rows = (
            str(summary.topology.mesh_rows)
            if summary.topology.mesh_rows is not None
            else "na"
        )
        cols = (
            str(summary.topology.mesh_cols)
            if summary.topology.mesh_cols is not None
            else "na"
        )
        lines.extend(
            [
                "PARALLEL_NOC_TOPOLOGY "
                f"topology={summary.topology.topology_name} "
                f"rows={rows} cols={cols} "
                f"routers={','.join(str(router_id) for router_id in summary.topology.router_ids)}",
                "PARALLEL_NOC_TOPOLOGY_LINKS "
                f"links={format_topology_links(summary.topology)}",
                "PARALLEL_NOC_TOPOLOGY_ATTACH "
                f"owners={format_topology_owners(summary.topology)}",
            ]
        )
    return tuple(lines)
