<!--
     Copyright 2026, Proofcraft Pty Ltd

     SPDX-License-Identifier: CC-BY-SA-4.0
-->

# seL4 benchmark history

Historical [sel4bench] results for plotting and analysis.

Each successful run of the [sel4bench] workflow adds one set of data points
to the time series files in this repository.

[sel4bench]: https://github.com/seL4/sel4bench

## Repo layout

```
<year>/<platform>/<config>.jsonl    time series data
metrics.yml                         metadata on what benchmarks are tracked
```

## Data format

Each line in the `<config>.jsonl` files has one JSON object, corresponding to
one workflow run:

```json
{"ts": "2026-06-12T05:57:25Z", "sha": "00c86fb8",
 "sha_kernel": "868454e1", "sha_bench": "776ba8a8", "run_id": 27397639006,
 "ipc_call": [363, 365, 368, 366, 368, 373, 2.0, 16],
 "ipc_reply": [346, 347, 348, 348, 349, 349, 1.5, 16],
 "...": []}
```

- `ts`: `created_at` timestamp of the workflow run
- `sha`: sel4bench-manifest SHA; multiple runs (re-runs) can exist for each manifest
- `sha_kernel`: seL4 repo SHA in that manifest (redundant; for plotting)
- `sha_bench`: sel4bench repo SHA in that manifest (redundant; for plotting)
- `run_id`: GitHub Actions run id; disambiguates re-runs of one SHA
- remaining keys: a metric `key` from [metrics.yml](metrics.yml), with value
  `[min, q1, median, mean, q3, max, stddev, n]` (0 for values that don't exist
  for early processing).

Not all metrics exist in all runs. Some configs are missing some benchmarks, new
ones can be added over time. Currently all metrics are cycle counts (lower =
better).
