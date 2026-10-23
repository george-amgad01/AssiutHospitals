"""Expected travel time per lane (requirement 5, free-flow part only).

الزمن المتوقع لعبور كل مسار = طول المسار / سرعته القصوى.

This module implements **only** the free-flow half of the cost model:

    t(lane) = length(lane) / speed(lane)

Congestion adjustment is deliberately NOT implemented here.  Requirement 5
demands that the congestion design be approved before it is coded, so the
model exposes a per-edge ``congestion_factor`` hook that is empty for now and
defaults to ``1.0`` (free flow).  When the design is approved the caller will
fill that mapping from TraCI measurements; no other code has to change.

واجهة عامل الازدحام موجودة لكنها فارغة (1.0 = تدفق حر) بانتظار الموافقة على
تصميم احتساب الازدحام.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from .netmodel import Network

#: Fallback speed (m/s) when a lane does not declare one.  ~50 km/h.
DEFAULT_SPEED_MPS = 13.89


@dataclass
class TimeModel:
    """Travel-time model over the lane graph.

    Parameters
    ----------
    network:
        Parsed SUMO network.
    vehicle_class:
        Used only for documentation here; the lane graph filters permissions.
    congestion_factor:
        Optional ``edge id -> multiplier`` (>= 1.0 means slower).  Empty means
        pure free flow.  This is the single hook the approved congestion model
        will populate.

    نموذج الزمن: يحوّل طول المسار وسرعته إلى ثوانٍ، مع منفذ جاهز لعامل الازدحام.
    """

    network: Network
    vehicle_class: str = "emergency"
    congestion_factor: Dict[str, float] = field(default_factory=dict)

    # ------------------------------------------------------------------ basics
    def _edge_and_index(self, lane_id: str):
        info = self.network.lane_graph.lane_info.get(lane_id)
        if info is None:
            raise KeyError("unknown lane: {0}".format(lane_id))
        edge_id, index = info
        edge = self.network.edges.get(edge_id)
        if edge is None:
            raise KeyError("unknown edge for lane: {0}".format(lane_id))
        return edge, index

    def length(self, lane_id: str) -> float:
        """Drivable lane length in metres (0 for unknown lanes).

        طول المسار بالأمتار.
        """
        edge, index = self._edge_and_index(lane_id)
        return edge.lane_length(index)

    def speed(self, lane_id: str) -> float:
        """Lane speed limit in m/s (never zero).

        السرعة القصوى للمسار؛ تُستخدم سرعة افتراضية عند غيابها.
        """
        edge, index = self._edge_and_index(lane_id)
        speed = edge.lane_speed(index)
        return speed if speed > 0 else DEFAULT_SPEED_MPS

    def factor(self, lane_id: str) -> float:
        """Congestion multiplier for the lane's edge (1.0 while disabled).

        معامل الازدحام للشارع؛ 1.0 يعني تدفقاً حراً.
        """
        if not self.congestion_factor:
            return 1.0
        edge, _index = self._edge_and_index(lane_id)
        value = self.congestion_factor.get(edge.id, 1.0)
        return value if value >= 1.0 else 1.0

    # -------------------------------------------------------------------- cost
    def lane_time(self, lane_id: str, from_frac: float = 0.0, to_frac: float = 1.0) -> float:
        """Travel time for the ``[from_frac, to_frac]`` part of a lane.

        Fractions are measured along the lane (0 = start, 1 = end), so the
        same function serves a whole lane, a partial first lane (the ambulance
        already sits on it) and a partial last lane (the hospital entrance).

        زمن عبور جزء من المسار بين نسبتين (0 البداية، 1 النهاية).
        """
        lo = 0.0 if from_frac < 0.0 else (1.0 if from_frac > 1.0 else from_frac)
        hi = 0.0 if to_frac < 0.0 else (1.0 if to_frac > 1.0 else to_frac)
        if hi <= lo:
            return 0.0
        distance = self.length(lane_id) * (hi - lo)
        return distance / self.speed(lane_id) * self.factor(lane_id)

    def lane_time_full(self, lane_id: str) -> float:
        """Free-flow time for the whole lane in seconds.

        زمن عبور المسار كاملاً بالثواني.
        """
        return self.lane_time(lane_id, 0.0, 1.0)

    # ------------------------------------------------------------------ helper
    def describe(self) -> Dict[str, object]:
        """Small dict for CLI/JSON output (proves congestion is disabled).

        ملخص يوضح أن الازدحام غير مفعّل بعد.
        """
        return {
            "mode": "free_flow" if not self.congestion_factor else "congestion_adjusted",
            "congestion_enabled": bool(self.congestion_factor),
            "vehicle_class": self.vehicle_class,
            "default_speed_mps": DEFAULT_SPEED_MPS,
        }
