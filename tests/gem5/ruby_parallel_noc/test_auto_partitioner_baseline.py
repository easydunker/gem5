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


gem5_verify_config(
    name="ruby-parallel-noc-auto-partitioner-baseline",
    fixtures=(),
    verifiers=(
        NamedMatchRegex(
            "parallel-noc-mode-line",
            r"^PARALLEL_NOC_MODE=parallel REQUESTED=parallel "
            r"WORKERS=2 NUM_CPUS=4$",
        ),
        NamedMatchRegex(
            "parallel-noc-coordinator-line",
            r"^PARALLEL_NOC_COORDINATOR mode=parallel workers=2$",
        ),
        NamedMatchRegex(
            "parallel-noc-partition-line",
            r"^PARALLEL_NOC_PARTITION partitions=2 queues=1,2 "
            r"sim_quantum=1$",
        ),
        NamedMatchRegex(
            "parallel-noc-partitioner-line",
            r"^PARALLEL_NOC_PARTITIONER requested=topology_auto "
            r"strategy=mesh_blocks reason=mesh_xy_rectangular "
            r"auto_shape=mesh_blocks requested_workers=3 "
            r"effective_workers=2 routers=4 partitions=2$",
        ),
        NamedMatchRegex(
            "parallel-noc-partition-map-line",
            r"^PARALLEL_NOC_PARTITION_MAP queues=1:\[0,1\];2:\[2,3\]$",
        ),
        NamedMatchRegex(
            "parallel-noc-note-line",
            r"^PARALLEL_NOC_NOTE requested_mode=parallel "
            r"requested_workers=3 effective_mode=parallel "
            r"effective_workers=2 reason=parallel mode reduced worker count "
            r"to 2 for 2 partitions$",
        ),
        NamedMatchRegex(
            "parallel-noc-runtime-line",
            r"^PARALLEL_NOC_RUNTIME entered=0:1,1:1,2:1 "
            r"dispatches=0:\d+,1:\d+,2:\d+$",
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
    ),
    config=joinpath(
        config.base_dir,
        "tests",
        "gem5",
        "ruby_parallel_noc",
        "configs",
        "ruby_garnet_equiv.py",
    ),
    config_args=[
        "--network-accel-mode",
        "parallel",
        "--network-accel-workers",
        "3",
        "--network-accel-partitioner",
        "topology_auto",
        "--network-accel-auto-shape",
        "mesh_blocks",
        "--network-accel-report-partitions",
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
    ],
    valid_isas=(constants.null_tag,),
    valid_hosts=constants.supported_hosts,
    length=constants.quick_tag,
    protocol="Garnet_standalone",
    uses_kvm=False,
)
