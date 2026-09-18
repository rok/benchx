# Comparator

**Status:** Draft for review
**Companion to:** `system-decomposition.md` §3.6, `benchmark-result-schema.md`

## 1. Role

The comparator evaluates an explicit target point against a reference formed
from preceding points in the same series. The target is normally the newest
point selected by the caller, but it is an immutable input to the comparison;
the comparator never silently substitutes an earlier point. It computes the
effect and applies a configured comparison method to classify the target as
improved, regressed, no change detected, or indeterminate. Every verdict carries
its evidence, and insufficient history is reported rather than ignored.

The comparator is a side-effect-free evaluator and runs on demand. A selector
chooses the target and reference inputs. The change detector decides when and
which series to evaluate continuously, while policy decides whether a verdict
should block or alert.

## 2. Input

The logical core contract is:

```text
evaluate(target point, reference points, comparison method)
    -> comparison document
```

The target and reference points belong to one series under one identity-policy
schema and use one estimator. The target is explicit so a comparison remains
stable when newer results arrive. Reference points precede the target and are
selected by a versioned method, for example from a bounded ancestral window.
The exact API boundary between the comparator and store is an open question
(§7), but the comparator never assigns series membership itself.

A source with a revision graph uses the target's ancestors, not an arbitrary
linearization of other branches. When ancestry is unavailable, the store may
supply a native linear order. Without either, the reference cannot be formed and
the verdict is indeterminate. If a revision has multiple attempts, configuration
must select one, combine them by a declared method, or evaluate them separately;
the comparator never picks one implicitly.

Reference selection honors recorded distribution resets, accepted change
points, and applicable continuity events, so measurements from an obsolete
performance regime do not inflate current noise. Every boundary that truncates
or joins history is included in the comparison evidence.

A batch request identifies a target run or revision and the series expected for
that target. It evaluates each target point independently and reports an expected
series with no target result as missing; it never substitutes that series' most
recent result from an older run. Result documents are ingested before comparison.
An offline workbench uses a local store, which may be ephemeral, so local and
hosted use follow the same path.

## 3. Eligibility guard

Before computing a verdict, the comparator checks that:

- the explicit target and every reference point have the same series
  fingerprint, identity-policy schema, and estimator;
- the target has a usable estimate — otherwise that target is indeterminate,
  not replaced by an older successful point;
- every reference point satisfies the configured status and quality rules;
- every reference point precedes the target under the selected ancestry or
  native order; and
- the reference contains enough evidence for the configured method, or an
  explicit provisional rule applies.

Excluded points and their reasons remain visible in the output. Changes in
observed context do not split a series by themselves, but differences between
the target and its reference are carried as caveats so that a kernel, load, or
other recorded condition is not hidden from the reader.

An intentional comparison across an identity difference requires the store to
materialize the series under an explicit identity policy that projects that
difference out. The comparator never bypasses the resulting series boundary.

## 4. Comparison method and verdict

A comparison method has a stable name and version. It defines the reference
window and estimator, effect measure, treatment of within-result precision and
between-point variation, minimum evidence, and decision threshold.

For the target point, the method produces:

- **Reference estimate**: the expected value derived from the preceding eligible
  points.
- **Effect**: a declared measure of change from the reference estimate. Relative
  change is the default only when the reference is nonzero; the method must
  define an absolute, ratio, logarithmic, or other measure and its behavior for
  zero or negative values.
- **Noise**: variation expressed on the same scale as the effect and estimated
  from the reference points. Observation-level precision within one result and
  variation between series points remain distinct evidence; a method may combine
  them only through a declared rule. For a new series with insufficient history,
  project configuration may supply a conservative provisional estimate (for
  example, 30%). Measured noise replaces it once enough evidence exists. The
  output identifies the source of the estimate and whether it is provisional.
- **Verdict**: the initial method indicates a change when |effect| exceeds *k* ×
  noise, with *k* a project-configured multiplier. Indicated changes are labeled
  improved or regressed using the quantity's direction metadata when present,
  otherwise just *changed*. When the evidence is sufficient but the threshold
  is not exceeded, the verdict is *no change detected*.
- **Indeterminate**: there is no usable target or reference, ordering is unknown,
  or the method lacks enough evidence and no provisional rule applies. The
  reason is part of the verdict.

A quantity declared deterministic (§4.4 of the schema) does not need a noise
estimate. Once it has a preceding eligible point, exact equality means no change
detected and any difference indicates a change.

The dispersion-scaled initial method is deliberately simple and respects each
series' observed variability — a 2% change on a 0.2%-noise series is indicated,
while a 2% change on a 5%-noise series is not. Prediction intervals,
significance tests, minimum-effect filters, or multiple-comparison control can
be added as new method versions without changing the surrounding contract.

## 5. Output

A **comparison document** is machine-readable and self-describing. For each
evaluation it records:

- the target point and exact reference-point inputs;
- the series fingerprint, identity-policy schema, estimator, and ordering or
  ancestry used;
- the reference window, reset or continuity boundaries, comparison method and
  version, and complete configuration;
- the reference estimate, effect measure and value, noise and its source,
  threshold or limits, evidence counts, and verdict with reason; and
- exclusions, observed-context differences, quality caveats, and missing target
  results from a batch request.

The document is renderable as a reviewer-speed summary ("these target results
regressed, these improved, these show no detected change, these were
indeterminate, and these were missing") and consumable by alerting or CI gates.

Comparison documents are derived and recomputed on demand; the result store
persists their immutable inputs rather than the documents themselves. Supplying
the recorded target, reference points, method version, and configuration
reproduces the document even after newer points arrive.

## 6. Boundaries

- **Not target selection:** selecting "latest", a target run, or a target
  revision happens before invoking the comparator.
- **Not an arbitrary cross-series pair engine:** the comparator evaluates a
  target against preceding points in the same series.
- **Not policy:** *k*, provisional noise, eligibility rules, and gating decisions
  are project configuration; the comparator reports, humans and policy decide.
- **Not the detector:** it consumes a fixed historical reference but does not
  watch series, schedule evaluation, detect drift, or locate change points.
- **Not the identity authority:** series membership comes from the store's
  identity policy; the comparator only validates and consumes it.
- **Not a data source:** every number in the output is traceable to input results.

## 7. Open questions

1. **Series-resolution boundary.** Should the comparator receive (A) a series
   already resolved by the store, or (B) a comparison identity and retrieve the
   corresponding series from the store itself? In either design, the comparator
   must not assign membership: series membership is determined by the store's
   identity policy and is intentionally configurable.
2. **Explicit A/B use cases.** Are comparisons between two selected revisions,
   variants, or environments a separate operation layered on this latest-point
   evaluator, or must this component also support them without weakening its
   single-series contract?
