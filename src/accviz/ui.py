"""Streamlit user interface for accviz.

The module contains the rendering logic. :mod:`accviz.dashboard` is the thin script that
Streamlit runs. The data directory defaults to the ``ACCVIZ_DATA_DIR`` environment
variable, then to ``data/sample``. Users can also upload their own four CSV files.
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from accviz import charts, config
from accviz.analysis import AnalysisResult, analyze
from accviz.loader import Dataset, load_raw_directory, prepare_dataset
from accviz.report import RATIO_LABELS, format_value
from accviz.validation import ValidationResult

UPLOAD_KEYS = list(config.DATASET_FILES)


def _default_data_dir() -> str:
    return os.environ.get("ACCVIZ_DATA_DIR", str(config.DEFAULT_DATA_DIR))


@st.cache_data(show_spinner="Loading and validating data…")
def load_from_directory(directory: str) -> tuple[Dataset | None, ValidationResult]:
    try:
        raw = load_raw_directory(directory)
    except FileNotFoundError as exc:
        result = ValidationResult()
        result.error(str(exc))
        return None, result
    return prepare_dataset(raw)


def load_from_uploads(files: dict[str, object]) -> tuple[Dataset | None, ValidationResult]:
    raw = {key: pd.read_csv(f, dtype=str, keep_default_na=False) for key, f in files.items()}
    return prepare_dataset(raw)


def money(value: float | None) -> str:
    return format_value("revenue", value)


def sidebar_source() -> tuple[Dataset | None, ValidationResult]:
    st.sidebar.header("Data source")
    source = st.sidebar.radio("Choose data", ["Directory", "Upload CSV files"], horizontal=False)
    if source == "Directory":
        directory = st.sidebar.text_input("Data directory", value=_default_data_dir())
        return load_from_directory(directory)

    uploads = {}
    for key, filename in config.DATASET_FILES.items():
        uploads[key] = st.sidebar.file_uploader(filename, type="csv", key=f"upload_{key}")
    if all(uploads.values()):
        return load_from_uploads(uploads)
    st.sidebar.info("Upload all four files to analyse your own data.")
    return None, ValidationResult()


def sidebar_period(ds: Dataset) -> tuple[pd.Timestamp, pd.Timestamp]:
    min_day, max_day = ds.start_date.date(), ds.end_date.date()
    st.sidebar.header("Period")
    selection = st.sidebar.date_input(
        "Date range",
        value=(min_day, max_day),
        min_value=min_day,
        max_value=max_day,
        format="YYYY-MM-DD",
    )
    if isinstance(selection, (list, tuple)):
        if len(selection) == 2:
            start, end = selection
        elif len(selection) == 1:
            start, end = selection[0], selection[0]
        else:
            start, end = min_day, max_day
    else:
        start, end = selection, selection
    return pd.Timestamp(start), pd.Timestamp(end)


def render_validation(result: ValidationResult) -> None:
    if result.errors:
        st.error("The data contains errors and cannot be analysed:\n\n" + "\n\n".join(f"- {e}" for e in result.errors))
    if result.warnings:
        with st.expander(f"Data quality warnings ({len(result.warnings)})", expanded=not result.errors):
            for warning in result.warnings:
                st.warning(warning)


def render_kpis(result: AnalysisResult) -> None:
    cols = st.columns(4)
    values = [
        ("Revenue", money(result.kpis["revenue"]), None),
        ("Net income", money(result.kpis["net_income"]), format_value("net_margin", result.ratios["net_margin"]) + " net margin"),
        ("Closing cash", money(result.kpis["closing_cash"]), None),
        ("Outstanding receivables", money(result.kpis["outstanding_receivables"]), None),
    ]
    for col, (label, value, delta) in zip(cols, values):
        col.metric(label, value, delta)
    cols2 = st.columns(4)
    values2 = [
        ("Gross profit", money(result.kpis["gross_profit"]), None),
        ("Total assets", money(result.kpis["total_assets"]), None),
        ("Current ratio", format_value("current_ratio", result.ratios["current_ratio"]), None),
        (
            "Revenue vs budget",
            format_value("revenue_vs_budget_pct", result.kpis["revenue_vs_budget_pct"]),
            None,
        ),
    ]
    for col, (label, value, delta) in zip(cols2, values2):
        col.metric(label, value, delta)


def render_overview(result: AnalysisResult) -> None:
    render_kpis(result)
    left, right = st.columns([3, 2])
    left.plotly_chart(charts.revenue_expense_trend(result.income_monthly), width="stretch")
    right.plotly_chart(charts.expense_donut(result.expenses), width="stretch")


def render_income(result: AnalysisResult) -> None:
    left, right = st.columns(2)
    left.plotly_chart(charts.income_waterfall(result.income_totals), width="stretch")
    right.plotly_chart(charts.margin_trend(result.income_monthly), width="stretch")
    st.subheader("Monthly income statement")
    st.dataframe(result.income_monthly.round(2), hide_index=True, width="stretch")
    st.subheader("Financial ratios")
    ratio_df = pd.DataFrame(
        {
            "Ratio": [RATIO_LABELS[k] for k in RATIO_LABELS],
            "Value": [format_value(k, result.ratios.get(k)) for k in RATIO_LABELS],
        }
    )
    st.dataframe(ratio_df, hide_index=True, width="stretch")
    st.subheader("Revenue and expense by account")
    left, right = st.columns(2)
    left.dataframe(result.revenues.round(2), hide_index=True, width="stretch")
    right.dataframe(result.expenses.round(2), hide_index=True, width="stretch")


def render_balance(result: AnalysisResult) -> None:
    bs = result.balance_sheet
    if bs.is_balanced():
        st.success(f"Balance sheet as of {bs.as_of:%Y-%m-%d} is balanced (assets = liabilities + equity).")
    else:
        st.error(f"Balance sheet is NOT balanced: difference {bs.difference:,.2f} {config.CURRENCY}.")
    left, right = st.columns(2)
    left.plotly_chart(charts.balance_sheet_composition(bs), width="stretch")
    right.plotly_chart(charts.cash_line(result.cash), width="stretch")
    summary = pd.DataFrame(
        {
            "Item": ["Total assets", "Total liabilities", "Share capital", "Current-period earnings", "Total equity"],
            "Amount": [bs.total_assets, bs.total_liabilities, bs.share_capital, bs.current_earnings, bs.total_equity],
        }
    )
    st.dataframe(summary.round(2), hide_index=True, width="stretch")


def render_receivables(result: AnalysisResult) -> None:
    left, right = st.columns([3, 2])
    left.plotly_chart(charts.aging_bars(result.aging_summary), width="stretch")
    right.subheader("Top customers")
    right.dataframe(result.top_customers.round(2), hide_index=True, width="stretch")
    st.subheader("Open invoices at period end")
    st.dataframe(result.aging.round(2), hide_index=True, width="stretch")


def render_budget(ds: Dataset, result: AnalysisResult) -> None:
    if ds.budget.empty:
        st.info("No budget rows in the data: add budget.csv to compare actuals with a budget.")
        return
    if result.budget_summary.empty:
        st.info("No budget rows for the selected period.")
        return
    st.plotly_chart(charts.budget_variance_bars(result.budget_summary), width="stretch")
    st.subheader("Budget versus actual by month and account")
    st.dataframe(result.budget_monthly.round(2), hide_index=True, width="stretch")


def render_data_quality(ds: Dataset, result: AnalysisResult, validation: ValidationResult) -> None:
    st.subheader("Validation")
    st.write("No errors." if validation.ok else f"{len(validation.errors)} error(s).")
    st.write(f"Warnings: {len(validation.warnings)}")
    st.subheader("Row counts")
    st.write(
        pd.DataFrame(
            {
                "Table": ["Chart of accounts", "Journal lines", "Invoices", "Budget rows"],
                "Rows": [len(ds.chart_of_accounts), len(ds.journal), len(ds.invoices), len(ds.budget)],
            }
        )
    )
    st.subheader(f"Trial balance ({result.period_label})")
    tb = result.trial_balance[["account_code", "account_name", "debit", "credit", "balance"]]
    total_debit, total_credit = tb["debit"].sum(), tb["credit"].sum()
    if abs(total_debit - total_credit) <= config.BALANCE_TOLERANCE:
        st.success(f"Trial balance is balanced: debits {total_debit:,.2f} = credits {total_credit:,.2f}.")
    else:
        st.error(f"Trial balance is NOT balanced: debits {total_debit:,.2f} ≠ credits {total_credit:,.2f}.")
    st.dataframe(tb.round(2), hide_index=True, width="stretch")


def main() -> None:
    st.set_page_config(page_title="Accounting Visualization", page_icon="📊", layout="wide")
    st.title("📊 Accounting Visualization Dashboard")
    ds, validation = sidebar_source()
    if ds is None or not validation.ok:
        render_validation(validation)
        st.stop()
    render_validation(validation)

    start, end = sidebar_period(ds)
    if start > end:
        st.error("The start date must not be after the end date.")
        st.stop()
    result = analyze(ds, start, end)
    st.caption(f"Period: {result.period_label} · Currency: {config.CURRENCY}")

    tabs = st.tabs(["Overview", "Income statement", "Balance sheet & cash", "Receivables", "Budget", "Data quality"])
    with tabs[0]:
        render_overview(result)
    with tabs[1]:
        render_income(result)
    with tabs[2]:
        render_balance(result)
    with tabs[3]:
        render_receivables(result)
    with tabs[4]:
        render_budget(ds, result)
    with tabs[5]:
        render_data_quality(ds, result, validation)

