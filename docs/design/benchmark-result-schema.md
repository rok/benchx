# Benchmark Measurement Result Schema and Migration Contract

**Status:** Minimal draft incorporating source, metrology, and design-partner review<br>
**Companion to:** *A Continuous Benchmarking Framework: Benchmark Result Definition and Storage Schema*<br>
**Author:** Rok Mihevc<br>
**Review date:** 2026-09-11

## 1. Purpose

This document defines the minimum model needed to ingest, compare, and migrate computing benchmark results without inventing statistical meaning. Detection, alerts, thresholds, scheduling, and run lifecycle are out of scope.

> A **measurement result** records the evidence from one measurement attempt for one quantity and one workload variant, together with its conditions and provenance. It holds individual repeated measurements as observations when the producer provides them; an aggregate-only result is valid.

One attempt may report several quantities. CPU time, GPU time, peak memory, and a correctness metric are separate scalar results with separate units, joined by a shared `attempt_key`. A retry is a new attempt with a new key.

> **Reported coordinates** are the facts a producer reports about what was measured and under which conditions: project, designated source, benchmark identity, workload variant, subject, quantity, comparison context, environment, and optional resource selection. They exclude the designated source revision, which is the history axis, and all provenance such as attempt/run keys and timestamps.

> **Comparison identity** is the projection of reported coordinates that project policy requires to match before two estimates are points in the same history. Producers report coordinates; they never declare identity or series membership.

> A **series** is one comparison identity projected through one estimator and followed across revisions of the designated subject source:
>
> **policy(reported coordinates) × estimator**

The estimator is a projection as well: one observation batch feeds a mean series and a median series without being stored twice (§4.5). The server fingerprints reported coordinates for audit, applies a versioned identity policy, and materializes series as rebuildable indexes (§4.3).

Two sources appear on every result. The top-level `source`/`revision` identify the subject component whose revisions form the history axis. `benchmark` identifies the code that defined and executed the workload; its exact revision is a reported coordinate that policy normally maps to a declared benchmark version or an audited continuity mapping rather than splitting history on every benchmark commit. A composite subject such as Arrow–NumPy interoperability names every component, designates one as the axis, and pins the others (§4.2).

Conditions intentionally allowed to vary, such as kernel or glibc version, are recorded per result as **observed context**. They annotate history without splitting it (§4.2).

For example, one series could track:

- project: Apache Arrow benchmarks; subject/source: Apache Arrow from `https://github.com/apache/arrow`;
- workload variant: Parquet read with Snappy compression;
- quantity: wall time in seconds;
- estimator: mean;
- subject configuration: release build with Clang 18;
- benchmark identity: the suite source/revision;
- comparison context: protocol version, Python 3.12, and the warmup/calibration strategy;
- environment: runner `bench-01` with a specified CPU and core policy; resource selection: absent, or a GPU UUID/device index for a per-device result.

Each subject revision contributes zero or more results, producing the history shown in a benchmark chart. Under this policy, changing a workload parameter, quantity, comparison-context value, or environment yields a different series; a different estimator yields a different series over the same coordinates; changing only the attempt/run key, timestamp, kernel, or glibc version does not.

The common operations are to find a series, order its results by revision, plot estimates, inspect observation batches, group an attempt's quantities, and trace a result to its producer. The indexed core is therefore scalar; richer data remains representable without first-class tables.

## 2. Vocabulary

| Term | Meaning here |
|---|---|
| **Run** | Orchestration-level grouping created by a scheduler, CLI, CI job, or similar work-order author. |
| **Attempt** | One execution request and outcome for one workload variant; it may complete, fail, or be skipped. A retry is a new attempt. |
| **Workload** | Named benchmark operation before its parameter domain is expanded. |
| **Workload variant** | A workload plus one resolved parameter assignment. |
| **Subject** | Implementation or system under test. It may contain several named components; one source is the revision axis. |
| **Quantity** | Named scalar output with a canonical unit, such as `wall-time` in `s` or `peak-rss` in `By`. An open, project-extensible vocabulary (§4.4). Canonical units use UCUM when representable. |
| **Estimator** | Rule producing a scalar estimate, such as mean, median, minimum, slope, a percentile, a function of several input quantities, or a source-defined value. Selected by policy as a series projection; reported only inside estimate summaries, never as a coordinate. |
| **Reported coordinates** | Producer-reported facts describing what was measured and under which conditions, fingerprinted before any policy is applied. |
| **Comparison identity** | Policy projection of reported coordinates that must match for comparison. |
| **Series** | Derived comparison-time construct: one comparison identity × one estimator under one identity-policy schema. Materialized as an index; never declared by producers. |
| **Observation** | One measured value produced by a repetition after declared normalization. |
| **Observation batch** | Observations of one quantity from one attempt. Three repetitions producing 1.0 ms, 1.1 ms, and 1.0 ms are three observations in one batch. |
| **Estimate** | Scalar used for plots and analysis; not a known “true value.” Producer estimates are typed summaries on the immutable result; derived estimates are series points. |
| **Statistic** | Numeric summary computed from observations, such as a mean, median, percentile, or standard deviation. |
| **Precision statistic** | Statistic describing observation dispersion, such as standard deviation, MAD, or IQR. |
| **Measurement uncertainty** | Uncertainty associated with an estimate. It is not synonymous with error or observation spread. |
| **Environment** | Host or allocation shared by an attempt's results, especially runner and hardware identity. |

