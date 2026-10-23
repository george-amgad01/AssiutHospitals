"""Alternative dispatch algorithms used by the comparison (requirement 7).

الخوارزميات البديلة المستخدمة في المقارنة (المتطلب 7).

The dispatch search itself uses Dijkstra (see :mod:`assiut_hospitals.dispatch`).
This module adds the algorithms selected by the owner:

* **A\*** - shortest lane path with an admissible straight-line time heuristic;
* **Bellman-Ford** - independent shortest-time reference;
* **VAM, least-cost, north-west corner and MODI** - transportation-problem
  selection methods.

The four transportation methods do **not** traverse the road graph.  They are
applied to a small, explicitly documented transportation model:

* rows = suitable hospitals in the start zone, supply = their free beds;
* column 1 = the one patient (demand 1), cost = free-flow travel time from the
  ambulance to that hospital;
* column 2 = a dummy demand that absorbs the remaining beds, cost = a large
  constant so the patient is not assigned to the dummy.

The selected hospital is the row allocated to column 1.  Its road route and
travel time are then taken from the Dijkstra cost matrix, because these methods
choose a destination and do not build a path.  This limitation is reported in
the comparison output instead of pretending that they are pathfinders.

طرق النقل لا تبحث في شبكة الطرق؛ تُطبَّق على نموذج نقل صغير موضّح أعلاه،
ثم يُؤخذ مسار المستشفى المختار من مصفوفة ديكسترا. هذا القيد مذكور صراحةً
في مخرجات المقارنة.
"""

from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .netmodel import LaneGraph, Network
from .traveltime import TimeModel

INF = float("inf")
EPS = 1e-9
Point = Tuple[float, float]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def entry_times(
    graph: LaneGraph,
    model: TimeModel,
    distances: Dict[str, float],
    offsets: Dict[str, float],
    vehicle_class: str = "emergency",
) -> Dict[str, Tuple[float, Optional[str]]]:
    """Cheapest way to enter each lane, with the predecessor used.

    أقل زمن لدخول كل مسار مع المسار السابق الذي حقق هذا الزمن.
    """
    entries: Dict[str, Tuple[float, Optional[str]]] = {}
    for lane, predecessors in graph.predecessors.items():
        best = INF
        best_pred: Optional[str] = None
        for pred in predecessors:
            if pred not in distances:
                continue
            if not graph.lane_allowed(pred, vehicle_class):
                continue
            candidate = distances[pred] + model.lane_time(
                pred, offsets.get(pred, 0.0), 1.0
            )
            if candidate < best:
                best = candidate
                best_pred = pred
        if best_pred is not None:
            entries[lane] = (best, best_pred)
    return entries


def bellman_ford(
    graph: LaneGraph,
    model: TimeModel,
    start_lanes: Sequence[str],
    start_frac: float,
    vehicle_class: str = "emergency",
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, Optional[str]]]:
    """Bellman-Ford shortest travel times on the lane graph.

    زمن الوصول الأقصر بطريقة بيلمان-فورد؛ مرجع مستقل عن ديكسترا.

    The relaxation order is lane-id order.  Because all weights are positive
    free-flow times, the algorithm is exact and also acts as an independent
    check of Dijkstra's distances.
    """
    dist: Dict[str, float] = {}
    offsets: Dict[str, float] = {}
    previous: Dict[str, Optional[str]] = {}
    for lane in start_lanes:
        dist[lane] = 0.0
        offsets[lane] = start_frac
        previous[lane] = None

    nodes = [
        lane
        for lane in graph.lane_info
        if graph.lane_allowed(lane, vehicle_class)
    ]
    if not nodes:
        return dist, offsets, previous

    # The cost of leaving a lane depends only on its fixed offset.  Origin
    # lanes keep their start offset; every other lane starts at 0.
    weights: Dict[str, float] = {}
    for lane in nodes:
        weights[lane] = model.lane_time(
            lane, start_frac if lane in dist else 0.0, 1.0
        )

    for _ in range(max(0, len(nodes) - 1)):
        changed = False
        for lane in nodes:
            if lane not in dist:
                continue
            base = dist[lane]
            successor_cost = base + weights.get(lane, 0.0)
            for successor in graph.successors.get(lane, ()):
                if not graph.lane_allowed(successor, vehicle_class):
                    continue
                if successor_cost + EPS < dist.get(successor, INF):
                    dist[successor] = successor_cost
                    offsets[successor] = 0.0
                    previous[successor] = lane
                    changed = True
        if not changed:
            break
    return dist, offsets, previous


