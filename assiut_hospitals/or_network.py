"""Road-capacitated integer network model for the OR extension.

نموذج شبكة صحيح مقيّد بسعة الطرق لامتداد بحوث العمليات.

The model is deliberately separate from the transportation tableau.  It maps
each kit/patient trip to the actual lane sequence returned by the distance
router, adds ordinary background flow, and enforces lane capacity.  The solver
is SciPy's HiGHS MILP.  A verifier recomputes every constraint independently.

هذا النموذج منفصل عن جدول النقل: يحوّل كل رحلة إلى مسارات فعلية ويضيف التدفق
الخلفي ويفرض سعة كل مسار، ثم يتحقق من الحل مستقلاً.
"""

from __future__ import annotations

import math
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .netmodel import Network
from .or_config import ORPlanningConfig, ORTestData
from .or_router import DistanceRoute, DistanceRouter

INF = float("inf")
EPS = 1e-7


@dataclass
class RouteLink:
    """One candidate kit or patient trip on a concrete lane route."""

    kind: str  # "kit" or "patient"
    source: str
    target: str
    route: DistanceRoute
    note: str = ""

    @property
    def distance_m(self) -> float:
        return self.route.distance_m

    @property
    def seconds(self) -> float:
        return self.route.seconds


@dataclass
class Flow:
    """A selected trip in the network plan."""

    kind: str
    source: str
    target: str
    quantity: int
    route: DistanceRoute

    @property
    def distance_m(self) -> float:
        return self.route.distance_m

    @property
    def seconds(self) -> float:
        return self.route.seconds

    def as_dict(self) -> Dict[str, object]:
        return {
            "kind": self.kind,
            "source": self.source,
            "target": self.target,
            "quantity": self.quantity,
            "distance_m": round(self.distance_m, 3),
            "seconds": round(self.seconds, 4),
            "lanes": self.route.lanes,
            "edges": self.route.edges,
            "prohibited_hits": self.route.prohibited_hits,
        }


@dataclass
class LaneLoad:
    """Background and ambulance flow for one lane."""

    lane_id: str
    edge_id: str
    edge_type: str
    background: float
    ambulance: float
    capacity: float

    @property
    def total(self) -> float:
        return self.background + self.ambulance

    @property
    def slack(self) -> float:
        return self.capacity - self.total

    @property
    def over_capacity(self) -> bool:
        return self.total > self.capacity + 1e-7

    def as_dict(self) -> Dict[str, object]:
        return {
            "lane_id": self.lane_id,
            "edge_id": self.edge_id,
            "edge_type": self.edge_type,
            "background": round(self.background, 3),
            "ambulance": round(self.ambulance, 3),
            "total": round(self.total, 3),
            "capacity": round(self.capacity, 3),
            "slack": round(self.slack, 3),
            "over_capacity": self.over_capacity,
        }


