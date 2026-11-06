"""SQLite access layer for the engagement star schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"
TABLES = ("dim_members", "dim_events", "fact_attendance")


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript((SQL_DIR / "schema.sql").read_text())


def _insert(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    """Bulk insert a frame, storing datetimes as ISO text and missing values as NULL."""
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            fmt = "%Y-%m-%d %H:%M:%S" if col.endswith("_ts") else "%Y-%m-%d"
            df[col] = df[col].dt.strftime(fmt)
    cols = list(df.columns)
    placeholders = ", ".join("?" for _ in cols)
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
    rows = df.astype(object).where(df.notna(), None).itertuples(index=False, name=None)
    conn.executemany(sql, [tuple(v.item() if hasattr(v, "item") else v for v in r) for r in rows])


def load_tables(
    conn: sqlite3.Connection,
    members: pd.DataFrame,
    events: pd.DataFrame,
    attendance: pd.DataFrame,
) -> None:
    """Replace all rows in the star schema with the given cleaned frames.

    Runs in a single transaction, so a constraint failure leaves the previous
    load intact. (pandas ``to_sql`` commits on its own, which is why plain
    ``executemany`` is used here.)
    """
    with conn:
        conn.execute("DELETE FROM fact_attendance")
        conn.execute("DELETE FROM dim_members")
        conn.execute("DELETE FROM dim_events")
        _insert(conn, "dim_members", members)
        _insert(conn, "dim_events", events)
        _insert(conn, "fact_attendance", attendance)


def list_queries() -> list[str]:
    """Names of the analysis queries in sql/ (everything except the schema)."""
    return sorted(p.stem for p in SQL_DIR.glob("*.sql") if p.stem != "schema")


def run_named_query(conn: sqlite3.Connection, name: str) -> pd.DataFrame:
    """Run a query from the sql/ folder by file stem, e.g. ``'topic_popularity'``."""
    if not name.replace("_", "").isalnum():
        raise ValueError(f"Invalid query name: {name!r}")
    path = SQL_DIR / f"{name}.sql"
    if not path.exists():
        raise FileNotFoundError(f"No SQL file named {name}.sql")
    return pd.read_sql_query(path.read_text(), conn)


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}


def read_star(conn: sqlite3.Connection) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load the three star-schema tables as DataFrames with parsed dates."""
    members = pd.read_sql_query("SELECT * FROM dim_members", conn, parse_dates=["join_date"])
    events = pd.read_sql_query("SELECT * FROM dim_events", conn, parse_dates=["event_date"])
    events["capacity"] = events["capacity"].astype("Int64")
    attendance = pd.read_sql_query("SELECT * FROM fact_attendance", conn, parse_dates=["signup_ts"])
    return members, events, attendance
