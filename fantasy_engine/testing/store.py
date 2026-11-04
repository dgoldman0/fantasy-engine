"""The record of test runs, and digests of the inputs they read.

One SQLite file holds every run's metadata, the latest result of each unit
together with the inputs that run read, and a cache of file digests keyed by
each file's identity (device, inode, size, modification and change times),
so a file is hashed again only after it changes.
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
    heads TEXT NOT NULL
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

PASSING = ("passed", "empty")


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

    @property
    def passed(self) -> bool:
        return self.outcome in PASSING


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
        self._digests: dict[str, tuple[str, str]] = {}
        self._new_digests: dict[str, tuple[str, str]] = {}

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
    def digest_listing(path: str) -> str:
        names = sorted_listing(path)
        if names is None:
            return "absent"
        return hashlib.sha256("\n".join(names).encode("utf-8", "surrogateescape")).hexdigest()

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

    def describe(self, inputs: Inputs, unrecordable: list[str]) -> dict:
        """Digest every input, in the form a later run compares against."""

        candidates = import_candidates(inputs.import_names)
        return {
            "files": {path: _kept(self.digest_file(path)) for path in inputs.files},
            "listings": {path: _kept(self.digest_listing(path))
                         for path in inputs.listings},
            "imports": {
                path: _kept(self.digest_imports(path, candidates))
                for path in inputs.import_listings
            },
            "metadata": {
                path: _kept(self.digest_metadata(path))
                for path in inputs.metadata_listings
            },
            "import_names": inputs.import_names,
            "state": inputs.state,
            "unrecordable": sorted(unrecordable),
        }

    def changes(self, described: dict, limit: int | None = 1) -> list[Change]:
        """The inputs whose digests differ from DESCRIBED, up to LIMIT."""

        found: list[Change] = []

        def note(kind: str, path: str, before: str, now: str) -> bool:
            before, now = _kept(before), _kept(now)
            if before != now:
                found.append(Change(kind, path, before, now))
            return limit is not None and len(found) >= limit

        for path, before in described["files"].items():
            if note("file", path, before, self.digest_file(path)):
                return found
        for path, before in described["listings"].items():
            if note("listing", path, before, self.digest_listing(path)):
                return found
        candidates = import_candidates(described["import_names"])
        for path, before in described["imports"].items():
            if note("imports", path, before, self.digest_imports(path, candidates)):
                return found
        for path, before in described["metadata"].items():
            if note("metadata", path, before, self.digest_metadata(path)):
                return found
        return found

    # -- runs and results --------------------------------------------------

    def begin_run(self, run_id: str, mode: str, heads: dict) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO runs (run_id, started, mode, heads) VALUES (?, ?, ?, ?)",
                (run_id, time.time(), mode, json.dumps(heads, sort_keys=True)),
            )

    def finish_run(self, run_id: str) -> None:
        with self.db:
            self.db.execute("UPDATE runs SET finished = ? WHERE run_id = ?",
                            (time.time(), run_id))

    def run_info(self, run_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT started, finished, mode, heads FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return {"started": row[0], "finished": row[1], "mode": row[2],
                "heads": json.loads(row[3])}

    def record(self, result: Result) -> None:
        """Keep RESULT, the unit's latest pass and nothing older."""

        blob = zlib.compress(json.dumps(result.inputs, sort_keys=True).encode(), 6)
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO results (unit, run_id, outcome, duration, "
                "finished, launch_key, inputs, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (result.unit, result.run_id, result.outcome, result.duration,
                 result.finished, result.launch_key, blob, result.note),
            )
            keep = {result.run_id}
            latest_pass = self._latest(result.unit, passing=True)
            if latest_pass is not None:
                keep.add(latest_pass.run_id)
            marks = ",".join("?" * len(keep))
            self.db.execute(
                "DELETE FROM results WHERE unit = ? AND run_id NOT IN (%s)" % marks,
                (result.unit, *sorted(keep)),
            )
        self.flush_digests()

    def _latest(self, unit: str, passing: bool) -> Result | None:
        query = (
            "SELECT unit, run_id, outcome, duration, finished, launch_key, inputs, note "
            "FROM results WHERE unit = ?"
        )
        if passing:
            query += " AND outcome IN (%s)" % ",".join("?" * len(PASSING))
        query += " ORDER BY finished DESC LIMIT 1"
        params = (unit, *PASSING) if passing else (unit,)
        row = self.db.execute(query, params).fetchone()
        if row is None:
            return None
        inputs = json.loads(zlib.decompress(row[6]))
        return Result(row[0], row[1], row[2], row[3], row[4], row[5], inputs, row[7])

    def latest_pass(self, unit: str) -> Result | None:
        return self._latest(unit, passing=True)

    def latest(self, unit: str) -> Result | None:
        return self._latest(unit, passing=False)
