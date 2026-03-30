import math
import re

from .partition_model import (
    ExtractedInternalLink,
    ExtractedRouter,
    TopologyExtraction,
)


_INDEXED_CHILD_RE = re.compile(r"^(?P<prefix>.+?)(?P<index>\d+)$")


class TopologyExtractionError(RuntimeError):
    pass


def _indexed_ruby_children(ruby_system, prefix):
    children = []
    for name in dir(ruby_system):
        if not name.startswith(prefix):
            continue
        suffix = name[len(prefix) :]
        if suffix.isdigit():
            children.append((int(suffix), getattr(ruby_system, name)))
    return [child for _, child in sorted(children)]


def _ruby_object_aliases(ruby_system):
    aliases = {}
    for name in dir(ruby_system):
        if name.startswith("_"):
            continue
        match = _INDEXED_CHILD_RE.match(name)
        if match is None:
            continue
        aliases[id(getattr(ruby_system, name))] = name
    return aliases


def _stable_object_label(obj):
    path = getattr(obj, "path", None)
    if callable(path):
        return path().rsplit(".", 1)[-1]
    return obj.__class__.__name__


def _sequencer_index(controller, cpu_port_index):
    sequencer = getattr(controller, "sequencer", None)
    if sequencer is None:
        return None
    if id(sequencer) not in cpu_port_index:
        raise TopologyExtractionError(
            f"could not map controller {_stable_object_label(controller)} "
            "to a Ruby CPU port"
        )
    return cpu_port_index[id(sequencer)]


def _infer_mesh_shape(topology_name, router_ids, network):
    if topology_name != "Mesh_XY":
        return (None, None)

    router_count = len(router_ids)
    rows = int(getattr(network, "num_rows", 0) or 0)
    if rows > 0:
        if router_count % rows != 0:
            raise TopologyExtractionError(
                f"mesh_rows={rows} does not divide router_count={router_count}"
            )
        return (rows, router_count // rows)

    if tuple(router_ids) != tuple(range(router_count)):
        raise TopologyExtractionError(
            "Mesh_XY shape inference requires contiguous router IDs"
        )

    for candidate_rows in range(int(math.isqrt(router_count)), 0, -1):
        if router_count % candidate_rows == 0:
            return (candidate_rows, router_count // candidate_rows)

    raise TopologyExtractionError(
        f"could not infer a Mesh_XY shape for router_count={router_count}"
    )


def extract_topology(system):
    network = system.ruby.network
    routers = sorted(
        list(network.routers),
        key=lambda router: int(router.router_id),
    )
    if not routers:
        raise TopologyExtractionError("Ruby/Garnet network has no routers")

    router_ids = [int(router.router_id) for router in routers]
    if len(set(router_ids)) != len(router_ids):
        raise TopologyExtractionError("Ruby/Garnet network has duplicate router IDs")

    topology_name = str(getattr(network, "topology", "unknown"))
    mesh_rows, mesh_cols = _infer_mesh_shape(topology_name, router_ids, network)

    router_owners = {
        router_id: {
            "controller_labels": [],
            "ext_link_indices": [],
            "netif_indices": [],
            "cpu_indices": [],
            "cpu_port_indices": [],
            "mem_ctrl_indices": [],
        }
        for router_id in router_ids
    }

    ruby_aliases = _ruby_object_aliases(system.ruby)
    cpu_ports = list(getattr(system.ruby, "_cpu_ports", []))
    cpu_port_index = {id(port): index for index, port in enumerate(cpu_ports)}
    dir_ctrls = _indexed_ruby_children(system.ruby, "dir_cntrl")
    dir_ctrl_index = {
        id(controller): index for index, controller in enumerate(dir_ctrls)
    }
    mem_ctrls = list(getattr(system, "mem_ctrls", []))
    if mem_ctrls and dir_ctrls and len(mem_ctrls) != len(dir_ctrls):
        raise TopologyExtractionError(
            "could not prove directory-controller to memory-controller ownership"
        )

    ext_links = list(getattr(network, "ext_links", []))
    netifs = list(getattr(network, "netifs", []))
    if len(netifs) != len(ext_links):
        raise TopologyExtractionError(
            "could not prove one network interface per external link"
        )

    for ext_link_index, ext_link in enumerate(ext_links):
        router_id = int(ext_link.int_node.router_id)
        if router_id not in router_owners:
            raise TopologyExtractionError(
                f"external link {ext_link_index} points to unknown router {router_id}"
            )
        owners = router_owners[router_id]
        owners["ext_link_indices"].append(ext_link_index)
        if netifs:
            owners["netif_indices"].append(ext_link_index)

        controller = ext_link.ext_node
        owners["controller_labels"].append(
            ruby_aliases.get(id(controller), _stable_object_label(controller))
        )

        cpu_port = _sequencer_index(controller, cpu_port_index)
        if cpu_port is not None:
            owners["cpu_port_indices"].append(cpu_port)
            if cpu_port < len(getattr(system, "cpu", [])):
                owners["cpu_indices"].append(cpu_port)

        dir_index = dir_ctrl_index.get(id(controller))
        if dir_index is not None and mem_ctrls:
            owners["mem_ctrl_indices"].append(dir_index)

    internal_links = []
    for fallback_link_id, int_link in enumerate(getattr(network, "int_links", [])):
        src_router_id = int(int_link.src_node.router_id)
        dst_router_id = int(int_link.dst_node.router_id)
        if src_router_id not in router_owners:
            raise TopologyExtractionError(
                f"internal link source router {src_router_id} is unknown"
            )
        if dst_router_id not in router_owners:
            raise TopologyExtractionError(
                f"internal link destination router {dst_router_id} is unknown"
            )
        internal_links.append(
            ExtractedInternalLink(
                src_router_id=src_router_id,
                dst_router_id=dst_router_id,
                link_id=getattr(int_link, "link_id", fallback_link_id),
            )
        )

    extracted_routers = tuple(
        ExtractedRouter(router_id=router_id, **owners)
        for router_id, owners in sorted(router_owners.items())
    )
    return TopologyExtraction(
        topology_name=topology_name,
        routers=extracted_routers,
        internal_links=tuple(internal_links),
        mesh_rows=mesh_rows,
        mesh_cols=mesh_cols,
    )
