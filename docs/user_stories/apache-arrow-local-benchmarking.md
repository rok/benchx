# Apache Arrow local benchmarking user stories

**Project:** [Apache Arrow](https://github.com/apache/arrow) — C++ core and the
bindings built on it.
**Current benchmarking setup:** `archery benchmark`, the benchmarking front-end
that ships in the Arrow repository (`dev/archery`), run by hand on a
contributor's own machine against locally configured CMake build directories.
CI shares only half of this: Conbench's `ArcheryAdapter` runs `archery
benchmark run` to produce the C++ micro-benchmark results, then compares them
server-side. `archery benchmark diff` — the comparison described here — runs
nowhere but on developer machines, and its results are discarded.
**Contact:** Raúl Cumplido

> Companion to [`apache-arrow.md`](apache-arrow.md), which covers the
> continuous side: Conbench, arrow-benchmarks-ci, and the dedicated fleet. That
> document describes how Arrow *tracks* performance. This one describes how
> Arrow contributors actually *investigate* it day to day, which is a different
> workflow with different failure modes and no persistence at all.

## Who uses benchmarks here

- **C++ contributors** — testing whether a kernel or algorithm change helped,
  usually many times in a row, before anything is pushed.
- **Build and packaging maintainers** — deciding which compile-time options and
  hardening flags to enable by default, and needing to know what each costs.
- **Reviewers** — reproducing a claim made in a pull request description on
  their own hardware.
- **Release managers** — spot-checking a release candidate against the previous
  release without waiting on fleet capacity.

## The tool surface being described

Everything below is `archery benchmark`, which has three subcommands. This
section exists so the stories can refer to concrete invocations; it is meant to
grow as we cover more of the command surface.

| Subcommand | What it does |
|---|---|
| `archery benchmark list [<target>]` | Enumerate benchmarks in a target. |
| `archery benchmark run [<target>]` | Run one target's suites and report or save results. |
| `archery benchmark diff [<contender> [<baseline>]]` | Run two targets and print a comparison table. |

A **target** is one of four things, and this flexibility is the tool's main
strength:

- a **CMake build directory** (`/tmp/bench-plain`) — used as-is;
- a **git revision** (`HEAD~1`, a tag, a branch) — cloned into a temporary
  directory and built from scratch, optionally kept with `--preserve`;
- the literal token **`WORKSPACE`** — the current checkout, no clone;
- a **saved results file** from an earlier `archery benchmark run --output` —
  replayed rather than recomputed.

Selected options that matter to the stories: `--benchmark-filter=<regex>` and
`--suite-filter=<regex>` to scope the work, `--repetitions=<n>` (default 1 for
C++) and `--repetition-min-time=<seconds>` for precision, `--threshold=<f>`
(default `0.05`) for the regression verdict, `--cc` / `--cxx` / `--cxx-flags`
and `--cmake-extras` when archery does the building, and `--no-counters` to
suppress the counters column.

## Stories

### Measure what a build option costs

> As a build or packaging maintainer, I want to measure the performance cost of
> a compile-time option against the same commit built without it, so that I can
> decide whether to enable it by default and defend that decision.

**Today:** Configure two build directories from one source tree, build the same
benchmark target in each, and let archery run and compare the two binaries. It
does not configure anything itself in this mode; it invokes the build system on
each directory (a no-op when already built) and then runs what it finds.

Workflow sketch, measuring `-DARROW_HARDENING=ON` on Arrow's `take` kernel for
chunked strings:

```console
$ cmake -S cpp -B /tmp/bench-plain    -GNinja -DCMAKE_BUILD_TYPE=Release \
      -DARROW_BUILD_BENCHMARKS=ON -DARROW_COMPUTE=ON
$ cmake -S cpp -B /tmp/bench-hardened -GNinja -DCMAKE_BUILD_TYPE=Release \
      -DARROW_BUILD_BENCHMARKS=ON -DARROW_COMPUTE=ON -DARROW_HARDENING=ON

$ cmake --build /tmp/bench-plain    --target arrow-compute-vector-selection-benchmark
$ cmake --build /tmp/bench-hardened --target arrow-compute-vector-selection-benchmark

$ archery benchmark diff \
      --benchmark-filter=TakeChunkedChunkedStringMonotonicIndices \
      --repetitions=10 \
      /tmp/bench-hardened /tmp/bench-plain
```

The first positional argument is the contender and the second the baseline. The
reported metric here is items/sec, so a positive change means the contender —
the hardened build — is faster. Roughly three minutes later:

```
Non-regressions: (5)
                                            benchmark          baseline         contender  change %
TakeChunkedChunkedStringMonotonicIndices/4194304/1000 43.013M items/sec 43.340M items/sec     0.761
  TakeChunkedChunkedStringMonotonicIndices/4194304/10 42.920M items/sec 42.973M items/sec     0.124
   TakeChunkedChunkedStringMonotonicIndices/4194304/0 48.697M items/sec 48.710M items/sec     0.027
   TakeChunkedChunkedStringMonotonicIndices/4194304/1 70.518M items/sec 70.366M items/sec    -0.216
   TakeChunkedChunkedStringMonotonicIndices/4194304/2 45.003M items/sec 43.922M items/sec    -2.403
```

**Pain:** Four separate things go wrong in that output.

- **The comparison does not describe itself.** Archery received two opaque
  directory paths. Nothing in the result records that this measured hardening
  on against hardening off, which compiler was used, or which commit was built.
  That knowledge exists only in the operator's shell history, so the table
  cannot be archived, shared, or re-derived from its own contents.
- **What ran is decided by leftovers.** Suites are discovered by globbing
  `*-benchmark` in each build directory, and any benchmark present on only one
  side is dropped from the table without a count, so a stale binary from an
  earlier build quietly changes what is being compared.
- **The verdict is wrong.** Every row is filed under "Non-regressions" because
  the default threshold is a flat 5% applied to medians. The underlying harness
  measured a coefficient of variation of 0.17–0.37% on these very runs and
  reported it, and archery discarded it. The -2.4% row is more than ten times
  that noise floor — a real and repeatable cost of hardening on the 50%-null
  case — and the tool says it is fine. A fixed percentage cannot be right for
  both a 0.17% benchmark and a noisy one.
- **The parameters are not interpretable.** `/4194304/2` means 50% nulls and
  `/4194304/1000` means 0.1% nulls. That is only recoverable from Google
  Benchmark user counters, which archery prints as an unstructured blob mixed
  with measurement bookkeeping such as `repetition_index`. Nothing distinguishes
  a counter that describes the workload from one that describes the run.
- **The answer is then discarded.** There is no way to keep this comparison and
  ask the same question after the next release, to see whether the cost of
  hardening grew.

### Iterate on a kernel without touching CI

> As a C++ contributor, I want to test a performance idea against a baseline
> build on my own machine and get an answer in minutes, so that I only spend
> shared fleet time once I believe the change is worth reviewing.

**Today:** Keep a baseline build directory around, rebuild only the target under
development, and diff the two directories. Nothing unrelated is rebuilt and no
fleet capacity is consumed. Scoping is essential: this build exposes about 3,500
benchmarks, so `--benchmark-filter` is not a convenience but a requirement.
**Pain:** The local answer and the eventual CI answer share a measurement
producer but nothing else. Locally, `archery benchmark diff` takes medians and
applies a flat percentage threshold; in CI, Conbench receives the same runner's
output and applies its own statistics. The precision differs too: CI's
`cpp-micro` group runs 6 repetitions at `--repetition-min-time=0.05`, while a
careful local run at the harness default of 0.5s does roughly ten times the work
per point. So a local run can easily be the *more* precise of the two, and
reconciling the two verdicts is a matter of judgement rather than something the
tooling establishes. Local results also never reach the place where the project
keeps its performance history, so the exploration behind a merged change is lost
even when the change lands.

### Compare against a previous revision or release

> As a contributor or release manager, I want to compare my current checkout
> against a git revision or a release tag, so that I can answer "is this slower
> than it was?" without provisioning anything.

**Today:** Archery accepts git revisions directly as targets and will clone and
build them itself:

```console
$ export LAST=$(git tag -l "apache-arrow-[0-9]*" | sort -rV | head -1)
$ archery benchmark diff --suite-filter="^arrow-compute-aggregate" \
      --benchmark-filter="(Sum|Mean)Kernel" WORKSPACE "$LAST"
```

**Pain:** Each such comparison rebuilds Arrow from scratch in a temporary
directory, which dominates the runtime and is repeated every time the question
is asked. The build configuration archery chooses for the cloned revision is its
own default, which is not necessarily the configuration of the workspace it is
being compared against — so the comparison can silently differ in more than the
source revision. The `--preserve` flag mitigates the rebuild cost only if the
operator remembers to use it and then manages the preserved directories by hand.

### Reuse a measurement instead of repeating it

> As a contributor, I want to measure an expensive baseline once and compare
> several candidates against it, so that I am not paying for the same baseline
> run over and over.

**Today:** `archery benchmark run --output=run.json <target>` saves results, and
`archery benchmark diff WORKSPACE run.json` compares against the saved file
without recomputing it.
**Pain:** The saved file records the measurements but not the conditions that
produced them — no machine identity, no build configuration, no timestamp that
the comparison checks. Nothing prevents diffing today's workspace against a
baseline captured last month on a different machine, and the output gives no
indication that this happened. The two output formats also diverge confusingly:
`--output` writes the human-readable table, while machine-readable JSON requires
`archery --quiet benchmark diff > result.json`.

### Get results out into something that keeps them

> As a contributor who has just found something real locally, I want to keep the
> measurement, so that the next person asking the same question starts from my
> answer instead of repeating the work.

**Today:** Almost nothing, and what exists is out of reach. `archery benchmark
run` does capture run metadata — timestamp, full command line, platform, core
count — expressly so that runs are hard to confuse, but only when the target is
a git revision, and into a temporary directory that is deleted unless
`--preserve` is passed. `diff` never captures it at all. In the build-directory
workflow the comparison is simply printed and lost, and promoting a local
finding into Arrow's tracked history means re-running it through the CI pipeline
on fleet hardware, which measures a different build in a different environment.
**Pain:** The project's two benchmarking modes share a tool but not a result
model, so there is no path from "I measured this on my workstation" to "the
project knows this." Every one-off investigation starts from zero.

## What must not break

- Comparing two already-built build directories directly, with no rebuild and
  no git revision required for either side.
- Targets being interchangeable: a build directory, a git revision, the current
  workspace, or a saved results file, in any combination.
- Scoping a run by suite and benchmark regex, which is what makes a ~3,500
  benchmark build usable at all.
- Running entirely offline on a developer machine, with no server, account, or
  network dependency.
- Replaying a saved baseline instead of recomputing it.

## Wishes

- Build configuration — compile flags, feature toggles, compiler and version —
  captured as recorded, first-class identity, so that "hardened versus plain" is
  a comparison the system understands rather than two directory paths.
- Comparing two configurations at the same commit, not only one configuration
  across commits, and being able to track that difference over time.
- Using the dispersion the harness already reports instead of a single fixed
  percentage threshold, so that a 2% change on a 0.2% benchmark is not filed
  under "non-regressions".
- Keeping harness counters that describe the workload separate from those that
  describe the measurement, and treating the former as case parameters.
- A guard against comparing measurements that were never comparable — different
  machine, different build configuration, different tool version.
- Promoting a local one-off comparison into tracked history without rewriting it
  for a different system.
- One output format that is both readable and machine-parseable, rather than
  choosing between them with an unrelated flag.

## Scale and constraints

- A benchmarks-enabled Arrow C++ build exposes roughly 3,500 individual
  benchmarks across on the order of 40 suite binaries; nobody runs them all
  locally.
- A single filtered family — one benchmark, five parameter values, ten
  repetitions, two builds — takes about three minutes. Useful precision costs
  minutes, not seconds.
- Measurements are taken on unreserved developer hardware: laptops and
  workstations doing other things at the same time. The noise floor is a
  property of the moment, not of the machine.
- Building both sides of a build-option comparison from scratch is hours, so
  build directories are long-lived and reused, and drift between them is a real
  hazard.
- Results are currently transient by construction. Any future system must not
  assume a local run is worth persisting, but must make it possible.
