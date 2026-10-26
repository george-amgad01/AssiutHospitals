# Emergency dispatch algorithm comparison

Measured on the real Assiut SUMO network with the owner-approved start-zone-only search and free-flow travel times.

**Important:** Dijkstra, A* and Bellman-Ford are pathfinders. VAM, least-cost, north-west corner and MODI are transportation-problem selection methods; they choose a hospital and do not build a road route. Their route and travel time are taken from the Dijkstra matrix, and the Dijkstra matrix time is included in their runtime.

Generated: `2026-10-27T00:50:22`

## Summary

| Algorithm | Runs | Mean runtime (ms) | Mean route time (s) | Optimal | Verified | Failures |
|---|---:|---:|---:|---:|---:|---:|
| Dijkstra | 16 | 23.340 | 16.587 | 12 | 16 | 0 |
| A* | 16 | 10.757 | 16.587 | 12 | 16 | 0 |
| Bellman-Ford | 16 | 273.468 | 16.587 | 12 | 16 | 0 |
| VAM | 16 | 23.392 | 16.587 | 12 | 16 | 0 |
| Least-cost | 16 | 23.366 | 16.587 | 12 | 16 | 0 |
| North-west corner | 16 | 23.349 | 24.999 | 8 | 16 | 0 |
| MODI | 16 | 23.374 | 16.587 | 12 | 16 | 0 |

## Per-case results

