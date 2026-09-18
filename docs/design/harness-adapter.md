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
| `protocol` | `coordinates.comparison_context.protocol` | work order's precision settings and environment policy, spelled per schema Appendix B, including every setting the harness output does not echo back: timing mode, warmup, calibration mode, confidence level, instrument and its value-altering switches |
| `scenario` | `workload.parameters.scenario`, `benchmark` | optional reference to a versioned scenario document that fixes the workload and names the estimator and direction, as the OpenTelemetry benchmarks do; the estimator declared there is carried with `method_version` naming the scenario revision |
| `host runtime` | `coordinates.comparison_context` | runner: Python version, JVM, compiler where the harness does not report it |
| `observed_context` | `observed_context` | runner's snapshot: kernel, driver, governor, load, temperature; facts from the setup file and context collectors (§5.1) |
| `run_key`, `attempt_key`, `labels`, `round` | `provenance`, `procedure.round` | run author and executor |
| `started_at` | `provenance.started_at` | runner; the harness's own timestamp is a fallback |
| `parameter_rules` | governs §4.3 | project configuration, optional |

The adapter merges the context document with harness-reported values field by field. When both report the same fact, the runner's value wins for identity fields and the harness's value is kept in `provenance.info` for audit. Google Benchmark's `host_name` never becomes environment identity, because the runner's identity schema decides what identity is. The merge is typed and per field, never a dictionary overlay: harness parameters live in `workload.parameters` and cannot collide with a schema field, so a benchmark parameter named `name` or `source` is just a parameter. An adapter does not autodetect machine identity itself, and it never fills a field it cannot know with a placeholder value; the field is absent, `unknown`, or the result is thin.

A minimal context for a local `timeit` run is a source, a revision, dirty and tree state, a hostname environment, a run key, and an attempt key. That is enough for a valid thin result.

## 4. Translating half

### 4.1 Input and output

The native input is everything the harness wrote, not one file: ASV's results JSON is unreadable without its `benchmarks.json` sidecar, cargo-criterion writes a report directory beside its message stream. The adapter names every file it needs and captures the sidecars as provenance artifacts with checksums, so a translation can be repeated from artifacts alone.

One ingest object per attempt and quantity, each validating against `schemas/measurement-result/0.1.0/schema.json` before it leaves the adapter. Documents are written as separate files named by their `ingest_key` with `/` and `:` replaced, so a directory of adapter output is a valid file-drop delivery (schema §5.4) and sorts by key. An adapter that cannot produce a valid document for a case emits an `error` result for that case with reason `adapter.mapping-failed` and the native fragment in `provenance.info`; it never drops the case, and it never emits a document that fails validation with only a warning attached.

### 4.2 Quantities and units

Each native measure maps to one schema quantity by name and canonical UCUM unit (schema §4.4, Appendix A). The adapter converts the harness's unit to the canonical one and records the original in `provenance.original_unit`. Distinct native semantics get distinct quantity names: Google Benchmark's `real_time` is `wall-time`, `cpu_time` is `cpu-time`, `bytes_per_second` is `throughput-bytes`. A harness measure with no schema counterpart becomes a project-declared quantity under project rules, or is retained in `provenance.info` and not emitted.

### 4.3 Workload variants and parameters

The workload name is the harness's case name. Parameters come from structured native fields when the harness has them, such as pytest-benchmark's `params` or JMH's `params`. Encoded names such as `BM_Sort/1024/2` are split into name and parameters only under a project's `parameter_rules`; without rules the full string is the workload name and nothing is parsed (schema §6). Harness counters are split by the rules too: a counter that describes the workload, such as null fraction, becomes a parameter; one that describes the run, such as `repetition_index`, goes to procedure; the rest go to observed context. Dataset identity, when the harness or work order names one, goes to `workload.dataset`. The converse holds as well: an adapter never encodes parameters, a quantity, a package, or a unit into the workload name to tell results apart. Those are structured fields, and a name assembled from them changes whenever their serialization does. Nor does a name carry control flags: a recognized suffix such as Bencher's `-bencher-ignore` is stripped into `provenance.labels`, never left in identity. Native parameter values are kept as the harness serialized them, ASV's `repr()` strings included, never evaluated or re-serialized, and the order of parameter combinations is taken from the result file rather than the current suite, because the two can disagree.

### 4.4 Observations and summaries

