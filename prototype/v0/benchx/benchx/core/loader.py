"""Read a file into a JSON object, rejecting what Python's json module lets through.

Python's json accepts things that are not interoperable JSON: NaN and Infinity
literals, numbers that overflow a double (1e400 becomes inf), integers that
canonical JSON (RFC 8785, used for fingerprints) cannot represent exactly, and
repeated keys, of which it silently keeps the last. The hooks below raise on the
first of these, which stops the parse.
"""

import json
import math
from pathlib import Path
from typing import Any

from .errors import BadNumber, DuplicateKey, ReadError

MAX_EXACT_INTEGER = 2**53 - 1
"""Largest integer magnitude an IEEE double, and so RFC 8785, represents exactly."""


def read(path: Path) -> dict[str, Any]:
    """Return the file's top-level JSON object, or raise a `ReadError`."""
    text = _read_text(path)
    data = _parse(text)

    if not isinstance(data, dict):
        raise ReadError(reason="top level must be a JSON object")

    return data


def _read_text(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ReadError(reason=f"cannot read file: {exc.strerror or exc}") from None

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReadError(reason=f"invalid UTF-8 at byte {exc.start}") from None


def _parse(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_parse_object,
            parse_constant=_parse_constant,
            parse_float=_parse_float,
            parse_int=_parse_int,
        )
    except json.JSONDecodeError as exc:
        raise ReadError(reason=exc.msg, line=exc.lineno, column=exc.colno) from None
    except RecursionError:
        raise ReadError(reason="nesting too deep") from None


# --- Parser hooks ------------------------------------------------------------
#
# json.loads calls these for every object and number it parses.


def _parse_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}

    for key, value in pairs:
        if key in obj:
            raise DuplicateKey(key=key)
        obj[key] = value

    return obj


def _parse_constant(literal: str) -> float:
    """Called for NaN, Infinity, and -Infinity, none of which are JSON."""
    raise BadNumber(literal=literal, reason="not a JSON number")


def _parse_float(literal: str) -> float:
    value = float(literal)
    if math.isfinite(value):
        return value

    raise BadNumber(literal=literal, reason="overflows a double")


def _parse_int(literal: str) -> int:
    try:
        value = int(literal)
    except ValueError:
        # Longer than Python's integer string conversion limit (4300 digits).
        raise BadNumber(
            literal=literal[:20] + "…", reason="integer too large"
        ) from None

    if abs(value) <= MAX_EXACT_INTEGER:
        return value

    reason = "integer outside ±(2**53 - 1) cannot be represented exactly"
    raise BadNumber(literal=literal, reason=reason)
