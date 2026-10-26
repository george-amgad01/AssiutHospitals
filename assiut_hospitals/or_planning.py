"""End-to-end Operations Research planning for Assiut.

تخطيط بحوث العمليات من البداية إلى النهاية لمدينة أسيوط.

The module connects the existing hospital dataset and manual zones to:

* the lane-level distance router (:mod:`or_router`);
* the kit-only transportation tableau (VAM / NWC / least-cost / MODI);
* the road-capacitated integer network model (:mod:`or_network`).

The transportation tableau and the network model are intentionally separate.
The tableau has no lane capacities, and the network model does not claim that
VAM/MODI alone is a road-capacitated optimum.  All unavailable quantities are
read from the clearly labelled synthetic test-data file.

هذا الملف يربط بيانات المستشفيات والمناطق اليدوية بمسار المسارات الفعلية،
وجدول النقل، ونموذج الشبكة المقيّد بالسعة. الفصل بين الجدول والشبكة مقصود.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .capacity import CapacityBook, load_capacity
from .config import Config, load_config
from .dataset import Dataset, HospitalRecord, load_dataset
from .dispatch_config import DispatchConfig, Zone, load_dispatch_config
from .netmodel import Network
from .or_config import ORPlanningConfig, ORTestData, load_or_config, load_or_test_data
from .or_modi import compare_transport_methods, solve_modi
from .or_network import Flow, NetworkPlan, NetworkSolver, RouteLink
from .or_router import (
    DistanceRoute,
    DistanceRouter,
    ORRoutingError,
    RoutePoint,
    SearchStats,
)
from .or_transport import (
    BalancedProblem,
    TransportProblem,
    TransportResult,
    balance_problem,
    check_allocation,
)

EPS = 1e-7
INF = float("inf")


# ---------------------------------------------------------------------------
# Prepared entities
# ---------------------------------------------------------------------------
@dataclass
class HospitalOR:
    """One routable hospital with its OR role and state.

    مستشفى قابل للتوجيه مع دوره وحالته في نموذج بحوث العمليات.
    """

    slug: str
    display_name: str
    category: str
    zone_id: str
    zone_name: str
    lat: float
    lon: float
    emergency: bool
    beds_total: int
    beds_free: int
    kit_supply: int
    can_leave: bool
    can_enter: bool
    source_active: bool
    patient_destination: bool
    excluded_reason: str
    point: Optional[RoutePoint]
    snap_distance_m: float
    record: HospitalRecord

    def as_dict(self) -> Dict[str, object]:
        return {
            "slug": self.slug,
            "display_name": self.display_name,
            "category": self.category,
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "emergency": self.emergency,
            "beds_total": self.beds_total,
            "beds_free": self.beds_free,
            "kit_supply": self.kit_supply,
            "can_leave": self.can_leave,
            "can_enter": self.can_enter,
            "source_active": self.source_active,
            "patient_destination": self.patient_destination,
            "excluded_reason": self.excluded_reason,
            "snap_distance_m": round(self.snap_distance_m, 2),
            "point": self.point.as_dict() if self.point is not None else None,
        }


@dataclass
class ZoneOR:
    """A manual zone with its anchor and OR counts.

    منطقة يدوية مع نقطة ارتكازها وأعدادها في نموذج بحوث العمليات.
    """

    zone: Zone
    anchor: Optional[HospitalOR]
    hospitals: List[HospitalOR]
    active_sources: List[HospitalOR]
    patient_destinations: List[HospitalOR]
    kit_demand: int
    patient_demand: int

    @property
    def id(self) -> str:
        return self.zone.id

    @property
    def total_supply(self) -> int:
        return sum(item.kit_supply for item in self.hospitals)

    @property
    def total_beds(self) -> int:
        return sum(item.beds_free for item in self.patient_destinations)

    def as_dict(self) -> Dict[str, object]:
        return {
            "id": self.zone.id,
            "name": self.zone.name,
            "boundary": {
                "south": self.zone.south,
                "west": self.zone.west,
                "north": self.zone.north,
                "east": self.zone.east,
            },
            "anchor": self.anchor.slug if self.anchor is not None else None,
            "hospital_count": len(self.hospitals),
            "hospitals": [item.slug for item in self.hospitals],
            "active_sources": [item.slug for item in self.active_sources],
            "patient_destinations": [item.slug for item in self.patient_destinations],
            "kit_supply": self.total_supply,
            "kit_demand": self.kit_demand,
            "patient_demand": self.patient_demand,
            "free_beds": self.total_beds,
        }


@dataclass
class MatrixCell:
    """A routed origin/destination pair, or a documented unavailable cell."""

    source: str
    target: str
    route: Optional[DistanceRoute]
    reason: str = ""

    @property
    def available(self) -> bool:
        return self.route is not None

    @property
    def distance_m(self) -> Optional[float]:
        return self.route.distance_m if self.route is not None else None

    @property
    def seconds(self) -> Optional[float]:
        return self.route.seconds if self.route is not None else None

    def as_dict(self) -> Dict[str, object]:
        return {
            "source": self.source,
            "target": self.target,
            "available": self.available,
            "distance_m": round(self.distance_m, 3)
            if self.distance_m is not None
            else None,
            "seconds": round(self.seconds, 4) if self.seconds is not None else None,
            "reason": self.reason,
            "route": self.route.as_dict(include_segments=False)
            if self.route is not None
            else None,
        }


@dataclass
class ORPlanResult:
    """All OR outputs needed by the reports and verifier.

    كل مخرجات بحوث العمليات اللازمة للتقارير والتحقق.
    """

    config: ORPlanningConfig
    data: ORTestData
    dataset: Dataset
    dispatch_config: DispatchConfig
    capacity: CapacityBook
    network: Network
    hospitals: Dict[str, HospitalOR]
    zones: List[ZoneOR]
    kit_problem: Optional[TransportProblem]
    balanced: Optional[BalancedProblem]
    transport: Dict[str, TransportResult]
    kit_cells: Dict[Tuple[str, str], MatrixCell]
    patient_cells: Dict[Tuple[str, str], MatrixCell]
    routing_comparison: List[Dict[str, object]]
    network_plan: Optional[NetworkPlan]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    timings: Dict[str, float] = field(default_factory=dict)
    prohibited_summary: Dict[str, object] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    @property
    def feasible(self) -> bool:
        if self.errors:
            return False
        if self.network_plan is None:
            return False
        return self.network_plan.feasible

    @property
    def optimal(self) -> bool:
        if self.network_plan is None:
            return False
        return self.network_plan.success and self.network_plan.demand_met

    @property
    def total_kit_supply(self) -> int:
        return sum(item.kit_supply for item in self.hospitals.values())

    @property
    def total_kit_demand(self) -> int:
        return sum(zone.kit_demand for zone in self.zones)

    @property
    def total_patient_demand(self) -> int:
        return sum(zone.patient_demand for zone in self.zones)

    @property
    def total_beds(self) -> int:
        return sum(item.beds_free for item in self.hospitals.values() if item.patient_destination)

    def summary(self) -> Dict[str, object]:
        transport_rows = {
            name: {
                "feasible": result.feasible,
                "status": result.status,
                "objective": None
                if not math.isfinite(result.objective)
                else round(result.objective, 6),
                "unmet": result.unmet,
                "unused": result.unused,
                "iterations": result.iterations,
                "seconds": round(result.seconds, 6),
            }
            for name, result in self.transport.items()
        }
        return {
            "synthetic": self.data.synthetic,
            "feasible": self.feasible,
            "optimal_for_network_milp": self.optimal,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "hospitals": len(self.hospitals),
            "zones": [zone.as_dict() for zone in self.zones],
            "kit_supply": self.total_kit_supply,
            "kit_demand": self.total_kit_demand,
            "patient_demand": self.total_patient_demand,
            "free_beds": self.total_beds,
            "transport": transport_rows,
            "network": self.network_plan.as_dict() if self.network_plan else None,
            "timings": {key: round(value, 6) for key, value in self.timings.items()},
            "prohibited": dict(self.prohibited_summary),
            "notes": list(self.notes),
            "sources": {
                "or_config": str(self.config.path),
                "or_data": str(self.data.path),
                "dispatch_config": str(self.dispatch_config.path),
                "capacity": {
                    "source": self.capacity.source,
                    "synthetic": self.capacity.synthetic,
                    "notice": self.capacity.notice,
                    "records": len(self.capacity.by_slug),
                    "errors": list(self.capacity.errors),
                },
                "network": str(self.network.path),
            },
        }


class ORPlanner:
    """Prepare, route, allocate, optimize, and validate one OR plan.

    يجهّز المسارات والتخصيص ويحل نموذج الشبكة ثم يتحقق من الحل.
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        or_config: Optional[ORPlanningConfig] = None,
        test_data: Optional[ORTestData] = None,
        dataset: Optional[Dataset] = None,
        dispatch_config: Optional[DispatchConfig] = None,
        capacity: Optional[CapacityBook] = None,
        network: Optional[Network] = None,
    ):
        self.config = config or load_config()
        self.or_config = or_config or load_or_config(root=self.config.root)
        self.data = test_data or load_or_test_data(self.or_config)
        self.dataset = dataset or load_dataset(self.config.dataset_file)
        self.dispatch_config = dispatch_config or load_dispatch_config(
            self.or_config.dispatch_config_path, root=self.config.root
        )
        self.capacity = capacity or load_capacity(
            self.dispatch_config.capacity_file,
            self.dataset,
            clinics_as_emergency=self.dispatch_config.clinics_as_emergency,
        )
        self.network = network or Network(self.config.net_file)
        if self.network.lane_graph is None:
            raise RuntimeError("network has no lane graph")
        self.graph = self.network.lane_graph
        self.router = DistanceRouter(
            self.network,
            vehicle_class=self.or_config.vehicle_class,
            explicit_prohibited_lanes=self.or_config.explicit_prohibited_lanes,
            max_point_snap_m=self.or_config.max_point_snap_m,
        )
        self.main_component = self.graph.main_component(self.or_config.vehicle_class)
        self._allowed_lanes = set(self.graph.lane_info) - self.router.prohibited
        self._reverse: Dict[str, Set[str]] = {lane: set() for lane in self._allowed_lanes}
        for lane in self._allowed_lanes:
            for successor in self.graph.successors.get(lane, ()):
                if successor in self._allowed_lanes:
                    self._reverse[successor].add(lane)

        self.hospitals: Dict[str, HospitalOR] = {}
        self.zones: List[ZoneOR] = []
        self.kit_cells: Dict[Tuple[str, str], MatrixCell] = {}
        self.patient_cells: Dict[Tuple[str, str], MatrixCell] = {}
        self.errors: List[str] = []
        self.warnings: List[str] = []

    # ------------------------------------------------------------------ helpers
    def _can_enter(self, record: HospitalRecord) -> bool:
        """Can a vehicle from the main component reach the hospital lane?"""
        edge = record.snap.edge_id
        targets = set(self.graph.usable_lanes(edge, self.or_config.vehicle_class))
        targets &= self._allowed_lanes
        if not targets or not self.main_component:
            return False
        stack = list(targets)
        seen = set(targets)
        while stack:
            lane = stack.pop()
            if lane in self.main_component:
                return True
            for predecessor in self._reverse.get(lane, ()):
                if predecessor not in seen:
                    seen.add(predecessor)
                    stack.append(predecessor)
        return False

    def _can_leave(self, record: HospitalRecord) -> bool:
        if not self.main_component:
            return False
        reachable = self.graph.reachable_lanes(
            [record.snap.edge_id], self.or_config.vehicle_class
        )
        reachable &= self._allowed_lanes
        return bool(reachable & self.main_component)

    def _zone_for(self, slug: str) -> Optional[Zone]:
        return self.dispatch_config.zone_of(slug)

    # ------------------------------------------------------------------ prepare
    def prepare(self) -> List[str]:
        """Build hospital roles and zone summaries from existing sources.

        يبني أدوار المستشفيات وملخصات المناطق من المصادر الموجودة دون اختراع
        قدرات أو طلبات.
        """
        self.errors = []
        self.warnings = []
        self.hospitals = {}
        self.zones = []

        routable = sorted(self.dataset.routable, key=lambda item: item.slug)
        if len(routable) != self.or_config.require_hospital_count:
            self.errors.append(
                "routable hospital count is {0}, expected {1}".format(
                    len(routable), self.or_config.require_hospital_count
                )
            )
        if self.or_config.require_exactly_four_zones and len(self.dispatch_config.zones) != 4:
            self.errors.append(
                "dispatch config must contain exactly four zones (found {0})".format(
                    len(self.dispatch_config.zones)
                )
            )

        zone_ids = [zone.id for zone in self.dispatch_config.zones]
        for zone in self.dispatch_config.zones:
            if zone.id not in self.data.zone_anchors:
                self.errors.append("missing zone anchor for {0}".format(zone.id))
            if zone.id not in self.data.zone_demand_kits:
                self.errors.append("missing kit demand for {0}".format(zone.id))
            if zone.id not in self.data.zone_demand_patients:
                self.errors.append("missing patient demand for {0}".format(zone.id))
        for extra in sorted(set(self.data.zone_anchors) - set(zone_ids)):
            self.errors.append("zone anchor for unknown zone {0}".format(extra))
        for extra in sorted(set(self.data.zone_demand_kits) - set(zone_ids)):
            self.errors.append("kit demand for unknown zone {0}".format(extra))
        for extra in sorted(set(self.data.zone_demand_patients) - set(zone_ids)):
            self.errors.append("patient demand for unknown zone {0}".format(extra))

        records_by_slug = {record.slug: record for record in routable}
        for slug in sorted(set(self.data.kit_supply_by_hospital) - set(records_by_slug)):
            self.errors.append(
                "kit supply is assigned to a non-routable/unknown hospital: {0}".format(
                    slug
                )
            )
        for slug in sorted(set(records_by_slug) - set(self.data.kit_supply_by_hospital)):
            self.errors.append("missing kit supply for routable hospital {0}".format(slug))

        anchors: Dict[str, HospitalOR] = {}
        for record in routable:
            slug = record.slug
            zone = self._zone_for(slug)
            if zone is None:
                self.errors.append("routable hospital {0} is not assigned to a zone".format(slug))
                zone_id = ""
                zone_name = ""
            else:
                zone_id = zone.id
                zone_name = zone.name
            capacity_item = self.capacity.get(slug)
            if capacity_item is None:
                self.errors.append("missing emergency capacity record for {0}".format(slug))
                beds_total = 0
                beds_free = 0
            else:
                beds_total = capacity_item.beds_total
                beds_free = capacity_item.beds_free
            emergency = self.capacity.effective_emergency(record)
            can_leave = self._can_leave(record)
            can_enter = self._can_enter(record)
            supply = int(self.data.kit_supply_by_hospital.get(slug, 0))
            if supply > 0 and not can_leave:
                self.errors.append(
                    "kit source {0} cannot leave its dead-end road component".format(slug)
                )
            source_active = bool(supply > 0 and can_leave)
            patient_destination = bool(emergency and beds_free > 0 and can_enter)
            excluded_reason = ""
            if not emergency:
                excluded_reason = "not an emergency facility under the clinic policy"
            elif beds_free <= 0:
                excluded_reason = "no free emergency bed"
            elif not can_enter:
                excluded_reason = "receiving lane cannot be reached from the main network"
            if beds_free > 0 and not patient_destination:
                self.warnings.append(
                    "hospital {0} has {1} free bed(s) but is not a patient destination: {2}".format(
                        slug, beds_free, excluded_reason
                    )
                )
            point: Optional[RoutePoint]
            try:
                point = self.router.point_for_hospital(record)
            except ORRoutingError as exc:
                point = None
                self.errors.append("cannot create route point for {0}: {1}".format(slug, exc))
            hospital = HospitalOR(
                slug=slug,
                display_name=record.display_name,
                category=record.hospital.category,
                zone_id=zone_id,
                zone_name=zone_name,
                lat=record.hospital.lat,
                lon=record.hospital.lon,
                emergency=emergency,
                beds_total=beds_total,
                beds_free=beds_free,
                kit_supply=supply,
                can_leave=can_leave,
                can_enter=can_enter,
                source_active=source_active,
                patient_destination=patient_destination,
                excluded_reason=excluded_reason,
                point=point,
                snap_distance_m=record.snap.distance_m,
                record=record,
            )
            self.hospitals[slug] = hospital

        for zone in self.dispatch_config.zones:
            anchor_slug = self.data.zone_anchors.get(zone.id, "")
            anchor = self.hospitals.get(anchor_slug)
            if anchor is None:
                self.errors.append(
                    "zone {0} anchor {1} is not a routable hospital".format(
                        zone.id, anchor_slug
                    )
                )
            else:
                if anchor.zone_id != zone.id:
                    self.errors.append(
                        "zone {0} anchor {1} is assigned to zone {2} instead".format(
                            zone.id, anchor_slug, anchor.zone_id
                        )
                    )
                if not anchor.can_leave or not anchor.can_enter:
                    self.errors.append(
                        "zone {0} anchor {1} is not on the main strongly connected component".format(
                            zone.id, anchor_slug
                        )
                    )
                anchors[zone.id] = anchor

        for zone in self.dispatch_config.zones:
            members = sorted(
                (item for item in self.hospitals.values() if item.zone_id == zone.id),
                key=lambda item: item.slug,
            )
            kit_demand = int(self.data.zone_demand_kits.get(zone.id, 0))
            patient_demand = int(self.data.zone_demand_patients.get(zone.id, 0))
            zone_or = ZoneOR(
                zone=zone,
                anchor=anchors.get(zone.id),
                hospitals=members,
                active_sources=[item for item in members if item.source_active],
                patient_destinations=[item for item in members if item.patient_destination],
                kit_demand=kit_demand,
                patient_demand=patient_demand,
            )
            self.zones.append(zone_or)

        q = self.or_config.kits_per_trip
        for hospital in self.hospitals.values():
            if hospital.kit_supply % q != 0:
                self.errors.append(
                    "kit supply at {0} ({1}) is not a multiple of kits_per_trip={2}".format(
                        hospital.slug, hospital.kit_supply, q
                    )
                )
        for zone in self.zones:
            if zone.kit_demand % q != 0:
                self.errors.append(
                    "kit demand at {0} ({1}) is not a multiple of kits_per_trip={2}".format(
                        zone.id, zone.kit_demand, q
                    )
                )
        if not self.main_component:
            self.errors.append("the lane graph has no main strongly connected component")
        return list(self.errors)

    # ------------------------------------------------------------------ routing
    def _route(
        self, source: Optional[RoutePoint], target: Optional[RoutePoint], label: str
    ) -> Tuple[Optional[DistanceRoute], str]:
        if source is None or target is None:
            return None, "missing route point"
        try:
            route = self.router.shortest_path(source, target, "dijkstra")
        except ORRoutingError as exc:
            return None, str(exc)
        if route is None:
            return None, "no lane-level route under the current prohibitions"
        if route.seconds > self.or_config.shift_hours * 3600.0 + 1e-6:
            return None, "route takes {0:.1f} s, above the {1:.1f} h shift limit".format(
                route.seconds, self.or_config.shift_hours
            )
        if route.prohibited_hits:
            return None, "route uses prohibited lanes: {0}".format(
                ", ".join(route.prohibited_hits)
            )
        return route, ""

    def build_matrices(self) -> None:
        """Route every active kit source to every zone anchor and vice versa.

        يوجّه كل مصدر كراتين نشط إلى نقاط ارتكاز المناطق، وكل نقطة ارتكاز إلى
        المستشفيات المستقبِلة، على مسارات المسارات الفعلية.
        """
        self.kit_cells = {}
        self.patient_cells = {}
        for zone in self.zones:
            if zone.anchor is None:
                continue
            anchor_point = zone.anchor.point
            for source in sorted(self.hospitals.values(), key=lambda item: item.slug):
                if not source.source_active:
                    continue
                key = (source.slug, zone.id)
                route, reason = self._route(
                    source.point, anchor_point, "kit {0}->{1}".format(*key)
                )
                self.kit_cells[key] = MatrixCell(source.slug, zone.id, route, reason)
                if route is None:
                    self.warnings.append(
                        "kit cell {0}->{1} unavailable: {2}".format(
                            source.slug, zone.id, reason
                        )
                    )

        for zone in self.zones:
            if zone.anchor is None:
                continue
            anchor_point = zone.anchor.point
            for destination in sorted(
                self.hospitals.values(), key=lambda item: item.slug
            ):
                if not destination.patient_destination:
                    continue
                key = (zone.id, destination.slug)
                route, reason = self._route(
                    anchor_point, destination.point, "patient {0}->{1}".format(*key)
                )
                self.patient_cells[key] = MatrixCell(
                    zone.id, destination.slug, route, reason
                )
                if route is None:
                    self.warnings.append(
                        "patient cell {0}->{1} unavailable: {2}".format(
                            zone.id, destination.slug, reason
                        )
                    )

    def build_transport_problem(self) -> Tuple[TransportProblem, BalancedProblem]:
        """Build the kit-only tableau; unresolved roads become forbidden cells.

        يبني جدول الكراتين فقط، وتصبح الطرق غير المتاحة خلايا ممنوعة.
        """
        sources = sorted(
            (item for item in self.hospitals.values() if item.source_active),
            key=lambda item: item.slug,
        )
        zone_ids = [zone.id for zone in self.zones]
        costs: List[List[Optional[float]]] = []
        for source in sources:
            row: List[Optional[float]] = []
            for zone_id in zone_ids:
                cell = self.kit_cells.get((source.slug, zone_id))
                row.append(cell.distance_m if cell is not None and cell.available else None)
            costs.append(row)
        problem = TransportProblem(
            row_labels=[item.slug for item in sources],
            col_labels=zone_ids,
            costs=costs,
            supplies=[item.kit_supply for item in sources],
            demands=[zone.kit_demand for zone in self.zones],
            units="medical kits",
            row_notes=["active kit source" for _ in sources],
            col_notes=["zone delivery anchor" for _ in zone_ids],
        )
        return problem, balance_problem(problem)

    def solve_transport(self) -> Tuple[TransportProblem, BalancedProblem, Dict[str, TransportResult]]:
        problem, balanced = self.build_transport_problem()
        results = compare_transport_methods(balanced, include_exact=True)
        return problem, balanced, results

    def solve_network(self) -> NetworkPlan:
        """Build and solve the lane-capacitated integer network model."""
        kit_links: List[RouteLink] = []
        for (source_slug, zone_id), cell in sorted(self.kit_cells.items()):
            if not cell.available or cell.route is None:
                continue
            kit_links.append(
                RouteLink("kit", source_slug, zone_id, cell.route, "kit cell")
            )
        patient_links: List[RouteLink] = []
        for (zone_id, target_slug), cell in sorted(self.patient_cells.items()):
            if not cell.available or cell.route is None:
                continue
            patient_links.append(
                RouteLink("patient", zone_id, target_slug, cell.route, "patient cell")
            )
        supplies = {
            item.slug: item.kit_supply
            for item in self.hospitals.values()
            if item.source_active and item.kit_supply > 0
        }
        beds = {
            item.slug: item.beds_free
            for item in self.hospitals.values()
            if item.patient_destination
        }
        kit_demands = {zone.id: zone.kit_demand for zone in self.zones}
        patient_demands = {zone.id: zone.patient_demand for zone in self.zones}
        solver = NetworkSolver(
            self.or_config,
            self.data,
            self.network,
            self.router,
            [zone.id for zone in self.zones],
            supplies,
            beds,
            kit_demands,
            patient_demands,
            kit_links,
            patient_links,
        )
        return solver.solve()

    # ------------------------------------------------------------------ comparison
    def compare_routing(self) -> List[Dict[str, object]]:
        """Compare Dijkstra, A*, and Bellman-Ford on four representative trips.

        يقارن الخوارزميات على أربع رحلات تمثيلية مع التحقق من المسافة والصلاحية.
        """
        comparison: List[Dict[str, object]] = []
        if len(self.zones) < 2:
            return comparison
        for index, zone in enumerate(self.zones):
            next_zone = self.zones[(index + 1) % len(self.zones)]
            if not zone.active_sources or next_zone.anchor is None:
                continue
            source = zone.active_sources[0]
            target = next_zone.anchor
            stats: List[SearchStats] = self.router.compare(source.point, target.point)
            rows = [
                {
                    "algorithm": item.algorithm,
                    "found": item.found,
                    "distance_m": None
                    if item.distance_m is None
                    else round(item.distance_m, 3),
                    "seconds": None
                    if item.seconds is None
                    else round(item.seconds, 4),
                    "settled": item.settled,
                    "elapsed_seconds": round(item.elapsed_seconds, 9),
                    "note": item.note,
                }
                for item in stats
            ]
            found_distances = {
                round(item.distance_m, 6)
                for item in stats
                if item.found and item.distance_m is not None
            }
            comparison.append(
                {
                    "source_zone": zone.id,
                    "source": source.slug,
                    "target_zone": next_zone.id,
                    "target": target.slug,
                    "algorithms": rows,
                    "distance_spread_m": round(
                        max(found_distances) - min(found_distances), 6
                    )
                    if found_distances
                    else None,
                    "all_found": all(item.found for item in stats),
                    "consistent": len(found_distances) <= 1,
                }
            )
        return comparison

    # ------------------------------------------------------------------ validation
    def _validate_transport(
        self,
        balanced: BalancedProblem,
        results: Dict[str, TransportResult],
    ) -> None:
        for name, result in sorted(results.items()):
            if not result.feasible:
                status = result.status.lower()
                known_limitation = (
                    name == "NWC" and "forbidden" in status
                ) or (
                    name == "MODI" and "cell caps" in status
                )
                if known_limitation:
                    self.warnings.append(
                        "transport method {0} is unavailable by design: {1}".format(
                            name, result.status
                        )
                    )
                else:
                    self.errors.append(
                        "transport method {0} is not feasible: {1}".format(
                            name, result.status
                        )
                    )
                continue
            allocation_errors = check_allocation(balanced, result.allocation)
            for message in allocation_errors:
                self.errors.append("{0}: {1}".format(name, message))
        vam = results.get("VAM")
        modi = results.get("MODI")
        exact = results.get("exact-MILP")
        if vam is not None and modi is not None and vam.feasible and modi.feasible:
            if modi.objective > vam.objective + 1e-6:
                self.errors.append(
                    "MODI objective {0} is worse than VAM objective {1}".format(
                        modi.objective, vam.objective
                    )
                )
            if modi.status != "optimal":
                self.warnings.append(
                    "MODI did not prove optimality: {0}".format(modi.status)
                )
        if exact is not None and exact.feasible:
            for name in ("VAM", "MODI"):
                item = results.get(name)
                if item is not None and item.feasible:
                    gap = item.objective - exact.objective
                    if gap > 1e-6:
                        self.warnings.append(
                            "{0} objective is {1:.3f} above the exact table optimum (gap {2:.3f})".format(
                                name, item.objective, exact.objective, gap
                            )
                        )
                    elif gap < -1e-6:
                        self.errors.append(
                            "{0} objective {1:.3f} is below the exact table optimum {2:.3f}".format(
                                name, item.objective, exact.objective
                            )
                        )
        if modi is not None and modi.feasible and modi.reduced_costs is not None:
            for i, row in enumerate(modi.reduced_costs):
                for j, value in enumerate(row):
                    if value is None:
                        continue
                    if value < -1e-6 and (i, j) not in set(modi.basis):
                        self.errors.append(
                            "MODI final non-basic reduced cost is negative at ({0},{1})".format(
                                i, j
                            )
                        )

    def _validate_network(self, plan: NetworkPlan) -> None:
        if not plan.success:
            self.errors.append("network MILP did not solve: {0}".format(plan.message))
        for name, passed in plan.checks.items():
            if name == "demand_met":
                continue
            if not passed:
                self.errors.append("network constraint failed: {0}".format(name))
        for message in plan.errors:
            if message not in self.errors:
                self.errors.append(message)
        if plan.total_unmet_kits or plan.total_unmet_patients:
            self.warnings.append(
                "network plan leaves {0} kit unit(s) and {1} patient transfer(s) unmet".format(
                    plan.total_unmet_kits, plan.total_unmet_patients
                )
            )
        if plan.background_over_capacity:
            self.warnings.append(
                "{0} lane(s) have background flow at or above the estimated capacity".format(
                    len(plan.background_over_capacity)
                )
            )

    # ------------------------------------------------------------------ plan
    def plan(self, routing_comparison: bool = True) -> ORPlanResult:
        """Run the complete reproducible OR pipeline."""
        started = time.perf_counter()
        timings: Dict[str, float] = {}
        t0 = time.perf_counter()
        self.prepare()
        timings["prepare"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        self.build_matrices()
        timings["routing_matrices"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        kit_problem, balanced, transport = self.solve_transport()
        timings["transportation"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        network_plan = self.solve_network()
        timings["network_milp"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        comparison = self.compare_routing() if routing_comparison else []
        timings["routing_comparison"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        self._validate_transport(balanced, transport)
        self._validate_network(network_plan)
        if len(self.hospitals) != self.or_config.require_hospital_count:
            self.errors.append(
                "prepared hospital count {0} != {1}".format(
                    len(self.hospitals), self.or_config.require_hospital_count
                )
            )
        timings["validation"] = time.perf_counter() - t0
        timings["total"] = time.perf_counter() - started

        result = ORPlanResult(
            config=self.or_config,
            data=self.data,
            dataset=self.dataset,
            dispatch_config=self.dispatch_config,
            capacity=self.capacity,
            network=self.network,
            hospitals=dict(self.hospitals),
            zones=list(self.zones),
            kit_problem=kit_problem,
            balanced=balanced,
            transport=transport,
            kit_cells=dict(self.kit_cells),
            patient_cells=dict(self.patient_cells),
            routing_comparison=comparison,
            network_plan=network_plan,
            errors=list(self.errors),
            warnings=list(self.warnings),
            timings=timings,
            prohibited_summary=self.router.prohibited_summary(),
            notes=[
                "SYNTHETIC test quantities are used where the repository has no owner data.",
                "The transportation tableau has no lane capacities; the network MILP does.",
                "A feasible network plan is not the same as a proven global optimum for every operational objective.",
                "Free beds are receiving capacity; they are not a shipped resource.",
            ],
        )
        return result
