"""The pipeline (worker-prototype.md section 2), driving half only.

Stages 1-5 are implemented: accept, materialize, plan, capture, execute.
Stage 6, translating invocations into measurement results, is the next
milestone; until then the run directory holds the raw harness output, the
context document, and the accounting log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .. import adapters
from . import context, document, order as order_module, vcs
from .errors import WorkerError

DEFAULT_TIMEOUT_SECONDS = 1800.0


@dataclass
class Outcome:
    exit_code: int
    run_dir: Path | None = None
    planned: list = field(default_factory=list)
    invocations: list = field(default_factory=list)
    message: str = ""

    def summary(self) -> str:
        if self.exit_code != 0 and not self.invocations:
            return self.message
        failed = [i for i in self.invocations if i.returncode != 0 or i.timed_out]
        return (
            f"planned {len(self.planned)} case(s); "
            f"ran {len(self.invocations)}, {len(failed)} failed; "
            f"raw output in {self.run_dir}"
        )


def _run_dir(out_dir: Path, order) -> Path:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    return out_dir / f"{stamp}-{order.ref.split(':', 1)[1][:8]}"


def _capture(order, target) -> document.ContextDocument:
    return document.build(
        order,
        target,
        revision=vcs.describe(target.source_dir),
        environment=context.environment(),
        observed=context.observed(),
        runner=context.runner(),
        warnings=context.warnings(),
    )


def run(order_path, out_dir="results", dry_run: bool = False,
        timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Outcome:
    from .target import resolve

    try:
        order = order_module.load(order_path)
        adapter = adapters.get(order.harness["name"])
        order_module.accept(order, adapter)
        target = resolve(order)
        planned = adapter.plan(order, target)
        captured = _capture(order, target)
    except WorkerError as exc:
        return Outcome(exit_code=exc.exit_code, message=str(exc))

    if dry_run:
        return Outcome(
            exit_code=0,
            planned=planned,
            message=_describe(order, target, planned, captured),
        )

    run_dir = _run_dir(Path(out_dir), order)
    (run_dir / "raw").mkdir(parents=True, exist_ok=True)
    (run_dir / "workorder.json").write_bytes(order.canonical)
    document.write_json(captured.to_dict(), run_dir / "context.json")

    invocations = []
    for case in planned:
        invocations.append(adapter.invoke(order, target, case, run_dir / "raw", timeout))
        document.write_json(
            _accounting(order, target, planned, invocations, timeout),
            run_dir / "run.json",
        )
    return Outcome(exit_code=0, run_dir=run_dir, planned=planned,
                   invocations=invocations)


def _accounting(order, target, planned, invocations, timeout) -> dict:
    """What was planned and what happened, so a truncated run is visible."""
    return {
        "workorder_ref": order.ref,
        "harness": order.harness,
        "suite": order.document["suite"],
        "timeout_seconds": timeout,
        "planned": [
            {"name": case.name, "label": case.label} for case in planned
        ],
        "planned_set_known": all(case.name is not None for case in planned),
        "invocations": [
            {
                "case": invocation.case.label,
                "argv": invocation.argv,
                "returncode": invocation.returncode,
                "timed_out": invocation.timed_out,
                "started_at": invocation.started_at,
                "ended_at": invocation.ended_at,
                "duration_seconds": invocation.duration_seconds,
                "raw": str(invocation.raw_path) if invocation.raw_path else None,
                "parsed": invocation.raw is not None,
            }
            for invocation in invocations
        ],
        "results_written": False,
        "note": "translation to measurement results is the next milestone",
    }


def _describe(order, target, planned, captured) -> str:
    lines = [
        f"work order {order.path} ({order.ref})",
        f"harness    {order.harness['name']}",
        f"target     {target.kind}: {target.executable or target.python}",
        f"suite      {order.document['suite']}",
        f"quantities {', '.join(order.quantities)}",
        f"checkout   {target.source_dir} "
        f"({captured.revision['dirty']}, {captured.revision['revision']})",
        f"machine    {captured.environment['identity']['hostname']} "
        f"({captured.environment['identity']['cpu_count']} cpus)",
    ]
    if all(case.name is not None for case in planned):
        lines.append(f"planned    {len(planned)} case(s):")
        lines += [f"  {case.name}" for case in planned]
    else:
        lines.append("planned    unknown: this harness cannot list its cases")
    return "\n".join(lines)
