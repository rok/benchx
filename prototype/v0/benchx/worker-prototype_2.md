# Worker prototype

**Status:** Draft, September 2026. Plan for `bx run`: the runner of
`runner.md` (#24) with adapters per `harness-adapter.md` (#31) for Google
Benchmark and pyperf. Consumes work orders (`work-order.md`), emits results
(result schema version 5), within `prototype-scope.md` and
`prototype-design.md` (#27). Where this document and a schema differ, the
schema wins. pyperf facts are from the pyperf 2.10.0 documentation.

**Implemented so far:** the driving half. `bx run` accepts an order, resolves
its target, fixes the planned set, captures the context document, invokes the
harness, and keeps the raw output with an accounting log. Translation into
measurement results (stage 6) is the next milestone, so no results are
written yet.

**Headline:** the work order draft (#35) now carries `harness`, a tagged
`target` (`build_dir` or `python_env`), and a `protocol` object, so a pyperf
run can be ordered. G1–G3 are closed; G10 moves to the result schema
(§12).

## 1. Scope

```text
bx run <order.json> [--out DIR] [--dry-run]
```

One order, local machine, one result file per planned case and quantity.
The worker never reads or writes the store; its output directory is what
`bx ingest` sweeps.

- **In:** Google Benchmark suites in a build directory; pyperf scripts run
  by a Python interpreter; `wall-time` (both) and `cpu-time` (Google
  Benchmark only); capture of revision, dirty state, tree ids, build or
  interpreter configuration, machine identity, and observed context.
- **Out:** builds, environment policy enforcement (including
  `pyperf system tune`), other harnesses, Google Benchmark counters, memory
  quantities, ingest, comparison, and any queue or daemon (`runner.md`
  records the decision against an intake queue).

## 2. Pipeline

| Stage | Both harnesses | Google Benchmark | pyperf |
| --- | --- | --- | --- |
| 1. Accept | Parse strict JSON, validate, compute `workorder_ref`, check every quantity is mappable and every setting applicable | — | Reject `filter` and `cpu-time`: no support |
| 2. Materialize | Locate the checkout (`source_dir`, else discovered) | Exactly one executable named `suite` under `build_dir`; read `CMakeCache.txt`; checkout from `CMAKE_HOME_DIRECTORY`, then the git top level | Interpreter and script; pyperf importable by that interpreter |
| 3. Plan | Fix the planned set | `--benchmark_list_tests` with the filter; probe the minimum-time flag format (§4) | **No listing exists; planned set unknown (G5)** |
| — | The order's `harness.name` selects the adapter for stages 3, 5, and 6 | — | — |
| 4. Capture | Revision, dirty state, tree, `machine/v1` identity, captured by the worker before execution (as suggested in the #24 review), so a crash cannot lose them | CMake cache | Interpreter version, implementation, build flags |
| 5. Execute | Timeout; raw output and stdout/stderr kept | One process per case | One invocation per script; pyperf spawns its own processes |
| 6. Emit | Translate, validate each result against the result schema, write atomically (not yet implemented) | — | — |

Failures by stage:

| Stage | Failure | Outcome |
| --- | --- | --- |
| 1, 2 | Invalid order, missing or ambiguous suite, unsupported setting | Exit 1 before touching the machine; no results |
| 2, 4 | Unreadable cache or checkout | Recorded as absent or `unknown`; not fatal |
| 3 | Listing fails | Exit 2; nothing was planned |
| 5 | Crash, timeout, harness error, skip | An error or skipped result for the case; not a worker failure |
| 6 | Worker produced a non-conforming result | A bug: written to `invalid/` with the errors; exit 3 |

Exit 0 means every planned case and quantity has a result, including error,
skipped, and partial ones (`runner.md`: every outcome is a result). For
pyperf, "every planned case" degrades to "every case that appeared" until
G5 is resolved. The worker ends with a stderr summary, such as
`planned 12 cases × 2 quantities; wrote 24 results (22 success, 2 error: crash)`.

## 3. Harness differences

| | Google Benchmark | pyperf |
| --- | --- | --- |
| Unit | Compiled binary | Python script run by an interpreter |
| List cases | `--benchmark_list_tests` | None |
| Filter | `--benchmark_filter` regex | None in the runner CLI |
| Processes | One per invocation; the worker runs one invocation per case | Orchestrator spawns worker processes per benchmark; no per-case invocation possible |
| Precision knobs | Repetitions, minimum time | Processes, values per process, warmups, loops, minimum time |
| Harness defaults | 1 repetition | 20 processes × 3 values, 1 warmup, 0.1 s minimum time; with a JIT, 6 processes × 10 values and 10 warmups |
| Code vs flags | Settings in code (`Repetitions()`, `MinTime()`, `Iterations()`) override flags and show in the case name | Flags override `Runner(...)` defaults set in code |
| Calibration | Iterations chosen per case, inside the run | Separate calibration run; `--loops` fixes it |
| Warmups | Not reported | Reported per run |
| Values | Per-iteration time per repetition | Normalized per loop iteration |
| Observations | One per repetition, flat | Processes × values, grouped by process |
| Aggregates | Mean, median, stddev, cv rows | None in output |
| Quantities | Real time, CPU time, counters | Wall time; memory via `--track-memory` or `--tracemalloc` |
| Timestamps | One per invocation | Per run |
| Timeout | None; worker-enforced | `--timeout`, exit code 124; none by default |
| Environment | Inherited | Only PATH, PYTHONPATH, HOME, TEMP, a few Windows variables, and locale variables, unless `--inherit-environ` or `--copy-env` |
| Affinity | As launched | Pins to isolated CPUs automatically when present |
| Names | Structured segments; template names can contain spaces | Free text, often with spaces |
| Crash isolation | Per case, because the worker runs one process per case | Per run process, but a failure stops the rest of the script (verify, §13) |

## 4. Driving

**Google Benchmark,** one invocation per planned case:

```text
<suite> --benchmark_filter=^<escaped case>$
        --benchmark_repetitions=<N>
        --benchmark_min_time=<S>s
        --benchmark_report_aggregates_only=false
        --benchmark_out=<raw>/<n>.json --benchmark_out_format=json
```

- **Why per case:** a segfault costs one case, which becomes an error result
  instead of losing the rest of the suite. Each case also gets its own
  `started_at` and `ended_at`, and one attempt is exactly one process.
- **Cost:** a process start per case and the loss of warm state between
  cases. M4 measures whether that changes results.
- **Minimum-time format:** older Google Benchmark releases reject the `s`
  suffix. The Plan stage probes it during listing and falls back to a bare
  number.
- **Filter escaping:** case names are regex-escaped for the anchored filter.
  Check this against template names such as `BM<int, 8>`.

**pyperf,** one invocation per script:

```text
<python> <script> --output=<raw>/<n>.json
        --processes=<P> --values=<V> --warmups=<W> --min-time=<S>
        --timeout=<T> --inherit-environ=<vars>
```

**Both:**

- **Precision flags:** the worker always passes every precision flag, using
  its own documented defaults when the order omits one (Google Benchmark: 1
  repetition, 0.5 s). The recorded protocol is then exactly what ran, never
  an unrecorded harness default. For pyperf this also overrides the
  JIT-dependent defaults.
- **Settings in code:** Google Benchmark settings made in code override the
  flags. They appear as name segments, and the worker records them as that
  case's effective protocol.
- **Protocol:** the order's `protocol.repetitions` levels map directly onto
  `--processes` and `--values`, `calibration` onto `--min-time` or
  `--loops`, and `warmup` onto `--warmups`. The worker rejects a key its
  adapter cannot apply, and records every key it does apply.
- **Timeout:** work order version 1 has none. The worker applies a fixed
  per-case (Google Benchmark) or per-script (pyperf, via `--timeout`)
  default and records it in `provenance.info.timeout_seconds`. A CLI
  override would break the order's self-containment, so the fix is a work
  order field (G6, Q7).
- **Environment:** variables the protocol depends on, such as thread counts,
  must be forwarded to pyperf explicitly with `--inherit-environ` (G6).

## 5. Mapping to results

Common to both harnesses:

| Result field | Source |
| --- | --- |
| `producer` | `{"name": "benchx/<harness>", "version": <benchx version>, "mapping_version": "1"}` |
| `ingest_key` | `<attempt_key>/<quantity>`, unique per result |
| `project`, `source` | Copied from the order |
| `revision.key` | `git rev-parse HEAD` in the checkout |
| `benchmark` | The subject's source and revision (assumption, §7) |
| `coordinates.subject` | `name` from the last segment of `source.uri`; one primary component; `configuration` per harness (below) |
| `coordinates.quantity` | Unit `s`, `lower-is-better` |
| `coordinates.environment` | `machine/v1`, identity `{hostname, cpu_model, cpu_count}`, captured by the worker, never by the harness, so both harnesses on one machine share environment identity; harness-reported CPU details go in `metadata` |
| `measurement.status` | `success`; `partial` (reason `repetitions-incomplete`); `error` (reasons `harness-error`, `crash`, `timeout`); `skipped` (reason `skipped`). Error and skipped results keep full coordinates and have no observations |
| `quality.warnings` | `cpu-scaling-enabled`; `harness-debug-build` when the benchmark library was built in debug mode |
| `provenance` | `run_key` and `labels` from the order; `subject_dirty`, `subject_tree`, `benchmark_dirty`, `benchmark_tree` (§6, §7); `runner`; `original_unit`; the raw output file as `source_payload_uri` and `source_payload_sha256`; under `info`: `workorder_ref`, `requested_by`, `reason`, `timeout_seconds`, `benchmark_inferred` |

Per harness:

| Field | Google Benchmark | pyperf |
| --- | --- | --- |
| `attempt_key` | `urn:uuid:<uuid4>` per case invocation; a re-run gets new keys | `urn:uuid:<uuid4>` per benchmark per invocation |
| `workload.name` | Family name (up to the first `/`) | Benchmark name, percent-encoded (tokens forbid whitespace); original in `provenance.native_id` |
| `workload.parameters` | Remaining name segments: `k:v` named, bare values `arg0`, `arg1`, …, `threads:N` a parameter. Control segments (`real_time`, `process_time`, `manual_time`, `min_time:`, `iterations:`, `repeats:`) go to `comparison_context.protocol` instead | None; names are opaque |
| `quantity` | `wall-time` from `real_time`, `cpu-time` from `cpu_time`, converted from `time_unit` | `wall-time` from values (unit `second`) |
| `observations` | Repetition rows, flat | Structured: `value`, `group` = run index, `ordinal`; warmups as `included: false` with `exclusion_reason: warmup` (Q17) |
| `summaries` | `mean`, `median`, `stddev` as statistic summaries; percentage aggregates (cv) dropped | None |
| `procedure` | `attempted_repetitions`, `completed_repetitions`, `duration_seconds`; `inner_iterations` when all rows agree, otherwise per-row counts in `provenance.info` | Attempted and completed values, `warmups_performed`, `duration_seconds`, `inner_iterations` = loops × inner loops |
| `comparison_context` | `{"harness": {"name": "google-benchmark"}, "protocol": {...}}` with the effective repetitions and calibration, including settings from code | Harness; processes, values, warmups, loops or calibration; interpreter (Q18) |
| `subject.configuration` | CMake cache allowlist: `CMAKE_BUILD_TYPE`, `CMAKE_CXX_COMPILER`, `CMAKE_CXX_FLAGS`, `CMAKE_CXX_FLAGS_<TYPE>`; keys absent when unreadable | Interpreter version, implementation, build flags |
| `observed_context` | Kernel, OS release, load average, CPU scaling | Kernel, OS release, plus pyperf run metadata (load, frequency, CPU config, ASLR, affinity) |
| `status` | Per case, from rows, exit code, and timeout | Per benchmark in output: success or partial. Script failure or exit 124: error, but only for cases known in advance (G5) |
| `started_at`, `ended_at` | Worker clock around the invocation (UTC) | Worker clock too, because pyperf's per-run `date` carries no timezone; the native date goes in `provenance.info` (§13) |

## 6. Revision, dirty state, tree id

Identical for both harnesses:

- **Dirty state:** `dirty` if `git status --porcelain` reports anything,
  `clean` if not, and `unknown` if there is no checkout or git fails. When
  it is `unknown`, the tree id is absent.
- **Clean tree:** the id is `HEAD^{tree}`.
- **Dirty tree:** written through a temporary index (`GIT_INDEX_FILE=<tmp>`,
  then `read-tree HEAD`, `add -A`, `write-tree`). This hashes exactly the
  files `git status` counts and never touches the user's index.

## 7. Assumptions recorded in results

1. **Benchmark location:** benchmark code lives in the subject checkout, so
   `benchmark` and its dirty flag and tree are copied from the subject, and
   `provenance.info.benchmark_inferred` is `true`. This is right for Arrow
   and wrong for separate benchmark repositories (G7).
2. **Subject name:** the last segment of the source URI.
3. **Work order reference:** `workorder_ref` is kept under `provenance.info`
   until the result schema has a field (G12).
4. **pyperf planned set:** whatever appears in the output (G5).

## 8. Output

```text
<out>/<UTC start>-<first 8 hex of workorder_ref>/
  workorder.json         # canonical (RFC 8785) form of the order
  results/<key>.json     # one per case and quantity, validated
  raw/<n>.json           # harness output per invocation
  raw/<n>.stdout, raw/<n>.stderr
  run.json               # accounting: planned cases, outcomes, result keys
  invalid/               # only if the worker produced a non-conforming result
```

- **One directory per invocation,** because several orders may share a run
  key.
- **File names** percent-encode the ingest key.
- **Atomic writes:** every file is written under a temporary name and
  renamed, so a crash never leaves a partial document.
- **`run.json`** is an informational log, not a contract document.

## 9. Code layout

The worker goes in #34's package, `prototype/v0/benchx/benchx/`.

| Module | Responsibility |
| --- | --- |
| `core/schemas/work-order/1/schema.json` | The work order schema, in #34's integer-path layout |
| `core/validation.py` (changed) | Register every bundled schema by `$id` in a `referencing.Registry` so cross-schema references resolve; add the `work_order` kind |
| `worker/order.py` | Load, validate, canonicalize, compute `workorder_ref`, check applicability |
| `worker/target.py` | Suite or script lookup, CMake cache, interpreter, checkout discovery |
| `worker/vcs.py` | Revision, dirty state, tree id |
| `worker/context.py` | `machine/v1` identity and observed context |
| `worker/run.py` | Pipeline, accounting, exit codes |
| `worker/document.py` | The context document, and atomic writes |
| `worker/emit.py` | Assemble, validate, atomically write results (next milestone) |
| `worker/keys.py` | Attempt and ingest keys, token and file-name escaping |
| `worker/schemas.py` | Bundled schemas, registered by `$id` so cross-schema references resolve |
| `adapters/gbench/drive.py` | List cases, probe the minimum-time spelling, build arguments, invoke with timeout, keep raw output |
| `adapters/gbench/translate.py` | Names, units, statuses, summaries, keys (next milestone) |
| `adapters/pyperf/drive.py` | Build arguments, forward environment, invoke, keep raw output |
| `adapters/pyperf/translate.py` | Runs to grouped observations, warmups, loops, names, statuses (next milestone) |
| `worker/cli.py` | `bx run`, until it is wired into the package's own CLI |

**Adapter halves (#31).** The driving half turns the order into invocations
and never builds results. The translating half turns one invocation plus the
worker's context document (source, revision, trees, subject, environment,
protocol, keys) into results and never inspects the machine. A further
harness is then another pair of modules.

**Dependencies:** `jsonschema` and `referencing` (already used by #34),
`rfc8785`, pyperf (for tests), and the standard library.

## 10. Testing

- **Fake Google Benchmark harness:** a small Python script speaking the part
  of the Google Benchmark CLI the worker uses. It can be told to crash, hang,
  skip, error, or drop repetitions, so every pipeline path is testable
  without a C++ toolchain.
- **Recorded Google Benchmark output:** JSON from real binaries for
  translator tests, covering positional and named arguments, threads,
  aggregates including cv, skips, errors, and each time unit.
- **Real pyperf:** pyperf is a pip dependency, so tests run tiny real scripts
  with minimal settings, including a script that raises mid-suite and one
  that times out.
- **VCS:** temporary repositories: clean, modified, untracked-only,
  ignored-only, and none.
- **Schema:** every emitted file is validated against the full result schema
  in tests, not only at run time; `bx validate` over an output directory is
  the end-to-end check.

## 11. Milestones

| Milestone | Delivers |
| --- | --- |
| M1 | Order acceptance: bundled schema, cross-schema references, `bx validate --kind work_order`, and `bx run --dry-run` printing the planned cases and captured context |
| M2 | Google Benchmark happy path against the fake harness |
| M3 | Google Benchmark failure paths (crash, timeout, skip, harness error, partial), accounting, and exit codes |
| M4 | Real Google Benchmark: fixtures, the minimum-time probe, name edge cases, and the two-build Arrow demo from `prototype-design.md` feeding `bx compare` |
| M5 | pyperf, now unblocked by #35 |

## 12. Gaps in schemas and designs

| | Gap | Where | Impact |
| --- | --- | --- | --- |
| G1 | ~~No `harness` field~~ | Work order | **Closed** in #35: required `harness` object; open value versus enum stays open |
| G2 | ~~Only a `build_dir` target~~ | Work order | **Closed** in #35: `target.kind` is `build_dir` or `python_env`; the target's shape stays an open question |
| G3 | ~~`repetitions` is one integer~~ | Work order | **Closed** in #35: `protocol.repetitions` is a list of levels, so pyperf's 20 processes × 3 values, 1 warmup, and 100 ms minimum time are all expressible |
| G4 | `suite` and `filter` have Google Benchmark semantics | Work order | pyperf has no filter; its suite is a script path |
| G5 | No declared case list | Work order, `runner.md` | pyperf cannot list its benchmarks, so its planned set is unknown and a crashed script looks like a shorter suite, the pain #31 targets |
| G6 | No timeout; no environment forwarding | Work order | pyperf passes workers only PATH, PYTHONPATH, HOME, TEMP, a few Windows variables, and locale variables, so thread counts and similar settings are silently lost |
| G7 | No benchmark source or subject name | Work order | Known; more pressing for pyperf, whose benchmarks often live in separate repositories |
| G8 | No place for the interpreter or dependency pins | Work order, result mapping | Is the interpreter subject configuration or host runtime? Are pins non-primary subject components? |
| G9 | No key for harness name and version | Result schema Appendix B | `comparison_context` is open; the key is unspecified |
| G10 | No process-level repetition keys | Result schema Appendix B and `procedure` | Appendix B should define `repetitions.levels`; `procedure` has one attempted and one completed count, so it cannot say 20 processes planned, 18 completed, 3 values each |
| G11 | Name escaping for tokens | `harness-adapter.md` key escaping (check coverage) | pyperf names with spaces; Google Benchmark template names |
| G12 | No `workorder_ref` | Result schema | Known |
| G13 | Comparator pools all observations | `comparator.md`, `prototype-design.md` §5 | pyperf values are normalized per loop and grouped by process; pooling ignores the between-process variance that `group` carries |
| G14 | No pyperf entry in the adapter catalog | `harness-adapter.md` | Mapping rules undefined |
| G15 | Environment identity fields | #33 (unread) | Which fields, and worker- or harness-collected |
| G16 | Environment policy overlap | `runner.md` | pyperf's automatic pinning and `system tune` versus the runner's policy |

## 13. To verify

- **pyperf output on a crash:** whether pyperf writes `--output` when the
  script dies mid-suite. If not, completed benchmarks are lost too.
- **pyperf crash scope:** whether a failed worker process stops the rest of
  the script.
- **pyperf timestamps:** the timezone of pyperf's per-run `date`; results
  require UTC. Until this is settled the worker clock is used, which is
  coarser: one timestamp per script rather than per benchmark.
- **Google Benchmark JSON:** its skip and error fields across versions.

## 14. Open questions

Still open from the previous round:

| | Question | Current assumption |
| --- | --- | --- |
| Q1 | Build on the existing example implementation (#27)? | From scratch |
| Q2 | Worker executes one order and exits? | Yes |
| Q3 | Environment identity per #33? | `machine/v1` per #27 |
| Q4 | Google Benchmark: one invocation per case? | Yes |
| Q5 | `benchmark` field in the work order now? | Inferred |
| Q6 | Subject name from the order? | Derived |
| Q7 | Timeout in the work order? | Worker default |
| Q8 | Worker fills omitted precision settings? | Yes |
| Q9 | `workorder_ref` in the result schema now? | `provenance.info` |
| Q10 | Google Benchmark counters in scope? | No |
| Q11 | Output: per-invocation directories? | Yes |
| Q12 | Package schema path `work-order/1/`? | Yes |

New with pyperf:

| | Question |
| --- | --- |
| Q13 | Closed: #35 changes version 1 in place, since it is an unmerged draft |
| Q14 | Closed: `protocol.repetitions.levels` carries processes and values |
| Q15 | pyperf `filter`: reject, or run everything and emit only matches? |
| Q16 | pyperf case list: declared in the order, or an enumeration shim (pyperf offers none)? |
| Q17 | pyperf warmups: observations with `included: false`, or dropped? |
| Q18 | Interpreter: subject configuration or host runtime in `comparison_context`? (Depends on whether CPython is the subject.) |
| Q19 | Dependency pins (for example from `uv.lock`): subject components, environment metadata, or not recorded? |
| Q20 | pyperf's automatic CPU pinning: allow, disable, or record only? |
| Q21 | Timeout as `error`, or `censored` with a lower bound? |
| Q22 | The work order schema is copied into the package as `core/schemas/work-order/1/schema.json`. Copy, symlink, or a packaging step that pulls from `schemas/`? |
| Q23 | `bx run` lives in `worker/cli.py` so #34's `cli.py` stays untouched. Merge them when #34 lands? |

Deferred, not open: skipping execution when identical results already exist
(raised in the #24 review) belongs to the workbench, since the worker is
store-unaware. Context collectors and `.benchx/setup.json` (#31) are
deferred, so `machine/v1` capture is hard-coded.
