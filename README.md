# Assiut emergency dispatch

An emergency-ambulance **dispatch search** built on the real Assiut SUMO road
network. From any valid start point inside the four owner-approved zones, it
returns the fastest suitable hospital, the complete lane-level route, and the
expected free-flow travel time. It also contains a measured comparison of the
seven algorithms selected by the project owner.

An additive **operations-research (OR) extension** plans one day of medical-kit
deliveries and patient transfers across the same four zones. It uses the real
lane-level network, removes prohibited lanes, tracks cumulative ambulance flow
per lane, enforces lane capacities and the 48-ambulance fleet, and keeps the
transportation-tableau methods (NWC, least-cost, VAM, MODI) separate from the
road-capacitated network MILP.

This is a **routing and planning tool**, not a live dispatch centre. It does
not read live hospital capacity, does not model congestion, and does not run a
SUMO simulation. The shipped emergency capacity/specialty data and the OR test
quantities are clearly labelled **SYNTHETIC**.

The project reads the network and base routes from
`D:\Dashboard - Copy\sumo\`; it never writes to that directory.

---

## Quick start

```powershell
# Use the real Python 3.10 interpreter on this machine
$py = "C:\Users\gamer\AppData\Local\Programs\Python\Python310\python.exe"

# 1. Regenerate the dataset, map data and empty SUMO route file
& $py run.py build

# 2. Check the owner-approved zones and capacity configuration
& $py run.py dispatch --check

# 3. Serve the dispatch map (no live stream, no SUMO process)
& $py run.py serve --port 8770
#    open http://127.0.0.1:8770/

# 4. Run the dispatch search from the command line
& $py run.py dispatch --lat 27.1774203 --lon 31.1837216 --specialty burns

# 5. Re-run the measured comparison of all seven algorithms
& $py run.py compare

# 6. Independent Bellman-Ford validation of the search and routes
& $py tools\verify_dispatch.py

# 7. Solve the one-day OR kit/patient plan and write the OR reports
& $py run.py or-plan

# 8. Run the same OR model and print its independent checks without files
& $py run.py or-check

