"""Fingerprints, the prototype identity policy, and series points (schema §4.3, §4.5)."""

import statistics
import urllib.parse

from .core import canonical, sha256_hex

IDENTITY_SCHEMA = "benchx/prototype-identity/v1"
MEDIAN = {"name": "median", "method_version": "benchx/median/v1", "input_level": "observations"}


def _hash(prefix: str, *parts: bytes) -> str:
    return sha256_hex(prefix.encode() + b"\0" + b"\0".join(parts))


def reported_coordinates(doc: dict) -> dict:
    """Everything reported about what was measured, minus the axis revision (§4.3)."""
    reported = {"source": doc["source"], "coordinates": doc["coordinates"]}
    for key in ("project", "benchmark"):
        if key in doc:
            reported[key] = doc[key]
    return reported


def reported_coordinates_fingerprint(doc: dict) -> str:
    return _hash("benchmark-reported-coordinates-v1", canonical(reported_coordinates(doc)))


def _normalize_uri(uri: str) -> str:
    parts = urllib.parse.urlsplit(uri)
    path = parts.path.rstrip("/").removesuffix(".git")
    return urllib.parse.urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def comparison_identity(doc: dict, project: str) -> dict:
    """benchx/prototype-identity/v1: the reported coordinates, source URIs
    normalized, the implicit project for a thin result, and the exact
    benchmark revision omitted, since the prototype has no declared benchmark
    versions and benchmarks in the subject's checkout would otherwise split
    history on every commit (schema §1)."""
    identity = {"project": project, "source": _normalize_uri(doc["source"]["uri"]),
                "coordinates": doc["coordinates"]}
    if "benchmark" in doc:
        identity["benchmark"] = _normalize_uri(doc["benchmark"]["source"]["uri"])
    return identity


def series_fingerprint(doc: dict, project: str, estimator: dict) -> str:
    comparison = _hash("benchmark-comparison-v1", IDENTITY_SCHEMA.encode(),
                       canonical(comparison_identity(doc, project)))
    return _hash("benchmark-series-v6", comparison.encode(),
                 _hash("benchmark-estimator-v1", canonical(estimator)).encode())


def _values(doc: dict) -> list[float]:
    return [o["value"] if isinstance(o, dict) else o for o in doc["measurement"].get("observations", [])]


def points(doc: dict, project: str) -> list[dict]:
    """The series points a result contributes (§4.5): the derived median when it
    has observations, and each producer estimate it carries."""
    if doc["measurement"]["status"] not in ("success", "partial"):
        return []
    found = []
    if values := _values(doc):
        found.append((MEDIAN, statistics.median(values), "server"))
    for summary in doc["measurement"].get("summaries", []):
        if summary["type"] == "estimate":
            found.append((summary["estimator"], summary["value"], "producer"))
    return [{"series_fingerprint": series_fingerprint(doc, project, estimator),
             "estimator": estimator, "value": value, "source": source} for estimator, value, source in found]
