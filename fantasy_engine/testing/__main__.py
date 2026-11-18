"""Command line for test selection.

    python -m fantasy_engine.testing run [PATTERN ...]   run what changed
    python -m fantasy_engine.testing run --full          run everything
    python -m fantasy_engine.testing run --dry-run       show what would run
    python -m fantasy_engine.testing list [PATTERN ...]  list the units
    python -m fantasy_engine.testing explain UNIT        what changed since its pass

A PATTERN matches unit names such as ``akashic:local_testing/test_pad.py``
or ``lm1:phase1_io``, with shell wildcards; without a wildcard it matches any
unit whose name contains it.  ``--set`` picks the units that run with each
change (``release``, the default), those plus the units that wait for the
release's final run (``final``), the units for what the release leaves out
(``outside``), or every unit (``all``).  ``--recorded`` selects every unit
the record already holds, which the selection can judge without running
them, and patterns given with it add the units they name beside those, so
one command runs what changed among the recorded units and a test the
record has not seen yet.  ``--repo`` limits either to its repositories.

A unit can run and test nothing, as a test file that holds only a standalone
driver does under pytest.  Every command says so: ``run`` counts those units
apart from the passes and says when the run a skipped unit relies on ran
nothing, and a dry run, ``list`` and ``explain`` mark each unit whose last
run ran nothing.

A unit can also pass no test because every test skipped, or because its
module skipped itself, as when an image, library or program it needs is
missing.  It tested nothing, and its record seldom holds what made the tests
skip, so it never counts as a pass and runs again at each run.  ``run``
counts and names those units apart, and a dry run, ``list`` and ``explain``
mark each unit whose tests all skipped at its last run.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path

from .runner import Lock, Runner, decide, launch_key
from .store import ALL_SKIPPED, EMPTY, Store
from .suites import FINAL_ONLY, OUTSIDE_RELEASE, Unit, repositories

_SETS = {
    "release": ("release",),
    "final": ("release", "final"),
    "outside": ("outside",),
    "all": ("release", "final", "outside"),
}


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


def _select(args, store: Store | None = None) -> tuple[list, list[Unit]]:
    repos = repositories(Path(args.workspace) if args.workspace else None)
    every = [unit for repo in repos for unit in repo.units()]
    present = {repo.name for repo in repos}
    known = {unit.id for unit in every}
    stale = sorted(name for name in OUTSIDE_RELEASE | FINAL_ONLY
                   if name.split(":", 1)[0] in present and name not in known)
    for name in stale:
        print("note: the sets name %s, which no longer exists" % name, file=sys.stderr)
    if args.repo:
        unknown = set(args.repo) - present
        if unknown:
            raise SystemExit("No repository named %s" % ", ".join(sorted(unknown)))
        every = [unit for unit in every if unit.repo.name in args.repo]
    wanted = _SETS[args.set]
    units = [unit for unit in every if unit.set in wanted]
    if getattr(args, "recorded", False) and store is not None:
        # The recorded units, and beside them any the patterns name, so a
        # new test runs in the same command as the units it sits among.
        units = [unit for unit in units
                 if store.latest(unit.id) is not None
                 or (args.patterns and _matches(unit, args.patterns))]
    else:
        units = [unit for unit in units if _matches(unit, args.patterns)]
    return repos, units


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("patterns", nargs="*", metavar="PATTERN")
    parser.add_argument("--repo", action="append",
                        help="limit to a repository (repeatable)")
    parser.add_argument("--set", choices=tuple(_SETS), default="release")
    parser.add_argument("--recorded", action="store_true",
                        help="every unit the record holds, and beside them "
                             "any the patterns name")
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

    store = Store(Path(args.store) if args.store else None)
    try:
        repos, units = _select(args, store)
        if args.command == "list":
            outcomes = store.latest_outcomes()
            marks = {EMPTY: "  (ran nothing at its last run)",
                     ALL_SKIPPED: "  (all its tests skipped at its last run)"}
            for unit in units:
                print(unit.id + marks.get(outcomes.get(unit.id), ""))
            return 0
        if args.command == "explain":
            runner = Runner(store, repos=repos)
            for unit in units:
                launch = unit.repo.launch(unit, runner.python)
                env = runner.environment(launch, runner.scratch / "t",
                                         runner.scratch / "r")
                key = launch_key(launch.argv, launch.cwd, env, runner.python,
                                 runner.locations)
                decision = decide(unit, key, store, runner.locations)
                if decision.skip:
                    why = runner.unchanged(decision.previous)
                else:
                    why = decision.reason
                    if runner.last_ran_nothing(unit):
                        why += "; it ran nothing at its last run"
                    elif runner.last_all_skipped(unit):
                        why += "; all its tests skipped at its last run"
                print("%s: %s" % (unit.id, why))
                if decision.previous is not None and not decision.skip:
                    for change in store.changes(decision.previous.inputs, limit=None,
                                                locations=runner.locations)[:20]:
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
