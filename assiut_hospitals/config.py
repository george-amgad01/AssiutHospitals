"""Configuration loading and path resolution.

The project reads the SUMO network / route files from an *external* location
(default: the dashboard project) instead of copying them, so the same dataset
can later be dropped into any other simulation without duplicating data.

Everything the project writes goes into the project directory itself
(`data/`, `sumo/`, `web/`).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_CONFIG_NAME = "config.json"


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


@dataclass
class Config:
    """Resolved configuration for the project."""

    root: Path
    raw: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ paths
    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def sumo_dir(self) -> Path:
        return self.root / "sumo"

    @property
    def web_dir(self) -> Path:
        return self.root / "web"

    @property
    def cache_file(self) -> Path:
        return self.resolve_path(self.raw["overpass"]["cache_file"])

    @property
    def dataset_file(self) -> Path:
        return self.data_dir / "hospitals.json"

    @property
    def poi_file(self) -> Path:
        return self.sumo_dir / "hospitals.poi.xml"

    @property
    def hospital_routes_file(self) -> Path:
        return self.sumo_dir / "hospitals.rou.xml"

    @property
    def sumocfg_file(self) -> Path:
        return self.sumo_dir / "hospitals.sumocfg"

    @property
    def network_js(self) -> Path:
        return self.web_dir / "network.js"

    @property
    def hospitals_js(self) -> Path:
        return self.web_dir / "hospitals.js"

    # -------------------------------------------------------------- sections
    @property
    def network(self) -> Dict[str, Any]:
        return self.raw.get("network", {})

    @property
    def projection(self) -> Dict[str, Any]:
        return self.raw.get("projection", {})

    @property
    def overpass(self) -> Dict[str, Any]:
        return self.raw.get("overpass", {})

    @property
    def snapping(self) -> Dict[str, Any]:
        return self.raw.get("snapping", {})

    @property
    def ambulances(self) -> Dict[str, Any]:
        return self.raw.get("ambulances", {})

    @property
    def server(self) -> Dict[str, Any]:
        return self.raw.get("server", {})

    # ---------------------------------------------------------- source files
    @property
    def net_file(self) -> Path:
        return Path(self.resolve_path(self.network["net_file"]))

    @property
    def route_file(self) -> Optional[Path]:
        value = self.network.get("route_file")
        return Path(self.resolve_path(value)) if value else None

    @property
    def additional_file(self) -> Optional[Path]:
        value = self.network.get("additional_file")
        return Path(self.resolve_path(value)) if value else None

    # --------------------------------------------------------------- helpers
    def resolve_path(self, value: str) -> str:
        """Resolve a possibly relative path against the project root."""
        if not value:
            return value
        p = Path(value)
        if p.is_absolute():
            return str(p)
        return str((self.root / p).resolve())

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.sumo_dir, self.web_dir):
            d.mkdir(parents=True, exist_ok=True)

    def dump(self) -> None:
        """Write the (possibly modified) configuration back to disk."""
        path = self.root / DEFAULT_CONFIG_NAME
        path.write_text(
            json.dumps(self.raw, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def load_config(path: Optional[str] = None, root: Optional[str] = None) -> Config:
    """Load `config.json`.

    Parameters
    ----------
    path:
        Explicit path to a config file.  Relative paths are resolved against
        the project root.
    root:
        Project root (defaults to the directory containing this package).
    """
    base = Path(root).resolve() if root else PROJECT_ROOT
    cfg_path = Path(path) if path else base / DEFAULT_CONFIG_NAME
    if not cfg_path.is_absolute():
        cfg_path = base / cfg_path
    raw = _read_json(cfg_path)
    return Config(root=base, raw=raw)


def default_origin_junctions(config: Config) -> List[str]:
    """Origin junctions used for the outbound (hospital -> city) ambulance flow."""
    return list(config.ambulances.get("origin_junctions", []))
