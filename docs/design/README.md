# Design documents

Reading order for reviewers. The schema is the root; everything else is
designed around it (see the repository README for the philosophy).

| Document | What it defines | Status |
|---|---|---|
| [`benchmark-result-schema.md`](benchmark-result-schema.md) | What a result is: series identity, the open quantity vocabulary, the result and ingest contracts, migration from existing tools | draft |
| [`system-decomposition.md`](system-decomposition.md) | The ten components, their roles and boundaries, traceability to user stories | draft |
| [`runner.md`](runner.md) | Executing benchmark work on one node: work orders, pipeline, environment policy | draft |
| [`comparator.md`](comparator.md) | Pairwise verdicts: comparability guard, dispersion-scaled statistics, the comparison document | draft |
| [`profiling.md`](profiling.md) | Profiles as attached evidence: capture rules, artifact contract, pprof→OpenTelemetry migration path | draft |
| [`prototype-scope.md`](prototype-scope.md) | What the minimal prototype demonstrates and the decisions locked for it | agreed |
| [`prototype-design.md`](prototype-design.md) | How the prototype is built: one CLI, Parquet store, three JSON documents, Python | draft |

Not yet designed (roles fixed in the decomposition, documents pending):
harness adapters (beyond schema §6.2), workbench, scheduler internals,
change detector, alerting & annotations, views, series continuity/lineage,
importers (beyond schema §6).
