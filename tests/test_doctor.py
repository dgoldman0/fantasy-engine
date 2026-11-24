"""fantasy-engine doctor: each requirement reported as found, missing with
what to do, or as advice, and a bare computer reported in full."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from fantasy_engine import command, components, doctor, machines

ALL_FEATURES = " ".join(("fpu", "sse2", *components.NATIVE_MARCH_FEATURES, "avx2"))


def _cpuinfo(tmp_path: Path, flags: str) -> Path:
    path = tmp_path / "cpuinfo"
    path.write_text(f"processor\t: 0\nflags\t\t: {flags}\n\nprocessor\t: 1\nflags\t\t: {flags}\n")
    return path


def _result(code: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], code, out, err)


def test_the_processor_needs_the_baselines_features(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(doctor.platform, "machine", lambda: "x86_64")
    assert doctor.computer(_cpuinfo(tmp_path, ALL_FEATURES)).state == doctor.OK
    lacking = doctor.computer(_cpuinfo(tmp_path, ALL_FEATURES.replace(" popcnt", "")))
    assert lacking.state == doctor.MISSING and "lacks popcnt" in lacking.detail
    monkeypatch.setattr(doctor.platform, "system", lambda: "Darwin")
    other = doctor.computer(_cpuinfo(tmp_path, ALL_FEATURES))
    assert other.state == doctor.MISSING and "WSL2" in other.remedy


def test_python_is_held_to_the_projects_version(monkeypatch, tmp_path):
    too_new = doctor.python({"requires-python": ">=3.99"})
    assert [finding.state for finding in too_new] == [doctor.MISSING]
    assert "needs 3.99 or later" in too_new[0].detail and "uv" in too_new[0].remedy
    found = doctor.python({"requires-python": ">=3.0"})
    assert [finding.requirement for finding in found] == ["Python", "Python's headers"]
    monkeypatch.setattr(doctor.sysconfig, "get_paths", lambda: {"include": str(tmp_path)})
    assert doctor.python({"requires-python": ">=3.0"})[1].state == doctor.MISSING


def test_each_package_the_project_names_is_checked():
    found = doctor.packages({"dependencies": [
        "pytest>=1", "no-such-package-for-fantasy-engine>=1", "pytest>=999"]})
    assert [finding.state for finding in found] == [doctor.OK, doctor.MISSING, doctor.MISSING]
    assert found[1].detail == "not installed for this Python"
    assert "needs 999 or later" in found[2].detail
    named = {finding.requirement for finding in doctor.packages()}
    assert {"pybind11", "setuptools", "pygame", "Pillow"} <= named


def _compiler(tmp_path: Path, name: str, status: int) -> Path:
    path = tmp_path / name
    path.write_text(f"#!/bin/sh\nif [ \"$1\" = --version ]; then echo '{name} 9.9'; exit 0; fi\n"
                    f"cat > /dev/null\necho 'no such option' >&2\nexit {status}\n")
    path.chmod(0o755)
    return path


def test_the_compiler_must_build_cxx17_for_the_baseline(tmp_path, monkeypatch):
    monkeypatch.setenv("CXX", str(_compiler(tmp_path, "good-c++", 0)))
    assert [finding.state for finding in doctor.compilers()] == [doctor.OK]
    monkeypatch.setenv("CXX", str(_compiler(tmp_path, "old-c++", 1)))
    (failed,) = doctor.compilers()
    assert failed.state == doctor.MISSING
    assert "cannot compile C++17 for x86-64-v2: no such option" in failed.detail
    monkeypatch.setenv("CXX", str(tmp_path / "absent-c++"))
    assert doctor.compilers()[0].remedy.endswith("sudo apt install build-essential).")


def test_libslirp_is_found_through_pkg_config(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/usr/bin/{name}")
    found = doctor.libslirp(run=lambda arguments, **options: _result(0, "4.7.0\n"))
    assert (found.state, found.detail) == (doctor.OK, "4.7.0")
    lacking = doctor.libslirp(run=lambda arguments, **options: _result(
        1, err="Package 'glib-2.0', required by 'slirp', not found\n"))
    assert lacking.state == doctor.MISSING and "glib-2.0" in lacking.detail
    assert "libglib2.0-dev" in lacking.remedy


def test_e2fsprogs_and_fonts_are_the_components_to_judge(tmp_path):
    trees = machines.Trees(tmp_path / "akashic", tmp_path / "megapad", tmp_path / "lm1",
                           sources={}, development=True)
    asked = []

    def image_tool(arguments, **options):
        asked.append((arguments[1:], options["cwd"], options["env"]["MEGAPAD_ROOT"]))
        return _result(0, json.dumps({"e2fsprogs": {"mke2fs": {
            "path": "/usr/sbin/mke2fs", "version": "mke2fs 1.47.0 (5-Feb-2023)\n\tUsing ..."}}}))

    found = doctor.e2fsprogs(trees, run=image_tool)
    assert found.state == doctor.OK and found.detail == "mke2fs 1.47.0 (5-Feb-2023) (/usr/sbin)"
    assert asked == [(["-m", "toolchain.image", "host"], trees.akashic, str(trees.megapad))]
    refused = doctor.e2fsprogs(trees, run=lambda arguments, **options: _result(
        1, err="error: /usr/sbin/mke2fs is not e2fsprogs 1.47.0 or later:\nmke2fs 1.46.5\n"))
    assert refused.state == doctor.MISSING
    assert refused.detail == "/usr/sbin/mke2fs is not e2fsprogs 1.47.0 or later:"

    lacking = doctor.fonts(trees, run=lambda arguments, **options: _result(
        0, json.dumps({"Noto Sans Hebrew": True, "Noto Color Emoji": False})))
    if doctor.shutil.which("fc-match"):
        assert lacking.state == doctor.ADVICE and "lacks Noto Color Emoji" in lacking.detail


def test_the_display_is_advice():
    assert doctor.display({"DISPLAY": ":1"}).state == doctor.OK
    assert doctor.display({"WAYLAND_DISPLAY": "wayland-0"}).detail == "WAYLAND_DISPLAY=wayland-0"
    assert doctor.display({}).state == doctor.ADVICE


def test_a_bare_computer_is_reported_in_full(tmp_path, monkeypatch, capsys):
    """No programs on the PATH and no desktop session: each tool is missing
    with what to do, the components cannot be read, and doctor fails."""

    monkeypatch.setenv("PATH", str(tmp_path / "nothing"))
    monkeypatch.delenv("CXX", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert command.main(["doctor", "--cache-dir", str(tmp_path / "cache")]) == 1
    lines = capsys.readouterr().out.splitlines()
    states = {line[9:].split(":", 1)[0]: line[:8].strip() for line in lines if line[:1] != " "}
    for requirement in ("git", "make", "libslirp", "the components",
                        "C++ compiler for LM1's chiplet module"):
        assert states[requirement] == "missing", requirement
    assert states["display"] == "advice"
    assert states["Python"] == "ok" and states["pygame"] == "ok"
    remedies = [line.strip() for line in lines if line.startswith(" ")]
    assert "Install it (on Ubuntu and Debian: sudo apt install git)." in remedies
    assert not (tmp_path / "cache").exists()


def test_the_report_fails_only_on_what_is_missing():
    lines = []
    findings = [doctor.Finding("git", doctor.OK, "2.43"),
                doctor.Finding("fonts", doctor.ADVICE, "few", "Install some.")]
    assert doctor.report(findings, lines.append) == 0
    assert lines == ["ok       git: 2.43", "advice   fonts: few", "         Install some."]
    findings.append(doctor.Finding("make", doctor.MISSING, "not found", "Install it."))
    assert doctor.report(findings, lines.append) == 1


@pytest.mark.skipif(sys.platform != "linux", reason="reads /proc/cpuinfo")
def test_this_computers_processor_is_read():
    assert doctor.computer().requirement == "this computer"
