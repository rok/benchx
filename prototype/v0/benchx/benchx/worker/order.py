"""Accepting a work order (worker-prototype.md section 2, stage 1).

The order is parsed strictly, validated, referenced by content, and checked
for applicability: the adapter must exist and must be able to apply every
quantity and protocol key it names (work-order.md W5).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from . import schemas
from .errors import OrderRejected


@dataclass(frozen=True)
class Order:
    path: Path
    document: dict
    canonical: bytes
    ref: str  # "sha256:<hex>" over the canonical form

    @property
    def harness(self) -> dict:
        return self.document["harness"]

    @property
    def quantities(self) -> list[str]:
        return list(self.document["quantities"])

    @property
    def protocol(self) -> dict:
        return dict(self.document.get("protocol", {}))

    @property
    def provenance(self) -> dict:
        return dict(self.document["provenance"])

    def repetition_level(self, unit: str, default: int | None = None) -> int | None:
        """The `n` of the protocol repetition level named `unit`, if requested."""
        for level in self.protocol.get("repetitions", {}).get("levels", []):
            if level["unit"] == unit:
                return level["n"]
        return default


def canonicalize(document: dict) -> bytes:
    """RFC 8785 canonical form, which `workorder_ref` hashes."""
    import rfc8785

    return rfc8785.dumps(document)


def load(path: str | Path) -> Order:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OrderRejected(f"cannot read {path}: {exc}") from exc
    try:
        document = json.loads(text)
    except ValueError as exc:
        raise OrderRejected(f"{path} is not valid JSON: {exc}") from exc
    try:
        schemas.validate(document, "work_order")
    except schemas.SchemaError as exc:
        raise OrderRejected(str(exc)) from exc

    canonical = canonicalize(document)
    ref = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return Order(path=path, document=document, canonical=canonical, ref=ref)


def accept(order: Order, adapter) -> None:
    """Reject anything the adapter cannot apply, before touching the machine."""
    unsupported = [q for q in order.quantities if q not in adapter.QUANTITIES]
    if unsupported:
        raise OrderRejected(
            f"{adapter.NAME} cannot produce {', '.join(sorted(unsupported))}; "
            f"it maps {', '.join(sorted(adapter.QUANTITIES))}"
        )
    unknown = sorted(set(order.protocol) - set(adapter.PROTOCOL_KEYS))
    if unknown:
        raise OrderRejected(
            f"{adapter.NAME} cannot apply protocol key(s): {', '.join(unknown)}"
        )
    adapter.check_order(order)
