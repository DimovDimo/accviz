"""Plotly figure builders.

Every builder takes plain DataFrames (or dictionaries) produced by the analytics layer and
returns a :class:`plotly.graph_objects.Figure`. Empty input yields a figure with a clear
"no data" message instead of raising an exception.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from accviz import config
from accviz.statements import BalanceSheet

# Colour palette: green = favourable/income, red = unfavourable, blue = neutral totals.
GREEN = "#2E7D32"
RED = "#C62828"
BLUE = "#1565C0"
ORANGE = "#EF6C00"
GREY = "#616161"
PALETTE = ["#1565C0", "#EF6C00", "#2E7D32", "#8E24AA", "#00897B", "#C62828", "#F9A825", "#5D4037"]
TEMPLATE = "plotly_white"


def _empty_figure(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        title=title,
        template=TEMPLATE,
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[
            {
                "text": "No data for the selected period",
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"size": 16, "color": GREY},
            }
        ],
    )
    return fig


def _money_axis(label: str = "") -> dict:
    return {"title": label or f"Amount ({config.CURRENCY})", "tickformat": ",.0f"}


def revenue_expense_trend(income: pd.DataFrame) -> go.Figure:
    """Monthly revenue and total expenses as bars, with net income as a line."""
    title = "Monthly revenue, expenses and net income"
    if income.empty:
        return _empty_figure(title)
    expenses = income["cost_of_sales"] + income["operating_expenses"] + income["financial_expenses"] + income["tax_expense"]
    fig = go.Figure()
    fig.add_bar(x=income["period"], y=income["revenue"], name="Revenue", marker_color=BLUE)
    fig.add_bar(x=income["period"], y=expenses, name="Total expenses", marker_color=ORANGE)
    fig.add_scatter(
        x=income["period"],
        y=income["net_income"],
        name="Net income",
        mode="lines+markers",
        line={"color": GREEN, "width": 3},
    )
    fig.update_layout(
        title=title,
        template=TEMPLATE,
        barmode="group",
        hovermode="x unified",
        yaxis=_money_axis(),
        legend={"orientation": "h", "y": -0.2},
    )
    return fig


def margin_trend(income: pd.DataFrame) -> go.Figure:
    """Gross and net margin in percent by month."""
    title = "Gross and net margin by month"
    if income.empty:
        return _empty_figure(title)
    revenue = income["revenue"].where(income["revenue"] != 0)
    gross = (income["gross_profit"] / revenue * 100).fillna(0)
    net = (income["net_income"] / revenue * 100).fillna(0)
    fig = go.Figure()
    fig.add_scatter(x=income["period"], y=gross, name="Gross margin %", mode="lines+markers", line={"color": BLUE})
    fig.add_scatter(x=income["period"], y=net, name="Net margin %", mode="lines+markers", line={"color": GREEN})
    fig.update_layout(title=title, template=TEMPLATE, yaxis=_money_axis("Margin (%)"), hovermode="x unified")
    return fig


def expense_donut(expenses: pd.DataFrame) -> go.Figure:
    """Share of each expense account in total expenses."""
    title = "Expense structure"
    if expenses.empty:
        return _empty_figure(title)
    fig = go.Figure(
        go.Pie(
            labels=expenses["account_name"],
            values=expenses["amount"],
            hole=0.45,
            marker={"colors": PALETTE},
            sort=False,
            textinfo="percent",
        )
    )
    fig.update_layout(title=title, template=TEMPLATE, legend={"orientation": "v"})
    return fig


def income_waterfall(totals: dict[str, float]) -> go.Figure:
    """Walk from revenue to net income (cost, expense and tax steps are negative)."""
    title = "Income statement waterfall (selected period)"
    if not totals or all(abs(v) < config.BALANCE_TOLERANCE for v in totals.values()):
        return _empty_figure(title)
    labels = ["Revenue", "Cost of sales", "Operating expenses", "Financial expenses", "Tax expense", "Net income"]
    values = [
        totals["revenue"],
        -totals["cost_of_sales"],
        -totals["operating_expenses"],
        -totals["financial_expenses"],
        -totals["tax_expense"],
        totals["net_income"],
    ]
    measures = ["absolute", "relative", "relative", "relative", "relative", "total"]
    fig = go.Figure(
        go.Waterfall(
            x=labels,
            y=values,
            measure=measures,
            increasing={"marker": {"color": GREEN}},
            decreasing={"marker": {"color": RED}},
            totals={"marker": {"color": BLUE}},
            connector={"line": {"color": GREY}},
            text=[f"{v:,.0f}" for v in values],
            textposition="outside",
        )
    )
    fig.update_layout(title=title, template=TEMPLATE, yaxis=_money_axis(), showlegend=False)
    return fig


def cash_line(cash: pd.DataFrame) -> go.Figure:
    """Closing cash balance by month with net movement bars."""
    title = "Cash balance and monthly net cash movement"
    if cash.empty:
        return _empty_figure(title)
    colors = [GREEN if v >= 0 else RED for v in cash["net_change"]]
    fig = go.Figure()
    fig.add_bar(x=cash["period"], y=cash["net_change"], name="Net cash movement", marker_color=colors, opacity=0.6)
    fig.add_scatter(
        x=cash["period"],
        y=cash["closing_balance"],
        name="Closing cash balance",
        mode="lines+markers",
        line={"color": BLUE, "width": 3},
        fill="tozeroy",
        fillcolor="rgba(21,101,192,0.08)",
    )
    fig.update_layout(title=title, template=TEMPLATE, yaxis=_money_axis(), hovermode="x unified")
    return fig


def aging_bars(summary: pd.DataFrame) -> go.Figure:
    """Outstanding receivables per aging bucket, green (current) to red (90+ days)."""
    title = "Accounts receivable aging"
    if summary.empty or summary["outstanding"].sum() == 0:
        return _empty_figure(title)
    colors = [GREEN, "#9E9D24", "#F9A825", ORANGE, RED][: len(summary)]
    fig = go.Figure(
        go.Bar(
            x=summary["bucket"],
            y=summary["outstanding"],
            marker_color=colors,
            text=[f"{v:,.0f} ({c} inv.)" for v, c in zip(summary["outstanding"], summary["invoice_count"])],
            textposition="outside",
        )
    )
    fig.update_layout(title=title, template=TEMPLATE, yaxis=_money_axis("Outstanding amount"))
    return fig


def budget_variance_bars(summary: pd.DataFrame) -> go.Figure:
    """Variance (actual - budget) per account; green when favourable, red otherwise."""
    title = "Budget variance by account (actual − budget)"
    if summary.empty:
        return _empty_figure(title)
    labels = summary["account_code"] + " " + summary["account_name"]
    colors = [GREEN if fav else RED for fav in summary["favorable"]]
    fig = go.Figure(
        go.Bar(
            x=summary["variance"],
            y=labels,
            orientation="h",
            marker_color=colors,
            text=[f"{v:+,.0f}" for v in summary["variance"]],
            textposition="outside",
        )
    )
    fig.update_layout(
        title=title,
        template=TEMPLATE,
        xaxis=_money_axis("Variance"),
        yaxis={"autorange": "reversed"},
        showlegend=False,
    )
    return fig


def balance_sheet_composition(bs: BalanceSheet) -> go.Figure:
    """Stacked columns: assets versus liabilities and equity."""
    title = f"Balance sheet composition as of {bs.as_of:%Y-%m-%d}"
    if abs(bs.total_assets) < config.BALANCE_TOLERANCE and abs(bs.total_liabilities + bs.total_equity) < config.BALANCE_TOLERANCE:
        return _empty_figure(title)
    current_assets = bs.current_assets
    non_current_assets = bs.total_assets - bs.current_assets
    current_liab = bs.current_liabilities
    non_current_liab = bs.total_liabilities - bs.current_liabilities
    categories = ["Assets", "Liabilities and equity"]
    series = [
        ("Current assets", [current_assets, 0.0], BLUE),
        ("Non-current assets", [non_current_assets, 0.0], "#90CAF9"),
        ("Current liabilities", [0.0, current_liab], ORANGE),
        ("Non-current liabilities", [0.0, non_current_liab], "#FFCC80"),
        ("Equity", [0.0, bs.total_equity], GREEN),
    ]
    fig = go.Figure()
    for name, values, color in series:
        fig.add_bar(x=categories, y=values, name=name, marker_color=color)
    fig.update_layout(
        title=title,
        template=TEMPLATE,
        barmode="stack",
        yaxis=_money_axis(),
        legend={"orientation": "h", "y": -0.2},
    )
    return fig


SECTION_COLORS = {"operating": BLUE, "investing": ORANGE, "financing": GREY}
SEVERITY_COLORS = {"high": RED, "medium": ORANGE, "low": BLUE}


def cash_flow_bars(monthly: pd.DataFrame) -> go.Figure:
    """Operating, investing and financing cash flow per month, with the net change as a line."""
    title = "Monthly cash flow by activity"
    if monthly.empty:
        return _empty_figure(title)
    fig = go.Figure()
    labels = {"operating": "Operating", "investing": "Investing", "financing": "Financing"}
    for key in ("operating", "investing", "financing"):
        fig.add_bar(x=monthly["period"], y=monthly[key], name=labels[key], marker_color=SECTION_COLORS[key])
    fig.add_scatter(
        x=monthly["period"],
        y=monthly["net_change"],
        name="Net change",
        mode="lines+markers",
        line={"color": GREEN, "width": 2},
    )
    fig.update_layout(
        title=title,
        template=TEMPLATE,
        barmode="relative",
        yaxis=_money_axis(),
        legend={"orientation": "h", "y": -0.2},
    )
    return fig


def forecast_chart(table: pd.DataFrame) -> go.Figure:
    """Actual monthly revenue, the fitted trend and the forecast with its 95 % band."""
    title = "Revenue: actual, forecast and 95 % band"
    if table.empty:
        return _empty_figure(title)
    actual = table[table["kind"] == "actual"]
    future = table[table["kind"] == "forecast"]
    fig = go.Figure()
    fig.add_scatter(x=actual["period"], y=actual["value"], name="Actual", mode="lines+markers", line={"color": BLUE})
    if "fitted" in actual and actual["fitted"].notna().any():
        fig.add_scatter(x=actual["period"], y=actual["fitted"], name="Fitted", mode="lines", line={"color": GREY, "dash": "dot"})
    if not future.empty:
        band_x = list(future["period"]) + list(future["period"][::-1])
        band_y = list(future["upper"]) + list(future["lower"][::-1])
        fig.add_scatter(x=band_x, y=band_y, fill="toself", fillcolor="rgba(239,108,0,0.15)", line={"width": 0},
                        name="95 % band", hoverinfo="skip")  # fmt: skip
        fig.add_scatter(x=future["period"], y=future["value"], name="Forecast", mode="lines+markers",
                        line={"color": ORANGE, "dash": "dash"})  # fmt: skip
    fig.update_layout(title=title, template=TEMPLATE, yaxis=_money_axis(), legend={"orientation": "h", "y": -0.2})
    return fig


def department_bars(pivot: pd.DataFrame) -> go.Figure:
    """Expenses per month stacked by department (cost centre)."""
    title = "Expenses by cost centre and month"
    if pivot.empty:
        return _empty_figure(title)
    fig = go.Figure()
    for i, column in enumerate(pivot.columns):
        fig.add_bar(x=list(pivot.index), y=pivot[column], name=str(column), marker_color=PALETTE[i % len(PALETTE)])
    fig.update_layout(title=title, template=TEMPLATE, barmode="stack", yaxis=_money_axis(),
                      legend={"orientation": "h", "y": -0.2})  # fmt: skip
    return fig


def audit_bars(summary: pd.DataFrame) -> go.Figure:
    """Number of lines flagged per audit rule, coloured by severity."""
    title = "Audit findings by rule"
    if summary.empty or summary["findings"].sum() == 0:
        return _empty_figure(title)
    colors = [SEVERITY_COLORS.get(sev, GREY) for sev in summary["severity"]]
    fig = go.Figure()
    fig.add_bar(x=summary["label"], y=summary["findings"], marker_color=colors,
                text=summary["findings"], textposition="auto", name="Findings")  # fmt: skip
    fig.update_layout(title=title, template=TEMPLATE, yaxis={"title": "Findings"})
    return fig
