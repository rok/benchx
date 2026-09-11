# Measurement-result schema

- **Status:** draft 0.1.0
- **Message schema URI:** `urn:benchx:schema:measurement-result:0.1.0`
- **Arrow schema URI:** `urn:benchx:schema:measurement-result-arrow:0.1.0`

## Scope

A measurement result records **one attempt to estimate one quantity** for one
workload and subject under declared conditions. If one benchmark invocation
reports wall time and peak memory, it produces two measurement results. A retry
produces another result.

The record contains measured facts and provenance. Comparisons, regressions,
alerts, correctness verdicts, and derived series identifiers are separate
concerns. An explicit harness skip is a result; work that was planned but never
attempted belongs in a run manifest rather than this table.

## Current artifacts

| Artifact | Purpose |
|---|---|
| [`schema.json`](../../schemas/measurement-result/0.1.0/schema.json) | JSON Schema 2020-12 validation for a measurement message. |
| [`measurement_arrow.py`](../../tools/measurement_arrow.py) | Static PyArrow schema, validated-message conversion, and Parquet writing. |
| [`measurement_message_to_parquet.py`](../../tools/measurement_message_to_parquet.py) | Strict JSON validation and conversion CLI. |
| [`success.json`](../../schemas/measurement-result/0.1.0/examples/success.json) | Example valid message. |

The JSON Schema and Arrow schema are authored independently. The implementation
does not infer Arrow field order or types from a message, an example, or JSON
Schema keywords.

## Message model

The top-level object is closed: unknown core properties are rejected. It has
the following fields in 0.1.0:

| Field | Required | Meaning |
|---|---:|---|
| `schema_uri` | yes | Exact message contract version. |
| `measurement_id` | yes | Lowercase UUID identifying this measurement fact. |
| `producer` | yes | Producer name, version, and native-to-BenchX mapping version. |
| `ingest_key` | yes | Producer-scoped key used to make ingestion idempotent. |
| `project` | yes | Namespace for project-defined names and conventions. |
| `coordinates` | yes | Workload, subject, environment, and protocol. |
| `quantity` | yes | Measured quantity, unit, and optional descriptive properties. |
| `estimator` | yes | Estimator name and optional parameters. |
| `outcome` | yes | Status plus optional reason and diagnostic message. |
| `evidence` | conditional | Estimate, observations, summaries, or censoring constraint. |
| `observed_context` | no | Open JSON object containing observed conditions. |
| `procedure` | no | Open JSON object containing acquisition details. |
| `artifacts` | no | References to external evidence such as samples, logs, or profiles. |
| `provenance` | yes | Timestamps, run keys, and native-payload references. |
| `extensions` | no | Namespaced extension values. |

### Coordinates

`coordinates` contains four required closed objects:

- `workload` identifies the benchmark case and optionally its version,
  parameters, and dataset;
- `subject` identifies the implementation or system under test and optionally
  its version, source revision, and configuration;
- `environment` contains a versioned identity object and optional label;
- `protocol` identifies the measurement protocol version and optional settings.

These are recorded facts, not a universal comparison key. Project policy
selects which coordinates must match when comparing measurements.

### Quantity and estimator

`quantity.name` and `estimator.name` are project-defined non-empty strings.
Different meanings require different quantity names. For example, peak resident
memory and bytes allocated are not one generic memory quantity.

All numeric evidence is expressed in `quantity.unit`. The intended convention
is case-sensitive UCUM notation where possible, such as `s`, `By`, `J`, `W`,
`1`, `By/s`, or `1/s`. The current JSON Schema requires a non-empty string but
does not validate UCUM syntax.

`quantity.direction`, when present, is `lower-is-better` or
`higher-is-better`. It describes the quantity; it is not a comparison verdict.
A percentile such as p99 belongs in the estimator rather than the quantity
name.

### Outcomes and evidence

The JSON Schema enforces these combinations:

| Status | Requirements |
|---|---|
| `success` | `evidence.estimate` and `evidence.estimate_source` are required; `constraint` is forbidden. |
| `partial` | Same evidence rules as `success`; `outcome.reason` is required. |
| `censored` | `outcome.reason` and `evidence.constraint` are required; `estimate` and `estimate_source` are forbidden. |
| `error` | `outcome.reason` is required; `evidence` is forbidden. |
| `skipped` | `outcome.reason` is required; `evidence` is forbidden. |

Reasons are lowercase tokens matching the schema pattern, for example
`timeout`, `resource-exhausted.memory`, or `unsupported`. `outcome.message` is
human-readable diagnostic text and is not intended for classification.

Evidence may contain:

- a point `estimate` and its `estimate_source`;
- one or more raw `observations`, represented as numbers or structured JSON
  observations;
- typed `summaries`, including statistics, intervals, source bounds, and
  uncertainty statements;
- a lower bound, upper bound, or interval `constraint` for censored outcomes;
- namespaced extension values.

The schema enforces required fields and rejects numeric fields that do not
apply to a summary or constraint kind. It does not currently enforce ordering
between lower and upper bounds.

### Open JSON values and extensions

Most core structures are closed with `additionalProperties: false`. Deliberately
open values are limited to fields such as parameters, configuration, identity,
settings, context, procedure, metadata, and extensions.

Extension property names must contain a namespace-like `:` or `/` separator.
This allows experimentation without silently accepting misspelled core fields.

## JSON representation

The reference implementation accepts JSON. Parsing rejects duplicate object
keys and the non-JSON numeric tokens `NaN`, `Infinity`, and `-Infinity` before
JSON Schema validation.

Messages use the I-JSON-compatible JSON data model:

