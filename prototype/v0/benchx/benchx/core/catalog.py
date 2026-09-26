"""The schemas shipped with benchx."""

import json
from functools import cache
from importlib import resources

from jsonschema import Draft202012Validator, FormatChecker


@cache
def lookup(kind: str, version: int) -> Draft202012Validator | None:
    file = (
        resources.files(__package__) / "schemas" / kind / str(version) / "schema.json"
    )
    if not file.is_file():
        return None

    schema = json.loads(file.read_text("utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())
