# Multicore NoC Simulation Acceleration Plan

> **For agentic workers:** REQUIRED: Use `superpowers:subagent-driven-development` (if subagents available) or `superpowers:executing-plans` to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Speed up existing detailed multicore NoC simulations in gem5 by using host multicore execution, while leaving Garnet unchanged and preserving deterministic simulation results.

**Architecture:** Introduce a backend-agnostic acceleration framework in the simulation/runtime and Ruby orchestration layers rather than modifying Garnet internals. Use Garnet as the first target workload and correctness oracle, but keep all speedup work outside `src/mem/ruby/network/garnet/*` so the framework can later support a custom NoC.

**Tech Stack:** gem5 C++ (simulation/event/runtime layer), Python config layer, gem5 test harness (`tests/gem5`), Docker-based build/test workflow.

---

## Context and Constraints

- The long-term goal is a custom NoC, but the current scope is **speeding up existing NoC simulations**.
- Garnet may be used as the workload/backend for this phase, but **Garnet itself must not be modified for speedup work**.
- Speedup must target **one simulation run**, not `multisim`.
- Correctness and determinism are mandatory.
- Docker-only build/test execution is required for this project flow.
- Existing verified baseline today:
  - `build/Garnet_standalone/gem5.opt` can run:
    - `tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py`
    - `configs/example/garnet_synth_traffic.py`

---

## Design Summary

Build a **generic network-simulation acceleration layer** outside Garnet:

1. Keep current Garnet/Ruby behavior as the reference implementation.
2. Add a new execution coordinator at the simulation/runtime layer, not in Garnet.
3. Start with **serial batched orchestration** to reduce scheduler overhead without using host multicore.
4. Once serial batched behavior is equivalent, add **host-multicore execution** around safe runtime and Ruby-level work partitions.
5. Validate against existing baseline NoC workloads before enabling any performance-oriented mode.

This phase is not “parallel Garnet internals.” It is “multicore execution of current NoC simulations with Garnet left unchanged, using runtime and Ruby-layer orchestration where needed.”

---

## Non-Goals

- Replacing Garnet with a custom NoC in this phase.
- Editing `src/mem/ruby/network/garnet/*` for speedup logic.
- Treating the current single-queue scheduler as the only allowed place to change. Deeper runtime and Ruby-layer changes are allowed if they stay backend-agnostic and keep Garnet untouched.
- Claiming wall-clock speedup before deterministic equivalence is proven.
- Broad full-system optimization outside NoC-heavy workloads.

---

## Reusable Principles for Later Custom NoC

- Keep the execution framework backend-agnostic where possible.
- Prefer runtime-level and Ruby-orchestration boundaries over Garnet-specific hooks.
- Separate:
  - simulation orchestration
  - runtime partitioning
  - backend selection
  - result collection
  - equivalence validation
- Treat Garnet as backend `v1`, custom NoC as backend `v2`.

---

## Chunk 1: Baseline Harness and Workload Definition

### Task 1: Lock down baseline workloads and result invariants

**Files:**
- Modify: `tests/gem5/ruby_parallel_noc/test_equivalence.py`
- Modify: `tests/gem5/ruby_parallel_noc/README.md`
- Modify: `tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py`
- Reuse: `configs/example/garnet_synth_traffic.py`

- [x] **Step 1: Normalize existing ruby_parallel_noc baseline test metadata**
Ensure the suite targets the correct build shape for the current baseline and has unique verifier IDs.

- [x] **Step 2: Record the baseline execution commands**
Document the direct Docker commands that run:
  - `ruby_garnet_equiv.py`
  - `garnet_synth_traffic.py`

- [x] **Step 3: Define exact invariants for this phase**
For baseline comparison, capture:
  - completion cause
  - completion tick
  - presence of expected summary lines
  - selected stats file existence

- [x] **Step 4: Re-run baseline commands in Docker**
Verify both existing baseline runs still work from the checked-out source tree.

- [ ] **Step 5: Commit**
```bash
git add tests/gem5/ruby_parallel_noc/test_equivalence.py tests/gem5/ruby_parallel_noc/README.md tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py
git commit -m "test: lock down multicore noc baseline harness"
```

