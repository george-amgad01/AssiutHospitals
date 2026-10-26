# Architecture summary (final state)

## Overview
- Purpose: Start-zone-only emergency dispatch on the real Assiut SUMO network. Given a start point, find the nearest suitable hospital in the start zone by fastest free-flow travel time, return a lane-level route and expected time. Compare 7 algorithms (measured). 
- Additive OR extension: one-day, lane-capacitated kit/patient planning over the same four zones, with a 48-ambulance fleet, VAM/MODI tableau traces, and an independent verifier.
- Not a simulation/live system. No TraCI, no live capacity, no congestion model. Emergency capacity/specialties and OR test quantities are **SYNTHETIC**.
- Reads from `D:\Dashboard - Copy\sumo\` (network/base routes) but never writes there. All outputs live in this repo.
- Web UI is `web/dispatch.html/js` (Leaflet). Server is static + dispatch API only.

## High-level architecture
Layers:
1. **Configuration** (`config.json`, `config/dispatch.json`) - paths, projection, zones (manual), policy (search_scope, exclusions, clinics, cost), algorithms, owner decisions.
2. **Network model** (`netmodel.py`) - parse `net.xml`, build class-aware lane graph, compute SCC for dead-end detection, provide connectivity/reachability helpers.
3. **Data sources** (`overpass.py`, `hospitals.py`, `dataset.py`, `emergency_capacity.json`) - fetch/cache OSM healthcare, normalize/deduplicate, snap to network, attach synthetic capacity/specialties.
4. **Geospatial/projection & snapping** (`projection.py`, `snapping.py`) - UTM36N<->WGS84 helpers, class-aware nearest-usable-lane snapping with distance limits.
5. **Routing/time** (`traveltime.py`) - free-flow time per lane/edge (length/speed). No congestion.
6. **Dispatch engine** (`dispatch_config.py`, `capacity.py`, `dispatch.py`) - zone lookup, origin validation (snap + SCC dead-end refusal), candidate evaluation (suitability/order), Dijkstra search on lane graph, route reconstruction/verification.
7. **Algorithms & comparison** (`algorithms.py`, `compare.py`) - A*, Bellman-Ford, and transportation selection (VAM/least-cost/NWC/MODI) adapted with Dijkstra matrix; measurement and reports.
8. **Build/emit** (`emit.py`) - write dataset/POI/empty routes/map JS for web; no flows/TLS/hubs/ambulance metadata.
9. **Server/UI** (`server.py`, `web/*`) - static server serving dispatch page and JSON APIs (`/api/dispatch`, `/api/dispatch/meta`, `/api/hospitals`, `/api/network`).
10. **CLI/validation** (`run.py`, `tools/verify_dispatch.py`) - commands for build/serve/dispatch/compare/list/info and independent Bellman-Ford validation.
11. **OR configuration/data** (`or_config.py`, `config/or_planning.json`, `data/or_test_data.json`) - fleet/kit/capacity rules separate from clearly labelled synthetic test quantities.
12. **OR routing/tableau/network** (`or_router.py`, `or_transport.py`, `or_modi.py`, `or_network.py`, `or_planning.py`) - lane-level Dijkstra/A*/Bellman-Ford, NWC/least-cost/VAM/MODI, exact tableau MILP, and lane/fleet-capacitated network MILP.
13. **OR reports/validation** (`or_report.py`, `tools/verify_or.py`) - Markdown/JSON/CSV/SVG artifacts and independent trace/network/small-instance checks.

## Data flow (dispatch)
1. Client sends `lat/lon/specialty` to `/api/dispatch` (or CLI `run.py dispatch`).
2. Load config/dispatch/capacity/dataset/network.
3. Snap origin to nearest emergency-usable lane within 400m; if fails -> error.
4. Check origin not on dead-end component via SCC (must reach main component) else refuse.
5. Find start zone containing point (manual rectangles). If outside or boundary-ambiguous -> reject. Else search only that zone.
6. Run Dijkstra from origin on class-aware lane graph (free-flow). Compute distances/offsets/predecessors.
7. Evaluate hospitals in zone in time order: skip excluded, not routable, no route, no ED, no free beds, missing specialty, clinics excluded. First suitable = optimal.
8. Reconstruct lane-level route, verify, attach geometry/metadata, return JSON/CLI output.

