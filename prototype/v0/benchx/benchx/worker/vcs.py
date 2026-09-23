"""Revision, dirty state, and tree id of a checkout (worker-prototype.md section 6).

Dirty state is tri-state; when it is unknown the tree id is absent, which is
what the result schema requires.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

UNKNOWN = "unknown"


def _git(*args: str, cwd: Path, env: dict | None = None) -> str | None:
    try:
        done = subprocess.run(
            ("git", *args),
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip()


def top_level(path: Path) -> Path | None:
    out = _git("rev-parse", "--show-toplevel", cwd=path)
    return Path(out) if out else None


def revision_key(checkout: Path) -> str | None:
    return _git("rev-parse", "HEAD", cwd=checkout)


def dirty_state(checkout: Path) -> str:
    out = _git("status", "--porcelain", cwd=checkout)
    if out is None:
        return UNKNOWN
    return "dirty" if out else "clean"


def tree_id(checkout: Path, state: str) -> str | None:
    """Content hash of the working tree: HEAD's tree when clean, else the
    tree written through a temporary index, which never touches the user's."""
    if state == "clean":
        return _git("rev-parse", "HEAD^{tree}", cwd=checkout)
    if state != "dirty":
        return None
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / "index"))
        if _git("read-tree", "HEAD", cwd=checkout, env=env) is None:
            return None
        if _git("add", "-A", cwd=checkout, env=env) is None:
            return None
        return _git("write-tree", cwd=checkout, env=env)


def describe(checkout: Path | None) -> dict:
    """Everything the worker captures from a checkout, in one call."""
    if checkout is None:
        return {"revision": None, "dirty": UNKNOWN, "tree": None}
    state = dirty_state(checkout)
    return {
        "revision": revision_key(checkout),
        "dirty": state,
        "tree": tree_id(checkout, state),
    }
