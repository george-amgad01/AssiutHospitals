# Assiut Operations Research Report

**Generated (UTC):** 2026-10-26T22:20:34+00:00

> **DATA STATUS: SYNTHETIC TEST QUANTITIES**

> SYNTHETIC TEST DATA. OSM/SUMO do not publish hospital kit stock, zone demand, patient-transfer demand, background lane flow, or measured road capacity. Every number below is a configurable test value and must be replaced with owner-provided data before operational use.

This report covers the one-day, capacity-constrained kit/patient model. It is additive to the existing emergency dispatch project; it does not replace that dispatcher. The road network and hospital coordinates are the existing Assiut assets and are not modified by this report.

## 1. Executive result

| item | value |
|---|---|
| routed hospitals | 25 |
| manual zones | 4 |
| active kit sources | 17 |
| patient destinations | 19 |
| kit supply / demand | 180 / 170 |
| unused kit supply / unmet kit demand | 10 / 0 |
| patient transfers / usable free beds | 18 / 89 |
| VAM initial objective Z0 | 92553.958 kit-metres |
| MODI final objective | 92553.958 kit-metres |
| exact tableau MILP | 92553.958 kit-metres |
| network MILP status | optimal |
| network feasible | True |
| network demand met | True |
| total vehicle-metres | 9888.711 |
| errors / warnings | 0 / 5 |

**Feasible vs optimal.** A feasible plan satisfies supply, demand, bed, fleet, route, prohibited-lane, and lane-capacity checks. The network MILP's `optimal` status is optimality for the stated integer model; it is not a proof of global optimality for every possible real-world objective. VAM and MODI alone are **not** claimed to optimize the road-capacitated network.

## 2. Data, zones, and resources

The four zones and hospital membership are read from the owner-approved manual dispatch configuration. The OR layer does not invent an automatic zone assignment. Zone demand and kit stock are synthetic test values unless the source is explicitly owner data.

| zone | name | anchor | hospitals | active sources | patient destinations | kit supply | kit demand | patient demand | usable free beds |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| Z1 | North-West | el-hayah-hospital | 10 | 6 | 6 | 60 | 50 | 6 | 29 |
| Z2 | North-East | al-mabara-hospital | 3 | 3 | 3 | 40 | 40 | 4 | 15 |
| Z3 | South-West | al-rowad | 3 | 1 | 3 | 10 | 40 | 4 | 14 |
| Z4 | South-East | el-salam-hospital | 9 | 7 | 7 | 70 | 40 | 4 | 31 |

Zone counts, supplies, and demands are deliberately unequal. No equal-demand or equal-hospital-count assumption is used. Hospital membership is the existing manual assignment, not a Voronoi or nearest-anchor calculation.

### Hospital roles and resources

| hospital | category | zone | emergency | beds total/free | kits | can leave | can enter | role / exclusion |
|---|---|---|---|---:|---:|---|---|---|
| al-mabara-hospital | hospital | Z2 | yes | 20/6 | 20 | yes | yes | kit source; patient destination |
| al-rowad | hospital | Z3 | yes | 10/3 | 10 | yes | yes | kit source; patient destination |
| antar-ent-clinic | clinic | Z4 | no | 4/2 | 0 | yes | yes | not an emergency facility under the clinic policy |
| arc-angle-mikhael-hospital | hospital | Z4 | yes | 12/5 | 10 | yes | yes | kit source; patient destination |
| asyout-hospital-for-mental-health | hospital | Z1 | yes | 8/2 | 0 | no | no | receiving lane cannot be reached from the main network |
| asyut-chest-hospital | hospital | Z1 | yes | 14/4 | 10 | yes | yes | kit source; patient destination |
| asyut-university-hospital | hospital | Z3 | yes | 30/8 | 0 | no | yes | patient destination |
| dar-el-shefaa-hospital | hospital | Z1 | yes | 16/5 | 0 | no | yes | patient destination |
| el-akaad-hospital | hospital | Z1 | yes | 10/3 | 10 | yes | yes | kit source; patient destination |
| el-aksaa-hospital | hospital | Z4 | yes | 14/4 | 10 | yes | yes | kit source; patient destination |
| el-fayrouz-hospital | hospital | Z1 | yes | 10/2 | 0 | no | no | receiving lane cannot be reached from the main network |
| el-hayah-hospital | hospital | Z1 | yes | 18/5 | 10 | yes | yes | kit source; patient destination |
| el-nseem-dr-trez-mansour-hospital | hospital | Z4 | yes | 12/3 | 10 | yes | yes | kit source; patient destination |
| el-reda-hospital | hospital | Z2 | yes | 14/4 | 10 | yes | yes | kit source; patient destination |
| el-safaa-hospital | hospital | Z1 | yes | 16/6 | 10 | yes | yes | kit source; patient destination |
| el-salam-hospital | hospital | Z4 | yes | 20/7 | 10 | yes | yes | kit source; patient destination |
| el-salama-hospital | hospital | Z1 | yes | 12/3 | 0 | no | no | receiving lane cannot be reached from the main network |
| el-shorta-hospital | hospital | Z1 | yes | 18/0 | 10 | yes | no | kit source |
| el-zerayeen-hospital | hospital | Z4 | yes | 10/2 | 10 | yes | yes | kit source; patient destination |
| el-zhraa-hospital | hospital | Z1 | yes | 22/6 | 10 | yes | yes | kit source; patient destination |
| essam-el-shrief-el-tkasosy-hospital | hospital | Z4 | yes | 12/4 | 10 | yes | yes | kit source; patient destination |
| osm-node-10883658615 | clinic | Z4 | no | 6/2 | 0 | yes | yes | not an emergency facility under the clinic policy |
| osm-node-14078009201 | hospital | Z4 | yes | 25/6 | 10 | yes | yes | kit source; patient destination |
| osm-way-94168667 | hospital | Z3 | yes | 10/3 | 0 | no | yes | patient destination |
| sant-maria-hospital | hospital | Z2 | yes | 18/5 | 10 | yes | yes | kit source; patient destination |

A free bed is **receiving capacity** at a destination. It is not a resource loaded into an ambulance. Kits, beds, ambulances, and background traffic are separate quantities.

## 3. Mathematical model and data rules

The full notation and constraints are in `OR_MODEL.md`. In brief:

- **Sets:** routable hospitals, four manual zones, lane graph, active kit sources, patient destinations.
- **Kit variable:** integer number of 10-kit trips from source to zone anchor; each trip consumes 10 kits.
- **Patient variable:** integer number of patient transfers from a zone anchor to a receiving hospital.
- **Ambulance variable:** integer vehicles assigned to each zone; total is capped at 48.
- **Unmet variables:** explicit kit and patient shortages; the solver pays a large penalty rather than hiding them.
- **Road constraints:** for every lane, background flow + ambulance flow on that lane <= estimated capacity. Background flow is kept separate.
- **Prohibited lanes:** removed from the lane graph before search; they are not a large finite cost.

### Road-capacity estimate

The repository has no measured lane capacity. The shipped value is a **documented `SYNTHETIC_ESTIMATE` estimate**, computed from lane count and road type, not from street length alone. It is configurable in `config/or_planning.json`.

| parameter | value |
|---|---|
| planning interval [h] | 24.0 |
| reserve fraction | 0.0 |
| default vehicles/lane/hour | 800.0 |
| minimum vehicles/lane | 10.0 |

| road type | vehicles/lane/hour |
|---|---:|
| highway.footway | 0.0 |
| highway.living_street | 400.0 |
| highway.motorway | 1800.0 |
| highway.primary | 1400.0 |
| highway.primary_link | 900.0 |
| highway.residential | 700.0 |
| highway.secondary | 1200.0 |
| highway.secondary_link | 900.0 |
| highway.service | 300.0 |
| highway.steps | 0.0 |
| highway.tertiary | 1000.0 |
| highway.tertiary_link | 900.0 |
| highway.trunk | 1600.0 |
| highway.unclassified | 650.0 |

### Prohibited lanes