Per-repetition rows become the observation batch, one value per repetition in the canonical unit after the harness's own normalization, which the adapter records under `procedure` (inner iterations, warmups performed) and `protocol` (calibration mode). When the harness reports per-repetition metadata, observations are structured objects carrying `ordinal` and any group or pair key. Harness aggregates map to typed summaries with `source: "producer"`: a mean or median to an `estimate` with the harness's estimator declared by name and method version, standard deviation or MAD to `statistic`, a reported confidence interval to `confidence_interval` with its level, opaque bounds such as `stat`/`sys` to `source_bounds`. A harness's single headline number is an estimate whose estimator the adapter must know and declare: pytest-benchmark's `ops` is the reciprocal of the mean, JMH's `score` depends on `mode`, cargo's `bench:` value is a median with half the min-to-max spread as its deviation. When the adapter cannot establish what the number is, the estimator is `source-defined` with the harness's own label, never a guessed `mean`. Dispersion is typed the same way: an absolute deviation is a `statistic` in the quantity's unit, a relative one such as `±1.12%` is a `statistic` named as relative and dimensionless, and a bound whose meaning is unknown is `source_bounds` with the harness's label. A dispersion figure is never stored as a string. An adapter never computes a statistic the harness did not report; the server derives what policy needs. Observations are always finite: a repetition that produced no value is not a `null` placeholder in the batch but a smaller batch with `procedure.completed_repetitions` below `attempted_repetitions` and status `partial`. Inner iterations per observation and the repetition count are two different numbers and are never conflated into one `iterations` field. When the iteration count varies per observation, as in cargo-criterion's `[d, 2d, …, Nd]` samples and BenchmarkDotNet's per-measurement `Operations`, each structured observation carries its own count and `procedure.inner_iterations` is omitted; the per-iteration value is the total divided by that count.

Some harnesses emit a post-processed batch beside the raw one. BenchmarkDotNet's `Result` rows are its `Workload/Actual` rows minus the median overhead with outliers removed. The adapter takes the raw rows as the batch and never subtracts overhead or drops outliers itself; a harness's processed batch is kept only when the processing is declared under `protocol`, and the overhead rows become a sibling `overhead-time` result or provenance. Rows whose unit is a percentage or ratio, such as Google Benchmark's `cv` and `RMS` aggregates, are dimensionless `statistic`s and are never converted with the time unit. A harness that rounds its stored aggregates, ASV to five significant digits, has that precision recorded in the summary's `method` so a later recomputation from observations can tell rounding from disagreement. A value the harness derives from a synthetic quantity by a constant, CodSpeed's simulated cycles divided by an assumed frequency and presented as time or speed, is stored as the underlying quantity with the constant in `provenance.info`, never as `wall-time` or a rate.

A status-valued native metric, LNT's `execution_status` or `compile_status`, is not a quantity. It sets the status and reason of its sibling results for that test. A string-valued native metric such as a binary hash is provenance.

### 4.5 Statuses

| Native condition | Status | Reason |
|---|---|---|
| all repetitions completed | `success` | |
| some repetitions failed, usable evidence remains | `partial` | harness reason or `harness.partial` |
| harness reported a bound only, such as a timeout | `censored` | `timeout`, with the constraint |
| harness error, crash, or non-zero exit for the case | `error` | harness reason or `harness.error` |
| harness skipped the case explicitly | `skipped` | harness reason or `harness.skipped` |
| case in the work order, absent from output | `error` | `harness.no-output`, emitted by the driving half |
| harness marks the case as not applicable, such as ASV's `NaN` for an invalid parameter combination | `skipped` | harness reason or `harness.not-applicable` |

A case is never dropped by a `continue` in the mapping code. Every native row and every ordered case ends as exactly one result per quantity. When a source records failure only at a coarser grain than the variant, as rustc-perf's error table does per benchmark, the adapter emits one `error` result at that grain, with the workload name and no parameters, and never fans it out to guessed variants. A harness's sentinel revision values, pytest-benchmark's `"unversioned"` and `"unknown"`, never become a revision key; the context document's revision is authoritative and a missing one makes the result thin.

### 4.6 Keys

