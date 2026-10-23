"""Emergency dispatch search: nearest suitable hospital by fastest time.

بحث الإرسال: أقرب مستشفى مناسب حسب أسرع زمن وصول داخل منطقة نقطة البداية.

The search follows the owner-approved rules:

1. determine the manual zone that contains the snapped start point;
2. visit facilities in that zone only, in increasing **travel time**;
3. skip facilities without a free emergency place;
4. skip facilities that do not provide the required specialty;
5. skip clinics and the owner-excluded dead-end destinations;
6. the first suitable facility is the result, with its lane-level route.

الترتيب: تحديد منطقة البداية يدوياً، ثم الأقرب زمنياً، ثم التحقق من المكان
الشاغر والتخصص واستبعاد العيادات والوجهات المسدودة.

Travel time comes from :class:`~assiut_hospitals.traveltime.TimeModel`.
Only free-flow time (length / speed) is used by the owner's decision; the
congestion hook stays disabled.

زمن الرحلة من نموذج الزمن (طول/سرعة)؛ الازدحام غير مفعّل بقرار المالك.
"""

from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .capacity import CapacityBook, load_capacity
from .config import Config, load_config
from .dataset import Dataset, HospitalRecord, load_dataset
from .dispatch_config import DispatchConfig, Zone, load_dispatch_config
from .netmodel import LaneGraph, Network, open_network
from .snapping import SnapResult, Snapper
from .traveltime import TimeModel

INF = float("inf")


class DispatchError(RuntimeError):
    """Raised when a dispatch request cannot be answered.

    خطأ في طلب الإرسال (نقطة غير صالحة، تخصص غير معروف، ...).
    """


# ---------------------------------------------------------------------------
# Result objects
# ---------------------------------------------------------------------------
@dataclass
class Origin:
    """Where the ambulance starts (requested point + snapped road point)."""

    lat: float
    lon: float
    edge_id: str
    pos: float
    pos_frac: float
    distance_m: float
    snapped_lat: float
    snapped_lon: float
    lanes: Tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "lat": round(self.lat, 7),
            "lon": round(self.lon, 7),
            "snapped_lat": round(self.snapped_lat, 7),
            "snapped_lon": round(self.snapped_lon, 7),
            "edge_id": self.edge_id,
            "pos": round(self.pos, 3),
            "snap_distance_m": round(self.distance_m, 2),
            "lanes": list(self.lanes),
        }


@dataclass
class RouteSegment:
    """One lane of the optimal route."""

    edge_id: str
    lane_id: str
    from_frac: float
    to_frac: float
    seconds: float
    length_m: float
    internal: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "edge": self.edge_id,
            "lane": self.lane_id,
            "from_frac": round(self.from_frac, 6),
            "to_frac": round(self.to_frac, 6),
            "seconds": round(self.seconds, 3),
            "length_m": round(self.length_m, 2),
            "internal": self.internal,
        }


@dataclass
class Route:
    """A complete lane-level route with its expected travel time."""

    segments: List[RouteSegment] = field(default_factory=list)
    seconds: float = 0.0
    length_m: float = 0.0

    @property
    def lanes(self) -> List[str]:
        return [segment.lane_id for segment in self.segments]

    @property
    def edges(self) -> List[str]:
        """Normal (non-internal) edges in travel order, consecutive duplicates merged.

        الشوارع العادية في مسار الرحلة بالترتيب.
        """
        result: List[str] = []
        for segment in self.segments:
            if segment.internal:
                continue
            if not result or result[-1] != segment.edge_id:
                result.append(segment.edge_id)
        return result

    @property
    def all_edges(self) -> List[str]:
        result: List[str] = []
        for segment in self.segments:
            if not result or result[-1] != segment.edge_id:
                result.append(segment.edge_id)
        return result

    def recompute(self) -> Tuple[float, float]:
        """Independently re-sum the segment costs.

        إعادة جمع أزمنة المقاطع للتحقق المستقل من الزمن الكلي.
        """
        return (
            math.fsum(segment.seconds for segment in self.segments),
            math.fsum(segment.length_m for segment in self.segments),
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "seconds": round(self.seconds, 3),
            "length_m": round(self.length_m, 1),
            "edges": self.edges,
            "all_edges": self.all_edges,
            "lanes": self.lanes,
            "segments": [segment.as_dict() for segment in self.segments],
        }


