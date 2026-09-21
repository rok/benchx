"""`inspect` runs the stages in order and returns the first issue any of them finds."""

import json

import pytest

from benchx.core import inspect
from benchx.core.errors import (
    BadNumber,
    Code,
    DocumentError,
    PrimarySourceMismatch,
    ReadError,
    SchemaNotFound,
    StructureError,
)


def error(path, kind=DocumentError):
    """The error `inspect` raises for this file."""
    with pytest.raises(kind) as raised:
        inspect(path, "measurement-result")
    return raised.value


def test_valid_document_is_returned(write, adhoc):
    assert inspect(write(adhoc), "measurement-result") == adhoc


def test_read_error(write):
    assert type(error(write('{"schema_version": 5, "x": NaN}'))) is BadNumber


def test_unparseable_file(write):
    assert type(error(write("{"))) is ReadError


def test_missing_schema(write):
    assert (
        type(error(write({"schema_version": 99, "anything": "goes"}))) is SchemaNotFound
    )


def test_structure_checked_before_rules(write, adhoc):
    # Breaks a rule too, and would crash rules that assume structure if they ran.
    adhoc["coordinates"]["quantity"]["unit"] = "seconds"
    del adhoc["coordinates"]["subject"]
    issue = error(write(adhoc))
    assert type(issue) is StructureError and issue.path == ("coordinates",)


def test_rules_run_when_structure_passes(write, adhoc):
    adhoc["coordinates"]["subject"]["components"][0]["source"] = (
        "https://example.org/other"
    )
    assert type(error(write(adhoc))) is PrimarySourceMismatch


def test_error_rendering(write, adhoc):
    adhoc["procedure"]["slot"] = -1
    assert str(error(write(adhoc))) == (
        "malformed at /procedure/slot: -1 is less than the minimum of 0"
    )


def test_codes_serialize_as_strings():
    assert json.dumps({"code": Code.UNIT_CONFLICT}) == '{"code": "unit-conflict"}'