In metrology, the quantity intended for a workload variant at a revision is the **measurand**; it needs no database entity here. Use `accuracy`, `precision`, `error`, `bias`, `confidence interval`, and `coverage interval` only with their defined meanings, and preserve source terminology when its exact meaning is unknown.

## 3. Design rules

1. **Producers report facts; policy derives identity.** A result carries reported coordinates, never a comparison identity or series identifier (§4.3).
2. **The designated subject revision is the series axis.** Ingest time is not historical order; dirty working-tree state is a per-result flag, never a revision property (§4.1).
3. **One result contains one quantity and unit.** A multi-output attempt emits several results joined by `attempt_key`; tuple outputs are split into named scalar quantities.
4. **Observed context never splits history on its own.** Promotion into identity requires a new mapping and identity-policy schema (§4.2).
5. **Environment and selected resource are explicit.** Environment identifies the shared host; optional resource selection identifies the CPU set, GPU, or partition one result applies to.
6. **Observations are preferred, not required.** Aggregate-only history remains valid and is marked producer-supplied.
7. **Summaries are typed.** Estimates, statistics, uncertainty, intervals, and opaque source bounds remain distinct entries (§5.3).
8. **Canonical units are interoperable.** Use UCUM case-sensitive units when representable, normalize values before storage, and keep the original unit in provenance.
9. **Ingestion is idempotent and auditable.** Producer identity is stable and namespaced; its software version is not part of the idempotency key (§5.4).
10. **Grouping keys are provenance.** The run author defines `run_key`; the executor defines a namespace-qualified `attempt_key`; neither enters identity.
11. **Decision policy is separate.** Direction, thresholds, guard bands, correctness verdicts, and alerts never enter identity or imply a verdict.
12. **The quantity vocabulary is open.** Adding a quantity is configuration, not a schema change; a quantity's meaning and unit are immutable once used (§4.4).

## 4. Minimal schema

### 4.1 Core tables

| Table | One row represents | Key or invariant |
|---|---|---|
| `project` | namespace for project-defined names and policy | unique project key |
| `source` | versioned code or data source, usually a repository | unique `(project_id, canonical_uri)` |
| `workload_variant` | workload plus one resolved parameter assignment | unique `(project_id, name, parameters)` |
| `quantity` | named scalar output with canonical unit (UCUM unit when representable) and descriptive metadata (§4.4) | unique `(project_id, name)`; immutable after use |
| `environment` | host/allocation identity plus descriptive metadata | unique `(identity_schema, fingerprint)` |
| `revision` | source revision and optional native order metadata | unique `(source_id, revision_key)` |
| `series` | derived index: one comparison identity × one estimator under one identity-policy schema | unique `series_fingerprint`; rebuildable |
| `series_point` | one result projected into one series, with its estimate | unique `(series_fingerprint, producer, ingest_key)`; rebuildable |
| `benchmark_result` | immutable producer record for one attempt × one quantity | unique `(producer, ingest_key)`; indexed by `reported_coordinates_fingerprint` |

`workload_variant.parameters` is a canonical JSON object holding one concrete assignment. A workload declared with `size=[10, 100, 1000]` yields three variants; a parameter value may itself be an array, such as a matrix shape, and the benchmark definition resolves the distinction before ingestion.

`source` and `revision` serve both subject and benchmark code. A revision key has no intrinsic order: history queries take ancestry from the source repository or an auxiliary revision catalog keyed by `(source_id, revision_key)`; without either, results stay queryable but revision order and ancestor-based baselines are unavailable. Parent hashes are not copied into results.

A `revision` row is keyed by the clean VCS identifier. Whether the measured checkout had uncommitted changes is a fact about the result: `subject_dirty`, `benchmark_dirty`, and an optional patch digest live in provenance, so a clean and a dirty result at the same commit share a revision row. Detectors exclude dirty results by default because the revision key alone does not identify the measured code.

`benchmark_result` stores coordinates exactly as reported plus their fingerprint, `attempt_key`, the outcome, observed context, observation batch, producer summaries, procedure, quality, and provenance as validated JSON. All of it is immutable after ingest. Promote a JSON structure to a child table only when a concrete query, size, or integrity requirement justifies it. No core tables exist for estimator, unit, procedure, run/attempt, observation, interval, uncertainty component, covariance, revision order, or aliases; estimator and unit vocabularies are configuration.

`series` and `series_point` are materialized indexes. The server applies the identity policy to reported coordinates, creates a series per projected identity and estimator, and a point per eligible result. Rebuilding under one policy schema never deletes indexes built under another. Stable annotations and external references use `series_fingerprint`, not a row ID.

A composite subject keeps the axis explicit and pins every non-primary component:

```json
{
  "name": "arrow-numpy-interop",
  "components": [
    {"role": "primary"},
    {"role": "numpy", "source": "https://github.com/numpy/numpy", "revision": "v2.3.0"}
  ]
}
```

### 4.2 Field placement

| Destination | Put here | Examples |
|---|---|---|
| **Workload-variant parameters** | Resolved controlled workload/input | size, compression, dataset, scenario |
| **Subject descriptor** | What is under test: components, roles, pinned non-axis revisions, build/configuration | Arrow–NumPy roles, build type, compiler/flags, JIT/AOT mode, backend |
| **Benchmark identity** | Exact code that defined/executed the workload | source URI, revision |
| **Comparison context** | How the subject is exercised and measured; intended settings | protocol version, host runtime such as Python version, warmup/GC/calibration policy, adaptive vs. pedantic timing, timer, CUDA events vs. synchronization, cache-clearing policy |
| **Environment identity** | Host or allocation shared by an attempt | runner, CPU model, available accelerators, memory, cluster shape |
| **Resource selection** | Optional resource one result applies to | CPU/core set, GPU UUID/device index, accelerator partition |
| **Observed context** | Conditions allowed to vary within a series | kernel, glibc, microcode, image digest, load, temperature |
| **Result procedure** | Realized batch-wide acquisition details | repetitions completed, inner iterations selected, warmups performed, durations, caches actually cleared |
| **Provenance** | Audit metadata | run/attempt/batch keys, dirty flags and patch digest, CI link, logs, runner software, derivation inputs, source payload |

Three rules resolve most cases:

- **Subject versus measurement.** A setting that changes the artifact under test belongs in the subject descriptor; a setting that changes how it is exercised or measured belongs in comparison context. Both are coordinates; the split exists for readability and adapter consistency, and a field goes in exactly one.
- **Intended versus realized.** An adaptive timer's minimum-duration rule is comparison context; the loop count it chose is procedure. A requested cache reset is comparison context; whether it ran is procedure. Per-observation ordinal, group, pair, and inclusion data belongs on structured observations, not in procedure.
- **Identity versus annotation.** A timer, harness, probe, or data-reduction version goes in comparison context if its change must split history, observed context if it should only annotate, and provenance if audit-only. A project that later needs an observed field to match promotes it into reported coordinates through a new mapping version and identity-policy schema; producers do not move fields on their own.

The top-level `source` is the authoritative axis. The subject component with role `primary` may omit its `source`; if present it must match, and a mismatch is an identity violation (§5.4). Non-primary components carry a source URI and pinned revision as fixed coordinates.

A runner-level **probe** maps to a quantity plus the instrumentation used to acquire it: `GPUTimeProbe` might yield `gpu-time` via CUDA events, `OSSMemoryProbe` yield `peak-rss` via a named OS counter. Probe names are not a schema vocabulary.

### 4.3 Fingerprints

The **reported-coordinate fingerprint** preserves the complete tuple before any policy: top-level project/source, the exact `benchmark` identity, and the `coordinates` object of §5.2. It never contains row IDs, an estimator, the axis revision, or attempt/run keys.

```text
reported_coordinates_fingerprint = SHA-256("benchmark-reported-coordinates-v1\0" + JCS(reported_coordinates))
```

A project's **identity policy** projects and normalizes reported coordinates into a comparison-identity object, for example by normalizing equivalent source URIs, mapping exact benchmark revisions to declared versions, or omitting a coordinate it allows to vary. The policy carries an `identity_schema` that changes whenever projection semantics or continuity mappings change; an operational release that yields the same schema does not split history.

```text
comparison_fingerprint = SHA-256("benchmark-comparison-v1\0" + identity_schema + "\0" + JCS(comparison_identity))
estimator_fingerprint  = SHA-256("benchmark-estimator-v1\0" + JCS(estimator))
series_fingerprint     = SHA-256("benchmark-series-v6\0" + comparison_fingerprint + "\0" + estimator_fingerprint)
```

`JCS` is RFC 8785 canonical JSON. The server computes all fingerprints; canonical source URIs, number/string normalization, omitted values, estimator method versions, and identity schema definitions are part of the contract.

### 4.4 Quantity vocabulary

Quantities are an **open vocabulary**: wall time is not privileged, and the schema never enumerates what may be measured. CPU, GPU, and wall time; three distinct memory semantics; hardware counters; throughput; energy; binary size; quality scores are all ordinary quantities. Appendix A gives non-normative examples.

A quantity declaration carries:

- **`name`**, stable within the project and immutable once used. Distinct semantics need distinct names: bytes allocated, returned-object size, and peak RSS are three quantities, never one `memory`.
- **`unit`**, the canonical UCUM unit (rule 8). Counts are `1`; rates are unit-per-time such as `By/s`. Synthetic units are named as what they are: a simulator's weighted cycle estimate is `estimated-cycles` in `1`, never seconds.
- **`direction`** *(optional)*: `lower-is-better` or `higher-is-better`. Recorded because producers know it; excluded from identity and verdicts (rule 11).
- **`deterministic`** *(optional)*: repetition under fixed conditions reproduces the value, as with simulated instruction counts or binary size. One observation is then complete evidence, not a weak sample.

