# Benchmark Measurement Result Schema and Migration Contract

**Status:** Minimal draft incorporating source, metrology, and design-partner review<br>
**Companion to:** *A Continuous Benchmarking Framework: Benchmark Result Definition and Storage Schema*<br>
**Author:** Rok Mihevc<br>
**Review date:** 2026-09-11

## 1. Purpose

This document defines the minimum model needed to ingest, compare, and migrate computing benchmark results without inventing statistical meaning.

> A **measurement result** records the estimate and evidence from one measurement attempt for one quantity and one concrete workload variant, together with its conditions and provenance. When a producer provides individual repeated measurements, the result holds their values as observations. A result that provides only an aggregate estimate remains valid when the individual observations are unavailable.

One benchmark attempt may report several quantities. CPU time, GPU time, peak memory, and a numeric correctness metric are stored as separate scalar results with separate units, joined by the same namespace-qualified `attempt_key`. A retry is a new attempt and receives a new key.

> **Reported coordinates** are the facts a producer reports about what was measured and under which conditions: benchmark identity, workload, subject, quantity, comparison context, environment, and optional resource selection. They exclude the designated source revision, which is the history axis, and exclude attempt/run IDs, timestamps, and other provenance.

> **Comparison identity** is the projection of reported coordinates that project policy requires to match before two estimates may be treated as points in the same benchmark history. Producers report coordinates; they never declare comparison identity or series membership.

A **series** is a comparison-time construct: one comparison identity, projected through one estimator, followed across revisions of its designated subject source:

> **policy(project × source × benchmark identity × workload variant × subject × quantity × comparison context × environment × resource selection) × estimator**

The producer-reported tuple is fingerprinted on every result for audit and deduplication (§4.3). Project policy then projects those coordinates into comparison identity. The estimator is a further projection: one observation batch may feed a mean series and a median series without being stored twice (§4.5).

The source and revision on the result identify the subject component used as the history axis. The benchmark implementation has its own source/revision identity recorded on every result. Exact benchmark revision is provenance rather than automatic series identity: project policy uses a declared benchmark/protocol version or an audited continuity mapping to decide whether a benchmark change preserves meaning. A composite subject such as Arrow–NumPy interoperability names all components; one source is the series axis and the other component revisions remain fixed subject coordinates.

Potentially influential conditions that are intentionally allowed to vary—such as the kernel or glibc version—are recorded with each result as **observed context**. They remain visible for annotation and analysis without automatically creating a new series. This is a comparison-policy role, not an intrinsic property of a field: a project that requires the kernel to match puts it in comparison context instead.

For example, one series could track:

- project namespace: Apache Arrow benchmarks;
- subject/source: Apache Arrow from `https://github.com/apache/arrow`;
- workload variant: Parquet read with Snappy compression;
- quantity: wall time in seconds;
- estimator: mean;
- subject configuration: release build with Clang 18;
- benchmark identity: the suite source/revision;
- comparison context: benchmark/protocol version, Python 3.12, and the warmup/calibration strategy;
- environment: runner `bench-01` with a specified CPU and core policy.
- resource selection: absent for this CPU measurement, or a GPU UUID/device index for a per-device result.

For a local benchmark directory probing an Arrow checkout, `project` is the chosen benchmark namespace, `benchmark` identifies the directory's source state, and top-level `source`/`revision` identify Arrow. For an Arrow–NumPy interoperability workload, the subject descriptor lists both components and the series designates whichever component is intentionally varied as its revision axis.

Each subject revision may contribute zero or more results to this series, producing the history shown in a benchmark chart. Changing the workload parameters, comparison-relevant benchmark semantics, quantity, a comparison-context value, or environment yields different coordinates and therefore a different series; selecting a different estimator yields a different series over the same coordinates. Changing only the attempt/run key, timestamp, kernel, or glibc version does not under this example's identity policy; the latter two remain attached as observed context.

The common operations are to find a series, order its results by revision when source topology is available, plot its estimates, inspect observation batches, group quantities from one attempt, and trace each result to its producer. The indexed core is therefore scalar; richer data remains representable without requiring first-class tables.

Detection, alerts, thresholds, scheduling, and run lifecycle are out of scope.

## 2. Vocabulary

