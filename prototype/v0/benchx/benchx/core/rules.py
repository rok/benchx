"""Rules JSON Schema cannot express, run once a document fits its schema.

Because the structural check has passed, rules may index into required fields
directly. Each rule raises a `RuleViolation` for the first breach it finds;
`check_result` runs them in order, so the first rule to raise wins.
"""

import json
from datetime import datetime
from typing import Any

from .errors import PathParts, PrimarySourceMismatch, RuleViolation


def check(data: dict[str, Any], kind: str) -> None:
    """Raise a `RuleViolation` for the first rule `data` breaks.

    Kinds without rules always pass.
    """
    if kind == "measurement-result":
        check_result(data)


# --- result ------------------------------------------------------------------


def check_result(data: dict[str, Any]) -> None:
    primary_source(data)
    one_estimate_per_estimator(data)
    ordered_bounds(data)
    ordered_timestamps(data)
    repetition_counts(data)


def primary_source(data: dict[str, Any]) -> None:
    """The primary subject component's source, when given, is the top-level source."""
    expected = data["source"]["uri"]
    components = data["coordinates"]["subject"]["components"]

    for index, component in enumerate(components):
        if component["role"] != "primary":
            continue

        reported = component.get("source")
        if reported is None or reported == expected:
            continue

        raise PrimarySourceMismatch(
            path=("coordinates", "subject", "components", index, "source"),
            reported=reported,
            expected=expected,
        )


def one_estimate_per_estimator(data: dict[str, Any]) -> None:
    """At most one producer estimate per estimator declaration."""
    summaries = data["measurement"].get("summaries", [])
    seen: set[str] = set()

    for index, summary in enumerate(summaries):
        if summary["type"] != "estimate":
            continue

        estimator = summary["estimator"]
        key = json.dumps(estimator, sort_keys=True)
        if key not in seen:
            seen.add(key)
            continue

        raise RuleViolation(
            path=("measurement", "summaries", index),
            rule="duplicate-estimate",
            reason=f"duplicate estimate for estimator {estimator['name']!r}",
        )


def ordered_bounds(data: dict[str, Any]) -> None:
    """Constraints, intervals, and source bounds are non-empty: lower <= upper."""
    measurement = data["measurement"]

    constraint = measurement.get("constraint")
    if constraint is not None and constraint["kind"] == "interval":
        _raise_on_empty_interval(
            path=("measurement", "constraint"),
            lower=constraint["lower"],
            upper=constraint["upper"],
            closed=constraint["lower_inclusive"] and constraint["upper_inclusive"],
        )

    for index, summary in enumerate(measurement.get("summaries", [])):
        if "lower" not in summary or "upper" not in summary:
            continue

        _raise_on_empty_interval(
            path=("measurement", "summaries", index),
            lower=summary["lower"],
            upper=summary["upper"],
            closed=True,
        )


def _raise_on_empty_interval(
    path: PathParts, lower: float, upper: float, closed: bool
) -> None:
    if lower > upper or (lower == upper and not closed):
        raise RuleViolation(
            path=path,
            rule="empty-interval",
            reason=f"empty interval from {lower} to {upper}",
        )


def ordered_timestamps(data: dict[str, Any]) -> None:
    """ended_at, when given, is not before started_at."""
    provenance = data["provenance"]
    if "ended_at" not in provenance:
        return

    started = datetime.fromisoformat(provenance["started_at"])
    ended = datetime.fromisoformat(provenance["ended_at"])
    if ended >= started:
        return

    raise RuleViolation(
        path=("provenance", "ended_at"),
        rule="ended-before-started",
        reason="ended_at is before started_at",
    )


def repetition_counts(data: dict[str, Any]) -> None:
    """completed_repetitions does not exceed attempted_repetitions."""
    procedure = data.get("procedure", {})
    attempted = procedure.get("attempted_repetitions")
    completed = procedure.get("completed_repetitions")
    if attempted is None or completed is None:
        return
    if completed <= attempted:
        return

    raise RuleViolation(
        path=("procedure", "completed_repetitions"),
        rule="repetition-counts",
        reason=f"{completed} completed repetitions exceed {attempted} attempted",
    )
