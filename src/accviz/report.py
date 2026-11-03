"""Self-contained HTML report.

The report embeds Plotly's JavaScript once (in the first chart) so the file opens offline.
"""

from __future__ import annotations

import html
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from accviz import charts, config, departments
from accviz.analysis import AnalysisResult, analyze
from accviz.cashflow import SECTION_LABELS
from accviz.loader import Dataset

KPI_LABELS: dict[str, str] = {
    "revenue": "Revenue",
    "gross_profit": "Gross profit",
    "net_income": "Net income",
    "closing_cash": "Closing cash",
    "outstanding_receivables": "Outstanding receivables",
    "total_assets": "Total assets",
    "revenue_vs_budget_pct": "Revenue vs budget",
}
RATIO_LABELS: dict[str, str] = {
    "gross_margin": "Gross margin",
    "operating_margin": "Operating margin",
    "net_margin": "Net margin",
    "current_ratio": "Current ratio",
    "debt_to_equity": "Debt-to-equity",
}
PERCENT_KEYS = {"gross_margin", "operating_margin", "net_margin", "revenue_vs_budget_pct"}


def format_money(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "–"
    return f"{value:,.2f} {config.CURRENCY}"


def format_value(key: str, value: float | None) -> str:
    if value is None or pd.isna(value):
        return "–"
    if key in PERCENT_KEYS:
        # round first and add 0.0 so that a value of -0.0 is shown as 0.0 %, not -0.0 %
        return f"{round(value * 100, 1) + 0.0:,.1f} %"
    if key == "current_ratio" or key == "debt_to_equity":
        return f"{value:,.2f}"
    return format_money(value)


def _table(df: pd.DataFrame, money_cols: list[str] | None = None) -> str:
    """Render a DataFrame as an HTML table with formatted money columns."""
    shown = df.copy()
    for col in money_cols or []:
        if col in shown.columns:
            shown[col] = shown[col].map(lambda v: f"{v:,.2f}")
    return shown.to_html(index=False, escape=True, border=0, classes="data")


def _figure_html(fig: go.Figure, include_js: bool) -> str:
    return fig.to_html(
        full_html=False,
        include_plotlyjs=True if include_js else False,
        config={"displaylogo": False, "responsive": True},
    )


def _chart_sections(result: AnalysisResult) -> list[tuple[str, go.Figure]]:
    sections = [
        ("Revenue, expenses and net income", charts.revenue_expense_trend(result.income_monthly)),
        ("Margins", charts.margin_trend(result.income_monthly)),
        ("Income statement waterfall", charts.income_waterfall(result.income_totals)),
        ("Expense structure", charts.expense_donut(result.expenses)),
        ("Cash flow by activity", charts.cash_flow_bars(result.cash_flow_monthly)),
        ("Cash", charts.cash_line(result.cash)),
        ("Receivables aging", charts.aging_bars(result.aging_summary)),
        ("Payables aging", charts.aging_bars(result.ap_summary)),
        ("Budget variance", charts.budget_variance_bars(result.budget_summary)),
        ("Revenue forecast", charts.forecast_chart(result.forecast.table if result.forecast else pd.DataFrame())),
        ("Expenses by cost centre", charts.department_bars(departments.department_pivot(result.departments_monthly))),
        ("Audit findings by rule", charts.audit_bars(result.audit.summary if result.audit else pd.DataFrame())),
        ("Balance sheet composition", charts.balance_sheet_composition(result.balance_sheet)),
    ]
    return sections


_CSS = """
body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin: 0;
       background: #f5f7fa; color: #1f2933; }
header { background: #1f3a5f; color: #fff; padding: 24px 32px; }
header h1 { margin: 0 0 6px 0; font-size: 26px; }
header p { margin: 0; opacity: .85; }
main { padding: 24px 32px; max-width: 1280px; margin: auto; }
section { background: #fff; border-radius: 10px; padding: 20px 24px; margin-bottom: 22px;
          box-shadow: 0 1px 3px rgba(0,0,0,.08); }
h2 { margin-top: 0; font-size: 20px; color: #1f3a5f; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; }
.kpi { background: #f0f4fa; border-radius: 8px; padding: 14px; }
.kpi .label { font-size: 13px; color: #52606d; }
.kpi .value { font-size: 20px; font-weight: 600; margin-top: 4px; }
table.data { border-collapse: collapse; width: 100%; font-size: 14px; }
table.data th, table.data td { padding: 6px 10px; border-bottom: 1px solid #e4e7eb; text-align: right; }
table.data th:first-child, table.data td:first-child { text-align: left; }
table.data th { background: #f0f4fa; }
.status-ok { color: #2e7d32; font-weight: 600; }
.status-bad { color: #c62828; font-weight: 600; }
footer { text-align: center; color: #7b8794; font-size: 13px; padding: 16px; }
"""


def _cash_flow_html(result: AnalysisResult) -> str:
    cf = result.cash_flow
    if cf is None:
        return "<p>No cash flow data.</p>"
    summary = pd.DataFrame(
        {
            "Item": [
                "Opening cash",
                SECTION_LABELS["operating"],
                SECTION_LABELS["investing"],
                SECTION_LABELS["financing"],
                "Net change in cash",
                "Closing cash",
                "GL closing cash",
            ],
            "Amount": [
                cf.opening_cash,
                cf.operating,
                cf.investing,
                cf.financing,
                cf.net_change,
                cf.closing_cash,
                cf.gl_closing_cash,
            ],
        }
    )
    status = "reconciled to the general ledger" if cf.is_reconciled() else f"difference {cf.difference:,.2f}"
    monthly = result.cash_flow_monthly
    money = [c for c in monthly.columns if c != "period"]
    return (
        f"<p>Cash flow {status}.</p>"
        + _table(summary, ["Amount"])
        + "<h3>Monthly</h3>"
        + _table(monthly, money)
    )


def _payables_html(result: AnalysisResult) -> str:
    summary = _table(result.ap_summary[["bucket", "invoice_count", "outstanding"]], ["outstanding"])
    recon = _table(result.reconciliation_table.drop(columns=["status"], errors="ignore"),
                   ["gl_balance", "subledger_balance", "difference"]) if not result.reconciliation_table.empty else ""  # fmt: skip
    suppliers = _table(result.top_suppliers, ["outstanding"]) if not result.top_suppliers.empty else "<p>No open supplier invoices.</p>"  # fmt: skip
    return f"<h3>Aging</h3>{summary}<h3>Reconciliation to the general ledger</h3>{recon}<h3>Largest open balances</h3>{suppliers}"  # fmt: skip


def _forecast_html(result: AnalysisResult) -> str:
    if result.forecast is None:
        return f"<p>{html.escape(result.forecast_error or 'Forecast not available.')}</p>"
    fut = result.forecast.future.rename(columns={"value": "forecast", "lower": "lower 95 %", "upper": "upper 95 %"})
    mape = f"{result.forecast_mape * 100:.1f} %" if result.forecast_mape is not None else "–"
    model = "trend × seasonal index" if result.forecast.seasonal else "linear trend (fewer than 24 months)"
    return (
        f"<p>Model: {html.escape(model)}. Backtest MAPE on a 6-month holdout: {mape}.</p>"
        + _table(fut[["period", "forecast", "lower 95 %", "upper 95 %"]], ["forecast", "lower 95 %", "upper 95 %"])
    )


def _departments_html(result: AnalysisResult) -> str:
    if result.departments_summary.empty:
        return "<p>No expenses in the selected period.</p>"
    return _table(result.departments_summary, ["amount"])


def _audit_html(result: AnalysisResult) -> str:
    audit = result.audit
    if audit is None:
        return "<p>No audit results.</p>"
    b = audit.benford
    benford = (
        f"Benford first-digit test on {b.count:,} amounts: chi-square {b.chi_square:,.1f} "
        f"(critical value {b.critical_value}), MAD {b.mad:.4f} – {b.conformity}. "
        "Benford results are indicators, not proof of error."
    )
    summary = _table(audit.summary[["label", "severity", "findings", "entries"]])
    findings = audit.findings.head(25)
    shown = _table(findings[["date", "entry_id", "rule", "account_code", "amount", "detail"]], ["amount"])
    more = f"<p>Showing 25 of {len(audit.findings)} findings.</p>" if len(audit.findings) > 25 else ""
    return (
        f"<p>{html.escape(benford)}</p>{summary}"
        f"<h3>Findings</h3>{shown}{more}"
    )


def render_report(dataset: Dataset, start=None, end=None) -> str:
    """Return the complete HTML document for the selected period."""
    result = analyze(dataset, start, end)
    bs = result.balance_sheet
    balanced_label = (
        '<span class="status-ok">Balanced</span>' if bs.is_balanced() else '<span class="status-bad">NOT balanced</span>'
    )

    kpi_cards = "".join(
        f'<div class="kpi"><div class="label">{html.escape(label)}</div>'
        f'<div class="value">{html.escape(format_value(key, result.kpis.get(key)))}</div></div>'
        for key, label in KPI_LABELS.items()
    )
    ratio_rows = pd.DataFrame(
        {
            "Ratio": [RATIO_LABELS[k] for k in RATIO_LABELS],
            "Value": [format_value(k, result.ratios.get(k)) for k in RATIO_LABELS],
        }
    )

    income_table = result.income_monthly.copy()
    money_cols = [c for c in income_table.columns if c != "period"]
    income_html = _table(income_table, money_cols)

    aging_html = _table(result.aging_summary[["bucket", "invoice_count", "outstanding"]], ["outstanding"])
    budget_html = _table(
        result.budget_summary[["account_code", "account_name", "budget", "actual", "variance"]],
        ["budget", "actual", "variance"],
    )
    bs_rows = pd.DataFrame(
        {
            "Item": ["Total assets", "Total liabilities", "Share capital", "Current-period earnings", "Total equity"],
            "Amount": [
                bs.total_assets,
                bs.total_liabilities,
                bs.share_capital,
                bs.current_earnings,
                bs.total_equity,
            ],
        }
    )
    bs_html = _table(bs_rows, ["Amount"])
    cash_html = _cash_flow_html(result)
    payables_html = _payables_html(result)
    forecast_html = _forecast_html(result)
    departments_html = _departments_html(result)
    audit_html = _audit_html(result)

    chart_html = []
    for index, (title, fig) in enumerate(_chart_sections(result)):
        chart_html.append(
            f"<section><h2>{html.escape(title)}</h2>{_figure_html(fig, include_js=index == 0)}</section>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Accounting report – {html.escape(result.period_label)}</title>
<style>{_CSS}</style>
</head>
<body>
<header>
  <h1>Accounting visualization report</h1>
  <p>Period: {html.escape(result.period_label)} · Currency: {config.CURRENCY} · Balance sheet: {balanced_label}</p>
</header>
<main>
<section>
  <h2>Key figures</h2>
  <div class="kpis">{kpi_cards}</div>
</section>
{''.join(chart_html)}
<section>
  <h2>Financial ratios</h2>
  {_table(ratio_rows)}
</section>
<section>
  <h2>Monthly income statement</h2>
  {income_html}
</section>
<section>
  <h2>Cash flow statement (direct method)</h2>
  {cash_html}
</section>
<section>
  <h2>Balance sheet summary</h2>
  {bs_html}
</section>
<section>
  <h2>Receivables aging detail</h2>
  {aging_html}
</section>
<section>
  <h2>Payables aging and reconciliation</h2>
  {payables_html}
</section>
<section>
  <h2>Budget versus actual (by account)</h2>
  {budget_html}
</section>
<section>
  <h2>Revenue forecast</h2>
  {forecast_html}
</section>
<section>
  <h2>Cost centres (expenses by department)</h2>
  {departments_html}
</section>
<section>
  <h2>Journal audit analytics</h2>
  {audit_html}
</section>
</main>
<footer>Generated by accviz · synthetic sample data unless stated otherwise</footer>
</body>
</html>
"""


def write_report(dataset: Dataset, path: str | Path, start=None, end=None) -> Path:
    """Render the report and write it to *path* (parent folders are created)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(dataset, start, end), encoding="utf-8")
    return out