| Term | Meaning here |
|---|---|
| **Run** | Orchestration-level grouping created by a scheduler, CLI, CI job, or similar work-order author. |
| **Attempt** | One execution request and outcome for one concrete workload variant; it may complete, fail, or be skipped. A retry is a new attempt. |
| **Workload** | Named benchmark operation before its parameter domain is expanded. |
| **Workload variant** | A workload plus one resolved parameter assignment. |
| **Subject** | Implementation or system under test. It may contain several named components, although one source is the revision axis of a series. |
| **Quantity** | Named scalar output and canonical unit, such as `wall-time` in `s` or `peak-rss` in `By`. An open, project-extensible vocabulary (§4.4). Canonical units use UCUM when representable. |
| **Estimator** | Rule producing a scalar estimate from an observation batch, such as mean, median, minimum, slope, a percentile such as `p99`, a function of several input quantities, or a source-defined value. Selected by project policy as a series projection, not reported as a coordinate. |
| **Reported coordinates** | Producer-reported facts describing what was measured and under which conditions. Stored across top-level project/source, `benchmark`, and `coordinates`, then fingerprinted without first applying comparison policy. |
| **Comparison identity** | Projected subset of reported coordinates that must match for comparison. |
| **Series** | Derived comparison-time construct: one comparison-identity fingerprint × one estimator under a versioned identity policy. Materialized as an index for queries; never declared by producers. |
| **Observation** | One measured value produced by a repetition after declared normalization. |
| **Observation batch** | Observations of one quantity collected by one attempt. Three repetitions producing 1.0 ms, 1.1 ms, and 1.0 ms are three observations in one batch. |
| **Estimate** | Scalar used for plots and analysis; it is not a known “true value.” Producer estimates are typed summaries on immutable results; derived estimates are stored as series points. |
| **Statistic** | Numeric summary computed from observations, such as a mean, median, percentile, or standard deviation. A batch may retain many statistics; each series projects the estimate belonging to its estimator. |
| **Precision statistic** | Statistic describing observation dispersion, such as standard deviation, MAD, or IQR. |
| **Measurement uncertainty** | Uncertainty associated with an estimate. It is not synonymous with error or observation spread. |
| **Environment** | Comparison-relevant execution resources, especially runner and hardware identity. |

In metrology, the particular quantity intended for a workload variant at a revision is the **measurand**. It need not be a database entity here.

Use `accuracy`, `precision`, `error`, `bias`, `confidence interval`, and `coverage interval` only with their defined meanings. Preserve source terminology when its exact meaning is unknown.

## 3. Design rules

1. **Producers report facts; policy derives identity.** A result carries reported coordinates and never a comparison identity or series identifier. The server preserves a fingerprint of all reported coordinates, applies a versioned identity policy to project a comparison identity, and combines that identity with an estimator to derive a series. One observation batch may support mean, median, and other projections without being stored twice.
2. **The designated subject revision is the series axis.** Exact benchmark code revision is captured separately on every result. Dirty working-tree state is a per-result flag, never a property of a revision row; ingest time is not historical order.
3. **One result contains one quantity and unit.** A multi-output attempt emits several results joined by a namespace-qualified `attempt_key`. Tuple-valued outputs are split into named scalar quantities.
4. **Observed context does not automatically define a series.** Snapshot potentially relevant changing conditions on each result so analysis can annotate, stratify, or exclude them without fragmenting history. Promotion into identity requires an explicit policy/fingerprint version change.
5. **Environment and selected resource are explicit.** Environment identifies the shared host or allocation. Optional per-result resource selection identifies the CPU set, GPU UUID/device index, or other resource to which that quantity applies. Store non-identity environment facts as observed context.
6. **Observations are preferred, not required.** Aggregate-only history remains valid and is marked producer-supplied.
7. **Summaries are typed.** Per-estimator estimates, other statistics, precision, uncertainty, confidence intervals, coverage intervals, and opaque source bounds remain distinct typed entries.
8. **Canonical units are interoperable.** Use UCUM case-sensitive units when representable, normalize values before storage, and preserve the producer's original unit in provenance.
9. **Ingestion is idempotent and auditable.** Preserve a producer-scoped key, producer/mapping version, native ID, and source payload reference. Producer identity is stable and namespaced; its software version is not part of the idempotency key.
10. **Grouping keys are provenance, not comparison identity.** The run author defines `run_key`; the executor defines a namespace-qualified `attempt_key` per concrete execution, and producers preserve or deterministically map it. Re-ingestion preserves both, while a retry gets a new attempt key.
11. **Decision policy is separate.** Optimization direction, target values, thresholds, guard bands, correctness verdicts, and alerts do not enter result or series identity. A quantity may carry its direction as descriptive metadata (§4.4); it never implies a verdict.
12. **The quantity vocabulary is open.** Adding a quantity is application configuration, not a schema change: it creates new series and touches no existing data. Distinct measurement semantics require distinct quantity names, and a quantity's meaning and unit are immutable once used.

## 4. Minimal schema

### 4.1 Core tables

| Table | One row represents | Key or invariant |
|---|---|---|
| `project` | namespace for project-defined names and policy | unique project key |
| `source` | versioned code or data source, usually a repository | unique `(project_id, canonical_uri)` |
| `workload_variant` | workload plus one resolved parameter assignment | unique `(project_id, name, parameters)` |
| `quantity` | named scalar output with canonical UCUM unit when representable, plus optional descriptive metadata (§4.4) | unique `(project_id, name)`; immutable after use |
| `environment` | explicit host/allocation identity plus descriptive metadata | unique `(identity_schema, fingerprint)` |
| `revision` | source revision and optional native order metadata | unique `(source_id, revision_key)` |
| `series` | derived index row: one comparison identity × one estimator under one identity-policy schema | unique `(comparison_fingerprint, estimator_fingerprint)`; rebuildable from results and retained by policy schema |
| `series_point` | one result projected into one series, with its selected estimate and optional derived summaries | unique `(series_id, result_id)`; rebuildable from immutable results and policy |
| `benchmark_result` | immutable producer record for one attempt × one quantity, with reported coordinates and an optional observation batch | unique `(producer, ingest_key)`; indexed by `reported_coordinates_fingerprint` |

