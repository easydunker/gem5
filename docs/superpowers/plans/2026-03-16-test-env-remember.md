# gem5 Test Environment Memory Notes

## Purpose

This file records non-obvious setup/runtime facts that downstream workers should
remember when running build/tests in this repo.

---

## Environment Facts (observed)

- Docker CLI is available.
- Docker daemon access may require elevated permission in restricted harnesses.
- Host Python had missing `pytest`; prefer containerized test execution.
- `tests/main.py` can run even when no suites are selected (watch for `0 suites`).
- GHCR pull for `ghcr.io/gem5/gem5/ubuntu-24.04_all-dependencies:latest` returned `denied`; that path is inconsistent with repo CI and Docker docs.
- Repo workflows and current Docker usage expect `ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest`.
- Another valid official image namespace is `ghcr.io/gem5/devcontainer:latest`.
- Local Dockerfile fallback currently depends on Docker Hub token endpoint reachability for `ubuntu:24.04`.
- `tests/main.py` discovers directory roots; passing a single test file path to `run` can produce `0 suites`.
- `ghcr.io/gem5/devcontainer:latest` includes a prebuilt binary at `/usr/local/bin/gem5` (not `gem5.opt`).
- The `ruby_parallel_noc` baseline path needs `build/Garnet_standalone/gem5.opt`, not `build/NULL/gem5.opt` and not `build/ALL/gem5.opt`.
- The `ruby_parallel_noc` harness suite path targets `build/NULL_Garnet_standalone/gem5.opt`.

---

## Execution Rules

- Always run build/tests from container unless explicitly debugging host issues.
- Always build `build/ALL/gem5.opt` before running system-level tests.
- Always mount repo with:
  - `-v "$PWD":/workspace`
  - `-w /workspace` (or `/workspace/tests` for harness commands)
  - `-u $(id -u):$(id -g)` to avoid root-owned artifacts.
- For harness/test runs, also mount host tmp:
  - `-v /tmp:/tmp`
- For `tests/gem5/ruby_parallel_noc`, prefer a same-source
  `build/Garnet_standalone/gem5.opt` build for direct config execution.
- For the harness-driven `ruby_parallel_noc` suite, use or allow build of
  `build/NULL_Garnet_standalone/gem5.opt`.

---

## Common Pitfalls

1. `0 suites` from `tests/main.py run <file>`
- Cause: positional inputs are discovery directories, not test-file selectors.
- Fix: list suites with `./main.py list -q --suites <dir>` and run by `--uid`.

2. Confusing “all tests pass” target
- `quick`, `long`, `very-long` are separate scopes; run in stages.
- Use batching by UID and `rerun` to recover from transient failures.

3. Network/resource flakiness
- Some example tests may fetch resources; classify failures as transient vs deterministic.
- Base-image fetch can fail before build/tests begin (`auth.docker.io` connection reset); treat as `infra`.

4. Container `/tmp` exhaustion
- Some suites create output directories under `/tmp`; without `-v /tmp:/tmp`, fixture setup can fail with `OSError: [Errno 28] No space left on device`.
- This failure can cascade into noisy result-handler exceptions; record the first `/tmp` space error as the primary cause.

5. Performance comparisons
- Do not gate CI on wall-clock speedup.
- Keep perf checks manual and report medians across repeats.

6. Docker Desktop build instability
- High-parallelism `scons build/ALL/gem5.opt` runs on Apple Silicon Docker Desktop can fail with `g++: fatal error: Killed signal terminated program cc1plus`.
- The assembler errors that follow are secondary fallout from truncated compiler output, not the primary root cause.
- Retrying with low fixed parallelism such as `-j2` is the right first diagnostic step.

7. Deterministic compile error after OOM is removed
- After increasing Docker memory and retrying at `-j2`, the build progressed further but failed deterministically in `src/arch/arm/kvm/armv8_cpu.cc`.
- The first real errors were unresolved identifiers:
  - `lookUpMiscReg`
  - `MISCREG_USR_NS_WR` and related `MISCREG_*`
- These identifiers are declared in `src/arch/arm/regs/misc_info.hh`, suggesting a missing include or stale file inconsistency in the ARM KVM codepath.

