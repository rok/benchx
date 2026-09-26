"""Problems found in documents. Match on class; `code` is what leaves benchx."""

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from jsonpointer import JsonPointer

PathParts = tuple[str | int, ...]


class Code(StrEnum):
    MALFORMED = "malformed"
    IDENTITY_VIOLATION = "identity-violation"
    # Store-dependent; reported by ingest.
    IDEMPOTENCY_CONFLICT = "idempotency-conflict"
    UNIT_CONFLICT = "unit-conflict"
    ATTEMPT_CONFLICT = "attempt-conflict"
    QUARANTINED = "quarantined"


@dataclass(frozen=True, kw_only=True)
class DocumentError:
    code: ClassVar[Code] = Code.MALFORMED
    path: PathParts = ()

    @property
    def message(self) -> str:
        raise NotImplementedError

    @property
    def location(self) -> str | None:
        return JsonPointer.from_parts(self.path).path or "/"

    def __str__(self) -> str:
        if self.location is None:
            return f"{self.code}: {self.message}"
        return f"{self.code} at {self.location}: {self.message}"


@dataclass(frozen=True, kw_only=True)
class ReadError(DocumentError):
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


@dataclass(frozen=True, kw_only=True)
class DuplicateKey(ReadError):
    key: str
    reason: str = "duplicate key"

    @property
    def message(self) -> str:
        return f"duplicate key {self.key!r}"


@dataclass(frozen=True, kw_only=True)
class BadNumber(ReadError):
    literal: str

    @property
    def message(self) -> str:
        return f"{self.literal}: {self.reason}"


@dataclass(frozen=True, kw_only=True)
class SchemaNotFound(DocumentError):
    reason: str

    @property
    def message(self) -> str:
        return self.reason


@dataclass(frozen=True, kw_only=True)
class StructureError(DocumentError):
    keyword: str
    reason: str

    @property
    def message(self) -> str:
        return self.reason


@dataclass(frozen=True, kw_only=True)
class RuleViolation(DocumentError):
    rule: ClassVar[str]


@dataclass(frozen=True, kw_only=True)
class PrimarySourceMismatch(RuleViolation):
    code: ClassVar[Code] = Code.IDENTITY_VIOLATION
    rule: ClassVar[str] = "primary-source"
    reported: str
    expected: str

    @property
    def message(self) -> str:
        return (
            f"primary component source {self.reported!r} "
            f"differs from source {self.expected!r}"
        )


@dataclass(frozen=True, kw_only=True)
class DuplicateEstimate(RuleViolation):
    rule: ClassVar[str] = "duplicate-estimate"
    estimator: str

    @property
    def message(self) -> str:
        return f"duplicate estimate for estimator {self.estimator!r}"


@dataclass(frozen=True, kw_only=True)
class EmptyInterval(RuleViolation):
    rule: ClassVar[str] = "empty-interval"
    lower: float
    upper: float

    @property
    def message(self) -> str:
        return f"empty interval from {self.lower} to {self.upper}"


@dataclass(frozen=True, kw_only=True)
class EndedBeforeStarted(RuleViolation):
    rule: ClassVar[str] = "ended-before-started"

    @property
    def message(self) -> str:
        return "ended_at is before started_at"


@dataclass(frozen=True, kw_only=True)
class CompletedExceedsAttempted(RuleViolation):
    rule: ClassVar[str] = "repetition-counts"
    completed: int
    attempted: int

    @property
    def message(self) -> str:
        return (
            f"{self.completed} completed repetitions exceed {self.attempted} attempted"
        )
