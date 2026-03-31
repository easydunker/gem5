# Smart Ruby/Garnet Partitioner Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current router-ID modulo queue assignment with a deterministic, topology-aware smart partitioner for Ruby/Garnet so one NoC simulation can use multiple host CPUs while preserving cycle-faithful Ruby/Garnet behavior.

**Architecture:** Keep Garnet as the detailed reference model and keep speedup logic outside `src/mem/ruby/network/garnet/*`. Build the partitioner primarily in the Ruby/Python config layer from the existing router/link graph, then use the existing runtime-side `src/sim/network_accel` coordinator only for worker activation, validation, and stable reporting. Synchronization remains one simulation quantum per cycle so correctness stays tied to the current detailed NoC semantics.

**Tech Stack:** gem5 Python config layer (`configs/ruby`, `configs/example`), gem5 runtime C++ layer (`src/sim/network_accel`, `src/sim/python.cc`, `src/python/m5/simulate.py`), existing Ruby/Garnet test package (`tests/gem5/ruby_parallel_noc`), Docker-first build/test flow.

---

## Current State

- `configs/ruby/NetworkAccel.py` already supports `off`, `serial_batched`, and `parallel`.
- The current `parallel` path assigns routers to worker queues by `router_id % active_workers`.
- The current path already splits internal-link objects by source vs destination event queue and sets `root.sim_quantum = 1`.
- The current runtime coordinator in `src/sim/network_accel/*` already validates active queues and reports summary information.
- The current design gap is the partitioning policy itself:
  - it is not topology-aware,
  - it does not size workers from host availability,
  - it does not optimize cut edges or load balance,
  - it is not yet framed as a reusable smart partitioner for Ruby/Garnet NoC studies.

## Design Intent

This work is not "parallelize Garnet internals." It is "partition Ruby/Garnet simulation objects into deterministic event-queue domains so the existing detailed NoC model can run across more than one host core without losing confidence in the results."

For this project, "close-to-RTL confidence" means:

- keep Garnet's detailed router/link/credit behavior unchanged,
- preserve cycle-level completion metrics against the current single-core detailed baseline,
- preserve `system.ruby.network.*` stats across equivalent runs,
- allow only the already-known multi-event-queue exit artifact where `parallel` may report `exit_tick = tick + sim_quantum`.

It does **not** mean claiming literal RTL co-simulation equivalence.

## Approaches Considered

### Option A: Keep the current modulo partitioner

- Pros:
  - minimal engineering work,
  - already partly wired.
- Cons:
  - ignores topology locality,
  - creates unnecessary cut edges,
  - gives poor balance on non-trivial controller attachment layouts,
  - weak story for NoC-design confidence.

### Option B: Deterministic topology-aware static partitioner

- Pros:
  - preserves determinism,
  - exploits `Mesh_XY` structure,
  - keeps Garnet untouched,
  - understandable and debuggable,
  - fits the current config/runtime split.
- Cons:
  - needs explicit extraction logic for router graph and attached objects,
  - needs conservative fallback behavior for unsupported topologies.

### Option C: Runtime/profile-guided or dynamic rebalancing

- Pros:
  - potentially better speedups on irregular traffic.
- Cons:
  - high complexity,
  - higher nondeterminism risk,
  - hard to validate for close-to-baseline NoC behavior,
  - not justified for the current scope.

**Recommendation:** implement Option B now. Keep runtime partitioning static and deterministic. Leave dynamic rebalancing as a future phase only if the static design proves too weak.

## Hard Constraints

- Do not move speedup logic into `src/mem/ruby/network/garnet/*`.
- Do not change Ruby/Garnet functional behavior to chase speedup.
- Do not make wall-clock speedup a CI pass/fail condition.
- Do not depend on host Python for verification.
- Do all build/test execution in Docker using the rules from `docs/superpowers/plans/2026-03-16-test-env-remember.md`.
- Prefer `build/Garnet_standalone/gem5.opt` for direct NoC runs and `build/NULL_Garnet_standalone/gem5.opt` for harness runs.

