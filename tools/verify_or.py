#!/usr/bin/env python
"""Independent verification of the Assiut Operations Research extension.

تحقق مستقل من امتداد بحوث العمليات في أسيوط.

The verifier deliberately recomputes the physical consequences of the chosen
plan instead of trusting the report:

* every available matrix cell is re-routed with Bellman-Ford;
* every allocation is checked against row/column conservation, forbidden
  cells, integer quantities, and dummy handling;
* the VAM trace is replayed step by step and the MODI cycle/potential/reduced
  cost conditions are checked independently;
* small tableaux are compared with exhaustive enumeration, an exact MILP, and
  unbalanced/infeasible cases;
* every selected network route is checked for continuity, prohibited lanes,
  lane capacity, fleet, supply, demand, and bed limits.

No file is written.  Exit code 0 means every check passed.

لا يكتب هذا الملف أي تقرير؛ الشيفرة 0 تعني نجاح جميع الفحوص.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  # pragma: no cover
    pass

from assiut_hospitals.or_config import ORConfigError, load_or_config  # noqa: E402
from assiut_hospitals.or_modi import solve_modi  # noqa: E402
from assiut_hospitals.or_network import NetworkSolver  # noqa: E402
from assiut_hospitals.or_planning import ORPlanResult, ORPlanner  # noqa: E402
from assiut_hospitals.or_transport import (  # noqa: E402
    EPS,
    BalancedProblem,
    TransportError,
    TransportProblem,
    balance_problem,
    check_allocation,
    compute_objective,
    solve_transport_exact,
    solve_vam,
)

TOL = 1e-6

CHECKS: List[Tuple[bool, str, str]] = []


def check(condition: bool, label: str, detail: str = "") -> bool:
    """Record one PASS/FAIL line."""
    CHECKS.append((bool(condition), label, detail))
    print("  {0:<58} {1}{2}".format(
        label, "PASS" if condition else "FAIL", "  " + detail if detail else ""
    ))
    return bool(condition)


def _same(a: float, b: float, tolerance: float = TOL) -> bool:
    return abs(float(a) - float(b)) <= tolerance


def _matrix_integer(matrix: Sequence[Sequence[float]]) -> bool:
    return all(
        abs(float(value) - round(float(value))) <= TOL
        for row in matrix
        for value in row
    )


def _matrix_no_forbidden(
    problem: BalancedProblem, allocation: Sequence[Sequence[float]]
) -> bool:
    return all(
        allocation[i][j] <= EPS or problem.costs[i][j] is not None
        for i in range(problem.rows)
        for j in range(problem.cols)
    )


# ---------------------------------------------------------------------------
# Small exact enumeration
# ---------------------------------------------------------------------------
def exhaustive_minimum(problem: BalancedProblem) -> Tuple[Optional[float], Optional[List[List[int]]]]:
    """Exhaustively enumerate every integral feasible transportation plan.

    This is intentionally separate from the SciPy MILP.  It is only used on
    tiny tableaux, where exhaustive output is authoritative.
    """
    rows = problem.rows
    cols = problem.cols
    best = math.inf
    best_allocation: Optional[List[List[int]]] = None
    allocation = [[0 for _ in range(cols)] for _ in range(rows)]
    col_used = [0 for _ in range(cols)]

    def finish_row(i: int, remaining: int, current_cost: float) -> None:
        nonlocal best, best_allocation
        if i == rows:
            if remaining == 0 and all(
                col_used[j] == int(problem.demands[j]) for j in range(cols)
            ):
                if current_cost < best - TOL:
                    best = current_cost
                    best_allocation = [list(row) for row in allocation]
            return
        if current_cost >= best - TOL:
            return

        def fill_cell(j: int, row_left: int, row_cost: float) -> None:
            if j == cols:
                if row_left == 0:
                    finish_row(i + 1, 0, row_cost)
                return
            max_here = min(row_left, int(problem.demands[j]) - col_used[j])
            cap = problem.cap(i, j)
            if cap is not None:
                max_here = min(max_here, int(cap))
            cost = problem.costs[i][j]
            if cost is None:
                allocation[i][j] = 0
                fill_cell(j + 1, row_left, row_cost)
                return
            for quantity in range(max_here + 1):
                allocation[i][j] = quantity
                col_used[j] += quantity
                fill_cell(j + 1, row_left - quantity, row_cost + cost * quantity)
                col_used[j] -= quantity
            allocation[i][j] = 0

        fill_cell(0, int(problem.supplies[i]), current_cost)

    finish_row(0, 0, 0.0)
    return (None if best_allocation is None else best), best_allocation


def verify_small_exact() -> None:
    print("\n-- small tableau: exhaustive enumeration, VAM, MODI, exact MILP --")
    problem = TransportProblem(
        row_labels=["S1", "S2", "S3"],
        col_labels=["D1", "D2", "D3"],
        costs=[[11.0, 1.0, 1.0], [1.0, 21.0, 18.0], [1.0, 29.0, 13.0]],
        supplies=[3, 4, 5],
        demands=[4, 3, 5],
    )
    balanced = balance_problem(problem)
    best, best_allocation = exhaustive_minimum(balanced)
    check(best is not None, "small exhaustive instance is feasible")
    vam = solve_vam(balanced)
    modi = solve_modi(balanced, vam)
    exact = solve_transport_exact(balanced)
    check(vam.feasible and modi.feasible, "small VAM and MODI are feasible")
    check(exact is not None and exact.feasible, "small exact MILP is feasible")
    if best is not None:
        check(
            exact is not None and _same(exact.objective, best, 1e-5),
            "small exact MILP equals exhaustive optimum",
            "{0} vs {1}".format(
                None if exact is None else exact.objective, best
            ),
        )
        check(
            _same(modi.objective, best, 1e-5),
            "small MODI equals exhaustive optimum",
            "{0} vs {1}".format(modi.objective, best),
        )
        check(
            vam.objective + 1e-5 >= best,
            "small VAM is not below the true optimum",
        )
        if best_allocation is not None:
            check(
                _matrix_integer(modi.allocation)
                and _matrix_no_forbidden(balanced, modi.allocation),
                "small MODI allocation is integral and avoids forbidden cells",
            )
    check(len(modi.basis) == balanced.rows + balanced.cols - 1, "small MODI basis has m+n-1 cells")

    # Forbidden cell retained by all methods.
    forbidden = TransportProblem(
        row_labels=["S1", "S2"],
        col_labels=["D1", "D2"],
        costs=[[1.0, None], [1.0, 2.0]],
        supplies=[1, 2],
        demands=[1, 2],
    )
    forbidden_balanced = balance_problem(forbidden)
    forbidden_exact = solve_transport_exact(forbidden_balanced)
    forbidden_vam = solve_vam(forbidden_balanced)
    forbidden_modi = solve_modi(forbidden_balanced, forbidden_vam)
    check(
        forbidden_exact is not None
        and forbidden_exact.feasible
        and _matrix_no_forbidden(forbidden_balanced, forbidden_exact.allocation),
        "forbidden-cell exact allocation is valid",
    )
    check(
        _matrix_no_forbidden(forbidden_balanced, forbidden_vam.allocation)
        and _matrix_no_forbidden(forbidden_balanced, forbidden_modi.allocation),
        "VAM and MODI never allocate a forbidden cell",
    )

    # A binding cap must be handled by the exact MILP and rejected explicitly by
    # the standard MODI path, rather than silently ignored.
    capped = TransportProblem(
        row_labels=["S1", "S2"],
        col_labels=["D1", "D2"],
        costs=[[1.0, 2.0], [2.0, 1.0]],
        supplies=[3, 3],
        demands=[3, 3],
        cell_caps=[[1, None], [None, None]],
    )
    capped_balanced = balance_problem(capped)
    capped_exact = solve_transport_exact(capped_balanced)
    check(
        capped_exact is not None
        and capped_exact.feasible
        and capped_exact.allocation[0][0] <= 1 + EPS,
        "binding cell cap is respected by the exact MILP",
    )
    cap_rejected = False
    try:
        solve_modi(capped_balanced, solve_vam(capped_balanced))
    except TransportError as exc:
        cap_rejected = "cell caps" in str(exc)
    check(cap_rejected, "binding cap is rejected explicitly by standard MODI")

    # Unbalanced cases: a dummy is added only when justified.
    surplus = TransportProblem(
        row_labels=["S"], col_labels=["D"], costs=[[2.0]], supplies=[20], demands=[10]
    )
    surplus_balanced = balance_problem(surplus)
    surplus_vam = solve_vam(surplus_balanced)
    check(
        surplus_balanced.dummy_col is not None and surplus_vam.unused == 10,
        "surplus table gets a dummy column and reports 10 unused",
    )
    shortage = TransportProblem(
        row_labels=["S"], col_labels=["D"], costs=[[2.0]], supplies=[10], demands=[20]
    )
    shortage_balanced = balance_problem(shortage)
    shortage_vam = solve_vam(shortage_balanced)
    check(
        shortage_balanced.dummy_row is not None and shortage_vam.unmet == 10,
        "shortage table gets a dummy row and reports 10 unmet",
    )

    infeasible = TransportProblem(
        row_labels=["S"], col_labels=["D"], costs=[[None]], supplies=[10], demands=[10]
    )
    infeasible_balanced = balance_problem(infeasible)
    infeasible_exact = solve_transport_exact(infeasible_balanced)
    check(
        infeasible_exact is not None and not infeasible_exact.feasible,
        "a completely forbidden tableau is reported as infeasible",
    )


# ---------------------------------------------------------------------------
# VAM / MODI replay
# ---------------------------------------------------------------------------
def _vam_trace_checks(problem: BalancedProblem, result) -> None:
    vam = result
    check(vam.feasible, "VAM result is feasible")
    check(len(vam.trace) == vam.iterations, "VAM trace length equals iteration count")
    check(
        not check_allocation(problem, vam.allocation),
        "VAM final allocation passes independent conservation checks",
        "; ".join(check_allocation(problem, vam.allocation)[:2]),
    )
    previous = [[0.0 for _ in range(problem.cols)] for _ in range(problem.rows)]
    trace_ok = True
    detail = ""
    for item in vam.trace:
        selected = item.get("selected_line", {})
        cell = item.get("cell", {})
        row = int(cell.get("row", -1))
        col = int(cell.get("col", -1))
        if not (0 <= row < problem.rows and 0 <= col < problem.cols):
            trace_ok = False
            detail = "bad selected cell"
            break
        if problem.costs[row][col] is None:
            trace_ok = False
            detail = "selected forbidden cell"
            break
        row_penalties = item.get("row_penalties", {})
        col_penalties = item.get("col_penalties", {})
        numeric = [value for value in list(row_penalties.values()) + list(col_penalties.values()) if value is not None]
        if not numeric:
            trace_ok = False
            detail = "no penalty available"
            break
        selected_penalty = float(selected.get("penalty", -1.0))
        if not _same(selected_penalty, max(numeric)):
            trace_ok = False
            detail = "selected penalty is not the maximum penalty"
            break
        if not _same(float(cell.get("cost")), float(problem.costs[row][col])):
            trace_ok = False
            detail = "trace cost does not match the cost table"
            break
        quantity = float(item.get("quantity", -1.0))
        if quantity < -TOL:
            trace_ok = False
            detail = "negative VAM quantity"
            break
        before_row = sum(previous[row])
        before_col = sum(previous[i][col] for i in range(problem.rows))
        if quantity > problem.supplies[row] - before_row + TOL:
            trace_ok = False
            detail = "VAM quantity exceeds remaining supply"
            break
        if quantity > problem.demands[col] - before_col + TOL:
            trace_ok = False
            detail = "VAM quantity exceeds remaining demand"
            break
        allocation = item.get("allocation", [])
        if len(allocation) != problem.rows:
            trace_ok = False
            detail = "bad trace allocation shape"
            break
        changed = False
        for i in range(problem.rows):
            for j in range(problem.cols):
                expected = previous[i][j] + (quantity if (i, j) == (row, col) else 0.0)
                if not _same(float(allocation[i][j]), expected):
                    changed = True
        if changed:
            trace_ok = False
            detail = "VAM allocation update is not a single-cell allocation"
            break
        for i, row_values in enumerate(allocation):
            if sum(row_values) > problem.supplies[i] + TOL:
                trace_ok = False
                detail = "VAM trace row exceeds supply"
                break
            if trace_ok:
                for j in range(problem.cols):
                    if sum(allocation[k][j] for k in range(problem.rows)) > problem.demands[j] + TOL:
                        trace_ok = False
                        detail = "VAM trace column exceeds demand"
                        break
        if not trace_ok:
            break
        previous = [[float(value) for value in row_values] for row_values in allocation]
    check(trace_ok, "VAM penalties, selections, quantities, and allocations replay correctly", detail)
    if vam.trace:
        final_trace = vam.trace[-1].get("allocation", [])
        check(
            all(
                _same(float(final_trace[i][j]), float(vam.allocation[i][j]))
                for i in range(problem.rows)
                for j in range(problem.cols)
            ),
            "VAM final trace allocation equals the returned allocation",
        )
    total_allocated = sum(sum(row) for row in vam.allocation)
    check(
        _same(total_allocated, sum(problem.supplies)),
        "VAM allocates every balanced supply unit",
    )


def _modi_trace_checks(problem: BalancedProblem, vam, modi) -> None:
    check(modi.feasible, "MODI result is feasible")
    check(modi.status == "optimal", "MODI reports the optimality test passed", modi.status)
    check(len(modi.basis) == problem.rows + problem.cols - 1, "MODI final basis has m+n-1 cells")
    check(
        all(problem.costs[i][j] is not None for i, j in modi.basis),
        "MODI final basis contains no forbidden cell",
    )
    if modi.potentials_u is not None and modi.potentials_v is not None:
        basis_ok = all(
            _same(
                float(modi.potentials_u[i] + modi.potentials_v[j]),
                float(problem.costs[i][j]),
            )
            for i, j in modi.basis
        )
        check(basis_ok, "MODI potentials satisfy every basic cell")
        reduced_ok = modi.reduced_costs is not None
        if reduced_ok:
            for i in range(problem.rows):
                for j in range(problem.cols):
                    value = modi.reduced_costs[i][j]
                    cost = problem.costs[i][j]
                    if cost is None:
                        if value is not None:
                            reduced_ok = False
                        continue
                    expected = cost - modi.potentials_u[i] - modi.potentials_v[j]
                    if value is None or not _same(float(value), float(expected)):
                        reduced_ok = False
                        break
                    if (i, j) not in set(modi.basis) and value < -TOL:
                        reduced_ok = False
                        break
        check(reduced_ok, "MODI final reduced costs are optimal and internally consistent")
    if modi.initial_objective is not None:
        check(
            _same(float(modi.initial_objective), float(vam.objective)),
            "MODI initial objective equals the VAM objective",
        )
    check(
        _same(float(modi.objective), compute_objective(problem, modi.allocation)),
        "MODI objective equals its final allocation cost",
    )
    check(
        not check_allocation(problem, modi.allocation),
        "MODI final allocation passes independent conservation checks",
    )
    previous = [[float(value) for value in row] for row in vam.allocation]
    trace_ok = True
    detail = ""
    for item in modi.trace:
        entering = item.get("entering", {})
        i = int(entering.get("row", -1))
        j = int(entering.get("col", -1))
        if not (0 <= i < problem.rows and 0 <= j < problem.cols):
            trace_ok = False
            detail = "bad MODI entering cell"
            break
        reduced = item.get("reduced_costs", [])
        if len(reduced) != problem.rows or any(len(row) != problem.cols for row in reduced):
            trace_ok = False
            detail = "bad MODI reduced-cost table"
            break
        if not _same(float(entering.get("reduced_cost", 0.0)), float(reduced[i][j])):
            trace_ok = False
            detail = "MODI entering reduced cost mismatch"
            break
        cycle = item.get("cycle", [])
        if len(cycle) < 4 or len(cycle) % 2 != 0 or tuple(cycle[0]) != (i, j):
            trace_ok = False
            detail = "MODI cycle is not an even closed path beginning at the entering cell"
            break
        cycle_ok = True
        for left, right in zip(cycle, cycle[1:] + cycle[:1]):
            if left[0] != right[0] and left[1] != right[1]:
                cycle_ok = False
                break
        if not cycle_ok:
            trace_ok = False
            detail = "MODI cycle cells do not alternate row/column"
            break
        plus = [tuple(cell) for cell in cycle[0::2]]
        minus = [tuple(cell) for cell in cycle[1::2]]
        theta = min(previous[a][b] for a, b in minus)
        if not _same(float(item.get("theta", 0.0)), float(theta)):
            trace_ok = False
            detail = "MODI theta does not equal the minimum minus-cell allocation"
            break
        updated = [[previous[a][b] for b in range(problem.cols)] for a in range(problem.rows)]
        for a, b in plus:
            updated[a][b] += theta
        for a, b in minus:
            updated[a][b] -= theta
        trace_allocation = item.get("allocation", [])
        if len(trace_allocation) != problem.rows:
            trace_ok = False
            detail = "bad MODI trace allocation shape"
            break
        if any(
            not _same(float(trace_allocation[a][b]), float(max(0.0, updated[a][b])))
            for a in range(problem.rows)
            for b in range(problem.cols)
        ):
            trace_ok = False
            detail = "MODI allocation does not match the cycle adjustment"
            break
        previous = [[float(value) for value in row] for row in trace_allocation]
    check(trace_ok, "MODI cycles, theta values, and allocation updates replay correctly", detail)


# ---------------------------------------------------------------------------
# Full plan verification
# ---------------------------------------------------------------------------
def verify_routes(result: ORPlanResult) -> None:
    print("\n-- route/matrix consistency --")
    graph = result.network.lane_graph
    router = None
    # The planner object is not stored in the result, so reconstruct the small
    # routing view needed for checks from the result's network/config.
    from assiut_hospitals.or_router import DistanceRouter

    router = DistanceRouter(
        result.network,
        vehicle_class=result.config.vehicle_class,
        explicit_prohibited_lanes=result.config.explicit_prohibited_lanes,
        max_point_snap_m=result.config.max_point_snap_m,
    )
    check(
        router.prohibited
        == {
            lane
            for lane in graph.lane_info
            if not graph.lane_allowed(lane, result.config.vehicle_class)
        }
        | set(result.config.explicit_prohibited_lanes),
        "router prohibition set matches the class rules plus explicit closures",
    )
    cells = list(result.kit_cells.values()) + list(result.patient_cells.values())
    check(len(cells) > 0, "route matrices contain cells")
    check(
        len(result.kit_cells)
        == len([h for h in result.hospitals.values() if h.source_active]) * len(result.zones),
        "kit matrix has one row per active source and one column per zone",
    )
    check(
        len(result.patient_cells)
        == len([h for h in result.hospitals.values() if h.patient_destination])
        * len(result.zones),
        "patient matrix has one row per zone and one column per destination",
    )
    available = 0
    route_ok = True
    consistency_ok = True
    prohibited_ok = True
    detail = ""
    for cell in cells:
        if not cell.available or cell.route is None:
            continue
        available += 1
        route = cell.route
        distance, seconds = route.recompute()
        if not _same(distance, route.distance_m, 1e-5):
            route_ok = False
            detail = "stored distance does not match route segments"
        if route.seconds > result.config.shift_hours * 3600.0 + TOL:
            route_ok = False
            detail = "route exceeds the shift limit"
        if route.prohibited_hits:
            prohibited_ok = False
            detail = "route has prohibited hits"
        for lane in route.lanes:
            if lane in router.prohibited or not graph.lane_allowed(
                lane, result.config.vehicle_class
            ):
                prohibited_ok = False
                detail = "route uses a prohibited/unauthorised lane"
        for left, right in zip(route.lanes, route.lanes[1:]):
            if right not in graph.successors.get(left, ()):
                route_ok = False
                detail = "route is not lane-continuous at {0}->{1}".format(left, right)
        # Bellman-Ford is the independent distance check.
        other = router.shortest_path(route.source, route.target, "bellman_ford")
        if other is None or not _same(other.distance_m, route.distance_m, 1e-5):
            consistency_ok = False
            detail = "Bellman-Ford distance differs from the stored route"
    check(available > 0, "at least one matrix cell has a usable route")
    check(route_ok, "all compared routes are continuous and within the shift", detail)
    check(prohibited_ok, "all compared routes avoid prohibited/unauthorised lanes", detail)
    check(consistency_ok, "Bellman-Ford agrees with every available matrix route", detail)
    check(
        result.prohibited_summary.get("total_prohibited_lanes", 0)
        == len(router.prohibited),
        "reported prohibited-lane total equals the router set",
    )
    for source in (
        hospital for hospital in result.hospitals.values() if hospital.source_active
    ):
        check(
            any(
                result.kit_cells.get((source.slug, zone.id)) is not None
                and result.kit_cells[(source.slug, zone.id)].available
                for zone in result.zones
            ),
            "active source {0} has at least one usable zone route".format(source.slug),
        )
    check(len(result.routing_comparison) >= 1, "routing comparison contains measured pairs")
    comparison_ok = all(
        group.get("all_found") and group.get("consistent")
        for group in result.routing_comparison
    )
    check(comparison_ok, "Dijkstra, A*, and Bellman-Ford agree on every comparison pair")


def verify_transport(result: ORPlanResult) -> None:
    print("\n-- transportation tableau --")
    check(result.kit_problem is not None, "kit transportation problem exists")
    check(result.balanced is not None, "balanced tableau exists")
    if result.kit_problem is None or result.balanced is None:
        return
    problem = result.balanced
    check(
        result.kit_problem.rows
        == len([h for h in result.hospitals.values() if h.source_active]),
        "tableau row count equals active kit sources",
    )
    check(
        result.kit_problem.cols == len(result.zones),
        "tableau column count equals manual zones",
    )
    check(
        problem.rows == result.kit_problem.rows
        and problem.cols == result.kit_problem.cols
        + (1 if problem.dummy_col is not None else 0),
        "balanced tableau shape accounts for the labelled dummy column",
    )
    check(
        problem.shortage == max(0, result.kit_problem.total_demand() - result.kit_problem.total_supply()),
        "tableau shortage is balanced explicitly",
    )
    check(
        problem.surplus == max(0, result.kit_problem.total_supply() - result.kit_problem.total_demand()),
        "tableau surplus is balanced explicitly",
    )
    for name in ("NWC", "least-cost", "VAM", "MODI", "exact-MILP"):
        method = result.transport.get(name)
        check(method is not None and method.feasible, "{0} is feasible".format(name))
        if method is None or not method.feasible:
            continue
        errors = check_allocation(problem, method.allocation)
        check(not errors, "{0} allocation passes conservation".format(name), "; ".join(errors[:2]))
        check(
            _matrix_integer(method.allocation),
            "{0} allocation is integral".format(name),
        )
        check(
            _matrix_no_forbidden(problem, method.allocation),
            "{0} avoids forbidden cells".format(name),
        )
        check(
            _same(float(method.objective), compute_objective(problem, method.allocation)),
            "{0} objective is recomputed from its allocation".format(name),
        )
        if problem.dummy_col is not None:
            dummy_total = sum(method.allocation[i][problem.dummy_col] for i in range(problem.rows))
            check(
                _same(dummy_total, problem.surplus),
                "{0} uses the dummy column exactly for unused supply".format(name),
            )
        if problem.dummy_row is not None:
            dummy_total = sum(method.allocation[problem.dummy_row][j] for j in range(problem.cols))
            check(
                _same(dummy_total, problem.shortage),
                "{0} uses the dummy row exactly for unmet demand".format(name),
            )
    exact = result.transport.get("exact-MILP")
    vam = result.transport.get("VAM")
    modi = result.transport.get("MODI")
    if exact is not None and exact.feasible:
        if vam is not None and vam.feasible:
            check(
                vam.objective + 1e-5 >= exact.objective,
                "VAM does not beat the exact tableau optimum",
                "{0:.3f} vs {1:.3f}".format(vam.objective, exact.objective),
            )
        if modi is not None and modi.feasible:
            check(
                _same(modi.objective, exact.objective, 1e-4),
                "MODI matches the exact tableau optimum",
                "{0:.3f} vs {1:.3f}".format(modi.objective, exact.objective),
            )
    if vam is not None:
        _vam_trace_checks(problem, vam)
    if vam is not None and modi is not None:
        _modi_trace_checks(problem, vam, modi)


def verify_network(result: ORPlanResult) -> None:
    print("\n-- lane-capacitated network --")
    plan = result.network_plan
    check(plan is not None, "network plan exists")
    if plan is None:
        return
    check(plan.success, "MILP reports a successful solve", plan.message)
    check(not plan.errors, "network plan has no reported errors", "; ".join(plan.errors[:2]))
    check(
        all(value for name, value in plan.checks.items() if name != "demand_met"),
        "all independent physical network checks pass",
    )
    check(plan.demand_met, "network plan meets all kit and patient demand")
    check(plan.vehicles_used <= result.config.fleet_size, "fleet limit is respected")
    check(
        all(value >= 0 for value in plan.ambulance_by_zone.values()),
        "zone fleet assignments are non-negative",
    )
    supplies = {
        item.slug: item.kit_supply
        for item in result.hospitals.values()
        if item.source_active and item.kit_supply > 0
    }
    beds = {
        item.slug: item.beds_free
        for item in result.hospitals.values()
        if item.patient_destination
    }
    assigned_kits = {source: 0 for source in supplies}
    assigned_beds = {hospital: 0 for hospital in beds}
    selected_flow_ok = True
    route_ok = True
    prohibited_ok = True
    detail = ""
    graph = result.network.lane_graph
    for flow in plan.kit_flows:
        if flow.source not in supplies:
            selected_flow_ok = False
            detail = "kit flow from an inactive source"
            break
        assigned_kits[flow.source] += flow.quantity * result.config.kits_per_trip
        if flow.target not in {zone.id for zone in result.zones}:
            selected_flow_ok = False
            detail = "kit flow to an unknown zone"
            break
    for flow in plan.patient_flows:
        if flow.target not in beds:
            selected_flow_ok = False
            detail = "patient flow to a non-destination"
            break
        assigned_beds[flow.target] += flow.quantity
        if flow.source not in {zone.id for zone in result.zones}:
            selected_flow_ok = False
            detail = "patient flow from an unknown zone"
            break
    check(selected_flow_ok, "selected flows use active sources and valid destinations", detail)
    for source, supply in supplies.items():
        if assigned_kits.get(source, 0) > supply + TOL:
            selected_flow_ok = False
            detail = "kit flow exceeds source supply"
            break
        if plan.unused_supply.get(source, 0) != supply - assigned_kits.get(source, 0):
            selected_flow_ok = False
            detail = "unused supply is not recomputed correctly"
            break
    check(selected_flow_ok, "source supply and unused-supply reporting agree")

    demand_ok = True
    for zone in result.zones:
        kit_delivered = sum(
            flow.quantity * result.config.kits_per_trip
            for flow in plan.kit_flows
            if flow.target == zone.id
        )
        if kit_delivered + plan.unmet_kits.get(zone.id, 0) != zone.kit_demand:
            demand_ok = False
            detail = "kit demand conservation failed for {0}".format(zone.id)
            break
        patient_delivered = sum(
            flow.quantity for flow in plan.patient_flows if flow.source == zone.id
        )
        if patient_delivered + plan.unmet_patients.get(zone.id, 0) != zone.patient_demand:
            demand_ok = False
            detail = "patient demand conservation failed for {0}".format(zone.id)
            break
    check(demand_ok, "zone kit/patient demand conservation holds", detail)

    bed_ok = True
    for hospital, capacity in beds.items():
        if assigned_beds.get(hospital, 0) > capacity + TOL:
            bed_ok = False
            detail = "patient flow exceeds free beds at {0}".format(hospital)
            break
        if plan.unused_beds.get(hospital, 0) != capacity - assigned_beds.get(hospital, 0):
            bed_ok = False
            detail = "unused beds are not reported correctly at {0}".format(hospital)
            break
    check(bed_ok, "free beds are receiving capacity only and are respected", detail)

    fleet_ok = True
    for zone in result.zones:
        trips = sum(
            flow.quantity * result.config.kits_per_trip / result.config.kits_per_trip
            for flow in plan.kit_flows
            if flow.target == zone.id
        )
        # Each kit trip is one ambulance trip; convert kits back to trips.
        trips = sum(flow.quantity for flow in plan.kit_flows if flow.target == zone.id)
        trips += sum(flow.quantity for flow in plan.patient_flows if flow.source == zone.id)
        if trips > plan.ambulance_by_zone.get(zone.id, 0) + TOL:
            fleet_ok = False
            detail = "zone {0} uses more trips than assigned vehicles".format(zone.id)
            break
    check(fleet_ok, "zone trip counts do not exceed assigned ambulances", detail)

    expected_lane_ambulance: Dict[str, float] = {}
    for flow in plan.kit_flows + plan.patient_flows:
        if flow.route.prohibited_hits:
            prohibited_ok = False
            detail = "selected flow has prohibited hits"
        for lane in flow.route.lanes:
            expected_lane_ambulance[lane] = expected_lane_ambulance.get(lane, 0.0) + flow.quantity
            if lane in result.network.lane_graph.lane_info and not graph.lane_allowed(
                lane, result.config.vehicle_class
            ):
                prohibited_ok = False
                detail = "selected flow uses an unauthorised lane"
    check(prohibited_ok, "selected network routes avoid prohibited lanes", detail)

    for flow in plan.kit_flows + plan.patient_flows:
        distance, seconds = flow.route.recompute()
        if not _same(distance, flow.route.distance_m, 1e-5):
            route_ok = False
            detail = "selected route distance mismatch"
            break
        if flow.route.seconds > result.config.shift_hours * 3600.0 + TOL:
            route_ok = False
            detail = "selected route exceeds shift limit"
            break
        for left, right in zip(flow.route.lanes, flow.route.lanes[1:]):
            if right not in graph.successors.get(left, ()):
                route_ok = False
                detail = "selected route is not continuous"
                break
        if not route_ok:
            break
    check(route_ok, "selected network routes are continuous and valid", detail)

    # Recompute every lane load from first principles.
    load_ok = True
    for lane, expected in expected_lane_ambulance.items():
        load = plan.lane_loads.get(lane)
        if load is None:
            load_ok = False
            detail = "selected lane is missing from lane_loads"
            break
        if not _same(load.ambulance, expected):
            load_ok = False
            detail = "lane ambulance load was not recomputed correctly"
            break
        edge = result.network.edges.get(load.edge_id)
        capacity = result.config.road_capacity.capacity_for_lane(
            edge.type if edge is not None else ""
        )
        background = float(result.data.background_lane_flow.get(lane, 0.0))
        if not _same(load.capacity, capacity):
            load_ok = False
            detail = "lane capacity does not match the configurable estimate"
            break
        if not _same(load.background, background):
            load_ok = False
            detail = "background flow is not kept separate/correct"
            break
        if load.ambulance + background > capacity + 1e-7:
            load_ok = False
            detail = "lane load exceeds estimated capacity"
            break
    check(load_ok, "lane loads, background flow, and capacities are recomputed correctly", detail)
    check(
        not plan.background_over_capacity,
        "no lane has background flow above its estimated capacity",
    )
    check(
        all(not load.over_capacity for load in plan.lane_loads.values()),
        "all reported lane loads are within capacity",
    )
    check(
        _same(
            float(plan.solver_objective or 0.0),
            plan.total_vehicle_m
            + result.config.mip_fleet_tiebreak * plan.vehicles_used
            + result.config.mip_unmet_penalty
            * (plan.total_unmet_kits + plan.total_unmet_patients),
            1e-3,
        ),
        "solver objective equals distance + fleet tie-break + explicit unmet penalties",
    )
    exact = result.transport.get("exact-MILP")
    if exact is not None and exact.feasible:
        check(
            plan.kit_vehicle_m * result.config.kits_per_trip + 1e-5 >= exact.objective,
            "network kit distance is not better than the unconstrained table benchmark",
        )


def verify_shortage_reporting(result: ORPlanResult) -> None:
    """Confirm that a deliberately impossible fleet can expose unmet demand."""
    print("\n-- explicit shortage reporting --")
    zone = result.zones[0]
    # Replace the route links with none and remove all fleet capacity.  The
    # model must still solve by paying the unmet penalty and reporting it.
    config = replace(result.config, fleet_size=0)
    solver = NetworkSolver(
        config,
        result.data,
        result.network,
        _router_for(result),
        [zone.id],
        {},
        {},
        {zone.id: 0},
        {zone.id: 1},
        [],
        [],
    )
    plan = solver.solve()
    check(plan.success, "shortage case still produces a solver result", plan.message)
    check(
        plan.status == "optimal-with-unmet-demand",
        "shortage case is labelled optimal-with-unmet-demand",
        plan.status,
    )
    check(
        plan.total_unmet_patients == 1 and plan.unmet_patients.get(zone.id) == 1,
        "shortage is reported as one unmet patient",
    )
    physical = all(value for name, value in plan.checks.items() if name != "demand_met")
    check(physical, "shortage does not create a false physical-constraint failure")
    check(not plan.demand_met, "shortage is not presented as a demand-met plan")


def _router_for(result: ORPlanResult):
    from assiut_hospitals.or_router import DistanceRouter

    return DistanceRouter(
        result.network,
        vehicle_class=result.config.vehicle_class,
        explicit_prohibited_lanes=result.config.explicit_prohibited_lanes,
        max_point_snap_m=result.config.max_point_snap_m,
    )


def verify_context(result: ORPlanResult) -> None:
    print("\n-- data, zones, and fixed policy --")
    check(
        len(result.dataset.routable) == 25,
        "dataset has 25 routable hospitals",
        str(len(result.dataset.routable)),
    )
    check(len(result.zones) == 4, "four manual zones are present")
    check(result.config.fleet_size == 48, "fleet size is fixed at 48")
    check(len(result.hospitals) == 25, "all routable hospitals have OR state")
    check(
        all(hospital.zone_id for hospital in result.hospitals.values()),
        "every routable hospital is assigned to exactly one manual zone",
    )
    check(
        all(
            hospital.zone_id
            == (result.dispatch_config.zone_of(hospital.slug).id
                if result.dispatch_config.zone_of(hospital.slug) is not None
                else "")
            for hospital in result.hospitals.values()
        ),
        "hospital zone labels agree with the manual dispatch configuration",
    )
    anchors_ok = True
    for zone in result.zones:
        if zone.anchor is None:
            anchors_ok = False
            continue
        anchor = zone.anchor
        if anchor.zone_id != zone.id or not anchor.can_leave or not anchor.can_enter:
            anchors_ok = False
    check(anchors_ok, "every zone anchor is routable, bidirectional, and inside its zone")
    check(
        result.data.total_kit_supply() == sum(item.kit_supply for item in result.hospitals.values()),
        "test-data supply total equals prepared hospital supply",
    )
    check(
        result.data.total_kit_demand() == sum(zone.kit_demand for zone in result.zones),
        "test-data kit demand total equals prepared zone demand",
    )
    check(
        result.data.total_patient_demand()
        == sum(zone.patient_demand for zone in result.zones),
        "test-data patient demand total equals prepared zone demand",
    )
    check(
        all(item.point is not None for item in result.hospitals.values()),
        "every routable hospital has a lane route point",
    )
    check(result.data.synthetic, "non-derived quantities are labelled SYNTHETIC")
    check(result.capacity.synthetic, "free-bed capacity is labelled SYNTHETIC")
    check(
        result.config.require_hospital_count == 25
        and result.config.require_exactly_four_zones,
        "fixed 25-hospital / 4-zone policy is enforced",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None, help="path to config.json")
    parser.add_argument(
        "--or-config", default=None, help="path to config/or_planning.json"
    )
    parser.add_argument(
        "--no-routing-comparison",
        action="store_true",
        help="skip the four measured routing-comparison groups",
    )
    args = parser.parse_args(argv)

    print("== OR verification ==")
    try:
        from assiut_hospitals.config import load_config

        config = load_config(args.config)
        or_config = load_or_config(args.or_config, root=config.root)
        planner = ORPlanner(config=config, or_config=or_config)
        result = planner.plan(routing_comparison=not args.no_routing_comparison)
    except ORConfigError as exc:
        print("OR CONFIG ERROR: {0}".format(exc))
        return 2
    except Exception as exc:
        print("OR RUN ERROR: {0}".format(exc))
        return 2

    print(
        "  plan: hospitals={0} zones={1} feasible={2} errors={3} warnings={4}".format(
            len(result.hospitals),
            len(result.zones),
            result.feasible,
            len(result.errors),
            len(result.warnings),
        )
    )
    verify_context(result)
    verify_routes(result)
    verify_transport(result)
    verify_network(result)
    verify_shortage_reporting(result)
    verify_small_exact()

    failures = [item for item in CHECKS if not item[0]]
    print("\n== summary ==")
    print("  checks : {0}".format(len(CHECKS)))
    print("  passed : {0}".format(len(CHECKS) - len(failures)))
    print("  failed : {0}".format(len(failures)))
    if failures:
        for _passed, label, detail in failures:
            print("  FAIL: {0}{1}".format(label, " ({0})".format(detail) if detail else ""))
        print("  RESULT: FAIL")
        return 1
    print("  RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