Percentiles are estimators, not quantities: tracked p99 latency is quantity `latency` with estimator `p99`, one series per percentile. The same physical quantity may be a measurand in one series and observed context in another; name and unit conventions are shared so a value moves between the two without translation.

### 4.5 Estimators and compound outputs

An estimator declaration has a name, method version, optional parameters that can alter the value such as percentile interpolation, and an input level of `observations` or `estimates`. Project policy lists the estimators it materializes. For every result with sufficient observations, the server writes a derived point per server-computable policy estimator; a result with only producer estimates joins only the series of the estimators it reported. Adding an estimator to policy later creates points for results with observations and never rewrites a stored result.

A **compound estimator** additionally declares semantic input roles and quantities, which enter `estimator_fingerprint`. A separate derivation-provenance object maps roles to stable `(producer, ingest_key)` input references, which do not enter identity. `attempt_key` locates candidate siblings; explicit references remove ambiguity when an attempt holds several results for a quantity. Paired observations carry matching group/ordinal or pair keys.

```json
{
  "estimator": {
    "name": "max",
    "method_version": "benchx/max/v1",
    "input_level": "estimates",
    "inputs": [{"role": "cpu", "quantity": "cpu-time"}, {"role": "gpu", "quantity": "gpu-time"}]
  },
  "derivation": {
    "inputs": [
      {"role": "cpu", "result": {"producer": "example.org/adapter", "ingest_key": "ci-1234:parquet-read/snappy:cpu-time"}},
      {"role": "gpu", "result": {"producer": "example.org/adapter", "ingest_key": "ci-1234:parquet-read/snappy:gpu-time"}}
    ]
  }
}
```

A compound result is an ordinary result for its own quantity, emitted either by the producer at measurement time or later by a server or analysis component acting as a producer. Both are new immutable results under the original `attempt_key`, carry `source = producer` summaries and derivation provenance, include observations only when paired input observations support them, and never modify their inputs. The two routes land in the same series exactly when output coordinates and the full versioned estimator declaration are equal. Attempt integrity (§5.3) guarantees the inputs share subject revision, benchmark revision, and host environment.

The indexed contract remains scalar: `median([cpu_times, gpu_times])` emits one `cpu-time` and one `gpu-time` result rather than a tuple. Vectors, covariance, and other multidimensional evidence remain artifacts (§7).

## 5. Result contract

### 5.1 Fields and statuses

| Group | Fields |
|---|---|
| **Identity facts** | reported project/source, exact benchmark identity, `coordinates`, `reported_coordinates_fingerprint`, subject `revision_id` |
| **Attempt grouping** | `attempt_key` |
| **Outcome** | `status`, optional reason, optional quantitative constraint |
| **Observed context** | optional immutable condition snapshot |
| **Producer evidence** | optional observation batch and immutable typed summaries |
| **Method** | optional realized procedure JSON |
| **Provenance** | producer/version, ingest/native/run/batch keys, derivation inputs, mapping version, timestamps, payload URI/checksum |
| **Quality** | immutable producer validation and warnings; store-side quarantine/exclusion is separate state |

Derived `series_point` rows live outside the result. Statuses are:

- `success`: a usable observation batch or at least one usable producer estimate;
- `partial`: the same evidence plus a reported partial failure and reason;
- `censored`: only a lower, upper, or interval constraint is known, such as `runtime > 60 s`;
- `error`: no usable estimate or constraint;
- `skipped`: the harness explicitly skipped this known workload variant.

Absence of a row means the variant was not reported. Detectors exclude partial, censored, error, skipped, quarantined, and dirty results by default.

### 5.2 Example ingest object

