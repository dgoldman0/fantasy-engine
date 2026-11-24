"""What this computer needs to build and run Fantasy Engine (PLAN.md Part 4d).

``fantasy-engine doctor`` checks each requirement in turn and prints one
finding for each: ``ok`` with what it found, ``missing`` with what to do, or
``advice`` for something the machine runs without but works better with.  It
exits with 1 when anything is missing.

Each rule is checked where it is kept.  The command's own requirements, the
Python and packages ``pyproject.toml`` names and the tools that build the
native parts, are checked here.  The e2fsprogs release the volumes need is
Akashic's image tool's rule, and the fonts the viewer falls back to are
MegaPad's list, so the doctor asks the component trees for those: the
components at their recorded commits, assembled into the cache as a build
would assemble them but not built, or in development mode the workspace's
checkouts.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import sysconfig
import tomllib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from . import components, machines
from .workspace import FANTASY_ENGINE_ROOT

OK, MISSING, ADVICE = "ok", "missing", "advice"

# How the documented hosts name what the checks below look for.
UBUNTU = {
    "git": "git",
    "make": "build-essential",
    "compiler": "build-essential",
    "libslirp": "pkg-config libslirp-dev libglib2.0-dev",
    "e2fsprogs": "e2fsprogs",
    "fonts": "fontconfig fonts-noto-core fonts-noto-cjk fonts-noto-color-emoji",
}

# A program that needs C++17, for the compiler check.
CXX17_PROGRAM = """\
#include <optional>
#include <string_view>
int main() {
    std::optional<std::string_view> word{"leviathan"};
    if constexpr (sizeof(void *) == 8) return word ? 0 : 1;
    return 2;
}
"""


@dataclass(frozen=True)
class Finding:
    """One requirement: what it is, whether this computer meets it, what was
    found, and what to do when it is not met."""

    requirement: str
    state: str
    detail: str
    remedy: str = ""


Run = Callable[..., subprocess.CompletedProcess]


def _run(arguments: list[str], **options) -> subprocess.CompletedProcess:
    return subprocess.run(arguments, capture_output=True, text=True, **options)


def _first_line(text: str) -> str:
    return text.strip().splitlines()[0] if text.strip() else ""


def _install(what: str) -> str:
    return f"Install it (on Ubuntu and Debian: sudo apt install {UBUNTU[what]})."


# This computer.

def computer(cpuinfo: Path = Path("/proc/cpuinfo")) -> Finding:
    """Linux on a 64-bit Intel or AMD processor with the features of the
    level the command builds native parts for."""

    system, machine = platform.system(), platform.machine()
    if system != "Linux" or machine not in ("x86_64", "AMD64"):
        return Finding("this computer", MISSING, f"{system} on {machine}",
                       "Fantasy Engine runs on Linux on 64-bit Intel and AMD processors, "
                       "and on Windows through WSL2.")
    try:
        flags = next((line.split(":", 1)[1].split()
                      for line in cpuinfo.read_text().splitlines()
                      if line.startswith("flags")), [])
    except OSError as error:
        return Finding("this computer", ADVICE, f"Linux on x86-64; {error}",
                       f"The native parts need a {components.NATIVE_MARCH} processor.")
    lacking = [flag for flag in components.NATIVE_MARCH_FEATURES if flag not in flags]
    if lacking:
        return Finding("this computer", MISSING,
                       f"the processor lacks {', '.join(lacking)}",
                       f"The native parts are built for {components.NATIVE_MARCH}, which "
                       "nearly every 64-bit processor made since 2009 supports.")
    return Finding("this computer", OK,
                   f"Linux on x86-64, with the {components.NATIVE_MARCH} features")


# The command's own Python and packages.

def _project(root: Path = FANTASY_ENGINE_ROOT) -> dict:
    with open(root / "pyproject.toml", "rb") as handle:
        return tomllib.load(handle)["project"]


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", text)[:3])


def python(project: dict | None = None) -> list[Finding]:
    """The Python running the command, at the version pyproject.toml asks
    for, with the headers the native parts compile against."""

    project = project or _project()
    wanted = project["requires-python"]
    minimum = _version(wanted)
    running = ".".join(map(str, sys.version_info[:3]))
    uv = ("Install uv (https://docs.astral.sh/uv/) and install the command with it, "
          "as the README says; uv brings Python 3.13 where this computer lacks it.")
    if sys.version_info[:len(minimum)] < minimum:
        return [Finding("Python", MISSING, f"{running} at {sys.executable}; the command needs "
                        f"{wanted.removeprefix('>=')} or later", uv)]
    found = [Finding("Python", OK, f"{running} at {sys.executable}")]
    headers = Path(sysconfig.get_paths()["include"]) / "Python.h"
    if headers.is_file():
        found.append(Finding("Python's headers", OK, str(headers.parent)))
    else:
        found.append(Finding("Python's headers", MISSING,
                             f"{headers} is missing, and the native parts compile against it",
                             uv + " Its Python carries its headers."))
    return found


def packages(project: dict | None = None) -> list[Finding]:
    """Each package pyproject.toml lists, installed at a version it allows."""

    project = project or _project()
    found = []
    for requirement in project.get("dependencies", []):
        name, at_least, version = re.match(r"\s*([A-Za-z0-9._-]+)\s*(>=)?\s*([^;,\s]*)",
                                           requirement).groups()
        wanted = version if at_least else ""
        try:
            version = metadata.version(name)
        except metadata.PackageNotFoundError:
            found.append(Finding(name, MISSING, "not installed for this Python",
                                 "Install the command with uv as the README says, which "
                                 "installs the packages it needs."))
            continue
        if wanted and _version(version) < _version(wanted):
            found.append(Finding(name, MISSING, f"{version}; the command needs {wanted} or later",
                                 "Install the command again with uv, which upgrades it."))
        else:
            found.append(Finding(name, OK, version))
    return found


# The tools that assemble the components and build their native parts.

def program(name: str, what: str, *, run: Run = _run) -> Finding:
    """The program NAME on the PATH, with the first line of its version."""

    path = shutil.which(name)
    if path is None:
        return Finding(name, MISSING, f"not found; {what}", _install(name))
    version = _first_line(run([path, "--version"]).stdout)
    return Finding(name, OK, f"{version} ({path})" if version else path)


def _compilers() -> list[tuple[str, list[str]]]:
    """The C++ compilers the native builds call: the one Python's build tools
    use for MegaPad's extensions, and the one LM1's chiplet Makefile uses.
    CXX in the environment sets both."""

    configured = os.environ.get("CXX")
    if configured:
        return [("the native builds", shlex.split(configured))]
    extensions = shlex.split(sysconfig.get_config_var("CXX") or "c++")
    return [("MegaPad's extensions", extensions), ("LM1's chiplet module", ["g++"])]


def compilers(*, run: Run = _run) -> list[Finding]:
    """Each C++ compiler the native builds call, compiling C++17 for the
    level the command builds for."""

    found, seen = [], set()
    for purpose, command in _compilers():
        path = shutil.which(command[0])
        requirement = f"C++ compiler for {purpose}"
        if path is None:
            found.append(Finding(requirement, MISSING, f"{command[0]} not found",
                                 _install("compiler")))
            continue
        if path in seen:
            continue
        seen.add(path)
        trial = run([*command, "-std=c++17", f"-march={components.NATIVE_MARCH}",
                     "-x", "c++", "-fsyntax-only", "-"], input=CXX17_PROGRAM)
        version = _first_line(run([path, "--version"]).stdout) or path
        if trial.returncode != 0:
            found.append(Finding(requirement, MISSING,
                                 f"{version} cannot compile C++17 for "
                                 f"{components.NATIVE_MARCH}: {_first_line(trial.stderr)}",
                                 "Install GCC 11 or Clang 12 or later (on Ubuntu and Debian: "
                                 f"sudo apt install {UBUNTU['compiler']})."))
        else:
            found.append(Finding(requirement, OK, version))
    return found


def libslirp(*, run: Run = _run) -> Finding:
    """libslirp's development files, with GLib's, as pkg-config finds them for
    the simulator's network card."""

    if shutil.which("pkg-config") is None:
        return Finding("libslirp", MISSING, "pkg-config, which finds libslirp, is not installed",
                       _install("libslirp"))
    result = run(["pkg-config", "--modversion", "slirp"])
    if result.returncode != 0:
        return Finding("libslirp", MISSING, _first_line(result.stderr) or "pkg-config finds no slirp",
                       "Install libslirp's and GLib's development files (on Ubuntu and "
                       f"Debian: sudo apt install {UBUNTU['libslirp']}).")
    return Finding("libslirp", OK, result.stdout.strip())