## Partitioner Model

### Partition Unit

- Primary unit: one router domain.
- Partition graph nodes:
  - `system.ruby.network.routers`
- Partition graph edges:
  - `system.ruby.network.int_links`

### Objects Owned By a Router Partition

- router object and descendants,
- attached network interface objects,
- attached ext links,
- attached Ruby CPU ports / sequencers,
- attached controllers:
  - L1 controllers,
  - directory controllers,
  - memory-controller-side objects if discoverable from ext-link ownership,
- attached generator/tester CPUs for focused NoC workloads.

### Cross-Partition Boundary Ownership

For an internal link from router `A` to router `B`:

- source queue owns:
  - `network_link`,
  - `src_net_bridge`,
  - `src_cred_bridge`
- destination queue owns:
  - `dst_net_bridge`,
  - `credit_link`,
  - `dst_cred_bridge`

This mirrors the existing code path and the Garnet event flow in `src/mem/ruby/network/garnet/README.txt`.

### Safe Partition Boundaries

These are hard correctness rules inferred from the current code layout:

- keep each `Router` atomic:
  - do not split `InputUnit`,
  - `OutputUnit`,
  - `SwitchAllocator`,
  - `CrossbarSwitch`,
  - VC state,
  - routing state across partitions.
- keep each `NetworkInterface` atomic:
  - do not split injection,
  - arbitration,
  - stall handling,
  - flit ejection,
  - credit handling across partitions.
- cut only on explicit transport objects:
  - router-router internal links,
  - router-NI links,
  - paired network/credit links,
  - bridge pairs when CDC/SerDes is involved.
- if controllers and NIs are separated, treat `MessageBuffer` enqueue/dequeue/reanalyze behavior as a synchronization boundary with no relaxed ordering.

The plan must preserve the current same-tick semantics:

- all fan-in deliveries for a consumer must be visible before that consumer's wakeup for the tick,
- ordered-vnet behavior must not be perturbed by cross-thread arrival order,
- same-cycle `MessageBuffer` reanalysis must not be delayed behind younger traffic.

### Worker Sizing

- `parallel` must never silently stay on one host queue.
- Effective workers must be:
  - `<= useful partition count`,
  - `<= host-available CPU count minus one main queue`,
  - `<= optional user cap`.
- Automated tests must use explicit worker counts.
- Manual performance runs may use host auto-sizing.

### Determinism Rule

All partition decisions must be stable for the same topology and options.

Sort order must always be explicit:

- routers sorted by `router_id`,
- queues sorted numerically,
- attached objects sorted by stable path or numeric ID,
- fallback decisions broken by lexicographic or numeric ordering only.

## Config Surface

Keep the existing mode knobs and add a distinct partitioner surface.

Recommended public options:

- `--network-accel-mode {off,serial_batched,parallel}`
- `--network-accel-workers {INT|auto}`
- `--network-accel-max-workers INT`
- `--network-accel-partitioner {manual,topology_auto}`
- `--network-accel-auto-shape {mesh_blocks,mesh_strips,graph_bfs,router_chunks}`
- `--network-accel-report-partitions`

Backward compatibility:

- keep `--parallel-noc-mode` and `--parallel-noc-workers` aliases.
- default partitioner for `parallel` should remain conservative until all tests and docs are updated:
  - phase 1 default: `manual`
  - phase 2 default: `topology_auto`

## Strategy Rules

### `manual`

- preserve the current explicit/manual behavior,
- remain the escape hatch for debugging and bisects.

### `topology_auto`

- detect `Mesh_XY` first,
- if `Mesh_XY`:
  - evaluate `mesh_blocks` and `mesh_strips`,
  - choose the best deterministic plan by:
    - minimizing cut edges,
    - minimizing load imbalance,
    - minimizing maximum partition span,
    - stable tie-break by queue/router ordering.
