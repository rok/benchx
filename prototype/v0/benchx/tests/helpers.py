"""Shared test helpers: orders built without a validator, and temp checkouts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from benchx.worker.order import Order

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ZERO_REF = "sha256:" + "0" * 64


def make_order(document: dict, path: Path | None = None) -> Order:
    """An Order without jsonschema or rfc8785, which the driving half never needs."""
    return Order(
        path=path or Path("work-order.json"),
        document=document,
        canonical=json.dumps(document, sort_keys=True).encode("utf-8"),
        ref=ZERO_REF,
    )


def gbench_order(build_dir: Path, source_dir: Path | None = None, **extra) -> Order:
    document = {
        "workorder_version": 1,
        "project": "arrow",
        "source": {"uri": "https://github.com/apache/arrow", "type": "git"},
        "harness": {"name": "google-benchmark"},
        "target": {"kind": "build_dir", "build_dir": str(build_dir)},
        "suite": "suite-benchmark",
        "quantities": ["wall-time", "cpu-time"],
        "provenance": {"run_key": "test-run"},
    }
    if source_dir:
        document["target"]["source_dir"] = str(source_dir)
    document.update(extra)
    return make_order(document)


def pyperf_order(python: str, script: Path, source_dir: Path | None = None,
                 **extra) -> Order:
    document = {
        "workorder_version": 1,
        "source": {"uri": "https://github.com/scipy/scipy", "type": "git"},
        "harness": {"name": "pyperf"},
        "target": {"kind": "python_env", "python": python},
        "suite": str(script),
        "quantities": ["wall-time"],
        "provenance": {"run_key": "test-run"},
    }
    if source_dir:
        document["target"]["source_dir"] = str(source_dir)
    document.update(extra)
    return make_order(document)


def make_build_dir(root: Path, suite: str = "suite-benchmark",
                   harness: str = "fake_gbench.py") -> Path:
    build_dir = root / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    target = build_dir / suite
    shutil.copy(FIXTURES / harness, target)
    target.chmod(0o755)
    (build_dir / "CMakeCache.txt").write_text(
        "CMAKE_BUILD_TYPE:STRING=Release\n"
        "CMAKE_CXX_COMPILER:FILEPATH=/usr/bin/c++\n"
        "CMAKE_CXX_FLAGS:STRING=-O2\n"
        "SOMETHING_ELSE:BOOL=ON\n"
        f"CMAKE_HOME_DIRECTORY:INTERNAL={root}\n",
        encoding="utf-8",
    )
    return build_dir


def make_repo(root: Path) -> Path:
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e")
    root.mkdir(parents=True, exist_ok=True)
    (root / "README").write_text("hello\n", encoding="utf-8")
    for args in (("init", "-q"), ("add", "-A"), ("commit", "-qm", "first")):
        subprocess.run(("git", *args), cwd=root, env=env, check=True,
                       capture_output=True)
    return root
