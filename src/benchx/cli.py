"""bx: a thin command line over the benchx package (prototype-design.md §1).

Every command reads the project's `benchx.conf.json` (benchx.config), found from the
working directory upward. The local store and the result files are in the
project root unless that file says otherwise, or `$BENCHX_HOME` relocates the store. A command-line argument wins over
the file, and the file over a built-in default.
"""

import argparse
import contextlib
import dataclasses
import json
import logging
import os
import sys
import tempfile
import traceback
from pathlib import Path
from typing import get_args

from . import bench as bench_mod
from . import compare as compare_mod
from . import config as config_mod
from . import core, harnesses, log, orders, runner, session, snapshot
from . import store as store_mod
from . import tables as tables_mod
from . import target as target_mod
from . import views as views_mod
from .core.validation import Kind
from .errors import BenchxError, UsageError
from .results import MemoryStore, warning_codes

EXIT_OK = 0
EXIT_INVALID = 1  # a document invalid, a result rejected, or a target without a description
EXIT_REFUSED = 2  # the command was refused or could not be carried out
OUTCOMES = {EXIT_OK: "ok", EXIT_INVALID: "invalid", EXIT_REFUSED: "refused"}

say = log.console(__name__)  # what `bx` shows its user: console messages
logger = logging.getLogger(__name__)


def _load():
    """Load the project's configuration and exclude its own paths from tree identity."""
    cfg = config_mod.load()
    snapshot.ignore(*cfg.own_paths)
    return cfg


def _start_logging(cfg, args, out, command, *, read_config=True, lenient=False):
    """Configure the diagnostic log for this command and return `cfg` with `log_file` set."""
    destination, source, level, level_source = log.configure_for_command(cfg, args, out, command, lenient=lenient)
    cfg = dataclasses.replace(cfg, log_file=destination if isinstance(destination, Path) else None)
    snapshot.ignore(*cfg.own_paths, *([args.out] if getattr(args, "out", None) else []))  # the log is not the tree
    log.log_startup(
        cfg, args, destination, source, level, level_source, read_config=read_config, home_env=config_mod.HOME_ENV
    )
    return cfg


def _report_unmeasured(rows) -> None:
    """Print per-case failure/skip details below the table and record a degraded-run summary.

    The summary table itself is printed by the caller; this prints any per-case `message` strings
    at WARNING when at least one case failed (always shown), or INFO when only skipped cases had
    messages (hidden under `-q`). Exit status remains 0 either way, and `log.degraded()` appends
    the unmeasured count to the log footer (and stdout if quiet mode would otherwise hide failures).
    """
    details = bench_mod.failures(rows)
    failed_rows = [row for row in rows if not row["status"].startswith(("success", "skipped"))]
    failed_with_msg = {row["case"] for row in failed_rows if row["message"]}
    if details:
        has_failures = bool(failed_with_msg)
        say.out(
            details, log.ANSWER if has_failures else log.TABLE, level=logging.WARNING if has_failures else logging.INFO
        )
    failed_cases = {row["case"] for row in failed_rows}
    if failed_cases:
        all_cases = {row["case"] for row in rows}
        silent_failures = failed_cases - failed_with_msg
        log.degraded(
            f"{len(failed_cases)} of {len(all_cases)} cases not measured",
            shown=bool(log.quiet() and (not failed_with_msg or silent_failures)),
        )


def _is_missing_pyarrow(exc: ModuleNotFoundError) -> bool:
    return bool(exc.name and exc.name.split(".")[0] == "pyarrow")


def _open_store(path, *, hint: str | None = None):
    """Open the local store (Parquet or JSONL), or explain how to install pyarrow for a Parquet file."""
    try:
        return store_mod.Store(path)
    except ModuleNotFoundError as exc:
        if _is_missing_pyarrow(exc):
            suffix = f", or {hint}" if hint else ""
            raise BenchxError(
                f"Parquet store ({path}) requires pyarrow; install it with `pip install 'benchx[parquet]'`{suffix}"
            ) from None
        raise


def _prepare(args, *, open_store: bool = False):
    """Load config, start logging (no output folder), and optionally open the local store."""
    cfg = _start_logging(_load(), args, None, args.cmd)
    if not open_store:
        return cfg
    return cfg, _open_store(cfg.store_path)


def cmd_run(args):
    """Run one order, write its result files, and deliver them to the local
    store. The runner itself stays store-unaware (runner.md §2 principle 6);
    this command composes it with ingest, as the workbench does."""
    cfg = _load()
    store = None if args.no_ingest else _open_store(cfg.store_path, hint="pass --no-ingest to write JSON results only")
    out = Path(args.out) if args.out else cfg.results_dir
    # `bx run` has no check phase; the log goes in --out, and nowhere without it (the results
    # directory is shared by every run).
    cfg = _start_logging(cfg, args, Path(args.out) if args.out else None, "run")
    logger.info("order file %s; output %s", Path(args.order).resolve(), out)
    say.progress(f"running the order {Path(args.order).name}")
    summary = runner.run(args.order, out, allow_collectors=args.allow_collectors)
    _report_unmeasured(bench_mod.summarize(summary["files"]))
    say.out(
        f"{summary['results']} result(s) for {summary['cases']} case(s) -> {summary['out']}"
        f"  (order {summary['order'][:19]})",
        log.SUMMARY,
    )
    if store is None:
        logger.info("ingest skipped (--no-ingest): the results are files only")
        return EXIT_OK
    return _report(store.ingest_paths(summary["files"]), store.path)


def _session_position(args) -> tuple[dict, int | None, int | None, int | None]:
    """Validate and return `(labels, round_, slot, total_rounds)` when joining a multi-call session."""
    labels = {}
    for item in args.label or []:
        name, eq, value = item.partition("=")
        if not (name and eq and value):
            raise UsageError(f"--label wants NAME=VALUE, not {item!r}")
        session.check_label_name(name)  # a SessionError, which cmd_bench reports as it does a UsageError
        if name in labels:
            raise UsageError(f"--label {name} is given twice")
        labels[name] = value
    round_, rounds = None, None
    if args.round is not None:
        first, slash, last = args.round.partition("/")
        try:
            round_, rounds = int(first), int(last) if slash else None
        except ValueError:
            raise UsageError(
                f"--round wants R, or R/N for a session of N rounds, whole numbers, not {args.round!r}"
            ) from None
        if round_ < 0:
            raise UsageError(f"--round wants a number from 0, not {round_}")
        if rounds is not None and rounds < 1:
            raise UsageError(f"--round {args.round}: a session has at least 1 round, not {rounds}")
        if rounds is not None and round_ >= rounds:
            raise UsageError(f"--round {args.round}: with {rounds} round(s) they are numbered 0 to {rounds - 1}")
    if args.slot is not None and args.slot < 0:
        raise UsageError(f"--slot wants a number from 0, not {args.slot}")
    if (labels or round_ is not None or args.slot is not None) and not args.run_key:
        raise UsageError(
            "--label, --round and --slot need an explicit --run-key: the default is a timestamp "
            "per call, so two calls would never share a run"
        )
    if (labels or round_ is not None) and args.slot is None:
        raise UsageError(
            "--label and --round need --slot: without one, the sides of a run would share an "
            "ingest key and their results would conflict"
        )
    return labels, round_, args.slot, rounds