- `producer.name` is a stable namespaced adapter identity, such as `benchx/gbench-adapter`; `producer.version` is its software version; `mapping_version` its rule set.
- `ingest_key` is `<run_key>:<workload>/<parameters>:<quantity>` plus the attempt discriminator when a run holds several attempts of one variant. It is unique per producer and stable across re-runs of the translation. Each component is percent-escaped so that a `/` or `:` inside a workload name, common in Nyrkiö-style path names and pytest node ids, cannot collide with the separators.
- `attempt_key` is taken from the context document. When the driving half runs the harness it mints one per invocation; when translating a native file that already carries an attempt identifier with known semantics, it preserves that; otherwise it mints a distinct key per case rather than guessing that results were measured together (schema §6).
- `run_key`, `labels`, and `round` pass through untouched, and are identical on every result the adapter emits for one native output.
- Each catalog entry states what its `attempt_key` groups. It is always one execution of one workload variant; grouping across variants, such as "all parameter values of one benchmark" or "one suite file", is `batch_key`, which is provenance and never used for pairing.
- `started_at` is the measurement start reported by the harness or the context document, never the time the adapter constructed the document. When neither reports one and the source carries only an ordering timestamp, Codespeed's revision date for instance, that value is used and `provenance.info.started_at_source` names the fallback.

### 4.7 Compound outputs

A harness that reports a derived quantity per repetition, such as cupyx returning CPU and GPU time together, yields two ordinary results. An adapter emits a compound result (schema §4.5) only when the harness itself computed it per repetition; it does not derive compounds, which is server or comparator work.

## 5. Driving half

The driving half is a thin shell around one harness binary or entry point:

1. **Scope.** Translate the work order's case filters into the harness's filter syntax, such as `--benchmark_filter=<regex>` or pytest `-k`.
2. **Precision.** Translate requested repetitions, minimum time, and warmup into harness flags, and record the requested values under `protocol` so intended settings are comparison context. What the harness actually did is read back from its output into `procedure`. Every setting the output does not echo is recorded here or nowhere: Google Benchmark's timing mode, warmup time, and random interleaving; pytest-benchmark's pedantic versus calibrated mode and warmup rounds; cargo-criterion's confidence level and resample count; JMH's warmup and measurement plan. The driving half also asks for the fullest output the harness offers, such as BenchmarkDotNet's full rather than brief export, since a brief export has no observations.
3. **Environment.** Apply nothing itself. Thread caps, pinning, and device selection are the runner's environment policy; the driving half only passes through environment variables the policy set and records the harness's view of them.
4. **Run.** Invoke the harness with machine-readable output enabled, a per-attempt `attempt_key`, and a time limit. Capture stdout, stderr, exit status, and the native output file into provenance artifacts. A non-zero exit does not abort translation: whatever native output exists is translated, and the exit status becomes the reason on the results that lack output.
5. **Account.** Compare cases in the work order with cases in the output and emit `error` results with `harness.no-output` for the difference, so a truncated run never looks like a shorter suite.

The driving half never edits native output. Translation runs on the captured file so that the same file can be re-translated later under a newer mapping version.

### 5.1 Context collectors

Some facts that could explain a change in an estimate are reported by neither the harness nor the runner: the options a pinned library was compiled with, an inherited environment variable, whether the CPU throttled during the run. A **context collector** is a plugin for recording them. It is a last resort: a fact the harness output, the work order, or the runner's environment policy can supply comes from there, and a collected fact never overrides one.

A collector is a named command registered for one of two points, `before` or `after` the harness invocation of step 4. The driving half runs it in the harness's working directory and environment, with the harness's privileges and no more, outside any timed region and under a time limit. The command changes nothing and prints one JSON object of facts to stdout:

```json
{"blas": "openblas-0.3.27", "simd_baseline": ["SSE", "SSE2", "SSE3"]}
```

The driving half captures that output as a provenance artifact and adds the facts to the context document's `observed_context` under the collector's name, here `observed_context.numpy-build.blas`. Translation therefore stays repeatable from artifacts, and a collector cannot collide with the runner's snapshot or with another collector. Facts are copied to every result of the invocation they were collected around. A collector that fails, times out, or prints anything else contributes no facts, and those results carry the warning `collector-failed`; nothing is substituted and the run continues.

**Setup file.** The simplest collector runs no code. By convention the party that prepares an environment can write what it knows into `.benchx/setup.json` at the root of the benchmark suite, as one JSON object of facts in the same shape, and the party that runs benchmarks there needs to know nothing about how the environment was built:

```json
{"install": "source-build", "cflags": "-O3 -march=x86-64-v3", "blas": "openblas-0.3.27", "image": "sha256:4f1c..."}
```