- if not `Mesh_XY` but graph is connected:
  - use deterministic `graph_bfs`.
- if graph extraction is incomplete or topology is unsupported:
  - downgrade or reject with an explicit note,
  - never silently claim parallel activation.

## Scoring Heuristic

Use a simple deterministic cost model. Keep it explainable.

Per-router weight:

- base router weight: `1`
- plus attached ext-link count,
- plus attached network-interface count,
- plus attached controller count,
- plus optional small penalty for routers with many cross-partition edges.

Partition score tuple:

1. total cross-partition edge count
2. max partition weight
3. weight spread (`max - min`)
4. lexicographic router membership summary

Choose the minimum tuple.

This is intentionally static and deterministic. Do not add profile-guided adaptation in this phase.

## Known Correctness Hazards

The implementation must explicitly guard against these:

- shared/global state that is not naturally thread-safe:
  - packet ID generation,
  - static network metadata,
  - global functional traversals,
  - Ruby drain/checkpoint/writeback paths
- RNG-sensitive behavior:
  - routing randomness,
  - message-buffer randomization
- heterogeneous-link timing state:
  - bridge scheduling,
  - extra credit handling,
  - deadlock detection sensitivity

If any of these surfaces cannot be isolated behind the current event-queue partition model, the implementation must degrade or reject instead of silently proceeding.

## Reporting Requirements

Keep existing lines and add partitioner-specific lines.

Required summary lines:

- `PARALLEL_NOC_MODE`
- `PARALLEL_NOC_COORDINATOR`
- `PARALLEL_NOC_PARTITION`
- `PARALLEL_NOC_RUNTIME`
- `PARALLEL_NOC_METRIC`
- `PARALLEL_NOC_STATS`
- `PARALLEL_NOC_NOTE`
- `PARALLEL_NOC_PARTITIONER`
- `PARALLEL_NOC_PARTITION_MAP`

Required fields:

- requested mode,
- requested workers,
- effective mode,
- effective workers,
- host-visible CPU count,
- router count,
- partition count,
- strategy,
- auto-shape,
- queue-to-router mapping,
- downgrade reason if any.

Example format shape only:

```text
PARALLEL_NOC_PARTITIONER strategy=topology_auto auto_shape=mesh_blocks requested_workers=auto effective_workers=4 host_cpus=8 routers=16 partitions=4
PARALLEL_NOC_PARTITION_MAP queues=1:[0,1,4,5];2:[2,3,6,7];3:[8,9,12,13];4:[10,11,14,15]
```

## File Structure

### Files to Modify

- `configs/ruby/NetworkAccel.py`
  - keep as the public entrypoint,
  - shrink into orchestration only if helper modules are added.

- `configs/example/garnet_synth_traffic.py`
  - use the shared smart partitioner surface,
  - print stable partitioner summaries when requested.

- `tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py`
  - remain the canonical focused correctness config,
  - use the same smart partitioner API as the example config.

- `src/sim/network_accel/NetworkAccelCoordinator.hh`
- `src/sim/network_accel/NetworkAccelCoordinator.cc`
  - keep runtime validation/reporting here,
  - do not move topology planning into C++.

- `src/sim/network_accel/WorkerPool.hh`
- `src/sim/network_accel/WorkerPool.cc`
  - extend worker activation/accounting for host-aware sizing and stable queue summaries.

- `src/sim/python.cc`
- `src/python/m5/simulate.py`
  - expose any extra runtime-facing summaries needed by configs/tests.

- `tests/gem5/ruby_parallel_noc/README.md`
  - document direct-run matrix, harness rules, and Docker commands.

- `tests/gem5/ruby_parallel_noc/compare_perf.py`
  - optionally extend manual perf reporting to print the chosen partitioner settings.

