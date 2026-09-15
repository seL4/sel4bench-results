#!/usr/bin/env nix-shell
#! nix-shell -i bash
#! nix-shell -p pup jq git libxml2
# Copyright 2026, UNSW
#
# SPDX-License-Identifier: BSD-2-Clause

# Usage: ./backfill_old_history.sh /path/to/seL4-website /path/to/sel4bench-manifest

set -eo pipefail

website="$1"
sel4bench_manifest="$2"

project_revision_in_manifest_commit() {
    project_name="$1"
    manifest_commit="$2"

    git -C "$sel4bench_manifest" show $manifest_commit:default.xml \
    | xmllint --xpath "string(//project[@name='$project_name']/@revision)" -
}

PY_PARSE_RESULTS_OLD='
import fileinput
import json
import sys
from pathlib import Path
import os
import shutil

BOARD_TO_NEWNAME = {
    "A9/i.MX6/Sabre": ("sabre", "SABRE", ""),
    "i7-4770/Haswell": ("pc99", "PC99", "_haswell3"),
    "i7-6700/Skylake": ("pc99", "PC99", "_skylake"),
    "i7-6700/Skylake (without meltdown mitigation)": ("pc99", "PC99", "_noksw_skylake"),
    "A57/Tx1/Jetson": ("tx1", "TX1", ""),
    "U54-MC/SiFive Freedom U540/Hifive": ("hifive", "HIFIVE", ""),
}

raw_data = json.load(open(sys.argv[1]))
# Arbitrarily picked to be lower than the results_new and the actual run IDs
run_id = 14000000000
for row in raw_data:
    results = row["results"]
    stage = 0
    for data in results:
        if data[0] == "ISA":
            if stage == 0:
                # Default
                assert data == ["ISA","Mode","Core/SoC/Board","Clock","IRQ Invoke","IPC call","IPC reply","Notify"]
            elif stage == 1:
                # MCS
                assert data == ["ISA","Mode","Core/SoC/Board","Clock","IRQ Invoke","IPC call","IPC reply","Notify"]
            elif stage == 2:
                assert data == ["ISA", "Mode", "Core/SoC/Board", "Clock", "Compiler", "Build command"], data
            elif stage == 3:
                assert data == ["ISA", "Mode", "Core/SoC/Board", "Clock", "Compiler", "Build command"], data
            else:
                raise Exception("oopsISA")

            stage += 1
            continue

        if stage == 0:
            raise Exception("oops0")
        elif stage == 1 or stage == 2:
            is_mcs = stage == 2
            arch, word_size, board, freq, irq_invoke, irq_invoke_stdev, ipc_call, ipc_call_stdev, ipc_reply, ipc_reply_stdev, notify, notify_stdev = data
            irq_invoke, ipc_call, ipc_reply, notify = (int(v) for v in [irq_invoke, ipc_call, ipc_reply, notify])
            irq_invoke_stdev, ipc_call_stdev, ipc_reply_stdev, notify_stdev = (int(v.strip("()")) for v in [irq_invoke_stdev, ipc_call_stdev, ipc_reply_stdev, notify_stdev])

            ts = row["ts"]
            year = ts[:4]
            assert year
            newname = BOARD_TO_NEWNAME[board]
            filename = "{}{}_{}{}.jsonl.prepend".format(newname[1], "_MCS" if is_mcs else "", word_size, newname[2])
            fname = Path(".") / year / newname[0] / filename
            fname.parent.mkdir(parents=True, exist_ok=True)
            with open(fname, "a+") as f:
                json.dump({
                    "ts": ts,
                    "sha": row["sha"],
                    "sha_kernel": row["sha_kernel"],
                    "sha_bench": row["sha_bench"],
                    "run_id": run_id,

                    ## METRICS
                    "ipc_call": [[0, 0, 0, ipc_call, 0, 0, ipc_call_stdev, 16]],
                    "ipc_reply": [[0, 0, 0, ipc_reply, 0, 0, ipc_reply_stdev, 16]],
                    "irq_switch": [[0, 0, 0, irq_invoke, 0, 0, irq_invoke_stdev, 16]],
                    "notify_process": [[0, 0, 0, notify, 0, 0, notify_stdev, 16]],
                }, f)
                f.write("\n")

            run_id += 1


        elif stage == 3 or stage == 4:
            continue
        else:
            raise Exception("oops5")
'

PY_PARSE_RESULTS_NEW='
import fileinput
import json
import sys
import os
from pathlib import Path
import shutil

RUN_TO_FOLDER_NAME = {
    "SABRE_32": "sabre",
    "HIFIVE_64": "hifive",
    "PC99_64_haswell3": "pc99-haswell3",
    "PC99_64_noksw_haswell3": "pc99-haswell3",
    "PC99_64_skylake": "pc99-skylake",
    "PC99_64_noksw_skylake": "pc99-skylake",
    "TX1_64": "tx1",
    "SABRE_MCS_32": "sabre",
    "HIFIVE_MCS_64": "hifive",
    "PC99_MCS_64_haswell3": "pc99-haswell3",
    "PC99_MCS_64_noksw_haswell3": "pc99-haswell3",
    "PC99_MCS_64_skylake": "pc99-skylake",
    "PC99_MCS_64_noksw_skylake": "pc99-skylake",
    "TX1_MCS_64": "tx1",
}