```json
{
  "schema_version": 5,
  "producer": {"name": "example.org/benchmark-adapter", "version": "4.0", "mapping_version": "native-to-benchx/v5"},
  "ingest_key": "ci-1234:parquet-read/snappy:wall-time",
  "attempt_key": "ci.example.org/runs/ci-1234/attempts/parquet-read-snappy-1",
  "project": "arrow",
  "source": {"uri": "https://github.com/apache/arrow", "type": "git"},
  "revision": {"key": "02addad..."},
  "benchmark": {
    "source": {"uri": "https://github.com/example/arrow-benchmarks", "type": "git"},
    "revision": {"key": "92ef3aa..."}
  },
  "coordinates": {
    "workload": {"name": "parquet-read", "parameters": {"compression": "snappy"}},
    "subject": {
      "name": "apache-arrow",
      "components": [{"role": "primary"}],
      "configuration": {"build_type": "release", "compiler": "clang-18"}
    },
    "quantity": {"name": "wall-time", "unit": "s"},
    "comparison_context": {
      "python": "3.12",
      "protocol": {
        "name": "benchmark-time",
        "version": "v1",
        "timer": "perf_counter",
        "warmup": {"mode": "time", "seconds": 1},
        "calibration": {"mode": "adaptive", "minimum_sample_seconds": 0.01},
        "filesystem_cache": "unchanged"
      }
    },
    "environment": {
      "schema": "machine/v1",
      "identity": {"runner": "bench-01", "cpu": "AMD EPYC 7R13", "cores": 8}
    }
  },
  "measurement": {
    "status": "success",
    "observations": [0.0371, 0.0364, 0.0363, 0.0370, 0.0368],
    "summaries": [
      {
        "type": "estimate",
        "estimator": {"name": "mean", "method_version": "benchx/mean/v1", "input_level": "observations"},
        "value": 0.03672,
        "source": "producer"
      },
      {
        "type": "statistic",
        "name": "sample_standard_deviation",
        "value": 0.0003564,
        "method": "n-1",
        "source": "producer"
      },
      {
        "type": "confidence_interval",
        "statistic": "mean",
        "level": 0.95,
        "lower": 0.03628,
        "upper": 0.03716,
        "method": "student-t",
        "source": "producer"
      }
    ]
  },
  "observed_context": {"kernel": "6.8.0-31-generic", "glibc": "2.39"},
  "procedure": {"inner_iterations": 100, "attempted_repetitions": 5, "completed_repetitions": 5, "warmups_performed": 1},
  "provenance": {
    "run_key": "ci.example.org/runs/ci-1234",
    "started_at": "2026-07-18T09:12:44Z",
    "subject_dirty": false,
    "benchmark_dirty": true,
    "benchmark_patch_sha256": "aaaa...",
    "runner": {"name": "example-runner", "version": "2.1"},
    "source_payload_sha256": "bbbb..."
  },
  "quality": {"warnings": ["dirty-benchmark-tree"]}
}
```

After accepting it, the server may materialize points such as the following. They are not fields on the result:

```json
{
  "series_fingerprint": "cccc...",
  "result": {"producer": "example.org/benchmark-adapter", "ingest_key": "ci-1234:parquet-read/snappy:wall-time"},
  "estimator": {"name": "median", "method_version": "benchx/median/v1", "input_level": "observations"},
  "value": 0.0368,
  "source": "derived"
}
```

### 5.3 Semantics and integrity

**Evidence**

- `summaries` is an extensible producer-evidence list with types `estimate`, `statistic`, `confidence_interval`, `coverage_interval`, `source_bounds`, `standard_uncertainty`, and `expanded_uncertainty`. Each entry records the statistic addressed, source, method, and level or factor when applicable. Values use the quantity's canonical unit unless explicitly dimensionless.
- A producer `estimate` has a finite value, a complete estimator declaration, and `source = producer`; at most one per estimator per result.
- Observations are finite values in the quantity's unit after declared normalization. A numeric array is the common batch; structured observations carry per-observation ordinal, group, pair, inclusion, or exclusion data.
- Observation standard deviation is a precision statistic, not automatically the uncertainty of a mean or median. Unknown bounds stay `source_bounds`; labels such as `stat`, `sys`, `range`, or `error` keep source semantics.
- For a deterministic quantity (§4.4), one observation is complete evidence and must not be treated as an undersampled distribution.
- `success` and `partial` require a non-empty usable batch or at least one finite producer estimate. `censored` requires a constraint with kind (`lower_bound`, `upper_bound`, `interval`), finite bounds, inclusivity, and cause. `error` and `skipped` carry none of these. Iteration and repetition counts are positive, durations non-negative, and interval lower bounds never exceed upper bounds.

**Derived projections**

- A result contributes to a series when it has a producer estimate for that estimator or enough observations for the server to derive one. The value is stored in `series_point`; a producer estimate for the same estimator stays unchanged, and a material discrepancy is recorded as a point warning.
- Producers never send a comparison fingerprint, series identifier, series point, or identity-policy schema. Reported coordinates and producer evidence are immutable; derived indexes change only by adding or rebuilding policy-versioned materializations, and schemas are retained side by side.
- `observed_context` is excluded from reported coordinates and never enters identity; analyses may annotate, filter, or stratify by it.

**Attempts and keys**

- A harness invocation reporting several quantities yields one result per quantity sharing `attempt_key`; corresponding observations share group/ordinal or pair keys.
- **Attempt integrity.** Results sharing an `attempt_key` must agree on project, designated source, subject revision, benchmark revision, dirty flags, workload variant, subject descriptor, environment identity, and `run_key`. They may differ in quantity, resource selection, and quantity-specific instrumentation. Disagreement with a stored sibling is an *attempt conflict* (§5.4). Resource selection is what lets GPU 0 and GPU 1 results share one host environment.
- `run_key` comes from the run author. The executor creates a globally namespace-qualified `attempt_key`, such as a URI-like key or UUID, and producers preserve or deterministically map it. Neither key enters identity. Identical retries of `(producer, ingest_key)` return the existing result; different payloads conflict.
- An expected ground-truth value belongs to workload/dataset metadata or an artifact; an error norm or mismatch count derived from it is another quantity; a pass/fail verdict is decision policy.
- A result's designated source, workload variant, and quantity belong to one project, and its subject revision refers to its designated source.
- Large observation sets, covariance matrices, profiles, histograms, and similar outputs are external artifacts with media type, URI, and checksum. Migrations retain mapping version and source payload reference.