@dataclass
class NetworkPlan:
    """Result of the road-capacitated MILP."""

    status: str
    success: bool
    message: str
    solver_seconds: float = 0.0
    variables: int = 0
    constraints: int = 0
    solver_objective: Optional[float] = None
    kit_flows: List[Flow] = field(default_factory=list)
    patient_flows: List[Flow] = field(default_factory=list)
    ambulance_by_zone: Dict[str, int] = field(default_factory=dict)
    unmet_kits: Dict[str, int] = field(default_factory=dict)
    unmet_patients: Dict[str, int] = field(default_factory=dict)
    unused_supply: Dict[str, int] = field(default_factory=dict)
    unused_beds: Dict[str, int] = field(default_factory=dict)
    lane_loads: Dict[str, LaneLoad] = field(default_factory=dict)
    checks: Dict[str, bool] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    blocked_links: List[Dict[str, str]] = field(default_factory=list)
    background_over_capacity: List[Dict[str, object]] = field(default_factory=list)

    @property
    def kit_vehicle_m(self) -> float:
        return sum(flow.quantity * flow.distance_m for flow in self.kit_flows)

    @property
    def patient_vehicle_m(self) -> float:
        return sum(flow.quantity * flow.distance_m for flow in self.patient_flows)

    @property
    def total_vehicle_m(self) -> float:
        return self.kit_vehicle_m + self.patient_vehicle_m

    @property
    def total_unmet_kits(self) -> int:
        return sum(self.unmet_kits.values())

    @property
    def total_unmet_patients(self) -> int:
        return sum(self.unmet_patients.values())

    @property
    def total_unused_supply(self) -> int:
        return sum(self.unused_supply.values())

    @property
    def total_unused_beds(self) -> int:
        return sum(self.unused_beds.values())

    @property
    def demand_met(self) -> bool:
        return self.total_unmet_kits == 0 and self.total_unmet_patients == 0

    @property
    def feasible(self) -> bool:
        return self.success and self.demand_met and all(self.checks.values())

    @property
    def vehicles_used(self) -> int:
        return sum(self.ambulance_by_zone.values())

    def as_dict(self) -> Dict[str, object]:
        return {
            "status": self.status,
            "success": self.success,
            "message": self.message,
            "solver_seconds": round(self.solver_seconds, 6),
            "variables": self.variables,
            "constraints": self.constraints,
            "solver_objective": self.solver_objective,
            "feasible": self.feasible,
            "demand_met": self.demand_met,
            "kit_flows": [flow.as_dict() for flow in self.kit_flows],
            "patient_flows": [flow.as_dict() for flow in self.patient_flows],
            "ambulance_by_zone": dict(self.ambulance_by_zone),
            "vehicles_used": self.vehicles_used,
            "unmet_kits": dict(self.unmet_kits),
            "unmet_patients": dict(self.unmet_patients),
            "unused_supply": dict(self.unused_supply),
            "unused_beds": dict(self.unused_beds),
            "kit_vehicle_m": round(self.kit_vehicle_m, 3),
            "patient_vehicle_m": round(self.patient_vehicle_m, 3),
            "total_vehicle_m": round(self.total_vehicle_m, 3),
            "lane_loads": {
                lane: load.as_dict() for lane, load in sorted(self.lane_loads.items())
            },
            "checks": dict(self.checks),
            "errors": list(self.errors),
            "notes": list(self.notes),
            "blocked_links": list(self.blocked_links),
            "background_over_capacity": list(self.background_over_capacity),
        }


@dataclass
class _Variable:
    index: int
    kind: str
    source: str
    target: str
    route: Optional[DistanceRoute]
    distance_m: float
    upper: float
    label: str


