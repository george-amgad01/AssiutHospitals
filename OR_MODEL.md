# Operations Research Model - Assiut Emergency Resource Distribution

> This document defines the mathematical model **before** the implementation.
> Every quantity that is not present in the repository is marked `SYNTHETIC`
> and is loaded from a configurable test-data file.  The model is a planning
> model, not a claim about real hospital stocks or measured road capacity.

## 1. Scope and planning assumptions

| Item | Value | Source / status |
| --- | ---: | --- |
| Planning horizon | one day (24 h) | owner specification |
| Hospitals in the OR model | 25 | the 25 routable facilities in `data/hospitals.json`; 3 outside-network facilities and 1 non-routable in-network facility are map-only |
| Service zones | 4 | owner-approved `11/3/3/9` zones in `config/dispatch.json` |
| Ambulance fleet | 48 | fixed owner assumption |
| Ambulance trips per vehicle per day | 1 | conservative planning assumption (no multi-trip shift model) |
| Kits per ambulance trip | 10 | configurable test assumption |
| Resource categories | medical kits, free emergency beds, ambulances | separate units and roles (see below) |
| Road cost | free-flow shortest distance | owner decision: no congestion adjustment |
| Background road traffic | separate from the 48 ambulances | no measured lane flow is available; the shipped test value is zero |
| Road capacity | estimated from lane count/road type | **SYNTHETIC ESTIMATE** where no measured capacity exists |

The model does **not** treat free hospital beds as a commodity that is shipped
to zones.  Beds are receiving capacity at hospital destinations.  Kits are an
indivisible commodity moved by ambulance trips.  Ambulances are integer
vehicles, and ordinary background traffic is a separate lane load.

## 2. Sets and indices

| Symbol | Meaning |
| --- | --- |
| \(H\) | set of 25 routable hospitals; \(i \in H\) |
| \(H_s \subseteq H\) | hospitals with positive kit supply and a route that can leave the facility |
| \(H_b \subseteq H\) | hospitals that can receive patients (emergency department, free bed, and an inbound road route) |
| \(Z\) | set of four service zones; \(j \in Z\) |
| \(E\) | set of lane-level road edges in the SUMO network |
| \(E_p \subseteq E\) | prohibited lanes (vehicle-class restriction or explicit closure) |
| \(K\) | medical-kit trips |
| \(P\) | patient-transfer trips |

Zone boundaries and hospital-to-zone assignment are read verbatim from
`config/dispatch.json`; the OR model does not derive an assignment.

## 3. Parameters and units