Physical partitioning and indexes are implementation choices; global idempotency must hold regardless.

### 5.4 Ingest contract

The ingest object (§5.2) is the message; transport is a deployment choice. The litmus test is **file drop**: writing result documents to a directory that is later swept into the store must be a valid delivery path.

- **Acknowledgment means validated and durable.** A positive response promises the result is stored and queryable; the producer may forget it.
- **Entities auto-create; meaning is protected.** First sight of a project, source, workload variant, quantity, or revision creates it, and series and points are materialized without changing the result. A quantity arriving with a different unit is rejected as a unit conflict, enforcing rule 12 at ingest rather than at declaration.
- **No ordering, no deadline.** Results may arrive late, duplicated, or out of order; an offline laptop or weekly batch is valid indefinitely.
- **Batches are transport optimizations.** A multi-result delivery is N independent documents with N outcomes; there is no atomic batch, and `attempt_key` survives any framing.
- **Machine-readable rejection taxonomy.** At minimum *malformed*, *idempotency conflict* (same `(producer, ingest_key)`, different payload), *unit conflict*, *identity violation* (coordinates and revision from different sources, a primary component whose source differs from the top-level source, or a payload carrying a series identifier or fingerprint), *attempt conflict* (§5.3), and *quarantined* (accepted but withheld pending review).

## 6. Migration contract

Each import records whether observations are structured, flat, or absent; whether several quantities share a native attempt; whether benchmark and subject revisions can be distinguished; whether reported coordinates are complete for the identity policy or *thin*; and whether summaries are typed, source-defined, or absent.

*Thin* means the source lacks coordinates the target policy requires. The importer records the missing attributes in provenance rather than inventing defaults, and thin imports are not matched across sources without an approved mapping. An importer preserves a native attempt identifier when its grouping semantics are known and otherwise generates a distinct attempt key per result.

Importers must be idempotent, retain source payload and mapping version, report identity collisions before writing, preserve failures/skips/limits, reject unit conflicts, and use the same mapping rules as live adapters. They must not parse parameters from names without project rules or copy source-local fingerprints.

### 6.1 Tool mapping summary

| Source | Core mapping | Important caveat |
|---|---|---|
| **ASV** | hardware → environment; OS → observed context; environment/dependencies/build → subject descriptor or comparison context by semantics; benchmark + parameters → workload variant; result → **median estimate**; samples → observations; CI99 → median confidence interval | `null` is failed and `NaN` is skipped. Preserve exact benchmark version as benchmark identity; map its declared semantic version conservatively into comparison context. |
| **Conbench** | native case → workload variant; hardware → environment; source → designated source/revision; context fields split among subject, comparison context, and observed context; data → observations; times → procedure | Derive quantity and estimator; do not copy `history_fingerprint`. Use the source deployment's configured summary policy. |
| **Bencher** | Project/Testbed/Benchmark/Measure → project/environment/workload variant/quantity; Metric → source-defined estimate; Report → provenance | Bounds are adapter-defined. Keep opaque bounds as `source_bounds`; threshold direction is decision policy. |
| **Codespeed** | Project/source/revision → project and designated axis; Executable → subject descriptor; Benchmark → workload variant + quantity; Environment → environment/observed context; Result aggregates → summaries | `Benchmark.data_type` selects mean or median. Snapshot mutable unit definitions. |
| **LNT** | suite → project; Machine fields split among subject, environment, comparison context, and observed context; Test → workload variant; metric → quantity; list/scalar → observations/estimate; Run → provenance | Preserve native order, status/hash, and source metadata. Opaque machine identity is thin. |
| **Nyrkiö** | test path → workload variant; metric name/unit → quantity; value → source-defined estimate; source attributes → revision | Preserve per-metric direction as source decision metadata; conflicts require review. |
| **github-action-benchmark** | suite/project; name → workload variant; tool/unit → quantity; value → source-defined estimate; commit/date → revision/provenance | Interpret `range` by adapter version; otherwise retain it as an opaque summary. History may be truncated. |
| **OpenTelemetry Benchmarks** | scenario ID/workload → workload variant/comparison context; tracked package version → revision; `name`/`unit`/`value` → quantity/estimate; `extra` → environment/observed context/provenance | Its current output is github-action-benchmark's `{name, unit, value, extra}` format. Estimator and direction come from the scenario document; observations and uncertainty are absent. |
| **rustc-perf** | artifact → revision; pstat dimensions → workload variant/comparison context/quantity; collection → run/attempt/observation grouping | Group compatible collection rows into observations. Environment is thin unless collector metadata can be joined. |
| **CodSpeed** | aggregate-only source estimate | No reviewed public export schema supports a migration contract. |

### 6.2 Live harness adapters