def _common(cfg, args, *, forced_adapter=None, forced_suite=None) -> dict:
    """Resolve settings shared by `bx bench` and `bx compare` (`CLI flags > benchx.conf.json > defaults`).

    Validates harness family compatibility and precision flags, returning the normalized settings dict
    plus a `sources` list of `(name, value, source)` tuples for diagnostic logging (popped before
    forwarding the dict to `session`).
    """
    block = cfg.adapter
    given = forced_adapter or args.adapter
    if given and block.get("name") and not harnesses.same_family(given, block["name"]):
        raise config_mod.ConfigError(
            f"adapter {given!r}, but {cfg.where} sets adapter.name to {block['name']!r}, "
            "and its precision belongs to that harness and the ones that share it "
            "(pyperf and asv)"
        )
    sources = []
    quantities = (
        config_mod.parse_quantities(args.quantity)
        if args.quantity
        else list(block.get("quantities", config_mod.DEFAULTS["adapter.quantities"]))
    )
    sources.append(
        (
            "quantities",
            ", ".join(quantities),
            "flag" if args.quantity else "file" if "quantities" in block else "default",
        )
    )
    if args.project and args.no_project:
        raise UsageError("give --project or --no-project, not both")
    adapter, adapter_source = cfg.pick_with_source("adapter.name", given, flag="--adapter")
    named = block.get("name")
    if given and named and given != named:  # the file's block serves another adapter of its family
        adapter_source += f"; the file says {named}, same family"
    sources.append(("adapter", adapter, adapter_source))
    suite, suite_source = cfg.pick_with_source("adapter.suite", forced_suite or args.suite, flag="--suite")
    sources.append(("suite", suite, suite_source))
    from_flag = {}
    for item in args.env or []:
        name, eq, value = item.partition("=")
        if not (name and eq):
            # Avoid echoing `item`: it often holds a secret rather than a NAME=VALUE typo.
            raise UsageError("-e wants NAME=VALUE (the item is not shown, in case it holds a value)")
        from_flag[name] = value
    from_file = cfg.section("environment_variables")
    environment_variables = {**from_file, **from_flag}
    where = [
        *(["-e: " + ", ".join(sorted(from_flag))] if from_flag else []),
        *(["file: " + ", ".join(sorted(from_file))] if from_file else []),
    ]
    if overrode := sorted(set(from_flag) & set(from_file)):
        where.append(f"-e overrode the file's {', '.join(overrode)}")
    sources.append(("environment_variables", "names only", "; ".join(where) or "default: none"))
    if args.no_project:
        project = None
        sources.append(("project", "none: results are filed as local/HOST", "flag --no-project"))
    else:
        project, project_source = cfg.pick_with_source("project", args.project, flag="--project", default=None)
        sources.append(("project", project or "none: results are filed as local/HOST", project_source))
    source_uri, uri_source = cfg.pick_with_source(
        "source.uri", args.source_uri or None, flag="--source-uri", default=None
    )
    sources.append(("source.uri", source_uri or "the checkout's origin remote", uri_source))
    case_s, case_source = cfg.pick_with_source(
        "timeouts.case_s",
        getattr(args, "case_timeout", None),
        flag="--case-timeout",
        default=harnesses.get(adapter).DEFAULT_CASE_TIMEOUT_S,
    )
    if case_source == "default":
        case_source = "default for asv, which times every round of a benchmark" if adapter == "asv" else "default"
    sources.append(("timeouts.case_s", f"{case_s:g} s", case_source))
    order_s, order_source = cfg.pick_with_source("timeouts.order_s", None, flag="")
    sources.append(("timeouts.order_s", f"{order_s:g} s", order_source))
    flagged = [name for name in harnesses.FLAG_NAMES if getattr(args, name) is not None]
    precision_file = sorted(block.get("precision") or {})
    sources.append(
        (
            "precision",
            f"flags {', '.join(flagged) or 'none'}; file {', '.join(precision_file) or 'none'}",
            "flag over file over the harness's defaults",
        )
    )
    if args.filter:
        sources.append(("filter", args.filter, "flag"))
    harness_verbosity, verbosity_source = log.resolve_harness_verbosity(cfg, args)
    sources.append(("harness verbosity", harness_verbosity, verbosity_source))
    flags = {name: getattr(args, name) for name in harnesses.FLAG_NAMES}
    harnesses.get(adapter).flags_to_precision(**flags)
    return {
        "adapter": adapter,
        "suite": suite,
        "flags": flags,
        "file_precision": block.get("precision"),
        "quantities": quantities,
        "filter": args.filter,
        "environment_variables": environment_variables,
        "project": project,
        "run_key": args.run_key,
        "out": args.out,
        "source_uri": source_uri,
        "build": not args.no_build,
        "provider": cfg.provider,
        "collectors": cfg.collectors,
        "results_dir": cfg.results_dir,
        # An asv case is every round of its benchmark, each bounded by the benchmark's own timeout.
        "case_s": case_s,
        "order_s": order_s,
        "config_path": cfg.path,
        "harness_verbosity": harness_verbosity,
        "sources": sources,
    }


