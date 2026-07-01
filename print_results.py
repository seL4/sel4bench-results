#!/usr/bin/env python3
# Copyright 2026, Proofcraft Pty Ltd
#
# SPDX-License-Identifier: BSD-2-Clause

"""Pretty-print results from the .jsonl time series files or in this repo or
   raw sel4bench .json files."""

from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any, Optional

import sel4bench_extract as extract
from sel4bench_extract import FIELDS, Result

# type for a single run; no attempt to model the data content (includes metadata fields)
Entry = dict[str, Any]
# type of the data read from metrics.yml (key -> distribution bool)
Dist = dict[str, bool]

# fields that only exist in entries with distribution data (not early-processing)
DIST_FIELDS = ["min", "q1", "median", "q3", "max"]

# printed by default
DEFAULT_FIELDS = ["mean", "stddev"]

# meta data for each run: jsonl key -> display name
META = {
    "ts": "time",
    "sha": "manifest",
    "sha_kernel": "kernel",
    "sha_bench": "bench",
    "run_id": "run-id",
}

# base URL for linking a run_id
RUN_URL = "https://github.com/seL4/sel4bench/actions/runs"

# URL template for linking a manifest sha
MANIFEST_URL = "https://github.com/seL4/sel4bench-manifest/blob/{}/default.xml"

HERE = os.path.dirname(os.path.abspath(__file__))


def dist_of_metrics(metrics: list[extract.Metric]) -> Dist:
    """Return {key: distribution} for rendering, from metric definitions."""
    return {m["key"]: m.get("distribution", True) for m in metrics}


def read_entries(path: str) -> list[Entry]:
    """Return all non-empty JSON objects in a .jsonl file, in file order."""
    entries: list[Entry] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            entries.append(json.loads(line))
    if not entries:
        raise ValueError(f"{path}: no entries")
    return entries


def read_results_json(path: str, metrics: list[extract.Metric]) -> Entry:
    """Extract results from a raw sel4bench JSON result file as time series entry."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return extract.extract_entry(data, metrics)


def read_results_log(path: str, metrics: list[extract.Metric]) -> Entry:
    """Extract results from a raw sel4bench log file as time series entry."""
    with open(path, encoding="utf-8") as f:
        match = re.search(r"JSON OUTPUT\n(.*?)END JSON OUTPUT", f.read(), re.DOTALL)
    if match is None:
        raise ValueError(f"{path}: no 'JSON OUTPUT ... END JSON OUTPUT' block found")
    data = json.loads(match.group(1))
    return extract.extract_entry(data, metrics)


def read_results(path: str, metrics: list[extract.Metric]) -> list[Entry]:
    """Read a time series from a .jsonl, raw .json, or raw sel4bench log file.
       Return a single-element list for the raw .json and log cases."""
    if path.endswith(".jsonl"):
        return sorted(read_entries(path), key=lambda entry: entry.get("run_id", 0))
    elif path.endswith(".json"):
        return [read_results_json(path, metrics)]
    else:
        return [read_results_log(path, metrics)]


def first_iteration(iterations: list[Result]) -> Result:
    """Result array for the first iteration"""
    return iterations[0]


def fmt_time(ts: str) -> str:
    """Render timestamps like 2026-06-23T00:04:35Z as 'YYYY-MM-DD HH:MM:SS UTC'"""
    if not isinstance(ts, str) or "T" not in ts or len(ts) != 20:
        return ts
    return ts.replace('T', ' ').replace('Z', " UTC")


def fmt(value: int | float | str) -> str:
    """Format a numeric cell; drop trailing .0 for whole numbers."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def fmt_delta(cur: int | float | None, prev: int | float | None) -> str:
    """Signed change from prev to cur, or '' if not comparable."""
    if not isinstance(cur, (int, float)) or not isinstance(prev, (int, float)):
        return ""
    # we want only one decimal place; also makes float 0 comparison valid below
    d = round(cur - prev, 1)
    if d == 0:
        return ""
    s = fmt(d)
    return s if s.startswith("-") else "+" + s


def fmt_pct(cur: int | float | None, prev: int | float | None) -> str:
    """Signed percentage change from prev to cur, or '' if not comparable."""
    if not isinstance(cur, (int, float)) or not isinstance(prev, (int, float)):
        return ""
    if prev == 0 or cur == prev:
        return ""
    p = round((cur - prev) / prev * 100, 1)
    s = fmt(p) + "%"
    return s if s.startswith("-") else "+" + s


