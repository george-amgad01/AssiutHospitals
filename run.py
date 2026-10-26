#!/usr/bin/env python
"""Assiut Hospitals - emergency dispatch on the real Assiut SUMO network.

Usage
-----
    python run.py build                 # fetch OSM data, snap, write every artefact
    python run.py build --refresh       # ... and re-download the OSM data
    python run.py serve                 # serve the static dispatch map
    python run.py dispatch --lat 27.19 --lon 31.18 --specialty burns
    python run.py compare               # measured algorithm comparison table
    python run.py or-plan               # capacity-constrained OR plan + reports
    python run.py or-check              # validate the OR model without writing files
    python run.py list                  # print the hospital table
    python run.py info                  # show the resolved configuration
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:  # make sure Arabic names can be printed on a legacy console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  # pragma: no cover - very old interpreters
    pass

from assiut_hospitals.config import load_config  # noqa: E402
from assiut_hospitals.emit import generate  # noqa: E402


def _print_header(title: str) -> None:
    print()
    print("== {0} ".format(title) + "=" * max(0, 68 - len(title)))


def cmd_build(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    _print_header("build")
    dataset = generate(config, refresh=args.refresh, verbose=True)
    counts = dataset.meta.get("counts", {})
    print()
    print("  hospitals : {0}".format(counts.get("total", 0)))
    print("  in network: {0}".format(counts.get("in_network", 0)))
    print("  routable  : {0}".format(counts.get("routable", 0)))
    print("  outside   : {0}".format(counts.get("outside", 0)))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from assiut_hospitals.server import serve

    config = load_config(args.config)
    _print_header("serve")
    serve(
        config,
        host=args.host,
        port=args.port,
        open_browser=args.open,
    )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    from assiut_hospitals.dataset import load_dataset

    config = load_config(args.config)
    dataset = load_dataset(config.dataset_file)
    _print_header("hospitals")
    print(
        "  {0:<46} {1:<14} {2:<20} {3:>8} {4:>10}".format(
            "name", "category", "edge", "snap[m]", "routable"
        )
    )
    for record in dataset.hospitals:
        print(
            "  {0:<46} {1:<14} {2:<20} {3:>8.1f} {4:>10}".format(
                record.display_name[:46],
                record.hospital.category,
                record.snap.edge_id[:20] or "-",
                record.snap.distance_m,
                "yes" if record.routable else "no",
            )
        )
    return 0


def cmd_dispatch(args: argparse.Namespace) -> int:
    """Run the start-zone-only dispatch search from one point.

    يشغّل بحث الإرسال في منطقة نقطة البداية فقط.
    """
    from assiut_hospitals.dispatch import Dispatcher, DispatchError

    config = load_config(args.config)
    dispatcher = Dispatcher(config=config)

    errors = dispatcher.validate()
    if not args.json:
        _print_header("dispatch")
        for error in errors:
            print("  config error: {0}".format(error))
    if errors and not args.force:
        if args.json:
            print(json.dumps({"config_errors": errors, "result": None}, ensure_ascii=False, indent=1))
        else:
            print()
            print("  RESULT: FAIL (fix the configuration or pass --force)")
        return 2

    if args.check:
        for zone in dispatcher.dcfg.zones:
            records = dispatcher.dcfg.hospitals_of(zone, dispatcher.dataset)
            routable = [r for r in records if r.routable]
            print(
                "  {0:<3} {1:<32} hospitals={2:<2} routable={3}".format(
                    zone.id, zone.name, len(records), len(routable)
                )
            )
        print("  zone source : {0}".format(dispatcher.dcfg.zone_source))
        print("  search scope: {0}".format(dispatcher.dcfg.search_scope))
        print("  capacity    : {0}".format(dispatcher.capacity.source))
        print(
            "  clinics     : {0}".format(
                "counted as emergency" if dispatcher.dcfg.clinics_as_emergency else "excluded"
            )
        )
        print(
            "  excluded    : {0}".format(
                ", ".join(sorted(dispatcher.dcfg.excluded_destinations)) or "none"
            )
        )
        print()
        print("  RESULT: {0}".format("PASS" if not errors else "FAIL"))
        return 0 if not errors else 1

    if args.lat is None or args.lon is None:
        print("  error: --lat and --lon are required (or use --check)")
        return 2

    try:
        result = dispatcher.search(
            args.lat, args.lon, args.specialty, verify=not args.no_verify
        )
    except DispatchError as exc:
        print("  error: {0}".format(exc))
        return 2

    payload = result.as_dict()
    payload["config_errors"] = errors
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=1))
        return 0 if result.optimal is not None else 1

    origin = result.origin
    print(
        "  origin      : {0:.6f}, {1:.6f} -> edge {2} ({3:.1f} m snap)".format(
            origin.lat, origin.lon, origin.edge_id, origin.distance_m
        )
    )
    print("  specialty   : {0}".format(result.specialty))
    print("  search zone : {0}".format(result.search_zone))
    print(
        "  capacity    : {0}{1}".format(
            result.capacity_source,
            " (SYNTHETIC - not real data)" if result.synthetic_capacity else "",
        )
    )
    print(
        "  cost model  : {0} (congestion enabled: {1})".format(
            result.cost_model.get("mode"),
            result.cost_model.get("congestion_enabled"),
        )
    )
    print()
    for zone in result.zones:
        if zone.winner is not None:
            print(
                "  {0:<3} {1:<30} -> {2:<40} {3:8.1f} s".format(
                    zone.zone_id,
                    zone.zone_name,
                    zone.winner.name[:40],
                    zone.winner.seconds or 0.0,
                )
            )
        else:
            print(
                "  {0:<3} {1:<30} -> none ({2})".format(
                    zone.zone_id, zone.zone_name, zone.note
                )
            )

    print()
    if result.optimal is None or result.route is None:
        print("  RESULT: no suitable hospital found in the start zone")
        return 1

    route = result.route
    print(
        "  OPTIMAL     : {0} ({1}), zone {2}".format(
            result.optimal.name, result.optimal.slug, result.optimal.zone_id
        )
    )
    print(
        "  expected    : {0:.1f} s  |  {1:.0f} m  |  {2} edges".format(
            route.seconds, route.length_m, len(route.edges)
        )
    )
    print("  route       : {0}".format(" -> ".join(route.edges)))
    print(
        "  search time : {0:.3f} s (Dijkstra + candidate evaluation)".format(
            result.runtime_seconds
        )
    )
    for note in result.notes:
        print("  note        : {0}".format(note))
    print()
    print("  RESULT: PASS")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """Run the measured comparison of all owner-selected algorithms.

    يشغّل مقارنة فعلية بين كل الخوارزميات التي اختارها المالك.
    """
    from assiut_hospitals.compare import run_comparison
    from assiut_hospitals.dispatch import Dispatcher, DispatchError

    config = load_config(args.config)
    dispatcher = Dispatcher(config=config)
    errors = dispatcher.validate()
    for error in errors:
        print("CONFIG ERROR: {0}".format(error))
    if errors:
        return 2

    specialties = [
        item.strip() for item in args.specialties.split(",") if item.strip()
    ]
    for specialty in specialties:
        if specialty not in dispatcher.dcfg.specialty_catalog:
            print("unknown specialty: {0}".format(specialty))
            return 2

    _print_header("algorithm comparison")
    try:
        payload = run_comparison(
            dispatcher,
            specialties=specialties,
            out_dir=Path(args.out_dir) if args.out_dir else None,
            verbose=not args.quiet,
        )
    except DispatchError as exc:
        print("  error: {0}".format(exc))
        return 2

    print()
    print("  markdown: {0}".format(payload["markdown_path"]))
    print("  json    : {0}".format(payload["json_path"]))
    print("  failures: {0}".format(payload["failures"]))
    return 0 if payload["failures"] == 0 else 1


def _or_summary_lines(result) -> None:
    """Print the compact, non-hiding summary used by both OR commands."""
    synthetic = result.data.synthetic or result.capacity.synthetic
    print("  synthetic input: {0}".format(
        "YES - replace before operational use" if synthetic else "no"
    ))
    print("  hospitals      : {0} routable, {1} zones".format(
        len(result.hospitals), len(result.zones)
    ))
    print("  kit supply     : {0} kits in {1} active sources".format(
        result.total_kit_supply,
        sum(1 for item in result.hospitals.values() if item.source_active),
    ))
    gap = result.total_kit_supply - result.total_kit_demand
    print("  kit demand     : {0} kits; unused supply {1}, unmet demand {2}".format(
        result.total_kit_demand, max(gap, 0), max(-gap, 0)
    ))
    print("  patient demand : {0} transfers; {1} usable free beds".format(
        result.total_patient_demand, result.total_beds
    ))
    vam = result.transport.get("VAM")
    modi = result.transport.get("MODI")
    exact = result.transport.get("exact-MILP")
    print("  VAM Z0         : {0} kit-metres".format(
        "n/a" if vam is None else "{0:.3f}".format(vam.objective)
    ))
    print("  MODI           : {0} ({1})".format(
        "n/a" if modi is None else "{0:.3f} kit-metres".format(modi.objective),
        "n/a" if modi is None else modi.status,
    ))
    print("  exact tableau  : {0}".format(
        "n/a" if exact is None else "{0:.3f} kit-metres".format(exact.objective)
    ))
    plan = result.network_plan
    if plan is not None:
        print("  network MILP   : {0} / success={1}".format(plan.status, plan.success))
        print("  demand met     : {0} (unmet kits {1}, unmet patients {2})".format(
            plan.demand_met, plan.total_unmet_kits, plan.total_unmet_patients
        ))
        print("  vehicles       : {0} / {1}".format(
            plan.vehicles_used, result.config.fleet_size
        ))
        print("  vehicle-metres : {0:.3f} (kit {1:.3f}, patient {2:.3f})".format(
            plan.total_vehicle_m, plan.kit_vehicle_m, plan.patient_vehicle_m
        ))
    print("  feasible       : {0}".format("YES" if result.feasible else "NO"))
    print("  optimal         : {0}".format(
        "YES for the stated network MILP"
        if result.optimal
        else "NO - not a proof of global optimality"
    ))
    for error in result.errors:
        print("  ERROR          : {0}".format(error))
    for warning in result.warnings:
        print("  warning        : {0}".format(warning))


def _or_result_label(result) -> str:
    """Distinguish a feasible plan, unmet demand, and a hard model failure."""
    plan = result.network_plan
    if result.errors:
        return "FAIL (model or physical check failed)"
    if plan is None:
        return "FAIL (no network plan)"
    if not plan.success:
        return "FAIL / INFEASIBLE"
    if not plan.demand_met:
        return "FAIL (unmet demand)"
    if not plan.feasible:
        return "FAIL (physical constraint)"
    return "PASS (feasible)"


def cmd_or_plan(args: argparse.Namespace) -> int:
    """Build and solve the complete OR plan and write every report.

    يبني ويحل خطة بحوث العمليات كاملة ويكتب كل التقارير.
    """
    from assiut_hospitals.or_config import ORConfigError, load_or_config
    from assiut_hospitals.or_planning import ORPlanner
    from assiut_hospitals.or_report import write_reports

    config = load_config(args.config)
    try:
        or_config = load_or_config(args.or_config, root=config.root)
        planner = ORPlanner(config=config, or_config=or_config)
        result = planner.plan(routing_comparison=not args.no_routing_comparison)
    except ORConfigError as exc:
        print("OR CONFIG ERROR: {0}".format(exc))
        return 2
    except Exception as exc:  # network/route/solver failures must be visible
        print("OR RUN ERROR: {0}".format(exc))
        return 2

    _print_header("OR capacity-constrained plan")
    _or_summary_lines(result)
    if not args.no_write:
        out_dir = Path(args.out_dir) if args.out_dir else result.config.output_dir
        paths = write_reports(result, out_dir)
        print()
        print("  report         : {0}".format(paths["markdown"]))
        print("  json           : {0}".format(paths["json"]))
        print("  tables / csv   : {0}".format(out_dir))
        print("  route sketch   : {0}".format(paths["routes_svg"]))
    if args.json:
        print()
        print(json.dumps(result.summary(), ensure_ascii=False, indent=1, default=str))
    print()
    print("  RESULT: {0}".format(_or_result_label(result)))
    return 0 if result.feasible else 1


def cmd_or_check(args: argparse.Namespace) -> int:
    """Run the OR model and print its independent constraints without files.

    يشغّل نموذج بحوث العمليات ويطبع قيوده المستقلة دون كتابة ملفات.
    """
    from assiut_hospitals.or_config import ORConfigError, load_or_config
    from assiut_hospitals.or_planning import ORPlanner

    config = load_config(args.config)
    try:
        or_config = load_or_config(args.or_config, root=config.root)
        planner = ORPlanner(config=config, or_config=or_config)
        result = planner.plan(routing_comparison=False)
    except ORConfigError as exc:
        print("OR CONFIG ERROR: {0}".format(exc))
        return 2
    except Exception as exc:
        print("OR RUN ERROR: {0}".format(exc))
        return 2

    _print_header("OR checks")
    _or_summary_lines(result)
    plan = result.network_plan
    if plan is not None:
        print()
        print("  independent checks:")
        for name, passed in sorted(plan.checks.items()):
            print("    {0:<32} {1}".format(name, "PASS" if passed else "FAIL"))
    print()
    if args.json:
        print(json.dumps(result.summary(), ensure_ascii=False, indent=1, default=str))
    print()
    print("  RESULT: {0}".format(_or_result_label(result)))
    return 0 if result.feasible and not result.errors else 1


def cmd_info(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    _print_header("info")
    print("  project root : {0}".format(config.root))
    print("  net file     : {0}".format(config.net_file))
    print("  route file   : {0}".format(config.route_file))
    print("  dataset      : {0}".format(config.dataset_file))
    print("  poi file     : {0}".format(config.poi_file))
    print("  routes file  : {0}".format(config.hospital_routes_file))
    print("  sumocfg      : {0}".format(config.sumocfg_file))
    print("  web dir      : {0}".format(config.web_dir))
    try:
        from assiut_hospitals.bootstrap import sumo_home, sumo_tools_dir

        print("  SUMO_HOME    : {0}".format(sumo_home()))
        print("  SUMO tools   : {0}".format(sumo_tools_dir()))
    except Exception:
        pass
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="Assiut emergency dispatch on the real SUMO network",
    )
    parser.add_argument("--config", help="path to config.json", default=None)
    sub = parser.add_subparsers(dest="command")

    p_build = sub.add_parser("build", help="generate all artefacts")
    p_build.add_argument("--refresh", action="store_true", help="re-download the OSM data")
    p_build.set_defaults(func=cmd_build)

    p_serve = sub.add_parser("serve", help="serve the static dispatch map")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.add_argument("--open", action="store_true", help="open a browser window")
    p_serve.set_defaults(func=cmd_serve)

    p_compare = sub.add_parser(
        "compare", help="measure and compare all dispatch algorithms"
    )
    p_compare.add_argument(
        "--specialties",
        default="general,trauma,cardiac,pediatric",
        help="comma separated specialties to test",
    )
    p_compare.add_argument(
        "--out-dir",
        default=None,
        help="directory for algorithm_comparison.md/json (default: reports/)",
    )
    p_compare.add_argument("--quiet", action="store_true", help="do not print each case")
    p_compare.set_defaults(func=cmd_compare)

    p_or_plan = sub.add_parser(
        "or-plan", help="solve the capacity-constrained OR model and write reports"
    )
    p_or_plan.add_argument(
        "--or-config",
        default=None,
        help="path to config/or_planning.json (default: config/or_planning.json)",
    )
    p_or_plan.add_argument(
        "--json",
        action="store_true",
        help="print the machine-readable summary in addition to the text",
    )
    p_or_plan.add_argument(
        "--out-dir",
        default=None,
        help="directory for the OR reports (default: reports/)",
    )
    p_or_plan.add_argument(
        "--no-write",
        action="store_true",
        help="do not write reports (use --json for the summary)",
    )
    p_or_plan.add_argument(
        "--no-routing-comparison",
        action="store_true",
        help="skip the Dijkstra/A*/Bellman-Ford comparison",
    )
    p_or_plan.set_defaults(func=cmd_or_plan)

    p_or_check = sub.add_parser(
        "or-check",
        help="solve the OR model and print checks without writing reports",
    )
    p_or_check.add_argument(
        "--or-config",
        default=None,
        help="path to config/or_planning.json (default: config/or_planning.json)",
    )
    p_or_check.add_argument(
        "--json",
        action="store_true",
        help="print the machine-readable summary in addition to the text",
    )
    p_or_check.set_defaults(func=cmd_or_check)

    p_dispatch = sub.add_parser(
        "dispatch", help="find the fastest suitable hospital from a point"
    )
    p_dispatch.add_argument("--lat", type=float, default=None, help="start latitude")
    p_dispatch.add_argument("--lon", type=float, default=None, help="start longitude")
    p_dispatch.add_argument(
        "--specialty", default="general", help="required specialty (default: general)"
    )
    p_dispatch.add_argument(
        "--check", action="store_true", help="validate the zones/capacity and exit"
    )
    p_dispatch.add_argument("--json", action="store_true", help="print the full JSON result")
    p_dispatch.add_argument(
        "--no-verify", action="store_true", help="skip the independent route check"
    )
    p_dispatch.add_argument(
        "--force", action="store_true", help="run even if the configuration has errors"
    )
    p_dispatch.set_defaults(func=cmd_dispatch)

    p_list = sub.add_parser("list", help="print the hospital table")
    p_list.set_defaults(func=cmd_list)

    p_info = sub.add_parser("info", help="show the resolved configuration")
    p_info.set_defaults(func=cmd_info)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
