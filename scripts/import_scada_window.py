#!/usr/bin/env python3
"""
Import a bounded SCADA window into Tiger Cloud (idempotent).

Default window: 2019-01-12 14:00:00 .. 2019-01-12 17:00:00 inclusive
(presenter window). Use --start/--end and optional --end-exclusive for
larger historical ranges. Checks storage capacity before importing.
Refreshes readings_15m outside a transaction after import.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from datetime import datetime
from pathlib import Path

import wntr

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.db import get_connection, sanitize_db_error  # noqa: E402
from app.sensors_meta import UNIT_BY_TYPE, load_sensor_definitions  # noqa: E402
from app.storage_capacity import assert_capacity_for_import  # noqa: E402

DEFAULT_START = datetime(2019, 1, 12, 14, 0, 0)
DEFAULT_END = datetime(2019, 1, 12, 17, 0, 0)

FILES = {
    "pressure": "2019_SCADA_Pressures.csv",
    "flow": "2019_SCADA_Flows.csv",
    "tank_level": "2019_SCADA_Levels.csv",
}


def parse_decimal(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def network_ids(inp_path: Path) -> tuple[set[str], set[str]]:
    wn = wntr.network.WaterNetworkModel(str(inp_path))
    return set(wn.node_name_list), set(wn.link_name_list)


def in_window(ts: datetime, start: datetime, end: datetime, *, end_exclusive: bool) -> bool:
    if ts < start:
        return False
    if end_exclusive:
        return ts < end
    return ts <= end


def iter_window_rows(
    csv_path: Path,
    sensor_ids: set[str],
    start: datetime,
    end: datetime,
    *,
    end_exclusive: bool,
) -> tuple[list[tuple[datetime, str, float]], dict[str, int]]:
    stats = {
        "rows_in_window": 0,
        "values_emitted": 0,
        "missing_cells": 0,
        "unknown_columns": 0,
    }
    out: list[tuple[datetime, str, float]] = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh, delimiter=";")
        header = next(reader)
        if not header or header[0].strip().lower() not in {"timestamp", "datetime"}:
            raise ValueError(f"Unexpected header in {csv_path.name}: {header[:3]}")
        columns = [c.strip() for c in header[1:]]
        unknown = [c for c in columns if c not in sensor_ids]
        stats["unknown_columns"] = len(unknown)

        for row in reader:
            if not row:
                continue
            ts = datetime.strptime(row[0].strip(), "%Y-%m-%d %H:%M:%S")
            if not in_window(ts, start, end, end_exclusive=end_exclusive):
                continue
            stats["rows_in_window"] += 1
            for col_name, raw in zip(columns, row[1:], strict=False):
                if col_name not in sensor_ids:
                    continue
                value = parse_decimal(raw) if raw is not None else None
                if value is None:
                    stats["missing_cells"] += 1
                    continue
                out.append((ts, col_name, value))
                stats["values_emitted"] += 1
    return out, stats


def validate_sensor_units(sensors: list[dict[str, str]]) -> None:
    for s in sensors:
        expected = UNIT_BY_TYPE[s["measurement_type"]]  # type: ignore[index]
        if s["unit"] != expected:
            raise ValueError(
                f"Unit mismatch for {s['id']}: got {s['unit']!r}, expected {expected!r}"
            )


def upsert_sensors(conn, sensors: list[dict[str, str]]) -> None:
    with conn.cursor() as cur:
        for s in sensors:
            cur.execute(
                """
                INSERT INTO sensors (id, measurement_type, unit, network_element_id, network_element_kind)
                VALUES (%(id)s, %(measurement_type)s, %(unit)s, %(network_element_id)s, %(network_element_kind)s)
                ON CONFLICT (id) DO UPDATE SET
                    measurement_type = EXCLUDED.measurement_type,
                    unit = EXCLUDED.unit,
                    network_element_id = EXCLUDED.network_element_id,
                    network_element_kind = EXCLUDED.network_element_kind
                """,
                s,
            )


def copy_and_upsert(conn, rows: list[tuple[datetime, str, float]], *, chunk_size: int = 50_000) -> int:
    total = 0
    with conn.cursor() as cur:
        for i in range(0, max(len(rows), 1), chunk_size):
            chunk = rows[i : i + chunk_size]
            cur.execute("TRUNCATE readings_staging")
            if not chunk:
                continue
            buf = io.StringIO()
            writer = csv.writer(buf)
            for ts, sid, value in chunk:
                writer.writerow([ts.strftime("%Y-%m-%d %H:%M:%S"), sid, f"{value:.12g}"])
            buf.seek(0)
            with cur.copy(
                "COPY readings_staging (ts, sensor_id, value) FROM STDIN WITH (FORMAT csv)"
            ) as copy:
                copy.write(buf.read())
            cur.execute(
                """
                INSERT INTO readings (ts, sensor_id, value)
                SELECT ts, sensor_id, value FROM readings_staging
                ON CONFLICT (ts, sensor_id) DO UPDATE SET value = EXCLUDED.value
                """
            )
            total += len(chunk)
    return total


def refresh_cagg() -> None:
    with get_connection() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("CALL refresh_continuous_aggregate('readings_15m', NULL, NULL)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Idempotent BattLeDIM SCADA import")
    parser.add_argument("--start", default=DEFAULT_START.isoformat(sep=" "))
    parser.add_argument("--end", default=DEFAULT_END.isoformat(sep=" "))
    parser.add_argument(
        "--end-exclusive",
        action="store_true",
        help="Treat --end as exclusive (ts < end). Default is inclusive.",
    )
    parser.add_argument(
        "--skip-capacity-check",
        action="store_true",
        help="Unsafe: skip storage capacity gate (not recommended).",
    )
    args = parser.parse_args()
    start = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end)
    if end < start or (args.end_exclusive and end <= start):
        print("FAIL: invalid start/end range")
        return 1

    settings = get_settings()
    inp_path = settings.ripple_inp_path
    if not inp_path.is_file():
        print(f"FAIL: EPANET model missing at {inp_path}")
        return 1

    raw_dir = REPO_ROOT / "data" / "raw"
    try:
        sensors = load_sensor_definitions()
        validate_sensor_units(sensors)
        node_ids, link_ids = network_ids(inp_path)

        validated: list[dict[str, str]] = []
        for s in sensors:
            eid = s["network_element_id"]
            kind = s["network_element_kind"]
            if kind == "node" and eid not in node_ids:
                print(f"FAIL: sensor {s['id']} node {eid} not in L-TOWN.inp")
                return 1
            if kind == "link" and eid not in link_ids:
                print(f"FAIL: sensor {s['id']} link {eid} not in L-TOWN.inp")
                return 1
            validated.append(s)

        by_type: dict[str, set[str]] = {"pressure": set(), "flow": set(), "tank_level": set()}
        for s in validated:
            by_type[s["measurement_type"]].add(s["id"])

        all_rows: list[tuple[datetime, str, float]] = []
        file_stats: dict[str, dict[str, int]] = {}
        for mtype, filename in FILES.items():
            path = raw_dir / filename
            if not path.is_file():
                print(f"FAIL: missing {path}")
                return 1
            rows, stats = iter_window_rows(
                path,
                by_type[mtype],
                start,
                end,
                end_exclusive=args.end_exclusive,
            )
            all_rows.extend(rows)
            file_stats[filename] = stats

        if not args.skip_capacity_check:
            snap = assert_capacity_for_import(len(all_rows))
            print(
                "capacity:"
                f" db_bytes={snap.database_bytes}"
                f" limit_bytes={snap.limit_bytes}"
                f" working_ceiling_bytes={snap.working_ceiling_bytes}"
                f" available_to_limit_bytes={snap.available_to_limit_bytes}"
                f" usable_bytes={snap.usable_bytes}"
                f" est_import_bytes={len(all_rows) * snap.bytes_per_reading_est}"
                f" staged_readings={len(all_rows)}"
            )
        else:
            print("capacity: SKIPPED (--skip-capacity-check)")

        with get_connection() as conn:
            upsert_sensors(conn, validated)
            inserted = copy_and_upsert(conn, all_rows)
            with conn.cursor() as cur:
                if args.end_exclusive:
                    cur.execute(
                        """
                        SELECT COUNT(*) AS n,
                               COUNT(DISTINCT sensor_id) AS sensors,
                               MIN(ts) AS min_ts,
                               MAX(ts) AS max_ts
                        FROM readings
                        WHERE ts >= %s AND ts < %s
                        """,
                        (start, end),
                    )
                else:
                    cur.execute(
                        """
                        SELECT COUNT(*) AS n,
                               COUNT(DISTINCT sensor_id) AS sensors,
                               MIN(ts) AS min_ts,
                               MAX(ts) AS max_ts
                        FROM readings
                        WHERE ts >= %s AND ts <= %s
                        """,
                        (start, end),
                    )
                summary = cur.fetchone()
            conn.commit()

        refresh_cagg()

        bound = "<" if args.end_exclusive else "<="
        print("OK: import complete")
        print(f"window: {start} .. {end} (ts {bound} end)")
        print(f"sensors_upserted: {len(validated)}")
        print(f"staging_rows: {inserted}")
        print(
            "readings_in_window:"
            f" count={summary['n']} sensors={summary['sensors']}"
            f" min_ts={summary['min_ts']} max_ts={summary['max_ts']}"
        )
        for name, stats in file_stats.items():
            print(
                f"file {name}: rows_in_window={stats['rows_in_window']} "
                f"values={stats['values_emitted']} missing_cells={stats['missing_cells']} "
                f"unknown_columns={stats['unknown_columns']}"
            )
        timesteps = summary["n"] // max(summary["sensors"], 1) if summary["sensors"] else 0
        complete_grid = summary["sensors"] * timesteps if timesteps else 0
        print(
            f"missingness: actual_readings={summary['n']} "
            f"distinct_sensors={summary['sensors']} "
            f"approx_timesteps={timesteps} "
            f"approx_complete_grid={complete_grid} "
            f"shortfall_vs_grid={max(complete_grid - summary['n'], 0)}"
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {sanitize_db_error(str(exc))}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
