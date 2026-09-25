"""Comparator invariants and method, on hand-built results whose values the test controls.

Each test changes one thing from a clean three-round `revisions` run and
checks that the comparator notices (prototype-ablation.md §6).
"""

import copy

import pytest

from benchx import compare

BASE, HEAD = "a" * 40, "b" * 40


def result(side, round_, slot, value, workload="BM_W", **changes):
    doc = {
        "producer": {"name": "benchx/gbench-adapter"},
        "ingest_key": f"run:{workload}:wall-time:slot-{slot}",
        "source": {"uri": "https://example.org/demo"},
        "revision": {"key": side},
        "coordinates": {
            "workload": {"name": workload},
            "subject": {"name": "demo", "components": [{"role": "primary"}], "configuration": {"build_type": "Release"}},
            "quantity": {"name": "wall-time", "unit": "s", "direction": "lower-is-better"},
            "comparison_context": {"harness": {"name": "google-benchmark"}},
            "environment": {"schema": "machine/v1", "identity": {"runner": "host"}},
        },
        "measurement": {"status": "success", "observations": [value]},
        "observed_context": {"kernel": "6.8"},
        "procedure": {"round": round_, "slot": slot},
        "provenance": {"run_key": "run", "subject_dirty": "clean", "benchmark_dirty": "clean", "subject_tree": side},
    }
    for path, value_ in changes.items():
        target = doc
        *parents, leaf = path.split("__")
        for part in parents:
            target = target[part]
        target[leaf] = value_
    return doc


def run(rounds=3, base_values=(1.0, 2.0, 3.0), ratio=1.1):
    """Alternating base/head attempts; the head is `ratio` times the base in each round."""
    docs, slot = [], 0
    for r in range(rounds):
        for side, value in ((BASE, base_values[r]), (HEAD, base_values[r] * ratio)):
            docs.append(result(side, r, slot, value))
            slot += 1
    return docs


def evaluate(docs, **kwargs):
    return compare.compare(docs, run_key="run", profile="revisions", baseline=BASE, **kwargs)


def invariants(doc):
    return [f["invariant"] for f in doc["failed_invariants"]]


def test_clean_run():
    doc = evaluate(run())
    assert invariants(doc) == [] and doc["units"][0]["verdict"] == "regressed"


def test_pairs_by_round_not_by_arrival():
    """C13: the head's rounds arrive in reverse; pairing by round still sees +10% exactly."""
    docs = run()
    heads = [d for d in docs if d["revision"]["key"] == HEAD]
    for d, r in zip(heads, (2, 1, 0)):
        d["procedure"]["round"] = r
        d["measurement"]["observations"] = [(r + 1) * 1.1]
    unit = evaluate(docs)["units"][0]
    assert unit["effect"] == pytest.approx(0.1) and unit["noise"] == pytest.approx(0, abs=1e-12)


def test_equal_attempts():
    """C4: a unit with fewer attempts on one side gets no verdict."""
    docs = run()
    docs.append(result(BASE, 3, 6, 4.0, workload="BM_W"))
    docs.append(result(HEAD, 3, 7, 4.4, workload="BM_Other"))
    doc = evaluate(docs)
    assert invariants(doc) == ["equal-attempts"]
    assert [u["workload"] for u in doc["units"]] == []  # BM_W failed; BM_Other is missing on base
    assert doc["missing"] == [{"workload": "BM_Other", "parameters": "{}", "quantity": "wall-time", "side": BASE}]


def test_two_sides():
    """C5: a third tree in the run."""
    docs = run()
    docs.append(result("c" * 40, 3, 6, 1.0))
    assert invariants(evaluate(docs)) == ["two-sides"]


def test_sides_agree():
    """C1: the revisions sides must share subject configuration."""
    docs = run()
    for d in docs[1::2]:
        d["coordinates"]["subject"]["configuration"] = {"build_type": "Debug"}
    assert invariants(evaluate(docs)) == ["sides-agree"]


def test_exclusions():
    """C6: a failed attempt is listed and its round drops out of the pairing."""
    docs = run(rounds=4, base_values=(1.0, 2.0, 3.0, 4.0))
    docs[2]["measurement"] = {"status": "error", "reason": "harness.error"}
    doc = evaluate(docs)
    assert doc["exclusions"] == [{"ingest_key": docs[2]["ingest_key"], "status": "error", "reason": "harness.error"}]
    assert doc["units"][0]["rounds"] == 3


def test_min_rounds():
    """C9: two rounds are not enough by default."""
    unit = evaluate(run(rounds=2))["units"][0]
    assert (unit["verdict"], unit["reason"]) == ("indeterminate", "insufficient-rounds")
    assert evaluate(run(rounds=2), min_rounds=2)["units"][0]["verdict"] == "regressed"


def test_observed_context_differences():
    """C10: a condition that differs between the sides is carried as a caveat."""
    docs = run()
    for d in docs[1::2]:
        d["observed_context"] = {"kernel": "6.9", "load_avg_1m": 3.2}
    assert evaluate(docs)["units"][0]["observed_context_differences"] == ["kernel"]


def test_deterministic_quantities_are_deferred():
    docs = run()
    for d in docs:
        d["coordinates"]["quantity"]["deterministic"] = True
    unit = evaluate(docs)["units"][0]
    assert (unit["verdict"], unit["reason"]) == ("indeterminate", "deterministic-deferred")


def test_environments_needs_its_label():
    docs = copy.deepcopy(run())
    with pytest.raises(compare.CompareError, match="label"):
        compare.compare(docs, run_key="run", profile="environments", baseline="plain")