def build_rows(
    entry: Entry, metrics: Dist, prev: Optional[Entry], fields: list[str]
) -> tuple[list[str], list[list[str]], list[list[str]], list[list[str]]]:
    """Return (header, rows, deltas, pcts) of cell strings for the table."""
    header = ["Metric"] + fields
    rows: list[list[str]] = []     # value strings and metric key in column 0
    deltas: list[list[str]] = []   # absolute delta strings ("" where none); col 0 unused
    pcts: list[list[str]] = []     # percentage delta strings ("" where none)
    for key, iterations in entry.items():
        if key in META or not isinstance(iterations, list):
            continue
        results = first_iteration(iterations)
        dist = metrics.get(key, True)
        prev_results = prev.get(key) if prev else None
        prev_result = first_iteration(prev_results) if prev_results else None
        cells, dcells, pcells = [key], [""], [""]
        for field in fields:
            i = FIELDS.index(field)
            v = results[i]
            if not dist and field in DIST_FIELDS:
                cells.append("-")
            else:
                cells.append(fmt(v))
            pv = prev_result[i] if isinstance(prev_result, list) \
                 and i < len(prev_result) else None
            dcells.append(fmt_delta(v, pv))
            pcells.append(fmt_pct(v, pv))
        rows.append(cells)
        deltas.append(dcells)
        pcts.append(pcells)
    return header, rows, deltas, pcts


def render_markdown(
    entry: Entry,
    metrics: Dist,
    prev: Optional[Entry] = None,
    fields: list[str] = FIELDS,
    abs_delta: bool = False,
) -> str:
    """Render one entry as a Markdown table, optionally with delta columns."""
    header, rows, deltas, pcts = build_rows(entry, metrics, prev, fields)

    # optional percentage delta and absolute delta
    # no delta for n; no percentage delta for stddev
    def expand(values: list[str], dvalues: list[str], pvalues: list[str]) -> list[str]:
        out = [values[0]]
        for i, field in enumerate(fields, start=1):
            # small offset for stddev and n columns on terminal
            out.append("  " + values[i] if field == "stddev" else values[i])
            if prev and field != "n":
                if abs_delta:
                    out.append(dvalues[i])
                if field != "stddev":
                    out.append(pvalues[i])
        return out

    n = len(header)
    cells = [expand(header, ["Δ"] * n, ["Δ%"] * n)]
    for row, drow, prow in zip(rows, deltas, pcts):
        cells.append(expand(row, drow, prow))

    widths = [max(len(r[i]) for r in cells) for i in range(len(cells[0]))]

    def line(row: list[str]) -> str:
        parts = (f"{c:<{widths[i]}}" if i == 0 else f"{c:>{widths[i]}}"
                 for i, c in enumerate(row))
        return "| " + " | ".join(parts) + " |"

    # Left-align name column, right-align the rest
    sep = ["-" * widths[0] if i == 0 else "-" * (widths[i] - 1) + ":"
           for i in range(len(widths))]
    out = [line(cells[0]), "| " + " | ".join(sep) + " |"]
    out += [line(c) for c in cells[1:]]
    return "\n".join(out)


def find_entry(entries: list[Entry], run_id: Optional[int]) -> Optional[Entry]:
    """The entry with run_id, or the latest entry if run_id is None.

    Returns None if a specific run_id is requested but not present.
    """
    if run_id is None:
        return entries[-1]
    return next((e for e in entries if e.get("run_id") == run_id), None)


def pick_prev(
    entries: list[Entry],
    base: Optional[list[Entry]],
    run_id: Optional[int],
    diff_ref: int,
) -> Optional[Entry]:
    """Return the entry to diff against. Diff against `base` if given, else
       against `entries` itself. `run_id` selects the anchor: the entry with
       that run_id, or the last entry if run_id is None or not present. `diff_ref`
       is relative to the anchor when it is not an absolute run-id."""
    series = base if base is not None else entries
    anchor = find_entry(series, run_id) or series[-1]
    if diff_ref == 0:
        # For a base series, diff the input against the base anchor; within a
        # single series anchor==input, so nothing to diff against.
        return anchor if base is not None else None
    if diff_ref < 0:
        pidx = series.index(anchor) + diff_ref
        return series[pidx] if pidx >= 0 else None
    return find_entry(series, diff_ref)


def config_of_path(path: str) -> str:
    """Return CONFIG in path/to/CONFIG.jsonl"""
    return os.path.splitext(os.path.basename(path))[0]