raw_data = json.load(open(sys.argv[1]))
# Picked to be less than the actual run IDs we have stored, and greater than 'old' history
run_id = 15000000000
for row in raw_data:
    results = row["results"]["data"]
    results_default, results_mcs = results["Default"], results["MCS"]
    ts = row["ts"]
    year = ts[:4]

    for result in results_default + results_mcs:
        run_name = result["run"]
        fname = Path(".") / year / RUN_TO_FOLDER_NAME[run_name] / (run_name + ".jsonl.prepend")
        fname.parent.mkdir(parents=True, exist_ok=True)

        with open(fname, "a+") as f:
            json.dump({
                "ts": ts,
                "sha": row["sha"],
                "sha_kernel": row["sha_kernel"],
                "sha_bench": row["sha_bench"],
                "run_id": run_id,
                "compiler": result["compiler"],

                ## METRICS
                "ipc_call": [[0, 0, 0, result["call"][0], 0, 0, result["call"][1], 16]],
                "ipc_reply": [[0, 0, 0, result["reply"][0], 0, 0, result["reply"][1], 16]],
                "ipc_call_fpu": [[0, 0, 0, result["call_fpu"][0], 0, 0, result["call_fpu"][1], 16]] if "call_fpu" in result else None,
                "ipc_reply_fpu": [[0, 0, 0, result["reply_fpu"][0], 0, 0, result["reply_fpu"][1], 16]] if "reply_fpu" in result else None,
                "irq_switch": [[0, 0, 0, result["irq"][0], 0, 0, result["irq"][1], 16]],
                "notify_process": [[0, 0, 0, result["notify"][0], 0, 0, result["notify"][1], 16]],
            }, f)
            f.write("\n")

        run_id += 1

'

# a630c0e43dd1008a7e46614d158f636ecc5708eb is the last commit with About/Performance/index.html
git -C "$website" log --pretty='format:%H' a630c0e43dd1008a7e46614d158f636ecc5708eb -- About/Performance/index.html \
| while IFS= read -r website_commit || [ -n "$website_commit" ]; do
    # Produces the URL like this:
    #   https://github.com/seL4/sel4bench-manifest/blob/014a7f865b0164806c40a6de9af5c3469b973d38/default.xml
    # Which we chop to just get the commit.
    manifest_commit=$(
        git -C "$website" show $website_commit:About/Performance/index.html \
        | pup "a[href^=https://github.com/seL4/sel4bench-manifest/blob] attr{href}" \
        | cut -d'/' -f 7
    )

    timestamp=$(
        git -C "$sel4bench_manifest" show --no-patch --pretty='%aI' $manifest_commit
    )

    sha_kernel=$(project_revision_in_manifest_commit "seL4.git" "$manifest_commit")
    sha_bench=$(project_revision_in_manifest_commit "sel4bench.git" "$manifest_commit")

    export timestamp manifest_commit sha_kernel sha_bench

    git -C "$website" show $website_commit:About/Performance/index.html \
    | pup "table tr json{}" \
    | jq ".[] | .children | map(.text)" \
    | jq --slurp '{ ts: env.timestamp, sha: env.manifest_commit, sha_kernel: env.sha_kernel, sha_bench: env.sha_bench, results: . }'

done \
| jq --slurp > old_history_raw.json


git -C "$website" log --pretty='format:%H' -- _data/benchmarks.json \
| while IFS= read -r website_commit || [ -n "$website_commit" ]; do
    # Produces the URL like this:
    #   https://github.com/seL4/sel4bench-manifest/blob/014a7f865b0164806c40a6de9af5c3469b973d38/default.xml
    # Which we chop to just get the commit.
    manifest_commit=$(
        git -C "$website" show $website_commit:_data/benchmarks.json \
        | jq -r '.sha'
    )
    if [[ "$manifest_commit" == "null" ]]; then
        break
    fi

    timestamp=$(
        git -C "$sel4bench_manifest" show --no-patch --pretty='%aI' $manifest_commit
    )

    sha_kernel=$(project_revision_in_manifest_commit "seL4.git" "$manifest_commit")
    sha_bench=$(project_revision_in_manifest_commit "sel4bench.git" "$manifest_commit")

    export timestamp manifest_commit sha_kernel sha_bench

    git -C "$website" show $website_commit:_data/benchmarks.json \
    | jq '{ ts: env.timestamp, sha: env.manifest_commit, sha_kernel: env.sha_kernel, sha_bench: env.sha_bench, results: . }'
done \
| jq --slurp > new_history_raw.json


python -c "$PY_PARSE_RESULTS_OLD" old_history_raw.json
python -c "$PY_PARSE_RESULTS_NEW" new_history_raw.json

find 202* -type f -name "*.prepend" -exec bash -x -c 'f=${0}; fl=${0%".prepend"}; if [[ -f "$fl" ]]; then cat "$fl" >> "$f"; fi; mv "$f" "$fl"' {} \;