The driving half reads the file before each harness invocation and treats it as the output of a collector named `setup`: captured as an artifact, placed under `observed_context.setup`, and with an unreadable file handled as a failed collector. An absent file is not an error. The file describes one prepared environment, so it is written by the setup step and never committed, and the suite lists `.benchx/` in its `.gitignore`; an untracked file would otherwise enter the benchmark tree id and mark the tree dirty (schema §4.1). When one checkout serves several environments, as in an `environments` run (schema §5.5), each environment sets `BENCHX_SETUP_FILE` to its own file. The file is a declaration, not an observation: the adapter reports what it says and whoever writes it owns its truth, so a fact that setup can declare belongs here and a command collector is for what nobody can declare.

Collected facts are observed context and never enter identity on their own. A project that needs one to match, a BLAS backend for instance, promotes it into reported coordinates through a new mapping version and identity-policy schema (schema §4.2). Values should therefore be the same whenever the environment is the same: no timestamps, absolute paths, or process ids, and lists sorted where order carries no meaning.

Recommended facts, none of them required:

| Point | Collect |
|---|---|
| `before` | build options of the subject and its pinned libraries as the library itself reports them, such as `numpy.show_config()`, `pyarrow.build_info`, or selected `CMakeCache.txt` entries; compiler and flags; the BLAS and threading backends actually loaded; named environment variables that alter behaviour, never the whole environment, because results are published; governor, SMT, turbo, transparent huge pages, ASLR |
| `after` | load, CPU frequency, temperature, and throttle counters over the invocation |

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
| `skipped`, `skip_message` | `skipped` status; a separate pair from the error pair, absent on normal rows |
| `aggregate_name`, `aggregate_unit` | `time` aggregates are summaries in the quantity's unit; `percentage` aggregates such as `cv` and custom statistics are dimensionless `statistic`s; aggregates exist only when at least two repetitions succeeded, so their absence is not an error |
| `BigO` and `RMS` rows (`big_o`, `cpu_coefficient`, `real_coefficient`, `rms`) | family-level complexity fit, not a summary of one variant; project-declared quantities on a family result or `provenance.info` |
| `family_index`, `per_family_instance_index` | `provenance.info` |
| timing mode (`UseRealTime`, `UseManualTime`, `MeasureProcessCPUTime`), warmup time, `min_time` form, random interleaving, perf-counter list | not in the JSON; recorded by the driving half under `protocol`; counter and rate values take their denominator from the timing mode |
| `context.host_name`, `num_cpus`, `mhz_per_cpu`, `caches` | `provenance.info`; identity comes from the context document |
| `context.cpu_scaling_enabled`, `load_avg` | `observed_context` |
| `context.date` | `started_at` fallback |
| `context.executable`, `library_build_type` | `provenance.info`; build type belongs in the subject configuration the runner supplies |

Attempt key: one per `run_name` row group, that is per encoded case; `batch_key` may group the cases of one binary. Aggregate rows are kept as producer summaries, not discarded. User counters carry no flags in the JSON, so whether a counter is a rate, per-thread, or per-iteration value comes from the quantity declaration under `parameter_rules`.

### 6.2 pytest-benchmark

Round data (`stats.data`, always present with `--benchmark-json`) is per-iteration time and becomes observations; `params` become parameters and `fullname` is the workload name; `options.min_rounds`, `min_time`, `max_time`, `warmup`, `timer`, and `disable_gc` go to `protocol` as requested settings, with `timer` as `protocol.timer`; `stats.rounds` and `iterations` go to `procedure`; `stats.min/mean/median/stddev/iqr` become producer summaries, `ops` is the reciprocal of the mean, and `ld15iqr`, `hd15iqr`, and the `outliers` string are `source_bounds` with the harness's labels because their definitions differ from their docstrings; `machine_info` and `commit_info` are audit only, superseded by the context document, and `commit_info.id` may be a sentinel. Not in the output and therefore recorded by the driving half: pedantic versus calibrated mode, warmup rounds performed. Errored and skipped tests are absent from the export, which is what the driving half's accounting exists for.

### 6.3 cupyx profiler

`cpu_times` and `gpu_times` per repetition become paired observations of `cpu-time` and `gpu-time` sharing an `attempt_key` and ordinals; `n_warmup` and `n_repeat` go to `protocol`; the timing method, CUDA events, goes to `protocol.timer`; the selected device to `resource_selection`.

### 6.4 JMH