def cmd_bench(args):
    """Run one target once, print its summary table, and optionally ingest results into the local store.

    Validates flags, provider requirements, and harness settings before creating the output folder
    or starting the run log.
    """
    cfg = _load()
    if args.functions and args.filter:
        raise UsageError("give case names or --filter, not both")
    target, forced_suite, forced_adapter = bench_mod.resolve_target(
        args.target, adapter=args.adapter, suite=args.suite, tree=args.tree
    )
    settings = _common(cfg, args, forced_adapter=forced_adapter, forced_suite=forced_suite)
    settings["labels"], settings["round_"], settings["slot"], rounds = _session_position(args)
    session.check_harness(settings["adapter"], settings["flags"], settings["file_precision"], settings["quantities"])
    if target.startswith("@"):
        cfg.require_provider(target)
    # A name may carry `(arguments)` where the harness has parametrized benchmarks.
    names = harnesses.exact_filter(args.functions, harnesses.get(settings["adapter"]).NAMES_TAKE_ARGUMENTS)
    run_key = args.run_key or orders.default_run_key("bench")
    out = Path(args.out) if args.out else session.run_directory(cfg.results_dir, run_key)
    cfg = _start_logging(cfg, args, out, "bench")
    logger.info(
        "run key %s (%s); output folder %s (%s)",
        run_key,
        "given" if args.run_key else "generated",
        out,
        "--out" if args.out else "the results directory",
    )
    log.log_settings(settings.pop("sources"))
    settings["run_key"], settings["out"] = run_key, out
    settings["filter"] = names or settings["filter"]
    store = None if args.no_ingest else _open_store(cfg.store_path, hint="pass --no-ingest to write JSON results only")
    # Include session placement `(round R[/N], slot S, k=v)` on the stderr progress line when present.
    placed_parts = [
        p
        for p in (
            f"round {settings['round_']}{f'/{rounds}' if rounds else ''}" if settings["round_"] is not None else "",
            f"slot {settings['slot']}" if settings["slot"] is not None else "",
            ", ".join(f"{name}={value}" for name, value in (settings["labels"] or {}).items()),
        )
        if p
    ]
    placed = f" ({', '.join(placed_parts)})" if placed_parts else ""
    suite_label = Path(settings["suite"]).name if settings.get("suite") else "the suite"
    say.progress(f"measuring {suite_label} on {target}{placed}")
    summary = session.bench_target(target, store=store, progress=say.info, **settings)
    rows = bench_mod.summarize(summary["files"])
    say.out(bench_mod.render(rows), log.TABLE)
    _report_unmeasured(rows)
    say.out(f"\n{summary['results']} result(s) -> {summary['out']}  (order {summary['order'][:19]})", log.SUMMARY)
    if store is None:
        logger.info("ingest skipped (--no-ingest): the results are files only")
        return EXIT_OK
    return _report(summary["outcome"], store.path)


def cmd_config(args):
    """Initialize a starter `benchx.conf.json` or display resolved configuration and logging settings."""
    if args.action == "init":
        # `init` does not read the file: it resolves the logging settings from the flags and the environment
        _start_logging(config_mod.Config.empty(), args, None, "config", read_config=False)
        path = config_mod.write_template(args.dir, args.adapter)
        print(f"wrote {path}")
        return EXIT_OK
    cfg = _prepare(args)
    rows = [*_resolved(cfg), *log.logging_rows(cfg, args)]
    print(f"file  {cfg.where}\nroot  {cfg.root}")
    for key, value, source in rows:
        print(f"{key:<26} {value}  ({source})")
    return EXIT_OK


def _config_row(cfg: config_mod.Config, key: str, default=None) -> tuple[str, str, str]:
    value = cfg.get(key)
    if value is not None:
        return key, json.dumps(value), "file"
    if default is None:
        default = config_mod.DEFAULTS.get(key)
    if default is not None:
        return key, json.dumps(default), "default"
    return key, "-", "unset"


def _resolved(cfg: config_mod.Config):
    """Yield `(key, formatted_value, source)` for each config key before CLI overrides."""
    for key in ("project", "source.uri", "provider.command", "adapter.name", "adapter.suite", "adapter.quantities"):
        yield _config_row(cfg, key)
    adapter_name = cfg.adapter.get("name")
    if adapter_name:
        resolved = harnesses.get(adapter_name).precision({}, cfg.adapter.get("precision"))
        yield "adapter.precision", json.dumps(resolved), "file + default" if cfg.adapter.get("precision") else "default"
    case_default = (
        harnesses.get(adapter_name).DEFAULT_CASE_TIMEOUT_S if adapter_name else config_mod.DEFAULTS["timeouts.case_s"]
    )
    yield _config_row(cfg, "environment_variables")
    yield _config_row(cfg, "timeouts.case_s", case_default)
    yield _config_row(cfg, "timeouts.order_s")
    store_from = (
        f"${config_mod.HOME_ENV}"
        if os.environ.get(config_mod.HOME_ENV)
        else "file"
        if "store" in cfg.section("paths")
        else "default"
    )
    yield "paths.store", str(cfg.store_path), store_from
    yield "paths.results", str(cfg.results_dir), "file" if "results" in cfg.section("paths") else "default"
    for key in ("compare.profile", "compare.rounds", "compare.k", "compare.min_rounds"):
        yield _config_row(cfg, key)


def _report(outcome, store_path=None):
    """Report ingest counts (on stderr at INFO after a run, or on stdout at ANSWER for `bx ingest`).

    Returns `EXIT_INVALID` if any document was rejected, otherwise `EXIT_OK`.
    """
    for r in outcome["rejected"]:
        say.warning(f"  rejected {r['document']}: {r['code']} — {r['message']}")
    counts = f"ingested {outcome['ingested']}, duplicate {outcome['duplicate']}"
    if outcome["rejected"]:
        codes = sorted({r["code"] for r in outcome["rejected"]})
        counts += f", rejected {len(outcome['rejected'])} ({', '.join(codes)})"
    if store_path:
        say.info(f"{store_path}: {counts}")
    else:
        say.out(counts, log.ANSWER)
    return EXIT_INVALID if outcome["rejected"] else EXIT_OK


def cmd_ingest(args):
    """Validate result files or directories and ingest them into the local store."""
    _, store = _prepare(args, open_store=True)
    logger.info("ingesting %d path(s): %s", len(args.paths), ", ".join(str(Path(p).resolve()) for p in args.paths))
    return _report(store.ingest_paths(args.paths))


def cmd_series(args):
    """List distinct series in the local store matching optional filters."""
    _, store = _prepare(args, open_store=True)
    listed = store.series(args.workload, args.quantity)
    if not listed:
        logger.info("no series%s", " matches the filter" if args.workload or args.quantity else " in the store")
    for s in listed:
        estimator = json.loads(s["estimator"])["method_version"]
        print(
            f"{s['fingerprint'][:12]}  {s['project']}  {s['workload']}  {s['quantity']} [{s['unit']}]  est={estimator}"
        )
    return EXIT_OK