# ---------------------------------------------------------------------------
# A*
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Target:
    """A hospital entrance that A* may stop at."""

    slug: str
    lane_id: str
    frac: float
    point: Point


@dataclass
class AStarResult:
    """Best target found by one multi-target A* search."""

    seconds: float
    slug: str
    lane_id: str
    pred: Optional[str]
    kind: str
    frac: float
    distances: Dict[str, float] = field(default_factory=dict)
    offsets: Dict[str, float] = field(default_factory=dict)
    previous: Dict[str, Optional[str]] = field(default_factory=dict)
    settled: int = 0


def astar_to_targets(
    graph: LaneGraph,
    model: TimeModel,
    network: Network,
    origin_lanes: Sequence[str],
    origin_frac: float,
    targets: Sequence[Target],
    vehicle_class: str = "emergency",
) -> Optional[AStarResult]:
    """Find the fastest target with multi-target A*.

    إيجاد أسرع مستشفى بطريقة A* متعددة الأهداف.

    The heuristic is ``straight_line_distance / maximum_lane_speed``.  It can
    never exceed the real free-flow time, so A* returns the same optimum as
    Dijkstra and Bellman-Ford.  The search stops as soon as no unexpanded lane
    can improve the best complete target cost.
    """
    if not targets:
        return None

    # Precompute the lane start point and the global maximum speed once.
    # حساب نقاط بداية المسارات وأقصى سرعة مرة واحدة.
    lane_xy: Dict[str, Point] = {}
    max_speed = 0.0
    for lane in graph.lane_info:
        point = graph.lane_start_xy(lane)
        if point is not None:
            lane_xy[lane] = point
        speed = model.speed(lane)
        if speed > max_speed:
            max_speed = speed
    if max_speed <= 0.0:
        max_speed = 1.0

    targets_by_lane: Dict[str, List[Target]] = {}
    for target in targets:
        targets_by_lane.setdefault(target.lane_id, []).append(target)
    target_points = [target.point for target in targets]

    heuristic_cache: Dict[str, float] = {}

    def heuristic(lane: str) -> float:
        if lane in origin_lanes:
            # The ambulance is already part-way along this lane; using the
            # lane start would over-estimate.  Zero is always admissible.
            return 0.0
        if lane in heuristic_cache:
            return heuristic_cache[lane]
        point = lane_xy.get(lane)
        if point is None:
            value = 0.0
        else:
            value = min(
                math.hypot(point[0] - target[0], point[1] - target[1])
                for target in target_points
            ) / max_speed
        heuristic_cache[lane] = value
        return value

    dist: Dict[str, float] = {}
    offsets: Dict[str, float] = {}
    previous: Dict[str, Optional[str]] = {}
    heap: List[Tuple[float, float, str]] = []
    for lane in origin_lanes:
        dist[lane] = 0.0
        offsets[lane] = origin_frac
        previous[lane] = None
        heapq.heappush(heap, (heuristic(lane), 0.0, lane))

    best: Optional[AStarResult] = None
    settled = 0

    def consider(
        seconds: float,
        target: Target,
        pred: Optional[str],
        kind: str,
    ) -> None:
        nonlocal best
        if best is None or seconds + EPS < best.seconds:
            best = AStarResult(
                seconds=seconds,
                slug=target.slug,
                lane_id=target.lane_id,
                pred=pred,
                kind=kind,
                frac=target.frac,
                distances=dist,
                offsets=offsets,
                previous=previous,
                settled=settled,
            )

    # A hospital on the start lane and ahead of the ambulance.
    for lane in origin_lanes:
        for target in targets_by_lane.get(lane, ()):
            if target.frac + EPS >= origin_frac:
                consider(
                    model.lane_time(lane, origin_frac, target.frac),
                    target,
                    None,
                    "same",
                )

    while heap:
        if best is not None and best.seconds <= heap[0][0] + EPS:
            break
        _f, current_g, lane = heapq.heappop(heap)
        if current_g > dist.get(lane, INF) + EPS:
            continue
        settled += 1
        remaining = model.lane_time(lane, offsets.get(lane, 0.0), 1.0)
        for successor in graph.successors.get(lane, ()):
            if not graph.lane_allowed(successor, vehicle_class):
                continue
            new_g = current_g + remaining
            # A complete route can finish by entering a hospital lane and
            # driving to the exact snapped position.
            for target in targets_by_lane.get(successor, ()):
                consider(
                    new_g + model.lane_time(successor, 0.0, target.frac),
                    target,
                    lane,
                    "entry",
                )
            if new_g + EPS < dist.get(successor, INF):
                dist[successor] = new_g
                offsets[successor] = 0.0
                previous[successor] = lane
                heapq.heappush(
                    heap, (new_g + heuristic(successor), new_g, successor)
                )
    return best


