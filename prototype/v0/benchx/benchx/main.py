"""Command-line entry point (`bx`).

Commands call into the library and turn its exceptions into output; no
validation logic lives here.
"""

import argparse
import sys
from pathlib import Path

from .core import inspect
from .core.errors import DocumentError

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
        description="Report the first problem in each document, "
        "or nothing when all are valid.",
    )
    parser.add_argument("files", type=Path, nargs="+")
    parser.add_argument(
        "--kind",
        choices=["measurement-result", "work-order", "comparison-document"],
        default="measurement-result",
        help="kind of document being checked (default: %(default)s)",
    )
    parser.set_defaults(run=run_validate)


def run_validate(arguments: argparse.Namespace) -> int:
    invalid = 0

    for path in arguments.files:
        try:
            inspect(path, arguments.kind)
        except DocumentError as error:
            print(f"{path}: {error}", file=sys.stderr)
            invalid += 1

    checked = len(arguments.files)
    print(f"{checked - invalid}/{checked} valid", file=sys.stderr)
    return EXIT_INVALID if invalid else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
