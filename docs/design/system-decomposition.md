# System Decomposition

**Status:** Draft for review
**Companion to:** `benchmark-result-schema.md` (the schema), `../user_stories/` (the needs)
**Author:** Rok Mihevc

## 1. Purpose

This document names the components of the continuous benchmarking system and
defines what each one does — functionally, not technologically. It is the map
from the collected user stories to the parts we will design one by one. Each
component gets its own design document later; here every definition is kept
short enough to review at a glance.

Two rules shape the decomposition:

1. **The schema is the only shared language.** Components exchange benchmark
   results, series, and revisions as the schema defines them. A component is
   described by what it produces or consumes in schema terms, never by how
   another component works inside.
2. **Components are separable.** A project must be able to adopt one piece —
   just the local runner, or just the store and views — without the rest.
   The user stories range from a volunteer project with a dozen weekly
   benchmarks to a fleet processing ~100,000 results per day; no single
   deployment shape fits both.

## 2. Overview

```
                 produce results                consume results
  ┌────────────┐  ┌────────────┐   ┌───────┐   ┌────────────┐  ┌──────────┐
  │ Workbench  │  │  Runner +  │   │       │   │ Comparator │  │  Views   │
  │ (local CLI)│─▶│  Adapters  │──▶│ Store │──▶│  Detector  │─▶│  Alerts  │
  └────────────┘  └────────────┘   │       │   └────────────┘  └──────────┘
  ┌────────────┐        ▲          └───────┘
  │ Importers  │────────┼──────────────▲
  └────────────┘        │
                  ┌───────────┐
                  │ Scheduler │  decides what runs, where, when
                  └───────────┘
```

Everything to the left of the store produces schema results; everything to the
right only reads them. The scheduler orchestrates producers but never touches
results itself.

## 3. Components

### 3.1 Result store

**Role:** The system of record for benchmark results.

- Accepts results in the schema's ingest form; validates, normalizes units,
  and stores them idempotently with full provenance.
- Maintains series identity: assigns each result to its series, computes
  fingerprints, and guards immutability of identity.
- Records **continuity events** — a benchmark rename, a machine succession, an
  identity-policy change — so that history survives evolution of the suite and
  the fleet instead of silently fragmenting or silently blending.
- Answers queries: find a series, order its results by revision, retrieve
  observations and provenance, list what exists for a revision or a run.
- Keeps raw observations so better statistics can be applied to old data later.

**Does not:** run anything, compare anything, decide anything. It stores and
serves facts.

### 3.2 Harness adapters

**Role:** Translate one native harness's output into schema results.

- One adapter per harness (Google Benchmark, ASV, JMH, pytest-benchmark, …),
  following the schema's mapping rules: samples become observations, aggregate
  statistics become typed summaries, harness metadata is split into case
  parameters, comparison context, observed context, procedure, and provenance.
- Separates counters that describe the workload (case parameters) from those
  that describe the measurement (procedure).
- Emits one result per quantity: a run that measures wall time, GPU time, and
  peak memory produces one result in each of three series.
- Preserves failure semantics: a failed, skipped, or partially failed
  benchmark becomes an explicit result status, never a silent absence.

**Does not:** execute benchmarks, judge results, or invent metadata the
harness did not report.

### 3.3 Runner

**Role:** Execute benchmark work on one compute node and report what happened.

- Takes a work order — which benchmarks, at which revision or build, with
  which parameters — and carries it out: obtains or builds the target,
  invokes the harness, collects output through the adapter.
- Controls and records the execution environment: thread caps, CPU pinning,
  device selection and synchronization, warmup and JIT state. What it cannot
  control, it records as observed context so no setting is lost from results.
- Captures identity honestly: machine, build configuration, compiler, source
  revision, dirty working tree. A result that cannot state where it came from
  is a defect.
- Behaves identically whether invoked by a person on a laptop or by the
  scheduler on a fleet machine; only precision settings and environment
  strictness differ.

**Does not:** decide what to run or when, store history, or compare results.

### 3.4 Workbench

**Role:** The developer's local interface for one-off benchmarking.

- Runs and compares benchmarks on the developer's own machine, entirely
  offline: current workspace against a baseline build, one build configuration
  against another at the same commit, a checkout against a release tag.
- Saves any run as a self-describing result file and replays it later as a
  comparison target, so expensive baselines are measured once.
- Refuses, or loudly warns about, invalid comparisons: different machine,
  different build configuration, unknown provenance.
- Supports the iteration loop: scoping by filter, quick low-precision runs
  while exploring, higher precision on demand.
- Can promote a kept local result into the result store unchanged — the local
  file and the stored result are the same schema object.

**Does not:** require a server, an account, or any part of the fleet.
It is the runner plus comparator wrapped for human, interactive use.

### 3.5 Scheduler

**Role:** Decide what gets benchmarked, where, and when.

- Turns events into work orders for runners: a merged commit, a request on a
  pull request ("run these suites on my PR"), a cron schedule, a release
  candidate.
- Supports backfill: benchmarking skipped or historical revisions on request,
  including automatic narrowing of a regression range to a culprit commit.
- Manages the queue against a heterogeneous fleet: some benchmarks need
  specific hardware, machines come and go, requests have priorities.
- Reports work-order status — queued, running, finished, failed — so a person
  who asked for benchmarks can see where their request stands.

**Does not:** interpret results. Its output is runs, not verdicts.

**Optional.** A deployment is complete without a scheduler: any person, CI
job, or script may author work orders directly. The scheduler exists for
contention — shared fleets, queues, priorities, automated backfill — and
nothing else in the system depends on its existence.

