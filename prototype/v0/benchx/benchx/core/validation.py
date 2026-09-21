import json
from functools import cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, exceptions

from .errors import SchemaNotFound, StructureError


def find_schema(data: dict[str, Any], kind: str) -> Draft202012Validator:
    if kind == "measurement-result":
        field = "schema_version"
    elif kind == "work-order":
        field = "workorder_version"
    elif kind == "comparison-document":
        field = "comparison_version"
    else:
        raise ValueError(
            f"unknown kind {kind!r}; expected one of"
            "measurement-result, work-order, comparison-document"
        )

    if field not in data:
        raise SchemaNotFound(reason=f"no {field} field; expected a {kind}")
    version = data[field]

    # bool is a subclass of int in Python, so `true` would otherwise pass.
    if not isinstance(version, int) or isinstance(version, bool):
        raise SchemaNotFound(path=(field,), reason="version must be an integer")

    validator = _load(kind, version)
    if validator is None:
        reason = f"no schema for {kind} version {version}"
        raise SchemaNotFound(path=(field,), reason=reason)

    return validator


def check(data: dict[str, Any], validator: Draft202012Validator) -> None:
    """Raise a `StructureError` for the first way `data` does not fit its schema."""
    try:
        validator.validate(data)
    except exceptions.ValidationError as error:
        raise StructureError(
            path=tuple(error.absolute_path),
            keyword=str(error.validator),
            reason=error.message,
        ) from None


@cache
def _load(kind: str, version: int) -> Draft202012Validator | None:
    file = (
        resources.files(__package__) / "schemas" / kind / str(version) / "schema.json"
    )
    if not file.is_file():
        return None

    contents = json.loads(file.read_text("utf-8"))
    return Draft202012Validator(contents, format_checker=FormatChecker())
