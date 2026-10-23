"""Lightweight parser for SUMO ``.net.xml`` files.

The project deliberately avoids a hard dependency on ``sumolib`` so that it
runs with a plain standard-library Python installation.  Only the parts of the
network that are actually needed are extracted:

* junctions (position + type),
* normal edges (geometry, length, endpoints),
* traffic lights (tlLogic id -> controlling junction).

Geometry note
-------------
Networks written by ``netedit`` usually store the edge outline in the
``shape`` attribute of the ``<edge>`` element.  When it is missing the shape
of the first lane is used, and finally a straight line between the two
junction positions is used.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .projection import NetProjection, parse_proj_parameter

Point = Tuple[float, float]


def _parse_shape(raw: Optional[str]) -> List[Point]:
    """Parse a SUMO ``"x,y x,y ..."`` shape string."""
    if not raw:
        return []
    points: List[Point] = []
    for token in raw.split():
        if "," not in token:
            continue
        x_str, _, y_str = token.partition(",")
        try:
            points.append((float(x_str), float(y_str)))
        except ValueError:
            continue
    return points


def polyline_length(points: Sequence[Point]) -> float:
    total = 0.0
    for i in range(1, len(points)):
        dx = points[i][0] - points[i - 1][0]
        dy = points[i][1] - points[i - 1][1]
        total += math.hypot(dx, dy)
    return total


def class_allowed(
    allow: Optional[str], disallow: Optional[str], vehicle_class: str
) -> bool:
    """Does a lane with these permissions admit a vehicle of ``vehicle_class``?

    The rule mirrors SUMO's own check for leaf vehicle classes: an explicit
    ``allow`` list is exclusive (``all`` excepted), otherwise everything but
    the classes named in ``disallow`` is permitted.
    """
    if allow:
        classes = set(allow.split())
        if "all" in classes:
            return True
        return vehicle_class in classes
    disallowed = set((disallow or "").split())
    return vehicle_class not in disallowed


@dataclass
class Junction:
    id: str
    x: float
    y: float
    type: str = "priority"
    inc_lanes: Tuple[str, ...] = ()
    int_lanes: Tuple[str, ...] = ()


@dataclass
class Edge:
    id: str
    from_junction: str = ""
    to_junction: str = ""
    type: str = ""
    function: str = ""
    shape: List[Point] = field(default_factory=list)
    length: float = 0.0
    #: ``(allow, disallow)`` of every lane, in lane index order
    lane_permissions: List[Tuple[Optional[str], Optional[str]]] = field(default_factory=list)
    #: drivable length of every lane in metres, in lane index order
    lane_lengths: List[float] = field(default_factory=list)
    #: speed limit of every lane in m/s, in lane index order
    lane_speeds: List[float] = field(default_factory=list)

    @property
    def is_internal(self) -> bool:
        return self.function == "internal" or self.id.startswith(":")

    def lane_length(self, lane_index: int) -> float:
        """Length of one lane in metres (falls back to the edge geometry).

        طول المسار الواحد بالأمتار؛ يُستخدم في حساب زمن الرحلة.
        """
        if 0 <= lane_index < len(self.lane_lengths) and self.lane_lengths[lane_index] > 0:
            return self.lane_lengths[lane_index]
        return self.length

    def lane_speed(self, lane_index: int) -> float:
        """Speed limit of one lane in m/s (``0`` when unknown).

        السرعة القصوى للمسار بالمتر/الثانية؛ صفر يعني غير معروفة.
        """
        if 0 <= lane_index < len(self.lane_speeds) and self.lane_speeds[lane_index] > 0:
            return self.lane_speeds[lane_index]
        return 0.0

    def allows_class(self, vehicle_class: str, lane_index: Optional[int] = None) -> bool:
        """Can a vehicle of ``vehicle_class`` drive on this edge?

        ``lane_index`` restricts the check to a single lane; by default the
        check is performed for lane 0 (the lane SUMO uses for
        ``arrivalPos`` / ``departPos``) and falls back to any lane.
        """
        if not self.lane_permissions:
            return True
        if lane_index is not None:
            if lane_index >= len(self.lane_permissions):
                return False
            allow, disallow = self.lane_permissions[lane_index]
            return class_allowed(allow, disallow, vehicle_class)
        if self.lane_permissions:
            allow, disallow = self.lane_permissions[0]
            if class_allowed(allow, disallow, vehicle_class):
                return True
        return any(
            class_allowed(allow, disallow, vehicle_class)
            for allow, disallow in self.lane_permissions
        )


class LaneGraph:
    """Lane level routing graph built from the ``<connection>`` elements.

    SUMO routes vehicles on lanes, not on edges: a vehicle can only enter the
    next edge when there is a lane-to-lane connection at the junction.  The
    edge level view of the network is therefore not enough to decide whether
    a route exists, which is why this graph is used when the generator picks
    the ambulance origins.
    """

    def __init__(self, root: ET.Element, network: "Network" = None):
        self.network = network
        self.successors: Dict[str, List[str]] = {}
        self.predecessors: Dict[str, List[str]] = {}
        self.edge_lanes: Dict[str, List[str]] = {}
        #: lane id -> ``(edge id, lane index)``
        self.lane_info: Dict[str, Tuple[str, int]] = {}
        #: cached largest strongly connected component per vehicle class
        self._main_component_cache: Dict[str, set] = {}

        for edge in root.findall("edge"):
            edge_id = edge.get("id", "")
            internal = edge.get("function") == "internal" or edge_id.startswith(":")
            lane_ids: List[str] = []
            for position, lane in enumerate(edge.findall("lane")):
                lane_id = lane.get("id") or "{0}_{1}".format(edge_id, lane.get("index"))
                try:
                    index = int(lane.get("index"))
                except (TypeError, ValueError):
                    index = position
                self.lane_info[lane_id] = (edge_id, index)
                if not internal:
                    lane_ids.append(lane_id)
            if lane_ids:
                self.edge_lanes[edge_id] = lane_ids

        for connection in root.findall("connection"):
            from_edge = connection.get("from")
            to_edge = connection.get("to")
            from_lane = connection.get("fromLane")
            to_lane = connection.get("toLane")
            if not (from_edge and to_edge and from_lane is not None and to_lane is not None):
                continue
            source = "{0}_{1}".format(from_edge, from_lane)
            target = "{0}_{1}".format(to_edge, to_lane)
            self.successors.setdefault(source, []).append(target)
            self.predecessors.setdefault(target, []).append(source)

    def lanes_of(self, edge_id: str) -> List[str]:
        return self.edge_lanes.get(edge_id, [])

    def lane_allowed(self, lane_id: str, vehicle_class: str = "") -> bool:
        """May a vehicle of ``vehicle_class`` drive on ``lane_id``?"""
        if not vehicle_class or self.network is None:
            return True
        info = self.lane_info.get(lane_id)
        if info is None:
            return True
        edge_id, index = info
        edge = self.network.edges.get(edge_id)
        if edge is None:
            return True
        return edge.allows_class(vehicle_class, lane_index=index)

    def edge_of_lane(self, lane_id: str) -> Optional[str]:
        """Return the edge that owns ``lane_id`` (``None`` when unknown).

        يُرجع الشارع الذي ينتمي إليه المسار.
        """
        info = self.lane_info.get(lane_id)
        return info[0] if info else None

    def lane_start_xy(self, lane_id: str) -> Optional[Point]:
        """Start coordinate of a lane in SUMO network metres.

        إحداثيات بداية المسار في نظام شبكة سومو (بالمتر).
        """
        edge_id = self.edge_of_lane(lane_id)
        if edge_id is None or self.network is None:
            return None
        edge = self.network.edges.get(edge_id)
        if edge is None:
            return None
        if edge.shape:
            return edge.shape[0]
        from_junction = self.network.junctions.get(edge.from_junction)
        if from_junction is not None:
            return (from_junction.x, from_junction.y)
        return None

    def main_component(self, vehicle_class: str = "") -> set:
        """Lanes in the largest strongly connected component.

        أكبر مكوّن strongly connected في شبكة المسارات. يُستخدم لتمييز
        نقطة البداية المسدودة: إذا لم تستطع الوصول إلى هذا المكوّن فهي
        فرع مسدود ولا يمكن للإسعاف الخروج منه.

        The largest SCC is a structural definition (no arbitrary distance
        threshold).  A start on a side street that eventually joins the main
        network is accepted; a start trapped in a tiny dead-end loop is not.
        """
        if vehicle_class in self._main_component_cache:
            return self._main_component_cache[vehicle_class]

        nodes = [
            lane_id
            for lane_id in self.lane_info
            if self.lane_allowed(lane_id, vehicle_class)
        ]
        node_set = set(nodes)
        adjacency: Dict[str, List[str]] = {}
        reverse: Dict[str, List[str]] = {lane_id: [] for lane_id in nodes}
        for lane_id in nodes:
            successors = [
                target
                for target in self.successors.get(lane_id, ())
                if target in node_set
                and self.lane_allowed(target, vehicle_class)
            ]
            adjacency[lane_id] = successors
            for target in successors:
                reverse[target].append(lane_id)

        # Iterative Kosaraju: first pass computes the finishing order.
        # كوساراجو تكراري: المرور الأول لحساب ترتيب الانتهاء.
        visited = set()
        order: List[str] = []
        for start in nodes:
            if start in visited:
                continue
            visited.add(start)
            stack: List[Tuple[str, int]] = [(start, 0)]
            while stack:
                node, index = stack[-1]
                successors = adjacency.get(node, ())
                if index < len(successors):
                    target = successors[index]
                    stack[-1] = (node, index + 1)
                    if target not in visited:
                        visited.add(target)
                        stack.append((target, 0))
                else:
                    order.append(node)
                    stack.pop()

        # Second pass on the reversed graph: collect the SCCs.
        # المرور الثاني على الرسم المعكوس لجمع المكونات.
        component_of: Dict[str, int] = {}
        sizes: List[int] = []
        for start in reversed(order):
            if start in component_of:
                continue
            component_id = len(sizes)
            component_of[start] = component_id
            stack = [start]
            size = 0
            while stack:
                node = stack.pop()
                size += 1
                for predecessor in reverse.get(node, ()):
                    if predecessor not in component_of:
                        component_of[predecessor] = component_id
                        stack.append(predecessor)
            sizes.append(size)

        if not sizes:
            result: set = set()
        else:
            largest = sizes.index(max(sizes))
            result = {
                lane_id
                for lane_id, component_id in component_of.items()
                if component_id == largest
            }
        self._main_component_cache[vehicle_class] = result
        return result

    def lane_length(self, lane_id: str) -> float:
        """Drivable length of ``lane_id`` in metres.

        طول المسار بالأمتار (صفر إذا كان المسار غير معروف).
        """
        info = self.lane_info.get(lane_id)
        if info is None or self.network is None:
            return 0.0
        edge_id, index = info
        edge = self.network.edges.get(edge_id)
        return edge.lane_length(index) if edge is not None else 0.0

    def lane_speed(self, lane_id: str) -> float:
        """Speed limit of ``lane_id`` in m/s (``0`` when unknown).

        السرعة القصوى للمسار بالمتر/الثانية.
        """
        info = self.lane_info.get(lane_id)
        if info is None or self.network is None:
            return 0.0
        edge_id, index = info
        edge = self.network.edges.get(edge_id)
        return edge.lane_speed(index) if edge is not None else 0.0

    def usable_lanes(self, edge_id: str, vehicle_class: str = "") -> List[str]:
        """The lanes of ``edge_id`` a vehicle of ``vehicle_class`` may use."""
        return [
            lane_id
            for lane_id in self.lanes_of(edge_id)
            if self.lane_allowed(lane_id, vehicle_class)
        ]

    def reachable_lanes(self, start_edges: Iterable[str], vehicle_class: str = "") -> set:
        """All lanes that can be reached when starting on ``start_edges``."""
        seen = set()
        stack: List[str] = []
        for edge_id in start_edges:
            for lane_id in self.lanes_of(edge_id):
                if not self.lane_allowed(lane_id, vehicle_class):
                    continue
                if lane_id not in seen:
                    seen.add(lane_id)
                    stack.append(lane_id)
        while stack:
            lane = stack.pop()
            for successor in self.successors.get(lane, ()):
                if successor in seen:
                    continue
                if not self.lane_allowed(successor, vehicle_class):
                    continue
                seen.add(successor)
                stack.append(successor)
        return seen

    def route_exists(
        self, source_edge: str, target_edge: str, vehicle_class: str = ""
    ) -> bool:
        """Is there a lane level route from ``source_edge`` to ``target_edge``?

        The search honours the vehicle class, exactly like SUMO's router does:
        lanes that the ambulance may not use are not traversed.
        """
        target_lanes = set(self.lanes_of(target_edge))
        if not target_lanes:
            return False
        if source_edge == target_edge:
            return True
        if not self.usable_lanes(source_edge, vehicle_class):
            return False
        reachable = self.reachable_lanes([source_edge], vehicle_class)
        return any(
            lane in reachable and self.lane_allowed(lane, vehicle_class)
            for lane in target_lanes
        )

    def reverse_reachable_lanes(
        self, target_edges: Iterable[str], vehicle_class: str = ""
    ) -> set:
        """All lanes from which ``target_edges`` can be reached."""
        seen = set()
        stack: List[str] = []
        for edge_id in target_edges:
            for lane_id in self.lanes_of(edge_id):
                if not self.lane_allowed(lane_id, vehicle_class):
                    continue
                if lane_id not in seen:
                    seen.add(lane_id)
                    stack.append(lane_id)
        while stack:
            lane = stack.pop()
            for predecessor in self.predecessors.get(lane, ()):
                if predecessor in seen:
                    continue
                if not self.lane_allowed(predecessor, vehicle_class):
                    continue
                seen.add(predecessor)
                stack.append(predecessor)
        return seen


@dataclass
class TrafficLight:
    """A traffic light as seen through SUMO/TraCI.

    ``id`` is the *tlLogic* id (the identifier TraCI reports), ``junction_id``
    is the SUMO junction that carries the lights.
    """

    id: str
    junction_id: str
    x: float
    y: float
    programs: int = 1
    phase_count: int = 0
    label: str = ""


class Network:
    """Parsed representation of the SUMO network."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.junctions: Dict[str, Junction] = {}
        self.edges: Dict[str, Edge] = {}
        self.traffic_lights: List[TrafficLight] = []
        self.net_offset: Point = (0.0, 0.0)
        self.conv_boundary: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
        self.orig_boundary: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
        self.proj_parameter: str = ""
        self.projection: NetProjection = NetProjection()
        self._tls_junction: Dict[str, str] = {}
        self.lane_graph: Optional[LaneGraph] = None
        self._parse()

    # ------------------------------------------------------------------ parse
    def _parse(self) -> None:
        root = ET.parse(str(self.path)).getroot()

        location = root.find("location")
        if location is not None:
            self.proj_parameter = location.get("projParameter", "") or ""
            offset = location.get("netOffset")
            if offset:
                parts = offset.split(",")
                if len(parts) == 2:
                    self.net_offset = (float(parts[0]), float(parts[1]))
            self.conv_boundary = _parse_boundary(location.get("convBoundary"))
            self.orig_boundary = _parse_boundary(location.get("origBoundary"))

        zone = parse_proj_parameter(self.proj_parameter)
        self.projection = NetProjection(zone=zone, net_offset=self.net_offset)

        for j in root.findall("junction"):
            try:
                x = float(j.get("x", "0"))
                y = float(j.get("y", "0"))
            except ValueError:
                continue
            self.junctions[j.get("id", "")] = Junction(
                id=j.get("id", ""),
                x=x,
                y=y,
                type=j.get("type", "priority"),
                inc_lanes=tuple((j.get("incLanes") or "").split()),
                int_lanes=tuple((j.get("intLanes") or "").split()),
            )

        for e in root.findall("edge"):
            edge = Edge(
                id=e.get("id", ""),
                from_junction=e.get("from", "") or "",
                to_junction=e.get("to", "") or "",
                type=e.get("type", "") or "",
                function=e.get("function", "") or "",
                shape=_parse_shape(e.get("shape")),
            )
            lanes = e.findall("lane")
            edge.lane_permissions = [
                (lane.get("allow"), lane.get("disallow")) for lane in lanes
            ]
            for lane in lanes:
                try:
                    edge.lane_lengths.append(float(lane.get("length", "0")))
                except (TypeError, ValueError):
                    edge.lane_lengths.append(0.0)
                try:
                    edge.lane_speeds.append(float(lane.get("speed", "0")))
                except (TypeError, ValueError):
                    edge.lane_speeds.append(0.0)
            if not edge.shape:
                if lanes:
                    edge.shape = _parse_shape(lanes[0].get("shape"))
            if not edge.shape and edge.from_junction and edge.to_junction:
                a = self.junctions.get(edge.from_junction)
                b = self.junctions.get(edge.to_junction)
                if a and b:
                    edge.shape = [(a.x, a.y), (b.x, b.y)]
            edge.length = polyline_length(edge.shape)
            self.edges[edge.id] = edge

        self._parse_traffic_lights(root)
        self.lane_graph = LaneGraph(root, self)

    def _parse_traffic_lights(self, root: ET.Element) -> None:
        # internal lane -> junction, preferring the "real" (non internal) junction
        lane_to_junction: Dict[str, str] = {}
        for junction in self.junctions.values():
            for lane in junction.int_lanes:
                if not junction.id.startswith(":"):
                    lane_to_junction[lane] = junction.id
        for junction in self.junctions.values():
            if junction.id.startswith(":"):
                for lane in junction.int_lanes:
                    lane_to_junction.setdefault(lane, junction.id)

        junction_to_tl: Dict[str, set] = {}
        for conn in root.findall("connection"):
            tl_id = conn.get("tl")
            if not tl_id:
                continue
            via = conn.get("via")
            junction_id = lane_to_junction.get(via or "")
            if junction_id is None:
                continue
            junction_to_tl.setdefault(junction_id, set()).add(tl_id)

        programs: Dict[str, int] = {}
        phases: Dict[str, int] = {}
        for logic in root.findall("tlLogic"):
            tl_id = logic.get("id", "")
            programs[tl_id] = programs.get(tl_id, 0) + 1
            phases[tl_id] = max(phases.get(tl_id, 0), len(logic.findall("phase")))

        # one entry per traffic light; the "real" junction wins over the
        # internal ones (a light can control several internal lanes)
        tl_to_junction: Dict[str, str] = {}
        for junction_id, tl_ids in junction_to_tl.items():
            for tl_id in tl_ids:
                current = tl_to_junction.get(tl_id)
                if current is None or (
                    current.startswith(":") and not junction_id.startswith(":")
                ):
                    tl_to_junction[tl_id] = junction_id

        for tl_id, junction_id in tl_to_junction.items():
            junction = self.junctions.get(junction_id)
            if junction is None:
                continue
            self.traffic_lights.append(
                TrafficLight(
                    id=tl_id,
                    junction_id=junction_id,
                    x=junction.x,
                    y=junction.y,
                    programs=programs.get(tl_id, 1),
                    phase_count=phases.get(tl_id, 0),
                )
            )
        self.traffic_lights.sort(key=lambda t: t.id)

    # --------------------------------------------------------------- accessors
    @property
    def normal_edges(self) -> List[Edge]:
        """All edges that can be used as a route endpoint."""
        return [e for e in self.edges.values() if not e.is_internal]

    @property
    def boundary(self) -> Tuple[float, float, float, float]:
        """The `convBoundary` of the network in local coordinates."""
        return self.conv_boundary

    def contains_local(self, x: float, y: float, margin: float = 0.0) -> bool:
        min_x, min_y, max_x, max_y = self.conv_boundary
        if min_x == max_x == 0.0 and min_y == max_y == 0.0:
            return True
        return (
            min_x - margin <= x <= max_x + margin
            and min_y - margin <= y <= max_y + margin
        )

    def to_geo(self, x: float, y: float) -> Point:
        return self.projection.to_geo(x, y)

    def to_local(self, lon: float, lat: float) -> Point:
        return self.projection.to_local(lon, lat)

    def traffic_light_by_id(self, tl_id: str) -> Optional[TrafficLight]:
        for tl in self.traffic_lights:
            if tl.id == tl_id:
                return tl
        return None


def _parse_boundary(raw: Optional[str]) -> Tuple[float, float, float, float]:
    if not raw:
        return (0.0, 0.0, 0.0, 0.0)
    parts = [p for p in raw.split(",") if p.strip()]
    try:
        values = [float(p) for p in parts]
    except ValueError:
        return (0.0, 0.0, 0.0, 0.0)
    while len(values) < 4:
        values.append(0.0)
    return (values[0], values[1], values[2], values[3])


_CACHE: Dict[str, Network] = {}


def open_network(path: Path, use_cache: bool = True) -> Network:
    """Open (and cache) a network file."""
    key = str(Path(path).resolve())
    if use_cache and key in _CACHE:
        return _CACHE[key]
    network = Network(Path(path))
    if use_cache:
        _CACHE[key] = network
    return network
