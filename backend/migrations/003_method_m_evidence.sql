-- Frozen Experimental Method M January evidence (relational + hypertables).
-- Stores detector outputs only — no evaluation labels, no raw SCADA duplication.
-- TIMESTAMP WITHOUT TIME ZONE = naive BattLeDIM benchmark clock.

CREATE TABLE IF NOT EXISTS method_m_runs (
    run_id TEXT PRIMARY KEY,
    method TEXT NOT NULL DEFAULT 'M',
    label TEXT NOT NULL,
    experimental BOOLEAN NOT NULL DEFAULT TRUE,
    disclaimer TEXT NOT NULL,
    resolution TEXT NOT NULL,
    resolution_note TEXT NOT NULL,
    coverage_start TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    coverage_end TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    coverage_note TEXT,
    tau DOUBLE PRECISION NOT NULL,
    tau_recover DOUBLE PRECISION NOT NULL,
    timestep_sec INTEGER NOT NULL,
    recover_steps INTEGER NOT NULL,
    version_hashes JSONB NOT NULL,
    serving_hours_sha256 TEXT NOT NULL,
    serving_notifications_sha256 TEXT NOT NULL,
    n_score_stamps INTEGER NOT NULL,
    n_contributor_rows INTEGER NOT NULL,
    n_notifications INTEGER NOT NULL,
    artifact_dir TEXT NOT NULL,
    imported_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT method_m_runs_hours_hash_uniq UNIQUE (serving_hours_sha256),
    CONSTRAINT method_m_runs_notif_hash_uniq UNIQUE (serving_notifications_sha256)
);

CREATE TABLE IF NOT EXISTS method_m_scores (
    ts TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    run_id TEXT NOT NULL REFERENCES method_m_runs (run_id) ON DELETE CASCADE,
    score DOUBLE PRECISION,
    argmax_sensor_id TEXT,
    PRIMARY KEY (ts, run_id)
);

SELECT create_hypertable(
    'method_m_scores',
    'ts',
    if_not_exists => TRUE,
    migrate_data => TRUE
);

CREATE INDEX IF NOT EXISTS method_m_scores_run_ts_idx
    ON method_m_scores (run_id, ts DESC);

CREATE TABLE IF NOT EXISTS method_m_sensor_evidence (
    ts TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    run_id TEXT NOT NULL REFERENCES method_m_runs (run_id) ON DELETE CASCADE,
    sensor_id TEXT NOT NULL,
    abs_z_calibrated DOUBLE PRECISION NOT NULL,
    delta_m3h DOUBLE PRECISION NOT NULL,
    sigma_scale_m3h DOUBLE PRECISION NOT NULL,
    qv_m3h DOUBLE PRECISION NOT NULL,
    ref_mean_m3h DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (ts, run_id, sensor_id)
);

SELECT create_hypertable(
    'method_m_sensor_evidence',
    'ts',
    if_not_exists => TRUE,
    migrate_data => TRUE
);

CREATE INDEX IF NOT EXISTS method_m_evidence_run_ts_z_idx
    ON method_m_sensor_evidence (run_id, ts, abs_z_calibrated DESC);

CREATE TABLE IF NOT EXISTS method_m_notifications (
    run_id TEXT NOT NULL REFERENCES method_m_runs (run_id) ON DELETE CASCADE,
    notify_ts TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    end_ts TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    peak_score DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (run_id, notify_ts),
    CONSTRAINT method_m_notifications_order CHECK (notify_ts <= end_ts)
);

CREATE INDEX IF NOT EXISTS method_m_notifications_run_notify_idx
    ON method_m_notifications (run_id, notify_ts DESC);
