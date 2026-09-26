from collections.abc import Iterator
from typing import Any, Literal, assert_never

from jsonschema import Draft202012Validator

from . import catalog
from .errors import SchemaNotFound, StructureError

Kind = Literal["measurement-result", "work-order", "comparison-document"]


def find_schema(
    data: dict[str, Any], kind: Kind
) -> tuple[Draft202012Validator | None, list[SchemaNotFound]]:
    if kind == "measurement-result":
        field = "schema_version"
    elif kind == "work-order":
        field = "workorder_version"
    elif kind == "comparison-document":
        field = "comparison_version"
    else:
        assert_never(kind)

    if field not in data:
        reason = f"no {field} field; expected a {kind}"
        return None, [SchemaNotFound(reason=reason)]
    version = data[field]

    # bool is a subclass of int.
    if not isinstance(version, int) or isinstance(version, bool):
        reason = "version must be an integer"
        return None, [SchemaNotFound(path=(field,), reason=reason)]

    validator = catalog.lookup(kind, version)
    if validator is None:
        reason = f"no schema for {kind} version {version}"
        return None, [SchemaNotFound(path=(field,), reason=reason)]

    return validator, []


def check(
    data: dict[str, Any], validator: Draft202012Validator
) -> Iterator[StructureError]:
    for error in validator.iter_errors(data):
        yield StructureError(
            path=tuple(error.absolute_path),
            keyword=str(error.validator),
            reason=error.message,
        )
