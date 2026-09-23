"""pyperf, driving half (worker-prototype.md sections 3-4).

pyperf spawns its own worker processes, and its runner can neither list nor
filter benchmarks, so the whole script is one unit of execution and the
planned set is only known once the output is read (G5).
"""

from __future__ import annotations

from pathlib import Path

from ... import adapters
from ...worker import keys
from ...worker.errors import OrderRejected

NAME = "pyperf"
QUANTITIES = {"wall-time"}
PROTOCOL_KEYS = ("repetitions", "calibration", "warmup")

DEFAULT_PROCESSES = 20
DEFAULT_VALUES = 3
DEFAULT_WARMUPS = 1
DEFAULT_MIN_TIME_SECONDS = 0.1
TIMEOUT_EXIT_CODE = 124


def check_order(order) -> None:
    if "filter" in order.document:
        raise OrderRejected(f"{NAME} has no case filter; scope by suite instead")
    units = {
        level["unit"]
        for level in order.protocol.get("repetitions", {}).get("levels", [])
    }
    unsupported = units - {"process", "value"}
    if unsupported:
        raise OrderRejected(
            f"{NAME} repeats over processes and values, "
            f"not {', '.join(sorted(unsupported))}"
        )
    if order.protocol.get("warmup", {}).get("mode") == "time":
        raise OrderRejected(f"{NAME} warms up by count, not by duration")


def plan(order, target) -> list:
    """One unit: the script. pyperf cannot enumerate its benchmarks."""
    return [adapters.Case(name=None, label=target.suite)]


def build_argv(order, target, raw_path: Path, timeout: float) -> list:
    calibration = order.protocol.get("calibration", {})
    warmup = order.protocol.get("warmup", {})
    if warmup.get("mode") == "none":
        warmups = 0
    else:
        warmups = warmup.get("n_warmup", DEFAULT_WARMUPS)
    argv = [
        target.python,
        target.script,
        f"--output={raw_path}",
        f"--processes={order.repetition_level('process', DEFAULT_PROCESSES)}",
        f"--values={order.repetition_level('value', DEFAULT_VALUES)}",
        f"--warmups={warmups}",
    ]
    if calibration.get("mode") == "fixed":
        argv.append(f"--loops={calibration['n_iterations']}")
    else:
        minimum = calibration.get("minimum_sample_seconds", DEFAULT_MIN_TIME_SECONDS)
        argv.append(f"--min-time={minimum}")
    # pyperf enforces its own timeout and exits 124; the worker's is the backstop.
    argv.append(f"--timeout={timeout}")
    return argv


def invoke(order, target, case, raw_dir: Path, timeout: float) -> adapters.Invocation:
    raw_dir.mkdir(parents=True, exist_ok=True)
    stem = keys.to_filename(case.label)
    raw_path = raw_dir / f"{stem}.json"
    outcome = adapters.run_process(
        build_argv(order, target, raw_path, timeout),
        timeout=timeout * 1.2,
        cwd=target.script.parent,
    )
    invocation = adapters.finish(outcome, case, raw_dir, stem, raw_path)
    if invocation.returncode == TIMEOUT_EXIT_CODE:
        invocation.timed_out = True
    return invocation
