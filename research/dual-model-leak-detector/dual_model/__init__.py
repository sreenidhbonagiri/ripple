"""Physics-based pressure–leak dual model (research isolation).

Stage 1–2: dual hydraulic construction + synthetic mechanism verification.
Measured-data calibration and detection evaluation are intentionally absent.
"""

from .dual_builder import DualModelSpec, attach_virtual_reservoirs, pressure_to_head
from .simulate import DualSimulationResult, run_dual_steady, run_dual_timeseries

__all__ = [
    "DualModelSpec",
    "DualSimulationResult",
    "attach_virtual_reservoirs",
    "pressure_to_head",
    "run_dual_steady",
    "run_dual_timeseries",
]

__version__ = "0.1.0"