# Benchmark Measurement Result Schema and Migration Contract

**Status:** Minimal draft after source and metrology review  
**Companion to:** *A Continuous Benchmarking Framework: Benchmark Result Definition and Storage Schema*  
**Author:** Rok Mihevc  
**Review date:** 2026-07-23

## 1. Purpose

This document defines the minimum model needed to ingest, compare, and migrate computing benchmark results without inventing statistical meaning.

> A **measurement result** records one attempt to estimate one quantity for one benchmark case at one source revision, together with the available evidence and provenance.

> **Comparison identity** is the canonical set of attributes that project policy requires to match before two estimates may be treated as points in the same benchmark history. It includes workload and measurement semantics plus conditions that must remain fixed. It excludes the source revision, which is the history axis, and excludes run IDs, timestamps, and other provenance.

A **series** is one comparison identity followed across source revisions:

> **project × source × case × quantity × estimator × comparison context × environment**

Potentially influential conditions that are intentionally allowed to vary—such as the kernel or glibc version—are recorded with each result as **observed context**. They remain visible for annotation and analysis without creating a new series.

For example, one series could track:

- project/source: Apache Arrow from `https://github.com/apache/arrow`;
- case: Parquet read with Snappy compression;
- quantity: wall time in seconds;
- estimator: mean;
- comparison context: Python 3.12, Clang 18, and timing protocol v1;
- environment: runner `bench-01` with a specified CPU and core policy.

Each revision may contribute zero or more results to this series, producing the history shown in a benchmark chart. Changing the compression parameter, quantity, estimator, a comparison-context value, or environment creates a different series. Changing only the run ID, timestamp, kernel, or glibc version does not under this example's identity policy; the latter two remain attached as observed context.

The common operations are to find a series, order its results by revision, plot its estimates, inspect observations, and trace each result to its producer. The indexed core is therefore scalar; richer data remains representable without requiring first-class tables.

Detection, alerts, thresholds, scheduling, and run lifecycle are out of scope.

## 2. Vocabulary

| Term | Meaning here |
|---|---|
| **Case** | Named benchmark workload plus parameters. |
| **Quantity** | Named output and canonical unit, such as `wall-time` in `s` or `peak-memory` in `By`. Canonical units use UCUM when representable. |
| **Estimator** | Rule producing the canonical estimate, such as mean, median, minimum, slope, or a source-defined value. |
| **Observation** | One replicate measured value after declared normalization. |
| **Estimate** | Canonical scalar used for plots and analysis; it is not a known “true value.” |
| **Statistic** | Numeric summary computed from observations, such as a mean, median, percentile, or standard deviation. The series estimator identifies which statistic is the canonical estimate. |
| **Precision statistic** | Statistic describing observation dispersion, such as standard deviation, MAD, or IQR. |
| **Measurement uncertainty** | Uncertainty associated with an estimate. It is not synonymous with error or observation spread. |
| **Comparison context** | Software, build, protocol, and instrumentation settings chosen as series identity. Stored in `series.comparison_context`. |
| **Observed context** | Immutable per-result snapshot of relevant but non-identity conditions. Stored in `benchmark_result.observed_context`. |
| **Environment** | Comparison-relevant execution resources, especially runner and hardware identity. |

In metrology, the particular quantity intended for a case at a revision is the **measurand**. It need not be a database entity here.

Use `accuracy`, `precision`, `error`, `bias`, `confidence interval`, and `coverage interval` only with their defined meanings. Preserve source terminology when its exact meaning is unknown.

## 3. Design rules

1. **Quantity and estimator are part of comparison identity.** Wall time and memory, or mean and median, never share a series.
2. **Revision is the series axis.** Ingest time is not historical order.
3. **Comparison context defines the history boundary.** Put a setting there when project policy requires a new series after it changes. Precision-only details such as repetition count belong with the result procedure.
4. **Observed context does not define a series.** Snapshot potentially relevant changing conditions on each result so analysis can annotate, stratify, or exclude them without fragmenting history.
5. **Environment identity is explicit.** Hash only the declared runner/resource identity; store non-identity environment facts as observed context.
6. **Observations are preferred, not required.** Aggregate-only history remains valid and is marked producer-supplied.
7. **Summaries are typed.** Precision, uncertainty, confidence intervals, coverage intervals, and opaque source bounds remain distinct.
8. **Canonical units are interoperable.** Use UCUM case-sensitive units when representable, normalize values before storage, and preserve the producer's original unit in provenance.
9. **Ingestion is idempotent and auditable.** Preserve a producer-scoped key, producer/mapping version, native ID, and source payload reference. Producer identity is stable and namespaced; its software version is not part of the idempotency key.
10. **Decision policy is separate.** Optimization direction, thresholds, guard bands, and alert verdicts do not enter result or series identity.

