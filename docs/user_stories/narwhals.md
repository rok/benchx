# Narwhals user stories

**Project:** Narwhals, https://github.com/narwhals-dev/narwhals
**Current benchmarking setup:** Manually on Kaggle, irregularly
**Contact:** MarcoGorelli

## Who uses benchmarks here

Contributors and reviewers are interested in knowing that PRs don't add
too much overhead. Also, if they modify an algorithm
which Narwhals re-implements (e.g. rolling mean for PyArrow),
they want to know that their implementation doesn't get slower over time.

Downstream users (e.g. Plotly, scikit-learn) want to know that using Narwhals
won't add too much overhead to their own code compared with handling pandas/Polars
support natively themselves.

## Stories

> As a contributor/reviewer, I want to know that a PR doesn't increase overhead too much.

**Today:** If a reviewer suspects that an operation may incur unnecessary overhead, they
  flag it in a review. A Kaggle notebook with some performance comparisons may get run
  (https://www.kaggle.com/code/marcogorelli/narwhals-vs-pandas-overhead-tpc-h-s2).
**Pain:** This is a manual process, and it's also very noisy. Results vary noticeably
  between runs. Furthermore, it's not captured for posterity on GitHub.

Example PRs:
- Reducing overhead based on avoiding copies (this showed up in the Kaggle notebook,
  although it's not captured on GitHub): https://github.com/narwhals-dev/narwhals/pull/2559.
- Improving one small operation, measured with a micro-benchmark (and `timeit`): 
https://github.com/narwhals-dev/narwhals/pull/1276.

> As a downstream library, I want to know that adopting Narwhals won't result in extra overhead.

**Today:** I run my existing benchmarks with and without Narwhals. If they're good,
  I start using Narwhals.
**Pain:** I won't maintain two different versions of my library (one with and one without Narwhals).
  So, just because overhead is low now, doesn't mean it will stay low forever.

Example: Plotly write about the performance benefits of switching to Narwhals: https://plotly.com/blog/chart-smarter-not-harder-universal-dataframe-support/.

However, the old pandas-only code paths are not kept up to date, so if these numbers vary over time, it can be difficult to disentangle whether it's due to their own internal logic having changed, changes in Narwhals, or changes in pandas / Polars.

## Wishes

A way for a downstream library to know that the overhead of using Narwhals (compared with their old
pandas-specific paths) will stay low. Without them maintaining two versions of their library
(one with, one without Narwhals) I can't think of how to achieve this, but wanted to capture it anyway.

What I think is achievable would be to benchmark some tests (e.g. TPC-H queries) in pandas-native and
compare them with Narwhals paths, and check that the overhead does not increase over time. Something like
that, for each PR, we a notification telling us "this PR does not meaningfully alter overhead for any backend",
or "this PR adds 20% overhead for the pandas backend".

Discussion around benchmarking in Narwhals: https://github.com/narwhals-dev/narwhals/issues/805. Some points:
- codspeed evaluated, but not used (Polars removed it, Itamar's comment about limited usefulness for non-algorithmic benchmarking)
- full TPCH even at just 0.25 scale run can take 40 minutes in CI, which is too long
- maybe, only run based on trigger (comment or label) rather than every PR

## Scale and constraints

A common issue we face is that pandas often makes unnecessary copies (especially before version 3.0).
We don't need to run on huge data, but it needs to be large enough that the cost of doing an extra copy
of a pandas Series is noticeable among the rest of the noise.

