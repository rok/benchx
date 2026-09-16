# Harness Adapter Design

**Status:** Draft for review

**Companion to:** `system-decomposition.md` §3.2, `runner.md` §7, `benchmark-result-schema.md` (the schema; where this document and the schema differ, the schema wins)

**Author:** Rok Mihevc

## 1. Role

A harness adapter translates one native benchmark harness's output into schema results. It is the only component that knows a harness's file format, statistics, and quirks; everything downstream sees schema objects only.

Per `runner.md` §7 an adapter has two halves:

- **Driving:** turn a work order's scoping and precision settings into the harness's own invocation, run it, and capture its native output and exit status.
- **Translating:** turn native output plus a supplied context document into ingest objects (schema §5.2), one per attempt and quantity.

The translating half stands alone. A CI job, the workbench, or an importer can apply the same mapping to a native file without a runner, which is what lets a local result and a fleet result be the same object.

## 2. Principles

1. **Never invent.** An adapter reports what the harness reported and what the context document supplies. Anything else is absent, marked `unknown`, or a thin result (schema §4.1), never a default.
2. **One quantity per result.** A harness row measuring wall time, CPU time, and throughput yields three results sharing an `attempt_key` (schema §3 rule 3).
3. **Observations over aggregates.** Per-repetition rows become observations; harness aggregates become typed producer summaries alongside them, never instead of them (schema §3 rule 6).
4. **Split the harness's metadata by meaning.** Workload-describing values go to workload-variant parameters, intended settings to comparison context, realized settings to procedure, uncontrolled conditions to observed context, bookkeeping to provenance (schema §4.2). A harness field never lands in two places.
5. **Every outcome is a result.** A failed, timed-out, or skipped case becomes a result with that status and reason; absence always means "not attempted".
6. **Deterministic and idempotent.** The same native output and context produce byte-identical documents, and the same `(producer, ingest_key)` on re-run.
7. **The mapping is versioned.** `producer.mapping_version` names the exact native-to-schema rules applied; changing a rule changes the version.

## 3. Context document

The translating half cannot know where the native output came from. The runner, workbench, or importer supplies that as a **context document**, the adapter's second input. It carries exactly the schema fields a harness cannot report, and nothing the harness can:

| Context field | Schema destination | Who fills it |
|---|---|---|
| `producer` | `producer` | the adapter itself; name and version are its own, `mapping_version` is its rule set |
| `project` | `project` | runner or work order; absent for thin local results |
| `source`, `revision`, `subject_dirty`, `subject_tree` | top level and `provenance` | runner, from the checkout it measured |
| `benchmark` and its dirty flag and tree | `benchmark`, `provenance` | runner; absent for thin local results |
| `subject` descriptor | `coordinates.subject` | work order: components, roles, pinned revisions, build configuration |
| `environment` | `coordinates.environment` | runner's environment policy: identity schema and identity fields |
| `resource_selection` | `coordinates.resource_selection` | runner, when it selected a device or core set |
| `protocol` | `coordinates.comparison_context.protocol` | work order's precision settings and environment policy, spelled per schema Appendix B |
| `host runtime` | `coordinates.comparison_context` | runner: Python version, JVM, compiler where the harness does not report it |
| `observed_context` | `observed_context` | runner's snapshot: kernel, driver, governor, load, temperature |
| `run_key`, `attempt_key`, `labels`, `round` | `provenance`, `procedure.round` | run author and executor |
| `started_at` | `provenance.started_at` | runner; the harness's own timestamp is a fallback |
| `parameter_rules` | governs §4.3 | project configuration, optional |

The adapter merges the context document with harness-reported values field by field. When both report the same fact, the runner's value wins for identity fields and the harness's value is kept in `provenance.info` for audit. Google Benchmark's `host_name` never becomes environment identity, because the runner's identity schema decides what identity is.

A minimal context for a local `timeit` run is a source, a revision, dirty and tree state, a hostname environment, a run key, and an attempt key. That is enough for a valid thin result.

## 4. Translating half

### 4.1 Output

One ingest object per attempt and quantity, each validating against `schemas/measurement-result/0.1.0/schema.json` before it leaves the adapter. Documents are written as separate files named by their `ingest_key` with `/` and `:` replaced, so a directory of adapter output is a valid file-drop delivery (schema §5.4) and sorts by key. An adapter that cannot produce a valid document for a case emits an `error` result for that case with reason `adapter.mapping-failed` and the native fragment in `provenance.info`; it never drops the case.