## 4. Minimal schema

### 4.1 Core tables

| Table | One row represents | Key or invariant |
|---|---|---|
| `project` | benchmark namespace | unique project key |
| `source` | benchmark source, usually a repository | unique `(project_id, canonical_uri)` |
| `benchmark_case` | case plus exact parameters | unique `(project_id, name, parameters)` |
| `quantity` | named output with canonical UCUM unit when representable | unique `(project_id, name)`; immutable after use |
| `environment` | explicit environment identity and descriptive metadata | unique `(identity_schema, fingerprint)` |
| `revision` | source revision, parents, and optional native order metadata | unique `(source_id, revision_key)` |
| `series` | exact comparison identity | unique fingerprint and natural identity |
| `benchmark_result` | one reported attempt | unique `(producer, ingest_key)` |

`benchmark_case.parameters` is a canonical JSON object with primitive values. Adapters preserve numeric values when source semantics are known; the core does not require a general scientific-variable or bin model.

`series` stores source, case, quantity, estimator, comparison-context JSON, and environment. These fields are immutable.

`benchmark_result` stores the outcome plus observed context, observations, summaries, procedure, quality, and provenance as validated JSON. Promote a JSON structure to a child table only when a concrete query, size, or integrity requirement justifies it.

No separate core tables are required for estimator, unit, procedure, measuring system, run/event, observation, interval, uncertainty component, covariance, revision order, or aliases. Estimator and unit vocabularies are application configuration.

### 4.2 Field placement

| Destination | Put here | Examples |
|---|---|---|
| **Case parameters** | Controlled workload/input | size, compression, dataset, scenario |
| **Comparison context** | Settings whose change must create a series | compiler/flags, runtime family, backend, target, protocol version, warmup/GC policy, timer/counter |
| **Environment identity** | Stable execution resources that define a series | runner, CPU model, core policy, memory, cluster shape |
| **Observed context** | Relevant conditions allowed to vary within a series | kernel, glibc, microcode, image digest, runtime patch, load, temperature |
| **Result procedure** | Precision/acquisition details | repetitions, inner iterations, order, durations, fork/block/pair keys |
| **Provenance** | Audit and descriptive metadata | run/batch key, CI link, logs, model/correction notes, artifacts, source payload |

A timer, harness, or data-reduction version needs no separate entity: include it in comparison context if its change must split history, in observed context if it should only annotate history, and in provenance if it is audit-only.

### 4.3 Series fingerprint

The database uses `series.id` for joins. A portable fingerprint is:

```text
SHA-256("benchmark-series-v4\0" + RFC-8785-canonical-JSON(identity))
```

The canonical identity is the tuple from §1, assembled from the top-level project/source and the `series` object in §5.2; it never contains database row IDs. Environment contributes its identity schema and fingerprint, not descriptive metadata.

The server computes fingerprints. Canonical source URIs, JSON canonicalization, number/string normalization, omitted values, and identity schema versions are part of the contract.

## 5. Result contract

### 5.1 Fields and statuses

| Group | Fields |
|---|---|
| **Identity** | `series_id`, `revision_id` |
| **Outcome** | `status`, optional `estimate`, `estimate_source`, optional quantitative constraint |
| **Observed context** | optional immutable non-identity condition snapshot |
| **Evidence** | optional observations and typed summaries |
| **Method** | optional procedure JSON |
| **Provenance** | producer/version, ingest/native/run/batch keys, mapping version, timestamps, payload URI/checksum, info |
| **Quality** | optional validation, quarantine, warnings, and exclusions |

Statuses are:

- `success`: usable point estimate;
- `partial`: usable estimate plus a reported partial failure;
- `censored`: only a supported lower, upper, or interval constraint is known, such as `runtime > 60 s`;
- `error`: no usable estimate or quantitative constraint;
- `skipped`: the harness explicitly skipped this known case.

Absence of a row means the case was not reported. Detection excludes partial, censored, error, skipped, and quarantined results by default.

### 5.2 Example ingest object