8. Devcontainer binary mismatch
- `/usr/local/bin/gem5` from `ghcr.io/gem5/devcontainer:latest` can fail
  against this checkout with enum mismatch `Bf16Cvt` while importing
  `configs/common/Options.py`.
- Treat that as a source/binary mismatch, not as a Ruby/Garnet config bug.
- Use a same-source Docker-built binary for repo validation.

9. ruby_parallel_noc harness state
- The duplicate verifier UID issue in `test_equivalence.py` was fixed by giving
  the verifier subtests distinct names.
- The suite metadata was corrected to target the `NULL_Garnet_standalone`
  harness build path.
- Direct config execution still remains the fastest baseline validation path:
  `tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py`.

---

## Logging Requirements

For each run session, record:

- Container image used.
- Build command and build result.
- Test command(s) and outcome summary:
  - total suites run
  - passed
  - failed
  - skipped
- For failures:
  - suite UID
  - first error line
  - classification (`infra`, `flaky`, `deterministic code issue`).

---

## Hand-off Checklist

- [ ] Build artifact exists: `build/ALL/gem5.opt`.
- [x] Command transcript saved (or summarized).
- [ ] Failed UIDs list persisted.
- [ ] Next worker can resume directly from failed UID batch.
- [x] Alternate relevant build artifact exists: `build/Garnet_standalone/gem5.opt`.
- [x] Harness build artifact exists: `build/NULL_Garnet_standalone/gem5.opt`.

---

## Session Update (2026-03-16)

- Container image used: none selected yet; original runbook path was wrong.
- Build command attempted:
  - `docker build --platform linux/amd64 -f util/dockerfiles/ubuntu-24.04_all-dependencies/Dockerfile -t gem5-local:ubuntu24-alldeps .`
  - Outcome: failed twice before layer build due Docker Hub token fetch reset (`infra`).
- Test commands attempted: none (blocked before image/build).
- Failure records:
  - `image_pull_ghcr_latest` -> `denied` (`infra`)
  - `dockerfile_base_pull_ubuntu_24_04` -> `connection reset by peer` (`infra`)

## Session Update Addendum (2026-03-16)

- Verified from repo workflows/docs that the intended image is `ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest`.
- Verified user clarification that `ghcr.io/gem5/devcontainer:latest` is also a correct official image.
- Re-test required with corrected GHCR namespace before treating Section 1 as blocked.
- Verified from `ext/testlib` that package-specific test execution should use directory discovery plus `--uid`, not direct file-path `run` commands.
- Verified that container test runs should mount host `/tmp` to avoid fixture setup failures from limited container tmp space.
- Retried official pull with the corrected image path; auth succeeds, but the large layer download is unstable and re-enters retry/download cycles instead of completing the image locally (`infra` until proven otherwise).
- Official image later became available locally after manual pull.
- Reproduced the full build failure systematically:
  - high parallelism caused Docker VM / `cc1plus` kill behavior
  - low parallelism (`-j2`) avoided the OOM symptom but still did not produce `build/ALL/gem5.opt`
  - deterministic failure is now `src/arch/arm/kvm/armv8_cpu.cc` unresolved `lookUpMiscReg` / `MISCREG_*` symbols (`deterministic code issue`)

## Session Update (2026-03-17)

- Verified the `ruby_parallel_noc` package is baseline-only today:
  - non-`off` modes are intentionally downgraded to `off`
  - no parallel NoC implementation exists yet under `src/mem/ruby/network/garnet`
- Verified `ghcr.io/gem5/devcontainer:latest` is not usable for this checkout's
  tests because the prebuilt `/usr/local/bin/gem5` fails with enum mismatch
  `Bf16Cvt` during Python config import (`source/binary mismatch`).
- Built the minimal correct same-source binary for the multicore Garnet/Ruby
  baseline:
  - `docker run --rm -u $(id -u):$(id -g) -v "$PWD":/workspace -w /workspace ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest bash -lc 'scons build/Garnet_standalone/gem5.opt -j2 2>&1' | tee /tmp/garnet-standalone-build-j2.log`
  - Outcome: success; `build/Garnet_standalone/gem5.opt` exists.
- Ran the existing `ruby_parallel_noc` baseline config directly in Docker with
  the built binary.
  - Outcome: success
  - Key output:
    - `PARALLEL_NOC_MODE=off REQUESTED=off WORKERS=1 NUM_CPUS=4`
    - `PARALLEL_NOC_METRIC tick=2000 cause=Network Tester completed simCycles`
