import csv
from pathlib import Path

import pandas as pd
import pytest

from isn_engagement import seed


def _read(path: Path) -> list[dict[str, str]]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def test_generate_writes_three_files_with_expected_sizes(tmp_path: Path) -> None:
    counts = seed.generate(tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == {"members.csv", "events.csv", "attendance.csv"}
    assert counts["members"] == 201  # 200 plus one injected duplicate row
    assert counts["events"] == 40
    assert counts["attendance"] > 500


def test_generate_is_deterministic(tmp_path: Path) -> None:
    seed.generate(tmp_path / "a", seed=7)
    seed.generate(tmp_path / "b", seed=7)
    for name in ("members.csv", "events.csv", "attendance.csv"):
        assert (tmp_path / "a" / name).read_text() == (tmp_path / "b" / name).read_text()


def test_different_seeds_produce_different_data(tmp_path: Path) -> None:
    seed.generate(tmp_path / "a", seed=1)
    seed.generate(tmp_path / "b", seed=2)
    assert (tmp_path / "a/members.csv").read_text() != (tmp_path / "b/members.csv").read_text()


def test_events_span_three_terms_evenly(tmp_path: Path) -> None:
    seed.generate(tmp_path, dirty=False)
    ev = pd.read_csv(tmp_path / "events.csv")
    dates = pd.to_datetime(ev["event_date"])
    per_term = [
        ((dates >= str(s)) & (dates < str(e))).sum()
        for s, e in zip(seed.TERM_STARTS, [*seed.TERM_STARTS[1:], "2026-12-31"], strict=True)
    ]
    assert per_term == [14, 13, 13]


def test_no_attendance_before_member_joined(tmp_path: Path) -> None:
    seed.generate(tmp_path, dirty=False)
    m = pd.read_csv(tmp_path / "members.csv", parse_dates=["join_date"])
    e = pd.read_csv(tmp_path / "events.csv", parse_dates=["event_date"])
    a = pd.read_csv(tmp_path / "attendance.csv").merge(m, on="member_id").merge(e, on="event_id")
    assert (a["join_date"] <= a["event_date"]).all()


def test_clean_mode_has_no_injected_dirt(tmp_path: Path) -> None:
    seed.generate(tmp_path, dirty=False)
    members = _read(tmp_path / "members.csv")
    assert len({m["member_id"] for m in members}) == len(members)
    assert all(m["major"] for m in members)
    assert all(m["email"] == m["email"].strip().lower() for m in members)


def test_emails_are_synthetic_scu_addresses(tmp_path: Path) -> None:
    seed.generate(tmp_path, dirty=False)
    assert all(m["email"].endswith("@scu.edu") for m in _read(tmp_path / "members.csv"))


def test_generate_rejects_tiny_datasets(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        seed.generate(tmp_path, n_members=5)


def test_seed_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seed.main(["--out", str(tmp_path), "--members", "30", "--events", "15"])
    assert "members" in capsys.readouterr().out
    assert len(_read(tmp_path / "events.csv")) == 15
