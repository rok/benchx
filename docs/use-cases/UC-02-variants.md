# Benchmark Use Case Template

---

## UC-02: Fixed branch and environment invariants

| | |
|---|---|
| **Status** | draft |
| **Owner** | MarcoGorelli |
| **Last updated** | 2026-02-09 |
| **Related** | |

### 1. Summary

A project would like to compare two functions, within the same branch, in exactly the same environment, and check that one is never (much) slower than the other one.

For example, check that `func_1` is always faster than `func_2`, or at least no less than 5% slower.

### 2. Motivation

Several projects want to ensure that certain invariants remain true over time. For example:

- [Narwhals](https://github.com/narwhals-dev/narwhals) wants to compare the following and check that the former is never much slower than the latter:
  - Run a function in pandas natively.
  - Run a function in Narwhals (backed by pandas).
- [Polars](https://github.com/pola-rs/polars/pull) wants to check that some operations are never slower than their Python standard library or pandas counterparts.

Motivation:

- For Narwhals, they want to ensure that, if a project switches from being pandas-specific to being dataframe-agnostic via Narwhals, then the overhead should be either negative or very small. Example of where this was brought up and measured: [Plotly: chart smarter, not harder](https://plotly.com/blog/chart-smarter-not-harder-universal-dataframe-support/).
- For Polars, they want to ensure that anyone switching over from pandas has a positive experience performance-wise. Example issue: [dt.truncate is 3-4x slower in polars compared to pandas](https://github.com/pola-rs/polars/issues/16531).

### 3. Actors and trigger

- **Actor:** contributor or maintainer.
- **Trigger:** manual command or per-PR CI (depending on how slow these tests are to run).
- **Frequency:** per commit if the tests aren't too slow, else per release (or when triggered manually).

### 4. Workflow sketch

Something like
```
$ benchx run --compare-variants pandas_truncate.py polars_truncate.py dt_truncate

role              benchmark_name   time    vs. baseline
baseline          dt_truncate      1.20s   -
variant           dt_truncate      1.24s   +3.3%   (within a 5% margin — OK)
```

If the difference was greater than some threshold, say here 5%, this would be flagged as an error.
It's up to the maintainers whether this blocks merge.

### 5. Study design

The core of the use case. Every record is a measurement plus coordinates:

- **Code identity** - benchmark ID, parameters
- **Code version** - commit, patch/variant label, build configuration
- **Environment** - machine, OS, CPU, BLAS vendor and threading, tuning state
- **Execution context** - session, round, interleave position, instrument

State for each:

| Coordinate | Role | Notes |
|---|---|---|
| Code identity | varying | |
| Code version | controlled | |
| Environment | controlled | |
| Execution context | controlled | |

- **Varying** - the independent variable; identifying fields must be present and
  *distinct* across records being compared.
- **Controlled** - must be present and *equal* across records being compared.
- **Free** - genuinely irrelevant to the comparison's validity. Justify each one;
  "free" is where invalid comparisons hide.

Code identity varies within each run (we are comparing two functions). Code environment
may vary across runs.

### 6. Measurements

| Measure | Instrument | Unit | Direction |
|---|---|---|---|
| wall time | pyperf | s | lower is better |
| peak memory (optional) | memray | bytes | lower is better |

- **Raw samples retained?** yes
- **Is the instrument available in every environment this use case spans?**
  It should be, yes.

### 7. Comparison semantics

- **What comparison is valid?** paired within each session
- **Estimator:** minimum is usually recommended
- **What counts as a real difference?** A difference which exceeds a user-defined threshold.
- **Expected noise floor** the difference between runs may vary across environments. But within
  each environment, the invariant should hold.

### 8. Schema implications

- **Profile:** new. fixed-branch-and-environment-invariants
- **Fields required beyond the core:**
  - "role": {"variant", "baseline"}.
  - "session_id": str
- **Fields required to be *absent* or explicitly null:** none
- **New fields not currently in the schema:**
  - "role": Enum('variant', 'baseline'). Defined by who writes the benchmark.
- **Comparability key:** same branch and environment.
- **Validation invariants:** branch and environment.
- **Conflicts with existing use cases:** other comparisons don't have "role".

### 9. Storage and lifecycle

tbd

### 10. Degenerate and failure modes

We are comparing "variant" vs "baseline", and checking that "variant" is never much slower than "baseline".

If either one fails to run, the benchmark should be deemed to have failed, as they should both pass.

- What happens when a *controlled* coordinate silently isn't constant? (Machine
  thermal state drifts; BLAS changes under an unpinned environment; the working tree
  is dirty.) Is that detectable from the record alone, or does bad data enter the
  store looking valid? This shouldn't affect the data, as that should be constant
  across "variant" and "baseline". Thermal state drifts may be an issue.
- What happens with missing or partial data - one variant failed, a machine dropped
  out, an instrument is unavailable? It should be re-run.
- What is the worst wrong conclusion someone could draw, and does the schema make it
  harder or easier to draw? One may incorrectly draw the conclusion that "variant" is
  actually significantly slower than "baseline".

### 11. Non-goals

Cross-branch or cross-environment comparisons.

### 12. Open questions
