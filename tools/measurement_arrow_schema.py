"""Static Arrow schemas for BenchX measurement results."""

import pyarrow as pa


MESSAGE_SCHEMA_URI = "urn:benchx:schema:measurement-result:0.1.0"
ARROW_SCHEMA_URI = "urn:benchx:schema:measurement-result-arrow:0.1.0"
PARQUET_MAPPING_URI = "urn:benchx:mapping:arrow-to-parquet:0.1.0"
JSON_METADATA = {b"benchx.canonicalization": b"RFC8785"}

UTF8 = pa.string()
BOOL = pa.bool_()
FLOAT64 = pa.float64()
TIMESTAMP = pa.timestamp("us", tz="UTC")
JSON = pa.json_()


def is_json_type(data_type: pa.DataType) -> bool:
    return getattr(data_type, "extension_name", None) == "arrow.json"


def _field(
    name: str,
    data_type: pa.DataType,
    *,
    nullable: bool = False,
) -> pa.Field:
    return pa.field(
        name,
        data_type,
        nullable=nullable,
        metadata=JSON_METADATA if is_json_type(data_type) else None,
    )


def _list(data_type: pa.DataType) -> pa.ListType:
    return pa.list_(_field("element", data_type))


DATASET = pa.struct(
    [
        _field("name", UTF8),
        _field("version", UTF8, nullable=True),
        _field("sha256", UTF8, nullable=True),
        _field("parameters", JSON, nullable=True),
    ]
)

WORKLOAD = pa.struct(
    [
        _field("name", UTF8),
        _field("version", UTF8, nullable=True),
        _field("parameters", JSON, nullable=True),
        _field("dataset", DATASET, nullable=True),
    ]
)

SOURCE_REVISION = pa.struct(
    [
        _field("uri", UTF8),
        _field("revision", UTF8),
        _field("dirty", BOOL, nullable=True),
    ]
)

SUBJECT = pa.struct(
    [
        _field("name", UTF8),
        _field("version", UTF8, nullable=True),
        _field("source", SOURCE_REVISION, nullable=True),
        _field("configuration", JSON, nullable=True),
    ]
)

ENVIRONMENT = pa.struct(
    [
        _field("identity_schema", UTF8),
        _field("identity", JSON),
        _field("label", UTF8, nullable=True),
    ]
)

PROTOCOL = pa.struct(
    [
        _field("name", UTF8),
        _field("version", UTF8),
        _field("settings", JSON, nullable=True),
    ]
)

COORDINATES = pa.struct(
    [
        _field("workload", WORKLOAD),
        _field("subject", SUBJECT),
        _field("environment", ENVIRONMENT),
        _field("protocol", PROTOCOL),
    ]
)

QUANTITY = pa.struct(
    [
        _field("name", UTF8),
        _field("unit", UTF8),
        _field("direction", UTF8, nullable=True),
        _field("deterministic", BOOL, nullable=True),
    ]
)

ESTIMATOR = pa.struct(
    [
        _field("name", UTF8),
        _field("parameters", JSON, nullable=True),
    ]
)

OUTCOME = pa.struct(
    [
        _field("status", UTF8),
        _field("reason", UTF8, nullable=True),
        _field("message", UTF8, nullable=True),
    ]
)

SUMMARY = pa.struct(
    [
        _field("kind", UTF8),
        _field("name", UTF8, nullable=True),
        _field("value", FLOAT64, nullable=True),
        _field("lower", FLOAT64, nullable=True),
        _field("upper", FLOAT64, nullable=True),
        _field("level", FLOAT64, nullable=True),
        _field("factor", FLOAT64, nullable=True),
        _field("source", UTF8, nullable=True),
        _field("method", UTF8, nullable=True),
        _field("extensions", JSON, nullable=True),
    ]
)

CONSTRAINT = pa.struct(
    [
        _field("kind", UTF8),
        _field("lower", FLOAT64, nullable=True),
        _field("upper", FLOAT64, nullable=True),
        _field("lower_inclusive", BOOL, nullable=True),
        _field("upper_inclusive", BOOL, nullable=True),
        _field("cause", UTF8),
    ]
)

EVIDENCE = pa.struct(
    [
        _field("estimate", FLOAT64, nullable=True),
        _field("estimate_source", UTF8, nullable=True),
        _field("observations", _list(JSON), nullable=True),
        _field("summaries", _list(SUMMARY), nullable=True),
        _field("constraint", CONSTRAINT, nullable=True),
        _field("extensions", JSON, nullable=True),
    ]
)

ARTIFACT = pa.struct(
    [
        _field("uri", UTF8),
        _field("media_type", UTF8),
        _field("schema_uri", UTF8, nullable=True),
        _field("sha256", UTF8, nullable=True),
        _field("role", UTF8, nullable=True),
        _field("metadata", JSON, nullable=True),
    ]
)

PROVENANCE = pa.struct(
    [
        _field("recorded_at", TIMESTAMP),
        _field("started_at", TIMESTAMP, nullable=True),
        _field("ended_at", TIMESTAMP, nullable=True),
        _field("run_key", UTF8, nullable=True),
        _field("batch_key", UTF8, nullable=True),
        _field("native_id", UTF8, nullable=True),
        _field("source_payload_uri", UTF8, nullable=True),
        _field("source_payload_sha256", UTF8, nullable=True),
        _field("info", JSON, nullable=True),
    ]
)

MEASUREMENT_ARROW_SCHEMA = pa.schema(
    [
        _field("schema_uri", UTF8),
        _field("measurement_id", UTF8),
        _field(
            "producer",
            pa.struct(
                [
                    _field("name", UTF8),
                    _field("version", UTF8),
                    _field("mapping_version", UTF8),
                ]
            ),
        ),
        _field("ingest_key", UTF8),
        _field("project", UTF8),
        _field("coordinates", COORDINATES),
        _field("quantity", QUANTITY),
        _field("estimator", ESTIMATOR),
        _field("outcome", OUTCOME),
        _field("evidence", EVIDENCE, nullable=True),
        _field("observed_context", JSON, nullable=True),
        _field("procedure", JSON, nullable=True),
        _field("artifacts", _list(ARTIFACT), nullable=True),
        _field("provenance", PROVENANCE),
        _field("extensions", JSON, nullable=True),
    ],
    metadata={
        b"benchx.schema_uri": MESSAGE_SCHEMA_URI.encode("utf-8"),
        b"benchx.arrow_schema_uri": ARROW_SCHEMA_URI.encode("utf-8"),
        b"benchx.parquet_mapping": PARQUET_MAPPING_URI.encode("utf-8"),
    },
)


def _storage_type(data_type: pa.DataType) -> pa.DataType:
    if is_json_type(data_type):
        return data_type.storage_type
    if pa.types.is_struct(data_type):
        return pa.struct([_storage_field(field) for field in data_type])
    if pa.types.is_list(data_type):
        return pa.list_(_storage_field(data_type.value_field))
    return data_type


def _storage_field(field: pa.Field) -> pa.Field:
    return pa.field(
        field.name,
        _storage_type(field.type),
        nullable=field.nullable,
    )


MEASUREMENT_STORAGE_SCHEMA = pa.schema(
    [_storage_field(field) for field in MEASUREMENT_ARROW_SCHEMA]
)
