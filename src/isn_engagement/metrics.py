"""Engagement metrics computed from the cleaned star schema (pure pandas, no UI)."""

from __future__ import annotations

import itertools

import pandas as pd

from isn_engagement.terms import sort_terms, term_sort_key

RECENCY_CAP_DAYS = 120
FREQUENCY_CAP = 8
RISK_WEIGHTS = {"recency": 0.5, "frequency": 0.3, "declining": 0.2}
RISK_TIERS = ["Low", "Medium", "High"]


def checkins(attendance: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Checked-in attendance joined to event attributes."""
    att = attendance[attendance["checked_in"] == 1]
    return att.merge(events, on="event_id", how="inner")


def attendance_trend(attendance: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Per event: date, title, topic, signups, check-ins, and show rate (check-ins / signups)."""
    agg = attendance.groupby("event_id").agg(
        signups=("member_id", "count"), checkins=("checked_in", "sum")
    )
    out = events.set_index("event_id").join(agg).fillna({"signups": 0, "checkins": 0})
    out[["signups", "checkins"]] = out[["signups", "checkins"]].astype(int)
    out["show_rate"] = (out["checkins"] / out["signups"].where(out["signups"] > 0)).fillna(0.0)
    cols = ["event_id", "event_date", "term", "title", "topic", "signups", "checkins", "show_rate"]
    return out.reset_index()[cols].sort_values(["event_date", "event_id"]).reset_index(drop=True)


def term_summary(attendance: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Per term: events held, check-ins, distinct active members, average turnout."""
    cols = ["term", "events", "checkins", "active_members", "avg_turnout"]
    if events.empty:
        return pd.DataFrame(columns=cols)
    trend = attendance_trend(attendance, events)
    active = checkins(attendance, events).groupby("term")["member_id"].nunique()
    out = trend.groupby("term").agg(events=("event_id", "count"), checkins=("checkins", "sum"))
    out["active_members"] = active.reindex(out.index).fillna(0).astype(int)
    out["avg_turnout"] = out["checkins"] / out["events"]
    out = out.reset_index()
    return out.sort_values("term", key=lambda s: s.map(term_sort_key)).reset_index(drop=True)[cols]


def repeat_attendance_rate(attendance: pd.DataFrame, min_events: int = 2) -> float:
    """Share of members with at least one check-in who checked in ``min_events``+ times."""
    if min_events < 1:
        raise ValueError("min_events must be at least 1")
    per = attendance[attendance["checked_in"] == 1].groupby("member_id").size()
    if per.empty:
        return 0.0
    return float((per >= min_events).mean())


def attendance_frequency(attendance: pd.DataFrame) -> pd.DataFrame:
    """Distribution of active members by how many events they checked in to."""
    per = attendance[attendance["checked_in"] == 1].groupby("member_id").size()
    dist = per.value_counts().sort_index()
    return pd.DataFrame(
        {"events_attended": dist.index.astype(int), "members": dist.to_numpy().astype(int)}
    )


def topic_popularity(attendance: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Per topic: events, signups, check-ins, average turnout, show rate, average fill rate.

    Fill rate is check-ins / room capacity per event, averaged over events with a
    known capacity.
    """
    cols = ["topic", "events", "signups", "checkins", "avg_turnout", "show_rate", "avg_fill_rate"]
    if events.empty:
        return pd.DataFrame(columns=cols)
    trend = attendance_trend(attendance, events).merge(
        events[["event_id", "capacity"]], on="event_id"
    )
    cap = pd.to_numeric(trend["capacity"], errors="coerce").astype(float)
    trend["fill_rate"] = trend["checkins"] / cap.where(cap > 0)
    out = trend.groupby("topic").agg(
        events=("event_id", "count"),
        signups=("signups", "sum"),
        checkins=("checkins", "sum"),
        avg_fill_rate=("fill_rate", "mean"),
    )
    out["avg_turnout"] = out["checkins"] / out["events"]
    out["show_rate"] = (out["checkins"] / out["signups"].where(out["signups"] > 0)).fillna(0.0)
    out["avg_fill_rate"] = out["avg_fill_rate"].fillna(0.0)
    out = out.reset_index().sort_values(["avg_turnout", "topic"], ascending=[False, True])
    return out.reset_index(drop=True)[cols]


def cohort_retention(
    members: pd.DataFrame, attendance: pd.DataFrame, events: pd.DataFrame
) -> pd.DataFrame:
    """Matrix: rows = join-term cohort, columns = term, values = share of cohort active.

    Cells for terms before a cohort joined are NaN (not applicable, not zero).
    """
    sizes = members.groupby("join_term")["member_id"].nunique()
    if sizes.empty:
        return pd.DataFrame()
    ci = checkins(attendance, events)[["member_id", "term"]].drop_duplicates()
    merged = ci.merge(members[["member_id", "join_term"]], on="member_id")
    counts = merged.groupby(["join_term", "term"])["member_id"].nunique().unstack(fill_value=0)
    order = sort_terms(set(counts.columns) | set(sizes.index) | set(events["term"]))
    rates = counts.reindex(index=sizes.index, columns=order, fill_value=0).div(sizes, axis=0)
    rates = rates.reindex(index=sort_terms(set(sizes.index))).astype(float)
    for cohort in rates.index:
        before = [t for t in rates.columns if term_sort_key(t) < term_sort_key(cohort)]
        rates.loc[cohort, before] = float("nan")
    rates.index.name = "cohort"
    rates.columns.name = "term"
    return rates


def term_retention(attendance: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Share of each term's active members who were active again in the next term."""
    cols = ["from_term", "to_term", "base", "retained", "retention_rate"]
    ci = checkins(attendance, events)
    by_term = ci.groupby("term")["member_id"].apply(set).to_dict()
    terms = sort_terms(set(events["term"]))
    rows = []
    for prev, nxt in itertools.pairwise(terms):
        base = by_term.get(prev, set())
        kept = len(base & by_term.get(nxt, set()))
        rows.append(
            {
                "from_term": prev,
                "to_term": nxt,
                "base": len(base),
                "retained": kept,
                "retention_rate": kept / len(base) if base else 0.0,
            }
        )
    return pd.DataFrame(rows, columns=cols)


def risk_tier(score: float) -> str:
    """Bucket a 0-100 churn score: Low (<40), Medium (40-70), High (>70)."""
    if not 0 <= score <= 100:
        raise ValueError(f"Risk score out of range: {score}")
    if score < 40:
        return "Low"
    if score <= 70:
        return "Medium"
    return "High"


def churn_risk(
    members: pd.DataFrame,
    attendance: pd.DataFrame,
    events: pd.DataFrame,
    as_of: pd.Timestamp | str | None = None,
) -> pd.DataFrame:
    """Score each member 0-100 on churn risk from recency, frequency, and trend.

    - recency: days since last check-in, or since joining if they never checked
      in (so brand new members are not flagged on day one), capped at 120
    - frequency: lifetime check-ins, saturating at 8
    - declining: was active before the latest term but not during it

    Members who joined after ``as_of`` are excluded.
    """
    cols = [
        "member_id",
        "first_name",
        "last_name",
        "major",
        "class_year",
        "checkins",
        "recent",
        "last_checkin",
        "days_since",
        "risk_score",
        "risk_tier",
    ]
    ev = events.copy()
    ev["event_date"] = pd.to_datetime(ev["event_date"])
    if ev.empty or members.empty:
        return pd.DataFrame(columns=cols)
    as_of = pd.Timestamp(as_of) if as_of is not None else ev["event_date"].max()
    past = ev[ev["event_date"] <= as_of]
    latest_term = past.sort_values("event_date")["term"].iloc[-1] if not past.empty else None

    ci = checkins(attendance, past)
    g = ci.groupby("member_id")
    stats = pd.DataFrame({"last_checkin": g["event_date"].max(), "checkins": g.size()})
    recent = ci[ci["term"] == latest_term].groupby("member_id").size().rename("recent")
    m = members.copy()
    m["join_date"] = pd.to_datetime(m["join_date"])
    m = m[m["join_date"] <= as_of]
    stats = (
        m.set_index("member_id")[["first_name", "last_name", "major", "class_year", "join_date"]]
        .join(stats)
        .join(recent)
    )
    stats["checkins"] = stats["checkins"].fillna(0).astype(int)
    stats["recent"] = stats["recent"].fillna(0).astype(int)
    anchor = stats["last_checkin"].fillna(stats["join_date"])
    stats["days_since"] = (as_of - anchor).dt.days.clip(0, RECENCY_CAP_DAYS).astype(int)

    recency = stats["days_since"] / RECENCY_CAP_DAYS
    frequency = 1 - stats["checkins"].clip(upper=FREQUENCY_CAP) / FREQUENCY_CAP
    declining = ((stats["recent"] == 0) & (stats["checkins"] > 0)).astype(float)
    w = RISK_WEIGHTS
    score = 100 * (w["recency"] * recency + w["frequency"] * frequency + w["declining"] * declining)
    stats["risk_score"] = score.round(1)
    stats["risk_tier"] = stats["risk_score"].map(risk_tier)
    out = stats.reset_index().sort_values(["risk_score", "member_id"], ascending=[False, True])
    return out.reset_index(drop=True)[cols]


def breakdown(members: pd.DataFrame, attendance: pd.DataFrame, by: str) -> pd.DataFrame:
    """Members, active members, and check-ins grouped by a member attribute."""
    if by not in members.columns:
        raise KeyError(f"Unknown member column: {by}")
    per = attendance[attendance["checked_in"] == 1].groupby("member_id").size().rename("checkins")
    m = members.set_index("member_id").join(per).fillna({"checkins": 0})
    out = m.groupby(by).agg(
        members=("checkins", "size"),
        checkins=("checkins", "sum"),
        active=("checkins", lambda s: int((s > 0).sum())),
    )
    out["checkins"] = out["checkins"].astype(int)
    out["active_rate"] = out["active"] / out["members"]
    out["checkins_per_member"] = out["checkins"] / out["members"]
    return (
        out.reset_index()
        .sort_values(["checkins", by], ascending=[False, True])
        .reset_index(drop=True)
    )


def kpis(
    members: pd.DataFrame, attendance: pd.DataFrame, events: pd.DataFrame
) -> dict[str, float | int]:
    """Headline numbers for the dashboard's KPI row."""
    ci = attendance[attendance["checked_in"] == 1]
    signups = len(attendance)
    n_members = int(members["member_id"].nunique())
    active = int(ci["member_id"].nunique())
    return {
        "members": n_members,
        "events": int(events["event_id"].nunique()),
        "signups": signups,
        "checkins": len(ci),
        "active_members": active,
        "active_rate": active / n_members if n_members else 0.0,
        "show_rate": len(ci) / signups if signups else 0.0,
        "repeat_rate": repeat_attendance_rate(attendance),
    }


def filter_data(
    members: pd.DataFrame,
    attendance: pd.DataFrame,
    events: pd.DataFrame,
    terms: list[str] | None = None,
    topics: list[str] | None = None,
    majors: list[str] | None = None,
    years: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Apply dashboard filters; attendance is restricted to the kept members and events.

    An empty or None filter means "no restriction" on that dimension.
    """
    if terms:
        events = events[events["term"].isin(terms)]
    if topics:
        events = events[events["topic"].isin(topics)]
    if majors:
        members = members[members["major"].isin(majors)]
    if years:
        members = members[members["class_year"].isin(years)]
    attendance = attendance[
        attendance["event_id"].isin(events["event_id"])
        & attendance["member_id"].isin(members["member_id"])
    ]
    return members, attendance, events
