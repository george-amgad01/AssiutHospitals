# Assiut Hospitals — the complete build log

This document is the **engineering narrative** of how `D:\AssiutHospitals` was
built: what was investigated, which assumptions were tested, which designs were
tried and discarded, which bugs were found, and why the final architecture looks
the way it does.

It is deliberately more detailed than `README.md`. The README tells you *how to
use* the project; this file tells you *how it came to exist* — including the
dead ends, so that nobody has to walk them again.

* Project: `D:\AssiutHospitals`
* Source network: `D:\Dashboard - Copy\sumo\`
* SUMO 1.26 (`C:\Program Files (x86)\Eclipse\Sumo`), Python 3.10
* Original map stage: **29 hospitals, 26 in-network, 25 routable**
* Final dispatch stage: **start-zone-only search, four owner-approved zones,
  seven compared algorithms, 39/39 validation checks, 0 algorithm-comparison
  failures**
* Removed by owner decision: old dashboard, live stream, traffic-light display,
  hub/dashed lines, UI filters and the 48 periodic ambulance flows
* Requirement 5 is resolved as **free-flow only**; no congestion code is active
* Requirement 10 is **not built**; options are in
  [`SIMULATION_OPTIONS.md`](SIMULATION_OPTIONS.md)

> **Historical note.** Sections 1-19 and the early Part II phases record how the
> original map and the first dispatch prototype were built. Several details in
> those sections (48 flows, the live stream, the old dashboard, the old
> all-zone search and the placeholder zones) were later removed or replaced by
> the owner decisions. **Part III at the end of this document is the
> authoritative final state.**

---

## Table of contents

1. [The goal and the hard constraints](#1-the-goal-and-the-hard-constraints)
2. [Phase 1 — reconnaissance of the existing dashboard](#2-phase-1--reconnaissance-of-the-existing-dashboard)
3. [Phase 2 — the network model](#3-phase-2--the-network-model)
4. [Phase 3 — coordinate systems and projection](#4-phase-3--coordinate-systems-and-projection)
5. [Phase 4 — the hospital data (OSM / Overpass)](#5-phase-4--the-hospital-data-osm--overpass)
6. [Phase 5 — snapping hospitals onto roads](#6-phase-5--snapping-hospitals-onto-roads)
7. [Phase 6 — choosing the routing mechanism](#7-phase-6--choosing-the-routing-mechanism)
8. [Phase 7 — routability, attempt #1: junctions and TAZ](#8-phase-7--routability-attempt-1-junctions-and-taz)
9. [Phase 8 — routability, attempt #2: edge-to-edge flows](#9-phase-8--routability-attempt-2-edge-to-edge-flows)
10. [Phase 9 — the lane-level rewrite and the vehicle-class bug](#10-phase-9--the-lane-level-rewrite-and-the-vehicle-class-bug)
11. [Phase 10 — hub selection done right](#11-phase-10--hub-selection-done-right)
12. [Phase 11 — the SUMO/TraCI runtime bugs](#12-phase-11--the-sumotraci-runtime-bugs)
13. [Phase 12 — the map](#13-phase-12--the-map)
14. [Phase 13 — validation](#14-phase-13--validation)
15. [Final results](#15-final-results)
16. [Complete bug and fix log](#16-complete-bug-and-fix-log)
17. [Design decisions and why](#17-design-decisions-and-why)
18. [Known limitations](#18-known-limitations)
19. [How to reproduce every step](#19-how-to-reproduce-every-step)
20. [Part II — the emergency dispatch extension](#20-part-ii--the-emergency-dispatch-extension)
21. [Phase 14 — requirement 1: the minimal map](#21-phase-14--requirement-1-the-minimal-map)
22. [Phase 15 — requirement 2: the manual zones](#22-phase-15--requirement-2-the-manual-zones)
23. [Phase 16 — requirements 3 and 4: capacity and the search](#23-phase-16--requirements-3-and-4-capacity-and-the-search)
24. [Phase 17 — independent validation](#24-phase-17--independent-validation)
25. [Phase 18 — API and UI wiring](#25-phase-18--api-and-ui-wiring)
26. [Phase 19 — requirement 5: the congestion design (not implemented)](#26-phase-19--requirement-5-the-congestion-design-not-implemented)
27. [Pending owner decisions](#27-pending-owner-decisions)
28. [Dispatch bug and issue log](#28-dispatch-bug-and-issue-log)
29. [Appendix A — all 29 hospitals](#appendix-a--all-29-hospitals)
30. [Appendix B — the nine traffic lights](#appendix-b--the-nine-traffic-lights)
31. [Appendix C — file map](#appendix-c--file-map)
32. [Appendix D — dispatch data contract](#appendix-d--dispatch-data-contract)
33. [Part III — final dispatch completion](#33-part-iii--final-dispatch-completion)
34. [Phase 20 — owner decisions A-L](#34-phase-20--owner-decisions-a-l)
35. [Phase 21 — dead ends and start refusal](#35-phase-21--dead-ends-and-start-refusal)
36. [Phase 22 — start-zone-only search](#36-phase-22--start-zone-only-search)
37. [Phase 23 — the seven algorithms](#37-phase-23--the-seven-algorithms)
38. [Phase 24 — measured comparison](#38-phase-24--measured-comparison)
39. [Phase 25 — removing the old mismatches](#39-phase-25--removing-the-old-mismatches)
40. [Phase 26 — final verification](#40-phase-26--final-verification)
41. [Phase 27 — final bug and issue log](#41-phase-27--final-bug-and-issue-log)
42. [Phase 28 — final state and limitations](#42-phase-28--final-state-and-limitations)

---

## 1. The goal and the hard constraints

The request was: **build a new standalone project containing a map of all
hospitals in Assiut city, built on the SUMO network/routes of the existing
dashboard, with ambulances routed to/from the hospital locations.**

The original scope was deliberately limited to *map + hospital-routed
ambulances*. A later request (Part II, section 20) added an on-demand
**dispatch search**: given a point, find the fastest suitable hospital. The
project is still not a live dispatch centre: there is no call generator, no
live capacity feed, no priority pre-emption and no operational deployment.

Four constraints shaped almost every decision:

| # | Constraint | Consequence |
|---|---|---|
| 1 | Must **read**, not copy, the network and routes from `D:\Dashboard - Copy` | All paths are absolute in `config.json`; the project can be deleted/rebuilt without touching the dashboard |
| 2 | No `PYTHONPATH` setup allowed | `bootstrap.py` injects `%SUMO_HOME%\tools` into `sys.path` at import time |
| 3 | `PyQtWebEngine` is **not installed anywhere** | No desktop window; the map is a browser page served over HTTP |
| 4 | All generated XML/JSON must be **UTF-8 without BOM** | Never use PowerShell `Set-Content -Encoding UTF8` (it writes a BOM); all writes go through one helper |

Constraint 2 is worth a note: on this machine `python` on `PATH` is the MSYS2
build (no `pip`, no SUMO packages), while the real interpreter is
`C:\Users\gamer\AppData\Local\Programs\Python\Python310\python.exe`, which has
`traci`. Everything is therefore invoked as
`"C:\...\Python310\python.exe" D:\AssiutHospitals\run.py ...`.

Constraint 4 bit early: the first version of the build script wrote JSON from
PowerShell and every file started with `EF BB BF`. That breaks `json.load` in
some tools and makes SUMO's XML parser unhappy. It was replaced with a single
`write_text()` helper:

```python
def write_text(path, text):
    """Write UTF-8 text *without* a byte order mark."""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
```

Every artefact (dataset, POI file, route file, sumocfg, map JS) goes through
it. A final audit of all 30 source + generated text files found **zero BOMs**.

---

## 2. Phase 1 — reconnaissance of the existing dashboard

Before writing a line of the new project, the existing dashboard was inventoried.

### 2.1 What the dashboard contains

```
D:\Dashboard - Copy\
├── sumo\
│   ├── Version 3 George.net.xml          the network  (4,153 edge elements)
│   ├── project (1).rou.xml               base traffic  (contains the emergency vType)
│   ├── project (2).sumocfg               SUMO config
│   └── project (2).add.xml               additional file
├── web\
│   └── assiut_map.html                   reference UI (Leaflet, dark theme, 9 TLS)
└── simulation\
    └── mappo_optimized_4.py              RL controller (not used by this project)
```

### 2.2 Two copies of the same data

There is a second copy under `D:\DeafCommPlatform - Copy\network\` +
`D:\DeafCommPlatform - Copy\routes\`. Both the network file and
`project (1).rou.xml` were compared byte-for-byte and are **identical**. The
`D:\Dashboard - Copy` copy was chosen as the source of truth because it is the
one referenced by the dashboard's own config.

### 2.3 What the network file actually is

`Version 3 George.net.xml` is a plain SUMO net file produced by `netconvert`.
It is **not** an OSM file and it contains **no `<geometry>` elements** — the
road geometry exists only as `shape="x,y x,y ..."` attributes on edges and
lanes. That single fact determined how the map layer had to be generated.

Counts (verified by parsing):

| Element | Count |
|---|---|
| `<junction>` | 1,296 (757 normal + 539 internal) |
| `<edge>` | 4,153 (1,268 normal + 2,885 internal) |
| lanes on normal edges | 1,700 |
| `<connection>` | 6,069 |
| `<tlLogic>` | 14 entries → **9 distinct ids** (some have 4 programs) |
| `<tl>` | 9 |

The network covers Assiut city only. Its bounding box is
roughly `27.1707 … 27.2037 N`, `31.1605 … 31.2022 E`.

Road composition of the 1,268 normal edges:

| type | count |
|---|---|
| `highway.residential` | 589 |
| `highway.tertiary` | 205 |
| `highway.secondary` | 185 |
| `highway.service` | 97 |
| `highway.primary` | 84 |
| *(no type)* | 55 |
| `highway.footway` | 25 |
| `highway.steps` | 11 |
| links + others | 17 |

### 2.4 The traffic-light trap

The nine lights have **two different id spaces**:

* the net file's junction ids are `tls_1`, `tls_2`, `TLS_3` … `TLS_9`
  (note the inconsistent casing!),
* the TraCI/`tlLogic` ids are the OSM-derived names
  (`5716218813`, `cluster_5716218908_5716218909`, …).

Sumo's `tlLogic` id is what TraCI reports, so the map needs the OSM names, but
the *position* of a light must be taken from its junction, and a junction id is
not simply derivable from the `tlLogic` id. The mapping was recovered from the
`<connection tl="...">` elements plus the `intLanes` attribute of each junction:

1. build `internal lane -> (normal) junction` from every junction's `intLanes`,
   preferring non-internal junctions,
2. for every `<connection>` with a `tl` attribute, look up `via` in that map,
3. the result is `tlLogic id -> junction id`.

> **Bug found here:** the first version also accepted *internal* junctions as
> fallbacks, which produced duplicate entries — the light
> `cluster_13387024595_...` appeared three times (once for `TLS_8`, once for
> `:TLS_8_13_0`, once for `:TLS_8_15_0`). The map therefore showed **11**
> traffic lights instead of 9. The fix was to key the result by `tlLogic` id and
> let a real junction always win over an internal one. Verified: exactly 9.

The nine lights are: **Kobry1, Kobry2, Mahkama, Mahmoud Rashwan, Gomharia,
El Nemis, City, El Hilaly, Kairo** (see Appendix B).

---

## 3. Phase 2 — the network model

Rather than depend on `sumolib` (which would add another `PYTHONPATH` /
`SUMO_HOME` dependency and is comparatively slow to import), the project ships
its own `net.xml` parser — **stdlib only**:

```
assiut_hospitals/netmodel.py
├── NetProjection      UTM 36N <-> SUMO local
├── Junction           id, x, y, type, incLanes, intLanes
├── Edge               id, from/to, type, function, shape, lane permissions
├── TrafficLight       OSM id, junction, programs, phases
├── LaneGraph          lane-level routing graph (see Phase 9)
└── Network            the container + open_network()
```

### 3.1 Vehicle-class permissions

SUMO's lane permission semantics are subtle and were verified empirically
against this network:

* if `allow` **is present**, the lane is usable *only* by the listed classes
  (or by `all`),
* if `allow` is **absent**, the lane is usable unless the vehicle class is in
  `disallow`.

Consequence, which matters a lot: `allow="passenger"` does **not** permit an
ambulance (`vClass="emergency"`). `disallow="passenger"` likewise does not
block it.

In this network:

| | count |
|---|---|
| normal edges | 1,268 |
| edges **not** usable by `emergency` on lane 0 | **133** |
| … of which `highway.service` | 97 |
| … of which `highway.footway` | 25 |
| … of which `highway.steps` | 11 |
| edges with an `allow` attribute | 133 |
| edges with a `disallow` attribute | 1,080 |

So roughly **10 % of the roads cannot be used by an ambulance at all**. They are
mostly footpaths, stairs, and — critically — the internal service roads of the
university campus, which are tagged
`allow="pedestrian delivery bicycle"`. That detail becomes the central plot
point of Phase 9.

### 3.2 Why not sumolib

`sumolib` would have been the obvious choice, but:

* it is another thing that must be on `sys.path` (see constraint 2),
* parsing `net.xml` directly is ~30 lines and gives exact control over
  permission handling,
* the project also needs `shape` attributes as raw coordinate tuples, which
  `sumolib` hides behind geometry objects.

The parser reads the file once (~0.2 s for this network) and caches everything
in memory.

---

## 4. Phase 3 — coordinate systems and projection

Three coordinate spaces are in play:

1. **WGS84 lon/lat** — what OSM gives us,
2. **UTM zone 36N metres** — what the net's `projParameter` says,
3. **SUMO local metres** — what the net file's `x` / `y` attributes use.

The net file declares:

```xml
<location netOffset="-317785.18,-3006446.53"
          projParameter="+proj=utm +zone=36 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
          .../>
