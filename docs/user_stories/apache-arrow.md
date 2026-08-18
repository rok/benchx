# Apache Arrow user stories

**Project:** [Apache Arrow](https://github.com/apache/arrow) — a multi-language
columnar data toolkit (C++, Python, R, Java, JavaScript, Go, Rust, …).
**Current benchmarking setup:** Continuous benchmarking with
[Conbench](https://github.com/conbench/conbench) fed by
[arrow-benchmarks-ci](https://github.com/ursacomputing/arrow-benchmarks-ci):
dedicated physical and cloud machines run benchmark suites on every merged
commit and on request for pull requests; results are stored in a central
Conbench server and alerts are posted back to GitHub.
**Contact:** Rok Mihevc

## Who uses benchmarks here

- **Contributors** — want to know whether their change makes Arrow faster or
  slower before it merges, without learning the benchmarking infrastructure.
- **Reviewers and committers** — want a trustworthy performance signal as part
  of code review.
- **Performance engineers / regression triagers** — watch the main branch for
  regressions, investigate alerts, and find the commit responsible.
- **Benchmark authors** — add and evolve benchmarks in several languages and
  harnesses.
- **Infrastructure operators** — keep a small fleet of benchmark machines
  running and the results trustworthy.
- **Release managers** — want confidence that a release is not slower than the
  previous one.

## Stories

### Ask for benchmarks on a pull request

> As a contributor, I want to request benchmarks on my open pull request with a
> single comment (optionally limited to one language or suite), so that I get a
> performance verdict without setting up hardware or learning the pipeline.

**Today:** Commenting `@ursabot please benchmark` (with optional filters like
language or benchmark name) queues runs on the benchmark machines; results
arrive as a PR comment with links to comparisons against the baseline commit.
**Pain:** Queueing behind other requests can take hours; partial failures are
hard to interpret; the filters and their spelling must be learned by word of
mouth.

### Read a comparison without being a statistician

> As a reviewer, I want a summary that says "these benchmarks got meaningfully
> slower, these got faster, the rest are unchanged," so that I can judge a PR
> without reading hundreds of raw numbers.

**Today:** Conbench compares contender and baseline runs and flags results
whose change exceeds a statistical threshold; the PR comment links to the
comparison page.
**Pain:** The line between real change and machine noise is not always
believable — small true regressions hide below the threshold, and noisy
benchmarks cry wolf, which trains reviewers to ignore the signal.

### Watch the main branch and catch regressions

> As a performance engineer, I want every merged commit benchmarked and an
> alert when a benchmark's history takes a lasting turn for the worse, so that
> regressions are caught within days, not discovered at release time.

**Today:** Merged commits are benchmarked automatically; alerting compares new
results against recent history and posts to GitHub.
**Pain:** A single noisy result can raise an alert while a slow drift over
many commits raises none; after a genuine, accepted change in performance, the
history has to be manually "reset" or alerts keep firing; when several commits
merge between runs, narrowing down the culprit needs manual re-runs.

### Investigate a regression to its cause

> As a performance engineer, I want to open a benchmark's history, see exactly
> when it changed and under what conditions, and drill into the runs around the
> change, so that I can attribute the regression to a specific commit and file
> an actionable issue.

**Today:** Conbench shows per-benchmark history charts with commit links;
missing commits can be benchmarked retroactively to narrow a range.
**Pain:** History silently fragments — a renamed benchmark, a changed
parameter, an upgraded machine, or a new compiler each start a fresh, unlinked
history, and the old one becomes hard to find; telling "the code got slower"
apart from "the machine changed" requires tribal knowledge.

### Keep benchmarks across seven languages

> As a benchmark author, I want to write benchmarks in my language's native
> harness and have the results land in the same place with the same meaning,
> so that Arrow's performance story is visible in one system rather than seven.

**Today:** Language-specific harnesses (C++ Google Benchmark, Python/R
macrobenchmarks, Java JMH, and others) are adapted into a common submission
format.
**Pain:** Each harness reports different statistics and metadata, and some
detail is lost in translation; failed or skipped benchmarks are easy to
mistake for missing ones.

### Evolve benchmarks without losing their past

> As a benchmark author, I want to rename a benchmark or add a parameter
> without discarding years of history, so that improving the suite does not
> cost us our memory of it.

**Today:** Renames and parameter changes effectively start new histories.
**Pain:** This punishes exactly the people who maintain the suite; teams delay
cleanups to avoid losing continuity.

### Operate the fleet without corrupting the data

> As an infrastructure operator, I want to add, upgrade, or retire benchmark
> machines and have the system understand which results remain comparable, so
> that hardware maintenance does not masquerade as performance change.

**Today:** Machines are named and their runs keyed to that name; operators
know from experience which changes break comparability.
**Pain:** An OS upgrade or hardware swap can silently either split history or,
worse, blend incomparable results into one chart; a misbehaving machine's
results have to be spotted and excluded by hand.

### Trust the numbers at release time

> As a release manager, I want to compare a release candidate against the
> previous release across all languages and machines, so that I can state
> confidently in the release notes whether performance improved or regressed.

**Today:** Assembled manually from history charts and comparison pages.
**Pain:** There is no single "release vs release" view; the answer lives in
many charts and in people's heads.

## What must not break

- On-demand PR benchmarking via a bot comment, with filtering.
- Automatic benchmarking of every merged commit on dedicated machines.
- One central place where results from all languages and machines land.
- Comparison against the correct baseline (the PR's fork point, not just the
  latest run).
- Alerts delivered where developers already are (GitHub), not a separate
  dashboard they must remember to check.
- Retroactive benchmarking of skipped commits to narrow a regression range.

## Wishes

- Regression detection that adapts to each benchmark's own noise level instead
  of one global threshold, and that catches slow drifts.
- A way to acknowledge or mute an alert, with the decision remembered and
  visible to others.
- Benchmark renames and machine upgrades treated as first-class events with
  history continuity, instead of silent breaks.
- Distinguishing "the harness failed" from "the benchmark was not run" from
  "the benchmark was skipped on purpose."
- A release-to-release comparison view.
- Keeping the raw per-repetition measurements, so better statistics can be
  applied to old data later.

## Scale and constraints

- Roughly 1,000 results per full run and on the order of 100,000 results per
  day at peak (many languages × machines × parameter combinations).
- History matters for years — regressions are sometimes traced across major
  versions.
- A mixed fleet: bare-metal machines tuned for low noise alongside cloud
  instances; some benchmarks need specific hardware.
- Benchmarks live in several repositories and harnesses; the measured code and
  the benchmark code evolve independently.
