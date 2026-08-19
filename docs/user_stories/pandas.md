# pandas user story

---

# pandas user stories

**Project:** pandas, https://github.com/pandas-dev/pandas
**Current benchmarking setup:** On every commit, in CI, a suite of benchmarks is run, but just to test that they run without errors. Separately, each commit to `main` is put through a more extensive benchmark suite, which takes several hours (~7). If a performance regression is detected, this is left as a comment on the PR, and can be investigated.
**Contact:** MarcoGorelli

## Who uses benchmarks here

Contributors and reviewers are interested in knowing that their PRs don't degrade performance.

## Stories

Use as many as apply. Format:

### Fixes shouldn't regress performance (too much)

> As a contributor or reviewer, I want to know that my work will not meaningfull degrade performance.

**Today:** The full benchmark suite is run once a PR is merged.
**Pain:** Getting signal once a PR has been merged is a bit late. Trying to run the benchmarks yourself is [time-consuming](https://github.com/pandas-dev/pandas/issues/29165) and [noisy](https://github.com/pandas-dev/pandas/issues/23412).

Sometimes, the comments are addressed, e.g. https://github.com/pandas-dev/pandas/pull/65919.

> As a maintainer, I want to know what impact different dependencies or builds will have.

**Today:** Manual testing, if any.
**Pain:** ASV does not allow for this level of customisability, https://github.com/pandas-dev/pandas/issues/55007. Cross-arch comparisons also desired.

> As a maintainer, I want there to be comprehensive end-to-end testing.

**Today:** Benchmarks only test microbenchmarks (single operations).
**Pain:** Issue related to more realistic end-to-end benchmarks (e.g. excessive internal copying) aren't surfaced.

## What must not break

## Wishes

- cross-arch comparisons
- cross numpy version comparisons
- comprehensive end-to-end benchmarks (not just microbenchmarks)
- a benchmark suite which doesn't take hours and could be fast enough to block PRs

## Scale and constraints

Current setup takes ~7 hours, which is too long to block PRs.

