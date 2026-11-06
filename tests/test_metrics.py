import math

import pandas as pd
import pytest

from isn_engagement import metrics


def test_attendance_trend_counts_and_show_rate(attendance, events) -> None:
    t = metrics.attendance_trend(attendance, events).set_index("event_id")
    assert t.loc["E1", "signups"] == 2 and t.loc["E1", "checkins"] == 2
    assert t.loc["E2", "show_rate"] == pytest.approx(0.5)
    assert list(t.index) == ["E1", "E2", "E3", "E4"]  # chronological


def test_attendance_trend_includes_events_with_no_signups(attendance, events) -> None:
    extra = pd.concat(
        [events, events.iloc[[0]].assign(event_id="E5", event_date=pd.Timestamp("2026-05-01"))]
    )
    t = metrics.attendance_trend(attendance, extra).set_index("event_id")
    assert t.loc["E5", "signups"] == 0 and t.loc["E5", "show_rate"] == 0.0


def test_term_summary(attendance, events) -> None:
    s = metrics.term_summary(attendance, events)
    assert list(s["term"]) == ["Fall 2025", "Winter 2026", "Spring 2026"]
    fall = s.iloc[0]
    assert fall["events"] == 2 and fall["checkins"] == 3 and fall["active_members"] == 2
    assert fall["avg_turnout"] == pytest.approx(1.5)


def test_term_summary_empty() -> None:
    empty_ev = pd.DataFrame(columns=["event_id", "event_date", "term", "title", "topic"])
    empty_att = pd.DataFrame(columns=["member_id", "event_id", "checked_in"])
    assert metrics.term_summary(empty_att, empty_ev).empty


def test_repeat_attendance_rate(attendance) -> None:
    # Active: M1 (4), M2 (1), M3 (1), M4 (1) -> 1 of 4 repeat
    assert metrics.repeat_attendance_rate(attendance) == pytest.approx(0.25)
    assert metrics.repeat_attendance_rate(attendance, min_events=1) == 1.0


def test_repeat_rate_edge_cases(attendance) -> None:
    assert metrics.repeat_attendance_rate(attendance.assign(checked_in=0)) == 0.0
    with pytest.raises(ValueError):
        metrics.repeat_attendance_rate(attendance, min_events=0)


def test_attendance_frequency(attendance) -> None:
    f = metrics.attendance_frequency(attendance)
    assert dict(zip(f["events_attended"], f["members"], strict=True)) == {1: 3, 4: 1}


def test_topic_popularity(attendance, events) -> None:
    t = metrics.topic_popularity(attendance, events).set_index("topic")
    sql = t.loc["SQL & Data"]
    assert sql["events"] == 2 and sql["checkins"] == 4
    assert sql["avg_turnout"] == pytest.approx(2.0)
    # Fill rate only uses E1 (capacity 10, 2 check-ins); E3 has unknown capacity.
    assert sql["avg_fill_rate"] == pytest.approx(0.2)
    assert t.index[0] == "SQL & Data"  # sorted by turnout


def test_cohort_retention_matrix(members, attendance, events) -> None:
    r = metrics.cohort_retention(members, attendance, events)
    assert list(r.index) == ["Fall 2025", "Winter 2026", "Spring 2026"]
    assert r.loc["Fall 2025", "Fall 2025"] == pytest.approx(1.0)  # M1 and M2
    assert r.loc["Fall 2025", "Winter 2026"] == pytest.approx(0.5)  # only M1
    assert r.loc["Winter 2026", "Spring 2026"] == pytest.approx(0.0)  # M3 no-showed
    assert math.isnan(r.loc["Spring 2026", "Fall 2025"])  # before cohort joined


def test_cohort_retention_empty_members(attendance, events, members) -> None:
    assert metrics.cohort_retention(members.iloc[0:0], attendance, events).empty


def test_term_retention(attendance, events) -> None:
    r = metrics.term_retention(attendance, events)
    assert list(r["from_term"]) == ["Fall 2025", "Winter 2026"]
    first = r.iloc[0]
    assert first["base"] == 2 and first["retained"] == 1
    assert first["retention_rate"] == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("score", "tier"), [(0, "Low"), (39.9, "Low"), (40, "Medium"), (70, "Medium"), (70.1, "High")]
)
def test_risk_tier_thresholds(score: float, tier: str) -> None:
    assert metrics.risk_tier(score) == tier