| item | value |
|---|---:|
| network vehicle-class prohibited lanes | 387 |
| explicit prohibited lanes in config | 0 |
| total removed from graph | 387 |

The rule is: lanes without permission for `emergency` and explicit closures are removed from every search. If no route exists, the cell is reported as unavailable; the solver does not silently use a large penalty as a substitute for a physical prohibition.

## 4. Kit-only transportation tableau

The tableau is a **kit-only** model. It does not contain road capacities. Its exact optimum is therefore a cost benchmark and an allocation benchmark, not a road-capacitated feasibility claim.

### Initial cost table

| source | supply | Z1 | Z2 | Z3 | Z4 | row note |
|---|---|---|---|---|---|---|
| al-mabara-hospital | 20 | 2293.332 | 0.000 | 2713.241 | 2074.552 | active kit source |
| al-rowad | 10 | 3213.280 | 2750.369 | 0.000 | 1204.770 | active kit source |
| arc-angle-mikhael-hospital | 10 | 2002.150 | 1727.338 | 1591.970 | 953.280 | active kit source |
| asyut-chest-hospital | 10 | 1666.600 | 1943.518 | 2610.150 | 2047.840 | active kit source |
| el-akaad-hospital | 10 | 444.630 | 1484.938 | 1397.750 | 835.440 | active kit source |
| el-aksaa-hospital | 10 | 1245.080 | 1738.719 | 1493.300 | 1052.290 | active kit source |
| el-hayah-hospital | 10 | 0.000 | 1341.208 | 1681.080 | 1118.770 | active kit source |
| el-nseem-dr-trez-mansour-hospital | 10 | 2124.842 | 1661.930 | 946.132 | 383.822 | active kit source |
| el-reda-hospital | 10 | 513.432 | 1307.020 | 1530.392 | 968.082 | active kit source |
| el-safaa-hospital | 10 | 0.000 | 1341.208 | 1681.080 | 1118.770 | active kit source |
| el-salam-hospital | 10 | 2687.070 | 2224.158 | 562.310 | 0.000 | active kit source |
| el-shorta-hospital | 10 | 1256.590 | 855.998 | 2200.140 | 1637.830 | active kit source |
| el-zerayeen-hospital | 10 | 2002.150 | 1727.339 | 1591.970 | 953.280 | active kit source |
| el-zhraa-hospital | 10 | 511.420 | 1305.009 | 1528.380 | 966.070 | active kit source |
| essam-el-shrief-el-tkasosy-hospital | 10 | 1997.080 | 1534.168 | 818.370 | 256.060 | active kit source |
| osm-node-14078009201 | 10 | 2579.965 | 2117.053 | 1080.215 | 838.945 | active kit source |
| sant-maria-hospital | 10 | 970.730 | 1247.648 | 1914.280 | 1351.970 | active kit source |
| **demand** | 170 | 50 | 40 | 40 | 40 |  |

All costs are lane-route distances in **metres** from the active kit source to the manual zone anchor. `FORBIDDEN` means no route existed under the current prohibited-lane and shift rules. Cell caps are **not used** in this kit-only tableau (the network model enforces lane capacities separately).

### Balance / dummy

Original supply = 180, original demand = 170, shortage = 0, surplus = 10.

The balanced table has 17 rows and 5 columns, with no dummy row and dummy column `4`.

A dummy is added only because the supplied test data is unbalanced. It is labelled and its zero-cost allocation is reported as unused supply or unmet demand, never as a real trip.

### VAM initial solution

**Z0 (VAM initial objective): 92553.958 kit-metres.**

The selection rule is deterministic: choose the largest penalty; rows win ties over columns, and the lower index wins the remaining tie. Penalties are recomputed after every allocation. A line with one available cell uses that cell's cost as its penalty and is marked in the trace notes.

