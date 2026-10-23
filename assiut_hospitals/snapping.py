"""Snap geographic points onto the SUMO network.

The snap is a plain point-to-polyline projection: for every candidate edge the
query point is projected onto each segment of the edge outline and the closest
projection wins.  The resulting ``pos`` is the distance (in metres) along the
edge measured from the *from* junction, which is exactly the convention SUMO
uses for ``arrivalPos`` / ``departPos``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .netmodel import Edge, Network, open_network

Point = Tuple[float, float]


@dataclass
class SnapResult:
    """Result of snapping a point onto the network."""

    edge_id: str
    pos: float
    distance_m: float
    x: float
    y: float
    edge_length: float
    from_junction: str
    to_junction: str
    edge_type: str = ""
    usable: bool = True

    @property
    def routable(self) -> bool:
        return bool(self.edge_id)

    def as_dict(self) -> Dict[str, object]:
        return {
            "edge_id": self.edge_id,
            "pos": round(self.pos, 3),
            "distance_m": round(self.distance_m, 2),
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "edge_length": round(self.edge_length, 2),
            "from_junction": self.from_junction,
            "to_junction": self.to_junction,
            "edge_type": self.edge_type,
            "usable": self.usable,
        }


def _project_on_segment(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> Tuple[float, float, float]:
    """Project (px, py) onto segment a->b.

    Returns ``(distance, along, t)`` where ``along`` is the distance from `a`
    to the projected point and ``t`` the normalised position on the segment.
    """
    dx = bx - ax
    dy = by - ay
    seg_sq = dx * dx + dy * dy
    if seg_sq <= 1e-12:
        return math.hypot(px - ax, py - ay), 0.0, 0.0
    t = ((px - ax) * dx + (py - ay) * dy) / seg_sq
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    proj_x = ax + t * dx
    proj_y = ay + t * dy
    distance = math.hypot(px - proj_x, py - proj_y)
    seg_len = math.sqrt(seg_sq)
    return distance, t * seg_len, t


class Snapper:
    """Snaps points onto a :class:`~assiut_hospitals.netmodel.Network`.

    Parameters
    ----------
    network:
        The parsed network.
    vehicle_class:
        Vehicle class the snapped edge has to be usable for (default
        ``emergency``, the class of the ambulance).  Edges that do not admit
        that class (pedestrian service roads for example) are only used when
        nothing better is close by.
    max_unusable_distance_m:
        How far the snapper may look for a usable edge before it falls back
        to the closest edge of any kind.
    """

    def __init__(
        self,
        network: Network,
        vehicle_class: str = "emergency",
        max_unusable_distance_m: float = 400.0,
    ):
        self.network = network
        self.vehicle_class = vehicle_class
        self.max_unusable_distance_m = max_unusable_distance_m
        self._edges: List[Edge] = network.normal_edges
        self._usable: Dict[str, bool] = {
            edge.id: edge.allows_class(vehicle_class, lane_index=0)
            for edge in self._edges
        }
        # pre-compute cumulative segment lengths per edge
        self._cum: Dict[str, List[float]] = {}
        for edge in self._edges:
            cum: List[float] = []
            total = 0.0
            for i in range(1, len(edge.shape)):
                dx = edge.shape[i][0] - edge.shape[i - 1][0]
                dy = edge.shape[i][1] - edge.shape[i - 1][1]
                total += math.hypot(dx, dy)
                cum.append(total)
            self._cum[edge.id] = cum

    @property
    def candidate_count(self) -> int:
        return len(self._edges)

    def snap_local(self, x: float, y: float) -> SnapResult:
        """Snap a point given in *network local* coordinates."""
        best: Optional[Tuple[float, float, Edge]] = None
        best_usable: Optional[Tuple[float, float, Edge]] = None
        for edge in self._edges:
            shape = edge.shape
            if len(shape) < 2:
                if shape:
                    distance = math.hypot(x - shape[0][0], y - shape[0][1])
                    if best is None or distance < best[0]:
                        best = (distance, 0.0, edge)
                    if self._usable.get(edge.id) and (best_usable is None or distance < best_usable[0]):
                        best_usable = (distance, 0.0, edge)
                continue
            cum = self._cum[edge.id]
            usable = self._usable.get(edge.id, True)
            for i in range(1, len(shape)):
                ax, ay = shape[i - 1]
                bx, by = shape[i]
                distance, along, _t = _project_on_segment(x, y, ax, ay, bx, by)
                if best is None or distance < best[0]:
                    pos = cum[i - 1] + along
                    if pos > edge.length:
                        pos = edge.length
                    best = (distance, pos, edge)
                if usable and (best_usable is None or distance < best_usable[0]):
                    pos = cum[i - 1] + along
                    if pos > edge.length:
                        pos = edge.length
                    best_usable = (distance, pos, edge)

        chosen = best
        if best_usable is not None and best_usable[0] <= self.max_unusable_distance_m:
            # a road an ambulance may actually use always wins
            chosen = best_usable
        if chosen is None:
            return SnapResult("", 0.0, float("inf"), x, y, 0.0, "", "", usable=False)
        distance, pos, edge = chosen
        is_usable = self._usable.get(edge.id, True)
        proj = self._project_on_edge(edge, x, y)
        return SnapResult(
            edge_id=edge.id,
            pos=pos,
            distance_m=distance,
            x=proj[0],
            y=proj[1],
            edge_length=edge.length,
            from_junction=edge.from_junction,
            to_junction=edge.to_junction,
            edge_type=edge.type,
            usable=is_usable,
        )

    def _project_on_edge(self, edge: Edge, x: float, y: float) -> Point:
        shape = edge.shape
        if len(shape) < 2:
            return shape[0] if shape else (x, y)
        best = None
        for i in range(1, len(shape)):
            ax, ay = shape[i - 1]
            bx, by = shape[i]
            distance, _along, t = _project_on_segment(x, y, ax, ay, bx, by)
            if best is None or distance < best[0]:
                best = (distance, ax + t * (bx - ax), ay + t * (by - ay))
        if best is None:
            return (x, y)
        return (best[1], best[2])

    def snap_geo(self, lon: float, lat: float) -> SnapResult:
        x, y = self.network.to_local(lon, lat)
        return self.snap_local(x, y)


_SNAP_CACHE: Dict[str, Snapper] = {}


def get_snapper(net_file: Path, vehicle_class: str = "emergency") -> Snapper:
    """Return a (cached) snapper for the given network file."""
    key = "{0}|{1}".format(Path(net_file).resolve(), vehicle_class)
    if key not in _SNAP_CACHE:
        _SNAP_CACHE[key] = Snapper(open_network(net_file), vehicle_class=vehicle_class)
    return _SNAP_CACHE[key]


def snap_point(
    lat: float,
    lon: float,
    net_file: Optional[Path] = None,
    config_path: Optional[str] = None,
    vehicle_class: str = "emergency",
) -> SnapResult:
    """Snap a geographic coordinate onto the network.

    This is the public integration helper:

    >>> from assiut_hospitals import snap_point
    >>> snap_point(27.18, 31.12).edge_id
    '1092013771#0'
    """
    from .config import load_config

    if net_file is None:
        config = load_config(config_path)
        net_file = config.net_file
    snapper = get_snapper(Path(net_file), vehicle_class=vehicle_class)
    return snapper.snap_geo(lon, lat)
