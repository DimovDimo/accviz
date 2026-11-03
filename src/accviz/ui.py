"""Streamlit user interface for accviz.

The module contains the rendering logic. :mod:`accviz.dashboard` is the thin script that
Streamlit runs. The data directory defaults to the ``ACCVIZ_DATA_DIR`` environment
variable, then to ``data/sample``. Users can also upload their own CSV files; the four
required files are mandatory and ``supplier_invoices.csv`` is optional.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from accviz import audit as audit_mod
from accviz import charts, config, departments, forecast, statements
from accviz.analysis import AnalysisResult, analyze
from accviz.export import workbook_bytes
from accviz.loader import Dataset, load_raw_directory, prepare_dataset, read_csv_table
from accviz.report import RATIO_LABELS, format_value
from accviz.validation import ValidationResult

UPLOAD_KEYS = list(config.DATASET_FILES)
OPTIONAL_UPLOAD_KEYS = list(config.OPTIONAL_FILES)
TAB_NAMES = [
    "Overview",
    "Income statement",
    "Cash flow",
    "Balance sheet",
    "Receivables & payables",
    "Budget",
    "Forecast",
    "Audit",
    "Data quality",
]


def _default_data_dir() -> str:
    return os.environ.get("ACCVIZ_DATA_DIR", str(config.DEFAULT_DATA_DIR))


def directory_signature(directory: str) -> tuple:
    """File names, sizes and modification times, so that a changed file invalidates the cache."""
    base = Path(directory)
    names = list(config.DATASET_FILES.values()) + list(config.OPTIONAL_FILES.values())
    signature = []
    for name in names:
        path = base / name
        if path.is_file():
            stat = path.stat()
            signature.append((name, stat.st_size, stat.st_mtime_ns))
        else:
            signature.append((name, None, None))
    return tuple(signature)


@st.cache_data(show_spinner="Loading and validating data…")
def _load_directory_cached(directory: str, signature: tuple) -> tuple[Dataset | None, ValidationResult]:
    """``signature`` is only a cache key: a regenerated file must trigger a reload."""
    try:
        raw = load_raw_directory(directory)
    except FileNotFoundError as exc:
        result = ValidationResult()
        result.error(str(exc))
        return None, result
    return prepare_dataset(raw)


def load_from_directory(directory: str) -> tuple[Dataset | None, ValidationResult]:
    return _load_directory_cached(directory, directory_signature(directory))


def load_from_uploads(files: dict[str, object]) -> tuple[Dataset | None, ValidationResult]:
    raw: dict[str, pd.DataFrame] = {}
    problems = ValidationResult()
    for key, uploaded in files.items():
        if uploaded is None:
            continue
        name = config.DATASET_FILES.get(key) or config.OPTIONAL_FILES.get(key, key)
        try:
            raw[key] = read_csv_table(uploaded)
        except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError, ValueError) as exc:
            problems.error(f"{name}: could not be read as a CSV file ({exc.__class__.__name__}: {exc})")
    if problems.errors:
        return None, problems
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
    for key, filename in config.OPTIONAL_FILES.items():
        uploads[key] = st.sidebar.file_uploader(f"{filename} (optional)", type="csv", key=f"upload_{key}")
    if all(uploads[key] for key in UPLOAD_KEYS):
        return load_from_uploads(uploads)
    st.sidebar.info("Upload the four required files to analyse your own data.")
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
        ("Revenue vs budget", format_value("revenue_vs_budget_pct", result.kpis["revenue_vs_budget_pct"]), None),
    ]
    for col, (label, value, delta) in zip(cols2, values2):
        col.metric(label, value, delta)


def render_overview(result: AnalysisResult) -> None:
    render_kpis(result)
    left, right = st.columns([3, 2])
    left.plotly_chart(charts.revenue_expense_trend(result.income_monthly), width="stretch")
    right.plotly_chart(charts.expense_donut(result.expenses), width="stretch")
    if result.cash_flow is not None:
        cf = result.cash_flow
        status = "reconciled to the GL" if cf.is_reconciled() else f"difference {cf.difference:,.2f}"
        st.caption(f"Net cash flow {money(cf.net_change)} ({status}) · Audit findings: {result.audit.total_findings}")


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
    st.subheader("Expenses by cost centre (department)")
    if result.departments_monthly.empty:
        st.info("No expenses in the selected period.")
        return
    pivot = departments.department_pivot(result.departments_monthly)
    st.plotly_chart(charts.department_bars(pivot), width="stretch")
    st.dataframe(result.departments_summary.round(4), hide_index=True, width="stretch")


def render_cashflow(result: AnalysisResult) -> None:
    cf = result.cash_flow
    if cf is None:
        st.info("No cash flow data.")
        return
    if cf.is_reconciled():
        st.success(f"Cash flow reconciles to the general ledger: difference {cf.difference:,.2f} {config.CURRENCY}.")
    else:
        st.error(f"Cash flow does NOT reconcile: difference {cf.difference:,.2f} {config.CURRENCY}.")
    cols = st.columns(4)
    cols[0].metric("Opening cash", money(cf.opening_cash))
    cols[1].metric("Operating", money(cf.operating))
    cols[2].metric("Investing", money(cf.investing))
    cols[3].metric("Financing", money(cf.financing))
    cols2 = st.columns(2)
    cols2[0].metric("Net change in cash", money(cf.net_change))
    cols2[1].metric("Closing cash", money(cf.closing_cash))
    st.plotly_chart(charts.cash_flow_bars(result.cash_flow_monthly), width="stretch")
    st.subheader("Monthly statement (direct method)")
    st.dataframe(result.cash_flow_monthly.round(2), hide_index=True, width="stretch")
    st.subheader("Cash movements by account")
    st.dataframe(cf.lines.round(2), hide_index=True, width="stretch")
    st.caption(
        "Operating: customer receipts, supplier and staff payments, tax and interest. "
        "Investing: fixed assets. Financing: loan repayments and share capital. "
        "Opening-balance entries form the opening cash and are not flows."
    )


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
    st.subheader("Receivables (customers)")
    left, right = st.columns([3, 2])
    left.plotly_chart(charts.aging_bars(result.aging_summary), width="stretch")
    right.subheader("Top customers")
    right.dataframe(result.top_customers.round(2), hide_index=True, width="stretch")
    st.subheader("Open invoices at period end")
    st.dataframe(result.aging.round(2), hide_index=True, width="stretch")


def render_payables(result: AnalysisResult) -> None:
    st.subheader("Payables (suppliers)")
    if result.ap_aging.empty:
        st.info("No open supplier invoices. Add supplier_invoices.csv to analyse payables.")
    else:
        left, right = st.columns([3, 2])
        left.plotly_chart(charts.aging_bars(result.ap_summary), width="stretch")
        right.subheader("Largest open balances")
        right.dataframe(result.top_suppliers.round(2), hide_index=True, width="stretch")
        st.subheader("Open supplier invoices at period end")
        st.dataframe(result.ap_aging.round(2), hide_index=True, width="stretch")
    st.subheader("Reconciliation to the general ledger")
    table = result.reconciliation_table
    if table.empty:
        return
    for _, row in table.iterrows():
        if row["status"] == "reconciled":
            st.success(f"{row['control']} (GL {row['account_code']}) reconciles to the sub-ledger.")
        else:
            st.error(
                f"{row['control']} (GL {row['account_code']}) differs from the sub-ledger by "
                f"{row['difference']:,.2f} {config.CURRENCY}. Check for postings that bypass the sub-ledger."
            )
    st.dataframe(table.round(2), hide_index=True, width="stretch")


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


def render_forecast(ds: Dataset, result: AnalysisResult) -> None:
    horizon = st.slider("Months to forecast", min_value=3, max_value=12, value=6, key="forecast_horizon")
    history = forecast.revenue_series(statements.income_statement(ds.journal, ds.chart_of_accounts, None, result.end))
    try:
        model = forecast.fit_forecast(history, horizon)
    except ValueError as exc:
        st.info(f"Forecast not available: {exc}")
        return
    model_name = "trend × seasonal index" if model.seasonal else "linear trend (fewer than 24 months of history)"
    cols = st.columns(3)
    cols[0].metric("Model", "seasonal" if model.seasonal else "trend only", model_name)
    cols[1].metric("Residual std. deviation", money(model.residual_sd))
    mape = "–" if result.forecast_mape is None else f"{result.forecast_mape * 100:.1f} %"
    cols[2].metric("Backtest MAPE (6-month holdout)", mape)
    st.plotly_chart(charts.forecast_chart(model.table), width="stretch")
    st.subheader("Forecast by month")
    future = model.future.rename(columns={"value": "forecast", "lower": "lower 95 %", "upper": "upper 95 %"})
    st.dataframe(future[["period", "forecast", "lower 95 %", "upper 95 %"]].round(2), hide_index=True, width="stretch")
    st.caption(
        "Forecast = trend × seasonal index (seasonal indices need at least 24 months). "
        "The 95 % band is ±1.96 residual standard deviations. The backtest refits on all but the "
        "last six months of history and reports the mean absolute percentage error."
    )


def render_audit(result: AnalysisResult) -> None:
    audit = result.audit
    if audit is None:
        st.info("No audit results.")
        return
    st.caption(
        f"Entries tested: {audit.entries_tested:,} · manual entries: {audit.manual_entries:,} "
        f"({audit.manual_share:.1%}). Findings are indicators for review, not proof of error."
    )
    left, right = st.columns([3, 2])
    left.plotly_chart(charts.audit_bars(audit.summary), width="stretch")
    right.subheader("Rules")
    right.dataframe(audit.summary[["label", "severity", "findings", "entries"]], hide_index=True, width="stretch")
    b = audit.benford
    st.subheader("Benford first-digit test")
    text = (
        f"{b.count:,} amounts tested (recurring fixed amounts excluded: {b.excluded_recurring}). "
        f"Chi-square {b.chi_square:,.1f} against the critical value {b.critical_value} (8 df, 5 %): "
        f"{'passes' if b.passed else 'does not pass'}. Mean absolute deviation {b.mad:.4f}: {b.conformity}."
    )
    st.write(text)
    st.dataframe(b.digits.round(4), hide_index=True, width="stretch")
    st.caption(
        "Benford's law holds for amounts spread over several orders of magnitude. Narrow, "
        "single-decade ledgers, such as the synthetic sample, often do not conform, so treat this as an indicator."
    )
    st.subheader("Findings")
    if audit.findings.empty:
        st.success("No findings in the selected period.")
        return
    options = ["All rules"] + [audit_mod.RULE_LABELS[r] for r in audit_mod.RULES]
    choice = st.selectbox("Rule", options, key="audit_rule")
    shown = audit.findings
    if choice != "All rules":
        rule = next(r for r in audit_mod.RULES if audit_mod.RULE_LABELS[r] == choice)
        shown = shown[shown["rule"] == rule]
    st.dataframe(shown.round(2), hide_index=True, width="stretch")


def render_data_quality(ds: Dataset, result: AnalysisResult, validation: ValidationResult) -> None:
    st.subheader("Validation")
    st.write("No errors." if validation.ok else f"{len(validation.errors)} error(s).")
    st.write(f"Warnings: {len(validation.warnings)}")
    st.subheader("Row counts")
    st.write(
        pd.DataFrame(
            {
                "Table": ["Chart of accounts", "Journal lines", "Customer invoices", "Supplier invoices", "Budget rows"],
                "Rows": [
                    len(ds.chart_of_accounts),
                    len(ds.journal),
                    len(ds.invoices),
                    len(ds.supplier_invoices),
                    len(ds.budget),
                ],
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
    st.subheader("Control account reconciliations")
    st.dataframe(result.reconciliation_table.round(2), hide_index=True, width="stretch")


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
    st.sidebar.download_button(
        "Download Excel workbook (.xlsx)",
        data=workbook_bytes(result),
        file_name=f"accounting_{start:%Y%m%d}_{end:%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    tabs = st.tabs(TAB_NAMES)
    with tabs[0]:
        render_overview(result)
    with tabs[1]:
        render_income(result)
    with tabs[2]:
        render_cashflow(result)
    with tabs[3]:
        render_balance(result)
    with tabs[4]:
        render_receivables(result)
        render_payables(result)
    with tabs[5]:
        render_budget(ds, result)
    with tabs[6]:
        render_forecast(ds, result)
    with tabs[7]:
        render_audit(result)
    with tabs[8]:
        render_data_quality(ds, result, validation)
