"""`bx run`, until it is wired into the package's own CLI (#34).

    python -m benchx.worker.cli ORDER [--out DIR] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys

from .run import DEFAULT_TIMEOUT_SECONDS, run


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="bx run", description=__doc__)
    parser.add_argument("order", help="path to a work order")
    parser.add_argument("--out", default="results", help="output directory")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="accept the order, plan, and capture context, but run nothing",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="seconds per invocation (recorded; a work order field would be better)",
    )
    args = parser.parse_args(argv)

    outcome = run(args.order, args.out, dry_run=args.dry_run, timeout=args.timeout)
    stream = sys.stdout if outcome.exit_code == 0 else sys.stderr
    print(outcome.summary() if not args.dry_run else outcome.message, file=stream)
    return outcome.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
