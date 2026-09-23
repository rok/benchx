"""Machine facts the harness is never asked for (worker-prototype.md section 2, stage 4).

Environment identity is captured by the worker for every harness, so results
from different harnesses on one machine share an environment.
"""

from __future__ import annotations

import glob
import os
import platform
import re
from datetime import datetime, timezone

from . import __version__

ENVIRONMENT_SCHEMA = "machine/v1"


def now() -> str:
    """RFC 3339 UTC, the spelling the result schema asserts."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _cpu_model() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine() or "unknown"


def environment() -> dict:
    return {
        "schema": ENVIRONMENT_SCHEMA,
        "identity": {
            "hostname": platform.node() or "unknown",
            "cpu_model": _cpu_model(),
            "cpu_count": os.cpu_count() or 1,
        },
        "metadata": {"machine": platform.machine(), "system": platform.system()},
    }


def _cpu_scaling() -> bool | None:
    paths = glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor")
    governors = []
    for path in paths:
        try:
            with open(path, encoding="utf-8") as handle:
                governors.append(handle.read().strip())
        except OSError:
            return None
    if not governors:
        return None
    return any(g != "performance" for g in governors)


def observed() -> dict:
    """Conditions allowed to vary within a series; never part of identity."""
    snapshot = {
        "kernel": platform.release(),
        "os": platform.platform(),
    }
    try:
        snapshot["load_average_1min"] = os.getloadavg()[0]
    except (OSError, AttributeError):
        pass
    scaling = _cpu_scaling()
    if scaling is not None:
        snapshot["cpu_scaling_enabled"] = scaling
    return snapshot


def warnings() -> list[str]:
    return ["cpu-scaling-enabled"] if _cpu_scaling() else []


def runner() -> dict:
    return {"name": "benchx-worker", "version": __version__}


def parse_cmake_cache(text: str, keys: tuple[str, ...]) -> dict:
    """The allowlisted build settings, from a CMakeCache.txt."""
    found = {}
    pattern = re.compile(r"^([A-Za-z0-9_]+):[A-Z]+=(.*)$")
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if match and match.group(1) in keys and match.group(2):
            found[match.group(1)] = match.group(2)
    return found