`rawData[fork][iteration]` becomes structured observations with `group` set to the fork; `score` is the mean of iteration scores across forks and is declared as such; `scoreError` is a t-based 99.9% half-width and `scoreConfidence` becomes a `confidence_interval` of the mean at that level, except that both are serialized as the string `"NaN"` when fewer than three iterations exist and are then omitted; `mode` selects quantity and unit, `ops/<tu>` for throughput and `<tu>/op` for the time modes; in `sample` mode `rawDataHistogram` is a per-iteration multiset and is kept as weighted structured observations or an artifact, and `scorePercentiles` are estimates only in that mode; `secondaryMetrics` become sibling results whose `rawData` may be ragged against the primary; `params` are strings and are typed only under rules; `warmup*`, `measurement*`, and `jvmArgs` go to `protocol`, `jvm`, `jdkVersion`, and `vmName` to comparison context as host runtime.

### 6.5 cargo-criterion

`--message-format=json` emits one object per line keyed by `reason`; unknown reasons and fields are tolerated. For `benchmark-complete`, `measured_values[i]` is the total time for `iteration_count[i]` iterations, so each observation is their quotient with the count on the structured observation; `slope` is an estimator in its own right, a regression of sample time on iteration count, and `typical` resolves to `slope` or `mean` and is declared as whichever it was rather than stored as a third estimate; `mean`, `median`, `median_abs_dev`, and `slope` bounds are bootstrap `confidence_interval`s at the run's `confidence_level`, which the message omits and the driving half supplies together with `nresamples`; `throughput[].per_iteration` is a workload parameter and rate results are derived, not read; `change` is a verdict against an untracked baseline and is dropped; `report_directory` is an artifact reference and `group-complete` supplies `batch_key`; a `unit` other than `ns` comes from a custom measurement and maps to a project-declared quantity.

### 6.6 BenchmarkDotNet

Observations come from `Measurements` rows with `IterationMode: Workload` and `IterationStage: Actual`, each `Nanoseconds / Operations` with `Operations` on the observation, `LaunchIndex` as `group`, and `IterationIndex` as ordinal; `Overhead/Actual` rows become a sibling `overhead-time` result; `Result` rows are the harness's processed batch and are not used unless the mapping declares the overhead subtraction and outlier mode under `protocol`; `Jitting`, `Pilot`, and `Warmup` counts go to `procedure`. `Statistics.ConfidenceInterval` is of the mean at level 0.999, `Percentiles` are estimates, the remaining moments and fences are `statistic`s with source names; `Memory.BytesAllocatedPerOperation` and the `Gen*Collections` counts are aggregate-only sibling quantities from the last launch; `Parameters` is a printed string split only under rules and `FullName` is the workload name; `HardwareIntrinsics`, `HasRyuJit`, `Configuration`, and `RuntimeVersion` are subject configuration, `HardwareTimerKind` and `ChronometerFrequency` are `protocol.timer`, `HasAttachedDebugger` is observed context. Job settings are not exported and come from the work order; the driving half requests the full export.

### 6.7 ASV

A live ASV run is read from its results JSON plus `benchmarks.json`. Rows are positional against `result_columns`; `samples` when present become observations and `result` is a median estimate; `stats_ci_99_a/b` become a `confidence_interval` at level 0.99 whose `method` names the runner's quantile method and its small-sample fallback; `stats_q_25/q_75` are `statistic`s; `null` is `error` and `NaN` is `skipped`; `version` is benchmark identity; the file's `params` are kept verbatim and combination order follows the file; `profile` is an artifact. A results file accumulates runs and its `started_at` is the latest, so the driving half supplies the start time of the attempt it just ran.

### 6.8 timeit and ad hoc scripts

The workbench adapter for `timeit.repeat` output: each repeat is an observation after dividing by the loop count, which is recorded as `procedure.inner_iterations`; `protocol` records `timer: perf_counter` and adaptive calibration; the result is thin unless the context document supplies a project and benchmark identity.

### 6.9 Custom JSON in the github-action-benchmark shape

An on-ramp for harnesses without an adapter: an array of `{name, value, unit, range?, extra?}` entries, the format that action accepts for its custom tools. Each entry becomes one aggregate-only result whose estimate is `source-defined` unless a scenario document names it, whose unit is converted to UCUM with the original kept, and whose direction comes from the quantity declaration rather than from the tool name. `range` is typed per §4.4 when its form is recognizable and kept as `source_bounds` otherwise. `extra` goes to `provenance.info` verbatim; when a producer documents it as `key=value` lines, as the OpenTelemetry benchmarks do with `runner`, `cpu`, `kernel`, `runtime`, and `framework`, rules split those keys by meaning the same way counters are, and undocumented keys stay in `provenance.info`. Projects are told plainly that this path stores no observations and that a real adapter recovers them.