def cmd_history(args):
    """Print chronological measurement history for a stored series."""
    _, store = _prepare(args, open_store=True)
    points = store.history(args.series)
    if not points:
        logger.info("no series matches %s", args.series)
    elif len(matched := {p["series_fingerprint"] for p in points}) > 1:
        logger.warning(
            "%s matches %d series, whose points are listed together; `changed` is worked out per series: %s",
            args.series,
            len(matched),
            ", ".join(sorted(f[:12] for f in matched)),
        )
    print("revision order unavailable without a revision graph; listed by measurement start")
    for p in points:
        changed = f"  changed: {', '.join(p['changed'])}" if p["changed"] else ""
        warned = f"  [{', '.join(p['warnings'])}]" if p["warnings"] else ""  # such as dirty-subject-tree
        print(
            f"{p['revision'][:12]}  {p['started_at']}  {p['value']:.6g} ({p['source']})  {p['ingest_key']}"
            f"{changed}{warned}"
        )
    return EXIT_OK


def cmd_head(args):
    """Show the latest ingested results from the local store."""
    _, store = _prepare(args, open_store=True)
    total, rows = store.head(args.n, args.project, args.workload, measurands=args.table)
    if args.json:
        for row in rows:
            print(row["document"])
        return EXIT_OK
    if not total:
        logger.info(
            "%s holds no result%s", store.path, "s that match the filter" if args.project or args.workload else ""
        )
    print(f"{store.path}: {total} result(s); latest {len(rows)}, newest first")
    if args.table:  # the columns of `bx bench`, led by where each result came from; measurands only
        print(
            bench_mod.render(
                [
                    {
                        **bench_mod.row_of(json.loads(r["document"])),
                        "revision": r["revision"][:10],
                        "run": r["run_key"],
                        "project": r["project"],
                    }
                    for r in rows
                ],
                leading=("revision", "run", "project"),
            )
        )
        return EXIT_OK
    cells = []
    for r in rows:
        median = f"{r['median']:.6g} {r['unit']}" if r["median"] is not None else "-"
        started = r["started_at"].strftime("%Y-%m-%d %H:%M:%S")
        labels = f"  {r['labels']}" if r["labels"] else ""
        codes = warning_codes(json.loads(r["document"]))  # such as dirty-subject-tree, as `--table` shows them
        status = r["status"] + (f"  [{', '.join(codes)}]" if codes else "")
        cells.append(
            (
                f"{r['row']:>5}",
                started,
                r["run_key"],
                r["workload"],
                r["quantity"],
                status,
                median,
                r["revision"][:10],
                f"{r['project']}{labels}",
            )
        )
    widths = [max([len(cell[i]) for cell in cells], default=0) for i in range(len(cells[0]))] if cells else []
    for cell in cells:
        print("  ".join(text.ljust(width) for text, width in zip(cell, widths)).rstrip())
    return EXIT_OK


def cmd_target(args):
    """Ask for a target's description: `describe` only reports, `prepare` may
    build (the provider's own tools do that, never benchx)."""
    cfg = _prepare(args)
    if args.target.startswith("@"):
        cfg.require_provider(args.target)
    description = target_mod.resolve(args.target, operation=args.operation, provider=cfg.provider)
    if description is None:
        say.warning(f"{args.target} has no description: no {target_mod.SIDECAR} in it")
        return EXIT_INVALID
    print(json.dumps(description, indent=1))
    return EXIT_OK


# Flags that belong to one mode of `bx compare` (prototype-design.md §1).
_MEASURE_ONLY = (
    "adapter",
    "suite",
    "filter",
    "quantity",
    "rounds",
    "env",
    *harnesses.FLAG_NAMES,
    "project",
    "no_project",
    "run_key",
    "out",
    "source_uri",
    "no_build",
    "no_ingest",
)
_READ_ONLY = ("baseline", "results")


def _mode(args, profile) -> str:
    """Select `'measure'` or `'read'` mode and reject flags incompatible with the chosen mode."""
    variants = profile == "variants"
    targets = "one target" if variants else "two targets"
    if args.targets and args.run:
        raise UsageError(f"give {targets} or --run, not both")
    if not args.targets and not args.run:
        raise UsageError(f"give {targets} (measure mode) or --run KEY (read mode)")

    def flagged(names):
        return [f"--{n.replace('_', '-')}" for n in names if getattr(args, n) not in (None, [], False)]

    if args.targets:
        if len(args.targets) != (1 if variants else 2):
            raise UsageError(
                "measure mode takes exactly one target for variants: TARGET"
                if variants
                else "measure mode takes exactly two targets: BASELINE CONTENDER"
            )
        if wrong := flagged(("results",) if variants else _READ_ONLY):
            raise UsageError(f"{', '.join(wrong)} belongs to read mode (--run)")
        return "measure"
    if wrong := flagged(_MEASURE_ONLY):
        raise UsageError(f"{', '.join(wrong)} belongs to measure mode ({targets})")
    if not args.baseline:
        raise UsageError("read mode needs --baseline")
    return "read"


def cmd_compare(args):
    """Compare two targets by measuring them or analyze stored results from an existing run."""
    cfg = _load()
    policy, sources = _policy(cfg, args)
    mode = _mode(args, policy["profile"])
    if args.vary and policy["profile"] != "variants":
        raise UsageError(
            f"--vary names the parameter whose values are the sides of a variants comparison, not of {policy['profile']}"
        )
    if args.label and policy["profile"] == "variants":
        raise UsageError(
            "--label names the sides of an environments comparison; the sides of a variants "
            "comparison are two values of a parameter (--vary)"
        )
    if args.tables and args.json:
        raise UsageError("--tables is a text view: not with --json")
    if args.all and not args.tables:
        raise UsageError("--all goes with --tables")
    sources.append(("mode", mode, "inferred: " + ("targets were given" if mode == "measure" else "--run was given")))
    return _measure(cfg, args, policy, sources) if mode == "measure" else _read(cfg, args, policy, sources)


def _policy(cfg, args) -> tuple[dict, list]:
    """Resolve comparison policy settings (`compare.profile`, `compare.k`, `compare.min_rounds`)
    from CLI flags, config file, or centralized defaults, along with their sources for logging."""
    policy, sources = {}, []
    for field, flag_val, flag in (
        ("profile", args.profile, "--profile"),
        ("k", args.k, "--k"),
        ("min_rounds", args.min_rounds, "--min-rounds"),
    ):
        key = f"compare.{field}"
        value, source = cfg.pick_with_source(key, flag_val, flag=flag)
        policy[field] = value
        sources.append((key, value, source))
    return policy, sources