| step | selected line | penalty | cell | quantity | struck | allocations after step |
|---:|---|---:|---|---:|---|---|
| 1 | row: asyut-chest-hospital | 1666.600 | asyut-chest-hospital -> DUMMY_UNUSED_SUPPLY | 10 | asyut-chest-hospital, DUMMY_UNUSED_SUPPLY | al-mabara-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>al-rowad: [0.0, 0.0, 0.0, 0.0, 0.0]<br>arc-angle-mikhael-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>asyut-chest-hospital: [0.0, 0.0, 0.0, 0.0, 10.0]<br>el-akaad-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-aksaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-hayah-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-nseem-dr-trez-mansour-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-reda-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-safaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-salam-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-shorta-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zerayeen-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zhraa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>essam-el-shrief-el-tkasosy-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>osm-node-14078009201: [0.0, 0.0, 0.0, 0.0, 0.0]<br>sant-maria-hospital: [0.0, 0.0, 0.0, 0.0, 0.0] |
| 2 | row: al-mabara-hospital | 2074.552 | al-mabara-hospital -> Z2 | 20 | al-mabara-hospital | al-mabara-hospital: [0.0, 20.0, 0.0, 0.0, 0.0]<br>al-rowad: [0.0, 0.0, 0.0, 0.0, 0.0]<br>arc-angle-mikhael-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>asyut-chest-hospital: [0.0, 0.0, 0.0, 0.0, 10.0]<br>el-akaad-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-aksaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-hayah-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-nseem-dr-trez-mansour-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-reda-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-safaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-salam-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-shorta-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zerayeen-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zhraa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>essam-el-shrief-el-tkasosy-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>osm-node-14078009201: [0.0, 0.0, 0.0, 0.0, 0.0]<br>sant-maria-hospital: [0.0, 0.0, 0.0, 0.0, 0.0] |
| 3 | row: al-rowad | 1204.770 | al-rowad -> Z3 | 10 | al-rowad | al-mabara-hospital: [0.0, 20.0, 0.0, 0.0, 0.0]<br>al-rowad: [0.0, 0.0, 10.0, 0.0, 0.0]<br>arc-angle-mikhael-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>asyut-chest-hospital: [0.0, 0.0, 0.0, 0.0, 10.0]<br>el-akaad-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-aksaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-hayah-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-nseem-dr-trez-mansour-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-reda-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-safaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-salam-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-shorta-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zerayeen-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zhraa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>essam-el-shrief-el-tkasosy-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>osm-node-14078009201: [0.0, 0.0, 0.0, 0.0, 0.0]<br>sant-maria-hospital: [0.0, 0.0, 0.0, 0.0, 0.0] |
| 4 | row: el-hayah-hospital | 1118.770 | el-hayah-hospital -> Z1 | 10 | el-hayah-hospital | al-mabara-hospital: [0.0, 20.0, 0.0, 0.0, 0.0]<br>al-rowad: [0.0, 0.0, 10.0, 0.0, 0.0]<br>arc-angle-mikhael-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>asyut-chest-hospital: [0.0, 0.0, 0.0, 0.0, 10.0]<br>el-akaad-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-aksaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-hayah-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-nseem-dr-trez-mansour-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-reda-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-safaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-salam-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-shorta-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zerayeen-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zhraa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>essam-el-shrief-el-tkasosy-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>osm-node-14078009201: [0.0, 0.0, 0.0, 0.0, 0.0]<br>sant-maria-hospital: [0.0, 0.0, 0.0, 0.0, 0.0] |
| 5 | row: el-safaa-hospital | 1118.770 | el-safaa-hospital -> Z1 | 10 | el-safaa-hospital | al-mabara-hospital: [0.0, 20.0, 0.0, 0.0, 0.0]<br>al-rowad: [0.0, 0.0, 10.0, 0.0, 0.0]<br>arc-angle-mikhael-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>asyut-chest-hospital: [0.0, 0.0, 0.0, 0.0, 10.0]<br>el-akaad-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-aksaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-hayah-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-nseem-dr-trez-mansour-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-reda-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-safaa-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-salam-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-shorta-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zerayeen-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zhraa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>essam-el-shrief-el-tkasosy-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>osm-node-14078009201: [0.0, 0.0, 0.0, 0.0, 0.0]<br>sant-maria-hospital: [0.0, 0.0, 0.0, 0.0, 0.0] |
| 6 | row: arc-angle-mikhael-hospital | 638.690 | arc-angle-mikhael-hospital -> Z4 | 10 | arc-angle-mikhael-hospital | al-mabara-hospital: [0.0, 20.0, 0.0, 0.0, 0.0]<br>al-rowad: [0.0, 0.0, 10.0, 0.0, 0.0]<br>arc-angle-mikhael-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>asyut-chest-hospital: [0.0, 0.0, 0.0, 0.0, 10.0]<br>el-akaad-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-aksaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-hayah-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-nseem-dr-trez-mansour-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-reda-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-safaa-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-salam-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-shorta-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zerayeen-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zhraa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>essam-el-shrief-el-tkasosy-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>osm-node-14078009201: [0.0, 0.0, 0.0, 0.0, 0.0]<br>sant-maria-hospital: [0.0, 0.0, 0.0, 0.0, 0.0] |
| 7 | row: el-zerayeen-hospital | 638.690 | el-zerayeen-hospital -> Z4 | 10 | el-zerayeen-hospital | al-mabara-hospital: [0.0, 20.0, 0.0, 0.0, 0.0]<br>al-rowad: [0.0, 0.0, 10.0, 0.0, 0.0]<br>arc-angle-mikhael-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>asyut-chest-hospital: [0.0, 0.0, 0.0, 0.0, 10.0]<br>el-akaad-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-aksaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-hayah-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-nseem-dr-trez-mansour-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-reda-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-safaa-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-salam-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-shorta-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zerayeen-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-zhraa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>essam-el-shrief-el-tkasosy-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>osm-node-14078009201: [0.0, 0.0, 0.0, 0.0, 0.0]<br>sant-maria-hospital: [0.0, 0.0, 0.0, 0.0, 0.0] |
| 8 | row: essam-el-shrief-el-tkasosy-hospital | 562.310 | essam-el-shrief-el-tkasosy-hospital -> Z4 | 10 | essam-el-shrief-el-tkasosy-hospital | al-mabara-hospital: [0.0, 20.0, 0.0, 0.0, 0.0]<br>al-rowad: [0.0, 0.0, 10.0, 0.0, 0.0]<br>arc-angle-mikhael-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>asyut-chest-hospital: [0.0, 0.0, 0.0, 0.0, 10.0]<br>el-akaad-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-aksaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-hayah-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-nseem-dr-trez-mansour-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-reda-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-safaa-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-salam-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-shorta-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zerayeen-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-zhraa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>essam-el-shrief-el-tkasosy-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>osm-node-14078009201: [0.0, 0.0, 0.0, 0.0, 0.0]<br>sant-maria-hospital: [0.0, 0.0, 0.0, 0.0, 0.0] |
| 9 | row: el-nseem-dr-trez-mansour-hospital | 562.310 | el-nseem-dr-trez-mansour-hospital -> Z4 | 10 | el-nseem-dr-trez-mansour-hospital, Z4 | al-mabara-hospital: [0.0, 20.0, 0.0, 0.0, 0.0]<br>al-rowad: [0.0, 0.0, 10.0, 0.0, 0.0]<br>arc-angle-mikhael-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>asyut-chest-hospital: [0.0, 0.0, 0.0, 0.0, 10.0]<br>el-akaad-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-aksaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-hayah-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-nseem-dr-trez-mansour-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-reda-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-safaa-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-salam-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-shorta-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zerayeen-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-zhraa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>essam-el-shrief-el-tkasosy-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>osm-node-14078009201: [0.0, 0.0, 0.0, 0.0, 0.0]<br>sant-maria-hospital: [0.0, 0.0, 0.0, 0.0, 0.0] |
| 10 | row: el-salam-hospital | 1661.849 | el-salam-hospital -> Z3 | 10 | el-salam-hospital | al-mabara-hospital: [0.0, 20.0, 0.0, 0.0, 0.0]<br>al-rowad: [0.0, 0.0, 10.0, 0.0, 0.0]<br>arc-angle-mikhael-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>asyut-chest-hospital: [0.0, 0.0, 0.0, 0.0, 10.0]<br>el-akaad-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-aksaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-hayah-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-nseem-dr-trez-mansour-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-reda-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-safaa-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-salam-hospital: [0.0, 0.0, 10.0, 0.0, 0.0]<br>el-shorta-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zerayeen-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-zhraa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>essam-el-shrief-el-tkasosy-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>osm-node-14078009201: [0.0, 0.0, 0.0, 0.0, 0.0]<br>sant-maria-hospital: [0.0, 0.0, 0.0, 0.0, 0.0] |
| 11 | row: osm-node-14078009201 | 1036.839 | osm-node-14078009201 -> Z3 | 10 | osm-node-14078009201 | al-mabara-hospital: [0.0, 20.0, 0.0, 0.0, 0.0]<br>al-rowad: [0.0, 0.0, 10.0, 0.0, 0.0]<br>arc-angle-mikhael-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>asyut-chest-hospital: [0.0, 0.0, 0.0, 0.0, 10.0]<br>el-akaad-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-aksaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-hayah-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-nseem-dr-trez-mansour-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-reda-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-safaa-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-salam-hospital: [0.0, 0.0, 10.0, 0.0, 0.0]<br>el-shorta-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zerayeen-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-zhraa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>essam-el-shrief-el-tkasosy-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>osm-node-14078009201: [0.0, 0.0, 10.0, 0.0, 0.0]<br>sant-maria-hospital: [0.0, 0.0, 0.0, 0.0, 0.0] |
| 12 | row: el-akaad-hospital | 953.120 | el-akaad-hospital -> Z1 | 10 | el-akaad-hospital | al-mabara-hospital: [0.0, 20.0, 0.0, 0.0, 0.0]<br>al-rowad: [0.0, 0.0, 10.0, 0.0, 0.0]<br>arc-angle-mikhael-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>asyut-chest-hospital: [0.0, 0.0, 0.0, 0.0, 10.0]<br>el-akaad-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-aksaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-hayah-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-nseem-dr-trez-mansour-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-reda-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-safaa-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-salam-hospital: [0.0, 0.0, 10.0, 0.0, 0.0]<br>el-shorta-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zerayeen-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-zhraa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>essam-el-shrief-el-tkasosy-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>osm-node-14078009201: [0.0, 0.0, 10.0, 0.0, 0.0]<br>sant-maria-hospital: [0.0, 0.0, 0.0, 0.0, 0.0] |
| 13 | row: el-zhraa-hospital | 793.588 | el-zhraa-hospital -> Z1 | 10 | el-zhraa-hospital | al-mabara-hospital: [0.0, 20.0, 0.0, 0.0, 0.0]<br>al-rowad: [0.0, 0.0, 10.0, 0.0, 0.0]<br>arc-angle-mikhael-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>asyut-chest-hospital: [0.0, 0.0, 0.0, 0.0, 10.0]<br>el-akaad-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-aksaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-hayah-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-nseem-dr-trez-mansour-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-reda-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-safaa-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-salam-hospital: [0.0, 0.0, 10.0, 0.0, 0.0]<br>el-shorta-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zerayeen-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-zhraa-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>essam-el-shrief-el-tkasosy-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>osm-node-14078009201: [0.0, 0.0, 10.0, 0.0, 0.0]<br>sant-maria-hospital: [0.0, 0.0, 0.0, 0.0, 0.0] |
| 14 | row: el-reda-hospital | 793.588 | el-reda-hospital -> Z1 | 10 | el-reda-hospital, Z1 | al-mabara-hospital: [0.0, 20.0, 0.0, 0.0, 0.0]<br>al-rowad: [0.0, 0.0, 10.0, 0.0, 0.0]<br>arc-angle-mikhael-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>asyut-chest-hospital: [0.0, 0.0, 0.0, 0.0, 10.0]<br>el-akaad-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-aksaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-hayah-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-nseem-dr-trez-mansour-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-reda-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-safaa-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-salam-hospital: [0.0, 0.0, 10.0, 0.0, 0.0]<br>el-shorta-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-zerayeen-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-zhraa-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>essam-el-shrief-el-tkasosy-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>osm-node-14078009201: [0.0, 0.0, 10.0, 0.0, 0.0]<br>sant-maria-hospital: [0.0, 0.0, 0.0, 0.0, 0.0] |
| 15 | row: el-shorta-hospital | 1344.141 | el-shorta-hospital -> Z2 | 10 | el-shorta-hospital | al-mabara-hospital: [0.0, 20.0, 0.0, 0.0, 0.0]<br>al-rowad: [0.0, 0.0, 10.0, 0.0, 0.0]<br>arc-angle-mikhael-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>asyut-chest-hospital: [0.0, 0.0, 0.0, 0.0, 10.0]<br>el-akaad-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-aksaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-hayah-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-nseem-dr-trez-mansour-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-reda-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-safaa-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-salam-hospital: [0.0, 0.0, 10.0, 0.0, 0.0]<br>el-shorta-hospital: [0.0, 10.0, 0.0, 0.0, 0.0]<br>el-zerayeen-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-zhraa-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>essam-el-shrief-el-tkasosy-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>osm-node-14078009201: [0.0, 0.0, 10.0, 0.0, 0.0]<br>sant-maria-hospital: [0.0, 0.0, 0.0, 0.0, 0.0] |
| 16 | row: sant-maria-hospital | 666.631 | sant-maria-hospital -> Z2 | 10 | sant-maria-hospital, Z2 | al-mabara-hospital: [0.0, 20.0, 0.0, 0.0, 0.0]<br>al-rowad: [0.0, 0.0, 10.0, 0.0, 0.0]<br>arc-angle-mikhael-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>asyut-chest-hospital: [0.0, 0.0, 0.0, 0.0, 10.0]<br>el-akaad-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-aksaa-hospital: [0.0, 0.0, 0.0, 0.0, 0.0]<br>el-hayah-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-nseem-dr-trez-mansour-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-reda-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-safaa-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-salam-hospital: [0.0, 0.0, 10.0, 0.0, 0.0]<br>el-shorta-hospital: [0.0, 10.0, 0.0, 0.0, 0.0]<br>el-zerayeen-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-zhraa-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>essam-el-shrief-el-tkasosy-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>osm-node-14078009201: [0.0, 0.0, 10.0, 0.0, 0.0]<br>sant-maria-hospital: [0.0, 10.0, 0.0, 0.0, 0.0] |
| 17 | row: el-aksaa-hospital | 1493.300 | el-aksaa-hospital -> Z3 | 10 | el-aksaa-hospital, Z3 | al-mabara-hospital: [0.0, 20.0, 0.0, 0.0, 0.0]<br>al-rowad: [0.0, 0.0, 10.0, 0.0, 0.0]<br>arc-angle-mikhael-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>asyut-chest-hospital: [0.0, 0.0, 0.0, 0.0, 10.0]<br>el-akaad-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-aksaa-hospital: [0.0, 0.0, 10.0, 0.0, 0.0]<br>el-hayah-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-nseem-dr-trez-mansour-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-reda-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-safaa-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>el-salam-hospital: [0.0, 0.0, 10.0, 0.0, 0.0]<br>el-shorta-hospital: [0.0, 10.0, 0.0, 0.0, 0.0]<br>el-zerayeen-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>el-zhraa-hospital: [10.0, 0.0, 0.0, 0.0, 0.0]<br>essam-el-shrief-el-tkasosy-hospital: [0.0, 0.0, 0.0, 10.0, 0.0]<br>osm-node-14078009201: [0.0, 0.0, 10.0, 0.0, 0.0]<br>sant-maria-hospital: [0.0, 10.0, 0.0, 0.0, 0.0] |