- `tests/gem5/ruby_parallel_noc/compare_stats.py`
  - extend only if extra exact/allowed fields are needed.

### Files to Create

- `configs/ruby/network_accel/__init__.py`
- `configs/ruby/network_accel/partition_model.py`
- `configs/ruby/network_accel/topology_extract.py`
- `configs/ruby/network_accel/strategies.py`
- `configs/ruby/network_accel/host_sizing.py`
- `configs/ruby/network_accel/summary.py`

- `tests/gem5/ruby_parallel_noc/test_auto_partitioner_smoke.py`
- `tests/gem5/ruby_parallel_noc/test_auto_partitioner_equivalence.py`
- `tests/gem5/ruby_parallel_noc/test_auto_partitioner_large_mesh.py`
- `tests/gem5/ruby_parallel_noc/test_auto_partitioner_fallback.py`

Optional only if needed:

- `tests/gem5/ruby_parallel_noc/test_auto_partitioner_repeatability.py`

---

## Chunk 1: Lock the Public Surface

### Task 1: Define options and plan objects

**Files:**
- Modify: `configs/ruby/NetworkAccel.py`
- Modify: `tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py`
- Modify: `configs/example/garnet_synth_traffic.py`
- Create: `tests/gem5/ruby_parallel_noc/test_auto_partitioner_smoke.py`

- [x] **Step 1: Add failing smoke coverage for new options**

Cover at least:

- `--network-accel-partitioner manual`
- `--network-accel-partitioner topology_auto`
- `--network-accel-workers auto`
- `--network-accel-auto-shape mesh_blocks`
- `--network-accel-auto-shape mesh_strips`

- [x] **Step 2: Define small plan data structures**

Add focused structures with clear responsibility:

- `RouterPartition`
- `PartitionPlan`
- `PartitionSummary`

Each structure should answer exactly one question:

- what belongs together,
- which queue it maps to,
- what must be printed for verification.

- [x] **Step 3: Keep `NetworkAccel.py` as the stable public API**

Expected API shape:

```python
def add_network_accel_options(parser): ...
def configure_network_accel(root, system, requested_mode, requested_workers, ...): ...
```

Internal helpers may move into `configs/ruby/network_accel/*`, but callers must stay simple.

- [x] **Step 4: Add stable partitioner summary formatting**

All lists must be sorted before printing. Summary output must be regex-friendly and compact.

- [x] **Step 5: Run focused smoke coverage in Docker**

Use the Docker rules from `docs/superpowers/plans/2026-03-16-test-env-remember.md`:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace/tests \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  ./main.py list -q --suites gem5/ruby_parallel_noc
```

Then run the new smoke suite by `--uid`, not by file path.

- [x] **Step 6: Commit**

```bash
git add configs/ruby/NetworkAccel.py \
  configs/example/garnet_synth_traffic.py \
  tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py \
  tests/gem5/ruby_parallel_noc/test_auto_partitioner_smoke.py \
  configs/ruby/network_accel
git commit -m "feat(noc): add smart partitioner public surface"
```

**Checklist (Chunk 1)**

- [x] New config surface is defined.
- [x] Old aliases still parse.
- [x] The partitioner summary format is stable.
- [x] No Garnet source files were touched.

---

## Chunk 2: Extract the Ruby/Garnet Partition Graph

### Task 2: Build deterministic topology extraction

**Files:**
- Create: `configs/ruby/network_accel/topology_extract.py`
- Create: `configs/ruby/network_accel/partition_model.py`
- Modify: `configs/ruby/NetworkAccel.py`
- Create: `tests/gem5/ruby_parallel_noc/test_auto_partitioner_equivalence.py`

- [x] **Step 1: Extract routers and internal links from the existing Ruby network**

The extractor must discover:

- router IDs,
- ext-link attachments,
- int-link source/destination router IDs,
- network interfaces,
- controller-like objects reachable from ext links or Ruby object tables.

- [x] **Step 2: Infer `Mesh_XY` shape when applicable**

Use configuration/topology metadata first. Only infer from router IDs if the metadata is insufficient and the inference is deterministic.

- [x] **Step 3: Add exact unit-level expectations for extraction**

At minimum, the test plan should validate:

- 4-router `2x2` mesh extraction,
- router ordering is stable,
- internal-link directionality is preserved,
- attached ext-link/controller ownership is deterministic.

- [x] **Step 4: Reject incomplete extraction cleanly**

If ownership cannot be proven, emit an explicit note and downgrade/reject `parallel`.

- [x] **Step 5: Run focused correctness coverage in Docker**

Use the same suite-discovery rule:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace/tests \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  ./main.py run -vv --skip-build --uid '<fill after listing>'
```