```

so

```
local = UTM36N + netOffset
```

`pyproj` is not installed, so the UTM conversion was implemented from scratch
in `projection.py` using the standard Krüger series (the same equations
`pyproj`/`proj` use for Transverse Mercator), with:

* central meridian 15° E for zone 36,
* scale factor k₀ = 0.9996,
* false easting 500,000 m, false northing 0 (northern hemisphere),
* WGS84 ellipsoid constants.

### 4.1 Validation

The implementation was checked against an independent reference on all nine
traffic-light coordinates **and** on the network corners:

```
max error over 9 TLS: 0.06 m
```

That is well below the 1–2 m of noise in OSM node positions, so the projection
is not the limiting factor anywhere in the pipeline.

> **Bug found here (later):** the HTTP server originally converted vehicle
> positions with `lonlat_to_utm(x, y)`, i.e. it treated *local* network metres
> as if they were *lon/lat degrees*. Every vehicle on the live map was plotted
> somewhere in the Atlantic. The fix was to call `network.to_geo(x, y)`, which
> runs local → UTM → lon/lat. This was caught by comparing the streamed
> coordinates with the hospital coordinates (both should be ≈ 27.18 N,
> 31.18 E).

---

## 5. Phase 4 — the hospital data (OSM / Overpass)

### 5.1 Source query

All healthcare POIs of the **Asyut governorate** were requested from Overpass
using the area relation `3603726184`:

```
[out:json][timeout:90];
area(3603726184)->.a;
(
  node["amenity"~"^(hospital|clinic)$"](area.a);
  way ["amenity"~"^(hospital|clinic)$"](area.a);
  node["healthcare"](area.a);
  way ["healthcare"](area.a);
);
out center tags;
```

### 5.2 The mirror problem

`overpass-api.de` answered **HTTP 406 Not Acceptable** for this query (it
dislikes certain query shapes without an explicit `Accept` header, and was
rate-limiting too). Several mirrors were tried; the one that worked reliably
was:

```
https://maps.mail.ru/osm/tools/overpass/api/interpreter
```

`overpass.py` therefore keeps an ordered list of mirrors and falls through on
failure. The answer is cached in `data/osm_hospitals_raw.json`, so the build is
fully reproducible offline; `--refresh` is required to re-download.

### 5.3 The raw data

```
30 elements = 25 nodes + 5 ways
28 × amenity=hospital
 2 × amenity=clinic
 1 × emergency=yes
```

### 5.4 De-duplication

Two OSM nodes describe the same building:

```
node/14078009201  27.1774203, 31.1837216   مستشفى أسيوط العام
node/14078010101  27.1774218, 31.1837077   مستشفى أسيوط العام
```

They are **≈1.4 m apart** (0.0000139° longitude at this latitude). The
de-duplicator (`hospitals.dedupe`, radius 30 m) merges records whose display
names are identical and which lie within 30 m of each other. When two records
compete, it prefers the one with **more OSM tags**, then the lower OSM key — so
for this pair node `14078009201` survives and `14078010101` is recorded in its
`merged_from` list.

```
30 raw  ->  29 facilities
```

### 5.5 Naming

Arabic OSM names are kept verbatim. For each facility the dataset carries:

* `name` — exactly as mapped (may be Arabic or English),
* `name_en` — a transliteration / English name when available,
* `name_ar` — the Arabic name,
* `display_name` — the best label for the UI (English when known),
* `slug` — a stable ASCII identifier (`el-shorta-hospital`) used for flow ids
  and DOM keys. Arabic names that have no Latin form get a slug derived from
  the OSM type/id (`osm-way-94168667`), because SUMO flow ids must be ASCII.

Total: **27 hospitals + 2 clinics**, 29 records.

---

## 6. Phase 5 — snapping hospitals onto roads

Each hospital's lon/lat is projected into SUMO local coordinates and projected
onto the closest point of every road edge. That sounds trivial; it is not,
because of three traps.

### Trap 1 — geometry lives in `shape` attributes

As established in Phase 2, there are no `<geometry>` elements. `snapping.py`
therefore iterates `edge.shape` segments and does point-to-segment projection in
local metres, tracking the distance along the edge (`pos`) so that the result can
later be used as `arrivalPos` / `departPos`.

### Trap 2 — ambulances may not use every road

A hospital next to a footpath would otherwise be "snapped" onto a road no
ambulance can drive on. The snapper is therefore **vehicle-class aware**:

```
candidates = edges whose lane 0 allows the vehicle class
fallback   = if nothing usable within 400 m, any edge
threshold  = 250 m (snapping.max_snap_distance_m)
```

> **Concrete case:** `Essam El Shrief El Tkasosy Hospital` is 51 m from
> `820440648`, a `highway.service` edge with
> `allow="pedestrian delivery bicycle"` (51 m long, 1 lane). Snapping it there
> would have produced an unroutable hospital. The class-aware snapper instead
> picked `97405586#3` at **14.0 m** — a normal tertiary road.

### Trap 3 — permissions can be per lane

The check is done per lane index. For the hub edges the generator records the
**first usable lane index**, because SUMO's `departLane` / `arrivalLane` are
lane indices, not booleans.

### Result

```
29 hospitals: 26 inside the network, 3 outside
25 routable, 4 not
```

The three outside are genuinely outside the simulated area:

| hospital | distance to nearest road |
|---|---|
| Abo Teeg Central Hospital | 17,182.7 m |
| University Dental Hospital | 11,021.0 m |
| Nekabet El Moalmen Hospital | 870.3 m |

The fourth is inside but far from any road:

| hospital | distance | why no |
|---|---|---|
| Unnamed hospital (OSM way/94168695) | 454.8 m | exceeds the 250 m snap threshold |

These four are still written to the dataset, still get a POI marker on the map,
and are drawn in grey — the map is a *map of all hospitals*, not only of the
serviceable ones.

---

## 7. Phase 6 — choosing the routing mechanism

"Routable" hides two separate questions, and they were answered separately:

1. **Geometric** — which road edge is this hospital actually on? (Phase 5.)
2. **Topological** — can an ambulance legally drive from one edge to another?

For question 2 there were three candidate mechanisms:

| mechanism | verdict |
|---|---|
| an adjacency graph over **edges** | rejected on paper: SUMO routes on **lanes**, so an edge graph over-approximates. Two edges can be "connected" (some `<connection>` exists) while the lane a vehicle is actually in cannot reach the lane the route needs. Turn-only lanes and lane permissions are exactly the information a projection throws away. |
| `<flow fromJunction=… toJunction=…>` | implemented first — see Phase 7 |
| `<flow from="<edge>" to="<edge>">` | implemented second and kept — see Phase 8 |

The implementation therefore settled on a **lane-level** graph — the same
granularity SUMO itself uses — rather than an edge-level one. That decision
looked merely tidy at the time; Phase 9 shows that it was the only reason the
project could find the real bug at all.

---

## 8. Phase 7 — routability, attempt #1: junctions and TAZ

The first mechanism that was actually built used junction-to-junction flows:

```xml
<flow id="amb_in_el-shorta-hospital" fromJunction="J17" toJunction="J20"/>
```

with `<junction-taz value="true"/>` in the sumocfg so that junctions could be
used as traffic assignment zones.

This failed for a reason that is obvious in hindsight and that no amount of
validation would have fixed: **`fromJunction` lets SUMO pick a random outgoing
edge at the junction**. If the junction has four outgoing edges, three of them
may be the wrong way. Vehicles departed in the wrong direction, hit dead ends,
teleported, and never reached the hospital.

Also discovered along the way:

* `toEdge` / `fromEdge` are **not valid attributes** of a SUMO route file
  (they exist only in other contexts), so the "obvious" fix was not available.
* `<junction-taz value="true"/>` is required for `toJunction` to work at all —
  and note that a `toJunction` sink must have **incoming** edges, while a
  `fromJunction` source must have **outgoing** ones. Of the 18 configured
  junctions, `J24` has no incoming edge and had to be filtered out, leaving
  **17** usable origins.

That left the third mechanism, which is the one that survived.

---

## 9. Phase 8 — routability, attempt #2: edge-to-edge flows

SUMO flows support `from="<edge>"` and `to="<edge>"` with explicit positions:

```xml
<flow id="amb_in_el-shorta-hospital" type="emergency"
      begin="0.00" end="3600.00" period="600.00" color="220,30,30"
      from="94168920#2" departLane="3" departPos="0.00"
      to="601421695#2" arrivalLane="0" arrivalPos="36.94"/>
```

This is deterministic: the origin edge and the destination edge are fixed, and
SUMO computes the exact lane-accurate route between them. No random edge choice,
no dead ends.

Two details that were needed to make it work in practice:

1. **Positions must be strictly inside the edge.** The hospital's snap position
   can be exactly at the edge end (e.g. `pos = 952.44` on a `952.44 m` edge).
   SUMO rejects `arrivalPos` equal to the length, so every position is clamped:

   ```python
   pos = min(record.snap.pos, max(edge_length - 0.5, 0.0))
   ```

2. **Lane indices must be explicit.** With `departLane` / `arrivalLane` left at
   their defaults, SUMO picks a lane by its own "best lane" heuristic, which
   may be a lane without an outgoing connection at the next junction. Setting
   the *first usable* lane index makes insertion deterministic.

At this point the scenario ran — but six hospitals were skipped because no hub
edge could be found, and one flow still failed with
`has no valid route`. That last error is the subject of Phase 9.

---

## 10. Phase 9 — the lane-level rewrite and the vehicle-class bug

This was the hardest part of the project and deserves a full account.

### 10.1 The symptom

One generated flow was rejected by SUMO:

```
Error: Vehicle 'amb_out_el-shorta-hospital.0' has no valid route.
```

The flow was an ordinary edge-to-edge flow of the form

```xml
<flow id="amb_out_&lt;hospital&gt;" type="emergency"
      from="&lt;hub edge&gt;" departPos="..." to="&lt;hospital edge&gt;" arrivalPos="..."/>
```

Rerunning SUMO standalone with several `departPos` / `arrivalPos` combinations
(`0/0`, `0/end`, `end/0`, `mid/mid`) produced the same error every time, which
ruled the positions out. Meanwhile a hand-written lane-level BFS reported that a
path *did* exist — dozens of lane-to-lane hops across the city.

So: "the path exists" but "SUMO disagrees". Something in the model was wrong.

### 10.2 The debugging path

The shortest way to find the disagreement was to dump every edge on the BFS
path together with its lane permissions:

```
601421695#2   highway.primary     allow=(none)                        emergency OK
601421695#3   highway.primary     allow=(none)                        emergency OK
...
701132859#0   highway.secondary   allow=(none)                        emergency OK
94169015#0    highway.service     allow=pedestrian delivery bicycle   NOT OK
94169015#1    highway.service     allow=pedestrian delivery bicycle   NOT OK
...
```

There it was. The BFS route cut through the **university campus service roads**
`94169015#0 … #7`, which are `highway.service` with
`allow="pedestrian delivery bicycle"`. An ambulance is not in that list, so
SUMO's router — which *does* honour vehicle-class permissions — refused the
route. My lane graph had been built from `<connection>` elements alone and had
no idea that permissions existed.

This also explains why the failure looked position-independent, why it only
affected certain hospitals, and why the reverse direction worked (it used a
different one-way sequence of edges).

### 10.3 The fix: a lane graph that knows about vehicles

`LaneGraph` was rewritten to be class-aware:

```python
lane_info[lane_id] = (edge_id, lane_index)      # authoritative, from `<lane index=..>`

def lane_allowed(lane_id, vehicle_class):
    edge_id, index = lane_info[lane_id]
    return network.edges[edge_id].allows_class(vehicle_class, lane_index=index)

def reachable_lanes(start_edges, vehicle_class): ...
def reverse_reachable_lanes(target_edges, vehicle_class): ...
def route_exists(source, target, vehicle_class): ...
```

