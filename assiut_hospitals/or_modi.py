"""MODI (u-v) optimality iterations for the kit-only transportation tableau.

تكرارات MODI (u-v) لجدول النقل الخاص بالكراتين فقط.

MODI is applied to the balanced table produced by :mod:`or_transport`.  It
respects forbidden cells by keeping them out of the basis and out of entering
candidates.  Binding cell upper bounds require a different bounded-transport
algorithm; that case raises an explicit error.  Road capacities are enforced by
the separate network MILP.

يطبّق MODI على الجدول المتوازن، ويحافظ على الخلايا الممنوعة خارج الأساس،
ويرفض ادعاء الأمثلية عند وجود حدود خلايا ملزمة.
"""

from __future__ import annotations

import math
import time
from typing import Dict, List, Optional, Set, Tuple

from .or_transport import (
    EPS,
    BalancedProblem,
    Cell,
    TransportError,
    TransportResult,
    blank_allocation,
    result_from_allocation,
    solve_least_cost,
    solve_northwest,
    solve_transport_exact,
    solve_vam,
)


def _basis_from_allocation(
    problem: BalancedProblem, allocation: List[List[float]]
) -> Tuple[Set[Cell], List[Cell], List[str]]:
    """Build an independent basis, adding zero basic cells where needed."""
    basis: Set[Cell] = set()
    added: List[Cell] = []
    notes: List[str] = []
    for i in range(problem.rows):
        for j in range(problem.cols):
            if allocation[i][j] > EPS:
                if problem.costs[i][j] is None:
                    raise TransportError(
                        "allocation uses prohibited cell ({0},{1})".format(i, j)
                    )
                basis.add((i, j))

    parent = list(range(problem.rows + problem.cols))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> bool:
        ra, rb = find(a), find(b)
        if ra == rb:
            return False
        parent[rb] = ra
        return True

    for i, j in sorted(basis):
        if not union(i, problem.rows + j):
            raise TransportError(
                "initial allocation has a cycle; a basic feasible solution is required"
            )

    for i in range(problem.rows):
        for j in range(problem.cols):
            if (i, j) in basis or problem.costs[i][j] is None:
                continue
            if union(i, problem.rows + j):
                basis.add((i, j))
                added.append((i, j))

    if len(basis) != problem.rows + problem.cols - 1:
        raise TransportError(
            "forbidden cells disconnect the tableau; cannot build a spanning basis"
        )
    if added:
        notes.append(
            "degeneracy handled by adding {0} zero basic cell(s): {1}".format(
                len(added),
                ", ".join(
                    "({0},{1})".format(problem.row_labels[i], problem.col_labels[j])
                    for i, j in added
                ),
            )
        )
    return basis, added, notes


def _potentials(
    problem: BalancedProblem, basis: Set[Cell]
) -> Tuple[List[float], List[float]]:
    """Solve u_i + v_j = c_ij for basic cells."""
    adjacency: Dict[int, List[Tuple[int, float]]] = {}
    for i, j in basis:
        cost = problem.costs[i][j]
        if cost is None:
            raise TransportError("basis contains a prohibited cell")
        adjacency.setdefault(i, []).append((problem.rows + j, cost))
        adjacency.setdefault(problem.rows + j, []).append((i, cost))

    u: List[Optional[float]] = [None] * problem.rows
    v: List[Optional[float]] = [None] * problem.cols
    if problem.rows == 0:
        return [], []
    u[0] = 0.0
    queue = [0]
    while queue:
        node = queue.pop(0)
        if node < problem.rows:
            i = node
            for neighbor, cost in adjacency.get(node, []):
                j = neighbor - problem.rows
                if u[i] is None:
                    continue
                expected = cost - u[i]
                if v[j] is None:
                    v[j] = expected
                    queue.append(neighbor)
                elif abs(v[j] - expected) > 1e-6:
                    raise TransportError("inconsistent basic potentials")
        else:
            j = node - problem.rows
            for neighbor, cost in adjacency.get(node, []):
                i = neighbor
                if v[j] is None:
                    continue
                expected = cost - v[j]
                if u[i] is None:
                    u[i] = expected
                    queue.append(neighbor)
                elif abs(u[i] - expected) > 1e-6:
                    raise TransportError("inconsistent basic potentials")

    if any(value is None for value in u) or any(value is None for value in v):
        raise TransportError("basis is disconnected; potentials cannot be computed")
    return [float(value) for value in u], [float(value) for value in v]


