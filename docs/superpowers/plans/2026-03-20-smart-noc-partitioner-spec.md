# Smart NoC Partitioner Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, topology-aware automatic network-acceleration partitioner for Ruby/Garnet NoC simulations so users can request parallel execution without manually assigning event queues.

**Architecture:** Extend the current Ruby-side network acceleration helper into a reusable partitioning subsystem that derives partitions from the built router graph and attached Ruby endpoints. Keep all acceleration and partitioning logic outside `src/mem/ruby/network/garnet/*`, preserve deterministic behavior, and expose the chosen partition map through stable summary lines and focused tests.

**Tech Stack:** gem5 Python config layer (`configs/ruby`, `configs/network`, `configs/topologies`), gem5 simulation/runtime C++ layer (`src/sim/network_accel`, `src/python/m5`), gem5 test harness (`tests/gem5`), Docker-based build/test workflow.

---

## File Structure

### Files to Modify

- `configs/ruby/NetworkAccel.py`
  - Current manual Ruby/Garnet event-queue mapper.
  - Will become the main Python entrypoint for:
    - option parsing,
    - partition strategy selection,
    - router-graph inspection,
    - partition-to-eventq assignment,
    - deterministic summary generation.

- `tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py`
  - Existing focused config used by the multicore NoC tests.
  - Should remain a thin caller of the shared auto partitioner, not contain partitioning logic itself.

- `configs/example/garnet_synth_traffic.py`
  - Canonical direct Garnet config.
  - Should consume the same generic partitioner surface to prove the feature is not test-only.

- `src/sim/network_accel/NetworkAccelCoordinator.hh`
- `src/sim/network_accel/NetworkAccelCoordinator.cc`
  - Runtime-side validation/reporting for active queues, dispatch counts, and partition expectations.
  - May need new state to carry partition summaries or expected queue counts from the Python layer.

- `src/sim/python.cc`
- `src/python/m5/simulate.py`
  - Python bindings for any new runtime-facing partition summaries or validation hooks.

- `tests/gem5/ruby_parallel_noc/test_parallel_baseline.py`
- `tests/gem5/ruby_parallel_noc/test_network_accel_smoke.py`
- `tests/gem5/ruby_parallel_noc/test_equivalence.py`
- `tests/gem5/ruby_parallel_noc/test_serial_batched_baseline.py`
  - Extend the existing baseline/smoke coverage with automatic partitioner-specific expectations.

- `tests/gem5/ruby_parallel_noc/README.md`
  - Document Docker build/run/test flow and new auto partitioner behavior.

- `docs/superpowers/plans/2026-03-20-smart-noc-partitioner-spec.md`
  - Update with execution notes during implementation.

### Files to Create

- `tests/gem5/ruby_parallel_noc/test_auto_partitioner_baseline.py`
  - Focused harness coverage for `parallel` with automatic partitioning enabled.

- `tests/gem5/ruby_parallel_noc/test_auto_partitioner_smoke.py`
  - Smaller matrix for option parsing, downgrade/reject behavior, and summary line shape.

- `tests/gem5/ruby_parallel_noc/test_auto_partitioner_large_mesh.py`
  - Directs the partitioner at a larger mesh shape such as `4x4` and checks that:
    - partitions are contiguous or block-based for `Mesh_XY`,
    - requested worker count is bounded deterministically,
    - summary lines remain stable.

### Optional Split If `NetworkAccel.py` Gets Too Large

Only do this if the current file becomes unwieldy during implementation.

- `configs/ruby/network_accel/partition_model.py`
  - Partition data structures and formatting helpers.

- `configs/ruby/network_accel/topology_extract.py`
  - Router-graph and endpoint attachment extraction helpers.

- `configs/ruby/network_accel/strategies.py`
  - Concrete partitioning strategies:
    - manual,
    - mesh block,
    - generic graph fallback.

Keep the public API in `configs/ruby/NetworkAccel.py` stable even if internals split.

---

## Design Requirements

### Functional Requirements