- UTF-8 text and unique object member names;
- valid JSON strings and values;
- finite numbers representable in the RFC 8785 number domain;
- UTC RFC 3339 timestamps ending in `Z`, with no more than six fractional
  digits.

The CLI runs RFC 8785 serialization over the validated message to check the
supported number domain. It separately applies RFC 8785 to `schema.json` before
computing the message-schema SHA-256 checksum. Object member order in an input
message has no semantic meaning.

YAML is not accepted by the current reference tool. A future YAML reader must
convert YAML into the same JSON data model before validation; YAML-specific
values, duplicate keys, aliases, custom tags, and non-string mapping keys must
not alter the contract.

## Static Arrow schema

`MEASUREMENT_ARROW_SCHEMA` is a statically declared `pyarrow.Schema`. Its field
order, nesting, types, nullability, and metadata are the table contract. The
schema uses:

- `string`, `bool`, and `float64` scalar fields;
- `timestamp("us", tz="UTC")` for provenance timestamps;
- ordered `struct` and `list` fields;
- Arrow's canonical `json_()` extension for open or heterogeneous JSON values.

The order of the top-level Arrow fields is:

```text
schema_uri, measurement_id, producer, ingest_key, project, coordinates,
quantity, estimator, outcome, evidence, observed_context, procedure,
artifacts, provenance, extensions
```

Open JSON values are serialized with RFC 8785 and stored as `json_()` over
UTF-8. This preserves their complete JSON value without inferring unstable
struct fields. The same representation is used for heterogeneous observations.

### Construction schema

PyArrow cannot construct the nested `json_()` extension fields in this schema
directly with `Table.from_pylist`. At import time,
`measurement_arrow.py` derives a private construction schema by recursively
replacing each `json_()` type with its UTF-8 storage type. The converter:

1. projects values by walking `MEASUREMENT_ARROW_SCHEMA`;
2. parses timestamp strings into timezone-aware `datetime` values;
3. serializes `json_()` values with RFC 8785;
4. constructs a table with the private construction schema;
5. casts the complete table to `MEASUREMENT_ARROW_SCHEMA`.

The construction schema is an implementation detail. It does not define a
second storage contract and is not inferred from message values.

`measurement_arrow.py` exposes:

```python
validated_message_to_arrow_table(message)
validated_messages_to_arrow_table(messages)
write_validated_measurement_parquet(
    message,
    output,
    message_schema_sha256=hash,
)
```

These functions expect already validated Python mappings. The
`measurement_message_to_parquet.py` command-line entry point performs strict
JSON parsing and JSON Schema validation before calling the Parquet writer.

## Parquet output

The command-line writer stores the Arrow schema in Parquet and writes these
BenchX metadata entries:

```text
benchx.schema_uri = urn:benchx:schema:measurement-result:0.1.0
benchx.arrow_schema_uri = urn:benchx:schema:measurement-result-arrow:0.1.0
benchx.parquet_mapping = urn:benchx:mapping:arrow-to-parquet:0.1.0
benchx.message_schema_sha256 = <SHA-256 of RFC 8785 schema.json bytes>
```

Arrow `json_()` fields are written with the Parquet JSON logical type. Parquet
field IDs are not assigned in 0.1.0; fields are identified by nested name and
schema URI.

Compression, dictionary encoding, row groups, statistics, and partitioning are
physical writer choices. Decoded values and logical schemas are expected to be
stable, but byte-identical Parquet output is not guaranteed across writers or
versions.

## Validation boundaries

The current CLI provides:

- strict JSON parsing for duplicate keys and non-finite tokens;
- JSON Schema 2020-12 validation with format checking enabled;
- an RFC 8785 serialization check;
- projection to the static Arrow schema;
- Parquet writing with schema metadata.

The following checks are not implemented yet:

- UCUM unit validation;
- lower/upper bound ordering;
- `started_at <= ended_at`;
- safe-integer policy and other explicit I-JSON semantic checks beyond what the
  parser and RFC 8785 library reject;
- uniqueness and immutability of `(producer.name, ingest_key)` payloads;
- project-level immutability of quantity/unit associations;
- automated drift detection between JSON Schema and the static Arrow schema;
- Arrow or Parquet reconstruction back into a validated measurement message.

## Versioning and limitations

Version 0.1.0 is a draft. The message and Arrow schema URIs identify their exact
versions and should be stored with every result. Incompatible changes to field
meaning, required fields, physical types, field order, canonicalization, or
identity rules require new schema URIs. Historical messages should retain their
original bytes and schema URI rather than being rewritten in place.

Current limitations include:

- the Arrow schema is authored in PyArrow rather than a language-neutral Arrow
  schema notation;
- recent Arrow and Parquet implementations are required for canonical JSON
  extension and logical-type support;
- binary64 evidence cannot represent arbitrary-precision decimal values or all
  integer counters exactly;
- JSON-backed open fields are not directly predicate-addressable as nested
  Parquet columns;
- comparison policy and run completeness require records outside this schema.

## Standards used

- [JSON Schema 2020-12](https://json-schema.org/draft/2020-12/json-schema-core)
  for message validation;
- [I-JSON, RFC 7493](https://www.rfc-editor.org/rfc/rfc7493) for the intended
  interoperable JSON subset;
- [RFC 8785 JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785)
  for canonical open values and schema checksum bytes;
- [UCUM](https://ucum.org/ucum) as the intended unit notation;
- RFC 3339 UTC timestamps with microsecond precision;
- [Arrow canonical JSON extension](https://arrow.apache.org/docs/format/CanonicalExtensions.html#json)
  for open JSON values;
- [Parquet JSON logical type](https://github.com/apache/parquet-format/blob/master/LogicalTypes.md#json)
  for persisted JSON columns.
