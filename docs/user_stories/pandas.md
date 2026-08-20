# pandas user stories

**Project:** pandas, https://github.com/pandas-dev/pandas
**Current benchmarking setup:** On every commit, in CI, a suite of benchmarks is run, but just to test that they run without errors. The contributing guide encourages contributors to run the benchmarks manually, but this isn't enforced. Separately, each commit to `main` is put through a more extensive benchmark suite, which takes several hours (~7). If a performance regression is detected, this is left as a comment on the PR, and can be investigated. Benchmark timings can be viewed at https://asv-runner.github.io/asv-collection/pandas/.
**Contact:** MarcoGorelli

## Who uses benchmarks here

Contributors and reviewers are interested in knowing that their PRs don't degrade performance. Infrastructure operators want benchmarks that can be run reliably, on well-funded infrastructure.

## Stories

> As a contributor or reviewer, I want to know that my work will not meaningfully degrade performance.

**Today:** The full benchmark suite is run once a PR is merged.
**Pain:** Getting signal once a PR has been merged is a bit late. Trying to run the benchmarks yourself is [time-consuming](https://github.com/pandas-dev/pandas/issues/29165) and [noisy](https://github.com/pandas-dev/pandas/issues/23412).

Sometimes, the comments are addressed, e.g. https://github.com/pandas-dev/pandas/pull/65919.

> As a maintainer, I want to know what impact different dependencies or builds will have.

**Today:** Manual testing, if any.
**Pain:** ASV does not allow for this level of customisability, https://github.com/pandas-dev/pandas/issues/55007. Cross-arch comparisons also desired, as is the ability to view the exact dependencies used for a particular run (not currently recorded).

> As a maintainer, I want there to be comprehensive end-to-end testing.

**Today:** Benchmarks only test microbenchmarks (single operations).
**Pain:** Issue related to more realistic end-to-end benchmarks (e.g. excessive internal copying) aren't surfaced.

> As a maintainer, I want it to be easy to trigger a full benchmark run, for example by commenting `/perf`.

**Today:** I either have to wait for a PR to be merged, or ask a contributor to run the benchmarks locally.
**Pain:** The signal may come late, or the noise from running local benchmarks may be unreliable.

Discussion where `/perf` was proposed https://github.com/pandas-dev/pandas/issues/55007#issuecomment-1779858378.

> As a maintainer, I want to be able to access raw benchmark results.

**Today:** Summary statistics are viewable on the asv website.
**Pain:** To get a more complete picture, it may be useful to look at the raw numbers.

> As a maintainer / infra engineer, I want a benchmark suite which is not prohibitively expensive to run.

**Today:** The benchmark suite takes ~7 hours. Some individual tests take >20 seconds.
**Pain:** It's not feasible to regularly run a 7 hour benchmark suite locally, and can it realistically be used to block PRs.

Discussion https://github.com/pandas-dev/pandas/issues/23412

> As a maintainer / contributor, I want to have representative datasets to test with.

**Today:** Benchmarks run with toy datasets which are very artificial.
**Pain:** We don't know how representative the benchmarks are of real datasets.

Discussion https://github.com/pandas-dev/pandas/issues/15911

## What must not break

There are currently several benchmarks that contributors and maintainers use. It's not clear how attached people are to the exact benchmark tests, and whether they need to stay or if they'd be happy to rewrite them from scratch.

## Wishes

- cross-arch comparisons
- dependency tracking, comparisons of different dependencies
- comprehensive end-to-end benchmarks (not just microbenchmarks)
- a benchmark suite which doesn't take hours and could be fast enough to block PRs (https://github.com/pandas-dev/pandas/issues/23412)
- a representative dataset to run benchmarks with
- queryable raw data from benchmark results, rather than just statistical summaries
- ability to trigger benchmarks on a PR with a comment like `/perf`

## Scale and constraints

Current setup takes ~7 hours, which is too long to block PRs.
