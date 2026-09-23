"""Resolving a work order's target (worker-prototype.md section 2, stage 2).

Both kinds resolve to: something to execute, a checkout to read the revision
from, and the configuration the worker captures rather than the order states.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import context
from .errors import OrderRejected

CMAKE_KEYS = (
    "CMAKE_BUILD_TYPE",
    "CMAKE_CXX_COMPILER",
    "CMAKE_CXX_FLAGS",
    "CMAKE_CXX_FLAGS_DEBUG",
    "CMAKE_CXX_FLAGS_RELEASE",
    "CMAKE_CXX_FLAGS_RELWITHDEBINFO",
)


@dataclass
class Target:
    kind: str
    suite: str
    executable: Path | None = None  # build_dir: the suite binary
    python: Path | None = None  # python_env: the interpreter
    script: Path | None = None  # python_env: the suite script
    source_dir: Path | None = None
    configuration: dict = field(default_factory=dict)
    # Driving-half scratch space, such as a probed flag spelling. Never a
    # coordinate: nothing here reaches a result.
    harness_options: dict = field(default_factory=dict)


def _checkout(order_dir: Path | None, fallback: Path | None):
    from . import vcs

    for candidate in (order_dir, fallback):
        if candidate and candidate.is_dir():
            top = vcs.top_level(candidate)
            if top:
                return top
    return None


def _find_executable(build_dir: Path, suite: str) -> Path:
    matches = [
        p
        for p in build_dir.rglob(suite)
        if p.is_file() and os.access(p, os.X_OK)
    ]
    if not matches:
        raise OrderRejected(f"no executable named {suite!r} under {build_dir}")
    if len(matches) > 1:
        listed = ", ".join(str(p) for p in sorted(matches)[:5])
        raise OrderRejected(f"{len(matches)} executables named {suite!r}: {listed}")
    return matches[0]


def _build_dir_target(order) -> Target:
    spec = order.document["target"]
    build_dir = Path(spec["build_dir"])
    if not build_dir.is_dir():
        raise OrderRejected(f"build_dir {build_dir} is not a directory")
    executable = _find_executable(build_dir, order.document["suite"])

    configuration, home = {}, None
    cache = build_dir / "CMakeCache.txt"
    if cache.is_file():
        text = cache.read_text(encoding="utf-8", errors="replace")
        configuration = context.parse_cmake_cache(text, CMAKE_KEYS)
        match = re.search(r"^CMAKE_HOME_DIRECTORY:[A-Z]+=(.*)$", text, re.M)
        if match:
            home = Path(match.group(1).strip())

    declared = spec.get("source_dir")
    return Target(
        kind="build_dir",
        suite=order.document["suite"],
        executable=executable,
        source_dir=_checkout(Path(declared) if declared else None, home or build_dir),
        configuration=configuration,
    )


_PROBE = (
    "import json,platform,sys;"
    "print(json.dumps({'python_version': platform.python_version(),"
    "'python_implementation': platform.python_implementation(),"
    "'python_compiler': platform.python_compiler(),"
    "'executable': sys.executable}))"
)


def _python_env_target(order) -> Target:
    spec = order.document["target"]
    python = Path(spec["python"])
    if not (python.is_file() and os.access(python, os.X_OK)):
        raise OrderRejected(f"python {python} is not an executable file")
    try:
        probe = subprocess.run(
            [str(python), "-c", _PROBE], capture_output=True, text=True, timeout=120
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise OrderRejected(f"cannot run {python}: {exc}") from exc
    if probe.returncode != 0:
        raise OrderRejected(f"{python} failed to start: {probe.stderr.strip()[:200]}")
    configuration = json.loads(probe.stdout)
    configuration.pop("executable", None)

    declared = spec.get("source_dir")
    source_dir = _checkout(Path(declared) if declared else None, Path.cwd())

    suite = order.document["suite"]
    script = Path(suite)
    if not script.is_absolute() and source_dir:
        script = source_dir / suite
    if not script.is_file():
        raise OrderRejected(f"suite script {script} does not exist")

    return Target(
        kind="python_env",
        suite=suite,
        python=python,
        script=script,
        source_dir=source_dir,
        configuration=configuration,
    )


def resolve(order) -> Target:
    kind = order.document["target"]["kind"]
    if kind == "build_dir":
        return _build_dir_target(order)
    if kind == "python_env":
        return _python_env_target(order)
    raise OrderRejected(f"unsupported target kind {kind!r}")
