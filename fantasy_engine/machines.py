"""Configurations as machines a person builds and runs (PLAN.md Part 4c).

A configuration is a TOML file that Akashic's image tool reads.  This
repository ships some under configurations/, and a person makes their own
with ``new``.  Each has one folder, private to the user, under the data root
(``~/.local/share/fantasy-engine/configurations/<name>/`` by default): the
user's own configuration file, the volumes the image tool builds, and their
session manifest.  A build replaces the boot, settings and system volumes
and keeps the user volume once it exists.

Every step that needs what a configuration says asks the image tool in the
component trees, so this repository never interprets the format.  The trees
are the components at the commits ``components.toml`` records, assembled in
the cache, or in development mode a workspace's checkouts as they stand.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from . import components
from .workspace import FANTASY_ENGINE_ROOT

Log = Callable[[str], None]

SHIPPED = FANTASY_ENGINE_ROOT / "configurations"
CONFIGURATION_FILE = "configuration.toml"
# The boot image's name in a configuration's folder; the image tool names the
# other volumes and the session manifest after it.
IMAGE_NAME = "machine.img"
MANIFEST_NAME = "machine-session.json"
BUILT_FROM_NAME = "built-from.json"
_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,62}\Z")
# How long a server may take to prepare its machine before its socket
# answers: the boot script runs first.
SERVER_START_SECONDS = 300.0


class MachineError(RuntimeError):
    """A configuration that cannot be found, built or run, and why."""


@dataclass(frozen=True)
class Machine:
    """A configuration and the folder its volumes live in."""

    name: str
    configuration: Path  # its TOML file
    folder: Path  # its volumes and session manifest
    own: bool  # the user's own, or shipped with this repository


@dataclass(frozen=True)
class Trees:
    """The component trees a build or a run uses, and what a build records
    of them: each component's commit, or in development mode each
    checkout's head and a digest of its changes."""

    akashic: Path
    megapad: Path
    lm1: Path
    sources: Mapping[str, object]
    development: bool


def data_root(data_dir: Path | str | None = None) -> Path:
    """Where configurations' folders live: DATA_DIR, or the XDG data home's
    fantasy-engine folder."""

    if data_dir is not None:
        return Path(data_dir).expanduser().resolve()
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "fantasy-engine"


def runtime_root(data_dir: Path | str | None = None) -> Path:
    """A private folder for servers' sockets: the user's runtime folder's
    fantasy-engine folder, or the data root's when there is none."""

    base = os.environ.get("XDG_RUNTIME_DIR")
    folder = Path(base) / "fantasy-engine" if base else data_root(data_dir) / "run"
    return components.private_folder(folder)


def _folder(name: str, data_dir: Path | str | None) -> Path:
    return data_root(data_dir) / "configurations" / name


def catalog(data_dir: Path | str | None = None) -> list[Machine]:
    """The shipped configurations and the user's own, by name."""

    machines = {}
    if SHIPPED.is_dir():
        for path in sorted(SHIPPED.glob(f"*/{CONFIGURATION_FILE}")):
            name = path.parent.name
            machines[name] = Machine(name, path, _folder(name, data_dir), own=False)
    own = data_root(data_dir) / "configurations"
    if own.is_dir():
        for path in sorted(own.glob(f"*/{CONFIGURATION_FILE}")):
            name = path.parent.name
            machines[name] = Machine(name, path, path.parent, own=True)
    return [machines[name] for name in sorted(machines)]


def find(name: str, data_dir: Path | str | None = None) -> Machine:
    """The configuration NAME: the user's own, or else a shipped one."""

    for machine in catalog(data_dir):
        if machine.name == name:
            return machine
    known = ", ".join(machine.name for machine in catalog(data_dir)) or "none"
    raise MachineError(f"no configuration is named {name!r} (the configurations: {known})")


def manifest(machine: Machine) -> dict | None:
    """The session manifest of MACHINE's last build, or None."""

    path = machine.folder / MANIFEST_NAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def _git(tree: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(tree), *arguments],
        capture_output=True,
        env={**os.environ, **components._GIT_ENVIRONMENT},
    )
    if result.returncode != 0:
        raise MachineError(f"git {' '.join(arguments)} failed in {tree}: "
                           + result.stderr.decode(errors="replace").strip())
    return result.stdout


def _checkout_state(tree: Path) -> dict[str, str]:
    """A checkout's head and a digest of its changes: what it differs by
    from that head, and each untracked file's name and contents."""

    digest = hashlib.sha256(_git(tree, "diff", "HEAD", "--binary"))
    for name in sorted(_git(tree, "ls-files", "--others", "--exclude-standard", "-z")
                       .split(b"\0")):
        if name:
            digest.update(name + b"\0" + hashlib.sha256((tree / name.decode()).read_bytes())
                          .digest())
    return {"head": _git(tree, "rev-parse", "HEAD").decode().strip(),
            "changes": digest.hexdigest()}


def chiplet_module(lm1: Path) -> Path:
    """LM-1's chiplet module, as LM-1's own build leaves it."""

    return lm1 / "chiplet" / "build" / "lm1_chiplet.so"


