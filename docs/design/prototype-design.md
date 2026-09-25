# Prototype Design

**Status:** Draft for review
**Companion to:** `prototype-scope.md` (what's in the slice); `benchmark-result-schema.md` (the result); `work-order.md` and `schemas/work-order/0.1.0` (#35, the work order); `harness-adapter.md`; `benchmark-environments.md`; `comparator.md`; `runner.md`, as narrowed by `benchmark-environments.md` §8; `measurement-result-parquet.md` (#30, the result row)

## 1. Shape

One command-line tool over a Python API, a local store that is a single
Parquet file, three document formats. No server, no daemon: the transport is
the file system, which the ingest contract (schema §5.4) already accepts as a
conforming delivery path. Every arrow in the slice is a file a reviewer can
open. JSON is for documents in transit, the work orders, result files, and
comparison documents that pass between components; the store is Parquet only,
one file any Arrow-capable tool can read.

```
bx run <order.json> [--out DIR] [--no-ingest]
                                         # runner + adapter → DIR/*.json, delivered to the store
bx ingest <dir|file>                     # sweep documents into the store
bx series [--workload … --quantity …]    # list series
bx history <series>                      # one series' points (a query)
bx head [-n 10] [--json]                 # the latest results in the store, newest first
bx compare --run KEY --profile revisions|environments --baseline VALUE
           [--label NAME] [--results DIR] [--k 3] [--json]
```

The CLI is a thin layer: each command is one call into the `benchx` package,
so the workbench, a CI script, or a notebook can do the same without a
subprocess.

The local store has one place, `~/.benchx/store.parquet`, and no command
takes another; `$BENCHX_HOME` relocates benchx's home as a whole, for tests
and CI. `bx run` delivers what it measures there: it writes the result files,
then ingests exactly those files. The `runner` module itself stays
store-unaware (`runner.md` §2 principle 6); the command composes it with
ingest, which is the delivery step of `runner.md` §4 and what the workbench
is. The files are still written first, so a result file remains a valid
ingest payload (criterion 1) and a rejected ingest loses nothing.
`--no-ingest` writes the files only, for delivery elsewhere. Delivery is an
invocation choice, never an order field, so replaying an order elsewhere does
not post to the original store.

## 2. The three documents

**Work order.** The prototype reads the #35 work order
(`schemas/work-order/0.1.0`, `workorder_version: 1`) and defines no format of
its own. One order is one side of one round: the runner executes one order
per invocation (`runner.md` §7), and #35 already restricts the target to what
the prototype needs, an existing `build_dir` with an optional `source_dir`.

Interleaving needs two fields #35 lists as an open question: `round`, which
it proposes as an optional order field copied to `procedure.round`, and
`slot`, which it says only whoever coordinates the sides can assign. #35's
schema rejects unknown top-level fields, so the prototype validates orders
against the #35 schema extended by exactly these two optional integers,
copied to `procedure.round` and `procedure.slot`, and proposes them to #35;
nothing else is added. The calling script is the coordinator: it writes one order per side and round and
runs them alternately. That loop is the caller's, not benchx's
(`benchmark-environments.md` §2.2 principle 4 and §5.7), since no harness can
interleave two separate binaries.

The smallest ad hoc order is #35's `examples/adhoc.json` with a round, a slot,
and a label added:

```json
{
  "workorder_version": 1,
  "source": {"uri": "https://github.com/apache/arrow", "type": "git"},
  "benchmark": {"kind": "subject"},
  "harness": {"name": "google-benchmark"},
  "target": {"kind": "build_dir", "build_dir": "/tmp/bench-hardened",
             "source_dir": "/home/rok/arrow"},
  "suite": "arrow-compute-vector-selection-benchmark",
  "filter": "TakeChunked.*",
  "quantities": ["wall-time"],
  "protocol": {"repetitions": {"mode": "fixed",
                               "levels": [{"unit": "repetition", "n": 10}]}},
  "round": 0,
  "slot": 1,
  "provenance": {"run_key": "urn:uuid:9b2e4f1a-6c3d-4e8f-a7b0-1c2d3e4f5a6b",
                 "labels": {"build": "hardened"}}
}
```

A tracked order adds `project` and, where it matters, `subject.name`; #35's
`examples/arrow.json` is the full form.

**Result:** exactly the schema §5.2 ingest object, one file per attempt ×
quantity, named by its `ingest_key`. The order is referenced as #35 §5 says:
`provenance.info.workorder_ref` = `sha256:` over the order's RFC 8785 form,
until the result schema gains a field for it. No prototype-only fields, so
criterion 1 holds by construction.

**Comparison document** (output of `bx compare`), following `comparator.md`
§5:

```json
{
  "comparison_version": 1,
  "mode": "run",
  "run_key": "urn:uuid:9b2e4f1a-…",
  "profile": "environments",
  "varying": "provenance.labels.build",
  "baseline": "plain",
  "contender": "hardened",
  "method": {"name": "benchx/paired-relative", "version": "v1",
             "estimator": "median", "k": 3.0, "min_rounds": 3},
  "identity_schema": "benchx/prototype-identity/v1",
  "local_only": true,
  "units": [
    {"workload": {"name": "TakeChunked…/4194304/2", "parameters": {}},
     "quantity": "wall-time",
     "series": {"baseline": "…", "contender": "…"},
     "rounds": 10,
     "reference_estimate": 0.0455, "effect": 0.024,
     "noise": 0.0021, "noise_source": "paired-rounds",
     "verdict": "regressed", "reason": null,
     "observed_context_differences": []}
  ],
  "missing": [{"workload": "…", "quantity": "wall-time", "side": "contender"}],
  "failed_invariants": [],
  "exclusions": [],
  "inputs": [{"producer": "benchx/gbench-adapter", "ingest_key": "…"}]
}
```

`--json` emits this; the default output renders it as the reviewer table
(regressed, improved, no change detected, and indeterminate sections, then
the missing, failed-invariant, and excluded listings with counts). A
comparison in which either side is not `clean` has `local_only: true`
(schema §5.5).

## 3. Runner and adapter (`bx run`)

The runner validates the order against the #35 schema, resolves
`target.build_dir/suite`, and refuses the order if the binary is absent. It
changes nothing on the machine and passes its own environment through, with
the order's `environment_variables` applied on top as #35 W6 requires.

The runner refuses, before running anything, an order it cannot apply
exactly (#35 W5): another harness or target kind, `workload_parameters`
(Google Benchmark takes none), a quantity other than `wall-time` or
`cpu-time`, or a protocol key the adapter has no flag for. Protocol keys the
order leaves out are recorded with Google Benchmark's defaults (#35 W4a).

The Google Benchmark adapter's driving half lists the planned cases with
`--benchmark_list_tests` and the order's filter, then runs each planned case
in its own process, with `--benchmark_filter=^case$`,
`--benchmark_repetitions`, `--benchmark_min_time`, and JSON output. One
process per case is what lets `timeout_seconds` apply to a single workload
variant, as #35 requires, and confines a crash to its case. Stdout, stderr,
and the native JSON are kept as provenance artifacts. Its translating half follows
`harness-adapter.md` §6.1: iteration rows become observations, aggregate rows
producer summaries, encoded names and user counters are split only under
`parameter_rules` (none in the prototype, so names stay whole and counters go
to observed context), and a planned case absent from the output is an `error`
result with reason `harness.no-output` (§5 step 5). Keys follow §4.6: one
`attempt_key` per case per invocation, and an `ingest_key` whose attempt
discriminator is the slot, since one run holds an attempt of each variant per
side and round, and the slot is the one number unique to each.

Context comes from the sources `benchmark-environments.md` §3 defines, each
landing where its §3.4 puts it:

- **Snapshot** (§3.1, the part readable without privileges): host name, CPU
  model, and core count as environment identity under `machine/v1`, also in
  ad hoc mode, so both profiles have a full environment identity (schema
  §5.5); OS, kernel, libc, governor, and load as observed context; an
  allowlist of thread-control environment variables as observed context,
  which is the allowlist option among those #35 leaves open for recording the
  inherited environment.
- **Source identity**, from `target.source_dir`, or from the
  `CMAKE_HOME_DIRECTORY` the build directory records when the order names
  none: revision, `subject_dirty`, and `subject_tree` (schema §4.1). When
  neither locates a checkout the runner refuses the order, because a result
  must state its revision (`runner.md` §2) and #35 §3's `unknown` case leaves
  none to state; that gap goes back to #35. The benchmark code is the
  subject's own checkout (`benchmark.kind: subject`).
- **Build configuration**, from a built-in plugin that reads
  `CMakeCache.txt` in the build directory: build type, compiler and version,
  flags, and the project's own options (cache entries prefixed with the
  upper-cased project name, `ARROW_*` for Arrow), never paths, so two directories configured
the same way report the same configuration. Nobody declared these, so the detected
  values are recorded as the intended ones in `coordinates.subject.configuration`
  (§3.4). This is what makes the hardened and plain directories differ in
  coordinates, which the `environments` profile requires.
- **Declared facts**, from `.benchx/setup.json` or `BENCHX_SETUP_FILE`
  (`harness-adapter.md` §5.1), for what the cache cannot tell, such as how a
  dependency was installed. The prototype has no placement rules, so they
  land in `observed_context.setup` and enter no identity.

`benchmark-environments.md` §3.4 asks that every fact carry its source
(`detected`, `declared`, or a plugin name). The prototype does not record it
yet: §9 question 1 leaves the representation open, and nothing in the slice
would read it.

What the prototype does not detect is recorded as absent, never guessed. In
particular a build directory can be stale against its `source_dir`; the
prototype records the tree as it is at run time and does not detect staleness
(`runner.md` §8 question 3).

## 4. Store (`bx ingest` + queries)

The local store is one Parquet file, always `~/.benchx/store.parquet` (§1);
the one other store is the temporary file `bx compare --results` compares
through. There are no side files:
no JSON, no separate entity tables. Each row is one result, the
`benchmark_result` of schema §4.1:

- **Message columns:** the row `measurement-result-parquet.md` (#30) derives
  from the result schema, typed structs and lists with open objects as
  canonical JSON, for queries.
- **Derived columns:** the store project (the result's own, or
  `local/<hostname>` for a thin one), `reported_coordinates_fingerprint`,
  `payload_sha256`, and an attempt signature over the fields schema §5.3
  requires results of one attempt to share.
- **The document:** `document` holds the result in its RFC 8785 canonical
  form. #30's columns cannot reproduce it, since its mapping is not
  byte-preserving (a bare observation and a structured one map alike), so this
  column is the audit copy and what the comparator reads.
- **The work order:** `work_order_ref`, and `work_order` with the order itself
  when it was delivered beside the results, so every result traces to its
  order inside the file (criterion 6).

The other core tables of schema §4.1, `project`, `source`,
`workload_variant`, `quantity`, `environment`, `revision`, `series`, and
`series_point`, are not stored. They are computed from the rows when a query
asks for them. Schema §4.1 already calls series and series points rebuildable
indexes; at prototype scale, rebuilding them on every query is cheaper than
keeping them consistent, and "entities auto-create" (schema §5.4) holds in the
sense that nothing is rejected for being first seen: the first result with a
quantity defines its unit, and later results are checked against it.

A Parquet file cannot be appended to, so an ingest that accepts anything
rewrites the file: the existing rows and the new ones go to a temporary file
beside it, which is synced and renamed over the store. The rename is atomic,
so a reader sees the old store or the new one, never a partial one, and the
acknowledgment means validated and durable. When the result schema has gained
a column or nested field since the file was written, the old rows are carried
over with nulls in it, so one file can hold results written under several
schema versions; a schema that removes or retypes a field is a new message
contract and a new store file.

Ingest follows schema §5.4. Each document is read strictly (duplicate keys,
non-finite numbers, and unsafe integers are rejected, as
`measurement-result-parquet.md` §5 describes, since JSON Schema validation
cannot see them) and validated against the result schema. Entities
auto-create. Rejections carry the §5.4 taxonomy codes: *malformed*,
*idempotency conflict*, *unit conflict*, *identity violation*, and
*attempt conflict*; *quarantined* does not occur, since quarantine is
deferred. Each is reported on stderr with a non-zero exit, and everything is
counted (`ingested 42, duplicate 3, rejected 1 (unit-conflict)`). Re-running
`bx ingest` on the same directory is a visible no-op (criterion 2).

Series need an identity policy and a list of estimators (schema §4.3, §4.5).
The prototype has one of each, fixed in code:

- **Identity policy** `benchx/prototype-identity/v1`: comparison identity is
  the reported coordinates with source URIs normalized, a thin result's
  implicit project, and the exact benchmark revision omitted. The prototype
  has no declared benchmark versions, and with benchmarks in the subject's
  checkout the benchmark revision changes on every commit, so keeping it
  would split history at every point (schema §1).
- **Estimators:** `median`, derived from observations, plus any producer
  estimate a result carries.

A thin result gets the implicit project `local/<hostname>` (schema §4.1).
Idempotency, unit, and attempt-integrity checks scan the store's bookkeeping
columns, which is fine at prototype scale; a real deployment would index them.

`bx head` shows the store's size and its latest results, newest first, with
run key, workload, quantity, status, median, revision, project, and labels;
with `--json` it prints the stored documents instead. Recency is ingest
order, since every ingest appends to the rewritten file.

`bx series` and `bx history` are queries over the derived `series` and
`series_point`.
`bx history` lists a series' points; without a revision graph revision order
is unavailable (schema §4.1), so it lists them by measurement start and says
so. It evaluates nothing, since history mode is deferred.

## 5. Comparator (`bx compare`)

Run mode as `comparator.md` §2.3 defines it. Inputs always come from a store
(§2.1): the local store by default, or, with `--results DIR`, a throwaway
store the directory of result files is ingested into first, for results that
were never delivered to the local one. The request names the run, the profile, and the baseline value of the
varying coordinate:

| Profile | Varying coordinate | `--baseline` names | Sides must agree on |
|---|---|---|---|
| `revisions` | subject tree id | a revision or tree id prefix | workload variant, subject configuration, environment, comparison context |
| `environments` | subject configuration, named by the label `--label` gives | the label value | subject revision, workload variant, environment, comparison context |

Before any verdict, the eligibility guard (§3) checks the profile's
invariants over the run: exactly two sides that differ only in the varying
coordinate, equal attempt counts per side, and sides alternating by
`procedure.slot`. A failed invariant is recorded and the affected units get no
verdict. A variant present on one side only is listed as missing
(criterion 4). Results with a status other than `success` are excluded and
listed.

Per comparison unit (one workload variant and quantity), the method
`benchx/paired-relative/v1`:

- pairs the two sides' attempts by `procedure.round`;
- takes each attempt's median observation;
- computes per round the relative difference d = contender / baseline − 1;
- reports the effect as the mean of d, and the noise as the standard error
  of d across rounds (`noise_source: paired-rounds`);
- indicates a change when |effect| > *k* × noise, labeled by the quantity's
  direction when known; otherwise *no change detected*;
- is indeterminate with a reason when fewer than `min_rounds` pairs exist
  (`insufficient-rounds`), when a baseline value is zero, or when the guard
  excluded the unit.

Deterministic quantities are deferred: none of the prototype's quantities is
one, so a unit whose quantity is declared deterministic is indeterminate with
reason `deterministic-deferred` rather than compared exactly (comparator §4).
Default
*k* = 3 and `min_rounds` = 3, overridable per invocation; per-project
configuration is deferred. Choosing a paired method for run mode is the
prototype's answer to `comparator.md` §7 question 1, open until reviewed.

Comparison documents are recomputed on demand and not stored
(`comparator.md` §5); the store keeps their inputs.

## 6. Demonstration

Both profiles use one shape: two prepared build directories, one run key, R
rounds, and a calling script that alternates the sides and assigns `round`
and `slot`.

- **Revisions:** two git worktrees of one source at the base and head
  commits, each built into its own directory with the same configuration.
  The two orders differ only in `target`. Compare with
  `bx compare --run KEY --profile revisions --baseline <base commit>`.
- **Environments:** one checkout configured twice with one option changed,
  as the Arrow local story does for hardening, into `/tmp/bench-plain` and
  `/tmp/bench-hardened`. The orders differ in `target.build_dir` and in the
  label `build: plain|hardened`. Compare with
  `bx compare --run KEY --profile environments --label build --baseline plain`.

The demo runs the two shapes once each. Revisions run ad hoc: the orders
name no project, and `bx compare --results` compares them through a
throwaway store. Environments run tracked: the orders name a project, and
the comparison reads the local store. The environments results are then
re-ingested to show idempotency, and compared again with `--results`; that
document must equal the one from the local store (criterion 8).

Every `bx run` delivers to the local store, so both shapes' results land in
`~/.benchx/store.parquet`, the ad hoc ones as thin results of project
`local/<hostname>`. Run keys carry a timestamp, so successive demo runs add
rows rather than colliding on `ingest_key`. The store and each series'
history grow from run to run, and the demo ends with `bx head`.

## 7. Deliberate simplifications

- One harness, one target kind, no builds, no environment policy: the user
  prepares both sides (`benchmark-environments.md` §2).
- Environment identity is the snapshot's host name, CPU model, and core
  count; continuity events, quarantine, and artifact storage are absent.
- One identity policy and one derived estimator, fixed in code.
- The store is one file, rewritten on every ingest that accepts something,
  with no concurrency story beyond the atomic rename; entities and series are
  computed on query, and ingest-time checks are scans, not indexes.
- Staleness of a build directory against its source tree is not detected.
- History has no revision order: there is no revision graph, so `bx history`
  lists points by measurement start.

None of these changes a contract; each is a smaller implementation of one.

## 8. Implementation notes

The prototype is written in **Python**, chosen on 2026-08-31 after an
ecosystem survey against Rust and Go for the most mature libraries on every
contract-critical need and the fastest iteration while the document formats
settle:

- `pyarrow` for the single-file Parquet store and nested list/struct columns;
- `jsonschema` with a `referencing` registry, since the work-order schema
  references the result schema (#35 §6);
- `rfc8785` for canonical JSON in fingerprints and the work-order hash;
- the standard library elsewhere (`hashlib`, `subprocess`, `statistics`).

The package has one module per component behind the CLI: `benchx.core`
(document loading, strict JSON, schema validation, and the rules schemas
cannot express, as proposed in #34), `benchx.runner`, `benchx.adapters.gbench`,
`benchx.store`, and `benchx.compare`. It is distributed with `uv tool install`
or `pipx`, with no single-binary requirement. Whether a graduated version is
rewritten in another language is decided later; the documents and the
Parquet layout, not the code, are the interfaces, which keeps that option
cheap.

## 9. Review checklist

The prototype is correct when the eight criteria in `prototype-scope.md` §3
pass. The demo script performs §6 for both profiles, in both shapes.