- Ran the canonical existing example `configs/example/garnet_synth_traffic.py`
  with the same binary.
  - Outcome: success
  - Key output:
    - `Exiting @ tick 2000 because Network Tester completed simCycles`
- Re-checked the harness package load path:
  - `docker run ... ./main.py list -vv --suites gem5/ruby_parallel_noc`
  - Old outcome: blocked by `DuplicateTestItemException`
  - Old classification: `deterministic test harness issue`

## Session Update Addendum (2026-03-17, later)

- Fixed `tests/gem5/ruby_parallel_noc/test_equivalence.py` so the two verifier
  subtests no longer generate duplicate test UIDs.
- Corrected the suite metadata to use:
  - `valid_isas=(constants.null_tag,)`
  - `protocol="Garnet_standalone"`
- Re-ran suite discovery in Docker:
  - `docker run ... ./main.py list -vv --suites gem5/ruby_parallel_noc`
  - Outcome: success
  - Selectable suite UID:
    - `SuiteUID:tests/gem5/ruby_parallel_noc/test_equivalence.py:ruby-parallel-noc-baseline-off-NULL-aarch64-opt-Garnet_standalone`
- Started the harness suite run in Docker:
  - `docker run ... ./main.py run -vv --uid 'SuiteUID:tests/gem5/ruby_parallel_noc/test_equivalence.py:ruby-parallel-noc-baseline-off-NULL-aarch64-opt-Garnet_standalone'`
  - Current state at handoff: still building `build/NULL_Garnet_standalone/gem5.opt`
  - Classification: `in_progress`

## Session Update Addendum (2026-03-17, RISCV setup validation)

- Re-read the Docker setup runbook and memory notes before execution.
- Confirmed the official Docker test image is present locally:
  - `ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest`
- Confirmed Docker daemon access works:
  - `docker ps`
  - Outcome: success
- Chose a lighter validation path instead of re-running `build/ALL/gem5.opt`:
  - rationale: user only needed setup verification, and RISCV is sufficient for
    that scope.
- Built a fresh same-source RISCV binary in Docker with the user-requested
  parallelism:
  - `docker run --rm -u $(id -u):$(id -g) -v "$PWD":/workspace -w /workspace ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest bash -lc 'scons build/RISCV/gem5.opt -j4 2>&1' | tee /tmp/riscv-gem5-build-j4.log`
  - Outcome: success
  - Fresh artifact timestamp observed:
    - `build/RISCV/gem5.opt` -> `Mar 17 21:59:50 2026`
- Verified the test harness entrypoint inside the container:
  - `docker run --rm -u $(id -u):$(id -g) -v "$PWD":/workspace -v /tmp:/tmp -w /workspace/tests ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest ./main.py -h`
  - Outcome: success
- Listed `hello_se` suite UIDs to confirm the harness can still discover tests:
  - `docker run --rm -u $(id -u):$(id -g) -v "$PWD":/workspace -v /tmp:/tmp -w /workspace/tests ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest ./main.py list -q --suites gem5/se_mode/hello_se`
  - Outcome: success
  - Notable observation: RISCV hello cases are discoverable, but the suite UID
    naming still uses the generic `ALL-aarch64-opt` suffix, so direct config
    execution is the cleaner RISCV-only validation path.
- Ran an end-to-end direct RISCV SE hello workload with the freshly built
  binary:
  - `docker run --rm -u $(id -u):$(id -g) -v "$PWD":/workspace -w /workspace ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest bash -lc 'build/RISCV/gem5.opt tests/gem5/se_mode/hello_se/configs/simple_binary_run.py riscv-hello timing --resource-directory tests/gem5/resources riscv'`
  - Outcome: success
  - Key output:
    - `Resource 'riscv-hello' was not found locally. Downloading ...`
    - `Finished downloading resource 'riscv-hello'.`
    - `Hello world!`
    - `Exiting @ tick 434864700 because exiting with last active thread context.`
- Classification summary for this session:
  - Docker image availability: `pass`
  - RISCV build path with `-j4`: `pass`
  - Harness entrypoint wiring: `pass`
  - Resource download path: `pass`
  - Direct RISCV workload execution: `pass`
