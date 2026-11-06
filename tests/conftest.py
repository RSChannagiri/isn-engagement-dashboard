"""Shared fixtures: a tiny hand-built star schema and a full seeded pipeline run."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from isn_engagement import db, etl, seed


@pytest.fixture
def members() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "member_id": ["M1", "M2", "M3", "M4"],
            "first_name": ["Ava", "Ben", "Cam", "Dee"],
            "last_name": ["Ng", "Ortiz", "Park", "Quinn"],
            "email": ["a@scu.edu", "b@scu.edu", "c@scu.edu", "d@scu.edu"],
            "major": ["MIS", "MIS", "Finance", "Marketing"],
            "class_year": ["Junior", "Senior", "Junior", "Freshman"],
            "join_date": pd.to_datetime(["2025-09-25", "2025-09-25", "2026-01-06", "2026-04-01"]),
            "join_term": ["Fall 2025", "Fall 2025", "Winter 2026", "Spring 2026"],
        }
    )


@pytest.fixture
def events() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "event_id": ["E1", "E2", "E3", "E4"],
            "title": ["Intro to SQL", "Resume Night", "Tableau Bootcamp", "Mixer"],
            "topic": ["SQL & Data", "Career", "SQL & Data", "Social"],
            "event_type": ["Workshop", "Panel", "Workshop", "Social"],
            "event_date": pd.to_datetime(["2025-10-01", "2025-11-01", "2026-02-01", "2026-04-15"]),
            "term": ["Fall 2025", "Fall 2025", "Winter 2026", "Spring 2026"],
            "location": ["Lucas Hall", "Lucas Hall", "Benson", "Benson"],
            "capacity": pd.array([10, 20, None, 40], dtype="Int64"),
        }
    )


@pytest.fixture
def attendance() -> pd.DataFrame:
    rows = [
        ("M1", "E1", 1),
        ("M1", "E2", 1),
        ("M1", "E3", 1),
        ("M1", "E4", 1),
        ("M2", "E1", 1),
        ("M2", "E2", 0),
        ("M3", "E3", 1),
        ("M3", "E4", 0),
        ("M4", "E4", 1),
    ]
    df = pd.DataFrame(rows, columns=["member_id", "event_id", "checked_in"])
    df["signup_ts"] = pd.Timestamp("2025-09-30 10:00:00")
    return df


@pytest.fixture(scope="session")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Generate the default synthetic dataset and run the full ETL once."""
    base = tmp_path_factory.mktemp("seeded")
    raw, db_path, report = base / "raw", base / "isn.db", base / "quality_report.md"
    seed.generate(raw)
    etl.run(raw, db_path, report)
    return {"raw": raw, "db": db_path, "report": report}


@pytest.fixture
def star(seeded: dict[str, Path]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    conn = db.connect(seeded["db"])
    try:
        return db.read_star(conn)
    finally:
        conn.close()
