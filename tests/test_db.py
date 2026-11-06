import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from isn_engagement import db, metrics
from isn_engagement.bootstrap import ensure_database


@pytest.fixture
def conn(seeded: dict[str, Path]):
    c = db.connect(seeded["db"])
    yield c
    c.close()


def test_schema_has_star_tables(conn: sqlite3.Connection) -> None:
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert set(db.TABLES) <= names


def test_foreign_keys_enforced(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO fact_attendance VALUES ('NOPE', 'E001', '2025-01-01 00:00:00', 1)"
        )


def test_check_constraints(tmp_path: Path) -> None:
    c = db.connect(tmp_path / "c.db")
    db.create_schema(c)
    c.execute(
        "INSERT INTO dim_members VALUES ('M1','A','B','a@scu.edu','MIS','Junior',"
        "'2025-09-25','Fall 2025')"
    )
    c.execute(
        "INSERT INTO dim_events VALUES ('E1','T','SQL','Workshop','2025-10-01','Fall 2025',"
        "'Lucas',40)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO fact_attendance VALUES ('M1','E1','2025-09-30 00:00:00',2)")
    with pytest.raises(sqlite3.IntegrityError):
        c.execute(
            "INSERT INTO dim_events VALUES ('E2','T','SQL','Workshop','2025-10-01',"
            "'Fall 2025','Lucas',0)"
        )
    c.close()


def test_load_tables_rolls_back_on_failure(tmp_path: Path, conn: sqlite3.Connection) -> None:
    m, e, a = db.read_star(conn)
    target = db.connect(tmp_path / "t.db")
    db.create_schema(target)
    db.load_tables(target, m, e, a)
    bad = a.copy()
    bad.loc[0, "member_id"] = "GHOST"
    with pytest.raises(sqlite3.IntegrityError):
        db.load_tables(target, m, e, bad)
    assert db.table_counts(target)["fact_attendance"] == len(a)
    target.close()


def test_list_queries_excludes_schema() -> None:
    names = db.list_queries()
    assert "schema" not in names
    assert {"topic_popularity", "cohort_retention", "repeat_attendance"} <= set(names)


@pytest.mark.parametrize("name", db.list_queries())
def test_every_named_query_runs(conn: sqlite3.Connection, name: str) -> None:
    df = db.run_named_query(conn, name)
    assert not df.empty


def test_run_named_query_rejects_unknown_and_traversal(conn: sqlite3.Connection) -> None:
    with pytest.raises(FileNotFoundError):
        db.run_named_query(conn, "does_not_exist")
    with pytest.raises(ValueError):
        db.run_named_query(conn, "../etc/passwd")


def test_sql_repeat_rate_matches_pandas(conn: sqlite3.Connection) -> None:
    _, _, a = db.read_star(conn)
    sql_rate = db.run_named_query(conn, "repeat_attendance").loc[0, "repeat_rate"]
    assert sql_rate == pytest.approx(metrics.repeat_attendance_rate(a), abs=1e-3)


def test_sql_topic_popularity_matches_pandas(conn: sqlite3.Connection) -> None:
    _, e, a = db.read_star(conn)
    sql = db.run_named_query(conn, "topic_popularity").set_index("topic")
    py = metrics.topic_popularity(a, e).set_index("topic")
    pd.testing.assert_series_equal(
        sql["checkins"].sort_index(), py["checkins"].sort_index(), check_dtype=False
    )
    assert sql["avg_fill_rate"].sort_index().to_numpy() == pytest.approx(
        py["avg_fill_rate"].sort_index().to_numpy(), abs=1e-3
    )


def test_sql_term_summary_matches_pandas(conn: sqlite3.Connection) -> None:
    _, e, a = db.read_star(conn)
    sql = db.run_named_query(conn, "attendance_by_term")
    py = metrics.term_summary(a, e)
    assert list(sql["term"]) == list(py["term"])
    assert list(sql["active_members"]) == list(py["active_members"])


def test_read_star_parses_dates(conn: sqlite3.Connection) -> None:
    m, e, a = db.read_star(conn)
    assert pd.api.types.is_datetime64_any_dtype(m["join_date"])
    assert pd.api.types.is_datetime64_any_dtype(e["event_date"])
    assert pd.api.types.is_datetime64_any_dtype(a["signup_ts"])


def test_ensure_database_bootstraps_from_nothing(tmp_path: Path) -> None:
    db_path, raw = tmp_path / "isn.db", tmp_path / "raw"
    assert ensure_database(db_path, raw) is True
    assert (raw / "members.csv").exists() and db_path.exists()
    assert ensure_database(db_path, raw) is False
