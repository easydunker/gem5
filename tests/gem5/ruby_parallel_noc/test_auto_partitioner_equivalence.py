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
    name="ruby-parallel-noc-topology-auto-equivalence",
    fixtures=(),
    verifiers=(
        NamedMatchRegex(
            "parallel-noc-mode-line",
            r"^PARALLEL_NOC_MODE=parallel REQUESTED=parallel "
            r"WORKERS=2 NUM_CPUS=4$",
        ),
        NamedMatchRegex(
            "parallel-noc-partitioner-line",
            r"^PARALLEL_NOC_PARTITIONER requested=topology_auto "
            r"strategy=mesh_blocks "
            r"reason=mesh_xy_rectangular "
            r"auto_shape=mesh_blocks requested_workers=auto "
            r"effective_workers=2 routers=4 partitions=2$",
        ),
        NamedMatchRegex(
            "parallel-noc-topology-line",
            r"^PARALLEL_NOC_TOPOLOGY topology=Mesh_XY rows=2 cols=2 "
            r"routers=0,1,2,3$",
        ),
        NamedMatchRegex(
            "parallel-noc-topology-links-line",
            r"^PARALLEL_NOC_TOPOLOGY_LINKS "
            r"links=0>1,0>2,1>0,1>3,2>0,2>3,3>1,3>2$",
        ),
        NamedMatchRegex(
            "parallel-noc-topology-owners-line",
            r"^PARALLEL_NOC_TOPOLOGY_ATTACH "
            r"owners=0:\[cpu:0,cpu_port:0,ctrl:dir_cntrl0,ctrl:l1_cntrl0,"
            r"ext:0,ext:4,netif:0,netif:4\];"
            r"1:\[cpu:1,cpu_port:1,ctrl:dir_cntrl1,ctrl:l1_cntrl1,"
            r"ext:1,ext:5,netif:1,netif:5\];"
            r"2:\[cpu:2,cpu_port:2,ctrl:dir_cntrl2,ctrl:l1_cntrl2,"
            r"ext:2,ext:6,netif:2,netif:6\];"
            r"3:\[cpu:3,cpu_port:3,ctrl:dir_cntrl3,ctrl:l1_cntrl3,"
            r"ext:3,ext:7,netif:3,netif:7\]$",
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
        "auto",
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
