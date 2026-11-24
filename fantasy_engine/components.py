"""The components Fantasy Engine is built from (PLAN.md Part 1b).

``components.toml`` at this repository's root names each component, the
repository it comes from and the commit the release uses.  ``assemble``
writes a component's tree at exactly that commit into the cache: through
``git archive`` from the workspace's checkout when that checkout holds the
commit, and otherwise from a shallow fetch of that one commit.  A checkout's
uncommitted changes and its current branch therefore never reach a build.

``build_native`` then builds the native parts in the assembled trees with
each component's own build: MegaPad's ``make build``, for the Python that
runs this command, and LM1's chiplet Makefile, against the assembled
MegaPad.  Every part is compiled for the release's x86-64-v2 baseline, so
what a person builds matches what prebuilt releases ship.  LM1's chiplet
module compiles MegaPad's header in, so LM1's tree is kept apart for each
MegaPad commit it is built against.

Everything here lives under the cache folder, in folders that only the
user's own account can open (PLAN.md decision 40).
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from .workspace import FANTASY_ENGINE_ROOT, workspace_root

LOCK_FILE = FANTASY_ENGINE_ROOT / "components.toml"

# The components in the order they are prepared.  LM1's chiplet module
# builds against MegaPad's header, so MegaPad comes first.
COMPONENT_NAMES = ("megapad", "akashic", "lm1")

# The processor level the command builds every native part for: the
# release's baseline (PLAN.md decision 23), for which LM1's chiplet module
# is always built and MegaPad's extensions are built when MP64_MARCH names it.
NATIVE_MARCH = "x86-64-v2"
# What x86-64-v2 adds to the first x86-64 processors, as Linux names the
# features in /proc/cpuinfo: CMPXCHG16B, LAHF and SAHF in 64-bit mode,
# POPCNT, SSE3, SSSE3, SSE4.1 and SSE4.2.
NATIVE_MARCH_FEATURES = ("cx16", "lahf_lm", "popcnt", "pni", "ssse3", "sse4_1", "sse4_2")
_KEYS = frozenset(("repository", "commit"))
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")

# The record inside an assembled tree of what it holds.  A tree without it
# is incomplete, whatever else it holds.
ASSEMBLED_STAMP = ".fantasy-engine-component.json"

# Git without prompts, in one language, and blind to the user's hooks and
# per-user settings, which could otherwise change what an archive holds.
_GIT_ENVIRONMENT = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "LC_ALL": "C",
}

Log = Callable[[str], None]


class ComponentError(RuntimeError):
    """A lock file, checkout or build the command cannot use."""


@dataclass(frozen=True)
class Component:
    name: str
    repository: str
    commit: str

    @property
    def short(self) -> str:
        return self.commit[:8]


def load(path: Path | str = LOCK_FILE) -> list[Component]:
    """The components the lock file at PATH names, in COMPONENT_NAMES' order.

    Each must be there, with its repository and its full commit, and nothing
    else may be: a misspelt name or setting would otherwise be ignored
    without a word."""

    path = Path(path)
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        raise ComponentError(f"there is no lock file at {path}") from None
    except tomllib.TOMLDecodeError as error:
        raise ComponentError(f"{path} is not valid TOML: {error}") from None
    unknown = sorted(set(data) - set(COMPONENT_NAMES))
    if unknown:
        raise ComponentError(f"{path} names no component called {', '.join(unknown)}")
    missing = [name for name in COMPONENT_NAMES if name not in data]
    if missing:
        raise ComponentError(f"{path} lacks {', '.join(missing)}")
    components = []
    for name in COMPONENT_NAMES:
        table = data[name]
        if not isinstance(table, dict):
            raise ComponentError(f"{path}: {name} must be a table")
        extra = sorted(set(table) - _KEYS)
        if extra:
            raise ComponentError(f"{path}: {name} has no setting {', '.join(extra)}")
        repository, commit = table.get("repository"), table.get("commit")
        if not isinstance(repository, str) or not repository:
            raise ComponentError(f"{path}: {name} needs its repository")
        if not isinstance(commit, str) or not _COMMIT.match(commit):
            raise ComponentError(
                f"{path}: {name}'s commit must be 40 lowercase hexadecimal digits")
        components.append(Component(name, repository, commit))
    return components


def cache_root(cache_dir: Path | str | None = None) -> Path:
    """The command's cache: CACHE_DIR, or fantasy-engine in the user's cache
    folder."""

    if cache_dir is not None:
        return Path(cache_dir).expanduser().resolve()
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return Path(base) / "fantasy-engine"


def private_folder(path: Path) -> Path:
    """PATH as a folder only the user's own account can open, made when it
    is missing.  A folder another account owns is refused."""

    path.mkdir(parents=True, exist_ok=True)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise ComponentError(f"{path} is not a folder")
    if info.st_uid != os.getuid():
        raise ComponentError(f"{path} belongs to another account")
    if stat.S_IMODE(info.st_mode) & 0o077:
        os.chmod(path, 0o700)
    return path


@contextlib.contextmanager
def _locked(path: Path) -> Iterator[None]:
    """Hold PATH's lock, so two commands never prepare one tree at once."""

    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _git(arguments: list[str], *, what: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *arguments], capture_output=True, text=True,
                            env={**os.environ, **_GIT_ENVIRONMENT})
    if result.returncode != 0:
        raise ComponentError(f"{what} failed: git {' '.join(arguments)}\n"
                             + (result.stderr or result.stdout).strip())
    return result


