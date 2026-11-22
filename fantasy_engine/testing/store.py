"""The record of test runs, and digests of the inputs they read.

One SQLite file holds every run's metadata, the passes of each unit that
the record keeps together with the inputs each of those runs read, the
unit's latest result when that was no pass, and a cache of file digests
keyed by each file's identity (device, inode, size, modification and change
times), so a file is hashed again only after it changes.  A unit's inputs
name a file inside a repository by the repository (``suites.Locations``), so
the record serves every checkout of the same repositories.

Several checkouts share the record, and each holds its own state of the
repositories: a branch's worktree may build MegaPad's native libraries from
other sources than main's.  A unit's passes are therefore kept per
workspace, the set of repository folders a run used, and a unit is skipped
when its current inputs match any pass on record.  Which passes stay is
decided whenever a unit passes (``Store.record``):

- A workspace keeps only its newest pass of each unit.  An older pass from
  the same workspace describes a state that workspace has left, and would
  serve again only if its files returned to exactly that state.
- A pass from a workspace whose folders no longer exist, or from a run that
  named no workspace, as runs did before workspaces were recorded, is kept
  until the unit passes again anywhere.  Until then it still serves any
  checkout that holds the same files, as main does after a branch merges
  without further change; once the unit has passed again, the checkout that
  now holds those files has recorded its own pass.
- A result that is no pass is kept only while it is the unit's latest
  result, so it keeps its meaning for reports, and it never stands for a
  pass.

A unit thus holds at most one pass for each workspace that existed when the
unit last passed.  An age limit would instead drop passes that a live
workspace still relies on, such as main's for units that go weeks without
changing, or keep a retired workspace's passes for the whole period.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

from .records import (Inputs, entry_stem, import_candidates, is_metadata_entry,
                      sorted_listing)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started REAL NOT NULL,
    finished REAL,
    mode TEXT NOT NULL,
    heads TEXT NOT NULL,
    workspace TEXT
);
CREATE TABLE IF NOT EXISTS results (
    unit TEXT NOT NULL,
    run_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    duration REAL NOT NULL,
    finished REAL NOT NULL,
    launch_key TEXT NOT NULL,
    inputs BLOB NOT NULL,
    note TEXT NOT NULL,
    PRIMARY KEY (unit, run_id)
);
CREATE INDEX IF NOT EXISTS results_by_unit ON results (unit, finished);
CREATE TABLE IF NOT EXISTS digests (
    path TEXT PRIMARY KEY,
    signature TEXT NOT NULL,
    digest TEXT NOT NULL
);
"""

# A unit that ran no test, such as a pytest file that only holds a standalone
# driver, ends as EMPTY.  Its result counts as passing for the skip, since
# while nothing it read has changed it would again find nothing to run, but
# no report counts it as a pass: each says that it ran nothing.
EMPTY = "empty"
PASSING = ("passed", EMPTY)

# A unit that passed no test because every test skipped, or because its
# module skipped itself while pytest collected it, ends as ALL_SKIPPED.  It
# tested nothing, and what made its tests skip, such as a missing image,
# library or program, is seldom anything its record holds, so its result
# never counts as passing: the unit runs again at each run until its tests
# run, and every report keeps it apart from the passes.
ALL_SKIPPED = "all-skipped"


def default_path() -> Path:
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache"
    )
    return Path(cache) / "fantasy-engine" / "testing" / "records.sqlite3"


@dataclass
class Result:
    unit: str
    run_id: str
    outcome: str
    duration: float
    finished: float
    launch_key: str
    inputs: dict
    note: str
    # The workspace of the run that recorded it (``workspace_identity``),
    # as the record reads it back; None for a run that named none.
    workspace: str | None = None

    @property
    def ran_nothing(self) -> bool:
        return self.outcome == EMPTY

    @property
    def all_skipped(self) -> bool:
        return self.outcome == ALL_SKIPPED

    @property
    def passing(self) -> bool:
        return self.outcome in PASSING


def workspace_identity(roots: dict[str, str]) -> str:
    """The workspace that ROOTS, each repository's folder by its name, make
    up: every folder as it resolves, so a workspace whose folders link to
    main's checkouts is main's workspace."""
    return json.dumps({name: os.path.realpath(root) for name, root in roots.items()},
                      sort_keys=True)


def workspace_exists(workspace: str | None) -> bool:
    """Whether every folder of WORKSPACE is still there; False for a run
    that named no workspace."""
    if not workspace:
        return False
    try:
        folders = json.loads(workspace)
    except ValueError:
        return False
    return bool(folders) and all(os.path.isdir(folder) for folder in folders.values())


@dataclass
class Change:
    kind: str
    path: str
    before: str
    now: str

    def __str__(self) -> str:
        what = {"file": "", "listing": "listing of ", "imports": "imports in ",
                "metadata": "package metadata in "}
        return "%s%s (%s -> %s)" % (what[self.kind], self.path,
                                     _short(self.before), _short(self.now))


