"""Self-bootstrapping of the SUMO python tools.

``traci`` (and ``sumolib``) ship with SUMO in ``%SUMO_HOME%\\tools``.  This
module puts that directory on ``sys.path`` automatically so the project works
without the user having to set ``PYTHONPATH`` first.

The bootstrap is *optional*: everything that is not needed to run SUMO (the
data pipeline, the map generator) works with a bare standard library
installation.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional

_CANDIDATE_HOMES = (
    r"C:\Program Files (x86)\Eclipse\Sumo",
    r"C:\Program Files\Eclipse\Sumo",
    r"C:\Program Files (x86)\Eclipse\SUMO",
    r"C:\Program Files\Eclipse\SUMO",
)


def sumo_home() -> Optional[Path]:
    """Best effort discovery of the SUMO installation directory."""
    env = os.environ.get("SUMO_HOME")
    if env:
        candidate = Path(env)
        if candidate.exists():
            return candidate

    for raw in _CANDIDATE_HOMES:
        candidate = Path(raw)
        if candidate.exists():
            return candidate

    executable = shutil.which("sumo")
    if executable:
        # <SUMO_HOME>/bin/sumo.exe
        return Path(executable).resolve().parent.parent
    return None


def sumo_tools_dir() -> Optional[Path]:
    home = sumo_home()
    if home is None:
        return None
    tools = home / "tools"
    return tools if tools.exists() else None


def ensure_sumo_tools(extra: Optional[List[str]] = None) -> Optional[Path]:
    """Make ``traci`` / ``sumolib`` importable, return the tools directory."""
    tools = sumo_tools_dir()
    if tools is None:
        return None
    path = str(tools)
    if path not in sys.path:
        sys.path.insert(0, path)
    for item in extra or []:
        if item not in sys.path:
            sys.path.insert(0, item)
    return tools


def import_traci():
    """Import :mod:`traci`, bootstrapping ``sys.path`` when required."""
    try:
        import traci  # type: ignore

        return traci
    except ImportError:
        ensure_sumo_tools()
        import traci  # type: ignore

        return traci