## 7. Conformance

Every adapter ships:

- **Fixtures:** at least one native output file and context document per supported status, with the expected ingest objects committed beside them. A conformance test translates the fixtures and compares byte for byte.
- **Validation:** every emitted document validates against the pinned schema version; the conformance test runs the schema's own example checks.
- **Idempotency:** translating the same inputs twice yields identical `ingest_key`s and documents.
- **Attempt integrity:** sibling results from one native row agree on every field schema §5.3 lists.
- **Mapping changelog:** each `mapping_version` documents what changed and whether re-translation of old native files is recommended.

## 8. Prior art

Two existing adapter layers were read closely. Their choices are the reason for several rules above.

### 8.1 Conbench's `benchadapt`

Conbench ships the closest existing design: a `BenchmarkAdapter` base class that runs a command, transforms native output into `BenchmarkResult` records, and posts them, with Google Benchmark, Archery, ASV, and Folly implementations. Several of its choices are the reason for rules above.

| Conbench behaviour | Consequence | Rule here |
|---|---|---|
| One class runs the harness, transforms, and posts; `subprocess.run(check=True)` aborts on a non-zero exit | a crashing suite loses every result that did complete | driving and translating halves; translation always runs on captured output (§5) |
| Runtime metadata injected through `result_fields_override` and `result_fields_append`, a shallow dictionary overlay | a parameter named `name` clobbers the benchmark name, so the ASV adapter renames it `name_`; overrides replace whole dictionaries silently | typed context document with per-field precedence; parameters in their own object (§3) |
| Identity is one untyped `tags` dictionary: name, parameters, `suite`, `source`, plus anything appended | any stray tag splits history; Google Benchmark parameters land as one opaque string `"32768/0"` | parameters, comparison context, observed context, and provenance are separate destinations; parsing only under declared rules (§4.3) |
| `batch_id` means a benchmark name in one adapter, a suite in another, a file in a third | no consumer can rely on what a batch groups | `attempt_key` is always one execution of one variant; wider grouping is `batch_key` and each adapter states what it groups (§4.6) |
| Aggregate rows are dropped, and the server recomputes mean, median, min, max, standard deviation, and IQR from samples, letting its own value win on conflict | producer statistics vanish; single-sample results with aggregates are "inconsistent" and partly ignored | producer summaries are kept and typed; the store derives points beside them and warns on discrepancy, never overwrites (§4.4) |
| One `iterations` field means micro-benchmark loop count in some clients and sample count in others, resolved by special cases on the server | ambiguity that had to be documented as legacy | inner iterations and repetitions are distinct procedure fields (§4.4) |
| A `null` inside `stats.data` marks the whole result as errored with a generated message | partial evidence is discarded as failure | finite observations only; missing repetitions shrink the batch and set `partial` (§4.4, §4.5) |
| The ASV adapter skips `NaN` results and unknown benchmarks with `continue` | cases vanish from the store instead of appearing as skipped | every case ends as a result; `NaN` is `skipped` (§4.5) |
| `machine_info` is autodetected in the adapter from `platform.node()`, `lscpu`, and `nvidia-smi`, with an environment variable to pin the host name; required fields the ASV adapter cannot supply are filled with `0` and `"x"` | identity depends on where the adapter ran, and mandatory fields produce fabricated values | identity comes from the runner's environment policy; unknown is `unknown` or absent, never a placeholder (§3) |
| `timestamp` defaults to the time the result object was constructed | measurement time and translation time are conflated | `started_at` is measurement start (§4.6) |
| No idempotency key; results are posted one by one with a single retry, and a duplicate POST creates a duplicate result | retries are unsafe and partial delivery is undetectable | deterministic `ingest_key`; file drop is the delivery path (§4.1, §4.6) |
| `to_publishable_dict` warns "not publishable" and posts anyway | invalid results reach the server | no document leaves the adapter unless it validates (§4.1) |
| `run_name`, `run_reason`, and `run_tags` are assumed consistent across a run "with no technical enforcement" | consumers cannot rely on the assumption | run-level fields are identical on every result of one output (§4.6); the store enforces attempt integrity |

