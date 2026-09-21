"""Everything that can be wrong with a document, as exceptions.

    DocumentError
    ├── ReadError          loader.read: the file is not usable JSON
    │   ├── DuplicateKey
    │   └── BadNumber
    ├── SchemaNotFound     validation.find_schema: no schema applies
    ├── StructureError     validation.check: the document does not fit its schema
    └── RuleViolation      rules.check: a rule the schema cannot express is broken
        └── PrimarySourceMismatch

Each stage raises at the first problem, so a document is either returned whole
or rejected with one reason. Every error carries a rejection `code` from the
schema doc's taxonomy (§5.4). Structure and rule errors carry a `path` into the
document (a tuple of keys and indexes, empty for the root); read errors describe
the file instead.

They are dataclasses as well as exceptions, so a caller can compare them and
read their fields rather than parse their messages. They are not frozen: an
exception is mutated as it propagates, since Python and pytest assign its
__traceback__, which a frozen dataclass refuses.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from jsonpointer import JsonPointer

PathParts = tuple[str | int, ...]


class Code(StrEnum):
    """Rejection codes. Members are their string values."""

    MALFORMED = "malformed"
    IDENTITY_VIOLATION = "identity-violation"
    # Store-dependent; raised by ingest, never by the validation stages.
    IDEMPOTENCY_CONFLICT = "idempotency-conflict"
    UNIT_CONFLICT = "unit-conflict"
    ATTEMPT_CONFLICT = "attempt-conflict"
    QUARANTINED = "quarantined"


@dataclass(kw_only=True)
class DocumentError(Exception):
    code: ClassVar[Code] = Code.MALFORMED
    path: PathParts = ()

    @property
    def message(self) -> str:
        raise NotImplementedError

    @property
    def location(self) -> str | None:
        """Where the error is, for display; None when it concerns the whole file."""
        pointer = JsonPointer.from_parts(self.path).path
        return pointer or "/"

    def __str__(self) -> str:
        if self.location is None:
            return f"{self.code}: {self.message}"
        return f"{self.code} at {self.location}: {self.message}"


# --- loader.read -------------------------------------------------------------


@dataclass(kw_only=True)
class ReadError(DocumentError):
    """The file cannot be read, decoded, or parsed as a JSON object.

    Read errors describe the file, not a place in a parsed document, so they
    have no path; syntax errors carry a line and column.
    """

    reason: str
    line: int | None = None
    column: int | None = None

    @property
    def message(self) -> str:
        return self.reason

    @property
    def location(self) -> str | None:
        if self.line is None:
            return None
        return f"line {self.line}, column {self.column}"


@dataclass(kw_only=True)
class DuplicateKey(ReadError):
    """An object repeats a key; JSON parsers silently keep only one value."""

    key: str
    reason: str = "duplicate key"

    @property
    def message(self) -> str:
        return f"duplicate key {self.key!r}"


@dataclass(kw_only=True)
class BadNumber(ReadError):
    """A number that is not JSON (NaN, Infinity) or not exactly representable."""

    literal: str

    @property
    def message(self) -> str:
        return f"{self.literal}: {self.reason}"


# --- validation.find_schema --------------------------------------------------


@dataclass(kw_only=True)
class SchemaNotFound(DocumentError):
    reason: str

    @property
    def message(self) -> str:
        return self.reason


# --- validation.check --------------------------------------------------------


@dataclass(kw_only=True)
class StructureError(DocumentError):
    keyword: str
    """The JSON Schema keyword that failed, such as required or enum."""
    reason: str

    @property
    def message(self) -> str:
        return self.reason


# --- rules.check -------------------------------------------------------------


@dataclass(kw_only=True)
class RuleViolation(DocumentError):
    rule: str
    """Stable rule name, such as duplicate-estimate."""
    reason: str

    @property
    def message(self) -> str:
        return self.reason


@dataclass(kw_only=True)
class PrimarySourceMismatch(RuleViolation):
    code: ClassVar[Code] = Code.IDENTITY_VIOLATION
    rule: str = "primary-source"
    reason: str = "primary component source differs from the top-level source"
    reported: str
    expected: str

    @property
    def message(self) -> str:
        return (
            f"primary component source {self.reported!r} "
            f"differs from source {self.expected!r}"
        )