## Data flow (OR)
1. Load `config/or_planning.json`, `data/or_test_data.json`, the existing hospital dataset, manual zones, synthetic capacity and network.
2. Build hospital roles: active kit sources need outgoing routes; patient destinations need emergency status, free beds and incoming reachability. Report exclusions.
3. Build lane-level Dijkstra matrices for active source -> zone anchor and zone anchor -> patient destination. Unreachable pairs stay unavailable.
4. Build the kit-only balanced transportation table; solve NWC/least-cost/VAM, apply MODI, and compare with an exact tableau MILP.
5. Build the network MILP over candidate lane routes with integer kit/patient/ambulance variables, explicit unmet variables, bed/supply/demand/fleet constraints, and lane capacities.
6. Recompute lane loads and physical checks independently; write Markdown/JSON/CSV/SVG reports.
7. `tools\verify_or.py` repeats routing, trace, network and small-instance checks independently.

## File-by-file description

### Root
- `run.py` - CLI entry point. Commands: `build`, `serve`, `dispatch` (with `--check`, `--json`), `compare`, `or-plan`, `or-check`, `list`, `info`. Removes old `validate` command. JSON dispatch exits 1 if no optimal; OR commands exit nonzero on infeasible/unmet plans.
- `config.json` - Base paths (network/net/route/additional/sumo), projection (UTM36N), Overpass mirrors/cache, snapping limits, server settings. (Old ambulance/live settings remain unused.)
- `README.md` - User manual: quick start, requirement status, dispatch behavior, zones/capacity (synthetic), algorithms/comparison, OR extension, validation, API, layout, limits. References `SIMULATION_OPTIONS.md` and `OR_MODEL.md`.
- `OR_MODEL.md` - Complete OR sets, units, parameters, variables, constraints, objective, assumptions, data provenance and reporting requirements.
- `PROCESS.md` - Engineering build log (historical + Parts III/IV final state). Documents decisions, bugs, algorithms, removals, OR implementation, results and final verification.
- `SIMULATION_OPTIONS.md` - Options report only (A-D) with prerequisites; no simulation built.
- `ARCHITECTURE_SUMMARY.md` - This file.

### config/
- `config/dispatch.json` - Owner-approved policy: 4 zones (11/3/3/9), manual assignment, `search_scope=start_zone_only`, `clinics_as_emergency=false`, excluded destinations, origin snap/refuse-dead-end, free-flow cost, 7 algorithms, owner decisions A-L.
- `config/or_planning.json` - OR rules: 48 fleet, 10 kits/trip, one trip/day, 12 h shift, 24 h horizon, zone anchors, explicit prohibited lanes, `SYNTHETIC_ESTIMATE` lane capacity, MIP settings and output directory.