`workload_variant.parameters` is a canonical JSON object containing one concrete parameter assignment. For a workload declared with `size=[10, 100, 1000]`, adapters emit three variants whose `size` values are `10`, `100`, and `1000`. A parameter value may itself be an array, such as a matrix shape; the distinction is resolved by the benchmark definition before result ingestion.

`source` and `revision` are reusable for both benchmark and subject code. A series designates one subject source whose revision is the history axis. Each result also references the exact benchmark source/revision; non-axis subject component revisions are recorded in the subject descriptor. VCS parent hashes are not copied into each result. A revision key, especially a Git hash, has no intrinsic order: history queries obtain ancestry and ordering from the source repository or an auxiliary revision catalog keyed by `(source_id, revision_key)`. Without either, results remain queryable but revision order and ancestor-based baseline selection are unavailable.

A `revision` row is keyed by the clean VCS identifier only. Whether the checkout that was actually measured had uncommitted changes is a fact about the result, so `benchmark_result` stores `subject_dirty` and `benchmark_dirty` flags, plus an optional patch digest, in provenance. Two results at the same commit, one clean and one dirty, therefore share a revision row and differ in provenance. Producers set the flags whenever they can determine them and may include a quality warning. Store-side quarantine/exclusion state remains separate from the immutable result. Automated detection excludes results with a dirty subject or benchmark tree by default because a clean revision key alone does not identify the code that was measured.

`benchmark_result` stores the coordinates exactly as reported—designated source, exact benchmark identity, workload variant, subject descriptor, quantity, comparison-context JSON, environment, and optional resource selection—together with the server-computed `reported_coordinates_fingerprint` (§4.3). The result, its coordinates, observations, and producer summaries are immutable once ingested. A compound subject descriptor may name several components and their roles; the designated source identifies the component whose revisions a series follows.

`series` and `series_point` are materialized indexes, not producer-facing entities. The server applies an identity policy to reported coordinates, creates a series for each projected comparison identity and estimator, and creates a point for each eligible result. When observations support the policy estimator, a point uses the server-derived estimate; otherwise it may use an immutable producer estimate. Server computation never edits or replaces producer evidence. Rebuilding a materialization for one policy schema does not delete series produced under an older schema. Persisted annotations and external references use the series fingerprint and identity-policy schema rather than an ephemeral database row ID.

A composite subject keeps the designated axis explicit and pins every non-primary component, for example:

```json
{
  "name": "arrow-numpy-interop",
  "components": [
    {"role": "primary"},
    {
      "role": "numpy",
      "source": "https://github.com/numpy/numpy",
      "revision": "v2.3.0"
    }
  ]
}
```

`benchmark_result` also stores `attempt_key`, the exact benchmark revision, the outcome, observed context, observation batch, producer-supplied typed summaries, procedure, quality, and provenance as validated JSON. Promote a JSON structure to a child table only when a concrete query, size, or integrity requirement justifies it.

No separate core tables are required for estimator, unit, procedure, measuring system, run/attempt, observation, interval, uncertainty component, covariance, revision order, or aliases. Estimator and unit vocabularies are application configuration.

### 4.2 Field placement

| Destination | Put here | Examples |
|---|---|---|
| **Workload-variant parameters** | Resolved controlled workload/input | size, compression, dataset, scenario |
| **Subject descriptor** | What is under test: named components, their roles and pinned non-axis revisions, and how the artifact was built or configured | Arrow–NumPy component roles, build type, compiler/flags, JIT/AOT mode, backend selection |
| **Benchmark identity on result** | Exact code that defined/executed the workload | source URI, revision |
| **Comparison context** | How the subject is exercised and measured: intended settings whose change must create a series | declared benchmark/protocol version, host runtime such as the Python version, warmup/GC/calibration policy, adaptive vs. pedantic timing, timer/counter, CUDA events vs. synchronization, cache-clearing policy |
| **Environment identity** | Host or allocation shared by results from an attempt | runner, CPU model, available accelerators, memory, cluster shape |
| **Resource selection** | Optional resource to which this result applies | CPU/core set, GPU UUID/device index, accelerator partition |
| **Observed context** | Relevant conditions allowed to vary within a series | kernel, glibc, microcode, image digest, runtime patch, load, temperature |
| **Result procedure** | Realized batch-wide acquisition details and actions | repetitions completed, selected inner iterations, warmups performed, order, durations, caches actually cleared |
| **Provenance** | Audit and descriptive metadata | run/attempt/batch key, subject/benchmark dirty flags and patch digest, CI link, work-order reference, logs, runner software, model/correction notes, artifacts, source payload |