### 4.2 Quantities and units

Each native measure maps to one schema quantity by name and canonical UCUM unit (schema §4.4, Appendix A). The adapter converts the harness's unit to the canonical one and records the original in `provenance.original_unit`. Distinct native semantics get distinct quantity names: Google Benchmark's `real_time` is `wall-time`, `cpu_time` is `cpu-time`, `bytes_per_second` is `throughput-bytes`. A harness measure with no schema counterpart becomes a project-declared quantity under project rules, or is retained in `provenance.info` and not emitted.

### 4.3 Workload variants and parameters

The workload name is the harness's case name. Parameters come from structured native fields when the harness has them, such as pytest-benchmark's `params` or JMH's `params`. Encoded names such as `BM_Sort/1024/2` are split into name and parameters only under a project's `parameter_rules`; without rules the full string is the workload name and nothing is parsed (schema §6). Harness counters are split by the rules too: a counter that describes the workload, such as null fraction, becomes a parameter; one that describes the run, such as `repetition_index`, goes to procedure; the rest go to observed context. Dataset identity, when the harness or work order names one, goes to `workload.dataset`.

### 4.4 Observations and summaries

Per-repetition rows become the observation batch, one value per repetition in the canonical unit after the harness's own normalization, which the adapter records under `procedure` (inner iterations, warmups performed) and `protocol` (calibration mode). When the harness reports per-repetition metadata, observations are structured objects carrying `ordinal` and any group or pair key. Harness aggregates map to typed summaries with `source: "producer"`: a mean or median to an `estimate` with the harness's estimator declared by name and method version, standard deviation or MAD to `statistic`, a reported confidence interval to `confidence_interval` with its level, opaque bounds such as `stat`/`sys` to `source_bounds`. An adapter never computes a statistic the harness did not report; the server derives what policy needs.

### 4.5 Statuses

| Native condition | Status | Reason |
|---|---|---|
| all repetitions completed | `success` | |
| some repetitions failed, usable evidence remains | `partial` | harness reason or `harness.partial` |
| harness reported a bound only, such as a timeout | `censored` | `timeout`, with the constraint |
| harness error, crash, or non-zero exit for the case | `error` | harness reason or `harness.error` |
| harness skipped the case explicitly | `skipped` | harness reason or `harness.skipped` |
| case in the work order, absent from output | `error` | `harness.no-output`, emitted by the driving half |

### 4.6 Keys

- `producer.name` is a stable namespaced adapter identity, such as `benchx/gbench-adapter`; `producer.version` is its software version; `mapping_version` its rule set.
- `ingest_key` is `<run_key>:<workload>/<parameters>:<quantity>` plus the attempt discriminator when a run holds several attempts of one variant. It is unique per producer and stable across re-runs of the translation.
- `attempt_key` is taken from the context document. When the driving half runs the harness it mints one per invocation; when translating a native file that already carries an attempt identifier with known semantics, it preserves that; otherwise it mints a distinct key per case rather than guessing that results were measured together (schema §6).
- `run_key`, `labels`, and `round` pass through untouched.

### 4.7 Compound outputs

A harness that reports a derived quantity per repetition, such as cupyx returning CPU and GPU time together, yields two ordinary results. An adapter emits a compound result (schema §4.5) only when the harness itself computed it per repetition; it does not derive compounds, which is server or comparator work.

## 5. Driving half

The driving half is a thin shell around one harness binary or entry point:

1. **Scope.** Translate the work order's case filters into the harness's filter syntax, such as `--benchmark_filter=<regex>` or pytest `-k`.
2. **Precision.** Translate requested repetitions, minimum time, and warmup into harness flags, and record the requested values under `protocol` so intended settings are comparison context. What the harness actually did is read back from its output into `procedure`.
3. **Environment.** Apply nothing itself. Thread caps, pinning, and device selection are the runner's environment policy; the driving half only passes through environment variables the policy set and records the harness's view of them.
4. **Run.** Invoke the harness with machine-readable output enabled, a per-attempt `attempt_key`, and a time limit. Capture stdout, stderr, exit status, and the native output file into provenance artifacts.
5. **Account.** Compare cases in the work order with cases in the output and emit `error` results with `harness.no-output` for the difference, so a truncated run never looks like a shorter suite.

The driving half never edits native output. Translation runs on the captured file so that the same file can be re-translated later under a newer mapping version.

## 6. Adapter catalog

