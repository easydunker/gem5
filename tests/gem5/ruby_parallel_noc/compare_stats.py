#!/usr/bin/env python3
"""
Compare selected Ruby Parallel NoC stats with explicit equivalence rules.

This helper is intentionally narrow. It does not attempt a full-file diff
because host-side stats and multi-event-queue exit accounting can differ even
when the Ruby/network behavior is equivalent.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys


EXACT_KEYS = (
    "simFreq",
    "system.ruby.clk_domain.clock",
)

EXACT_PREFIXES = (
    "system.ruby.network.",
)

PLUS_ONE_KEYS = (
    "simTicks",
    "finalTick",
)

EXCLUDED_SUBSTRINGS = (
    ".power_state.",
)


@dataclass(frozen=True)
class ComparisonProfile:
    name: str
    accepted_tick_deltas: tuple[int, ...]


PROFILES = {
    "exact": ComparisonProfile(
        name="exact",
        accepted_tick_deltas=(0,),
    ),
    "parallel": ComparisonProfile(
        name="parallel",
        accepted_tick_deltas=(0, 1),
    ),
}


def parse_stats(path: Path) -> dict[str, str]:
    stats: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if (
            not line
            or line.startswith("----------")
            or line.startswith("Begin")
            or line.startswith("End")
        ):
            continue

        payload, _, _comment = line.partition("#")
        parts = payload.split()
        if len(parts) < 2:
            continue

        key = parts[0]
        value = " ".join(parts[1:])
        stats[key] = value

    return stats


def keys_to_compare(
    reference: dict[str, str],
    candidate: dict[str, str],
    profile: ComparisonProfile,
) -> list[str]:
    selected = set(EXACT_KEYS)
    selected.update(PLUS_ONE_KEYS)

    for source in (reference, candidate):
        for key in source:
            if key.startswith(EXACT_PREFIXES) and not any(
                excluded in key for excluded in EXCLUDED_SUBSTRINGS
            ):
                selected.add(key)

    return sorted(selected)


def compare(reference_path: Path, candidate_path: Path, profile: ComparisonProfile) -> int:
    reference = parse_stats(reference_path)
    candidate = parse_stats(candidate_path)

    failures: list[str] = []
    compared = 0

    for key in keys_to_compare(reference, candidate, profile):
        compared += 1
        ref_value = reference.get(key)
        cand_value = candidate.get(key)

        if ref_value is None or cand_value is None:
            failures.append(
                f"{key}: missing in "
                f"{'reference' if ref_value is None else 'candidate'}"
            )
            continue

        if key in PLUS_ONE_KEYS:
            try:
                ref_tick = int(ref_value)
                cand_tick = int(cand_value)
            except ValueError:
                failures.append(
                    f"{key}: expected integer tick values, got "
                    f"reference={ref_value!r} candidate={cand_value!r}"
                )
                continue

            delta = cand_tick - ref_tick
            if delta not in profile.accepted_tick_deltas:
                expected = " or ".join(
                    f"reference + {tick_delta}"
                    if tick_delta
                    else "reference"
                    for tick_delta in profile.accepted_tick_deltas
                )
                failures.append(
                    f"{key}: expected candidate to equal {expected}, got "
                    f"reference={ref_tick} candidate={cand_tick}"
                )
            continue

        if ref_value != cand_value:
            failures.append(
                f"{key}: reference={ref_value!r} candidate={cand_value!r}"
            )

    if failures:
        print("compare_stats: FAIL")
        print(f"profile={profile.name}")
        print(f"reference={reference_path}")
        print(f"candidate={candidate_path}")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print("compare_stats: PASS")
    print(f"profile={profile.name}")
    print(f"reference={reference_path}")
    print(f"candidate={candidate_path}")
    print(f"compared_keys={compared}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        required=True,
        help="Comparison rule-set to apply.",
    )
    args = parser.parse_args()

    return compare(
        reference_path=args.reference,
        candidate_path=args.candidate,
        profile=PROFILES[args.profile],
    )


if __name__ == "__main__":
    sys.exit(main())
