"""Plotly figure builders. Each takes a metrics DataFrame and returns a Figure.

Kept separate from the Streamlit app so charts can be unit tested and reused
in notebooks. Colors follow a fixed, colorblind-validated palette: categorical
hues are assigned in a fixed order, magnitude uses a single blue ramp, and the
churn tiers use reserved status colors that always ship with a text label.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
STATUS = {"Low": "#0ca30c", "Medium": "#fab219", "High": "#d03b3b"}
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURFACE = "#fcfcfb"


def _base(fig: go.Figure, title: str, height: int = 360) -> go.Figure:
    fig.update_layout(
        title={"text": title, "x": 0, "font": {"size": 16, "color": INK}},
        height=height,
        margin={"l": 8, "r": 8, "t": 48, "b": 8},
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font={"family": "system-ui, -apple-system, Segoe UI, sans-serif", "color": INK_2},
        hoverlabel={"bgcolor": "white", "font": {"color": INK}},
        legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 1, "xanchor": "right"},
        bargap=0.3,
    )
    fig.update_xaxes(showgrid=False, linecolor=AXIS, tickfont={"color": MUTED})
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=AXIS, tickfont={"color": MUTED})
    return fig


def _hbar_headroom(fig: go.Figure, values: pd.Series) -> go.Figure:
    """Leave room past the longest bar so outside value labels are not clipped."""
    top = float(values.max()) if len(values) else 0.0
    fig.update_xaxes(range=[0, top * 1.15 if top > 0 else 1])
    fig.update_traces(cliponaxis=False)
    return fig


def _empty(title: str) -> go.Figure:
    fig = _base(go.Figure(), title, height=240)
    fig.add_annotation(
        text="No data for the current filters",
        showarrow=False,
        font={"color": MUTED, "size": 14},
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def attendance_trend_chart(trend: pd.DataFrame) -> go.Figure:
    """Signups vs check-ins per event over time (two lines, one shared count axis)."""
    title = "Signups and check-ins per event"
    if trend.empty:
        return _empty(title)
    fig = go.Figure()
    custom = trend[["title", "topic", "show_rate"]].to_numpy()
    for name, col, color in (
        ("Signups", "signups", SERIES[1]),
        ("Check-ins", "checkins", SERIES[0]),
    ):
        fig.add_trace(
            go.Scatter(
                x=trend["event_date"],
                y=trend[col],
                name=name,
                mode="lines+markers",
                line={"width": 2, "color": color},
                marker={"size": 8, "color": color, "line": {"width": 2, "color": SURFACE}},
                customdata=custom,
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>%{customdata[1]}<br>"
                    f"{name}: %{{y}}<br>Show rate: %{{customdata[2]:.0%}}<extra></extra>"
                ),
            )
        )
    fig.update_layout(hovermode="x unified")
    fig.update_yaxes(title_text="People", rangemode="tozero")
    return _base(fig, title)


def term_chart(summary: pd.DataFrame) -> go.Figure:
    """Distinct active members per term."""
    title = "Active members per term"
    if summary.empty:
        return _empty(title)
    fig = go.Figure(
        go.Bar(
            x=summary["term"],
            y=summary["active_members"],
            marker={"color": SERIES[0], "cornerradius": 4},
            text=summary["active_members"],
            textposition="outside",
            textfont={"color": INK_2},
            customdata=summary[["events", "checkins", "avg_turnout"]].to_numpy(),
            hovertemplate=(
                "<b>%{x}</b><br>Active members: %{y}<br>Events: %{customdata[0]}"
                "<br>Check-ins: %{customdata[1]}<br>Avg turnout: %{customdata[2]:.1f}"
                "<extra></extra>"
            ),
        )
    )
    fig.update_yaxes(title_text="Members", rangemode="tozero")
    fig.update_traces(cliponaxis=False)
    return _base(fig, title)


def topic_chart(topics: pd.DataFrame) -> go.Figure:
    """Average turnout per event by topic, sorted, horizontal bars."""
    title = "Average turnout by workshop topic"
    if topics.empty:
        return _empty(title)
    data = topics.sort_values("avg_turnout")
    fig = go.Figure(
        go.Bar(
            x=data["avg_turnout"],
            y=data["topic"],
            orientation="h",
            marker={"color": SERIES[0], "cornerradius": 4},
            text=data["avg_turnout"].map(lambda v: f"{v:.1f}"),
            textposition="outside",
            textfont={"color": INK_2},
            customdata=data[["events", "show_rate", "avg_fill_rate"]].to_numpy(),
            hovertemplate=(
                "<b>%{y}</b><br>Avg turnout: %{x:.1f}<br>Events: %{customdata[0]}"
                "<br>Show rate: %{customdata[1]:.0%}<br>Avg fill rate: "
                "%{customdata[2]:.0%}<extra></extra>"
            ),
        )
    )
    fig.update_xaxes(title_text="Check-ins per event", showgrid=True, gridcolor=GRID)
    fig.update_yaxes(showgrid=False)
    _hbar_headroom(fig, data["avg_turnout"])
    return _base(fig, title, height=max(260, 48 * len(data) + 80))


def cohort_heatmap(rates: pd.DataFrame) -> go.Figure:
    """Cohort x term retention heatmap on a single-hue sequential ramp."""
    title = "Cohort retention (share of each join cohort active per term)"
    if rates.empty:
        return _empty(title)
    z = rates.to_numpy(dtype=float)
    text = [["" if pd.isna(v) else f"{v:.0%}" for v in row] for row in z]
    scale = [[i / (len(BLUE_RAMP) - 1), c] for i, c in enumerate(BLUE_RAMP)]
    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=list(rates.columns),
            y=list(rates.index),
            text=text,
            texttemplate="%{text}",
            colorscale=scale,
            zmin=0,
            zmax=1,
            xgap=2,
            ygap=2,
            colorbar={"title": {"text": "Active"}, "tickformat": ".0%"},
            hovertemplate="Cohort %{y}<br>%{x}: %{z:.0%} active<extra></extra>",
        )
    )
    fig.update_yaxes(autorange="reversed", title_text="Join cohort", showgrid=False)
    fig.update_xaxes(title_text="Active term")
    return _base(fig, title, height=300)


def breakdown_chart(data: pd.DataFrame, by: str, label: str) -> go.Figure:
    """Check-ins per member by a member attribute (major or class year)."""
    title = f"Check-ins per member by {label.lower()}"
    if data.empty:
        return _empty(title)
    d = data.sort_values("checkins_per_member")
    fig = go.Figure(
        go.Bar(
            x=d["checkins_per_member"],
            y=d[by],
            orientation="h",
            marker={"color": SERIES[0], "cornerradius": 4},
            text=d["checkins_per_member"].map(lambda v: f"{v:.1f}"),
            textposition="outside",
            textfont={"color": INK_2},
            customdata=d[["members", "active", "checkins"]].to_numpy(),
            hovertemplate=(
                "<b>%{y}</b><br>Check-ins per member: %{x:.2f}<br>Members: "
                "%{customdata[0]}<br>Active: %{customdata[1]}<br>Check-ins: "
                "%{customdata[2]}<extra></extra>"
            ),
        )
    )
    fig.update_xaxes(showgrid=True, gridcolor=GRID)
    fig.update_yaxes(showgrid=False)
    _hbar_headroom(fig, d["checkins_per_member"])
    return _base(fig, title, height=max(260, 44 * len(d) + 80))


def frequency_chart(freq: pd.DataFrame) -> go.Figure:
    """How many active members attended 1, 2, 3, ... events."""
    title = "How many events do active members attend?"
    if freq.empty:
        return _empty(title)
    fig = go.Figure(
        go.Bar(
            x=freq["events_attended"],
            y=freq["members"],
            marker={"color": SERIES[0], "cornerradius": 4},
            hovertemplate="%{x} events: %{y} members<extra></extra>",
        )
    )
    fig.update_xaxes(title_text="Events attended", dtick=1)
    fig.update_yaxes(title_text="Members", rangemode="tozero")
    fig.update_traces(cliponaxis=False)
    return _base(fig, title, height=300)


def churn_tier_chart(risk: pd.DataFrame) -> go.Figure:
    """Member count per churn-risk tier, status colored and labeled."""
    title = "Members by churn-risk tier"
    if risk.empty:
        return _empty(title)
    counts = risk["risk_tier"].value_counts().reindex(list(STATUS), fill_value=0)
    fig = go.Figure(
        go.Bar(
            x=list(counts.index),
            y=counts.to_numpy(),
            marker={"color": [STATUS[t] for t in counts.index], "cornerradius": 4},
            text=[f"{t}: {n}" for t, n in counts.items()],
            textposition="outside",
            textfont={"color": INK_2},
            hovertemplate="%{x} risk: %{y} members<extra></extra>",
        )
    )
    fig.update_yaxes(title_text="Members", rangemode="tozero")
    fig.update_traces(cliponaxis=False)
    return _base(fig, title, height=300)
