from pathlib import Path

import pandas as pd
import pytest

from isn_engagement import db, etl
from isn_engagement.etl import QualityReport, SchemaError


def raw_members(**overrides: list[str]) -> pd.DataFrame:
    data = {
        "member_id": ["M0001", "M0002"],
        "first_name": ["ava", "ben"],
        "last_name": ["ng", "o'brien"],
        "email": ["a@scu.edu", "b@scu.edu"],
        "major": ["MIS", "Finance"],
        "class_year": ["Junior", "Senior"],
        "join_date": ["2025-09-25", "2026-01-06"],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def raw_events(**overrides: list[str]) -> pd.DataFrame:
    data = {
        "event_id": ["E001", "E002"],
        "title": ["Intro to SQL", "Mixer"],
        "topic": ["SQL & Data", "Social"],
        "event_type": ["Workshop", "Social"],
        "event_date": ["2025-10-01", "2026-01-10"],
        "location": ["Lucas Hall", ""],
        "capacity": ["40", "60"],
    }
    data.update(overrides)
    return pd.DataFrame(data)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("Y", 1), ("yes", 1), (" TRUE ", 1), ("1", 1), ("N", 0), ("no", 0), ("", 0), (None, 0)],
)
def test_parse_bool_spellings(value: object, expected: int) -> None:
    assert etl.parse_bool(value) == expected


def test_parse_bool_unrecognized_returns_none() -> None:
    assert etl.parse_bool("maybe") is None


def test_validate_columns_reports_missing() -> None:
    with pytest.raises(SchemaError, match="email"):
        etl.validate_columns(raw_members().drop(columns=["email"]), "members")


def test_clean_members_normalizes_text_and_assigns_term() -> None:
    report = QualityReport()
    out = etl.clean_members(raw_members(email=[" A@SCU.EDU ", "b@scu.edu"]), report)
    assert out.loc[0, "email"] == "a@scu.edu"
    assert out.loc[1, "last_name"] == "O'Brien"
    assert list(out["join_term"]) == ["Fall 2025", "Winter 2026"]


def test_clean_members_fills_missing_major() -> None:
    report = QualityReport()
    out = etl.clean_members(raw_members(major=["", "Finance"]), report)
    assert out.loc[0, "major"] == "Undeclared"
    assert report.issues["members: missing major filled as Undeclared"] == 1


def test_clean_members_drops_duplicates_by_id_and_email() -> None:
    raw = pd.concat([raw_members(), raw_members().iloc[[0]]], ignore_index=True)
    raw.loc[2, "member_id"] = "M0003"  # same email, new id
    report = QualityReport()
    out = etl.clean_members(raw, report)
    assert len(out) == 2
    assert report.issues["members: duplicate rows removed"] == 1


def test_clean_members_drops_invalid_email_and_bad_date() -> None:
    report = QualityReport()
    out = etl.clean_members(
        raw_members(email=["not-an-email", "b@scu.edu"], join_date=["2025-09-25", "someday"]),
        report,
    )
    assert out.empty
    assert report.issues["members: invalid email dropped"] == 1
    assert report.issues["members: unparseable join_date dropped"] == 1


def test_clean_members_class_year_casing_and_unknown() -> None:
    report = QualityReport()
    out = etl.clean_members(raw_members(class_year=["junior", "5th year"]), report)
    assert list(out["class_year"]) == ["Junior", "Unknown"]
    assert report.issues["members: class_year casing normalized"] == 1
    assert report.issues["members: unknown class_year set to Unknown"] == 1


def test_clean_members_accepts_us_date_format() -> None:
    report = QualityReport()
    out = etl.clean_members(raw_members(join_date=["09/25/2025", "2026-01-06"]), report)
    assert out.loc[0, "join_date"] == "2025-09-25"
    assert report.issues["members: non-ISO join_date normalized"] == 1


