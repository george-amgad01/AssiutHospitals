# Emergency dispatch algorithm comparison

Measured on the real Assiut SUMO network with the owner-approved start-zone-only search and free-flow travel times.

**Important:** Dijkstra, A* and Bellman-Ford are pathfinders. VAM, least-cost, north-west corner and MODI are transportation-problem selection methods; they choose a hospital and do not build a road route. Their route and travel time are taken from the Dijkstra matrix, and the Dijkstra matrix time is included in their runtime.

Generated: `2026-10-23T20:48:28`

## Summary

| Algorithm | Runs | Mean runtime (ms) | Mean route time (s) | Optimal | Verified | Failures |
|---|---:|---:|---:|---:|---:|---:|
| Dijkstra | 16 | 16.067 | 16.587 | 12 | 16 | 0 |
| A* | 16 | 6.191 | 16.587 | 12 | 16 | 0 |
| Bellman-Ford | 16 | 135.929 | 16.587 | 12 | 16 | 0 |
| VAM | 16 | 16.105 | 16.587 | 12 | 16 | 0 |
| Least-cost | 16 | 16.084 | 16.587 | 12 | 16 | 0 |
| North-west corner | 16 | 16.076 | 24.999 | 8 | 16 | 0 |
| MODI | 16 | 16.091 | 16.587 | 12 | 16 | 0 |

## Per-case results