@dataclass
class Candidate:
    """One hospital evaluated from the ambulance origin."""

    slug: str
    name: str
    zone_id: str
    seconds: Optional[float]
    reachable: bool
    routable_flag: bool
    emergency: bool
    beds_free: int
    specialties: Tuple[str, ...]
    #: internal arrival details used to rebuild the route
    lane_id: str = ""
    kind: str = ""
    pred: Optional[str] = None
    frac: float = 0.0
    #: owner-approved exclusion (dead-end destination, ...), or ``None``
    excluded_reason: Optional[str] = None

    def reason_for(self, specialty: str) -> Optional[str]:
        """Why this candidate cannot be selected (``None`` if it can).

        سبب استبعاد المرشح، أو None إذا كان صالحاً.
        """
        if self.excluded_reason:
            return self.excluded_reason
        if not self.routable_flag:
            return "facility is not routable in the dataset"
        if not self.reachable:
            return "no lane-level route for an ambulance"
        if not self.emergency:
            return "no emergency department"
        if self.beds_free <= 0:
            return "no free emergency place"
        if specialty not in self.specialties:
            return "required specialty is not available"
        return None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "zone": self.zone_id,
            "seconds": None if self.seconds is None else round(self.seconds, 3),
            "reachable": self.reachable,
            "beds_free": self.beds_free,
            "specialties": list(self.specialties),
            "excluded": self.excluded_reason,
        }


@dataclass
class ZoneOutcome:
    """The winning hospital of one zone (or the reason there is none)."""

    zone_id: str
    zone_name: str
    winner: Optional[Candidate]
    checked: List[Dict[str, Any]] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "winner": self.winner.as_dict() if self.winner else None,
            "checked": self.checked,
            "note": self.note,
        }


