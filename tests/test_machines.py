"""Configurations as machines: finding them, their folders, the rebuild
rule, the server and viewer they run with, new configurations, and a build
in development mode through the workspace's Akashic image tool."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from fantasy_engine import command, machines
from fantasy_engine.workspace import workspace_root

MANIFEST = {
    "title": "Desktop",
    "storage": {"boot": "machine.img", "settings": "machine-settings.img",
                "system": "machine-system.img", "user": "machine-user.img"},
    "machine": {"ram_kib": 1024, "ext_mem_mib": 384, "vram_mib": 4,
                "full_cores": 1, "clusters": 0},
    "rich_terminal": {"policy": {"b": 2, "a": 1}, "retained_policy": {"c": 3}},
    "viewer": {"cols": 160, "rows": 48, "font_size": 16},
    "network": {"enabled": False, "local_access": False},
    "built_from": {"components": {"akashic": "a" * 40},
                   "configuration": {"sha256": "c", "documents_sha256": "d"}},
}


def _trees(root: Path, **sources) -> machines.Trees:
    return machines.Trees(root / "akashic", root / "megapad", root / "lm1",
                          sources=sources or {"akashic": "a" * 40}, development=False)


def _own(data: Path, name: str, text: str = "[configuration]\n") -> Path:
    folder = data / "configurations" / name
    folder.mkdir(parents=True)
    (folder / machines.CONFIGURATION_FILE).write_text(text)
    return folder


def test_the_catalog_holds_the_shipped_desktop_and_the_users_own(tmp_path):
    _own(tmp_path, "mine")
    names = {machine.name: machine for machine in machines.catalog(tmp_path)}
    assert not names["desktop"].own
    assert names["desktop"].configuration == machines.SHIPPED / "desktop" / "configuration.toml"
    assert names["desktop"].folder == tmp_path / "configurations" / "desktop"
    assert names["mine"].own and names["mine"].folder == tmp_path / "configurations" / "mine"
    assert machines.find("mine", tmp_path) == names["mine"]
    with pytest.raises(machines.MachineError, match="desktop, mine"):
        machines.find("absent", tmp_path)


def test_list_says_whether_each_is_built(tmp_path, capsys):
    folder = tmp_path / "configurations" / "desktop"
    folder.mkdir(parents=True)
    assert command.main(["list", "--data-dir", str(tmp_path)]) == 0
    assert "desktop  (shipped, not built)" in capsys.readouterr().out
    (folder / machines.MANIFEST_NAME).write_text(json.dumps(MANIFEST))
    assert command.main(["list", "--data-dir", str(tmp_path)]) == 0
    assert "desktop  (shipped, built)  Desktop" in capsys.readouterr().out


def test_the_server_runs_the_volumes_the_manifest_names(tmp_path):
    machine = machines.Machine("desktop", tmp_path / "c.toml", tmp_path / "desktop", own=False)
    trees = _trees(tmp_path)
    socket_path = tmp_path / "run" / "desktop.sock"
    command_line = machines.server_command(machine, trees, MANIFEST, socket_path)
    assert command_line[1:4] == [str(tmp_path / "megapad" / "megapad.py"), "--mode", "simulator"]

    def option(name):
        return command_line[command_line.index(name) + 1]

    assert option("--storage") == str(machine.folder / "machine.img")
    assert option("--user-storage") == str(machine.folder / "machine-user.img")
    assert option("--socket") == str(socket_path)
    assert (option("--ext-mem-mib"), option("--cores")) == ("384", "1")
    assert (option("--cols"), option("--rows")) == ("160", "48")
    assert option("--rich-terminal-policy") == '{"a":1,"b":2}'
    assert option("--retained-terminal-policy") == '{"c":3}'
    assert option("--chiplet") == str(tmp_path / "lm1" / "chiplet" / "build" / "lm1_chiplet.so")
    assert "--nic" not in command_line and "--debug-access" not in command_line

    networked = dict(MANIFEST, network={"enabled": True, "local_access": True})
    command_line = machines.server_command(machine, trees, networked, socket_path,
                                           debug_access=True)
    assert command_line[command_line.index("--nic") + 1] == "slirp"
    assert "--local-access" in command_line and "--debug-access" in command_line

    viewer = machines.viewer_command(trees, MANIFEST, socket_path)
    assert viewer[viewer.index("--font-size") + 1] == "16"
    assert viewer[viewer.index("--title") + 1] == "Desktop"
    assert viewer[viewer.index("--font") + 1].endswith("assets/fonts/DejaVuSansMono.ttf")


def test_a_build_is_stale_when_what_it_was_built_from_changed(tmp_path, monkeypatch):
    folder = _own(tmp_path, "mine")
    machine = machines.find("mine", tmp_path)
    trees = _trees(tmp_path)
    said = {"sha256": "c", "documents_sha256": "d"}
    monkeypatch.setattr(machines, "check", lambda machine, source: dict(said))
    assert machines.stale(machine, trees) == "it has not been built"
    (folder / machines.MANIFEST_NAME).write_text(json.dumps(MANIFEST))
    assert machines.stale(machine, trees) == "a volume is missing"
    for name in MANIFEST["storage"].values():
        (folder / name).write_bytes(b"")
    assert machines.stale(machine, trees) is None
    assert machines.stale(machine, _trees(tmp_path, akashic="b" * 40)) == "a component changed"
    said["sha256"] = "changed"
    assert machines.stale(machine, trees) == "its configuration changed"
    said.update(sha256="c", documents_sha256="changed")
    assert machines.stale(machine, trees) == "its documents changed"


def test_new_copies_the_file_and_the_documents_beside_it(tmp_path, monkeypatch):
    folder = _own(tmp_path, "mine", "[configuration]\ntitle = \"Mine\"\n")
    (folder / "papers").mkdir()
    (folder / "papers" / "note.txt").write_text("a note\n")
    original = machines.find("mine", tmp_path)
    monkeypatch.setattr(machines, "check",
                        lambda machine, source: {"documents": str(folder / "papers")})
    copy = machines.new("copy", original, _trees(tmp_path), tmp_path)
    assert copy.own and copy.configuration.read_text() == original.configuration.read_text()
    assert (copy.folder / "papers" / "note.txt").read_text() == "a note\n"
    for path in (copy.folder, copy.folder / "papers"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o700
    for path in (copy.configuration, copy.folder / "papers" / "note.txt"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(machines.MachineError, match="already named 'copy'"):
        machines.new("copy", original, _trees(tmp_path), tmp_path)
    with pytest.raises(machines.MachineError, match="lowercase letters"):
        machines.new("My Copy", original, _trees(tmp_path), tmp_path)


def _repository(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / "file").write_text("one\n")
    subprocess.run(["git", "-C", str(path), "add", "file"], check=True)
    subprocess.run(["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "-m", "one"], check=True)
    return path


def test_development_mode_uses_the_checkouts_as_they_stand(tmp_path):
    workspace = tmp_path / "workspace"
    for name in ("akashic", "megapad", "lm1"):
        _repository(workspace / name)
    with pytest.raises(machines.MachineError, match="_megaforth_native.*_mp64_slirp.*chiplet"):
        machines.trees(workspace=workspace)
    for stem in ("_megaforth_native", "_mp64_slirp"):
        (workspace / "megapad" / f"{stem}.cpython-313-x86_64-linux-gnu.so").write_bytes(b"")
    machines.chiplet_module(workspace / "lm1").parent.mkdir(parents=True)
    machines.chiplet_module(workspace / "lm1").write_bytes(b"")
    trees = machines.trees(workspace=workspace)
    assert trees.development and trees.akashic == workspace / "akashic"
    before = trees.sources["akashic"]
    (workspace / "akashic" / "file").write_text("two\n")
    after = machines.trees(workspace=workspace).sources["akashic"]
    assert after["head"] == before["head"] and after["changes"] != before["changes"]
    (workspace / "akashic" / "new").write_text("new\n")
    assert machines.trees(workspace=workspace).sources["akashic"] != after


READER = workspace_root() / "akashic" / "toolchain" / "image" / "configuration.py"


@pytest.mark.skipif(not READER.is_file(),
                    reason="the workspace's Akashic has no configuration reader")
def test_a_build_in_development_mode_keeps_the_user_volume(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    try:
        trees = machines.trees(workspace=workspace_root())
    except machines.MachineError as error:
        pytest.skip(str(error))
    folder = _own(tmp_path, "pad", (
        "[configuration]\nformat = 1\ntitle = \"Desk with Pad\"\n"
        "[[practice.entry]]\napplet = \"pad\"\n[volumes.user]\nsize-mib = 16\n"
    ))
    machine = machines.find("pad", tmp_path)
    built = machines.build(machine, trees, log=lambda message: None)
    assert built["built_from"]["components"] == dict(trees.sources)
    assert machines.stale(machine, trees) is None
    user = folder / built["storage"]["user"]
    with user.open("r+b") as volume:
        volume.seek(-4, os.SEEK_END)
        volume.write(b"mine")
    configuration = folder / machines.CONFIGURATION_FILE
    configuration.write_text(configuration.read_text().replace("Desk with Pad", "Pad"))
    assert machines.stale(machine, trees) == "its configuration changed"
    assert machines.build(machine, trees, log=lambda message: None)["title"] == "Pad"
    assert user.read_bytes()[-4:] == b"mine"


def test_run_refuses_files_another_account_could_read(tmp_path, monkeypatch):
    folder = _own(tmp_path, "mine")
    machine = machines.find("mine", tmp_path)
    (folder / machines.MANIFEST_NAME).write_text(json.dumps(MANIFEST))
    for name in MANIFEST["storage"].values():
        (folder / name).write_bytes(b"")
    for path in (folder, *folder.iterdir()):
        path.chmod(0o700 if path.is_dir() else 0o600)
    assert machines.exposed(machine, MANIFEST) == []
    (folder / "machine-user.img").chmod(0o644)
    folder.chmod(0o755)
    found = machines.exposed(machine, MANIFEST)
    assert len(found) == 2
    assert any("machine-user.img is open to other accounts (mode 644" in line for line in found)

    def no_server(*args, **kwargs):
        raise AssertionError("an exposed machine starts no server")

    monkeypatch.setattr(machines, "stale", lambda machine, source: None)
    monkeypatch.setattr(machines.subprocess, "Popen", no_server)
    with pytest.raises(machines.MachineError, match="must be the user's alone"):
        machines.run(machine, _trees(tmp_path), data_dir=tmp_path)


def test_the_command_creates_files_for_the_user_alone(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setitem(command._COMMANDS, "list",
                        lambda args: seen.append(os.umask(0o077)) or 0)
    previous = os.umask(0o022)
    try:
        assert command.main(["list", "--data-dir", str(tmp_path)]) == 0
        assert seen == [0o077]
        assert os.umask(0o022) == 0o022
    finally:
        os.umask(previous)
