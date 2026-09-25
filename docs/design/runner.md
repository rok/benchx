# Runner Architecture

**Status:** Draft for review
**Companion to:** `system-decomposition.md` §3.3, `benchmark-result-schema.md`

## 1. Role

The runner executes benchmark work on one compute node and reports what
happened as schema results. It is the only component that touches real
hardware. It does not decide what to run, store history, or judge outcomes.

One runner design serves both deployment shapes: invoked by the scheduler on a
fleet machine, or by a person (via the workbench) on a laptop. The pipeline is
identical; only precision settings and environment strictness differ.

## 2. Principles

1. **A run is described before it is executed.** Every run starts from an
   explicit, self-contained **work order**; nothing is inferred from leftovers
   on the machine. What the work order doesn't specify, the runner records.
2. **Honest identity or no result.** A result that cannot state its source
   revision, build configuration, and machine identity is a defect. Dirty
   working trees, unknown builds, and stale binaries are detected and marked,
   never silently measured.
3. **Control what you can, record what you can't.** Environment settings the
   runner can enforce (thread caps, pinning, device selection) it enforces and
   records; conditions it cannot control (kernel, load, temperature) it
   snapshots as observed context.
4. **The harness measures; the runner surrounds.** Measurement itself belongs
   to the native harness and its adapter. The runner prepares, invokes,
   captures, and reports.
5. **Every outcome is a result.** Build failure, harness crash, timeout, or
   explicit skip each produce a schema result with the corresponding status —
   absence of a result always means "was not attempted."
6. **Two interfaces, both documents.** The runner touches the rest of the
   system only through two contract artifacts: work orders in, results out.
   No component is required at either end — a scheduler, a CI job, or a
   person may author work orders; results may go to a live store, a local
   file, or both. The runner never knows or cares which.

## 3. The work order

The runner's single input. It names:

- **what** — benchmark suite(s) and case filters, and the quantities to collect;
- **at what** — the target: a source revision to build, an existing build to
  use, or a prebuilt artifact;
- **how** — build configuration, harness precision settings (repetitions,
  minimum time), and the environment policy to enforce;
- **for whom** — provenance to thread through: run key, requester, reason.

A work order is a **versioned, self-contained, replayable contract
artifact** — the same design discipline as the result. Results reference the
work order that produced them in provenance, so any run is reproducible from
its stored order. Work orders come from a scheduler, a CI job, the workbench,
or a shell; the runner does not care which.

## 4. Run pipeline

Each work order flows through five stages:

```
resolve target → prepare environment → execute → capture context → emit results
```

1. **Resolve target.** Obtain the code to measure: check out and build a
   revision, verify an existing build directory (recording its configuration
   and detecting staleness), or accept a prebuilt artifact. Builds are cached
   and reusable so baselines are not rebuilt per question.
2. **Prepare environment.** Apply the environment policy: thread and affinity
   caps, accelerator selection, warmup/JIT requirements, quiescence checks.
   Policies are per-project and per-node; a laptop policy checks little, a
   tuned bare-metal policy checks much. Anything the policy demands but the
   node cannot deliver fails the run visibly.
3. **Execute.** Invoke the native harness through its adapter, scoped by the
   work-order filters, with the requested precision.
4. **Capture context.** Assemble identity and conditions: machine and
   environment identity, build configuration, source revision (including
   dirty state), and the observed-context snapshot (kernel, versions,
   frequency governor, load, temperature where available).
5. **Emit results.** Combine adapter output with captured context into schema
   results — one per case × quantity, including failures and skips — and
   deliver them: to the store's ingest API, to a local result file, or both.

Stages are separable: "resolve target" without "execute" is a build; a saved
result file replayed as a comparison baseline skips straight to emit.

## 5. Environment policy

The named, versioned set of demands a run must satisfy, referenced from the
work order:

- what to **enforce**: thread caps, CPU pinning, governor, device selection,
  synchronization discipline for accelerators;
- what to **verify**: quiescence, required hardware present, clean tree;
- what to **record**: everything enforced and verified, plus the
  observed-context snapshot.

The policy's identity-relevant parts land in the result's comparison context
and environment identity, so "measured under policy X" is visible and
comparable. Loosening or tightening a policy is therefore a series-splitting
event, not a silent change.

## 6. Failure handling

- Build failure, harness error, timeout: an `error` result carrying logs in
  provenance.
- Partial suite completion: per-case results for what ran, `error`/`skipped`
  for what did not — never a truncated table.
- Environment policy unsatisfiable: the run is refused before execution, with
  the reason reported to whoever ordered it.
- The runner is stateless between work orders except for declared caches
  (builds, checkouts); a crashed runner loses at most the in-flight run.

## 7. Boundaries

- **Not the scheduler:** takes orders, never creates them.
- **Not the adapter:** harness knowledge lives in adapters the runner
  invokes. An adapter has two halves: **driving** (translating work-order
  scoping and precision into the harness's own invocation) and
  **translating** (native output plus supplied context into schema results).
  The translating half stands alone, so importers and CI users can apply the
  same mapping without a runner.
- **Not the comparator:** emits results, never verdicts.
- **Not a provisioner:** runs on machines it is given; fleet membership and
  machine lifecycle belong to operations and the scheduler.
- **Not a queue:** by explicit decision, the runner holds no intake queue —
  it executes one work order per invocation, and buffering, ordering, and
  serializing pending work belong to whoever submits it (scheduler, CI, or
  person).

## 8. Open questions

1. Does the runner own build caching policy, or is a build a distinct
   cacheable artifact the scheduler can place on nodes?
2. How much of the environment policy vocabulary is core versus per-project
   plugin (e.g. accelerator synchronization differs per backend)?
3. Is "verify an existing build directory" fully solvable, or do we accept
   best-effort staleness detection with prominent marking?