Every BFS edge is filtered through `lane_allowed`. Lanes that an ambulance may
not use are simply not traversable, which is exactly what SUMO does.

The lane graph is built from the 6,069 `<connection>` elements and contains
5,004 lane nodes (including internal lanes) — so it is cheap to build and
exact.

> **Side note on turn restrictions:** before blaming permissions, the
> connection *states* were audited to rule out turn restrictions as the cause.
> In this network the states are only `M` (4,310), `m` (1,559), `=` (103),
> `O` (47), `o` (50) — i.e. all permissive. Turn restrictions were **not** the
> problem. This mattered: it would have been easy to spend hours on the wrong
> hypothesis.

### 10.4 The immediate effect

After the rewrite, SUMO ran clean (`exit 0`) — but **7 hospitals were skipped**
instead of 6, because the stricter check rejected more of the naive hub choices.
That was expected: the class-aware graph is *correct*, and it exposed that hub
selection itself was too narrow. That is Phase 10.

---

## 11. Phase 10 — hub selection done right

A "hub" is the city edge an ambulance starts from (inbound) or drives to
(outbound). The original implementation only considered the **outgoing edges of
the 17 configured ambulance-station junctions**, and required that the edge be
routable in both directions.

That was too strict, and it is why hospitals were being skipped. Two examples
from the diagnostics:

| hospital | edges that can reach it | why no hub |
|---|---|---|
| El Shorta (edge `601421695#2`) | only 8 | the valid hubs are upstream on a 37 m primary stub — none of them belongs to a configured junction |
| Dar El Shefaa (edge `601637232#13`) | 1,033 | it is reachable from everywhere, but its 13 reachable successors never include a station edge |

### 11.1 The algorithm that replaced it

Per hospital, two BFS runs on the class-aware lane graph:

```
forward  = reachable_lanes([hospital_edge], cls)          # where can we go?
backward = reverse_reachable_lanes([hospital_edge], cls)  # who can reach us?
```

Then:

* **inbound** candidate = an edge with a usable lane in `backward`
  (an ambulance can start there and reach the hospital),
* **outbound** candidate = an edge with a usable lane in `forward`
  (an ambulance can leave the hospital and reach that edge),
* **round trip** candidate = an edge in both sets; this is preferred because
  it makes the two flows meet at a single station.

Ranking of candidates, in order:

1. edges belonging to a configured ambulance-station junction (tier 0),
2. any other edge (tier 1),
3. inside a tier: the shortest straight-line distance to the hospital.

Tier 1 is the fallback that unblocked the last hospitals: when no station edge
can reach a hospital, the ambulance uses the nearest road that can, rather than
the hospital being dropped from the simulation.

### 11.2 The dead-end discovery

Two hospitals — `Asyut University Hospital` and
`Unnamed hospital (way/94168667)` — both snap to the end of
`701132859#4`, a **952.44 m** secondary road. Inspecting the connections showed
that its single lane has **no successors at all**:

```
701132859#4_0  ->  (nothing)
```

It is a genuine dead end in the source network (the road into the campus simply
stops). SUMO has no reversing; an ambulance can enter but can never leave.

The generator therefore emits **inbound only** for those two, and records
`ambulance.inbound = true, ambulance.outbound = false` in the dataset. The map
shows them in orange ("arrival only"), and the validator only requires the
directions that were actually emitted.

This is an honest limitation of the source network, not a bug in this project.

### 11.3 Result

```
29 hospitals, 25 routable
48 flows = 25 inbound + 23 outbound
0 hospitals skipped
```

---

## 12. Phase 11 — the SUMO/TraCI runtime bugs

With the routes correct, the next layer of problems was the *runtime*: starting
SUMO, talking to it, and getting numbers out of it. Five bugs, all of them
silent-failure-shaped.

### 12.1 `--remote-addr` is not a SUMO option

The first `validate` run died instantly:

```
Error: On processing option '--remote-addr':
       No option with the name 'remote-addr' exists.
```

Removed. TraCI connects to `localhost` by default; only `--remote-port` is
needed.

### 12.2 `traci.connect()` without a label silently breaks every domain

This one is nasty. This code *appears* to work:

```python
traci.connect(port, numRetries=1)          # returns a Connection object
traci.simulationStep()                     # FatalTraCIError: Not connected.
```

The reason is in `traci/main.py`: `connect()` only registers the connection in
the domain pool when it is given a **label**. Without a label the connection
object is returned but `traci.simulation`, `traci.vehicle`, … keep pointing at
nothing.

Fix:

```python
traci.connect(port, numRetries=1, host="localhost", label="assiu-hospital")
traci.switch("assiu-hospital")
```

and a careful `close()` that also removes the label from
`connection._connections`, otherwise the second `connect()` in the same process
raises `Connection '<label>' is already active`.

### 12.3 SUMO's stdout pipe fills up and blocks the simulation

The scenario was launched with `stdout=subprocess.PIPE`. SUMO emits a lot of
traffic-light warnings for this network (the source `.net.xml` has genuinely
malformed TLS programs — "Missing yellow phase", "Unsafe green phase", …). The
OS pipe buffer is 64 KB on Windows. Once it filled, **SUMO blocked on write**
and stopped answering TraCI: no error, no timeout, just a hang on the first
`simulationStep()`.

That is why a hand-written test that redirected SUMO's output to a *file*
worked instantly while the same step through `Scenario` hung forever.

Fix: redirect stdout/stderr to `sumo/sumo-run.log` and read that file when a
diagnostic is needed.

### 12.4 Wrong TraCI method names

The TraCI API had changed since the code was drafted:

| used | correct |
|---|---|
| `simulation.getRunningNumber()` | *(does not exist)* |
| `simulation.getDepartedVehicleIDs()` | `simulation.getDepartedIDList()` |
| `simulation.getArrivedVehicleIDs()` | `simulation.getArrivedIDList()` |

### 12.5 Per-step counters presented as totals

`getDepartedNumber()`, `getArrivedNumber()` and `getLoadedNumber()` are
**per-step** values, not cumulative totals. The live map was showing
"arrived: 0, inserted: 2" while hundreds of vehicles were running.

Measured behaviour (120 steps, step length 1 s):

```
t=  0  idlist= 34  loaded=48  departed=34  arrived=0
t= 20  idlist= 84  loaded= 2  departed= 3  arrived=0
t= 40  idlist=121  loaded= 4  departed= 7  arrived=2
```

`loaded` is clearly *inserted this step*, not *currently loaded*.

Fix: `Scenario.step()` now accumulates the per-step deltas itself, and
`stats.running` is `len(vehicle.getIDList())`. After the fix the live stream
reports a monotone story (inserted 905 → 948, arrived 449 → 514, running
456 → 434).

### 12.6 The lon/lat bug

Already described in Phase 3: the server was running local metres through
`lonlat_to_utm()`. Fixed by using `network.to_geo()`, and the network object is
now cached instead of being re-parsed on every publish (it used to be re-read
from disk for every animation frame).

---

## 13. Phase 12 — the map

### 13.1 Why a browser page

`PyQtWebEngine` is not installed on any of the available interpreters, so a
desktop window was off the table from the start. The map is a static page served
by a stdlib HTTP server, with the live simulation streamed over
**Server-Sent Events**.

Choosing SSE over WebSockets was pragmatic: `http.server` cannot do WebSockets
without a third-party library, while SSE is just a long-lived `GET` with
`text/event-stream` and works out of the box.

### 13.2 Data hand-off

The map does not call TraCI. The build writes two plain JavaScript globals:

```
web/network.js    window.ASSIUT_NETWORK  = { meta, center, bounds, roads, trafficLights }
web/hospitals.js  window.ASSIUT_HOSPITALS = { meta, hospitals }
```

* `roads` is an array of `[[lat, lon], ...]` polylines (one per normal edge),
  generated from the `shape` attributes — 1,268 polylines.
* `trafficLights` is `[{id, junction, label, lat, lon}]` — 9 entries.
* each hospital carries its `snap` and an `ambulance` block with the hub edges,
  their geo positions, and the hospital's own snapped geo position, so the map
  can draw the dashed station→hospital route without any extra request.

This makes `web/` usable as a **static** map: `?static=1` renders everything
and never opens the event stream.

### 13.3 Leaflet, vendored

Leaflet 1.9.4 (`leaflet.js`, `leaflet.css`, marker images) is vendored under
`web/vendor/` so the map works without a CDN. Only the CARTO dark basemap tiles
are fetched from the internet, and if they fail the road network and the
hospitals are still drawn on a dark canvas.

### 13.4 Rendering approach

* 1,268 road polylines are drawn with `preferCanvas: true` into Leaflet's canvas
  renderer (SVG would create ~30k DOM nodes and stutter).
* one extra "main roads" layer redraws only the edges with more than six shape
  points (i.e. the long, curved arterials) slightly thicker, which makes the
  street hierarchy readable at city zoom.
* hospitals use `L.divIcon` (a rotated teardrop), colour-coded by state:
  red = in+out, orange = arrival only, grey = outside the network.
* ambulance stations are small purple dots; the dashed line from station to
  hospital is drawn per hospital.
