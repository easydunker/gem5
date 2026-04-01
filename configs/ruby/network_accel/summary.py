from .partition_model import (
    format_partition_map,
    format_topology_links,
    format_topology_owners,
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


__all__ = [
    "format_partition_summary_lines",
]
