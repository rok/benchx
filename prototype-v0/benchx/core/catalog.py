"""The schemas in the repository's schemas/ directory."""

import json
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

SCHEMAS = Path(__file__).resolve().parents[3] / "schemas"

# The release shipped for each major version a document can declare.
RELEASES = {
    "measurement-result": {5: "0.1.0"},
}


@cache
def lookup(kind: str, version: int) -> Draft202012Validator | None:
    release = RELEASES.get(kind, {}).get(version)
    if release is None:
        return None

    schema = json.loads((SCHEMAS / kind / release / "schema.json").read_text("utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())
