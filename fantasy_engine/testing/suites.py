"""The system's repositories, the test units in each, and how each unit runs.

A unit is what the selection runs or skips as a whole, in a process of its
own: a test file for MegaPad, Akashic and this repository, and a test batch
for LM1, whose emulator tests run through LM1's own harness.  Each
repository is launched through its usual entry point, so a unit runs the
same way whether or not the selection starts it.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ..workspace import FANTASY_ENGINE_ROOT, workspace_root

# Variables that a repository's launch sets for its own units: where its
# tests find another checkout, and the pinned tools they run.  The runner
# passes no caller's value for them, so whether a caller exported them
# cannot split the record.  A unit that does not read them never sees them,
# and one that does gets the same value from every caller in a workspace.
LAUNCH_VARIABLES = frozenset(("MEGAPAD_ROOT", "LM1_ROOT", "AKASHIC_E2FSPROGS_TOOL_DIR",
                              "AKASHIC_EXT4_BACKEND"))

# Units for what the first release leaves out (decision 35): Sound Lab,
# Observatory and Worlds, audio output and the sound synthesis libraries,
# and data graphics, the plots, waveforms and instruments of the rich
# terminal's series path, which only those applets use.  They stay in their
# repositories and run when asked for with ``--set outside``.
OUTSIDE_RELEASE: frozenset[str] = frozenset((
    # Sound Lab, Observatory and Worlds
    "akashic:local_testing/test_soundlab_fields.py",
    "akashic:local_testing/test_soundlab_prompt_restore.py",
    "akashic:local_testing/test_soundlab_waveform.py",
    "akashic:local_testing/test_observatory_worlds_slice.py",
    "akashic:local_testing/test_rich_terminal_soundlab_observatory_journeys.py",
    # the series path
    "akashic:local_testing/test_data_graphics_series.py",
    "akashic:local_testing/test_rich_field_series_reuse.py",
    "akashic:local_testing/test_rich_series_producer.py",
    "akashic:local_testing/test_rich_terminal_series_acceptance.py",
    "akashic:local_testing/test_rich_terminal_series_engine.py",
    "akashic:local_testing/test_rich_terminal_series_neutral.py",
    "akashic:local_testing/test_rich_terminal_uidl_series_planner.py",
    # data graphics: plots, waveforms and instruments
    "akashic:local_testing/test_applet_data_graphics_integrations.py",
    "akashic:local_testing/test_data_graphics_format.py",
    "akashic:local_testing/test_data_graphics_plot.py",
    "akashic:local_testing/test_data_graphics_waveform_cells.py",
    "akashic:local_testing/test_data_graphics_waveform_widget.py",
    "akashic:local_testing/test_data_graphics_widget.py",
    "akashic:local_testing/test_rich_candidate_instruments.py",
    "akashic:local_testing/test_rich_instrument_reuse.py",
    "akashic:local_testing/test_rich_terminal_apt1_instrument_provider_structure.py",
    "akashic:local_testing/test_rich_terminal_legacy_instrument_provider.py",
    "akashic:local_testing/test_rich_terminal_plot_line_planner.py",
    "akashic:local_testing/test_rich_terminal_plot_line_provider.py",
    "akashic:local_testing/test_rich_terminal_uidl_instrument_planner.py",
    "akashic:local_testing/test_semantic_data_graphics.py",
    "akashic:local_testing/test_uidl_data_graphics_snapshot.py",
    # sound synthesis
    "akashic:local_testing/test_audio_fx.py",
    "akashic:local_testing/test_audio_poly.py",
    "akashic:local_testing/test_audio_string.py",
    "akashic:local_testing/test_audio_synth.py",
    "akashic:local_testing/test_fft_reverb.py",
    # audio output
    "megapad:tests/simulator/test_audio.py",
    "megapad:tests/test_audio_output.py",
    "megapad:tests/test_audio_sinks.py",
))

# Units that wait for the release's final run instead of running with each
# change: MegaPad's system test, whose KDOS classes alone hold about 1,900
# tests and peak near 6.7 GiB.
FINAL_ONLY: frozenset[str] = frozenset((
    "megapad:tests/test_system.py",
    # Akashic's ext4 files run on the simulator with each change; on the
    # emulator, the device-faithful reference, they run whole at the end of
    # each step of the release plan and in its final run, about two hours
    # and 5.4 GiB at the peak.
    "akashic:local_testing/test_vfs_ext4.py@emulator",
    "akashic:local_testing/test_vfs_ext4_user_volume.py@emulator",
    "akashic:local_testing/test_vfs_ext4_retained_orphan.py@emulator",
    "akashic:local_testing/test_vfs_replace_ext4.py@emulator",
))


@dataclass(frozen=True)
class Unit:
    repo: "Repo"
    name: str

    @property
    def id(self) -> str:
        return "%s:%s" % (self.repo.name, self.name)

    @property
    def set(self) -> str:
        """"outside" for decision 35's units, "final" for those that wait for
        the final run, and "release" for the rest."""
        if self.id in OUTSIDE_RELEASE:
            return "outside"
        if self.id in FINAL_ONLY:
            return "final"
        return "release"


@dataclass
class Launch:
    argv: list[str]
    cwd: Path
    pythonpath: list[Path] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    # Files the launcher itself reads, outside any recorded Python process.
    launcher_inputs: list[Path] = field(default_factory=list)


class Repo:
    name = ""

    def __init__(self, root: Path):
        self.root = Path(root)

    def __repr__(self) -> str:
        return "%s(%s)" % (type(self).__name__, self.root)

    def __hash__(self) -> int:
        return hash((self.name, self.root))

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, Repo) and self.name == other.name
                and self.root == other.root)

    def present(self) -> bool:
        return self.root.is_dir()

    def prepare(self, env: dict[str, str]) -> None:
        """Build what the units need, once, before any of them is decided."""

    def units(self) -> list[Unit]:
        raise NotImplementedError

    def launch(self, unit: Unit, python: str) -> Launch:
        raise NotImplementedError

    def notes(self, environ) -> list[str]:
        """What a run should say about the caller's environment ENVIRON
        before this repository's units run, such as a variable its own
        launch sets in place of the caller's."""
        return []

    def tool_folders(self, env: dict[str, str]) -> list[Path]:
        """Folders of programs this repository vouches for, given a unit's
        environment.

        The recording sees that a unit starts a program and not what the
        program reads, so a unit that starts one cannot be resumed: nothing
        shows that what the interrupted attempt read is unchanged.  A
        repository lifts that for the programs in the folders it returns
        here by stating that each reads only its own file and the files its
        arguments name.  The recorder notes both when the program starts, so
        they are inputs of the unit like any file a Python process reads.

        The statement is the repository's to make and to keep true.  A
        program that finds files by itself, as git finds its repository and
        a TeX engine its packages, does not belong in such a folder.  A file
        that a tool reads because its environment or a command script names
        it has to be read by the tests as well, or it is no input.
        """
        return []

    def outcome(self, returncode: int) -> str:
        return "passed" if returncode == 0 else "failed"

    def tracked(self, *patterns: str) -> list[str]:
        listed = subprocess.run(
            ["git", "-C", str(self.root), "ls-files", "-z", "--", *patterns],
            check=True, capture_output=True,
        ).stdout.decode("utf-8", "surrogateescape")
        return sorted(name for name in listed.split("\0") if name)


