"""Merge the record files of one run into the inputs that decide its result.

Each Python process of a run writes its own record (see
``recorder/sitecustomize.py``).  A path counts as an input when some process
read it and no process wrote, renamed or removed it: what the run writes
itself is output, and a file it reads and then rewrites is its own state.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

# Pseudo-filesystems and devices hold nothing a later run could compare.
# /dev/shm is ordinary storage in RAM, so files there can be inputs.
_PSEUDO_ROOTS = ("/proc/", "/sys/", "/dev/")
_RAM_ROOT = "/dev/shm/"


@dataclass
class Observation:
    """What the processes of one run read, wrote and started."""

    processes: list[dict] = field(default_factory=list)
    reads: set[str] = field(default_factory=set)
    writes: set[str] = field(default_factory=set)
    listings: set[str] = field(default_factory=set)
    import_listings: set[str] = field(default_factory=set)
    metadata_listings: set[str] = field(default_factory=set)
    import_names: set[str] = field(default_factory=set)
    unrecordable: set[str] = field(default_factory=set)
    # For each unrecordable entry that is a started program, the files it
    # ran; None stands for a start whose file could not be found.
    started: dict[str, set[str | None]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    unfinished: int = 0

    def started_tools(self, folders) -> tuple[list[str], list[str]]:
        """Split what the run did outside the recording by FOLDERS.

        Returns the files of the started programs that lie inside one of
        FOLDERS, and the unrecordable entries that such programs do not
        account for: a program from elsewhere, one whose file could not be
        found, or anything else the recording could not follow.
        """

        roots = [os.path.realpath(folder) + os.sep for folder in folders]
        tools: set[str] = set()
        others: list[str] = []
        for entry in sorted(self.unrecordable):
            files = self.started.get(entry)
            inside = files is not None and all(
                name is not None and name.startswith(tuple(roots))
                for name in files
            ) and bool(roots)
            if inside:
                tools.update(files)  # type: ignore[arg-type]
            else:
                others.append(entry)
        return sorted(tools), others

    def inputs(self, excluded: tuple[Path, ...]) -> "Inputs":
        """The run's inputs, leaving out its outputs and EXCLUDED trees."""

        roots = tuple(str(path).rstrip("/") + "/" for path in excluded)

        def kept(path: str) -> bool:
            if path.startswith(_PSEUDO_ROOTS) and not path.startswith(_RAM_ROOT):
                return False
            return not (path + "/").startswith(roots)

        state = self.reads & self.writes
        return Inputs(
            files=sorted(p for p in self.reads - self.writes if kept(p)),
            listings=sorted(p for p in self.listings - self.writes if kept(p)),
            import_listings=sorted(
                p for p in self.import_listings - self.writes if kept(p)
            ),
            metadata_listings=sorted(
                p for p in self.metadata_listings - self.writes if kept(p)
            ),
            import_names=sorted(self.import_names),
            state=sorted(p for p in state if kept(p)),
        )


@dataclass
class Inputs:
    """Paths whose contents or listings decide a run's result."""

    files: list[str]
    listings: list[str]
    import_listings: list[str]
    metadata_listings: list[str]
    import_names: list[str]
    state: list[str]


def load(record_dir: Path) -> Observation:
    """Merge every record file in RECORD_DIR."""

    seen = Observation()
    for record in sorted(record_dir.glob("*.jsonl")):
        finished = False
        with record.open("r", encoding="utf-8", errors="surrogateescape") as lines:
            for raw in lines:
                if not raw.endswith("\n"):
                    break  # a process stopped in the middle of a line
                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    seen.errors.append("an unreadable line in %s" % record.name)
                    continue
                kind = item["t"]
                if kind == "proc":
                    seen.processes.append(item)
                elif kind == "end":
                    finished = True
                elif kind == "r":
                    seen.reads.add(item["p"])
                elif kind == "w":
                    seen.writes.add(item["p"])
                elif kind == "d":
                    seen.listings.add(item["p"])
                elif kind == "i":
                    seen.import_listings.add(item["p"])
                elif kind == "e":
                    seen.metadata_listings.add(item["p"])
                elif kind == "m":
                    seen.import_names.add(item["p"])
                elif kind == "x":
                    entry = "%s (%s)" % (item["p"], item.get("why", "unrecorded"))
                    seen.unrecordable.add(entry)
                    if item.get("why") == "not Python":
                        seen.started.setdefault(entry, set()).add(item.get("file"))
                elif kind == "err":
                    seen.errors.append(item["p"])
        if not finished:
            seen.unfinished += 1
    return seen


def import_candidates(names: list[str]) -> frozenset[str]:
    """The entry stems that could satisfy any of these imports in a folder."""

    return frozenset(name.rpartition(".")[2] for name in names)


def entry_stem(entry: str) -> str:
    return entry.split(".", 1)[0]


def is_metadata_entry(folder: str, entry: str) -> bool:
    """Whether importlib.metadata reads ENTRY when it scans FOLDER."""

    low = entry.lower()
    if low.endswith((".dist-info", ".egg-info")):
        return True
    return low == "egg-info" and folder.lower().endswith(".egg")


def sorted_listing(path: str) -> list[str] | None:
    try:
        return sorted(os.listdir(path))
    except (FileNotFoundError, NotADirectoryError):
        return None
