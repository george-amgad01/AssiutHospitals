# Simulation options report

**Status: report only. No simulation was built.** This file is the requested
requirement 10 deliverable. It describes the realistic options, their inputs,
outputs, limitations and effort so the owner can choose one. Nothing here is
implemented in the project.

The dispatch tool itself is complete and validated without a simulation. The old
live simulation, its SSE stream, the 48 periodic flows and the old validation
command were removed by owner decision. `sumo/hospitals.rou.xml` is deliberately
empty.

---

## What a simulation would need to answer

A useful simulation must be explicit about its question. The dispatch tool
answers “which hospital is fastest under free-flow time?”. A simulation could
answer one or more of:

1. How do dispatch choices change when many ambulances compete for the same
   roads and hospitals?
2. How do queues and turnaround times behave when emergency capacity changes?
3. How sensitive is the chosen hospital to congestion, signal timing or blocked
   roads?
4. How does a dispatch policy compare with a baseline (nearest hospital,
   fixed assignment, random suitable hospital)?
5. What happens when the nearest suitable hospital becomes full during the run?

Without a defined question and a demand/capacity scenario, a simulation would
produce numbers that look precise but mean little. That is why no simulation was
built automatically.

---

## Option A — offline SUMO scenario with scripted demand

### Idea

Generate a fixed set of ambulance trips from the dispatch tool, write them to a
SUMO route file, and run SUMO once. Each trip starts at a chosen point, follows
the computed route to a hospital, and optionally returns. No live TraCI control
is needed during the run.

### Inputs

* the real network: `Version 3 George.net.xml`;
* a demand scenario written by the owner or generated from a documented list of
  start points and specialties;
* the existing base traffic routes (`project (1).rou.xml`) if background traffic
  is wanted;
* a fixed emergency-capacity snapshot, clearly labelled synthetic or real;
* a deterministic seed.

### Outputs

* per-trip arrival time, route length, waiting time;
* per-hospital arrivals and (if modelled) bed occupancy over time;
* aggregate travel-time distributions;
* comparison with the free-flow dispatch estimate.

### Advantages

* reproducible and easy to validate;
* no live control loop, no race conditions;
* fits the existing SUMO configuration and the real network;
* can be run headless on a laptop.

### Limitations

* demand is fixed in advance; it cannot react to hospital fullness;
* no live re-dispatch when a hospital fills;
* results depend heavily on the chosen background traffic and seed;
* it is still a simulation of assumptions, not real operations.

### Effort

Moderate: a route generator, a scenario file, a result parser and a report. It
must not reuse the removed 48 periodic flows; a new documented demand file would
have to be approved first.

---

## Option B — SUMO + TraCI dynamic dispatch

### Idea

Run SUMO with TraCI. A controller asks the validated `Dispatcher` for a hospital
when an ambulance is created or when its target becomes unavailable, inserts the
vehicle, monitors arrival, and updates capacity.

### Inputs

* Option A inputs, plus a live capacity state and a re-dispatch policy;
* a decision rule for “hospital became full / route blocked”;
* a defined dispatch trigger (call arrival process or fixed schedule);
* a controller loop and stop conditions.

### Outputs

* dynamic hospital load over time;
* ambulance response and turnaround times;
* counts of skipped/full hospitals and re-dispatches;
* comparison of policies under the same demand.

### Advantages

* can answer the interesting operational questions;
* reuses the existing class-aware lane graph, Dijkstra search and route builder;
* can expose the skip-and-continue behaviour under competition.

### Limitations

* substantially more complex and harder to validate;
* needs a real or explicitly synthetic capacity time series;
* TraCI control can hide bugs (vehicles not inserted, teleports, deadlocks);
* the current project deliberately has no live stream or live bed feed;
* a controller is a new subsystem, not a small extension.

### Effort

High: controller, capacity state, event handling, deadlock/teleport checks,
statistical runs, and a new validation contract.

---

## Option C — external discrete-event / queueing model

### Idea

Do not simulate every road lane. Model each hospital as a service station with
arrival, travel-time and treatment-time distributions, and model dispatch as a
policy over those distributions. Road travel times can be sampled from the
validated dispatch results or from a fitted distribution.

### Inputs

* a demand arrival process;
* travel-time distributions by origin/hospital pair (from measured routes);
* capacity and service-time distributions;
* a dispatch policy.

### Outputs

* waiting-time and utilization distributions;
* probability that a suitable hospital is full;
* policy comparison at low computational cost;
* sensitivity analysis.

### Advantages

* fast enough for many Monte Carlo replications;
* makes assumptions explicit;
* useful when the question is capacity/queueing rather than road geometry.

### Limitations

* not spatially exact; it does not reproduce SUMO traffic;
* results are only as good as the distributions;
* cannot validate lane-level routes or signal effects;
* needs real capacity/service data to be meaningful.

### Effort

Low to moderate for a small queueing model, but only if the owner accepts its
abstraction and supplies distributions. It should not be presented as a SUMO
study.

---

## Option D — no simulation

### Idea

Keep the project as a validated routing/selection tool. Use the measured
algorithm comparison and the dispatch API for decision support, and collect real
operational data separately before any simulation.

### Advantages

* no invented demand or capacity dynamics;
* no risk of presenting synthetic simulation output as evidence;
* the current deliverable is complete and independently validated.

### Limitations

* cannot study competition, queues or time-varying capacity;
* cannot compare operational policies under load.

### Effort

None.

---

## Cross-cutting requirements for any chosen option

Whichever option is selected, the following must be explicit before coding:

1. **Question and metrics.** What decision will the simulation inform?
2. **Demand.** Fixed list, arrival process, or real call log? Who owns it?
3. **Capacity.** Real time series, synthetic scenario, or fixed snapshot? It must
   be labelled in every output.
4. **Background traffic.** Use the existing base routes, a calibrated scenario,
   or no background traffic?
5. **Seeds and replications.** One deterministic run is not a statistical study.
6. **Warm-up and stop rules.** Especially for queue/occupancy metrics.
7. **Validation.** Compare simulated free-flow travel times with the already
   validated dispatch times before trusting congested results.
8. **Failure handling.** Teleports, collisions, stuck vehicles, full hospitals,
   and unreachable destinations must be counted, not silently dropped.
9. **Output location.** New files only; do not modify
   `D:\Dashboard - Copy\sumo\`.
10. **No fake data.** Any synthetic demand/capacity file must say `SYNTHETIC` in
    its source/notice fields and in the report.

---

## Recommendation (for owner decision, not an automatic choice)

If the owner needs a first simulation, **Option A** is the smallest defensible
step: it reuses the real network, keeps the validated routes, is reproducible,
and can be validated against the free-flow results. **Option B** is the only
option that can answer dynamic re-dispatch and hospital-fullness questions, but
it is a new subsystem and needs real capacity dynamics. **Option C** is useful
only for capacity/queueing questions and must not be described as a road
simulation. **Option D** is the correct choice if the question is not yet
defined.

The owner must choose the option and supply the missing demand/capacity inputs
before implementation begins.