Two placement rules resolve most cases. The first is **subject versus measurement**: a setting that changes the artifact under test—its build, its compiler and flags, its JIT or AOT mode, its selected backend—belongs in the subject descriptor, while a setting that changes how that artifact is exercised or measured—host runtime, protocol, timer, warmup, cache policy—belongs in comparison context. Both are reported coordinates and enter the reported-coordinate fingerprint. Identity policy normally includes them in comparison identity; the placement rule exists primarily for readability and adapter consistency. A field is placed in exactly one of them.

The second is **intended strategy versus realized execution**. For example, an adaptive timer's minimum-duration rule belongs in comparison context, while the loop count it selected belongs in procedure. A requested filesystem-cache reset belongs in comparison context, while whether and how it ran belongs in procedure. Host/allocation identity belongs in environment, the resource measured by one result belongs in resource selection, and audit-only runner software identity belongs in provenance.

Per-observation ordinal, group, pairing, inclusion, and exclusion metadata belongs only on structured observations. `procedure` contains batch-wide acquisition details; it does not duplicate per-observation coordinates.

The top-level `source` is the authoritative designated axis. The subject component with role `primary` may omit its `source`; when present it must equal the top-level source, and a mismatch is rejected as an identity violation (§5.4). Non-primary components carry their own source URI and a pinned revision, which are fixed coordinates rather than history axes.

A runner-level **probe** maps to a quantity plus the protocol/instrumentation used to acquire it. `GPUTimeProbe` might produce `gpu-time` using CUDA events, while `OSSMemoryProbe` produces `peak-rss` using a named OS counter and sampling strategy. Probe class names are not a closed schema vocabulary.

A timer, harness, probe, or data-reduction version needs no separate entity: include it in comparison context if its change must split history, in observed context if it should only annotate history, and in provenance if it is audit-only.

### 4.3 Reported-coordinate, comparison, and series fingerprints

The **reported-coordinate fingerprint** preserves the complete coordinate tuple before policy projection. It is computed from top-level project/source, the exact `benchmark` identity, and the `coordinates` object in §5.2:

```text
reported_coordinates_fingerprint = SHA-256("benchmark-reported-coordinates-v1\0" + RFC-8785-canonical-JSON(reported_coordinates))
```

It never contains database row IDs, an estimator, the subject revision on the designated history axis, or attempt/run keys. It does contain the exact benchmark revision so identity policy can apply audited benchmark-continuity mappings. It is useful for audit and exact-match queries, but it is not itself series identity.

A project's identity policy projects and normalizes reported coordinates into a canonical comparison-identity object. For example, it may normalize equivalent source URIs or omit a reported coordinate that policy allows to vary. The policy has an `identity_schema` identifier that changes when projection semantics or audited continuity mappings change:

```text
comparison_fingerprint = SHA-256("benchmark-comparison-v1\0" + identity_schema + "\0" + RFC-8785-canonical-JSON(comparison_identity))
estimator_fingerprint = SHA-256("benchmark-estimator-v1\0" + RFC-8785-canonical-JSON(estimator))
series_fingerprint = SHA-256("benchmark-series-v6\0" + comparison_fingerprint + "\0" + estimator_fingerprint)
```

An operational policy or software release that produces the same identity schema does not split history. A genuinely different identity schema creates distinct series, retained alongside older policy projections rather than replacing them.

The database may use `series.id` internally, but stable annotations and external references use `series_fingerprint`. Results are indexed by `reported_coordinates_fingerprint`; `series_point` rows materialize policy-derived membership and estimates.

The server computes all fingerprints. Canonical source URIs, JSON canonicalization, number/string normalization, omitted values, estimator method versions, and identity schema definitions are part of the contract.

### 4.4 Quantity vocabulary

Quantities are an **open vocabulary**: wall time is not privileged, and the
schema never enumerates what may be measured. A survey of existing harnesses
and tracking systems shows the range one project may record — CPU, GPU, and
wall time; three distinct memory semantics; hardware counters; throughput;
energy and power; binary size and build time; quality scores. All of these are
ordinary quantities here. Appendix A gives non-normative examples.

A quantity declaration carries:

- **`name`** — stable within the project, immutable once used. Distinct
  measurement semantics require distinct names: bytes allocated per operation,
  the size of a returned object, and peak process RSS are three quantities,
  never one `memory`.
- **`unit`** — the canonical UCUM unit (§3 rule 9). Counts are dimensionless
  (`1`); rates use unit-per-time (`By/s`, `1/s`). Synthetic units are legal
  but must be named as what they are: a simulator's weighted cycle estimate is
  `estimated-cycles` in `1`, never seconds.
- **`direction`** *(optional, descriptive)* — `lower-is-better`,
  `higher-is-better`, or absent. Recorded because nearly every producer knows
  it; excluded from identity and from any verdict (§3 rule 12).