- **Google Benchmark:** iteration rows become observations; aggregate rows remain producer summaries; secondary metrics become sibling results sharing `attempt_key`; split mixed context into comparison context, environment, observed context, procedure, and provenance.
- **pytest-benchmark:** round data becomes observations; requested warmup/timing strategy goes in comparison context, realized rounds, iterations, and warmups in procedure.
- **JMH:** preserve fork grouping; map `scoreConfidence` as a 99.9% confidence interval; mode and secondary metrics define quantity/estimator semantics.
- **cargo-criterion:** pair `iteration_count` with `measured_values`; retain typical/mean/median/MAD/slope estimates and bounds.
- **BenchmarkDotNet:** detailed measurements become observations; retain parameters, job, host, statistics, confidence interval, and percentiles with source semantics.

### 6.3 OpenTelemetry interoperability

OpenTelemetry defines no general benchmark-result convention; its benchmark repository reports through github-action-benchmark, and OTLP Metrics is a generic time-series transport. Compatibility is therefore an adapter concern.

For OTLP export, map environment to `Resource`, producer name/version to `Scope`, quantity/unit to a `Metric`, the exported `series_point` estimate to a `Gauge` point, and project/source/workload variant/comparison context/resource selection/revision/estimator to point attributes. Export only usable scalar estimates: OTLP has no lossless representation for observations, source bounds, intervals, errors/skips, or idempotency keys, so the result store remains the system of record. Because OTLP treats attributes as stream identity, do not export observed context as metric attributes when one continuous downstream series is required; put it on a linked log/span instead. When ingesting OpenTelemetry CI/CD metadata, map `vcs.repository.url.full` to source URI, `vcs.ref.head.revision` to revision key, `cicd.pipeline.run.id` to run key, and `cicd.worker.id` to environment identity, preserving the original attributes and schema URL in provenance.

## 7. Scope and simplifications

The following do not justify core tables for current use cases:

- **Measurement procedure, measuring system, and model:** covered by comparison context, observed context, procedure, and provenance.
- **Runs/events:** `run_key`, `attempt_key`, and `batch_key` group results without a transactional parent.
- **Observation rows, uncertainty budgets, covariance, and multidimensional data:** inline typed JSON for the common case; artifacts for the large or specialist case.
- **Unit and estimator tables:** the quantity stores its unit; policy lists the estimators it projects.
- **Revision graph and alias tables:** source integrations or an optional revision catalog provide topology; audited display mappings provide aliases.

A structure becomes first-class only when it participates in comparison identity, referential integrity, or frequent indexed queries. This keeps the core at nine tables. The store also excludes alert policy, CI orchestration, source-code hashes as workload-variant identity, source-local fingerprints, large blobs, and branch/fork metadata as revision properties.

## 8. Reviewed sources

### Measurement science and experimental physics