- [x] **Step 6: Commit**

```bash
git add configs/ruby/NetworkAccel.py \
  configs/ruby/network_accel/topology_extract.py \
  configs/ruby/network_accel/partition_model.py \
  tests/gem5/ruby_parallel_noc/test_auto_partitioner_equivalence.py
git commit -m "feat(noc): extract deterministic Ruby Garnet partition graph"
```

**Checklist (Chunk 2)**

- [x] Router graph extraction is deterministic.
- [x] `Mesh_XY` classification is explicit.
- [x] Ownership of attached objects is reproducible.
- [x] Unsupported cases fail loudly.

---

## Chunk 3: Implement the Smart Partitioning Strategies

### Task 3: Add `mesh_blocks`, `mesh_strips`, and deterministic fallback

**Files:**
- Create: `configs/ruby/network_accel/strategies.py`
- Create: `configs/ruby/network_accel/summary.py`
- Modify: `configs/ruby/NetworkAccel.py`
- Create: `tests/gem5/ruby_parallel_noc/test_auto_partitioner_large_mesh.py`
- Create: `tests/gem5/ruby_parallel_noc/test_auto_partitioner_fallback.py`

- [x] **Step 1: Implement `mesh_blocks`**

For `Mesh_XY`, generate contiguous rectangular partitions. Score candidate shapes using the tuple described above.

- [x] **Step 2: Implement `mesh_strips`**

Add row- or column-strip partitioning as an alternative candidate. Keep it deterministic and comparable to `mesh_blocks`.

- [x] **Step 3: Implement deterministic non-mesh fallback**

Recommended order:

- `graph_bfs` if graph extraction is complete,
- `router_chunks` only as the last conservative fallback.

- [x] **Step 4: Attach objects to chosen router partitions**

The plan must explicitly assign:

- routers,
- tester CPUs,
- Ruby CPU ports,
- network interfaces,
- ext links,
- controller objects,
- internal-link halves.

- [x] **Step 5: Bound worker count safely**

If `requested_workers` is `auto`, resolve it from host-visible CPU count. Use:

- `len(os.sched_getaffinity(0))` if available,
- otherwise `os.cpu_count()`,
- then subtract one for the main queue,
- then clamp to useful partition count and any user cap.

- [x] **Step 6: Print deterministic summary lines**

The same topology and options must yield the same:

- partition count,
- queue count,
- queue-to-router map,
- downgrade/fallback note.

- [x] **Step 7: Run large-mesh focused validation in Docker**

Target case:

- `Mesh_XY`
- `--num-cpus 16`
- `--num-dirs 16`
- `--mesh-rows 4`

- [x] **Step 8: Commit**

```bash
git add configs/ruby/NetworkAccel.py \
  configs/ruby/network_accel/strategies.py \
  configs/ruby/network_accel/summary.py \
  tests/gem5/ruby_parallel_noc/test_auto_partitioner_large_mesh.py \
  tests/gem5/ruby_parallel_noc/test_auto_partitioner_fallback.py
git commit -m "feat(noc): add topology-aware smart partitioning"
```