def _megapad_extension(megapad: Path, stem: str) -> bool:
    return any(megapad.glob(f"{stem}.*.so"))


def trees(*, workspace: Path | None = None, lock_file: Path = components.LOCK_FILE,
          cache_dir: Path | str | None = None, log: Log = print) -> Trees:
    """The component trees: with WORKSPACE, its checkouts as they stand,
    whose native parts must already be built; otherwise each component at
    the commit LOCK_FILE records, assembled in the cache and built there."""

    if workspace is None:
        prepared = components.prepare(lock_file, cache_dir=cache_dir, log=log)
        commits = {component.name: component.commit for component in components.load(lock_file)}
        return Trees(prepared["akashic"], prepared["megapad"], prepared["lm1"],
                     sources=commits, development=False)
    workspace = Path(workspace).resolve()
    found = {name: workspace / name for name in components.COMPONENT_NAMES}
    for name, tree in found.items():
        if not (tree / ".git").exists():
            raise MachineError(f"the workspace has no {name} checkout: {tree}")
    missing = [
        what for what, present in (
            ("MegaPad's _megaforth_native (make -C megapad build)",
             _megapad_extension(found["megapad"], "_megaforth_native")),
            ("MegaPad's _mp64_slirp (make -C megapad build)",
             _megapad_extension(found["megapad"], "_mp64_slirp")),
            ("LM-1's chiplet module (make -C lm1/chiplet)",
             chiplet_module(found["lm1"]).is_file()),
        ) if not present
    ]
    if missing:
        raise MachineError("development mode uses the workspace's native parts as built, "
                           "and these are missing: " + "; ".join(missing))
    return Trees(found["akashic"], found["megapad"], found["lm1"],
                 sources={name: _checkout_state(tree) for name, tree in found.items()},
                 development=True)


def _tool(source: Trees, *arguments: str, capture: bool = False) -> subprocess.CompletedProcess:
    """Run Akashic's image tool in SOURCE's trees."""

    return subprocess.run(
        [sys.executable, "-m", "toolchain.image", *arguments],
        cwd=source.akashic,
        env={**os.environ, "MEGAPAD_ROOT": str(source.megapad)},
        capture_output=capture,
        text=True,
    )


def check(machine: Machine, source: Trees) -> dict:
    """What MACHINE's configuration says, as the image tool reads it."""

    result = _tool(source, "check", str(machine.configuration), capture=True)
    if result.returncode != 0:
        raise MachineError(result.stderr.strip().removeprefix("error: "))
    return json.loads(result.stdout)


def stale(machine: Machine, source: Trees) -> str | None:
    """Why MACHINE needs a build before it runs, or None when its volumes
    are built from what SOURCE and its configuration hold now."""

    built = manifest(machine)
    if built is None:
        return "it has not been built"
    volumes = [name for name in built.get("storage", {}).values() if name]
    if any(not (machine.folder / name).is_file() for name in volumes):
        return "a volume is missing"
    recorded = built.get("built_from") or {}
    if recorded.get("components") != dict(source.sources):
        return "a component changed"
    now = check(machine, source)
    configuration = recorded.get("configuration") or {}
    if configuration.get("sha256") != now["sha256"]:
        return "its configuration changed"
    if configuration.get("documents_sha256") != now["documents_sha256"]:
        return "its documents changed"
    return None


