"""Human-readable and machine-readable OR reports.

تقارير بحوث العمليات للقراءة الآلية والبشرية.

The report deliberately shows the complete VAM and MODI traces, the cost table
with forbidden cells, and the independent network checks.  It never hides a
synthetic quantity and never turns a feasible network plan into a claim of a
global optimum for every possible operational objective.

يعرض التقرير تتبّع VAM وMODI الكامل وجدول التكاليف والخلايا الممنوعة وفحوص
الشبكة المستقلة، ويوضح أن الحل الممكن ليس بالضرورة برهان أمثلية عالمية.
"""

from __future__ import annotations

import csv
import html
import json
import math
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .or_planning import MatrixCell, ORPlanResult
from .or_transport import BalancedProblem, TransportResult

DEFAULT_REPORT_FILES = {
    "markdown": "or_report.md",
    "json": "or_plan.json",
    "hospitals_csv": "or_hospitals.csv",
    "zones_csv": "or_zones.csv",
    "cost_table_csv": "or_kit_cost_table.csv",
    "vam_trace_csv": "or_vam_trace.csv",
    "modi_trace_csv": "or_modi_trace.csv",
    "transport_csv": "or_transport_comparison.csv",
    "routing_csv": "or_routing_comparison.csv",
    "kit_flows_csv": "or_network_kit_flows.csv",
    "patient_flows_csv": "or_network_patient_flows.csv",
    "lane_loads_csv": "or_lane_loads.csv",
    "checks_csv": "or_checks.csv",
    "routes_svg": "or_routes.svg",
}