**Checklist (Chunk 3)**

- [x] `Mesh_XY` gets locality-aware partitions.
- [x] Worker counts are bounded deterministically.
- [x] Fallback behavior is explicit.
- [x] Queue-to-router maps are stable across repeats.

---

## Chunk 4: Integrate Runtime Validation Without Moving Planning Into C++

### Task 4: Extend runtime validation and summary plumbing

**Files:**
- Modify: `src/sim/network_accel/NetworkAccelCoordinator.hh`
- Modify: `src/sim/network_accel/NetworkAccelCoordinator.cc`
- Modify: `src/sim/network_accel/WorkerPool.hh`
- Modify: `src/sim/network_accel/WorkerPool.cc`
- Modify: `src/sim/python.cc`
- Modify: `src/python/m5/simulate.py`
- Modify: `tests/gem5/ruby_parallel_noc/test_parallel_baseline.py`
- Modify: `tests/gem5/ruby_parallel_noc/test_network_accel_smoke.py`

- [x] **Step 1: Keep C++ as validation/reporting only**

Do not re-implement topology analysis in C++.

- [x] **Step 2: Add any missing runtime-facing summary accessors**

Needed fields may include:

- host-visible CPU count,
- effective worker count,
- compact queue summary,
- downgrade reason,
- active queue/dispatch summaries.

- [x] **Step 3: Tighten runtime assertions**

Fail fast if:

- `parallel` is active without `sim_quantum`,
- active queues do not match the chosen worker set,
- any claimed worker queue never enters or never dispatches.

- [x] **Step 4: Extend focused tests to check new summary fields**

Do not just check "run succeeded." Check the report surface.

- [x] **Step 5: Run repeated deterministic validation**

Repeat the same direct `parallel` run three times and confirm:

- same partition summary,
- same metric tick,
- same `system.ruby.network.*` stats,
- same queue activity pattern shape.

- [x] **Step 6: Commit**

```bash
git add src/sim/network_accel/NetworkAccelCoordinator.hh \
  src/sim/network_accel/NetworkAccelCoordinator.cc \
  src/sim/network_accel/WorkerPool.hh \
  src/sim/network_accel/WorkerPool.cc \
  src/sim/python.cc \
  src/python/m5/simulate.py \
  tests/gem5/ruby_parallel_noc/test_parallel_baseline.py \
  tests/gem5/ruby_parallel_noc/test_network_accel_smoke.py
git commit -m "feat(noc): validate and report smart partitioner runtime state"
```

**Checklist (Chunk 4)**

- [x] Runtime still owns validation, not planning.
- [x] `parallel` claims are provable from runtime counters.
- [x] Repeated runs are deterministic.
- [x] No Garnet internals were modified.

---

## Chunk 5: Verify Correctness and Measure Speedup

### Task 5: Run the Docker-first correctness matrix

**Files:**
- Modify: `tests/gem5/ruby_parallel_noc/README.md`
- Modify: `tests/gem5/ruby_parallel_noc/compare_perf.py`
- Modify: `tests/gem5/ruby_parallel_noc/compare_stats.py`

- [ ] **Step 1: Build the direct-run binary in Docker**

Reference rules from `docs/superpowers/plans/2026-03-16-test-env-remember.md`:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -w /workspace \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  bash -lc 'scons build/Garnet_standalone/gem5.opt -j2 2>&1' \
  | tee /tmp/garnet-standalone-build-j2.log
```

- [ ] **Step 2: Build the harness binary in Docker**

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -w /workspace \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  bash -lc 'scons build/NULL_Garnet_standalone/gem5.opt -j2 2>&1' \
  | tee /tmp/null-garnet-standalone-build-j2.log
```

- [ ] **Step 3: Run the small exact-equivalence smoke case**

Run all four:

- `off`
- `serial_batched`
- `parallel + manual`
- `parallel + topology_auto`