| Origin | Zone | Specialty | Algorithm | Selected hospital | Runtime (ms) | Route time (s) | Length (m) | Edges | Optimal | Verified |
|---|---|---|---|---|---:|---:|---:|---:|---|---|
| asyut-chest-hospital | Z1 | general | Dijkstra | Asyut Chest Hospital | 24.128 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | general | A* | Asyut Chest Hospital | 16.534 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | general | Bellman-Ford | Asyut Chest Hospital | 347.742 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | general | VAM | Asyut Chest Hospital | 24.224 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | general | Least-cost | Asyut Chest Hospital | 24.182 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | general | North-west corner | Asyut Chest Hospital | 24.142 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | general | MODI | Asyut Chest Hospital | 24.167 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | trauma | Dijkstra | — | 22.967 | — | — | 0 | — | yes |
| asyut-chest-hospital | Z1 | trauma | A* | — | 0.805 | — | — | 0 | — | yes |
| asyut-chest-hospital | Z1 | trauma | Bellman-Ford | — | 404.563 | — | — | 0 | — | yes |
| asyut-chest-hospital | Z1 | trauma | VAM | — | 22.967 | — | — | 0 | — | yes |
| asyut-chest-hospital | Z1 | trauma | Least-cost | — | 22.967 | — | — | 0 | — | yes |
| asyut-chest-hospital | Z1 | trauma | North-west corner | — | 22.967 | — | — | 0 | — | yes |
| asyut-chest-hospital | Z1 | trauma | MODI | — | 22.967 | — | — | 0 | — | yes |
| asyut-chest-hospital | Z1 | cardiac | Dijkstra | Asyut Chest Hospital | 24.953 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | cardiac | A* | Asyut Chest Hospital | 15.822 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | cardiac | Bellman-Ford | Asyut Chest Hospital | 325.000 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | cardiac | VAM | Asyut Chest Hospital | 25.015 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | cardiac | Least-cost | Asyut Chest Hospital | 24.981 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | cardiac | North-west corner | Asyut Chest Hospital | 24.964 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | cardiac | MODI | Asyut Chest Hospital | 24.983 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | pediatric | Dijkstra | El Zhraa Hospital | 21.718 | 51.962 | 1226.4 | 16 | yes | yes |
| asyut-chest-hospital | Z1 | pediatric | A* | El Zhraa Hospital | 27.722 | 51.962 | 1226.4 | 16 | yes | yes |
| asyut-chest-hospital | Z1 | pediatric | Bellman-Ford | El Zhraa Hospital | 396.835 | 51.962 | 1226.4 | 16 | yes | yes |
| asyut-chest-hospital | Z1 | pediatric | VAM | El Zhraa Hospital | 21.853 | 51.962 | 1226.4 | 16 | yes | yes |
| asyut-chest-hospital | Z1 | pediatric | Least-cost | El Zhraa Hospital | 21.762 | 51.962 | 1226.4 | 16 | yes | yes |
| asyut-chest-hospital | Z1 | pediatric | North-west corner | El Hayah Hospital | 21.734 | 79.853 | 1707.7 | 24 | no | yes |
| asyut-chest-hospital | Z1 | pediatric | MODI | El Zhraa Hospital | 21.797 | 51.962 | 1226.4 | 16 | yes | yes |
| al-mabara-hospital | Z2 | general | Dijkstra | Al Mabara Hospital | 27.497 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | general | A* | Al Mabara Hospital | 11.704 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | general | Bellman-Ford | Al Mabara Hospital | 362.878 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | general | VAM | Al Mabara Hospital | 27.556 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | general | Least-cost | Al Mabara Hospital | 27.525 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | general | North-west corner | Al Mabara Hospital | 27.508 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | general | MODI | Al Mabara Hospital | 27.528 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | trauma | Dijkstra | Al Mabara Hospital | 26.918 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | trauma | A* | Al Mabara Hospital | 13.226 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | trauma | Bellman-Ford | Al Mabara Hospital | 400.290 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | trauma | VAM | Al Mabara Hospital | 26.975 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | trauma | Least-cost | Al Mabara Hospital | 26.952 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | trauma | North-west corner | Al Mabara Hospital | 26.931 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | trauma | MODI | Al Mabara Hospital | 26.950 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | cardiac | Dijkstra | Al Mabara Hospital | 26.324 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | cardiac | A* | Al Mabara Hospital | 10.904 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | cardiac | Bellman-Ford | Al Mabara Hospital | 319.560 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | cardiac | VAM | Al Mabara Hospital | 26.374 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | cardiac | Least-cost | Al Mabara Hospital | 26.349 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | cardiac | North-west corner | Al Mabara Hospital | 26.333 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | cardiac | MODI | Al Mabara Hospital | 26.350 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | pediatric | Dijkstra | El Reda Hospital | 23.735 | 86.426 | 2069.9 | 23 | yes | yes |
| al-mabara-hospital | Z2 | pediatric | A* | El Reda Hospital | 13.669 | 86.426 | 2069.9 | 23 | yes | yes |
| al-mabara-hospital | Z2 | pediatric | Bellman-Ford | El Reda Hospital | 241.829 | 86.426 | 2069.9 | 23 | yes | yes |
| al-mabara-hospital | Z2 | pediatric | VAM | El Reda Hospital | 23.775 | 86.426 | 2069.9 | 23 | yes | yes |
| al-mabara-hospital | Z2 | pediatric | Least-cost | El Reda Hospital | 23.755 | 86.426 | 2069.9 | 23 | yes | yes |
| al-mabara-hospital | Z2 | pediatric | North-west corner | El Reda Hospital | 23.744 | 86.426 | 2069.9 | 23 | yes | yes |
| al-mabara-hospital | Z2 | pediatric | MODI | El Reda Hospital | 23.766 | 86.426 | 2069.9 | 23 | yes | yes |
| al-rowad | Z3 | general | Dijkstra | Al Rowad | 19.085 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | general | A* | Al Rowad | 11.822 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | general | Bellman-Ford | Al Rowad | 132.020 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | general | VAM | Al Rowad | 19.139 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | general | Least-cost | Al Rowad | 19.110 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | general | North-west corner | Al Rowad | 19.096 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | general | MODI | Al Rowad | 19.114 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | trauma | Dijkstra | Al Rowad | 18.783 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | trauma | A* | Al Rowad | 11.608 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | trauma | Bellman-Ford | Al Rowad | 136.549 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | trauma | VAM | Al Rowad | 18.824 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | trauma | Least-cost | Al Rowad | 18.803 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | trauma | North-west corner | Al Rowad | 18.792 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | trauma | MODI | Al Rowad | 18.805 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | cardiac | Dijkstra | — | 24.634 | — | — | 0 | — | yes |
| al-rowad | Z3 | cardiac | A* | — | 0.161 | — | — | 0 | — | yes |
| al-rowad | Z3 | cardiac | Bellman-Ford | — | 137.469 | — | — | 0 | — | yes |
| al-rowad | Z3 | cardiac | VAM | — | 24.634 | — | — | 0 | — | yes |
| al-rowad | Z3 | cardiac | Least-cost | — | 24.634 | — | — | 0 | — | yes |
| al-rowad | Z3 | cardiac | North-west corner | — | 24.634 | — | — | 0 | — | yes |
| al-rowad | Z3 | cardiac | MODI | — | 24.634 | — | — | 0 | — | yes |
| al-rowad | Z3 | pediatric | Dijkstra | — | 18.947 | — | — | 0 | — | yes |
| al-rowad | Z3 | pediatric | A* | — | 0.261 | — | — | 0 | — | yes |
| al-rowad | Z3 | pediatric | Bellman-Ford | — | 141.193 | — | — | 0 | — | yes |
| al-rowad | Z3 | pediatric | VAM | — | 18.947 | — | — | 0 | — | yes |
| al-rowad | Z3 | pediatric | Least-cost | — | 18.947 | — | — | 0 | — | yes |
| al-rowad | Z3 | pediatric | North-west corner | — | 18.947 | — | — | 0 | — | yes |
| al-rowad | Z3 | pediatric | MODI | — | 18.947 | — | — | 0 | — | yes |
| antar-ent-clinic | Z4 | general | Dijkstra | El Nseem Dr.Trez Mansour Hospital | 20.356 | 10.650 | 266.6 | 5 | yes | yes |
| antar-ent-clinic | Z4 | general | A* | El Nseem Dr.Trez Mansour Hospital | 11.255 | 10.650 | 266.6 | 5 | yes | yes |
| antar-ent-clinic | Z4 | general | Bellman-Ford | El Nseem Dr.Trez Mansour Hospital | 239.242 | 10.650 | 266.6 | 5 | yes | yes |
| antar-ent-clinic | Z4 | general | VAM | El Nseem Dr.Trez Mansour Hospital | 20.458 | 10.650 | 266.6 | 5 | yes | yes |
| antar-ent-clinic | Z4 | general | Least-cost | El Nseem Dr.Trez Mansour Hospital | 20.422 | 10.650 | 266.6 | 5 | yes | yes |
| antar-ent-clinic | Z4 | general | North-west corner | Arc Angle Mikhael Hospital | 20.379 | 39.419 | 786.5 | 14 | no | yes |
| antar-ent-clinic | Z4 | general | MODI | El Nseem Dr.Trez Mansour Hospital | 20.434 | 10.650 | 266.6 | 5 | yes | yes |
| antar-ent-clinic | Z4 | trauma | Dijkstra | مستشفى أسيوط العام | 22.098 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | trauma | A* | مستشفى أسيوط العام | 13.187 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | trauma | Bellman-Ford | مستشفى أسيوط العام | 218.584 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | trauma | VAM | مستشفى أسيوط العام | 22.160 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | trauma | Least-cost | مستشفى أسيوط العام | 22.134 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | trauma | North-west corner | Arc Angle Mikhael Hospital | 22.109 | 39.419 | 786.5 | 14 | no | yes |
| antar-ent-clinic | Z4 | trauma | MODI | مستشفى أسيوط العام | 22.160 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | cardiac | Dijkstra | مستشفى أسيوط العام | 22.809 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | cardiac | A* | مستشفى أسيوط العام | 12.961 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | cardiac | Bellman-Ford | مستشفى أسيوط العام | 255.232 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | cardiac | VAM | مستشفى أسيوط العام | 22.889 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | cardiac | Least-cost | مستشفى أسيوط العام | 22.844 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | cardiac | North-west corner | El Aksaa Hospital | 22.824 | 53.030 | 1018.4 | 16 | no | yes |
| antar-ent-clinic | Z4 | cardiac | MODI | مستشفى أسيوط العام | 22.891 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | pediatric | Dijkstra | — | 28.489 | — | — | 0 | — | yes |
| antar-ent-clinic | Z4 | pediatric | A* | — | 0.471 | — | — | 0 | — | yes |
| antar-ent-clinic | Z4 | pediatric | Bellman-Ford | — | 316.506 | — | — | 0 | — | yes |
| antar-ent-clinic | Z4 | pediatric | VAM | — | 28.489 | — | — | 0 | — | yes |
| antar-ent-clinic | Z4 | pediatric | Least-cost | — | 28.489 | — | — | 0 | — | yes |
| antar-ent-clinic | Z4 | pediatric | North-west corner | — | 28.489 | — | — | 0 | — | yes |
| antar-ent-clinic | Z4 | pediatric | MODI | — | 28.489 | — | — | 0 | — | yes |

## Verification

Every pathfinder result is compared with Bellman-Ford.  Every transportation selection is checked against the Bellman-Ford time for the hospital it selected.  A failure is shown in the table and makes the command exit with status 1.