def _holds(store: list[str], commit: str) -> bool:
    """Whether the object store git reaches through STORE holds COMMIT."""

    result = subprocess.run(["git", *store, "cat-file", "-e", f"{commit}^{{commit}}"],
                            capture_output=True, env={**os.environ, **_GIT_ENVIRONMENT})
    return result.returncode == 0


def _checkout(component: Component, workspace: Path | None) -> Path | None:
    """The workspace's checkout of COMPONENT, if it has one."""

    if workspace is None:
        return None
    checkout = workspace / component.name
    return checkout if (checkout / ".git").exists() else None


def _object_store(component: Component, workspace: Path | None, cache: Path) -> list[str]:
    """Git arguments that reach an object store holding COMPONENT's commit:
    the workspace's checkout when it holds the commit, or else the cache's
    copy of the repository, which a shallow fetch of that one commit fills.
    The fetched commit gets a ref of its own, so no clean-up prunes it."""

    checkout = _checkout(component, workspace)
    if checkout is not None and _holds(["-C", str(checkout)], component.commit):
        return ["-C", str(checkout)]
    store = private_folder(cache / "repositories") / f"{component.name}.git"
    if not store.exists():
        _git(["init", "--bare", "--quiet", str(store)], what=f"making {store}")
    arguments = ["--git-dir", str(store)]
    if not _holds(arguments, component.commit):
        _git([*arguments, "fetch", "--quiet", "--depth", "1", "--no-tags",
              component.repository, component.commit],
             what=f"fetching {component.name} {component.short} from {component.repository}")
        if not _holds(arguments, component.commit):
            raise ComponentError(f"{component.repository} did not give "
                                 f"{component.name}'s commit {component.commit}")
        _git([*arguments, "update-ref", f"refs/fantasy-engine/{component.commit}",
              component.commit], what=f"keeping {component.name} {component.short}")
    return arguments


def tree_name(component: Component, components: list[Component]) -> str:
    """The folder that holds COMPONENT's assembled tree.  LM1's tree also
    names the MegaPad commit its chiplet module compiles against."""

    name = f"{component.name}-{component.commit}"
    if component.name == "lm1":
        megapad = next(c for c in components if c.name == "megapad")
        name += f"-megapad-{megapad.commit}"
    return name