def test_clean_events_fixes_dates_capacity_and_topic() -> None:
    report = QualityReport()
    out = etl.clean_events(
        raw_events(
            event_date=["2025/10/01", "2026-01-10"],
            capacity=["0", "abc"],
            topic=["SQL & Data", " sql & data "],
        ),
        report,
    )
    assert list(out["event_date"]) == ["2025-10-01", "2026-01-10"]
    assert out["capacity"].isna().all()
    assert list(out["topic"]) == ["SQL & Data", "SQL & Data"]
    assert list(out["term"]) == ["Fall 2025", "Winter 2026"]
    assert report.issues["events: invalid capacity set to null"] == 2
    assert report.issues["events: non-ISO event_date normalized"] == 1


def test_clean_attendance_drops_orphans_dupes_and_bad_rows() -> None:
    report = QualityReport()
    members = etl.clean_members(raw_members(), report)
    events = etl.clean_events(raw_events(), report)
    raw = pd.DataFrame(
        {
            "member_id": ["M0001", "m0001", "M0002", "M9999", "M0002", "M0001"],
            "event_id": ["E001", "E001", "E999", "E001", "E002", "E002"],
            "signup_ts": ["2025-09-30 10:00:00"] * 4 + ["garbage", "2026-01-09 09:00:00"],
            "checked_in": ["N", "yes", "Y", "Y", "Y", "maybe"],
        }
    )
    out = etl.clean_attendance(raw, members, events, report)
    assert len(out) == 1
    # Duplicate (member, event) keeps the checked-in row even if it came second.
    assert out.iloc[0].to_dict()["checked_in"] == 1
    for key in (
        "attendance: duplicate check-ins removed",
        "attendance: unknown member_id dropped",
        "attendance: unknown event_id dropped",
        "attendance: unparseable signup_ts dropped",
        "attendance: unrecognized checked_in dropped",
    ):
        assert report.issues[key] == 1, key


def test_quality_report_markdown_and_totals() -> None:
    r = QualityReport()
    r.add("x", 2)
    r.add("x", 3)
    r.add("ignored", 0)
    r.rows_in["members"], r.rows_out["members"] = 10, 8
    md = r.to_markdown()
    assert "| members | 10 | 8 | 2 |" in md
    assert "| x | 5 |" in md
    assert "ignored" not in md
    assert r.total_issues == 5
    assert list(r.to_frame().columns) == ["issue", "count"]


def test_extract_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        etl.extract(tmp_path)


def test_full_pipeline_catches_injected_dirt(seeded: dict[str, Path]) -> None:
    text = seeded["report"].read_text()
    for issue in (
        "members: duplicate rows removed",
        "members: missing major filled as Undeclared",
        "events: non-ISO event_date normalized",
        "events: invalid capacity set to null",
        "attendance: unknown member_id dropped",
        "attendance: unknown event_id dropped",
        "attendance: duplicate check-ins removed",
    ):
        assert issue in text


def test_full_pipeline_loads_clean_star(seeded: dict[str, Path]) -> None:
    conn = db.connect(seeded["db"])
    try:
        counts = db.table_counts(conn)
        assert counts["dim_members"] == 200
        assert counts["dim_events"] == 40
        orphans = conn.execute(
            "SELECT COUNT(*) FROM fact_attendance a "
            "LEFT JOIN dim_members m ON m.member_id = a.member_id WHERE m.member_id IS NULL"
        ).fetchone()[0]
        assert orphans == 0
    finally:
        conn.close()


def test_rerunning_etl_is_idempotent(seeded: dict[str, Path], tmp_path: Path) -> None:
    db_path = tmp_path / "again.db"
    etl.run(seeded["raw"], db_path)
    etl.run(seeded["raw"], db_path)
    conn = db.connect(db_path)
    try:
        assert db.table_counts(conn)["dim_members"] == 200
    finally:
        conn.close()


def test_etl_cli(seeded: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    etl.main(
        [
            "--raw",
            str(seeded["raw"]),
            "--db",
            str(tmp_path / "x.db"),
            "--report",
            str(tmp_path / "r.md"),
        ]
    )
    assert "Data Quality Report" in capsys.readouterr().out
    assert (tmp_path / "r.md").exists()
