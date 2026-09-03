# benchx

A design for a continuous benchmarking system — not one monolithic tool, but a
cluster of cooperating components (benchmark runners on compute nodes,
schedulers, ingestion adapters, result storage, views, comparison and alerting
services) that together let a project measure its performance on every change
and trust what it sees.

## Approach: schema first

Everything here flows out of one artifact: the **benchmark result schema**. It
defines what a measurement result is, what makes two results comparable, and
how histories of results are identified and preserved. Every other component —
runner, scheduler, dashboard, alerter, migration tool — is designed *around*
the schema, producing or consuming it, rather than the schema being shaped by
any single tool's needs.

For this to work, the schema must be designed correctly up front: rigorous
about measurement semantics (units, estimators, uncertainty), neutral toward
harnesses and languages, and rich enough that future use cases can sit on top
of it without schema changes. The current draft is grounded in a review of
metrology standards (VIM/GUM) and of existing benchmarking systems and
harnesses, with a migration contract so that history from today's tools is not
lost.

## Grounded in user stories

To make sure the schema and the components serve real needs, we are collecting
user stories from projects that will eventually use the system — who benchmarks,
what they do today, where it hurts, what must not break. Apache Arrow's
continuous benchmarking setup is the first collected story; more will follow.
The stories drive which components exist and what each must do; the schema must
allow all of them.

## Contents

- `docs/design/benchmark-result-schema.md` — the benchmark result schema and
  migration contract (the core design document).
- `docs/user_stories/` — user story template and collected stories.

## Status

Design phase. No implementation yet; the goal at this stage is to get the
schema and the component boundaries right.

## License

Apache License 2.0.
