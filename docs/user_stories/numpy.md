# NumPy user stories

**Project:** [NumPy](https://github.com/numpy/numpy) - fundamental
n-dimensional array library for Python
**Current benchmarking setup:** An ASV benchmark suite is run locally
as needed
**Contact:** Maanas Arora

## Who uses benchmarks here

- **Contributors** and **Reviewers**: check PRs for regressions and
(for performance PRs) measure improvements.
- **Maintainers**: track performance regressions over releases as needed.

## Stories

> As a contributor or reviewer, I want to check the performance impact of
> a PR, so that I do not merge a regression.

**Today:** If changes are made that could have performance implications,
the author or reviewer runs potentially impacted `asv` benchmarks against
`main` on their local machine.
**Pain:** The process is currently completely manual and there is no CI.
`asv` benchmarking can be very noisy, especially due to differences between
compilers, hardware, and configurations, but sometimes even during multiple
runs on the same environment. Particularly, comparisons between branches
are unreliable.

> As a contributor or reviewer of a performance improvement, I want to
> measure the performance improvement resulting from the PR, so that
> I can judge its impact and whether it is worth pursuing.

**Today:** The author or reviewer runs relevant `asv` benchmarks in the
NumPy suite locally or (for specialized changes not in the suite) runs
a Python script to measure the improvement with simple tools
e.g. `timeit`, and copies the results (and/or script) into the
PR description or a comment.
**Pain:** Same as above, the process is completely manual; there is no
provenance for the copied results. Python scripts are not a robust
benchmarking system, but are often used because there is limited support
for flexible one-off benchmarking. `asv` benchmarks are also often
unreliable.

> As a maintainer, I want to inspect the performance of `main` over time,
> so that I can identify the source of a regression.

**Today:** There is no remote continuous benchmark history, so when a regression
is suspected, a maintainer manually checks out and benchmarks candidate commits
with `asv`, often using `git bisect` when necessary.
**Pain:** Regressions are easily missed because of no continuous reporting.
Because there is no centralized "source of truth", coordination is expensive.
Bisecting commits with `asv` is slow and noisy.

> As a contributor, I want to configure the environment(s) for a benchmark run,
> including BLAS libraries, SIMD support, and compiler optimization levels,
> so that I can compare benchmarks across configurations.

**Today:** The contributor builds NumPy (often with `spin build`) and selects
different settings or modifies the environment, then runs `asv` on
each environment of interest.
This is repeated once per environment, and the results are compared manually.
**Pain:** The repeated build-benchmark-compare cycle is slow, tedious,
and error-prone.

## What must not break

- On-demand benchmarking with any NumPy build.
- Benchmark comparisons between branches or builds.
- Reproducible and human-readable benchmark outputs.
- Parametrized benchmarks.
- Ability to reuse a shared benchmark suite.

## Wishes

- Better statistical reliability for benchmarking.
- Better provenance and richer metadata for benchmarks.
- Full access to raw benchmarks.
- More flexible automated control over configuration.
- Smooth integration with CI pipelines.
- Flexible one-off benchmarks.

## Scale and constraints

- Benchmarking is currently occasional: usually 1-2 runs of relevant benchmarks
  over the history of a performance-relevant PR, run locally over 1+ machines.
  Usually, 0-3 benchmark runs per week.
- Note for context: there was an initiative by a maintainer to regularly
  upload benchmarks from their machine for regression tracking (now outdated):
  - https://github.com/numpy/numpy/issues/28801
- One other historical initiative (ran between 2016 and 2022):
  - https://pv.github.io/numpy-bench/
  - https://pv.github.io/scipy-bench/ 

