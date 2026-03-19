# Copyright (c) 2026
# All rights reserved.

"""
Baseline correctness test for future Ruby/Garnet parallel NoC work.

This test is intentionally single-core-host safe:
- It only checks baseline "off" mode today.
- It should pass before multicore NoC feature implementation.
"""

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
    name="ruby-parallel-noc-baseline-off",
    fixtures=(),
    verifiers=(
        NamedMatchRegex(
            "parallel-noc-mode-line",
            r"^PARALLEL_NOC_MODE=off REQUESTED=off .*",
        ),
        NamedMatchRegex(
            "parallel-noc-output-summary",
            r"^Exiting @ tick 2000 because Network Tester completed "
            r"simCycles$",
        ),
        NamedMatchRegex(
            "parallel-noc-metric-line",
            r"^PARALLEL_NOC_METRIC tick=2000 exit_tick=2000 cause=Network "
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
        "--parallel-noc-mode",
        "off",
        "--parallel-noc-workers",
        "1",
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
