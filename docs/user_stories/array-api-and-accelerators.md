# Array API / hardware accelerators user stories

**Project:** any project supporting multiple array providers and/or hardware accelerators
**Current benchmarking setup:** ad-hoc benchmarks only
**Contact:** Evgeni

## Who uses benchmarks here

- **Contributors** -- want to compare performance across software/hardware types
- **Reviewers** -- same questions, only during the review stage
- **Maintainers** -- track performance regressions for specific hardware/software


## Stories

### Compare performance of `numpy` vs `torch` as the array library

> As a contributor, I want to compare performance of an Array API compatible function
> for `numpy` and `torch` as array libraries.

**Today:** Parametrize the benchmark with the array library, `xp`.
**Pain:** `asv`-based [`XPBenchmark`](https://github.com/scipy/scipy/blob/main/benchmarks/benchmarks/common.py#L22) is inconvenient for one-off benchmarks; ad hoc bespoke
harnesses, for example, [the RBF benchmark](https://github.com/ev-br/bench_playground/blob/master/rbf_bench.py) or [the Rotation benchmark](https://github.com/amacati/scipy/blob/1d5e0ec9e82cc246e9961647d1bba4ba9796226f/xp_bench/rot_benchmark.py#L885) are manual,
hard to find and difficult to reuse.


### Benchmark an array-api compatible function on a GPU

> As a contributor, I want to run benchmarks with a certain Array API backend on GPU.
> The device needs synchronization. For backends that support both CPU and GPU devices,
> I need to guard GPU synchronization behind a check (a la `torch.cuda.is_available`).

**Today:** Benchmark author has to insert synchronization primitives manually.
**Pain:** Synchronization primitives differ depending on the array provider: 
`jax.block_until_ready` vs `torch.cuda.synchronize` vs `cupy.synchronize`.


### Measure CPU and GPU time separately

> As a maintainer, I want to make sure a function utilizes the device efficiently, and
> flag unexpected host-device transfers. To this end, I want to measure CPU and GPU times
> separately, and flag large changes in the ratio of the two.

**Today:** Is only available through `%gpu_timeit`, equivalently the [`cupyx.profile.Benchmark`](https://github.com/cupy/cupy/blob/v14.1.1/cupyx/profiler/_time.py#L233) interface. 
**Pain:** `%gpu_timeit` interface geared towards one-off measurements.


### Benchmark an array-api compatible function on a multi-GPU system

> As a contributor, I have a machine with two GPU cards and I want to compare their
> performance.

**Today:** Benchmark runner needs to set the device manually. Synchronization needs to
be done per-device, via `CUDA Events API` not via global `cuda.synchronize` API.
**Pain:** Only available through CuPy's
(`cupyx.profiler.benchmark` interface)[https://github.com/cupy/cupy/blob/v14.1.1/cupyx/profiler/_time.py#L170-L177]


### Benchmark under JIT

> As a contributor, I want to compare a function in JIT and eager mode. The JIT
> invocations differ by the array library (`jax.jit` vs `torch.compile`). And I need to
> pre-JIT the benchmarking targets, and warm up the JIT.

**Today:** Ensure jitting before starting to take measurements. Warm the JIT manually.
**Pain:** Not much support from benchmarking harnesses. Details depend on the array
provider and backend-specific actions might be needed (for example, clean up filesystem
level cached kernels).


### Control threading state, internal threadpools and NUMA affinity

> As a contributor, I want to be able to have control on the low-threading details
> to avoid oversubscription. This requires OS-level actions: setting environment
> variables (`OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1`), using `taskset` etc.


**Today:** Set the needed OS-level variables manually, outside of the benchmarking harness.
**Pain:** Setting things outside of the benchmark harness is error-prone, and settings
leave no trace in the results; the latter makes analyzing results error-prone, too.


## What must not break

N/A

## Wishes

- Convenient parametrization over array provider libraries, hardware types and execution
  modes (eager vs jit, sync vs async);
- Ability to adapt the runner to backend-specific details (filesystem caches,
  synchronization API etc);
- Reuse the same benchmarks for both one-off in-development iterations and performance
  tracking.

## Scale and constraints

Similar to other uses of one-off benchmarking and performance tracking.
