# Copyright (c) 2026
# All rights reserved.
#
# Ruby/Garnet configuration used by tests/gem5/ruby_parallel_noc.
#
# The acceleration framework lives outside Garnet. This config wires the
# selected execution mode into that external coordinator while keeping the
# workload itself unchanged.

import argparse
import os

import m5
from m5.objects import *
from m5.util import addToPath

addToPath("../../../../configs")
addToPath("../../../../configs/common")
addToPath("../../../../configs/ruby")

from common import Options  # noqa: E402
from ruby import Ruby  # noqa: E402


def _set_subtree_eventq(obj, eventq_index):
    for child in obj.descendants():
        child.eventq_index = eventq_index
    obj.eventq_index = eventq_index


def _configure_parallel_router_domains(root, system, requested_workers):
    routers = list(system.ruby.network.routers)
    if len(routers) < 2:
        raise RuntimeError(
            "Parallel NoC mode requires at least two routers/partitions."
        )

    active_workers = min(requested_workers, len(routers))
    if active_workers < 2:
        raise RuntimeError(
            "Parallel NoC mode requires at least two active workers."
        )

    def queue_for_router(router_index):
        return 1 + (int(router_index) % active_workers)

    for router in routers:
        _set_subtree_eventq(router, queue_for_router(router.router_id))

    for i, cpu in enumerate(system.cpu):
        _set_subtree_eventq(cpu, queue_for_router(i))

    for i, ctrl in enumerate(system.ruby._cpu_ports):
        _set_subtree_eventq(ctrl, queue_for_router(i))

    l1_ctrls = [getattr(system.ruby, f"l1_cntrl{i}") for i in range(len(routers))]
    for i, ctrl in enumerate(l1_ctrls):
        _set_subtree_eventq(ctrl, queue_for_router(i))

    dir_ctrls = [getattr(system.ruby, f"dir_cntrl{i}") for i in range(len(routers))]
    for i, ctrl in enumerate(dir_ctrls):
        _set_subtree_eventq(ctrl, queue_for_router(i))

    for i, mem_ctrl in enumerate(system.mem_ctrls):
        _set_subtree_eventq(mem_ctrl, queue_for_router(i % len(routers)))

    for i, netif in enumerate(system.ruby.network.netifs):
        _set_subtree_eventq(netif, queue_for_router(i % len(routers)))

    for i, ext_link in enumerate(system.ruby.network.ext_links):
        _set_subtree_eventq(ext_link, queue_for_router(i % len(routers)))

    for int_link in system.ruby.network.int_links:
        src_queue = queue_for_router(int_link.src_node.router_id)
        dst_queue = queue_for_router(int_link.dst_node.router_id)
        _set_subtree_eventq(int_link.network_link, src_queue)
        _set_subtree_eventq(int_link.src_net_bridge, src_queue)
        _set_subtree_eventq(int_link.src_cred_bridge, src_queue)
        _set_subtree_eventq(int_link.dst_net_bridge, dst_queue)
        _set_subtree_eventq(int_link.credit_link, dst_queue)
        _set_subtree_eventq(int_link.dst_cred_bridge, dst_queue)
        int_link.eventq_index = src_queue

    root.sim_quantum = 1
    m5.activateParallelNetworkAcceleration(len(routers))