- **`deterministic`** *(optional, descriptive)* — declares that repetition
  under fixed conditions reproduces the value exactly or nearly so, as with
  simulated instruction counts or binary size. A single observation of a
  deterministic quantity is complete evidence, not a weak sample.

Two placement rules complete the picture:

- **Percentiles are estimators, not quantities.** A tracked p99 latency is
  quantity `latency` with estimator `p99` — one series per percentile — not a
  minted `latency-p99` quantity.
- **The same physical quantity may be a measurand or a condition.** CPU
  frequency or temperature is a quantity when it is what the series estimates,
  and observed context when it is a recorded condition of some other
  measurement. Name and unit conventions are shared across both uses so a
  value can move between them without translation.

### 4.5 Estimators and compound outputs

An immutable result may retain producer-supplied mean, median, percentile, dispersion, and other summaries together. The estimator is not part of reported coordinates. It is a series projection: project policy lists the estimators it materializes, and the server writes computed values to rebuildable `series_point` rows rather than adding summaries to the producer result. A mean series and a median series over the same coordinates therefore share one stored result and one observation batch; there are never two producer results with duplicated observations for the sake of a second estimator.

An aggregate-only producer reports the estimate summaries it has, each labelled with its estimator and `source = producer`. The corresponding series point references that immutable summary. Adding an estimator to project policy later creates points for results with sufficient observations and leaves aggregate-only results without that estimator out of the new series; it never rewrites stored results.

An estimator declaration has a name, method/version, optional parameters, and explicit input level (`observations` or `estimates`). Parameters include details that can alter the result, such as percentile interpolation. A compound estimator also declares semantic input roles and quantities; these stable semantics enter `estimator_fingerprint`. A separate derivation-provenance object maps those roles to stable input result references, which do not enter series identity. `attempt_key` locates candidate siblings, while direct references remove ambiguity when an attempt contains more than one result for a quantity. When observations must remain paired, structured observations carry matching group/ordinal or pair keys.

```json
{
  "estimator": {
    "name": "max",
    "method_version": "benchx/max/v1",
    "input_level": "estimates",
    "inputs": [
      {"role": "cpu", "quantity": "cpu-time"},
      {"role": "gpu", "quantity": "gpu-time"}
    ]
  },
  "derivation": {
    "inputs": [
      {
        "role": "cpu",
        "result": {"producer": "example.org/adapter", "ingest_key": "ci-1234:parquet-read:cpu-time"}
      },
      {
        "role": "gpu",
        "result": {"producer": "example.org/adapter", "ingest_key": "ci-1234:parquet-read:gpu-time"}
      }
    ]
  }
}
```

A compound result is an ordinary result for its own quantity and may come into existence in either of two ways:

- **Emitted by the producer.** The harness computes the compound value at measurement time and reports it as a sibling result under the same `attempt_key`, with immutable estimate summaries marked `source = producer`, an estimator declaration, and derivation provenance containing stable input result references. When the inputs were paired per repetition, the producer may also report a derived observation batch.
- **Derived later.** A server or analysis component acts as a producer and emits a new immutable derived result under the original namespace-qualified `attempt_key`, with producer-supplied summaries and derivation provenance referencing the input results. It includes observations only when paired input observations support them. Derivation never modifies the input results.

The routes yield the same series only when output coordinates and the complete versioned estimator declaration are equal. Producer identity, derivation records, and concrete input result references remain provenance rather than series identity. The attempt-integrity rule in §5.3 guarantees that the inputs share subject revision, benchmark revision, and host environment.

The indexed contract remains scalar. An operation such as `median([cpu_times, gpu_times])` that produces two values emits two results—one for `cpu-time` and one for `gpu-time`—rather than a tuple-valued estimate. Large vectors, covariance, or specialist multidimensional evidence remain artifacts (§7).

## 5. Result contract

### 5.1 Fields and statuses

| Group | Fields |
|---|---|
| **Identity facts** | reported project/designated source, exact benchmark identity, `coordinates`, server-computed `reported_coordinates_fingerprint`, and subject `revision_id` |
| **Attempt grouping** | namespace-qualified `attempt_key` |
| **Outcome** | `status`, optional quantitative constraint |
| **Observed context** | optional immutable non-identity condition snapshot |
| **Producer evidence** | optional observation batch and immutable typed summaries supplied by the producer |
| **Derived projections** | rebuildable `series_point` rows, stored outside the producer result |
| **Method** | optional realized procedure JSON |
| **Provenance** | producer/version, ingest/native/run/batch keys, derivation input result references, mapping version, timestamps, payload URI/checksum, info |
| **Quality** | optional immutable producer validation and warnings; store quarantine/exclusion state is separate |

Statuses are:

- `success`: a usable observation batch or at least one usable producer estimate summary;
- `partial`: the same evidence as `success`, plus a reported partial failure;
- `censored`: only a supported lower, upper, or interval constraint is known, such as `runtime > 60 s`;
- `error`: no usable estimate or quantitative constraint;
- `skipped`: the harness explicitly skipped this known workload variant.