### VAM final allocation (kits)

| source | supply | Z1 | Z2 | Z3 | Z4 | DUMMY_UNUSED_SUPPLY | row total |
|---|---|---|---|---|---|---|---|
| al-mabara-hospital | 20 | 0 | 20 | 0 | 0 | 0 | 20 |
| al-rowad | 10 | 0 | 0 | 10 | 0 | 0 | 10 |
| arc-angle-mikhael-hospital | 10 | 0 | 0 | 0 | 10 | 0 | 10 |
| asyut-chest-hospital | 10 | 0 | 0 | 0 | 0 | 10 | 10 |
| el-akaad-hospital | 10 | 10 | 0 | 0 | 0 | 0 | 10 |
| el-aksaa-hospital | 10 | 0 | 0 | 10 | 0 | 0 | 10 |
| el-hayah-hospital | 10 | 10 | 0 | 0 | 0 | 0 | 10 |
| el-nseem-dr-trez-mansour-hospital | 10 | 0 | 0 | 0 | 10 | 0 | 10 |
| el-reda-hospital | 10 | 10 | 0 | 0 | 0 | 0 | 10 |
| el-safaa-hospital | 10 | 10 | 0 | 0 | 0 | 0 | 10 |
| el-salam-hospital | 10 | 0 | 0 | 10 | 0 | 0 | 10 |
| el-shorta-hospital | 10 | 0 | 10 | 0 | 0 | 0 | 10 |
| el-zerayeen-hospital | 10 | 0 | 0 | 0 | 10 | 0 | 10 |
| el-zhraa-hospital | 10 | 10 | 0 | 0 | 0 | 0 | 10 |
| essam-el-shrief-el-tkasosy-hospital | 10 | 0 | 0 | 0 | 10 | 0 | 10 |
| osm-node-14078009201 | 10 | 0 | 0 | 10 | 0 | 0 | 10 |
| sant-maria-hospital | 10 | 0 | 10 | 0 | 0 | 0 | 10 |
| **column total** | **180** | **50** | **40** | **40** | **40** | **10** | **180** |

Dummy: column 4. The dummy cells carry zero cost and are labelled `DUMMY_UNUSED_SUPPLY` or `DUMMY_UNMET_DEMAND`; they are not physical deliveries.

### MODI (u-v) trace

**Initial VAM objective:** 92553.958 kit-metres. **Final MODI objective:** 92553.958 kit-metres. **Status:** optimal. **Iterations:** 4.

Forbidden cells stay outside the basis and outside the entering candidate set. Degeneracy is handled by adding zero basic cells; every addition is listed in the notes. The adjustment cycle alternates plus/minus cells and is shown in full below.

MODI notes: degeneracy handled by adding 4 zero basic cell(s): (al-mabara-hospital,Z1), (al-mabara-hospital,Z3), (al-mabara-hospital,Z4), (al-mabara-hospital,DUMMY_UNUSED_SUPPLY)

#### MODI iteration 1

u = `[0.0, -2713.241483438084, -1121.271537274853, 0.0, -1848.7015372748529, -1219.9411137589277, -2293.331537274853, -1690.729564828127, -1779.899919853765, -2293.331537274853, -2150.9315150107436, 855.9984627251472, -1121.2714912479673, -1781.9113948476038, -1818.491537274853, -1633.0266304357838, 1247.648469906815]`; v = `[2293.331537274853, 0.0, 2713.241483438084, 2074.551515010743, 0.0]`

Entering cell: **sant-maria-hospital -> Z1**, reduced cost **-2570.250**, theta **0.000**, degenerate **True**, leaving cell **al-mabara-hospital -> Z1**.

Cycle: (sant-maria-hospital,Z1) -> (sant-maria-hospital,Z2) -> (al-mabara-hospital,Z2) -> (al-mabara-hospital,Z1)

Reduced-cost table (rows are sources; columns are destinations):