class PytestRepo(Repo):
    """A repository whose test files run under plain pytest."""

    test_dir = "tests"
    recursive = False

    def units(self) -> list[Unit]:
        pattern = "%s/test_*.py" % self.test_dir
        names = self.tracked(pattern)
        if not self.recursive:
            names = [n for n in names if os.path.dirname(n) == self.test_dir]
        return [Unit(self, name) for name in names]

    def pythonpath(self) -> list[Path]:
        return []

    def launch(self, unit: Unit, python: str) -> Launch:
        # The cache plugin would read and rewrite .pytest_cache on every run.
        # fe_cases records each passing test, so an interrupted unit resumes.
        return Launch(
            argv=[python, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                  "-p", "fe_cases", unit.name],
            cwd=self.root,
            pythonpath=self.pythonpath(),
        )

    def outcome(self, returncode: int) -> str:
        if returncode == 0:
            return "passed"
        if returncode == 5:
            # pytest collected no test, as from a file that only holds a
            # standalone driver: the unit ran nothing (store.EMPTY).
            return "empty"
        return "failed"


class AkashicRepo(PytestRepo):
    name = "akashic"
    test_dir = "local_testing"

    # The ext4 tests run the pinned e2fsprogs build that this variable names,
    # on images and command files they wrote.  Its tools read their own
    # files, their arguments, and the mke2fs configuration their environment
    # names, which the tests hash against the profile's manifest and so read
    # themselves.  Declaring the folder by the variable the tests take it
    # from keeps the declaration on the folder they run from, and the
    # variable is part of the launch key, so another folder is another launch.
    TOOL_FOLDER_VARIABLES = ("AKASHIC_E2FSPROGS_TOOL_DIR",)

    # Where Akashic's local_testing/README.md builds that pinned e2fsprogs.
    # A unit runs it from here unless the caller names another build.
    PINNED_E2FSPROGS = (Path.home() / ".cache" / "fantasy-engine"
                        / "e2fsprogs-1.47.4" / "sbin")

    # The ext4 files that run on the simulator by default, and on the
    # emulator as units named with this suffix (see FINAL_ONLY).
    EXT4_FILES = ("local_testing/test_vfs_ext4.py",
                  "local_testing/test_vfs_ext4_user_volume.py",
                  "local_testing/test_vfs_ext4_retained_orphan.py",
                  "local_testing/test_vfs_replace_ext4.py")
    ON_EMULATOR = "@emulator"

    def __init__(self, root: Path, megapad_root: Path):
        super().__init__(root)
        self.megapad_root = Path(megapad_root)

    def pythonpath(self) -> list[Path]:
        # Some tests import MegaPad modules before the harness adds MegaPad.
        return [self.megapad_root]

    def units(self) -> list[Unit]:
        units = super().units()
        present = {unit.name for unit in units}
        return units + [Unit(self, name + self.ON_EMULATOR)
                        for name in self.EXT4_FILES if name in present]

    def launch(self, unit: Unit, python: str) -> Launch:
        # A unit named with ON_EMULATOR runs its file with the emulator
        # chosen; every other unit takes the harness's default machine.
        on_emulator = unit.name.endswith(self.ON_EMULATOR)
        if on_emulator:
            unit = Unit(self, unit.name[:-len(self.ON_EMULATOR)])
        # The tests find MegaPad through MEGAPAD_ROOT, and it is always the
        # workspace's: the MegaPad the run's report names.
        launch = super().launch(unit, python)
        launch.env["MEGAPAD_ROOT"] = str(self.megapad_root)
        if on_emulator:
            launch.env["AKASHIC_EXT4_BACKEND"] = "emulator"
        tools = os.environ.get("AKASHIC_E2FSPROGS_TOOL_DIR")
        if not tools and self.PINNED_E2FSPROGS.is_dir():
            tools = str(self.PINNED_E2FSPROGS)
        if tools:
            launch.env["AKASHIC_E2FSPROGS_TOOL_DIR"] = tools
        return launch

    def notes(self, environ) -> list[str]:
        named = environ.get("MEGAPAD_ROOT")
        if named and Path(named).resolve() != self.megapad_root.resolve():
            return ["MEGAPAD_ROOT names %s, but Akashic's tests use the "
                    "workspace's MegaPad, %s; --workspace chooses another"
                    % (named, self.megapad_root)]
        return []

    def tool_folders(self, env: dict[str, str]) -> list[Path]:
        return [Path(env[name]) for name in self.TOOL_FOLDER_VARIABLES
                if env.get(name)]


