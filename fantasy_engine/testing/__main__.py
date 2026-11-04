"""Command line for test selection.

    python -m fantasy_engine.testing run [PATTERN ...]   run what changed
    python -m fantasy_engine.testing run --full          run everything
    python -m fantasy_engine.testing run --dry-run       show what would run
    python -m fantasy_engine.testing list [PATTERN ...]  list the units
    python -m fantasy_engine.testing explain UNIT        what changed since its pass

A PATTERN matches unit names such as ``akashic:local_testing/test_pad.py``
or ``lm1:phase1``, with shell wildcards; without a wildcard it matches any
unit whose name contains it.  ``--set`` picks the release's units (the
default), the units outside the release, or both.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path

from .runner import Lock, Runner, decide, launch_key
from .store import Store
from .suites import Unit, repositories


def _matches(unit: Unit, patterns: list[str]) -> bool:
    if not patterns:
        return True
    for pattern in patterns:
        if any(c in pattern for c in "*?["):
            if fnmatch.fnmatchcase(unit.id, pattern):
                return True
        elif pattern in unit.id:
            return True
    return False


def _select(args) -> tuple[list, list[Unit]]:
    repos = repositories(Path(args.workspace) if args.workspace else None)
    if args.repo:
        unknown = set(args.repo) - {repo.name for repo in repos}
        if unknown:
            raise SystemExit("No repository named %s" % ", ".join(sorted(unknown)))
        repos = [repo for repo in repos if repo.name in args.repo]
    units = []
    for repo in repos:
        for unit in repo.units():
            if args.set == "release" and not unit.in_release:
                continue
            if args.set == "outside" and unit.in_release:
                continue
            if _matches(unit, args.patterns):
                units.append(unit)
    return repos, units


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("patterns", nargs="*", metavar="PATTERN")
    parser.add_argument("--repo", action="append",
                        help="limit to a repository (repeatable)")
    parser.add_argument("--set", choices=("release", "outside", "all"),
                        default="release")
    parser.add_argument("--workspace", help="the folder holding the repositories")
    parser.add_argument("--store", help="the record file (default under ~/.cache)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m fantasy_engine.testing",
                                     description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run the units whose inputs changed")
    _common(run)
    run.add_argument("--full", action="store_true",
                     help="run every unit and check the selection")
    run.add_argument("--dry-run", action="store_true",
                     help="report what would run, without running it")
    run.add_argument("--timeout", type=float,
                     help="seconds before a unit is stopped (default: none)")
    listing = commands.add_parser("list", help="list the units")
    _common(listing)
    explain = commands.add_parser("explain", help="show what changed for units")
    _common(explain)
    args = parser.parse_args(argv)

    repos, units = _select(args)
    if args.command == "list":
        for unit in units:
            print(unit.id)
        return 0

    store = Store(Path(args.store) if args.store else None)
    try:
        if args.command == "explain":
            runner = Runner(store, repos=repos)
            for unit in units:
                launch = unit.repo.launch(unit, runner.python)
                env = runner.environment(launch, runner.scratch / "t",
                                         runner.scratch / "r")
                decision = decide(unit, launch_key(launch.argv, launch.cwd, env,
                                                   runner.python), store)
                print("%s: %s" % (unit.id, "unchanged" if decision.skip else decision.reason))
                if decision.previous is not None and not decision.skip:
                    for change in store.changes(decision.previous.inputs, limit=None)[:20]:
                        print("    %s" % change)
            return 0
        with Lock():
            runner = Runner(store, repos=repos, timeout=args.timeout)
            summary = runner.run(units, full=args.full, dry_run=args.dry_run)
        return 1 if summary.failed or summary.missed else 0
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