def _reduced_costs(
    problem: BalancedProblem,
    basis: Set[Cell],
    u: List[float],
    v: List[float],
) -> List[List[Optional[float]]]:
    table: List[List[Optional[float]]] = []
    for i in range(problem.rows):
        row: List[Optional[float]] = []
        for j in range(problem.cols):
            cost = problem.costs[i][j]
            if cost is None:
                row.append(None)
            elif (i, j) in basis:
                row.append(0.0)
            else:
                row.append(cost - u[i] - v[j])
        table.append(row)
    return table


def _find_cycle(
    problem: BalancedProblem, basis: Set[Cell], row: int, col: int
) -> List[Cell]:
    """Find the unique basic path from ``row`` to ``col`` and add entering."""
    adjacency: Dict[int, List[Tuple[int, Cell]]] = {}
    for i, j in basis:
        adjacency.setdefault(i, []).append((problem.rows + j, (i, j)))
        adjacency.setdefault(problem.rows + j, []).append((i, (i, j)))

    start = row
    target = problem.rows + col
    parent: Dict[int, Optional[int]] = {start: None}
    parent_cell: Dict[int, Cell] = {}
    queue = [start]
    while queue:
        node = queue.pop(0)
        if node == target:
            break
        for neighbor, cell in adjacency.get(node, []):
            if neighbor in parent:
                continue
            parent[neighbor] = node
            parent_cell[neighbor] = cell
            queue.append(neighbor)
    if target not in parent:
        raise TransportError("cannot find a MODI adjustment cycle; basis is disconnected")

    path_cells: List[Cell] = []
    current = target
    while parent[current] is not None:
        path_cells.append(parent_cell[current])
        current = parent[current]
    path_cells.reverse()
    cycle = [(row, col)] + path_cells
    if len(cycle) % 2 != 0:
        raise TransportError("MODI cycle has odd length")
    return cycle