class NetworkSolver:
    """Build and solve the lane-capacitated integer network model.

    بناء وحل نموذج الشبكة الصحيح المقيّد بسعة المسارات.
    """

    def __init__(
        self,
        config: ORPlanningConfig,
        data: ORTestData,
        network: Network,
        router: DistanceRouter,
        zone_ids: Sequence[str],
        supplies: Dict[str, int],
        beds: Dict[str, int],
        kit_demands: Dict[str, int],
        patient_demands: Dict[str, int],
        kit_links: Sequence[RouteLink],
        patient_links: Sequence[RouteLink],
    ):
        self.config = config
        self.data = data
        self.network = network
        self.router = router
        self.zone_ids = list(zone_ids)
        self.supplies = dict(supplies)
        self.beds = dict(beds)
        self.kit_demands = dict(kit_demands)
        self.patient_demands = dict(patient_demands)
        self.kit_links = list(kit_links)
        self.patient_links = list(patient_links)
        self.graph = router.graph

    # ------------------------------------------------------------------ lanes
    def lane_capacity(self, lane_id: str) -> Tuple[float, str, str]:
        edge_id = self.graph.edge_of_lane(lane_id) or ""
        edge = self.network.edges.get(edge_id)
        edge_type = edge.type if edge is not None else ""
        capacity = self.config.road_capacity.capacity_for_lane(edge_type)
        return capacity, edge_id, edge_type

    def _link_allowed(self, link: RouteLink, blocked: List[Dict[str, str]]) -> bool:
        if link.route is None:
            return False
        if link.seconds > self.config.shift_hours * 3600.0 + 1e-6:
            blocked.append(
                {
                    "kind": link.kind,
                    "source": link.source,
                    "target": link.target,
                    "reason": "route exceeds shift limit ({0:.1f} s)".format(
                        link.seconds
                    ),
                }
            )
            return False
        for lane in link.route.lanes:
            if lane in self.router.prohibited:
                blocked.append(
                    {
                        "kind": link.kind,
                        "source": link.source,
                        "target": link.target,
                        "reason": "route uses prohibited lane {0}".format(lane),
                    }
                )
                return False
            capacity, _edge_id, _edge_type = self.lane_capacity(lane)
            background = float(self.data.background_lane_flow.get(lane, 0.0))
            if background > capacity + 1e-7:
                blocked.append(
                    {
                        "kind": link.kind,
                        "source": link.source,
                        "target": link.target,
                        "reason": "lane {0} background {1:.1f} exceeds capacity {2:.1f}".format(
                            lane, background, capacity
                        ),
                    }
                )
                return False
            if capacity <= 0.0:
                blocked.append(
                    {
                        "kind": link.kind,
                        "source": link.source,
                        "target": link.target,
                        "reason": "lane {0} has zero estimated capacity".format(lane),
                    }
                )
                return False
        return True

    # ------------------------------------------------------------------ solve
    def solve(self) -> NetworkPlan:
        try:
            import numpy as np
            from scipy.optimize import Bounds, LinearConstraint, milp
            from scipy.sparse import coo_matrix
        except Exception:  # pragma: no cover - optional dependency
            return NetworkPlan(
                status="unavailable",
                success=False,
                message="SciPy is required for the network MILP",
                errors=["SciPy is not installed; install scipy>=1.9"],
            )

        selected_kit: List[RouteLink] = []
        selected_patient: List[RouteLink] = []
        blocked: List[Dict[str, str]] = []
        for link in self.kit_links:
            if self._link_allowed(link, blocked):
                selected_kit.append(link)
        for link in self.patient_links:
            if self._link_allowed(link, blocked):
                selected_patient.append(link)

        variables: List[_Variable] = []
        kit_vars: List[_Variable] = []
        patient_vars: List[_Variable] = []
        ambulance_vars: Dict[str, _Variable] = {}
        unmet_kit_vars: Dict[str, _Variable] = {}
        unmet_patient_vars: Dict[str, _Variable] = {}

        def add_var(
            kind: str,
            source: str,
            target: str,
            route: Optional[DistanceRoute],
            distance: float,
            upper: float,
            label: str,
        ) -> _Variable:
            variable = _Variable(
                index=len(variables),
                kind=kind,
                source=source,
                target=target,
                route=route,
                distance_m=distance,
                upper=upper,
                label=label,
            )
            variables.append(variable)
            return variable

        q = float(self.config.kits_per_trip)
        for link in selected_kit:
            upper = min(
                self.supplies.get(link.source, 0) / q,
                self.kit_demands.get(link.target, 0) / q,
            )
            if upper <= 0:
                continue
            kit_vars.append(
                add_var(
                    "kit",
                    link.source,
                    link.target,
                    link.route,
                    link.distance_m,
                    math.floor(upper + 1e-9),
                    "{0}->{1}".format(link.source, link.target),
                )
            )
        for link in selected_patient:
            upper = min(
                self.patient_demands.get(link.source, 0),
                self.beds.get(link.target, 0),
            )
            if upper <= 0:
                continue
            patient_vars.append(
                add_var(
                    "patient",
                    link.source,
                    link.target,
                    link.route,
                    link.distance_m,
                    math.floor(upper + 1e-9),
                    "{0}->{1}".format(link.source, link.target),
                )
            )
        for zone in self.zone_ids:
            ambulance_vars[zone] = add_var(
                "ambulance",
                zone,
                zone,
                None,
                0.0,
                float(self.config.fleet_size),
                "fleet[{0}]".format(zone),
            )
        for zone in self.zone_ids:
            unmet_kit_vars[zone] = add_var(
                "unmet_kit",
                zone,
                zone,
                None,
                0.0,
                float(self.kit_demands.get(zone, 0)),
                "unmet_kits[{0}]".format(zone),
            )
            unmet_patient_vars[zone] = add_var(
                "unmet_patient",
                zone,
                zone,
                None,
                0.0,
                float(self.patient_demands.get(zone, 0)),
                "unmet_patients[{0}]".format(zone),
            )

        if not variables:
            return NetworkPlan(
                status="infeasible",
                success=False,
                message="no decision variables were created",
                errors=["no kit or patient variables"],
            )

        rows: List[Tuple[str, Dict[int, float], float, float]] = []

        def add_constraint(
            label: str,
            coefficients: Dict[int, float],
            lower: float,
            upper: float,
        ) -> None:
            cleaned = {
                index: value
                for index, value in coefficients.items()
                if abs(value) > 1e-12
            }
            if not cleaned:
                return
            rows.append((label, cleaned, lower, upper))

        # Source kit supply.
        for source, supply in sorted(self.supplies.items()):
            coefficients = {
                var.index: q for var in kit_vars if var.source == source
            }
            if coefficients:
                add_constraint(
                    "kit_supply[{0}]".format(source),
                    coefficients,
                    -INF,
                    float(supply),
                )

        # Zone kit demand and patient demand.
        for zone in self.zone_ids:
            coefficients = {
                var.index: q for var in kit_vars if var.target == zone
            }
            coefficients[unmet_kit_vars[zone].index] = 1.0
            add_constraint(
                "zone_kit_demand[{0}]".format(zone),
                coefficients,
                float(self.kit_demands.get(zone, 0)),
                float(self.kit_demands.get(zone, 0)),
            )
            coefficients = {
                var.index: 1.0 for var in patient_vars if var.source == zone
            }
            coefficients[unmet_patient_vars[zone].index] = 1.0
            add_constraint(
                "zone_patient_demand[{0}]".format(zone),
                coefficients,
                float(self.patient_demands.get(zone, 0)),
                float(self.patient_demands.get(zone, 0)),
            )

        # Hospital bed receiving capacity.
        for hospital, bed_count in sorted(self.beds.items()):
            coefficients = {
                var.index: 1.0 for var in patient_vars if var.target == hospital
            }
            if coefficients:
                add_constraint(
                    "hospital_beds[{0}]".format(hospital),
                    coefficients,
                    -INF,
                    float(bed_count),
                )

        # Fleet and zone allocation.
        add_constraint(
            "fleet_limit",
            {var.index: 1.0 for var in ambulance_vars.values()},
            -INF,
            float(self.config.fleet_size),
        )
        for zone in self.zone_ids:
            coefficients: Dict[int, float] = {}
            for var in kit_vars:
                if var.target == zone:
                    coefficients[var.index] = 1.0
            for var in patient_vars:
                if var.source == zone:
                    coefficients[var.index] = 1.0
            coefficients[ambulance_vars[zone].index] = -1.0
            add_constraint(
                "zone_trips[{0}]".format(zone),
                coefficients,
                -INF,
                0.0,
            )

        # Lane incidence and capacity: background + ambulance <= C_e.
        lane_use: Dict[str, Dict[int, int]] = {}
        for var in kit_vars + patient_vars:
            if var.route is None:
                continue
            counts = Counter(var.route.lanes)
            for lane, count in counts.items():
                lane_use.setdefault(lane, {})[var.index] = count

        background_over: List[Dict[str, object]] = []
        for lane in sorted(set(lane_use) | set(self.data.background_lane_flow)):
            if lane not in self.graph.lane_info:
                background_over.append(
                    {
                        "lane_id": lane,
                        "reason": "background flow names a lane not in the network",
                    }
                )
                continue
            capacity, edge_id, edge_type = self.lane_capacity(lane)
            background = float(self.data.background_lane_flow.get(lane, 0.0))
            if background > capacity + 1e-7:
                background_over.append(
                    {
                        "lane_id": lane,
                        "edge_id": edge_id,
                        "edge_type": edge_type,
                        "background": background,
                        "capacity": capacity,
                        "reason": "background alone exceeds estimated capacity",
                    }
                )
                continue
            coefficients = lane_use.get(lane)
            if coefficients:
                add_constraint(
                    "lane_capacity[{0}]".format(lane),
                    {index: float(count) for index, count in coefficients.items()},
                    -INF,
                    capacity - background,
                )

        # Objective: vehicle distance, then a tiny fleet tie-break, then unmet.
        objective = np.zeros(len(variables))
        for var in variables:
            if var.kind in ("kit", "patient"):
                objective[var.index] = var.distance_m
            elif var.kind == "ambulance":
                objective[var.index] = self.config.mip_fleet_tiebreak
            elif var.kind.startswith("unmet"):
                objective[var.index] = self.config.mip_unmet_penalty

        lower = np.zeros(len(variables))
        upper = np.array([var.upper for var in variables], dtype=float)
        integrality = np.ones(len(variables))

        # Sparse constraint matrix.
        row_indices: List[int] = []
        col_indices: List[int] = []
        data_values: List[float] = []
        row_lower: List[float] = []
        row_upper: List[float] = []
        for row_index, (label, coefficients, lo, hi) in enumerate(rows):
            for column, value in coefficients.items():
                row_indices.append(row_index)
                col_indices.append(column)
                data_values.append(value)
            row_lower.append(lo)
            row_upper.append(hi)
        matrix = coo_matrix(
            (data_values, (row_indices, col_indices)),
            shape=(len(rows), len(variables)),
        ).tocsr()

        started = time.perf_counter()
        try:
            result = milp(
                c=objective,
                integrality=integrality,
                bounds=Bounds(lower, upper),
                constraints=LinearConstraint(matrix, row_lower, row_upper),
                options={
                    "time_limit": self.config.mip_time_limit_seconds,
                    "mip_rel_gap": self.config.mip_relative_gap,
                },
            )
        except Exception as exc:  # pragma: no cover - solver failure
            return NetworkPlan(
                status="solver-error",
                success=False,
                message=str(exc),
                variables=len(variables),
                constraints=len(rows),
                solver_seconds=time.perf_counter() - started,
                errors=["MILP solver error: {0}".format(exc)],
                blocked_links=blocked,
                background_over_capacity=background_over,
            )

        solver_seconds = time.perf_counter() - started
        if result.x is None:
            return NetworkPlan(
                status="infeasible",
                success=False,
                message=str(getattr(result, "message", "no solution")),
                variables=len(variables),
                constraints=len(rows),
                solver_seconds=solver_seconds,
                errors=["MILP returned no solution"],
                blocked_links=blocked,
                background_over_capacity=background_over,
            )

        x = np.rint(result.x).astype(int)
        kit_flows: List[Flow] = []
        patient_flows: List[Flow] = []
        for var in kit_vars:
            quantity = int(x[var.index])
            if quantity > 0 and var.route is not None:
                kit_flows.append(
                    Flow("kit", var.source, var.target, quantity, var.route)
                )
        for var in patient_vars:
            quantity = int(x[var.index])
            if quantity > 0 and var.route is not None:
                patient_flows.append(
                    Flow("patient", var.source, var.target, quantity, var.route)
                )
        ambulance_by_zone = {
            zone: int(x[var.index]) for zone, var in ambulance_vars.items()
        }
        unmet_kits = {
            zone: int(x[var.index]) for zone, var in unmet_kit_vars.items()
        }
        unmet_patients = {
            zone: int(x[var.index]) for zone, var in unmet_patient_vars.items()
        }

        assigned_kits: Dict[str, int] = {source: 0 for source in self.supplies}
        for flow in kit_flows:
            assigned_kits[flow.source] = assigned_kits.get(flow.source, 0) + (
                flow.quantity * self.config.kits_per_trip
            )
        unused_supply = {
            source: max(0, supply - assigned_kits.get(source, 0))
            for source, supply in self.supplies.items()
        }
        assigned_beds: Dict[str, int] = {hospital: 0 for hospital in self.beds}
        for flow in patient_flows:
            assigned_beds[flow.target] = assigned_beds.get(flow.target, 0) + flow.quantity
        unused_beds = {
            hospital: max(0, beds - assigned_beds.get(hospital, 0))
            for hospital, beds in self.beds.items()
        }

        # Independent lane-load reconstruction from the selected routes.
        lane_loads: Dict[str, LaneLoad] = {}
        for lane in sorted(set(lane_use) | set(self.data.background_lane_flow)):
            if lane not in self.graph.lane_info:
                continue
            capacity, edge_id, edge_type = self.lane_capacity(lane)
            background = float(self.data.background_lane_flow.get(lane, 0.0))
            ambulance = 0.0
            for flow in kit_flows + patient_flows:
                ambulance += flow.quantity * flow.route.lanes.count(lane)
            lane_loads[lane] = LaneLoad(
                lane_id=lane,
                edge_id=edge_id,
                edge_type=edge_type,
                background=background,
                ambulance=ambulance,
                capacity=capacity,
            )

        errors: List[str] = []
        checks: Dict[str, bool] = {}

        # Route validity and prohibited lanes.
        route_ok = True
        prohibited_ok = True
        for flow in kit_flows + patient_flows:
            if flow.route.prohibited_hits:
                prohibited_ok = False
                errors.append(
                    "selected route {0}->{1} uses a prohibited lane".format(
                        flow.source, flow.target
                    )
                )
            lanes = flow.route.lanes
            for left, right in zip(lanes, lanes[1:]):
                if right not in self.graph.successors.get(left, ()):
                    route_ok = False
                    errors.append(
                        "selected route {0}->{1} is not continuous at {2}->{3}".format(
                            flow.source, flow.target, left, right
                        )
                    )
            if abs(flow.route.recompute()[0] - flow.route.distance_m) > 1e-5:
                route_ok = False
                errors.append(
                    "selected route {0}->{1} has inconsistent distance".format(
                        flow.source, flow.target
                    )
                )
            for lane in lanes:
                if lane in self.router.prohibited:
                    prohibited_ok = False

        # Supply/demand checks.
        supply_ok = all(
            assigned_kits.get(source, 0) <= supply + 1e-9
            for source, supply in self.supplies.items()
        )
        kit_demand_ok = all(
            sum(
                flow.quantity * self.config.kits_per_trip
                for flow in kit_flows
                if flow.target == zone
            )
            + unmet_kits.get(zone, 0)
            == self.kit_demands.get(zone, 0)
            for zone in self.zone_ids
        )
        patient_demand_ok = all(
            sum(flow.quantity for flow in patient_flows if flow.source == zone)
            + unmet_patients.get(zone, 0)
            == self.patient_demands.get(zone, 0)
            for zone in self.zone_ids
        )
        bed_ok = all(
            assigned_beds.get(hospital, 0) <= beds + 1e-9
            for hospital, beds in self.beds.items()
        )
        fleet_ok = sum(ambulance_by_zone.values()) <= self.config.fleet_size
        zone_trip_ok = all(
            sum(flow.quantity for flow in kit_flows if flow.target == zone)
            + sum(flow.quantity for flow in patient_flows if flow.source == zone)
            <= ambulance_by_zone.get(zone, 0)
            for zone in self.zone_ids
        )
        road_ok = not any(load.over_capacity for load in lane_loads.values())
        integer_ok = all(
            abs(float(result.x[index]) - round(float(result.x[index]))) <= 1e-5
            for index in range(len(variables))
        )

        checks.update(
            {
                "solver_success": bool(result.success),
                "supply_within_limits": supply_ok,
                "kit_demand_matched": kit_demand_ok,
                "patient_demand_matched": patient_demand_ok,
                "bed_capacity_respected": bed_ok,
                "fleet_limit_respected": fleet_ok,
                "zone_trip_balance": zone_trip_ok,
                "road_capacity_respected": road_ok,
                "prohibited_lanes_avoided": prohibited_ok,
                "routes_continuous": route_ok,
                "integer_allocations": integer_ok,
                "demand_met": sum(unmet_kits.values()) == 0
                and sum(unmet_patients.values()) == 0,
            }
        )
        physical_checks = {
            name: value for name, value in checks.items() if name != "demand_met"
        }
        if not all(physical_checks.values()):
            errors.append("one or more independent network checks failed")
        if not result.success:
            errors.append("MILP status: {0}".format(getattr(result, "message", "unknown")))

        plan = NetworkPlan(
            status=(
                "optimal"
                if result.success and all(physical_checks.values()) and not errors
                and sum(unmet_kits.values()) + sum(unmet_patients.values()) == 0
                else "optimal-with-unmet-demand"
                if result.success and all(physical_checks.values()) and not errors
                else "not-optimal-or-failed"
            ),
            success=bool(result.success),
            message=str(getattr(result, "message", "")),
            solver_seconds=solver_seconds,
            variables=len(variables),
            constraints=len(rows),
            solver_objective=float(result.fun) if result.fun is not None else None,
            kit_flows=sorted(kit_flows, key=lambda f: (f.source, f.target)),
            patient_flows=sorted(patient_flows, key=lambda f: (f.source, f.target)),
            ambulance_by_zone=ambulance_by_zone,
            unmet_kits=unmet_kits,
            unmet_patients=unmet_patients,
            unused_supply=unused_supply,
            unused_beds=unused_beds,
            lane_loads=lane_loads,
            checks=checks,
            errors=errors,
            notes=[
                "The lane loads are reconstructed independently from the selected routes.",
                "Background flow is kept separate from the ambulance flow.",
                "Unmet variables make a shortage explicit instead of hiding it.",
            ],
            blocked_links=blocked,
            background_over_capacity=background_over,
        )
        return plan
