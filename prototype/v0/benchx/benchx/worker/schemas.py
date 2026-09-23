"""Loading and validating the bundled contract schemas.

Temporary home: `benchx.core.validation` (#34) should own this once it can
register schemas by `$id`, which the work order's cross-schema `$ref`s need.
Every bundled schema is registered, so a reference from one to another
resolves without touching the filesystem again.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

SCHEMA_ROOT = Path(__file__).resolve().parent.parent / "core" / "schemas"

# kind -> (directory, version field)
KINDS = {
    "work_order": ("work-order", "workorder_version"),
    "measurement_result": ("measurement-result", "schema_version"),
}


class SchemaError(Exception):
    def __init__(self, kind: str, messages: list[str]):
        self.kind = kind
        self.messages = messages
        super().__init__(f"{kind} does not conform:\n  " + "\n  ".join(messages))


@functools.lru_cache(maxsize=None)
def _registry():
    from referencing import Registry, Resource

    resources = []
    for path in sorted(SCHEMA_ROOT.glob("*/*/schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        if "$id" in schema:
            resources.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(resources)


@functools.lru_cache(maxsize=None)
def load(kind: str, version: int) -> dict:
    directory, _ = KINDS[kind]
    path = SCHEMA_ROOT / directory / str(version) / "schema.json"
    if not path.is_file():
        raise SchemaError(kind, [f"no schema for version {version}"])
    return json.loads(path.read_text(encoding="utf-8"))


def version_of(document: dict, kind: str) -> int:
    _, field = KINDS[kind]
    version = document.get(field)
    if not isinstance(version, int) or isinstance(version, bool):
        raise SchemaError(kind, [f"{field} must be an integer"])
    return version


def validate(document: dict, kind: str) -> None:
    """Raise SchemaError unless `document` conforms to its version of `kind`."""
    from jsonschema import Draft202012Validator

    schema = load(kind, version_of(document, kind))
    validator = Draft202012Validator(
        schema,
        registry=_registry(),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    errors = sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path))
    if errors:
        messages = [
            f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in errors
        ]
        raise SchemaError(kind, messages)
