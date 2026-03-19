# gem5 Test Environment Setup Runbook (Docker-First, Step-by-Step)

> **For agentic workers:** Execute this checklist in order. Do not skip steps.  
> **Intent:** No product code changes. Only environment setup, configuration guideline updates, and test/example execution.

**Goal:** Make this repo testable in a reproducible Docker environment, with clear procedures for running existing tests/examples and recording outcomes.

**Scope target:** After setup, workers should be able to run the repo’s existing tests/examples (at least `quick` suite first, then `long`/`very-long` in batches) from container with repeatable commands.

**Current NoC-work focus:** For multicore NoC simulation work, validate against the
existing Garnet-based baseline workloads while keeping Garnet itself unchanged.
The most relevant artifacts for this path are `build/Garnet_standalone/gem5.opt`
for direct baseline runs and `build/NULL_Garnet_standalone/gem5.opt` for the
`tests/main.py` harness-driven `ruby_parallel_noc` suite.

---

## 0. Pre-Flight Checklist (must pass before proceeding)

- [x] `pwd` is repo root (`.../gem5`).
- [x] Docker CLI is available: `docker --version`.
- [x] Docker daemon is reachable: `docker ps`.
- [x] Disk has enough free space for build + test outputs.
- [ ] Network access is available for image pull/resource download.

If daemon or network fails, stop and log blocker in notes file.

---

## 1. Select Container Image

### 1.1 Preferred path: prebuilt GHCR image

- [ ] Pull official test image:

```bash
docker pull ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest
```

- [ ] Confirm test image exists locally:

```bash
docker images | grep 'ghcr.io/gem5/ubuntu-24.04_all-dependencies'
```

- [ ] Optional: pull official devcontainer image if you need the broader
  development environment rather than the leaner test image:

```bash
docker pull ghcr.io/gem5/devcontainer:latest
```

### 1.2 Fallback path: build local image from repo Dockerfile

Only run if 1.1 fails.

- [ ] Build local image:

```bash
docker build \
  -f util/dockerfiles/ubuntu-24.04_all-dependencies/Dockerfile \
  -t gem5-local:ubuntu24-alldeps \
  .
```

- [ ] Confirm local image:

```bash
docker images | grep 'gem5-local:ubuntu24-alldeps'
```

### 1.3 Set image variable for downstream commands

- [ ] Set one of the following and keep it for all steps:

```bash
export GEM5_DOCKER_IMAGE=ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest
# or
export GEM5_DOCKER_IMAGE=gem5-local:ubuntu24-alldeps
```

---

## 2. Build gem5 in Container

- [ ] Run build:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -w /workspace \
  "$GEM5_DOCKER_IMAGE" \
  scons build/ALL/gem5.opt -j2
```

On Apple Silicon/macOS with Docker Desktop, use a small fixed `-j` value such
as `-j2`. Host-side `nproc` is not portable to macOS, and higher parallelism
can trigger Docker VM instability or compiler OOM kills before any meaningful
compiler diagnostics appear.

- [ ] Verify artifact:

```bash
test -x build/ALL/gem5.opt
```

- [ ] Record build metadata:

```bash
./build/ALL/gem5.opt --version || true
```

### 2.1 Minimal NoC-baseline build path

For the current multicore NoC simulation scope, prefer the smallest correct
build target instead of `build/ALL/gem5.opt`.

- [ ] Build direct baseline binary:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -w /workspace \
  "$GEM5_DOCKER_IMAGE" \
  bash -lc 'scons build/Garnet_standalone/gem5.opt -j2 2>&1' \
  | tee /tmp/garnet-standalone-build-j2.log
```

- [ ] Verify direct baseline artifact:

```bash
test -x build/Garnet_standalone/gem5.opt
```

- [ ] If running the harness suite, allow `tests/main.py` to build the suite
  target or prebuild it explicitly:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -w /workspace \
  "$GEM5_DOCKER_IMAGE" \
  bash -lc 'scons build/NULL_Garnet_standalone/gem5.opt -j2 2>&1' \
  | tee /tmp/null-garnet-standalone-build-j2.log
```

- [ ] Verify harness artifact if built explicitly:

```bash
test -x build/NULL_Garnet_standalone/gem5.opt
```

---

## 3. Verify Test Harness Wiring

- [ ] Sanity check test harness:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace/tests \
  "$GEM5_DOCKER_IMAGE" \
  ./main.py -h
```

