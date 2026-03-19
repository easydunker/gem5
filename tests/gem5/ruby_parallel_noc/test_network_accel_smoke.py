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


def add_smoke_suite(name, mode, workers):
    effective_mode = mode
    effective_workers = workers
    note_regex = None
    partition_regex = None
    if mode == "parallel":
        partition_regex = (
            r"^PARALLEL_NOC_PARTITION partitions=4 queues=1,2,3 "
            r"sim_quantum=1$"
        )
        metric_regex = (
            r"^PARALLEL_NOC_METRIC tick=2000 exit_tick=2001 cause=Network "
            r"Tester completed simCycles$"
        )
    else:
        metric_regex = (
            r"^PARALLEL_NOC_METRIC tick=2000 exit_tick=2000 cause=Network "
            r"Tester completed simCycles$"
        )

    verifiers = [
        NamedMatchRegex(
            "parallel-noc-mode-line",
            rf"^PARALLEL_NOC_MODE={effective_mode} REQUESTED={mode} "
            rf"WORKERS={effective_workers} NUM_CPUS=4$",
        ),
        NamedMatchRegex(
            "parallel-noc-coordinator-line",
            rf"^PARALLEL_NOC_COORDINATOR mode={effective_mode} "
            rf"workers={effective_workers}$",
        ),
    ]
    if note_regex:
        verifiers.append(
            NamedMatchRegex("parallel-noc-note-line", note_regex)
        )
    if partition_regex:
        verifiers.append(
            NamedMatchRegex("parallel-noc-partition-line", partition_regex)
        )
    verifiers.extend(
        [
            NamedMatchRegex(
                "parallel-noc-metric-line",
                metric_regex,
            ),
            NamedMatchRegex(
                "parallel-noc-stats-line",
                r"^PARALLEL_NOC_STATS path=.*[/\\]stats\.txt exists=True$",
            ),
            NamedStatsFileExists("parallel-noc-stats-file-exists"),
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
        config_args=[
            "--parallel-noc-mode",
            mode,
            "--parallel-noc-workers",
            str(workers),
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


add_smoke_suite(
    name="ruby-parallel-noc-serial-batched-smoke",
    mode="serial_batched",
    workers=2,
)
add_smoke_suite(
    name="ruby-parallel-noc-parallel-smoke",
    mode="parallel",
    workers=3,
)
