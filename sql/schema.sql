-- Star schema: two dimensions (members, events) and one fact table (attendance).
CREATE TABLE IF NOT EXISTS dim_members (
    member_id   TEXT PRIMARY KEY,
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    major       TEXT NOT NULL,
    class_year  TEXT NOT NULL,
    join_date   TEXT NOT NULL,
    join_term   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_events (
    event_id    TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    topic       TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    event_date  TEXT NOT NULL,
    term        TEXT NOT NULL,
    location    TEXT,
    capacity    INTEGER CHECK (capacity > 0)
);

CREATE TABLE IF NOT EXISTS fact_attendance (
    member_id   TEXT NOT NULL REFERENCES dim_members(member_id),
    event_id    TEXT NOT NULL REFERENCES dim_events(event_id),
    signup_ts   TEXT NOT NULL,
    checked_in  INTEGER NOT NULL CHECK (checked_in IN (0, 1)),
    PRIMARY KEY (member_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_att_event ON fact_attendance(event_id);
