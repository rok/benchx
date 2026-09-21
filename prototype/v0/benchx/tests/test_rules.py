import copy

import pytest

from benchx.core import rules, validation
from benchx.core.errors import Code, PrimarySourceMismatch, RuleViolation


def check(data: dict) -> RuleViolation | None:
    """Return the rule `data` breaks, or None. Its schema must already fit."""
    validation.check(data, validation.find_schema(data, "measurement-result"))
    try:
        rules.check(data, "measurement-result")
    except RuleViolation as violation:
        return violation
    return None


def where(issue: RuleViolation) -> tuple:
    return issue.rule, issue.path


@pytest.mark.parametrize("name", ["adhoc", "arrow"])
def test_schema_doc_examples_break_no_rules(request, name):
    assert check(request.getfixturevalue(name)) is None


def test_kind_without_rules_passes():
    assert rules.check({}, "comparison-document") is None


def test_primary_source_mismatch(adhoc):
    adhoc["coordinates"]["subject"]["components"][0]["source"] = (
        "https://github.com/someone/fork"
    )
    issue = check(adhoc)
    assert issue == PrimarySourceMismatch(
        path=("coordinates", "subject", "components", 0, "source"),
        reported="https://github.com/someone/fork",
        expected=adhoc["source"]["uri"],
    )
    assert issue.code is Code.IDENTITY_VIOLATION


def test_primary_source_match_is_fine(adhoc):
    adhoc["coordinates"]["subject"]["components"][0]["source"] = adhoc["source"]["uri"]
    assert check(adhoc) is None


def test_duplicate_estimate(arrow):
    arrow["measurement"]["summaries"].append(
        copy.deepcopy(arrow["measurement"]["summaries"][0])
    )
    issue = check(arrow)
    assert type(issue) is RuleViolation and issue.code is Code.MALFORMED
    assert where(issue) == ("duplicate-estimate", ("measurement", "summaries", 3))


def test_different_method_versions_are_different_estimators(arrow):
    other = copy.deepcopy(arrow["measurement"]["summaries"][0])
    other["estimator"]["method_version"] = "benchx/mean/v2"
    arrow["measurement"]["summaries"].append(other)
    assert check(arrow) is None


def test_inverted_confidence_interval(arrow):
    arrow["measurement"]["summaries"][2].update(lower=0.04, upper=0.03)
    assert where(check(arrow)) == ("empty-interval", ("measurement", "summaries", 2))


@pytest.mark.parametrize(
    "lower, upper, inclusive, ok",
    [
        (1, 2, False, True),
        (2, 2, True, True),
        (2, 2, False, False),
        (3, 2, True, False),
    ],
)
def test_censored_interval(adhoc, lower, upper, inclusive, ok):
    adhoc["measurement"] = {
        "status": "censored",
        "reason": "timeout",
        "constraint": {
            "kind": "interval",
            "lower": lower,
            "upper": upper,
            "lower_inclusive": inclusive,
            "upper_inclusive": inclusive,
            "cause": "timeout",
        },
    }
    assert (check(adhoc) is None) is ok


def test_ended_before_started(adhoc):
    adhoc["provenance"]["ended_at"] = "2026-09-14T10:00:00Z"
    assert where(check(adhoc)) == ("ended-before-started", ("provenance", "ended_at"))


def test_completed_exceeds_attempted(adhoc):
    adhoc["procedure"]["completed_repetitions"] = 6
    assert where(check(adhoc)) == (
        "repetition-counts",
        ("procedure", "completed_repetitions"),
    )


def test_first_rule_in_order_wins(adhoc):
    adhoc["coordinates"]["subject"]["components"][0]["source"] = (
        "https://example.org/other"
    )
    adhoc["procedure"]["completed_repetitions"] = 6
    assert check(adhoc).rule == "primary-source"