| Symbol | Definition | Unit |
| --- | --- | --- |
| \(S_i\) | kit supply at hospital \(i\) | kits (integer) |
| \(D_j\) | kit demand of zone \(j\) | kits (integer) |
| \(P_j\) | patient-transfer demand of zone \(j\) | patients (integer) |
| \(B_i\) | free emergency beds at hospital \(i\) | beds (integer, receiving capacity) |
| \(Q\) | kits carried by one kit-delivery trip | kits/trip |
| \(c_{ij}\) | shortest feasible road distance \(i \to\) zone \(j\) anchor | metres |
| \(c'_{ji}\) | shortest feasible road distance zone \(j\) anchor \(\to i\) | metres |
| \(t_{ij}, t'_{ji}\) | free-flow travel time for the same routes | seconds |
| \(C_e\) | permitted vehicle crossings on lane \(e\) in the planning interval | vehicles/day |
| \(B_e\) | ordinary background vehicle flow on lane \(e\), excluding the 48 ambulances | vehicles/day |
| \(a_{eij}\) | 1 if the \(i \to j\) route uses lane \(e\), otherwise 0 | indicator |
| \(a'_{eji}\) | 1 if the \(j \to i\) patient route uses lane \(e\), otherwise 0 | indicator |
| \(F\) | available ambulance fleet | 48 vehicles |
| \(L\) | maximum one-trip duration (shift) | seconds/trip |

## 4. Decision variables

| Variable | Meaning | Domain |
| --- | --- | --- |
| \(x_{ij}\) | kits sent from hospital \(i\) to zone \(j\) | integer \(\ge 0\), multiple of \(Q\) |
| \(y_{ij}\) | kit-delivery trips from \(i\) to \(j\): \(x_{ij}=Qy_{ij}\) | integer \(\ge 0\) |
| \(u_{ji}\) | patients transferred from zone \(j\) to hospital \(i\) | integer \(\ge 0\) |
| \(z_j\) | ambulances allocated to zone \(j\) | integer \(\ge 0\) |
| \(m^{K}_j\) | unmet kit demand in zone \(j\) | integer \(\ge 0\) |
| \(m^{P}_j\) | unmet patient-transfer demand in zone \(j\) | integer \(\ge 0\) |

The network-constrained model uses \(y\), \(u\), \(z\), and the two unmet
variables.  The standard transportation tableau uses \(x\) directly.

## 5. Primary objective

The primary **transportation-tableau** objective is

\[
\min Z_K = \sum_{i\in H_s}\sum_{j\in Z} c_{ij}x_{ij},
\]

measured in **kit-metres**.  Because one trip carries \(Q\) kits, the equivalent
trip-distance component is

\[
Z^{v}_K = \sum_{i,j} c_{ij}y_{ij} = Z_K/Q.
\]

The patient-transfer component is reported separately:

\[
Z_P = \sum_{j\in Z}\sum_{i\in H_b} c'_{ji}u_{ji}.
\]

The network planner minimizes the **vehicle-metre** objective

\[
\min Z_N = Z^{v}_K + Z_P
          = \sum_{i,j} c_{ij}y_{ij}
          + \sum_{j,i} c'_{ji}u_{ji}.
\]

\(Z_K\) is used for the transportation tableau and its exact-MILP check.  \(Z_N\)
is used for the lane-capacitated network plan.  They are reported separately
with their units so that kit-metres and vehicle-metres are never confused.

## 6. Constraints

### 6.1 Kit supply

\[
\sum_{j\in Z} Qy_{ij} \le S_i \qquad \forall i\in H_s.
\]

Kits are indivisible.  Supplies and demands are multiples of \(Q\); the
validator rejects a data file that violates this unit rule.

### 6.2 Kit demand and unmet demand

\[
\sum_{i\in H_s} Qy_{ij} + m^{K}_j = D_j \qquad \forall j\in Z.
\]

If \(m^{K}_j>0\), the result is **partial** and the unmet quantity is reported.
It is never silently called feasible.

### 6.3 Patient demand

\[
\sum_{i\in H_b} u_{ji} + m^{P}_j = P_j \qquad \forall j\in Z.
\]

### 6.4 Hospital bed capacity (receiving side only)

\[
\sum_{j\in Z} u_{ji} \le B_i \qquad \forall i\in H_b.
\]

\(B_i\) is not a shipped supply and does not appear on the supply side of the
kit problem.

### 6.5 Ambulance fleet and zone allocation

\[
\sum_{j\in Z} z_j \le 48,
\]

\[
\sum_{i\in H_s} y_{ij} + \sum_{i\in H_b} u_{ji} \le z_j
\qquad \forall j\in Z.
\]

Each ambulance makes at most one trip in the planning day.  A route whose
free-flow duration exceeds the shift limit \(L\) is not offered as a variable
and is reported as unavailable.  \(z_j\) is a zone-level fleet count: a kit trip
is charged to its destination zone and a patient transfer to its origin zone.
Empty repositioning and return legs are outside this model.

### 6.6 Road capacity, background traffic, and prohibited lanes

For every lane \(e\),

\[
B_e + \sum_{i,j} a_{eij}y_{ij}
      + \sum_{j,i} a'_{eji}u_{ji} \le C_e.
\]

The background term is kept separate from the ambulance terms in the report.
If \(e\in E_p\), the lane is removed from the routing graph and every
\(a_{eij}=a'_{eji}=0\) by construction.  A finite penalty is **not** used as a
substitute for prohibition.

### 6.7 Non-negativity and integrality

\[
y_{ij},u_{ji},z_j,m^{K}_j,m^{P}_j \in \mathbb{Z}_{\ge 0}.
\]

There are no fractional ambulances, patients, or kit crates.

## 7. Standard transportation model (VAM / least-cost / NWC / MODI)

The auditable transportation tableau is the kit-only model:

* rows: active hospital sources \(H_s\) (supply \(S_i\));
* columns: the four zones (demand \(D_j\));
* cost \(c_{ij}\): Dijkstra shortest road distance in metres;
* prohibited cells: no feasible lane-level route;
* cell caps: supported for test instances, but not used in the shipped kit
  tableau; shared road capacities are enforced by the network-constrained
  model, not by the ordinary tableau.

Cell caps are honoured by the allocation routines and by the exact tableau MILP.
If a cap binds during standard MODI, the ordinary u-v basis cannot represent the
bounded cell without a bounded-transport extension; the implementation raises an
explicit `TransportError` instead of claiming an optimality result.

If total supply exceeds total demand, a clearly labelled **dummy destination**
with zero cost absorbs unused supply.  If demand exceeds supply, a clearly
labelled **dummy source** exposes unmet demand.  The dummy quantities are never
mixed with real supplies or demands without a label.

The **north-west corner rule is strict**: if any cell is forbidden, it raises a
clear error instead of silently jumping over a cell, because a jump would no
longer be the north-west corner rule.  Least-cost and VAM skip forbidden and
saturated cells.  MODI keeps forbidden cells out of the basis.  The exact
tableau MILP is the reference method for forbidden cells and binding caps.
The planner records an explicit NWC-forbidden refusal or MODI-binding-cap
refusal as a method-limitation warning, not as a false network infeasibility;
the separate network MILP still decides whether the physical plan is feasible.

The standard tableau does not contain lane flows.  Therefore VAM, least-cost,
NWC, and MODI are **selection/initial-solution methods** for the transportation
model.  Their objective values are compared with the exact transportation
optimum, while the road-capacity-constrained solution is produced by the
MILP described in Section 8.

## 8. Network-constrained optimisation

The network-constrained planner is a mixed-integer linear program:

* integer trip variables \(y_{ij}\), \(u_{ji}\), and \(z_j\);
* kit-unit conversion \(x_{ij}=Qy_{ij}\);
* the constraints of Sections 6.1-6.7;
* lane-incidence coefficients \(a_{eij}\) and \(a'_{eji}\) reconstructed from
  the actual lane-level Dijkstra paths;
* unmet-demand variables \(m^{K}_j,m^{P}_j\) with a large objective penalty so
  a shortage is explicit rather than an unexplained infeasibility.

The solver is `scipy.optimize.milp` (HiGHS).  The result is independently
checked by the verifier by recomputing every route, every lane load, every
supply/demand balance, the bed capacity, and the fleet count.

## 9. Zone construction and data status

The four zones are the owner-approved rectangular zones from
`config/dispatch.json`.  The OR layer adds one **manual zone anchor** per zone:
a real hospital in that zone whose snapped lane belongs to the main strongly
connected component.  The anchor is the delivery/patient origin point used for
the distance matrix.  It is not a new supply or a fabricated coordinate.
Costs are measured between snapped lane access points, not facility entrances;
walking/entrance offsets are not added.  Two distinct facilities can therefore
share one snapped access point and have a modelled road distance of zero even
when their entrances differ.  This is an access-point artifact, not a measured
zero distance, and it is reported as a limitation.

Shipped quantities:

* 25 routable hospitals;
* 4 zones;
* 48 ambulances;
* 10 kits per kit trip;
* synthetic kit supply: 180 kits;
* synthetic kit demand: 170 kits (10 kits become unused supply);
* synthetic patient demand: 18 transfers;
* background lane flow: zero because no measured lane-level flow exists.

All synthetic values and the reason for each are in
`data/or_test_data.json`.  Replacing that file with owner data requires no code
change.

## 10. Missing real-world data and limitations

The following are **not** available in the repository and are therefore
documented assumptions, not measurements:

1. real kit stock at each hospital;
2. real kit demand and patient-transfer demand by zone;
3. measured lane-level road capacity;
4. measured background traffic per lane;
5. future closed/prohibited lanes for the planning day;
6. real free-bed counts (the existing capacity file is already labelled
   `SYNTHETIC`);
7. time windows, loading/unloading times, and multi-trip ambulance shifts;
8. a verified central depot; the zone anchor is a modelling convenience based
   on a real hospital location;
9. alternative route enumeration: the MILP selects flows over one Dijkstra
   candidate path per source/zone or zone/hospital pair, not every possible
   path, and does not reroute dynamically.

The model is suitable for reproducible course work and feasibility testing.
It must not be used for live dispatch until the synthetic inputs are replaced.

## 11. Validation requirements

The implementation must demonstrate:

* supply and demand conservation;
* at most 48 ambulances and integer vehicle counts;
* no route through a prohibited lane;
* no lane load above its estimated capacity;
* integer kit/patient allocations;
* correct VAM penalties, quantities, and \(Z_0\);
* MODI reduced costs and optimality for the standard tableau;
* agreement of Dijkstra, A*, and Bellman-Ford on sample routes;
* an exact small-instance check by enumeration or an independent MILP;
* explicit partial/infeasible results when demand, fleet, or capacity cannot
  be satisfied.

Run `python tools/verify_or.py` and `python run.py or-plan` to reproduce these
checks and the reports.
