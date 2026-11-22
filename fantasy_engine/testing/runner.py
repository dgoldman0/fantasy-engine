"""Run test units one at a time, skipping those whose inputs haven't changed.

For each unit the runner compares the inputs that each of its passing runs
on record read with their current contents (the record keeps a pass for
each workspace that ran the unit; see ``store``).  A unit is skipped when
one of those passes matches: the same launch settings (its command, its
folder, and the environment it receives, which takes from the caller only
the variables that shape a result, while those that locate another
checkout or a pinned tool are set by the unit's repository), no program
started whose reads went unrecorded, and no input changed.  It is then
reported as unchanged since that pass's run.  Otherwise it runs, and the
report gives the reason that the most fitting pass failed to match: the
pass from the run's own workspace when there is one, else the newest.  A
full run executes every unit and checks the selection: a unit the
selection would have skipped that now gives a different result reveals an
input the recording missed.

A unit can run and test nothing: pytest collects no test from a file that
holds only a standalone driver, and the unit ends as empty.  The skip takes
that result as it takes a pass, since pytest would again find nothing while
nothing it read has changed, but every report keeps it apart from a pass.
The summary counts the units that ran nothing beside those that passed, a
skipped unit's line says when the run it relies on ran nothing, a dry run
marks each unit to run whose last run ran nothing, and a full run counts a
unit that now passes where it ran nothing, or now runs nothing where it
passed, as a missed input.

A unit can also pass no test because every test skipped, or because its
module skipped itself while pytest collected it, as when an image, library
or program it needs is missing; the unit ends as all-skipped.  What made
its tests skip is seldom anything its record holds, so the skip never takes
that result as a pass, and the unit runs again at each run until its tests
run.  Every report names it apart from the passes, and a full run counts a
unit whose tests now all skip, where the selection would have skipped it,
as a missed input.

Units run sequentially, each in a process of its own, with throwaway files
in /dev/shm, which is RAM, and a pinned PYTHONHASHSEED.

A unit whose run was interrupted, as when the session running it ends,
resumes after the tests it passed.  The recorder's records and the list of
passed tests (``recorder/fe_cases.py``) live in the unit's partial folder
in RAM until a result is recorded.  The next run deselects those tests when
its launch settings are the same and nothing the interrupted attempt read
has changed since it started; otherwise the unit starts over.

An attempt that started a program other than Python resumes only when every
such program lies in a folder its repository declares (``Repo.tool_folders``):
the repository states that those programs read only their own file and the
files their arguments name.  Both are recorded when a program starts, so a
changed tool or a changed file handed to it starts the unit over.  The same
statement lets such a unit be skipped, like a unit that starts no program,
while nothing it or its programs read has changed.  A program from anywhere
else keeps the unit from resuming and from being skipped.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from . import records
from .recorder.fe_cases import PASSED_ENV, RESUME_ENV, SKIPPED_ENV
from .store import ALL_SKIPPED, EMPTY, PASSING, Result, Store, workspace_identity
from .suites import LAUNCH_VARIABLES, Locations, Repo, Unit

RECORDER_DIR = Path(__file__).resolve().parent / "recorder"
RAM = Path("/dev/shm")

# Variables a unit receives from the caller's environment.  Everything else
# is left out, so a run's environment is exactly what its key describes.
# LAUNCH_VARIABLES are left out too: a repository's launch sets them.
_PASSED = ("PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LANGUAGE",
           "TERM", "TZ", "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY",
           "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE", "DBUS_SESSION_BUS_ADDRESS")
_PASSED_PREFIXES = ("LC_", "MP64_", "MEGAPAD_", "MEGAFORTH_", "AKASHIC_", "LM1_")
# Variables that locate the display or programs rather than shape a result.
# PATH stays out because the programs it finds are keyed by their own paths.
_UNKEYED = frozenset(("PATH", "TERM", "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY",
                      "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE",
                      "DBUS_SESSION_BUS_ADDRESS", "TMPDIR",
                      "FE_TESTSEL_RECORD_DIR", PASSED_ENV, RESUME_ENV,
                      SKIPPED_ENV))
_KEYED_PROGRAMS = ("python3", "python", "make")


def _listed(path: Path) -> bool:
    try:
        return bool(path.read_text(encoding="utf-8").split())
    except OSError:
        return False


def passed_no_test(passed: Path, skipped: Path) -> bool:
    """Whether a pytest unit that ended cleanly passed no test because its
    tests, or its module, skipped: fe_cases lists each passed test in
    PASSED and each skip in SKIPPED.  The passes of an interrupted attempt
    stay on PASSED, so a resumed unit counts them."""
    return not _listed(passed) and _listed(skipped)


def _base_environment() -> dict[str, str]:
    env = {name: os.environ[name] for name in _PASSED if name in os.environ}
    for name, value in os.environ.items():
        if name.startswith(_PASSED_PREFIXES) and name not in LAUNCH_VARIABLES:
            env[name] = value
    return env


_versions: dict[str, str] = {}


def _program_identity(program: str | None) -> str:
    if program is None:
        return "absent"
    real = os.path.realpath(program)
    if real not in _versions:
        try:
            info = os.stat(real)
            _versions[real] = "%s:%d:%d" % (real, info.st_size, info.st_mtime_ns)
        except OSError:
            _versions[real] = real
    return _versions[real]


def launch_key(argv: list[str], cwd: Path, env: dict[str, str], python: str,
               locations: Locations | None = None) -> str:
    """The digest of what a unit's launch decides.  With LOCATIONS, a path
    inside a repository counts by its repository, so every checkout of the
    same repositories launches a unit the same way."""
    named = locations.names if locations is not None else (lambda value: value)
    keyed_env = {k: named(v) for k, v in env.items() if k not in _UNKEYED}
    programs = {name: _program_identity(shutil.which(name, path=env.get("PATH")))
                for name in _KEYED_PROGRAMS}
    programs["interpreter"] = _program_identity(python)
    programs["interpreter-version"] = sys.version
    folder = named(os.path.abspath(cwd)) if locations is not None else str(cwd)
    text = json.dumps({"argv": [named(arg) for arg in argv], "cwd": folder,
                       "env": keyed_env, "programs": programs}, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()


def repository_heads(repos: list[Repo]) -> dict[str, str]:
    heads = {}
    for repo in repos:
        try:
            head = subprocess.run(["git", "-C", str(repo.root), "rev-parse", "--short=8", "HEAD"],
                                  check=True, capture_output=True, text=True).stdout.strip()
            dirty = subprocess.run(["git", "-C", str(repo.root), "status", "--porcelain",
                                    "--untracked-files=no"],
                                   check=True, capture_output=True, text=True).stdout.strip()
            heads[repo.name] = head + ("+changes" if dirty else "")
        except (OSError, subprocess.CalledProcessError):
            heads[repo.name] = "unknown"
    return heads


@dataclass
class Decision:
    """Whether a unit can be skipped, and why it runs if not."""

    skip: bool
    reason: str
    previous: Result | None = None


def decide(unit: Unit, key: str, store: Store,
           locations: Locations | None = None,
           workspace: str | None = None) -> Decision:
    """Skip UNIT when a pass on record matches its launch KEY and current
    inputs.  The pass WORKSPACE recorded comes first, then the newest; when
    none matches, the first of them gives the reason the unit runs."""
    passes = store.passes(unit.id)
    if not passes:
        return Decision(False, "no passing run on record")
    passes.sort(key=lambda result: workspace is None or result.workspace != workspace)
    first: Decision | None = None
    for previous in passes:
        unrecordable = previous.inputs.get("unrecordable") or []
        if previous.launch_key != key:
            decision = Decision(False, "its launch settings changed", previous)
        elif unrecordable:
            decision = Decision(False, "it starts %s" % unrecordable[0], previous)
        else:
            changed = store.changes(previous.inputs, limit=1, locations=locations)
            if not changed:
                return Decision(True, "unchanged", previous)
            decision = Decision(False, "changed: %s" % changed[0], previous)
        first = first or decision
    return first


@dataclass
class Summary:
    ran: int = 0
    passed: int = 0
    empty: list[str] = field(default_factory=list)  # ran, and ran nothing
    all_skipped: list[str] = field(default_factory=list)  # ran, and every test skipped
    failed: list[str] = field(default_factory=list)
    skipped: int = 0
    skipped_empty: int = 0  # skipped on a run in which they ran nothing
    last_empty: int = 0     # a dry run's units to run whose last run ran nothing
    last_all_skipped: int = 0  # those whose tests all skipped at their last run
    skipped_seconds: float = 0.0
    ran_seconds: float = 0.0
    missed: list[str] = field(default_factory=list)
    unsettled: list[str] = field(default_factory=list)


class Runner:
    def __init__(self, store: Store, *, repos: list[Repo], out: TextIO = sys.stdout,
                 python: str = sys.executable, scratch: Path | None = None,
                 timeout: float | None = None, partial_root: Path | None = None):
        self.store = store
        self.repos = repos
        self.locations = Locations(repos)
        # The repositories' folders, which keep their own passes in the record.
        self.workspace = workspace_identity({repo.name: str(repo.root) for repo in repos})
        self.out = out
        self.python = python
        # Short names: pytest's temporary folders, and any Unix sockets in
        # them, sit below TMPDIR, and socket paths are limited to 108 bytes.
        self.scratch = Path(scratch) if scratch is not None else RAM / ("fet-%d" % os.getpid())
        self.timeout = timeout
        # Interrupted units' partial attempts outlive the run, one folder per
        # record, so that two records never resume each other's units.
        if partial_root is None:
            tag = hashlib.sha256(str(store.path).encode()).hexdigest()[:12]
            partial_root = RAM / "fe-test-partial" / tag
        self.partial_root = Path(partial_root)
        self.heads: dict[str, str] = {}

    def say(self, text: str) -> None:
        print(text, file=self.out, flush=True)

    def describe_previous(self, result: Result) -> str:
        info = self.store.run_info(result.run_id) or {}
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(result.finished))
        heads = ", ".join("%s %s" % item for item in sorted(info.get("heads", {}).items()))
        return "%s (%s; %s)" % (result.run_id, when, heads)

    def unchanged(self, previous: Result) -> str:
        """Why a unit is skipped: the run it relies on, and whether the
        unit ran nothing there."""
        text = "unchanged since %s" % self.describe_previous(previous)
        if previous.ran_nothing:
            text += ", in which it ran nothing"
        return text

    def last_ran_nothing(self, unit: Unit) -> bool:
        last = self.store.latest(unit.id)
        return last is not None and last.ran_nothing

    def last_all_skipped(self, unit: Unit) -> bool:
        last = self.store.latest(unit.id)
        return last is not None and last.all_skipped

    def run(self, units: list[Unit], *, full: bool = False, dry_run: bool = False) -> Summary:
        summary = Summary()
        now = time.time()
        run_id = "%s.%03d-%04x" % (time.strftime("%Y%m%d-%H%M%S", time.localtime(now)),
                                   int(now * 1000) % 1000, os.getpid() & 0xFFFF)
        self.heads = repository_heads(self.repos)
        mode = "full" if full else "select"
        if not dry_run:
            self.store.begin_run(run_id, mode, self.heads, self.workspace)
            self.prune_logs(keep=5)
        self.say("%s run %s over %d units; %s" % (
            "Dry" if dry_run else mode.capitalize(), run_id, len(units),
            ", ".join("%s %s" % item for item in sorted(self.heads.items()))))
        for repo in dict.fromkeys(unit.repo for unit in units):
            for note in repo.notes(os.environ):
                self.say("note: %s" % note)
        try:
            if not dry_run:
                # A build can change what units read, so it comes before any
                # decision; a dry run builds nothing.
                for repo in dict.fromkeys(unit.repo for unit in units):
                    repo.prepare(_base_environment())
            for unit in units:
                self.one(unit, run_id, full=full, dry_run=dry_run, summary=summary)
        finally:
            if not dry_run:
                self.store.finish_run(run_id)
            shutil.rmtree(self.scratch, ignore_errors=True)
            logs = self.logs_root / run_id
            if logs.is_dir() and not any(logs.iterdir()):
                logs.rmdir()
        self.report(summary, dry_run=dry_run)
        return summary

    @property
    def logs_root(self) -> Path:
        return self.scratch.parent / "fe-test-logs"

    def prune_logs(self, keep: int) -> None:
        """Failed units' logs stay in RAM for the last few runs only."""
        if not self.logs_root.is_dir():
            return
        runs = sorted(p for p in self.logs_root.iterdir() if p.is_dir())
        for old in runs[:-keep] if len(runs) > keep else []:
            shutil.rmtree(old, ignore_errors=True)

    def environment(self, launch, tmp: Path, record: Path) -> dict[str, str]:
        env = _base_environment()
        env.update(launch.env)
        env["PYTHONHASHSEED"] = "0"
        env["PYTHONPATH"] = os.pathsep.join(
            [str(RECORDER_DIR)] + [str(path) for path in launch.pythonpath])
        env["TMPDIR"] = str(tmp)
        env["FE_TESTSEL_RECORD_DIR"] = str(record)
        return env

    def partial(self, unit: Unit) -> Path:
        return self.partial_root / hashlib.sha256(unit.id.encode()).hexdigest()[:16]

    def resumable(self, partial: Path, unit: Unit, key: str,
                  tool_folders: list[Path] | tuple[Path, ...] = (),
                  cwd: Path | None = None) -> int:
        """How many tests an interrupted attempt of UNIT passed, when it can
        resume: same launch key, same checkout, every read recorded, and
        nothing it read changed after it stopped.  0 when there is nothing
        to resume.  The attempt's reads name its own checkout's files, so an
        attempt in another checkout, which launches with the same key, is
        no evidence about this one's: CWD, the unit's folder, tells them
        apart.

        A program the attempt started counts as read in full when it lies
        in one of TOOL_FOLDERS, the folders the unit's repository declares;
        its file is then checked like any other input, as the files its
        arguments named already are.  A program from elsewhere leaves reads
        unrecorded.

        The attempt's own writes, such as a new __pycache__ folder, came
        before it stopped, and a change while it ran makes its result
        unsettled when the unit finishes.  A read of a path that does not
        exist counts as unchanged while the folder that would hold it does.
        """
        try:
            meta = json.loads((partial / "meta.json").read_text())
            passed = set((partial / "passed").read_text().split())
        except (OSError, ValueError):
            return 0
        if meta.get("unit") != unit.id or meta.get("key") != key or not passed:
            return 0
        if cwd is not None and meta.get("cwd") != os.path.abspath(cwd):
            return 0
        seen = records.load(partial / "records")
        tools, unrecorded = seen.started_tools(tool_folders)
        if unrecorded or seen.errors:
            return 0
        written = [partial / "passed", *(partial / "records").glob("*.jsonl")]
        stopped_ns = max(os.stat(path).st_mtime_ns for path in written)
        excluded = (partial, Path(meta["tmp"]), self.store.path.parent)
        inputs = seen.inputs(excluded)
        for name in (inputs.files + inputs.listings + inputs.import_listings
                     + inputs.metadata_listings + tools):
            path = Path(name)
            while not path.exists() and path != path.parent:
                path = path.parent
            try:
                if os.stat(path).st_ctime_ns > stopped_ns:
                    return 0
            except OSError:
                return 0
        return len(passed)

    @staticmethod
    def stop_orphan(partial: Path) -> None:
        """End a unit an interrupted run left running, so that it never runs
        twice at once.  Units run in sessions of their own, which outlive
        the run that started them."""
        try:
            pid = int((partial / "pid").read_text())
            environ = Path("/proc/%d/environ" % pid).read_bytes()
        except (OSError, ValueError):
            return
        if ("%s=%s" % (PASSED_ENV, partial / "passed")).encode() not in environ:
            return  # the number now belongs to another program
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        while Path("/proc/%d" % pid).exists():
            time.sleep(0.05)

    def one(self, unit: Unit, run_id: str, *, full: bool, dry_run: bool,
            summary: Summary) -> None:
        launch = unit.repo.launch(unit, self.python)
        tmp = self.scratch / "t"
        partial = self.partial(unit)
        record, passed = partial / "records", partial / "passed"
        skipped = partial / "skipped"
        env = self.environment(launch, tmp, record)
        env[PASSED_ENV] = str(passed)
        env[SKIPPED_ENV] = str(skipped)
        key = launch_key(launch.argv, launch.cwd, env, self.python, self.locations)
        if not dry_run:
            self.stop_orphan(partial)
        tool_folders = unit.repo.tool_folders(env)
        decision = decide(unit, key, self.store, self.locations, self.workspace)
        if decision.skip and not full:
            if not dry_run:
                shutil.rmtree(partial, ignore_errors=True)
            summary.skipped += 1
            summary.skipped_seconds += decision.previous.duration
            if decision.previous.ran_nothing:
                summary.skipped_empty += 1
            self.say("SKIP  %s  %s" % (unit.id, self.unchanged(decision.previous)))
            return
        resumed = 0 if full else self.resumable(partial, unit, key, tool_folders,
                                                launch.cwd)
        note = "; resumes after %d passed tests" % resumed if resumed else ""
        if dry_run:
            summary.ran += 1
            last = self.store.latest(unit.id)
            if last is not None and last.ran_nothing:
                summary.last_empty += 1
                note += "; it ran nothing at its last run"
            elif last is not None and last.all_skipped:
                summary.last_all_skipped += 1
                note += "; all its tests skipped at its last run"
            self.say("RUN?  %s  %s%s" % (unit.id, decision.reason, note))
            return

        if resumed:
            started_ns = json.loads((partial / "meta.json").read_text())["started_ns"]
            env[RESUME_ENV] = str(passed)
        else:
            shutil.rmtree(partial, ignore_errors=True)
            record.mkdir(parents=True)
            started_ns = time.time_ns()
            (partial / "meta.json").write_text(json.dumps({
                "unit": unit.id, "key": key, "started_ns": started_ns,
                "tmp": str(tmp), "cwd": os.path.abspath(launch.cwd)}))
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        logs = self.logs_root / run_id
        logs.mkdir(parents=True, exist_ok=True)
        log_path = logs / (unit.id.replace("/", "_").replace(":", "__") + ".log")
        attempt_ns = time.time_ns()
        returncode, peak_kib = self.execute(launch, env, log_path,
                                            pid_path=partial / "pid")
        duration = (time.time_ns() - attempt_ns) / 1e9

        seen = records.load(record)
        excluded = (tmp, partial, self.store.path.parent, logs)
        inputs = seen.inputs(excluded)
        # The declared tools the unit started are inputs by their files, as
        # the files their arguments named already are, so they leave nothing
        # unrecorded.  A program from anywhere else does.
        tools, unrecordable = seen.started_tools(tool_folders)
        inputs.files = sorted(set(inputs.files) | set(tools)
                              | {str(p) for p in launch.launcher_inputs})
        if seen.errors:
            unrecordable.append("a recorder error (%s)" % seen.errors[0])
        if not seen.processes:
            unrecordable.append("no recorded Python process")
        described = self.store.describe(inputs, unrecordable, self.locations)
        moved = self.changed_during(inputs, started_ns)

        outcome = unit.repo.outcome(returncode)
        if resumed and outcome == EMPTY:
            outcome = "passed"  # its interrupted attempt passed every test
        if outcome in PASSING and passed_no_test(passed, skipped):
            outcome = ALL_SKIPPED
        note = "" if not moved else "inputs changed while it ran: %s" % moved[0]
        if moved and outcome in PASSING:
            outcome = "unsettled"
            summary.unsettled.append(unit.id)
        self.store.record(Result(unit.id, run_id, outcome, duration, time.time(),
                                 key, described, note))
        shutil.rmtree(partial, ignore_errors=True)
        summary.ran += 1
        summary.ran_seconds += duration
        detail = "%s in %.1f s, peak %d MiB" % (outcome, duration, peak_kib // 1024)
        if resumed:
            detail += ", resumed after %d passed tests" % resumed
        if outcome in PASSING:
            if outcome == EMPTY:
                summary.empty.append(unit.id)
                detail += "; it ran nothing"
            else:
                summary.passed += 1
            log_path.unlink(missing_ok=True)
            # A passing result its record did not predict is as much a
            # missed input as a failure: tests that appeared, or vanished,
            # while nothing the unit read changed.
            if full and decision.skip and outcome != decision.previous.outcome:
                summary.missed.append(unit.id)
                detail += ("; MISSED INPUT: the selection would have skipped it "
                           "as %s" % self.unchanged(decision.previous))
        elif outcome == ALL_SKIPPED:
            summary.all_skipped.append(unit.id)
            detail += "; all its tests skipped"
            log_path.unlink(missing_ok=True)
            # Its record predicted a pass: what made the tests skip is
            # something the recording missed.
            if full and decision.skip:
                summary.missed.append(unit.id)
                detail += ("; MISSED INPUT: the selection would have skipped it "
                           "as %s" % self.unchanged(decision.previous))
        elif outcome == "failed":
            summary.failed.append(unit.id)
            detail = "FAILED (exit %d) in %.1f s; log %s" % (returncode, duration, log_path)
            if resumed:
                detail += "; resumed after %d passed tests" % resumed
            if full and decision.skip:
                summary.missed.append(unit.id)
                detail += "; MISSED INPUT: the selection would have skipped it"
        else:
            detail += "; %s" % note
        self.say("RUN   %s  %s -> %s" % (unit.id, decision.reason, detail))

    def execute(self, launch, env: dict[str, str], log_path: Path,
                pid_path: Path | None = None) -> tuple[int, int]:
        with open(log_path, "wb") as log:
            process = subprocess.Popen(
                launch.argv, cwd=launch.cwd, env=env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            )
            if pid_path is not None:
                pid_path.write_text(str(process.pid))
            deadline = None if self.timeout is None else time.monotonic() + self.timeout
            try:
                while True:
                    pid, status, usage = os.wait4(process.pid, os.WNOHANG)
                    if pid:
                        break
                    if deadline is not None and time.monotonic() > deadline:
                        os.killpg(process.pid, signal.SIGKILL)
                    time.sleep(0.05)
            except KeyboardInterrupt:
                os.killpg(process.pid, signal.SIGKILL)
                os.wait4(process.pid, 0)
                process.returncode = -signal.SIGKILL
                raise
            process.returncode = os.waitstatus_to_exitcode(status)
            # Anything the unit left running in its session goes with it.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        return process.returncode, usage.ru_maxrss

    @staticmethod
    def changed_during(inputs: records.Inputs, started_ns: int) -> list[str]:
        moved = []
        for path in inputs.files:
            try:
                if os.stat(path).st_ctime_ns > started_ns:
                    moved.append(path)
            except OSError:
                continue
        return moved

    def report(self, summary: Summary, *, dry_run: bool) -> None:
        work = " (about %.0f s of recorded work)" % summary.skipped_seconds
        if summary.skipped_empty:
            work += (", %d of which ran nothing in the run they rely on"
                     % summary.skipped_empty)
        if dry_run:
            would_run = "%d units" % summary.ran
            marks = []
            if summary.last_empty:
                marks.append("%d of which ran nothing at their last run"
                             % summary.last_empty)
            if summary.last_all_skipped:
                marks.append("%d of which skipped all their tests at their last run"
                             % summary.last_all_skipped)
            if marks:
                would_run += ", %s," % ", ".join(marks)
            self.say("Would run %s and skip %d%s." % (would_run, summary.skipped, work))
            return
        counts = ["%d passed" % summary.passed]
        if summary.empty:
            counts.append("%d ran nothing" % len(summary.empty))
        if summary.all_skipped:
            counts.append("%d skipped all their tests" % len(summary.all_skipped))
        counts.append("%d failed" % len(summary.failed))
        if summary.unsettled:
            counts.append("%d unsettled" % len(summary.unsettled))
        self.say("Ran %d units in %.0f s: %s. Skipped %d unchanged units%s." % (
            summary.ran, summary.ran_seconds, ", ".join(counts), summary.skipped, work))
        for unit in summary.failed:
            self.say("  failed: %s" % unit)
        for unit in summary.all_skipped:
            self.say("  skipped all its tests: %s" % unit)
        for unit in summary.missed:
            self.say("  MISSED INPUT: %s gave a result its key did not predict" % unit)


class Lock:
    """Only one selection run at a time, however many sessions are open."""

    def __init__(self, path: Path = RAM / "fe-test.lock"):
        self.path = path
        self.handle = None

    def __enter__(self) -> "Lock":
        self.handle = open(self.path, "w")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.handle.close()
            raise SystemExit("Another test-selection run holds %s; wait for it." % self.path)
        return self

    def __exit__(self, *exc) -> None:
        fcntl.flock(self.handle, fcntl.LOCK_UN)
        self.handle.close()
