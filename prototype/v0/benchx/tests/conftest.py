import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(kind: str, name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / kind / f"{name}.json").read_text())


@pytest.fixture
def adhoc() -> dict[str, Any]:
    return copy.deepcopy(fixture("result", "adhoc"))


@pytest.fixture
def arrow() -> dict[str, Any]:
    return copy.deepcopy(fixture("result", "arrow"))


@pytest.fixture
def write(tmp_path: Path) -> Callable[[str | bytes | dict], Path]:
    """Write JSON text, bytes, or a dict to a file and return its path."""

    def _write(content: str | bytes | dict) -> Path:
        path = tmp_path / "doc.json"
        if isinstance(content, dict):
            content = json.dumps(content)
        if isinstance(content, str):
            content = content.encode()
        path.write_bytes(content)
        return path

    return _write