# ---------------------------------------------------------------------------
# Transportation-problem selection methods
# ---------------------------------------------------------------------------
@dataclass
class TransportResult:
    """Allocation returned by one transportation method."""

    method: str
    selected_index: Optional[int]
    allocation: List[List[float]]
    iterations: int = 0


def _northwest(supplies: Sequence[float], demands: Sequence[float]) -> List[List[float]]:
    """North-west corner initial solution.

    حل الركن الشمالي الغربي الأولي.
    """
    m, n = len(supplies), len(demands)
    allocation = [[0.0] * n for _ in range(m)]
    supply = list(supplies)
    demand = list(demands)
    i = j = 0
    while i < m and j < n:
        quantity = min(supply[i], demand[j])
        allocation[i][j] = quantity
        supply[i] -= quantity
        demand[j] -= quantity
        if supply[i] <= EPS:
            i += 1
        if demand[j] <= EPS:
            j += 1
    return allocation


def _least_cost(
    costs: Sequence[Sequence[float]],
    supplies: Sequence[float],
    demands: Sequence[float],
) -> List[List[float]]:
    """Least-cost greedy initial solution.

    حل التكلفة الأقل (اختيار الخانة الأرخص باستمرار).
    """
    m, n = len(costs), len(costs[0])
    allocation = [[0.0] * n for _ in range(m)]
    supply = list(supplies)
    demand = list(demands)
    while True:
        rows = [i for i in range(m) if supply[i] > EPS]
        cols = [j for j in range(n) if demand[j] > EPS]
        if not rows or not cols:
            break
        i, j = min(
            ((i, j) for i in rows for j in cols),
            key=lambda cell: (costs[cell[0]][cell[1]], cell[0], cell[1]),
        )
        quantity = min(supply[i], demand[j])
        allocation[i][j] += quantity
        supply[i] -= quantity
        demand[j] -= quantity
    return allocation


def _vam(
    costs: Sequence[Sequence[float]],
    supplies: Sequence[float],
    demands: Sequence[float],
) -> List[List[float]]:
    """Vogel's Approximation Method initial solution.

    حل طريقة فوغل للتقريب الأولي.
    """
    m, n = len(costs), len(costs[0])
    allocation = [[0.0] * n for _ in range(m)]
    supply = list(supplies)
    demand = list(demands)

    while True:
        rows = [i for i in range(m) if supply[i] > EPS]
        cols = [j for j in range(n) if demand[j] > EPS]
        if not rows or not cols:
            break

        row_penalties: List[Tuple[float, int]] = []
        for i in rows:
            values = sorted(costs[i][j] for j in cols)
            penalty = values[1] - values[0] if len(values) > 1 else values[0]
            row_penalties.append((penalty, i))

        col_penalties: List[Tuple[float, int]] = []
        for j in cols:
            values = sorted(costs[i][j] for i in rows)
            penalty = values[1] - values[0] if len(values) > 1 else values[0]
            col_penalties.append((penalty, j))

        best_row = max(row_penalties, key=lambda item: (item[0], -item[1]))
        best_col = max(col_penalties, key=lambda item: (item[0], -item[1]))
        if best_row[0] >= best_col[0]:
            i = best_row[1]
            j = min(cols, key=lambda col: (costs[i][col], col))
        else:
            j = best_col[1]
            i = min(rows, key=lambda row: (costs[row][j], row))

        quantity = min(supply[i], demand[j])
        allocation[i][j] += quantity
        supply[i] -= quantity
        demand[j] -= quantity
    return allocation


