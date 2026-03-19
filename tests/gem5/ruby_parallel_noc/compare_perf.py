#!/usr/bin/env python3
"""
Manual performance comparison helper for Ruby/Garnet parallel NoC work.

This is intentionally not a CI verifier. It compares wall-clock time for:
- baseline off mode
- target mode (serial_batched or parallel)
"""

import argparse
import statistics
import subprocess
import time
from pathlib import Path


def build_command(args, mode: str, workers: int, outdir: Path):
    return [
        str(args.gem5_bin),
        "-d",
        str(outdir),
        "-re",
        "--silent-redirect",
        str(args.config),
        "--parallel-noc-mode",
        mode,
        "--parallel-noc-workers",
        str(workers),
        "--network",
        "garnet",
        "--topology",
        "Mesh_XY",
        "--num-cpus",
        str(args.num_cpus),
        "--num-dirs",
        str(args.num_dirs),
        "--mesh-rows",
        str(args.mesh_rows),
        "--sim-cycles",
        str(args.sim_cycles),
        "--synthetic",
        args.synthetic,
        "--injectionrate",
        str(args.injectionrate),
        "--routing-algorithm",
        str(args.routing_algorithm),
    ]


def run_once(args, mode: str, workers: int, outdir: Path):
    cmd = build_command(args, mode, workers, outdir)
    start = time.perf_counter()
    proc = subprocess.run(cmd, check=False)
    elapsed = time.perf_counter() - start
    if proc.returncode != 0:
        raise RuntimeError(
            f"gem5 run failed for mode={mode}, workers={workers}, "
            f"returncode={proc.returncode}"
        )
    return elapsed


def median_run(args, mode: str, workers: int):
    values = []
    for i in range(args.repeats):
        outdir = args.outdir_root / f"ruby_parallel_noc_{mode}_{workers}_r{i}"
        outdir.parent.mkdir(parents=True, exist_ok=True)
        print(f"running mode={mode} workers={workers} outdir={outdir}")
        values.append(run_once(args, mode, workers, outdir))
    return statistics.median(values), values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gem5-bin", required=True, type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("tests/gem5/ruby_parallel_noc/configs/ruby_garnet_equiv.py"),
    )
    parser.add_argument(
        "--mode",
        choices=["serial_batched", "parallel"],
        default="parallel",
        help="Target mode to compare against baseline off.",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--outdir-root", type=Path, default=Path("m5out"))
    parser.add_argument("--num-cpus", type=int, default=16)
    parser.add_argument("--num-dirs", type=int, default=16)
    parser.add_argument("--mesh-rows", type=int, default=4)
    parser.add_argument("--sim-cycles", type=int, default=20000)
    parser.add_argument("--synthetic", default="uniform_random")
    parser.add_argument("--injectionrate", type=float, default=0.05)
    parser.add_argument("--routing-algorithm", type=int, default=1)
    args = parser.parse_args()

    off_median, off_all = median_run(args, "off", 1)
    tgt_median, tgt_all = median_run(args, args.mode, args.workers)

    speedup = off_median / tgt_median if tgt_median > 0 else 0.0
    print("=== Ruby Parallel NoC Performance Comparison ===")
    print(
        f"config={args.config} num_cpus={args.num_cpus} num_dirs={args.num_dirs} "
        f"mesh_rows={args.mesh_rows} sim_cycles={args.sim_cycles} "
        f"synthetic={args.synthetic} injectionrate={args.injectionrate} "
        f"routing_algorithm={args.routing_algorithm}"
    )
    print(f"baseline(off, workers=1) median: {off_median:.3f}s runs={off_all}")
    print(
        f"target({args.mode}, workers={args.workers}) "
        f"median: {tgt_median:.3f}s runs={tgt_all}"
    )
    print(f"speedup: {speedup:.3f}x")


if __name__ == "__main__":
    main()
