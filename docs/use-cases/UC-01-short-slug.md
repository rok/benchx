# Benchmark Use Case Template

## UC-01: Run a single parametrized benchmark

| | |
|---|---|
| **Status** | draft |
| **Owner** | |
| **Last updated** | |
| **Related** |  |

### 1. Summary

A contributor runs a single parametrized benchmark in a fixed environment.
The benchmark parametrization is problem-dependent: when developing an algorithm
which involves linear algebra, they verify scaling of the run time versus matrix size;
when developing an array-agnostic variant of a routine, they compare performance
for varying array providers.


### 2. Motivation

In this use case, there is no comparison across history, build or runtime environments
or machines: the benchmark itself all necessary information via its parametrization.

There can be one or multiple parameters (problem size, execution mode, array provider);
the benchmark may report one or multiple measurements (CPU time, peak memory).


### 3. Actors and trigger

- **Actor:** contributor on a laptop 
- **Trigger:** a manually typed command
- **Frequency:** on demand


### 4. Workflow sketch

The commands or UI actions, in order, including what the actor sees back. Rough is
fine; the point is to expose where data is produced and consumed.

```
$ <command>
<what they see>
```

Note where the loop closes: what do they do with the answer? If the answer is
"nothing, they look at it," say that - some use cases really are just display, and
those have much weaker schema requirements than ones feeding an automated decision.

```
$ bench-runner benchmark-id

N   CPU time, msec  memory, mb
------------------------------
10    1e-3              10
100   0.12              101             
1000  11.0              1200
```

The default view is just display. However, results need saving according to the schema,
for a user might want to add their own view/analysis postprocessing.

Such postprocessing is too problem-specific to and is left to user.
Further use cases may add commonly used viewers/analyzers.


### 5. Study design

| Coordinate | Role | Notes |
|---|---|---|
| Code identity | free | |
| Code version | free | |
| Environment | free | |
| Execution context | free | |

In the core use case, everything is free since the measurements are ephemeral.
Other, more specific use cases add actual constraints.

Related to the **open question 2**: saving benchmark results may need a knob to control
whether to append or replace existing saved results. This is useful in several contexts:
- add other parameter values without rerunning existing runs;
- roughly assess run-to-run variations.


### 6. Measurements

Not specified, may vary per scenario.


### 7. Comparison semantics

n/a


### 8. Schema implications

- Profile: new
- Fields required beyond the core: derived from the benchmark parametrization;
- New fields not currently in the schema: dynamic, defined by the benchmark itself;
  Each new field is numerical, needs to have a name and a unit;
  If a benchmark is not parametrized, the default field `{name: "result", unit: None)`
  is used. 
- Comparability key: n/a
- Validation invariants: n/a
- Conflicts with existing use cases: n/a


### 9. Storage and lifecycle

- **Volume:** records per invocation
- **Retention:** session-scoped
- **Location:** local working dir
- **Does this data ever need to join against data from another use case?** Potentially,
  multiple runs may need joining (e.g. run one more problem size without re-running
  the previous run). However this is not crucial for this specific use case.


### 10. Degenerate and failure modes

- What happens when a *controlled* coordinate silently isn't constant: Nothing is
  controlled therefore this is not an issue. However, a separate utility to check
  that core values match could be useful.
- What happens with missing or partial data: Nothing drastic, benchmarking runs are
  manually triggered and are ephemeral. 
- What is the worst wrong conclusion someone could draw, and does the schema make it
  harder or easier to draw?


### 11. Non-goals

- build/runtime environment control
- repository state (can be dirty)
- comparisons across commits, environments or machines


### 12. Open questions

1. Where is the information about the benchmarking strategy is stored: e.g. which
measurements to take (CPU time, GPU time, peak memory), how to take measurements
(how to synchronize the device) etc: in the benchmark itself, in a per-session config,
in a per-project config?

2. Support appending results to the local store, e.g. add one more parameter value
without rerunning the already-run benchmarks? For this use case the answer might be
a "no" to avoid coupling between a runner and storage.

