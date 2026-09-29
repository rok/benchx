"""The schemas shipped with benchx."""

import json
from functools import cache
from importlib import resources

from jsonschema import Draft202012Validator, FormatChecker

# The release shipped for each major version a document can declare.
RELEASES = {
    "measurement-result": {5: "0.1.0"},
}


@cache
def lookup(kind: str, version: int) -> Draft202012Validator | None:
    release = RELEASES.get(kind, {}).get(version)
    if release is None:
        return None

    file = resources.files(__package__) / "schemas" / kind / release / "schema.json"
    schema = json.loads(file.read_text("utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())
