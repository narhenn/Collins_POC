"""
edm — the Wire-EDM digital-twin domain module.

A detailed, first-principles model of a CNC wire-cut Electrical Discharge
Machine (submerged dielectric, brass wire), built to the same shape as the
turbine twin so it plugs into the platform unchanged:

  * physics.py   — gap/spark electro-thermal physics + a stateful forward sim
  * predict.py   — per-subsystem health + forward projection + RUL
  * ingest.py    — the live per-tenant twin (state / diagnostics / predict)
  * scenario.py  — the fault catalogue used by the sim and the what-if engine

Behaviours (findings rules) live in behaviors/edm/.
"""