# ---------------------------------------------------------------------------
# Small formatting helpers
# ---------------------------------------------------------------------------
def _fmt(value: Optional[float], digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return "inf" if value > 0 else "-inf"
    return "{0:.{1}f}".format(value, digits)


def _md(value: Any) -> str:
    text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _matrix_rows(matrix: Sequence[Sequence[Any]], labels: Sequence[str]) -> List[str]:
    lines: List[str] = []
    for index, row in enumerate(matrix):
        values = []
        for value in row:
            if value is None:
                values.append("FORBIDDEN")
            elif isinstance(value, float):
                values.append(_fmt(value, 3))
            else:
                values.append(str(value))
        lines.append("{0}: {1}".format(labels[index], " | ".join(values)))
    return lines


def _write_csv(path: Path, headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(list(headers))
        for row in rows:
            writer.writerow([" " if item is None else item for item in row])


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


# ---------------------------------------------------------------------------
# Cost table
# ---------------------------------------------------------------------------
def _cost_rows(result: ORPlanResult) -> List[Dict[str, Any]]:
    if result.kit_problem is None:
        return []
    problem = result.kit_problem
    rows: List[Dict[str, Any]] = []
    for i, source in enumerate(problem.row_labels):
        item: Dict[str, Any] = {
            "source": source,
            "supply_kits": problem.supplies[i],
        }
        for j, zone in enumerate(problem.col_labels):
            cost = problem.costs[i][j]
            item[zone] = cost
            item["cell_cap_{0}".format(zone)] = problem.cap(i, j)
        rows.append(item)
    return rows


def _cost_table_markdown(result: ORPlanResult) -> List[str]:
    if result.kit_problem is None:
        return ["No kit transportation table was built."]
    problem = result.kit_problem
    headers = ["source", "supply"] + list(problem.col_labels) + ["row note"]
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "---|" * len(headers))
    for i, source in enumerate(problem.row_labels):
        values: List[str] = [source, str(problem.supplies[i])]
        for j in range(problem.cols):
            cost = problem.costs[i][j]
            if cost is None:
                values.append("FORBIDDEN")
            else:
                values.append(_fmt(cost, 3))
        values.append(_md(problem.row_notes[i] if i < len(problem.row_notes) else ""))
        lines.append("| " + " | ".join(values) + " |")
    demand_row = ["**demand**", str(problem.total_demand())] + [
        str(problem.demands[j]) for j in range(problem.cols)
    ] + [""]
    lines.append("| " + " | ".join(demand_row) + " |")
    lines.append("")
    lines.append(
        "All costs are lane-route distances in **metres** from the active kit "
        "source to the manual zone anchor. `FORBIDDEN` means no route existed "
        "under the current prohibited-lane and shift rules. Cell caps are "
        "**not used** in this kit-only tableau (the network model enforces lane "
        "capacities separately)."
    )
    return lines


# ---------------------------------------------------------------------------
# VAM / MODI sections
# ---------------------------------------------------------------------------
def _vam_markdown(result: ORPlanResult) -> List[str]:
    vam = result.transport.get("VAM")
    if vam is None:
        return ["VAM did not produce a result."]
    lines = [
        "### VAM initial solution",
        "",
        "**Z0 (VAM initial objective): {0} kit-metres.**".format(_fmt(vam.objective, 3)),
        "",
        "The selection rule is deterministic: choose the largest penalty; rows "
        "win ties over columns, and the lower index wins the remaining tie. "
        "Penalties are recomputed after every allocation. A line with one "
        "available cell uses that cell's cost as its penalty and is marked in "
        "the trace notes.",
        "",
        "| step | selected line | penalty | cell | quantity | struck | allocations after step |",
        "|---:|---|---:|---|---:|---|---|",
    ]
    labels = result.balanced.row_labels if result.balanced is not None else []
    for item in vam.trace:
        selected = item.get("selected_line", {})
        cell = item.get("cell", {})
        struck = list(item.get("struck_rows", [])) + list(
            item.get("struck_columns", [])
        )
        allocation = item.get("allocation", [])
        allocation_text = "<br>".join(
            "{0}: {1}".format(labels[i] if i < len(labels) else i, row)
            for i, row in enumerate(allocation)
        )
        lines.append(
            "| {step} | {kind}: {label} | {penalty} | {row} -> {col} | {qty} | {struck} | {allocation} |".format(
                step=item.get("step"),
                kind=_md(selected.get("kind", "")),
                label=_md(selected.get("label", "")),
                penalty=_fmt(selected.get("penalty")),
                row=_md(cell.get("row_label", "")),
                col=_md(cell.get("col_label", "")),
                qty=_fmt(item.get("quantity"), 0),
                struck=_md(", ".join(struck) or "-"),
                allocation=allocation_text,
            )
        )
    lines.append("")
    if vam.notes:
        lines.append("VAM notes: " + "; ".join(vam.notes))
        lines.append("")
    lines.append("### VAM final allocation (kits)")
    lines.append("")
    lines.extend(_allocation_markdown(result, vam))
    return lines


def _allocation_markdown(
    result: ORPlanResult, transport: TransportResult
) -> List[str]:
    if result.balanced is None:
        return ["No balanced table."]
    problem = result.balanced
    headers = ["source", "supply"] + list(problem.col_labels) + ["row total"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for i, label in enumerate(problem.row_labels):
        row = transport.allocation[i]
        values = [label, str(problem.supplies[i])] + [
            str(int(round(value))) for value in row
        ] + [str(int(round(sum(row))))]
        lines.append("| " + " | ".join(values) + " |")
    col_totals = [
        str(int(round(sum(transport.allocation[i][j] for i in range(problem.rows)))))
        for j in range(problem.cols)
    ]
    lines.append(
        "| **column total** | **{0}** | {1} | **{2}** |".format(
            sum(problem.supplies),
            " | ".join(["**{0}**".format(value) for value in col_totals]),
            int(round(sum(transport.allocation[i][j] for i in range(problem.rows) for j in range(problem.cols)))),
        )
    )
    lines.append("")
    lines.append(
        "Dummy: {0}. The dummy cells carry zero cost and are labelled "
        "`DUMMY_UNUSED_SUPPLY` or `DUMMY_UNMET_DEMAND`; they are not physical "
        "deliveries.".format(
            "row {0}".format(problem.dummy_row)
            if problem.dummy_row is not None
            else "column {0}".format(problem.dummy_col)
            if problem.dummy_col is not None
            else "none (balanced)"
        )
    )
    lines.append("")
    return lines


def _modi_markdown(result: ORPlanResult) -> List[str]:
    modi = result.transport.get("MODI")
    if modi is None:
        return ["MODI did not produce a result."]
    if result.balanced is None:
        return ["No balanced table for MODI."]
    problem = result.balanced
    lines = [
        "### MODI (u-v) trace",
        "",
        "**Initial VAM objective:** {0} kit-metres. **Final MODI objective:** "
        "{1} kit-metres. **Status:** {2}. **Iterations:** {3}.".format(
            _fmt(modi.initial_objective, 3),
            _fmt(modi.objective, 3),
            _md(modi.status),
            modi.iterations,
        ),
        "",
        "Forbidden cells stay outside the basis and outside the entering "
        "candidate set. Degeneracy is handled by adding zero basic cells; every "
        "addition is listed in the notes. The adjustment cycle alternates "
        "plus/minus cells and is shown in full below.",
        "",
    ]
    if modi.notes:
        lines.append("MODI notes: " + "; ".join(modi.notes))
        lines.append("")
    if not modi.trace:
        lines.append("The VAM starting solution already satisfies the MODI optimality test.")
        lines.append("")
    for item in modi.trace:
        u = item.get("u", [])
        v = item.get("v", [])
        entering = item.get("entering", {})
        cycle = item.get("cycle", [])
        lines.append("#### MODI iteration {0}".format(item.get("iteration")))
        lines.append("")
        lines.append("u = `{0}`; v = `{1}`".format(u, v))
        lines.append("")
        lines.append(
            "Entering cell: **{0} -> {1}**, reduced cost **{2}**, theta **{3}**, "
            "degenerate **{4}**, leaving cell **{5} -> {6}**.".format(
                _md(entering.get("row_label", "")),
                _md(entering.get("col_label", "")),
                _fmt(entering.get("reduced_cost"), 3),
                _fmt(item.get("theta"), 3),
                item.get("degenerate"),
                _md(item.get("leaving_label", [""])[0]),
                _md(item.get("leaving_label", ["", ""])[1]),
            )
        )
        lines.append("")
        lines.append(
            "Cycle: "
            + " -> ".join(
                "({0},{1})".format(
                    problem.row_labels[cell[0]] if cell else "",
                    problem.col_labels[cell[1]] if len(cell) > 1 else "",
                )
                for cell in cycle
            )
        )
        lines.append("")
        lines.append("Reduced-cost table (rows are sources; columns are destinations):")
        lines.append("")
        lines.append("```")
        lines.extend(_matrix_rows(item.get("reduced_costs", []), problem.row_labels))
        lines.append("```")
        lines.append("")
        lines.append("Allocation after the iteration (kits):")
        lines.append("")
        lines.append("```")
        lines.extend(_matrix_rows(item.get("allocation", []), problem.row_labels))
        lines.append("```")
        lines.append("")
    lines.append("### MODI final checks")
    lines.append("")
    lines.append("Final potentials: u = `{0}`; v = `{1}`".format(
        modi.potentials_u, modi.potentials_v
    ))
    lines.append("")
    lines.append("Final basic cells: `{0}`".format(modi.basis))
    lines.append("")
    lines.append("Final reduced-cost table:")
    lines.append("")
    lines.append("```")
    if modi.reduced_costs is not None:
        lines.extend(_matrix_rows(modi.reduced_costs, problem.row_labels))
    lines.append("```")
    lines.append("")
    lines.append(
        "A negative reduced cost in a non-basic admissible cell would mean that "
        "the MODI optimality test had not yet passed. The report and verifier "
        "check this explicitly."
    )
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Network / routing sections
# ---------------------------------------------------------------------------
def _network_markdown(result: ORPlanResult) -> List[str]:
    plan = result.network_plan
    if plan is None:
        return ["The network MILP did not run."]
    lines = [
        "### Road-capacitated network plan",
        "",
        "| field | value |",
        "|---|---|",
        "| MILP status | {0} |".format(_md(plan.status)),
        "| solver success | {0} |".format(plan.success),
        "| message | {0} |".format(_md(plan.message)),
        "| variables / constraints | {0} / {1} |".format(plan.variables, plan.constraints),
        "| solver time [s] | {0} |".format(_fmt(plan.solver_seconds, 6)),
        "| solver objective | {0} |".format(_fmt(plan.solver_objective, 3)),
        "| kit vehicle-metres | {0} |".format(_fmt(plan.kit_vehicle_m, 3)),
        "| patient vehicle-metres | {0} |".format(_fmt(plan.patient_vehicle_m, 3)),
        "| total vehicle-metres | {0} |".format(_fmt(plan.total_vehicle_m, 3)),
        "| vehicles used / fleet | {0} / {1} |".format(
            plan.vehicles_used, result.config.fleet_size
        ),
        "| unmet kit units | {0} |".format(plan.total_unmet_kits),
        "| unmet patient transfers | {0} |".format(plan.total_unmet_patients),
        "| unused kit supply | {0} |".format(plan.total_unused_supply),
        "| unused receiving beds | {0} |".format(plan.total_unused_beds),
        "",
        "`feasible` means all physical checks pass and no demand is unmet. "
        "`optimal` here means optimal for the stated network MILP, not a proof "
        "for every possible operational objective.",
        "",
        "#### Fleet assignment",
        "",
        "| zone | vehicles used | kit trips to zone | patient trips from zone |",
        "|---|---:|---:|---:|",
    ]
    for zone in result.zones:
        lines.append(
            "| {0} | {1} | {2} | {3} |".format(
                zone.id,
                plan.ambulance_by_zone.get(zone.id, 0),
                sum(flow.quantity for flow in plan.kit_flows if flow.target == zone.id),
                sum(flow.quantity for flow in plan.patient_flows if flow.source == zone.id),
            )
        )
    lines.append("")
    lines.append("#### Selected kit trips")
    lines.append("")
    if plan.kit_flows:
        lines.append("| source | zone | trips | kits | distance [m] | time [s] | lanes |")
        lines.append("|---|---|---:|---:|---:|---:|---:|")
        for flow in plan.kit_flows:
            lines.append(
                "| {0} | {1} | {2} | {3} | {4} | {5} | {6} |".format(
                    _md(flow.source),
                    flow.target,
                    flow.quantity,
                    flow.quantity * result.config.kits_per_trip,
                    _fmt(flow.distance_m),
                    _fmt(flow.seconds, 1),
                    len(flow.route.lanes),
                )
            )
    else:
        lines.append("No kit trips were selected.")
    lines.append("")
    lines.append("#### Selected patient transfers")
    lines.append("")
    if plan.patient_flows:
        lines.append("| origin zone | receiving hospital | transfers | distance [m] | time [s] | lanes |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for flow in plan.patient_flows:
            lines.append(
                "| {0} | {1} | {2} | {3} | {4} | {5} |".format(
                    flow.source,
                    _md(flow.target),
                    flow.quantity,
                    _fmt(flow.distance_m),
                    _fmt(flow.seconds, 1),
                    len(flow.route.lanes),
                )
            )
    else:
        lines.append("No patient transfers were selected.")
    lines.append("")
    lines.append(
        "A zero distance means that the origin zone anchor and the receiving "
        "facility share a snapped lane access point (or are the same facility); "
        "see the access-point limitation in section 9."
    )
    lines.append("")
    lines.append("#### Constraint checks (recomputed independently after the solve)")
    lines.append("")
    lines.append("| check | result |")
    lines.append("|---|---|")
    for name, passed in sorted(plan.checks.items()):
        lines.append("| {0} | {1} |".format(_md(name), "PASS" if passed else "FAIL"))
    lines.append("")
    top_lanes = sorted(
        plan.lane_loads.values(),
        key=lambda item: (item.ambulance, item.background, item.lane_id),
        reverse=True,
    )[:15]
    lines.append(
        "#### Lane loads (top 15 by ambulance flow; complete table in "
        "`or_lane_loads.csv`)"
    )
    lines.append("")
    lines.append("| lane | edge | type | background | ambulance | total | capacity | slack |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|")
    for item in top_lanes:
        lines.append(
            "| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} |".format(
                _md(item.lane_id),
                _md(item.edge_id),
                _md(item.edge_type),
                _fmt(item.background),
                _fmt(item.ambulance),
                _fmt(item.total),
                _fmt(item.capacity),
                _fmt(item.slack),
            )
        )
    lines.append("")
    if plan.background_over_capacity:
        lines.append("**Background flow alone exceeds estimated capacity on these lanes:**")
        lines.append("")
        for item in plan.background_over_capacity:
            lines.append("- `{0}`: {1}".format(item.get("lane_id"), item.get("reason")))
        lines.append("")
    if plan.blocked_links:
        lines.append("**Candidate links excluded before the MILP:**")
        lines.append("")
        for item in plan.blocked_links[:20]:
            lines.append(
                "- {0} {1}->{2}: {3}".format(
                    item.get("kind"), item.get("source"), item.get("target"), item.get("reason")
                )
            )
        lines.append("")
    return lines


def _routing_markdown(result: ORPlanResult) -> List[str]:
    lines = [
        "### Routing algorithm comparison",
        "",
        "These are measured examples from this run, not fixed performance "
        "claims. All three algorithms must return the same shortest distance "
        "for the same pair; timing differences are implementation effects.",
        "",
    ]
    if not result.routing_comparison:
        lines.append("No routing comparison pairs were available.")
        return lines
    lines.append(
        "| source | target | algorithm | found | distance [m] | time [s] | settled states | search time [s] |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---:|")
    for group in result.routing_comparison:
        for item in group["algorithms"]:
            lines.append(
                "| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} |".format(
                    _md(group["source"]),
                    _md(group["target"]),
                    _md(item.get("algorithm")),
                    "yes" if item.get("found") else "no",
                    _fmt(item.get("distance_m")),
                    _fmt(item.get("seconds")),
                    item.get("settled"),
                    _fmt(item.get("elapsed_seconds"), 9),
                )
            )
    lines.append("")
    inconsistent = [group for group in result.routing_comparison if not group.get("consistent")]
    if inconsistent:
        lines.append(
            "**WARNING:** {0} pair(s) did not return one consistent distance.".format(
                len(inconsistent)
            )
        )
    else:
        lines.append(
            "All compared pairs returned consistent distances. The route "
            "validity and prohibited-lane checks are repeated in the network "
            "verification."
        )
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------
def _svg_routes(result: ORPlanResult) -> str:
    plan = result.network_plan
    flows = []
    if plan is not None:
        flows = list(plan.kit_flows) + list(plan.patient_flows)
    points: List[Tuple[float, float]] = []
    geometry: List[Tuple[str, str, List[Tuple[float, float]]]] = []
    for flow in flows:
        polyline = _route_geometry(result, flow.route)
        if len(polyline) < 2:
            continue
        geometry.append((flow.kind, flow.source + " -> " + flow.target, polyline))
        points.extend(polyline)
    for hospital in result.hospitals.values():
        points.append((hospital.lat, hospital.lon))
    if not points:
        points = [(27.18, 31.18), (27.20, 31.20)]
    lats = [item[0] for item in points]
    lons = [item[1] for item in points]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    span_lat = max(1e-9, max_lat - min_lat)
    span_lon = max(1e-9, max_lon - min_lon)
    width, height = 1200.0, 1000.0
    margin = 45.0

    def project(lat: float, lon: float) -> Tuple[float, float]:
        x = margin + (lon - min_lon) / span_lon * (width - 2 * margin)
        y = height - margin - (lat - min_lat) / span_lat * (height - 2 * margin)
        return x, y

    out: List[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="{0}" height="{1}" viewBox="0 0 {0} {1}">'.format(
            int(width), int(height)
        ),
        "<title>Assiut OR selected routes</title>",
        "<desc>Selected kit and patient routes. Not a geographic map projection; coordinates are stretched to fit.</desc>",
        '<rect width="100%" height="100%" fill="#fbfbf8"/>',
    ]
    for index, (kind, label, polyline) in enumerate(geometry):
        colour = "#1769aa" if kind == "kit" else "#d95f02"
        coords = " ".join(
            "{0:.2f},{1:.2f}".format(*project(lat, lon)) for lat, lon in polyline
        )
        out.append(
            '<polyline points="{0}" fill="none" stroke="{1}" stroke-width="2.2" '
            'stroke-opacity="0.58"><title>{2}</title></polyline>'.format(
                coords, colour, html.escape(label)
            )
        )
    for hospital in result.hospitals.values():
        x, y = project(hospital.lat, hospital.lon)
        if hospital.patient_destination:
            colour = "#2a7f62"
        elif hospital.source_active:
            colour = "#1769aa"
        else:
            colour = "#777777"
        out.append(
            '<circle cx="{0:.2f}" cy="{1:.2f}" r="3.6" fill="{2}" stroke="#222" stroke-width="0.5">'
            "<title>{3}</title></circle>".format(
                x, y, colour, html.escape(hospital.slug)
            )
        )
    for zone in result.zones:
        if zone.anchor is None:
            continue
        x, y = project(zone.anchor.lat, zone.anchor.lon)
        out.append(
            '<rect x="{0:.2f}" y="{1:.2f}" width="9" height="9" fill="none" stroke="#111" stroke-width="1.6">'
            "<title>{2} anchor: {3}</title></rect>".format(
                x - 4.5, y - 4.5, html.escape(zone.id), html.escape(zone.anchor.slug)
            )
        )
    out.extend(
        [
            '<text x="20" y="28" font-family="sans-serif" font-size="18" fill="#111">Assiut OR selected routes</text>',
            '<text x="20" y="50" font-family="sans-serif" font-size="12" fill="#444">blue = kit route, orange = patient route; green circle = patient destination; square = zone anchor</text>',
            "</svg>",
        ]
    )
    return "\n".join(out) + "\n"


def _route_geometry(result: ORPlanResult, route) -> List[Tuple[float, float]]:
    """Return route geometry as (lat, lon) pairs, robust to missing edges."""
    points: List[Tuple[float, float]] = []
    seen_edges = set()
    for segment in route.segments:
        if segment.edge_id in seen_edges:
            continue
        seen_edges.add(segment.edge_id)
        edge = result.network.edges.get(segment.edge_id)
        if edge is None:
            continue
        for x, y in edge.shape:
            lon, lat = result.network.to_geo(x, y)
            pair = (lat, lon)
            if not points or points[-1] != pair:
                points.append(pair)
    return points


# ---------------------------------------------------------------------------
# Main writer
# ---------------------------------------------------------------------------
def write_reports(result: ORPlanResult, out_dir: Optional[Path] = None) -> Dict[str, str]:
    """Write every OR artefact and return the absolute paths.

    يكتب كل مخرجات بحوث العمليات ويعيد مساراتها المطلقة.
    """
    output = Path(out_dir) if out_dir else result.config.output_dir
    output.mkdir(parents=True, exist_ok=True)
    paths = {key: output / name for key, name in DEFAULT_REPORT_FILES.items()}

    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    summary = result.summary()
    summary["generated_utc"] = generated
    summary["environment"] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    try:
        import numpy
        import scipy

        summary["environment"]["numpy"] = numpy.__version__
        summary["environment"]["scipy"] = scipy.__version__
    except Exception:
        pass
    summary["transport_details"] = {
        name: _transport_payload(item) for name, item in result.transport.items()
    }
    summary["kit_cost_table"] = {
        "rows": result.kit_problem.row_labels if result.kit_problem else [],
        "cols": result.kit_problem.col_labels if result.kit_problem else [],
        "costs": result.kit_problem.costs if result.kit_problem else [],
        "supplies": result.kit_problem.supplies if result.kit_problem else [],
        "demands": result.kit_problem.demands if result.kit_problem else [],
        "cell_caps": result.kit_problem.cell_caps if result.kit_problem else None,
    }
    summary["hospital_details"] = [
        item.as_dict() for item in sorted(result.hospitals.values(), key=lambda h: h.slug)
    ]
    summary["kit_cells"] = [
        cell.as_dict()
        for _, cell in sorted(result.kit_cells.items(), key=lambda item: item[0])
    ]
    summary["patient_cells"] = [
        cell.as_dict()
        for _, cell in sorted(result.patient_cells.items(), key=lambda item: item[0])
    ]
    _write_text(paths["json"], json.dumps(_json_safe(summary), ensure_ascii=False, indent=2) + "\n")

    _write_csv(
        paths["hospitals_csv"],
        [
            "slug",
            "display_name",
            "category",
            "zone_id",
            "emergency",
            "beds_total",
            "beds_free",
            "kit_supply",
            "can_leave",
            "can_enter",
            "source_active",
            "patient_destination",
            "excluded_reason",
            "snap_distance_m",
        ],
        (
            [
                item.slug,
                item.display_name,
                item.category,
                item.zone_id,
                item.emergency,
                item.beds_total,
                item.beds_free,
                item.kit_supply,
                item.can_leave,
                item.can_enter,
                item.source_active,
                item.patient_destination,
                item.excluded_reason,
                round(item.snap_distance_m, 2),
            ]
            for item in sorted(result.hospitals.values(), key=lambda h: h.slug)
        ),
    )
    _write_csv(
        paths["zones_csv"],
        [
            "zone",
            "name",
            "anchor",
            "hospital_count",
            "active_sources",
            "patient_destinations",
            "kit_supply",
            "kit_demand",
            "patient_demand",
            "free_beds",
        ],
        (
            [
                zone.id,
                zone.zone.name,
                zone.anchor.slug if zone.anchor else "",
                len(zone.hospitals),
                len(zone.active_sources),
                len(zone.patient_destinations),
                zone.total_supply,
                zone.kit_demand,
                zone.patient_demand,
                zone.total_beds,
            ]
            for zone in result.zones
        ),
    )
    if result.kit_problem is not None:
        problem = result.kit_problem
        _write_csv(
            paths["cost_table_csv"],
            ["source", "supply"] + list(problem.col_labels),
            (
                [problem.row_labels[i], problem.supplies[i]]
                + [problem.costs[i][j] for j in range(problem.cols)]
                for i in range(problem.rows)
            ),
        )
    _write_csv(
        paths["transport_csv"],
        [
            "method",
            "feasible",
            "status",
            "objective",
            "unmet",
            "unused",
            "iterations",
            "seconds",
        ],
        (
            [
                name,
                item.feasible,
                item.status,
                item.objective,
                item.unmet,
                item.unused,
                item.iterations,
                item.seconds,
            ]
            for name, item in result.transport.items()
        ),
    )
    if result.balanced is not None:
        vam = result.transport.get("VAM")
        if vam is not None:
            _write_csv(
                paths["vam_trace_csv"],
                [
                    "step",
                    "selected_kind",
                    "selected_label",
                    "penalty",
                    "cell_row",
                    "cell_col",
                    "quantity",
                    "struck_rows",
                    "struck_columns",
                    "allocation_json",
                ],
                (
                    [
                        item.get("step"),
                        item.get("selected_line", {}).get("kind"),
                        item.get("selected_line", {}).get("label"),
                        item.get("selected_line", {}).get("penalty"),
                        item.get("cell", {}).get("row_label"),
                        item.get("cell", {}).get("col_label"),
                        item.get("quantity"),
                        json.dumps(item.get("struck_rows", [])),
                        json.dumps(item.get("struck_columns", [])),
                        json.dumps(item.get("allocation", [])),
                    ]
                    for item in vam.trace
                ),
            )
    modi = result.transport.get("MODI")
    if modi is not None:
        _write_csv(
            paths["modi_trace_csv"],
            [
                "iteration",
                "entering_row",
                "entering_col",
                "reduced_cost",
                "theta",
                "degenerate",
                "leaving_row",
                "leaving_col",
                "u_json",
                "v_json",
                "cycle_json",
                "reduced_costs_json",
                "allocation_json",
            ],
            (
                [
                    item.get("iteration"),
                    item.get("entering", {}).get("row_label"),
                    item.get("entering", {}).get("col_label"),
                    item.get("entering", {}).get("reduced_cost"),
                    item.get("theta"),
                    item.get("degenerate"),
                    item.get("leaving_label", ["", ""])[0],
                    item.get("leaving_label", ["", ""])[1],
                    json.dumps(item.get("u", [])),
                    json.dumps(item.get("v", [])),
                    json.dumps(item.get("cycle", [])),
                    json.dumps(item.get("reduced_costs", [])),
                    json.dumps(item.get("allocation", [])),
                ]
                for item in modi.trace
            ),
        )
    routing_rows: List[List[Any]] = []
    for group in result.routing_comparison:
        for item in group["algorithms"]:
            routing_rows.append(
                [
                    group["source_zone"],
                    group["source"],
                    group["target_zone"],
                    group["target"],
                    item.get("algorithm"),
                    item.get("found"),
                    item.get("distance_m"),
                    item.get("seconds"),
                    item.get("settled"),
                    item.get("elapsed_seconds"),
                    group.get("consistent"),
                ]
            )
    _write_csv(
        paths["routing_csv"],
        [
            "source_zone",
            "source",
            "target_zone",
            "target",
            "algorithm",
            "found",
            "distance_m",
            "seconds",
            "settled",
            "elapsed_seconds",
            "consistent",
        ],
        routing_rows,
    )
    plan = result.network_plan
    if plan is not None:
        _write_csv(
            paths["kit_flows_csv"],
            ["source", "zone", "trips", "kits", "distance_m", "seconds", "lanes", "edges"],
            (
                [
                    flow.source,
                    flow.target,
                    flow.quantity,
                    flow.quantity * result.config.kits_per_trip,
                    flow.distance_m,
                    flow.seconds,
                    len(flow.route.lanes),
                    " ".join(flow.route.edges),
                ]
                for flow in plan.kit_flows
            ),
        )
        _write_csv(
            paths["patient_flows_csv"],
            ["zone", "hospital", "transfers", "distance_m", "seconds", "lanes", "edges"],
            (
                [
                    flow.source,
                    flow.target,
                    flow.quantity,
                    flow.distance_m,
                    flow.seconds,
                    len(flow.route.lanes),
                    " ".join(flow.route.edges),
                ]
                for flow in plan.patient_flows
            ),
        )
        _write_csv(
            paths["lane_loads_csv"],
            [
                "lane_id",
                "edge_id",
                "edge_type",
                "background",
                "ambulance",
                "total",
                "capacity",
                "slack",
                "over_capacity",
            ],
            (
                [
                    item.lane_id,
                    item.edge_id,
                    item.edge_type,
                    item.background,
                    item.ambulance,
                    item.total,
                    item.capacity,
                    item.slack,
                    item.over_capacity,
                ]
                for item in sorted(plan.lane_loads.values(), key=lambda x: x.lane_id)
            ),
        )
        _write_csv(
            paths["checks_csv"],
            ["check", "passed"],
            sorted(plan.checks.items()),
        )
    _write_text(paths["routes_svg"], _svg_routes(result))

    markdown = _markdown_report(result, generated)
    _write_text(paths["markdown"], markdown)
    return {key: str(path.resolve()) for key, path in paths.items()}


def _transport_payload(result: TransportResult) -> Dict[str, Any]:
    return {
        "method": result.method,
        "allocation": result.allocation_as_int(),
        "objective": None if not math.isfinite(result.objective) else result.objective,
        "feasible": result.feasible,
        "status": result.status,
        "unmet": result.unmet,
        "unused": result.unused,
        "iterations": result.iterations,
        "seconds": result.seconds,
        "trace": result.trace,
        "notes": result.notes,
        "potentials_u": result.potentials_u,
        "potentials_v": result.potentials_v,
        "reduced_costs": result.reduced_costs,
        "basis": result.basis,
        "initial_objective": result.initial_objective,
    }


# ---------------------------------------------------------------------------
# Markdown document
# ---------------------------------------------------------------------------
def _markdown_report(result: ORPlanResult, generated: str) -> str:
    plan = result.network_plan
    lines: List[str] = [
        "# Assiut Operations Research Report",
        "",
        "**Generated (UTC):** {0}".format(generated),
        "",
        "> **DATA STATUS: {0}**".format(
            "SYNTHETIC TEST QUANTITIES"
            if result.data.synthetic or result.capacity.synthetic
            else "OWNER-DATA"
        ),
        "",
        "> {0}".format(
            result.data.notice
            if result.data.synthetic
            else "The quantities are supplied by the owner; see the source files."
        ),
        "",
        "This report covers the one-day, capacity-constrained kit/patient model. "
        "It is additive to the existing emergency dispatch project; it does not "
        "replace that dispatcher. The road network and hospital coordinates are "
        "the existing Assiut assets and are not modified by this report.",
        "",
        "## 1. Executive result",
        "",
        "| item | value |",
        "|---|---|",
        "| routed hospitals | {0} |".format(len(result.hospitals)),
        "| manual zones | {0} |".format(len(result.zones)),
        "| active kit sources | {0} |".format(
            sum(1 for item in result.hospitals.values() if item.source_active)
        ),
        "| patient destinations | {0} |".format(
            sum(1 for item in result.hospitals.values() if item.patient_destination)
        ),
        "| kit supply / demand | {0} / {1} |".format(
            result.total_kit_supply,
            result.total_kit_demand,
        ),
        "| unused kit supply / unmet kit demand | {0} / {1} |".format(
            max(result.total_kit_supply - result.total_kit_demand, 0),
            max(result.total_kit_demand - result.total_kit_supply, 0),
        ),
        "| patient transfers / usable free beds | {0} / {1} |".format(
            result.total_patient_demand, result.total_beds
        ),
        "| VAM initial objective Z0 | {0} kit-metres |".format(
            _fmt(result.transport.get("VAM").objective if result.transport.get("VAM") else None)
        ),
        "| MODI final objective | {0} kit-metres |".format(
            _fmt(result.transport.get("MODI").objective if result.transport.get("MODI") else None)
        ),
        "| exact tableau MILP | {0} kit-metres |".format(
            _fmt(result.transport.get("exact-MILP").objective if result.transport.get("exact-MILP") else None)
        ),
        "| network MILP status | {0} |".format(_md(plan.status if plan else "not run")),
        "| network feasible | {0} |".format(result.feasible),
        "| network demand met | {0} |".format(plan.demand_met if plan else False),
        "| total vehicle-metres | {0} |".format(_fmt(plan.total_vehicle_m if plan else None)),
        "| errors / warnings | {0} / {1} |".format(len(result.errors), len(result.warnings)),
        "",
        "**Feasible vs optimal.** A feasible plan satisfies supply, demand, bed, "
        "fleet, route, prohibited-lane, and lane-capacity checks. The network "
        "MILP's `optimal` status is optimality for the stated integer model; it "
        "is not a proof of global optimality for every possible real-world "
        "objective. VAM and MODI alone are **not** claimed to optimize the "
        "road-capacitated network.",
        "",
        "## 2. Data, zones, and resources",
        "",
        "The four zones and hospital membership are read from the owner-approved "
        "manual dispatch configuration. The OR layer does not invent an automatic "
        "zone assignment. Zone demand and kit stock are synthetic test values "
        "unless the source is explicitly owner data.",
        "",
        "| zone | name | anchor | hospitals | active sources | patient destinations | kit supply | kit demand | patient demand | usable free beds |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for zone in result.zones:
        lines.append(
            "| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | {8} | {9} |".format(
                zone.id,
                _md(zone.zone.name),
                _md(zone.anchor.slug if zone.anchor else "MISSING"),
                len(zone.hospitals),
                len(zone.active_sources),
                len(zone.patient_destinations),
                zone.total_supply,
                zone.kit_demand,
                zone.patient_demand,
                zone.total_beds,
            )
        )
    lines.extend(
        [
            "",
            "Zone counts, supplies, and demands are deliberately unequal. No "
            "equal-demand or equal-hospital-count assumption is used. Hospital "
            "membership is the existing manual assignment, not a Voronoi or "
            "nearest-anchor calculation.",
            "",
            "### Hospital roles and resources",
            "",
            "| hospital | category | zone | emergency | beds total/free | kits | can leave | can enter | role / exclusion |",
            "|---|---|---|---|---:|---:|---|---|---|",
        ]
    )
    for item in sorted(result.hospitals.values(), key=lambda h: h.slug):
        role = []
        if item.source_active:
            role.append("kit source")
        if item.patient_destination:
            role.append("patient destination")
        if not role:
            role.append(item.excluded_reason or "not used")
        lines.append(
            "| {0} | {1} | {2} | {3} | {4}/{5} | {6} | {7} | {8} | {9} |".format(
                _md(item.slug),
                _md(item.category),
                item.zone_id,
                "yes" if item.emergency else "no",
                item.beds_total,
                item.beds_free,
                item.kit_supply,
                "yes" if item.can_leave else "no",
                "yes" if item.can_enter else "no",
                _md("; ".join(role)),
            )
        )
    lines.extend(
        [
            "",
            "A free bed is **receiving capacity** at a destination. It is not a "
            "resource loaded into an ambulance. Kits, beds, ambulances, and "
            "background traffic are separate quantities.",
            "",
            "## 3. Mathematical model and data rules",
            "",
            "The full notation and constraints are in `OR_MODEL.md`. In brief:",
            "",
            "- **Sets:** routable hospitals, four manual zones, lane graph, active "
            "kit sources, patient destinations.",
            "- **Kit variable:** integer number of 10-kit trips from source to "
            "zone anchor; each trip consumes 10 kits.",
            "- **Patient variable:** integer number of patient transfers from a "
            "zone anchor to a receiving hospital.",
            "- **Ambulance variable:** integer vehicles assigned to each zone; "
            "total is capped at 48.",
            "- **Unmet variables:** explicit kit and patient shortages; the "
            "solver pays a large penalty rather than hiding them.",
            "- **Road constraints:** for every lane, background flow + ambulance "
            "flow on that lane <= estimated capacity. Background flow is kept "
            "separate.",
            "- **Prohibited lanes:** removed from the lane graph before search; "
            "they are not a large finite cost.",
            "",
            "### Road-capacity estimate",
            "",
            "The repository has no measured lane capacity. The shipped value is a "
            "**documented `{0}` estimate**, computed from lane count and road type, "
            "not from street length alone. It is configurable in "
            "`config/or_planning.json`.".format(result.config.road_capacity.source),
            "",
            "| parameter | value |",
            "|---|---|",
            "| planning interval [h] | {0} |".format(
                result.config.road_capacity.planning_interval_hours
            ),
            "| reserve fraction | {0} |".format(
                result.config.road_capacity.reserve_fraction
            ),
            "| default vehicles/lane/hour | {0} |".format(
                result.config.road_capacity.default_vehicles_per_lane_hour
            ),
            "| minimum vehicles/lane | {0} |".format(
                result.config.road_capacity.minimum_vehicles_per_lane
            ),
            "",
            "| road type | vehicles/lane/hour |",
            "|---|---:|",
        ]
    )
    for edge_type, rate in sorted(
        result.config.road_capacity.vehicles_per_lane_hour_by_type.items()
    ):
        lines.append("| {0} | {1} |".format(_md(edge_type), rate))
    lines.extend(
        [
            "",
            "### Prohibited lanes",
            "",
            "| item | value |",
            "|---|---:|",
            "| network vehicle-class prohibited lanes | {0} |".format(
                result.prohibited_summary.get("network_class_prohibited_lanes", 0)
            ),
            "| explicit prohibited lanes in config | {0} |".format(
                result.prohibited_summary.get("explicit_prohibited_lanes", 0)
            ),
            "| total removed from graph | {0} |".format(
                result.prohibited_summary.get("total_prohibited_lanes", 0)
            ),
            "",
            "The rule is: lanes without permission for `{0}` and explicit closures "
            "are removed from every search. If no route exists, the cell is "
            "reported as unavailable; the solver does not silently use a large "
            "penalty as a substitute for a physical prohibition.".format(
                result.config.vehicle_class
            ),
            "",
            "## 4. Kit-only transportation tableau",
            "",
            "The tableau is a **kit-only** model. It does not contain road "
            "capacities. Its exact optimum is therefore a cost benchmark and an "
            "allocation benchmark, not a road-capacitated feasibility claim.",
            "",
            "### Initial cost table",
            "",
        ]
    )
    lines.extend(_cost_table_markdown(result))
    lines.extend(
        [
            "",
            "### Balance / dummy",
            "",
        ]
    )
    if result.balanced is not None:
        balanced = result.balanced
        if balanced.dummy_row is None:
            dummy_row_text = "no dummy row"
        else:
            dummy_row_text = "dummy row `{0}`".format(balanced.dummy_row)
        if balanced.dummy_col is None:
            dummy_col_text = "no dummy column"
        else:
            dummy_col_text = "dummy column `{0}`".format(balanced.dummy_col)
        lines.extend(
            [
                "Original supply = {0}, original demand = {1}, shortage = {2}, "
                "surplus = {3}.".format(
                    balanced.base.total_supply(),
                    balanced.base.total_demand(),
                    balanced.shortage,
                    balanced.surplus,
                ),
                "",
                "The balanced table has {0} rows and {1} columns, with {2} and "
                "{3}.".format(
                    balanced.rows,
                    balanced.cols,
                    dummy_row_text,
                    dummy_col_text,
                ),
                "",
                "A dummy is added only because the supplied test data is "
                "unbalanced. It is labelled and its zero-cost allocation is "
                "reported as unused supply or unmet demand, never as a real trip.",
                "",
            ]
        )
    lines.extend(_vam_markdown(result))
    lines.extend(_modi_markdown(result))
    lines.extend(
        [
            "### Transportation method comparison",
            "",
            "| method | feasible | status | objective (kit-metres) | unmet | unused | iterations | seconds |",
            "|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for name, item in result.transport.items():
        lines.append(
            "| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} |".format(
                _md(name),
                item.feasible,
                _md(item.status),
                _fmt(item.objective),
                item.unmet,
                item.unused,
                item.iterations,
                _fmt(item.seconds, 6),
            )
        )
    lines.extend(
        [
            "",
            "NWC and least-cost are comparison baselines; VAM is the initial "
            "solution; MODI is applied to the VAM allocation. The exact tableau "
            "MILP is an independent check of `Z0` and the final MODI objective. "
            "It does not enforce lane capacities.",
            "",
            "## 5. Road-capacitated network result",
            "",
        ]
    )
    lines.extend(_network_markdown(result))
    lines.extend(
        [
            "",
            "## 6. Routing algorithm comparison",
            "",
        ]
    )
    lines.extend(_routing_markdown(result))
    lines.extend(
        [
            "",
            "## 7. Validation and acceptance",
            "",
            "| area | result / evidence |",
            "|---|---|",
            "| conservation | all transportation row/column sums checked independently |",
            "| 48-ambulance limit | network check and fleet table above |",
            "| prohibited lanes | excluded from search; selected routes report no hits |",
            "| lane capacities | every selected route is assigned to every traversed lane; background is added separately |",
            "| integer assignments | kit trips, patient transfers, and vehicles are integral |",
            "| bed/resource shortages | unmet kit/patient variables are explicit; unused supply/beds are reported |",
            "| feasible/infeasible cases | the exact tableau solver and the network MILP both report status; a failure is never presented as success |",
            "| VAM penalties/allocations/Z0 | full trace, allocation tables, and `Z0` above |",
            "| MODI optimality/constraints | potentials, reduced costs, cycles, forbidden-cell preservation, and final check above |",
            "| Dijkstra/A*/Bellman-Ford | same distance on the compared pairs; route validity checked independently |",
            "| small exact validation | `tools/verify_or.py` brute-forces small tableaux and compares exact MILP |",
            "",
            "### Errors and warnings from this run",
            "",
        ]
    )
    if result.errors:
        for item in result.errors:
            lines.append("- **ERROR:** {0}".format(_md(item)))
    else:
        lines.append("- No errors.")
    if result.warnings:
        for item in result.warnings:
            lines.append("- WARNING: {0}".format(_md(item)))
    else:
        lines.append("- No warnings.")
    lines.extend(
        [
            "",
            "## 8. Reproduce",
            "",
            "```powershell",
            "& 'C:\\Users\\gamer\\AppData\\Local\\Programs\\Python\\Python310\\python.exe' run.py or-plan",
            "& 'C:\\Users\\gamer\\AppData\\Local\\Programs\\Python\\Python310\\python.exe' tools\\verify_or.py",
            "```",
            "",
            "Optional inputs: `--or-config config/or_planning.json`, "
            "`--out-dir reports`, `--json`, `--no-routing-comparison`, "
            "`--no-write`.",
            "",
            "The generated artifacts are deterministic in content apart from the "
            "UTC generation timestamp and measured runtimes. The synthetic input "
            "files are the source of every non-derived quantity.",
            "",
            "## 9. Missing data and limitations",
            "",
            "- Real free-bed counts, kit stock, zone kit demand, patient-transfer "
            "demand, measured background lane flow, and measured lane capacity are "
            "not present in the repository. The shipped values are synthetic and "
            "must be replaced before operational use.",
            "- The road-capacity value is a planning estimate from lane count and "
            "road type. It is not a field measurement.",
            "- Costs use snapped lane access points; facility-entrance or walking "
            "offsets are not added. Two distinct facilities can share one snapped "
            "access point, giving a modelled road distance of zero even when their "
            "entrances differ.",
            "- The network MILP selects flows over one Dijkstra candidate route per "
            "source/zone or zone/hospital pair. It does not enumerate alternative "
            "paths or reroute dynamically around congestion.",
            "- The transportation tableau treats a zone anchor as one delivery "
            "point. The network model routes trips to that anchor; it does not "
            "split a zone's demand across multiple internal destinations.",
            "- The fleet model is a conservative one-trip-per-ambulance-per-day "
            "assumption. It does not model shift scheduling, refuelling, or "
            "multiple trips by the same vehicle.",
            "- Fleet zone accounting charges kit trips to the destination zone and "
            "patient transfers to the origin zone. Empty repositioning and return "
            "legs are not modelled.",
            "- Standard MODI is used only on the kit-only tableau. It is not "
            "claimed to enforce lane capacities or the fleet limit.",
            "- The network MILP's `optimal` status is optimality for the stated "
            "integer model and objective. It is not a claim that the model captures "
            "every real operational objective.",
            "- The SVG plot is a schematic fit to the selected routes; it is not a "
            "survey-grade geographic projection.",
            "",
            "## 10. Source files",
            "",
            "| item | path |",
            "|---|---|",
            "| OR rules | `{0}` |".format(result.config.path),
            "| OR test data | `{0}` |".format(result.data.path),
            "| dispatch/zones | `{0}` |".format(result.dispatch_config.path),
            "| synthetic capacity | `{0}` |".format(result.capacity.source),
            "| SUMO network | `{0}` |".format(result.network.path),
            "",
            "## 11. Generated artifacts",
            "",
            "| artifact | file |",
            "|---|---|",
            "| this report | `or_report.md` |",
            "| full machine-readable plan | `or_plan.json` |",
            "| hospital roles | `or_hospitals.csv` |",
            "| zones | `or_zones.csv` |",
            "| kit cost table | `or_kit_cost_table.csv` |",
            "| VAM trace | `or_vam_trace.csv` |",
            "| MODI trace | `or_modi_trace.csv` |",
            "| transportation comparison | `or_transport_comparison.csv` |",
            "| routing comparison | `or_routing_comparison.csv` |",
            "| selected kit flows | `or_network_kit_flows.csv` |",
            "| selected patient flows | `or_network_patient_flows.csv` |",
            "| lane loads | `or_lane_loads.csv` |",
            "| network checks | `or_checks.csv` |",
            "| selected-route sketch | `or_routes.svg` |",
            "",
        ]
    )
    return "\n".join(lines) + "\n"
