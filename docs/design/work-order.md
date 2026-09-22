# Work order

**Status:** Draft, September 2026. Accompanies
[`schemas/work-order/0.1.0/schema.json`](../../schemas/work-order/0.1.0/schema.json);
where the two differ, the schema wins. Builds on `runner.md` (#24),
`prototype-design.md` (#27), `benchmark-result-schema.md` (#2), and
`harness-adapter.md` (#31).

## 1. Purpose

A work order is the runner's single input: what to run, against what, how,
and for whom. A runner executes one order per invocation, and every result it
emits references that order. Following `runner.md`, the order is a contract
artifact. It is versioned, so validators reject versions they don't know;
self-contained, so no flags or environment variables change what runs; and
replayable, so the same order against the same target plans the same
attempts. How orders are produced, queued, and scheduled is out of scope.

## 2. Rules

**W1. Order decisions, capture observations.** The order carries only what
its author decides. Anything the runner can observe is captured, never
ordered, because a wrong stated fact copied into a result looks exactly like
a measured one.

**W2. No identity.** An order never declares series membership or
fingerprints. Identity is computed from reported facts (result schema
rule 1).

**W3. Every field has a destination.** Each field either scopes execution or
is copied into a named result field.

**W4. Strict.** Every object rejects unknown properties, which catches typos
and enforces W1 and W2 mechanically. Adding a field requires a new
`workorder_version`.

**W5. Order only what the runner applies.** Otherwise results would claim
settings nobody applied. This is why version 1 has no environment policy.

## 3. Fields

| Field | Required | In each result |
| --- | --- | --- |
| `workorder_version` | yes | Not copied; the integer `1` |
| `project` | no | `project`; if omitted, results are thin (result schema section 4.1) |
| `source` | yes | `source` |
| `target.build_dir` | yes | Scopes execution; build configuration captured into `coordinates.subject.configuration` |
| `target.source_dir` | no | `revision.key`, `provenance.subject_dirty`, and `provenance.subject_tree` captured from it |
| `suite`, `filter` | `suite` only | Scope execution; matching cases become `coordinates.workload` |
| `quantities` | yes | `coordinates.quantity.name`, one result per case and quantity |
| `repetitions` | no | `comparison_context.protocol.repetitions`; realized counts in `procedure.attempted_repetitions` and `procedure.completed_repetitions` |
| `minimum_sample_seconds` | no | `comparison_context.protocol.calibration`; realized count in `procedure.inner_iterations` |
| `provenance.run_key` | yes | `provenance.run_key` |
| `provenance.labels` | no | `provenance.labels` |
| `provenance.requested_by`, `reason` | no | `provenance.info.requested_by`, `provenance.info.reason` |

**Target.** Version 1 supports only an existing build directory, the one kind
the prototype runner accepts. The runner refuses the order if the suite is
missing. If it can't locate the checkout, `subject_dirty` is `unknown` and
`subject_tree` is absent; the `revision.dirty` flag in
`prototype-design.md` is superseded by these. Paths should be absolute.

**Suite and filter.** Both have Google Benchmark semantics in version 1: a
binary name and a `--benchmark_filter` regex. The driving half should list
the matching cases before running (`--benchmark_list_tests`), so a truncated
run shows up as missing cases rather than a shorter suite.

**Quantities.** Any name the result schema accepts as a quantity name (a
`token`) is accepted; Appendix A is the shared vocabulary, not a rule. Units
come from the adapter mapping, not the order. Quantities from one invocation
share an `attempt_key`.

**Precision.** Requested values go in `comparison_context.protocol`; realized
values go in `procedure`. If a setting is omitted, the driving half records
the harness default. `comparison_context` is an open object in the result
schema, so the Appendix B spellings are a convention, not something
validation checks.

**Provenance.** `run_key` is required because only the order's author can
supply it; the result schema makes the run author responsible for it.
Result provenance is closed and has no fields for `requested_by` or
`reason`, so the runner records them under `provenance.info`, the result
schema's open descriptive metadata.

**Version.** `workorder_version` is named differently from a result's
`schema_version` so a loader can tell the two document kinds apart.

## 4. What an order never contains

Revision key, dirty state, tree id, build configuration, environment and
observed context, start time, attempt and ingest keys, units, and series
fingerprints. The runner, adapter, or ingest supplies each of these, and the
schema rejects them as unknown fields.

## 5. Linking results to orders

`prototype-design.md` puts a `workorder_ref` in every result's provenance,
but result schema version 5 has no such field, and its provenance rejects
unknown fields. Until the result schema adds one, the runner records the
reference as `provenance.info.workorder_ref`. Because this is how every
result is traced back to its plan, the proposal is to add `workorder_ref` to
result provenance in the next result schema version.

The value is proposed to be `sha256:<hex>` over the order's RFC 8785
canonical form, the same recipe as the result schema's fingerprints. The
reference survives reformatting and moves, and an edited order can't be
mistaken for the original.

## 6. File format and validation

The canonical form is strict JSON in a `.json` file. Tools may accept a
commented `.jsonc` file, selected by extension, but must validate and hash
the parsed value and never rewrite an order in place. The caution comes from
asv, whose `json5`-based config parsing also accepts `NaN` and `Infinity`
and loses comments on rewrite.

The schema uses draft 2020-12 and the result schema's `$id` scheme:
`urn:benchx:schema:work-order:0.1.0`. Its shared types (`token`,
`nonEmptyString`, `sourceRef`) are aliases in `$defs` that reference the
result schema's definitions, so every value the runner copies into a result
is valid there by construction, and the result schema's version is named in
one place. The cost is that the work order schema is not standalone:
validators must load the result schema too (in Python, register it in a
`referencing.Registry`; in ajv, `addSchema`). `format: uri` is checked only
when format checking is enabled. `examples/` holds a complete order
(`arrow.json`) and the smallest valid one (`adhoc.json`). Invalid fixtures
that each break one rule should be added.

## 7. Open questions

**Harness.** Nothing names the harness, so `suite` and `filter` only work for
Google Benchmark. Proposal: a required `harness` object, such as
`{"name": "google-benchmark"}`.

**Protocol.** Only repetitions and minimum sample time can be requested.
Proposal: a `protocol` object in Appendix B spellings, copied into
`comparison_context.protocol`, with both existing settings moved inside it.

**Rounds.** Interleaved comparisons need alternating orders. The result
schema already has `procedure.round`, zero-based, kept by a retry, and
paired across sides. Proposal: an optional `round` in the order, copied
into it. `procedure.slot`, the realized position across all sides, can't be
assigned by a runner that sees one order; it needs whoever coordinates the
sides.

**Target kinds.** A revision to build and a prebuilt artifact
(`runner.md`) need `workorder_version: 2`.

**Environment policy.** Add a `{name, version}` reference once a runner
enforces policies.

**Benchmark and subject.** Every result requires
`provenance.benchmark_dirty`, and a result without a top-level `benchmark`
(`{source, revision}`) is thin even when the order names a project. Results
also require `coordinates.subject.name`. The order determines none of these.
A runner can infer them when benchmarks live in the subject repository, as
Arrow's do; otherwise the order needs an optional benchmark source and
checkout, and possibly a subject name.

**Versioning.** The work order follows the result schema's convention:
`0.1.0` in the path and `$id`, and an integer constant in the document (`5`
for results, `1` here). The rule relating the two is still open and should
be settled for both schemas at once.
