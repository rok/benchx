import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from benchx.core.catalog import SCHEMAS

EXAMPLES = SCHEMAS / "measurement-result" / "0.1.0" / "examples"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


@pytest.fixture(params=sorted(EXAMPLES.glob("*.json")), ids=lambda path: path.stem)
def example(request: pytest.FixtureRequest) -> dict[str, Any]:
    return load(request.param)


@pytest.fixture
def adhoc() -> dict[str, Any]:
    return load(EXAMPLES / "adhoc.json")


@pytest.fixture
def arrow() -> dict[str, Any]:
    return load(EXAMPLES / "arrow.json")


@pytest.fixture
def write(tmp_path: Path) -> Callable[[str | bytes | dict], Path]:
    def _write(content: str | bytes | dict) -> Path:
        path = tmp_path / "doc.json"
        if isinstance(content, dict):
            content = json.dumps(content)
        if isinstance(content, str):
            content = content.encode()
        path.write_bytes(content)
        return path

    return _write