def build_parser():
    parser = argparse.ArgumentParser()
    Options.addNoISAOptions(parser)

    parser.add_argument(
        "--synthetic",
        default="uniform_random",
        choices=[
            "uniform_random",
            "tornado",
            "bit_complement",
            "bit_reverse",
            "bit_rotation",
            "neighbor",
            "shuffle",
            "transpose",
        ],
    )
    parser.add_argument("--injectionrate", type=float, default=0.02)
    parser.add_argument("--precision", type=int, default=3)
    parser.add_argument("--sim-cycles", type=int, default=2000)
    parser.add_argument("--num-packets-max", type=int, default=-1)
    parser.add_argument("--single-sender-id", type=int, default=-1)
    parser.add_argument("--single-dest-id", type=int, default=-1)
    parser.add_argument(
        "--inj-vnet",
        type=int,
        default=-1,
        choices=[-1, 0, 1, 2],
    )

    # Future feature knobs. These are parsed now so tests can be stable
    # before/after feature implementation.
    parser.add_argument(
        "--parallel-noc-mode",
        default="off",
        choices=["off", "serial_batched", "parallel"],
        help="Future Garnet parallel execution mode.",
    )
    parser.add_argument(
        "--parallel-noc-workers",
        type=int,
        default=1,
        help="Future worker count for parallel NoC mode.",
    )

    Ruby.define_options(parser)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    requested_mode = args.parallel_noc_mode
    m5.setNetworkAcceleration(requested_mode, args.parallel_noc_workers)

    if args.num_dirs != args.num_cpus:
        raise RuntimeError(
            f"Expected --num-dirs == --num-cpus for this test config, got "
            f"{args.num_dirs} and {args.num_cpus}."
        )

    cpus = [
        GarnetSyntheticTraffic(
            num_packets_max=args.num_packets_max,
            single_sender=args.single_sender_id,
            single_dest=args.single_dest_id,
            sim_cycles=args.sim_cycles,
            traffic_type=args.synthetic,
            inj_rate=args.injectionrate,
            inj_vnet=args.inj_vnet,
            precision=args.precision,
            num_dest=args.num_dirs,
        )
        for _ in range(args.num_cpus)
    ]

    system = System(cpu=cpus, mem_ranges=[AddrRange(args.mem_size)])
    system.voltage_domain = VoltageDomain(voltage=args.sys_voltage)
    system.clk_domain = SrcClockDomain(
        clock=args.sys_clock, voltage_domain=system.voltage_domain
    )

    Ruby.create_system(args, False, system)
    system.ruby.clk_domain = SrcClockDomain(
        clock=args.ruby_clock, voltage_domain=system.voltage_domain
    )

    for i, ruby_port in enumerate(system.ruby._cpu_ports):
        cpus[i].test = ruby_port.in_ports

    root = Root(full_system=False, system=system)
    root.system.mem_mode = "timing"
    m5.ticks.setGlobalFrequency("1ps")

    if requested_mode == "parallel":
        _configure_parallel_router_domains(
            root, system, args.parallel_noc_workers
        )

    effective_mode = m5.getNetworkAccelerationMode()
    effective_workers = m5.getNetworkAccelerationWorkers()
    requested_workers = m5.getRequestedNetworkAccelerationWorkers()

    print(
        "PARALLEL_NOC_MODE="
        f"{effective_mode} REQUESTED={requested_mode} "
        f"WORKERS={effective_workers} NUM_CPUS={args.num_cpus}"
    )
    print(
        "PARALLEL_NOC_COORDINATOR "
        f"mode={effective_mode} workers={effective_workers}"
    )
    if effective_mode == "parallel":
        print(
            "PARALLEL_NOC_PARTITION "
            f"partitions={m5.getNetworkAccelerationParallelPartitions()} "
            f"queues={m5.getNetworkAccelerationQueueSummary()} "
            f"sim_quantum={root.sim_quantum}"
        )
    if m5.networkAccelerationDowngraded():
        print(
            "PARALLEL_NOC_NOTE "
            f"requested_mode={requested_mode} "
            f"requested_workers={requested_workers} "
            f"effective_mode={effective_mode} "
            f"effective_workers={effective_workers} "
            f"reason={m5.getNetworkAccelerationNote()}"
        )

    m5.instantiate()
    exit_event = m5.simulate(args.abs_max_tick)
    exit_tick = m5.curTick()
    metric_tick = exit_tick
    if effective_mode == "parallel":
        # Global exit delivery in multi-event-queue mode is scheduled one
        # quantum after the workload-completion event.
        metric_tick -= int(root.sim_quantum)
    stats_path = os.path.join(m5.options.outdir, "stats.txt")
    print(
        f"Exiting @ tick {exit_tick} because {exit_event.getCause()}"
    )
    print(
        "PARALLEL_NOC_METRIC "
        f"tick={metric_tick} exit_tick={exit_tick} "
        f"cause={exit_event.getCause()}"
    )
    print(
        "PARALLEL_NOC_STATS "
        f"path={stats_path} exists={os.path.isfile(stats_path)}"
    )


if __name__ == "__m5_main__":
    main()