def _add_zero_basics(
    allocation: List[List[float]],
    m: int,
    n: int,
) -> set:
    """Complete a transportation basis with independent zero cells.

    إكمال الأساس بخلايا صفرية مستقلة حتى يعمل اختبار MODI.
    """
    basic = {
        (i, j)
        for i in range(m)
        for j in range(n)
        if allocation[i][j] > EPS
    }
    parent = list(range(m + n))

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for i, j in basic:
        union(i, m + j)

    needed = m + n - 1
    for i in range(m):
        for j in range(n):
            if len(basic) >= needed:
                return basic
            if (i, j) in basic:
                continue
            if find(i) != find(m + j):
                basic.add((i, j))
                union(i, m + j)
    return basic


def _potentials(
    costs: Sequence[Sequence[float]],
    basic: set,
    m: int,
    n: int,
) -> Tuple[List[float], List[float]]:
    """Compute MODI row/column potentials for a basic solution."""
    u: List[Optional[float]] = [None] * m
    v: List[Optional[float]] = [None] * n
    u[0] = 0.0
    changed = True
    while changed:
        changed = False
        for i, j in basic:
            if u[i] is not None and v[j] is None:
                v[j] = costs[i][j] - u[i]
                changed = True
            elif v[j] is not None and u[i] is None:
                u[i] = costs[i][j] - v[j]
                changed = True
    return (
        [0.0 if value is None else value for value in u],
        [0.0 if value is None else value for value in v],
    )


def _cycle_cells(
    basic: set,
    entering: Tuple[int, int],
    m: int,
    n: int,
) -> Optional[List[Tuple[int, int]]]:
    """Find the stepping-stone cycle created by an entering cell."""
    i0, j0 = entering
    row_edges: List[List[int]] = [[] for _ in range(m)]
    col_edges: List[List[int]] = [[] for _ in range(n)]
    for i, j in basic:
        row_edges[i].append(j)
        col_edges[j].append(i)

    # The basic cells form a tree.  Find the unique path from column j0 back
    # to row i0, then prepend the entering cell.
    start = ("c", j0)
    target = ("r", i0)
    stack: List[Tuple[Tuple[str, int], List[Tuple[int, int]]]] = [
        (start, [])
    ]
    seen = {start}
    path: Optional[List[Tuple[int, int]]] = None
    while stack:
        node, cells = stack.pop()
        kind, index = node
        if kind == "r":
            for j in row_edges[index]:
                cell = (index, j)
                next_node = ("c", j)
                if next_node == target:
                    continue
                if next_node in seen:
                    continue
                if next_node == start:
                    continue
                seen.add(next_node)
                stack.append((next_node, cells + [cell]))
                if next_node == target:
                    path = cells + [cell]
                    break
        else:
            for i in col_edges[index]:
                cell = (i, index)
                next_node = ("r", i)
                if next_node == target:
                    path = cells + [cell]
                    break
                if next_node in seen:
                    continue
                seen.add(next_node)
                stack.append((next_node, cells + [cell]))
        if path is not None:
            break
    if path is None:
        # The direct alternating path is normally found above; fall back to a
        # breadth-first search over the same tree.
        queue: List[Tuple[Tuple[str, int], List[Tuple[int, int]]]] = [
            (start, [])
        ]
        seen = {start}
        while queue:
            node, cells = queue.pop(0)
            kind, index = node
            neighbours = (
                [("c", j, (index, j)) for j in row_edges[index]]
                if kind == "r"
                else [("r", i, (i, index)) for i in col_edges[index]]
            )
            for next_kind, next_index, cell in neighbours:
                next_node = (next_kind, next_index)
                if next_node == target:
                    path = cells + [cell]
                    queue = []
                    break
                if next_node not in seen:
                    seen.add(next_node)
                    queue.append((next_node, cells + [cell]))
    if path is None:
        return None
    return [entering] + path


