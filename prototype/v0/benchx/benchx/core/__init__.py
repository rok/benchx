"""Read, schema-check, and rule-check benchx documents.

Stages return problems with the document rather than raising them, report every
one they find, and may assume earlier stages found none.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import loader, rules, validation
from .errors import DocumentError
from .validation import Kind


@dataclass
class Inspection:
    path: Path
    kind: Kind
    data: dict[str, Any] | None  # None unless valid
    errors: Sequence[DocumentError]

    @property
    def valid(self) -> bool:
        return not self.errors


def inspect(path: Path, kind: Kind) -> Inspection:
    data, read_errors = loader.read(path)
    if data is None:
        return Inspection(path, kind, None, read_errors)

    validator, schema_errors = validation.find_schema(data, kind)
    if validator is None:
        return Inspection(path, kind, None, schema_errors)

    errors: list[DocumentError] = list(validation.check(data, validator))
    if not errors:
        errors = list(rules.check(data, kind))
    return Inspection(path, kind, None if errors else data, errors)
