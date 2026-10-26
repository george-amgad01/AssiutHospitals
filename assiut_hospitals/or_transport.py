"""Transportation-tableau data, balancing, VAM, least-cost, and NWC.

بيانات جدول النقل والموازنة وطرق VAM وأقل تكلفة والزاوية الشمالية الغربية.

The methods in this module solve the **kit-only transportation tableau**.  The
tableau has no lane capacities; the road-capacitated plan is a separate MILP in
:mod:`assiut_hospitals.or_planning`.  This separation is deliberate and is
reported to the user instead of pretending that VAM/MODI enforce road limits.

طرق هذا الملف تحل جدول الكراتين فقط، ولا تحتوي سعات المسارات. حل الشبكة
المقيّد بالسعة نموذج MILP منفصل.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

EPS = 1e-7
INF = float("inf")
Cell = Tuple[int, int]


class TransportError(RuntimeError):
    """The transportation instance is invalid or cannot be solved.

    جدول النقل غير صالح أو غير قابل للحل.
    """


@dataclass
class TransportProblem:
    """A row/column cost table with supplies, demands, and optional caps.

    جدول تكاليف مع توريد وطلب وحدود خلايا اختيارية.
    """

    row_labels: List[str]
    col_labels: List[str]
    costs: List[List[Optional[float]]]
    supplies: List[int]
    demands: List[int]
    units: str = "units"
    cell_caps: Optional[List[List[Optional[int]]]] = None
    row_notes: List[str] = field(default_factory=list)
    col_notes: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.validate()

    @property
    def rows(self) -> int:
        return len(self.row_labels)

    @property
    def cols(self) -> int:
        return len(self.col_labels)

    def validate(self) -> None:
        if len(self.costs) != self.rows:
            raise TransportError("cost table row count does not match row labels")
        if len(self.supplies) != self.rows or len(self.demands) != self.cols:
            raise TransportError("supply/demand vector length mismatch")
        for i, row in enumerate(self.costs):
            if len(row) != self.cols:
                raise TransportError("cost table row {0} has wrong length".format(i))
            for j, cost in enumerate(row):
                if cost is not None and (not math.isfinite(cost) or cost < 0.0):
                    raise TransportError(
                        "cost[{0}][{1}] must be finite and non-negative".format(i, j)
                    )
        for i, supply in enumerate(self.supplies):
            if int(supply) != supply or supply < 0:
                raise TransportError("supply {0} must be a non-negative integer".format(i))
        for j, demand in enumerate(self.demands):
            if int(demand) != demand or demand < 0:
                raise TransportError("demand {0} must be a non-negative integer".format(j))
        if self.cell_caps is not None:
            if len(self.cell_caps) != self.rows:
                raise TransportError("cell_caps row count mismatch")
            for i, row in enumerate(self.cell_caps):
                if len(row) != self.cols:
                    raise TransportError("cell_caps row {0} has wrong length".format(i))
                for j, cap in enumerate(row):
                    if cap is not None and (int(cap) != cap or cap < 0):
                        raise TransportError(
                            "cell_caps[{0}][{1}] must be a non-negative integer".format(i, j)
                        )

    def total_supply(self) -> int:
        return int(sum(self.supplies))

    def total_demand(self) -> int:
        return int(sum(self.demands))

    def cap(self, i: int, j: int) -> Optional[int]:
        if self.cell_caps is None:
            return None
        return self.cell_caps[i][j]

    def as_dict(self) -> Dict[str, object]:
        return {
            "rows": list(self.row_labels),
            "cols": list(self.col_labels),
            "costs": [list(row) for row in self.costs],
            "supplies": list(self.supplies),
            "demands": list(self.demands),
            "units": self.units,
            "cell_caps": (
                None
                if self.cell_caps is None
                else [list(row) for row in self.cell_caps]
            ),
            "row_notes": list(self.row_notes),
            "col_notes": list(self.col_notes),
        }


@dataclass
class BalancedProblem:
    """A balanced tableau with an explicitly labelled dummy row/column.

    جدول متوازن مع صف/عمود وهمي موسوم بوضوح.
    """

    base: TransportProblem
    costs: List[List[Optional[float]]]
    supplies: List[int]
    demands: List[int]
    row_labels: List[str]
    col_labels: List[str]
    cell_caps: Optional[List[List[Optional[int]]]]
    dummy_row: Optional[int]
    dummy_col: Optional[int]
    shortage: int
    surplus: int

    @property
    def rows(self) -> int:
        return len(self.row_labels)

    @property
    def cols(self) -> int:
        return len(self.col_labels)

    def cost(self, i: int, j: int) -> Optional[float]:
        return self.costs[i][j]

    def cap(self, i: int, j: int) -> Optional[int]:
        if self.cell_caps is None:
            return None
        return self.cell_caps[i][j]

    def is_dummy_row(self, i: int) -> bool:
        return self.dummy_row is not None and i == self.dummy_row

    def is_dummy_col(self, j: int) -> bool:
        return self.dummy_col is not None and j == self.dummy_col

    def as_dict(self) -> Dict[str, object]:
        return {
            "rows": list(self.row_labels),
            "cols": list(self.col_labels),
            "costs": [list(row) for row in self.costs],
            "supplies": list(self.supplies),
            "demands": list(self.demands),
            "dummy_row": self.dummy_row,
            "dummy_col": self.dummy_col,
            "shortage": self.shortage,
            "surplus": self.surplus,
        }


@dataclass
class TransportResult:
    """One method's allocation and audit trail."""

    method: str
    allocation: List[List[float]]
    objective: float
    feasible: bool
    status: str
    unmet: int = 0
    unused: int = 0
    iterations: int = 0
    seconds: float = 0.0
    trace: List[Dict[str, object]] = field(default_factory=list)
    potentials_u: Optional[List[float]] = None
    potentials_v: Optional[List[float]] = None
    reduced_costs: Optional[List[List[Optional[float]]]] = None
    basis: List[Cell] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    initial_objective: Optional[float] = None

    def allocation_as_int(self) -> List[List[int]]:
        return [
            [
                int(round(value))
                if abs(value - round(value)) < 1e-6
                else int(value)
                for value in row
            ]
            for row in self.allocation
        ]

    def real_cells(self, problem: BalancedProblem) -> List[Dict[str, object]]:
        cells: List[Dict[str, object]] = []
        for i, row in enumerate(self.allocation):
            for j, quantity in enumerate(row):
                if quantity <= EPS:
                    continue
                cells.append(
                    {
                        "source": problem.row_labels[i],
                        "destination": problem.col_labels[j],
                        "quantity": int(round(quantity)),
                        "dummy_row": problem.is_dummy_row(i),
                        "dummy_col": problem.is_dummy_col(j),
                    }
                )
        return cells