### assiut_hospitals/ (core library)
- `__init__.py` - Package exports (version/config helpers as used).
- `bootstrap.py` - SUMO_HOME/sys.path bootstrap if needed.
- `config.py` - Load/resolve `config.json`, project paths, defaults.
- `projection.py` - UTM zone 36N coordinate transforms WGS84<->local.
- `netmodel.py` - Parse `net.xml` into `Network`/`Edge`/`Lane`/`Junction`. Build `LaneGraph` (adjacency by lane with permissions/length/speed). Parse traffic lights (stored but not displayed). `main_component(vehicle_class)` does iterative Kosaraju SCC and caches largest component for dead-end detection. Helpers for reachability, lane coords.
- `snapping.py` - `Snapper` finds nearest emergency-usable lane within `max_snap_distance_m` (400m for origin). Class-aware and geometry-aware.
- `overpass.py` - Overpass API client with mirrors, caching to `data/osm_hospitals_raw.json`, retries/timeouts.
- `hospitals.py` - Normalize OSM healthcare elements to `Hospital` objects, deduplicate.
- `dataset.py` - `HospitalRecord`/`Dataset`. Build from hospitals + snaps; `as_dict()` produces final dataset (no `ambulance` hub metadata). Save/load JSON.
- `emit.py` - Writers: `emit_dataset`, `emit_pois` (SUMO POI), `emit_empty_routes` (writes empty `<routes>` with comment), `emit_sumocfg`, `emit_web` writes `web/network.js` and `web/hospitals.js`. Removes old TLS/hub/flow code.
- `dispatch_config.py` - Load/validate `config/dispatch.json`. Define `Zone`, `DispatchConfig`. `zones_for_point()` finds containing rectangles (reject outside/boundary ambiguous). `excluded_reason()`. Validates counts, assignments, scope, algorithm list, free-flow policy.
- `capacity.py` - Load `data/emergency_capacity.json` (SYNTHETIC). Validate entries, provide `effective_emergency()`, `beds_free`, `specialties`. Enforces `clinics_as_emergency`.
- `traveltime.py` - `TimeModel` computes free-flow lane/edge times (length/speed). No congestion hooks active.
- `algorithms.py` - Pathfinding: `dijkstra_from_origin`, `bellman_ford`, `astar_to_targets` (multi-target A* with admissible straight-line/max-speed heuristic, same-lane-ahead/entry targets, safe stop). Transportation: `transport_select()` with `nwc/least_cost/vam/modi` over Dijkstra cost matrix (dummy demand) selecting hospital; MODI with basis handling/property tested.
- `compare.py` - Run measured comparison across 4 origins × 4 specialties for all 7 algorithms. Verify routes against Bellman-Ford, check continuity/emergency permission. Write `reports/algorithm_comparison.md` and `.json`. Includes explanation of transportation-method caveat.
- `dispatch.py` - Core engine. `Dispatcher` loads network/graph/dataset/capacity/dispatch config. `search()` snaps origin, refuses dead-end starts via SCC, finds start zone, runs Dijkstra, evaluates candidates in order, reconstructs route, verifies. Returns `DispatchResult` with `search_scope/search_zone`, candidates, optimal, route. Exits/returns per policy.
- `server.py` - Static HTTP server (stdlib). Serves `web/` files, maps `/` and `/index.html` to `dispatch.html`. API: `GET /api/dispatch` (lat/lon/specialty), `GET /api/dispatch/meta`, `GET /api/hospitals`, `GET /api/network`. JSON errors. No SSE/live/simulation endpoints.
- `or_config.py` - Load/validate OR rules and synthetic test data; road-capacity estimate from lane count and road type; no invented fallback values.
- `or_router.py` - State-layer lane router with Dijkstra, A* and Bellman-Ford; excludes class-prohibited and explicit lanes; handles source lane offsets and target points.
- `or_transport.py` - `TransportProblem`/`BalancedProblem`, labelled dummy row/column, allocation helpers, NWC, least-cost, VAM, exact SciPy transportation MILP, conservation checks and cell caps.
- `or_modi.py` - MODI basis construction, degeneracy zero-basics, potentials, reduced costs, BFS adjustment cycles, optimality iterations, and method comparison. Explicitly rejects binding caps.
- `or_network.py` - Lane-incidence network MILP: integer kit trips, patient transfers, zone fleet variables, unmet variables, supply/demand/bed/fleet constraints, lane capacities, selected flows, lane loads and independent checks.
- `or_planning.py` - End-to-end preparation, manual zone roles, routing matrices, transport solve, network solve, routing comparison, validation and warnings.
- `or_report.py` - Deterministic Markdown/JSON/CSV/SVG writer, including VAM/MODI traces, cost table, network flows and lane loads.

### data/
- `osm_hospitals_raw.json` - Cached Overpass response.
- `hospitals.json` - Generated dataset (29 hospitals/clinics). Fields: name/slug/category/coords/address/tags, `in_network`, `routable`, `snap{edge_id,pos,distance_m,lat,lon}`, zone assignment (or unassigned), capacity summary context. No ambulance hub/traffic metadata.
- `emergency_capacity.json` - SYNTHETIC emergency capacity/specialties per slug (source/notice marked SYNTHETIC). `beds_free`, `emergency_department`, `specialties`. Two clinics present but treated as non-emergency by policy.
- `or_test_data.json` - SYNTHETIC OR kit supply, zone kit/patient demand, real-hospital anchors, zero background flow, source/notice and explicit synthetic choices. Replace before operational use.

### sumo/
- `hospitals.poi.xml` - SUMO POI markers for hospitals (SUMO visualization artifact).
- `hospitals.rou.xml` - Empty routes file. Contains comment that periodic flows removed; zero `<flow>` elements.
- `hospitals.sumocfg` - Generated SUMO config referencing base network/routes and POIs (not used by dispatch server).

### web/
- `dispatch.html` - Dispatch UI: map container, sidebar (origin/specialty/algorithm metadata), results, policy notes. Only dashboard.
- `dispatch.js` - Leaflet map (dark tiles), draws real road network from `network.js`, draws hospitals from `hospitals.js`, handles click-to-set origin, calls `/api/dispatch`, renders route/metadata (shows start-zone-only, synthetic badge, policy notes).
- `network.js` - Generated road geometry (polylines) for the real network. No traffic lights.
- `hospitals.js` - Generated hospital dataset for map markers/popups.
- `vendor/` - Leaflet 1.9.4 CSS/JS and images.

