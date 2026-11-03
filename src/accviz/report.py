"""Self-contained HTML report.

The report embeds Plotly's JavaScript once (in the first chart) so the file opens offline.
"""

from __future__ import annotations

import html
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from accviz import charts, config
from accviz.analysis import AnalysisResult, analyze
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
        return f"{value * 100:,.1f} %"
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
    return [
        ("Revenue, expenses and net income", charts.revenue_expense_trend(result.income_monthly)),
        ("Margins", charts.margin_trend(result.income_monthly)),
        ("Income statement waterfall", charts.income_waterfall(result.income_totals)),
        ("Expense structure", charts.expense_donut(result.expenses)),
        ("Cash", charts.cash_line(result.cash)),
        ("Receivables aging", charts.aging_bars(result.aging_summary)),
        ("Budget variance", charts.budget_variance_bars(result.budget_summary)),
        ("Balance sheet composition", charts.balance_sheet_composition(result.balance_sheet)),
    ]


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
  <h2>Balance sheet summary</h2>
  {bs_html}
</section>
<section>
  <h2>Receivables aging detail</h2>
  {aging_html}
</section>
<section>
  <h2>Budget versus actual (by account)</h2>
  {budget_html}
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
