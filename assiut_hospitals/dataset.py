"""The hospital dataset: hospitals + their snap onto the SUMO network."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .hospitals import Hospital
from .snapping import SnapResult


@dataclass
class HospitalRecord:
    """A hospital together with its position on the road network."""

    hospital: Hospital
    snap: SnapResult
    in_network: bool = False
    routable: bool = False
    #: what the generator did for this hospital (ambulance flows, hubs, ...)
    ambulance: Dict[str, Any] = field(default_factory=dict)

    @property
    def slug(self) -> str:
        return self.hospital.slug

    @property
    def display_name(self) -> str:
        return self.hospital.display_name

    def as_dict(self) -> Dict[str, Any]:
        data = self.hospital.as_dict()
        data.update(
            {
                "slug": self.slug,
                "in_network": self.in_network,
                "routable": self.routable,
                "snap": self.snap.as_dict(),
            }
        )
        return data


@dataclass
class Dataset:
    """The full generated dataset."""

    meta: Dict[str, Any] = field(default_factory=dict)
    hospitals: List[HospitalRecord] = field(default_factory=list)

    # ---------------------------------------------------------------- queries
    @property
    def routable(self) -> List[HospitalRecord]:
        return [r for r in self.hospitals if r.routable]

    @property
    def outside(self) -> List[HospitalRecord]:
        return [r for r in self.hospitals if not r.routable]

    def by_slug(self, slug: str) -> Optional[HospitalRecord]:
        for record in self.hospitals:
            if record.slug == slug:
                return record
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "meta": self.meta,
            "hospitals": [r.as_dict() for r in self.hospitals],
        }


def load_dataset(path: Optional[Path] = None) -> Dataset:
    """Load a previously generated dataset from ``data/hospitals.json``."""
    from .config import PROJECT_ROOT

    dataset_path = Path(path) if path else PROJECT_ROOT / "data" / "hospitals.json"
    with open(dataset_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    hospitals: List[HospitalRecord] = []
    for item in payload.get("hospitals", []):
        hospital = Hospital(
            osm_type=item.get("osm_type", "node"),
            osm_id=int(item.get("osm_id", 0)),
            name=item.get("name", ""),
            name_ar=item.get("name_ar", ""),
            name_en=item.get("name_en", ""),
            category=item.get("category", "other"),
            lat=float(item.get("lat", 0.0)),
            lon=float(item.get("lon", 0.0)),
            emergency=bool(item.get("emergency", False)),
        )
        snap_data = item.get("snap", {})
        snap = SnapResult(
            edge_id=snap_data.get("edge_id", ""),
            pos=float(snap_data.get("pos", 0.0)),
            distance_m=float(snap_data.get("distance_m", float("inf"))),
            x=float(snap_data.get("x", 0.0)),
            y=float(snap_data.get("y", 0.0)),
            edge_length=float(snap_data.get("edge_length", 0.0)),
            from_junction=snap_data.get("from_junction", ""),
            to_junction=snap_data.get("to_junction", ""),
            edge_type=snap_data.get("edge_type", ""),
            usable=bool(snap_data.get("usable", True)),
        )
        hospitals.append(
            HospitalRecord(
                hospital=hospital,
                snap=snap,
                in_network=bool(item.get("in_network", False)),
                routable=bool(item.get("routable", False)),
                ambulance=item.get("ambulance", {}) or {},
            )
        )

    return Dataset(meta=payload.get("meta", {}), hospitals=hospitals)