class FantasyEngineRepo(PytestRepo):
    name = "fantasy-engine"


class MegaPadRepo(Repo):
    """MegaPad's tests run only through its Makefile; its conftest stops a
    bare pytest run.

    Two steps of a Makefile test target write to disk on every invocation,
    which a run per file would multiply.  The accelerator step copies its
    3 MB library into place even when nothing changed, so the accelerator is
    built once before a run and each unit tells make to take it as built
    (``-o accel``).  pytest's cache plugin rewrites a file of every test ID it
    has seen, about 1 MB here, so each unit passes the Makefile's own pytest
    settings back with that plugin turned off, and with fe_cases, which
    records each passing test so that an interrupted unit resumes.

    MegaPad's tests of LM1 behind a chiplet port, the files named
    test_lm1*.py, attach the library LM1's chiplet module builds.  They find
    LM1 through LM1_ROOT, which names the workspace's LM1 for them alone, so
    no other unit's launch depends on where LM1 lies; and the library is
    built before any unit is decided, as for LM1's own units.
    """

    name = "megapad"
    LM1_TESTS = "test_lm1"

    def __init__(self, root: Path, lm1: "LM1Repo | None" = None):
        super().__init__(root)
        self._pytest_settings: str | None = None
        self.lm1 = lm1

    def make_variable(self, name: str) -> str:
        """The value the Makefile gives NAME, empty when it gives none."""
        return subprocess.run(
            ["make", "-s", "--no-print-directory", "--eval",
             "fe-print-%: ; @echo $($*)", "fe-print-" + name],
            cwd=self.root, check=True, capture_output=True, text=True,
        ).stdout.strip()

    def pytest_settings(self) -> str:
        """PYTEST_CONFIG_ARGS as the Makefile sets it, with the cache off and
        fe_cases on."""
        if self._pytest_settings is None:
            printed = self.make_variable("PYTEST_CONFIG_ARGS")
            self._pytest_settings = (
                "%s -p no:cacheprovider -p fe_cases" % printed).strip()
        return self._pytest_settings

    def prepare(self, env: dict[str, str]) -> None:
        subprocess.run(["make", "--no-print-directory", "accel"], cwd=self.root,
                       env=env, check=True, stdout=subprocess.DEVNULL)
        # The simulator's extension holds services the simulator needs
        # whichever executor runs Forth, and every repository's tests start
        # simulators.  Its library is a file target that make rebuilds only
        # when a source is newer, so a current build costs nothing here.
        library = self.make_variable("SIMULATOR_ACCEL_LIB")
        if library:
            subprocess.run(["make", "--no-print-directory", library], cwd=self.root,
                           env=env, check=True, stdout=subprocess.DEVNULL)
        if self.lm1 is not None:
            self.lm1.build_chiplet(env)

    def units(self) -> list[Unit]:
        names = self.tracked("tests/*test_*.py")
        return [Unit(self, n) for n in names
                if os.path.basename(n).startswith("test_")]

    def attaches_lm1(self, unit: Unit) -> bool:
        return os.path.basename(unit.name).startswith(self.LM1_TESTS)

    def launch(self, unit: Unit, python: str) -> Launch:
        launch = Launch(
            argv=["make", "--no-print-directory", "-o", "accel", "test-sequential",
                  "TEST_PATH=%s" % unit.name,
                  "PYTEST_CONFIG_ARGS=%s" % self.pytest_settings()],
            cwd=self.root,
            launcher_inputs=[self.root / "Makefile"],
        )
        if self.lm1 is not None and self.attaches_lm1(unit):
            launch.env["LM1_ROOT"] = str(self.lm1.root)
        return launch

    def notes(self, environ) -> list[str]:
        named = environ.get("LM1_ROOT")
        if self.lm1 is not None and named and \
                Path(named).resolve() != self.lm1.root.resolve():
            return ["LM1_ROOT names %s, but MegaPad's tests of LM1 use the "
                    "workspace's LM1, %s; --workspace chooses another"
                    % (named, self.lm1.root)]
        return []


