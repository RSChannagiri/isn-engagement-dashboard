"""Extract raw CSV exports, clean them, report data quality, load to SQLite.

Pipeline: ``extract`` (read CSVs as text) -> ``clean_*`` (fix or drop bad rows,
recording every change in a :class:`QualityReport`) -> ``db.load_tables``.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from isn_engagement import db
from isn_engagement.terms import term_for

TRUTHY = {"y", "yes", "true", "1", "t", "x"}
FALSY = {"n", "no", "false", "0", "f", ""}
CLASS_YEARS = {"Freshman", "Sophomore", "Junior", "Senior", "Graduate"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")

REQUIRED_COLUMNS: dict[str, list[str]] = {
    "members": [
        "member_id",
        "first_name",
        "last_name",
        "email",
        "major",
        "class_year",
        "join_date",
    ],
    "events": ["event_id", "title", "topic", "event_type", "event_date", "location", "capacity"],
    "attendance": ["member_id", "event_id", "signup_ts", "checked_in"],
}


class SchemaError(ValueError):
    """Raised when a raw export is missing required columns."""


@dataclass
class QualityReport:
    """Row counts per table and counts of every issue found during cleaning."""

    issues: dict[str, int] = field(default_factory=dict)
    rows_in: dict[str, int] = field(default_factory=dict)
    rows_out: dict[str, int] = field(default_factory=dict)

    def add(self, key: str, n: int) -> None:
        if n:
            self.issues[key] = self.issues.get(key, 0) + int(n)

    @property
    def total_issues(self) -> int:
        return sum(self.issues.values())

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(sorted(self.issues.items()), columns=["issue", "count"])

    def to_markdown(self) -> str:
        lines = [
            "# Data Quality Report",
            "",
            "| table | rows in | rows out | dropped |",
            "|---|---|---|---|",
        ]
        for t, n_in in self.rows_in.items():
            n_out = self.rows_out.get(t, 0)
            lines.append(f"| {t} | {n_in} | {n_out} | {n_in - n_out} |")
        lines += ["", "| issue | count |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in sorted(self.issues.items())] or ["| none | 0 |"]
        return "\n".join(lines) + "\n"


def validate_columns(df: pd.DataFrame, table: str) -> None:
    """Raise :class:`SchemaError` if ``df`` lacks any required column for ``table``."""
    missing = [c for c in REQUIRED_COLUMNS[table] if c not in df.columns]
    if missing:
        raise SchemaError(f"{table}.csv is missing required columns: {', '.join(missing)}")


def parse_bool(value: object) -> int | None:
    """Parse the many spellings of yes/no found in exports. ``None`` if unrecognized."""
    s = "" if value is None or pd.isna(value) else str(value).strip().lower()
    if s in TRUTHY:
        return 1
    if s in FALSY:
        return 0
    return None


def _text(series: pd.Series) -> pd.Series:
    """Strip whitespace, treating missing values as empty strings."""
    return series.fillna("").astype(str).str.strip()


def clean_members(raw: pd.DataFrame, report: QualityReport) -> pd.DataFrame:
    validate_columns(raw, "members")
    df = raw.copy()
    report.rows_in["members"] = len(df)
    df["member_id"] = _text(df["member_id"]).str.upper()
    df["email"] = _text(df["email"]).str.lower()
    for col in ("first_name", "last_name"):
        df[col] = _text(df[col]).str.title()

    missing_id = df["member_id"] == ""
    report.add("members: missing member_id dropped", missing_id.sum())
    df = df[~missing_id]

    bad_email = ~df["email"].str.match(EMAIL_RE)
    report.add("members: invalid email dropped", bad_email.sum())
    df = df[~bad_email]

    df["major"] = _text(df["major"])
    missing_major = df["major"] == ""
    report.add("members: missing major filled as Undeclared", missing_major.sum())
    df.loc[missing_major, "major"] = "Undeclared"

    year = _text(df["class_year"]).str.title()
    report.add(
        "members: class_year casing normalized",
        ((year != _text(df["class_year"])) & year.isin(CLASS_YEARS)).sum(),
    )
    unknown_year = ~year.isin(CLASS_YEARS)
    report.add("members: unknown class_year set to Unknown", unknown_year.sum())
    df["class_year"] = year.where(~unknown_year, "Unknown")

    iso = pd.to_datetime(df["join_date"], errors="coerce", format="%Y-%m-%d")
    dates = pd.to_datetime(df["join_date"], errors="coerce", format="mixed")
    report.add("members: non-ISO join_date normalized", (iso.isna() & dates.notna()).sum())
    report.add("members: unparseable join_date dropped", dates.isna().sum())
    df = df.assign(join_date=dates).dropna(subset=["join_date"])

    before = len(df)
    df = df.drop_duplicates(subset=["member_id"]).drop_duplicates(subset=["email"])
    report.add("members: duplicate rows removed", before - len(df))

    df["join_term"] = df["join_date"].dt.date.map(term_for)
    df["join_date"] = df["join_date"].dt.strftime("%Y-%m-%d")
    report.rows_out["members"] = len(df)
    return df[
        [
            "member_id",
            "first_name",
            "last_name",
            "email",
            "major",
            "class_year",
            "join_date",
            "join_term",
        ]
    ].reset_index(drop=True)


def clean_events(raw: pd.DataFrame, report: QualityReport) -> pd.DataFrame:
    validate_columns(raw, "events")
    df = raw.copy()
    report.rows_in["events"] = len(df)
    df["event_id"] = _text(df["event_id"]).str.upper()
    df["title"] = _text(df["title"])
    df["location"] = _text(df["location"]).replace("", None)

    topic = _text(df["topic"])
    known = {t.lower(): t for t in topic if t and not t.islower()}
    fixed = topic.map(lambda t: known.get(t.lower(), t))
    report.add(
        "events: topic casing/whitespace normalized", (fixed != df["topic"].fillna("")).sum()
    )
    df["topic"] = fixed.replace("", "Other")

    etype = _text(df["event_type"])
    report.add("events: missing event_type set to Workshop", (etype == "").sum())
    df["event_type"] = etype.replace("", "Workshop")

    iso = pd.to_datetime(df["event_date"], errors="coerce", format="%Y-%m-%d")
    dates = pd.to_datetime(df["event_date"], errors="coerce", format="mixed")
    report.add("events: non-ISO event_date normalized", (iso.isna() & dates.notna()).sum())
    report.add("events: unparseable event_date dropped", dates.isna().sum())
    df = df.assign(event_date=dates).dropna(subset=["event_date"])

    cap = pd.to_numeric(df["capacity"], errors="coerce")
    bad_cap = cap.isna() | (cap <= 0)
    report.add("events: invalid capacity set to null", bad_cap.sum())
    df["capacity"] = cap.where(~bad_cap).round().astype("Int64")

    before = len(df)
    df = df.drop_duplicates(subset=["event_id"])
    report.add("events: duplicate rows removed", before - len(df))

    df["term"] = df["event_date"].dt.date.map(term_for)
    df["event_date"] = df["event_date"].dt.strftime("%Y-%m-%d")
    report.rows_out["events"] = len(df)
    return df[
        ["event_id", "title", "topic", "event_type", "event_date", "term", "location", "capacity"]
    ].reset_index(drop=True)


def clean_attendance(
    raw: pd.DataFrame, members: pd.DataFrame, events: pd.DataFrame, report: QualityReport
) -> pd.DataFrame:
    validate_columns(raw, "attendance")
    df = raw.copy()
    report.rows_in["attendance"] = len(df)
    df["member_id"] = _text(df["member_id"]).str.upper()
    df["event_id"] = _text(df["event_id"]).str.upper()

    raw_flag = _text(df["checked_in"])
    parsed = df["checked_in"].map(parse_bool)
    report.add("attendance: unrecognized checked_in dropped", parsed.isna().sum())
    report.add(
        "attendance: checked_in spelling normalized",
        (parsed.notna() & ~raw_flag.isin(["Y", "N"])).sum(),
    )
    df = df.assign(checked_in=parsed).dropna(subset=["checked_in"])
    df["checked_in"] = df["checked_in"].astype(int)

    # If a member appears twice for one event, keep the row where they checked in.
    before = len(df)
    df = (
        df.sort_values("checked_in", ascending=False, kind="stable")
        .drop_duplicates(subset=["member_id", "event_id"])
        .sort_index()
    )
    report.add("attendance: duplicate check-ins removed", before - len(df))

    orphan_m = ~df["member_id"].isin(members["member_id"])
    orphan_e = ~df["event_id"].isin(events["event_id"])
    report.add("attendance: unknown member_id dropped", orphan_m.sum())
    report.add("attendance: unknown event_id dropped", (orphan_e & ~orphan_m).sum())
    df = df[~orphan_m & ~orphan_e]

    ts = pd.to_datetime(df["signup_ts"], errors="coerce", format="mixed")
    report.add("attendance: unparseable signup_ts dropped", ts.isna().sum())
    df = df.assign(signup_ts=ts).dropna(subset=["signup_ts"])

    # Report-only check: signups logged after the event day usually mean walk-ins.
    ev_dates = pd.to_datetime(df["event_id"].map(events.set_index("event_id")["event_date"]))
    report.add(
        "attendance: signup after event day (walk-in, kept)",
        (df["signup_ts"].dt.normalize() > ev_dates).sum(),
    )

    df["signup_ts"] = df["signup_ts"].dt.strftime("%Y-%m-%d %H:%M:%S")
    report.rows_out["attendance"] = len(df)
    return df[["member_id", "event_id", "signup_ts", "checked_in"]].reset_index(drop=True)


def extract(raw_dir: Path) -> dict[str, pd.DataFrame]:
    """Read the three raw exports as text so cleaning controls every conversion."""
    frames = {}
    for table in REQUIRED_COLUMNS:
        path = raw_dir / f"{table}.csv"
        if not path.exists():
            raise FileNotFoundError(f"Missing raw export: {path}")
        frames[table] = pd.read_csv(path, dtype=str, keep_default_na=False)
    return frames


def transform(
    frames: dict[str, pd.DataFrame],
    report: QualityReport,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    members = clean_members(frames["members"], report)
    events = clean_events(frames["events"], report)
    attendance = clean_attendance(frames["attendance"], members, events, report)
    return members, events, attendance


def run(raw_dir: Path, db_path: Path, report_path: Path | None = None) -> QualityReport:
    """Full pipeline: CSVs in raw_dir -> SQLite at db_path. Returns the quality report."""
    report = QualityReport()
    members, events, attendance = transform(extract(raw_dir), report)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(db_path)
    try:
        db.create_schema(conn)
        db.load_tables(conn, members, events, attendance)
    finally:
        conn.close()
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report.to_markdown())
    return report


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Run the ISN engagement ETL.")
    p.add_argument("--raw", type=Path, default=Path("data/raw"))
    p.add_argument("--db", type=Path, default=Path("data/isn.db"))
    p.add_argument("--report", type=Path, default=Path("data/quality_report.md"))
    args = p.parse_args(argv)
    report = run(args.raw, args.db, args.report)
    print(report.to_markdown())


if __name__ == "__main__":
    main()
