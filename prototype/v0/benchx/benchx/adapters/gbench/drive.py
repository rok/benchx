"""Google Benchmark, driving half (worker-prototype.md sections 3-4).

One invocation per case, so a crash costs one case rather than the suite.
"""

from __future__ import annotations

import re
from pathlib import Path

from ... import adapters
from ...worker import keys
from ...worker.errors import OrderRejected, PlanFailed

NAME = "google-benchmark"
QUANTITIES = {"wall-time": "real_time", "cpu-time": "cpu_time"}
PROTOCOL_KEYS = ("repetitions", "calibration", "warmup")

DEFAULT_REPETITIONS = 1
DEFAULT_MIN_TIME_SECONDS = 0.5


def check_order(order) -> None:
    levels = order.protocol.get("repetitions", {}).get("levels", [])
    if len(levels) > 1 or any(level["unit"] != "repetition" for level in levels):
        raise OrderRejected(
            f"{NAME} repeats in one process: protocol.repetitions takes a single "
            "level with unit 'repetition'"
        )
    if order.protocol.get("warmup", {}).get("mode") == "fixed":
        raise OrderRejected(f"{NAME} warms up by time, not by count")


def repetitions(order) -> int:
    return order.repetition_level("repetition", DEFAULT_REPETITIONS)


def calibration_seconds(order) -> float:
    calibration = order.protocol.get("calibration", {})
    if calibration.get("mode") == "adaptive":
        return calibration["minimum_sample_seconds"]
    return DEFAULT_MIN_TIME_SECONDS


def _min_time_arg(target, seconds: float) -> str:
    """Releases before 1.8 reject the `s` suffix, so probe once while planning."""
    suffixed = f"--benchmark_min_time={seconds}s"
    probe = adapters.run_process(
        [target.executable, "--benchmark_list_tests=true", suffixed], timeout=120
    )
    return suffixed if probe["returncode"] == 0 else f"--benchmark_min_time={seconds}"


def plan(order, target) -> list:
    """The planned set: the cases the harness lists under the order's filter."""
    argv = [target.executable, "--benchmark_list_tests=true"]
    if "filter" in order.document:
        argv.append(f"--benchmark_filter={order.document['filter']}")
    listed = adapters.run_process(argv, timeout=300)
    if listed["returncode"] != 0:
        raise PlanFailed(
            f"{target.executable} could not list its cases: "
            f"{listed['stderr'].strip()[:200]}"
        )
    target.harness_options["min_time_arg"] = _min_time_arg(
        target, calibration_seconds(order)
    )
    return [
        adapters.Case(name=line.strip(), label=line.strip())
        for line in listed["stdout"].splitlines()
        if line.strip()
    ]


def build_argv(order, target, case, raw_path: Path) -> list:
    calibration = order.protocol.get("calibration", {})
    if calibration.get("mode") == "fixed":
        min_time = f"--benchmark_min_time={calibration['n_iterations']}x"
    else:
        min_time = target.harness_options.get(
            "min_time_arg", f"--benchmark_min_time={calibration_seconds(order)}s"
        )
    argv = [
        target.executable,
        f"--benchmark_filter=^{re.escape(case.name)}$",
        f"--benchmark_repetitions={repetitions(order)}",
        min_time,
        "--benchmark_report_aggregates_only=false",
        f"--benchmark_out={raw_path}",
        "--benchmark_out_format=json",
    ]
    warmup = order.protocol.get("warmup", {})
    if warmup.get("mode") == "time":
        argv.append(f"--benchmark_min_warmup_time={warmup['seconds']}")
    elif warmup.get("mode") == "none":
        argv.append("--benchmark_min_warmup_time=0")
    return argv


def invoke(order, target, case, raw_dir: Path, timeout: float) -> adapters.Invocation:
    raw_dir.mkdir(parents=True, exist_ok=True)
    stem = keys.to_filename(case.label)
    raw_path = raw_dir / f"{stem}.json"
    outcome = adapters.run_process(
        build_argv(order, target, case, raw_path), timeout=timeout
    )
    return adapters.finish(outcome, case, raw_dir, stem, raw_path)
