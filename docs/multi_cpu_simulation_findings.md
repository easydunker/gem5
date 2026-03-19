# Multi-CPU Simulation Investigation (gem5)

## Scope

This report summarizes a repo-wide investigation (split across subagents) into:

1. Why simulation often runs on a single host CPU.
2. What multi-host-CPU options already exist in this codebase.
3. Practical ways to speed up simulation.

---

## Executive Summary

The simulation is effectively single-host-CPU by default because almost all objects inherit `eventq_index = 0`, so they run on `MainEventQueue-0` only.  
gem5 **does** support multiple main event queues (and helper host threads), but this is opt-in and mostly wired for KVM-oriented flows (fast-forward/boot), not a general drop-in speedup for detailed timing/O3 simulation.

There are three distinct acceleration families in this repo:

1. **Parallel event queues (single gem5 process, multiple host threads)**: available, but mainly KVM-oriented and configuration-sensitive.
2. **dist-gem5 (multiple gem5 processes/nodes)**: available for distributed networked simulation use cases.
3. **multisim (many independent simulations in parallel)**: excellent throughput booster, but not one-run speedup.

---

## Why It Looks Single-CPU Today

### 1) Default object placement keeps everything on queue 0

- Root defaults to event queue 0: `src/sim/Root.py` (`eventq_index = 0`).
- SimObjects inherit parent event queue by default: `src/python/m5/SimObject.py` (`eventq_index = Param.UInt32(Parent.eventq_index, ...)`).
- SimObject runtime binds each object to queue from its params: `src/sim/sim_object.cc`.

Result: unless config code explicitly assigns non-zero `eventq_index`, the whole simulation stays on queue 0.

### 2) Multi-queue runtime exists, but only activates when multiple queues are actually allocated

- `src/sim/eventq.cc`: `numMainEventQueues` starts from 0 and queues are created lazily via `getEventQueue(index)`.
- `src/sim/simulate.cc`: helper host threads are created for queues `1..N-1`; queue 0 remains on main thread.
- Parallel mode only if `numMainEventQueues > 1`.

### 3) Parallel mode requires synchronization quantum and stricter scheduling semantics

- `src/sim/simulate.cc`: fatal if multi-queue without non-zero `simQuantum`.
- `src/sim/eventq.hh`: comments and checks enforce ordering/ownership assumptions across queues.
- `src/sim/global_event.*`: global barriers/ordering are used to keep cross-queue correctness.

Net effect: this is powerful but not transparent; configs and components must cooperate.

---

## Existing Multi-CPU / Speedup Paths in This Repo

## A) KVM + parallel event queues (single run speedup for KVM phase)

Evidence:

- `src/python/gem5/components/processors/base_cpu_processor.py`: assigns each KVM core its own event queue (`eventq_index = i + 1`) explicitly “to get the KVM CPUs to run on different host CPUs”.
- `src/python/gem5/components/processors/switchable_processor.py`: same pattern and `sim_quantum` setup.
- `configs/example/arm/fs_bigLITTLE.py` and `configs/deprecated/example/fs.py`: same KVM/per-queue assignment model.

Important caveat:

- This is mostly intended for KVM fast phases (boot/fast-forward), not full detailed timing fidelity.
- `CPUTypes.KVM` maps to `ATOMIC_NONCACHING` behavior; useful for speed, not detailed cache/timing studies.

## B) dist-gem5 (distributed multi-process simulation)

Evidence:

- Dist options in `configs/common/Options.py`.
- Example flow in `configs/example/arm/dist_bigLITTLE.py`.
- Launcher script in `util/dist/gem5-dist.sh`.

Notes:

- This is a separate distributed simulation model (processes/ranks + switch/server), not simply “make one detailed run use all host cores”.

## C) multisim (parallel independent jobs)

Evidence:

- `src/python/gem5/utils/multisim/multisim.py`: “run simulators ... in parallel.”

Notes:

- Great for total throughput (sweeps, experiments), but does not reduce wall-clock of one specific run.

---

## Stability / Fragility Signals Found

- `src/python/gem5/prebuilt/viper/board.py` explicitly disables some default multi-event-queue behavior because it “break[s] many things” in that GPU model.
- `src/python/gem5/components/processors/switchable_processor.py` documents a known caveat when switching between KVM and non-KVM with `sim_quantum` effects.
- Legacy/deprecated config surfaces still contain relevant logic (`configs/deprecated/example/fs.py`), and some wrappers still reference deprecated paths.

Interpretation: multi-queue support is real but uneven across subsystems and workflows.

---

## Practical Recommendations

## Priority 1: If acceptable, use KVM for non-ROI phases + switch to detailed core for ROI

Why:

- Highest practical speedup with current code.
- Already supported by stdlib/switchable processor patterns.

How:

1. Boot/fast-forward with KVM cores.
2. Assign per-core `eventq_index` (already done by stdlib KVM paths).
3. Set `root.sim_quantum`.
4. Switch to Timing/O3 only in ROI window.

## Priority 2: For campaign throughput, use multisim aggressively

Why:

- Near-linear scaling across host cores for independent runs.
- Lower risk than deep runtime modifications.

## Priority 3: Use dist-gem5 only if the target study is distributed by design

Why:

- Useful for distributed/networked multi-node scenarios.
- Not a general replacement for single-system detailed simulation speedup.

## Priority 4: Avoid trying to “just parallelize all detailed cores” without architectural work

Reason:

- Current event-queue synchronization and cross-queue constraints imply non-trivial correctness/determinism risk.
- Would require substantial engineering and validation across memory system/devices/global events.

---

## Suggested Next Steps (Concrete)

1. Pick one representative workload and measure baseline wall-clock with current detailed flow.
2. Prototype a KVM->Timing/O3 switch flow for that workload and measure:
   - wall-clock speedup,
   - ROI metric stability vs baseline.
3. In parallel, set up multisim for your experiment matrix to increase total throughput.
4. Only if still insufficient, open a focused design effort for broader multi-event-queue detailed execution (with explicit correctness tests around global events, memory ordering, exits, and device interactions).

---

## Bottom Line

The repo is not fundamentally “single-core only,” but the **default and most detailed paths** are effectively single-host-CPU unless specifically configured.  
Today, the most practical way to use multiple host CPUs for speed is:

- KVM + per-core event queues for fast phases, plus switching to detailed cores for ROI, and
- multisim for parallel experiment throughput.

