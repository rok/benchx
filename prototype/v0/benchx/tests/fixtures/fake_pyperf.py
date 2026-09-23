#!/usr/bin/env python3
"""A stand-in for a pyperf benchmark script, for driving-half tests.

Accepts the options the worker passes and writes pyperf-shaped JSON.
FAKE_PYPERF_MODE switches: ok (default), crash, hang, timeout.
"""

import json
import os
import sys
import time


def main(argv):
    args = {}
    for item in argv:
        key, _, value = item.partition("=")
        args[key] = value

    mode = os.environ.get("FAKE_PYPERF_MODE", "ok")
    if mode == "hang":
        time.sleep(60)
    if mode == "crash":
        print("Traceback (most recent call last):", file=sys.stderr)
        return 1
    if mode == "timeout":
        return 124

    processes = int(args.get("--processes", "20"))
    values = int(args.get("--values", "3"))
    warmups = int(args.get("--warmups", "1"))
    runs = [{
        "metadata": {"name": "sort a sorted list", "loops": 64, "calibrate_loops": 64},
        "warmups": [[64, 4.0e-06]],
        "values": [],
    }]
    for _ in range(processes):
        runs.append({
            "metadata": {"name": "sort a sorted list", "loops": 64},
            "warmups": [[64, 4.1e-06]] * warmups,
            "values": [4.2e-06] * values,
        })
    payload = {
        "version": "1.0",
        "metadata": {"unit": "second", "cpu_count": 8, "perf_version": "2.10.0"},
        "benchmarks": [{"metadata": {"name": "sort a sorted list"}, "runs": runs}],
    }
    out = args.get("--output")
    if out:
        with open(out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
    print(".", end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
