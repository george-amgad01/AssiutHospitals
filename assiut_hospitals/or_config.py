"""Configuration and synthetic test data for the Operations Research extension.

إعدادات وبيانات اختبارية لامتداد بحوث العمليات.

The OR layer deliberately separates *rules* (``config/or_planning.json``) from
*test quantities* (``data/or_test_data.json``).  OSM and SUMO do not publish
hospital kit stock, zone demand, patient-transfer demand, background lane flow,
or measured lane capacity, so every such quantity is labelled ``SYNTHETIC`` and
must be replaced by owner data without changing code.

طبقة بحوث العمليات تفصل القواعد عن الكميات الاختبارية؛ كل كمية غير منشورة
موسومة بأنها وصفية وقابلة للاستبدال.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .config import PROJECT_ROOT


class ORConfigError(ValueError):
    """Invalid OR configuration or test-data file.

    خطأ في إعدادات بحوث العمليات أو ملف البيانات الاختبارية.
    """


DEFAULT_OR_CONFIG = Path("config") / "or_planning.json"
DEFAULT_OR_DATA = Path("data") / "or_test_data.json"


# ---------------------------------------------------------------------------
# Road capacity estimate
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ORRoadCapacity:
    """Estimated lane capacity in vehicles per planning interval.

    تقدير سعة المسار بعدد المركبات في فترة التخطيط (ليس قياساً ميدانياً).

    The estimate is a documented fallback used only because the repository has
    no measured lane capacity.  It depends on lane count and road type, never on
    street length alone.
    """

    source: str
    notice: str
    planning_interval_hours: float
    default_vehicles_per_lane_hour: float
    minimum_vehicles_per_lane: float
    reserve_fraction: float
    vehicles_per_lane_hour_by_type: Dict[str, float] = field(default_factory=dict)

    def rate_for_type(self, edge_type: str) -> float:
        """Vehicles per lane per hour for an OSM/SUMO road type.

        عدد المركبات لكل مسار في الساعة لنوع الشارع.
        """
        return float(
            self.vehicles_per_lane_hour_by_type.get(
                edge_type, self.default_vehicles_per_lane_hour
            )
        )

    def capacity_for_lane(self, edge_type: str) -> float:
        """Estimated capacity of one lane over the planning interval.

        السعة التقديرية لمسار واحد خلال فترة التخطيط.
        """
        rate = self.rate_for_type(edge_type)
        if rate <= 0.0:
            return 0.0
        capacity = rate * self.planning_interval_hours * (1.0 - self.reserve_fraction)
        return max(self.minimum_vehicles_per_lane, capacity)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "notice": self.notice,
            "planning_interval_hours": self.planning_interval_hours,
            "default_vehicles_per_lane_hour": self.default_vehicles_per_lane_hour,
            "minimum_vehicles_per_lane": self.minimum_vehicles_per_lane,
            "reserve_fraction": self.reserve_fraction,
            "vehicles_per_lane_hour_by_type": dict(self.vehicles_per_lane_hour_by_type),
        }


# ---------------------------------------------------------------------------
# Main configuration
# ---------------------------------------------------------------------------
@dataclass
class ORPlanningConfig:
    """Resolved OR planning rules and file locations.

    قواعد التخطيط ومواقع الملفات بعد تحويل المسارات إلى مسارات مطلقة.
    """

    path: Path
    root: Path
    raw: Dict[str, Any]
    data_path: Path
    dispatch_config_path: Path
    vehicle_class: str = "emergency"
    fleet_size: int = 48
    kits_per_trip: int = 10
    ambulance_trips_per_day: int = 1
    shift_hours: float = 12.0
    planning_horizon_hours: float = 24.0
    max_point_snap_m: float = 500.0
    max_routable_snap_m: float = 400.0
    require_hospital_count: int = 25
    require_exactly_four_zones: bool = True
    explicit_prohibited_lanes: tuple[str, ...] = ()
    road_capacity: ORRoadCapacity = field(
        default_factory=lambda: ORRoadCapacity(
            source="UNSET",
            notice="",
            planning_interval_hours=24.0,
            default_vehicles_per_lane_hour=800.0,
            minimum_vehicles_per_lane=10.0,
            reserve_fraction=0.0,
        )
    )
    mip_unmet_penalty: float = 1.0e9
    mip_fleet_tiebreak: float = 1.0e-6
    mip_time_limit_seconds: float = 120.0
    mip_relative_gap: float = 0.0
    output_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "reports")

    def resolve(self, value: str) -> Path:
        """Resolve a possibly relative path against the project root."""
        path = Path(value)
        if path.is_absolute():
            return path
        return (self.root / path).resolve()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "config_file": str(self.path),
            "data_file": str(self.data_path),
            "dispatch_config": str(self.dispatch_config_path),
            "vehicle_class": self.vehicle_class,
            "fleet_size": self.fleet_size,
            "kits_per_trip": self.kits_per_trip,
            "ambulance_trips_per_day": self.ambulance_trips_per_day,
            "shift_hours": self.shift_hours,
            "planning_horizon_hours": self.planning_horizon_hours,
            "max_point_snap_m": self.max_point_snap_m,
            "max_routable_snap_m": self.max_routable_snap_m,
            "require_hospital_count": self.require_hospital_count,
            "require_exactly_four_zones": self.require_exactly_four_zones,
            "explicit_prohibited_lanes": list(self.explicit_prohibited_lanes),
            "road_capacity": self.road_capacity.as_dict(),
            "mip": {
                "unmet_penalty_per_unit": self.mip_unmet_penalty,
                "fleet_tiebreak_per_vehicle": self.mip_fleet_tiebreak,
                "time_limit_seconds": self.mip_time_limit_seconds,
                "relative_gap": self.mip_relative_gap,
            },
            "output_dir": str(self.output_dir),
        }


# ---------------------------------------------------------------------------
# Synthetic quantities
# ---------------------------------------------------------------------------
@dataclass
class ORTestData:
    """Synthetic supplies, demands, anchors, and background flow.

    الكميات الاختبارية: التوريد والطلب ونقاط ارتكاز المناطق والتدفق الخلفي.
    """

    path: Path
    source: str
    notice: str
    units: Dict[str, str]
    zone_anchors: Dict[str, str]
    kit_supply_by_hospital: Dict[str, int]
    zone_demand_kits: Dict[str, int]
    zone_demand_patients: Dict[str, int]
    background_lane_flow: Dict[str, float]
    background_note: str = ""
    synthetic_choices: tuple[str, ...] = ()

    @property
    def synthetic(self) -> bool:
        return self.source.upper().startswith("SYNTHETIC")

    def total_kit_supply(self) -> int:
        return sum(self.kit_supply_by_hospital.values())

    def total_kit_demand(self) -> int:
        return sum(self.zone_demand_kits.values())

    def total_patient_demand(self) -> int:
        return sum(self.zone_demand_patients.values())

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "synthetic": self.synthetic,
            "notice": self.notice,
            "units": dict(self.units),
            "zone_anchors": dict(self.zone_anchors),
            "kit_supply_by_hospital": dict(self.kit_supply_by_hospital),
            "zone_demand_kits": dict(self.zone_demand_kits),
            "zone_demand_patients": dict(self.zone_demand_patients),
            "background_lane_flow": dict(self.background_lane_flow),
            "background_note": self.background_note,
            "synthetic_choices": list(self.synthetic_choices),
            "totals": {
                "kit_supply": self.total_kit_supply(),
                "kit_demand": self.total_kit_demand(),
                "patient_demand": self.total_patient_demand(),
            },
        }


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def _read_json(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            raw = json.load(fh)
    except FileNotFoundError as exc:
        raise ORConfigError("file not found: {0}".format(path)) from exc
    except json.JSONDecodeError as exc:
        raise ORConfigError("invalid JSON in {0}: {1}".format(path, exc)) from exc
    if not isinstance(raw, dict):
        raise ORConfigError("{0}: top-level JSON value must be an object".format(path))
    return raw


def _as_float(raw: Mapping[str, Any], key: str, default: float) -> float:
    try:
        return float(raw.get(key, default))
    except (TypeError, ValueError) as exc:
        raise ORConfigError("'{0}' must be a number".format(key)) from exc


def _as_int(raw: Mapping[str, Any], key: str, default: int) -> int:
    try:
        return int(raw.get(key, default))
    except (TypeError, ValueError) as exc:
        raise ORConfigError("'{0}' must be an integer".format(key)) from exc


def load_or_config(
    path: Optional[str | Path] = None, root: Optional[str | Path] = None
) -> ORPlanningConfig:
    """Read ``config/or_planning.json``.

    يقرأ قواعد التخطيط ويتحقق من الأنواع الأساسية دون اشتقاق أي بيانات.
    """
    base = Path(root).resolve() if root else PROJECT_ROOT
    cfg_path = Path(path) if path else base / DEFAULT_OR_CONFIG
    if not cfg_path.is_absolute():
        cfg_path = base / cfg_path
    raw = _read_json(cfg_path)

    data_value = str(raw.get("data_file", DEFAULT_OR_DATA.as_posix()))
    dispatch_value = str(
        raw.get("dispatch_config", "config/dispatch.json")
    )
    data_path = Path(data_value)
    if not data_path.is_absolute():
        data_path = (base / data_path).resolve()
    dispatch_path = Path(dispatch_value)
    if not dispatch_path.is_absolute():
        dispatch_path = (base / dispatch_path).resolve()

    capacity_raw = raw.get("road_capacity") or {}
    by_type = capacity_raw.get("vehicles_per_lane_hour_by_type") or {}
    if not isinstance(by_type, dict):
        raise ORConfigError("road_capacity.vehicles_per_lane_hour_by_type must be an object")
    road_capacity = ORRoadCapacity(
        source=str(capacity_raw.get("source", "UNSET")),
        notice=str(capacity_raw.get("notice", "")),
        planning_interval_hours=_as_float(
            capacity_raw, "planning_interval_hours", 24.0
        ),
        default_vehicles_per_lane_hour=_as_float(
            capacity_raw, "default_vehicles_per_lane_hour", 800.0
        ),
        minimum_vehicles_per_lane=_as_float(
            capacity_raw, "minimum_vehicles_per_lane", 10.0
        ),
        reserve_fraction=_as_float(capacity_raw, "reserve_fraction", 0.0),
        vehicles_per_lane_hour_by_type={
            str(key): float(value) for key, value in by_type.items()
        },
    )

    mip = raw.get("mip") or {}
    output_value = str(raw.get("output_dir", "reports"))
    output_dir = Path(output_value)
    if not output_dir.is_absolute():
        output_dir = (base / output_dir).resolve()

    explicit = raw.get("explicit_prohibited_lanes") or []
    if not isinstance(explicit, list):
        raise ORConfigError("explicit_prohibited_lanes must be a list")
    explicit_lanes = tuple(str(item) for item in explicit)

    config = ORPlanningConfig(
        path=cfg_path,
        root=base,
        raw=raw,
        data_path=data_path,
        dispatch_config_path=dispatch_path,
        vehicle_class=str(raw.get("vehicle_class", "emergency")),
        fleet_size=_as_int(raw, "fleet_size", 48),
        kits_per_trip=_as_int(raw, "kits_per_trip", 10),
        ambulance_trips_per_day=_as_int(raw, "ambulance_trips_per_day", 1),
        shift_hours=_as_float(raw, "shift_hours", 12.0),
        planning_horizon_hours=_as_float(raw, "planning_horizon_hours", 24.0),
        max_point_snap_m=_as_float(raw, "max_point_snap_m", 500.0),
        max_routable_snap_m=_as_float(raw, "max_routable_snap_m", 400.0),
        require_hospital_count=_as_int(raw, "require_hospital_count", 25),
        require_exactly_four_zones=bool(raw.get("require_exactly_four_zones", True)),
        explicit_prohibited_lanes=explicit_lanes,
        road_capacity=road_capacity,
        mip_unmet_penalty=_as_float(mip, "unmet_penalty_per_unit", 1.0e9),
        mip_fleet_tiebreak=_as_float(mip, "fleet_tiebreak_per_vehicle", 1.0e-6),
        mip_time_limit_seconds=_as_float(mip, "time_limit_seconds", 120.0),
        mip_relative_gap=_as_float(mip, "relative_gap", 0.0),
        output_dir=output_dir,
    )

    # Basic rule checks are deliberately done in the loader, not in the
    # planner, so a malformed file fails before any network work starts.
    if config.fleet_size <= 0:
        raise ORConfigError("fleet_size must be positive")
    if config.kits_per_trip <= 0:
        raise ORConfigError("kits_per_trip must be positive")
    if config.ambulance_trips_per_day != 1:
        raise ORConfigError(
            "ambulance_trips_per_day must be 1 in this conservative one-trip model"
        )
    if config.shift_hours <= 0.0:
        raise ORConfigError("shift_hours must be positive")
    if config.planning_horizon_hours <= 0.0:
        raise ORConfigError("planning_horizon_hours must be positive")
    if config.max_point_snap_m <= 0.0:
        raise ORConfigError("max_point_snap_m must be positive")
    if not (0.0 <= config.road_capacity.reserve_fraction < 1.0):
        raise ORConfigError("road_capacity.reserve_fraction must be in [0, 1)")
    if config.mip_unmet_penalty <= 0.0:
        raise ORConfigError("mip.unmet_penalty_per_unit must be positive")
    return config


def load_or_test_data(config: ORPlanningConfig) -> ORTestData:
    """Read the explicitly labelled synthetic quantities.

    يقرأ الكميات الاختبارية الموسومة بوضوح؛ لا يستنتج أي قيمة غائبة.
    """
    raw = _read_json(config.data_path)
    anchors_raw = raw.get("zone_anchors") or {}
    if not isinstance(anchors_raw, dict):
        raise ORConfigError("zone_anchors must be an object")

    anchors: Dict[str, str] = {}
    for zone_id, item in anchors_raw.items():
        if isinstance(item, str):
            slug = item
        elif isinstance(item, dict):
            slug = str(item.get("hospital_slug", "")).strip()
        else:
            raise ORConfigError(
                "zone_anchors[{0}] must be a slug or an object".format(zone_id)
            )
        if not slug:
            raise ORConfigError("zone_anchors[{0}] is empty".format(zone_id))
        anchors[str(zone_id)] = slug

    supply_raw = raw.get("kit_supply_by_hospital") or {}
    demand_kits_raw = raw.get("zone_demand_kits") or {}
    demand_patients_raw = raw.get("zone_demand_patients") or {}
    background_raw = raw.get("background_lane_flow") or {}
    if not isinstance(supply_raw, dict) or not isinstance(demand_kits_raw, dict):
        raise ORConfigError("supply/demand tables must be objects")
    if not isinstance(demand_patients_raw, dict) or not isinstance(background_raw, dict):
        raise ORConfigError("patient demand/background flow tables must be objects")

    def nonnegative_int(value: Any, label: str) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise ORConfigError("{0} must be an integer".format(label)) from exc
        if number < 0:
            raise ORConfigError("{0} must be non-negative".format(label))
        return number

    units_raw = raw.get("units") or {}
    choices_raw = raw.get("synthetic_choices") or []
    data = ORTestData(
        path=config.data_path,
        source=str(raw.get("source", "UNSET")),
        notice=str(raw.get("notice", "")),
        units={str(key): str(value) for key, value in dict(units_raw).items()},
        zone_anchors=anchors,
        kit_supply_by_hospital={
            str(key): nonnegative_int(value, "kit_supply_by_hospital[{0}]".format(key))
            for key, value in supply_raw.items()
        },
        zone_demand_kits={
            str(key): nonnegative_int(value, "zone_demand_kits[{0}]".format(key))
            for key, value in demand_kits_raw.items()
        },
        zone_demand_patients={
            str(key): nonnegative_int(value, "zone_demand_patients[{0}]".format(key))
            for key, value in demand_patients_raw.items()
        },
        background_lane_flow={
            str(key): float(value) for key, value in background_raw.items()
        },
        background_note=str(raw.get("background_note", "")),
        synthetic_choices=tuple(str(item) for item in choices_raw),
    )
    for lane_id, value in data.background_lane_flow.items():
        if value < 0.0:
            raise ORConfigError(
                "background_lane_flow[{0}] must be non-negative".format(lane_id)
            )
    return data
