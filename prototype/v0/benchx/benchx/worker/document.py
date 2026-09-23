"""The context document: what the harness cannot know (#31).

The driving half captures it before execution and hands it, with the raw
harness output, to the translating half. Nothing here comes from a harness,
so results from different harnesses on one machine agree about the machine.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class ContextDocument:
    workorder_ref: str
    project: str | None
    source: dict
    harness: dict
    subject_name: str
    subject_configuration: dict
    revision: dict  # {"revision": ..., "dirty": ..., "tree": ...}
    environment: dict
    observed_context: dict
    runner: dict
    protocol: dict
    provenance: dict  # run_key, and requested_by/reason/labels when given
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def subject_name(source_uri: str) -> str:
    """Derived, because the order does not carry one (work-order.md section 7)."""
    return source_uri.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git") or "unknown"


def build(order, target, revision: dict, environment: dict, observed: dict,
          runner: dict, warnings: list) -> ContextDocument:
    document = order.document
    return ContextDocument(
        workorder_ref=order.ref,
        project=document.get("project"),
        source=document["source"],
        harness=document["harness"],
        subject_name=subject_name(document["source"]["uri"]),
        subject_configuration=target.configuration,
        revision=revision,
        environment=environment,
        observed_context=observed,
        runner=runner,
        protocol=order.protocol,
        provenance=order.provenance,
        warnings=warnings,
    )


def write_json(document: dict, path: Path) -> Path:
    """Write atomically: a crash never leaves a partial document behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(document, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path
