import pandas as pd
import plotly.graph_objects as go
import pytest

from isn_engagement import charts, metrics


def test_trend_chart_has_two_series_on_one_axis(attendance, events) -> None:
    fig = charts.attendance_trend_chart(metrics.attendance_trend(attendance, events))
    assert [t.name for t in fig.data] == ["Signups", "Check-ins"]
    assert all(t.yaxis in (None, "y") for t in fig.data)  # never a dual axis


def test_cohort_heatmap_labels_and_blank_cells(members, attendance, events) -> None:
    fig = charts.cohort_heatmap(metrics.cohort_retention(members, attendance, events))
    heat = fig.data[0]
    assert isinstance(heat, go.Heatmap)
    assert heat.zmin == 0 and heat.zmax == 1
    assert heat.text[2][0] == ""  # Spring cohort cannot be active in Fall
    assert heat.text[0][0] == "100%"


def test_churn_chart_uses_status_colors_with_labels(members, attendance, events) -> None:
    fig = charts.churn_tier_chart(metrics.churn_risk(members, attendance, events))
    bar = fig.data[0]
    assert list(bar.x) == ["Low", "Medium", "High"]
    assert list(bar.marker.color) == [charts.STATUS[t] for t in ("Low", "Medium", "High")]
    assert all(":" in label for label in bar.text)  # never color alone


def test_topic_chart_sorted_with_headroom(attendance, events) -> None:
    topics = metrics.topic_popularity(attendance, events)
    fig = charts.topic_chart(topics)
    xs = list(fig.data[0].x)
    assert xs == sorted(xs)
    assert fig.layout.xaxis.range[1] > max(xs)


@pytest.mark.parametrize(
    "builder",
    [
        charts.attendance_trend_chart,
        charts.term_chart,
        charts.topic_chart,
        charts.cohort_heatmap,
        charts.frequency_chart,
        charts.churn_tier_chart,
    ],
)
def test_builders_handle_empty_frames(builder) -> None:
    fig = builder(pd.DataFrame())
    assert fig.layout.annotations[0].text == "No data for the current filters"


def test_breakdown_chart(members, attendance) -> None:
    fig = charts.breakdown_chart(metrics.breakdown(members, attendance, "major"), "major", "Major")
    assert "major" in fig.layout.title.text
    assert charts.breakdown_chart(pd.DataFrame(), "major", "Major").data == ()