def _assembled(tree: Path, component: Component) -> bool:
    try:
        stamp = json.loads((tree / ASSEMBLED_STAMP).read_text())
    except (OSError, ValueError):
        return False
    return stamp.get("name") == component.name and stamp.get("commit") == component.commit


def assemble(component: Component, components: list[Component], *, cache: Path,
             workspace: Path | None, log: Log = print) -> Path:
    """COMPONENT's tree at its recorded commit, assembled into CACHE once and
    reused after that."""

    trees = private_folder(cache / "components")
    tree = trees / tree_name(component, components)
    with _locked(trees / f".{tree.name}.lock"):
        if _assembled(tree, component):
            return tree
        # What an interrupted assembly left, which nothing else can be using
        # while this lock is held.
        for leftover in trees.glob(f".{tree.name}.*.tmp"):
            shutil.rmtree(leftover)
        if tree.exists():
            shutil.rmtree(tree)
        store = _object_store(component, workspace, cache)
        source = " ".join(store[1:])
        log(f"Assembling {component.name} {component.short} from {source}")
        objects = _git([*store, "rev-parse", f"{component.commit}^{{tree}}"],
                       what=f"reading {component.name}'s tree").stdout.strip()
        scratch = Path(tempfile.mkdtemp(dir=trees, prefix=f".{tree.name}.", suffix=".tmp"))
        try:
            archive = subprocess.Popen(
                ["git", *store, "archive", "--format=tar", component.commit],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={**os.environ, **_GIT_ENVIRONMENT})
            with tarfile.open(fileobj=archive.stdout, mode="r|") as members:
                members.extractall(scratch, filter="data")
            complaint = archive.stderr.read().decode(errors="replace")
            if archive.wait() != 0:
                raise ComponentError(f"git archive of {component.name} {component.short} "
                                     f"failed:\n{complaint.strip()}")
            (scratch / ASSEMBLED_STAMP).write_text(json.dumps({
                "name": component.name,
                "repository": component.repository,
                "commit": component.commit,
                "tree": objects,
                "assembled": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }, indent=2) + "\n")
            os.rename(scratch, tree)
        except BaseException:
            shutil.rmtree(scratch, ignore_errors=True)
            raise
    return tree


def unpushed(component: Component, workspace: Path | None) -> str | None:
    """A warning when COMPONENT's commit is on no remote-tracking branch of
    the workspace's checkout.  Pushes are made by hand, so a recorded commit
    may be one that only this machine holds, which no one else can build."""

    checkout = _checkout(component, workspace)
    if checkout is None:
        return None
    result = subprocess.run(
        ["git", "-C", str(checkout), "branch", "--remotes", "--contains", component.commit,
         "--format=%(refname)"],
        capture_output=True, text=True, env={**os.environ, **_GIT_ENVIRONMENT})
    if result.returncode != 0 or result.stdout.strip():
        # A checkout without the commit says nothing; the fetch decides.
        return None
    return (f"{component.name}'s recorded commit {component.short} is on no "
            f"remote-tracking branch of {checkout}; others can build this lock "
            f"file only once it is pushed")


def _run_build(arguments: list[str], what: str, log: Log) -> None:
    log(f"Building {what}")
    result = subprocess.run(arguments, capture_output=True, text=True, env=native_environment())
    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip().splitlines()
        raise ComponentError(f"building {what} failed: {' '.join(arguments)}\n"
                             + "\n".join(output[-40:]))


def native_environment() -> dict[str, str]:
    """The environment of the native builds: MegaPad's extensions compiled
    for NATIVE_MARCH, and no Python bytecode caches written into the trees
    or the command's own environment by the build scripts."""

    return {**os.environ, "MP64_MARCH": NATIVE_MARCH, "PYTHONDONTWRITEBYTECODE": "1"}


def native_stamps(trees: dict[str, Path], abi: str) -> tuple[Path, Path]:
    """The records in the assembled TREES of MegaPad's extensions built for
    the Python of ABI, and of LM1's chiplet module."""

    return (trees["megapad"] / f".fantasy-engine-native.{abi}.json",
            trees["lm1"] / ".fantasy-engine-native.json")