@dataclass
class DispatchResult:
    """Full answer: per-zone results, the optimum, and its route."""

    origin: Origin
    specialty: str
    zones: List[ZoneOutcome]
    optimal: Optional[Candidate]
    route: Optional[Route]
    synthetic_capacity: bool
    capacity_source: str
    cost_model: Dict[str, Any]
    runtime_seconds: float
    search_scope: str = "start_zone_only"
    search_zone: str = ""
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "origin": self.origin.as_dict(),
            "specialty": self.specialty,
            "search_scope": self.search_scope,
            "search_zone": self.search_zone,
            "capacity_source": self.capacity_source,
            "synthetic_capacity": self.synthetic_capacity,
            "cost_model": self.cost_model,
            "zones": [zone.as_dict() for zone in self.zones],
            "optimal": (
                {
                    "hospital": self.optimal.name,
                    "slug": self.optimal.slug,
                    "zone": self.optimal.zone_id,
                    "seconds": round(self.optimal.seconds or 0.0, 3),
                    "route": self.route.as_dict() if self.route else None,
                }
                if self.optimal
                else None
            ),
            "runtime_seconds": round(self.runtime_seconds, 4),
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# The search
# ---------------------------------------------------------------------------
class Dispatcher:
    """Finds the fastest suitable hospital from any point on the map.

    يبحث من أي نقطة على الخريطة عن أسرع مستشفى مناسب داخل منطقة البداية فقط.
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        dataset: Optional[Dataset] = None,
        dispatch_config: Optional[DispatchConfig] = None,
        capacity: Optional[CapacityBook] = None,
        network: Optional[Network] = None,
        time_model: Optional[TimeModel] = None,
    ):
        self.config = config or load_config()
        self.dataset = dataset or load_dataset(self.config.dataset_file)
        self.dcfg = dispatch_config or load_dispatch_config()
        self.network = network or open_network(self.config.net_file)
        self.graph: LaneGraph = self.network.lane_graph
        self.capacity = capacity or load_capacity(
            self.dcfg.capacity_file,
            self.dataset,
            clinics_as_emergency=self.dcfg.clinics_as_emergency,
        )
        self.model = time_model or TimeModel(
            self.network, vehicle_class=self.dcfg.vehicle_class
        )
        self.snapper = Snapper(
            self.network, vehicle_class=self.dcfg.vehicle_class
        )
        self.vehicle_class = self.dcfg.vehicle_class
        #: structural dead-end test: the main strongly connected lane component
        self.main_component: set = self.graph.main_component(self.vehicle_class)

    # ------------------------------------------------------------- public API
    def validate(self) -> List[str]:
        """All configuration problems (zones + capacity), empty when valid.

        كل مشاكل الإعدادات؛ قائمة فارغة تعني أن الإعداد صحيح.
        """
        errors = list(self.dcfg.validate(self.dataset))
        errors.extend(self.capacity.errors)
        missing = set(self.dcfg.specialty_catalog) - set(self.capacity.catalog)
        if missing:
            errors.append(
                "specialties in config but not in the capacity file: {0}".format(
                    ", ".join(sorted(missing))
                )
            )
        return errors

    def search(
        self,
        lat: float,
        lon: float,
        specialty: str,
        verify: bool = True,
    ) -> DispatchResult:
        """Run the search under the approved owner rules.

        ينفذ البحث حسب قرارات المالك: منطقة البداية فقط، ثم أول مستشفى مناسب
        حسب الزمن، مع استبعاد العيادات والوجهات المسدودة.

        The zone is taken from the snapped start point.  If the point lies on a
        shared boundary the request is rejected instead of choosing a zone
        automatically.
        """
        started = time.perf_counter()
        if specialty not in self.dcfg.specialty_catalog:
            raise DispatchError(
                "unknown specialty '{0}' (catalog: {1})".format(
                    specialty, ", ".join(self.dcfg.specialty_catalog)
                )
            )

        origin = self._origin(lat, lon)

        if self.dcfg.search_scope == "start_zone_only":
            containing = self.dcfg.zones_for_point(
                origin.snapped_lat, origin.snapped_lon
            )
            if not containing:
                raise DispatchError(
                    "the snapped start point ({0:.6f}, {1:.6f}) is outside all "
                    "four zones".format(origin.snapped_lat, origin.snapped_lon)
                )
            if len(containing) > 1:
                raise DispatchError(
                    "the snapped start point lies on a boundary between zones "
                    "{0}; move the start point so the zone is unambiguous".format(
                        ", ".join(zone.id for zone in containing)
                    )
                )
            search_zones = containing
        else:
            search_zones = list(self.dcfg.zones)

        distances, offsets, previous = self._dijkstra(origin)
        entries = self._entry_times(distances, offsets)

        candidates: List[Candidate] = []
        wanted = {zone.id for zone in search_zones}
        for record in self.dataset.hospitals:
            zone = self.dcfg.zone_of(record.slug)
            if zone is None or zone.id not in wanted:
                continue
            candidates.append(
                self._candidate(record, zone, origin, distances, offsets, entries)
            )

        outcomes: List[ZoneOutcome] = []
        for zone in search_zones:
            in_zone = [c for c in candidates if c.zone_id == zone.id]
            outcomes.append(self._pick(zone, in_zone, specialty))

        winners = [outcome.winner for outcome in outcomes if outcome.winner is not None]
        optimal = (
            min(winners, key=lambda c: (c.seconds if c.seconds is not None else INF, c.slug))
            if winners
            else None
        )

        route = None
        if optimal is not None:
            route = self._route_for(optimal, origin, offsets, previous)
            if verify:
                self._verify_route(route, optimal)

        elapsed = time.perf_counter() - started
        notes: List[str] = []
        if self.capacity.synthetic:
            notes.append(
                "SYNTHETIC emergency capacity/specialty data - replace with real data "
                "before any operational use."
            )
        if self.dcfg.search_scope == "start_zone_only":
            notes.append(
                "Owner decision G: search is restricted to the zone containing "
                "the snapped start point ({0}).".format(search_zones[0].id)
            )
        if self.dcfg.excluded_destinations:
            notes.append(
                "Owner decision D: {0} dead-end destination(s) excluded: {1}.".format(
                    len(self.dcfg.excluded_destinations),
                    ", ".join(sorted(self.dcfg.excluded_destinations)),
                )
            )
        if not self.dcfg.clinics_as_emergency:
            notes.append("Owner decision C: clinics are not emergency facilities.")
        notes.append("Owner decision: free-flow travel time only; no congestion adjustment.")
        search_zone = (
            "{0} - {1}".format(search_zones[0].id, search_zones[0].name)
            if self.dcfg.search_scope == "start_zone_only"
            else "all zones"
        )
        return DispatchResult(
            origin=origin,
            specialty=specialty,
            zones=outcomes,
            optimal=optimal,
            route=route,
            synthetic_capacity=self.capacity.synthetic,
            capacity_source=self.capacity.source,
            cost_model=self.model.describe(),
            runtime_seconds=elapsed,
            search_scope=self.dcfg.search_scope,
            search_zone=search_zone,
            notes=notes,
        )

    # --------------------------------------------------------------- geometry
    def _origin(self, lat: float, lon: float) -> Origin:
        """Snap the requested start point onto a usable emergency lane.

        إسقاط نقطة البداية على أقرب شارع يسمح بمرور الإسعاف.
        """
        snap: SnapResult = self.snapper.snap_geo(lon, lat)
        if not snap.edge_id:
            raise DispatchError("no road found near the requested point")
        if not snap.usable:
            raise DispatchError(
                "nearest road '{0}' is not usable by a vehicle of class '{1}'".format(
                    snap.edge_id, self.vehicle_class
                )
            )
        if snap.distance_m > self.dcfg.max_origin_snap_m:
            raise DispatchError(
                "requested point is {0:.1f} m from the nearest usable road "
                "(limit {1:.0f} m)".format(
                    snap.distance_m, self.dcfg.max_origin_snap_m
                )
            )
        edge = self.network.edges[snap.edge_id]
        lanes = tuple(self.graph.usable_lanes(snap.edge_id, self.vehicle_class))
        if not lanes:
            raise DispatchError(
                "edge '{0}' has no lane usable by '{1}'".format(
                    snap.edge_id, self.vehicle_class
                )
            )
        if self.dcfg.refuse_dead_end_starts and self.main_component:
            reachable = self.graph.reachable_lanes(
                [snap.edge_id], self.vehicle_class
            )
            if not (reachable & self.main_component):
                raise DispatchError(
                    "requested start is on a dead-end component at edge '{0}'; "
                    "it cannot reach the main road network, so no dispatch route "
                    "can leave it (owner decision I)".format(snap.edge_id)
                )
        frac = snap.pos / edge.length if edge.length > 0 else 0.0
        frac = 0.0 if frac < 0.0 else (1.0 if frac > 1.0 else frac)
        sx, sy = snap.x, snap.y
        snapped_lon, snapped_lat = self.network.to_geo(sx, sy)
        return Origin(
            lat=lat,
            lon=lon,
            edge_id=snap.edge_id,
            pos=snap.pos,
            pos_frac=frac,
            distance_m=snap.distance_m,
            snapped_lat=snapped_lat,
            snapped_lon=snapped_lon,
            lanes=lanes,
        )

    # ---------------------------------------------------------------- routing
    def _dijkstra(
        self, origin: Origin
    ) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, Optional[str]]]:
        """Dijkstra over the class-aware lane graph, weighted by travel time.

        خوارزمية ديكسترا على الرسم الشبكي للمسارات بأوزان زمنية.

        ``dist[lane]`` is the time to reach the lane's start (or the origin's
        offset when the lane is one of the starting lanes).
        ``offset[lane]`` is the fraction already traversed at that point.
        """
        dist: Dict[str, float] = {}
        offset: Dict[str, float] = {}
        previous: Dict[str, Optional[str]] = {}
        heap: List[Tuple[float, str]] = []

        for lane in origin.lanes:
            dist[lane] = 0.0
            offset[lane] = origin.pos_frac
            previous[lane] = None
            heapq.heappush(heap, (0.0, lane))

        while heap:
            current_dist, lane = heapq.heappop(heap)
            if current_dist > dist.get(lane, INF) + 1e-9:
                continue
            remaining = self.model.lane_time(
                lane, offset.get(lane, 0.0), 1.0
            )
            for successor in self.graph.successors.get(lane, ()):
                if not self.graph.lane_allowed(successor, self.vehicle_class):
                    continue
                candidate = current_dist + remaining
                if candidate + 1e-9 < dist.get(successor, INF):
                    dist[successor] = candidate
                    offset[successor] = 0.0
                    previous[successor] = lane
                    heapq.heappush(heap, (candidate, successor))
        return dist, offset, previous

    def _entry_times(
        self, distances: Dict[str, float], offsets: Dict[str, float]
    ) -> Dict[str, Tuple[float, Optional[str]]]:
        """Cheapest way to *enter* each lane, with the predecessor used.

        أقل زمن لدخول كل مسار مع المسار السابق الذي حقق هذا الزمن.
        """
        entries: Dict[str, Tuple[float, Optional[str]]] = {}
        for lane, predecessors in self.graph.predecessors.items():
            best = INF
            best_pred: Optional[str] = None
            for pred in predecessors:
                if pred not in distances:
                    continue
                candidate = distances[pred] + self.model.lane_time(
                    pred, offsets.get(pred, 0.0), 1.0
                )
                if candidate < best:
                    best = candidate
                    best_pred = pred
            if best_pred is not None:
                entries[lane] = (best, best_pred)
        return entries

    def _blank_candidate(self, record: HospitalRecord, zone: Zone) -> Candidate:
        """Capacity/zone part of a candidate, before any routing result.

        بيانات السعة والمنطقة قبل حساب المسار؛ تُستخدم أيضاً في مقارنة
        الخوارزميات التي تحسب المسار بطريقة مختلفة.
        """
        capacity = self.capacity.get(record.slug)
        return Candidate(
            slug=record.slug,
            name=record.display_name,
            zone_id=zone.id,
            seconds=None,
            reachable=False,
            routable_flag=record.routable,
            emergency=bool(capacity and self.capacity.effective_emergency(record)),
            beds_free=int(capacity.beds_free) if capacity else 0,
            specialties=tuple(sorted(capacity.specialties)) if capacity else (),
            excluded_reason=self.dcfg.excluded_reason(record.slug),
        )

    def _candidate(
        self,
        record: HospitalRecord,
        zone: Zone,
        origin: Origin,
        distances: Dict[str, float],
        offsets: Dict[str, float],
        entries: Dict[str, Tuple[float, Optional[str]]],
    ) -> Candidate:
        """Compute the travel time from the origin to one hospital entrance.

        حساب زمن الوصول من نقطة البداية إلى مدخل مستشفى واحد.
        """
        base = self._blank_candidate(record, zone)
        if not record.routable or not record.snap.edge_id:
            return base

        edge = self.network.edges.get(record.snap.edge_id)
        if edge is None or edge.length <= 0:
            return base
        frac = record.snap.pos / edge.length
        frac = 0.0 if frac < 0.0 else (1.0 if frac > 1.0 else frac)

        best = INF
        best_lane = ""
        best_kind = ""
        best_pred: Optional[str] = None

        for lane in self.graph.usable_lanes(edge.id, self.vehicle_class):
            # (a) the ambulance already sits on this lane: drive forward only
            if lane in origin.lanes:
                start_frac = offsets.get(lane, origin.pos_frac)
                if frac >= start_frac:
                    candidate = self.model.lane_time(lane, start_frac, frac)
                    if candidate < best:
                        best = candidate
                        best_lane = lane
                        best_kind = "same"
                        best_pred = None
            # (b) enter the lane from a predecessor (this also covers a loop
            #     back onto the origin lane when the hospital is behind us)
            entry = entries.get(lane)
            if entry is not None:
                candidate = entry[0] + self.model.lane_time(lane, 0.0, frac)
                if candidate < best:
                    best = candidate
                    best_lane = lane
                    best_kind = "entry"
                    best_pred = entry[1]

        if not best_lane:
            return base
        base.seconds = best
        base.reachable = True
        base.lane_id = best_lane
        base.kind = best_kind
        base.pred = best_pred
        base.frac = frac
        return base

    # ----------------------------------------------------------------- zones
    def _pick(
        self, zone: Zone, candidates: Sequence[Candidate], specialty: str
    ) -> ZoneOutcome:
        """Pick the first suitable hospital in one zone (requirement 4a-d).

        اختيار أول مستشفى مناسب داخل المنطقة بعد الترتيب حسب الزمن.
        """
        ordered = sorted(
            candidates,
            key=lambda c: (c.seconds if c.seconds is not None else INF, c.slug),
        )
        checked: List[Dict[str, Any]] = []
        winner: Optional[Candidate] = None
        for candidate in ordered:
            reason = candidate.reason_for(specialty)
            checked.append(
                {
                    "slug": candidate.slug,
                    "name": candidate.name,
                    "seconds": (
                        None if candidate.seconds is None else round(candidate.seconds, 3)
                    ),
                    "beds_free": candidate.beds_free,
                    "accepted": reason is None,
                    "reason": reason or "selected",
                    "excluded": candidate.excluded_reason,
                }
            )
            if reason is None:
                winner = candidate
                break
        note = "" if winner else "no suitable emergency department in this zone"
        return ZoneOutcome(
            zone_id=zone.id,
            zone_name=zone.name,
            winner=winner,
            checked=checked,
            note=note,
        )

    # ---------------------------------------------------------------- routes
    def route_geometry(self, route: Optional[Route]) -> List[List[float]]:
        """Geo polyline (``[[lat, lon], ...]``) for drawing the route.

        يحوّل مسار الرحلة إلى نقاط جغرافية لرسمه على الخريطة.
        """
        if route is None:
            return []
        points: List[List[float]] = []
        for edge_id in route.all_edges:
            edge = self.network.edges.get(edge_id)
            if edge is None or len(edge.shape) < 2:
                continue
            for x, y in edge.shape:
                lon, lat = self.network.to_geo(x, y)
                point = [round(lat, 6), round(lon, 6)]
                if not points or points[-1] != point:
                    points.append(point)
        return points

    def _route_for(
        self,
        candidate: Candidate,
        origin: Origin,
        offsets: Dict[str, float],
        previous: Dict[str, Optional[str]],
    ) -> Route:
        """Rebuild the lane sequence of the winning candidate and time it.

        إعادة بناء تسلسل المسارات للمرشح الفائز وحساب زمنه.
        """
        if candidate.kind == "same":
            lanes = [candidate.lane_id]
        else:
            if candidate.pred is None:
                raise DispatchError("cannot rebuild route without a predecessor")
            lanes = self._path_to(candidate.pred, previous) + [candidate.lane_id]

        segments: List[RouteSegment] = []
        for index, lane in enumerate(lanes):
            edge_id = self.graph.edge_of_lane(lane) or ""
            from_frac = offsets.get(lane, 0.0) if index == 0 else 0.0
            to_frac = candidate.frac if index == len(lanes) - 1 else 1.0
            seconds = self.model.lane_time(lane, from_frac, to_frac)
            length = self.model.length(lane) * (to_frac - from_frac)
            segments.append(
                RouteSegment(
                    edge_id=edge_id,
                    lane_id=lane,
                    from_frac=from_frac,
                    to_frac=to_frac,
                    seconds=seconds,
                    length_m=length,
                    internal=edge_id.startswith(":"),
                )
            )
        route = Route(segments=segments)
        route.seconds, route.length_m = route.recompute()
        return route

    def _path_to(
        self, lane: str, previous: Dict[str, Optional[str]]
    ) -> List[str]:
        """Walk the predecessor chain back to the origin lane (inclusive).

        تتبع سلسلة المسارات السابقة حتى نقطة البداية.
        """
        chain: List[str] = []
        seen = set()
        current: Optional[str] = lane
        while current is not None and current not in seen:
            chain.append(current)
            seen.add(current)
            current = previous.get(current)
        chain.reverse()
        return chain

    # ------------------------------------------------------------ validation
    def _verify_route(self, route: Route, candidate: Candidate) -> None:
        """Check the route independently before returning it (rule 7).

        تحقق مستقل: مجموع أزمنة المقاطع، استمرارية المسارات، وصلاحية التصنيف.
        """
        total, _length = route.recompute()
        if candidate.seconds is None or abs(total - candidate.seconds) > 1e-6:
            raise DispatchError(
                "route time mismatch: computed {0:.6f}s, expected {1:.6f}s".format(
                    total, candidate.seconds or 0.0
                )
            )
        for index, segment in enumerate(route.segments):
            if not self.graph.lane_allowed(segment.lane_id, self.vehicle_class):
                raise DispatchError(
                    "route uses lane '{0}' that does not allow '{1}'".format(
                        segment.lane_id, self.vehicle_class
                    )
                )
            if index + 1 < len(route.segments):
                follower = route.segments[index + 1].lane_id
                if follower not in self.graph.successors.get(segment.lane_id, ()):
                    raise DispatchError(
                        "route is not connected: {0} -> {1}".format(
                            segment.lane_id, follower
                        )
                    )