### 3.6 Comparator

**Role:** Answer "did performance change between A and B?" defensibly.

- Compares two sets of results — contender against baseline — and classifies
  each shared series as improved, regressed, or unchanged, with the evidence
  for the verdict.
- Uses the observations and dispersion the results carry, so the threshold for
  "real change" reflects each benchmark's own noise rather than one flat
  percentage.
- Chooses and checks baselines correctly: a pull request compares against its
  fork point; a release compares against the previous release; mismatched
  identities are reported, not silently dropped from the table.
- Serves every scale of question with the same semantics: two local builds,
  one PR against main, one release against another — so a local verdict and a
  CI verdict can be reconciled instead of contradicting each other.

**Does not:** watch history over time (that is the detector) or decide what a
project does about a change (that is policy, expressed in alerts and review).

### 3.7 Change detector

**Role:** Watch each series' history and find the moments it truly changed.

- Runs continuously over series in the store, flagging step changes and slow
  drifts, calibrated to each series' own noise level.
- Places changes at revisions: its output is "this series changed at (or
  near) this commit," with confidence and supporting evidence, ready for a
  human to act on.
- Respects annotations: an acknowledged, accepted change resets expectations
  going forward instead of firing forever.
- Uses observed context to help separate "the code changed" from "the
  environment changed."

**Does not:** deliver notifications or track who was told; it produces
findings, not messages.

### 3.8 Alerting and annotations

**Role:** Deliver findings where developers already are, and remember what
people decided about them.

- Turns comparator verdicts and detector findings into notifications in the
  project's existing channels — a pull request comment, an issue, a commit
  status — rather than a dashboard someone must remember to check.
- Maintains the alert lifecycle: open, acknowledged, muted, resolved — with
  the decision and its author visible to everyone later.
- Stores annotations on series and revisions ("accepted regression, see
  issue N", "machine misbehaving, results excluded") that views, the
  comparator, and the detector all honor.

**Does not:** compute verdicts; it carries them and records the human
response.

### 3.9 Views

**Role:** Make the store's contents visible without requiring a statistician
or a frontend developer.

- Per-series history charts with revisions, change points, annotations, and
  continuity events marked.
- Comparison views: a PR summary readable at review speed ("these got slower,
  these got faster, the rest are unchanged"), and a release-to-release report
  across all languages and machines.
- Cross-series and parametrized views: the same benchmark across machines or
  architectures on one plot, scaling curves across a parameter, time and
  memory side by side.
- Works from schema queries only, so a project gets useful views by ingesting
  results — with no frontend work of its own.

**Does not:** own any data or compute any verdicts; every number shown is
traceable to stored results.

### 3.10 Importers

**Role:** Carry existing history into the store, once, honestly.

- Implement the schema's migration contract for each source system (ASV,
  Conbench, Codespeed, LNT, …): idempotent, provenance-preserving, explicit
  about what the source lacked rather than inventing it.
- Report identity collisions and unit conflicts for review before writing.

**Does not:** run continuously; live traffic goes through adapters.

## 4. What the stories demand of each component

Traceability, in brief — the pains each component exists to remove:

| Component | Pains it answers (from the user stories) |
|---|---|
| Result store | history fragmenting on renames, machine swaps, parameter changes; raw samples discarded; no provenance for pasted numbers; failed vs. skipped vs. missing indistinguishable |
| Harness adapters | seven languages landing in seven shapes; statistics lost in translation; workload parameters buried in counter blobs |
| Runner | environment settings set by hand and recorded nowhere; GPU sync and JIT warmup done manually; build configuration invisible in results |
| Workbench | local comparisons that cannot describe themselves; baselines rebuilt for every question; results printed and lost; stale-binary comparisons going unnoticed; no path from local finding to project history |
| Scheduler | hours-long queues with no visibility; benchmark requests learned by word of mouth; culprit-narrowing by manual re-runs; no `/perf`-style trigger |
| Comparator | flat 5% thresholds on 0.2%-noise benchmarks; wrong baselines; local and CI verdicts that disagree; incomparable results compared silently |
| Change detector | single noisy results raising alerts while slow drifts raise none; detection blind to each benchmark's own noise |
| Alerting & annotations | alerts firing forever after accepted changes; no mute or acknowledge; decisions living in people's heads |
| Views | no release-vs-release view; no cross-machine or scaling plots; custom views requiring frontend work |
| Importers | years of ASV/Conbench history stranded in old systems |

## 5. Boundaries of the system

Not components of this system:

- **Benchmark suites themselves.** Projects own their benchmarks and write
  them in their language's native harness; the system meets them at the
  adapter.
- **CI platforms and machine provisioning.** The scheduler integrates with
  them; it does not replace them.
- **Decision policy.** What counts as an acceptable regression is a project
  decision, recorded via annotations — never baked into results or identity.

## 6. Open questions

1. *Resolved:* comparator and change detector are two components sharing a
   statistics library, not a shape (see `comparator.md`).
2. *Resolved:* the store records identity; the comparator enforces
   comparability (see `comparator.md` §3).
3. Is the workbench a distinct deliverable or a thin skin over runner +
   comparator? Treated here as a skin with its own UX obligations.
4. How thin can the minimum viable deployment be? Partially answered: the
   scheduler is optional, and runner + adapter + result files form a complete
   producing deployment; the open part is the minimum consuming side.

Each component's design document will open by restating its role from this
page and must not widen it without amending this document.