def _read(cfg, args, policy, sources):
    """Read stored or ad hoc results for a run and render the comparison."""
    # A read stores nothing, so its records join the run's own log when the run folder exists;
    # and a log that cannot be opened there is skipped, not refused, unless a flag named it.
    run_dir = session.run_directory(cfg.results_dir, args.run)
    cfg = _start_logging(cfg, args, run_dir if run_dir.is_dir() else None, "compare", lenient=True)
    log.log_settings(sources)
    if args.results:
        store = MemoryStore()  # the ad hoc path: validated in memory without PyArrow
        outcome = store.ingest_paths(args.results)
        # The throwaway store is discarded on exit: its path would say nothing, so the count does.
        logger.debug("read mode with --results: %d document(s) ingested into a throwaway store", outcome["ingested"])
        if outcome["rejected"]:
            logger.warning("%d document(s) were rejected: the comparison was not run", len(outcome["rejected"]))
            return _report(outcome)
    else:
        store = _open_store(cfg.store_path, hint="pass --results DIR to compare JSON results directly")
    documents = store.documents(args.run)
    parameter = None
    if policy["profile"] == "variants":
        parameter = args.vary or compare_mod.infer_parameter(documents, args.run)
        if not args.vary:  # the choice is recorded in the document's `varying`, and said here too
            say.info(f"varying: {parameter} (the only parameter)")
            logger.info("%s was inferred from %d result document(s) of run %s", parameter, len(documents), args.run)
    doc = compare_mod.compare(
        documents,
        run_key=args.run,
        profile=policy["profile"],
        baseline=args.baseline,
        label=args.label,
        parameter=parameter,
        k=policy["k"],
        min_rounds=policy["min_rounds"],
    )
    _show(doc, args, documents)
    return EXIT_OK


def _measure(cfg, args, policy, sources):
    """The workbench's session loop: run both sides, deliver, compare."""
    # the check phase: nothing has run, and no folder exists yet
    settings = _common(cfg, args)
    session.check_harness(settings["adapter"], settings["flags"], settings["file_precision"], settings["quantities"])
    for spec in args.targets:
        if spec.startswith("@"):
            cfg.require_provider(spec)
    rounds, rounds_source = cfg.pick_with_source("compare.rounds", args.rounds, flag="--rounds")
    label = session.parse_label(args.label) if args.label else None
    store = (
        MemoryStore()
        if args.no_ingest
        else _open_store(
            cfg.store_path,
            hint="pass --no-ingest to compare without persisting to the local store",
        )
    )
    run_key = args.run_key or orders.default_run_key("compare")
    out = Path(args.out) if args.out else session.run_directory(cfg.results_dir, run_key)
    cfg = _start_logging(cfg, args, out, "compare")
    if not args.no_ingest:
        say.info(
            f"{store.path}"
        )  # stderr, so --json output stays clean; after the checks, so a refusal does not print it
    log.log_settings([*sources, *settings.pop("sources"), ("compare.rounds", rounds, rounds_source)])
    settings["run_key"], settings["out"] = run_key, out
    if policy["profile"] == "variants":
        doc = session.compare_variants(
            *args.targets,
            rounds=rounds,
            store=store,
            parameter=args.vary,
            baseline=args.baseline,
            progress=say.info,
            k=policy["k"],
            min_rounds=policy["min_rounds"],
            **settings,
        )
    else:
        doc = session.compare_targets(
            *args.targets, rounds=rounds, store=store, label=label, progress=say.info, **policy, **settings
        )
    _show(doc, args, store.documents(doc["selector"]["params"]["run_key"]) if args.tables else None)
    return EXIT_OK


def _show(doc, args, documents):
    """Print comparison output as JSON or text (and optional tables), noting degraded invariants/units."""
    units, failed = doc["units"], doc.get("failed_invariants", [])
    if failed and not units:
        log.degraded(f"0 units compared, {len(failed)} invariant(s) failed")
    elif failed:
        log.degraded(f"{len(failed)} invariant(s) failed")
    if indeterminate := [u for u in units if u["verdict"] == "indeterminate"]:
        log.degraded(f"{len(indeterminate)} of {len(units)} units indeterminate")
    if args.json:
        print(json.dumps(doc, indent=1))
        return
    print(compare_mod.render(doc))
    if args.tables:
        shown = tables_mod.render(doc, documents, all_rows=args.all)
        if not shown:
            logger.warning(
                "tables skipped: no units, or no contender (%d failed invariant(s))",
                len(doc.get("failed_invariants", [])),
            )
        print(shown)


def cmd_validate(args):
    """Validate one or more benchx JSON documents against the requested schema kind."""
    _start_logging(config_mod.Config.empty(), args, None, "validate", read_config=False)
    valid = 0
    logger.info("validating %d file(s) as %s", len(args.files), args.kind)
    for path in args.files:
        inspection = core.inspect(path, args.kind)
        for error in inspection.errors:
            say.warning(f"{path}: {error}")
        if inspection.valid:
            logger.debug("%s is a valid %s", path, args.kind)
        valid += inspection.valid
    say.info(f"{valid}/{len(args.files)} valid")
    return EXIT_OK if valid == len(args.files) else EXIT_INVALID