Recommended focused command shape:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  bash -lc 'rm -rf /tmp/ruby_parallel_noc_auto && mkdir -p /tmp/ruby_parallel_noc_auto && \
    /workspace/build/Garnet_standalone/gem5.opt \
      --outdir=/tmp/ruby_parallel_noc_auto \
      /workspace/tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py \
      --network-accel-mode parallel \
      --network-accel-workers 3 \
      --network-accel-partitioner topology_auto \
      --network-accel-auto-shape mesh_blocks \
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

- [ ] **Step 4: Compare stats for exact-equivalence cases**

Expected comparisons:

- `off` vs `serial_batched`: `--profile exact`
- `serial_batched` vs `parallel + manual`: `--profile parallel`
- `serial_batched` vs `parallel + topology_auto`: `--profile parallel`

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  python3 tests/gem5/ruby_parallel_noc/compare_stats.py \
    --profile parallel \
    --reference /tmp/ruby_parallel_noc_serial/stats.txt \
    --candidate /tmp/ruby_parallel_noc_auto/stats.txt
```

- [ ] **Step 5: Run a larger but still meaningful mesh workload**

Recommended correctness + perf candidate:

- `--num-cpus 16`
- `--num-dirs 16`
- `--mesh-rows 4`
- `--sim-cycles 20000`
- `--synthetic uniform_random`
- `--injectionrate 0.05`

Use square node counts for synthetic-traffic sweeps because the tester derives destinations from `sqrt(num_destinations)`.

- [ ] **Step 6: Run a long-distance traffic stress case**

Recommended:

- same `4x4` mesh,
- `--synthetic tornado`,
- `--injectionrate 0.05`

This is important because it forces more partition-boundary traffic than low-load local-friendly cases.

- [ ] **Step 7: Add one focused NoC sweep instead of a large matrix**

Keep this cheap and informative:

- traffic:
  - `uniform_random`
  - `neighbor`
  - `tornado` or `bit_complement`
- injection rate:
  - `0.02`
  - `0.08`
  - `0.15`
- virtual network:
  - `--inj-vnet 0`
  - `--inj-vnet 2`

Optional timing/resource sweep if the implementation reaches this far:

- `--router-latency 1,3`
- `--link-latency 1,3`
- or `--vcs-per-vnet 1,4`

- [ ] **Step 8: Run the canonical example config with the same partitioner**

Use `configs/example/garnet_synth_traffic.py` with:

- `parallel + topology_auto`
- `4x4` mesh
- same traffic pair:
  - `uniform_random`
  - `tornado`

- [ ] **Step 9: Measure wall-clock performance manually**

Use the helper:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  python3 tests/gem5/ruby_parallel_noc/compare_perf.py \
    --gem5-bin build/Garnet_standalone/gem5.opt \
    --mode parallel \
    --workers 4 \
    --num-cpus 16 \
    --num-dirs 16 \
    --mesh-rows 4 \
    --sim-cycles 20000 \
    --synthetic uniform_random \
    --injectionrate 0.05
```

Record:

- median baseline wall time,
- median smart-partitioner wall time,
- speedup ratio,
- partitioner settings used,
- whether multiple worker queues actually entered/dispatched.

- [ ] **Step 10: Compare high-signal network metrics**

In addition to the existing exact/parallel profile checks, explicitly review:

- `packets_injected`
- `packets_received`
- `flits_injected`
- `flits_received`
- `average_packet_latency`
- `average_flit_latency`
- `average_hops`
- `avg_link_utilization`
- `avg_vc_load`

- [ ] **Step 11: Add one Ruby-side end-to-end canary if the partitioner is generalized beyond `Garnet_standalone`**

If the implementation touches Ruby object ownership in a way that is intended to work outside the focused standalone path, run at least one extra protocol build and both of these existing configs on a small Garnet mesh:

- `configs/example/ruby_random_test.py`
- `configs/example/ruby_mem_test.py`