_LM1_BATCH = re.compile(r"^\s*\[([^\]]+)\] \(\d+ tests?\)")


class LM1Repo(Repo):
    """LM1's emulator tests run in named batches through LM1's own runner.

    LM1's chiplet module builds against MegaPad's chiplet_module.h, which it
    finds, as LM1's link bench does, through MEGAPAD_ROOT: for LM1's units
    and its build, always the workspace's MegaPad.
    """

    name = "lm1"

    def __init__(self, root: Path, megapad_root: Path | None = None):
        super().__init__(root)
        self.megapad_root = Path(megapad_root) if megapad_root is not None else None

    @property
    def emu(self) -> Path:
        return self.root / "emu"

    @property
    def chiplet(self) -> Path:
        return self.root / "chiplet"

    def build_chiplet(self, env: dict[str, str]) -> None:
        # The chiplet module's library, which LM1's chiplet batches and
        # MegaPad's tests of LM1 load.  LM1's binding builds it itself
        # whenever its sources' digest differs from the library's, but a
        # unit that starts make cannot be skipped at the next run, so the
        # library is built before any unit is decided.  make rebuilds it
        # only when a source is newer, so a current build costs nothing.
        if (self.chiplet / "Makefile").is_file():
            env = dict(env)
            if self.megapad_root is not None:
                env["MEGAPAD_ROOT"] = str(self.megapad_root)
            subprocess.run(["make", "--no-print-directory", "-C", str(self.chiplet)],
                           env=env, check=True, stdout=subprocess.DEVNULL)

    def prepare(self, env: dict[str, str]) -> None:
        self.build_chiplet(env)

    def notes(self, environ) -> list[str]:
        named = environ.get("MEGAPAD_ROOT")
        if self.megapad_root is not None and named and \
                Path(named).resolve() != self.megapad_root.resolve():
            return ["MEGAPAD_ROOT names %s, but LM1's chiplet module builds against "
                    "the workspace's MegaPad, %s; --workspace chooses another"
                    % (named, self.megapad_root)]
        return []

    def units(self) -> list[Unit]:
        listed = subprocess.run(
            [sys.executable, "-m", "lm1.testing.runner", "--test-dir", "tests", "list"],
            cwd=self.emu, check=True, capture_output=True, text=True,
            env={**os.environ, "PYTHONHASHSEED": "0"},
        ).stdout
        batches = [m.group(1) for m in map(_LM1_BATCH.match, listed.splitlines()) if m]
        return [Unit(self, name) for name in batches]

    def launch(self, unit: Unit, python: str) -> Launch:
        launch = Launch(
            argv=[python, "-m", "lm1.testing.runner", "--test-dir", "tests",
                  "run", "--batch", unit.name],
            cwd=self.emu,
        )
        if self.megapad_root is not None:
            launch.env["MEGAPAD_ROOT"] = str(self.megapad_root)
        return launch


