"""Unit tests for the Plotly figure builders."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import pytest

from accviz import charts
from accviz.analysis import analyze
from accviz.budget import VARIANCE_COLUMNS, budget_summary
from accviz.receivables import AGING_COLUMNS, aging_summary
from accviz.statements import INCOME_COLUMNS, BalanceSheet


def annotation_texts(fig: go.Figure) -> list[str]:
    return [a.text for a in fig.layout.annotations]


def empty_balance_sheet() -> BalanceSheet:
    return BalanceSheet(
        as_of=pd.Timestamp("2025-01-31"),
        balances=pd.DataFrame(),
        total_assets=0.0,
        total_liabilities=0.0,
        share_capital=0.0,
        current_earnings=0.0,
        current_assets=0.0,
        current_liabilities=0.0,
        cash=0.0,
        receivables=0.0,
    )


@pytest.fixture
def tiny(tiny_dataset):
    return analyze(tiny_dataset)


def test_revenue_expense_trend_values(tiny):
    fig = charts.revenue_expense_trend(tiny.income_monthly)
    bars = {trace.name: list(trace.y) for trace in fig.data if trace.type == "bar"}
    assert bars["Revenue"] == pytest.approx([500, 300])
    assert bars["Total expenses"] == pytest.approx([300, 70])  # Jan 200 + 100; Feb 30 + 40
    line = [t for t in fig.data if t.name == "Net income"][0]
    assert list(line.y) == pytest.approx([200, 230])


def test_margin_trend_has_two_series(tiny):
    fig = charts.margin_trend(tiny.income_monthly)
    names = [t.name for t in fig.data]
    assert names == ["Gross margin %", "Net margin %"]
    gross = list(fig.data[0].y)
    assert gross[0] == pytest.approx(60.0)  # Jan 300 / 500


def test_waterfall_walks_from_revenue_to_net_income(tiny):
    fig = charts.income_waterfall(tiny.income_totals)
    values = list(fig.data[0].y)
    assert values == pytest.approx([800, -200, -130, 0, -40, 430])
    assert fig.data[0].measure[-1] == "total"


def test_expense_donut_uses_account_names(tiny):
    fig = charts.expense_donut(tiny.expenses)
    assert isinstance(fig.data[0], go.Pie)
    assert "Cost of Goods Sold" in list(fig.data[0].labels)


def test_cash_line_has_bar_and_line(tiny):
    fig = charts.cash_line(tiny.cash)
    assert {t.type for t in fig.data} == {"bar", "scatter"}
    assert list(fig.data[1].y) == pytest.approx([700, 1200])


def test_aging_bars_one_bar_per_bucket(tiny):
    fig = charts.aging_bars(tiny.aging_summary)
    assert len(fig.data[0].x) == 5


def test_budget_variance_bars_colour_by_favourability(tiny):
    fig = charts.budget_variance_bars(tiny.budget_summary)
    colors = list(fig.data[0].marker.color)
    assert len(colors) == len(tiny.budget_summary)
    assert charts.GREEN in colors and charts.RED in colors


def test_balance_sheet_chart_has_five_series(tiny):
    fig = charts.balance_sheet_composition(tiny.balance_sheet)
    assert len(fig.data) == 5
    assert list(fig.data[0].x) == ["Assets", "Liabilities and equity"]


@pytest.mark.parametrize(
    "build",
    [
        lambda: charts.revenue_expense_trend(pd.DataFrame(columns=INCOME_COLUMNS)),
        lambda: charts.margin_trend(pd.DataFrame(columns=INCOME_COLUMNS)),
        lambda: charts.expense_donut(pd.DataFrame(columns=["account_name", "amount"])),
        lambda: charts.income_waterfall({}),
        lambda: charts.cash_line(pd.DataFrame(columns=["period", "net_change", "closing_balance"])),
        lambda: charts.aging_bars(aging_summary(pd.DataFrame(columns=AGING_COLUMNS))),
        lambda: charts.budget_variance_bars(budget_summary(pd.DataFrame(columns=VARIANCE_COLUMNS))),
        lambda: charts.balance_sheet_composition(empty_balance_sheet()),
    ],
)
def test_empty_input_gives_a_no_data_figure(build):
    fig = build()
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0
    assert any("No data" in text for text in annotation_texts(fig))


def test_every_chart_has_a_title_and_template(tiny):
    figures = [
        charts.revenue_expense_trend(tiny.income_monthly),
        charts.margin_trend(tiny.income_monthly),
        charts.expense_donut(tiny.expenses),
        charts.income_waterfall(tiny.income_totals),
        charts.cash_line(tiny.cash),
        charts.aging_bars(tiny.aging_summary),
        charts.budget_variance_bars(tiny.budget_summary),
        charts.balance_sheet_composition(tiny.balance_sheet),
    ]
    for fig in figures:
        assert fig.layout.title.text
        assert fig.layout.template is not None
