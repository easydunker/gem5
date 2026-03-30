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


def summarize_partition_plan(
    plan,
    *,
    requested_partitioner,
    strategy,
    reason,
    auto_shape,
    requested_workers,
    effective_workers,
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
    )


def format_partition_map(queue_to_router_map):
    return ";".join(
        f"{queue}:[{','.join(str(router_id) for router_id in router_ids)}]"
        for queue, router_ids in queue_to_router_map
    )


def format_partition_summary_lines(summary):
    return (
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
    )