| Origin | Zone | Specialty | Algorithm | Selected hospital | Runtime (ms) | Route time (s) | Length (m) | Edges | Optimal | Verified |
|---|---|---|---|---|---:|---:|---:|---:|---|---|
| asyut-chest-hospital | Z1 | general | Dijkstra | Asyut Chest Hospital | 13.818 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | general | A* | Asyut Chest Hospital | 7.240 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | general | Bellman-Ford | Asyut Chest Hospital | 170.327 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | general | VAM | Asyut Chest Hospital | 13.895 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | general | Least-cost | Asyut Chest Hospital | 13.853 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | general | North-west corner | Asyut Chest Hospital | 13.828 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | general | MODI | Asyut Chest Hospital | 13.848 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | trauma | Dijkstra | — | 14.699 | — | — | 0 | — | yes |
| asyut-chest-hospital | Z1 | trauma | A* | — | 0.346 | — | — | 0 | — | yes |
| asyut-chest-hospital | Z1 | trauma | Bellman-Ford | — | 165.810 | — | — | 0 | — | yes |
| asyut-chest-hospital | Z1 | trauma | VAM | — | 14.699 | — | — | 0 | — | yes |
| asyut-chest-hospital | Z1 | trauma | Least-cost | — | 14.699 | — | — | 0 | — | yes |
| asyut-chest-hospital | Z1 | trauma | North-west corner | — | 14.699 | — | — | 0 | — | yes |
| asyut-chest-hospital | Z1 | trauma | MODI | — | 14.699 | — | — | 0 | — | yes |
| asyut-chest-hospital | Z1 | cardiac | Dijkstra | Asyut Chest Hospital | 18.765 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | cardiac | A* | Asyut Chest Hospital | 7.058 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | cardiac | Bellman-Ford | Asyut Chest Hospital | 180.827 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | cardiac | VAM | Asyut Chest Hospital | 18.825 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | cardiac | Least-cost | Asyut Chest Hospital | 18.792 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | cardiac | North-west corner | Asyut Chest Hospital | 18.820 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | cardiac | MODI | Asyut Chest Hospital | 18.806 | 0.000 | 0.0 | 1 | yes | yes |
| asyut-chest-hospital | Z1 | pediatric | Dijkstra | El Zhraa Hospital | 16.784 | 51.962 | 1226.4 | 16 | yes | yes |
| asyut-chest-hospital | Z1 | pediatric | A* | El Zhraa Hospital | 14.040 | 51.962 | 1226.4 | 16 | yes | yes |
| asyut-chest-hospital | Z1 | pediatric | Bellman-Ford | El Zhraa Hospital | 193.440 | 51.962 | 1226.4 | 16 | yes | yes |
| asyut-chest-hospital | Z1 | pediatric | VAM | El Zhraa Hospital | 16.863 | 51.962 | 1226.4 | 16 | yes | yes |
| asyut-chest-hospital | Z1 | pediatric | Least-cost | El Zhraa Hospital | 16.808 | 51.962 | 1226.4 | 16 | yes | yes |
| asyut-chest-hospital | Z1 | pediatric | North-west corner | El Hayah Hospital | 16.793 | 79.853 | 1707.7 | 24 | no | yes |
| asyut-chest-hospital | Z1 | pediatric | MODI | El Zhraa Hospital | 16.830 | 51.962 | 1226.4 | 16 | yes | yes |
| al-mabara-hospital | Z2 | general | Dijkstra | Al Mabara Hospital | 15.207 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | general | A* | Al Mabara Hospital | 6.404 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | general | Bellman-Ford | Al Mabara Hospital | 147.621 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | general | VAM | Al Mabara Hospital | 15.250 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | general | Least-cost | Al Mabara Hospital | 15.227 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | general | North-west corner | Al Mabara Hospital | 15.214 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | general | MODI | Al Mabara Hospital | 15.229 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | trauma | Dijkstra | Al Mabara Hospital | 15.411 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | trauma | A* | Al Mabara Hospital | 6.380 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | trauma | Bellman-Ford | Al Mabara Hospital | 148.986 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | trauma | VAM | Al Mabara Hospital | 15.441 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | trauma | Least-cost | Al Mabara Hospital | 15.425 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | trauma | North-west corner | Al Mabara Hospital | 15.417 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | trauma | MODI | Al Mabara Hospital | 15.427 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | cardiac | Dijkstra | Al Mabara Hospital | 13.197 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | cardiac | A* | Al Mabara Hospital | 8.262 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | cardiac | Bellman-Ford | Al Mabara Hospital | 155.501 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | cardiac | VAM | Al Mabara Hospital | 13.245 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | cardiac | Least-cost | Al Mabara Hospital | 13.217 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | cardiac | North-west corner | Al Mabara Hospital | 13.206 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | cardiac | MODI | Al Mabara Hospital | 13.223 | 0.000 | 0.0 | 1 | yes | yes |
| al-mabara-hospital | Z2 | pediatric | Dijkstra | El Reda Hospital | 16.905 | 86.426 | 2069.9 | 23 | yes | yes |
| al-mabara-hospital | Z2 | pediatric | A* | El Reda Hospital | 8.863 | 86.426 | 2069.9 | 23 | yes | yes |
| al-mabara-hospital | Z2 | pediatric | Bellman-Ford | El Reda Hospital | 159.282 | 86.426 | 2069.9 | 23 | yes | yes |
| al-mabara-hospital | Z2 | pediatric | VAM | El Reda Hospital | 16.936 | 86.426 | 2069.9 | 23 | yes | yes |
| al-mabara-hospital | Z2 | pediatric | Least-cost | El Reda Hospital | 16.919 | 86.426 | 2069.9 | 23 | yes | yes |
| al-mabara-hospital | Z2 | pediatric | North-west corner | El Reda Hospital | 16.911 | 86.426 | 2069.9 | 23 | yes | yes |
| al-mabara-hospital | Z2 | pediatric | MODI | El Reda Hospital | 16.921 | 86.426 | 2069.9 | 23 | yes | yes |
| al-rowad | Z3 | general | Dijkstra | Al Rowad | 15.058 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | general | A* | Al Rowad | 6.296 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | general | Bellman-Ford | Al Rowad | 77.831 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | general | VAM | Al Rowad | 15.087 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | general | Least-cost | Al Rowad | 15.072 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | general | North-west corner | Al Rowad | 15.064 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | general | MODI | Al Rowad | 15.074 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | trauma | Dijkstra | Al Rowad | 13.995 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | trauma | A* | Al Rowad | 6.970 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | trauma | Bellman-Ford | Al Rowad | 79.777 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | trauma | VAM | Al Rowad | 14.025 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | trauma | Least-cost | Al Rowad | 14.009 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | trauma | North-west corner | Al Rowad | 14.001 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | trauma | MODI | Al Rowad | 14.011 | 0.920 | 25.6 | 3 | yes | yes |
| al-rowad | Z3 | cardiac | Dijkstra | — | 14.549 | — | — | 0 | — | yes |
| al-rowad | Z3 | cardiac | A* | — | 0.114 | — | — | 0 | — | yes |
| al-rowad | Z3 | cardiac | Bellman-Ford | — | 77.665 | — | — | 0 | — | yes |
| al-rowad | Z3 | cardiac | VAM | — | 14.549 | — | — | 0 | — | yes |
| al-rowad | Z3 | cardiac | Least-cost | — | 14.549 | — | — | 0 | — | yes |
| al-rowad | Z3 | cardiac | North-west corner | — | 14.549 | — | — | 0 | — | yes |
| al-rowad | Z3 | cardiac | MODI | — | 14.549 | — | — | 0 | — | yes |
| al-rowad | Z3 | pediatric | Dijkstra | — | 19.516 | — | — | 0 | — | yes |
| al-rowad | Z3 | pediatric | A* | — | 0.084 | — | — | 0 | — | yes |
| al-rowad | Z3 | pediatric | Bellman-Ford | — | 84.350 | — | — | 0 | — | yes |
| al-rowad | Z3 | pediatric | VAM | — | 19.516 | — | — | 0 | — | yes |
| al-rowad | Z3 | pediatric | Least-cost | — | 19.516 | — | — | 0 | — | yes |
| al-rowad | Z3 | pediatric | North-west corner | — | 19.516 | — | — | 0 | — | yes |
| al-rowad | Z3 | pediatric | MODI | — | 19.516 | — | — | 0 | — | yes |
| antar-ent-clinic | Z4 | general | Dijkstra | El Nseem Dr.Trez Mansour Hospital | 19.814 | 10.650 | 266.6 | 5 | yes | yes |
| antar-ent-clinic | Z4 | general | A* | El Nseem Dr.Trez Mansour Hospital | 10.308 | 10.650 | 266.6 | 5 | yes | yes |
| antar-ent-clinic | Z4 | general | Bellman-Ford | El Nseem Dr.Trez Mansour Hospital | 148.924 | 10.650 | 266.6 | 5 | yes | yes |
| antar-ent-clinic | Z4 | general | VAM | El Nseem Dr.Trez Mansour Hospital | 19.899 | 10.650 | 266.6 | 5 | yes | yes |
| antar-ent-clinic | Z4 | general | Least-cost | El Nseem Dr.Trez Mansour Hospital | 19.853 | 10.650 | 266.6 | 5 | yes | yes |
| antar-ent-clinic | Z4 | general | North-west corner | Arc Angle Mikhael Hospital | 19.825 | 39.419 | 786.5 | 14 | no | yes |
| antar-ent-clinic | Z4 | general | MODI | El Nseem Dr.Trez Mansour Hospital | 19.877 | 10.650 | 266.6 | 5 | yes | yes |
| antar-ent-clinic | Z4 | trauma | Dijkstra | مستشفى أسيوط العام | 17.163 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | trauma | A* | مستشفى أسيوط العام | 7.724 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | trauma | Bellman-Ford | مستشفى أسيوط العام | 130.705 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | trauma | VAM | مستشفى أسيوط العام | 17.206 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | trauma | Least-cost | مستشفى أسيوط العام | 17.187 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | trauma | North-west corner | Arc Angle Mikhael Hospital | 17.170 | 39.419 | 786.5 | 14 | no | yes |
| antar-ent-clinic | Z4 | trauma | MODI | مستشفى أسيوط العام | 17.215 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | cardiac | Dijkstra | مستشفى أسيوط العام | 16.509 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | cardiac | A* | مستشفى أسيوط العام | 8.650 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | cardiac | Bellman-Ford | مستشفى أسيوط العام | 132.560 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | cardiac | VAM | مستشفى أسيوط العام | 16.553 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | cardiac | Least-cost | مستشفى أسيوط العام | 16.530 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | cardiac | North-west corner | El Aksaa Hospital | 16.517 | 53.030 | 1018.4 | 16 | no | yes |
| antar-ent-clinic | Z4 | cardiac | MODI | مستشفى أسيوط العام | 16.549 | 24.085 | 669.1 | 13 | yes | yes |
| antar-ent-clinic | Z4 | pediatric | Dijkstra | — | 15.685 | — | — | 0 | — | yes |
| antar-ent-clinic | Z4 | pediatric | A* | — | 0.325 | — | — | 0 | — | yes |
| antar-ent-clinic | Z4 | pediatric | Bellman-Ford | — | 121.265 | — | — | 0 | — | yes |
| antar-ent-clinic | Z4 | pediatric | VAM | — | 15.685 | — | — | 0 | — | yes |
| antar-ent-clinic | Z4 | pediatric | Least-cost | — | 15.685 | — | — | 0 | — | yes |
| antar-ent-clinic | Z4 | pediatric | North-west corner | — | 15.685 | — | — | 0 | — | yes |
| antar-ent-clinic | Z4 | pediatric | MODI | — | 15.685 | — | — | 0 | — | yes |

## Verification

Every pathfinder result is compared with Bellman-Ford.  Every transportation selection is checked against the Bellman-Ford time for the hospital it selected.  A failure is shown in the table and makes the command exit with status 1.

