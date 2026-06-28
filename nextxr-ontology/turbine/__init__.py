"""
turbine — the Collins gas-turbine digital-twin domain pack (backend).

Cohesive home for the turbine twin's working parts that sit on top of the
NextXR ontology:

  physics.py   the gas-turbine physics model (expected values + forward sim)
  ingest.py    the sensor-ingestion service (3D layer -> behaviours -> findings)
  seed.py      builds a single-engine turbine twin (engine + modules + sensors)

The ontology itself lives in packs/aerospace/ (aero-classes.ttl, aero-shapes.ttl);
behaviours live in behaviors/aerospace/. This package wires those into a live,
sensor-fed twin the 3D layer streams real readings into.
"""

from turbine.physics import TurbinePhysics, SIGNALS, redlines  # noqa: F401