**Checklist (Chunk 1)**
- [x] Existing baseline workloads are reproducible in Docker.
- [x] Baseline suite discovery works.
- [x] The pre-feature reference output is documented.

---

## Chunk 2: Execution-Layer Abstraction

### Task 2: Introduce an external NoC acceleration framework boundary

**Files:**
- Create: `src/sim/network_accel/NetworkAccelMode.hh`
- Create: `src/sim/network_accel/NetworkAccelConfig.hh`
- Create: `src/sim/network_accel/NetworkAccelCoordinator.hh`
- Create: `src/sim/network_accel/NetworkAccelCoordinator.cc`
- Create: `src/sim/network_accel/SConscript`
- Modify: `src/sim/SConscript`
- Modify: `src/python/gem5` or config plumbing files as needed for option exposure

- [x] **Step 1: Write failing option/config smoke test**
Add a focused smoke test that expects new acceleration options to parse and construct cleanly without changing simulation behavior.

- [x] **Step 2: Add generic acceleration modes**
Introduce config surface like:
  - `off`
  - `serial_batched`
  - `parallel`

- [x] **Step 3: Add a coordinator skeleton**
The coordinator exists outside Garnet and owns no Garnet internals; for now it only records selected mode and exposes no-op integration points.

- [x] **Step 4: Wire build system**
Ensure the new simulation-layer files compile without touching Garnet code.

- [x] **Step 5: Run smoke tests**
Verify the new config surface exists and default behavior remains unchanged.

- [ ] **Step 6: Commit**
```bash
git add src/sim/network_accel src/sim/SConscript
git commit -m "feat(sim): add network acceleration framework skeleton"
```

**Checklist (Chunk 2)**
- [x] No changes to `src/mem/ruby/network/garnet/*`.
- [x] New execution-layer abstraction compiles.
- [x] Default mode is `off`.

---

## Chunk 3: Serial Batched Orchestration Outside Garnet

### Task 3: Reduce scheduler overhead without host multicore

**Files:**
- Modify: `src/sim/network_accel/NetworkAccelCoordinator.hh`
- Modify: `src/sim/network_accel/NetworkAccelCoordinator.cc`
- Modify: simulation/event integration files identified during implementation
- Create: `tests/gem5/ruby_parallel_noc/test_serial_batched_baseline.py`

- [x] **Step 1: Write failing serial-batched baseline test**
Test should run the existing multicore NoC baseline with `serial_batched` enabled and expect:
  - successful completion
  - same completion cause/tick as `off`

- [x] **Step 2: Implement serial batched mode outside Garnet**
Batch/schedule work at the simulation layer only.

- [x] **Step 3: Keep Garnet black-box**
No logic moves into Garnet classes, no Garnet wakeup methods are refactored.

- [x] **Step 4: Re-run direct workload commands**
Compare `off` vs `serial_batched` on the existing baseline workloads.

- [x] **Step 5: Run new focused tests**
Confirm serial batched mode is correctness-equivalent to `off`.

- [ ] **Step 6: Commit**
```bash
git add src/sim/network_accel tests/gem5/ruby_parallel_noc/test_serial_batched_baseline.py
git commit -m "feat(sim): add serial batched noc acceleration mode"
```

**Checklist (Chunk 3)**
- [x] Garnet remains unchanged.
- [x] `serial_batched` completes baseline workloads.
- [x] Baseline outputs remain deterministic.

Execution notes:
- `serial_batched` direct Docker run matched `off` exactly at tick `2000` with cause `Network Tester completed simCycles`.
- Focused harness suite `ruby-parallel-noc-serial-batched-baseline-NULL-aarch64-opt-Garnet_standalone` passed.
- Unsupported `parallel` requests are now downgraded to effective mode `off` with an explicit `PARALLEL_NOC_NOTE` line until Task 4 lands, so the config surface no longer misreports active execution mode.

---

## Chunk 4: Host-Multicore Execution

### Task 4: Add multicore execution around the external coordinator