Two Conbench choices are kept deliberately. Free-form `optional_benchmark_info` and `validation` map to `provenance.info` and `quality.validation`. And its rule that a result without a commit is "not considered for time series analysis" is the ancestor of thin results and the local-only comparison.

### 8.2 `github-action-benchmark`

The action extracts twelve harness formats into one record, `{name, value, unit, range?, extra?}`, appends it to a JSON file on a GitHub Pages branch, and compares against the previous entry with a flat ratio threshold. It is the most widely deployed adapter layer in the open-source ecosystem, and its record shape is what the schema doc's migration table (§6.1) imports.

| Action behaviour | Consequence | Rule here |
|---|---|---|
| Every harness collapses to one `value`; pytest's per-round `data`, JMH's `rawData`, and Google Benchmark's `cpu_time` are dropped or written into the free-text `extra` field | observations are unrecoverable; a second quantity survives only as prose | anything the harness reports as a number is an observation, a summary, a quantity, or a procedure field; `extra` is the anti-pattern (§4.2, §4.4) |
| `range` is a string whose meaning depends on the tool: `± dev` for cargo, `±1.12%` relative for benchmark.js, `stddev: 0.003` for pytest; the normalizer parses only the `±` form and silently skips the rest | dispersion cannot be compared or converted | dispersion is typed, absolute or relative is explicit, unknown bounds are `source_bounds` (§4.4) |
| Units are canonicalized by lowercasing and are converted to the *previous entry's* unit at write time, for the time and ops-per-time families only | a series' unit is whatever its first entry used; other families never convert | the quantity's canonical unit is fixed at declaration and the adapter converts to it, keeping the original (§4.2) |
| Direction is a property of the tool, so two custom tool names exist for "bigger" and "smaller", and Go's mixed-direction reported metrics are all treated as smaller-is-better | a throughput metric from a time-oriented tool is compared backwards | direction is quantity metadata (schema §4.4), never tool-level (§6.9) |
| JMH parameters are stringified into the name; Go appends the unit to name secondary metrics and a package suffix on collision | identity depends on serialization; a formatting change splits history | parameters and quantities are structured fields and never encoded into names (§4.3) |
| Google Benchmark aggregate rows are extracted as benchmarks named `_mean`, `_median`, `_stddev`; repeated rows share a name and the comparator keeps the first match | aggregates get their own histories and repetitions are lost | `run_type` is honored: repetitions are observations, aggregates are summaries (§6.1) |
| The headline number is whichever field the extractor picked: `real_time`, `ops`, `score`, `Mean`, a median; nothing records which statistic it is | a series mixes estimators without saying so | the estimate carries an estimator declaration; unknown means `source-defined` (§4.4) |
| The commit comes from the CI event payload, with a pull request's `repo.updated_at` used as its timestamp, and `date` is extraction time | the revision recorded can differ from the code measured, and timestamps are not measurement times | revision and tree id come from the checkout the runner measured; `started_at` is measurement start (§3, §4.6) |
| Text scrapers skip lines that do not match and throw on the first layout deviation; an empty extraction is fatal for the whole run | partial output is either silently thinned or entirely lost | machine-readable harness output is preferred, and every ordered case ends as a result (§4.5, §5) |
| The README warns that pull-request runs pushing to the data branch let any contributor rewrite history, and that hosted runners vary by 10 to 20 percent | trust and environment are left to the workflow author | results from untrusted sources carry their producer identity and are quarantined by ingest policy, never filtered by the adapter; hosted versus dedicated is environment identity, not a caveat |

Two of its choices are worth keeping. The custom JSON shape is a genuinely low on-ramp, which §6.9 adopts as an input format. And storing history in a plain JSON file in a branch, with `max-items-in-chart` as the only retention control, is a reminder that the file-drop path (schema §5.4) must not be the place where history is truncated.

### 8.3 Other systems and harnesses

The remaining systems in the schema doc's review list were read for adapter lessons. Those not already stated above:

