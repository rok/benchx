"""The schemas in the repository's schemas/ directory, or in $BENCHX_SCHEMAS."""

import json
import os
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

SCHEMAS = Path(
    os.environ.get("BENCHX_SCHEMAS") or Path(__file__).resolve().parents[3] / "schemas"
)

# The release shipped for each major version a document can declare.
RELEASES = {
    "measurement-result": {5: "0.1.0"},
    "work-order": {1: "0.1.0"},
}


@cache
def lookup(kind: str, version: int) -> Draft202012Validator | None:
    release = RELEASES.get(kind, {}).get(version)
    schema = _read(kind, release) if release else None
    if schema is None:
        return None

    return Draft202012Validator(
        schema, format_checker=FormatChecker(), registry=_registry()
    )


@cache
def _read(kind: str, release: str) -> dict | None:
    file = SCHEMAS / kind / release / "schema.json"
    if not file.is_file():
        return None

    schema = json.loads(file.read_text("utf-8"))
    if kind == "work-order":
        # Prototype extension proposed to #35 (prototype-design.md §2).
        for name in ("round", "slot"):
            schema["properties"][name] = {
                "description": f"Copied to procedure.{name}.",
                "type": "integer",
                "minimum": 0,
            }
    return schema


@cache
def _registry() -> Registry:
    # Schemas refer to each other by $id, so each validator sees all of them.
    schemas = [
        _read(kind, release)
        for kind, releases in RELEASES.items()
        for release in releases.values()
    ]
    return Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema))
        for schema in schemas
        if schema is not None
    )