Absence of a row means the workload variant was not reported. Detection excludes partial, censored, error, skipped, quarantined, and dirty-subject or dirty-benchmark results by default. A successful result with observations but no producer estimate remains usable because the server can derive series points.

### 5.2 Example ingest object

```json
{
  "schema_version": 5,
  "producer": {
    "name": "example.org/benchmark-adapter",
    "version": "4.0",
    "mapping_version": "native-to-benchx/v5"
  },
  "ingest_key": "ci-1234:parquet-read:wall-time",
  "attempt_key": "ci.example.org/runs/ci-1234/attempts/parquet-read-snappy-1",
  "project": "arrow",
  "source": {
    "uri": "https://github.com/apache/arrow",
    "type": "git"
  },
  "revision": {
    "key": "02addad..."
  },
  "benchmark": {
    "source": {
      "uri": "https://github.com/example/arrow-benchmarks",
      "type": "git"
    },
    "revision": {
      "key": "92ef3aa..."
    }
  },
  "coordinates": {
    "workload": {
      "name": "parquet-read",
      "parameters": {"compression": "snappy"}
    },
    "subject": {
      "name": "apache-arrow",
      "components": [
        {"role": "primary"}
      ],
      "configuration": {
        "build_type": "release",
        "compiler": "clang-18"
      }
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
      "identity": {
        "runner": "bench-01",
        "cpu": "AMD EPYC 7R13",
        "cores": 8
      }
    }
  },
  "measurement": {
    "status": "success",
    "observations": [0.0371, 0.0364, 0.0363, 0.0370, 0.0368],
    "summaries": [
      {
        "type": "estimate",
        "estimator": {
          "name": "mean",
          "method_version": "benchx/mean/v1",
          "input_level": "observations"
        },
        "value": 0.03672,
        "source": "producer"
      },
      {
        "type": "estimate",
        "estimator": {
          "name": "median",
          "method_version": "benchx/median/v1",
          "input_level": "observations"
        },
        "value": 0.0368,
        "source": "producer"
      },
      {
        "type": "statistic",
        "name": "sample_standard_deviation",
        "value": 0.0003564,
        "source": "producer",
        "method": "n-1"
      },
      {
        "type": "confidence_interval",
        "statistic": "mean",
        "level": 0.95,
        "lower": 0.03628,
        "upper": 0.03716,
        "source": "producer",
        "method": "student-t"
      }
    ]
  },
  "observed_context": {
    "kernel": "6.8.0-31-generic",
    "glibc": "2.39"
  },
  "procedure": {
    "inner_iterations": 100,
    "attempted_repetitions": 5,
    "completed_repetitions": 5,
    "warmups_performed": 1
  },
  "provenance": {
    "run_key": "ci.example.org/runs/ci-1234",
    "started_at": "2026-07-18T09:12:44Z",
    "subject_dirty": false,
    "benchmark_dirty": true,
    "benchmark_patch_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "runner": {"name": "example-runner", "version": "2.1"},
    "source_payload_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  },
  "quality": {
    "warnings": ["dirty-benchmark-tree"]
  }
}
```

The server may derive materialized points after accepting that immutable ingest object. They are not fields added to the producer result:

```json
{
  "series_fingerprint": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "result_id": "018f6f7e-4a17-7b2c-8d91-8c0b75c46f25",
  "estimator": {
    "name": "mean",
    "method_version": "benchx/mean/v1",
    "input_level": "observations"
  },
  "value": 0.03672,
  "source": "derived"
}
```

### 5.3 Semantics and integrity