def show_file(
    path: str,
    metrics: list[extract.Metric],
    fields: list[str],
    run_id: Optional[int],
    diff_ref: int,
    abs_delta: bool,
    base: Optional[list[Entry]] = None,
    base_path: Optional[str] = None,
) -> Optional[int]:
    """Print the table for one file at the given run_id (None = latest).

    A .jsonl file is treated as a time series; a .json file is read as a raw
    sel4bench JSON result file; any other file is read as a raw sel4bench log.
    If base exists, the table is diffed against the base series.

    Return the run_id actually shown, to be re-used for other files.
    """
    dist = dist_of_metrics(metrics)
    entries = read_results(path, metrics)
    if not path.endswith(".jsonl"):
        run_id = None
        if base is None:
            diff_ref = 0
    entry = find_entry(entries, run_id)

    meta = [f"file:     {path}"]
    if entry is None:
        meta.append(f"(run ID {run_id} not found)")
        print("\n".join(f"- {m}" for m in meta))
        return run_id

    prev = pick_prev(entries, base, run_id, diff_ref)

    for key, name in META.items():
        if key in entry and entry[key] not in ("", None):
            value = entry[key]
            if key == "run_id":
                value = f"[{value}]({RUN_URL}/{value})"
            elif key == "sha":
                value = f"[{value}]({MANIFEST_URL.format(value)})"
            elif key == "ts":
                value = fmt_time(value)
            meta.append(f"{name + ':':10}{value}")
    if prev is not None:
        # not all of these always exist (e.g. for raw .json)
        prev_run_id = prev.get('run_id', '')
        prev_run = f"[{prev_run_id}]({RUN_URL}/{prev_run_id})" if prev_run_id else ""
        prev_sha = prev.get('sha', '')
        prev_manifest = f"[{prev_sha}]({MANIFEST_URL.format(prev_sha)})" if prev_sha else ""
        prev_ts = fmt_time(prev.get('ts', ''))
        parts = []
        if base_path:
            parts.append(f"file={base_path}")
        if prev_ts:
            parts.append(f"time={prev_ts}")
        if prev_manifest:
            parts.append(f"manifest={prev_manifest}")
        if prev_run:
            parts.append(f"run-id {prev_run}")
        # align under "diff to:"
        indent = ",\n" + " " * 12
        meta.append(f"{'diff to:':10}" + indent.join(parts))
    elif diff_ref != 0:
        if diff_ref < 0:
            note = f"(fewer than {-diff_ref} entries before this one)"
        else:
            note = f"(run ID {diff_ref} not found)"
        meta.append(note)

    print(f"## {config_of_path(path)}")
    print()
    print("\n".join(f"- {m}" for m in meta))   # metadata as a bullet list
    print()
    print(render_markdown(entry, dist, prev, fields, abs_delta))
    return entry.get("run_id")


def main() -> None:
    """Parse command-line arguments and print tables for each input file."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jsonl", nargs="+",
                    help="time-series .jsonl file(s), raw sel4bench .json "
                         "result file(s), or raw sel4bench log file(s)")
    ap.add_argument("--metrics-file", default=os.path.join(HERE, "metrics.yml"),
                    help="path to metrics.yml (default: alongside this script)")
    ap.add_argument("--diff", type=int, nargs="?", const=-1, default=0,
                    metavar="REF",
                    help="show diff to previous entry; with a negative "
                         "argument, diff to n-th last entry; with a positive "
                         "argument, diff to given run ID")
    ap.add_argument("--base", metavar="FILE",
                    help="diff against a base .jsonl time series, raw "
                         "sel4bench .json file, or raw sel4bench log file")
    ap.add_argument("--run-id", type=int,
                    help="show this run ID instead of the latest entry")
    ap.add_argument("--full", action="store_true",
                    help="include min, q1, median, q3, max and n columns")
    ap.add_argument("--abs", action="store_true", dest="abs_delta",
                    help="also show absolute delta columns (default: percent only)")
    args = ap.parse_args()

    fields = FIELDS if args.full else DEFAULT_FIELDS
    metrics = extract.load_metrics(args.metrics_file)

    base = read_results(args.base, metrics) if args.base else None

    # Latest entry of first file determines run_id (unless specified)
    run_id = args.run_id
    for i, path in enumerate(args.jsonl):
        if i:
            print()
        shown_run_id = show_file(path, metrics, fields, run_id, args.diff,
                                 args.abs_delta, base, args.base)
        if run_id is None:
            run_id = shown_run_id

if __name__ == "__main__":
    main()