### tools/
- `verify_dispatch.py` - Independent validation: Dijkstra vs Bellman-Ford on 1,402 lanes (max delta 0), start-zone-only checks, route continuity/emergency permission/endpoint/time, clinic/exclusion checks, dead-end start refusal. 39 checks, 0 failures.
- `verify_or.py` - Independent OR validation: Bellman-Ford route matrices, forbidden/capacity checks, VAM trace replay, MODI basis/potential/reduced-cost/cycle replay, network lane/fleet/bed/demand checks, exact small-instance enumeration, binding-cap/shortage/infeasible cases. 136 checks, 0 failures.

### reports/
- `algorithm_comparison.md` / `.json` - Measured comparison of all 7 dispatch algorithms with per-case results, caveats about transportation methods, verification.
- `or_report.md` / `or_plan.json` - Human and machine OR reports, including model rules, cost table, VAM/MODI traces, network plan, routing comparison, checks and limitations.
- `or_*.csv` - Hospital roles, zones, cost table, VAM/MODI traces, transport/routing comparisons, selected flows, lane loads and checks.
- `or_routes.svg` - Schematic of the selected kit/patient routes and hospital roles.

## Key policies/behaviors
- **Zones**: 4 manual rectangles, 11/3/3/9, no automatic assignment. Search only start zone.
- **Dead ends**: SCC on lane graph; start must reach main component (1220 lanes) else refused. Destinations `asyut-university-hospital`, `osm-way-94168667` excluded.
- **Clinics**: `clinics_as_emergency=false` -> never emergency destinations.
- **Cost**: Free-flow only (length/speed). `congestion_enabled=false`.
- **Snap**: 400m max for origin. Hospitals: `osm-way-94168695` 454.81m from road -> routable=false (map-only). 3 outside-network hospitals map-only.
- **Transport methods**: Selection only via Dijkstra cost matrix + dummy demand; routes from Dijkstra. Runtime includes matrix time; documented.
- **OR spaces**: 25 routable hospitals, manual `11/3/3/9` zones, 17 active kit sources, 19 patient destinations, 48-vehicle fleet, one trip per vehicle/day.
- **OR resources**: Kits are shipped; free beds are receiving capacity. Background lane flow is separate from ambulance flow. All quantities are synthetic/test values.
- **OR roads**: Lane-level directed paths; 387 class-prohibited lanes removed; lane capacities `SYNTHETIC_ESTIMATE`; every selected route is assigned to every traversed lane and checked independently.
- **OR tableau vs network**: NWC/least-cost/VAM/MODI solve only the kit tableau. Binding cell caps are rejected by standard MODI; the exact tableau MILP handles them. The separate network MILP enforces roads/fleet/beds and reports unmet demand explicitly.
- **OR fleet accounting**: One trip per vehicle/day; kit trips are charged to the destination zone and patient transfers to the origin zone. Empty repositioning and return legs are not modelled.
- **OR access points**: Costs use snapped lane access points; entrance/walking offsets are not added. Facilities sharing a snapped point can have zero modelled road distance.
- **OR path scope**: One Dijkstra candidate route per source/zone and zone/hospital pair; the MILP selects flows over those candidates, not all possible paths.
- **No old artifacts**: Old dashboard files deleted, no SSE/live endpoints, no 48 flows, no TLS/hub metadata in generated data.

## Validation (current)
- `run.py dispatch --check`: PASS
- `run.py compare`: 0 failures (16 cases × 7)
- `tools/verify_dispatch.py`: 39 checks, 0 failures, max lane delta 0.00e+00s
- `run.py or-check`: physical checks pass; demand met; 35/48 vehicles; 0 lanes over capacity
- `tools/verify_or.py`: 136 checks, 0 failures

## How to run
```powershell
$py = "C:\Users\gamer\AppData\Local\Programs\Python\Python310\python.exe"
& $py run.py build
& $py run.py dispatch --check
& $py run.py serve --port 8770
& $py run.py dispatch --lat 27.1774203 --lon 31.1837216 --specialty burns
& $py run.py compare
& $py tools\verify_dispatch.py
& $py run.py or-plan
& $py run.py or-check
& $py tools\verify_or.py
```
(Use explicit interpreter on this machine.)
