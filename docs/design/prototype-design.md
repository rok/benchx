# Prototype Design

**Status:** Draft for review
**Companion to:** `prototype-scope.md` (what's in the slice), the schema doc
(document formats), `runner.md`, `comparator.md`

## 1. Shape

One command-line tool, one on-disk Parquet store, three document formats.
No server, no daemon: the "transport" is the file system, which the ingest
contract (§5.4) already blesses as a conforming delivery path. Every arrow
in the slice is a file a reviewer can open — documents as JSON, the store as
Parquet any Arrow-capable tool can read directly.

```
bx run <workorder.json>          # runner+adapter → results/*.json
bx ingest <dir|file>             # sweep documents into the store
bx series [--case … --quantity …]# list series
bx history <series>              # one series, ordered by revision
bx compare <A> <B> [--json]      # A, B: revision, run key, or results dir
```

## 2. The three documents

**Work order** (input, written by hand or by a wrapper script):

```json
{
  "workorder_version": 1,
  "project": "arrow",
  "source": {"uri": "https://github.com/apache/arrow", "type": "git"},
  "target": {"build_dir": "/tmp/bench-plain"},
  "suite": "arrow-compute-vector-selection-benchmark",
  "filter": "TakeChunked.*",
  "repetitions": 10,
  "quantities": ["wall-time"],
  "provenance": {"run_key": "local-2026-08-30-a", "requested_by": "rok"}
}
```

**Result**: exactly the schema §5.2 ingest object, one file per
case × quantity, plus `workorder_ref` in provenance. No prototype-only
fields — criterion 1 (local file = ingest payload) is satisfied by
construction.

**Comparison document** (output of `bx compare`):

```json
{
  "comparison_version": 1,
  "contender": {"run_key": "local-…-b"},
  "baseline": {"run_key": "local-…-a"},
  "k": 3.0,
  "verdicts": [
    {"series": "…fingerprint…", "case": "TakeChunked…/4194304/2",
     "quantity": "wall-time", "verdict": "regressed",
     "effect": 0.024, "noise": 0.0021, "n": [10, 10],
     "estimates": {"baseline": 0.0455, "contender": 0.0466}}
  ],
  "only_in_baseline": ["…"], "only_in_contender": [],
  "incomparable": [{"case": "…", "differs": ["environment.cpu"]}]
}
```

`--json` emits this; default output renders it as the reviewer table
(regressed / improved / unchanged / indeterminate sections, then the
unmatched and incomparable listings with counts).

## 3. Runner + adapter (`bx run`)

Prototype runner accepts only `build_dir` targets: it globs the named suite
binary, refuses if absent, and invokes it via the Google Benchmark adapter
(`--benchmark_filter`, `--benchmark_repetitions`,
`--benchmark_format=json`). The adapter translates per schema §6.2:
repetition rows → observations, aggregate rows → producer summaries,
workload counters → case parameters, the rest → procedure/provenance.

Captured context (best effort, honestly): hostname + CPU model + core count
as environment identity (`machine/v1`); compiler and flags from the build
directory's cache if readable, else marked absent; git revision and dirty
flag from the source tree; kernel/OS as observed context. A dirty tree
stamps `revision.dirty = true` — recorded, not refused.

## 4. Store (`bx ingest` + queries)

A directory (default `~/.benchx/store`) of **Parquet datasets** owned by the
CLI:

- `results/` — one row per benchmark result, appended as one Parquet file
  per ingest invocation. Scalar fields (producer, ingest key, series
  fingerprint, revision, status, estimate, timestamps) are typed columns;
  observations are a list column; observed context, procedure, summaries,
  and provenance are nested/JSON columns. Analytical queries — histories,
  cross-series scans — read columns, not documents.
- `entities/` — small Parquet tables for project, source, case, quantity,
  series, environment, and revision, rewritten on change (they are tiny).
- `raw/<producer>/<ingest_key>.json` — the ingest documents, verbatim, per
  the schema's source-payload provenance rule. The Parquet tables are the
  queryable store; the raw documents are the audit trail it can be rebuilt
  from.

Idempotency and unit-conflict checks scan the existing datasets at ingest
time — fine at prototype scale; a real deployment would index this.
Occasional compaction of small result files into larger ones is an optional
maintenance command, not a correctness requirement.

Ingest per §5.4: validate against the schema (statuses, finiteness, unit
form), compute the series fingerprint server-side (here: CLI-side, same
code), auto-create entities, reject unit conflicts and idempotency conflicts
with taxonomy codes on stderr and a non-zero exit, count everything
(`ingested 42, duplicate 3, rejected 1 (unit-conflict)`). Re-running
`bx ingest` on the same directory is a visible no-op (criterion 2).

## 5. Comparator (`bx compare`)

Resolves each side to results (store query by revision/run key, or a
directory of result files — mixing sides is allowed), pairs by series
fingerprint, then per pair:

- effect = (contender − baseline) / baseline estimate;
- noise = pooled relative dispersion of the two observation sets (their
  coefficients of variation combined); producer precision summaries used
  when observations are absent; unknown otherwise;
- verdict: `|effect| > k × noise` → changed (labeled by direction metadata
  when present); else unchanged; unknown noise or n = 1 on a
  non-deterministic quantity → indeterminate; deterministic quantities
  compare exactly.

Default `k = 3`, overridable per invocation; per-project configuration is
deferred.

## 6. Deliberate simplifications

- Environment identity is coarse (hostname-level); continuity events,
  quarantine, artifact storage: absent.
- One adapter, one target kind, no builds, no environment enforcement.
- The store is single-user, no concurrency story; ingest-time uniqueness
  checks are scans, not indexes.
- Comparison documents are printed, not stored (open question in
  `comparator.md` stays open).

None of these change a contract; each is a smaller implementation of one.

## 7. Implementation notes

The prototype is written in **Python** — chosen (2026-08-31, after an
ecosystem survey against Rust and Go) for the most mature libraries on every
contract-critical need and the fastest iteration while the document formats
are still settling:

- `pyarrow` — Parquet/Arrow store, best nested list/struct ergonomics;
- `jsonschema` — validation of the three document formats;
- `rfc8785` (Trail of Bits) — canonical JSON for series fingerprints;
- stdlib elsewhere (`hashlib`, `subprocess`, `statistics`).

Distributed via `uv tool install` / `pipx`; no single-binary requirement at
prototype stage. If the prototype graduates, the store/comparator rewrite
target is Rust (`arrow`/`parquet`, `jsonschema`, `serde_json_canonicalizer`
crates) — cheap precisely because the documents and Parquet layout, not the
code, are the interfaces.

## 8. Review checklist

The prototype is correct when the six criteria in `prototype-scope.md` §3
pass; the demo script is: build two Arrow benchmark binaries (or any two
Google Benchmark builds), `bx run` both, `bx compare` the run keys, ingest
both into the store, re-ingest to show idempotency, and re-run the same
comparison from store queries — same verdicts from files and store.