* the 9 traffic lights are small squares whose CSS class follows the streamed
  `state` string (TraCI's `getRedYellowGreenState()`): `r` → red,
  `y` → yellow, anything else → green.
* live ambulances are blue dots, keyed by vehicle id, updated in place on every
  SSE message and removed when the vehicle disappears from the stream.

### 13.5 Side panel

* 4 stat tiles (hospitals / routable / ambulances / arrived),
* filter chips: All, Routable, Arrival only, Not routable,
* a search box that matches English *and* Arabic names (both are concatenated
  into one lowercase haystack),
* a list sorted routable → arrival-only → blocked, then alphabetically,
* clicking an entry pans/zooms and opens the popup; clicking a marker selects
  the list entry.

### 13.6 Verifying a map you cannot see

The browser integration in this environment is not available, so the map was
verified in two independent ways:

1. **A headless smoke test** (`tools/smoketest_map.js`, Node) stubs just enough
   of Leaflet and the DOM to execute `network.js` + `hospitals.js` + `app.js`
   for real. It asserts the data contracts and exercises `applyState()` with a
   synthetic SSE payload.
2. **Headless Chrome** (`--headless=new --dump-dom --virtual-time-budget`)
   renders the page and the resulting DOM is inspected:

   ```
   leaflet-pane count    : 7
   hospital-marker count : 29
   tls-marker count      : 9
   hub-marker count      : 25
   list item rows        : 29
   canvas present        : True
   stat-hospitals        : 29
   stat-routable         : 25
   ```

   (`--screenshot` also produces a 1600×1000 PNG; it was verified to be
   non-empty, 185 KB.)

The live stream itself was verified separately by reading `/events` with
`urllib` and checking that each event contains vehicles with plausible
coordinates (27.18 N / 31.18 E), 9 traffic lights, and cumulative stats.

---

## 14. Phase 13 — validation

Validation is deliberately end-to-end rather than a file check: the real SUMO
scenario is started, every ambulance is watched, and a hospital counts as
served only if an ambulance **arrives on its snapped edge** and (when an
outbound flow exists) **departs from it**.

Implementation details worth noting:

* the simulation is stepped **one second at a time**, because
  `getArrivedIDList()` only reports the *last* step's arrivals — stepping 10 s
  at a time was silently losing 90 % of them;
* a vehicle's route is captured at **departure** and remembered until the
  vehicle arrives, because `vehicle.getRoute()` no longer works once the vehicle
  has left the network;
* only `amb_*` vehicles are tracked, so base-traffic vehicles that happen to
  drive over a hospital edge cannot inflate the numbers;
* the expectation is taken from the dataset (`ambulance.inbound` /
  `ambulance.outbound`), so the two dead-end hospitals are not falsely reported
  as failures.

Final report (1800 s of simulated time):

```
simulated 1800.0 s in 36.7 s wall clock
vehicles arrived: 144
hospitals served: 25/25
RESULT: PASS
```

Every one of the 25 routable hospitals received either 3 or 6 ambulance
arrivals within the 1800 s window; 23 of them also recorded 3 or 6 departures.
The two dead-end hospitals show arrivals but `out=0`, exactly as designed.

`data/validation.json` holds the machine-readable report
(`ok: true`, `counts: {total: 29, routable: 25, served: 25}`, `errors: []`).

---

## 15. Final results of the original map stage (superseded)

> This is a historical snapshot from before the owner decisions. The 48 flows,
> the live stream, `data/validation.json` and the all-zone search were later
> removed or replaced. See Part III for the final authoritative state.

```
Hospitals
  raw OSM elements ................ 30  (25 nodes, 5 ways)
  after de-duplication ............ 29  (27 hospitals, 2 clinics)
  inside the SUMO network ......... 26
  outside .........................  3
  routable ........................ 25

Ambulance flows
  inbound ......................... 25
  outbound ........................ 23
  total ........................... 48
  hospitals with no flow ..........  0
  hospitals with arrival only .....  2  (dead-end campus road)

Network
  normal edges .................... 1,268
  lanes ........................... 1,700
  lane-graph connections .......... 6,069
  edges unusable by an ambulance ... 133  (97 service, 25 footway, 11 steps)
  traffic lights ..................  9

Validation (1800 s)
  hospitals served ................ 25 / 25
  ambulances arrived .............. 144
  result .......................... PASS

Dispatch extension (requirements 1-4)
  zones ........................... 4  (PLACEHOLDER split 11/3/3/9)
  in-network hospitals assigned ... 26
  outside, not assigned ...........  3
  capacity ........................ SYNTHETIC
  search .......................... Dijkstra, free-flow cost
  independent validation .......... 192 checks, 0 failures
  congestion (requirement 5) ...... NOT implemented, design pending
```

---

## 16. Complete bug and fix log

Everything that broke, in the order it broke, with the root cause.

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | JSON files unreadable / SUMO XML errors | PowerShell `Set-Content -Encoding UTF8` writes a BOM | one `write_text()` helper, `encoding="utf-8", newline="\n"` |
| 2 | `<poi>` file rejected | malformed `<poi>` element | rewritten POI emitter |
| 3 | SUMO: duplicate option `--route-files` | two `<route-files>` elements written | comma-separated list in a single element |
| 4 | `toJunction` vehicle dead-ends | junction has no incoming edges | `J24` filtered from origins (17 remain) |
| 5 | hospital on a footpath, unroutable | snapper ignored vehicle class | class-aware `Snapper` + `max_unusable_distance_m=400` |
| 6 | vehicle teleports all over the city | `fromJunction` picks a **random** outgoing edge | replaced by deterministic `from="edge"` / `to="edge"` flows |
| 7 | `toEdge` / `fromEdge` rejected | not valid route-file attributes | (design change, see #6) |
| 8 | 6 hospitals skipped | hub restricted to station edges | forward/reverse lane reachability + tier-1 fallback |
| 9 | `Vehicle ... has no valid route` | lane BFS ignored `allow`/`disallow` — path crossed `allow="pedestrian delivery bicycle"` campus roads | vehicle-class-aware `LaneGraph` |
| 10 | `--remote-addr` rejected | not a SUMO 1.26 option | removed |
| 11 | `FatalTraCIError: Not connected` on every command | `traci.connect()` without a label does not register the connection in the domain pool | `label=` + `traci.switch()` |
| 12 | first `simulationStep()` hangs forever | SUMO's stdout `PIPE` (64 KB) filled with TLS warnings and blocked | redirect to `sumo/sumo-run.log` |
| 13 | `getRunningNumber` attribute error | method does not exist in this TraCI version | `len(vehicle.getIDList())` |
| 14 | arrivals never counted | `getArrivedIDList()` is per-step, loop stepped 10 s at a time | step 1 s at a time |
| 15 | `getDepartedVehicleIDs` attribute error | renamed in TraCI | `getDepartedIDList()` / `getArrivedIDList()` |
| 16 | live stats "arrived: 0" while vehicles ran | per-step counters used as totals | accumulate in `Scenario.step()` |
| 17 | vehicles plotted in the Atlantic | local metres passed through `lonlat_to_utm()` | `network.to_geo(x, y)` + cached network |
| 18 | 11 traffic lights instead of 9 | internal junctions accepted as TLS fallbacks → duplicates | key by `tlLogic` id, prefer real junction |
| 19 | `arrivalPos` == edge length rejected | snap point at the very end of an edge | clamp to `edge_length - 0.5` |
| 20 | 2 hospitals "fail" validation | dead-end campus road, no outbound possible | per-direction expectations from the dataset |

---

## 17. Design decisions and why

| Decision | Alternative | Why this one |
|---|---|---|
| Own `net.xml` parser | `sumolib` | stdlib only, no extra `sys.path` entry, exact control over lane permissions, raw `shape` access |
| Pure-Python UTM 36N | `pyproj` | not installed; the implementation was validated to 0.06 m so nothing is lost |
| Edge-to-edge `<flow>` | `fromJunction`/`toJunction` | deterministic; junctions pick a random outgoing edge |
| Lane-level routability | edge-level reachability | matches how SUMO actually routes; the edge-level version produced routes SUMO rejects |
| Class-aware lane graph | plain lane graph | 133 of 1,268 edges are unusable by an ambulance; ignoring that is the bug from Phase 9 |
| Fixed flow period (600 s) | exponential arrivals | deterministic ⇒ reproducible validation |
| Tier-0/tier-1 hub ranking | all edges | keeps the "ambulance station" semantics while still serving every hospital |
| Stdlib HTTP + SSE | Flask + WebSockets | zero dependencies; SSE is a plain long-lived GET |
| Vendored Leaflet | CDN | works offline, version-pinned |
| Canvas renderer | SVG | ~1,268 polylines would create tens of thousands of SVG nodes |
| `preferCanvas` + 2 polyline layers | per-road layers | one layer per road is 1,268 Leaflet objects and janky to zoom |

### Why the `emergency` vType is reused, not redefined

`project (1).rou.xml` already defines a `vType id="emergency"`. Defining it
again in `hospitals.rou.xml` would be a duplicate-id error in SUMO (both files
are loaded together). The emitter therefore only writes a `vType` when it is
missing from the base file.

### Why the ambulance flows use a dedicated colour

`color="220,30,30"` on every flow, which SUMO applies per vehicle — the map gets
red-ish ambulances in the SUMO GUI and blue dots in the web map (the web map
uses its own palette because it also streams the *base* emergency vehicles).

---

## 18. Known limitations

1. **Two hospitals cannot be left.** `Asyut University Hospital` and
   `Unnamed hospital (way/94168667)` snap to the tip of `701132859#4`, a
   952 m dead-end road. SUMO cannot turn a vehicle around, so only arrival
   flows exist. Fixing this requires changing the *source network* (adding a
   turnaround), which is out of scope for a project that must not modify the
   dashboard data.
2. **Three hospitals are outside the simulated area** and can never be served:
   Abo Teeg Central Hospital (17.2 km), University Dental Hospital (11.0 km),
   Nekabet El Moalmen Hospital (0.87 km).
3. **One hospital is inside but too far from any road** (454.8 m > the 250 m
   snap threshold): `Unnamed hospital (OSM way/94168695)`.
4. **The ambulance flows are synthetic.** They are a routing demonstration, not
   a real dispatch schedule: no incident generation, no priority rules. The
   separate dispatch search uses capacity data, but it does not create SUMO
   trips.
5. **Snapping is nearest-edge.** A hospital whose entrance is on the opposite
   side of a dual carriageway may be snapped to the wrong direction (SUMO
   cannot cross the median either, so this is consistent, but it can make a
   route longer than reality).
6. **The network is a 2023-era OSM extract.** New roads or hospitals since then
   are not present; re-running `build --refresh` only refreshes the hospital
   POIs, not the network.
7. **The basemap needs internet.** Tiles come from CARTO; everything else is
   local.
8. **Dispatch zones are placeholders** (quadrants, split 11/3/3/9), not the
   owner-approved four zones. See Part II, section 22.
9. **Dispatch capacity is SYNTHETIC.** No bed/specialty value is real. See
   section 23.1.
10. **Dispatch cost is free-flow.** Congestion (requirement 5) is designed on
    paper only. See section 26.
11. **The dispatch route is not a SUMO trip.** It is verified on the lane
    graph, but SUMO's own router has not executed it.
12. **A dead-end start has a tiny reachable set.** The mental-health road
    reaches four lanes; the university hospital may reach only its own edge.
    The behaviour is an open decision (I).

---

## 19. How to reproduce every step

```powershell
$py = "C:\Users\gamer\AppData\Local\Programs\Python\Python310\python.exe"

# 1. build (uses the cached Overpass answer)
& $py D:\AssiutHospitals\run.py build

# 1b. build and re-download the OSM data
& $py D:\AssiutHospitals\run.py build --refresh

# 2. run SUMO standalone and look for errors
& "C:\Program Files (x86)\Eclipse\Sumo\bin\sumo.exe" `
    -c D:\AssiutHospitals\sumo\hospitals.sumocfg --end 900 --no-step-log true

# 3. validate (spawns SUMO through TraCI)
& $py D:\AssiutHospitals\run.py validate --duration 1800 --json

# 4. inspect the data
& $py D:\AssiutHospitals\run.py list
& $py D:\AssiutHospitals\run.py info

# 5. map, live
& $py D:\AssiutHospitals\run.py serve --port 8770
#    -> http://127.0.0.1:8770/

# 6. map, static
& $py D:\AssiutHospitals\run.py serve --port 8770 --no-live
#    -> http://127.0.0.1:8770/?static=1

# 7. JS smoke test (needs Node)
node D:\AssiutHospitals\tools\smoketest_map.js

# 8. dispatch configuration check (zones + capacity)
& $py D:\AssiutHospitals\run.py dispatch --check

# 9. one dispatch query (human-readable)
& $py D:\AssiutHospitals\run.py dispatch --lat 27.1774203 --lon 31.1837216 --specialty burns

# 10. the same query as JSON
& $py D:\AssiutHospitals\run.py dispatch --lat 27.1774203 --lon 31.1837216 --specialty burns --json

# 11. independent Bellman-Ford validation (4 origins x 9 specialties)
& $py D:\AssiutHospitals\tools\verify_dispatch.py --specialties general,trauma,burns,cardiac,stroke,pediatric,obstetric,orthopedic,toxicology

# 12. dispatch map
#     -> http://127.0.0.1:8770/dispatch.html  (after step 5)
```

Expected `build` output:

```
[1/4] collecting OSM healthcare POIs
  using cached OSM data: 30 elements (D:\AssiutHospitals\data\osm_hospitals_raw.json)
  29 healthcare facilities after de-duplication
[2/4] snapping hospitals onto the SUMO network
  29 hospitals: 26 inside the network, 25 routable (0 on roads an ambulance may not use)
[3/4] writing SUMO + JSON artefacts
[4/4] writing the web map data

  hospitals : 29
  in network: 26
  routable  : 25
  outside   : 3
```

Expected `dispatch --check` output:

```
Z1  North-West (placeholder)         hospitals=11 routable=10
Z2  North-East (placeholder)         hospitals=3  routable=3
Z3  South-West (placeholder)         hospitals=3  routable=3
Z4  South-East (placeholder)         hospitals=9  routable=9
zone source : PLACEHOLDER - not owner-approved (review build)
capacity    : SYNTHETIC

RESULT: PASS
```

Expected verifier tail:

```
lane distances: 1402 lanes, max delta 0.00e+00s (BF 0.10-0.22 s)
checks: 192  failures: 0
RESULT: PASS
```

---

## 20. Part II — the emergency dispatch extension

### 20.1 The new request

After the map project was complete and validated, the owner asked for a
different tool built on the same network: an **emergency ambulance dispatch**
search. From any start point it must find the nearest suitable hospital by
**fastest travel time**, return the optimal route and time, and later compare
algorithms.

"Nearest" is defined by time, not straight-line distance. "Suitable" is defined
by an emergency department with a free place and the required specialty. The
search must run inside each of four manually defined zones and then choose the
best zone result.

The scope was split into ten numbered requirements/working rules. The first four
were built in this phase; requirements 5, 7, 8 and 10 were left for explicit
review, and the rest governed how the work was done. Nothing beyond the
requirements was added.

### 20.2 The working rules

The extension was built under stricter rules than the original map:

* one phase at a time, with a summary and a stop for review;
* complete files rather than fragments;
* code first, short explanation after;
* minimal changes to the existing project;
* Arabic/English comments on non-trivial functions;
* no invented data - anything synthetic is labelled **SYNTHETIC**;
* every algorithm result is checked against an independent shortest-time
  computation;
* old artefacts are reported but not removed or hidden without approval;
* requirement 5 (congestion) must be designed and approved before it is coded;
* the simulation study and the algorithm comparison are last, not now.

The existing map pipeline was reused as-is: the network parser, lane graph,
snapping, hospital dataset, Leaflet page and SUMO/TraCI layer were not rewritten.
The new code is a search layer on top of them.

### 20.3 What was deliberately not built

At this stage:

* no congestion adjustment (requirement 5);
* no algorithm comparison table (requirement 7);
* no simulation study (requirement 10);
* no automatic zone assignment (forbidden by requirement 2);
* no deletion of TLS, station markers, dashed lines, live stream, list filters
  or the 48 periodic flows (requirement 8 needs approval);
* no live bed feed, call queue or priority pre-emption.

---

## 21. Phase 14 — requirement 1: the minimal map

### 21.1 Why a new page instead of editing the old one

The original dashboard at `/` already draws the network, hospitals, TLS,
stations, dashed lines, live ambulances and filters. Requirement 1 asked for the
opposite: only the real map and the hospitals. Editing the old page would have
removed artefacts before approval, which requirement 8 forbids. A separate page
was therefore added:

```
web/dispatch.html     layout and panel
web/dispatch.js       Leaflet drawing + API calls
```

It reuses the generated `web/network.js` and `web/hospitals.js` and the vendored
Leaflet 1.9.4, so it needs no new data pipeline and no build step.

### 21.2 What it draws

* every normal road edge of the real SUMO network, as a polyline;
* all 29 facilities at their real OSM coordinates, with a tooltip and a popup
  showing the coordinates;
* a blue start marker where the user clicked;
* after a search, the returned route as a red polyline and a result card with
  hospital, zone, expected seconds, distance, edge count and search runtime.

The page fits the network bounds (with a small padding), not the three outside
hospitals, so the initial view is the simulated city. Whether the viewport should
include the outside facilities is an open question (L).

### 21.3 What it does not draw

The dispatch page never creates or reads:

* traffic-light markers or their live state;
* ambulance-station markers or the dashed station-to-hospital lines;
* the live ambulance stream (`/events`);
* the hospital list and its filters;
* the 48 periodic ambulance flows from `sumo/hospitals.rou.xml`.

`web/network.js` still contains the `trafficLights` array because the old page
uses it; `dispatch.js` ignores it. The old dashboard is untouched, so the
mismatches remain visible there until the owner approves removing them.

### 21.4 Interaction and verification

Clicking the map calls `setOrigin(lat, lon)` and mirrors the values into the two
number inputs. The search button accepts either a click or typed coordinates,
validates latitude/longitude range, calls `/api/dispatch`, then draws the
returned `optimal.route.geometry`.

The page, the JavaScript and the two generated data files were served on a test
port and checked for HTTP 200. A real request returned the optimal hospital,
time, edge list and geometry. The page also reads `/api/dispatch/meta` and shows
a warning badge when the zones are placeholders or the capacity is synthetic.

---

## 22. Phase 15 — requirement 2: the manual zones

### 22.1 The rule

Requirement 2 says the four theoretical zones, their boundaries and the
hospital-to-zone assignment are **manual**. It explicitly forbids automatic
assignment. The implementation therefore separates the two jobs:

```
config/dispatch.json     the only source of zone boundaries and hospital lists
dispatch_config.py       reads and validates that file; never assigns anything
```

`DispatchConfig.zone_of(slug)` simply scans the explicit lists. If a hospital is
not listed, it has no zone - there is no nearest-zone or point-in-polygon
fallback.

### 22.2 The placeholder split

No approved boundaries were available at build time, so four quadrants of the
network bounding box were used. The split point is the box centre
(`27.1862549275 N`, `31.1812651560 E`); the box edges come from the network
extent.

| zone | name in the file | facilities | routable | why |
|---|---|---|---|---|
| `Z1` | North-West (placeholder) | 11 | 10 | includes the 455 m non-routable facility |
| `Z2` | North-East (placeholder) | 3 | 3 | small cluster |
| `Z3` | South-West (placeholder) | 3 | 3 | includes both dead-end destinations |
| `Z4` | South-East (placeholder) | 9 | 9 | dense southern cluster |

The counts are the real number of facilities that fall in each placeholder
rectangle, not an 8/8/8/8 split. All 26 in-network facilities are assigned
exactly once. The 3 facilities outside the network are intentionally **not**
assigned, because the search can never reach them; they stay in the dataset and
on the map. The result is 26 assignments covering 25 routable facilities
(`osm-way-94168695` is in-network but not routable).

### 22.3 Validation, not derivation

`DispatchConfig.validate(dataset)` reports, and never repairs:

* the file must contain exactly four zones (`require_exactly_four_zones`);
* every boundary must satisfy `south < north` and `west < east`;
* a zone list must not be empty;
* every slug must exist in the dataset;
* a hospital may not appear in two zones;
* every `in_network` hospital must appear in exactly one zone;
* a listed hospital may not lie more than `assignment_tolerance_m` (25 m)
  outside its zone rectangle;
* a hospital that lies inside another zone's rectangle may not be assigned
  elsewhere.

The 25 m tolerance exists because a hospital point can sit just outside a
hand-drawn boundary while still belonging to that zone. It is a validation
tolerance, not an automatic assignment rule: the file still has to list the
hospital explicitly.

### 22.4 Why the zones are unequal

The placeholders follow geography, not an equal-count rule. The northern half of
the network contains most of the mapped facilities (11 + 3), while the southern
half has 3 + 9. Equalising them would require moving boundaries arbitrarily and
would be an automatic design decision. That is exactly what the owner has to
decide (A).

### 22.5 Replacing the placeholders

Edit `config/dispatch.json`, replace the four `boundary` objects and the four
`hospitals` lists, set `zone_source` to the approved description, then run:

```powershell
python run.py dispatch --check
```

The command prints the facility and routable count per zone and exits non-zero
if any validation rule fails. It is safe to run before every dispatch test.

---

## 23. Phase 16 — requirements 3 and 4: capacity and the search

### 23.1 The capacity file

OSM has no free-bed count and no reliable specialty list, so requirement 4 needs
a second input. `data/emergency_capacity.json` was added with one entry per
dataset slug and a nine-item specialty catalog. Every value is **SYNTHETIC**:

```
source  = "SYNTHETIC"
notice  = "SYNTHETIC DATA ... MUST be replaced ..."
```

The file is deliberately shaped to exercise the skip rules:

* `el-shorta-hospital` has `beds_total = 18`, `beds_free = 0` - the free-place
  check must skip it even though it offers burns and trauma;
* `asyut-chest-hospital` has cardiac but no burns - the specialty check must
  continue to another hospital;
* several small facilities offer only `general`;
* the two clinics are included only because `clinics_as_emergency` is
  provisionally `true`.

`capacity.py` validates the file (known slugs, negative values,
`beds_free <= beds_total`, specialties inside the catalog, an entry for every
dataset slug) and returns the errors without fixing them.

### 23.2 Travel time on a lane

`netmodel.py` now reads the per-lane `<lane length=... speed=...>` attributes
(the old map only needed edge geometry). `traveltime.py` turns them into a cost:

```
t(lane, a, b) = (b - a) * length(lane) / speed(lane) * factor(edge)
```

The fraction form matters because the ambulance usually starts in the middle of
a lane and stops at the hospital's snap point, not at the end of a lane. If a
lane has no speed, the model uses `13.89 m/s` (about 50 km/h); if it has no
length, it falls back to the edge length.

`factor(edge)` is the only congestion interface. It is an empty mapping in this
build, so it always returns `1.0`. `describe()` reports `free_flow` and
`congestion_enabled: false`. No congestion logic is hidden in the search.

### 23.3 Dijkstra on the class-aware lane graph

The search reuses the lane graph built for routability, so it inherits the
vehicle-class filter: a lane that does not allow `emergency` is never traversed.
Dijkstra runs from the origin lanes with:

* `dist[lane]` = time to reach the **start** of the lane (or 0 for a starting
  lane);
* `offset[lane]` = fraction of a starting lane already consumed;
* `previous[lane]` = predecessor used to rebuild the route.

The weight of leaving a lane is `lane_time(lane, offset, 1.0)`. This is a
standard non-negative shortest-path problem; all speeds are positive and all
weights are positive.

A second pass builds `entries[lane]`: the cheapest way to **enter** a lane from
any reachable predecessor. It is needed because a hospital can sit on a lane
whose own start time is not the best way to reach its entrance.

### 23.4 Partial lanes and the hospital-behind case

For each hospital entrance, the search tries every usable lane of the snapped
edge:

1. **Same lane, hospital ahead.** If the origin is on the lane and the hospital
   fraction is greater than or equal to the origin fraction, the cost is the
   partial time between the two fractions.
2. **Entry from a predecessor.** The cost is `entries[lane] + time(0, hospital
   fraction)`. This also handles a hospital **behind** the origin: the ambulance
   cannot reverse, so it must loop around the block and re-enter the lane from a
   predecessor. A same-lane-only implementation would silently overestimate or
   miss such hospitals.
3. **Choose the minimum** over all usable lanes and both cases.

If no lane produces a finite cost, the hospital is `reachable = false` and is
recorded with that reason.

### 23.5 The per-zone order

Requirement 4 defines an ordered check per zone:

1. nearest emergency department with a free place;
2. does it provide the required specialty?
3. if yes, record it as the zone result;
4. if not, continue to the next nearest.

The implementation expresses this as a sort followed by a filter:

```python
ordered = sorted(candidates, key=lambda c: (c.seconds or INF, c.slug))
for candidate in ordered:
    reason = candidate.reason_for(specialty)
    if reason is None:
        winner = candidate        # zone winner
        break
    checked.append(reason)        # auditable skip
```

`reason_for` checks, in order: routable, lane-level route exists, emergency
department, `beds_free > 0`, specialty present. Sorting by `seconds` first is
what makes "nearest" mean fastest; the slug is only a deterministic tie-break.
The complete `checked` list is returned in the JSON, so a "no hospital" answer
can be explained rather than guessed.

### 23.6 The optimum and the route

Historical (all four zones were searched before the owner decision): All four zones were searched, then:

```python
optimal = min(zone_winners, key=lambda c: (c.seconds, c.slug))
```

The route is rebuilt from the predecessor chain of the winning lane. If the
winner was on the origin lane ("same"), the route is a single partial segment;
otherwise it is `path_to(predecessor) + [winner lane]`. Every segment stores its
edge, lane, from/to fractions, time and length.

Before returning, `_verify_route` independently re-sums the segment times and
checks that:

* the total equals the candidate time within `1e-6 s`;
* every lane allows the `emergency` class;
* consecutive lanes are connected in the lane graph;
* the last fraction is the hospital's snap fraction.

This is the same rule used for every other algorithm result in the project: do
not trust the search, recompute it.

### 23.7 Determinism, complexity and a worked example

Dijkstra is deterministic because the heap is keyed by `(time, lane)` and the
candidate order ends with the slug. The graph has 1,402 lanes reachable from a
typical origin; the search is `O(E log V)` plus one pass over the hospitals.

Example from a real hospital coordinate (`27.1774203, 31.1837216`, the general
hospital), specialty `burns`, free-flow cost:

| zone | winner | seconds |
|---|---|---|
| Z1 | El Zhraa Hospital | 100.4 |
| Z2 | Sant Maria Hospital | 71.9 |
| Z3 | Asyut University Hospital | 124.0 |
| Z4 | Essam El Shrief El Tkasosy Hospital | **23.2** |

```
OPTIMAL  : Essam El Shrief El Tkasosy Hospital (Z4)
expected : 23.2 s | 583 m | 10 edges
search   : 0.023 s (Dijkstra + candidate evaluation)
```

The result is not "the nearest hospital by map distance": it is the fastest
candidate that passes the bed and specialty checks in its zone. The same origin
with `general` returns a different optimum, which is the intended behaviour.

---

## 24. Phase 17 — independent validation

### 24.1 Why Bellman-Ford

Validating Dijkstra with Dijkstra would only prove that the same code runs
twice. `tools/verify_dispatch.py` therefore implements **Bellman-Ford** on the
same class-aware lane graph and the same `TimeModel`:

* it relaxes every allowed lane connection repeatedly until no distance changes;
* it never uses a priority queue;
* it computes the entry table from its own distances;
* it recomputes every hospital time from those distances.

The two algorithms share the graph and the cost function but not the shortest
path logic. Agreement on 1,402 lanes is a strong consistency check.

### 24.2 What is compared

For four real hospital coordinates (one per zone) and nine specialties:

1. every lane distance from Dijkstra vs Bellman-Ford, tolerance `1e-6 s`;
2. each zone winner's time vs the independently recomputed hospital time;
3. the optimum vs the minimum of the four zone winners;
4. the route's first lane (must be an origin lane), last lane (must be the
   winner lane), endpoint fraction (must be the hospital snap fraction),
   lane continuity, `emergency` permission and re-summed time.

Dead-end origins are detected and skipped with a note: the mental-health
hospital reaches only 4 lanes, and the university hospital can reach only its
own edge. That is a property of the source network, not a search failure; how
that start should behave is an open decision (I).

### 24.3 The result

Command:

```powershell
python tools\verify_dispatch.py --specialties general,trauma,burns,cardiac,stroke,pediatric,obstetric,orthopedic,toxicology
```

Latest output:

```
origins     : 4
specialties : 9
capacity    : SYNTHETIC
lane distances: 1402 lanes, max delta 0.00e+00s (BF 0.10-0.22 s)
checks: 192  failures: 0
RESULT: PASS
```

The four origins were Asyut Chest Hospital, Al Mabara Hospital, Al Rowad and
ANTAR ENT clinic. The verifier also printed each zone's winner per specialty, so
the skip behaviour is visible: for example, from Asyut Chest Hospital the `burns`
optimum is El Zhraa, `trauma` goes to Al Mabara, and `orthopedic` goes to
El Akaad.

### 24.4 What the validation proves - and what it does not

It proves:

* Dijkstra and Bellman-Ford agree on every reachable lane;
* the zone winners and the final optimum are the true minima under the current
  cost model;
* every returned route is connected, permitted and ends at the hospital;
* the route time is not a stale number copied from the search.

It does **not** prove:

* real-world travel time - the cost is free-flow and the capacity is synthetic;
* that the route would be accepted by SUMO's own router - the dispatch route is
  computed on the lane graph but is not emitted as a SUMO trip;
* that another shortest-path algorithm would not be faster in wall-clock time;
* that the zone boundaries or the hospital assignment are correct.

Those are separate, explicitly deferred questions.

---

## 25. Phase 18 — API and UI wiring

### 25.1 CLI

`run.py dispatch` adds:

| flag | meaning |
|---|---|
| `--lat`, `--lon` | start point in decimal degrees (required unless `--check`) |
| `--specialty` | required specialty, default `general` |
| `--check` | validate zones and capacity, print counts, exit |
| `--json` | print the full result, including every checked candidate |
| `--force` | run even when configuration errors were reported |
| `--no-verify` | skip the route self-check (debugging only) |

Exit codes: `0` completed, `1` no suitable hospital in the human-readable
report, `2` input/configuration error. In `--json` mode a completed query exits
`0` even when `optimal` is `null`; the payload is the authoritative result. The
human-readable report prints origin snap, specialty, capacity source, cost
model, all four zone winners, the optimum, distance, edges, route and any notes.

### 25.2 HTTP endpoints

`serve()` constructs one `Dispatcher` at startup and injects it into the request
handler. The routes are:

* `GET /api/dispatch/meta` - specialties, capacity source, `synthetic`, vehicle
  class, zone source, cost model, configuration errors;
* `GET /api/dispatch?lat=&lon=&specialty=` - the full result;
* `/dispatch` and `/dispatch.html` - the page.

The server adds `optimal.route.geometry` (a list of `[lat, lon]` points) to the
JSON so the browser does not need to convert SUMO coordinates. A missing
dispatcher returns 503, a bad request 400 with an `error` string. The endpoints
are read-only: no bed is reserved and no simulation state changes.

### 25.3 Page behaviour

The page fetches the specialty catalog and the provenance metadata on load. A
search disables the button, shows "Searching the four zones...", calls the API
and either draws the route or shows the error. The result card reports seconds,
metres, edge count and search runtime. `Clear` removes the start, the route and
the result.

### 25.4 Error handling

`Dispatcher.search` raises `DispatchError` for:

* an unknown specialty (the message lists the catalog);
* a point with no road within the snap limit;
* a nearest road that does not allow `emergency`;
* a route that fails its own continuity/permission/time check.

The CLI maps these to exit code `2`; the API maps them to HTTP 400. A
configuration error is reported but does not crash by default; the CLI refuses
to search unless `--force` is passed, and `/api/dispatch/meta` exposes the same
list.

---

## 26. Phase 19 — requirement 5: the congestion design (not implemented)

### 26.1 Why nothing is coded

Requirement 5 says the cost must include current congestion, and the owner
explicitly required the **design to be approved before implementation**. The
free-flow part is active; the congestion part is only a hook. This is not an
omission hidden behind a default - the CLI, the JSON and the page all report
`congestion_enabled: false`.

### 26.2 The proposal

The proposed model, for approval, is:

1. at the start of a query, take one snapshot of live TraCI edge mean speeds
   (or lane mean speeds, if the owner prefers lane granularity);
2. smooth each edge with an exponential moving average (EMA) so one noisy step
   does not flip the chosen hospital;
3. compute `factor = speed_limit / max(v_hat, 2.0)`;
4. clamp to `[1.0, 5.0]` so a stopped edge cannot produce an infinite cost and a
   faster-than-limit measurement cannot make the route artificially cheap;
5. store the result in `TimeModel.congestion_factor` as `edge id -> factor`;
6. use `1.0` for edges with no measurement, no live connection or a static
   query.

The search code does not change: `lane_time` already multiplies by
`factor(edge)`.

### 26.3 Open sub-decisions

These are exactly the points that need approval before coding:

* **edge vs lane**: `traci.edge.getLastStepMeanSpeed` is simple but hides
  per-lane variation; lane-level means are more precise but noisier;
* **measurement source**: last-step mean speed, `getLastStepVehicleNumber` plus
  a speed-density relation, or a time-to-travel estimate;
* **EMA interval and α**: per simulation second, per 10 s, or per query; α
  controls how quickly the route reacts;
* **cap**: `[1.0, 5.0]` is a proposal, not a measurement;
* **missing data**: `1.0` is a neutral fallback but understates congestion on
  unmeasured edges;
* **static queries**: `--no-live` / no TraCI connection should either use free
  flow or refuse to claim a congestion-aware result;
* **emergency vehicles**: whether their own speed should be included (it can
  bias the measurement upwards);
* **snapshot consistency**: one snapshot per query is reproducible, but the
  route may take minutes to drive.

### 26.4 What changes when approved

Only the population of `TimeModel.congestion_factor` and the `cost` block in
`config/dispatch.json` need to change. `dispatch.py` and the lane graph stay as
they are. That was the reason for adding the hook before the design was
approved: the search layer would not have to be rewritten.

---

## 27. Historical: owner decisions at the time

### 27.1 A-H at the time (resolved by owner; see Phase 20)

| id | decision still needed | current provisional behaviour |
|---|---|---|
| A | real four-zone split (the current split is 11/3/3/9, not 8/8/8/8) | placeholder quadrants |
| B | real emergency beds and specialty lists | SYNTHETIC file |
| C | do the 2 clinics count as emergency destinations? | `clinics_as_emergency: true` |
| D | are the two dead-end hospitals acceptable destinations? | accepted (arrival only) |
| E | how to treat the 455 m hospital (`osm-way-94168695`)? | kept in dataset, excluded by the 250 m routability rule |
| F | real zone boundaries | quadrants of the network bounding box |
| G | confirm "search all four zones, then best" | implemented exactly like that |
| H | algorithm list for the comparison table | Dijkstra only |

### 27.2 I-L at the time (resolved by owner; see Phase 20)

| id | question | effect today |
|---|---|---|
| I | what should a start on a dead-end road do? | search runs, but the reachable set can be only 4 lanes (mental health) or just the hospital edge (university) |
| J | is the 400 m origin snap limit right? | origins snap up to 400 m; the dataset used 250 m |
| K | should the 3 outside hospitals be map context only? | they are shown but not assigned to a zone and can never be winners |
| L | should the map viewport include the outside hospitals? | viewport fits the network, so the 17 km / 11 km facilities may be off-screen |

No automatic answer was chosen for any of these.

### 27.3 Historical: requirements 7 and 10 at the time

> This subsection is superseded by Part III. Requirement 7 is now built and
> measured; requirement 10 remains not built but has an options report.

* **Requirement 7 (algorithm comparison).** At this point the owner had not
  supplied the algorithm list. The provisional implementation was Dijkstra only.
* **Requirement 10 (simulation study).** The owner asked for the study only at
  the end, after approval, and for the options to be reported rather than
  built. No study was run.

### 27.4 Dispatch limitations

1. Cost is free-flow; real congestion is ignored until requirement 5 is
   approved.
2. Capacity and specialties are synthetic; the result is a routing
   demonstration, not a clinical recommendation.
3. Zones are placeholders and unequal.
4. The route is computed and verified on the lane graph but is not emitted as a
   SUMO trip, so SUMO's own router has not executed it.
5. A hospital entrance is represented by the nearest usable lane point; a
   hospital with a gate on the opposite carriageway may get a longer route. The
   drawn polyline follows edge shapes, not individual lane centerlines.
6. The network is a 2023-era OSM extract; new roads and hospitals are absent.
7. No live feed: the answer is a snapshot of the supplied capacity file, not a
   real-time bed count.
8. The search has no U-turn; it loops around the block when the hospital is
   behind the start, or fails if no loop exists.

---

## 28. Dispatch bug and issue log

Everything that needed a decision or a workaround during the extension, in the
order it appeared.

| # | symptom / issue | cause | resolution |
|---|---|---|---|
| 1 | zone validation demanded every hospital, including the 3 outside | `in_network` was not part of the rule | require assignment only for `in_network` facilities; the outside three stay unassigned |
| 2 | `osm-way-94168695` is listed in Z1 but cannot be routed | it is 455 m from any road, over the 250 m dataset limit | kept assigned (it is in-network) and skipped by the `routable` check; decision E |
| 3 | two hospitals have no outbound ambulance flow | their campus road is a dead end with no successor lane | accepted as destinations; decision D |
| 4 | a dead-end start reaches very few lanes | the lane graph has no reverse/U-turn | verifier skips such origins with a note; decision I |
| 5 | origin snap uses 400 m, dataset snap uses 250 m | two different questions (where can an ambulance start vs where is the hospital) | documented; decision J |
| 6 | a hospital behind the origin was initially easy to miss | same-lane-only logic cannot go backwards | entry-from-predecessor case added; loop around the block |
| 7 | clinics were candidates without an explicit decision | `clinics_as_emergency` defaulted to true | exposed as a config flag; decision C |
| 8 | zones were unequal | they are geographic placeholders, not an equal split | documented; decision A |
| 9 | every result claimed a real bed count | the data file is invented | `source: SYNTHETIC` + notice + badge/CLI/API warning |
| 10 | the route had no independent check | Dijkstra could be trusted only by itself | Bellman-Ford verifier; 192 checks, 0 failures |
| 11 | the dispatch route was never executed by SUMO | it is a lane-graph route, not a generated trip | documented as a limitation, not claimed as SUMO validation |
| 12 | CLI printed `SYNTHETIC (SYNTHETIC - not real data)` | the source string already contains the label | cosmetic redundancy; kept because it is explicit |
| 13 | `--json` exited 0 even when no suitable hospital was found | the JSON branch returns before the `optimal is None` check | documented; JSON callers must inspect `optimal`, human mode still returns 1 |

---

## Appendix A — all 29 hospitals

`rout` = routable, `amb` = emitted ambulance flows.
Snap distance is the distance from the OSM position to the road edge.

| # | hospital | category | edge | snap | in net | rout | amb |
|---|---|---|---|---|---|---|---|
| 1 | Abo Teeg Central Hospital | hospital | `834696777` | 17,182.7 m | **no** | no | – |
| 2 | Al Mabara Hospital | hospital | `738247820#2` | 26.4 m | yes | yes | in+out |
| 3 | Al Rowad | hospital | `-778635853#6` | 76.3 m | yes | yes | in+out |
| 4 | ANTAR ENT clinic | clinic | `297204609#31` | 14.7 m | yes | yes | in+out |
| 5 | Arc Angle Mikhael Hospital | hospital | `-E10` | 6.2 m | yes | yes | in+out |
| 6 | Asyout Hospital for Mental Health | hospital | `601745501#2` | 56.5 m | yes | yes | in+out |
| 7 | Asyut Chest Hospital | hospital | `97620457#5` | 31.7 m | yes | yes | in+out |
| 8 | Asyut University Hospital | hospital | `701132859#4` | 127.3 m | yes | yes | **in** |
| 9 | Dar El Shefaa Hospital | hospital | `601637232#13` | 1.1 m | yes | yes | in+out |
| 10 | El Akaad Hospital | hospital | `-94168662#10` | 2.4 m | yes | yes | in+out |
| 11 | El Aksaa Hospital | hospital | `97405608#2` | 16.0 m | yes | yes | in+out |
| 12 | El Fayrouz Hospital | hospital | `-700111397` | 131.2 m | yes | yes | in+out |
| 13 | El Hayah Hospital | hospital | `398151290#6` | 1.7 m | yes | yes | in+out |
| 14 | El Nseem Dr.Trez Mansour Hospital | hospital | `97405586#0` | 3.1 m | yes | yes | in+out |
| 15 | El Reda Hospital | hospital | `601637232#12` | 1.6 m | yes | yes | in+out |
| 16 | El Safaa Hospital | hospital | `398151290#6` | 1.0 m | yes | yes | in+out |
| 17 | El Salam Hospital | hospital | `820440644#4` | 15.1 m | yes | yes | in+out |
| 18 | El Salama Hospital | hospital | `-700111397` | 53.7 m | yes | yes | in+out |
| 19 | El Shorta Hospital | hospital | `601421695#2` | 0.1 m | yes | yes | in+out |
| 20 | El Zerayeen Hospital | hospital | `97411049#2` | 15.3 m | yes | yes | in+out |
| 21 | El Zhraa Hospital | hospital | `601637232#12` | 1.1 m | yes | yes | in+out |
| 22 | Essam El Shrief El Tkasosy Hospital | hospital | `97405586#3` | 14.0 m | yes | yes | in+out |
| 23 | Nekabet El Moalmen Hospital | hospital | `-816252891#5` | 870.3 m | **no** | no | – |
| 24 | Sant Maria Hospital | hospital | `97608215#2` | 1.9 m | yes | yes | in+out |
| 25 | University Dental Hospital | hospital | `601415735#1` | 11,021.0 m | **no** | no | – |
| 26 | Unnamed hospital (way/94168667) | hospital | `701132859#4` | 141.6 m | yes | yes | **in** |
| 27 | Unnamed hospital (way/94168695) | hospital | `601745498` | 454.8 m | yes | **no** | – |
| 28 | مستشفى أسيوط العام | hospital | `820385165#0` | 28.9 m | yes | yes | in+out |
| 29 | مستشفى دار السلام | clinic | `820385165#4` | 13.3 m | yes | yes | in+out |

---

## Appendix B — historical: the nine traffic lights (no longer displayed)

| label | `tlLogic` id | junction | programs | phases |
|---|---|---|---|---|
| Kobry1 | `cluster_5716218908_5716218909` | `tls_1` | 1 | 3 |
| Kobry2 | `clusterJ0_cluster_6584594176_7639850262_7791048972_7886735542_#5more` | `tls_2` | 1 | 6 |
| Mahkama | `5716218813` | `TLS_3` | 1 | 4 |
| Mahmoud Rashwan | `cluster_1130035552_6581475302_6584594153_6584594170` | `TLS_4` | 4 | 4 |
| Gomharia | `cluster_6317381791_6570064975` | `TLS_5` | 1 | 3 |
| El Nemis | `cluster_1033118564_1128138549_7045517260_7045517261` | `TLS_6` | 1 | 4 |
| City | `cluster_6588723386_7646202672` | `TLS_7` | 1 | 6 |
| El Hilaly | `cluster_13387024595_13387024596_6304811468_6304811546_#3more` | `TLS_8` | 3 | 4 |
| Kairo | `7644809311` | `TLS_9` | 1 | 4 |

Note the casing inconsistency in the junction ids (`tls_1`, `tls_2` vs
`TLS_3…TLS_9`) — it comes straight from the source network.

---

## Appendix C — file map

```
D:\AssiutHospitals
├── README.md                     user manual
├── PROCESS.md                    this engineering log
├── SIMULATION_OPTIONS.md         options report only; no simulation built
├── run.py                        CLI (build | serve | dispatch | compare | list | info)
├── config.json                   base tunables and source paths
├── config\
│   └── dispatch.json             owner-approved zones, policy, exclusions, algorithms
├── assiut_hospitals\
│   ├── __init__.py               public API
│   ├── bootstrap.py              SUMO_HOME -> sys.path
│   ├── config.py                 config + path resolution
│   ├── projection.py             UTM 36N <-> local
│   ├── netmodel.py               net.xml parser, LaneGraph, SCC/dead-end helpers
│   ├── snapping.py               class-aware snapping
│   ├── overpass.py               Overpass client + cache
│   ├── hospitals.py              Hospital model + de-duplication
│   ├── dataset.py                HospitalRecord / Dataset
│   ├── emit.py                   all writers (no hubs, TLS or flows)
│   ├── dispatch_config.py        manual zone loader + policy validation
│   ├── capacity.py               emergency beds/specialties loader
│   ├── traveltime.py             free-flow time model
│   ├── algorithms.py             A*, Bellman-Ford, VAM, NWC, least-cost, MODI
│   ├── compare.py                measured comparison + report writer
│   ├── dispatch.py               start-zone-only search + route reconstruction
│   └── server.py                 static HTTP server + dispatch API
├── data\
│   ├── osm_hospitals_raw.json    cached Overpass answer
│   ├── hospitals.json            generated dataset (29 facilities)
│   └── emergency_capacity.json   SYNTHETIC beds/specialties
├── sumo\
│   ├── hospitals.poi.xml         POI markers
│   ├── hospitals.rou.xml         empty route file (zero flows)
│   └── hospitals.sumocfg         generated SUMO configuration
├── web\
│   ├── dispatch.html             the only dashboard
│   ├── dispatch.js               map + dispatch UI
│   ├── network.js                generated road geometry
│   ├── hospitals.js              generated hospital dataset
│   └── vendor\leaflet.{js,css}   vendored Leaflet 1.9.4
├── reports\
│   ├── algorithm_comparison.md
│   └── algorithm_comparison.json
└── tools\
    └── verify_dispatch.py        independent Bellman-Ford validation
```

### Generated artefact sizes (last build)

| file | size |
|---|---|
| `web/network.js` | 101,814 bytes |
| `data/hospitals.json` | 20,935 bytes |
| `web/hospitals.js` | 16,728 bytes |
| `sumo/hospitals.rou.xml` | 265 bytes (no flows) |
| `sumo/hospitals.poi.xml` | 4,069 bytes |
| `sumo/hospitals.sumocfg` | 899 bytes |
| `config/dispatch.json` | 4,951 bytes |
| `web/dispatch.js` | 8,763 bytes |
| `web/dispatch.html` | 5,009 bytes |
| `reports/algorithm_comparison.md` | 13,278 bytes |

---

## Appendix D — dispatch data contract

### D.1 `config/dispatch.json`

| key | type | meaning |
|---|---|---|
| `zone_source` | string | owner-approved provenance label (`OWNER-APPROVED ...`) |
| `vehicle_class` | string | SUMO class used for permissions; `emergency` |
| `require_exactly_four_zones` | bool | reject any other count |
| `assignment_tolerance_m` | number | how far a listed hospital may sit outside its rectangle |
| `capacity_file` | path | relative to the project root or absolute |
| `clinics_as_emergency` | bool | may an OSM `clinic` act as an emergency destination? |
| `specialty_catalog` | list[string] | accepted `--specialty` values |
| `origin.max_snap_distance_m` | number | maximum start-point snap distance |
| `cost.mode` | string | `free_flow` in this build |
| `cost.congestion.enabled` | bool | `false` by owner decision; free-flow only |
| `zones[]` | list | exactly four entries |
| `zones[].id` | string | `Z1`...`Z4`, unique |
| `zones[].name` | string | display label |
| `zones[].boundary` | object | `south`, `west`, `north`, `east` in degrees |
| `zones[].hospitals` | list[string] | explicit dataset slugs; no automatic assignment |
| `owner_decisions` | object | final A-L decisions, copied into review output |
| `search_scope` | string | `start_zone_only` |
| `excluded_destinations` | object | owner-excluded dead-end destinations |
| `comparison_algorithms` | list | seven measured algorithms |

### D.2 `data/emergency_capacity.json`

| key | type | meaning |
|---|---|---|
| `source` | string | `SYNTHETIC` now; every output checks this prefix |
| `notice` | string | human-readable provenance warning |
| `specialties_catalog` | list[string] | the allowed specialty vocabulary |
| `hospitals` | object | one entry per dataset slug |
| `hospitals[slug].emergency_department` | bool | has an emergency department |
| `hospitals[slug].beds_total` | int | total emergency places |
| `hospitals[slug].beds_free` | int | free places now; `0` means skip |
| `hospitals[slug].specialties` | list[string] | must be inside the catalog |
| `hospitals[slug].note` | string | free text, used to mark synthetic entries |

### D.3 `DispatchResult` (JSON)

| key | meaning |
|---|---|
| `origin` | requested lat/lon, snapped lat/lon, edge, position, snap distance, usable lanes |
| `specialty` | the validated specialty |
| `capacity_source` / `synthetic_capacity` | provenance and its boolean form |
| `cost_model` | `mode`, `congestion_enabled`, `vehicle_class`, default speed |
| `zones` | one entry per zone: winner, the ordered `checked` list with reasons, note |
| `optimal` | hospital name, slug, zone, seconds and (for the API) route with geometry |
| `route` | seconds, length, normal edges, all edges, lane list, per-segment fractions/times |
| `runtime_seconds` | wall-clock search time |
| `search_scope` / `search_zone` | start-zone-only policy and the selected zone |
| `notes` | SYNTHETIC and owner-decision notes |

### D.4 Validation contract

`tools/verify_dispatch.py` exits `0` only when every check passes. It prints
`checks: N  failures: 0` and `RESULT: PASS`; any mismatch is printed with the
specialty, zone or lane and a non-zero exit follows. The tolerance is `1e-6 s`
because the two algorithms use the same double-precision arithmetic but a
different relaxation order.


---

## 33. Part III - final dispatch completion

This part is the authoritative account of the final implementation. It records
the owner decisions that closed the earlier open questions, the structural
dead-end analysis, the start-zone-only search, the seven-algorithm comparison,
the removal work, and the final validation results.

---

## 34. Phase 20 - owner decisions A-L

The earlier prototype had several provisional choices. The owner reviewed the
evidence and answered every open question on 2026-10-23. The answers are stored
verbatim in `config/dispatch.json` under `owner_decisions`.

| ID | Decision | Consequence in code |
|---|---|---|
| A | Accept the current unequal `11/3/3/9` zone split | `zone_source = OWNER-APPROVED ...` |
| B | Keep clearly labelled SYNTHETIC capacity/specialty data | `capacity.py`, CLI/API badges, README |
| C | Do not count the two clinics as emergency facilities | `clinics_as_emergency = false` |
| D | Exclude the two dead-end hospitals as destinations | `excluded_destinations` |
| E | Keep `osm-way-94168695` map-only (454.81 m from a road) | routability limit unchanged |
| F | Keep the current manual quadrant boundaries | `zones[]` rectangles unchanged |
| G | Search only the zone containing the start point | `search_scope = start_zone_only` |
| H | Compare Dijkstra, A*, Bellman-Ford, VAM, least-cost, NWC and MODI | `comparison_algorithms` |
| I | Refuse a start on a dead-end component | SCC test in `Dispatcher._origin` |
| J | Keep the 400 m maximum start snap distance | `origin.max_snap_distance_m = 400` |
| K | Keep the three outside-network hospitals on the map only | no zone assignment |
| L | Fit the map to the real network bounds | `NET.bounds` in `dispatch.js` |

The configuration also records that requirement 5 is resolved as **free-flow
only**. No congestion code exists behind a flag; the time model reports
`mode = free_flow` and `congestion_enabled = false` in every result.

### 34.1 Why the decisions were checked first

Several earlier assumptions became invalid once the owner chose start-zone-only
search and dead-end refusal:

* an all-zone comparison could return a hospital in a different zone;
* a dead-end destination would produce a route that could never be driven out;
* a dead-end start would produce a shorter-than-real route or no route at all;
* clinics would have been counted as emergency destinations;
* the old UI claimed "four zones searched" and showed traffic lights and live
  ambulances that were no longer part of the requirement.

The implementation therefore changed policy first, then rebuilt the search,
then removed the old output paths. Validation was rerun after each stage.

---

## 35. Phase 21 - dead ends and start refusal

### 35.1 Why a distance threshold was not used

The first idea was to treat a start as a dead end when it could reach fewer than
some fixed number of lanes. That would have been an invented threshold. The
network is directed: a lane can be reachable from the start yet unable to reach
the main road system, and the size of that component does not tell us whether it
is structurally isolated.

### 35.2 Strongly connected components

`LaneGraph.main_component()` performs an iterative Kosaraju SCC analysis on the
class-aware lane graph and caches the result. The largest SCC has **1,220
lanes**. The start test is:

```
reachable = graph.reachable_lanes([start_edge], "emergency")
accepted  = bool(reachable & graph.main_component("emergency"))
```

If the intersection is empty, `_origin` raises `DispatchError` and the CLI exits
with status 2. No route is fabricated.

### 35.3 What the analysis found

* The main component contains 1,220 lanes.
* `asyout-hospital-for-mental-health` reaches only
  `{836116503_0, 601745501#3_0, 601745501#2_0, -836116503_0}`; it does not
  intersect the main component.
* `asyut-university-hospital` and `osm-way-94168667` snap to edge
  `701132859#4`; its lane `701132859#4_0` has no successors.
* Therefore both are excluded as destinations (decision D), and starts on those
  components are refused (decision I).

The structural test replaces the earlier arbitrary lane-count threshold and is
recorded in `config/dispatch.json` as
`dead_end_definition: "the start cannot reach the largest strongly connected lane component"`.

---

## 36. Phase 22 - start-zone-only search

### 36.1 Zone lookup

`DispatchConfig.zones_for_point()` returns every manual rectangle containing the
snapped start. The dispatcher:

* rejects a point outside all four zones;
* rejects a point on a shared boundary (two or more rectangles);
* otherwise searches exactly one zone.

The boundary rejection is deliberate: choosing one of two zones automatically
would violate the "no automatic choices" rule.

### 36.2 Candidate evaluation

For every hospital in the selected zone, `_candidate()` computes the fastest
arrival using the precomputed Dijkstra distances:

* if the hospital is on a start lane and ahead, use the remaining forward part;
* otherwise enter the lane from its best predecessor and drive to the hospital
  fraction;
* if neither exists, the candidate is unreachable and is skipped.

`_pick()` sorts candidates by travel time and returns the first one whose
`reason_for()` is `None`. The rejection order is explicit:

1. owner exclusion (dead-end destination);
2. not routable;
3. no lane-level route;
4. no emergency department;
5. no free place;
6. required specialty unavailable.

`clinics_as_emergency = false` is enforced by the capacity loader, so a clinic
never has an effective emergency department. The full `checked` list with a
reason for each candidate is still returned for transparency.

### 36.3 Result fields

`DispatchResult` now carries `search_scope` and `search_zone`. The web page no
longer says "all four zones"; it shows the start zone and the selected hospital's
zone. The JSON result keeps the same route and timing fields as before, plus the
policy notes.

### 36.4 No suitable hospital

If the zone has no suitable hospital, `optimal` is `null`. The CLI human output
exits 1. The `--json` mode also exits 1 (the earlier prototype incorrectly
exited 0). No fallback to another zone exists.

---

## 37. Phase 23 - the seven algorithms

### 37.1 Dijkstra (dispatch baseline)

The production search uses Dijkstra on the class-aware lane graph. It is the
only algorithm used by the live dispatch API. It returns distances, offsets and
predecessors; the route is rebuilt from the predecessor chain and checked by
`_verify_route()`.

### 37.2 A*

`algorithms.astar_to_targets()` is a multi-target A* implementation:

* targets are all usable lanes of every suitable hospital in the start zone;
* the heuristic is `straight-line distance from the lane start to the nearest
  target point / maximum lane speed`;
* the heuristic is zero on origin lanes, because the ambulance is already
  part-way along them;
* the search stops when the best complete target cost is no greater than the
  smallest open-lane `f` value;
* same-lane targets ahead of the start are considered before expansion;
* entering a target lane from a predecessor is considered as a complete route.

Because `straight-line / max_speed` can never exceed the real free-flow time,
A* is exact. It returned the same optimum as Dijkstra and Bellman-Ford in every
tested case.

### 37.3 Bellman-Ford

`algorithms.bellman_ford()` relaxes every lane in lane-id order for up to
`V - 1` rounds, with the same cost function and origin offsets as Dijkstra. It is
independent of the production search and is used as the reference in
`compare.py` and `tools/verify_dispatch.py`.

At 1,402 reachable lanes, Dijkstra and Bellman-Ford matched with maximum delta
`0.00e+00 s` at each tested origin.

### 37.4 Transportation methods - explicitly documented adaptation

VAM, least-cost, north-west corner and MODI are **not pathfinders**. The project
does not pretend they are. They are applied to this transportation model:

```
rows    = suitable hospitals in the start zone
supply  = free emergency beds per hospital
column 1 (patient) = demand 1, cost = Dijkstra free-flow time
column 2 (dummy)   = demand (total beds - 1), cost > every real cost
```

The hospital allocated to the patient column is selected. Its route and time are
taken from the Dijkstra matrix. The Dijkstra matrix time is included in the
measured runtime of these methods.

Implementation details:

* north-west corner allocates from the top-left cell, respecting supply/demand;
* least-cost repeatedly chooses the cheapest open cell;
* VAM computes row and column penalties and allocates at the maximum penalty;
* MODI starts from the north-west solution, adds independent zero basics,
  computes row/column potentials, chooses the most negative reduced cost,
  finds the stepping-stone cycle and pivots until no negative reduced cost
  remains.

A 300-random-matrix property test confirmed that MODI selects the cheapest real
hospital whenever the transportation model has a real optimum. The routes are
validated separately.

### 37.5 Why the comparison is not a fake benchmark

The report distinguishes two things:

1. **pathfinding runtime** (Dijkstra, A*, Bellman-Ford), where the algorithm
   genuinely builds a route;
2. **selection runtime plus Dijkstra matrix time** (transportation methods),
   where the algorithm chooses a destination and borrows the route.

The report prints this distinction, and `verified` is checked against
Bellman-Ford for every selected hospital. A method that chooses a suboptimal
hospital is shown as `Optimal = no`, not hidden.

---

## 38. Phase 24 - measured comparison

`run.py compare` chooses one routable, non-dead-end hospital coordinate per zone
and runs the specialties `general`, `trauma`, `cardiac`, `pediatric`. Each row
records wall-clock runtime, route time, route length, edge count, optimality and
verification.

Latest run (2026-10-23, 16 cases):

| Algorithm | Runs | Mean runtime (ms) | Mean route time (s) | Optimal | Verified | Failures |
|---|---:|---:|---:|---:|---:|---:|
| Dijkstra | 16 | 26.371 | 16.587 | 12 | 16 | 0 |
| A* | 16 | 10.816 | 16.587 | 12 | 16 | 0 |
| Bellman-Ford | 16 | 258.482 | 16.587 | 12 | 16 | 0 |
| VAM | 16 | 26.417 | 16.587 | 12 | 16 | 0 |
| Least-cost | 16 | 26.396 | 16.587 | 12 | 16 | 0 |
| North-west corner | 16 | 26.386 | 24.999 | 8 | 16 | 0 |
| MODI | 16 | 26.406 | 16.587 | 12 | 16 | 0 |

The four non-optimal cases per pathfinder/optimising method are the four cases
with no suitable hospital in the zone; those methods correctly returned no
selection. NWC's 8/16 and higher mean route time are expected because it is an
initial, non-optimising method. Full per-case data is in
`reports/algorithm_comparison.md` and `.json`.

Observed practical points:

* A* was the fastest pathfinder here because its heuristic prunes the search;
* Bellman-Ford was much slower, as expected for 1,402 lanes;
* transportation methods are dominated by the Dijkstra matrix cost;
* MODI recovered the optimal selection from the NWC starting solution;
* VAM and least-cost matched the optimum in these cases, but that is an
  empirical result for these inputs, not a general optimality claim.

---

## 39. Phase 25 - removing the old mismatches

The owner approved complete removal, not hiding behind CSS. The following were
deleted or regenerated:

| Old mismatch | Action |
|---|---|
| Original dashboard `web/index.html`, `web/app.js`, `web/style.css` | deleted; `/` now serves `dispatch.html` |
| Traffic-light layer and labels | removed from `emit.py`; regenerated `network.js` has no `trafficLights` |
| Ambulance station hubs/dashed lines | hub selection and metadata removed from `emit.py`; `hospitals.js`/dataset no longer emit ambulance hub data |
| Live ambulance stream | `server.py` rewritten as a static server; `/events` and `/api/state` removed |
| `SimulationRunner` / TraCI live process | `scenario.py` removed; server starts no SUMO process |
| UI list and filters | deleted with the old dashboard |
| 48 periodic ambulance flows | `sumo/hospitals.rou.xml` now contains zero `<flow>` elements; `emit_ambulance_routes` removed |
| Old validation command | removed; it depended on the deleted flows |
| `data/validation.json`, `sumo/sumo-run.log` | removed |

The new route writer is `emit_empty_routes()`. It preserves a valid routes-file
header so the SUMO configuration still loads, but contains no vehicles or flows.
The POI file remains a SUMO visualisation artefact; it is not a dashboard layer.

After regeneration, a text search for `trafficLights`, `ambulance` hub metadata,
`<flow` and `period=` in `network.js`, `hospitals.js`, `hospitals.json` and
`hospitals.rou.xml` returned no old content. The old server process and its SUMO
child that were still running on port 8770 were stopped before deleting the old
log.

---

## 40. Phase 26 - final verification

### 40.1 Dispatch verification

Command:

```powershell
& $py tools\verify_dispatch.py
```

Output summary:

```
origins: 4, specialties: general, burns, cardiac
checks: 39  failures: 0
RESULT: PASS
```

The script recomputed 1,402 reachable lane distances with Bellman-Ford at each
origin and found `max delta 0.00e+00 s`. It checked start-zone-only scope,
independent winners, route continuity, emergency permission, route time,
hospital endpoint fraction, clinic/exclusion policy, and dead-end start refusal.

### 40.2 Algorithm comparison

Command:

```powershell
& $py run.py compare
```

Result: 16 cases x 7 algorithms, `failures: 0`. Every selected route time was
within `1e-6 s` of the Bellman-Ford time, and every pathfinder selected the
Bellman-Ford optimum (or correctly selected nothing when the zone had no
suitable hospital).

### 40.3 Server smoke test

`run.py serve --port 8771` was started and checked with HTTP requests:

* `/` - 200 and serves the dispatch page;
* `/api/dispatch/meta` - 200 with `search_scope = start_zone_only`,
  `clinics_as_emergency = false`, the two exclusions and no config errors;
* `/api/dispatch?lat=...&lon=...&specialty=burns` - 200 with a hospital,
  route geometry and time;
* `/api/network` - 200;
* deleted `/app.js` - 404;
* no background SUMO process was started.

### 40.4 Encoding audit

All source and generated `.py`, `.md`, `.json`, `.js`, `.html`, `.xml`, `.cfg`
and `.css` files were decoded as UTF-8 and checked for a leading BOM. Result:
zero BOMs and zero decode errors.

---

## 41. Phase 27 - final bug and issue log

These are the issues found while completing the dispatch work. Earlier issues
are in section 28.

| # | Issue | Resolution |
|---|---|---|
| D1 | All-zone search contradicted owner decision G | rewrote `Dispatcher.search` to use only `zones_for_point(start)` and added `search_scope`/`search_zone` output |
| D2 | `_origin` accepted a dead-end start | added cached SCC `main_component()` and refusal check |
| D3 | Dead-end hospitals remained selectable | added owner `excluded_destinations` and candidate-level reason |
| D4 | Clinics could be emergency destinations | set `clinics_as_emergency=false`; capacity loader makes them non-emergency |
| D5 | JSON mode exited 0 when `optimal` was null | now exits 1 |
| D6 | UI said "all four zones" and "four zones searched" | changed to start-zone-only wording |
| D7 | A* needed a valid exact multi-target stopping rule | implemented admissible heuristic, same-lane ahead targets, entry targets and safe stop condition; compared with BF |
| D8 | Transportation methods are not pathfinders | added explicit transportation model, documented it, used Dijkstra only for selected route/time and included matrix runtime |
| D9 | MODI basis could degenerate | added independent zero basics and degenerate-pivot handling; property-tested on 300 random matrices |
| D10 | Old live server/SUMO process still held `sumo-run.log` | stopped the project's stale process, then removed the log |
| D11 | Old dashboard files were still reachable | deleted old files; `/` now maps to dispatch page |
| D12 | `emit.py` still generated hubs, TLS and 48 flows | removed the hub/TLS/flow code and added `emit_empty_routes` |
| D13 | `hospitals.json` still contained ambulance hub metadata | removed the `ambulance` field from `HospitalRecord.as_dict`; regenerated dataset |
| D14 | Stale validation and smoke-test tools depended on removed app/flows | removed `validation.py`, `scenario.py` and the old smoke test |

---

## 42. Phase 28 - final state and limitations

### Final state

* Four manual zones accepted by the owner: `11/3/3/9`.
* Start-zone-only search; no cross-zone fallback.
* 400 m snap limit; boundary ambiguity and outside-zone starts rejected.
* Dead-end starts refused by SCC analysis.
* Two dead-end destinations excluded; clinics excluded.
* 26 in-network facilities assigned; 3 outside-network facilities map-only.
* Dijkstra baseline; A*, Bellman-Ford and four transportation methods compared.
* 1,402 reachable lanes; Dijkstra/Bellman-Ford max delta `0.00e+00 s`.
* 39/39 dispatch checks and 0/112 comparison rows failed (16 cases x 7).
* Generated route file has zero flows.
* Old dashboard, TLS layer, live stream, hub metadata, filters and old validation
  were removed.
* `README.md` is the user manual; this file is the engineering log;
  `SIMULATION_OPTIONS.md` is the requested options report only.

### Limitations that remain by design

* Emergency capacity and specialty values are synthetic.
* Travel time is free-flow only; congestion is not modelled.
* There is no live bed feed, call queue, pre-emption or incident model.
* Transportation methods select hospitals; they do not build graph routes.
* Outside-network hospitals cannot be selected.
* No simulation study was built; only options were reported.
* The comparison runtime is machine-dependent and should be re-measured on the
  target machine rather than quoted as a constant.
