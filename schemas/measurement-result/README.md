# Measurement-result contract

The measurement-result contract records one attempt to estimate one quantity.
Version `0.1.0` is the current draft.

## Files

| Path | Role |
|---|---|
| [`0.1.0/schema.json`](0.1.0/schema.json) | JSON Schema 2020-12 message definition. |
| [`0.1.0/examples/success.json`](0.1.0/examples/success.json) | Complete successful-result example. |
| [`../../tools/measurement_arrow.py`](../../tools/measurement_arrow.py) | Static PyArrow schema, validated-message conversion, and Parquet writing. |
| [`../../tools/measurement_message_to_parquet.py`](../../tools/measurement_message_to_parquet.py) | Strict JSON validation and conversion CLI. |
| [`../../docs/design/measurement-result-schema.md`](../../docs/design/measurement-result-schema.md) | Data-model rationale, mapping rules, and current limitations. |

A message identifies this version with:

```text
urn:benchx:schema:measurement-result:0.1.0
```

The corresponding Arrow schema identifies itself with:

```text
urn:benchx:schema:measurement-result-arrow:0.1.0
```

## Contract layers

The JSON Schema validates message structure, property names, primitive types,
formats, enumerations, and outcome-dependent evidence. The static PyArrow
schema separately fixes table field order, nesting, physical types,
nullability, and canonical JSON columns. Neither schema is generated from the
other.

Additional requirements, including RFC 8785 canonicalization and checks that
cannot be expressed in JSON Schema, are documented in the design document.

## Reference conversion

Install the current dependencies:

```bash
python -m pip install jsonschema pyarrow rfc8785
```

Validate the example and write Parquet:

```bash
python tools/measurement_message_to_parquet.py \
  schemas/measurement-result/0.1.0/schema.json \
  schemas/measurement-result/0.1.0/examples/success.json \
  measurement.parquet
```

The command rejects duplicate JSON keys and non-finite JSON tokens, validates
with JSON Schema format checking enabled, canonicalizes open JSON values, and
writes the static Arrow schema into the Parquet file.

With `tools/` on `PYTHONPATH`, the Python conversion functions accept already
validated mappings:

```python
from measurement_arrow import (
    validated_message_to_arrow_table,
    validated_messages_to_arrow_table,
)
```

The validated-message prefix makes the API boundary explicit. Callers using
these functions directly are responsible for strict parsing and message
validation.

## Versioning

Version directories and schema URIs are immutable identifiers. Incompatible
changes require a new directory and new message and Arrow schema URIs. There is
no mutable `latest` schema alias.