def repositories(root: Path | None = None) -> list[Repo]:
    """The system's repositories, in the order a full run goes through them."""

    root = Path(root) if root is not None else workspace_root()
    megapad = root / "megapad"
    lm1 = LM1Repo(root / "lm1", megapad if megapad.is_dir() else None)
    repos: list[Repo] = [
        MegaPadRepo(megapad, lm1 if lm1.present() else None),
        AkashicRepo(root / "akashic", megapad),
        lm1,
        FantasyEngineRepo(FANTASY_ENGINE_ROOT if root == FANTASY_ENGINE_ROOT.parent
                          else root / "fantasy-engine"),
    ]
    return [repo for repo in repos if repo.present()]


class Locations:
    """Where the workspace's repositories sit.

    The record names a path inside a repository by the repository and the
    path there, as ``@akashic/local_testing/test_pad.py``, and a launch key
    names a repository's folder the same way.  Another checkout of the same
    repositories, such as a worktree, then reads the same record and
    compares its own copy of each file, so a unit is skipped there exactly
    when its files hold what they held at its last pass.  A path outside
    every repository, such as Python's library or a pinned tool, keeps its
    place.  Both the folder a repository is given as and the folder that
    resolves to are its, since a process may name a file either way.

    A listing of a folder inside a repository counts only the names that
    the repository's git does not ignore.  A test that lists a folder, as a
    glob does, would otherwise depend on the ignored names a checkout
    gathers there, such as caches and scratch files, which another checkout
    of the same commit lacks.  An ignored file that a test reads is still an
    input by its own path, so a checkout without it runs the test; a test
    that only counts ignored names, without reading them, would go
    unnoticed, which a full run reveals.  The names the import system looks
    for in a folder, and those pytest checks in the folders it lists on its
    way to a test file, count whether or not git ignores them, since either
    changes the run wherever it lies (see the recorder).
    """

    def __init__(self, repos: list[Repo]):
        roots: dict[str, str] = {}
        for repo in repos:
            for form in (os.path.abspath(repo.root), os.path.realpath(repo.root)):
                roots.setdefault(form.rstrip(os.sep) or os.sep, repo.name)
        # The longest folder first, so a repository inside another wins.
        self._roots = sorted(roots.items(), key=lambda item: -len(item[0]))
        self._folders = {repo.name: os.path.abspath(repo.root) for repo in repos}
        self._ignored: dict[str, list[str]] = {}

    def ignored(self, folder: str) -> frozenset[str]:
        """The names in FOLDER that its repository's git ignores and does
        not track; none for a folder outside every repository or inside an
        ignored one, whose listing counts in full."""
        name = self.name(folder)
        if not name.startswith("@"):
            return frozenset()
        repo, _, inner = name[1:].partition("/")
        if repo not in self._folders:
            return frozenset()
        if repo not in self._ignored:
            try:
                listed = subprocess.run(
                    ["git", "-C", self._folders[repo], "ls-files", "-z", "--others",
                     "--ignored", "--exclude-standard", "--directory"],
                    check=True, capture_output=True,
                ).stdout.decode("utf-8", "surrogateescape")
                self._ignored[repo] = [p.rstrip("/") for p in listed.split("\0") if p]
            except (OSError, subprocess.CalledProcessError):
                self._ignored[repo] = []
        prefix = inner + "/" if inner else ""
        return frozenset(path[len(prefix):] for path in self._ignored[repo]
                         if path.startswith(prefix) and "/" not in path[len(prefix):])

    def name(self, path: str) -> str:
        """PATH as the record names it."""
        for root, repo in self._roots:
            if path == root:
                return "@" + repo
            if path.startswith(root + os.sep):
                return "@%s/%s" % (repo, path[len(root) + 1:])
        return path

    def names(self, value: str) -> str:
        """VALUE, which may hold several paths as a search path does, with
        each as the record names it."""
        return os.pathsep.join(self.name(part) for part in value.split(os.pathsep))

    def path(self, name: str) -> str:
        """Where the record's NAME is in this workspace.  A name in a
        repository the workspace lacks stays as it is and names no file."""
        if not name.startswith("@"):
            return name
        repo, _, rest = name[1:].partition("/")
        folder = self._folders.get(repo)
        if folder is None:
            return name
        return os.path.join(folder, rest) if rest else folder