def test_risk_tier_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        metrics.risk_tier(101)


def test_churn_risk_orders_lapsed_above_engaged(members, attendance, events) -> None:
    r = metrics.churn_risk(members, attendance, events).set_index("member_id")
    # M1 attends every term; M2 lapsed after Fall with one check-in.
    assert r.loc["M2", "risk_score"] > r.loc["M1", "risk_score"]
    assert r.loc["M1", "risk_tier"] == "Low"
    assert r["risk_score"].between(0, 100).all()


def test_churn_risk_new_member_not_penalized_for_no_history(members, attendance, events):
    att = attendance[attendance["member_id"] != "M4"]
    r = metrics.churn_risk(members, att, events).set_index("member_id")
    # M4 joined 2 weeks before the as-of date: recency anchors on join date.
    assert r.loc["M4", "days_since"] == 14


def test_churn_risk_as_of_excludes_future(members, attendance, events) -> None:
    r = metrics.churn_risk(members, attendance, events, as_of="2025-12-01")
    assert set(r["member_id"]) == {"M1", "M2"}  # M3/M4 had not joined yet
    m1 = r.set_index("member_id").loc["M1"]
    assert m1["checkins"] == 2  # later check-ins are ignored


def test_churn_risk_empty_events(members, attendance, events) -> None:
    assert metrics.churn_risk(members, attendance, events.iloc[0:0]).empty


def test_breakdown_by_major(members, attendance) -> None:
    b = metrics.breakdown(members, attendance, "major").set_index("major")
    assert b.loc["MIS", "members"] == 2 and b.loc["MIS", "checkins"] == 5
    assert b.loc["MIS", "checkins_per_member"] == pytest.approx(2.5)
    assert b.loc["Finance", "active_rate"] == 1.0


def test_breakdown_unknown_column(members, attendance) -> None:
    with pytest.raises(KeyError):
        metrics.breakdown(members, attendance, "favorite_color")


def test_kpis(members, attendance, events) -> None:
    k = metrics.kpis(members, attendance, events)
    assert k["members"] == 4 and k["events"] == 4
    assert k["signups"] == 9 and k["checkins"] == 7
    assert k["show_rate"] == pytest.approx(7 / 9)
    assert k["active_rate"] == 1.0


def test_kpis_handle_empty(members, attendance, events) -> None:
    k = metrics.kpis(members.iloc[0:0], attendance.iloc[0:0], events.iloc[0:0])
    assert k["show_rate"] == 0.0 and k["active_rate"] == 0.0 and k["repeat_rate"] == 0.0


def test_filter_data_by_term_and_major(members, attendance, events) -> None:
    m, a, e = metrics.filter_data(members, attendance, events, terms=["Fall 2025"], majors=["MIS"])
    assert set(e["event_id"]) == {"E1", "E2"}
    assert set(m["member_id"]) == {"M1", "M2"}
    assert set(a["event_id"]) <= {"E1", "E2"} and set(a["member_id"]) <= {"M1", "M2"}


def test_filter_data_empty_filters_are_noop(members, attendance, events) -> None:
    m, a, e = metrics.filter_data(members, attendance, events, [], None, [], None)
    assert len(m) == len(members) and len(a) == len(attendance) and len(e) == len(events)


def test_filter_by_topic_and_year(members, attendance, events) -> None:
    _, a, e = metrics.filter_data(
        members, attendance, events, topics=["Social"], years=["Freshman"]
    )
    assert list(e["event_id"]) == ["E4"]
    assert list(a["member_id"]) == ["M4"]


def test_seeded_metrics_are_plausible(star) -> None:
    m, e, a = star
    k = metrics.kpis(m, a, e)
    assert 0.6 < k["show_rate"] < 0.95
    assert 0.3 < k["repeat_rate"] < 0.95
    r = metrics.cohort_retention(m, a, e)
    # The founding cohort should retain less over time (people drift away).
    fall = r.loc["Fall 2025"].dropna()
    assert fall.iloc[-1] < fall.iloc[0]
    tiers = set(metrics.churn_risk(m, a, e)["risk_tier"])
    assert tiers == {"Low", "Medium", "High"}
