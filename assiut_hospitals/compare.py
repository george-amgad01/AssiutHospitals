"""Measured algorithm comparison for the emergency dispatch (requirement 7).

مقارنة خوارزميات الإرسال بقياسات زمنية فعلية (المتطلب 7).

Each case is one (start point, required specialty) pair.  The script measures:

* the wall-clock runtime of each algorithm until it produces its answer;
* the resulting route's free-flow travel time and length;
* whether the selected hospital and time agree with the independent
  Bellman-Ford reference.

The pathfinders (Dijkstra, A*, Bellman-Ford) build their own routes.  The four
transportation methods only select a destination; their route is the Dijkstra
route to that destination, and the Dijkstra cost-matrix time is included in
their measured runtime.  This distinction is printed with the table.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .algorithms import (
    Target,
    astar_to_targets,
    bellman_ford,
    entry_times,
    transport_select,
)
from .config import PROJECT_ROOT
from .dispatch import Candidate, DispatchError, Dispatcher, Origin, Route, Zone, ZoneOutcome
from .dataset import HospitalRecord

TOLERANCE = 1e-6
PATHFINDERS = ("dijkstra", "astar", "bellman_ford")
TRANSPORT = ("vam", "least_cost", "northwest_corner", "modi")

ALGORITHM_LABELS = {
    "dijkstra": "Dijkstra",
    "astar": "A*",
    "bellman_ford": "Bellman-Ford",
    "vam": "VAM",
    "least_cost": "Least-cost",
    "northwest_corner": "North-west corner",
    "modi": "MODI",
}

ALGORITHM_NOTES = {
    "dijkstra": "Pathfinder (baseline used by the dispatch tool).",
    "astar": "Pathfinder; multi-target A* with an admissible straight-line heuristic.",
    "bellman_ford": "Independent pathfinder and reference optimum.",
    "vam": "Transportation selection; route/time taken from the Dijkstra matrix.",
    "least_cost": "Transportation selection; route/time taken from the Dijkstra matrix.",
    "northwest_corner": "Transportation selection; route/time taken from the Dijkstra matrix.",
    "modi": "Transportation selection improved with MODI; route/time from Dijkstra.",
}


@dataclass
class AlgorithmRow:
    """One algorithm result for one case."""

    origin: str
    zone: str
    specialty: str
    algorithm: str
    hospital: Optional[str]
    hospital_slug: Optional[str]
    runtime_seconds: float
    route_seconds: Optional[float]
    route_length_m: Optional[float]
    route_edges: int
    optimal: Optional[bool]
    verified: bool
    verification: str
    iterations: int = 0
    note: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "origin": self.origin,
            "zone": self.zone,
            "specialty": self.specialty,
            "algorithm": self.algorithm,
            "algorithm_label": ALGORITHM_LABELS.get(self.algorithm, self.algorithm),
            "hospital": self.hospital,
            "hospital_slug": self.hospital_slug,
            "runtime_seconds": round(self.runtime_seconds, 6),
            "route_seconds": (
                None if self.route_seconds is None else round(self.route_seconds, 6)
            ),
            "route_length_m": (
                None if self.route_length_m is None else round(self.route_length_m, 3)
            ),
            "route_edges": self.route_edges,
            "optimal": self.optimal,
            "verified": self.verified,
            "verification": self.verification,
            "iterations": self.iterations,
            "note": self.note,
        }


@dataclass
class CaseResult:
    origin: str
    lat: float
    lon: float
    zone: str
    specialty: str
    rows: List[AlgorithmRow] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "origin": self.origin,
            "lat": self.lat,
            "lon": self.lon,
            "zone": self.zone,
            "specialty": self.specialty,
            "error": self.error,
            "rows": [row.as_dict() for row in self.rows],
        }


# ---------------------------------------------------------------------------
# Case helpers
# ---------------------------------------------------------------------------
def _zone_for_origin(dispatcher: Dispatcher, origin: Origin) -> Zone:
    """Return the unambiguous start zone (owner decision G)."""
    containing = dispatcher.dcfg.zones_for_point(
        origin.snapped_lat, origin.snapped_lon
    )
    if not containing:
        raise DispatchError("origin is outside all four zones")
    if len(containing) > 1:
        raise DispatchError(
            "origin lies on a zone boundary: {0}".format(
                ", ".join(zone.id for zone in containing)
            )
        )
    return containing[0]


def _blank_suitable(
    dispatcher: Dispatcher,
    record: HospitalRecord,
    zone: Zone,
    specialty: str,
) -> Candidate:
    """Capacity/exclusion part of a candidate without running Dijkstra."""
    base = dispatcher._blank_candidate(record, zone)
    if base.excluded_reason:
        return base
    if not base.routable_flag or not base.emergency or base.beds_free <= 0:
        return base
    if specialty not in base.specialties:
        return base
    return base


def _is_suitable(candidate: Candidate, specialty: str) -> bool:
    if candidate.excluded_reason:
        return False
    if not candidate.routable_flag or not candidate.reachable:
        return False
    if not candidate.emergency or candidate.beds_free <= 0:
        return False
    return specialty in candidate.specialties


def _targets(
    dispatcher: Dispatcher,
    zone: Zone,
    specialty: str,
) -> List[Target]:
    """All routable target lanes of the suitable hospitals in one zone."""
    targets: List[Target] = []
    seen = set()
    for slug in zone.hospitals:
        record = dispatcher.dataset.by_slug(slug)
        if record is None:
            continue
        base = _blank_suitable(dispatcher, record, zone, specialty)
        if base.excluded_reason or not base.routable_flag:
            continue
        if not base.emergency or base.beds_free <= 0:
            continue
        if specialty not in base.specialties:
            continue
        if not record.snap.edge_id:
            continue
        edge = dispatcher.network.edges.get(record.snap.edge_id)
        if edge is None or edge.length <= 0:
            continue
        frac = record.snap.pos / edge.length
        frac = 0.0 if frac < 0.0 else (1.0 if frac > 1.0 else frac)
        point = (record.snap.x, record.snap.y)
        for lane in dispatcher.graph.usable_lanes(edge.id, dispatcher.vehicle_class):
            key = (slug, lane)
            if key in seen:
                continue
            seen.add(key)
            targets.append(Target(slug=slug, lane_id=lane, frac=frac, point=point))
    return targets


def _ordered_suitable(
    dispatcher: Dispatcher,
    zone: Zone,
    specialty: str,
    candidates: Sequence[Candidate],
) -> List[Candidate]:
    """Suitable candidates in the manual zone-list order (for NWC)."""
    by_slug = {candidate.slug: candidate for candidate in candidates}
    ordered: List[Candidate] = []
    for slug in zone.hospitals:
        candidate = by_slug.get(slug)
        if candidate is None:
            continue
        if _is_suitable(candidate, specialty):
            ordered.append(candidate)
    return ordered


def _candidate_from_astar(
    dispatcher: Dispatcher,
    zone: Zone,
    result,
) -> Candidate:
    record = dispatcher.dataset.by_slug(result.slug)
    if record is None:
        raise DispatchError("A* returned unknown hospital '{0}'".format(result.slug))
    candidate = dispatcher._blank_candidate(record, zone)
    candidate.seconds = result.seconds
    candidate.reachable = True
    candidate.lane_id = result.lane_id
    candidate.kind = result.kind
    candidate.pred = result.pred
    candidate.frac = result.frac
    return candidate


def _row(
    *,
    origin: str,
    zone: Zone,
    specialty: str,
    algorithm: str,
    candidate: Optional[Candidate],
    route: Optional[Route],
    runtime: float,
    optimal: Optional[bool],
    verified: bool,
    verification: str,
    iterations: int = 0,
) -> AlgorithmRow:
    return AlgorithmRow(
        origin=origin,
        zone=zone.id,
        specialty=specialty,
        algorithm=algorithm,
        hospital=candidate.name if candidate else None,
        hospital_slug=candidate.slug if candidate else None,
        runtime_seconds=runtime,
        route_seconds=route.seconds if route else None,
        route_length_m=route.length_m if route else None,
        route_edges=len(route.edges) if route else 0,
        optimal=optimal,
        verified=verified,
        verification=verification,
        iterations=iterations,
        note=ALGORITHM_NOTES[algorithm],
    )


# ---------------------------------------------------------------------------
# One comparison case
# ---------------------------------------------------------------------------
def run_case(
    dispatcher: Dispatcher,
    label: str,
    lat: float,
    lon: float,
    specialty: str,
) -> CaseResult:
    """Run all seven algorithms for one start point and specialty."""
    origin = dispatcher._origin(lat, lon)
    zone = _zone_for_origin(dispatcher, origin)
    case = CaseResult(
        origin=label, lat=lat, lon=lon, zone=zone.id, specialty=specialty
    )

    # ---- Dijkstra baseline
    started = time.perf_counter()
    distances, offsets, previous = dispatcher._dijkstra(origin)
    entries = dispatcher._entry_times(distances, offsets)
    candidates = [
        dispatcher._candidate(record, zone, origin, distances, offsets, entries)
        for record in dispatcher.dataset.hospitals
        if dispatcher.dcfg.zone_of(record.slug) is zone
    ]
    dijkstra_outcome = dispatcher._pick(zone, candidates, specialty)
    dijkstra_runtime = time.perf_counter() - started
    dijkstra_winner = dijkstra_outcome.winner
    dijkstra_route = (
        dispatcher._route_for(dijkstra_winner, origin, offsets, previous)
        if dijkstra_winner
        else None
    )
    if dijkstra_route is not None:
        dispatcher._verify_route(dijkstra_route, dijkstra_winner)

    # ---- Independent Bellman-Ford reference
    started = time.perf_counter()
    bf_distances, bf_offsets, bf_previous = bellman_ford(
        dispatcher.graph,
        dispatcher.model,
        origin.lanes,
        origin.pos_frac,
        dispatcher.vehicle_class,
    )
    bf_entries = entry_times(
        dispatcher.graph,
        dispatcher.model,
        bf_distances,
        bf_offsets,
        dispatcher.vehicle_class,
    )
    bf_candidates = [
        dispatcher._candidate(record, zone, origin, bf_distances, bf_offsets, bf_entries)
        for record in dispatcher.dataset.hospitals
        if dispatcher.dcfg.zone_of(record.slug) is zone
    ]
    bf_outcome = dispatcher._pick(zone, bf_candidates, specialty)
    bf_runtime = time.perf_counter() - started
    bf_winner = bf_outcome.winner
    bf_route = (
        dispatcher._route_for(bf_winner, origin, bf_offsets, bf_previous)
        if bf_winner
        else None
    )
    if bf_route is not None:
        dispatcher._verify_route(bf_route, bf_winner)
    bf_times = {
        candidate.slug: candidate.seconds
        for candidate in bf_candidates
        if candidate.seconds is not None
    }
    bf_optimum = bf_winner.slug if bf_winner else None
    bf_optimum_seconds = bf_winner.seconds if bf_winner else None

    # ---- A*
    started = time.perf_counter()
    targets = _targets(dispatcher, zone, specialty)
    astar_result = astar_to_targets(
        dispatcher.graph,
        dispatcher.model,
        dispatcher.network,
        origin.lanes,
        origin.pos_frac,
        targets,
        dispatcher.vehicle_class,
    )
    astar_runtime = time.perf_counter() - started
    astar_winner = (
        _candidate_from_astar(dispatcher, zone, astar_result)
        if astar_result is not None
        else None
    )
    astar_route = (
        dispatcher._route_for(
            astar_winner,
            origin,
            astar_result.offsets,
            astar_result.previous,
        )
        if astar_result is not None and astar_winner is not None
        else None
    )
    if astar_route is not None:
        dispatcher._verify_route(astar_route, astar_winner)

    # ---- Transportation methods
    suitable = _ordered_suitable(dispatcher, zone, specialty, candidates)
    transport_rows: List[AlgorithmRow] = []
    if suitable:
        costs = [float(candidate.seconds or 0.0) for candidate in suitable]
        supplies = [float(max(candidate.beds_free, 1)) for candidate in suitable]
        by_slug = {candidate.slug: candidate for candidate in suitable}
        for method in TRANSPORT:
            started = time.perf_counter()
            transport = transport_select(costs, supplies, method)
            selection_runtime = time.perf_counter() - started
            selected = suitable[transport.selected_index] if transport.selected_index is not None else None
            route = (
                dispatcher._route_for(selected, origin, offsets, previous)
                if selected is not None
                else None
            )
            if route is not None and selected is not None:
                try:
                    dispatcher._verify_route(route, selected)
                    verified = True
                    verification = "route time and continuity checked"
                except DispatchError as exc:
                    verified = False
                    verification = str(exc)
            else:
                verified = selected is None
                verification = "no suitable hospital" if selected is None else "route missing"
            expected = bf_times.get(selected.slug) if selected else None
            if expected is not None and route is not None:
                if abs(expected - route.seconds) > TOLERANCE:
                    verified = False
                    verification = "BF time {0:.6f}s != route {1:.6f}s".format(
                        expected, route.seconds
                    )
            optimal = (
                None
                if bf_optimum is None or selected is None
                else selected.slug == bf_optimum
            )
            transport_rows.append(
                _row(
                    origin=label,
                    zone=zone,
                    specialty=specialty,
                    algorithm=method,
                    candidate=selected,
                    route=route,
                    # The matrix cost comes from Dijkstra, so include it in the
                    # measured cost of this selection method.
                    runtime=dijkstra_runtime + selection_runtime,
                    optimal=optimal,
                    verified=verified,
                    verification=verification,
                    iterations=transport.iterations,
                )
            )
    else:
        for method in TRANSPORT:
            transport_rows.append(
                _row(
                    origin=label,
                    zone=zone,
                    specialty=specialty,
                    algorithm=method,
                    candidate=None,
                    route=None,
                    runtime=dijkstra_runtime,
                    optimal=None,
                    verified=True,
                    verification="no suitable hospital",
                )
            )

    # ---- Verification of the three pathfinders
    def path_verified(
        candidate: Optional[Candidate],
        route: Optional[Route],
    ) -> Tuple[bool, str]:
        if candidate is None:
            if bf_optimum is None:
                return True, "no suitable hospital in both results"
            return False, "no result, Bellman-Ford found {0}".format(bf_optimum)
        expected = bf_times.get(candidate.slug)
        if expected is None:
            return False, "Bellman-Ford cannot reach {0}".format(candidate.slug)
        if route is None:
            return False, "route missing"
        if abs(expected - route.seconds) > TOLERANCE:
            return False, "BF time {0:.6f}s != route {1:.6f}s".format(
                expected, route.seconds
            )
        if candidate.slug != bf_optimum:
            return False, "selected {0}, BF optimum {1}".format(
                candidate.slug, bf_optimum
            )
        return True, "matches independent Bellman-Ford optimum"

    dijkstra_ok, dijkstra_check = path_verified(dijkstra_winner, dijkstra_route)
    bf_ok, bf_check = path_verified(bf_winner, bf_route)
    astar_ok, astar_check = path_verified(astar_winner, astar_route)

    case.rows = [
        _row(
            origin=label,
            zone=zone,
            specialty=specialty,
            algorithm="dijkstra",
            candidate=dijkstra_winner,
            route=dijkstra_route,
            runtime=dijkstra_runtime,
            optimal=(
                None
                if bf_optimum is None or dijkstra_winner is None
                else dijkstra_winner.slug == bf_optimum
            ),
            verified=dijkstra_ok,
            verification=dijkstra_check,
        ),
        _row(
            origin=label,
            zone=zone,
            specialty=specialty,
            algorithm="astar",
            candidate=astar_winner,
            route=astar_route,
            runtime=astar_runtime,
            optimal=(
                None
                if bf_optimum is None or astar_winner is None
                else astar_winner.slug == bf_optimum
            ),
            verified=astar_ok,
            verification=astar_check,
        ),
        _row(
            origin=label,
            zone=zone,
            specialty=specialty,
            algorithm="bellman_ford",
            candidate=bf_winner,
            route=bf_route,
            runtime=bf_runtime,
            optimal=(
                None
                if bf_optimum is None or bf_winner is None
                else bf_winner.slug == bf_optimum
            ),
            verified=bf_ok,
            verification=bf_check,
        ),
    ] + transport_rows
    return case


# ---------------------------------------------------------------------------
# Default origins and full report
# ---------------------------------------------------------------------------
def default_origins(dispatcher: Dispatcher) -> List[Tuple[str, float, float]]:
    """One usable, non-dead-end hospital start per zone.

    نقطة بداية واحدة لكل منطقة من إحداثيات مستشفى حقيقي، مع تجاهل البدايات
    المسدودة التي يرفضها الإرسال.
    """
    origins: List[Tuple[str, float, float]] = []
    for zone in dispatcher.dcfg.zones:
        chosen = None
        for slug in zone.hospitals:
            record = dispatcher.dataset.by_slug(slug)
            if record is None or not record.routable:
                continue
            try:
                origin = dispatcher._origin(
                    record.hospital.lat, record.hospital.lon
                )
            except DispatchError:
                continue
            containing = dispatcher.dcfg.zones_for_point(
                origin.snapped_lat, origin.snapped_lon
            )
            if len(containing) == 1 and containing[0].id == zone.id:
                chosen = (slug, record.hospital.lat, record.hospital.lon)
                break
        if chosen is not None:
            origins.append(chosen)
    return origins


def _summary(rows: Sequence[AlgorithmRow]) -> List[Dict[str, Any]]:
    summary: List[Dict[str, Any]] = []
    for algorithm in PATHFINDERS + TRANSPORT:
        selected = [row for row in rows if row.algorithm == algorithm]
        if not selected:
            continue
        times = [
            row.route_seconds
            for row in selected
            if row.route_seconds is not None
        ]
        summary.append(
            {
                "algorithm": algorithm,
                "label": ALGORITHM_LABELS.get(algorithm, algorithm),
                "runs": len(selected),
                "mean_runtime_ms": round(
                    1000.0 * sum(row.runtime_seconds for row in selected) / len(selected),
                    3,
                ),
                "mean_route_seconds": (
                    round(sum(times) / len(times), 3) if times else None
                ),
                "optimal_runs": sum(1 for row in selected if row.optimal is True),
                "verified_runs": sum(1 for row in selected if row.verified),
                "failures": sum(1 for row in selected if not row.verified),
            }
        )
    return summary


def _markdown(payload: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Emergency dispatch algorithm comparison")
    lines.append("")
    lines.append(
        "Measured on the real Assiut SUMO network with the owner-approved "
        "start-zone-only search and free-flow travel times."
    )
    lines.append("")
    lines.append(
        "**Important:** Dijkstra, A* and Bellman-Ford are pathfinders. "
        "VAM, least-cost, north-west corner and MODI are transportation-problem "
        "selection methods; they choose a hospital and do not build a road route. "
        "Their route and travel time are taken from the Dijkstra matrix, and the "
        "Dijkstra matrix time is included in their runtime."
    )
    lines.append("")
    lines.append("Generated: `{0}`".format(payload["generated_at"]))
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(
        "| Algorithm | Runs | Mean runtime (ms) | Mean route time (s) | Optimal | Verified | Failures |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for item in payload["summary"]:
        lines.append(
            "| {label} | {runs} | {mean_runtime_ms:.3f} | {mean_route_seconds} | "
            "{optimal_runs} | {verified_runs} | {failures} |".format(
                label=item["label"],
                runs=item["runs"],
                mean_runtime_ms=item["mean_runtime_ms"],
                mean_route_seconds=(
                    "—" if item["mean_route_seconds"] is None else "{0:.3f}".format(item["mean_route_seconds"])
                ),
                optimal_runs=item["optimal_runs"],
                verified_runs=item["verified_runs"],
                failures=item["failures"],
            )
        )
    lines.append("")
    lines.append("## Per-case results")
    lines.append("")
    lines.append(
        "| Origin | Zone | Specialty | Algorithm | Selected hospital | Runtime (ms) | Route time (s) | Length (m) | Edges | Optimal | Verified |"
    )
    lines.append("|---|---|---|---|---|---:|---:|---:|---:|---|---|")
    for case in payload["cases"]:
        if case["error"]:
            lines.append(
                "| {origin} | {zone} | {specialty} | — | ERROR: {error} | — | — | — | — | — | no |".format(
                    **case
                )
            )
            continue
        for row in case["rows"]:
            lines.append(
                "| {origin} | {zone} | {specialty} | {algorithm} | {hospital} | "
                "{runtime:.3f} | {route_time} | {length} | {edges} | {optimal} | {verified} |".format(
                    origin=row["origin"],
                    zone=row["zone"],
                    specialty=row["specialty"],
                    algorithm=row["algorithm_label"],
                    hospital=row["hospital"] or "—",
                    runtime=1000.0 * row["runtime_seconds"],
                    route_time=(
                        "—" if row["route_seconds"] is None else "{0:.3f}".format(row["route_seconds"])
                    ),
                    length=(
                        "—" if row["route_length_m"] is None else "{0:.1f}".format(row["route_length_m"])
                    ),
                    edges=row["route_edges"],
                    optimal=(
                        "—" if row["optimal"] is None else ("yes" if row["optimal"] else "no")
                    ),
                    verified="yes" if row["verified"] else "**NO**",
                )
            )
    lines.append("")
    lines.append("## Verification")
    lines.append("")
    lines.append(
        "Every pathfinder result is compared with Bellman-Ford.  Every "
        "transportation selection is checked against the Bellman-Ford time for "
        "the hospital it selected.  A failure is shown in the table and makes "
        "the command exit with status 1."
    )
    lines.append("")
    return "\n".join(lines)


def run_comparison(
    dispatcher: Dispatcher,
    origins: Optional[Sequence[Tuple[str, float, float]]] = None,
    specialties: Optional[Sequence[str]] = None,
    out_dir: Optional[Path] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Run the comparison, write JSON/Markdown, and return the payload."""
    if origins is None:
        origins = default_origins(dispatcher)
    if specialties is None:
        specialties = ("general", "trauma", "cardiac", "pediatric")
    if out_dir is None:
        out_dir = PROJECT_ROOT / "reports"
    out_dir = Path(out_dir)

    cases: List[CaseResult] = []
    for label, lat, lon in origins:
        for specialty in specialties:
            if verbose:
                print(
                    "  {0:38s} {1:12s} ...".format(label[:38], specialty),
                    end="",
                    flush=True,
                )
            try:
                case = run_case(dispatcher, label, lat, lon, specialty)
            except DispatchError as exc:
                case = CaseResult(
                    origin=label,
                    lat=lat,
                    lon=lon,
                    zone="—",
                    specialty=specialty,
                    error=str(exc),
                )
            cases.append(case)
            if verbose:
                failures = sum(1 for row in case.rows if not row.verified)
                print(" {0} rows, {1} failure(s)".format(len(case.rows), failures))

    rows = [row for case in cases for row in case.rows]
    payload: Dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "search_scope": dispatcher.dcfg.search_scope,
        "zone_source": dispatcher.dcfg.zone_source,
        "cost_model": dispatcher.model.describe(),
        "algorithms": list(PATHFINDERS + TRANSPORT),
        "origins": [
            {"label": label, "lat": lat, "lon": lon}
            for label, lat, lon in origins
        ],
        "specialties": list(specialties),
        "cases": [case.as_dict() for case in cases],
        "summary": _summary(rows),
        "failures": sum(1 for row in rows if not row.verified),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "algorithm_comparison.json"
    md_path = out_dir / "algorithm_comparison.md"
    with open(json_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    with open(md_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(_markdown(payload))
        handle.write("\n")
    payload["json_path"] = str(json_path)
    payload["markdown_path"] = str(md_path)
    return payload