| System | Behaviour | Rule here |
|---|---|---|
| Bencher | six adapters fill the same untyped `lower_value`/`upper_value` with six meanings: a CI, a deviation, min and max, a relative margin; a `--average` switch chooses mean or median without recording it; repeated runs are reduced to the median entry, discarding samples | dispersion is typed and the estimator declared (§4.4); observations are never reduced by the adapter |
| Bencher | a `-bencher-ignore` suffix on the benchmark name is a control flag, stripped for identity | names never carry flags; recognized suffixes become labels (§4.3) |
| LNT | failure is a sibling metric, `execution_status` non-zero; `hash` is a string metric; lists across metrics are zipped by index into one sample row | status metrics set sibling status, string metrics are provenance (§4.4); paired rows keep matching ordinals |
| rustc-perf | errors are recorded per artifact and benchmark, never per profile, scenario, or metric; `backend`, `target`, and `frontend_threads` were backfilled by migration defaults on old rows | one `error` at the source's grain, no fan-out (§4.5); a coordinate a source backfilled is imported thin with the default noted, not as a reported value |
| ASV | one results file per machine, commit, and environment accumulates runs; `started_at` is overwritten; parameter combinations follow the file's own `params`, which may differ from the suite; stored statistics are rounded to five significant digits; the CI method changes with sample size | sidecars are inputs and artifacts (§4.1); values and order come from the file (§4.3); rounding precision is recorded in `method` (§4.4); the driving half supplies the attempt's own start time (§6.7) |
| Codespeed | a result is unique per revision, executable, benchmark, and environment, so a rerun replaces; `date` is nullable; `kernel` and `os` are environment identity | a source without a measurement time uses a named fallback (§4.6); environment fields the target treats as observed context are kept in provenance so the source's splits stay reproducible |
| Nyrkiö | the test name is a `/`-separated path that also names the API route; `timestamp` is part of the identity key; unit and direction are free per document | key components are escaped (§4.6); unit and direction conflicts are ingest rejections, not adapter fixes |
| CodSpeed | one run, simulated cycles weighted by cache misses, divided by an undisclosed constant frequency and presented as a speed; `exclude-allocations` changes what the value means; two spellings for one instrument | store the underlying synthetic quantity, never wall time (§4.4); instrument identity and value-altering switches are protocol, aliases are normalized under a mapping version (§3) |
| OpenTelemetry benchmarks | a stable scenario document is the single source of truth for workload, estimator, and direction; the output is the action's custom shape with `extra` as documented `key=value` lines; the revision axis is a dependency version | the context document may reference a versioned scenario for the estimator (§3); documented `extra` keys are split by rules (§6.9); a dependency version as axis is the `primary` pinned component with the harness repository as `benchmark` identity |
| Google Benchmark | `skipped` and `error_occurred` are two field pairs; `cv` and `RMS` are percentage rows; complexity rows are family-level; counter flags, timing mode, warmup, and interleaving are invisible in the JSON | §6.1 table |
| pytest-benchmark | errored and skipped tests are absent from the export; pedantic mode and warmup performed are not exported; `commit_info.id` may be `"unversioned"` | accounting by the driving half (§5); sentinels never become revisions (§4.5) |
| JMH | `scoreError` serializes as the string `"NaN"` below three iterations; sample mode reports histograms, not scalars; secondary `rawData` is ragged | §6.4 |
| cargo-criterion | iteration counts vary per sample; `typical` is an alias; the confidence level is not in the message; `change` is a verdict in the measurement stream | §4.4, §6.5 |
| BenchmarkDotNet | `Result` rows are overhead-subtracted and outlier-filtered; the brief export has no measurements; job settings are not exported | §4.4, §5, §6.6 |

## 9. Boundaries

- **Not the runner:** does not build, prepare environments, or choose what runs.
- **Not the store:** computes no fingerprints, no series, no continuity; the ingest object it emits carries reported coordinates only.
- **Not the comparator:** emits no verdicts and derives no compounds.
- **Not an importer:** importers reuse the translating half on historical exports, adding the migration contract's thin-identity bookkeeping (schema §6); the adapter itself handles one harness's live output.

## 10. Open questions

1. Should `parameter_rules` live in the work order, in project configuration, or beside the benchmark suite in the subject repository? The last keeps rules versioned with the names they parse.
2. When a harness reports an aggregate the schema types differently from the harness's own definition, such as Google Benchmark's `cv`, is a `statistic` with the harness's name sufficient, or does the schema need a coefficient-of-variation summary type?
3. Does the driving half own the per-attempt time limit, or is that an environment-policy setting the runner enforces around any adapter?
4. How much of the context document is a formal contract artifact like the work order, versus a set of named arguments to the translating function? A formal document makes file-based translation replayable; arguments are simpler for the runner.
5. Where are context collectors (§5.1) registered: in the work order, in project configuration, or beside the benchmark suite? The last versions them with the code they inspect, and lets a pull request change what runs with the harness's privileges.