- [ ] List candidate suites (machine-readable):

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace/tests \
  "$GEM5_DOCKER_IMAGE" \
  ./main.py list -q --suites gem5 > /tmp/gem5_suites.txt
```

- [ ] Confirm suite list is non-empty:

```bash
test -s /tmp/gem5_suites.txt
```

If empty, run `./main.py list -vv gem5` and log filter tags + blockers.

---

## 4. Run Existing Quick Tests (Baseline)

### 4.1 Run default quick suite

- [ ] Execute:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace/tests \
  "$GEM5_DOCKER_IMAGE" \
  ./main.py run --skip-build
```

### 4.2 If too large for one pass, run by UID batches

- [ ] Pick small subset first:

```bash
head -n 20 /tmp/gem5_suites.txt
```

- [ ] Run each selected suite:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace/tests \
  "$GEM5_DOCKER_IMAGE" \
  ./main.py run --skip-build --uid <SuiteUID>
```

### 4.3 Existing examples check

- [ ] List stdlib example suite UIDs:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace/tests \
  "$GEM5_DOCKER_IMAGE" \
  ./main.py list -q --suites gem5/example_configs/stdlib > /tmp/gem5_stdlib_suites.txt
```

- [ ] Run the selected stdlib example suite(s) by UID:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace/tests \
  "$GEM5_DOCKER_IMAGE" \
  ./main.py run --skip-build --uid <StdlibSuiteUID>
```

Note: `tests/main.py` discovers directories, not individual test file paths. The
`gem5/example_configs/stdlib` package currently exposes multiple suites; four are
`quick`, and one is `long`.

---

## 5. Run New Configuration-Guideline Test Package

These validate new testing guidelines and baseline compatibility.

- [ ] List ruby-parallel-noc suite UIDs:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace/tests \
  "$GEM5_DOCKER_IMAGE" \
  ./main.py list -vv --suites gem5/ruby_parallel_noc
```

- [ ] If suite UIDs are present, run by UID:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace/tests \
  "$GEM5_DOCKER_IMAGE" \
  ./main.py run --skip-build --uid <RubyParallelNocSuiteUID>
```

- [ ] Confirm output contains:
  - [ ] `PARALLEL_NOC_MODE=off REQUESTED=off`
  - [ ] `PARALLEL_NOC_METRIC tick=... cause=...`

If `list -vv --suites gem5/ruby_parallel_noc` returns no selectable suites,
record the blocker before attempting to run by file path. The current workspace
may have duplicate generated test UIDs in this package.

Amendment:
- [x] Direct baseline run works with a same-source Docker-built
  `build/Garnet_standalone/gem5.opt`.
- [x] The duplicate verifier UID blocker in
  `tests/gem5/ruby_parallel_noc/test_equivalence.py` was fixed by giving the
  verifier subtests distinct names.
- [x] The suite metadata was corrected to target
  `NULL_Garnet_standalone`, producing the selectable suite UID:
  `SuiteUID:tests/gem5/ruby_parallel_noc/test_equivalence.py:ruby-parallel-noc-baseline-off-NULL-aarch64-opt-Garnet_standalone`
- [ ] The harness-driven suite run is still pending final result while
  `build/NULL_Garnet_standalone/gem5.opt` builds in Docker.
- [x] Verified direct baseline command:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  bash -lc 'rm -rf /tmp/ruby_parallel_noc_smoke && mkdir -p /tmp/ruby_parallel_noc_smoke && \
    /workspace/build/Garnet_standalone/gem5.opt \
      --outdir=/tmp/ruby_parallel_noc_smoke \
      /workspace/tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py \
      --parallel-noc-mode off \
      --parallel-noc-workers 1 \
      --network garnet \
      --topology Mesh_XY \
      --num-cpus 4 \
      --num-dirs 4 \
      --mesh-rows 2 \
      --sim-cycles 2000 \
      --synthetic uniform_random \
      --injectionrate 0.02 \
      --routing-algorithm 1'
```