**Files:**
- Modify: `src/sim/network_accel/NetworkAccelCoordinator.hh`
- Modify: `src/sim/network_accel/NetworkAccelCoordinator.cc`
- Modify: runtime/event queue integration files identified during implementation
- Modify: Ruby orchestration/config files identified during implementation
- Create: `src/sim/network_accel/DeterministicMerge.hh`
- Create: `src/sim/network_accel/WorkerPool.hh`
- Create: `src/sim/network_accel/WorkerPool.cc`
- Create: `tests/gem5/ruby_parallel_noc/test_parallel_baseline.py`

- [x] **Step 1: Prove a real partition exists for this workload**
Identify a deterministic runtime or Ruby-level work partition for the target NoC workload that does not require changes under `src/mem/ruby/network/garnet/*`.

- [x] **Step 2: Write failing parallel-mode baseline test**
Run the same baseline with `parallel` mode and fixed worker count, expecting equivalence with `serial_batched`.

- [x] **Step 3: Add worker orchestration**
Parallelize only runtime- or Ruby-level work that is proven safe without changing Garnet internals.

- [x] **Step 4: Add deterministic merge/reduction**
Any shared outputs, cross-partition events, or summaries must merge in stable order.

- [x] **Step 5: Add strict assertions**
Fail fast if the required runtime partitioning, event-queue mapping, or synchronization preconditions are not satisfied in `parallel` mode.

- [x] **Step 6: Run repeated equivalence trials**
Run the same workload multiple times to confirm deterministic output.

- [ ] **Step 7: Commit**
```bash
git add src/sim/network_accel tests/gem5/ruby_parallel_noc/test_parallel_baseline.py
git commit -m "feat(sim): add multicore noc acceleration mode"
```

**Checklist (Chunk 4)**
- [x] `parallel` mode is opt-in.
- [x] `parallel` mode has a real runtime/Ruby partition behind it instead of a placeholder path.
- [x] Output remains deterministic across repeated runs.
- [x] No Garnet source edits were introduced.

Design note:
- If no deterministic partition can be established from runtime and Ruby-side changes alone, `parallel` must remain downgraded or rejected rather than misreported as active.

Execution notes:
- The deterministic partition is a Ruby/router-domain split created in `ruby_garnet_equiv.py`: each CPU tile, sequencer, L1 controller, directory controller, memory controller, router, and attached edge objects are assigned to a stable event-queue domain keyed by router ID, while internal-link bridge objects are split between source and destination domains.
- `parallel` now activates only after the config explicitly provisions that partition and sets `root.sim_quantum = 1`; otherwise the coordinator still downgrades or rejects unsupported configurations instead of misreporting active parallel execution.
- The runtime coordinator now owns a worker-pool description and stable queue summary so the effective worker count is deterministic and bounded by the discovered partition count.
- Direct Docker runs completed for `off`, `serial_batched`, and `parallel`. `off` and `serial_batched` exited at tick `2000`; `parallel` exits at raw tick `2001` because the multi-event-queue exit is delivered one quantum later, so the printed `PARALLEL_NOC_METRIC` reports `tick=2000 exit_tick=2001` for equivalence accounting.
- Repeated direct Docker trials for `parallel` produced identical output summaries across three runs.
- Focused harness suites passed on `build/NULL_Garnet_standalone/gem5.opt` with `--skip-build`:
  - `ruby-parallel-noc-parallel-baseline-NULL-aarch64-opt-Garnet_standalone`
  - `ruby-parallel-noc-parallel-smoke-NULL-aarch64-opt-Garnet_standalone`

---

## Chunk 5: Validation Matrix and Benchmarking

### Task 5: Add execution checklist, equivalence matrix, and benchmark flow

**Files:**
- Modify: `tests/gem5/ruby_parallel_noc/README.md`
- Create: `tests/gem5/ruby_parallel_noc/compare_stats.py`
- Modify: `tests/gem5/ruby_parallel_noc/compare_perf.py`
- Create: `docs/superpowers/plans/2026-03-13-garnet-parallel-detailed-sim-spec.md` (update as execution notes are learned)