def build(machine: Machine, source: Trees, *, log: Log = print) -> dict:
    """Build MACHINE's volumes in its folder from SOURCE and return the new
    session manifest.  The user volume is kept when it exists."""

    folder = components.private_folder(machine.folder)
    built_from = folder / BUILT_FROM_NAME
    descriptor = os.open(built_from, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump({"components": dict(source.sources),
                   "mode": "development" if source.development else "release"}, stream)
    log(f"Building {machine.name}")
    result = _tool(source, "build", str(machine.configuration), str(folder / IMAGE_NAME),
                   "--built-from", str(built_from))
    if result.returncode != 0:
        raise MachineError(f"the image tool could not build {machine.name}")
    built = manifest(machine)
    if built is None:
        raise MachineError(f"the image tool wrote no session manifest for {machine.name}")
    return built


def _compact(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def server_command(machine: Machine, source: Trees, built: Mapping, socket_path: Path, *,
                   debug_access: bool = False) -> list[str]:
    """The simulator server that runs MACHINE's volumes as BUILT describes
    them, serving SOCKET_PATH, with LM-1's chiplet module on its first
    port."""

    storage = built["storage"]
    command = [sys.executable, str(source.megapad / "megapad.py"), "--mode", "simulator",
               "--storage", str(machine.folder / storage["boot"])]
    for option, unit in (("--settings-storage", "settings"), ("--system-storage", "system"),
                         ("--user-storage", "user")):
        if storage.get(unit):
            command += [option, str(machine.folder / storage[unit])]
    hardware = built["machine"]
    viewer = built["viewer"]
    command += [
        "--socket", str(socket_path),
        "--ram-kib", str(hardware["ram_kib"]),
        "--ext-mem-mib", str(hardware["ext_mem_mib"]),
        "--vram-mib", str(hardware["vram_mib"]),
        "--cores", str(hardware["full_cores"]),
        "--cols", str(viewer["cols"]),
        "--rows", str(viewer["rows"]),
    ]
    rich = built.get("rich_terminal")
    if rich:
        command += ["--rich-terminal-policy", _compact(rich["policy"])]
        if rich.get("retained_policy"):
            command += ["--retained-terminal-policy", _compact(rich["retained_policy"])]
    network = built.get("network") or {}
    if network.get("enabled"):
        command += ["--nic", "slirp"]
        if network.get("local_access"):
            command.append("--local-access")
    if debug_access:
        command.append("--debug-access")
    command += ["--chiplet", str(chiplet_module(source.lm1))]
    return command


def viewer_command(source: Trees, built: Mapping, socket_path: Path) -> list[str]:
    """MegaPad's viewer on SOCKET_PATH, with Akashic's font at the size
    BUILT's configuration asks for."""

    return [sys.executable, str(source.megapad / "session_viewer.py"),
            "--socket", str(socket_path),
            "--font", str(source.akashic / "assets" / "fonts" / "DejaVuSansMono.ttf"),
            "--font-size", str(built["viewer"]["font_size"]),
            "--title", built.get("title") or "Fantasy Engine"]


def _answers(socket_path: Path) -> bool:
    if not socket_path.exists():
        return False
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
        try:
            probe.connect(str(socket_path))
        except OSError:
            return False
    return True


def _await_server(server: subprocess.Popen, socket_path: Path, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while not _answers(socket_path):
        if server.poll() is not None:
            raise MachineError(f"the server stopped before it served (status {server.returncode})")
        if time.monotonic() > deadline:
            raise MachineError(f"the server did not serve within {timeout:.0f} s")
        time.sleep(0.1)


def _stop(server: subprocess.Popen) -> None:
    if server.poll() is None:
        server.terminate()
        try:
            server.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10.0)


def exposed(machine: Machine, built: Mapping) -> list[str]:
    """What of MACHINE's folder another account owns or could read or
    write: the folder itself, each volume BUILT names, and the manifest.
    The volumes hold everything the machine knows, keys and sign-ins
    included, and the machine has no accounts of its own."""

    paths = [machine.folder, machine.folder / MANIFEST_NAME,
             *(machine.folder / name for name in built.get("storage", {}).values() if name)]
    found = []
    for path in paths:
        info = path.stat()
        if info.st_uid != os.getuid():
            found.append(f"{path} belongs to another account")
        elif info.st_mode & 0o077:
            found.append(f"{path} is open to other accounts "
                         f"(mode {info.st_mode & 0o777:o}; chmod go= it)")
    return found


def run(machine: Machine, source: Trees, *, data_dir: Path | str | None = None,
        viewer: bool = True, debug_access: bool = False, log: Log = print) -> int:
    """Build MACHINE when what it was built from changed, serve it, and
    open the viewer; the server stops when the viewer closes.  Without
    VIEWER, serve until interrupted."""

    reason = stale(machine, source)
    built = build(machine, source, log=log) if reason else manifest(machine)
    if reason:
        log(f"Built {machine.name}: {reason}")
    problems = exposed(machine, built)
    if problems:
        raise MachineError(f"{machine.name}'s files must be the user's alone: "
                           + "; ".join(problems))
    socket_path = runtime_root(data_dir) / f"{machine.name}.sock"
    if _answers(socket_path):
        raise MachineError(f"{machine.name} is already running on {socket_path}")
    server = subprocess.Popen(server_command(machine, source, built, socket_path,
                                             debug_access=debug_access))
    try:
        _await_server(server, socket_path, SERVER_START_SECONDS)
        if not viewer:
            log(f"Serving {machine.name} on {socket_path}; Ctrl+C stops it")
            return server.wait()
        return subprocess.run(viewer_command(source, built, socket_path)).returncode
    except KeyboardInterrupt:
        return 130
    finally:
        _stop(server)


def new(name: str, original: Machine, source: Trees,
        data_dir: Path | str | None = None) -> Machine:
    """Copy ORIGINAL's configuration file under NAME for the user to edit,
    with its documents folder when that folder sits beside it.  The copy
    gets a user volume of its own at its first build."""

    if not _NAME.match(name):
        raise MachineError(f"a configuration's name is lowercase letters, digits and dashes, "
                           f"not {name!r}")
    if any(machine.name == name for machine in catalog(data_dir)):
        raise MachineError(f"a configuration is already named {name!r}")
    said = check(original, source)
    folder = components.private_folder(_folder(name, data_dir))
    target = folder / CONFIGURATION_FILE
    shutil.copyfile(original.configuration, target)
    target.chmod(0o600)
    documents = said.get("documents")
    if documents and Path(documents).is_relative_to(original.configuration.parent):
        relative = Path(documents).relative_to(original.configuration.parent)
        copied = folder / relative
        shutil.copytree(documents, copied)
        for path in (copied, *copied.rglob("*")):
            path.chmod(0o700 if path.is_dir() else 0o600)
    return Machine(name, target, folder, own=True)
