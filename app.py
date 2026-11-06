"""ISN Engagement Dashboard (Streamlit).

Run with ``streamlit run app.py``. On first launch it generates the synthetic
seed exports and runs the ETL if ``data/isn.db`` does not exist yet.
All analysis lives in ``isn_engagement.metrics`` and ``isn_engagement.charts``;
this file only wires filters, layout, and widgets.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from isn_engagement import charts, db, metrics
from isn_engagement.bootstrap import ensure_database
from isn_engagement.terms import sort_terms

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("ISN_DB_PATH", ROOT / "data" / "isn.db"))
RAW_DIR = Path(os.environ.get("ISN_RAW_DIR", ROOT / "data" / "raw"))
REPORT_PATH = DB_PATH.with_name("quality_report.md")
YEAR_ORDER = ["Freshman", "Sophomore", "Junior", "Senior", "Graduate", "Unknown"]


@st.cache_data(show_spinner="Loading engagement data...")
def load(db_path: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ensure_database(Path(db_path), RAW_DIR, REPORT_PATH)
    conn = db.connect(db_path)
    try:
        return db.read_star(conn)
    finally:
        conn.close()


@st.cache_data
def named_query(db_path: str, name: str) -> pd.DataFrame:
    conn = db.connect(db_path)
    try:
        return db.run_named_query(conn, name)
    finally:
        conn.close()


def pct(x: float) -> str:
    return f"{x:.0%}"


st.set_page_config(page_title="ISN Engagement Dashboard", layout="wide")
members_all, events_all, attendance_all = load(str(DB_PATH))

st.title("ISN Member Engagement")
st.caption("Information Systems Network, Santa Clara University. Synthetic demo data.")

with st.sidebar:
    st.header("Filters")
    term_opts = sort_terms(set(events_all["term"]))
    sel_terms = st.multiselect("Term", term_opts, key="terms")
    sel_topics = st.multiselect("Topic", sorted(events_all["topic"].unique()), key="topics")
    sel_majors = st.multiselect("Major", sorted(members_all["major"].unique()), key="majors")
    years = [y for y in YEAR_ORDER if y in set(members_all["class_year"])]
    sel_years = st.multiselect("Class year", years, key="years")
    st.caption("Leave a filter empty to include everything.")

members, attendance, events = metrics.filter_data(
    members_all, attendance_all, events_all, sel_terms, sel_topics, sel_majors, sel_years
)
k = metrics.kpis(members, attendance, events)

cols = st.columns(6)
cols[0].metric("Members", k["members"])
cols[1].metric("Events", k["events"])
cols[2].metric("Check-ins", k["checkins"])
cols[3].metric("Active members", k["active_members"], help="Checked in at least once")
cols[4].metric("Show rate", pct(k["show_rate"]), help="Check-ins divided by signups")
cols[5].metric(
    "Repeat rate",
    pct(k["repeat_rate"]),
    help="Share of active members who attended 2 or more events",
)

tab_over, tab_topics, tab_ret, tab_churn, tab_members, tab_data = st.tabs(
    ["Overview", "Topics", "Retention", "Churn risk", "Members", "Data and SQL"]
)

with tab_over:
    trend = metrics.attendance_trend(attendance, events)
    st.plotly_chart(charts.attendance_trend_chart(trend), width="stretch")
    left, right = st.columns(2)
    summary = metrics.term_summary(attendance, events)
    left.plotly_chart(charts.term_chart(summary), width="stretch")
    right.plotly_chart(
        charts.frequency_chart(metrics.attendance_frequency(attendance)), width="stretch"
    )
    with st.expander("Per-event table"):
        st.dataframe(
            trend,
            hide_index=True,
            width="stretch",
            column_config={"show_rate": st.column_config.NumberColumn(format="percent")},
        )

with tab_topics:
    topics = metrics.topic_popularity(attendance, events)
    st.plotly_chart(charts.topic_chart(topics), width="stretch")
    if not topics.empty:
        top = topics.iloc[0]
        st.info(
            f"**{top['topic']}** draws the most people per event "
            f"({top['avg_turnout']:.1f} check-ins on average)."
        )
    st.dataframe(
        topics,
        hide_index=True,
        width="stretch",
        column_config={
            "show_rate": st.column_config.NumberColumn(format="percent"),
            "avg_fill_rate": st.column_config.NumberColumn(format="percent"),
            "avg_turnout": st.column_config.NumberColumn(format="%.1f"),
        },
    )

with tab_ret:
    rates = metrics.cohort_retention(members, attendance, events)
    st.plotly_chart(charts.cohort_heatmap(rates), width="stretch")
    st.subheader("Term over term retention")
    st.dataframe(
        metrics.term_retention(attendance, events),
        hide_index=True,
        width="stretch",
        column_config={"retention_rate": st.column_config.NumberColumn(format="percent")},
    )

with tab_churn:
    risk = metrics.churn_risk(members, attendance, events)
    left, right = st.columns([1, 2])
    left.plotly_chart(charts.churn_tier_chart(risk), width="stretch")
    with right:
        st.markdown(
            "**How the score works (0 to 100):** 50% recency (days since last check-in, "
            "or since joining if never checked in, capped at 120), 30% low frequency "
            "(fewer than 8 lifetime check-ins), 20% declining (active before but not in "
            "the latest term). High is above 70, Low is below 40."
        )
        tier = st.selectbox("Show tier", ["High", "Medium", "Low", "All"], key="tier")
    shown = risk if tier == "All" else risk[risk["risk_tier"] == tier]
    st.dataframe(
        shown,
        hide_index=True,
        width="stretch",
        column_config={
            "last_checkin": st.column_config.DateColumn("last check-in", format="YYYY-MM-DD"),
            "risk_score": st.column_config.ProgressColumn(
                "risk score", min_value=0, max_value=100, format="%.1f"
            ),
        },
    )
    st.download_button(
        "Download outreach list (CSV)",
        shown.to_csv(index=False),
        file_name=f"isn_churn_{tier.lower()}.csv",
        mime="text/csv",
    )

with tab_members:
    left, right = st.columns(2)
    by_major = metrics.breakdown(members, attendance, "major")
    by_year = metrics.breakdown(members, attendance, "class_year")
    left.plotly_chart(charts.breakdown_chart(by_major, "major", "Major"), width="stretch")
    right.plotly_chart(charts.breakdown_chart(by_year, "class_year", "Class year"), width="stretch")
    st.dataframe(
        by_major,
        hide_index=True,
        width="stretch",
        column_config={
            "active_rate": st.column_config.NumberColumn(format="percent"),
            "checkins_per_member": st.column_config.NumberColumn(format="%.2f"),
        },
    )

with tab_data:
    st.subheader("Data quality report (last ETL run)")
    if REPORT_PATH.exists():
        report_md = REPORT_PATH.read_text().removeprefix("# Data Quality Report\n")
        st.markdown(report_md)
    else:
        st.caption("No report found. Run `python -m isn_engagement.etl` to create one.")
    st.subheader("SQL queries")
    st.caption("The same metrics, written as plain SQL against the star schema (unfiltered).")
    query = st.selectbox("Query", db.list_queries(), key="query")
    st.code((db.SQL_DIR / f"{query}.sql").read_text(), language="sql")
    st.dataframe(named_query(str(DB_PATH), query), hide_index=True, width="stretch")
