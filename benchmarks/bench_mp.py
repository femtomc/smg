#!/usr/bin/env python3
"""Compare serial and parallel `smg scan` performance on real scan paths."""

from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path

from smg.graph import SemGraph
from smg.langs import load_extractors
from smg.scan import ScanStats, scan_paths
from smg.storage import find_root


def _scan_once(root: Path, paths: list[Path], jobs: int) -> tuple[float, ScanStats]:
    graph = SemGraph()
    started = time.perf_counter()
    stats = scan_paths(graph, root, paths=paths, jobs=jobs)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return elapsed_ms, stats


def _bench(root: Path, paths: list[Path], jobs: int, samples: int) -> tuple[float, ScanStats]:
    timings: list[float] = []
    last_stats: ScanStats | None = None
    for _ in range(samples):
        elapsed_ms, stats = _scan_once(root, paths, jobs)
        timings.append(elapsed_ms)
        last_stats = stats
    assert last_stats is not None
    return statistics.median(timings), last_stats


def _parse_jobs(raw: str) -> list[int]:
    jobs = sorted({int(item.strip()) for item in raw.split(",") if item.strip()})
    if not jobs or any(job < 1 for job in jobs):
        raise argparse.ArgumentTypeError("jobs must be a comma-separated list of positive integers")
    return jobs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=["src", "tests"], help="paths to scan, relative to project root")
    parser.add_argument("--jobs", type=_parse_jobs, default=_parse_jobs("1,2,4,8"), help="worker counts to compare")
    parser.add_argument("--samples", type=int, default=3, help="samples per worker count")
    args = parser.parse_args()

    if args.samples < 1:
        raise SystemExit("--samples must be at least 1")

    load_extractors()
    root = find_root()
    if root is None:
        raise SystemExit("no .smg project root found")

    paths = [(root / path).resolve() for path in args.paths]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise SystemExit(f"scan path(s) not found: {', '.join(missing)}")

    print(f"root: {root}")
    print(f"paths: {', '.join(str(path.relative_to(root)) for path in paths)}")
    print(f"samples: {args.samples}\n")

    rows: list[tuple[int, float, ScanStats]] = []
    for jobs in args.jobs:
        elapsed_ms, stats = _bench(root, paths, jobs, args.samples)
        rows.append((jobs, elapsed_ms, stats))

    baseline = rows[0][1]
    print(f"{'jobs':>4s} {'median ms':>10s} {'speedup':>8s} {'files':>6s} {'nodes':>7s} {'edges':>7s} {'skipped':>8s}")
    print("-" * 66)
    for jobs, elapsed_ms, stats in rows:
        speedup = baseline / elapsed_ms if elapsed_ms else 0.0
        print(
            f"{jobs:4d} {elapsed_ms:10.1f} {speedup:8.2f} "
            f"{stats.files:6d} {stats.nodes_added:7d} {stats.edges_added:7d} {stats.skipped_edges:8d}"
        )


if __name__ == "__main__":
    main()