```json
{
  "schema_version": 4,
  "producer": {
    "name": "example.org/benchmark-adapter",
    "version": "4.0",
    "mapping_version": "native-v4"
  },
  "ingest_key": "ci-1234:parquet-read:wall-time",
  "project": "arrow",
  "source": {
    "uri": "https://github.com/apache/arrow",
    "type": "git"
  },
  "revision": {
    "key": "02addad...",
    "parents": ["9b971f..."]
  },
  "series": {
    "case": {
      "name": "parquet-read",
      "parameters": {"compression": "snappy"}
    },
    "quantity": {"name": "wall-time", "unit": "s"},
    "estimator": "mean",
    "comparison_context": {
      "python": "3.12",
      "compiler": "clang-18",
      "protocol": "benchmark-time/v1",
      "timer": "perf_counter"
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
    "estimate": 0.03672,
    "estimate_source": "server",
    "observations": [0.0371, 0.0364, 0.0363, 0.0370, 0.0368],
    "summaries": [
      {
        "type": "statistic",
        "name": "sample_standard_deviation",
        "value": 0.0003564,
        "source": "server",
        "method": "n-1"
      },
      {
        "type": "confidence_interval",
        "statistic": "mean",
        "level": 0.95,
        "lower": 0.03628,
        "upper": 0.03716,
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
    "attempted_repetitions": 5
  },
  "provenance": {
    "run_key": "ci-1234",
    "started_at": "2026-07-18T09:12:44Z",
    "source_payload_sha256": "..."
  }
}
```

### 5.3 Semantics and integrity

- `estimate` is finite, in the quantity's canonical unit, and defined by the series estimator.
- `observed_context` is an immutable per-result snapshot and never enters the series fingerprint. Analyses may use it to mark change points, filter, or stratify results.
- Observations are finite values in that unit after declared normalization. A numeric array is the common form; structured objects may add ordinal/time, fork, block, pair, inclusion, or exclusion data.
- If observations exist and the estimator is server-computable, the server calculates the estimate. Otherwise it retains the producer estimate with `estimate_source = producer`.
- `summaries` is an extensible list. Supported types include `statistic`, `confidence_interval`, `coverage_interval`, `source_bounds`, `standard_uncertainty`, and `expanded_uncertainty`. Each entry records the estimate/statistic addressed, source, method, and level or factor when applicable. Numeric summary values use the quantity's canonical unit unless explicitly dimensionless.
- Observation standard deviation is a precision statistic, not automatically uncertainty of a mean or median. Unknown bounds stay `source_bounds`; labels such as `stat`, `sys`, `range`, or `error` retain source semantics.
- `success` and `partial` require a finite estimate. `censored` requires a constraint containing a kind (`lower_bound`, `upper_bound`, or `interval`), finite bound(s), inclusivity, and cause. `error` and `skipped` have neither.
- Inner-iteration and repetition sizes are positive; attempt/failure counts and durations are non-negative; interval lower bounds do not exceed upper bounds.
- A series's source, case, and quantity belong to the same project. A result's series and revision refer to the same source. Series identity is immutable. Promoting an observed-context field into comparison identity requires an explicit mapping/fingerprint version change rather than silently rewriting history.
- Identical retries of `(producer, ingest_key)` return the existing result; different payloads conflict.
- Migrations retain mapping version and source payload URI or checksum.
- Large observation sets, covariance matrices, profiles, histograms, likelihoods, and similar specialist outputs are external artifacts with media type/schema, URI, and checksum.

Physical partitioning and indexes are implementation choices. If PostgreSQL partitioning is used, global idempotency must still be enforced correctly.

## 6. Migration contract

Each import records whether:

- observations are structured, flat, or absent;
- comparison identity is full or thin;
- summaries are typed, source-defined, or absent.

`thin` means the source lacks one or more desired identity attributes. The importer records this and the missing attributes in provenance rather than inventing defaults. Thin identities are not matched across imports without an approved mapping.

Importers must be idempotent, retain source payload and mapping version, report identity collisions before writing, preserve failures/skips/limits, reject unit conflicts, and use the same mapping rules as live adapters. They must not parse parameters from names without project rules or copy source-local fingerprints.

### 6.1 Tool mapping summary

