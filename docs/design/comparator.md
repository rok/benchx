# Comparator

**Status:** Draft for review
**Companion to:** `system-decomposition.md` §3.6, `benchmark-result-schema.md`

## 1. Role

The comparator answers "did performance change between A and B?" defensibly.
It takes two sets of results — contender and baseline — and classifies each
shared series as improved, regressed, unchanged, or indeterminate, with the
evidence for every verdict. It is pairwise and on-demand; watching history
over time is the change detector's job (a separate component sharing only a
statistics library).

## 2. Inputs

An explicit pair: contender and baseline, each identified by revision, run
key, or a result file. The comparator resolves each side to a set of results
and pairs them by series identity. Baseline *selection* — fork points,
nearest benchmarked ancestor, previous release — is a layer on top that
produces an explicit pair; the core comparator never inspects git topology.

Sides may come from the store, from result files, or one of each: a local
measurement and a stored baseline compare exactly like two stored runs.

## 3. Comparability guard

The comparator is where incomparable results are refused. Two results are
compared only when they belong to the same series — same case, quantity,
estimator, comparison context, and environment identity. Anything else is
reported, never silently dropped:

- series present on only one side are listed with counts ("5 only in
  baseline, 2 only in contender"), so a stale binary or renamed benchmark is
  visible instead of quietly shrinking the table;
- near-misses (same case and quantity, different environment or context) are
  reported as *incomparable* with the differing fields named;
- an explicit override may compare across a named identity difference, and
  the output then carries that caveat permanently.

The store records identity; the comparator enforces it.

## 4. Verdicts

Per shared series, using the observations both sides carry:

- **Effect**: relative change of the two estimates.
- **Noise**: pooled dispersion estimated from both sides' observations; when
  observations are absent, from producer-supplied precision statistics; when
  neither exists, noise is unknown.
- **Verdict**: the change is real when |effect| exceeds *k* × noise, with
  *k* a project-configured multiplier. Real changes are labeled improved or
  regressed using the quantity's direction metadata when present, otherwise
  just *changed*.
- **Indeterminate**: unknown noise, or too few replicates for the quantity's
  nature. A single observation of a quantity declared deterministic (§4.4 of
  the schema) is complete evidence — for those, any difference beyond exact
  equality is real. A single observation of a noisy quantity is not.

This dispersion-scaled rule is deliberately the simplest statistic that
respects each benchmark's own noise — a 2% change on a 0.2%-noise benchmark
is real, a 2% change on a 5%-noise benchmark is not — replacing the flat
percentage threshold every user story complains about. Stronger machinery
(significance tests, minimum-effect filters, multiple-comparison control)
can replace the rule later without changing the contract around it.

## 5. Output

A **comparison document**: machine-readable, self-describing, listing per
series the verdict, effect, noise, replicate counts, and estimates, plus the
unmatched and incomparable sections from §3. Renderable as the reviewer-speed
summary ("these got slower, these faster, the rest unchanged, these could
not be compared") and consumable by alerting or CI gates. Like the result
document, it references the inputs that produced it and is reproducible from
them.

## 6. Boundaries

- **Not policy:** *k* and any gating decisions are project configuration;
  the comparator reports, humans and policy decide.
- **Not the detector:** no history, no drift, no change points.
- **Not a data source:** every number in the output is traceable to input
  results.

## 7. Open questions

1. How are multi-run baselines (pooling several baseline runs) folded into
   the pair model?
2. Does the comparison document get stored and referenced (e.g. by alerts),
   or recomputed on demand?