# 9. Independent OR validation, including small exhaustive cases
& $py tools\verify_or.py
```

`python` on this machine's `PATH` is the MSYS2 build; use the explicit
interpreter above. Building, dispatch, comparison and dispatch validation need
only the Python standard library. The OR extension additionally needs
`numpy` and `scipy` (with `scipy.optimize.milp`); the current environment uses
SciPy 1.13.0.

### Commands

| Command | Purpose |
|---|---|
| `run.py build [--refresh]` | Fetch/cache OSM data, snap hospitals, write dataset/POI/map data and an empty route file |
| `run.py serve [--port N] [--open]` | Serve `web/dispatch.html` and the dispatch JSON API |
| `run.py dispatch --check` | Validate zones, capacity and owner policy; print the zone table |
| `run.py dispatch --lat L --lon N --specialty S` | Run the start-zone-only search and print the route |
| `run.py dispatch ... --json` | Print the complete JSON result; exits 1 when there is no suitable hospital |
| `run.py compare` | Measure Dijkstra, A*, Bellman-Ford, VAM, least-cost, NWC and MODI |
| `run.py or-plan [--or-config PATH] [--out-dir DIR] [--json] [--no-write] [--no-routing-comparison]` | Solve the lane-capacitated one-day OR model and write `reports/` by default |
| `run.py or-check [--json]` | Solve the OR model and print every independent constraint without writing files |
| `run.py list` | Print all hospitals with edge, snap distance and routability |
| `run.py info` | Print resolved paths and SUMO environment |
| `tools\verify_dispatch.py` | Independent Dijkstra-vs-Bellman-Ford and route validation |
| `tools\verify_or.py` | Independent OR routing, transportation, MODI, network and small-instance validation |

The old `validate` command and the old live dashboard were removed together
with the 48 periodic ambulance flows. `sumo/hospitals.rou.xml` is intentionally
an empty route file.

---

## Final requirement status

| # | Requirement | Final status |
|---|---|---|
| 1 | Show only the real SUMO network and hospitals at their real coordinates | **Done** in `web/dispatch.html` / `web/dispatch.js` |
| 2 | Four manual zones with manual hospital assignment | **Done**; owner accepted the `11/3/3/9` split on 2026-10-23 |
| 3 | Start anywhere valid; search the zone containing the start | **Done**; `search_scope = start_zone_only` |
| 4 | Per hospital: emergency department, free place, required specialty; skip and continue | **Done**; capacity is SYNTHETIC |
| 5 | Travel time including current congestion | **Resolved by owner decision:** free-flow time only; no congestion code |
| 6 | Return hospital, route and expected time | **Done**; API, CLI and map |
| 7 | Compare the owner-selected algorithms with measured runtime and route time | **Done**; see `reports/algorithm_comparison.md` |
| 8 | Remove the old mismatches | **Done**; old dashboard, TLS display, live stream, filters, hub/dashed lines and 48 flows removed |
| 9 | Working rules: complete files, minimal changes, bilingual comments, no invented data, independent validation | **Followed**; synthetic data is labelled, not presented as real |
| 10 | Simulation study | **Not built**; options are reported separately in [`SIMULATION_OPTIONS.md`](SIMULATION_OPTIONS.md) |

“Resolved” for requirement 5 means the owner explicitly chose free-flow travel
time. No congestion factor is hidden in the code: every response reports
`mode = free_flow` and `congestion_enabled = false`.

### OR extension acceptance

| # | OR requirement | Final status |
|---|---|---|
| 1 | Fixed facts: 25 routable hospitals, 48 ambulances, 4 zones, one-day horizon | **Enforced** by `config/or_planning.json` and the planner |
| 2 | Define sets, parameters, units, variables, constraints and objective before implementation | **Done** in [`OR_MODEL.md`](OR_MODEL.md) |
| 3 | Do not invent real capacities, quantities, demand or road measurements | **Followed**; every such input is labelled `SYNTHETIC` in `data/or_test_data.json` or `config/or_planning.json` |
| 4 | Beds are receiving capacity, not a shipped resource; kits, beds, ambulances and background traffic stay separate | **Enforced** by separate variables, units and checks |
| 5 | Lane-level road representation with real lengths, valid connections, prohibited lanes and documented capacity estimates | **Done**; 387 class-prohibited lanes are removed from every search; capacity is `SYNTHETIC_ESTIMATE` from lane count and road type |
| 6 | Background traffic separate; cumulative ambulance flow on shared lanes | **Done**; lane loads recomputed independently after the solve |
| 7 | Enforce road capacities during optimization and independently afterward; report infeasibility explicitly | **Done**; SciPy/HiGHS MILP plus independent lane-load checks and explicit unmet variables |
| 8 | Review/rebuild four zones, assign every valid location consistently, keep zones configurable and inspectable | **Done**; the owner-approved manual `11/3/3/9` zones are reused, not re-derived |
| 9 | NWC, least-cost, VAM and MODI with forbidden cells, caps and balanced/unbalanced handling | **Done** for the kit-only tableau; forbidden cells, labelled dummies and caps are explicit, the exact tableau MILP checks the result, and standard MODI rejects a binding cap rather than claiming an unbounded optimum |
| 10 | Dijkstra, A* and Bellman-Ford; keep routing comparison separate from allocation comparison | **Done**; report sections are separate |
| 11 | Complete VAM and MODI traces, including penalties, selections, basis/degeneracy, potentials, reduced costs and cycles | **Done** in `reports/or_report.md` and the trace CSVs |
| 12 | Do not claim VAM/MODI are globally optimal for the physical network | **Stated** in the report and model document; the lane-capacitated MILP is separate |
| 13 | Conservation, fleet, prohibited-lane, capacity, integrality, shortages, feasible/infeasible and routing tests | **Done**; `tools/verify_or.py` runs 136 checks |
| 14 | Small-instance exact validation | **Done**; exhaustive enumeration and an independent MILP are compared against VAM/MODI |

---

## How the dispatch search works

1. **Snap the start** to the nearest ambulance-usable lane within **400 m**
   (`origin.max_snap_distance_m`). A point farther away is rejected.
2. **Refuse a dead-end start.** The dispatcher computes the largest strongly
   connected lane component of the class-aware lane graph. If the start cannot
   reach that component, the request fails instead of pretending a route
   exists.
3. **Find the start zone.** The snapped point is looked up in the four manual
   rectangles. If it is outside all four, or on a shared boundary, the request
   is rejected; the dispatcher never chooses a zone automatically.
4. **Run Dijkstra** over the class-aware lane graph, using free-flow time on
   each lane part: `seconds = length_m / speed_mps`.
5. **Evaluate only hospitals listed in that zone.** A hospital is skipped when
   it is not routable, has no emergency department, has zero free places, lacks
   the required specialty, is a clinic (`clinics_as_emergency = false`), or is
   an owner-excluded dead-end destination.
6. **Return the first suitable hospital by travel time**, with the complete lane
   sequence, road edges, length, expected time and search runtime. If no
   hospital in the zone qualifies, the result is empty rather than falling back
   to another zone.

The search is deterministic. Ties are broken by hospital slug.

### Dead ends and excluded destinations

Two facilities snap to a lane with no successors and are excluded as
destinations by owner decision D:

* `asyut-university-hospital`
* `osm-way-94168667`

The mental-health hospital reaches only a small four-lane dead-end component;
its coordinates are also refused as a **start** by owner decision I. The
structural test is based on strongly connected components, not an arbitrary
lane-count threshold.

`osm-way-94168695` is inside the network but **454.81 m** from a road, beyond the
250 m routability limit. It remains visible on the map only.

---

## Zones and emergency capacity

`config/dispatch.json` is the only source of zone boundaries and
hospital-to-zone assignment. The loader validates the file; it never derives an
assignment automatically.

| Zone | Name | Facilities | Routable | Notes |
|---|---|---:|---:|---|
| `Z1` | North-West | 11 | 10 | contains the 454.81 m non-routable map-only way |
| `Z2` | North-East | 3 | 3 | |
| `Z3` | South-West | 3 | 3 | contains both dead-end destinations |
| `Z4` | South-East | 9 | 9 | contains the two clinics |

All **26 in-network** facilities are assigned exactly once. The **3 facilities
outside** the simulated network are intentionally unassigned and are shown on
the map only:

* Abo Teeg Central Hospital
* Nekabet El Moalmen Hospital
* University Dental Hospital

The unequal `11/3/3/9` split is the owner-approved assignment, not a placeholder.

### Capacity data is synthetic

OSM does not publish free emergency beds or specialty lists. The file
`data/emergency_capacity.json` therefore contains **invented test data**:

* `source` and `notice` say `SYNTHETIC`;
* every one of the 29 dataset slugs has an entry;
* `beds_free > 0` is required for selection;
* specialties must be in the catalogue;
* `clinics_as_emergency` is `false`, so the two clinics are never destinations;
* `el-shorta-hospital` deliberately has `beds_free = 0`;
* `asyut-chest-hospital` deliberately lacks `burns`.

The CLI, JSON API and web badge all state that the capacity is synthetic. Replace
the file and its provenance fields before operational use.

---

## Algorithms and measured comparison

The dispatch tool itself uses **Dijkstra** as its baseline. The comparison runs
the seven algorithms selected by the owner:

| Algorithm | Role in this project |
|---|---|
| Dijkstra | Pathfinder and dispatch baseline; class-aware lane graph |
| A* | Pathfinder; multi-target A* with an admissible straight-line-time heuristic |
| Bellman-Ford | Independent pathfinder and reference optimum |
| VAM | Transportation-problem selection method (Vogel approximation) |
| Least-cost | Transportation-problem greedy selection method |
| North-west corner | Transportation-problem initial allocation |
| MODI | MODI (`u-v`) improvement of the north-west-corner solution |

### Important adaptation for the four transportation methods

VAM, least-cost, north-west corner and MODI are **not road pathfinders**. Applying
them directly to a graph would be meaningless. The project uses a small,
explicit transportation model:

* one row per suitable hospital in the start zone;
* row supply = that hospital's free beds;
* column 1 = the one patient (demand `1`); cost = Dijkstra travel time;
* column 2 = a dummy demand that absorbs the remaining beds; dummy cost is higher
  than every real cost.

The row allocated to column 1 is the selected hospital. Its road route and time
come from the Dijkstra cost matrix. This limitation is printed in the comparison
report and is **not** hidden. The Dijkstra matrix time is included in the
measured runtime of these methods, so they are not made to look artificially
fast.

### Latest measured result

Generated by `python run.py compare` on 2026-10-27, 16 cases (four zone origins ×
four specialties). Runtimes are wall-clock measurements on this machine and will
vary between runs.

| Algorithm | Runs | Mean runtime (ms) | Mean route time (s) | Optimal | Verified | Failures |
|---|---:|---:|---:|---:|---:|---:|
| Dijkstra | 16 | 23.340 | 16.587 | 12 | 16 | 0 |
| A* | 16 | 10.757 | 16.587 | 12 | 16 | 0 |
| Bellman-Ford | 16 | 273.468 | 16.587 | 12 | 16 | 0 |
| VAM | 16 | 23.392 | 16.587 | 12 | 16 | 0 |
| Least-cost | 16 | 23.366 | 16.587 | 12 | 16 | 0 |
| North-west corner | 16 | 23.349 | 24.999 | 8 | 16 | 0 |
| MODI | 16 | 23.374 | 16.587 | 12 | 16 | 0 |

“Optimal 12/16” means four cases had no suitable hospital in the start zone; the
algorithms correctly returned no selection there. North-west corner is a
deliberately non-optimising initial method, so its 8/16 and higher mean route
time are expected, not a failure. Every selected route/time was checked against
Bellman-Ford: **0 verification failures**.

Full results, including each origin, specialty, hospital, runtime, route time,
length, edge count and verification message:

* `reports/algorithm_comparison.md`
* `reports/algorithm_comparison.json`

---

## Operations-research extension

The OR layer is additive: it does not change the dispatch search or the
existing hospital dataset. The fixed model and notation are in
[`OR_MODEL.md`](OR_MODEL.md); the inputs are
`config/or_planning.json` and `data/or_test_data.json`.

### Model in brief

* **Hospitals:** the same 25 routable facilities, with the owner-approved
  manual `11/3/3/9` zone assignment.
* **Kit variable:** integer number of 10-kit ambulance trips from an active
  source to a zone anchor.
* **Patient variable:** integer number of patient transfers from a zone anchor
  to a receiving hospital.
* **Fleet variable:** integer vehicles assigned to each zone; total at most 48,
  with one trip per vehicle per day in this conservative model.
* **Beds:** receiving capacity at hospitals, never a shipped commodity.
* **Roads:** a lane-level route for every candidate pair, prohibited lanes
  removed, background flow tracked separately, and
  `background + ambulance <= estimated lane capacity`.
* **Shortages:** explicit unmet kit/patient variables with a large penalty, so
  a shortage is reported instead of hidden.

The standard transportation tableau (NWC, least-cost, VAM, MODI) is solved
separately for kits only. The road-capacitated plan is a SciPy/HiGHS MILP; the
two objectives are deliberately not mixed.

### Latest OR result

The shipped quantities are `SYNTHETIC`; the latest run produced:

| item | value |
|---|---:|
| routable hospitals / zones | 25 / 4 |
| active kit sources | 17 |
| kit supply / demand | 180 / 170 kits |
| unused kit supply / unmet kit demand | 10 / 0 kits |
| patient transfers / usable free beds | 18 / 89 |
| VAM initial `Z0` | 92,553.958 kit-metres |
| MODI final objective | 92,553.958 kit-metres, optimal |
| exact tableau MILP | 92,553.958 kit-metres |
| network MILP status | optimal, solver success |
| demand met | yes, 0 unmet kits and 0 unmet patient transfers |
| vehicles used / fleet | 35 / 48 |
| network objective | 9,888.711 vehicle-metres |
| lane loads above capacity | 0 of 538 active lane loads |

The network objective is **vehicle-metres**, not kit-metres: 9,255.396 for
kit trips plus 633.315 for patient trips. The transportation objectives are
**kit-metres** and are not directly comparable.

The full report includes the cost table, VAM penalties and allocations, MODI
potentials/reduced costs/cycles, fleet and lane tables, routing comparison,
and independent checks:

* `reports/or_report.md`
* `reports/or_plan.json`
* `reports/or_*.csv`
* `reports/or_routes.svg`

### Validation

`python tools\verify_or.py` runs 136 independent checks, including:

* route continuity, prohibited-lane avoidance and lane-load reconstruction;
* lane capacity, fleet, bed, supply, demand and integer-allocation checks;
* VAM trace replay, MODI basis/potential/reduced-cost/cycle replay;
* an exhaustive small-tableau optimum versus MODI and the exact MILP;
* forbidden-cell, binding-cap, shortage, unbalanced and infeasible cases.

Latest result: **136/136 checks pass, 0 failures**.

### Important OR limitations

* All supplies, zone demands, patient transfers, background lane flow and road
  capacities are configurable test values, not measured Assiut data.
* The MILP chooses among one Dijkstra candidate route per source/zone or
  zone/hospital pair. It does not search every possible road path or reroute
  traffic dynamically.
* A zone is represented by one delivery/origin anchor; internal distribution
  inside a zone is not modelled.
* The fleet model is one trip per ambulance per day; shift scheduling and
  multiple trips are out of scope.
* MODI optimality applies only to the kit-only tableau. It is not a proof of
  global optimality for the road-capacitated network.
* The network MILP's `optimal` status is optimal for the stated integer model
  and objective, not for every possible operational objective.

---

## Validation performed

### Dispatch and route validation

`python tools\verify_dispatch.py`:

* recomputes shortest times with Bellman-Ford on the same class-aware lane graph;
* compares every Dijkstra lane distance;
* checks the start-zone-only search against the independent winner;
* checks route endpoints, continuity, emergency permission and re-summed time;
* checks that clinics and excluded destinations are never selected;
* checks that a known dead-end start is refused.

Latest result:

```
origins: 4, specialties: general, burns, cardiac
lane distances: 1,402 lanes, max delta 0.00e+00 s at each origin
checks: 39  failures: 0
RESULT: PASS
```

### Algorithm validation

`python run.py compare`:

* compares Dijkstra, A* and Bellman-Ford results with the independent optimum;
* verifies every selected hospital's route time against Bellman-Ford;
* verifies every route's continuity and emergency permission;
* makes the command exit 1 on any failure.

Latest result: **0 failures** across all 16 cases and all seven algorithms.

### OR validation

`python tools\verify_or.py` independently rebuilds the network view, replays the
VAM and MODI traces, recomputes lane loads, and compares small tableaux with
exhaustive enumeration and an independent exact MILP.

Latest result:

```
checks : 136
passed : 136
failed : 0
RESULT: PASS
```

The separate `run.py or-check` command prints the network constraint checks
without writing files. `run.py or-plan` exits 1 when the plan is infeasible or
leaves demand unmet, and its report distinguishes a feasible plan from a proof
of optimality for every real-world objective.

### Data audit

The build regenerated `data/hospitals.json`, `web/network.js`,
`web/hospitals.js`, `sumo/hospitals.poi.xml`, `sumo/hospitals.rou.xml` and
`sumo/hospitals.sumocfg`. The generated map data contains no traffic-light
layer, no ambulance hubs, no dashed station lines and no periodic flows. The
route file contains zero `<flow>` elements. All source and generated text files
are UTF-8 **without BOM**.

---

## HTTP API

`run.py serve` serves only static files and the dispatch API:

| Endpoint | Meaning |
|---|---|
| `GET /` or `/dispatch.html` | Dispatch map |
| `GET /api/dispatch?lat=..&lon=..&specialty=..` | Dispatch result with route geometry |
| `GET /api/dispatch/meta` | Specialty catalogue, capacity source, policy and config errors |
| `GET /api/hospitals` | Generated hospital dataset |
| `GET /api/network` | Generated network geometry |

There is no `/events` stream, no `/api/state` endpoint and no background SUMO
process.

Errors are returned as `{"error": "..."}` with HTTP 400 (invalid request or
dispatch policy failure) or 503 (dispatcher not initialised). The old dashboard
files `index.html`, `app.js` and `style.css` no longer exist.

---

## Project layout

```
D:\AssiutHospitals
├── run.py                      CLI: build | serve | dispatch | compare | or-plan | or-check | list | info
├── config.json                 paths and network settings
├── config/dispatch.json        owner-approved zones, policy, exclusions, algorithms
├── config/or_planning.json     OR fleet, kit units, capacity estimate, MIP settings
├── OR_MODEL.md                 OR sets, variables, constraints, objective, assumptions
├── README.md                   this user manual
├── PROCESS.md                  the complete engineering build log
├── SIMULATION_OPTIONS.md       options report only; no simulation was built
├── assiut_hospitals/
│   ├── dispatch.py             start-zone-only Dijkstra search + route reconstruction
│   ├── dispatch_config.py      manual zone/capacity/policy loader and validator
│   ├── algorithms.py           A*, Bellman-Ford, transportation methods
│   ├── compare.py              measured comparison and report writer
│   ├── capacity.py             SYNTHETIC capacity loader
│   ├── netmodel.py             net.xml parser, lane graph, SCC/dead-end helpers
│   ├── traveltime.py           free-flow time model
│   ├── server.py               static HTTP server + dispatch API
│   ├── or_config.py            OR rule/test-data loader and validation
│   ├── or_router.py            lane-level router: Dijkstra, A*, Bellman-Ford
│   ├── or_transport.py         NWC, least-cost, VAM, exact transportation MILP
│   ├── or_modi.py              MODI basis/potential/cycle iterations
│   ├── or_network.py           lane-capacitated fleet/kit/patient MILP
│   ├── or_planning.py          end-to-end OR pipeline and validation
│   ├── or_report.py            OR Markdown/JSON/CSV/SVG reports
│   └── ...                     projection, snapping, Overpass, dataset, emit
├── data/
│   ├── osm_hospitals_raw.json  cached Overpass response
│   ├── hospitals.json          generated dataset (29 facilities)
│   ├── emergency_capacity.json SYNTHETIC beds/specialties
│   └── or_test_data.json       SYNTHETIC kit supply, demand, anchors, background
├── sumo/
│   ├── hospitals.poi.xml       SUMO POI markers
│   ├── hospitals.rou.xml       empty: 48 periodic flows removed
│   └── hospitals.sumocfg       SUMO configuration
├── web/
│   ├── dispatch.html           the only dashboard
│   ├── dispatch.js             map + dispatch UI
│   ├── network.js              generated road geometry
│   ├── hospitals.js            generated hospital dataset
│   └── vendor/                 vendored Leaflet 1.9.4
├── reports/
│   ├── algorithm_comparison.md / .json
│   ├── or_report.md            full OR report
│   ├── or_plan.json            machine-readable OR plan
│   ├── or_*.csv                OR tables, traces, flows, lane loads, checks
│   └── or_routes.svg           selected-route sketch
└── tools/
    ├── verify_dispatch.py      independent Bellman-Ford dispatch validation
    └── verify_or.py            independent OR routing/tableau/network validation
