"""Load sensor metadata — never includes leakage labels."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from app.config import REPO_ROOT

MeasurementType = Literal["pressure", "flow", "tank_level"]
ElementKind = Literal["node", "link"]

UNIT_BY_TYPE: dict[MeasurementType, str] = {
    "pressure": "m",
    "flow": "m³/h",
    "tank_level": "m",
}


def _parse_simple_yaml_list(text: str, key: str) -> list[str]:
    """Parse a top-level YAML list for `key:` without loading leakages."""
    lines = text.splitlines()
    items: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith(":") and not stripped.startswith("-"):
            in_section = stripped[:-1] == key
            continue
        if in_section:
            if stripped.startswith("-"):
                value = stripped[1:].strip()
                if value and not value.startswith("#"):
                    items.append(value)
            else:
                # left the list section
                break
    return items


def load_sensor_definitions(meta_path: Path | None = None) -> list[dict[str, str]]:
    """
    Prefer sensors_metadata.yaml (leak labels already stripped).
    Fall back to dataset_configuration.yaml but only read sensor keys.
    """
    raw_dir = REPO_ROOT / "data" / "raw"
    candidates = []
    if meta_path:
        candidates.append(meta_path)
    candidates.extend(
        [
            raw_dir / "sensors_metadata.yaml",
            raw_dir / "dataset_configuration.yaml",
        ]
    )

    text = None
    for path in candidates:
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            break
    if text is None:
        raise FileNotFoundError(
            "No sensor metadata found. Run scripts/download_scada_2019.sh "
            "or ensure data/raw/sensors_metadata.yaml exists."
        )

    # Explicitly ignore leakages / amrs / comments / times / Network
    pressure = _parse_simple_yaml_list(text, "pressure_sensors")
    flow = _parse_simple_yaml_list(text, "flow_sensors")
    level = _parse_simple_yaml_list(text, "level_sensors")

    sensors: list[dict[str, str]] = []
    for sid in pressure:
        sensors.append(
            {
                "id": sid,
                "measurement_type": "pressure",
                "unit": UNIT_BY_TYPE["pressure"],
                "network_element_id": sid,
                "network_element_kind": "node",
            }
        )
    for sid in flow:
        sensors.append(
            {
                "id": sid,
                "measurement_type": "flow",
                "unit": UNIT_BY_TYPE["flow"],
                "network_element_id": sid,
                "network_element_kind": "link",
            }
        )
    for sid in level:
        sensors.append(
            {
                "id": sid,
                "measurement_type": "tank_level",
                "unit": UNIT_BY_TYPE["tank_level"],
                "network_element_id": sid,
                "network_element_kind": "node",
            }
        )
    return sensors