```
al-mabara-hospital: 0.000 | 0.000 | 0.000 | 0.000 | 0.000
al-rowad: 3633.190 | 5463.610 | 0.000 | 1843.460 | 2713.241
arc-angle-mikhael-hospital: 830.090 | 2848.610 | -0.000 | 0.000 | 1121.272
asyut-chest-hospital: -626.732 | 1943.518 | -103.092 | -26.712 | 0.000
el-akaad-hospital: 0.000 | 3333.640 | 533.210 | 609.590 | 1848.702
el-aksaa-hospital: 171.690 | 2958.660 | 0.000 | 197.680 | 1219.941
el-hayah-hospital: 0.000 | 3634.540 | 1261.170 | 1337.550 | 2293.332
el-nseem-dr-trez-mansour-hospital: 1522.240 | 3352.660 | -76.380 | 0.000 | 1690.730
el-reda-hospital: 0.000 | 3086.920 | 597.050 | 673.430 | 1779.900
el-safaa-hospital: 0.000 | 3634.540 | 1261.170 | 1337.550 | 2293.332
el-salam-hospital: 2544.670 | 4375.090 | 0.000 | 76.380 | 2150.932
el-shorta-hospital: -1892.740 | 0.000 | -1369.100 | -1292.720 | -855.998
el-zerayeen-hospital: 830.090 | 2848.610 | -0.000 | 0.000 | 1121.271
el-zhraa-hospital: 0.000 | 3086.920 | 597.050 | 673.430 | 1781.911
essam-el-shrief-el-tkasosy-hospital: 1522.240 | 3352.660 | -76.380 | 0.000 | 1818.492
osm-node-14078009201: 1919.660 | 3750.080 | 0.000 | 397.420 | 1633.027
sant-maria-hospital: -2570.250 | 0.000 | -2046.610 | -1970.230 | -1247.648
```

Allocation after the iteration (kits):

```
al-mabara-hospital: 0.000 | 20.000 | 0.000 | 0.000 | 0.000
al-rowad: 0.000 | 0.000 | 10.000 | 0.000 | 0.000
arc-angle-mikhael-hospital: 0.000 | 0.000 | 0.000 | 10.000 | 0.000
asyut-chest-hospital: 0.000 | 0.000 | 0.000 | 0.000 | 10.000
el-akaad-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
el-aksaa-hospital: 0.000 | 0.000 | 10.000 | 0.000 | 0.000
el-hayah-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
el-nseem-dr-trez-mansour-hospital: 0.000 | 0.000 | 0.000 | 10.000 | 0.000
el-reda-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
el-safaa-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
el-salam-hospital: 0.000 | 0.000 | 10.000 | 0.000 | 0.000
el-shorta-hospital: 0.000 | 10.000 | 0.000 | 0.000 | 0.000
el-zerayeen-hospital: 0.000 | 0.000 | 0.000 | 10.000 | 0.000
el-zhraa-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
essam-el-shrief-el-tkasosy-hospital: 0.000 | 0.000 | 0.000 | 10.000 | 0.000
osm-node-14078009201: 0.000 | 0.000 | 10.000 | 0.000 | 0.000
sant-maria-hospital: 0.000 | 10.000 | 0.000 | 0.000 | 0.000
```

#### MODI iteration 2

u = `[0.0, -2713.241483438084, -1121.271537274853, 0.0, 721.548462725147, -1219.9411137589277, 276.91846272514704, -1690.729564828127, 790.350080146235, 276.91846272514704, -2150.9315150107436, 855.9984627251472, -1121.2714912479673, 788.3386051523962, -1818.491537274853, -1633.0266304357838, 1247.648469906815]`; v = `[-276.91846272514704, 0.0, 2713.241483438084, 2074.551515010743, 0.0]`

Entering cell: **sant-maria-hospital -> Z3**, reduced cost **-2046.610**, theta **0.000**, degenerate **True**, leaving cell **al-mabara-hospital -> Z3**.

Cycle: (sant-maria-hospital,Z3) -> (sant-maria-hospital,Z2) -> (al-mabara-hospital,Z2) -> (al-mabara-hospital,Z3)

Reduced-cost table (rows are sources; columns are destinations):

```
al-mabara-hospital: 2570.250 | 0.000 | 0.000 | 0.000 | 0.000
al-rowad: 6203.440 | 5463.610 | 0.000 | 1843.460 | 2713.241
arc-angle-mikhael-hospital: 3400.340 | 2848.610 | -0.000 | 0.000 | 1121.272
asyut-chest-hospital: 1943.518 | 1943.518 | -103.092 | -26.712 | 0.000
el-akaad-hospital: 0.000 | 763.390 | -2037.040 | -1960.660 | -721.548
el-aksaa-hospital: 2741.940 | 2958.660 | 0.000 | 197.680 | 1219.941
el-hayah-hospital: 0.000 | 1064.290 | -1309.080 | -1232.700 | -276.918
el-nseem-dr-trez-mansour-hospital: 4092.490 | 3352.660 | -76.380 | 0.000 | 1690.730
el-reda-hospital: 0.000 | 516.670 | -1973.200 | -1896.820 | -790.350
el-safaa-hospital: 0.000 | 1064.290 | -1309.080 | -1232.700 | -276.918
el-salam-hospital: 5114.920 | 4375.090 | 0.000 | 76.380 | 2150.932
el-shorta-hospital: 677.510 | 0.000 | -1369.100 | -1292.720 | -855.998
el-zerayeen-hospital: 3400.340 | 2848.610 | -0.000 | 0.000 | 1121.271
el-zhraa-hospital: 0.000 | 516.670 | -1973.200 | -1896.820 | -788.339
essam-el-shrief-el-tkasosy-hospital: 4092.490 | 3352.660 | -76.380 | 0.000 | 1818.492
osm-node-14078009201: 4489.910 | 3750.080 | 0.000 | 397.420 | 1633.027
sant-maria-hospital: 0.000 | 0.000 | -2046.610 | -1970.230 | -1247.648
```

Allocation after the iteration (kits):

```
al-mabara-hospital: 0.000 | 20.000 | 0.000 | 0.000 | 0.000
al-rowad: 0.000 | 0.000 | 10.000 | 0.000 | 0.000
arc-angle-mikhael-hospital: 0.000 | 0.000 | 0.000 | 10.000 | 0.000
asyut-chest-hospital: 0.000 | 0.000 | 0.000 | 0.000 | 10.000
el-akaad-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
el-aksaa-hospital: 0.000 | 0.000 | 10.000 | 0.000 | 0.000
el-hayah-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
el-nseem-dr-trez-mansour-hospital: 0.000 | 0.000 | 0.000 | 10.000 | 0.000
el-reda-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
el-safaa-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
el-salam-hospital: 0.000 | 0.000 | 10.000 | 0.000 | 0.000
el-shorta-hospital: 0.000 | 10.000 | 0.000 | 0.000 | 0.000
el-zerayeen-hospital: 0.000 | 0.000 | 0.000 | 10.000 | 0.000
el-zhraa-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
essam-el-shrief-el-tkasosy-hospital: 0.000 | 0.000 | 0.000 | 10.000 | 0.000
osm-node-14078009201: 0.000 | 0.000 | 10.000 | 0.000 | 0.000
sant-maria-hospital: 0.000 | 10.000 | 0.000 | 0.000 | 0.000
```

#### MODI iteration 3

u = `[0.0, -666.6314834380837, -1121.271537274853, 0.0, 721.548462725147, 826.6688862410724, 276.91846272514704, -1690.729564828127, 790.350080146235, 276.91846272514704, -104.3215150107435, 855.9984627251472, -1121.2714912479673, 788.3386051523962, -1818.491537274853, 413.58336956421635, 1247.648469906815]`; v = `[-276.91846272514704, 0.0, 666.6314834380837, 2074.551515010743, 0.0]`

Entering cell: **el-salam-hospital -> Z4**, reduced cost **-1970.230**, theta **0.000**, degenerate **True**, leaving cell **al-mabara-hospital -> Z4**.

Cycle: (el-salam-hospital,Z4) -> (el-salam-hospital,Z3) -> (sant-maria-hospital,Z3) -> (sant-maria-hospital,Z2) -> (al-mabara-hospital,Z2) -> (al-mabara-hospital,Z4)

Reduced-cost table (rows are sources; columns are destinations):

