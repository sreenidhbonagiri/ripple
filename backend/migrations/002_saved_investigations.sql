-- Saved historical investigation metadata (relational).
-- Measurements continue to come from readings / readings_15m — this table
-- stores only the view recipe (sensor, cursor, window, title/note, source).
-- A saved investigation is not immutable evidence and is not authentication.

CREATE TABLE IF NOT EXISTS saved_investigations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    note TEXT,
    sensor_id TEXT NOT NULL REFERENCES sensors (id),
    cursor_ts TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    window_start TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    window_end TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    source_id TEXT NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT saved_investigations_title_len
        CHECK (char_length(title) >= 1 AND char_length(title) <= 120),
    CONSTRAINT saved_investigations_note_len
        CHECK (note IS NULL OR char_length(note) <= 1000),
    CONSTRAINT saved_investigations_source_len
        CHECK (char_length(source_id) >= 1 AND char_length(source_id) <= 64),
    CONSTRAINT saved_investigations_window_order
        CHECK (window_start < window_end),
    CONSTRAINT saved_investigations_cursor_in_window
        CHECK (cursor_ts >= window_start AND cursor_ts <= window_end)
);

CREATE INDEX IF NOT EXISTS saved_investigations_created_at_idx
    ON saved_investigations (created_at DESC);
