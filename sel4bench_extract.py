# Copyright 2026, Proofcraft Pty Ltd
#
# SPDX-License-Identifier: BSD-2-Clause

"""Library for extracting results from sel4bench JSON output.
   Shared between this repo and the sel4bencha actions in seL4/ci-actions"""

from __future__ import annotations

from typing import Any, Optional

import yaml

# data field order in a result array
FIELDS = ["min", "q1", "median", "mean", "q3", "max", "stddev", "n"]

# a single result array
Result = list[float | int]
# a benchmark metric definition from metrics.yml
Metric = dict[str, Any]


def load_metrics(path: str) -> list[Metric]:
    """Return the list of metric definitions from a metrics.yml file."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["metrics"]


def find_in_iteration(entries: list[dict], metric: Metric) -> Optional[Result]:
    """Find the benchmark specified by the metric dict (benchmark name + row
       match) within the entries of a single iteration, and extract [min, q1,
       median, mean, q3, max, stddev, n]. Return None if not found."""

    for bench in entries:
        if bench['Benchmark'] != metric['benchmark']:
            continue
        for row in bench['Results']:
            if all(row.get(k) == v for k, v in metric['match'].items()):
                mean = round(row['Mean'])
                stddev = round(row['Stddev'], 1)
                n = row['Samples']
                if metric.get('distribution'):
                    return [round(row['Min']), round(row['1st quantile']),
                            round(row['Median']), mean, round(row['3rd quantile']),
                            round(row['Max']), stddev, n]
                return [0, 0, 0, mean, 0, 0, stddev, n]

    return None


def find_benchmark(data: list[dict], metric: Metric) -> Optional[list[Result]]:
    """Find the benchmark specified by the metric dict (benchmark name + row
       match) and return a list of result arrays [min, q1, median, mean, q3,
       max, stddev, n], one per iteration. Return None if not found."""

    # group by iteration first, so we can keep the iteration matching separate
    # from the benchmark name matching
    by_iteration: dict[Any, list[dict]] = {}
    for bench in data:
        by_iteration.setdefault(bench.get('Iteration', 0), []).append(bench)

    results = []
    for iteration in sorted(by_iteration):
        value = find_in_iteration(by_iteration[iteration], metric)
        if value is not None:
            results.append(value)

    return results if results else None


def extract_entry(data: list[dict], metrics: list[Metric]) -> dict[str, list[Result]]:
    """Reduce raw sel4bench JSON output to {metric key: iterations}"""

    entry: dict[str, list[Result]] = {}
    for metric in metrics:
        value = find_benchmark(data, metric)
        if value is not None:
            entry[metric['key']] = value
    return entry
