"""Run test units one at a time, skipping those whose inputs haven't changed.

For each unit the runner compares the inputs its latest passing run read
with their current contents.  A unit runs again when there is no passing
run, when its launch settings differ, when its last run started a program
whose reads went unrecorded, or when any input has changed; otherwise it is
reported as unchanged since that run.  A full run executes every unit and
checks the selection: a unit the selection would have skipped that now gives
a different result reveals an input the recording missed.

Units run sequentially, each in a process of its own, with throwaway files
in /dev/shm, which is RAM, and a pinned PYTHONHASHSEED.
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
from .store import Result, Store
from .suites import Repo, Unit

RECORDER_DIR = Path(__file__).resolve().parent / "recorder"
RAM = Path("/dev/shm")

# Variables a unit receives from the caller's environment.  Everything else
# is left out, so a run's environment is exactly what its key describes.
_PASSED = ("PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LANGUAGE",
           "TERM", "TZ", "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY",
           "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE", "DBUS_SESSION_BUS_ADDRESS")
_PASSED_PREFIXES = ("LC_", "MP64_", "MEGAPAD_", "MEGAFORTH_", "AKASHIC_", "LM1_")
# Variables that locate the display or programs rather than shape a result.
# PATH stays out because the programs it finds are keyed by their own paths.
_UNKEYED = frozenset(("PATH", "TERM", "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY",
                      "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE",
                      "DBUS_SESSION_BUS_ADDRESS", "TMPDIR",
                      "FE_TESTSEL_RECORD_DIR"))
_KEYED_PROGRAMS = ("python3", "python", "make")


def _base_environment() -> dict[str, str]:
    env = {name: os.environ[name] for name in _PASSED if name in os.environ}
    for name, value in os.environ.items():
        if name.startswith(_PASSED_PREFIXES):
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


def launch_key(argv: list[str], cwd: Path, env: dict[str, str], python: str) -> str:
    keyed_env = {k: v for k, v in env.items() if k not in _UNKEYED}
    programs = {name: _program_identity(shutil.which(name, path=env.get("PATH")))
                for name in _KEYED_PROGRAMS}
    programs["interpreter"] = _program_identity(python)
    programs["interpreter-version"] = sys.version
    text = json.dumps({"argv": argv, "cwd": str(cwd), "env": keyed_env,
                       "programs": programs}, sort_keys=True)
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


def decide(unit: Unit, key: str, store: Store) -> Decision:
    previous = store.latest_pass(unit.id)
    if previous is None:
        return Decision(False, "no passing run on record")
    if previous.launch_key != key:
        return Decision(False, "its launch settings changed", previous)
    unrecordable = previous.inputs.get("unrecordable") or []
    if unrecordable:
        return Decision(False, "it starts %s" % unrecordable[0], previous)
    changed = store.changes(previous.inputs, limit=1)
    if changed:
        return Decision(False, "changed: %s" % changed[0], previous)
    return Decision(True, "unchanged", previous)


@dataclass
class Summary:
    ran: int = 0
    passed: int = 0
    failed: list[str] = field(default_factory=list)
    skipped: int = 0
    skipped_seconds: float = 0.0
    ran_seconds: float = 0.0
    missed: list[str] = field(default_factory=list)
    unsettled: list[str] = field(default_factory=list)


class Runner:
    def __init__(self, store: Store, *, repos: list[Repo], out: TextIO = sys.stdout,
                 python: str = sys.executable, scratch: Path | None = None,
                 timeout: float | None = None):
        self.store = store
        self.repos = repos
        self.out = out
        self.python = python
        # Short names: pytest's temporary folders, and any Unix sockets in
        # them, sit below TMPDIR, and socket paths are limited to 108 bytes.
        self.scratch = Path(scratch) if scratch is not None else RAM / ("fet-%d" % os.getpid())
        self.timeout = timeout
        self.heads: dict[str, str] = {}

    def say(self, text: str) -> None:
        print(text, file=self.out, flush=True)

    def describe_previous(self, result: Result) -> str:
        info = self.store.run_info(result.run_id) or {}
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(result.finished))
        heads = ", ".join("%s %s" % item for item in sorted(info.get("heads", {}).items()))
        return "%s (%s; %s)" % (result.run_id, when, heads)

    def run(self, units: list[Unit], *, full: bool = False, dry_run: bool = False) -> Summary:
        summary = Summary()
        now = time.time()
        run_id = "%s.%03d-%04x" % (time.strftime("%Y%m%d-%H%M%S", time.localtime(now)),
                                   int(now * 1000) % 1000, os.getpid() & 0xFFFF)
        self.heads = repository_heads(self.repos)
        mode = "full" if full else "select"
        if not dry_run:
            self.store.begin_run(run_id, mode, self.heads)
            self.prune_logs(keep=5)
        self.say("%s run %s over %d units; %s" % (
            "Dry" if dry_run else mode.capitalize(), run_id, len(units),
            ", ".join("%s %s" % item for item in sorted(self.heads.items()))))
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

    def one(self, unit: Unit, run_id: str, *, full: bool, dry_run: bool,
            summary: Summary) -> None:
        launch = unit.repo.launch(unit, self.python)
        tmp, record = self.scratch / "t", self.scratch / "r"
        env = self.environment(launch, tmp, record)
        key = launch_key(launch.argv, launch.cwd, env, self.python)
        decision = decide(unit, key, self.store)
        if decision.skip and not full:
            summary.skipped += 1
            summary.skipped_seconds += decision.previous.duration
            self.say("SKIP  %s  unchanged since %s" % (
                unit.id, self.describe_previous(decision.previous)))
            return
        if dry_run:
            summary.ran += 1
            self.say("RUN?  %s  %s" % (unit.id, decision.reason))
            return

        for folder in (tmp, record):
            shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir(parents=True)
        logs = self.logs_root / run_id
        logs.mkdir(parents=True, exist_ok=True)
        log_path = logs / (unit.id.replace("/", "_").replace(":", "__") + ".log")
        started_ns = time.time_ns()
        returncode, peak_kib = self.execute(launch, env, log_path)
        duration = (time.time_ns() - started_ns) / 1e9

        seen = records.load(record)
        excluded = (tmp, record, self.store.path.parent, logs)
        inputs = seen.inputs(excluded)
        inputs.files = sorted(set(inputs.files) | {str(p) for p in launch.launcher_inputs})
        unrecordable = sorted(seen.unrecordable)
        if seen.errors:
            unrecordable.append("a recorder error (%s)" % seen.errors[0])
        if not seen.processes:
            unrecordable.append("no recorded Python process")
        described = self.store.describe(inputs, unrecordable)
        moved = self.changed_during(inputs, started_ns)

        outcome = unit.repo.outcome(returncode)
        note = "" if not moved else "inputs changed while it ran: %s" % moved[0]
        if moved and outcome in ("passed", "empty"):
            outcome = "unsettled"
            summary.unsettled.append(unit.id)
        self.store.record(Result(unit.id, run_id, outcome, duration, time.time(),
                                 key, described, note))
        summary.ran += 1
        summary.ran_seconds += duration
        detail = "%s in %.1f s, peak %d MiB" % (outcome, duration, peak_kib // 1024)
        if outcome in ("passed", "empty"):
            summary.passed += 1
            log_path.unlink(missing_ok=True)
        elif outcome == "failed":
            summary.failed.append(unit.id)
            detail = "FAILED (exit %d) in %.1f s; log %s" % (returncode, duration, log_path)
            if full and decision.skip:
                summary.missed.append(unit.id)
                detail += "; MISSED INPUT: the selection would have skipped it"
        else:
            detail += "; %s" % note
        self.say("RUN   %s  %s -> %s" % (unit.id, decision.reason, detail))

    def execute(self, launch, env: dict[str, str], log_path: Path) -> tuple[int, int]:
        with open(log_path, "wb") as log:
            process = subprocess.Popen(
                launch.argv, cwd=launch.cwd, env=env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            )
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
        if dry_run:
            self.say("Would run %d units and skip %d (about %.0f s of recorded work)." % (
                summary.ran, summary.skipped, summary.skipped_seconds))
            return
        self.say("Ran %d units in %.0f s: %d passed, %d failed%s. Skipped %d unchanged "
                 "units (about %.0f s of recorded work)." % (
                     summary.ran, summary.ran_seconds, summary.passed,
                     len(summary.failed),
                     ", %d unsettled" % len(summary.unsettled) if summary.unsettled else "",
                     summary.skipped, summary.skipped_seconds))
        for unit in summary.failed:
            self.say("  failed: %s" % unit)
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