```
al-mabara-hospital: 2570.250 | 0.000 | 2046.610 | 0.000 | 0.000
al-rowad: 4156.830 | 3417.000 | 0.000 | -203.150 | 666.631
arc-angle-mikhael-hospital: 3400.340 | 2848.610 | 2046.610 | 0.000 | 1121.272
asyut-chest-hospital: 1943.518 | 1943.518 | 1943.518 | -26.712 | 0.000
el-akaad-hospital: 0.000 | 763.390 | 9.570 | -1960.660 | -721.548
el-aksaa-hospital: 695.330 | 912.050 | 0.000 | -1848.930 | -826.669
el-hayah-hospital: 0.000 | 1064.290 | 737.530 | -1232.700 | -276.918
el-nseem-dr-trez-mansour-hospital: 4092.490 | 3352.660 | 1970.230 | 0.000 | 1690.730
el-reda-hospital: 0.000 | 516.670 | 73.410 | -1896.820 | -790.350
el-safaa-hospital: 0.000 | 1064.290 | 737.530 | -1232.700 | -276.918
el-salam-hospital: 3068.310 | 2328.480 | 0.000 | -1970.230 | 104.322
el-shorta-hospital: 677.510 | 0.000 | 677.510 | -1292.720 | -855.998
el-zerayeen-hospital: 3400.340 | 2848.610 | 2046.610 | 0.000 | 1121.271
el-zhraa-hospital: 0.000 | 516.670 | 73.410 | -1896.820 | -788.339
essam-el-shrief-el-tkasosy-hospital: 4092.490 | 3352.660 | 1970.230 | 0.000 | 1818.492
osm-node-14078009201: 2443.300 | 1703.470 | 0.000 | -1649.190 | -413.583
sant-maria-hospital: 0.000 | 0.000 | 0.000 | -1970.230 | -1247.648
```

Allocation after the iteration (kits):

```
al-mabara-hospital: 0.000 | 20.000 | 0.000 | 0.000 | 0.000
al-rowad: 0.000 | 0.000 | 10.000 | 0.000 | 0.000
arc-angle-mikhael-hospital: 0.000 | 0.000 | 0.000 | 10.000 | 0.000
asyut-chest-hospital: 0.000 | 0.000 | 0.000 | 0.000 | 10.000
el-akaad-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
el-aksaa-hospital: 0.000 | 0.000 | 10.000 | 0.000 | 0.000
el-hayah-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
el-nseem-dr-trez-mansour-hospital: 0.000 | 0.000 | 0.000 | 10.000 | 0.000
el-reda-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
el-safaa-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
el-salam-hospital: 0.000 | 0.000 | 10.000 | 0.000 | 0.000
el-shorta-hospital: 0.000 | 10.000 | 0.000 | 0.000 | 0.000
el-zerayeen-hospital: 0.000 | 0.000 | 0.000 | 10.000 | 0.000
el-zhraa-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
essam-el-shrief-el-tkasosy-hospital: 0.000 | 0.000 | 0.000 | 10.000 | 0.000
osm-node-14078009201: 0.000 | 0.000 | 10.000 | 0.000 | 0.000
sant-maria-hospital: 0.000 | 10.000 | 0.000 | 0.000 | 0.000
```

#### MODI iteration 4

u = `[0.0, -666.6314834380837, 848.9584627251464, 0.0, 721.548462725147, 826.6688862410724, 276.91846272514704, 279.5004351718726, 790.350080146235, 276.91846272514704, -104.3215150107435, 855.9984627251472, 848.9585087520321, 788.3386051523962, 151.73846272514658, 413.58336956421635, 1247.648469906815]`; v = `[-276.91846272514704, 0.0, 666.6314834380837, 104.3215150107435, 0.0]`

Entering cell: **sant-maria-hospital -> DUMMY_UNUSED_SUPPLY**, reduced cost **-1247.648**, theta **0.000**, degenerate **True**, leaving cell **al-mabara-hospital -> DUMMY_UNUSED_SUPPLY**.

Cycle: (sant-maria-hospital,DUMMY_UNUSED_SUPPLY) -> (sant-maria-hospital,Z2) -> (al-mabara-hospital,Z2) -> (al-mabara-hospital,DUMMY_UNUSED_SUPPLY)

Reduced-cost table (rows are sources; columns are destinations):

```
al-mabara-hospital: 2570.250 | 0.000 | 2046.610 | 1970.230 | 0.000
al-rowad: 4156.830 | 3417.000 | 0.000 | 1767.080 | 666.631
arc-angle-mikhael-hospital: 1430.110 | 878.380 | 76.380 | 0.000 | -848.958
asyut-chest-hospital: 1943.518 | 1943.518 | 1943.518 | 1943.518 | 0.000
el-akaad-hospital: 0.000 | 763.390 | 9.570 | 9.570 | -721.548
el-aksaa-hospital: 695.330 | 912.050 | 0.000 | 121.300 | -826.669
el-hayah-hospital: 0.000 | 1064.290 | 737.530 | 737.530 | -276.918
el-nseem-dr-trez-mansour-hospital: 2122.260 | 1382.430 | 0.000 | 0.000 | -279.500
el-reda-hospital: 0.000 | 516.670 | 73.410 | 73.410 | -790.350
el-safaa-hospital: 0.000 | 1064.290 | 737.530 | 737.530 | -276.918
el-salam-hospital: 3068.310 | 2328.480 | 0.000 | 0.000 | 104.322
el-shorta-hospital: 677.510 | 0.000 | 677.510 | 677.510 | -855.998
el-zerayeen-hospital: 1430.110 | 878.380 | 76.380 | 0.000 | -848.959
el-zhraa-hospital: 0.000 | 516.670 | 73.410 | 73.410 | -788.339
essam-el-shrief-el-tkasosy-hospital: 2122.260 | 1382.430 | 0.000 | 0.000 | -151.738
osm-node-14078009201: 2443.300 | 1703.470 | 0.000 | 321.040 | -413.583
sant-maria-hospital: 0.000 | 0.000 | 0.000 | 0.000 | -1247.648
```

Allocation after the iteration (kits):

```
al-mabara-hospital: 0.000 | 20.000 | 0.000 | 0.000 | 0.000
al-rowad: 0.000 | 0.000 | 10.000 | 0.000 | 0.000
arc-angle-mikhael-hospital: 0.000 | 0.000 | 0.000 | 10.000 | 0.000
asyut-chest-hospital: 0.000 | 0.000 | 0.000 | 0.000 | 10.000
el-akaad-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
el-aksaa-hospital: 0.000 | 0.000 | 10.000 | 0.000 | 0.000
el-hayah-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
el-nseem-dr-trez-mansour-hospital: 0.000 | 0.000 | 0.000 | 10.000 | 0.000
el-reda-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
el-safaa-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
el-salam-hospital: 0.000 | 0.000 | 10.000 | 0.000 | 0.000
el-shorta-hospital: 0.000 | 10.000 | 0.000 | 0.000 | 0.000
el-zerayeen-hospital: 0.000 | 0.000 | 0.000 | 10.000 | 0.000
el-zhraa-hospital: 10.000 | 0.000 | 0.000 | 0.000 | 0.000
essam-el-shrief-el-tkasosy-hospital: 0.000 | 0.000 | 0.000 | 10.000 | 0.000
osm-node-14078009201: 0.000 | 0.000 | 10.000 | 0.000 | 0.000
sant-maria-hospital: 0.000 | 10.000 | 0.000 | 0.000 | 0.000
```

### MODI final checks

Final potentials: u = `[0.0, -666.6314834380837, 848.9584627251464, 1247.648469906815, 721.548462725147, 826.6688862410724, 276.91846272514704, 279.5004351718726, 790.350080146235, 276.91846272514704, -104.3215150107435, 855.9984627251472, 848.9585087520321, 788.3386051523962, 151.73846272514658, 413.58336956421635, 1247.648469906815]`; v = `[-276.91846272514704, 0.0, 666.6314834380837, 104.3215150107435, -1247.648469906815]`

Final basic cells: `[(0, 1), (1, 2), (2, 3), (3, 4), (4, 0), (5, 2), (6, 0), (7, 3), (8, 0), (9, 0), (10, 2), (10, 3), (11, 1), (12, 3), (13, 0), (14, 3), (15, 2), (16, 0), (16, 1), (16, 2), (16, 4)]`

Final reduced-cost table:

