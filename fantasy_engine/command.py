"""The fantasy-engine command (PLAN.md Part 4c).

    fantasy-engine list
    fantasy-engine build NAME
    fantasy-engine run NAME [--no-viewer] [--debug-access]
    fantasy-engine new NAME FROM
    fantasy-engine prepare

``list`` shows the shipped configurations and the user's own, with whether
each is built.  ``build`` builds a configuration's volumes; ``run`` builds
them when what they were built from changed, serves them in MegaPad's
simulator and opens the viewer, and stops the server when the viewer
closes.  ``new`` copies a configuration under a new name for the user to
edit.  ``prepare`` assembles the components at the commits ``components.toml``
records and builds their native parts, which ``build`` and ``run`` also do.
With ``--workspace DIR`` the commands use that workspace's checkouts as they
stand instead, which is development mode.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import components, machines


def _add_sources(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace", type=Path, metavar="DIR",
        help="development mode: use the checkouts in DIR as they stand")
    parser.add_argument(
        "--components", type=Path, default=components.LOCK_FILE, metavar="FILE",
        help="the lock file to build from (default: this repository's components.toml)")
    parser.add_argument(
        "--cache-dir", type=Path, metavar="DIR",
        help="where assembled components are kept (default: ~/.cache/fantasy-engine)")


def _add_data(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--data-dir", type=Path, metavar="DIR",
        help="where configurations' folders are kept "
             "(default: ~/.local/share/fantasy-engine)")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fantasy-engine",
        description="Build and run Fantasy Engine's configurations.")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    listing = commands.add_parser(
        "list", help="show the configurations and whether each is built")
    _add_data(listing)

    build = commands.add_parser("build", help="build a configuration's volumes")
    build.add_argument("name")
    _add_sources(build)
    _add_data(build)

    run = commands.add_parser(
        "run", help="run a configuration, building it first when needed")
    run.add_argument("name")
    run.add_argument(
        "--no-viewer", action="store_true",
        help="serve without opening the viewer, until interrupted")
    run.add_argument(
        "--debug-access", action="store_true",
        help="let clients read the machine's memory and control it over the socket")
    _add_sources(run)
    _add_data(run)

    new = commands.add_parser(
        "new", help="copy a configuration under a new name to edit")
    new.add_argument("name")
    new.add_argument("original", metavar="FROM")
    _add_sources(new)
    _add_data(new)

    prepare = commands.add_parser(
        "prepare", help="prepare the components at their recorded commits",
        description="Assemble each component at the commit the lock file records "
                    "and build its native parts.")
    prepare.add_argument(
        "--components", type=Path, default=components.LOCK_FILE, metavar="FILE",
        help="the lock file to build from (default: this repository's components.toml)")
    prepare.add_argument(
        "--cache-dir", type=Path, metavar="DIR",
        help="where assembled components are kept (default: ~/.cache/fantasy-engine)")
    return parser


def _trees(args: argparse.Namespace) -> machines.Trees:
    return machines.trees(workspace=args.workspace, lock_file=args.components,
                          cache_dir=args.cache_dir)


def _list(args: argparse.Namespace) -> int:
    for machine in machines.catalog(args.data_dir):
        built = machines.manifest(machine)
        kind = "own" if machine.own else "shipped"
        state = "built" if built is not None else "not built"
        title = f"  {built['title']}" if built and built.get("title") else ""
        print(f"{machine.name}  ({kind}, {state}){title}")
    return 0


def _build(args: argparse.Namespace) -> int:
    machine = machines.find(args.name, args.data_dir)
    machines.build(machine, _trees(args))
    return 0


def _run(args: argparse.Namespace) -> int:
    machine = machines.find(args.name, args.data_dir)
    return machines.run(machine, _trees(args), data_dir=args.data_dir,
                        viewer=not args.no_viewer, debug_access=args.debug_access)


def _new(args: argparse.Namespace) -> int:
    original = machines.find(args.original, args.data_dir)
    machine = machines.new(args.name, original, _trees(args), args.data_dir)
    print(f"{machine.name}: {machine.configuration}")
    return 0


def _prepare(args: argparse.Namespace) -> int:
    trees = components.prepare(args.components, cache_dir=args.cache_dir)
    for name, tree in trees.items():
        print(f"{name}: {tree}")
    return 0


_COMMANDS = {"list": _list, "build": _build, "run": _run, "new": _new, "prepare": _prepare}


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # Whatever the command and the programs it starts create is the user's
    # alone; the image tool and the server also set their files' modes.
    previous = os.umask(0o077)
    try:
        return _COMMANDS[args.command](args)
    except (components.ComponentError, machines.MachineError) as error:
        print(f"fantasy-engine: {error}", file=sys.stderr)
        return 1
    finally:
        os.umask(previous)


if __name__ == "__main__":
    raise SystemExit(main())
