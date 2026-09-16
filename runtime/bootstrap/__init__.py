# runtime/bootstrap/__init__.py
"""
ANNY Three-Plane Bootstrap package.

Orchestrates the mandatory 11-gate readiness check across:
  Plane 1 — GitHub
  Plane 2 — Repository Fabric (dynamically bound via RuntimeConfig; fabric_org/fabric_repo required)
  Plane 3 — ANNY-RUNTIME (local execution)

ANNY_READY = true only when all 11 gates pass.
"""