```
al-mabara-hospital: 2570.250 | 0.000 | 2046.610 | 1970.230 | 1247.648
al-rowad: 4156.830 | 3417.000 | 0.000 | 1767.080 | 1914.280
arc-angle-mikhael-hospital: 1430.110 | 878.380 | 76.380 | 0.000 | 398.690
asyut-chest-hospital: 695.870 | 695.870 | 695.870 | 695.870 | 0.000
el-akaad-hospital: 0.000 | 763.390 | 9.570 | 9.570 | 526.100
el-aksaa-hospital: 695.330 | 912.050 | 0.000 | 121.300 | 420.980
el-hayah-hospital: 0.000 | 1064.290 | 737.530 | 737.530 | 970.730
el-nseem-dr-trez-mansour-hospital: 2122.260 | 1382.430 | 0.000 | 0.000 | 968.148
el-reda-hospital: 0.000 | 516.670 | 73.410 | 73.410 | 457.298
el-safaa-hospital: 0.000 | 1064.290 | 737.530 | 737.530 | 970.730
el-salam-hospital: 3068.310 | 2328.480 | 0.000 | 0.000 | 1351.970
el-shorta-hospital: 677.510 | 0.000 | 677.510 | 677.510 | 391.650
el-zerayeen-hospital: 1430.110 | 878.380 | 76.380 | 0.000 | 398.690
el-zhraa-hospital: 0.000 | 516.670 | 73.410 | 73.410 | 459.310
essam-el-shrief-el-tkasosy-hospital: 2122.260 | 1382.430 | 0.000 | 0.000 | 1095.910
osm-node-14078009201: 2443.300 | 1703.470 | 0.000 | 321.040 | 834.065
sant-maria-hospital: 0.000 | 0.000 | 0.000 | 0.000 | 0.000
```

A negative reduced cost in a non-basic admissible cell would mean that the MODI optimality test had not yet passed. The report and verifier check this explicitly.

### Transportation method comparison

| method | feasible | status | objective (kit-metres) | unmet | unused | iterations | seconds |
|---|---|---|---:|---:|---:|---:|---:|
| NWC | True | complete | 266837.658 | 0 | 10 | 17 | 0.000169 |
| least-cost | True | complete | 107473.758 | 0 | 10 | 17 | 0.002077 |
| VAM | True | complete | 92553.958 | 0 | 10 | 17 | 0.006384 |
| MODI | True | optimal | 92553.958 | 0 | 10 | 4 | 0.001016 |
| exact-MILP | True | optimal (independent MILP) | 92553.958 | 0 | 10 | 0 | 0.004284 |

NWC and least-cost are comparison baselines; VAM is the initial solution; MODI is applied to the VAM allocation. The exact tableau MILP is an independent check of `Z0` and the final MODI objective. It does not enforce lane capacities.

## 5. Road-capacitated network result

### Road-capacitated network plan

| field | value |
|---|---|
| MILP status | optimal |
| solver success | True |
| message | Optimization terminated successfully. (HiGHS Status 7: Optimal) |
| variables / constraints | 156 / 587 |
| solver time [s] | 0.005178 |
| solver objective | 9888.711 |
| kit vehicle-metres | 9255.396 |
| patient vehicle-metres | 633.315 |
| total vehicle-metres | 9888.711 |
| vehicles used / fleet | 35 / 48 |
| unmet kit units | 0 |
| unmet patient transfers | 0 |
| unused kit supply | 10 |
| unused receiving beds | 71 |

`feasible` means all physical checks pass and no demand is unmet. `optimal` here means optimal for the stated network MILP, not a proof for every possible operational objective.

#### Fleet assignment

| zone | vehicles used | kit trips to zone | patient trips from zone |
|---|---:|---:|---:|
| Z1 | 11 | 5 | 6 |
| Z2 | 8 | 4 | 4 |
| Z3 | 8 | 4 | 4 |
| Z4 | 8 | 4 | 4 |

#### Selected kit trips

| source | zone | trips | kits | distance [m] | time [s] | lanes |
|---|---|---:|---:|---:|---:|---:|
| al-mabara-hospital | Z2 | 2 | 20 | 0.000 | 0.0 | 1 |
| al-rowad | Z3 | 1 | 10 | 0.000 | 0.0 | 1 |
| arc-angle-mikhael-hospital | Z4 | 1 | 10 | 953.280 | 55.5 | 22 |
| el-akaad-hospital | Z1 | 1 | 10 | 444.630 | 27.8 | 10 |
| el-aksaa-hospital | Z3 | 1 | 10 | 1493.300 | 79.2 | 50 |
| el-hayah-hospital | Z1 | 1 | 10 | 0.000 | 0.0 | 1 |
| el-nseem-dr-trez-mansour-hospital | Z4 | 1 | 10 | 383.822 | 17.3 | 11 |
| el-reda-hospital | Z1 | 1 | 10 | 513.432 | 36.9 | 10 |
| el-safaa-hospital | Z1 | 1 | 10 | 0.000 | 0.0 | 1 |
| el-salam-hospital | Z4 | 1 | 10 | 0.000 | 0.0 | 1 |
| el-shorta-hospital | Z2 | 1 | 10 | 855.998 | 30.8 | 12 |
| el-zerayeen-hospital | Z4 | 1 | 10 | 953.280 | 55.5 | 22 |
| el-zhraa-hospital | Z1 | 1 | 10 | 511.420 | 36.8 | 10 |
| essam-el-shrief-el-tkasosy-hospital | Z3 | 1 | 10 | 818.370 | 35.1 | 22 |
| osm-node-14078009201 | Z3 | 1 | 10 | 1080.215 | 38.9 | 24 |
| sant-maria-hospital | Z2 | 1 | 10 | 1247.648 | 56.1 | 17 |

#### Selected patient transfers

| origin zone | receiving hospital | transfers | distance [m] | time [s] | lanes |
|---|---|---:|---:|---:|---:|
| Z1 | el-safaa-hospital | 6 | 0.000 | 0.0 | 1 |
| Z2 | al-mabara-hospital | 4 | 0.000 | 0.0 | 1 |
| Z3 | al-rowad | 3 | 0.000 | 0.0 | 1 |
| Z3 | osm-node-14078009201 | 1 | 633.315 | 22.8 | 16 |
| Z4 | el-salam-hospital | 4 | 0.000 | 0.0 | 1 |

A zero distance means that the origin zone anchor and the receiving facility share a snapped lane access point (or are the same facility); see the access-point limitation in section 9.

#### Constraint checks (recomputed independently after the solve)

| check | result |
|---|---|
| bed_capacity_respected | PASS |
| demand_met | PASS |
| fleet_limit_respected | PASS |
| integer_allocations | PASS |
| kit_demand_matched | PASS |
| patient_demand_matched | PASS |
| prohibited_lanes_avoided | PASS |
| road_capacity_respected | PASS |
| routes_continuous | PASS |
| solver_success | PASS |
| supply_within_limits | PASS |
| zone_trip_balance | PASS |

#### Lane loads (top 15 by ambulance flow; complete table in `or_lane_loads.csv`)