```

---

## Limits and deliberate non-goals

* **Synthetic capacity/specialty values.** Real bed counts and specialty lists
  must replace `data/emergency_capacity.json`.
* **Free-flow time only.** No congestion, signal delay, queue or incident model.
* **No live data.** No bed feed, no call queue, no priority pre-emption.
* **No simulation study.** The old live stream and periodic flows were removed.
  See `SIMULATION_OPTIONS.md` for the requested options report.
* **Start-zone-only.** If the start zone has no suitable hospital, the result is
  empty; the tool does not search another zone.
* **Dead-end starts are refused.** No fake route is produced.
* **Outside-network hospitals are map-only.** They cannot be selected.
* **Zone-boundary ambiguity is rejected.** The dispatcher does not guess.
* **Transportation methods are selection methods.** Their routes come from the
  Dijkstra matrix; this is stated in every report.
* **OR inputs are synthetic.** Replace `data/or_test_data.json` and the road
  capacity estimate in `config/or_planning.json` before operational use.
* **OR paths are candidate paths.** The network MILP chooses flows over one
  Dijkstra route per pair; it does not re-optimise the path set or dynamic
  traffic.
* **OR costs use snapped access points.** Entrance/walking offsets are not
  added; two distinct facilities can share a snapped point and therefore show
  zero road distance between their access points.
* **OR zones use one anchor each.** Internal delivery points inside a zone are
  not modelled.
* **OR MODI is not a network optimum.** MODI is optimal only for the kit-only
  transportation tableau; road capacity and the fleet are in the separate MILP.
* **OR fleet scheduling is simplified.** The model assumes one trip per
  ambulance per day and does not model shifts, refuelling or multiple trips.
* **OR fleet accounting uses the demand zone.** Kit trips are charged to the
  destination zone and patient transfers to the origin zone; empty
  repositioning and return legs are not modelled.

Engineering history, discarded designs, bugs and fixes are documented in
[`PROCESS.md`](PROCESS.md).
