"""Generation of every artefact of the project.

``build_dataset`` reads the OSM data, snaps the hospitals onto the SUMO
network and writes

* ``data/hospitals.json``     - the machine readable dataset,
* ``sumo/hospitals.poi.xml``  - SUMO POIs (the hospital markers),
* ``sumo/hospitals.rou.xml``  - an empty route file (periodic flows removed),
* ``sumo/hospitals.sumocfg``  - a ready to run SUMO configuration,
* ``web/network.js``          - the road network for the map,
* ``web/hospitals.js``         - the hospital dataset for the map.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .config import Config
from .dataset import Dataset, HospitalRecord
from .hospitals import Hospital, hospitals_from_elements
from .netmodel import Network, open_network
from .overpass import load_or_fetch
from .snapping import SnapResult, Snapper, get_snapper

XML_HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n'


# --------------------------------------------------------------------- helpers
def write_text(path: Path, text: str) -> Path:
    """Write UTF-8 text *without* a byte order mark."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def _xml_escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _round(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


# ------------------------------------------------------------------- pipeline
def collect_hospitals(config: Config, refresh: bool = False, verbose: bool = True) -> List[Hospital]:
    """Load (or download) the OSM data and normalise it."""
    overpass_cfg = config.overpass
    mirrors = overpass_cfg.get("mirrors", [])
    payload = load_or_fetch(
        config.cache_file,
        int(overpass_cfg.get("area_id", 3603726184)),
        mirrors,
        timeout=int(overpass_cfg.get("timeout_seconds", 90)),
        refresh=refresh or bool(overpass_cfg.get("refresh", False)),
        verbose=verbose,
    )
    hospitals = hospitals_from_elements(payload.get("elements", []))
    if verbose:
        print("  {0} healthcare facilities after de-duplication".format(len(hospitals)))
    return hospitals


def snap_hospitals(
    config: Config,
    hospitals: Sequence[Hospital],
    snapper: Optional[Snapper] = None,
    verbose: bool = True,
) -> List[HospitalRecord]:
    """Project every hospital onto the network and flag the routable ones."""
    network = open_network(config.net_file)
    vehicle_class = config.ambulances.get("vtype_class", "emergency")
    if snapper is None:
        snapper = get_snapper(config.net_file, vehicle_class=vehicle_class)
    max_distance = float(config.snapping.get("max_snap_distance_m", 250.0))

    records: List[HospitalRecord] = []
    for hospital in hospitals:
        x, y = network.to_local(hospital.lon, hospital.lat)
        snap = snapper.snap_local(x, y)
        inside = network.contains_local(x, y)
        routable = bool(
            inside and snap.edge_id and snap.usable and snap.distance_m <= max_distance
        )
        records.append(
            HospitalRecord(
                hospital=hospital,
                snap=snap,
                in_network=inside,
                routable=routable,
            )
        )

    if verbose:
        inside = sum(1 for r in records if r.in_network)
        routable = sum(1 for r in records if r.routable)
        blocked = sum(
            1 for r in records if r.in_network and not r.snap.usable
        )
        print(
            "  {0} hospitals: {1} inside the network, {2} routable"
            " ({3} on roads an ambulance may not use)".format(
                len(records), inside, routable, blocked
            )
        )
    return records


def build_dataset(
    config: Config,
    refresh: bool = False,
    verbose: bool = True,
) -> Dataset:
    """Run the full data pipeline (OSM -> hospitals -> snapped records)."""
    if verbose:
        print("[1/4] collecting OSM healthcare POIs")
    hospitals = collect_hospitals(config, refresh=refresh, verbose=verbose)

    if verbose:
        print("[2/4] snapping hospitals onto the SUMO network")
    records = snap_hospitals(config, hospitals, verbose=verbose)

    network = open_network(config.net_file)

    meta = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "net_file": str(config.net_file),
        "route_file": str(config.route_file) if config.route_file else "",
        "projection": {
            "zone": network.projection.zone,
            "net_offset": list(network.net_offset),
            "proj_parameter": network.proj_parameter,
        },
        "counts": {
            "total": len(records),
            "in_network": sum(1 for r in records if r.in_network),
            "routable": sum(1 for r in records if r.routable),
            "outside": sum(1 for r in records if not r.in_network),
        },
    }
    return Dataset(meta=meta, hospitals=records)


