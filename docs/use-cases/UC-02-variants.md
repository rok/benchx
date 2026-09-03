## UC-02: Fixed branch and environment invariants

| | |
|---|---|
| **Status** | draft |
| **Owner** | MarcoGorelli |
| **Last updated** | 2026-09-03 |
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
$ benchx compare-variants --baseline pandas_truncate.py --variant polars_truncate.py --name dt_truncate --rounds 5

role              benchmark_name   time     vs. baseline
baseline          dt_truncate      120 ns   -
variant           dt_truncate      124 ns   +3.3%   (within a 5% margin — OK)
```

After the rounds are run (interleaved), the minimum for each role is reported on.
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

Code identity varies within each run (we are comparing two functions). Everything else stays constant. Variant and baseline should be interleaved across multiple rounds per session so that per-session drift affects both roles equally.

### 6. Measurements

| Measure | Instrument | Unit | Direction |
|---|---|---|---|
| wall time | pyperf | ns | lower is better |
| peak memory (optional) | memray | bytes | lower is better |

- **Raw samples retained?** yes.
- **Is the instrument available in every environment this use case spans?**
  It should be, yes.

### 7. Comparison semantics

- **What comparison is valid?** within each session, the minimum timing per role is compared.
- **Estimator:** minimum is usually recommended
- **What counts as a real difference?** If `variant_timing > baseline_timing * (1+threshold)`
- **Expected noise floor** this depends on the code being benchmarked, but `threshold` should be set to account for that.

### 8. Schema implications

- **Profile:** new. fixed-branch-and-environment-invariants
- **Fields required beyond the core:**
  - "role": {"variant", "baseline"}.
  - `interleave_position`: obligatory (can't be null)
- **Fields required to be *absent* or explicitly null:** none
- **New fields not currently in the schema:**
  - "role": Enum('variant', 'baseline'). Defined by the caller (`--baseline` / `--variant`).
- **Comparability key:** same `session_id`, same `benchmark_name`, minimum timing across rounds.
- **Validation invariants:**:
  - For any `session_id` and `benchmark_name`, `role="baseline"` and `role="variant"` should have equal round counts.
  - Both records share the same commit and environment.
  - `interleave_position` must alternate between the roles.
- **Conflicts with existing use cases:** other comparisons don't have "role".

### 9. Storage and lifecycle

Store roles, session_ids, and timings. Don't store the threshold, as that's a user-policy which may be varied as the user wishes.

Volume storage scales as `2 x n_benchmarks x n_rounds`.

Even though this use case is focused on within-session comparisons, users may still be interested in plotting numbers over time across revisions. Nonetheless, we defer details pertaining to that to a different use case.

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

- Do we need to monitor / capture something like thermal state? Or do we just accept it as noise?
  Does interleaving address it?
- How should these benchmarks be triggered? Per-commit, per-release, per-merge? This feels out-of-scope, the answer is best left to the user to determine.
