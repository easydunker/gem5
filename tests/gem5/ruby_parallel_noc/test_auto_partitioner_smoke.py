# Copyright (c) 2026
# All rights reserved.

import os

from testlib import (
    config,
    constants,
    joinpath,
    test_util,
    verifier,
)

from gem5.suite import gem5_verify_config


class NamedMatchRegex(verifier.MatchRegex):
    def __init__(self, test_name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._test_name = test_name

    def instantiate_test(self, name_pfx):
        name = "-".join([name_pfx, self._test_name])
        return test_util.TestFunction(
            self._test, name=name, fixtures=self.fixtures
        )


class NamedNoMatchRegex(verifier.NoMatchRegex):
    def __init__(self, test_name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._test_name = test_name

    def instantiate_test(self, name_pfx):
        name = "-".join([name_pfx, self._test_name])
        return test_util.TestFunction(
            self._test, name=name, fixtures=self.fixtures
        )


class NamedStatsFileExists(verifier.Verifier):
    def __init__(self, test_name, filename="stats.txt"):
        super().__init__()
        self._test_name = test_name
        self._filename = filename

    def instantiate_test(self, name_pfx):
        name = "-".join([name_pfx, self._test_name])
        return test_util.TestFunction(
            self._test, name=name, fixtures=self.fixtures
        )

    def test(self, params):
        tempdir = params.fixtures[constants.tempdir_fixture_name].path
        stats_path = joinpath(tempdir, self._filename)
        if not os.path.isfile(stats_path):
            test_util.fail(f"Could not find expected stats file: {stats_path}")


def add_auto_partitioner_suite(
    name,
    partitioner,
    strategy,
    reason,
    workers,
    auto_shape,
    effective_workers,
    partition_count,
    partition_map,
    report_partitions=True,
    note_regex=None,
):
    queue_summary = ",".join(
        str(queue) for queue in range(1, effective_workers + 1)
    )
    active_queue_summary = ",".join(
        f"{queue}:1" for queue in range(0, effective_workers + 1)
    )
    dispatch_summary = ",".join(
        f"{queue}:\\d+" for queue in range(0, effective_workers + 1)
    )
    verifiers = [
        NamedMatchRegex(
            "parallel-noc-mode-line",
            rf"^PARALLEL_NOC_MODE=parallel REQUESTED=parallel "
            rf"WORKERS={effective_workers} NUM_CPUS=4$",
        ),
        NamedMatchRegex(
            "parallel-noc-coordinator-line",
            rf"^PARALLEL_NOC_COORDINATOR mode=parallel "
            rf"workers={effective_workers}$",
        ),
        NamedMatchRegex(
            "parallel-noc-partition-line",
            rf"^PARALLEL_NOC_PARTITION partitions={partition_count} "
            rf"queues={queue_summary} sim_quantum=1$",
        ),
        NamedMatchRegex(
            "parallel-noc-runtime-line",
            rf"^PARALLEL_NOC_RUNTIME entered={active_queue_summary} "
            rf"dispatches={dispatch_summary}$",
        ),
        NamedMatchRegex(
            "parallel-noc-metric-line",
            r"^PARALLEL_NOC_METRIC tick=2000 exit_tick=2001 cause=Network "
            r"Tester completed simCycles$",
        ),
        NamedMatchRegex(
            "parallel-noc-stats-line",
            r"^PARALLEL_NOC_STATS path=.*[/\\]stats\.txt exists=True$",
        ),
        NamedStatsFileExists("parallel-noc-stats-file-exists"),
    ]
    if note_regex:
        verifiers.append(
            NamedMatchRegex("parallel-noc-note-line", note_regex)
        )
    if report_partitions:
        verifiers.extend(
            [
                NamedMatchRegex(
                    "parallel-noc-partitioner-line",
                    rf"^PARALLEL_NOC_PARTITIONER requested={partitioner} "
                    rf"strategy={strategy} "
                    rf"reason={reason} "
                    rf"auto_shape={auto_shape} requested_workers={workers} "
                    rf"effective_workers={effective_workers} "
                    rf"routers=4 partitions={partition_count}$",
                ),
                NamedMatchRegex(
                    "parallel-noc-partition-map-line",
                    rf"^PARALLEL_NOC_PARTITION_MAP queues={partition_map}$",
                ),
            ]
        )
    else:
        verifiers.extend(
            [
                NamedNoMatchRegex(
                    "parallel-noc-partitioner-line-absent",
                    r"^PARALLEL_NOC_PARTITIONER ",
                ),
                NamedNoMatchRegex(
                    "parallel-noc-partition-map-line-absent",
                    r"^PARALLEL_NOC_PARTITION_MAP ",
                ),
            ]
        )

    config_args = [
        "--network-accel-mode",
        "parallel",
        "--network-accel-workers",
        str(workers),
        "--network-accel-partitioner",
        partitioner,
        "--network-accel-auto-shape",
        auto_shape,
    ]
    if not report_partitions:
        config_args.append("--no-network-accel-report-partitions")
    config_args.extend(
        [
            "--network",
            "garnet",
            "--topology",
            "Mesh_XY",
            "--num-cpus",
            "4",
            "--num-dirs",
            "4",
            "--mesh-rows",
            "2",
            "--sim-cycles",
            "2000",
            "--synthetic",
            "uniform_random",
            "--injectionrate",
            "0.02",
            "--routing-algorithm",
            "1",
        ]
    )

    gem5_verify_config(
        name=name,
        fixtures=(),
        verifiers=tuple(verifiers),
        config=joinpath(
            config.base_dir,
            "tests",
            "gem5",
            "ruby_parallel_noc",
            "configs",
            "ruby_garnet_equiv.py",
        ),
        config_args=config_args,
        valid_isas=(constants.null_tag,),
        valid_hosts=constants.supported_hosts,
        length=constants.quick_tag,
        protocol="Garnet_standalone",
        uses_kvm=False,
    )


add_auto_partitioner_suite(
    name="ruby-parallel-noc-manual-partitioner-smoke",
    partitioner="manual",
    strategy="manual",
    reason="as_requested",
    workers=3,
    auto_shape="mesh_blocks",
    effective_workers=3,
    partition_count=3,
    partition_map=r"1:\[0,3\];2:\[1\];3:\[2\]",
)

add_auto_partitioner_suite(
    name="ruby-parallel-noc-topology-auto-partitioner-smoke",
    partitioner="topology_auto",
    strategy="mesh_strips",
    reason="mesh_xy_strips",
    workers="auto",
    auto_shape="mesh_strips",
    effective_workers=2,
    partition_count=2,
    partition_map=r"1:\[0,1\];2:\[2,3\]",
)

add_auto_partitioner_suite(
    name="ruby-parallel-noc-topology-auto-partitioner-no-report-smoke",
    partitioner="topology_auto",
    strategy="mesh_strips",
    reason="mesh_xy_strips",
    workers="auto",
    auto_shape="mesh_strips",
    effective_workers=2,
    partition_count=2,
    partition_map=r"1:\[0,1\];2:\[2,3\]",
    report_partitions=False,
)

add_auto_partitioner_suite(
    name="ruby-parallel-noc-topology-auto-partitioner-downgrade-smoke",
    partitioner="topology_auto",
    strategy="mesh_blocks",
    reason="mesh_xy_rectangular",
    workers=8,
    auto_shape="mesh_blocks",
    effective_workers=2,
    partition_count=2,
    partition_map=r"1:\[0,1\];2:\[2,3\]",
    note_regex=(
        r"^PARALLEL_NOC_NOTE requested_mode=parallel requested_workers=8 "
        r"effective_mode=parallel effective_workers=2 "
        r"reason=parallel mode reduced worker count to 2 for 2 partitions$"
    ),
)
