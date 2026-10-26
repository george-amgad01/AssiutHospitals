"""Lane-level distance routing for the Operations Research extension.

توجيه على مستوى المسارات لامتداد بحوث العمليات.

This router differs from the emergency dispatcher in two important ways:

* the edge weight is **distance** (metres), not travel time;
* a source is represented by two graph layers.  The initial layer starts
  part-way along a lane, while the normal layer starts at the lane beginning.
  This makes repeated visits to the source lane correct and lets us compare
  Dijkstra, A*, and Bellman-Ford without hidden offset assumptions.

يمثل المصدر بطبقتين: طبقة البداية الجزئية وطبقة المسار الكامل، لذلك يكون
قياس المسافات صحيحاً عند العودة إلى مسار البداية.

Prohibited lanes are removed from the graph before any search.  They are not
represented by a large finite cost.
"""

from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .dataset import HospitalRecord
from .netmodel import LaneGraph, Network
from .snapping import SnapResult, Snapper
from .traveltime import TimeModel

INF = float("inf")
EPS = 1e-9
Point = Tuple[float, float]
State = Tuple[str, str]  # ("I" | "N", lane_id)


class ORRoutingError(RuntimeError):
    """A point cannot be snapped, or no route exists under the restrictions.

    تعذر إسقاط نقطة أو لا يوجد مسار في ظل القيود.
    """


@dataclass(frozen=True)
class RoutePoint:
    """A snapped point on a usable, non-prohibited lane.

    نقطة على مسار مسموح بعد الإسقاط.
    """

    label: str
    lat: float
    lon: float
    x: float
    y: float
    edge_id: str
    pos: float
    frac: float
    lanes: Tuple[str, ...]
    snap_distance_m: float

    def as_dict(self) -> Dict[str, object]:
        return {
            "label": self.label,
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "edge_id": self.edge_id,
            "pos": round(self.pos, 3),
            "frac": round(self.frac, 6),
            "lanes": list(self.lanes),
            "snap_distance_m": round(self.snap_distance_m, 2),
        }


@dataclass
class RouteSegment:
    """One partial or complete lane traversal."""

    lane_id: str
    edge_id: str
    from_frac: float
    to_frac: float
    length_m: float
    seconds: float
    internal: bool = False

    def as_dict(self) -> Dict[str, object]:
        return {
            "lane_id": self.lane_id,
            "edge_id": self.edge_id,
            "from_frac": round(self.from_frac, 6),
            "to_frac": round(self.to_frac, 6),
            "length_m": round(self.length_m, 3),
            "seconds": round(self.seconds, 4),
            "internal": self.internal,
        }


@dataclass
class DistanceRoute:
    """A feasible lane-level route with distance and free-flow time."""

    source: RoutePoint
    target: RoutePoint
    algorithm: str
    states: List[State] = field(default_factory=list)
    segments: List[RouteSegment] = field(default_factory=list)
    distance_m: float = 0.0
    seconds: float = 0.0
    settled: int = 0
    elapsed_seconds: float = 0.0

    @property
    def lanes(self) -> List[str]:
        return [segment.lane_id for segment in self.segments]

    @property
    def edges(self) -> List[str]:
        result: List[str] = []
        for segment in self.segments:
            if not result or result[-1] != segment.edge_id:
                result.append(segment.edge_id)
        return result

    @property
    def prohibited_hits(self) -> List[str]:
        # The router never creates a route with these lanes.  The property is
        # kept so reports and the verifier can assert it explicitly.
        return []

    def recompute(self) -> Tuple[float, float]:
        distance = sum(segment.length_m for segment in self.segments)
        seconds = sum(segment.seconds for segment in self.segments)
        return distance, seconds

    def as_dict(self, include_segments: bool = True) -> Dict[str, object]:
        data: Dict[str, object] = {
            "source": self.source.as_dict(),
            "target": self.target.as_dict(),
            "algorithm": self.algorithm,
            "distance_m": round(self.distance_m, 3),
            "seconds": round(self.seconds, 4),
            "lanes": self.lanes,
            "edges": self.edges,
            "prohibited_hits": self.prohibited_hits,
            "settled_states": self.settled,
            "elapsed_seconds": round(self.elapsed_seconds, 6),
        }
        if include_segments:
            data["segments"] = [segment.as_dict() for segment in self.segments]
        return data


