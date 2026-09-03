# Minimal Prototype Scope

**Status:** Agreed scope for a first prototype
**Companion to:** all design docs; decisions recorded 2026-08-30.

## 1. The slice

A thin end-to-end path proving every core contract once:

```
Google Benchmark binary
  → runner (existing build dir only) → result documents (files)
  → file-drop ingest → store (validated, idempotent, auto-created entities)
  → queries (list series, series history)
  → comparator (explicit pair, dispersion-scaled verdicts)
  → comparison document (JSON + readable table)
```

## 2. Component scope in the prototype

| Component | In prototype | Deferred |
|---|---|---|
| Runner | execute an existing build directory's benchmarks per a work order; capture identity and observed context | building revisions, environment policy enforcement beyond recording |
| Adapter | Google Benchmark JSON → schema results (both halves: drive filters/repetitions, translate output) | all other harnesses |
| Store | ingest per §5.4 contract (validated+durable ack, auto-create with unit-conflict rejection, idempotency); queries: list series, ordered history, get result | continuity events, quarantine workflow, artifact storage |
| Comparator | explicit pair, comparability guard, dispersion-scaled verdicts, comparison document | baseline selection layers, multi-run pooling |
| Work order / result / comparison documents | all three as versioned file formats | — |

**Out entirely:** scheduler, change detector, alerting, views beyond query
output, profiles, importers, workbench packaging (the prototype's CLI *is*
the proto-workbench).

## 3. Success criteria

1. The same result document is valid as a local file and as an ingest
   payload, unmodified (promotion is a copy).
2. Re-ingesting a delivered directory is a no-op (idempotency observable).
3. A quantity arriving with a conflicting unit is rejected with the
   machine-readable taxonomy code.
4. A benchmark present on only one side of a comparison appears in the
   unmatched section, never silently dropped.
5. A small real change on a quiet benchmark is flagged while a larger swing
   on a noisy one is not — demonstrated on real Google Benchmark output with
   repetitions.
6. Every result traces to its work order; every verdict traces to its input
   results.

## 4. Decisions locked for the prototype

- Ingest acknowledgment = validated and durable (§5.4).
- Entities auto-create; unit conflicts reject (§5.4).
- Batches are per-result, non-atomic (§5.4).
- Baseline is an explicit pair; selection logic layers on later.
- Verdict = dispersion-scaled threshold, k project-configured.
- Comparability guard lives in the comparator.
- Comparator and change detector remain separate components.
