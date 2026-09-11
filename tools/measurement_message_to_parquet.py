#!/usr/bin/env python3
"""Validate a BenchX measurement message and write it to Parquet.

Install dependencies:
    pip install jsonschema pyarrow rfc8785

Usage:
    python tools/measurement_message_to_parquet.py \
        schemas/measurement-result/0.1.0/schema.json \
        schemas/measurement-result/0.1.0/examples/success.json \
        measurement.parquet
"""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import rfc8785
from jsonschema import FormatChecker
from jsonschema.validators import validator_for

from measurement_arrow import (
    MESSAGE_SCHEMA_URI,
    write_validated_measurement_parquet,
)


def reject_duplicate_keys(pairs):
    # jsonschema only sees the parsed mapping, after duplicate keys are lost.
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def reject_non_finite(value):
    # Python's JSON parser accepts these even though JSON does not.
    raise ValueError(f"invalid JSON number: {value}")


def load_json(path: Path) -> Any:
    """Load strict JSON, rejecting duplicate keys and non-finite tokens."""
    with path.open(encoding="utf-8") as source:
        return json.load(
            source,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_non_finite,
        )


def validate_measurement_message(
    measurement: dict[str, Any],
    message_schema: dict[str, Any],
) -> None:
    """Validate one parsed measurement message."""
    if message_schema.get("$id") != MESSAGE_SCHEMA_URI:
        raise ValueError("unsupported measurement schema URI")

    validator_class = validator_for(message_schema)
    validator_class.check_schema(message_schema)
    validator_class(
        message_schema,
        format_checker=FormatChecker(),
    ).validate(measurement)

    # Enforce the JCS number domain before constructing the Arrow table.
    rfc8785.dumps(measurement)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("message_schema", type=Path)
    parser.add_argument("measurement", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    message_schema = load_json(args.message_schema)
    measurement = load_json(args.measurement)
    validate_measurement_message(measurement, message_schema)
    write_validated_measurement_parquet(
        measurement,
        args.output,
        message_schema_sha256=canonical_sha256(message_schema),
    )


if __name__ == "__main__":
    main()
