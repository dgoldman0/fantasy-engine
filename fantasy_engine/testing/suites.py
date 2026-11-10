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

FANTASY_ENGINE_ROOT = Path(__file__).resolve().parents[2]

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
            return "empty"  # nothing to collect, as in a standalone driver
        return "failed"


class AkashicRepo(PytestRepo):
    name = "akashic"
    test_dir = "local_testing"

    def __init__(self, root: Path, megapad_root: Path):
        super().__init__(root)
        self.megapad_root = Path(megapad_root)

    def pythonpath(self) -> list[Path]:
        # Some tests import MegaPad modules before the harness adds MegaPad.
        return [self.megapad_root]


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
    """

    name = "megapad"

    def __init__(self, root: Path):
        super().__init__(root)
        self._pytest_settings: str | None = None

    def pytest_settings(self) -> str:
        """PYTEST_CONFIG_ARGS as the Makefile sets it, with the cache off and
        fe_cases on."""
        if self._pytest_settings is None:
            printed = subprocess.run(
                ["make", "-s", "--no-print-directory", "--eval",
                 "fe-print-%: ; @echo $($*)", "fe-print-PYTEST_CONFIG_ARGS"],
                cwd=self.root, check=True, capture_output=True, text=True,
            ).stdout.strip()
            self._pytest_settings = (
                "%s -p no:cacheprovider -p fe_cases" % printed).strip()
        return self._pytest_settings

    def prepare(self, env: dict[str, str]) -> None:
        subprocess.run(["make", "--no-print-directory", "accel"], cwd=self.root,
                       env=env, check=True, stdout=subprocess.DEVNULL)

    def units(self) -> list[Unit]:
        names = self.tracked("tests/*test_*.py")
        return [Unit(self, n) for n in names
                if os.path.basename(n).startswith("test_")]

    def launch(self, unit: Unit, python: str) -> Launch:
        return Launch(
            argv=["make", "--no-print-directory", "-o", "accel", "test-sequential",
                  "TEST_PATH=%s" % unit.name,
                  "PYTEST_CONFIG_ARGS=%s" % self.pytest_settings()],
            cwd=self.root,
            launcher_inputs=[self.root / "Makefile"],
        )


_LM1_BATCH = re.compile(r"^\s*\[([^\]]+)\] \(\d+ tests?\)")


class LM1Repo(Repo):
    """LM1's emulator tests run in named batches through LM1's own runner."""

    name = "lm1"

    @property
    def emu(self) -> Path:
        return self.root / "emu"

    def units(self) -> list[Unit]:
        listed = subprocess.run(
            [sys.executable, "-m", "lm1.testing.runner", "--test-dir", "tests", "list"],
            cwd=self.emu, check=True, capture_output=True, text=True,
            env={**os.environ, "PYTHONHASHSEED": "0"},
        ).stdout
        batches = [m.group(1) for m in map(_LM1_BATCH.match, listed.splitlines()) if m]
        return [Unit(self, name) for name in batches]

    def launch(self, unit: Unit, python: str) -> Launch:
        return Launch(
            argv=[python, "-m", "lm1.testing.runner", "--test-dir", "tests",
                  "run", "--batch", unit.name],
            cwd=self.emu,
        )


def workspace_root() -> Path:
    configured = os.environ.get("FE_WORKSPACE")
    return Path(configured).resolve() if configured else FANTASY_ENGINE_ROOT.parent


def repositories(root: Path | None = None) -> list[Repo]:
    """The system's repositories, in the order a full run goes through them."""

    root = Path(root) if root is not None else workspace_root()
    megapad = root / "megapad"
    repos: list[Repo] = [
        MegaPadRepo(megapad),
        AkashicRepo(root / "akashic", megapad),
        LM1Repo(root / "lm1"),
        FantasyEngineRepo(FANTASY_ENGINE_ROOT if root == FANTASY_ENGINE_ROOT.parent
                          else root / "fantasy-engine"),
    ]
    return [repo for repo in repos if repo.present()]