- A producer-supplied `estimate` is a distinguished entry in the immutable result's `summaries`: it has `type = estimate`, a finite value in the quantity's canonical unit, a complete estimator declaration, and `source = producer`. A result holds at most one producer estimate summary per estimator. This supports aggregate-only producers without creating a second producer-summary representation.
- A result can contribute to a series when it has either a producer estimate for that series' estimator or sufficient observations for the server to derive one. The resulting value is stored in `series_point`; applying another estimator adds a derived point and series membership, not a summary on the producer result.
- The producer never sends a comparison fingerprint, series identifier, series point, or identity-policy schema. Reported `coordinates` are validated and fingerprinted on ingest. The server derives comparison identities, series, and points without mutating the accepted result.
- Identity-policy schemas are retained side by side. Rebuilding materialized series and points for one schema does not delete or reinterpret indexes built under another schema.
- `observed_context` is an immutable per-result snapshot excluded from reported coordinates. Analyses may annotate, filter, or stratify by it. A project that begins requiring a field to match promotes it into reported coordinates through a new mapping and identity-policy schema.
- Observations are finite values in the quantity's unit after declared normalization. A numeric array is the common observation batch. Structured observations—not procedure—carry per-observation ordinal/time, group, pair, inclusion, and exclusion data.
- If observations exist, the server calculates a `series_point` for every applicable server-computable estimator in project policy. A producer estimate for the same estimator remains unchanged; a discrepancy is recorded in series-point provenance and, when material, as a series-point warning.
- `summaries` is an extensible producer-evidence list. Supported types include `estimate`, `statistic`, `confidence_interval`, `coverage_interval`, `source_bounds`, `standard_uncertainty`, and `expanded_uncertainty`. Each entry records the estimate/statistic addressed, source, method, and level or factor when applicable. Numeric summary values use the quantity's canonical unit unless explicitly dimensionless.
- Observation standard deviation is a precision statistic, not automatically uncertainty of a mean or median. Unknown bounds stay `source_bounds`; labels such as `stat`, `sys`, `range`, or `error` retain source semantics.
- A single harness invocation that reports several quantities—say CPU time, GPU time, peak memory, and a numeric correctness metric—yields one result per quantity. The results share `attempt_key`; structured observations use matching group/ordinal or pair keys when values correspond across quantities.
- Environment identifies the host or allocation shared by an attempt. Optional `resource_selection` distinguishes results for GPU 0, GPU 1, a CPU set, or another selected resource without making sibling results disagree about their host environment.
- An observed scalar output or quality metric can be a quantity. An expected ground-truth value belongs to workload/dataset metadata or a referenced artifact; an error norm or mismatch count derived from expected and observed values is another quantity. A pass/fail correctness verdict remains quality/decision policy.
- For a quantity declared deterministic (§4.4), one observation is complete evidence: dispersion summaries are not expected, and analyses must not treat the single observation as an undersampled distribution.
- `success` and `partial` require either a non-empty usable observation batch or at least one finite producer estimate summary; `partial` also requires a reason. `censored` requires a constraint containing a kind (`lower_bound`, `upper_bound`, or `interval`), finite bound(s), inclusivity, and cause. `error` and `skipped` have neither observations, estimates, nor constraints.
- Inner-iteration and repetition sizes are positive; attempt/failure counts and durations are non-negative; interval lower bounds do not exceed upper bounds.
- A result's designated source, workload variant, and quantity belong to the same project, and its subject revision refers to its designated source. Reported coordinates and producer evidence are immutable; derived indexes change only by adding or rebuilding policy-versioned materializations.
- `run_key` is supplied by the scheduler, CLI, CI system, or other run author. The executor creates a globally namespace-qualified `attempt_key`—for example a URI-like key or UUID—and every producer preserves or deterministically maps it. A retry gets a new attempt key. Neither key enters comparison identity.
- **Attempt integrity.** All results sharing an `attempt_key` must agree on project, designated source, subject revision, benchmark revision, `subject_dirty` and `benchmark_dirty`, workload variant, subject descriptor, host environment identity, and `run_key`. They may differ in quantity, resource selection, and quantity-specific instrumentation. A result that violates shared fields against an already stored sibling is rejected as an *attempt conflict* (§5.4).
- A derived result names its inputs with stable `(producer, ingest_key)` references. Attempt integrity is a guard on shared execution facts, not a substitute for derivation lineage.
- `subject_dirty` and `benchmark_dirty` are per-result provenance flags with an optional patch digest. They never alter which `revision` row a result references, and a dirty subject or benchmark tree excludes the result from detection by default. Producer-reported validation and warnings remain immutable; later quarantine or exclusion decisions are separate store state or annotations.
- Identical retries of `(producer, ingest_key)` return the existing result; different payloads conflict. Re-ingestion preserves the original attempt and run keys.
- Migrations retain mapping version and source payload URI or checksum.
- Large observation sets, covariance matrices, profiles, histograms, likelihoods, and similar specialist outputs are external artifacts with media type/schema, URI, and checksum.

Physical partitioning and indexes are implementation choices. If PostgreSQL partitioning is used, global idempotency must still be enforced correctly.

### 5.4 Ingest contract

The ingest object (§5.2) is the message; how it travels is a deployment
choice. Any transport implementing these semantics is conforming — the
litmus test is **file drop**: writing result documents to a directory that
something later sweeps into the store must be a valid delivery path. A
canonical concrete transport binding is a deliberately deferred
implementation decision.

- **Acknowledgment means validated and durable.** A positive ingest response
  promises the result passed validation, is stored, and is queryable. A
  producer may forget a result once acknowledged.
- **Entities auto-create; meaning is protected.** First sight of a project,
  source, workload variant, quantity, or revision creates it. Applicable
  policy-versioned series and points are then materialized without changing the
  accepted result. A quantity arriving with a unit different from its existing
  declaration is rejected as a unit conflict—the immutability rule (§3 rule
  13) is enforced here, not by ceremony at declaration time.
- **No ordering, no deadline.** Results may arrive late, duplicated, or out
  of order; deferred delivery — an offline laptop, a weekly batch — is valid
  indefinitely. Revision is the history axis, source topology determines its
  order, and ingest time is provenance.