| Source | Core mapping | Important caveat |
|---|---|---|
| **ASV** | hardware → environment; OS → observed context; env/dependencies/version → comparison context; benchmark + parameters → case; result → **median estimate**; samples → observations; CI99 → median confidence interval | `null` is failed and `NaN` is skipped. Preserve benchmark version conservatively in comparison context. |
| **Conbench** | case/context/hardware/source map to case/comparison context/environment/source; data → observations; times → procedure | Derive quantity and estimator; do not copy `history_fingerprint`. Use the source deployment's configured summary policy. |
| **Bencher** | Project/Testbed/Benchmark/Measure → project/environment/case/quantity; Metric → source-defined estimate; Report → provenance | Bounds are adapter-defined. Keep opaque bounds as `source_bounds`; threshold direction is decision policy. |
| **Codespeed** | Project/source/revision; Executable → comparison context; Benchmark → case + quantity; Environment → thin environment/observed context; Result aggregates → summaries | `Benchmark.data_type` selects mean or median. Snapshot mutable unit definitions. |
| **LNT** | suite/project; Machine → reviewed environment/comparison/observed context; Test → case; metric → quantity; list/scalar → observations/estimate; Run → provenance | Preserve native order, status/hash, and source metadata. Opaque machine identity is thin. |
| **Nyrkiö** | test path → case; metric name/unit → quantity; value → source-defined estimate; source attributes → revision | Preserve per-metric direction as source decision metadata; conflicts require review. |
| **github-action-benchmark** | suite/project; name → case; tool/unit → quantity; value → source-defined estimate; commit/date → revision/provenance | Interpret `range` by adapter version; otherwise retain it as an opaque summary. History may be truncated. |
| **OpenTelemetry Benchmarks** | scenario ID/workload → case/comparison context; tracked package version → revision; `name`/`unit`/`value` → quantity/estimate; `extra` → environment/observed context/provenance | Its current output is github-action-benchmark's `{name, unit, value, extra}` format. Estimator and direction come from the scenario document; observations and uncertainty are absent. |
| **rustc-perf** | artifact → revision; pstat dimensions → case/comparison context/quantity; collection → run/observation grouping | Group compatible collection rows into observations. Environment is thin unless collector metadata can be joined. |
| **CodSpeed** | aggregate-only source estimate | No reviewed public export schema supports a migration contract. |

### 6.2 Live harness adapters

- **Google Benchmark:** iteration rows become observations; aggregate rows remain producer summaries; split mixed source context into comparison context, environment, observed context, procedure, and provenance.
- **pytest-benchmark:** exported round data becomes observations; place rounds, iterations, and warmup in procedure or comparison context according to identity policy.
- **JMH:** preserve fork grouping when available; map `scoreConfidence` as a 99.9% confidence interval for the score; mode and secondary metrics define quantity/estimator semantics.
- **cargo-criterion:** pair `iteration_count` with `measured_values`; retain typical/mean/median/MAD/slope estimates and bounds.
- **BenchmarkDotNet:** detailed measurements become observations; retain parameters, job, host, statistics, confidence interval, and percentiles with source semantics.

### 6.3 OpenTelemetry interoperability

OpenTelemetry does not define a general benchmark-result semantic convention. Its benchmark repository defines scenario-specific reporting through github-action-benchmark. OTLP Metrics is a generic time-series transport, so compatibility is an adapter concern rather than a reason to change the core schema.

For OTLP export, map environment to `Resource`, producer name/version to instrumentation `Scope`, quantity/unit to a `Metric`, the estimate to a `Gauge` point, and project/source/case/comparison context/revision/estimator to point attributes. Metric naming and attribute flattening are adapter policy. Export only usable scalar estimates by default: OTLP has no lossless standard representation for benchmark observations, source bounds, confidence intervals, errors/skips, or idempotency keys. The canonical result remains the system of record.

OTLP treats Resource and data-point attributes as metric-stream identity. Therefore, do not export observed context as metric attributes when one continuous downstream series is required. Export it on a linked benchmark-run log/span, or accept that the OTLP backend will split the stream. When ingesting OpenTelemetry CI/CD metadata, adapters may map `vcs.repository.url.full` to source URI, `vcs.ref.head.revision` to revision key, `cicd.pipeline.run.id` to run key, and `cicd.worker.id` to environment identity. Preserve the original attributes and semantic-convention schema URL in provenance.

## 7. Scope and simplifications

The following concepts are useful but do not justify core tables for current computing benchmark use cases:

- **Measurement procedure, measuring system, and model:** series-defining values go in `series.comparison_context`; changing non-identity conditions go in observed context; attempt details and corrections go in procedure/provenance.
- **Runs/events:** `run_key` and `batch_key` group results without imposing a shared transactional parent.
- **Observation rows:** inline JSON preserves common samples and grouping; very large data is external.
- **Uncertainty budgets and source variations:** typed summaries preserve their semantics.
- **Covariance and multidimensional data:** retain them as referenced artifacts until indexed operations are required.
- **Unit and estimator tables:** controlled vocabularies suffice; quantity stores the canonical unit and series stores the estimator.
- **Revision-order and alias tables:** native order metadata and audited query/display mappings suffice initially.

A structure becomes first-class only when it participates in comparison identity, referential integrity, or frequent indexed queries. This keeps the normalized core at eight tables while preserving an upgrade path.

The result store also excludes alert policy, CI orchestration, source-code hashes as permanent case identity, source-local fingerprints, large artifact blobs, and branch/fork metadata as intrinsic revision properties.

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

Detailed audits are in `benchmark-result-schema-source-review.md` and `benchmark-result-schema-metrology-review.md`.