# ---------------------------------------------------------------------------
# Balance
# ---------------------------------------------------------------------------
def balance_problem(problem: TransportProblem) -> BalancedProblem:
    """Balance supplies and demands with a labelled dummy only when needed.

    يوازن التوريد والطلب بصف/عمود وهمي فقط عند الحاجة، مع وسم واضح.
    """
    supply = problem.total_supply()
    demand = problem.total_demand()
    shortage = max(0, demand - supply)
    surplus = max(0, supply - demand)
    costs = [list(row) for row in problem.costs]
    supplies = list(problem.supplies)
    demands = list(problem.demands)
    row_labels = list(problem.row_labels)
    col_labels = list(problem.col_labels)
    caps = (
        None
        if problem.cell_caps is None
        else [list(row) for row in problem.cell_caps]
    )
    dummy_row: Optional[int] = None
    dummy_col: Optional[int] = None

    if surplus > 0:
        dummy_col = len(demands)
        col_labels.append("DUMMY_UNUSED_SUPPLY")
        demands.append(surplus)
        for row in costs:
            row.append(0.0)
        if caps is not None:
            for row in caps:
                row.append(None)
    elif shortage > 0:
        dummy_row = len(supplies)
        row_labels.append("DUMMY_UNMET_DEMAND")
        supplies.append(shortage)
        costs.append([0.0 for _ in demands])
        if caps is not None:
            caps.append([None for _ in demands])

    return BalancedProblem(
        base=problem,
        costs=costs,
        supplies=supplies,
        demands=demands,
        row_labels=row_labels,
        col_labels=col_labels,
        cell_caps=caps,
        dummy_row=dummy_row,
        dummy_col=dummy_col,
        shortage=shortage,
        surplus=surplus,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def blank_allocation(rows: int, cols: int) -> List[List[float]]:
    return [[0.0 for _ in range(cols)] for _ in range(rows)]


def remaining_cap(
    problem: BalancedProblem, i: int, j: int, allocation: List[List[float]]
) -> Optional[float]:
    cap = problem.cap(i, j)
    if cap is None:
        return None
    return max(0, cap - allocation[i][j])


def is_available(
    problem: BalancedProblem, i: int, j: int, allocation: List[List[float]]
) -> bool:
    if problem.costs[i][j] is None:
        return False
    if allocation_sum_row(allocation, i) >= problem.supplies[i] - EPS:
        return False
    if allocation_sum_col(allocation, j) >= problem.demands[j] - EPS:
        return False
    cap_remaining = remaining_cap(problem, i, j, allocation)
    return cap_remaining is None or cap_remaining > EPS


def allocation_sum_row(allocation: List[List[float]], i: int) -> float:
    return sum(allocation[i])


def allocation_sum_col(allocation: List[List[float]], j: int) -> float:
    return sum(allocation[i][j] for i in range(len(allocation)))


def compute_objective(
    problem: BalancedProblem, allocation: List[List[float]], real_only: bool = True
) -> float:
    """Cost of the allocation; dummy cells have zero cost and are excluded.

    تكلفة التخصيص؛ خلايا الصف/العمود الوهمي تكلفتها صفر ولا تُحسب.
    """
    total = 0.0
    for i, row in enumerate(allocation):
        if real_only and problem.is_dummy_row(i):
            continue
        for j, quantity in enumerate(row):
            if real_only and problem.is_dummy_col(j):
                continue
            cost = problem.costs[i][j]
            if cost is None:
                if quantity > EPS:
                    raise TransportError("prohibited cell has a positive allocation")
                continue
            total += cost * quantity
    return total


def result_from_allocation(
    balanced: BalancedProblem,
    method: str,
    allocation: List[List[float]],
    feasible: bool,
    status: str,
    trace: Optional[List[Dict[str, object]]] = None,
    seconds: float = 0.0,
    iterations: int = 0,
    notes: Optional[List[str]] = None,
) -> TransportResult:
    unmet = 0
    if balanced.dummy_row is not None:
        unmet = int(round(sum(allocation[balanced.dummy_row])))
    unused = 0
    if balanced.dummy_col is not None:
        unused = int(round(sum(row[balanced.dummy_col] for row in allocation)))
    return TransportResult(
        method=method,
        allocation=allocation,
        objective=compute_objective(balanced, allocation),
        feasible=feasible,
        status=status,
        unmet=unmet,
        unused=unused,
        iterations=iterations,
        seconds=seconds,
        trace=trace or [],
        notes=notes or [],
    )


def check_allocation(problem: BalancedProblem, allocation: List[List[float]]) -> List[str]:
    """Independent invariants for one allocation; returns error strings."""
    errors: List[str] = []
    if len(allocation) != problem.rows:
        return ["allocation row count mismatch"]
    for i, row in enumerate(allocation):
        if len(row) != problem.cols:
            errors.append("allocation row {0} length mismatch".format(i))
            continue
        row_sum = sum(row)
        if abs(row_sum - problem.supplies[i]) > 1e-6:
            errors.append(
                "row {0} sum {1} != supply {2}".format(
                    problem.row_labels[i], row_sum, problem.supplies[i]
                )
            )
        for j, quantity in enumerate(row):
            if abs(quantity - round(quantity)) > 1e-6:
                errors.append(
                    "fractional allocation at ({0},{1}): {2}".format(i, j, quantity)
                )
            if quantity < -1e-7:
                errors.append("negative allocation at ({0},{1})".format(i, j))
            if problem.costs[i][j] is None and quantity > 1e-7:
                errors.append("prohibited cell allocated at ({0},{1})".format(i, j))
            cap = problem.cap(i, j)
            if cap is not None and quantity > cap + 1e-6:
                errors.append(
                    "cell cap exceeded at ({0},{1}): {2} > {3}".format(
                        i, j, quantity, cap
                    )
                )
    for j in range(problem.cols):
        col_sum = sum(allocation[i][j] for i in range(problem.rows))
        if abs(col_sum - problem.demands[j]) > 1e-6:
            errors.append(
                "column {0} sum {1} != demand {2}".format(
                    problem.col_labels[j], col_sum, problem.demands[j]
                )
            )
    return errors


# ---------------------------------------------------------------------------
# VAM / least-cost
# ---------------------------------------------------------------------------
def _penalties(
    problem: BalancedProblem, allocation: List[List[float]]
) -> Tuple[Dict[int, Optional[float]], Dict[int, Optional[float]], List[str]]:
    """Row/column penalties over currently available cells.

    العقوبات تُحسب فقط على الخلايا غير الممنوعة وغير المشبعة؛ عند توفر خلية
    واحدة تُستخدم تكلفتها نفسها وتُذكر الملاحظة.
    """
    row_penalties: Dict[int, Optional[float]] = {}
    col_penalties: Dict[int, Optional[float]] = {}
    notes: List[str] = []
    for i in range(problem.rows):
        if allocation_sum_row(allocation, i) >= problem.supplies[i] - EPS:
            continue
        values = [
            problem.costs[i][j]
            for j in range(problem.cols)
            if is_available(problem, i, j, allocation)
        ]
        numeric = [float(value) for value in values if value is not None]
        if not numeric:
            row_penalties[i] = None
        elif len(numeric) == 1:
            row_penalties[i] = numeric[0]
            notes.append("row {0}: single available cell; penalty = its cost".format(i))
        else:
            numeric.sort()
            row_penalties[i] = numeric[1] - numeric[0]
    for j in range(problem.cols):
        if allocation_sum_col(allocation, j) >= problem.demands[j] - EPS:
            continue
        values = [
            problem.costs[i][j]
            for i in range(problem.rows)
            if is_available(problem, i, j, allocation)
        ]
        numeric = [float(value) for value in values if value is not None]
        if not numeric:
            col_penalties[j] = None
        elif len(numeric) == 1:
            col_penalties[j] = numeric[0]
            notes.append("column {0}: single available cell; penalty = its cost".format(j))
        else:
            numeric.sort()
            col_penalties[j] = numeric[1] - numeric[0]
    return row_penalties, col_penalties, notes


def choose_line(
    row_penalties: Dict[int, Optional[float]],
    col_penalties: Dict[int, Optional[float]],
) -> Optional[Tuple[str, int, float]]:
    candidates: List[Tuple[float, int, int, str]] = []
    for i, value in row_penalties.items():
        if value is not None:
            candidates.append((value, 1, -i, "row"))
    for j, value in col_penalties.items():
        if value is not None:
            candidates.append((value, 0, -j, "column"))
    if not candidates:
        return None
    # Maximum penalty; rows win ties; lower index wins ties.
    value, _kind_rank, negative_index, kind = max(candidates)
    return kind, -negative_index, value


def choose_cell_in_line(
    problem: BalancedProblem,
    allocation: List[List[float]],
    kind: str,
    index: int,
) -> Optional[Tuple[int, int, float]]:
    candidates: List[Tuple[float, int, int]] = []
    if kind == "row":
        for j in range(problem.cols):
            if is_available(problem, index, j, allocation):
                cost = problem.costs[index][j]
                if cost is not None:
                    candidates.append((float(cost), index, j))
    else:
        for i in range(problem.rows):
            if is_available(problem, i, index, allocation):
                cost = problem.costs[i][index]
                if cost is not None:
                    candidates.append((float(cost), i, index))
    if not candidates:
        return None
    cost, i, j = min(candidates)
    return i, j, cost


def _allocate_vam_least(
    problem: BalancedProblem, method: str, with_penalties: bool
) -> TransportResult:
    started = time.perf_counter()
    allocation = blank_allocation(problem.rows, problem.cols)
    remaining_supply = [float(value) for value in problem.supplies]
    remaining_demand = [float(value) for value in problem.demands]
    trace: List[Dict[str, object]] = []
    step = 0
    notes: List[str] = []

    while True:
        active_rows = [i for i, value in enumerate(remaining_supply) if value > EPS]
        active_cols = [j for j, value in enumerate(remaining_demand) if value > EPS]
        if not active_rows and not active_cols:
            break
        if not active_rows or not active_cols:
            notes.append("remaining supply/demand without an active line")
            break
        step += 1

        if with_penalties:
            row_penalties, col_penalties, penalty_notes = _penalties(problem, allocation)
            selection = choose_line(row_penalties, col_penalties)
            if selection is None:
                notes.append("no penalty-eligible line remains")
                break
            line_kind, line_index, line_penalty = selection
            cell = choose_cell_in_line(problem, allocation, line_kind, line_index)
            if cell is None:
                notes.append("selected line has no available cell")
                break
            i, j, cost = cell
        else:
            candidates: List[Tuple[float, int, int]] = []
            for i in active_rows:
                for j in active_cols:
                    if is_available(problem, i, j, allocation):
                        cell_cost = problem.costs[i][j]
                        if cell_cost is not None:
                            candidates.append((float(cell_cost), i, j))
            if not candidates:
                notes.append("no available cell remains (forbidden/capped)")
                break
            cost, i, j = min(candidates)
            line_kind, line_index, line_penalty = "global", -1, 0.0
            row_penalties = {}
            col_penalties = {}
            penalty_notes = []

        cap_remaining = remaining_cap(problem, i, j, allocation)
        quantity = min(remaining_supply[i], remaining_demand[j])
        if cap_remaining is not None:
            quantity = min(quantity, cap_remaining)
        if quantity <= EPS:
            notes.append("zero quantity at selected cell; stopping")
            break
        allocation[i][j] += quantity
        remaining_supply[i] -= quantity
        remaining_demand[j] -= quantity

        struck_rows = []
        struck_cols = []
        if remaining_supply[i] <= EPS:
            struck_rows.append(i)
        if remaining_demand[j] <= EPS:
            struck_cols.append(j)

        trace.append(
            {
                "step": step,
                "method": method,
                "row_penalties": {
                    problem.row_labels[key]: value
                    for key, value in sorted(row_penalties.items())
                },
                "col_penalties": {
                    problem.col_labels[key]: value
                    for key, value in sorted(col_penalties.items())
                },
                "penalty_notes": penalty_notes,
                "selected_line": {
                    "kind": line_kind,
                    "label": (
                        problem.row_labels[line_index]
                        if line_kind == "row"
                        else problem.col_labels[line_index]
                        if line_kind == "column"
                        else "global minimum"
                    ),
                    "index": line_index,
                    "penalty": line_penalty,
                },
                "cell": {
                    "row": i,
                    "col": j,
                    "row_label": problem.row_labels[i],
                    "col_label": problem.col_labels[j],
                    "cost": cost,
                },
                "quantity": quantity,
                "remaining_supply": {
                    problem.row_labels[k]: remaining_supply[k]
                    for k in range(problem.rows)
                },
                "remaining_demand": {
                    problem.col_labels[k]: remaining_demand[k]
                    for k in range(problem.cols)
                },
                "struck_rows": [problem.row_labels[k] for k in struck_rows],
                "struck_columns": [problem.col_labels[k] for k in struck_cols],
                "allocation": [list(row) for row in allocation],
            }
        )

    feasible = all(value <= EPS for value in remaining_supply) and all(
        value <= EPS for value in remaining_demand
    )
    return result_from_allocation(
        problem,
        method,
        allocation,
        feasible,
        "complete" if feasible else "partial/infeasible",
        trace=trace,
        seconds=time.perf_counter() - started,
        iterations=step,
        notes=notes,
    )


def solve_vam(problem: BalancedProblem) -> TransportResult:
    """VAM with deterministic maximum-penalty selection and full trace."""
    return _allocate_vam_least(problem, "VAM", with_penalties=True)


def solve_least_cost(problem: BalancedProblem) -> TransportResult:
    """Least-cost greedy allocation (a comparison baseline)."""
    return _allocate_vam_least(problem, "least-cost", with_penalties=False)


# ---------------------------------------------------------------------------
# North-west corner
# ---------------------------------------------------------------------------
def solve_northwest(problem: BalancedProblem) -> TransportResult:
    """Strict north-west corner; forbidden cells are refused, not bypassed."""
    started = time.perf_counter()
    for row in problem.costs:
        if any(cost is None for cost in row):
            raise TransportError(
                "north-west corner requires every cell to be admissible"
            )
    allocation = blank_allocation(problem.rows, problem.cols)
    remaining_supply = [float(value) for value in problem.supplies]
    remaining_demand = [float(value) for value in problem.demands]
    trace: List[Dict[str, object]] = []
    i = 0
    j = 0
    step = 0
    while i < problem.rows and j < problem.cols:
        step += 1
        cap_remaining = remaining_cap(problem, i, j, allocation)
        quantity = min(remaining_supply[i], remaining_demand[j])
        if cap_remaining is not None:
            quantity = min(quantity, cap_remaining)
        if quantity < -EPS:
            raise TransportError("negative north-west quantity")
        quantity = max(0.0, quantity)
        allocation[i][j] += quantity
        remaining_supply[i] -= quantity
        remaining_demand[j] -= quantity
        trace.append(
            {
                "step": step,
                "method": "NWC",
                "cell": {
                    "row": i,
                    "col": j,
                    "row_label": problem.row_labels[i],
                    "col_label": problem.col_labels[j],
                    "cost": problem.costs[i][j],
                },
                "quantity": quantity,
                "allocation": [list(row) for row in allocation],
            }
        )
        if remaining_supply[i] <= EPS and remaining_demand[j] <= EPS:
            i += 1
            j += 1
        elif remaining_supply[i] <= EPS:
            i += 1
        else:
            j += 1
    feasible = all(value <= EPS for value in remaining_supply) and all(
        value <= EPS for value in remaining_demand
    )
    return result_from_allocation(
        problem,
        "NWC",
        allocation,
        feasible,
        "complete" if feasible else "partial/infeasible",
        trace=trace,
        seconds=time.perf_counter() - started,
        iterations=step,
        notes=[] if feasible else ["north-west corner did not satisfy the table"],
    )


# ---------------------------------------------------------------------------
# Exact transportation optimum (independent check)
# ---------------------------------------------------------------------------
def solve_transport_exact(problem: BalancedProblem) -> Optional[TransportResult]:
    """Exact integer transportation optimum with SciPy HiGHS, if available.

    الحل الأمثل الدقيق لجدول النقل باستخدام SciPy؛ يُستخدم للتحقق المستقل.
    """
    try:
        import numpy as np
        from scipy.optimize import Bounds, LinearConstraint, milp
        from scipy.sparse import coo_matrix
    except Exception:  # pragma: no cover - optional dependency
        return None
    started = time.perf_counter()
    rows, cols = problem.rows, problem.cols
    variable_count = rows * cols
    objective = np.zeros(variable_count)
    lower = np.zeros(variable_count)
    upper = np.zeros(variable_count)
    for i in range(rows):
        for j in range(cols):
            index = i * cols + j
            cost = problem.costs[i][j]
            if cost is None:
                upper[index] = 0.0
            else:
                objective[index] = float(cost)
                upper[index] = float(min(problem.supplies[i], problem.demands[j]))
                cap = problem.cap(i, j)
                if cap is not None:
                    upper[index] = min(upper[index], float(cap))
    row_indices: List[int] = []
    col_indices: List[int] = []
    values: List[float] = []
    constraint_lower: List[float] = []
    constraint_upper: List[float] = []
    row_index = 0
    for i in range(rows):
        for j in range(cols):
            row_indices.append(row_index)
            col_indices.append(i * cols + j)
            values.append(1.0)
        constraint_lower.append(float(problem.supplies[i]))
        constraint_upper.append(float(problem.supplies[i]))
        row_index += 1
    for j in range(cols):
        for i in range(rows):
            row_indices.append(row_index)
            col_indices.append(i * cols + j)
            values.append(1.0)
        constraint_lower.append(float(problem.demands[j]))
        constraint_upper.append(float(problem.demands[j]))
        row_index += 1
    matrix = coo_matrix(
        (values, (row_indices, col_indices)), shape=(row_index, variable_count)
    ).tocsr()
    result = milp(
        c=objective,
        integrality=np.ones(variable_count),
        bounds=Bounds(lower, upper),
        constraints=LinearConstraint(matrix, constraint_lower, constraint_upper),
        options={"time_limit": 60.0, "mip_rel_gap": 0.0},
    )
    if not result.success or result.x is None:
        return TransportResult(
            method="exact-MILP",
            allocation=blank_allocation(rows, cols),
            objective=math.inf,
            feasible=False,
            status="solver failed: {0}".format(getattr(result, "message", "unknown")),
            seconds=time.perf_counter() - started,
        )
    allocation = blank_allocation(rows, cols)
    for i in range(rows):
        for j in range(cols):
            allocation[i][j] = float(round(result.x[i * cols + j]))
    return result_from_allocation(
        problem,
        "exact-MILP",
        allocation,
        True,
        "optimal (independent MILP)",
        seconds=time.perf_counter() - started,
        notes=["Exact integer optimum for the balanced kit-only tableau."],
    )
