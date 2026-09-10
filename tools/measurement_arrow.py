#!/usr/bin/env python3
"""Validate a BenchX measurement, build an Arrow table, and write Parquet.

Install dependencies:
    pip install jsonschema pyarrow rfc8785

Usage:
    python tools/measurement_arrow.py \
        schemas/measurement-result/0.1.0/schema.json \
        schemas/measurement-result/0.1.0/examples/success.json \
        measurement.parquet
"""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import rfc8785
from jsonschema import FormatChecker
from jsonschema.validators import validator_for

from measurement_arrow_schema import (
    MEASUREMENT_ARROW_SCHEMA,
    MEASUREMENT_STORAGE_SCHEMA,
    MESSAGE_SCHEMA_URI,
    is_json_type,
)


def _project(data_type: pa.DataType, value: Any) -> Any:
    if value is None:
        return None
    if is_json_type(data_type):
        return rfc8785.dumps(value).decode("utf-8")
    if pa.types.is_timestamp(data_type):
        return datetime.fromisoformat(
            value.removesuffix("Z") + "+00:00"
        )
    if pa.types.is_struct(data_type):
        return {
            field.name: _project(field.type, value.get(field.name))
            for field in data_type
        }
    if pa.types.is_list(data_type):
        return [_project(data_type.value_type, item) for item in value]
    return value


def messages_to_arrow_table(
    messages: list[dict[str, Any]],
) -> pa.Table:
    """Convert previously validated messages to the static Arrow schema."""
    rows = [
        {
            field.name: _project(field.type, message.get(field.name))
            for field in MEASUREMENT_ARROW_SCHEMA
        }
        for message in messages
    ]
    table = pa.Table.from_pylist(rows, schema=MEASUREMENT_STORAGE_SCHEMA)
    return table.cast(MEASUREMENT_ARROW_SCHEMA)


def message_to_arrow_table(message: dict[str, Any]) -> pa.Table:
    """Convert one previously validated message to the static Arrow schema."""
    return messages_to_arrow_table([message])


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


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as source:
        return json.load(
            source,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_non_finite,
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("message_schema", type=Path)
    parser.add_argument("measurement", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    message_schema = _load_json(args.message_schema)
    measurement = _load_json(args.measurement)

    if message_schema.get("$id") != MESSAGE_SCHEMA_URI:
        raise ValueError("unsupported measurement schema URI")

    Validator = validator_for(message_schema)
    Validator.check_schema(message_schema)
    Validator(
        message_schema,
        format_checker=FormatChecker(),
    ).validate(measurement)

    # Enforce the JCS number domain before constructing the Arrow table.
    rfc8785.dumps(measurement)

    table = message_to_arrow_table(measurement)
    metadata = dict(table.schema.metadata or {})
    metadata[b"benchx.message_schema_sha256"] = hashlib.sha256(
        rfc8785.dumps(message_schema)
    ).hexdigest().encode("ascii")

    pq.write_table(
        table.replace_schema_metadata(metadata),
        args.output,
        compression="zstd",
        use_dictionary=True,
        store_schema=True,
    )


if __name__ == "__main__":
    main()