def cmd_view(args):
    """Build static dashboard views and optionally serve them over local HTTP."""
    cfg = _load()
    serve = args.serve or args.out is None
    if args.open and not serve:
        raise UsageError("--open goes with serving (omit --out, or pass --serve)")
    cfg = _start_logging(cfg, args, None, "view")

    source_kwargs: dict = {}
    if args.runs is not None:
        source_kwargs["runs_dir"] = args.runs
    elif args.results is not None:
        source_kwargs["results_paths"] = list(args.results)
    else:
        source_kwargs["store_path"] = args.store if args.store is not None else cfg.store_path

    write_marts: bool | None = True if args.marts else False if (args.no_marts or args.out is None) else None
    build_kwargs = {
        **source_kwargs,
        "project_file": Path(args.project_file) if args.project_file else None,
        "title": args.title,
        "repo": Path(args.repo) if args.repo is not None else cfg.root,
        "write_marts": write_marts,
        "views_format": args.views_format,
        "stamp": args.stamp,
        "config": cfg,
    }
    port = 8000 if args.port is None else args.port
    fallback_port = args.port is None

    with contextlib.ExitStack() as stack:
        out_dir = (
            Path(args.out)
            if args.out is not None
            else Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="benchx-view-")))
        )
        try:
            summary = views_mod.build_site(out_dir, **build_kwargs)
        except ModuleNotFoundError as exc:
            if not _is_missing_pyarrow(exc):
                raise
            hint = (
                ", or pass --results DIR to build views from JSON results directly"
                if "store_path" in source_kwargs
                else ""
            )
            raise BenchxError(f"{exc}{hint}") from None

        exit_code = _report(summary["outcome"]) if summary["outcome"] and summary["outcome"]["rejected"] else EXIT_OK
        counts = summary["counts"]
        dest = f" -> {summary['out']}" if args.out is not None else ""
        print(f"{counts['points']} result(s), {counts['series']} series, {counts['distinct_commits']} commit(s){dest}")
        if serve:
            try:
                views_mod.serve_site(
                    out_dir,
                    host=args.host,
                    port=port,
                    fallback_port=fallback_port,
                    open_browser=args.open,
                )
            except OSError as exc:
                raise BenchxError(f"cannot serve on {args.host}:{port}: {exc}") from None
        return exit_code


def _add_target_options(parser, command):
    """The options `bx bench` and `bx compare` (measure mode) share: the harness,
    its suite and cases, its precision flags, and where the results go."""
    parser.add_argument(
        "--adapter", choices=sorted(harnesses.HARNESSES), help="the harness (default: adapter.name; required)"
    )
    parser.add_argument(
        "--suite",
        help="pyperf: the module's path in the working tree; "
        "google-benchmark: the binary in the build directory "
        "(default: adapter.suite; required)",
    )
    parser.add_argument(
        "--filter",
        help="a case filter regex (pyperf, asv: searched in the name, and in "
        "name(p0, p1) of a parametrized benchmark; "
        "google-benchmark: --benchmark_filter)",
    )
    parser.add_argument(
        "--quantity",
        metavar="NAMES",
        help=f"comma-separated, collected in one run (default: adapter.quantities, else "
        f"{', '.join(config_mod.DEFAULTS['adapter.quantities'])}); google-benchmark also reports cpu-time",
    )
    parser.add_argument(
        "-e",
        "--env",
        action="append",
        metavar="NAME=VALUE",
        help="set an environment variable for the benchmark (repeatable); each becomes a workload parameter",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        help=f"google-benchmark: repetitions per case (default {harnesses.GOOGLE_BENCHMARK.DEFAULT_REPETITIONS})",
    )
    parser.add_argument(
        "--processes", type=int, help=f"pyperf: worker processes (default {harnesses.PYPERF.DEFAULT_PROCESSES})"
    )
    parser.add_argument(
        "--values", type=int, help=f"pyperf: values per process (default {harnesses.PYPERF.DEFAULT_VALUES})"
    )
    parser.add_argument("--min-time", type=float, help="adaptive calibration: minimum seconds per sample")
    parser.add_argument("--loops", type=int, help="pyperf: fixed calibration, inner loops per value")
    parser.add_argument("--warmups", type=int, help="pyperf: warmup values per process (0: none)")
    parser.add_argument("--project", help="name a project, so the results join its series (default: project)")
    parser.add_argument(
        "--no-project",
        action="store_true",
        help="an ad hoc run, whatever the file's project says: filed as local/<hostname>",
    )
    parser.add_argument("--run-key", help=f"default: {command}-<UTC timestamp>")
    parser.add_argument(
        "--out",
        help="directory for orders and result files (default: RESULTS/RUN_KEY, "
        "RESULTS being paths.results, else ./results in the project root)",
    )
    parser.add_argument(
        "--harness-verbosity",
        type=log.parse_non_negative,
        metavar="N",
        help=f"ask the harness to say more (default {config_mod.DEFAULTS['adapter.verbosity']}: nothing more). "
        "pyperf and asv: 1 or more passes --verbose; Google Benchmark: N is passed as --v=N. Its output is "
        f"logged in full. Each -v past -vv does the same (-vvv is 1). ${log.HARNESS_VERBOSITY_ENV}, adapter.verbosity",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="ask a provider to describe each @CONFIG target instead of preparing (building) it",
    )
    parser.add_argument(
        "--source-uri", help="the source's URI (default: source.uri, else the checkout's origin remote)"
    )


def _logging_options() -> argparse.ArgumentParser:
    """The options every subcommand takes: where the log goes, how much it keeps, and how much
    the terminal shows. The three switch flags share one destination, so
    `--no-log`, `--log` and `--log-file PATH` exclude each other. None means not given, so
    any flag beats the environment and the file."""
    parent = argparse.ArgumentParser(add_help=False)
    group = parent.add_mutually_exclusive_group()
    group.add_argument(
        "--no-log",
        dest="log",
        action="store_const",
        const=False,
        default=None,
        help="write no log (the default is bx.log in the run's output folder)",
    )
    group.add_argument(
        "--log",
        dest="log",
        action="store_const",
        const=True,
        default=None,
        help="send the whole log to stderr instead of a file",
    )
    group.add_argument(
        "--log-file",
        dest="log",
        metavar="PATH",
        help="append the log to PATH ({out} is the run's output folder, {root} the project root)",
    )
    parent.add_argument(
        "--log-level",
        type=str.lower,
        choices=list(log.LEVELS),
        metavar="LEVEL",
        help=f"what the log keeps: {', '.join(log.LEVELS)} (default {config_mod.DEFAULTS['log_level']}; ${log.LOG_LEVEL_ENV})",
    )
    parent.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=None,
        help=f"show more on the terminal: -v every INFO record, -vv DEBUG too; each -v past -vv also asks the "
        f"harness to say more (--harness-verbosity) (${log.VERBOSE_ENV})",
    )
    parent.add_argument(
        "-q",
        "--quiet",
        action="count",
        default=None,
        help="show less on the terminal: -q hides the table and the other INFO messages (it keeps warnings, "
        "errors, the start line, the not-measured section and the result line); -qq keeps "
        "only errors and the not-measured section",
    )
    return parent


