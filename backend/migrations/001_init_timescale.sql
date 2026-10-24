-- Ripple Milestone 2: Tiger Data / TimescaleDB schema
-- TIMESTAMP WITHOUT TIME ZONE = naive BattLeDIM benchmark clock (no geographic TZ).

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sensors (
    id TEXT PRIMARY KEY,
    measurement_type TEXT NOT NULL CHECK (measurement_type IN ('pressure', 'flow', 'tank_level')),
    unit TEXT NOT NULL,
    network_element_id TEXT NOT NULL,
    network_element_kind TEXT NOT NULL CHECK (network_element_kind IN ('node', 'link'))
);

CREATE TABLE IF NOT EXISTS readings (
    ts TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    sensor_id TEXT NOT NULL REFERENCES sensors (id),
    value DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (ts, sensor_id)
);

SELECT create_hypertable(
    'readings',
    'ts',
    if_not_exists => TRUE,
    migrate_data => TRUE
);

-- Staging for COPY-based idempotent imports
CREATE TABLE IF NOT EXISTS readings_staging (
    ts TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    sensor_id TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL
);

-- Continuous aggregate: 15-minute buckets (created empty; refresh after import)
CREATE MATERIALIZED VIEW IF NOT EXISTS readings_15m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket(INTERVAL '15 minutes', ts) AS bucket,
    sensor_id,
    COUNT(*)::BIGINT AS count,
    SUM(value) AS sum,
    MIN(value) AS min,
    MAX(value) AS max
FROM readings
GROUP BY 1, 2
WITH NO DATA;