- Add an automatic partitioning mode for `parallel` network acceleration.
- Users must not need to manually assign event queues in common cases.
- The partitioner must be deterministic.
- The partitioner must work for current Ruby/Garnet NoC configs without modifying `src/mem/ruby/network/garnet/*`.
- The partitioner must use the router graph as the primary partitioning graph.
- The partitioner must attach local Ruby/CPU-side objects to router-owned partitions.
- The partitioner must split cross-partition boundary link objects safely and deterministically.
- The partitioner must degrade or reject unsupported topologies/configurations rather than silently misreporting active parallel execution.

### Non-Goals

- Implementing dynamic load balancing at runtime.
- Modifying Garnet router/link internals for acceleration logic.
- Introducing nondeterministic partition choices.
- Claiming wall-clock speedup as a gating criterion in automated tests.

### Partitioning Model

- Primary partition unit: router domain.
- Partition graph nodes: `system.ruby.network.routers`.
- Graph edges: `system.ruby.network.int_links`.
- Attached objects:
  - CPU/test generator objects,
  - Ruby sequencers / `system.ruby._cpu_ports`,
  - L1 controllers,
  - directory controllers,
  - memory controllers,
  - network interfaces,
  - ext links.
- Boundary objects:
  - internal forward and credit links,
  - CDC / SerDes bridges,
  - any link-side object that naturally has source vs destination ownership.

### Strategy Rules

- `manual`:
  - preserve current explicit mapping behavior for tests and debugging.

- `topology_auto`:
  - default automatic strategy.
  - for `Mesh_XY`, generate contiguous rectangular or strip-based partitions.
  - for simple graphs that are not recognized as meshes, fall back to deterministic router-ID chunking with a clear note line.

- `parallel` with `topology_auto`:
  - should automatically choose `active_workers = min(requested_workers, useful_partition_count)`.
  - must print why workers were reduced if reduction happens.

### Summary Output Requirements

Add or extend stable summary lines printed by the config:

- `PARALLEL_NOC_PARTITION`
  - existing line remains.
- `PARALLEL_NOC_RUNTIME`
  - existing line remains.
- `PARALLEL_NOC_PARTITIONER`
  - strategy name,
  - requested workers,
  - effective workers,
  - router count,
  - partition count.
- `PARALLEL_NOC_PARTITION_MAP`
  - deterministic queue-to-router grouping summary.
  - keep it compact and regex-friendly.
  - example shape only:
    - `queues=1:[0,1,4,5];2:[2,3,6,7]`
- `PARALLEL_NOC_NOTE`
  - use for downgrade/fallback explanations.

Do not emit verbose per-object dumps in normal runs.

---

## Chunk 1: Config Surface and Partition Model

### Task 1: Define the partitioner API and public config surface

**Files:**
- Modify: `configs/ruby/NetworkAccel.py`
- Modify: `tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py`
- Modify: `configs/example/garnet_synth_traffic.py`
- Test: `tests/gem5/ruby_parallel_noc/test_auto_partitioner_smoke.py`

- [ ] **Step 1: Add failing smoke tests for new options**

Add a smoke suite that expects the new config surface to parse:
- `--network-accel-partitioner manual`
- `--network-accel-partitioner topology_auto`
- `--network-accel-auto-shape mesh_blocks`

The smoke should initially fail because the options do not exist yet.

- [x] **Step 2: Add public parser options in `NetworkAccel.py`**

Add options such as:
- `--network-accel-partitioner`
  - choices: `manual`, `topology_auto`
  - default:
    - `manual` for backward compatibility first,
    - switch to `topology_auto` only after tests and docs are updated.
- `--network-accel-auto-shape`
  - choices: `mesh_blocks`, `mesh_strips`, `router_chunks`
  - default `mesh_blocks`
- `--network-accel-report-partitions`
  - bool, default `True`

Keep old `--parallel-noc-*` aliases working.

- [ ] **Step 3: Introduce explicit partition data structures**

Inside `NetworkAccel.py` or a split helper module, define focused structures:
- `RouterPartition`
- `PartitionPlan`
- `PartitionSummary`

Each should have one clear responsibility:
- assignment,
- object ownership,
- summary formatting.

- [ ] **Step 4: Implement deterministic summary formatting**

Provide helpers that produce stable strings for:
- partition count,
- queue summary,
- router membership per queue.

