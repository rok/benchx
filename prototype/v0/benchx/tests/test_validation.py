import json
from importlib import resources

import pytest
from jsonschema import Draft202012Validator

from benchx.core import validation
from benchx.core.errors import Code, SchemaNotFound, StructureError

TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def check(data: dict) -> StructureError | None:
    """Return the error `data` raises against its schema, or None when it fits."""
    validator = validation.find_schema(data, "measurement-result")
    try:
        validation.check(data, validator)
    except StructureError as error:
        return error
    return None


# --- bundled schemas ---------------------------------------------------------

SCHEMA_FILES = sorted(
    (kind.name, version.name, version / "schema.json")
    for kind in (resources.files("benchx.core") / "schemas").iterdir()
    for version in kind.iterdir()
)


@pytest.mark.parametrize("kind, version, file", SCHEMA_FILES, ids=lambda v: str(v)[:40])
def test_bundled_schemas_are_valid_json_schema(kind, version, file):
    Draft202012Validator.check_schema(json.loads(file.read_text("utf-8")))


def test_result_schema_is_bundled():
    assert ("measurement-result", "5") in {
        (kind, version) for kind, version, _ in SCHEMA_FILES
    }


# --- find_schema -------------------------------------------------------------


def test_finds_result_schema(adhoc):
    validator = validation.find_schema(adhoc, "measurement-result")
    assert isinstance(validator, Draft202012Validator)
    assert validator.schema["$id"] == "urn:benchx:schema:measurement-result:0.1.0"


def test_schema_is_cached(adhoc):
    first = validation.find_schema(adhoc, "measurement-result")
    assert validation.find_schema(adhoc, "measurement-result") is first


def test_unknown_kind_is_a_programming_error(adhoc):
    with pytest.raises(ValueError, match="unknown kind 'nonsense'"):
        validation.find_schema(adhoc, "nonsense")


@pytest.mark.parametrize(
    "data, kind, path, fragment",
    [
        ({"producer": {}}, "measurement-result", (), "no schema_version field"),
        (
            {"comparison_version": 1},
            "measurement-result",
            (),
            "expected a measurement-result",
        ),
        (
            {"schema_version": "5"},
            "measurement-result",
            ("schema_version",),
            "must be an integer",
        ),
        (
            {"schema_version": True},
            "measurement-result",
            ("schema_version",),
            "must be an integer",
        ),
        (
            {"schema_version": 4},
            "measurement-result",
            ("schema_version",),
            "no schema for measurement-result version 4",
        ),
        (
            {"workorder_version": 1},
            "work-order",
            ("workorder_version",),
            "no schema for work-order version 1",
        ),
    ],
)
def test_schema_not_found(data, kind, path, fragment):
    with pytest.raises(SchemaNotFound) as raised:
        validation.find_schema(data, kind)
    assert raised.value.path == path and fragment in raised.value.message


# --- check -------------------------------------------------------------------


@pytest.mark.parametrize("name", ["adhoc", "arrow"])
def test_schema_doc_examples_fit(request, name):
    assert check(request.getfixturevalue(name)) is None


def test_censored_skipped_and_workorder_artifact_fit(adhoc):
    censored = adhoc | {
        "measurement": {
            "status": "censored",
            "reason": "timeout",
            "constraint": {
                "kind": "lower_bound",
                "lower": 60,
                "lower_inclusive": False,
                "cause": "timeout",
            },
        }
    }
    skipped = adhoc | {"measurement": {"status": "skipped", "reason": "not-applicable"}}
    linked = json.loads(json.dumps(adhoc))
    linked["provenance"]["artifacts"] = [
        {
            "kind": "workorder",
            "media_type": "application/json",
            "uri": "file:///tmp/wo.json",
            "sha256": "a" * 64,
        }
    ]
    assert check(censored) is check(skipped) is check(linked) is None


def test_unexpected_property_is_malformed(adhoc):
    adhoc["series_fingerprint"] = "abc"
    issue = check(adhoc)
    assert type(issue) is StructureError and issue.code is Code.MALFORMED
    assert (issue.path, issue.keyword) == ((), "additionalProperties")
    assert (
        issue.message
        == "Additional properties are not allowed ('series_fingerprint' was unexpected)"
    )


@pytest.mark.parametrize(
    "mutate, path, keyword, message",
    [
        (
            lambda d: d.pop("ingest_key"),
            (),
            "required",
            "'ingest_key' is a required property",
        ),
        (
            lambda d: d["provenance"].pop("subject_tree"),
            ("provenance",),
            "required",
            "'subject_tree' is a required property",
        ),
        (
            lambda d: d["provenance"].__setitem__("benchmark_tree", TREE),
            ("provenance",),
            "not",
            None,
        ),
        (
            lambda d: d["measurement"].__setitem__("observations", [{"value": "slow"}]),
            ("measurement", "observations", 0),
            "oneOf",
            None,
        ),
        (
            lambda d: d["measurement"].update({"status": "error", "reason": "timeout"}),
            ("measurement",),
            "not",
            None,
        ),
        (
            lambda d: d["measurement"].__setitem__("status", "partial"),
            ("measurement",),
            "required",
            "'reason' is a required property",
        ),
        (
            lambda d: d["coordinates"]["environment"].pop("identity"),
            ("coordinates", "environment"),
            "required",
            "'identity' is a required property",
        ),
        (
            lambda d: d["coordinates"]["subject"]["components"].append(
                {"role": "primary"}
            ),
            ("coordinates", "subject", "components"),
            "maxContains",
            "Too many items match the given schema (expected at most 1)",
        ),
        (
            lambda d: d["source"].__setitem__("uri", "not a uri"),
            ("source", "uri"),
            "format",
            "'not a uri' is not a 'uri'",
        ),
        (
            lambda d: d["provenance"].__setitem__(
                "started_at", "2026-09-14T10:02:31+02:00"
            ),
            ("provenance", "started_at"),
            "pattern",
            None,
        ),
        (
            lambda d: d["procedure"].__setitem__("round", -1),
            ("procedure", "round"),
            "minimum",
            "-1 is less than the minimum of 0",
        ),
    ],
)
def test_structure_errors(adhoc, mutate, path, keyword, message):
    mutate(adhoc)
    issue = check(adhoc)
    assert type(issue) is StructureError
    assert (issue.path, issue.keyword) == (path, keyword)
    if message is not None:
        assert issue.message == message


def test_most_relevant_issue_is_deterministic(adhoc):
    adhoc["measurement"]["status"] = "done"
    adhoc["procedure"]["round"] = -1
    assert check(adhoc) == check(json.loads(json.dumps(adhoc)))
