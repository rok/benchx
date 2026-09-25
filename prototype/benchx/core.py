"""Documents: strict loading, schema validation, canonical form, hashes.

The schemas are read from the repository's schemas/ directory, or from
$BENCHX_SCHEMAS: the result schema (schemas/measurement-result/0.1.0) and the
work-order schema (schemas/work-order/0.1.0, from #35). The work-order schema
is extended here by exactly the two optional fields the
prototype needs and #35 lists as open, `round` and `slot`
(prototype-design.md §2).
"""

import copy
import hashlib
import json
import os
from pathlib import Path

import jsonschema
import rfc8785
from referencing import Registry, Resource

SCHEMA_DIR = Path(os.environ.get("BENCHX_SCHEMAS") or Path(__file__).resolve().parents[2] / "schemas")


def _schema(relative: str) -> dict:
    path = SCHEMA_DIR / relative
    if not path.exists():
        raise RuntimeError(f"schema not found: {path}; run from a benchx checkout or set BENCHX_SCHEMAS")
    return json.loads(path.read_text())


RESULT_SCHEMA = _schema("measurement-result/0.1.0/schema.json")
_ORDER_SCHEMA = _schema("work-order/0.1.0/schema.json")

ORDER_SCHEMA = copy.deepcopy(_ORDER_SCHEMA)
for _name, _meaning in (("round", "procedure.round"), ("slot", "procedure.slot")):
    ORDER_SCHEMA["properties"][_name] = {
        "description": f"Prototype extension proposed to #35: copied to {_meaning}.",
        "type": "integer",
        "minimum": 0,
    }

_REGISTRY = Registry().with_resources(
    (schema["$id"], Resource.from_contents(schema)) for schema in (RESULT_SCHEMA, ORDER_SCHEMA)
)
_RESULT_VALIDATOR = jsonschema.Draft202012Validator(RESULT_SCHEMA, registry=_REGISTRY)
_ORDER_VALIDATOR = jsonschema.Draft202012Validator(ORDER_SCHEMA, registry=_REGISTRY)


class DocumentError(Exception):
    """A document that cannot be accepted, with a schema §5.4 taxonomy code."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _unique_keys(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise DocumentError("malformed", f"duplicate JSON key in {[key for key, _ in pairs]}")
    return result


def _non_finite(token):
    raise DocumentError("malformed", f"invalid JSON number: {token}")


def loads(text: str):
    """Parse strict I-JSON: unique keys, finite numbers, safe integers.

    JSON Schema validation sees a document only after parsing, when duplicate
    keys are gone and NaN is an ordinary float, so these checks come first.
    """
    try:
        value = json.loads(text, object_pairs_hook=_unique_keys, parse_constant=_non_finite)
    except json.JSONDecodeError as e:
        raise DocumentError("malformed", str(e)) from None
    try:
        rfc8785.dumps(value)
    except Exception as e:  # integers beyond 2**53 and similar
        raise DocumentError("malformed", str(e)) from None
    return value


def load(path) -> object:
    return loads(Path(path).read_text(encoding="utf-8"))


def canonical(value) -> bytes:
    """RFC 8785 canonical JSON, as schema §4.3 uses for fingerprints."""
    return rfc8785.dumps(value)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def order_ref(order: dict) -> str:
    """#35 §5: the reference a result carries to the order that produced it."""
    return "sha256:" + sha256_hex(canonical(order))


def _validate(validator, document, kind):
    error = jsonschema.exceptions.best_match(validator.iter_errors(document))
    if error is not None:
        where = "/".join(str(p) for p in error.absolute_path) or "(root)"
        raise DocumentError("malformed", f"{kind} invalid at {where}: {error.message}")


def validate_result(document: dict) -> None:
    _validate(_RESULT_VALIDATOR, document, "result")


def validate_order(order: dict) -> None:
    _validate(_ORDER_VALIDATOR, order, "work order")