All summaries must sort by queue ID and router ID.

- [ ] **Step 5: Wire the new options through both configs**

Update:
- `tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py`
- `configs/example/garnet_synth_traffic.py`

Both should call the same public function, e.g.:
- `configure_network_accel(...)`

Neither should contain duplicated partitioning logic after this task.

- [ ] **Step 6: Run focused smoke test in Docker**

Run:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace/tests \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  ./main.py run -vv --skip-build --uid \
    'SuiteUID:tests/gem5/ruby_parallel_noc/test_auto_partitioner_smoke.py:<fill-after-discovery>'
```

Expected:
- PASS
- new option parsing lines present

- [ ] **Step 7: Commit**

```bash
git add configs/ruby/NetworkAccel.py \
  tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py \
  configs/example/garnet_synth_traffic.py \
  tests/gem5/ruby_parallel_noc/test_auto_partitioner_smoke.py
git commit -m "feat(noc): add automatic partitioner config surface"
```

**Execution Notes (2026-03-31)**
- Finished the remaining config-surface gap for `--network-accel-report-partitions`:
  - switched the parser to a real default-on boolean (`argparse.BooleanOptionalAction`);
  - kept default summary output enabled for existing callers;
  - added explicit suppression coverage with `--no-network-accel-report-partitions`;
  - gated `ruby_garnet_equiv.py` summary printing on the parsed flag, matching `garnet_synth_traffic.py`.
- Verification:
  - failing RED check before implementation:
    - `docker run --rm -u $(id -u):$(id -g) -v "$PWD":/workspace -v /tmp:/tmp -w /workspace/tests ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest ./main.py run -vv --skip-build --uid 'SuiteUID:tests/gem5/ruby_parallel_noc/test_auto_partitioner_smoke.py:ruby-parallel-noc-topology-auto-partitioner-no-report-smoke-NULL-aarch64-opt-Garnet_standalone'`
    - result: `3 Passed, 7 Failed` before the parser/config wiring existed.
  - passing focused smoke after implementation:
    - same command as above
    - result: `10 Passed in 2.1 seconds`
  - direct example config validation:
    - `docker run --rm -u $(id -u):$(id -g) -v "$PWD":/workspace -v /tmp:/tmp -w /workspace ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest bash -lc 'rm -rf /tmp/garnet_synth_no_report && mkdir -p /tmp/garnet_synth_no_report && /workspace/build/Garnet_standalone/gem5.opt --outdir=/tmp/garnet_synth_no_report /workspace/configs/example/garnet_synth_traffic.py --network-accel-mode parallel --network-accel-workers auto --network-accel-partitioner topology_auto --network-accel-auto-shape mesh_strips --no-network-accel-report-partitions --network garnet --topology Mesh_XY --num-cpus 4 --num-dirs 4 --mesh-rows 2 --sim-cycles 2000 --synthetic uniform_random --injectionrate 0.02 --routing-algorithm 1'`
    - result: successful run; `Exiting @ tick 2001 because Network Tester completed simCycles` with no partition summary lines emitted.

**Checklist (Chunk 1)**
- [ ] One public partitioner API exists.
- [ ] Backward-compatible flag aliases still work.
- [ ] Both canonical configs use the same helper.

---

## Chunk 2: Router-Graph Extraction and Mesh-Aware Planning

### Task 2: Build a deterministic topology-aware partition planner

**Files:**
- Modify: `configs/ruby/NetworkAccel.py`
- Modify or Create: `configs/ruby/network_accel/*` if split is needed
- Reference: `configs/topologies/Mesh_XY.py`
- Test: `tests/gem5/ruby_parallel_noc/test_auto_partitioner_large_mesh.py`

- [ ] **Step 1: Write failing planner tests for `Mesh_XY`**

Create tests that expect:
- 4-router `2x2` mesh with 3 workers:
  - 3 active queues,
  - deterministic router assignment,
  - contiguous grouping.
- 16-router `4x4` mesh with 4 workers:
  - 4 partitions,
  - each partition contains a contiguous `2x2` block or another documented deterministic pattern.

Keep expectations explicit in regex-friendly summaries rather than hidden logic.

- [ ] **Step 2: Extract router graph and endpoint attachments**

Add helpers to discover:
- routers by `router_id`,
- internal adjacency from `int_links`,
- external attachments from `ext_links`,
- local endpoint objects from:
  - `system.cpu`,
  - `system.ruby._cpu_ports`,
  - protocol-specific controller attrs such as `l1_cntrl*`, `dir_cntrl*`,
  - `system.mem_ctrls`,
  - `system.ruby.network.netifs`.

Do not hard-code only the current `4`-node test shape.

- [ ] **Step 3: Detect mesh layout when topology provides it**

Use available config facts such as:
- `options.topology == "Mesh_XY"`
- `options.mesh_rows`
- `len(network.routers)`

Infer `num_columns` and map router IDs to `(row, col)` deterministically.

- [ ] **Step 4: Implement `mesh_blocks` planning**

Given:
- router coordinates,
- requested workers,

produce near-contiguous rectangular partitions by:
- dividing rows/columns into bands,
- minimizing boundary cuts,
- preserving stable tie-breaking.

Document the exact heuristic in code comments and in the plan execution notes.

- [x] **Step 5: Implement deterministic generic fallback**

For topologies not yet explicitly supported:
- fallback to deterministic router-ID chunking,
- print `PARALLEL_NOC_NOTE` explaining the fallback,
- never pretend the planner used a mesh-aware split.

- [ ] **Step 6: Run direct planner validation in Docker**

Use direct config runs for at least:
- `2x2` mesh
- `4x4` mesh

Expected:
- summary lines stable across repeated runs,
- no exceptions,
- `parallel` remains active.

- [ ] **Step 7: Run large-mesh test in Docker**

Use a focused harness suite or direct config validator that checks the summary output for the large mesh case.

- [ ] **Step 8: Commit**

```bash
git add configs/ruby/NetworkAccel.py \
  configs/ruby/network_accel \
  tests/gem5/ruby_parallel_noc/test_auto_partitioner_large_mesh.py
git commit -m "feat(noc): add topology-aware router partition planner"
```

**Execution Notes (2026-03-31)**
- Aligned the non-mesh `topology_auto` fallback path with the spec:
  - mesh-oriented auto shapes on non-`Mesh_XY` topologies now resolve to deterministic `router_chunks`;
  - explicit `graph_bfs` support remains available only when the user explicitly requests it;
  - fallback runs now emit a compact summary note line:
    - `PARALLEL_NOC_NOTE requested=topology_auto auto_shape=<shape> fallback=router_chunks reason=non_mesh_topology`
- Verification:
  - before the fix, direct `Pt2Pt + topology_auto + mesh_blocks` output showed:
    - `PARALLEL_NOC_PARTITIONER requested=topology_auto strategy=graph_bfs reason=graph_connected ...`
    - no fallback note line.
  - focused harness verification after the fix:
    - `docker run --rm -u $(id -u):$(id -g) -v "$PWD":/workspace -v /tmp:/tmp -w /workspace/tests ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest ./main.py run -vv --skip-build --uid 'SuiteUID:tests/gem5/ruby_parallel_noc/test_auto_partitioner_fallback.py:ruby-parallel-noc-fallback-graph-bfs-NULL-aarch64-opt-Garnet_standalone'`
    - result: `11 Passed in 3.3 seconds`
    - `docker run --rm -u $(id -u):$(id -g) -v "$PWD":/workspace -v /tmp:/tmp -w /workspace/tests ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest ./main.py run -vv --skip-build --uid 'SuiteUID:tests/gem5/ruby_parallel_noc/test_auto_partitioner_fallback.py:ruby-parallel-noc-fallback-router-chunks-NULL-aarch64-opt-Garnet_standalone'`
    - result: `11 Passed in 3.2 seconds`

**Checklist (Chunk 2)**
- [ ] Router graph extraction is generic.
- [ ] `Mesh_XY` uses topology-aware partitioning.
- [ ] Unsupported topologies fall back deterministically with a note.

---

## Chunk 3: Object Ownership and Boundary Mapping

### Task 3: Attach Ruby and NoC-side objects to computed partitions

**Files:**
- Modify: `configs/ruby/NetworkAccel.py`
- Modify: `tests/gem5/ruby_parallel_noc/test_parallel_baseline.py`
- Modify: `tests/gem5/ruby_parallel_noc/test_network_accel_smoke.py`
- Test: `tests/gem5/ruby_parallel_noc/test_auto_partitioner_baseline.py`

- [x] **Step 1: Write failing baseline test for automatic partitioning**

Add a new baseline suite that runs:
- `--network-accel-mode parallel`
- `--network-accel-workers 3`
- `--network-accel-partitioner topology_auto`

Expect:
- successful completion,
- same metric tick as current parallel baseline,
- stable `PARALLEL_NOC_PARTITIONER` and `PARALLEL_NOC_PARTITION_MAP` lines.

- [ ] **Step 2: Replace manual per-object queue mapping with plan-driven assignment**

Use the computed `PartitionPlan` to assign:
- routers,
- CPUs / traffic generators,
- sequencers,
- L1 controllers,
- directory controllers,
- memory controllers,
- netifs,
- ext links.

Do not keep the current hard-coded “router index modulo worker count” path once the auto planner is active.

- [ ] **Step 3: Implement boundary handling for internal links**

For each cross-partition internal link:
- source-owned objects go to source partition,
- destination-owned objects go to destination partition.

This must cover:
- `network_link`
- `credit_link`
- `src_net_bridge`
- `src_cred_bridge`
- `dst_net_bridge`
- `dst_cred_bridge`

- [ ] **Step 4: Keep manual mode intact**

Manual mode should still exist for:
- debugging,
- regression comparison,
- cases where an implementer wants explicit placement.

- [ ] **Step 5: Emit stable partitioner summary lines**

Add:
- `PARALLEL_NOC_PARTITIONER`
- `PARALLEL_NOC_PARTITION_MAP`

Keep them compact enough for harness regex checks.

- [ ] **Step 6: Run direct `parallel` runs in Docker**

Run the direct config in Docker with:
- manual partitioner,
- auto partitioner.

Expected:
- both complete,
- both produce `stats.txt`,
- auto partitioner summary lines present,
- no loss of determinism in the output summary.

- [ ] **Step 7: Run focused harness tests in Docker**

Run:
- existing `test_parallel_baseline.py`
- new `test_auto_partitioner_baseline.py`
- updated smoke coverage

Expected:
- PASS

- [ ] **Step 8: Commit**

```bash
git add configs/ruby/NetworkAccel.py \
  tests/gem5/ruby_parallel_noc/test_parallel_baseline.py \
  tests/gem5/ruby_parallel_noc/test_network_accel_smoke.py \
  tests/gem5/ruby_parallel_noc/test_auto_partitioner_baseline.py
git commit -m "feat(noc): map Ruby and NoC objects with auto partitions"
```

**Execution Notes (2026-03-31)**
- Added `tests/gem5/ruby_parallel_noc/test_auto_partitioner_baseline.py` as the missing focused baseline for `parallel + topology_auto`.
- Current verified 2x2-mesh baseline behavior with `--network-accel-workers 3`:
  - deterministic reduction to `effective_workers=2`;
  - `PARALLEL_NOC_PARTITIONER requested=topology_auto strategy=mesh_blocks ... requested_workers=3 effective_workers=2 ...`;
  - `PARALLEL_NOC_PARTITION_MAP queues=1:[0,1];2:[2,3]`;
  - downgrade note emitted: `parallel mode reduced worker count to 2 for 2 partitions`.
- Verification:
  - direct pinning run:
    - `docker run --rm -u $(id -u):$(id -g) -v "$PWD":/workspace -v /tmp:/tmp -w /workspace ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest bash -lc 'rm -rf /tmp/ruby_parallel_noc_auto_baseline && mkdir -p /tmp/ruby_parallel_noc_auto_baseline && /workspace/build/Garnet_standalone/gem5.opt --outdir=/tmp/ruby_parallel_noc_auto_baseline /workspace/tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py --network-accel-mode parallel --network-accel-workers 3 --network-accel-partitioner topology_auto --network-accel-auto-shape mesh_blocks --network garnet --topology Mesh_XY --num-cpus 4 --num-dirs 4 --mesh-rows 2 --sim-cycles 2000 --synthetic uniform_random --injectionrate 0.02 --routing-algorithm 1'`
    - result: successful run with the summary lines above.
  - focused harness verification:
    - `docker run --rm -u $(id -u):$(id -g) -v "$PWD":/workspace -v /tmp:/tmp -w /workspace/tests ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest ./main.py run -vv --skip-build --uid 'SuiteUID:tests/gem5/ruby_parallel_noc/test_auto_partitioner_baseline.py:ruby-parallel-noc-auto-partitioner-baseline-NULL-aarch64-opt-Garnet_standalone'`
    - result: `11 Passed in 1.7 seconds`

**Checklist (Chunk 3)**
- [ ] Auto partitioning owns all relevant Ruby/Garnet-side objects.
- [ ] Boundary links are split safely.
- [ ] Manual mode still works.

---

## Chunk 4: Runtime Validation and Reporting

### Task 4: Tighten runtime-side assertions for the auto partitioner

**Files:**
- Modify: `src/sim/network_accel/NetworkAccelCoordinator.hh`
- Modify: `src/sim/network_accel/NetworkAccelCoordinator.cc`
- Modify: `src/sim/python.cc`
- Modify: `src/python/m5/simulate.py`
- Test: `tests/gem5/ruby_parallel_noc/test_auto_partitioner_smoke.py`

- [ ] **Step 1: Write failing runtime validation tests**

Extend smoke coverage to expect:
- queue-activity reporting for active worker queues,
- downgrade note when requested workers exceed useful partitions,
- failure or explicit downgrade when the planner cannot produce a valid partition.

- [ ] **Step 2: Add expected partition metadata to the runtime coordinator**

Extend the coordinator with enough state to validate:
- active worker count,
- expected queue IDs,
- queue entry counts,
- dispatch counts.

Do not move partition-planning logic into C++; keep C++ focused on validation and runtime accounting.

- [ ] **Step 3: Strengthen fast-fail assertions**

In `parallel` mode:
- fail if expected worker queues never enter the loop,
- fail if expected worker queues never dispatch any events,
- fail if runtime queue count disagrees with activated worker count.

- [ ] **Step 4: Expose any new summary accessors to Python**

Add any required bindings through:
- `src/sim/python.cc`
- `src/python/m5/simulate.py`

Keep naming aligned with existing `getNetworkAcceleration*` helpers.

- [ ] **Step 5: Verify the summary line contract**

Ensure the Python config can print runtime summaries after `m5.simulate(...)` returns and before exiting.

- [ ] **Step 6: Run focused smoke tests in Docker**

Run updated smoke suites only after rebuilding the relevant binaries in Docker.

- [ ] **Step 7: Commit**

```bash
git add src/sim/network_accel src/sim/python.cc src/python/m5/simulate.py \
  tests/gem5/ruby_parallel_noc/test_auto_partitioner_smoke.py
git commit -m "feat(sim): validate automatic noc partitions at runtime"
```

**Execution Notes (2026-03-31)**
- Added focused topology-auto downgrade smoke coverage in `tests/gem5/ruby_parallel_noc/test_auto_partitioner_smoke.py` for:
  - `--network-accel-mode parallel`
  - `--network-accel-workers 8`
  - `--network-accel-partitioner topology_auto`
  - `--network-accel-auto-shape mesh_blocks`
- Verified the runtime-side reduction note remains visible on the auto-partitioner path:
  - `PARALLEL_NOC_NOTE requested_mode=parallel requested_workers=8 effective_mode=parallel effective_workers=2 reason=parallel mode reduced worker count to 2 for 2 partitions`
- Focused harness verification:
  - `docker run --rm -u $(id -u):$(id -g) -v "$PWD":/workspace -v /tmp:/tmp -w /workspace/tests ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest ./main.py run -vv --skip-build --uid 'SuiteUID:tests/gem5/ruby_parallel_noc/test_auto_partitioner_smoke.py:ruby-parallel-noc-topology-auto-partitioner-downgrade-smoke-NULL-aarch64-opt-Garnet_standalone'`
  - result: `11 Passed in 1.6 seconds`

**Checklist (Chunk 4)**
- [ ] Runtime coordinator validates auto partitioner expectations.
- [ ] Queue activity is observable from Python/config output.
- [ ] Parallel mode still fails fast instead of silently misreporting.

---

## Chunk 5: Determinism, Stats Equivalence, and Docker Matrix

### Task 5: Add end-to-end verification and documentation

**Files:**
- Modify: `tests/gem5/ruby_parallel_noc/README.md`
- Modify: `tests/gem5/ruby_parallel_noc/compare_stats.py`
- Modify: `docs/superpowers/plans/2026-03-20-smart-noc-partitioner-spec.md`
- Test: `tests/gem5/ruby_parallel_noc/test_auto_partitioner_baseline.py`
- Test: `tests/gem5/ruby_parallel_noc/test_auto_partitioner_large_mesh.py`

- [ ] **Step 1: Write failing deterministic-equivalence checks**

Define the expected comparison matrix:
- `off` vs `serial_batched`
- `serial_batched` vs `parallel + manual partitioner`
- `parallel + manual partitioner` vs `parallel + topology_auto`

The last comparison is the new one.

- [x] **Step 2: Extend stats comparison helper only if needed**

If current selected deterministic stats are sufficient, keep them.
If auto partitioning introduces an expected summary-only difference, do not widen stats acceptance unnecessarily.

- [x] **Step 3: Document Docker-only execution flow**

Update `README.md` with:
- build commands for `build/Garnet_standalone/gem5.opt`
- build commands for `build/NULL_Garnet_standalone/gem5.opt`
- direct run commands for manual vs auto partitioner
- harness commands for focused suites
- repeated-run commands for determinism checks

- [ ] **Step 4: Run the full focused Docker matrix**

Required direct runs:
- `ruby_garnet_equiv.py` with:
  - `off`
  - `serial_batched`
  - `parallel + manual`
  - `parallel + topology_auto`
- `configs/example/garnet_synth_traffic.py` with `parallel + topology_auto`

Required harness runs:
- baseline `off`
- serial-batched baseline
- parallel manual baseline
- auto partitioner baseline
- auto partitioner smoke
- large mesh partitioner test

Required stats comparisons:
- exact profile for `off` vs `serial_batched`
- parallel profile for manual vs auto if the same exit semantics apply

- [ ] **Step 5: Add execution notes back into this plan**

Record:
- exact Docker commands used,
- key summary lines observed,
- any fallbacks/downgrades encountered,
- any determinism caveats found.

- [ ] **Step 6: Commit**

```bash
git add tests/gem5/ruby_parallel_noc/README.md \
  tests/gem5/ruby_parallel_noc/compare_stats.py \
  tests/gem5/ruby_parallel_noc/test_auto_partitioner_baseline.py \
  tests/gem5/ruby_parallel_noc/test_auto_partitioner_large_mesh.py \
  docs/superpowers/plans/2026-03-20-smart-noc-partitioner-spec.md
git commit -m "test(noc): validate automatic partitioner docker matrix"
```

**Execution Notes (2026-03-31)**
- `tests/gem5/ruby_parallel_noc/compare_stats.py` now keeps the `parallel` profile narrow while allowing both valid parallel equivalence cases:
  - same tick values for `parallel + manual` vs `parallel + topology_auto`;
  - `+1` tick delta for baseline-to-parallel comparisons that differ only because of multi-event-queue exit delivery.
- `tests/gem5/ruby_parallel_noc/README.md` now documents:
  - direct `parallel + topology_auto` runs;
  - manual-vs-auto `compare_stats.py --profile parallel` usage;
  - the focused `test_auto_partitioner_baseline.py` harness command;
  - current fallback coverage.
- Verification:
  - synthetic red/green helper check:
    - before fix, `python3 tests/gem5/ruby_parallel_noc/compare_stats.py --profile parallel --reference /tmp/compare_stats_ref.txt --candidate /tmp/compare_stats_cand.txt`
    - result before fix: `FAIL` because equal `simTicks/finalTick` were rejected.
    - result after fix: `PASS`
  - real gem5 stats comparison:
    - manual baseline generated at `/tmp/ruby_parallel_noc_parallel_manual/stats.txt`
    - auto baseline generated at `/tmp/ruby_parallel_noc_auto_baseline/stats.txt`
    - `python3 tests/gem5/ruby_parallel_noc/compare_stats.py --profile parallel --reference /tmp/ruby_parallel_noc_parallel_manual/stats.txt --candidate /tmp/ruby_parallel_noc_auto_baseline/stats.txt`
    - result: `PASS` with `compared_keys=55`

**Checklist (Chunk 5)**
- [ ] Auto partitioner is covered by both direct runs and harness suites.
- [ ] Docker-only commands are documented.
- [ ] Deterministic equivalence is demonstrated, not assumed.

---

## Docker Build and Test Commands

### Build `Garnet_standalone`

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -w /workspace \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  bash -lc 'scons build/Garnet_standalone/gem5.opt -j2 2>&1' \
  | tee /tmp/smart_noc_partitioner_garnet_build.log
```

### Build `NULL_Garnet_standalone`

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -w /workspace \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  bash -lc 'scons build/NULL_Garnet_standalone/gem5.opt -j2 2>&1' \
  | tee /tmp/smart_noc_partitioner_null_build.log
```

### Direct run template

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  bash -lc '<gem5 command here>'
```

### Harness template

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace/tests \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  ./main.py run -vv --skip-build --uid '<SuiteUID here>'
```

### Important rule for harness execution

Run focused `./main.py run` invocations sequentially, not in parallel, when they share the same mounted workspace and default `testing-results` directory.

---

## Risks and Mitigations

- Risk: The partitioner becomes too mesh-specific.
  - Mitigation: keep a generic deterministic fallback and print when it is used.

- Risk: Auto partitioning silently changes which objects belong to which queue.
  - Mitigation: emit compact partition map summaries and assert them in tests.

- Risk: Cross-partition link ownership is wrong.
  - Mitigation: keep explicit source/destination ownership rules and validate queue activity at runtime.

- Risk: Large worker counts increase synchronization overhead instead of speed.
  - Mitigation: cap effective workers by useful partition count and document that speedup is not a test gate.

- Risk: Docker/harness results are flaky because runs share `/tmp` or `testing-results`.
  - Mitigation: mount `/tmp`, keep harness runs sequential, and record first failure lines.

---

## Downstream Implementer Checklist

- [ ] Re-read `docs/superpowers/plans/2026-03-16-test-env-remember.md` before running anything.
- [ ] Use Docker only for builds and tests.
- [ ] Build both `build/Garnet_standalone/gem5.opt` and `build/NULL_Garnet_standalone/gem5.opt`.
- [ ] Keep all speedup logic out of `src/mem/ruby/network/garnet/*`.
- [ ] Keep the public config API backward-compatible while adding auto partitioning.
- [ ] Start with failing tests before implementation in each chunk.
- [ ] Run focused harness suites sequentially.
- [ ] Run direct Docker checks for:
  - [ ] `off`
  - [ ] `serial_batched`
  - [ ] `parallel + manual`
  - [ ] `parallel + topology_auto`
  - [ ] `garnet_synth_traffic.py + topology_auto`
- [ ] Run stats comparisons and record outputs.
- [ ] Update this spec with real execution notes during implementation.

---

## Definition of Done

- [ ] Users can request `parallel` acceleration with automatic partitioning and no manual queue assignment.
- [ ] `Mesh_XY` gets a deterministic topology-aware partition plan.
- [ ] Unsupported topologies fall back or downgrade explicitly.
- [ ] Auto partitioning remains outside Garnet internals.
- [ ] Focused harness tests pass in Docker.
- [ ] Direct Docker runs pass for both the ruby_parallel_noc config and the example Garnet traffic config.
- [ ] Deterministic stats equivalence is shown for auto partitioning relative to existing baselines.

---

## Suggested Commit Sequence

1. `feat(noc): add automatic partitioner config surface`
2. `feat(noc): add topology-aware router partition planner`
3. `feat(noc): map Ruby and NoC objects with auto partitions`
4. `feat(sim): validate automatic noc partitions at runtime`
5. `test(noc): validate automatic partitioner docker matrix`