The first adapters follow the schema's §6.2 mappings. Each entry names the native fields that matter and where they land.

### 6.1 Google Benchmark

| Native field | Destination |
|---|---|
| `benchmarks[].run_name`, `/`-encoded arguments | workload name; parameters only under `parameter_rules` |
| `run_type: iteration` rows | one observation per row per quantity |
| `run_type: aggregate` rows (`mean`, `median`, `stddev`, `cv`) | producer summaries: `estimate` for mean and median, `statistic` for the rest |
| `real_time`, `cpu_time`, `time_unit` | `wall-time`, `cpu-time` in `s` |
| `bytes_per_second`, `items_per_second` | `throughput-bytes` in `By/s`, `throughput-items` in `1/s` |
| `iterations` | `procedure.inner_iterations` per observation |
| `repetitions`, `repetition_index` | `procedure.attempted_repetitions`, observation `ordinal` |
| `threads` | `protocol.threads` |
| user counters | parameters, procedure, or observed context per `parameter_rules` |
| `error_occurred`, `error_message` | `error` status with the message as reason token and full text in `provenance.info` |
| `context.host_name`, `num_cpus`, `mhz_per_cpu`, `caches` | `provenance.info`; identity comes from the context document |
| `context.cpu_scaling_enabled`, `load_avg` | `observed_context` |
| `context.date` | `started_at` fallback |
| `context.executable`, `library_build_type` | `provenance.info`; build type belongs in the subject configuration the runner supplies |

### 6.2 pytest-benchmark

Round data (`stats.data` with `--benchmark-json`) becomes observations; `params` become parameters; `options.min_rounds`, `min_time`, `max_time`, `warmup` go to `protocol` as requested settings and `stats.rounds`, `iterations`, `warmup` performed go to `procedure`; `stats.min/mean/median/stddev/iqr` become producer summaries; `machine_info` and `commit_info` are audit only, superseded by the context document.

### 6.3 cupyx profiler

`cpu_times` and `gpu_times` per repetition become paired observations of `cpu-time` and `gpu-time` sharing an `attempt_key` and ordinals; `n_warmup` and `n_repeat` go to `protocol`; the timing method, CUDA events, goes to `protocol.timer`; the selected device to `resource_selection`.

### 6.4 JMH

Fork and iteration data become structured observations with `group` set to the fork; `scoreConfidence` becomes a `confidence_interval` at 99.9%; `mode` selects the quantity and unit; `params` become parameters; secondary metrics become sibling results.

### 6.5 timeit and ad hoc scripts

The workbench adapter for `timeit.repeat` output: each repeat is an observation after dividing by the loop count, which is recorded as `procedure.inner_iterations`; `protocol` records `timer: perf_counter` and adaptive calibration; the result is thin unless the context document supplies a project and benchmark identity.

## 7. Conformance

Every adapter ships:

- **Fixtures:** at least one native output file and context document per supported status, with the expected ingest objects committed beside them. A conformance test translates the fixtures and compares byte for byte.
- **Validation:** every emitted document validates against the pinned schema version; the conformance test runs the schema's own example checks.
- **Idempotency:** translating the same inputs twice yields identical `ingest_key`s and documents.
- **Attempt integrity:** sibling results from one native row agree on every field schema §5.3 lists.
- **Mapping changelog:** each `mapping_version` documents what changed and whether re-translation of old native files is recommended.

## 8. Boundaries

- **Not the runner:** does not build, prepare environments, or choose what runs.
- **Not the store:** computes no fingerprints, no series, no continuity; the ingest object it emits carries reported coordinates only.
- **Not the comparator:** emits no verdicts and derives no compounds.
- **Not an importer:** importers reuse the translating half on historical exports, adding the migration contract's thin-identity bookkeeping (schema §6); the adapter itself handles one harness's live output.

## 9. Open questions

1. Should `parameter_rules` live in the work order, in project configuration, or beside the benchmark suite in the subject repository? The last keeps rules versioned with the names they parse.
2. When a harness reports an aggregate the schema types differently from the harness's own definition, such as Google Benchmark's `cv`, is a `statistic` with the harness's name sufficient, or does the schema need a coefficient-of-variation summary type?
3. Does the driving half own the per-attempt time limit, or is that an environment-policy setting the runner enforces around any adapter?
4. How much of the context document is a formal contract artifact like the work order, versus a set of named arguments to the translating function? A formal document makes file-based translation replayable; arguments are simpler for the runner.
