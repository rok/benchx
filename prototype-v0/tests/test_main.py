import json

import pytest

from benchx import main


@pytest.fixture
def documents(tmp_path):
    def _documents(**named):
        paths = []
        for name, content in named.items():
            path = tmp_path / f"{name}.json"
            path.write_text(
                content if isinstance(content, str) else json.dumps(content)
            )
            paths.append(str(path))
        return paths

    return _documents


def test_valid_documents_say_nothing_on_stdout(documents, adhoc, arrow, capsys):
    files = documents(one=adhoc, two=arrow)
    code = main.main(["validate", *files])
    printed = capsys.readouterr()
    assert code == main.EXIT_OK
    assert printed.out == ""
    assert printed.err.strip() == "2/2 valid"


def test_each_invalid_document_is_reported_to_stderr(documents, adhoc, capsys):
    broken = json.loads(json.dumps(adhoc))
    broken["procedure"]["slot"] = -1
    files = documents(good=adhoc, bad=broken, unreadable="{")

    code = main.main(["validate", *files])
    errors = capsys.readouterr().err.splitlines()

    assert code == main.EXIT_INVALID
    assert "malformed at /procedure/slot" in errors[0]
    assert "Expecting property name" in errors[1]
    assert errors[-1] == "1/3 valid"


def test_every_error_in_a_document_is_reported(documents, adhoc, capsys):
    adhoc["procedure"]["slot"] = -1
    adhoc["procedure"]["round"] = -1
    [file] = documents(bad=adhoc)

    assert main.main(["validate", file]) == main.EXIT_INVALID
    errors = capsys.readouterr().err.splitlines()
    assert sorted(line.split(": ")[1] for line in errors[:-1]) == [
        "malformed at /procedure/round",
        "malformed at /procedure/slot",
    ]
    assert errors[-1] == "0/1 valid"


def test_kind_defaults_to_measurement_result_and_can_be_named(documents, adhoc, capsys):
    [file] = documents(one=adhoc)
    assert main.main(["validate", file]) == main.EXIT_OK
    assert main.main(["validate", "--kind", "measurement-result", file]) == main.EXIT_OK

    code = main.main(["validate", "--kind", "comparison-document", file])
    assert code == main.EXIT_INVALID
    assert "expected a comparison-document" in capsys.readouterr().err


def test_unknown_kind_is_rejected_by_the_parser(documents, adhoc):
    [file] = documents(one=adhoc)
    with pytest.raises(SystemExit):
        main.main(["validate", "--kind", "nonsense", file])