- [JCGM 200:2012, *International Vocabulary of Metrology (VIM)*](https://www.bipm.org/documents/20126/2071204/JCGM_200_2012.pdf)
- [JCGM 100:2008, *Guide to the Expression of Uncertainty in Measurement (GUM)*](https://www.bipm.org/documents/20126/2071204/JCGM_100_2008_E.pdf)
- [JCGM 106:2012, *The Role of Measurement Uncertainty in Conformity Assessment*](https://www.bipm.org/documents/20126/2071204/JCGM_106_2012_E.pdf)
- [BIPM, *SI Brochure*, 9th edition](https://www.bipm.org/documents/20126/41483022/SI-Brochure-9.pdf)
- [HEPData data format, pinned `e54de2d`](https://github.com/HEPData/hepdata-submission/blob/e54de2d5b349f92ca4eadc5722ea99c7273d24ee/docs/data_yaml.rst)
- OpenTelemetry: [performance benchmark guidance](https://github.com/open-telemetry/opentelemetry-specification/blob/3a145b2f860d5ad94a393bc0879b309d5b8153be/specification/performance-benchmark.md), [Metrics data model](https://github.com/open-telemetry/opentelemetry-specification/blob/3a145b2f860d5ad94a393bc0879b309d5b8153be/specification/metrics/data-model.md), and [CI/CD semantic conventions](https://github.com/open-telemetry/semantic-conventions/blob/baadd5669ac53133501de100c020b4fd06533f12/docs/resource/cicd.md)

### Benchmark systems and harnesses

- [ASV result format (`7032df7`)](https://github.com/airspeed-velocity/asv/blob/7032df701a969fa61f4c819ce9f71fb2e66f5a62/docs/source/dev.rst) and [statistics (`01d4a25`)](https://github.com/airspeed-velocity/asv_runner/blob/01d4a2556932ca63e8d7df6536551c6107397e66/asv_runner/statistics.py)
- [Conbench (`3af4a55`)](https://github.com/conbench/conbench/blob/3af4a55206ad3918762cc8dd7d3012eadbe96a54/conbench/entities/benchmark_result.py), [Bencher (`d2895af`)](https://github.com/bencherdev/bencher/tree/d2895af8c867c83b8fe766a6b84d8ccd4df5c315/services/console/src/content), and [Codespeed (`263860b`)](https://github.com/tobami/codespeed/blob/263860bc298fd970c8466b3161de386582e4f801/codespeed/models.py)
- [LNT (`0e08c62`)](https://github.com/llvm/llvm-lnt/tree/0e08c627cc4804279b9439dd8ba32959cf3872f8/docs), [Nyrkiö (`5b63790`)](https://github.com/nyrkio/nyrkio/blob/5b6379026e3cb28807dd8402f4d82ce2996700db/backend/api/model.py), [github-action-benchmark (`86d8bcf`)](https://github.com/benchmark-action/github-action-benchmark/tree/86d8bcf4dc945c81ee3547d15499abafc89a57b5/src), and [rustc-perf (`3bbef83`)](https://github.com/rust-lang/rustc-perf/tree/3bbef83aea7206205fe38d7612b0a0cd6cd75ba2/database)
- [CodSpeed CPU Simulation](https://codspeed.io/docs/instruments/cpu)
- OpenTelemetry Benchmarks: [S001 scenario](https://github.com/open-telemetry/opentelemetry-benchmarks/blob/3c826853b4964593b2cdb3ffdbb84a124ca8e706/scenarios/S001-counter-increment-api-only.md) and [harness reporting format](https://github.com/open-telemetry/opentelemetry-benchmarks/blob/3c826853b4964593b2cdb3ffdbb84a124ca8e706/harnesses/README.md)
- Harnesses: [Google Benchmark (`8b66b54`)](https://github.com/google/benchmark/blob/8b66b54f7e1bf6b25390dca1dea3f18a40e607f9/docs/user_guide.md), [pytest-benchmark (`47d66c8`)](https://github.com/ionelmc/pytest-benchmark/tree/47d66c88b84b5b11cc78e465cfc655d0a02de740), [JMH (`a194eea`)](https://github.com/openjdk/jmh/blob/a194eead0136bb66e5e59e4fdb2e18543e730929/jmh-core/src/main/java/org/openjdk/jmh/results/format/JSONResultFormat.java), [Criterion (`3dbc6c6`)](https://github.com/bheisler/criterion.rs/blob/3dbc6c618acb48885066422d81d50729aa17b2b7/book/src/cargo_criterion/external_tools.md), and [BenchmarkDotNet (`2365829`)](https://github.com/dotnet/BenchmarkDotNet/blob/2365829b82d95843e561f9ef666f4e9e86761d38/docs/articles/samples/IntroExportJson.md)

The pinned primary-source links above are the review record included with this draft.

## Appendix A: Example quantities (non-normative)

Illustrations of the open vocabulary (§4.4), with canonical UCUM units. None of these names is required; projects declare what they measure.

| Name | Unit | Meaning | Notes |
|---|---|---|---|
| `wall-time` | `s` | elapsed real time | universal |
| `cpu-time` | `s` | process CPU time | Google Benchmark default; hyperfine user/sys |
| `gpu-time` | `s` | device-side time, synchronized | cupyx, torch benchmarks |
| `latency` | `s` | per-request time; percentiles via estimators | vLLM, MLPerf server scenarios |
| `time-to-first-token` | `s` | streaming first-response time | LLM inference |
| `peak-rss` | `By` | peak process resident set size | ASV `peakmem_`, pyperf, rustc-perf `max-rss` |
| `allocated-bytes` | `By` | bytes allocated per operation | JMH GC profiler, BenchmarkDotNet, Go `B/op` |
| `allocations` | `1` | allocation count per operation | Go `allocs/op` |
| `object-size` | `By` | size of a produced object | ASV `mem_` |
| `gpu-peak-memory` | `By` | peak device memory | torch `max_memory_allocated` |
| `instructions` | `1` | retired instructions; deterministic when simulated | rustc-perf default metric |
| `cycles` | `1` | CPU cycles | noisier than instructions |
| `estimated-cycles` | `1` | simulator-weighted cycles (synthetic) | CodSpeed, Cachegrind models |
| `cache-misses` | `1` | cache misses, level named if specific | perf, JMH perfnorm |
| `branch-misses` | `1` | branch mispredictions | perf, BenchmarkDotNet |
| `page-faults` | `1` | page faults | perf, rustc-perf |
| `throughput-bytes` | `By/s` | bytes processed per second | Google Benchmark, criterion |
| `throughput-items` | `1/s` | items/operations per second | ops/s, tokens/s, IOPS |
| `energy` | `J` | energy consumed | RAPL, Scaphandre |
| `power` | `W` | average power draw | SPECpower, mobile benchmarks |
| `cpu-frequency` | `MHz` | observed frequency; often observed context instead | pyperf metadata |
| `temperature` | `Cel` | sensor temperature; often observed context instead | pyperf metadata |
| `binary-size` | `By` | linked artifact size; deterministic | rustc-perf `size:*`, LNT, Chromium |
| `build-time` | `s` | time to build the artifact | LNT, Bencher tutorials |
| `compression-ratio` | `1` | output/input size ratio | zstd, lzbench |
| `score` | `1` | quality metric paired with performance | LNT `score`, MLPerf accuracy |