# What the component trees say.

def trees(*, workspace: Path | None, lock_file: Path, cache_dir: Path | None,
          log: Callable[[str], None]) -> tuple[list[Finding], machines.Trees | None]:
    """The component trees the remaining checks ask, and what was found on
    the way: in development mode the workspace's checkouts with their native
    parts, which must be built; otherwise the components at their recorded
    commits, assembled but not built, which the first build or run builds."""

    if workspace is not None:
        try:
            found = machines.trees(workspace=workspace)
        except machines.MachineError as error:
            return [Finding("the workspace", MISSING, str(error),
                            "Build what is missing in the workspace's checkouts.")], None
        return [Finding("the workspace", OK, f"{Path(workspace).resolve()}, native parts built")], found
    try:
        assembled = components.assemble_all(lock_file, cache_dir=cache_dir, log=log)
    except components.ComponentError as error:
        return [Finding("the components", MISSING, str(error),
                        "Install git and reach GitHub, or check the lock file.")], None
    recorded = {component.name: component.commit for component in components.load(lock_file)}
    found = machines.Trees(assembled["akashic"], assembled["megapad"], assembled["lm1"],
                           sources=recorded, development=False)
    findings = [Finding("the components", OK, ", ".join(
        f"{name} {commit[:8]}" for name, commit in recorded.items()))]
    abi = sysconfig.get_config_var("SOABI")
    if all(stamp.exists() for stamp in components.native_stamps(assembled, abi)):
        findings.append(Finding("native parts", OK, f"built for {abi} and {components.NATIVE_MARCH}"))
    else:
        findings.append(Finding("native parts", ADVICE, "not built yet",
                                "The first build or run builds them, which takes about a minute."))
    return findings, found