| lane | edge | type | background | ambulance | total | capacity | slack |
|---|---|---|---:|---:|---:|---:|---:|
| 398151290#6_0 | 398151290#6 | highway.residential | 0.000 | 11.000 | 11.000 | 16800.000 | 16789.000 |
| 738247820#2_0 | 738247820#2 | highway.primary | 0.000 | 8.000 | 8.000 | 33600.000 | 33592.000 |
| -778635853#6_0 | -778635853#6 | highway.secondary | 0.000 | 8.000 | 8.000 | 28800.000 | 28792.000 |
| 820440644#4_0 | 820440644#4 | highway.tertiary | 0.000 | 7.000 | 7.000 | 24000.000 | 23993.000 |
| 700820443#3_0 | 700820443#3 | highway.residential | 0.000 | 3.000 | 3.000 | 16800.000 | 16797.000 |
| 700820443#2_0 | 700820443#2 | highway.residential | 0.000 | 3.000 | 3.000 | 16800.000 | 16797.000 |
| 700820443#1_0 | 700820443#1 | highway.residential | 0.000 | 3.000 | 3.000 | 16800.000 | 16797.000 |
| E23_1 | E23 |  | 0.000 | 2.000 | 2.000 | 19200.000 | 19198.000 |
| 97405586#5_0 | 97405586#5 | highway.tertiary | 0.000 | 2.000 | 2.000 | 24000.000 | 23998.000 |
| 97405586#4_0 | 97405586#4 | highway.tertiary | 0.000 | 2.000 | 2.000 | 24000.000 | 23998.000 |
| 97405586#3_0 | 97405586#3 | highway.tertiary | 0.000 | 2.000 | 2.000 | 24000.000 | 23998.000 |
| 94168784#1_0 | 94168784#1 | highway.residential | 0.000 | 2.000 | 2.000 | 16800.000 | 16798.000 |
| 94168784#0_0 | 94168784#0 | highway.residential | 0.000 | 2.000 | 2.000 | 16800.000 | 16798.000 |
| 834617697_0 | 834617697 | highway.tertiary | 0.000 | 2.000 | 2.000 | 24000.000 | 23998.000 |
| 834617696#2_1 | 834617696#2 | highway.tertiary | 0.000 | 2.000 | 2.000 | 24000.000 | 23998.000 |


## 6. Routing algorithm comparison

### Routing algorithm comparison

These are measured examples from this run, not fixed performance claims. All three algorithms must return the same shortest distance for the same pair; timing differences are implementation effects.

| source | target | algorithm | found | distance [m] | time [s] | settled states | search time [s] |
|---|---|---|---:|---:|---:|---:|---:|
| asyut-chest-hospital | al-mabara-hospital | Dijkstra | yes | 1943.518 | 79.579 | 420 | 0.002115900 |
| asyut-chest-hospital | al-mabara-hospital | A* | yes | 1943.518 | 79.579 | 158 | 0.001125900 |
| asyut-chest-hospital | al-mabara-hospital | Bellman-Ford | yes | 1943.518 | 79.579 | 4619 | 0.107218600 |
| al-mabara-hospital | al-rowad | Dijkstra | yes | 2713.241 | 135.360 | 1107 | 0.005384300 |
| al-mabara-hospital | al-rowad | A* | yes | 2713.241 | 135.360 | 413 | 0.002315400 |
| al-mabara-hospital | al-rowad | Bellman-Ford | yes | 2713.241 | 135.360 | 4619 | 0.106527000 |
| al-rowad | el-salam-hospital | Dijkstra | yes | 1204.770 | 75.686 | 379 | 0.001796200 |
| al-rowad | el-salam-hospital | A* | yes | 1204.770 | 75.686 | 203 | 0.001027100 |
| al-rowad | el-salam-hospital | Bellman-Ford | yes | 1204.770 | 75.686 | 4618 | 0.069736300 |
| arc-angle-mikhael-hospital | el-hayah-hospital | Dijkstra | yes | 2002.150 | 112.741 | 1185 | 0.005673400 |
| arc-angle-mikhael-hospital | el-hayah-hospital | A* | yes | 2002.150 | 112.741 | 487 | 0.002594200 |
| arc-angle-mikhael-hospital | el-hayah-hospital | Bellman-Ford | yes | 2002.150 | 112.741 | 4620 | 0.072017500 |

All compared pairs returned consistent distances. The route validity and prohibited-lane checks are repeated in the network verification.


## 7. Validation and acceptance

| area | result / evidence |
|---|---|
| conservation | all transportation row/column sums checked independently |
| 48-ambulance limit | network check and fleet table above |
| prohibited lanes | excluded from search; selected routes report no hits |
| lane capacities | every selected route is assigned to every traversed lane; background is added separately |
| integer assignments | kit trips, patient transfers, and vehicles are integral |
| bed/resource shortages | unmet kit/patient variables are explicit; unused supply/beds are reported |
| feasible/infeasible cases | the exact tableau solver and the network MILP both report status; a failure is never presented as success |
| VAM penalties/allocations/Z0 | full trace, allocation tables, and `Z0` above |
| MODI optimality/constraints | potentials, reduced costs, cycles, forbidden-cell preservation, and final check above |
| Dijkstra/A*/Bellman-Ford | same distance on the compared pairs; route validity checked independently |
| small exact validation | `tools/verify_or.py` brute-forces small tableaux and compares exact MILP |

### Errors and warnings from this run

- No errors.
- WARNING: hospital antar-ent-clinic has 2 free bed(s) but is not a patient destination: not an emergency facility under the clinic policy
- WARNING: hospital asyout-hospital-for-mental-health has 2 free bed(s) but is not a patient destination: receiving lane cannot be reached from the main network
- WARNING: hospital el-fayrouz-hospital has 2 free bed(s) but is not a patient destination: receiving lane cannot be reached from the main network
- WARNING: hospital el-salama-hospital has 3 free bed(s) but is not a patient destination: receiving lane cannot be reached from the main network
- WARNING: hospital osm-node-10883658615 has 2 free bed(s) but is not a patient destination: not an emergency facility under the clinic policy

## 8. Reproduce

```powershell
& 'C:\Users\gamer\AppData\Local\Programs\Python\Python310\python.exe' run.py or-plan
& 'C:\Users\gamer\AppData\Local\Programs\Python\Python310\python.exe' tools\verify_or.py
```

Optional inputs: `--or-config config/or_planning.json`, `--out-dir reports`, `--json`, `--no-routing-comparison`, `--no-write`.

The generated artifacts are deterministic in content apart from the UTC generation timestamp and measured runtimes. The synthetic input files are the source of every non-derived quantity.

## 9. Missing data and limitations

- Real free-bed counts, kit stock, zone kit demand, patient-transfer demand, measured background lane flow, and measured lane capacity are not present in the repository. The shipped values are synthetic and must be replaced before operational use.
- The road-capacity value is a planning estimate from lane count and road type. It is not a field measurement.
- Costs use snapped lane access points; facility-entrance or walking offsets are not added. Two distinct facilities can share one snapped access point, giving a modelled road distance of zero even when their entrances differ.
- The network MILP selects flows over one Dijkstra candidate route per source/zone or zone/hospital pair. It does not enumerate alternative paths or reroute dynamically around congestion.
- The transportation tableau treats a zone anchor as one delivery point. The network model routes trips to that anchor; it does not split a zone's demand across multiple internal destinations.
- The fleet model is a conservative one-trip-per-ambulance-per-day assumption. It does not model shift scheduling, refuelling, or multiple trips by the same vehicle.
- Fleet zone accounting charges kit trips to the destination zone and patient transfers to the origin zone. Empty repositioning and return legs are not modelled.
- Standard MODI is used only on the kit-only tableau. It is not claimed to enforce lane capacities or the fleet limit.
- The network MILP's `optimal` status is optimality for the stated integer model and objective. It is not a claim that the model captures every real operational objective.
- The SVG plot is a schematic fit to the selected routes; it is not a survey-grade geographic projection.

## 10. Source files

| item | path |
|---|---|
| OR rules | `D:\AssiutHospitals\config\or_planning.json` |
| OR test data | `D:\AssiutHospitals\data\or_test_data.json` |
| dispatch/zones | `D:\AssiutHospitals\config\dispatch.json` |
| synthetic capacity | `SYNTHETIC` |
| SUMO network | `D:\Dashboard - Copy\sumo\Version 3 George.net.xml` |

## 11. Generated artifacts

| artifact | file |
|---|---|
| this report | `or_report.md` |
| full machine-readable plan | `or_plan.json` |
| hospital roles | `or_hospitals.csv` |
| zones | `or_zones.csv` |
| kit cost table | `or_kit_cost_table.csv` |
| VAM trace | `or_vam_trace.csv` |
| MODI trace | `or_modi_trace.csv` |
| transportation comparison | `or_transport_comparison.csv` |
| routing comparison | `or_routing_comparison.csv` |
| selected kit flows | `or_network_kit_flows.csv` |
| selected patient flows | `or_network_patient_flows.csv` |
| lane loads | `or_lane_loads.csv` |
| network checks | `or_checks.csv` |
| selected-route sketch | `or_routes.svg` |