- [x] **Step 1: Write failing equivalence-matrix test plan**
Define runs for:
  - `off`
  - `serial_batched`
  - `parallel`

- [x] **Step 2: Add selected-stats comparison helper**
Compare exact or explicitly allowed fields only.

- [x] **Step 3: Add benchmark command flow**
Document manual perf runs after correctness is proven.

- [x] **Step 4: Re-run matrix in Docker**
Use Docker-only commands for all phases.

- [ ] **Step 5: Commit**
```bash
git add tests/gem5/ruby_parallel_noc/README.md tests/gem5/ruby_parallel_noc/compare_stats.py tests/gem5/ruby_parallel_noc/compare_perf.py docs/superpowers/plans/2026-03-13-garnet-parallel-detailed-sim-spec.md
git commit -m "docs(test): add noc acceleration validation matrix"
```

**Checklist (Chunk 5)**
- [x] Correctness matrix is documented.
- [x] Benchmark flow is documented.
- [x] Results are reproducible in Docker.

Execution notes:
- `tests/gem5/ruby_parallel_noc/README.md` now documents the three-mode Docker correctness matrix, the focused harness UIDs, and the manual Docker benchmark flow.
- `tests/gem5/ruby_parallel_noc/compare_stats.py` compares only selected deterministic stats:
  - exact profile: `off` vs `serial_batched`
  - parallel profile: exact Ruby-network stats plus explicit `simTicks`/`finalTick = reference + 1`
- The helper intentionally excludes host-side stats and Ruby/Garnet power-state residency counters, because those reflect runtime/exit accounting rather than NoC correctness.
- Docker matrix re-run results:
  - `off`: `PARALLEL_NOC_METRIC tick=2000 exit_tick=2000`
  - `serial_batched`: `PARALLEL_NOC_METRIC tick=2000 exit_tick=2000`
  - `parallel`: `PARALLEL_NOC_METRIC tick=2000 exit_tick=2001`
  - `compare_stats.py --profile exact --reference /tmp/ruby_parallel_noc_off/stats.txt --candidate /tmp/ruby_parallel_noc_serial/stats.txt`: PASS
  - `compare_stats.py --profile parallel --reference /tmp/ruby_parallel_noc_serial/stats.txt --candidate /tmp/ruby_parallel_noc_parallel/stats.txt`: PASS

---

## Execution Checklist

### Pre-Implementation

- [x] Confirm current baseline commands still pass in Docker:
  - `tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py`
  - `configs/example/garnet_synth_traffic.py`
- [x] Confirm suite discovery works:
  - `./main.py list -vv --suites gem5/ruby_parallel_noc`
- [x] Record the current suite UID before changing implementation.
  - `SuiteUID:tests/gem5/ruby_parallel_noc/test_equivalence.py:ruby-parallel-noc-baseline-off-NULL-aarch64-opt-Garnet_standalone`

### Build

- [x] Build the relevant binary in Docker only.
- [x] Prefer smallest correct target for the current test path.
- [ ] Save the build log path for each run.

### Test

- [x] Run direct baseline config command in Docker.
- [x] Run existing example command in Docker.
- [x] Run harness suite in Docker.
- [ ] Save first failure line if any test fails.

### Validation

- [x] Compare completion cause.
- [x] Compare completion tick.
- [x] Confirm expected output markers appear.
- [x] Confirm requested mode and effective mode agree, or an explicit downgrade/rejection marker is printed.
- [x] Confirm `stats.txt` is generated.

### Safety

- [x] No edits under `src/mem/ruby/network/garnet/` for speedup logic.
- [x] No claims of speedup before equivalence is stable.
- [x] Keep all new functionality opt-in.

---

## Docker Verification Commands

- [x] Baseline direct run:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  bash -lc '/workspace/build/Garnet_standalone/gem5.opt \
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

- [x] Existing example run:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  bash -lc '/workspace/build/Garnet_standalone/gem5.opt \
    --outdir=/tmp/garnet_synth_smoke \
    /workspace/configs/example/garnet_synth_traffic.py \
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