def solve_modi(
    problem: BalancedProblem,
    initial: TransportResult,
    max_iterations: int = 500,
) -> TransportResult:
    """Classical MODI optimality iterations with a full audit trail.

    يبدأ من حل VAM ويضيف خلايا أساس صفرية عند التدهور، ثم يتتبع الفرص
    والتكاليف المخفضة والدورات حتى الوصول إلى الأمثلية أو حد التكرار.
    """
    if not initial.feasible:
        raise TransportError("MODI requires a feasible initial allocation")
    if problem.cell_caps is not None:
        if any(
            cap is not None
            and cap < min(problem.supplies[i], problem.demands[j]) - EPS
            for i, row in enumerate(problem.cell_caps)
            for j, cap in enumerate(row)
        ):
            raise TransportError(
                "MODI with binding cell caps is not implemented; use the network MILP"
            )

    started = time.perf_counter()
    allocation = [list(row) for row in initial.allocation]
    basis, added, notes = _basis_from_allocation(problem, allocation)
    iterations = 0
    trace: List[Dict[str, object]] = []
    while iterations < max_iterations:
        u, v = _potentials(problem, basis)
        reduced = _reduced_costs(problem, basis, u, v)
        entering: Optional[Cell] = None
        entering_value = -EPS
        for i in range(problem.rows):
            for j in range(problem.cols):
                value = reduced[i][j]
                if value is None or (i, j) in basis:
                    continue
                if value < entering_value:
                    entering_value = value
                    entering = (i, j)
        if entering is None:
            break
        iterations += 1
        i, j = entering
        cycle = _find_cycle(problem, basis, i, j)
        plus = cycle[0::2]
        minus = cycle[1::2]
        theta = min(allocation[a][b] for a, b in minus)

        if theta <= EPS:
            leaving = next(
                ((a, b) for a, b in minus if allocation[a][b] <= EPS), minus[0]
            )
            basis.add(entering)
            basis.discard(leaving)
            trace.append(
                {
                    "iteration": iterations,
                    "u": list(u),
                    "v": list(v),
                    "reduced_costs": [list(row) for row in reduced],
                    "entering": {
                        "row": i,
                        "col": j,
                        "row_label": problem.row_labels[i],
                        "col_label": problem.col_labels[j],
                        "reduced_cost": entering_value,
                    },
                    "cycle": [list(cell) for cell in cycle],
                    "theta": 0.0,
                    "degenerate": True,
                    "leaving": list(leaving),
                    "leaving_label": [
                        problem.row_labels[leaving[0]],
                        problem.col_labels[leaving[1]],
                    ],
                    "allocation": [list(row) for row in allocation],
                }
            )
            continue

        for a, b in plus:
            allocation[a][b] += theta
        for a, b in minus:
            allocation[a][b] -= theta
        zero_minus = [
            (allocation[a][b], a, b) for a, b in minus if allocation[a][b] <= EPS
        ]
        if zero_minus:
            _, leave_i, leave_j = min(zero_minus)
        else:
            _, leave_i, leave_j = min((allocation[a][b], a, b) for a, b in minus)
        basis.add(entering)
        basis.discard((leave_i, leave_j))
        if len(basis) != problem.rows + problem.cols - 1:
            basis, extra_added, extra_notes = _basis_from_allocation(problem, allocation)
            added.extend(extra_added)
            notes.extend(extra_notes)
        trace.append(
            {
                "iteration": iterations,
                "u": list(u),
                "v": list(v),
                "reduced_costs": [list(row) for row in reduced],
                "entering": {
                    "row": i,
                    "col": j,
                    "row_label": problem.row_labels[i],
                    "col_label": problem.col_labels[j],
                    "reduced_cost": entering_value,
                },
                "cycle": [list(cell) for cell in cycle],
                "theta": theta,
                "degenerate": False,
                "leaving": [leave_i, leave_j],
                "leaving_label": [
                    problem.row_labels[leave_i],
                    problem.col_labels[leave_j],
                ],
                "allocation": [list(row) for row in allocation],
            }
        )
    else:
        notes.append("MODI iteration limit reached before optimality")

    u, v = _potentials(problem, basis)
    reduced = _reduced_costs(problem, basis, u, v)
    optimal = all(
        value is None or value >= -1e-6 or (i, j) in basis
        for i, row in enumerate(reduced)
        for j, value in enumerate(row)
    )
    result = result_from_allocation(
        problem,
        "MODI",
        allocation,
        True,
        "optimal" if optimal else "iteration limit / not proven optimal",
        trace=trace,
        seconds=time.perf_counter() - started,
        iterations=iterations,
        notes=notes,
    )
    result.potentials_u = u
    result.potentials_v = v
    result.reduced_costs = reduced
    result.basis = sorted(basis)
    result.initial_objective = initial.objective
    return result


def compare_transport_methods(
    problem: BalancedProblem, include_exact: bool = True
) -> Dict[str, TransportResult]:
    """Run NWC, least-cost, VAM, MODI, and optionally an exact MILP."""
    results: Dict[str, TransportResult] = {}
    errors: Dict[str, str] = {}
    for name, function in (
        ("NWC", solve_northwest),
        ("least-cost", solve_least_cost),
        ("VAM", solve_vam),
    ):
        try:
            results[name] = function(problem)
        except TransportError as exc:
            errors[name] = str(exc)
    vam = results.get("VAM")
    if vam is not None:
        try:
            results["MODI"] = solve_modi(problem, vam)
        except TransportError as exc:
            errors["MODI"] = str(exc)
    if include_exact:
        exact = solve_transport_exact(problem)
        if exact is not None:
            results["exact-MILP"] = exact
    for name, message in errors.items():
        results[name] = TransportResult(
            method=name,
            allocation=blank_allocation(problem.rows, problem.cols),
            objective=math.inf,
            feasible=False,
            status="error: {0}".format(message),
        )
    return results