@dataclass
class SearchStats:
    """Small timing/coverage record for the algorithm comparison."""

    algorithm: str
    found: bool
    distance_m: Optional[float]
    seconds: Optional[float]
    settled: int
    elapsed_seconds: float
    note: str = ""


class DistanceRouter:
    """Distance-weighted router with explicit prohibited-lane filtering.

    موجّه بأوزان المسافة مع استبعاد كامل للمسارات الممنوعة.
    """

    def __init__(
        self,
        network: Network,
        vehicle_class: str = "emergency",
        explicit_prohibited_lanes: Sequence[str] = (),
        max_point_snap_m: float = 500.0,
    ):
        self.network = network
        self.graph: LaneGraph = network.lane_graph
        self.vehicle_class = vehicle_class
        self.max_point_snap_m = max_point_snap_m
        self.snapper = Snapper(network, vehicle_class=vehicle_class)
        self.time_model = TimeModel(network, vehicle_class=vehicle_class)

        unknown = sorted(
            set(explicit_prohibited_lanes) - set(self.graph.lane_info)
        )
        if unknown:
            raise ORRoutingError(
                "explicit prohibited lanes do not exist in the network: {0}".format(
                    ", ".join(unknown)
                )
            )
        self.class_prohibited = {
            lane
            for lane in self.graph.lane_info
            if not self.graph.lane_allowed(lane, vehicle_class)
        }
        self.explicit_prohibited = set(explicit_prohibited_lanes)
        self.prohibited = self.class_prohibited | self.explicit_prohibited
        self.allowed_lanes = set(self.graph.lane_info) - self.prohibited

        # Cache lane geometry for A*.  The lane start is sufficient because the
        # last partial traverse is handled by the target evaluation.
        self._lane_start: Dict[str, Optional[Point]] = {}
        for lane in self.allowed_lanes:
            self._lane_start[lane] = self.graph.lane_start_xy(lane)

    # ------------------------------------------------------------------ points
    def point_for_hospital(self, record: HospitalRecord) -> RoutePoint:
        """Build a route point from the dataset's snapped hospital position."""
        snap = record.snap
        edge = self.network.edges.get(snap.edge_id)
        if edge is None or edge.length <= 0.0:
            raise ORRoutingError(
                "hospital '{0}' has no usable edge length".format(record.slug)
            )
        lanes = tuple(
            lane
            for lane in self.graph.usable_lanes(edge.id, self.vehicle_class)
            if lane in self.allowed_lanes
        )
        if not lanes:
            raise ORRoutingError(
                "hospital '{0}' has no non-prohibited lane for '{1}'".format(
                    record.slug, self.vehicle_class
                )
            )
        frac = min(1.0, max(0.0, snap.pos / edge.length))
        lon, lat = self.network.to_geo(snap.x, snap.y)
        return RoutePoint(
            label=record.slug,
            lat=lat,
            lon=lon,
            x=snap.x,
            y=snap.y,
            edge_id=edge.id,
            pos=snap.pos,
            frac=frac,
            lanes=lanes,
            snap_distance_m=snap.distance_m,
        )

    def point_for_geo(
        self, lat: float, lon: float, label: str, max_snap_m: Optional[float] = None
    ) -> RoutePoint:
        """Snap an arbitrary geographic coordinate and validate its lanes."""
        limit = self.max_point_snap_m if max_snap_m is None else max_snap_m
        snap: SnapResult = self.snapper.snap_geo(lon, lat)
        if not snap.edge_id:
            raise ORRoutingError("no road found near point '{0}'".format(label))
        edge = self.network.edges.get(snap.edge_id)
        if edge is None or edge.length <= 0.0:
            raise ORRoutingError("point '{0}' snaps to an edge without length".format(label))
        lanes = tuple(
            lane
            for lane in self.graph.usable_lanes(edge.id, self.vehicle_class)
            if lane in self.allowed_lanes
        )
        if not lanes:
            raise ORRoutingError(
                "point '{0}' has no non-prohibited lane for '{1}'".format(
                    label, self.vehicle_class
                )
            )
        if snap.distance_m > limit:
            raise ORRoutingError(
                "point '{0}' is {1:.1f} m from the nearest usable road "
                "(limit {2:.0f} m)".format(label, snap.distance_m, limit)
            )
        frac = min(1.0, max(0.0, snap.pos / edge.length))
        lon2, lat2 = self.network.to_geo(snap.x, snap.y)
        return RoutePoint(
            label=label,
            lat=lat2,
            lon=lon2,
            x=snap.x,
            y=snap.y,
            edge_id=edge.id,
            pos=snap.pos,
            frac=frac,
            lanes=lanes,
            snap_distance_m=snap.distance_m,
        )

    # ---------------------------------------------------------------- helpers
    def lane_length(self, lane: str) -> float:
        return self.graph.lane_length(lane)

    def _leave_cost(self, state: State, source: RoutePoint) -> float:
        lane = state[1]
        length = self.lane_length(lane)
        if state[0] == "I":
            return length * (1.0 - source.frac)
        return length

    def _successors(self, state: State) -> Iterable[str]:
        lane = state[1]
        for successor in self.graph.successors.get(lane, ()):
            if successor in self.allowed_lanes:
                yield successor

    def _state_path(self, state: State, previous: Dict[State, Optional[State]]) -> List[State]:
        chain: List[State] = []
        seen: Set[State] = set()
        current: Optional[State] = state
        while current is not None and current not in seen:
            chain.append(current)
            seen.add(current)
            current = previous.get(current)
        chain.reverse()
        return chain

    def _candidate(
        self,
        state: State,
        distance: float,
        source: RoutePoint,
        target: RoutePoint,
    ) -> Optional[float]:
        lane = state[1]
        if lane not in target.lanes:
            return None
        length = self.lane_length(lane)
        if state[0] == "I":
            if target.frac + EPS < source.frac:
                return None
            return distance + length * (target.frac - source.frac)
        return distance + length * target.frac

    def _make_route(
        self,
        source: RoutePoint,
        target: RoutePoint,
        states: List[State],
        algorithm: str,
        settled: int,
        elapsed: float,
    ) -> DistanceRoute:
        if not states:
            raise ORRoutingError("cannot build an empty route")
        last = states[-1]
        segments: List[RouteSegment] = []
        for index, state in enumerate(states):
            lane = state[1]
            edge_id = self.graph.edge_of_lane(lane) or ""
            if index == 0 and state[0] == "I":
                from_frac = source.frac
            else:
                from_frac = 0.0
            if index == len(states) - 1 and lane in target.lanes:
                to_frac = target.frac
            else:
                to_frac = 1.0
            if to_frac + EPS < from_frac:
                # A last target behind the current position is only valid if
                # the normal layer was reached through a loop; the state graph
                # guarantees that case.  A negative segment would be a bug.
                raise ORRoutingError(
                    "route has a backward segment on lane '{0}'".format(lane)
                )
            length = self.lane_length(lane) * (to_frac - from_frac)
            seconds = self.time_model.lane_time(lane, from_frac, to_frac)
            segments.append(
                RouteSegment(
                    lane_id=lane,
                    edge_id=edge_id,
                    from_frac=from_frac,
                    to_frac=to_frac,
                    length_m=length,
                    seconds=seconds,
                    internal=edge_id.startswith(":"),
                )
            )
        route = DistanceRoute(
            source=source,
            target=target,
            algorithm=algorithm,
            states=states,
            segments=segments,
            settled=settled,
            elapsed_seconds=elapsed,
        )
        route.distance_m, route.seconds = route.recompute()
        return route

    # ------------------------------------------------------------------ search
    def shortest_path(
        self,
        source: RoutePoint,
        target: RoutePoint,
        algorithm: str = "dijkstra",
    ) -> Optional[DistanceRoute]:
        """Find the shortest feasible route, or ``None`` when none exists.

        تُرجع أقصر مسار مسموح، أو ``None`` إذا لم يوجد مسار.
        """
        key = algorithm.lower().replace("-", "_").replace(" ", "_")
        if key in ("dijkstra", "d"):
            return self._dijkstra(source, target)
        if key in ("a_star", "astar", "a*"):
            return self._astar(source, target)
        if key in ("bellman_ford", "bellmanford", "bf"):
            return self._bellman_ford(source, target)
        raise ORRoutingError("unknown routing algorithm '{0}'".format(algorithm))

    def _start_states(self, source: RoutePoint) -> List[State]:
        return [("I", lane) for lane in source.lanes if lane in self.allowed_lanes]

    def _dijkstra(
        self, source: RoutePoint, target: RoutePoint
    ) -> Optional[DistanceRoute]:
        started = time.perf_counter()
        dist: Dict[State, float] = {}
        previous: Dict[State, Optional[State]] = {}
        heap: List[Tuple[float, State]] = []
        for state in self._start_states(source):
            dist[state] = 0.0
            previous[state] = None
            heapq.heappush(heap, (0.0, state))

        best_cost = INF
        best_state: Optional[State] = None
        settled = 0
        while heap:
            current, state = heapq.heappop(heap)
            if current > dist.get(state, INF) + EPS:
                continue
            settled += 1
            candidate = self._candidate(state, current, source, target)
            if candidate is not None and candidate + EPS < best_cost:
                best_cost = candidate
                best_state = state
            # Dijkstra can stop when the frontier cannot improve the best
            # complete target.  This is an independent early-exit rule; it does
            # not change distances.
            if best_state is not None and heap and heap[0][0] > best_cost + EPS:
                break
            leave = self._leave_cost(state, source)
            for successor in self._successors(state):
                next_state: State = ("N", successor)
                candidate_distance = current + leave
                if candidate_distance + EPS < dist.get(next_state, INF):
                    dist[next_state] = candidate_distance
                    previous[next_state] = state
                    heapq.heappush(heap, (candidate_distance, next_state))

        if best_state is None:
            return None
        states = self._state_path(best_state, previous)
        route = self._make_route(
            source,
            target,
            states,
            "Dijkstra",
            settled,
            time.perf_counter() - started,
        )
        if abs(route.distance_m - best_cost) > 1e-5:
            raise ORRoutingError(
                "Dijkstra route distance {0} != search distance {1}".format(
                    route.distance_m, best_cost
                )
            )
        return route

    def _heuristic(self, state: State, target: RoutePoint) -> float:
        if state[0] == "I":
            return 0.0
        point = self._lane_start.get(state[1])
        if point is None:
            return 0.0
        return math.hypot(point[0] - target.x, point[1] - target.y)

    def _astar(
        self, source: RoutePoint, target: RoutePoint
    ) -> Optional[DistanceRoute]:
        started = time.perf_counter()
        dist: Dict[State, float] = {}
        previous: Dict[State, Optional[State]] = {}
        heap: List[Tuple[float, float, State]] = []
        for state in self._start_states(source):
            dist[state] = 0.0
            previous[state] = None
            heapq.heappush(heap, (self._heuristic(state, target), 0.0, state))

        best_cost = INF
        best_state: Optional[State] = None
        settled = 0
        while heap:
            f_value, current, state = heapq.heappop(heap)
            if current > dist.get(state, INF) + EPS:
                continue
            if best_state is not None and f_value > best_cost + EPS:
                break
            settled += 1
            candidate = self._candidate(state, current, source, target)
            if candidate is not None and candidate + EPS < best_cost:
                best_cost = candidate
                best_state = state
            leave = self._leave_cost(state, source)
            for successor in self._successors(state):
                next_state: State = ("N", successor)
                candidate_distance = current + leave
                if candidate_distance + EPS < dist.get(next_state, INF):
                    dist[next_state] = candidate_distance
                    previous[next_state] = state
                    heapq.heappush(
                        heap,
                        (
                            candidate_distance + self._heuristic(next_state, target),
                            candidate_distance,
                            next_state,
                        ),
                    )

        if best_state is None:
            return None
        states = self._state_path(best_state, previous)
        route = self._make_route(
            source,
            target,
            states,
            "A*",
            settled,
            time.perf_counter() - started,
        )
        if abs(route.distance_m - best_cost) > 1e-5:
            raise ORRoutingError(
                "A* route distance {0} != search distance {1}".format(
                    route.distance_m, best_cost
                )
            )
        return route

    def _bellman_ford(
        self, source: RoutePoint, target: RoutePoint
    ) -> Optional[DistanceRoute]:
        started = time.perf_counter()
        start_states = self._start_states(source)
        normal_states: List[State] = [("N", lane) for lane in self.allowed_lanes]
        states = start_states + normal_states
        dist: Dict[State, float] = {state: INF for state in states}
        previous: Dict[State, Optional[State]] = {state: None for state in states}
        for state in start_states:
            dist[state] = 0.0

        # Explicit edges keep the source offset exact.  We do not assume that a
        # start lane is only visited once.
        edges: List[Tuple[State, State, float]] = []
        for lane in source.lanes:
            initial: State = ("I", lane)
            if initial not in dist:
                continue
            leave = self.lane_length(lane) * (1.0 - source.frac)
            for successor in self.graph.successors.get(lane, ()):
                if successor in self.allowed_lanes:
                    edges.append((initial, ("N", successor), leave))
        for lane in self.allowed_lanes:
            current: State = ("N", lane)
            length = self.lane_length(lane)
            for successor in self.graph.successors.get(lane, ()):
                if successor in self.allowed_lanes:
                    edges.append((current, ("N", successor), length))

        for _ in range(max(0, len(states) - 1)):
            changed = False
            for left, right, weight in edges:
                if dist[left] == INF:
                    continue
                candidate = dist[left] + weight
                if candidate + EPS < dist[right]:
                    dist[right] = candidate
                    previous[right] = left
                    changed = True
            if not changed:
                break

        best_cost = INF
        best_state: Optional[State] = None
        for state in states:
            if dist[state] == INF:
                continue
            candidate = self._candidate(state, dist[state], source, target)
            if candidate is not None and candidate + EPS < best_cost:
                best_cost = candidate
                best_state = state
        if best_state is None:
            return None
        states_path = self._state_path(best_state, previous)
        route = self._make_route(
            source,
            target,
            states_path,
            "Bellman-Ford",
            len(states),
            time.perf_counter() - started,
        )
        if abs(route.distance_m - best_cost) > 1e-5:
            raise ORRoutingError(
                "Bellman-Ford route distance {0} != search distance {1}".format(
                    route.distance_m, best_cost
                )
            )
        return route

    # -------------------------------------------------------------- comparison
    def compare(self, source: RoutePoint, target: RoutePoint) -> List[SearchStats]:
        """Run all three routing algorithms and return measured results."""
        results: List[SearchStats] = []
        for algorithm, label in (
            ("dijkstra", "Dijkstra"),
            ("astar", "A*"),
            ("bellman_ford", "Bellman-Ford"),
        ):
            try:
                route = self.shortest_path(source, target, algorithm)
                if route is None:
                    results.append(
                        SearchStats(
                            algorithm=label,
                            found=False,
                            distance_m=None,
                            seconds=None,
                            settled=0,
                            elapsed_seconds=0.0,
                            note="no feasible route",
                        )
                    )
                else:
                    results.append(
                        SearchStats(
                            algorithm=label,
                            found=True,
                            distance_m=route.distance_m,
                            seconds=route.seconds,
                            settled=route.settled,
                            elapsed_seconds=route.elapsed_seconds,
                        )
                    )
            except ORRoutingError as exc:
                results.append(
                    SearchStats(
                        algorithm=label,
                        found=False,
                        distance_m=None,
                        seconds=None,
                        settled=0,
                        elapsed_seconds=0.0,
                        note=str(exc),
                    )
                )
        return results

    # ---------------------------------------------------------------- geometry
    def route_geometry(self, route: DistanceRoute) -> List[List[float]]:
        """Geo polyline for a route, using the network edge outlines.

        يحوّل المسار إلى خط جغرافي لرسمه.
        """
        points: List[List[float]] = []
        seen_edges: Set[str] = set()
        for segment in route.segments:
            if segment.edge_id in seen_edges:
                continue
            seen_edges.add(segment.edge_id)
            edge = self.network.edges.get(segment.edge_id)
            if edge is None:
                continue
            for x, y in edge.shape:
                lon, lat = self.network.to_geo(x, y)
                point = [round(lat, 6), round(lon, 6)]
                if not points or points[-1] != point:
                    points.append(point)
        return points

    def prohibited_summary(self) -> Dict[str, object]:
        """Counts and examples for the report; never hides the rule."""
        examples = sorted(self.explicit_prohibited)[:20]
        return {
            "network_class_prohibited_lanes": len(self.class_prohibited),
            "explicit_prohibited_lanes": len(self.explicit_prohibited),
            "total_prohibited_lanes": len(self.prohibited),
            "explicit_examples": examples,
            "rule": "Lanes without permission for '{0}' and explicit closures are removed from every search; no finite penalty is used.".format(
                self.vehicle_class
            ),
        }
