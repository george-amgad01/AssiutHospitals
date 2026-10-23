#!/usr/bin/env python
"""Independent validation of the dispatch search (working rule 7).

تحقق مستقل من نتائج بحث الإرسال باستخدام خوارزمية ثانية.

The dispatcher uses Dijkstra on the class-aware lane graph.  This script
recomputes the shortest travel times with **Bellman-Ford** and checks:

* every lane time produced by Dijkstra against Bellman-Ford;
* the single start-zone winner (owner decision G) against the independent
  hospital time;
* the returned route (continuity, emergency permission, time, endpoints);
* that clinics and the owner-excluded dead-end destinations are never selected;
* that a dead-end start is refused (owner decision I).

Exit code 0 means every check passed.

لا تُعدَّل أي بيانات هنا؛ نقاط البداية هي إحداثيات المستشفيات الحقيقية.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path
from typing import List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  # pragma: no cover
    pass

from assiut_hospitals.algorithms import bellman_ford, entry_times  # noqa: E402
from assiut_hospitals.config import load_config  # noqa: E402
from assiut_hospitals.dispatch import Dispatcher, DispatchError  # noqa: E402

TOLERANCE = 1e-6


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None, help="path to config.json")
    parser.add_argument(
        "--specialties",
        default="general,burns,cardiac",
        help="comma separated specialties to test",
    )
    parser.add_argument(
        "--origins",
        type=int,
        default=4,
        help="number of routable hospital coordinates to use as origins",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    dispatcher = Dispatcher(config=config)
    errors = dispatcher.validate()
    for error in errors:
        print("CONFIG ERROR: {0}".format(error))
    if errors:
        print("RESULT: FAIL (invalid configuration)")
        return 1

    specialties = [item.strip() for item in args.specialties.split(",") if item.strip()]
    for specialty in specialties:
        if specialty not in dispatcher.dcfg.specialty_catalog:
            print("unknown specialty: {0}".format(specialty))
            return 1

    # One real hospital coordinate per zone.  _origin now refuses dead-end
    # components (owner decision I), so those hospitals are skipped here.
    origins = []
    for zone in dispatcher.dcfg.zones:
        for record in sorted(
            dispatcher.dcfg.hospitals_of(zone, dispatcher.dataset),
            key=lambda item: item.slug,
        ):
            if not record.routable:
                continue
            try:
                probe = dispatcher._origin(record.hospital.lat, record.hospital.lon)
            except DispatchError:
                continue
            containing = dispatcher.dcfg.zones_for_point(
                probe.snapped_lat, probe.snapped_lon
            )
            if len(containing) != 1 or containing[0].id != zone.id:
                continue
            origins.append((zone, record))
            break
    if args.origins > 0:
        origins = origins[: args.origins]

    print("== dispatch verification ==")
    print("  origins     : {0}".format(len(origins)))
    print("  specialties : {0}".format(", ".join(specialties)))
    print("  capacity    : {0}".format(dispatcher.capacity.source))
    print("  scope       : {0}".format(dispatcher.dcfg.search_scope))
    print()

    failures = 0
    checks = 0

    for zone, record in origins:
        label = record.display_name
        print(
            "-- origin: {0} [{1}] ({2}, {3})".format(
                label, zone.id, record.hospital.lat, record.hospital.lon
            )
        )
        origin = dispatcher._origin(record.hospital.lat, record.hospital.lon)
        dijkstra, offsets, _previous = dispatcher._dijkstra(origin)
        entries_d = dispatcher._entry_times(dijkstra, offsets)

        started = time.perf_counter()
        bellman, bf_offsets, _bf_previous = bellman_ford(
            dispatcher.graph,
            dispatcher.model,
            origin.lanes,
            origin.pos_frac,
            dispatcher.vehicle_class,
        )
        bf_seconds = time.perf_counter() - started
        entries_b = entry_times(
            dispatcher.graph,
            dispatcher.model,
            bellman,
            bf_offsets,
            dispatcher.vehicle_class,
        )

        # 1. Dijkstra vs Bellman-Ford on every reachable lane.
        worst = 0.0
        worst_lane = ""
        for lane, value in dijkstra.items():
            other = bellman.get(lane)
            if other is None:
                failures += 1
                print("   FAIL: lane {0} reachable by Dijkstra only".format(lane))
                continue
            delta = abs(value - other)
            if delta > worst:
                worst = delta
                worst_lane = lane
        checks += 1
        if worst > TOLERANCE:
            failures += 1
            print(
                "   FAIL: lane distances differ by {0:.9f}s at {1}".format(
                    worst, worst_lane
                )
            )
        else:
            print(
                "   lane distances: {0} lanes, max delta {1:.2e}s (BF {2:.2f}s)".format(
                    len(dijkstra), worst, bf_seconds
                )
            )

        # 2. Independent winner from the Bellman-Ford distances.
        bf_candidates = [
            dispatcher._candidate(
                item, zone, origin, bellman, bf_offsets, entries_b
            )
            for item in dispatcher.dataset.hospitals
            if dispatcher.dcfg.zone_of(item.slug) is zone
        ]
        bf_outcome = dispatcher._pick(zone, bf_candidates, specialty=specialties[0])
        bf_winner_any = bf_outcome.winner

        for specialty in specialties:
            try:
                result = dispatcher.search(
                    record.hospital.lat, record.hospital.lon, specialty, verify=True
                )
            except DispatchError as exc:
                failures += 1
                print("   FAIL: {0} search error: {1}".format(specialty, exc))
                continue

            checks += 1
            if result.search_scope != "start_zone_only":
                failures += 1
                print("   FAIL: {0} search scope is {1}".format(specialty, result.search_scope))
            if len(result.zones) != 1 or result.zones[0].zone_id != zone.id:
                failures += 1
                print(
                    "   FAIL: {0} searched zones {1}, expected only {2}".format(
                        specialty,
                        [item.zone_id for item in result.zones],
                        zone.id,
                    )
                )

            # 3. Recompute the same specialty winner for the searched zone.
            expected_outcome = dispatcher._pick(
                zone, bf_candidates, specialty=specialty
            )
            expected = expected_outcome.winner
            checks += 1
            if expected is None:
                if result.optimal is not None:
                    failures += 1
                    print(
                        "   FAIL: {0} returned {1}, BF found no suitable hospital".format(
                            specialty, result.optimal.slug
                        )
                    )
            elif (
                result.optimal is None
                or result.optimal.slug != expected.slug
                or abs((result.optimal.seconds or 0.0) - (expected.seconds or 0.0)) > TOLERANCE
            ):
                failures += 1
                print(
                    "   FAIL: {0} optimum {1} vs BF {2}".format(
                        specialty,
                        getattr(result.optimal, "slug", None),
                        expected.slug,
                    )
                )

            # 4. Owner rules: clinics and excluded destinations are never selected.
            if result.optimal is not None:
                selected_record = dispatcher.dataset.by_slug(result.optimal.slug)
                if selected_record is not None and selected_record.hospital.category == "clinic":
                    failures += 1
                    print("   FAIL: {0} selected a clinic".format(specialty))
                if dispatcher.dcfg.excluded_reason(result.optimal.slug):
                    failures += 1
                    print("   FAIL: {0} selected an excluded destination".format(specialty))
                if result.optimal.excluded_reason:
                    failures += 1
                    print("   FAIL: {0} winner carries an exclusion".format(specialty))

            # 5. The route itself: endpoints, continuity, permission, time.
            if result.optimal is not None and result.route is not None:
                route = result.route
                checks += 1
                if not route.segments:
                    failures += 1
                    print("   FAIL: {0} empty route".format(specialty))
                else:
                    first = route.segments[0]
                    last = route.segments[-1]
                    if first.lane_id not in origin.lanes:
                        failures += 1
                        print("   FAIL: {0} route starts on {1}".format(specialty, first.lane_id))
                    if last.lane_id != result.optimal.lane_id:
                        failures += 1
                        print("   FAIL: {0} route ends on {1}".format(specialty, last.lane_id))
                    for index, segment in enumerate(route.segments):
                        if not dispatcher.graph.lane_allowed(
                            segment.lane_id, dispatcher.vehicle_class
                        ):
                            failures += 1
                            print(
                                "   FAIL: {0} lane {1} forbids {2}".format(
                                    specialty, segment.lane_id, dispatcher.vehicle_class
                                )
                            )
                        if index + 1 < len(route.segments):
                            follower = route.segments[index + 1].lane_id
                            if follower not in dispatcher.graph.successors.get(
                                segment.lane_id, ()
                            ):
                                failures += 1
                                print(
                                    "   FAIL: {0} disconnected {1} -> {2}".format(
                                        specialty, segment.lane_id, follower
                                    )
                                )
                    total, _length = route.recompute()
                    if abs(total - (result.optimal.seconds or 0.0)) > TOLERANCE:
                        failures += 1
                        print(
                            "   FAIL: {0} route time {1} vs candidate {2}".format(
                                specialty, total, result.optimal.seconds
                            )
                        )
                    hospital = dispatcher.dataset.by_slug(result.optimal.slug)
                    edge = dispatcher.network.edges[hospital.snap.edge_id]
                    expected_frac = min(1.0, max(0.0, hospital.snap.pos / edge.length))
                    if abs(last.to_frac - expected_frac) > 1e-6:
                        failures += 1
                        print(
                            "   FAIL: {0} route ends at {1:.6f}, hospital at {2:.6f}".format(
                                specialty, last.to_frac, expected_frac
                            )
                        )

            label_text = (
                "{0} {1:.1f}s".format(result.optimal.name, result.optimal.seconds or 0.0)
                if result.optimal
                else "none"
            )
            print(
                "   {0:<9} zone={1} optimum={2}".format(
                    specialty,
                    result.search_zone,
                    label_text,
                )
            )
        print()

    # 6. A known dead-end start must be refused instead of silently searching.
    dead_end_slugs = list(dispatcher.dcfg.excluded_destinations)
    if dead_end_slugs:
        record = dispatcher.dataset.by_slug(dead_end_slugs[0])
        if record is not None:
            checks += 1
            try:
                dispatcher._origin(record.hospital.lat, record.hospital.lon)
            except DispatchError:
                pass
            else:
                failures += 1
                print(
                    "   FAIL: dead-end start {0} was accepted".format(
                        record.slug
                    )
                )

    print("checks: {0}  failures: {1}".format(checks, failures))
    print("RESULT: {0}".format("PASS" if failures == 0 else "FAIL"))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