- **Batches are transport optimizations.** A multi-result delivery is N
  independent documents with N independent outcomes; there is no atomic
  transport batch. Results from one benchmark attempt retain their shared
  `attempt_key` regardless of transport framing. Partial acceptance is normal
  and reported per result.
- **Machine-readable rejection taxonomy.** At minimum: *malformed* (schema
  validation failed), *idempotency conflict* (same `(producer, ingest_key)`,
  different payload), *unit conflict*, *identity violation* (e.g. coordinates
  and revision from different sources, a primary subject component whose
  source differs from the top-level source, or a payload carrying a series
  identifier, comparison fingerprint, or series point), *attempt conflict* (a
  result disagreeing with a stored sibling under the same `attempt_key` on the
  shared fields listed in §5.3), and *quarantined* (accepted but withheld from
  analysis pending review). Each is distinct so producers can react without
  parsing prose.

## 6. Migration contract

Each import records whether:

- observations are structured, flat, or absent;
- several quantities can be associated with the same native attempt;
- benchmark and subject source revisions can be distinguished;
- reported coordinates are complete for the identity policy or thin;
- summaries are typed, source-defined, or absent.

`thin` means the source lacks one or more coordinates required by the target identity policy. The importer records this and the missing attributes in provenance rather than inventing defaults. Thin imports are not matched across sources without an approved mapping. An importer preserves a native attempt identifier when its grouping semantics are known; otherwise it generates a distinct namespace-qualified attempt key per result rather than guessing that results were measured together.

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

- **Google Benchmark:** iteration rows become observations; aggregate rows remain producer summaries; secondary metrics become sibling quantity results sharing `attempt_key`; split mixed source context into comparison context, environment, observed context, procedure, and provenance.
- **pytest-benchmark:** exported round data becomes observations; put requested warmup/timing strategy in comparison context and realized rounds, iterations, and warmups in procedure.
- **JMH:** preserve fork grouping when available; map `scoreConfidence` as a 99.9% confidence interval for the score; mode and secondary metrics define quantity/estimator semantics.
- **cargo-criterion:** pair `iteration_count` with `measured_values`; retain typical/mean/median/MAD/slope estimates and bounds.
- **BenchmarkDotNet:** detailed measurements become observations; retain parameters, job, host, statistics, confidence interval, and percentiles with source semantics.

### 6.3 OpenTelemetry interoperability

OpenTelemetry does not define a general benchmark-result semantic convention. Its benchmark repository defines scenario-specific reporting through github-action-benchmark. OTLP Metrics is a generic time-series transport, so compatibility is an adapter concern rather than a reason to change the core schema.

For OTLP export, map environment to `Resource`, producer name/version to instrumentation `Scope`, quantity/unit to a `Metric`, the exported `series_point` estimate to a `Gauge` point, and project/source/workload variant/comparison context/resource selection/revision/estimator to point attributes. Metric naming and attribute flattening are adapter policy. Export only usable scalar estimates by default: OTLP has no lossless standard representation for benchmark observations, source bounds, confidence intervals, errors/skips, or idempotency keys. The canonical result remains the system of record.

OTLP treats Resource and data-point attributes as metric-stream identity. Therefore, do not export observed context as metric attributes when one continuous downstream series is required. Export it on a linked benchmark-run log/span, or accept that the OTLP backend will split the stream. When ingesting OpenTelemetry CI/CD metadata, adapters may map `vcs.repository.url.full` to source URI, `vcs.ref.head.revision` to revision key, `cicd.pipeline.run.id` to run key, and `cicd.worker.id` to environment identity. Preserve the original attributes and semantic-convention schema URL in provenance.

## 7. Scope and simplifications

The following concepts are useful but do not justify core tables for current computing benchmark use cases:

- **Measurement procedure, measuring system, and model:** series-defining values go in `coordinates.comparison_context`; changing non-identity conditions go in observed context; attempt details and corrections go in procedure/provenance.
- **Runs/events:** `run_key`, `attempt_key`, and `batch_key` group results without imposing a shared transactional parent.
- **Observation rows:** inline JSON preserves common samples and grouping; very large data is external.
- **Uncertainty budgets and source variations:** typed summaries preserve their semantics.
- **Covariance and multidimensional data:** retain them as referenced artifacts until indexed operations are required.
- **Unit and estimator tables:** controlled vocabularies suffice; quantity stores the canonical unit and the project comparison policy lists the estimators it projects.
- **Revision graph/order and alias tables:** source integrations or an optional revision catalog provide topology and ordering; audited query/display mappings provide aliases. Neither is repeated on every result.

A structure becomes first-class only when it participates in comparison identity, referential integrity, or frequent indexed queries. This keeps the normalized core at nine tables while preserving an upgrade path.

The result store also excludes alert policy, CI orchestration, source-code hashes as permanent workload-variant identity, source-local fingerprints, large artifact blobs, and branch/fork metadata as intrinsic revision properties.

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

Illustrations of the open vocabulary (§4.4), with canonical UCUM units. None
of these names is required; projects declare what they measure. Sources
observed recording each class are noted for orientation.

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
