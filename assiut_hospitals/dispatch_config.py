"""Manual dispatch configuration: four zones and their hospital lists.

إعدادات الإرسال اليدوية: أربع مناطق وحدودها وقوائم المستشفيات داخلها.

Requirement 2 forbids any automatic zone assignment.  Everything in this
module is read verbatim from ``config/dispatch.json``; the loader only
*validates* that the file is internally consistent and reports any
mismatch.  It never derives a hospital-to-zone assignment on its own.

لا يتم تعيين أي مستشفى لمنطقة تلقائياً؛ كل شيء يُقرأ من ملف الإعدادات
ويُتحقق منه فقط.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .config import PROJECT_ROOT
from .dataset import Dataset

DEFAULT_DISPATCH_CONFIG = Path("config") / "dispatch.json"


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Zone:
    """One manually defined rectangular zone.

    المنطقة تُعرَّف بمستطيل جغرافي (خط عرض/طول) وقائمة صريحة بأسماء المستشفيات.
    """

    id: str
    name: str
    south: float
    west: float
    north: float
    east: float
    hospitals: Tuple[str, ...] = ()

    def contains(self, lat: float, lon: float) -> bool:
        """Is the coordinate inside this zone rectangle? (inclusive)

        هل تقع النقطة داخل حدود المنطقة؟
        """
        return self.south <= lat <= self.north and self.west <= lon <= self.east

    def distance_to_point_m(self, lat: float, lon: float) -> float:
        """Distance from a point to the rectangle, in metres (0 when inside).

        المسافة بالمتر من النقطة إلى حدود المنطقة (صفر إذا كانت بالداخل).
        """
        dlat = 0.0
        dlon = 0.0
        if lat < self.south:
            dlat = self.south - lat
        elif lat > self.north:
            dlat = lat - self.north
        if lon < self.west:
            dlon = self.west - lon
        elif lon > self.east:
            dlon = lon - self.east
        if dlat == 0.0 and dlon == 0.0:
            return 0.0
        lat_m = dlat * 111_320.0
        lon_m = dlon * 111_320.0 * math.cos(math.radians(lat))
        return math.hypot(lat_m, lon_m)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "boundary": {
                "south": self.south,
                "west": self.west,
                "north": self.north,
                "east": self.east,
            },
            "hospitals": list(self.hospitals),
        }


@dataclass
class DispatchConfig:
    """The parsed ``config/dispatch.json``."""

    path: Path
    raw: Dict[str, Any] = field(default_factory=dict)
    zones: List[Zone] = field(default_factory=list)
    zone_source: str = "UNSET"
    vehicle_class: str = "emergency"
    specialty_catalog: List[str] = field(default_factory=list)
    capacity_file: Path = Path("data/emergency_capacity.json")
    clinics_as_emergency: bool = True
    max_origin_snap_m: float = 400.0
    refuse_dead_end_starts: bool = True
    search_scope: str = "start_zone_only"
    excluded_destinations: Dict[str, str] = field(default_factory=dict)
    comparison_algorithms: List[str] = field(default_factory=list)
    owner_decisions: Dict[str, str] = field(default_factory=dict)
    cost: Dict[str, Any] = field(default_factory=dict)
    require_exactly_four_zones: bool = True
    assignment_tolerance_m: float = 25.0

    # ------------------------------------------------------------------ lookup
    def zone_of(self, slug: str) -> Optional[Zone]:
        """Return the zone that explicitly lists ``slug`` (or ``None``).

        المنطقة التي تحتوي المستشفى حسب القائمة اليدوية.
        """
        for zone in self.zones:
            if slug in zone.hospitals:
                return zone
        return None

    def zone_by_id(self, zone_id: str) -> Optional[Zone]:
        for zone in self.zones:
            if zone.id == zone_id:
                return zone
        return None

    def zones_for_point(self, lat: float, lon: float) -> List[Zone]:
        """All zone rectangles that contain a coordinate (usually one).

        كل المناطق التي تحتوي النقطة؛ عادةً منطقة واحدة، وتُعاد القائمة
        كاملة إذا وقعت النقطة على حدّ مشترك حتى لا نختار تلقائياً.
        """
        return [zone for zone in self.zones if zone.contains(lat, lon)]

    def excluded_reason(self, slug: str) -> Optional[str]:
        """Owner-approved reason for removing a destination (or ``None``).

        سبب استبعاد المستشفى من وجهات الإرسال حسب قرار المالك.
        """
        return self.excluded_destinations.get(slug)

    # -------------------------------------------------------------- validation
    def validate(self, dataset: Dataset) -> List[str]:
        """Return a list of configuration errors (empty means valid).

        يتحقق من: العدد أربعة، الحدود صحيحة، كل مستشفى داخل الشبكة معيَّن
        مرة واحدة فقط، والتعيين يطابق الحدود الجغرافية.

        Consistency is checked, not repaired: a hospital that lies inside a
        zone rectangle but is listed in another zone is reported as an error.
        """
        errors: List[str] = []
        known = {record.slug: record for record in dataset.hospitals}

        if self.require_exactly_four_zones and len(self.zones) != 4:
            errors.append(
                "expected exactly 4 zones, found {0}".format(len(self.zones))
            )

        if self.search_scope not in ("start_zone_only", "all_zones"):
            errors.append(
                "unknown search_scope '{0}' (use start_zone_only or all_zones)".format(
                    self.search_scope
                )
            )

        # The comparison code implements exactly these seven methods.  Reject a
        # configuration that asks for another list instead of silently ignoring
        # it.  لا تقارن الخوارزميات إلا القائمة التي نفذها الكود فعلاً.
        expected_algorithms = [
            "dijkstra",
            "astar",
            "bellman_ford",
            "vam",
            "least_cost",
            "northwest_corner",
            "modi",
        ]
        if sorted(self.comparison_algorithms) != sorted(expected_algorithms):
            errors.append(
                "comparison_algorithms must contain exactly: {0}".format(
                    ", ".join(expected_algorithms)
                )
            )

        if str((self.cost or {}).get("mode", "")) != "free_flow":
            errors.append("cost.mode must be 'free_flow' (owner decision)")
        congestion = (self.cost or {}).get("congestion") or {}
        if bool(congestion.get("enabled", False)):
            errors.append("cost.congestion.enabled must stay false (owner decision)")

        for slug, reason in self.excluded_destinations.items():
            if slug not in known:
                errors.append(
                    "excluded destination references unknown hospital slug '{0}'".format(
                        slug
                    )
                )
            if not reason:
                errors.append(
                    "excluded destination '{0}' has no reason".format(slug)
                )

        seen_ids = set()
        assigned: Dict[str, str] = {}
        for zone in self.zones:
            if zone.id in seen_ids:
                errors.append("duplicate zone id: {0}".format(zone.id))
            seen_ids.add(zone.id)
            if not (zone.south < zone.north and zone.west < zone.east):
                errors.append(
                    "zone {0}: invalid boundary south={1} west={2} north={3} east={4}".format(
                        zone.id, zone.south, zone.west, zone.north, zone.east
                    )
                )
            if not zone.hospitals:
                errors.append("zone {0}: hospital list is empty".format(zone.id))
            for slug in zone.hospitals:
                if slug not in known:
                    errors.append(
                        "zone {0}: unknown hospital slug '{1}'".format(zone.id, slug)
                    )
                    continue
                if slug in assigned:
                    errors.append(
                        "hospital '{0}' is listed in both {1} and {2}".format(
                            slug, assigned[slug], zone.id
                        )
                    )
                assigned[slug] = zone.id

                record = known[slug]
                distance = zone.distance_to_point_m(
                    record.hospital.lat, record.hospital.lon
                )
                if distance > self.assignment_tolerance_m:
                    errors.append(
                        "hospital '{0}' is listed in {1} but lies {2:.0f} m outside "
                        "its boundary".format(slug, zone.id, distance)
                    )

        # every hospital that is inside the network must be assigned
        for record in dataset.hospitals:
            if record.in_network and record.slug not in assigned:
                errors.append(
                    "hospital '{0}' is inside the network but is not assigned to a zone".format(
                        record.slug
                    )
                )

        # a hospital inside a zone rectangle must not be assigned elsewhere
        for record in dataset.hospitals:
            if not record.in_network or record.slug not in assigned:
                continue
            for zone in self.zones:
                if not zone.contains(record.hospital.lat, record.hospital.lon):
                    continue
                if assigned[record.slug] != zone.id:
                    errors.append(
                        "hospital '{0}' lies inside {1} but is assigned to {2}".format(
                            record.slug, zone.id, assigned[record.slug]
                        )
                    )
        return errors

    def hospitals_of(self, zone: Zone, dataset: Dataset) -> List:
        """Dataset records explicitly listed in ``zone`` (order preserved).

        سجلات المستشفيات المذكورة صراحةً في المنطقة.
        """
        wanted = set(zone.hospitals)
        return [record for record in dataset.hospitals if record.slug in wanted]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "zone_source": self.zone_source,
            "vehicle_class": self.vehicle_class,
            "specialty_catalog": list(self.specialty_catalog),
            "capacity_file": str(self.capacity_file),
            "clinics_as_emergency": self.clinics_as_emergency,
            "max_origin_snap_m": self.max_origin_snap_m,
            "refuse_dead_end_starts": self.refuse_dead_end_starts,
            "search_scope": self.search_scope,
            "excluded_destinations": dict(self.excluded_destinations),
            "comparison_algorithms": list(self.comparison_algorithms),
            "owner_decisions": dict(self.owner_decisions),
            "cost": dict(self.cost),
            "zones": [zone.as_dict() for zone in self.zones],
        }


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _zone_from_dict(item: Dict[str, Any]) -> Zone:
    boundary = item.get("boundary") or {}
    hospitals = item.get("hospitals") or []
    return Zone(
        id=str(item.get("id", "")).strip(),
        name=str(item.get("name", item.get("id", ""))).strip(),
        south=float(boundary.get("south", 0.0)),
        west=float(boundary.get("west", 0.0)),
        north=float(boundary.get("north", 0.0)),
        east=float(boundary.get("east", 0.0)),
        hospitals=tuple(str(slug) for slug in hospitals),
    )


def load_dispatch_config(
    path: Optional[Path] = None, root: Optional[Path] = None
) -> DispatchConfig:
    """Read ``config/dispatch.json``.

    يقرأ ملف الإعدادات اليدوي دون أي اشتقاق تلقائي للحدود أو التعيين.
    """
    base = Path(root).resolve() if root else PROJECT_ROOT
    cfg_path = Path(path) if path else base / DEFAULT_DISPATCH_CONFIG
    if not cfg_path.is_absolute():
        cfg_path = base / cfg_path
    with open(cfg_path, "r", encoding="utf-8-sig") as fh:
        raw = json.load(fh)

    capacity_value = raw.get("capacity_file", "data/emergency_capacity.json")
    capacity_path = Path(capacity_value)
    if not capacity_path.is_absolute():
        capacity_path = (base / capacity_path).resolve()

    origin = raw.get("origin") or {}
    excluded = raw.get("excluded_destinations") or {}
    if isinstance(excluded, list):
        excluded_map = {
            str(item.get("slug", "")): str(item.get("reason", ""))
            for item in excluded
            if isinstance(item, dict)
        }
    else:
        excluded_map = {str(k): str(v) for k, v in dict(excluded).items()}
    return DispatchConfig(
        path=cfg_path,
        raw=raw,
        zones=[_zone_from_dict(item) for item in (raw.get("zones") or [])],
        zone_source=str(raw.get("zone_source", "UNSET")),
        vehicle_class=str(raw.get("vehicle_class", "emergency")),
        specialty_catalog=[str(s) for s in (raw.get("specialty_catalog") or [])],
        capacity_file=capacity_path,
        clinics_as_emergency=bool(raw.get("clinics_as_emergency", True)),
        max_origin_snap_m=float(origin.get("max_snap_distance_m", 400.0)),
        refuse_dead_end_starts=bool(origin.get("refuse_dead_end_starts", True)),
        search_scope=str(raw.get("search_scope", "start_zone_only")),
        excluded_destinations=excluded_map,
        comparison_algorithms=[
            str(item) for item in (raw.get("comparison_algorithms") or [])
        ],
        owner_decisions=dict(raw.get("owner_decisions") or {}),
        cost=dict(raw.get("cost") or {}),
        require_exactly_four_zones=bool(raw.get("require_exactly_four_zones", True)),
        assignment_tolerance_m=float(raw.get("assignment_tolerance_m", 25.0)),
    )