Use a bounded run first:

- `ruby_random_test.py --maxloads 5000`
- `ruby_mem_test.py --maxloads <small debug bound>`

This is the cheap way to catch:

- bursty backpressure bugs,
- deadlock/progress regressions,
- object-ownership mistakes not visible in the clean synthetic traffic path.

- [ ] **Step 12: Run focused harness suites**

Use directory listing plus `--uid`:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace/tests \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  ./main.py list -q --suites gem5/ruby_parallel_noc
```

Then run:

- baseline `off`
- `serial_batched`
- current `parallel`
- new auto-partitioner smoke/equivalence/large-mesh suites

- [ ] **Step 13: Update README with the final runbook**

The README must include:

- exact Docker image,
- exact mounts,
- exact build targets,
- direct-run commands,
- harness discovery rule,
- stats comparison commands,
- perf comparison commands,
- known `exit_tick = tick + 1` note for multi-event-queue `parallel`.

- [ ] **Step 14: Commit**

```bash
git add tests/gem5/ruby_parallel_noc/README.md \
  tests/gem5/ruby_parallel_noc/compare_perf.py \
  tests/gem5/ruby_parallel_noc/compare_stats.py \
  tests/gem5/ruby_parallel_noc
git commit -m "test(noc): validate smart partitioner correctness and perf flow"
```

**Checklist (Chunk 5)**

- [ ] Docker-only verification path is documented.
- [ ] Small `2x2` mesh case is exact or allowed-equivalent.
- [ ] Large `4x4` mesh case is exact or allowed-equivalent.
- [ ] Long-distance traffic case is covered.
- [ ] At least one focused sweep covers higher load or altered network timing.
- [ ] Example config uses the same partitioner path.
- [ ] Manual perf comparison shows whether the partitioner actually buys time.

---

## Acceptance Criteria

The implementation is ready only if all of the following are true:

- [ ] `parallel + topology_auto` activates only when a valid deterministic partition plan exists.
- [ ] `off`, `serial_batched`, `parallel + manual`, and `parallel + topology_auto` all complete the focused `2x2` correctness run.
- [ ] `parallel + topology_auto` preserves:
  - completion cause,
  - workload-completion tick,
  - `system.ruby.network.*` stats,
  - deterministic partition summaries across repeats.
- [ ] The only allowed timing difference in `parallel` remains the known exit-delivery artifact:
  - `exit_tick = tick + sim_quantum`
- [ ] A `4x4` mesh run proves the partitioner is doing useful multi-queue work rather than just claiming it.
- [ ] Unsupported topologies/configurations downgrade or reject with explicit `PARALLEL_NOC_NOTE`.
- [ ] No code under `src/mem/ruby/network/garnet/*` was modified for this feature.

## Non-Goals

- Runtime repartitioning or load migration.
- Learning-based partition selection.
- Claiming RTL equivalence beyond the current detailed Ruby/Garnet baseline.
- Full-system CPU-model parallelization outside the NoC acceleration boundary.

## Implementation Notes for Workers

- Start from the existing `configs/ruby/NetworkAccel.py` path. Do not redesign the whole stack.
- Treat `tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py` as the correctness oracle config.
- Keep Docker commands aligned with `docs/superpowers/plans/2026-03-16-test-env-remember.md`.
- Prefer exact repeated direct runs before widening the harness matrix.
- If a topology cannot be partitioned confidently, downgrade or reject. Do not guess.

## Final Handoff Checklist

- [ ] Public options implemented.
- [ ] Topology extractor implemented.
- [ ] Smart partition strategies implemented.
- [ ] Runtime reporting and validation updated.
- [ ] Direct correctness matrix run in Docker.
- [ ] Harness suites run in Docker.
- [ ] Stats comparisons recorded.
- [ ] Perf comparison recorded.
- [ ] README updated.
- [ ] No Garnet internals changed.
