"""Where this repository and the workspace around it sit.

The workspace is the folder that holds this repository beside MegaPad's,
Akashic's and LM1's checkouts.  FE_WORKSPACE names another one.
"""

from __future__ import annotations

import os
from pathlib import Path

FANTASY_ENGINE_ROOT = Path(__file__).resolve().parents[1]


def workspace_root() -> Path:
    configured = os.environ.get("FE_WORKSPACE")
    return Path(configured).resolve() if configured else FANTASY_ENGINE_ROOT.parent
