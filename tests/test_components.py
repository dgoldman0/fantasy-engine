"""The lock file, the assembly of components at their recorded commits, and
the native builds in the assembled trees (PLAN.md Part 1b)."""

import json
import os
import stat
import subprocess
import sysconfig
from pathlib import Path

import pytest

from fantasy_engine import command, components
from fantasy_engine.components import Component, ComponentError

GIT = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
       "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false"]


def git(cwd: Path, *arguments: str) -> str:
    return subprocess.run([*GIT, *arguments], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def repository(path: Path, files: dict[str, str], *, executable: tuple[str, ...] = ()) -> str:
    """A repository at PATH holding FILES in one commit, whose id it returns."""

    path.mkdir(parents=True)
    git(path, "init", "--quiet")
    for name, text in files.items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(text)
        if name in executable:
            (path / name).chmod(0o755)
    git(path, "add", "-A")
    git(path, "commit", "--quiet", "-m", "first")
    return git(path, "rev-parse", "HEAD")


def write_lock(path: Path, entries: dict[str, tuple[str, str]]) -> Path:
    path.write_text("".join(f'[{name}]\nrepository = "{url}"\ncommit = "{commit}"\n\n'
                            for name, (url, commit) in entries.items()))
    return path


COMMIT = "0123456789abcdef0123456789abcdef01234567"


# The lock file.

def test_this_repositorys_lock_file_names_every_component():
    loaded = components.load()
    assert [c.name for c in loaded] == ["megapad", "akashic", "lm1"]
    for component in loaded:
        assert len(component.commit) == 40
        assert component.repository.startswith("https://github.com/")


def table(name: str, **settings: str) -> str:
    settings = {"repository": "r", "commit": COMMIT, **settings}
    return f"[{name}]\n" + "".join(f'{key} = "{value}"\n' for key, value in settings.items()
                                   if value is not None)


AKASHIC_AND_LM1 = table("akashic") + table("lm1")


FAULTS = [
    ("missing", table("megapad") + table("akashic"), "lacks lm1"),
    ("unknown", table("megapad") + AKASHIC_AND_LM1 + "[chimera]\n",
     "no component called chimera"),
    ("setting", table("megapad", branch="main") + AKASHIC_AND_LM1,
     "megapad has no setting branch"),
    ("short", table("megapad", commit="0123abcd") + AKASHIC_AND_LM1, "40 lowercase"),
    ("upper", table("megapad", commit=COMMIT.upper()) + AKASHIC_AND_LM1, "40 lowercase"),
    ("unnamed", table("megapad", repository=None) + AKASHIC_AND_LM1, "needs its repository"),
    ("scalar", "megapad = 1\n" + AKASHIC_AND_LM1, "must be a table"),
    ("syntax", "[megapad\n", "not valid TOML"),
]


@pytest.mark.parametrize("text, complaint", [fault[1:] for fault in FAULTS],
                         ids=[fault[0] for fault in FAULTS])
def test_the_reader_names_what_is_wrong(tmp_path, text, complaint):
    lock = tmp_path / "components.toml"
    lock.write_text(text)
    with pytest.raises(ComponentError, match=complaint):
        components.load(lock)


def test_a_missing_lock_file_is_named(tmp_path):
    with pytest.raises(ComponentError, match="no lock file"):
        components.load(tmp_path / "components.toml")


# Assembly.

def test_assembly_takes_the_recorded_commit_whatever_the_checkout_holds(tmp_path):
    workspace = tmp_path / "workspace"
    checkout = workspace / "megapad"
    recorded = repository(checkout, {"x.txt": "recorded\n", "tool.sh": "#!/bin/sh\n"},
                          executable=("tool.sh",))
    # Switch to another branch with another commit, then leave the working
    # tree dirty and an untracked file beside it.
    git(checkout, "checkout", "--quiet", "-b", "other")
    (checkout / "x.txt").write_text("other\n")
    git(checkout, "commit", "--quiet", "-am", "second")
    (checkout / "x.txt").write_text("dirty\n")
    (checkout / "untracked.txt").write_text("stray\n")

    component = Component("megapad", "unused", recorded)
    tree = components.assemble(component, [component], cache=tmp_path / "cache",
                               workspace=workspace, log=lambda message: None)

    assert (tree / "x.txt").read_text() == "recorded\n"
    assert not (tree / "untracked.txt").exists()
    assert (tree / "tool.sh").stat().st_mode & stat.S_IXUSR
    stamp = json.loads((tree / components.ASSEMBLED_STAMP).read_text())
    assert stamp["commit"] == recorded
    assert stamp["tree"] == git(checkout, "rev-parse", f"{recorded}^{{tree}}")
    assert tree.name == f"megapad-{recorded}"


def test_assembly_fetches_a_commit_the_workspace_lacks(tmp_path):
    origin = tmp_path / "origin"
    recorded = repository(origin, {"x.txt": "recorded\n"})
    (origin / "x.txt").write_text("later\n")
    git(origin, "commit", "--quiet", "-am", "later")
    # Servers such as GitHub hand out any commit a branch reaches.
    git(origin, "config", "uploadpack.allowReachableSHA1InWant", "true")

    component = Component("megapad", f"file://{origin}", recorded)
    cache = tmp_path / "cache"
    tree = components.assemble(component, [component], cache=cache,
                               workspace=tmp_path / "empty-workspace",
                               log=lambda message: None)

    assert (tree / "x.txt").read_text() == "recorded\n"
    store = cache / "repositories" / "megapad.git"
    assert git(store, "rev-parse", "--is-shallow-repository") == "true"
    assert git(store, "rev-parse", f"refs/fantasy-engine/{recorded}") == recorded


def test_an_unknown_commit_is_reported(tmp_path):
    origin = tmp_path / "origin"
    repository(origin, {"x.txt": "x\n"})
    component = Component("megapad", f"file://{origin}", COMMIT)
    with pytest.raises(ComponentError, match="fetching megapad 01234567"):
        components.assemble(component, [component], cache=tmp_path / "cache",
                            workspace=None, log=lambda message: None)


def test_a_complete_tree_is_reused_and_an_incomplete_one_replaced(tmp_path):
    workspace = tmp_path / "workspace"
    recorded = repository(workspace / "akashic", {"x.txt": "recorded\n"})
    component = Component("akashic", "unused", recorded)
    cache = tmp_path / "cache"
    messages = []

    tree = components.assemble(component, [component], cache=cache, workspace=workspace,
                               log=messages.append)
    (tree / "kept.txt").write_text("a build's output\n")
    again = components.assemble(component, [component], cache=cache, workspace=workspace,
                                log=messages.append)
    assert again == tree and (tree / "kept.txt").exists()
    assert len(messages) == 1

    # A tree without its record, and what an interrupted assembly left.
    (tree / components.ASSEMBLED_STAMP).unlink()
    leftover = tree.parent / f".{tree.name}.abcd.tmp"
    leftover.mkdir()
    components.assemble(component, [component], cache=cache, workspace=workspace,
                        log=messages.append)
    assert not (tree / "kept.txt").exists()
    assert (tree / components.ASSEMBLED_STAMP).exists()
    assert not leftover.exists()


def test_git_reads_no_users_settings(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    recorded = repository(workspace / "akashic", {"x.txt": "a\nb\n"})
    settings = tmp_path / "gitconfig"
    settings.write_text("[core]\n\tautocrlf = true\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(settings))
    component = Component("akashic", "unused", recorded)
    tree = components.assemble(component, [component], cache=tmp_path / "cache",
                               workspace=workspace, log=lambda message: None)
    assert (tree / "x.txt").read_bytes() == b"a\nb\n"


def test_lm1s_tree_follows_the_megapad_it_compiles_against():
    lm1 = Component("lm1", "r", "1" * 40)
    first = [Component("megapad", "r", "a" * 40), lm1]
    second = [Component("megapad", "r", "b" * 40), lm1]
    assert components.tree_name(lm1, first) == f"lm1-{'1' * 40}-megapad-{'a' * 40}"
    assert components.tree_name(lm1, first) != components.tree_name(lm1, second)


# The warning about commits that are not pushed.

def test_a_commit_no_remote_branch_holds_is_reported(tmp_path):
    workspace = tmp_path / "workspace"
    recorded = repository(workspace / "megapad", {"x.txt": "x\n"})
    component = Component("megapad", "unused", recorded)
    message = components.unpushed(component, workspace)
    assert message is not None and recorded[:8] in message

    git(workspace / "megapad", "update-ref", "refs/remotes/origin/main", recorded)
    assert components.unpushed(component, workspace) is None
    # A checkout without the commit, or no checkout, leaves the fetch to decide.
    assert components.unpushed(Component("megapad", "unused", COMMIT), workspace) is None
    assert components.unpushed(Component("lm1", "unused", recorded), workspace) is None


# Privacy.

def test_folders_are_private_whatever_the_umask(tmp_path):
    workspace = tmp_path / "workspace"
    recorded = repository(workspace / "akashic", {"x.txt": "x\n"})
    cache = tmp_path / "cache"
    cache.mkdir(mode=0o755)
    os.chmod(cache, 0o755)
    previous = os.umask(0o022)
    try:
        component = Component("akashic", "unused", recorded)
        tree = components.assemble(component, [component],
                                   cache=components.private_folder(cache),
                                   workspace=workspace, log=lambda message: None)
    finally:
        os.umask(previous)
    for folder in (cache, cache / "components", tree):
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700, folder


def test_a_folder_another_account_owns_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(components.os, "getuid", lambda: os.stat(tmp_path).st_uid + 1)
    with pytest.raises(ComponentError, match="another account"):
        components.private_folder(tmp_path / "cache")


# The command, over components whose builds only record what they were given.

def fake_components(workspace: Path, *, megapad_build: str) -> dict[str, tuple[str, str]]:
    megapad = repository(workspace / "megapad", {"Makefile": megapad_build})
    akashic = repository(workspace / "akashic", {"README.md": "Akashic\n"})
    lm1 = repository(workspace / "lm1", {"chiplet/Makefile": (
        "all:\n\tmkdir -p build && echo $(MEGAPAD_ROOT) > build/megapad-root\n")})
    return {"megapad": ("unused", megapad), "akashic": ("unused", akashic),
            "lm1": ("unused", lm1)}


MEGAPAD_BUILD = ("build:\n\t$(VENV_PY) -c \"import sysconfig; "
                 "open('built-for', 'w').write(sysconfig.get_config_var('SOABI'))\"\n")


def test_build_assembles_every_component_and_builds_each_once(tmp_path, monkeypatch, capsys):
    workspace = tmp_path / "workspace"
    lock = write_lock(tmp_path / "components.toml",
                      fake_components(workspace, megapad_build=MEGAPAD_BUILD))
    monkeypatch.setenv("FE_WORKSPACE", str(workspace))
    monkeypatch.setattr(components, "_require_pybind11", lambda python: None)
    cache = tmp_path / "cache"

    assert command.main(["prepare", "--components", str(lock), "--cache-dir", str(cache)]) == 0
    output = capsys.readouterr()
    assert "warning: megapad's recorded commit" in output.err
    trees = dict(line.split(": ", 1) for line in output.out.splitlines() if ": /" in line)
    megapad, lm1 = Path(trees["megapad"]), Path(trees["lm1"])
    abi = sysconfig.get_config_var("SOABI")
    assert (megapad / "built-for").read_text() == abi
    assert (megapad / f".fantasy-engine-native.{abi}.json").exists()
    assert (lm1 / "chiplet" / "build" / "megapad-root").read_text().strip() == str(megapad)

    # A second build finds everything done.
    (megapad / "built-for").unlink()
    assert command.main(["prepare", "--components", str(lock), "--cache-dir", str(cache)]) == 0
    assert not (megapad / "built-for").exists()


def test_a_failed_build_is_reported_and_left_unrecorded(tmp_path, monkeypatch, capsys):
    workspace = tmp_path / "workspace"
    lock = write_lock(tmp_path / "components.toml",
                      fake_components(workspace, megapad_build="build:\n\texit 3\n"))
    monkeypatch.setenv("FE_WORKSPACE", str(workspace))
    monkeypatch.setattr(components, "_require_pybind11", lambda python: None)
    cache = tmp_path / "cache"

    assert command.main(["prepare", "--components", str(lock), "--cache-dir", str(cache)]) == 1
    assert "building MegaPad's native extensions" in capsys.readouterr().err
    assert not list(cache.glob("components/megapad-*/.fantasy-engine-native.*"))


def test_the_command_reports_a_missing_lock_file(tmp_path, capsys):
    assert command.main(["prepare", "--components", str(tmp_path / "none.toml"),
                         "--cache-dir", str(tmp_path / "cache")]) == 1
    assert "fantasy-engine: there is no lock file" in capsys.readouterr().err