def _short(digest: str) -> str:
    return digest[:12] if len(digest) > 12 else digest


def _kept(digest: str) -> str:
    """The part of a digest a unit's record keeps: 64 bits are plenty to
    notice a change, and a quarter of the size keeps full runs' writes small.
    Markers such as "absent" are kept whole."""
    return digest[:16] if len(digest) == 64 else digest


class Store:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(_SCHEMA)
        self._add_workspace_column()
        self._digests: dict[str, tuple[str, str]] = {}
        self._new_digests: dict[str, tuple[str, str]] = {}

    def _add_workspace_column(self) -> None:
        """A record made before runs named their workspace gains the column;
        its runs keep none, so their passes count as a retired workspace's."""
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(runs)")}
        if "workspace" in columns:
            return
        try:
            with self.db:
                self.db.execute("ALTER TABLE runs ADD COLUMN workspace TEXT")
        except sqlite3.OperationalError:
            # Another process opening the record added it first.
            columns = {row[1] for row in self.db.execute("PRAGMA table_info(runs)")}
            if "workspace" not in columns:
                raise

    def close(self) -> None:
        self.flush_digests()
        self.db.close()

    # -- digests -----------------------------------------------------------

    def _cached(self, path: str) -> tuple[str, str] | None:
        found = self._digests.get(path)
        if found is None:
            row = self.db.execute(
                "SELECT signature, digest FROM digests WHERE path = ?", (path,)
            ).fetchone()
            if row is not None:
                found = (row[0], row[1])
                self._digests[path] = found
        return found

    def digest_file(self, path: str) -> str:
        try:
            info = os.stat(path)
        except (FileNotFoundError, NotADirectoryError):
            return "absent"
        except OSError as exc:
            return "unreadable:%s" % exc.errno
        if stat.S_ISDIR(info.st_mode):
            return "directory"
        if not stat.S_ISREG(info.st_mode):
            return "special"
        signature = "%d:%d:%d:%d:%d" % (info.st_dev, info.st_ino, info.st_size,
                                        info.st_mtime_ns, info.st_ctime_ns)
        cached = self._cached(path)
        if cached is not None and cached[0] == signature:
            return cached[1]
        try:
            with open(path, "rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
        except OSError as exc:
            return "unreadable:%s" % exc.errno
        self._digests[path] = (signature, digest)
        self._new_digests[path] = (signature, digest)
        return digest

    @staticmethod
    def digest_listing(path: str, ignored: frozenset[str] = frozenset()) -> str:
        """The digest of folder PATH's names, less those IGNORED."""
        names = sorted_listing(path)
        if names is None:
            return "absent"
        kept = [name for name in names if name not in ignored]
        return hashlib.sha256("\n".join(kept).encode("utf-8", "surrogateescape")).hexdigest()

    @staticmethod
    def digest_imports(path: str, candidates: frozenset[str]) -> str:
        names = sorted_listing(path)
        if names is None:
            return "absent"
        relevant = [name for name in names if entry_stem(name) in candidates]
        return hashlib.sha256("\n".join(relevant).encode("utf-8", "surrogateescape")).hexdigest()

    @staticmethod
    def digest_metadata(path: str) -> str:
        names = sorted_listing(path)
        if names is None:
            return "absent"
        relevant = [name for name in names if is_metadata_entry(path, name)]
        return hashlib.sha256("\n".join(relevant).encode("utf-8", "surrogateescape")).hexdigest()

    def flush_digests(self) -> None:
        if self._new_digests:
            with self.db:
                self.db.executemany(
                    "INSERT OR REPLACE INTO digests (path, signature, digest) VALUES (?, ?, ?)",
                    [(p, s, d) for p, (s, d) in self._new_digests.items()],
                )
            self._new_digests.clear()

    def describe(self, inputs: Inputs, unrecordable: list[str],
                 locations=None) -> dict:
        """Digest every input, in the form a later run compares against,
        each named as LOCATIONS names it."""

        name = locations.name if locations is not None else (lambda path: path)
        ignored = locations.ignored if locations is not None else (lambda path: frozenset())
        candidates = import_candidates(inputs.import_names)
        return {
            "files": {name(path): _kept(self.digest_file(path))
                      for path in inputs.files},
            "listings": {name(path): _kept(self.digest_listing(path, ignored(path)))
                         for path in inputs.listings},
            "imports": {
                name(path): _kept(self.digest_imports(path, candidates))
                for path in inputs.import_listings
            },
            "metadata": {
                name(path): _kept(self.digest_metadata(path))
                for path in inputs.metadata_listings
            },
            "import_names": inputs.import_names,
            "state": [name(path) for path in inputs.state],
            "unrecordable": sorted(unrecordable),
        }

    def changes(self, described: dict, limit: int | None = 1,
                locations=None) -> list[Change]:
        """The inputs whose digests differ from DESCRIBED, up to LIMIT, each
        at the place LOCATIONS finds it in this workspace."""

        where = locations.path if locations is not None else (lambda name: name)
        ignored = locations.ignored if locations is not None else (lambda path: frozenset())
        found: list[Change] = []

        def note(kind: str, path: str, before: str, now: str) -> bool:
            before, now = _kept(before), _kept(now)
            if before != now:
                found.append(Change(kind, path, before, now))
            return limit is not None and len(found) >= limit

        for name, before in described["files"].items():
            path = where(name)
            if note("file", path, before, self.digest_file(path)):
                return found
        for name, before in described["listings"].items():
            path = where(name)
            if note("listing", path, before, self.digest_listing(path, ignored(path))):
                return found
        candidates = import_candidates(described["import_names"])
        for name, before in described["imports"].items():
            path = where(name)
            if note("imports", path, before, self.digest_imports(path, candidates)):
                return found
        for name, before in described["metadata"].items():
            path = where(name)
            if note("metadata", path, before, self.digest_metadata(path)):
                return found
        return found

    # -- runs and results --------------------------------------------------

    def begin_run(self, run_id: str, mode: str, heads: dict,
                  workspace: str | None = None) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO runs (run_id, started, mode, heads, workspace) "
                "VALUES (?, ?, ?, ?, ?)",
                (run_id, time.time(), mode, json.dumps(heads, sort_keys=True), workspace),
            )

    def finish_run(self, run_id: str) -> None:
        with self.db:
            self.db.execute("UPDATE runs SET finished = ? WHERE run_id = ?",
                            (time.time(), run_id))

    def run_info(self, run_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT started, finished, mode, heads, workspace FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return {"started": row[0], "finished": row[1], "mode": row[2],
                "heads": json.loads(row[3]), "workspace": row[4]}

    def record(self, result: Result) -> None:
        """Keep RESULT, and drop what it supersedes (see the module's notes):
        after a pass, the unit's older passes from the same workspace, its
        older passes from workspaces that no longer exist or were never
        named, and any older result that is no pass; after any other
        result, the older results that are no pass."""

        blob = zlib.compress(json.dumps(result.inputs, sort_keys=True).encode(), 6)
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO results (unit, run_id, outcome, duration, "
                "finished, launch_key, inputs, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (result.unit, result.run_id, result.outcome, result.duration,
                 result.finished, result.launch_key, blob, result.note),
            )
            rows = self.db.execute(
                "SELECT results.run_id, results.outcome, results.finished, runs.workspace "
                "FROM results LEFT JOIN runs ON runs.run_id = results.run_id "
                "WHERE results.unit = ? AND results.run_id != ?",
                (result.unit, result.run_id),
            ).fetchall()
            workspace = None
            if result.passing:
                info = self.run_info(result.run_id)
                workspace = info["workspace"] if info is not None else None
            dropped = []
            for run_id, outcome, finished, kept_workspace in rows:
                if finished > result.finished:
                    continue  # newer than RESULT, so nothing RESULT supersedes
                if outcome not in PASSING:
                    dropped.append(run_id)
                elif not result.passing:
                    continue
                elif workspace is not None and kept_workspace == workspace:
                    dropped.append(run_id)
                elif not workspace_exists(kept_workspace):
                    dropped.append(run_id)
            if dropped:
                marks = ",".join("?" * len(dropped))
                self.db.execute(
                    "DELETE FROM results WHERE unit = ? AND run_id IN (%s)" % marks,
                    (result.unit, *dropped),
                )
        self.flush_digests()

    _COLUMNS = ("results.unit, results.run_id, results.outcome, results.duration, "
                "results.finished, results.launch_key, results.inputs, results.note, "
                "runs.workspace")

    def _results(self, unit: str, passing: bool, limit: int | None = None) -> list[Result]:
        query = ("SELECT %s FROM results LEFT JOIN runs ON runs.run_id = results.run_id "
                 "WHERE results.unit = ?" % self._COLUMNS)
        params: tuple = (unit,)
        if passing:
            query += " AND results.outcome IN (%s)" % ",".join("?" * len(PASSING))
            params += PASSING
        query += " ORDER BY results.finished DESC"
        if limit is not None:
            query += " LIMIT %d" % limit
        return [Result(row[0], row[1], row[2], row[3], row[4], row[5],
                       json.loads(zlib.decompress(row[6])), row[7], row[8])
                for row in self.db.execute(query, params)]

    def passes(self, unit: str) -> list[Result]:
        """Every pass of UNIT the record keeps, the newest first."""
        return self._results(unit, passing=True)

    def latest_pass(self, unit: str) -> Result | None:
        found = self._results(unit, passing=True, limit=1)
        return found[0] if found else None

    def latest(self, unit: str) -> Result | None:
        found = self._results(unit, passing=False, limit=1)
        return found[0] if found else None

    def latest_outcomes(self) -> dict[str, str]:
        """Each recorded unit's latest outcome, read without its inputs."""
        rows = self.db.execute(
            "SELECT unit, outcome FROM results ORDER BY finished").fetchall()
        return {unit: outcome for unit, outcome in rows}