- [x] Verified direct output contains:
  - `PARALLEL_NOC_MODE=off REQUESTED=off WORKERS=1 NUM_CPUS=4`
  - `PARALLEL_NOC_METRIC tick=2000 cause=Network Tester completed simCycles`
- [x] Verified existing canonical baseline example:
  - `configs/example/garnet_synth_traffic.py`
  - Output: `Exiting @ tick 2000 because Network Tester completed simCycles`

---

## 6. Full Coverage Expansion (Operational Target)

For “all existing tests/examples runnable and passed”, execute in stages:

- [ ] `quick`: `./main.py run --skip-build`
- [ ] `long`: `./main.py run --skip-build --length=long`
- [ ] `very-long`: `./main.py run --skip-build --length=very-long`

Practical rule:
- [ ] Batch by `--uid` for reliability and resume control.
- [ ] Save failing suite UIDs.
- [ ] Use `./main.py rerun` after fixes/retries.

---

## 7. Optional Benchmark Baseline (for later multicore feature)

Non-gating, manual:

- [ ] Run:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -w /workspace \
  "$GEM5_DOCKER_IMAGE" \
  python3 tests/gem5/ruby_parallel_noc/compare_perf.py \
    --gem5-bin build/ALL/gem5.opt \
    --mode parallel \
    --workers 4 \
    --repeats 3
```

- [ ] Archive median times and speedup output.

---

## 8. Completion Checklist

- [ ] Container image selected and documented.
- [ ] `build/ALL/gem5.opt` built in container.
- [x] Minimal relevant NoC baseline binary `build/Garnet_standalone/gem5.opt`
  built in container.
- [ ] Existing quick tests run (or UID-batched equivalent).
- [ ] Existing example test file run (or UID equivalent).
- [ ] `tests/gem5/ruby_parallel_noc/test_equivalence.py` passed via harness.
- [x] Results/commands/errors recorded in memory notes file.

---

## 9. Failure Handling Checklist

- [x] If `docker pull` fails: use local Dockerfile build.
- [x] If Dockerfile build fails: capture error + image fallback decision.
- [ ] If suite count is zero: run `list -vv`, inspect tags, execute with `--uid`.
- [ ] If permissions fail: keep `-u $(id -u):$(id -g)` and verify mount path.
- [ ] If resource download fails in tests: retry with network and record transient vs deterministic failure.
- [x] If build fails with `cc1plus` killed under Docker Desktop: retry with low fixed parallelism (for example `-j2`) before trusting assembler fallout as the root cause.
- [x] If `ghcr.io/gem5/devcontainer:latest` binary fails against the checked-out source tree: treat it as a binary/source mismatch and use a same-source Docker build instead.

---

## 10. Amendments (2026-03-16)

### 10.1 Run Log (sequential execution)

- [x] Section 0 complete except network check.
  - `pwd` => `/Users/yingyi/personal/gem5`
  - `docker --version` => `Docker version 27.0.3, build 7d4bcd863a`
  - `docker ps` reachable
  - disk free => `166Gi` available on `/System/Volumes/Data`
- [x] Section 1.1 attempted with the original doc command.
  - `docker pull ghcr.io/gem5/gem5/ubuntu-24.04_all-dependencies:latest`
  - Result: `denied` from GHCR manifest access.
- [x] Section 1.1 amended after repo-doc verification.
  - Correct official image paths are `ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest` and `ghcr.io/gem5/devcontainer:latest`.
  - The extra `/gem5/` path segment in some docs is incorrect.
  - Re-run required with corrected image before deciding whether Section 1 is blocked.
- [ ] Section 1.1 re-run with corrected image path.
  - `docker pull ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest`
  - Current status: registry auth works, but the large layer repeatedly retries/restarts before the image is committed locally.
- [x] Section 1 completed after manual image pull.
  - `docker images` confirmed `ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest` locally.
- [x] Section 1.2 attempted after 1.1 failure.
  - `docker build --platform linux/amd64 -f util/dockerfiles/ubuntu-24.04_all-dependencies/Dockerfile -t gem5-local:ubuntu24-alldeps .`
  - Result (2 attempts): failed fetching Docker Hub anonymous token for `ubuntu:24.04` with `connection reset by peer`.
- [ ] Section 2 in progress after image became available.
  - Initial full build with high parallelism failed with `g++: fatal error: Killed signal terminated program cc1plus`, consistent with Docker VM memory pressure.
  - Retrying at `-j2` removed the OOM symptom but exposed a deterministic compile error in `src/arch/arm/kvm/armv8_cpu.cc`.
  - Current first deterministic errors:
    - `lookUpMiscReg` was not declared in this scope

### 10.2 Ruby/Garnet NoC Focus (2026-03-17)

- [x] Verified the current `ruby_parallel_noc` scope is baseline-only.
  - `tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py` accepts
    `serial_batched` and `parallel` flags but intentionally downgrades them to
    `off`.
  - No in-tree `GarnetBatchDriver` or equivalent parallel NoC implementation
    was found under `src/mem/ruby/network/garnet/`.
- [x] Verified the prebuilt devcontainer binary is not valid for this checkout.
  - `/usr/local/bin/gem5` from `ghcr.io/gem5/devcontainer:latest` fails against
    the current source tree with enum mismatch `Bf16Cvt` while importing
    `configs/common/Options.py`.
  - Practical rule: use same-source Docker builds for this repo checkout.
- [x] Built the minimal correct baseline binary for the NoC path:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -w /workspace \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  bash -lc 'scons build/Garnet_standalone/gem5.opt -j2 2>&1' \
  | tee /tmp/garnet-standalone-build-j2.log
```

  - Result: success; `build/Garnet_standalone/gem5.opt` produced.