def _modi(
    costs: Sequence[Sequence[float]],
    supplies: Sequence[float],
    demands: Sequence[float],
) -> Tuple[List[List[float]], int]:
    """MODI (u-v) improvement of the north-west corner solution.

    تحسين حل الركن الشمالي الغربي بطريقة MODI.
    """
    m, n = len(costs), len(costs[0])
    allocation = _northwest(supplies, demands)
    basic = _add_zero_basics(allocation, m, n)
    iterations = 0

    for _ in range(200):
        iterations += 1
        u, v = _potentials(costs, basic, m, n)
        entering: Optional[Tuple[int, int]] = None
        best_reduced = -EPS
        for i in range(m):
            for j in range(n):
                if (i, j) in basic:
                    continue
                reduced = costs[i][j] - u[i] - v[j]
                if reduced < best_reduced:
                    best_reduced = reduced
                    entering = (i, j)
        if entering is None:
            break

        cycle = _cycle_cells(basic, entering, m, n)
        if cycle is None:
            break
        minus_cells = cycle[1::2]
        theta = min(allocation[i][j] for i, j in minus_cells)
        if theta <= EPS:
            # Degenerate pivot: add the entering cell and remove the first
            # zero basic cell so the basis size stays correct.
            basic.add(entering)
            for cell in minus_cells:
                if allocation[cell[0]][cell[1]] <= EPS:
                    basic.discard(cell)
                    break
            continue
        for position, (i, j) in enumerate(cycle):
            if position % 2 == 0:
                allocation[i][j] += theta
            else:
                allocation[i][j] -= theta
        for i, j in list(basic):
            if allocation[i][j] <= EPS and (i, j) != entering:
                basic.discard((i, j))
        basic.add(entering)
    return allocation, iterations


def transport_select(
    costs: Sequence[float],
    supplies: Sequence[float],
    method: str,
) -> TransportResult:
    """Select a hospital with one transportation-problem method.

    اختيار مستشفى بإحدى طرق مسألة النقل.

    The patient column is column 0.  The dummy column (when it exists) has a
    large cost so that the patient is always allocated to a real hospital.
    """
    if len(costs) != len(supplies):
        raise ValueError("costs and supplies must have the same length")
    if not costs:
        raise ValueError("at least one hospital is required")
    total_supply = float(sum(supplies))
    if total_supply <= 0.0:
        raise ValueError("total free beds must be positive")

    dummy_cost = max(costs) + 1.0
    if total_supply > 1.0 + EPS:
        matrix = [[float(cost), dummy_cost] for cost in costs]
        demands = [1.0, total_supply - 1.0]
    else:
        matrix = [[float(cost)] for cost in costs]
        demands = [1.0]

    key = method.lower()
    iterations = 0
    if key in ("northwest_corner", "northwest", "nwc"):
        allocation = _northwest(supplies, demands)
    elif key in ("least_cost", "leastcost", "lc"):
        allocation = _least_cost(matrix, supplies, demands)
    elif key in ("vam", "vogel"):
        allocation = _vam(matrix, supplies, demands)
    elif key == "modi":
        allocation, iterations = _modi(matrix, supplies, demands)
    else:
        raise ValueError("unknown transportation method '{0}'".format(method))

    selected: Optional[int] = None
    best_quantity = 0.0
    for i, row in enumerate(allocation):
        quantity = row[0]
        if quantity > best_quantity + EPS:
            best_quantity = quantity
            selected = i
    if selected is None:
        # Fallback is explicit and should only happen for a degenerate matrix.
        selected = min(range(len(costs)), key=lambda index: (costs[index], index))
    return TransportResult(
        method=method,
        selected_index=selected,
        allocation=allocation,
        iterations=iterations,
    )


def measure(callable_, *args, **kwargs):
    """Call ``callable_`` and return ``(result, elapsed_seconds)``."""
    started = time.perf_counter()
    result = callable_(*args, **kwargs)
    return result, time.perf_counter() - started