def main(argv=None):
    options = _logging_options()
    ap = argparse.ArgumentParser(prog="bx", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", parents=[options], help="execute one work order (schemas/work-order/0.1.0)")
    p.add_argument("order")
    p.add_argument("--out", help="directory for result files (default ./results)")
    p.add_argument(
        "--no-ingest", action="store_true", help="only write the result files; do not deliver them to the local store"
    )
    p.add_argument(
        "--allow-collectors",
        action="store_true",
        help="run the order's context collectors: commands the order names (otherwise refused)",
    )
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser(
        "bench",
        parents=[options],
        help="benchmark one target: the single-target form of bx compare",
        description="bx bench TARGET --suite S [FUNCTION ...]: run one target once and print a table "
        "per case. TARGET and the options are those of bx compare: @CONFIG[=SOURCE_REF] "
        "(the project's target provider) or a path, which the harness reads (pyperf: a "
        "working tree; google-benchmark: BUILD_DIR[:SOURCE_DIR]). Each FUNCTION is an "
        "exact case name; with none, the harness's default cases. The shorthand "
        "bx bench MODULE.py [FUNCTION ...] benchmarks a Python module with pyperf: "
        "its checkout is the target, and its path there the suite. The shorthand "
        "bx bench PATH --adapter asv runs an asv suite, timed by pyperf: PATH holds "
        "asv.conf.json (its benchmark_dir is the suite) or is the benchmark directory; "
        "--filter searches name(p0, p1) per parameter combination, as asv run --bench, "
        "and the precision flags left out come from each benchmark's own attributes. "
        "Precision comes "
        "from the harness's defaults, the config file (pyperf; bx config init "
        "writes one) and the flags: flags win.",
    )
    p.add_argument(
        "target",
        metavar="TARGET",
        help="@CONFIG[=SOURCE_REF], a path, or (with no --suite) a Python file or an asv suite",
    )
    p.add_argument(
        "functions",
        nargs="*",
        metavar="FUNCTION",
        help="exact case names (default: all cases); pyperf, asv: the name of a "
        "parametrized benchmark selects all its combinations",
    )
    _add_target_options(p, "bench")
    p.add_argument("--tree", help="the shorthand's tree (default: the module's or suite's git checkout or directory)")
    p.add_argument(
        "--case-timeout",
        type=float,
        help=f"seconds before one case is stopped (default: timeouts.case_s, else "
        f"{config_mod.DEFAULTS['timeouts.case_s']:g}; asv: {harnesses.ASV.DEFAULT_CASE_TIMEOUT_S}, "
        "all rounds, each also stopped at the benchmark's own timeout)",
    )
    p.add_argument(
        "--label",
        action="append",
        metavar="NAME=VALUE",
        help="name this call's side of a session, such as env=numpy-2.0 (repeatable); the calls of a "
        "session share --run-key, and bx compare --run reads the label with --label NAME. "
        "Needs --run-key and --slot",
    )
    p.add_argument(
        "--round",
        metavar="R[/N]",
        help="this call's round in a session, numbered from 0: the sides' attempts are paired by it. "
        "R/N also says the session has N rounds, which the start line shows (nothing else uses "
        "it). Needs --run-key and --slot",
    )
    p.add_argument(
        "--slot",
        type=int,
        help="this call's position in the session's alternation (0, 1, 2, ...), kept by the caller's loop. "
        "Needs --run-key",
    )
    p.add_argument("--no-ingest", action="store_true", help="only write result files; skip the local store")
    p.set_defaults(fn=cmd_bench)

    p = sub.add_parser("config", parents=[options], help="write or show benchx.conf.json")
    p.add_argument(
        "action",
        choices=["init", "show"],
        help="init: write a benchx.conf.json stating a harness's defaults; show: what the file and the defaults give",
    )
    p.add_argument("--dir", default=".", help="init: where to write benchx.conf.json (default .)")
    p.add_argument(
        "--adapter",
        choices=sorted(harnesses.HARNESSES),
        default="pyperf",
        help="init: the harness (default %(default)s)",
    )
    p.set_defaults(fn=cmd_config)

    p = sub.add_parser("ingest", parents=[options], help="sweep result files and work orders into the local store")
    p.add_argument("paths", nargs="+")
    p.set_defaults(fn=cmd_ingest)

    p = sub.add_parser("series", parents=[options], help="list series")
    p.add_argument("--workload")
    p.add_argument("--quantity")
    p.set_defaults(fn=cmd_series)

    p = sub.add_parser("history", parents=[options], help="one series' points (a query; history mode is deferred)")
    p.add_argument("series", help="series fingerprint or prefix")
    p.set_defaults(fn=cmd_history)

    p = sub.add_parser("head", parents=[options], help="the latest results in the store, newest first")
    p.add_argument("-n", type=int, default=10, help="how many (default 10)")
    p.add_argument("--project", help="only this store project's results (e.g. numpy, local/HOST)")
    p.add_argument("--workload", help="only results whose benchmark name contains this")
    shape = p.add_mutually_exclusive_group()
    shape.add_argument("--json", action="store_true", help="print the stored documents instead")
    shape.add_argument(
        "--table",
        action="store_true",
        help="the `bx bench` table (median, mean ± sd, range, n, status) with revision, run and project",
    )
    p.set_defaults(fn=cmd_head)

    p = sub.add_parser(
        "target",
        parents=[options],
        help="ask for a target's description (schemas/target-description/0.1.0)",
        description="TARGET is @CONFIG[=SOURCE_REF], asking the provider named in "
        "benchx.conf.json, or a build directory holding .benchx-target.json. "
        "describe only reports a target that exists; prepare may build it.",
    )
    p.add_argument("operation", choices=["describe", "prepare"])
    p.add_argument("target")
    p.set_defaults(fn=cmd_target)

    p = sub.add_parser(
        "compare",
        parents=[options],
        help="compare two sides: read mode (--run) or measure mode (two targets)",
        description="Read mode compares results already measured: --run KEY --baseline VALUE. "
        "Measure mode runs two prepared targets, alternating them over "
        "--rounds rounds, delivers the results to the local store, then compares: "
        "BASELINE CONTENDER --suite NAME --rounds R, each target BUILD_DIR[:SOURCE_DIR] "
        "or @CONFIG[=SOURCE_REF] (the project's target provider). "
        "The variants profile takes one target: its sides are two values of one "
        "benchmark parameter (--vary), as in TARGET --profile variants --suite NAME "
        "--rounds R.",
    )
    p.add_argument("targets", nargs="*", metavar="TARGET", help="measure mode: BASELINE CONTENDER (variants: TARGET)")
    p.add_argument("--profile", choices=list(compare_mod.PROFILES), help="default: compare.profile")
    p.add_argument(
        "--vary",
        metavar="NAME",
        help="variants: the workload parameter whose two values are the sides "
        "(default: the only parameter the results carry)",
    )
    p.add_argument(
        "--k",
        type=float,
        help="confidence in normal sigmas: the threshold is the t quantile with that two-sided tail, "
        f"times the noise (default: compare.k, else {config_mod.DEFAULTS['compare.k']:g})",
    )
    p.add_argument(
        "--min-rounds",
        type=int,
        help=f"fewest paired rounds for a verdict (default: compare.min_rounds, else "
        f"{config_mod.DEFAULTS['compare.min_rounds']})",
    )
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--tables", action="store_true", help="after the summary, asv-style tables: one per side, then the changes"
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="with --tables: every row of the change table, not only the changed ones (as asv continuous)",
    )
    p.add_argument(
        "--label", help="read mode: the label that names the sides (environments); measure mode: NAME=BASE,CONTENDER"
    )
    p.add_argument(
        "--baseline",
        help="revisions: a revision or tree id prefix; environments: the label value; "
        "variants: the parameter's recorded value, quotes included ('baseline'); "
        "required in read mode, and in measure mode only for variants "
        "(default: the first declared value)",
    )
    read = p.add_argument_group("read mode")
    read.add_argument("--run", help="run key")
    read.add_argument(
        "--results", nargs="+", help="compare these result files or directories directly, without using the local store"
    )
    measure = p.add_argument_group("measure mode")
    measure.add_argument(
        "--rounds",
        type=int,
        help=f"alternation rounds; each runs both sides once (default: compare.rounds, else "
        f"{config_mod.DEFAULTS['compare.rounds']})",
    )
    measure.add_argument(
        "--no-ingest", action="store_true", help="write result files and compare in memory; skip the local store"
    )
    _add_target_options(measure, "compare")
    p.set_defaults(fn=cmd_compare)

    p = sub.add_parser(
        "validate",
        parents=[options],
        help="check documents against their schema and rules",
        description="Report every problem in each document, or nothing when all are valid.",
    )
    p.add_argument("files", type=Path, nargs="+")
    p.add_argument(
        "--kind",
        choices=get_args(Kind),
        default="measurement-result",
        help="kind of document being checked (default: %(default)s)",
    )
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser(
        "view",
        parents=[options],
        help="build and serve the static benchmark dashboard",
        description="Build static dashboard views from the local Parquet store, JSON result files "
        "(--results, no PyArrow required), or a runs/<sha>/<node>/ directory (--runs). "
        "With no --out, builds into a temporary directory and serves locally until Ctrl-C; "
        "with --out DIR, writes the static site (add --serve to also serve it).",
    )
    src = p.add_mutually_exclusive_group()
    src.add_argument("--store", help="local Parquet store (default: paths.store / $BENCHX_HOME/store.parquet)")
    src.add_argument("--results", nargs="+", help="JSON result files or directories, read directly without PyArrow")
    src.add_argument("--runs", help="runs/<sha>/<node>/ directory holding run.parquet and results.parquet")
    p.add_argument("--out", help="write the static site into DIR instead of a temporary directory")
    p.add_argument("--serve", action="store_true", help="serve the built site over local HTTP")
    p.add_argument("--host", default="127.0.0.1", help="bind address for local serving (default %(default)s)")
    p.add_argument(
        "--port",
        type=int,
        default=None,
        help="TCP port for local serving (default 8000, falling back to a free port if busy)",
    )
    p.add_argument("--open", action="store_true", help="open the served dashboard in the default web browser")
    p.add_argument("--project-file", help="project.json describing title, links, and upstream commit URL")
    p.add_argument("--title", help="override the dashboard page title")
    p.add_argument("--repo", help="git checkout used to enrich commit metadata for --store / --results")
    marts_group = p.add_mutually_exclusive_group()
    marts_group.add_argument(
        "--marts", action="store_true", help="write derived Parquet tables under data/ (requires benchx[parquet])"
    )
    marts_group.add_argument("--no-marts", action="store_true", help="skip writing derived Parquet tables under data/")
    p.add_argument(
        "--views-format",
        choices=("json", "parquet"),
        default="json",
        help="format for frontend view payloads under data/views/ (default %(default)s; parquet requires benchx[parquet])",
    )
    p.add_argument("--stamp", help="cache-busting version stamped onto static asset URLs in index.html")
    p.set_defaults(fn=cmd_view)

    args, extra = ap.parse_known_args(argv)
    # argparse takes a nargs="*" positional only from the first run of positionals, so cases
    # given after an option (`bx bench T --suite S CASE`) arrive here, on some Python versions.
    if args.cmd == "bench" and not any(item.startswith("-") for item in extra):
        args.functions += extra
    elif extra:
        ap.error(f"unrecognized arguments: {' '.join(extra)}")
    args.argv = list(sys.argv[1:] if argv is None else argv)  # the header records the command as given
    try:
        args.verbosity, args.verbosity_source, args.verbose_extra = log.resolve_verbosity(args)
    except UsageError as e:
        log.start_console(0)
        say.error(f"bx {args.cmd}: error: {e}")
        log.stop()
        return EXIT_REFUSED
    log.start_console(args.verbosity)  # first, so that a broken config file is still reported
    outcome, code = "crashed", None
    try:
        code = args.fn(args)
        outcome = OUTCOMES.get(code, "crashed")
        return code
    except runner.Refused as e:
        for problem in e.problems:
            say.error(f"refused: {problem}")
        code = EXIT_REFUSED
        outcome = OUTCOMES[code]
        return code
    except (BenchxError, core.catalog.FormatCheckerError) as e:
        say.error(f"bx {args.cmd}: error: {e}")
        code = EXIT_REFUSED
        outcome = OUTCOMES[code]
        return code
    except SystemExit as e:  # argparse, or a command that exits: let it through
        code = e.code if isinstance(e.code, int) else 0 if e.code is None else 1
        outcome = OUTCOMES.get(code, "crashed")
        raise
    except KeyboardInterrupt:
        logger.warning("interrupted")
        outcome = "interrupted"
        raise  # Python prints its traceback and exits by the signal, as it does without a log
    except Exception:  # what Python's own handler would print, and its exit status
        say.error(traceback.format_exc().rstrip("\n"))
        code = 1
        return code
    finally:
        log.footer(outcome, code)
        log.stop()


if __name__ == "__main__":
    sys.exit(main())