def build_native(trees: dict[str, Path], *, python: str = sys.executable,
                 log: Log = print) -> None:
    """Build the native parts in the assembled TREES with each component's
    own build, for NATIVE_MARCH: MegaPad's extensions for PYTHON, and LM1's
    chiplet module against the assembled MegaPad.  A tree whose build is
    already recorded, for this Python where that matters, is left as it is.
    Each build holds its tree's lock, so two commands never build in one
    tree at once."""

    if shutil.which("make") is None:
        raise ComponentError("building the native parts needs make, which is not installed")
    abi = sysconfig.get_config_var("SOABI") if python == sys.executable else _abi(python)
    megapad, lm1 = trees["megapad"], trees["lm1"]
    megapad_stamp, lm1_stamp = native_stamps(trees, abi)
    with _locked(megapad.parent / f".{megapad.name}.lock"):
        if not megapad_stamp.exists():
            _require_pybind11(python)
            _run_build(["make", "-C", str(megapad), "build", f"VENV_PY={python}"],
                       f"MegaPad's native extensions for {abi}", log)
            _write_stamp(megapad_stamp, {"python": python, "abi": abi, "march": NATIVE_MARCH})
    with _locked(lm1.parent / f".{lm1.name}.lock"):
        if not lm1_stamp.exists():
            _run_build(["make", "-C", str(lm1 / "chiplet"), f"MEGAPAD_ROOT={megapad}"],
                       "LM1's chiplet module", log)
            _write_stamp(lm1_stamp, {"megapad": str(megapad), "march": NATIVE_MARCH})


def _abi(python: str) -> str:
    result = subprocess.run(
        [python, "-c", "import sysconfig; print(sysconfig.get_config_var('SOABI'))"],
        capture_output=True, text=True)
    if result.returncode != 0:
        raise ComponentError(f"{python} could not be asked for its ABI")
    return result.stdout.strip()


def _require_pybind11(python: str) -> None:
    result = subprocess.run([python, "-c", "import pybind11"], capture_output=True)
    if result.returncode != 0:
        raise ComponentError(f"MegaPad's native extensions build with pybind11, which "
                             f"{python} cannot import; install it into that Python")


def _write_stamp(path: Path, facts: dict) -> None:
    facts = {**facts, "built": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    path.write_text(json.dumps(facts, indent=2) + "\n")


def assemble_all(lock_file: Path | str = LOCK_FILE, *, cache_dir: Path | str | None = None,
                 workspace: Path | None = None, log: Log = print,
                 warn: Log | None = None) -> dict[str, Path]:
    """Every component at the commit LOCK_FILE records, assembled into the
    cache, by name.  WORKSPACE, the workspace's folder by default, is where
    checkouts that may already hold the commits sit.  Each recorded commit
    that no remote-tracking branch holds is reported through WARN."""

    if warn is None:
        warn = lambda message: print(f"warning: {message}", file=sys.stderr)  # noqa: E731
    if shutil.which("git") is None:
        raise ComponentError("assembling the components needs git, which is not installed")
    components = load(lock_file)
    workspace = workspace_root() if workspace is None else Path(workspace)
    cache = private_folder(cache_root(cache_dir))
    for component in components:
        message = unpushed(component, workspace)
        if message:
            warn(message)
    return {component.name: assemble(component, components, cache=cache,
                                     workspace=workspace, log=log)
            for component in components}


def prepare(lock_file: Path | str = LOCK_FILE, *, cache_dir: Path | str | None = None,
            workspace: Path | None = None, log: Log = print,
            warn: Log | None = None) -> dict[str, Path]:
    """Every component at the commit LOCK_FILE records, assembled into the
    cache with its native parts built, by name (assemble_all)."""

    trees = assemble_all(lock_file, cache_dir=cache_dir, workspace=workspace, log=log,
                         warn=warn)
    build_native(trees, log=log)
    return trees
