"""The configurations this repository ships read cleanly with the image
tool of the workspace's Akashic (python3 -m toolchain.image check)."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from fantasy_engine.workspace import FANTASY_ENGINE_ROOT, workspace_root

CONFIGURATIONS = sorted(
    (FANTASY_ENGINE_ROOT / "configurations").glob("*/configuration.toml")
)


def test_the_desktop_ships():
    assert FANTASY_ENGINE_ROOT / "configurations" / "desktop" / "configuration.toml" in CONFIGURATIONS


@pytest.mark.parametrize("path", CONFIGURATIONS, ids=lambda path: path.parent.name)
def test_a_shipped_configuration_reads(path):
    akashic = workspace_root() / "akashic"
    if not (akashic / "toolchain" / "image" / "configuration.py").is_file():
        pytest.skip("the workspace's Akashic has no configuration reader")
    result = subprocess.run(
        [sys.executable, "-m", "toolchain.image", "check", str(path)],
        cwd=akashic,
        env=dict(os.environ, MEGAPAD_ROOT=str(workspace_root() / "megapad")),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["title"]