# ------------------------------------------------------------------- emitters
def emit_dataset_json(dataset: Dataset, path: Path) -> Path:
    payload = {
        "meta": dataset.meta,
        "hospitals": [record.as_dict() for record in dataset.hospitals],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
    return write_text(path, text)


def emit_poi_xml(dataset: Dataset, path: Path) -> Path:
    """Write the SUMO additional file with one POI per hospital."""
    lines = [
        XML_HEADER,
        '<additional xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ' xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/additional_file.xsd">',
    ]
    for index, record in enumerate(dataset.hospitals, start=1):
        hospital = record.hospital
        color = "1,0,0" if record.routable else "0.55,0.55,0.55"
        lines.append(
            '    <poi id="hosp_{0:03d}" type="hospital" x="{1}" y="{2}"'
            ' width="14" height="14" color="{3}" name="{4}"/>'.format(
                index,
                _round(record.snap.x, 2) if record.snap.edge_id else _round(
                    _local_x(dataset, record), 2
                ),
                _round(record.snap.y, 2) if record.snap.edge_id else _round(
                    _local_y(dataset, record), 2
                ),
                color,
                _xml_escape(hospital.display_name),
            )
        )
    lines.append("</additional>")
    lines.append("")
    return write_text(path, "\n".join(lines))


def _local_x(dataset: Dataset, record: HospitalRecord) -> float:
    meta_projection = dataset.meta.get("projection", {})
    offset = meta_projection.get("net_offset", [0.0, 0.0])
    from .projection import lonlat_to_utm

    easting, _northing = lonlat_to_utm(
        record.hospital.lon, record.hospital.lat, int(meta_projection.get("zone", 36))
    )
    return easting + float(offset[0])


def _local_y(dataset: Dataset, record: HospitalRecord) -> float:
    meta_projection = dataset.meta.get("projection", {})
    offset = meta_projection.get("net_offset", [0.0, 0.0])
    from .projection import lonlat_to_utm

    _easting, northing = lonlat_to_utm(
        record.hospital.lon, record.hospital.lat, int(meta_projection.get("zone", 36))
    )
    return northing + float(offset[1])


def emit_empty_routes(path: Path) -> Path:
    """Write an empty route file because the periodic flows were removed.

    كتابة ملف مسارات فارغ بعد إزالة التدفقات الدورية الـ48 بقرار المالك.
    """
    lines = [
        XML_HEADER,
        "<!-- No periodic ambulance flows: removed by owner decision (requirement 9). -->",
        '<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ' xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">',
        "</routes>",
        "",
    ]
    return write_text(path, "\n".join(lines))


def emit_sumocfg(config: Config, path: Path, include_base_routes: bool = True,
                 include_base_additional: bool = False) -> Path:
    """Write a SUMO configuration that runs the hospital scenario."""
    ambulances = config.ambulances
    end = float(ambulances.get("end", 3600))
    step = float(config.server.get("step_seconds", 1.0))

    lines = [
        XML_HEADER,
        "<!-- SUMO configuration generated by AssiutHospitals. -->",
        '<sumoConfiguration xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ' xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/sumoConfiguration.xsd">',
        "    <input>",
        '        <net-file value="{0}"/>'.format(_xml_escape(str(config.net_file))),
    ]
    # SUMO accepts a comma separated list of route files (a single option)
    route_files: List[str] = []
    if include_base_routes and config.route_file:
        route_files.append(str(config.route_file))
    route_files.append(str(config.hospital_routes_file))
    lines.append(
        '        <route-files value="{0}"/>'.format(
            _xml_escape(",".join(route_files))
        )
    )
    lines.append(
        '        <additional-files value="{0}"/>'.format(
            _xml_escape(str(config.poi_file))
        )
    )
    if include_base_additional and config.additional_file:
        lines.append(
            '        <additional-files value="{0}"/>'.format(
                _xml_escape(str(config.additional_file))
            )
        )
    lines.append('        <junction-taz value="true"/>')
    lines.append("    </input>")
    lines.append("    <time>")
    lines.append('        <begin value="0"/>')
    lines.append('        <end value="{0:.2f}"/>'.format(end))
    lines.append('        <step-length value="{0:.2f}"/>'.format(step))
    lines.append("    </time>")
    lines.append("    <processing>")
    lines.append('        <ignore-route-errors value="false"/>')
    lines.append("    </processing>")
    lines.append("    <report>")
    lines.append('        <no-step-log value="true"/>')
    lines.append('        <verbose value="false"/>')
    lines.append("    </report>")
    lines.append("</sumoConfiguration>")
    lines.append("")
    return write_text(path, "\n".join(lines))


def emit_network_js(config: Config, network: Network, path: Path) -> Path:
    """Write the road network (lat/lon polylines) for the web map."""
    roads: List[List[List[float]]] = []
    min_lat = min_lon = 90.0
    max_lat = max_lon = -90.0

    for edge in network.normal_edges:
        if len(edge.shape) < 2:
            continue
        polyline: List[List[float]] = []
        for x, y in edge.shape:
            lon, lat = network.to_geo(x, y)
            polyline.append([_round(lat, 6), _round(lon, 6)])
            min_lat = min(min_lat, lat)
            max_lat = max(max_lat, lat)
            min_lon = min(min_lon, lon)
            max_lon = max(max_lon, lon)
        roads.append(polyline)

    payload = {
        "meta": {
            "net_file": str(config.net_file),
            "edge_count": len(roads),
            "junction_count": len(network.junctions),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
        "center": [27.188, 31.1855],
        "bounds": [[min_lat, min_lon], [max_lat, max_lon]],
        "roads": roads,
    }
    text = (
        "/* generated by AssiutHospitals - do not edit by hand */\n"
        "window.ASSIUT_NETWORK = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n"
    )
    return write_text(path, text)


def emit_hospitals_js(dataset: Dataset, path: Path) -> Path:
    """Write the hospital dataset for the web map."""
    payload = {
        "meta": dataset.meta,
        "hospitals": [record.as_dict() for record in dataset.hospitals],
    }
    text = (
        "/* generated by AssiutHospitals - do not edit by hand */\n"
        "window.ASSIUT_HOSPITALS = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n"
    )
    return write_text(path, text)


# ------------------------------------------------------------------------ API
def generate(
    config: Config,
    refresh: bool = False,
    verbose: bool = True,
) -> Dataset:
    """Generate every artefact and return the dataset."""
    config.ensure_dirs()
    network = open_network(config.net_file)

    dataset = build_dataset(config, refresh=refresh, verbose=verbose)

    if verbose:
        print("[3/4] writing SUMO + JSON artefacts")
    emit_empty_routes(config.hospital_routes_file)
    emit_dataset_json(dataset, config.dataset_file)
    emit_poi_xml(dataset, config.poi_file)
    emit_sumocfg(config, config.sumocfg_file)

    if verbose:
        print("[4/4] writing the web map data")
    emit_network_js(config, network, config.network_js)
    emit_hospitals_js(dataset, config.hospitals_js)

    if verbose:
        print()
        print("  dataset   : {0}".format(config.dataset_file))
        print("  POIs      : {0}".format(config.poi_file))
        print("  routes    : {0} (no periodic flows)".format(config.hospital_routes_file))
        print("  sumocfg   : {0}".format(config.sumocfg_file))
        print("  map data  : {0}".format(config.network_js))
        print("             {0}".format(config.hospitals_js))
    return dataset
