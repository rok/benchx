"""Command-line entry point (`bx`)."""

import argparse
import sys
from pathlib import Path
from typing import get_args

from .core import inspect
from .core.validation import Kind

EXIT_OK = 0
EXIT_INVALID = 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bx")
    subcommands = parser.add_subparsers(dest="command", required=True)
    _add_validate(subcommands)

    arguments = parser.parse_args(argv)
    return arguments.run(arguments)


def _add_validate(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "validate",
        help="check documents against their schema and rules",
        description="Report every problem in each document, "
        "or nothing when all are valid.",
    )
    parser.add_argument("files", type=Path, nargs="+")
    parser.add_argument(
        "--kind",
        choices=get_args(Kind),
        default="measurement-result",
        help="kind of document being checked (default: %(default)s)",
    )
    parser.set_defaults(run=run_validate)


def run_validate(arguments: argparse.Namespace) -> int:
    valid = 0

    for path in arguments.files:
        inspection = inspect(path, arguments.kind)
        for error in inspection.errors:
            print(f"{path}: {error}", file=sys.stderr)
        valid += inspection.valid

    checked = len(arguments.files)
    print(f"{valid}/{checked} valid", file=sys.stderr)
    return EXIT_OK if valid == checked else EXIT_INVALID


if __name__ == "__main__":
    raise SystemExit(main())
