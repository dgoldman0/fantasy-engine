"""The fantasy-engine command (PLAN.md Part 4c).

``fantasy-engine build`` prepares what every configuration is built from:
each component at the commit ``components.toml`` records, assembled into
the cache, with its native parts built.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import components


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fantasy-engine",
        description="Build and run Fantasy Engine's configurations.")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    build = commands.add_parser(
        "build", help="prepare the components at their recorded commits",
        description="Assemble each component at the commit the lock file records "
                    "and build its native parts.")
    build.add_argument(
        "--components", type=Path, default=components.LOCK_FILE, metavar="FILE",
        help="the lock file to build from (default: this repository's components.toml)")
    build.add_argument(
        "--cache-dir", type=Path, metavar="DIR",
        help="where assembled components are kept (default: ~/.cache/fantasy-engine)")
    return parser


def _build(args: argparse.Namespace) -> int:
    trees = components.prepare(args.components, cache_dir=args.cache_dir)
    for name, tree in trees.items():
        print(f"{name}: {tree}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _build(args)
    except components.ComponentError as error:
        print(f"fantasy-engine: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
