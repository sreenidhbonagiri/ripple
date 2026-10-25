"""Unit conventions for dual-model hydraulics.

WNTR / EPANET SI internals use:
  - length / head / elevation: metres
  - pressure (reported): metres of water column (head relative to elevation)
  - flow: m³/s

BattLeDIM SCADA pressures are metres of water (European decimal commas in CSV).
Hydraulic head at a junction is:

    H = P + z

where P is pressure head (m) and z is node elevation (m). Virtual reservoir
total heads must be absolute hydraulic heads, not gauge pressures.

Flow reporting helpers convert to m³/h for human-readable tables (paper figures
use m³/h). Detection code (later stage) should keep SI internally.
"""

from __future__ import annotations

M3S_TO_M3H = 3600.0
M3H_TO_M3S = 1.0 / 3600.0
M3S_TO_LS = 1000.0


def m3s_to_m3h(q_m3s: float) -> float:
    return float(q_m3s) * M3S_TO_M3H


def m3h_to_m3s(q_m3h: float) -> float:
    return float(q_m3h) * M3H_TO_M3S