- [x] Ran existing multicore Garnet/Ruby baseline config with the built binary.
  - Output confirmed:
    - `PARALLEL_NOC_MODE=off REQUESTED=off WORKERS=1 NUM_CPUS=4`
    - `PARALLEL_NOC_METRIC tick=2000 cause=Network Tester completed simCycles`
- [x] Ran existing canonical example `configs/example/garnet_synth_traffic.py`
  with the same built binary.
  - Output confirmed:
    - `Exiting @ tick 2000 because Network Tester completed simCycles`
- [x] Re-checked the package harness state.
  - `tests/main.py list -vv --suites gem5/ruby_parallel_noc` still fails to
    load selectable suites because `test_equivalence.py` defines duplicate
    autogenerated verifier UIDs.
    - `MISCREG_USR_NS_WR` and related `MISCREG_*` identifiers were not declared in this scope
  - `build/ALL/gem5.opt` still not produced.

### 10.2 New Setup Preconditions

- Added precondition: ensure registry access is valid before Section 1.
  - GHCR image path must be publicly accessible to this host, or `docker login ghcr.io` must be configured.
  - Use repo-consistent namespace `ghcr.io/gem5/<image>:<tag>` for pulls; valid images for this runbook are `ubuntu-24.04_all-dependencies` and `devcontainer`.
  - Do not insert an extra `/gem5/` path segment.
  - Docker Hub token endpoint (`https://auth.docker.io/token`) must be reachable for fallback Dockerfile base image pulls.
- If both 1.1 and 1.2 fail due network/auth, stop execution and record as `infra` blocker before any test invocation.

### 10.3 Setup Instruction Amendment

- `tests/main.py` positional discovery targets are directories, not individual test files.
- Bind-mount host `/tmp` into the container for harness and suite runs:
  `-v /tmp:/tmp`
  This avoids fixture setup failures from the container's default temporary
  filesystem running out of space.
- For Docker Desktop on Apple Silicon, start gem5 builds with `-j2`.
  Higher parallelism can produce `cc1plus` kills from Docker VM memory
  pressure, which then surface as misleading assembler parse errors.
- For package-specific execution:
  - list suites first with `./main.py list -q --suites <dir>`
  - then run selected suites with `./main.py run --skip-build --uid <SuiteUID>`
- Do not use `./main.py run <path/to/test_file.py>` as the primary instruction in this runbook; it can yield `0 suites` even when tests exist.

### 10.4 Failure Handling Status (current run)

- [x] If `docker pull` fails: use local Dockerfile build.
- [x] If Dockerfile build fails: capture error + image fallback decision.
- [ ] If suite count is zero: run `list -vv`, inspect tags, execute with `--uid`.
- [ ] If permissions fail: keep `-u $(id -u):$(id -g)` and verify mount path.
- [ ] If resource download fails in tests: retry with network and record transient vs deterministic failure.
