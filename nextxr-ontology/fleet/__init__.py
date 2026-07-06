"""
fleet — the tram / light-rail fleet-network digital-twin domain module.

A whole-network twin (rolling stock, traction power, track & points,
signalling, operations), built to the same shape as the EDM and turbine twins
so it plugs into the platform unchanged:

  * network.py  — network specs: Melbourne tram dataset + the generic
                  normaliser that turns ANY fleet spec into a working twin
  * physics.py  — service/power/track network physics + a stateful forward sim
                  with live per-vehicle positions for the map
  * predict.py  — per-subsystem health + forward projection + RUL
  * scenario.py — the fault catalogue used by the sim and the what-if engine

Behaviours (findings rules) live in behaviors/fleet/.
"""
