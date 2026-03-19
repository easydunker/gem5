# Ruby Parallel NoC Tests

This package validates the execution-layer acceleration work for detailed
Ruby/Garnet simulations. The current phase covers three correctness modes:
`off`, `serial_batched`, and `parallel`.

## Correctness invariants

For the 4-core mesh workload in `configs/ruby_garnet_equiv.py`, validation
records:

- completion cause: `Network Tester completed simCycles`
- workload-completion tick:
  - `off`: `2000`
  - `serial_batched`: `2000`
  - `parallel`: `2000`
- raw exit tick:
  - `off`: `2000`
  - `serial_batched`: `2000`
  - `parallel`: `2001`
- expected summary lines:
  - `PARALLEL_NOC_MODE=...`
  - `PARALLEL_NOC_COORDINATOR ...`
  - `PARALLEL_NOC_METRIC tick=... exit_tick=... cause=...`
  - `PARALLEL_NOC_STATS path=... exists=True`
- selected stats file:
  - `stats.txt` exists in the run outdir
  - `system.ruby.network.*` stats match exactly across modes
  - `simTicks` and `finalTick` match exactly for `off` vs `serial_batched`
  - `parallel` is allowed to report `simTicks=finalTick=2001` because the
    multi-event-queue exit is delivered one `sim_quantum` later

## Docker correctness matrix

Run from repo root. Use the same-source `build/Garnet_standalone/gem5.opt`
binary for direct workload validation and mount `/tmp` to avoid container tmp
exhaustion during test runs.

Direct `off` run:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  bash -lc 'rm -rf /tmp/ruby_parallel_noc_off && mkdir -p /tmp/ruby_parallel_noc_off && \
    /workspace/build/Garnet_standalone/gem5.opt \
      --outdir=/tmp/ruby_parallel_noc_off \
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

Direct `serial_batched` run:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  bash -lc 'rm -rf /tmp/ruby_parallel_noc_serial && mkdir -p /tmp/ruby_parallel_noc_serial && \
    /workspace/build/Garnet_standalone/gem5.opt \
      --outdir=/tmp/ruby_parallel_noc_serial \
      /workspace/tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py \
      --parallel-noc-mode serial_batched \
      --parallel-noc-workers 2 \
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

Direct `parallel` run:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  bash -lc 'rm -rf /tmp/ruby_parallel_noc_parallel && mkdir -p /tmp/ruby_parallel_noc_parallel && \
    /workspace/build/Garnet_standalone/gem5.opt \
      --outdir=/tmp/ruby_parallel_noc_parallel \
      /workspace/tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py \
      --parallel-noc-mode parallel \
      --parallel-noc-workers 3 \
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

Stats comparison:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  python3 tests/gem5/ruby_parallel_noc/compare_stats.py \
    --profile exact \
    --reference /tmp/ruby_parallel_noc_off/stats.txt \
    --candidate /tmp/ruby_parallel_noc_serial/stats.txt

docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  python3 tests/gem5/ruby_parallel_noc/compare_stats.py \
    --profile parallel \
    --reference /tmp/ruby_parallel_noc_serial/stats.txt \
    --candidate /tmp/ruby_parallel_noc_parallel/stats.txt
```

Harness suite discovery:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace/tests \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  ./main.py list -q --suites gem5/ruby_parallel_noc
```

Focused harness verification:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace/tests \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  ./main.py run -vv --skip-build --uid \
    'SuiteUID:tests/gem5/ruby_parallel_noc/test_serial_batched_baseline.py:ruby-parallel-noc-serial-batched-baseline-NULL-aarch64-opt-Garnet_standalone'

docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace/tests \
  ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest \
  ./main.py run -vv --skip-build --uid \
    'SuiteUID:tests/gem5/ruby_parallel_noc/test_parallel_baseline.py:ruby-parallel-noc-parallel-baseline-NULL-aarch64-opt-Garnet_standalone'
```

## Current coverage

- `test_equivalence.py` locks down the baseline `off` mode.
- `test_serial_batched_baseline.py` proves `serial_batched` matches `off`.
- `test_parallel_baseline.py` proves `parallel` reports the real partition and
  matches the workload-completion metric from the baseline.
- `test_network_accel_smoke.py` covers option parsing and coordinator surface.

## Manual benchmark flow

Use `compare_perf.py` only after the correctness matrix above is clean. It is a
manual wall-clock helper, not a CI gate.

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
    --repeats 3 \
    --outdir-root /tmp/ruby_parallel_noc_perf \
    --num-cpus 16 \
    --num-dirs 16 \
    --mesh-rows 4 \
    --sim-cycles 20000 \
    --synthetic uniform_random \
    --injectionrate 0.05 \
    --routing-algorithm 1
```
