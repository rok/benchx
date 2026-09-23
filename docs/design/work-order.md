# Work order

**Status:** Draft, September 2026. Accompanies
[`schemas/work-order/0.1.0/schema.json`](../../schemas/work-order/0.1.0/schema.json);
where the two differ, the schema wins. Version 1 is an unmerged draft, so
it changes in place rather than by version bump. Builds on `runner.md` (#24),
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

**W4. Strict, except the protocol.** Every object rejects unknown properties,
which catches typos and enforces W1 and W2 mechanically. `protocol` is the
one exception: harness-specific keys pass through, and the runner, not the
schema, rejects a key it cannot apply (W5).

**W4a. Every applied setting is recorded.** Whatever the runner applies goes
into the result it produces, whether the order asked for it or the runner
defaulted it. An order is therefore never the only place a run parameter
exists.

**W5. Order only what the runner applies.** Otherwise results would claim
settings nobody applied. This is why version 1 has no environment policy.

## 3. Fields

| Field | Required | In each result |
| --- | --- | --- |
| `workorder_version` | yes | Not copied; the integer `1` |
| `project` | no | `project`; if omitted, results are thin (result schema section 4.1) |
| `source` | yes | `source` |
| `harness` | yes | `comparison_context.harness` |
| `target.kind` | yes | Selects the target shape: `build_dir` or `python_env` |
| `target.build_dir` | `build_dir` kind | Scopes execution; build configuration captured into `coordinates.subject.configuration` |
| `target.python` | `python_env` kind | Scopes execution; interpreter version, implementation, and build flags captured |
| `target.source_dir` | no | `revision.key`, `provenance.subject_dirty`, and `provenance.subject_tree` captured from it |
| `suite`, `filter` | `suite` only | Scope execution; matching cases become `coordinates.workload` |
| `quantities` | yes | `coordinates.quantity.name`, one result per case and quantity |
| `protocol` | no | `comparison_context.protocol`, verbatim; realized counterparts in `procedure` |
| `provenance.run_key` | yes | `provenance.run_key` |
| `provenance.labels` | no | `provenance.labels` |
| `provenance.requested_by`, `reason` | no | `provenance.info.requested_by`, `provenance.info.reason` |

**Harness.** `harness` names the harness that runs the suite, such as
`google-benchmark` or `pyperf`. It selects the adapter and fixes how
`suite`, `filter`, and the protocol keys are read, so nothing else in the
order can be interpreted without it. `version`, if given, is what the order
requires; the runner records the version it actually ran.

**Target.** Two kinds, tagged by `kind`. A `build_dir` target names an
existing build directory holding a compiled suite. A `python_env` target
names the interpreter that runs it, with the subject and the harness
installed. A revision to build and a prebuilt artifact (`runner.md`) are
future kinds. The runner refuses the order if the suite is missing. If it
can't locate the checkout, `subject_dirty` is `unknown` and `subject_tree`
is absent; the `revision.dirty` flag in `prototype-design.md` is superseded
by these. Paths should be absolute.

**Suite and filter.** Both are read in the named harness's terms: for Google
Benchmark a binary name and a `--benchmark_filter` regex; for pyperf a
script path, with no filter support at all. The driving half should fix the
planned set of cases before running, so a truncated run shows up as missing
cases rather than a shorter suite. Harnesses that cannot list their cases
make that impossible, which is an open question below.

**Quantities.** Any name the result schema accepts as a quantity name (a
`token`) is accepted; Appendix A is the shared vocabulary, not a rule. Units
come from the adapter mapping, not the order. Quantities from one invocation
share an `attempt_key`.

**Protocol.** `protocol` holds the intended acquisition settings in the
result schema's Appendix B spellings, and the runner copies it verbatim into
`comparison_context.protocol`; realized counterparts go in `procedure`. Three
keys are constrained here:

- `repetitions` is a list of levels, outermost first, because harnesses
  repeat at different levels: Google Benchmark repeats inside one process
  (one level), while pyperf spawns processes that each produce several
  values (two levels).
- `calibration` is either `adaptive` with a `minimum_sample_seconds`, or
  `fixed` with an iteration count.
- `warmup` is a count, a duration, or none.

Anything else passes through for the adapter to interpret (W4). Omitting
`protocol` means harness defaults apply, and the runner must record what it
actually used (W4a); it is never a licence to leave settings unrecorded.
`comparison_context` is an open object in the result schema, so these
spellings are a convention that ingest does not check.

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

**Harness name: open value or closed enum?** `harness.name` is an open
token today, so a new adapter ships without touching the schema and the
runner rejects a name it has no adapter for. A closed enum would catch typos
at validation time instead, at the cost of a schema change per harness.

**Target design.** Three parts are unsettled. Should `suite` stay at the top
level with a harness-specific meaning (a binary name, a script path), or
move into the target, which would let each kind name its own? For
`python_env`, is the right handle the interpreter path (as now, matching
pyperf's own `--python`), a virtual environment directory, or a project
directory the runner syncs itself? And should the two future kinds, a
revision to build and a prebuilt artifact, be designed now so the tag
vocabulary is settled, or added when a runner can use them?

**Protocol vocabulary.** The level list is new spelling, so where does it
belong? Appendix B of the result schema is the shared vocabulary, so it
should probably define `repetitions.levels` and the level units, which makes
this a result schema doc change even though `comparison_context` is open and
validates it today either way. The alternative spelling is a flat
`{"n_repeat": 3, "n_process": 20}`, shorter for the two cases we have and
harder to extend. Either way `procedure` needs a matching realized form:
it currently has one `attempted_repetitions` and one
`completed_repetitions`, with no way to say that 20 processes were planned
and 18 completed, and that each ran 3 values. That is a result schema
change, not just a doc one.

**Rounds.** Interleaved comparisons need alternating orders. The result
schema already has `procedure.round`, zero-based, kept by a retry, and
paired across sides. Proposal: an optional `round` in the order, copied
into it. `procedure.slot`, the realized position across all sides, can't be
assigned by a runner that sees one order; it needs whoever coordinates the
sides.

**Deferred target kinds.** A revision to build and a prebuilt artifact
(`runner.md`) are not designed yet; see the target question above.

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
