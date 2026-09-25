# Runner Schemas: Work Order, Environment Policy, Run Context

**Status:** Draft for review

**Companion to:** `runner.md` (PR #24), `benchmark-result-schema.md`

## 1. Purpose and scope

This document proposes three versioned schemas for the runner described in `runner.md`: the **work order** (the runner's input), the **environment policy** (referenced by the work order), and the **run context** (the conventions the runner uses when filling each result). Together with the existing measurement-result schema (`schemas/measurement-result/0.1.0`), they make up the runner's whole contract.

- **In scope:** everything a single runner invocation on one compute node reads or writes.
- **Out of scope:** scheduler state, store ingestion APIs, comparison verdicts, and harness-native output formats (adapters own those).
- **Non-goal for 0.1.0:** benchmarks that span several nodes. A work order targets exactly one node; many independent work orders across a fleet are fine. See §8.

## 2. Principles

Each schema rule below traces to a principle in `runner.md` or a rule in `benchmark-result-schema.md`.

1. **Work orders are documents, not calls.** A work order is plain JSON with a `schema_version`, a `work_order_id`, and a content hash. It can be written by hand, emitted by a scheduler or CI job, stored, and replayed. The runner reads nothing else.
2. **Self-contained means resolved.** Everything that changes the run is in the order or in a policy it references by name *and* version. Ambiguous references such as "latest" or a bare branch name are allowed only in a draft and resolved to fixed values before execution; the resolved order is what gets hashed and cited.
3. **No new result fields.** The runner adds nothing to the measurement-result schema. What it captures goes into slots that already exist: `coordinates.environment`, `coordinates.subject.configuration`, `observed_context`, `procedure`, and `provenance`.
4. **The work order is the run manifest.** `benchmark-result-schema.md` §5.1 leaves "lost vs. never planned" to the runner design. Here the resolved order lists every case the run plans, so a missing result can be told apart from one that was never requested.
5. **Every observation says whether it was available.** A condition the runner tried to observe but could not read is recorded as `unavailable`, never dropped. "No temperature on this VM" and "forgot to record temperature" look different.

## 3. Work order

A work order (`benchx/work-order/0.1.0`) has four required groups matching `runner.md` §3: **what**, **at what**, **how**, **for whom**. Every field says where it ends up in the result, so nothing the order asks for disappears without a trace.

| Field | Type | Req. | Group | Meaning | Lands in result as |
|---|---|---|---|---|---|
| `schema_version` | const | yes | — | `benchx/work-order/0.1.0` | — |
| `work_order_id` | URI or UUID | yes | — | Stable name for this order | `provenance.artifacts` (kind `work-order`, with sha256) |
| `state` | `draft` \| `resolved` | yes | — | Only `resolved` orders execute (§3.2) | — |
| `project` | token | yes | what | Project in the store | `project` |
| `suites[]` | array | yes | what | `{adapter, suite, include[], exclude[], parameters}` per harness suite | `coordinates.workload` via the adapter |
| `quantities[]` | array of names | yes | what | Quantities to collect, e.g. `wall-time`, `peak-rss` | `coordinates.quantity` |
| `target` | one of 4 kinds | yes | at what | What code to measure (§3.1) | `source`, `revision`, dirty flags, tree ids |
| `components[]` | array | no | at what | Pinned non-primary components `{name, role, source, revision}` | `coordinates.subject.components` |
| `build` | object | no | how | `{profile, type, compiler, flags[], options{}, cache}` | `coordinates.subject.configuration` |
| `precision` | object | yes | how | `{repetitions, min_time_s, warmups, inner_iterations}` (harness-neutral names, from Appendix B keys) | intended: `comparison_context`; realized: `procedure` |
| `schedule` | object | no | how | `{kind: sequential \| alternating \| random, seed}` across sides | `comparison_context.protocol.schedule`; realized `procedure.slot` |
| `timeouts` | object | yes | how | `{case_s, order_s}`, both positive | exceeded: `censored` or `error` result |
| `environment_policy` | `{name, version}` | yes | how | Named policy (§4) | policy identity in `coordinates.environment.identity` |
| `run_key` | token | yes | for whom | Groups this order with sibling orders in one comparison | `provenance.run_key` |
| `round` | integer | no | for whom | Position in an interleaved run; set by the run author | `procedure.round` |
| `labels` | string map | no | for whom | Caller labels, e.g. `{"env": "numpy-2.0"}` | `provenance.labels` |
| `requester` | `{kind, name}` | yes | for whom | `kind`: `scheduler` \| `ci` \| `workbench` \| `person` | `provenance.info.requester` |
| `reason` | string | no | for whom | Free text: why this run exists | `provenance.info.reason` |
| `plan[]` | array | resolved only | — | Every case × quantity the run will attempt | the run manifest (§6) |

### 3.1 Target kinds

| `target.kind` | Required fields | What the runner must verify |
|---|---|---|
| `revision` | `source.uri`, `revision` (full commit id) | Checkout matches `revision`; tree is clean after checkout |
| `working_tree` | `path`, `source.uri` | Records HEAD, dirty state, and tree id as found; never cleans the tree |
| `build` | `path`, `source.uri` | Build config and staleness vs. the tree it came from (`runner.md` open question 3) |
| `artifact` | `uri`, `sha256`, `source.uri`, `revision` | Checksum matches; `revision` is the artifact's declared source, taken on trust and flagged in `quality.warnings` |

### 3.2 Draft and resolved orders

A person or tool may write a **draft**: a branch name instead of a commit, `include` globs instead of cases, a policy without a version. Before execution it becomes a **resolved** order, with full commit ids, a pinned policy version, and an expanded `plan`. Results cite the resolved order's hash, never the draft's.

Resolution happens as early as possible, and the runner fills in only what is left:

- **Resolution only fills gaps.** It never changes a field that is already fixed, so a fully resolved order passes through the runner unchanged.
- **The requester resolves shared facts.** The scheduler, CI job, or workbench fixes everything that must be identical across sibling orders in a `run_key`: commit ids for branch names, policy versions, precision defaults, and the case list when it is knowable without a build. Resolving these once is what keeps both sides of a comparison on the same values.
- **The runner resolves only facts about its own machine.** These are working-tree state (HEAD, dirty flag, tree id), the case list for harnesses that enumerate cases only after a build, and the values actually enforced by the policy. It then records the resolved order as a provenance artifact before execution starts.
- **The runner refuses unresolved shared fields.** A draft that still names a branch, or a policy without a version, is refused rather than resolved against the runner's local clone or cache. That would infer the run from leftovers on the machine, which `runner.md` principle 1 forbids.

So a person on a laptop can hand the runner a loose draft whose target is `working_tree`, which is only meaningful on that machine anyway, while a fleet order arrives already pinned.

Where results are delivered (store URL, local file) is an invocation argument, not an order field. Replaying an order on another machine shouldn't silently post to the original store.

## 4. Environment policy

A policy (`benchx/environment-policy/0.1.0`) is a named, versioned list of rules. Each rule has a **check**, a **tier**, parameters, and an `on_fail` action. The tier sets both what the runner does and where the fact lands in the result.

| Tier | Runner action | On failure | Lands in result as | Enters identity? |
|---|---|---|---|---|
| `enforce` | Sets the condition before execution | Refuse the order | `coordinates.environment.identity` (policy name + version + enforced values) | Yes |
| `verify` | Checks before, and optionally after, execution | `refuse` or `warn`, per rule | Result in `observed_context`; failures in `quality.warnings` | No |
| `record` | Observes only | Never fails; unreadable = `unavailable` | `observed_context` | No |

Changing a policy's version changes environment identity, so it splits the series: the "series-splitting event, not a silent change" of `runner.md` §5.

### 4.1 Core check vocabulary

The core set is small and CPU/GPU generic. Project-specific checks use a namespaced prefix (`x-arrow.*`, `x-cupy.*`) so `runner.md` open question 2 can be settled case by case without a schema change.

| Check | Parameters | Laptop policy | Tuned-node policy |
|---|---|---|---|
| `threads.max` | `n` | enforce | enforce |
| `cpu.affinity` | CPU set | — | enforce |
| `cpu.governor` | e.g. `performance` | record | enforce |
| `cpu.boost` | on/off | record | enforce off |
| `cpu.smt` | on/off | record | verify |
| `gpu.device` | index or UUID | enforce | enforce |
| `gpu.clocks_locked` | MHz | — | enforce |
| `accel.sync` | `events` \| `device-sync` | enforce | enforce |
| `load.quiescent` | max 1-min load, window s | record | verify, refuse |
| `hardware.present` | CPU model pattern, GPU count, min RAM | verify, warn | verify, refuse |
| `tree.clean` | — | record | verify, refuse |
| `thermal.throttle` | counters to diff | record | verify, warn |
| `thermal.temperature` | sensors, sample interval s | record | record |

A laptop policy mostly records; a tuned-node policy mostly enforces. Both produce results in the same shape, which is what lets one runner serve both.

### 4.2 Refusal is still a result

`runner.md` §6 says an unsatisfiable policy refuses the run "with the reason reported". Principle 5 of the same document says every outcome is a result. This schema reconciles the two: a refusal emits one `error` result per `plan` entry with `measurement.reason = "policy_unsatisfied:<check>"`. Nothing is measured, but nothing goes missing either.

## 5. Run context

The runner fills existing measurement-result fields and defines no new ones. What it does define are two conventions for the open objects: an environment identity schema and an observed-context key set.

### 5.1 Identity and revision

| Fact | Result field | If unknown |
|---|---|---|
| Subject commit | `revision.key` | Order refused; no measurement without a revision |
| Subject dirty state | `provenance.subject_dirty` | `unknown`, never `clean` by default |
| Subject tree hash | `provenance.subject_tree` | Omitted; comparators then treat it as not code-identical |
| Benchmark code dirty state / tree | `provenance.benchmark_dirty`, `benchmark_tree` | as above |
| Build configuration | `coordinates.subject.configuration` | `quality.warnings`: `build_config_unverified` |
| Runner software | `provenance.runner` `{name, version}` | never unknown |
| Resolved work order | `provenance.artifacts` (kind `work-order`, URI + sha256) | never unknown |

### 5.2 Environment identity: `benchx/env-identity/0.1.0`

This goes in `coordinates.environment` with `schema = "benchx/env-identity/0.1.0"`. A fact goes in `identity` if a change should split history, and in `metadata` otherwise.

- **identity:** `machine_id` (salted hash of `/etc/machine-id` or equivalent), `cpu.model`, `cpu.logical_cores`, `memory_bytes`, `gpus[] {model, memory_bytes}`, `os.family`, `virtualization` (`bare-metal` | `vm` | `container` | `wsl`), `policy` (`name@version`), `enforced{}` (the values actually applied)
- **metadata:** hostname, GPU UUIDs, BIOS/firmware strings

GPU UUIDs stay out of identity, because swapping a card of the same model shouldn't split history. The device each result used goes in `coordinates.resource_selection`.

### 5.3 Observed context: `benchx/observed-context/0.1.0`

`observed_context` is an open object; the runner fills it using this convention. Every key holds an **observation record**, never a bare value:

```json
{"value": 71.0, "unit": "Cel", "status": "observed", "when": "sampled", "source": "hwmon/coretemp"}
```

- `status`: `observed` | `unavailable` | `error`. An `unavailable` record has no `value`.
- `when`: `before` | `after` | `sampled`. A sampled record's `value` is `{min, max, mean, n}`.
- Units are UCUM, as in the result schema.

| Key | Typical source (Linux) | `when` |
|---|---|---|
| `os.kernel`, `libc.version`, `cpu.microcode` | `uname`, `ldd`, `/proc/cpuinfo` | before |
| `cpu.governor`, `cpu.freq_mhz` | cpufreq sysfs | before, sampled |
| `load.avg_1m` | `/proc/loadavg` | before, after |
| `thermal.temperature` | hwmon / thermal zones; NVML for GPUs | sampled |
| `thermal.throttle_events` | throttle counters, after minus before; NVML throttle reasons | after |
| `container.image_digest` | runtime | before |

Throttle evidence is recorded separately from temperature. It's the signal that can explain a slower result, and it's available on some machines that don't expose temperature.

## 6. Outcome statuses

Every `plan` entry ends as exactly one result, using the five statuses the result schema already has. Each result carries its entry id in `provenance.info.plan_entry`. A plan entry with no result therefore means the runner itself died: the run was **lost**, not skipped.

| Runner outcome | Stage | `measurement.status` | `measurement.reason` | Extra evidence |
|---|---|---|---|---|
| All requested repetitions completed | execute | `success` | — | — |
| Some repetitions failed or were cut short | execute | `partial` | `repetitions_incomplete` | `procedure.completed_repetitions` |
| Case exceeded `timeouts.case_s`, time quantity | execute | `censored` | `timeout_case` | constraint `lower_bound` = `case_s` |
| Case exceeded `timeouts.case_s`, other quantity | execute | `error` | `timeout_case` | — |
| Harness explicitly skipped the case | execute | `skipped` | harness's own reason | — |
| Harness crashed mid-suite (remaining entries) | execute | `error` | `harness_crashed` | log in `provenance.artifacts` |
| Adapter could not translate output | emit | `error` | `adapter_error` | raw output as artifact |
| Build failed | resolve target | `error` (every entry) | `build_failed` | build log artifact |
| Policy check failed with `refuse` | prepare | `error` (every entry) | `policy_unsatisfied:<check>` | check result in `observed_context` |
| `timeouts.order_s` exceeded (unstarted entries) | any | `error` | `timeout_order` | — |
| Policy check failed with `warn` | prepare / after | unchanged | — | `quality.warnings` entry |
| Runner process killed | any | no result | — | resolved order shows the gap |

Reasons are drawn from a closed list of codes, optionally followed by `:<detail>`, so dashboards can group failures without parsing free text.

## 7. Versioning and hashing

All three schemas use the same scheme as `schemas/measurement-result/0.1.0`: semver in a directory path, with JSON Schema 2020-12 files and examples beside them.

| Schema | Path | Hash used for |
|---|---|---|
| Work order | `schemas/work-order/0.1.0/` | citing the resolved order from results |
| Environment policy | `schemas/environment-policy/0.1.0/` | detecting a policy edited without a version bump |
| Env identity | `schemas/env-identity/0.1.0/` | referenced by `coordinates.environment.schema` |

Orders and policies are hashed the same way the result schema hashes its fingerprints:

```text
work_order_sha256 = SHA-256("benchx-work-order-v1\0" + JCS(resolved_order))
policy_sha256     = SHA-256("benchx-env-policy-v1\0" + JCS(policy))
```

- **Only resolved orders are hashed.** A draft has no stable meaning, so it has no hash.
- **A policy's `(name, version)` is bound to one hash.** The store rejects a second policy body under the same name and version. That enforces "loosening a policy splits the series" in the store rather than by convention.
- **Compatibility:** a runner must refuse an order whose major `schema_version` it doesn't know. Minor versions only add optional fields, and older runners ignore them only if the field is in the schema's `ignorable` list. Otherwise they refuse, because silently ignoring a precision or policy field would produce a result that misdescribes itself.

## 8. Worked example: Arrow on a laptop

A contributor measures an uncommitted Parquet change on a WSL2 laptop: the local story from `docs/user_stories/apache-arrow-local-benchmarking.md`, using the names from `schemas/measurement-result/0.1.0/examples/arrow.json`.

**Resolved work order**

```json
{
  "schema_version": "benchx/work-order/0.1.0",
  "work_order_id": "urn:uuid:6f1c2b7e-3d4a-4e8b-9a51-0c2d7e9f4b13",
  "state": "resolved",
  "project": "arrow",
  "suites": [{"adapter": "google-benchmark", "suite": "parquet-read",
              "include": ["parquet-read/snappy"], "parameters": {}}],
  "quantities": ["wall-time"],
  "target": {"kind": "working_tree", "path": "~/arrow",
             "source": {"uri": "https://github.com/apache/arrow", "type": "git"}},
  "build": {"profile": "ninja-release", "type": "release", "compiler": "clang-18", "cache": "reuse"},
  "precision": {"repetitions": 5, "min_time_s": 0.01, "warmups": 1},
  "timeouts": {"case_s": 60, "order_s": 1800},
  "environment_policy": {"name": "laptop-default", "version": "1.0.0"},
  "run_key": "local:parquet-snappy-2026-09-23",
  "round": 1,
  "labels": {"side": "contender"},
  "requester": {"kind": "workbench", "name": "local"},
  "reason": "check snappy decode change before opening PR",
  "plan": [{"id": "p0", "case": "parquet-read/snappy", "quantity": "wall-time"}]
}
```

**Runner-owned fields of the resulting `success` result** (everything else comes from the adapter)

```json
{
  "revision": {"key": "02addad7a1f3ce7d6de6a6230ec4c17828cb8f52"},
  "coordinates": {
    "subject": {"configuration": {"build_type": "release", "compiler": "clang-18"}},
    "environment": {
      "schema": "benchx/env-identity/0.1.0",
      "identity": {"machine_id": "sha256:3e1f...", "cpu": {"model": "Intel Core i7-1260P", "logical_cores": 16},
                   "memory_bytes": 17179869184, "os": {"family": "linux"}, "virtualization": "wsl",
                   "policy": "laptop-default@1.0.0", "enforced": {"threads.max": 1}}
    }
  },
  "observed_context": {
    "os.kernel": {"value": "6.6.87.2-microsoft-standard-WSL2", "status": "observed", "when": "before"},
    "load.avg_1m": {"value": 0.42, "unit": "1", "status": "observed", "when": "before"},
    "cpu.governor": {"status": "unavailable", "when": "before"},
    "thermal.temperature": {"status": "unavailable", "when": "sampled"},
    "thermal.throttle_events": {"status": "unavailable", "when": "after"}
  },
  "provenance": {
    "run_key": "local:parquet-snappy-2026-09-23",
    "labels": {"side": "contender"},
    "subject_dirty": "dirty",
    "subject_tree": "9fceb02d0ae598e95dc970b74767f19372d61af8",
    "runner": {"name": "benchx-runner", "version": "0.1.0"},
    "artifacts": [{"kind": "work-order", "media_type": "application/json",
                   "schema": "benchx/work-order/0.1.0",
                   "uri": "file:///home/me/.benchx/orders/6f1c2b7e.json", "sha256": "..."}],
    "info": {"plan_entry": "p0", "requester": "workbench:local",
             "reason": "check snappy decode change before opening PR"}
  }
}
```

WSL2 exposes no governor, temperature, or throttle counters, so all three are recorded as `unavailable`. The dirty tree makes any comparison using this result local-only (`benchmark-result-schema.md` §5.5).

## 9. Open questions

1. **Multi-node benchmarks.** 0.1.0 targets one node per order. Should a later version allow a node group (`target.nodes[]` plus a coordinator role), or should a distributed benchmark stay a harness concern behind a single coordinator runner?
2. **Who stores resolved orders?** The order doubles as the run manifest, but the runner is store-unaware. Does the runner upload the order as an artifact alongside results, or does the requester (scheduler, workbench) keep it?
3. **Build failure before the plan exists.** §3.2 lets the runner expand `plan` after the build for harnesses that enumerate cases only then. If that build fails there are no plan entries to attach `error` results to. Does the runner emit a single order-level `build_failed` result, and under which workload coordinates?
4. **Should the observation-record convention move into the result schema?** Today `observed_context` is an open object. Making `{value, status, when, source}` normative there would let every producer, not just this runner, mark facts `unavailable`.
5. **Sampling overhead.** Sampling temperature and frequency during execution can itself disturb the measurement. What default interval (e.g. 1 s) and core placement keep it negligible, and should the policy be able to turn sampling off?
6. **Build caching** (`runner.md` open question 1). `build.cache` is modeled as `reuse` | `fresh` | `require-cached`. Is a build its own cacheable artifact with a hash that the order can reference instead?
7. **Delivery in the order?** This draft makes the result destination an invocation argument. Are there cases, such as CI, where the order should carry it?
8. **Refusal as results.** §4.2 turns a policy refusal into one `error` result per plan entry, which goes beyond `runner.md` §6's "refused before execution". Keep that, or report refusals only to the requester?
