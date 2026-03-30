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


def add_large_mesh_suite(name, auto_shape, strategy, reason, partition_map):
    gem5_verify_config(
        name=name,
        fixtures=(),
        verifiers=(
            NamedMatchRegex(
                "parallel-noc-mode-line",
                r"^PARALLEL_NOC_MODE=parallel REQUESTED=parallel "
                r"WORKERS=4 NUM_CPUS=16$",
            ),
            NamedMatchRegex(
                "parallel-noc-coordinator-line",
                r"^PARALLEL_NOC_COORDINATOR mode=parallel workers=4$",
            ),
            NamedMatchRegex(
                "parallel-noc-partition-line",
                r"^PARALLEL_NOC_PARTITION partitions=16 queues=1,2,3,4 "
                r"sim_quantum=1$",
            ),
            NamedMatchRegex(
                "parallel-noc-partitioner-line",
                rf"^PARALLEL_NOC_PARTITIONER requested=topology_auto "
                rf"strategy={strategy} reason={reason} "
                rf"auto_shape={auto_shape} requested_workers=auto "
                rf"effective_workers=4 routers=16 partitions=4$",
            ),
            NamedMatchRegex(
                "parallel-noc-partition-map-line",
                rf"^PARALLEL_NOC_PARTITION_MAP queues={partition_map}$",
            ),
            NamedMatchRegex(
                "parallel-noc-topology-line",
                r"^PARALLEL_NOC_TOPOLOGY topology=Mesh_XY rows=4 cols=4 "
                r"routers=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15$",
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
            "--network-accel-max-workers",
            "4",
            "--network-accel-partitioner",
            "topology_auto",
            "--network-accel-auto-shape",
            auto_shape,
            "--network-accel-report-partitions",
            "--network",
            "garnet",
            "--topology",
            "Mesh_XY",
            "--num-cpus",
            "16",
            "--num-dirs",
            "16",
            "--mesh-rows",
            "4",
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


add_large_mesh_suite(
    name="ruby-parallel-noc-large-mesh-blocks",
    auto_shape="mesh_blocks",
    strategy="mesh_blocks",
    reason="mesh_xy_rectangular",
    partition_map=r"1:\[0,1,4,5\];2:\[2,3,6,7\];3:\[8,9,12,13\];4:\[10,11,14,15\]",
)

add_large_mesh_suite(
    name="ruby-parallel-noc-large-mesh-strips",
    auto_shape="mesh_strips",
    strategy="mesh_strips",
    reason="mesh_xy_strips",
    partition_map=r"1:\[0,1,2,3\];2:\[4,5,6,7\];3:\[8,9,10,11\];4:\[12,13,14,15\]",
)

