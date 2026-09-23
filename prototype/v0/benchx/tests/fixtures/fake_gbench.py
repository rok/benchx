#!/usr/bin/env python3
"""A stand-in for a Google Benchmark binary, for driving-half tests.

Speaks only the part of the CLI the worker uses. Behaviour is switched with
FAKE_GBENCH_MODE: ok (default), crash, hang, error, partial; and with
FAKE_GBENCH_OLD=1 it rejects the `s` suffix on --benchmark_min_time, the way
releases before 1.8 do.
"""

import json
import os
import re
import sys
import time

CASES = [
    "BM_Take/1024/2",
    "BM_Take/4096/2",
    "BM_TakeChunked/1024/2",
]


def main(argv):
    args = {}
    for item in argv:
        key, _, value = item.partition("=")
        args[key] = value

    min_time = args.get("--benchmark_min_time", "")
    if os.environ.get("FAKE_GBENCH_OLD") and min_time.endswith(("s", "x")):
        print("invalid value for --benchmark_min_time", file=sys.stderr)
        return 1

    if "--benchmark_list_tests" in args:
        pattern = args.get("--benchmark_filter") or ""
        for case in CASES:
            if not pattern or re.search(pattern, case):
                print(case)
        return 0

    mode = os.environ.get("FAKE_GBENCH_MODE", "ok")
    if mode == "hang":
        time.sleep(60)
    if mode == "crash":
        print("segmentation fault", file=sys.stderr)
        return -11
    if mode == "error":
        return 1

    pattern = args.get("--benchmark_filter", "")
    selected = [c for c in CASES if not pattern or re.search(pattern, c)]
    repetitions = int(args.get("--benchmark_repetitions", "1"))
    if mode == "partial":
        repetitions = max(1, repetitions // 2)

    rows = []
    for case in selected:
        for index in range(repetitions):
            rows.append({
                "name": f"{case}/repeat:{index}" if repetitions > 1 else case,
                "run_name": case,
                "run_type": "iteration",
                "repetitions": repetitions,
                "repetition_index": index,
                "threads": 1,
                "iterations": 4096,
                "real_time": 1000.0 + index,
                "cpu_time": 900.0 + index,
                "time_unit": "ns",
            })
    payload = {
        "context": {
            "date": "2026-09-23T10:00:00+00:00",
            "num_cpus": 8,
            "library_build_type": "release",
        },
        "benchmarks": rows,
    }
    out = args.get("--benchmark_out")
    if out:
        with open(out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
    print(f"ran {len(selected)} case(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