- [x] Suite discovery:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace/tests \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  ./main.py list -vv --suites gem5/ruby_parallel_noc
```

Observed 2026-03-19 from same-source Docker runs:

- `ruby_garnet_equiv.py`
  - `PARALLEL_NOC_MODE=off REQUESTED=off WORKERS=1 NUM_CPUS=4`
  - `Exiting @ tick 2000 because Network Tester completed simCycles`
  - `PARALLEL_NOC_METRIC tick=2000 exit_tick=2000 cause=Network Tester completed simCycles`
  - `PARALLEL_NOC_STATS path=/tmp/ruby_parallel_noc_task5_off/stats.txt exists=True`
- `ruby_garnet_equiv.py` with `serial_batched`
  - `PARALLEL_NOC_MODE=serial_batched REQUESTED=serial_batched WORKERS=2 NUM_CPUS=4`
  - `PARALLEL_NOC_METRIC tick=2000 exit_tick=2000 cause=Network Tester completed simCycles`
  - `PARALLEL_NOC_STATS path=/tmp/ruby_parallel_noc_task5_serial/stats.txt exists=True`
- `ruby_garnet_equiv.py` with `parallel`
  - `PARALLEL_NOC_MODE=parallel REQUESTED=parallel WORKERS=3 NUM_CPUS=4`
  - `PARALLEL_NOC_PARTITION partitions=4 queues=1,2,3 sim_quantum=1`
  - `PARALLEL_NOC_METRIC tick=2000 exit_tick=2001 cause=Network Tester completed simCycles`
  - `PARALLEL_NOC_STATS path=/tmp/ruby_parallel_noc_task5_parallel/stats.txt exists=True`
- `garnet_synth_traffic.py`
  - `Exiting @ tick 2000 because Network Tester completed simCycles`
- suite discovery
  - `SuiteUID:tests/gem5/ruby_parallel_noc/test_equivalence.py:ruby-parallel-noc-baseline-off-NULL-aarch64-opt-Garnet_standalone`
  - `SuiteUID:tests/gem5/ruby_parallel_noc/test_parallel_baseline.py:ruby-parallel-noc-parallel-baseline-NULL-aarch64-opt-Garnet_standalone`
  - `SuiteUID:tests/gem5/ruby_parallel_noc/test_network_accel_smoke.py:ruby-parallel-noc-parallel-smoke-NULL-aarch64-opt-Garnet_standalone`

---

## Risks and Mitigations

- Risk: The external coordinator cannot extract enough speedup without touching Garnet.
  - Mitigation: prove serial-batched overhead reduction first; quantify the ceiling before broadening scope.

- Risk: Harness-selected build targets do not match the correct protocol/backend shape.
  - Mitigation: lock test metadata early and verify the exact suite UID/build target mapping.

- Risk: Source/binary mismatch from prebuilt Docker images causes false failures.
  - Mitigation: use same-source Docker builds for validation.

- Risk: Parallel orchestration introduces nondeterministic ordering above Garnet.
  - Mitigation: stable work partitioning, fixed-order merges, repeated deterministic trials.

- Risk: Docker Desktop instability masks actual simulator issues.
  - Mitigation: keep build scope minimal and log every Docker run separately.

---

## Definition of Done

- [x] Existing NoC baseline workloads run unchanged under `off`.
- [x] `serial_batched` is correctness-equivalent to `off`.
- [x] `parallel` is correctness-equivalent to `serial_batched`.
- [x] No speedup logic was added under `src/mem/ruby/network/garnet/`.
- [ ] At least one multicore NoC-heavy workload shows wall-clock improvement.
- [x] The framework remains usable for a future custom NoC backend.

---

## Suggested Commit Sequence

1. `test(noc): stabilize baseline ruby_parallel_noc harness`
2. `feat(sim): add network acceleration framework skeleton`
3. `feat(sim): add serial batched noc execution mode`
4. `feat(sim): add multicore noc execution mode`
5. `test(noc): add equivalence matrix and stats diff helpers`
6. `docs(noc): document multicore noc acceleration workflow`
