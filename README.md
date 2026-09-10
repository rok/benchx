# benchx

A design for a continuous benchmarking system — not one monolithic tool, but a
cluster of cooperating components (benchmark runners on compute nodes,
schedulers, ingestion adapters, result storage, views, comparison and alerting
services) that together let a project measure its performance on every change
and trust what it sees.

## Approach: schema first

Everything here flows out of one artifact: the **measurement-result schema**.
It defines a portable measurement fact and records the coordinates that
comparison and history services need, without embedding their policies or
verdicts. Every other component — runner, scheduler, dashboard, alerter,
migration tool — is designed *around* the schema, producing or consuming it,
rather than the schema being shaped by any single tool's needs.

For this to work, the schema must be rigorous about measurement semantics
(units, estimators, uncertainty), neutral toward harnesses and languages, and
rich enough that future use cases can sit on top of it without schema changes.
The initial draft is grounded in metrology terminology, existing benchmarking
systems, and stable JSON and columnar-storage standards.

## Grounded in user stories

To make sure the schema and the components serve real needs, we are collecting
user stories from projects that will eventually use the system — who benchmarks,
what they do today, where it hurts, what must not break. Apache Arrow's
continuous benchmarking setup is the first collected story; more will follow.
The stories drive which components exist and what each must do; the schema must
allow all of them.

## Contents

- [`docs/design/measurement-result-schema.md`](docs/design/measurement-result-schema.md)
  — the measurement-result contract, representation choices, mappings, and
  limitations.
- [`schemas/measurement-result/`](schemas/measurement-result/) — versioned
  message schemas and conformance examples.
- [`tools/measurement_arrow_schema.py`](tools/measurement_arrow_schema.py) —
  static Arrow schema and derived construction-storage schema.
- [`tools/measurement_arrow.py`](tools/measurement_arrow.py) — reference
  message-to-Parquet converter.
- [`docs/use-cases/`](docs/use-cases/) — workflows that exercise the design.
- [`docs/user_stories/`](docs/user_stories/) — user story template and collected
  stories.

## Status

Design phase, with a small reference JSON-to-Parquet implementation. The goal
at this stage is to validate the schema and component boundaries.

## License

Apache License 2.0.
