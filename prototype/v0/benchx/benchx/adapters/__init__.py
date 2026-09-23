"""Harness adapters, in two halves (#31).

The driving half turns an order into invocations and never builds results;
the translating half (not yet implemented) turns one invocation plus the
context document into ingest objects and never inspects the machine.
`harness.name` in the order selects the pair.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..worker import context
from ..worker.errors import OrderRejected


@dataclass(frozen=True)
class Case:
    """One planned unit of execution. `name` is None when the harness cannot
    enumerate its cases, so the whole suite is one unit (worker-prototype G5)."""

    name: str | None
    label: str


@dataclass
class Invocation:
    case: Case
    argv: list
    returncode: int
    timed_out: bool
    started_at: str
    ended_at: str
    duration_seconds: float
    raw_path: Path | None = None
    raw: dict | None = field(default=None, repr=False)
    stderr_tail: str = ""


def get(name: str):
    if name == "google-benchmark":
        from .gbench import drive
    elif name == "pyperf":
        from .pyperf import drive
    else:
        raise OrderRejected(f"no adapter for harness {name!r}")
    return drive


def run_process(argv: list, timeout: float | None, cwd: Path | None = None,
                env: dict | None = None):
    """Run a command, keeping timing and output. Never raises on failure."""
    started_at = context.now()
    began = time.monotonic()
    timed_out = False
    try:
        done = subprocess.run(
            [str(a) for a in argv],
            cwd=str(cwd) if cwd else None,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        returncode, stdout, stderr = done.returncode, done.stdout, done.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = -1
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
    return {
        "argv": [str(a) for a in argv],
        "returncode": returncode,
        "timed_out": timed_out,
        "started_at": started_at,
        "ended_at": context.now(),
        "duration_seconds": round(time.monotonic() - began, 6),
        "stdout": stdout,
        "stderr": stderr,
    }


def finish(outcome: dict, case: Case, raw_dir: Path, stem: str,
           raw_path: Path) -> Invocation:
    """Keep the harness's own output next to its stdout and stderr."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{stem}.stdout").write_text(outcome["stdout"], encoding="utf-8")
    (raw_dir / f"{stem}.stderr").write_text(outcome["stderr"], encoding="utf-8")
    return Invocation(
        case=case,
        argv=outcome["argv"],
        returncode=outcome["returncode"],
        timed_out=outcome["timed_out"],
        started_at=outcome["started_at"],
        ended_at=outcome["ended_at"],
        duration_seconds=outcome["duration_seconds"],
        raw_path=raw_path if raw_path.is_file() else None,
        raw=read_json(raw_path),
        stderr_tail=outcome["stderr"][-2000:],
    )


def read_json(path: Path | None):
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