def e2fsprogs(source: machines.Trees, *, run: Run = _run) -> Finding:
    """The e2fsprogs a build would make the ext4 volumes with, as Akashic's
    image tool judges them."""

    result = run([sys.executable, "-m", "toolchain.image", "host"], cwd=source.akashic,
                 env=machines.environment(source))
    if result.returncode != 0:
        complaint = result.stderr.strip().removeprefix("error: ")
        return Finding("e2fsprogs", MISSING, complaint.splitlines()[0] if complaint else
                       f"the image tool stopped with status {result.returncode}",
                       "Install e2fsprogs 1.47.0 or later (on Ubuntu and Debian: sudo apt "
                       "install e2fsprogs; Ubuntu 24.04, Debian 12 and current Fedora "
                       "have it).")
    tools = json.loads(result.stdout)["e2fsprogs"]
    mke2fs = tools.get("mke2fs") or next(iter(tools.values()))
    return Finding("e2fsprogs", OK, f"{_first_line(mke2fs['version'])} "
                   f"({Path(mke2fs['path']).parent})")


FONTS_PROGRAM = """\
import json
from rich_terminal.font_set import DEFAULT_FALLBACK_FAMILIES, discover_fallback_fonts
print(json.dumps({family: bool(discover_fallback_fonts((family,)))
                  for family in DEFAULT_FALLBACK_FAMILIES}))
"""


def fonts(source: machines.Trees, *, run: Run = _run) -> Finding:
    """The faces the viewer falls back to for characters its own font lacks,
    as fontconfig finds them for MegaPad's viewer."""

    if shutil.which("fc-match") is None:
        return Finding("fonts", ADVICE, "fontconfig is not installed, so the viewer has only "
                       "its own font, and characters it lacks show as boxes",
                       _install("fonts"))
    result = run([sys.executable, "-c", FONTS_PROGRAM], cwd=source.megapad,
                 env=machines.environment(source))
    if result.returncode != 0:
        return Finding("fonts", ADVICE, "MegaPad's viewer could not be asked for its fonts: "
                       + _first_line(result.stderr))
    families = json.loads(result.stdout)
    lacking = [family for family, present in families.items() if not present]
    if lacking:
        return Finding("fonts", ADVICE,
                       f"fontconfig lacks {', '.join(lacking)}, so characters only those "
                       "faces cover show as boxes", _install("fonts"))
    return Finding("fonts", OK, f"all {len(families)} faces the viewer falls back to")


def display(environ: dict[str, str] | None = None) -> Finding:
    """A desktop session for the viewer's window."""

    environ = os.environ if environ is None else environ
    for variable in ("WAYLAND_DISPLAY", "DISPLAY"):
        if environ.get(variable):
            return Finding("display", OK, f"{variable}={environ[variable]}")
    return Finding("display", ADVICE, "no desktop session, so the viewer cannot open a window",
                   "Run from a desktop session, or on Windows from WSL2 with WSLg; without one, "
                   "run --no-viewer only serves.")


def examine(*, workspace: Path | None = None, lock_file: Path = components.LOCK_FILE,
            cache_dir: Path | None = None,
            log: Callable[[str], None] = print) -> list[Finding]:
    """Every finding, in the order a person would set the computer up."""

    found = [computer(), *python(), *packages(),
             program("git", "the command assembles the components with it"),
             program("make", "the native parts build with it"),
             *compilers(), libslirp()]
    if shutil.which("git") is None:
        found.append(Finding("the components", MISSING, "reading them needs git",
                             "Install git; e2fsprogs and the fonts are checked once the "
                             "components can be read."))
        source = None
    else:
        on_the_way, source = trees(workspace=workspace, lock_file=lock_file,
                                   cache_dir=cache_dir, log=log)
        found += on_the_way
    if source is not None:
        found += [e2fsprogs(source), fonts(source)]
    found.append(display())
    return found


def report(findings: Iterable[Finding], write: Callable[[str], None] = print) -> int:
    """Print FINDINGS one to a line, each remedy below its finding, and
    return 1 when any requirement is missing."""

    missing = False
    for finding in findings:
        write(f"{finding.state:<8} {finding.requirement}: {finding.detail}")
        if finding.remedy and finding.state != OK:
            write(f"{'':<8} {finding.remedy}")
        missing = missing or finding.state == MISSING
    return 1 if missing else 0
