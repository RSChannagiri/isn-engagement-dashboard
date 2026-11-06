"""Smoke tests for the Streamlit dashboard using streamlit.testing.AppTest."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture
def app(seeded: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> AppTest:
    monkeypatch.setenv("ISN_DB_PATH", str(seeded["db"]))
    monkeypatch.setenv("ISN_RAW_DIR", str(seeded["raw"]))
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def _metric(at: AppTest, label: str) -> str:
    return next(m.value for m in at.metric if m.label == label)


def test_app_renders_kpis_and_tabs(app: AppTest) -> None:
    assert app.title[0].value == "ISN Member Engagement"
    assert _metric(app, "Members") == "200"
    assert _metric(app, "Events") == "40"
    assert [t.label for t in app.tabs] == [
        "Overview",
        "Topics",
        "Retention",
        "Churn risk",
        "Members",
        "Data and SQL",
    ]


def test_term_filter_narrows_events(app: AppTest) -> None:
    app.multiselect(key="terms").set_value(["Fall 2025"]).run()
    assert not app.exception
    assert _metric(app, "Events") == "14"


def test_major_filter_narrows_members(app: AppTest) -> None:
    app.multiselect(key="majors").set_value(["Finance"]).run()
    assert not app.exception
    assert int(_metric(app, "Members")) < 200


def test_filters_that_match_nothing_do_not_crash(app: AppTest) -> None:
    app.multiselect(key="terms").set_value(["Fall 2025"])
    app.multiselect(key="topics").set_value(["Social"])
    app.multiselect(key="majors").set_value(["Accounting"])
    app.multiselect(key="years").set_value(["Freshman"]).run()
    assert not app.exception


def test_churn_tier_and_sql_selectors(app: AppTest) -> None:
    app.selectbox(key="tier").set_value("All").run()
    assert not app.exception
    app.selectbox(key="query").set_value("churn_watchlist").run()
    assert not app.exception
    assert any("latest_term_checkins" in c.value for c in app.code)


def test_app_bootstraps_empty_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ISN_DB_PATH", str(tmp_path / "fresh.db"))
    monkeypatch.setenv("ISN_RAW_DIR", str(tmp_path / "raw"))
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception
    assert (tmp_path / "fresh.db").exists()
