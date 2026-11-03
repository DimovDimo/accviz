"""Excel workbook export (OOXML ``.xlsx`` via openpyxl).

The workbook has eleven sheets. Each sheet has a bold, shaded header row, frozen panes,
automatic column widths and number formats: money as ``#,##0.00``, percentages as
``0.0 %`` and counts as integers. Sheets can hold several titled tables (for example a
summary block above the detail).
"""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from accviz import config
from accviz.analysis import AnalysisResult, analyze
from accviz.loader import Dataset
from accviz.report import KPI_LABELS, RATIO_LABELS, format_value

SHEET_NAMES: tuple[str, ...] = (
    "Summary",
    "Income statement",
    "Cash flow",
    "Balance sheet",
    "Trial balance",
    "Receivables aging",
    "Payables aging",
    "Budget variance",
    "Departments",
    "Forecast",
    "Audit findings",
)

MONEY_FORMAT = "#,##0.00"
PERCENT_FORMAT = "0.0%"
INTEGER_FORMAT = "0"
DATE_FORMAT = "yyyy-mm-dd"
HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=12, color="1F3A5F")
PERCENT_COLUMNS = {"share", "variance_pct", "detection_rate", "observed_pct", "expected_pct", "margin"}
INTEGER_COLUMNS = {"invoice_count", "findings", "entries", "injected", "detected", "digit", "count", "entry_count"}
MAX_COLUMN_WIDTH = 48


def _format_for(column: str, series: pd.Series) -> str | None:
    if column in PERCENT_COLUMNS:
        return PERCENT_FORMAT
    if column in INTEGER_COLUMNS or pd.api.types.is_integer_dtype(series):
        return INTEGER_FORMAT
    if pd.api.types.is_datetime64_any_dtype(series):
        return DATE_FORMAT
    if pd.api.types.is_float_dtype(series):
        return MONEY_FORMAT
    return None


def _header_label(name: str) -> str:
    """'gl_closing_cash' -> 'GL closing cash'."""
    words = str(name).replace("_", " ").split()
    labels = [w.upper() if w.lower() == "gl" else w.lower() for w in words]
    text = " ".join(labels)
    return text[:1].upper() + text[1:]


def _clean(value, decimals: int = 2):
    """Convert numpy/pandas scalars to plain Python values that openpyxl can store.

    Floats are rounded (money to cents, ratios to 6 decimals) so float noise such as
    5.8e-11 never reaches the cell.
    """
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.to_pydatetime()
    if isinstance(value, (np.floating, float)):
        return None if math.isnan(float(value)) else round(float(value), decimals)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if value is pd.NaT:
        return None
    return value


def _write_table(ws, row: int, title: str | None, df: pd.DataFrame, freeze: bool = False) -> int:
    """Write an optional title and a formatted table. Returns the next free row (one blank line later)."""
    if title:
        ws.cell(row=row, column=1, value=title).font = TITLE_FONT
        row += 1
    if df.empty and len(df.columns) == 0:
        return row + 1
    header_row = row
    for col_idx, name in enumerate(df.columns, start=1):
        cell = ws.cell(row=row, column=col_idx, value=_header_label(name))
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    formats = {col: _format_for(col, df[col]) for col in df.columns}
    for values in df.itertuples(index=False, name=None):
        row += 1
        for col_idx, (col, value) in enumerate(zip(df.columns, values), start=1):
            decimals = 6 if col in PERCENT_COLUMNS else 2
            cell = ws.cell(row=row, column=col_idx, value=_clean(value, decimals))
            fmt = formats[col]
            if fmt:
                cell.number_format = fmt
    if freeze:
        ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    return row + 2


def _autosize(ws) -> None:
    widths: dict[int, int] = {}
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is None:
                continue
            text = f"{cell.value:,.2f}" if isinstance(cell.value, float) else str(cell.value)
            widths[cell.column] = max(widths.get(cell.column, 0), len(text))
    for col_idx, width in widths.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max(width + 2, 10), MAX_COLUMN_WIDTH)


def _summary_frame(result: AnalysisResult) -> pd.DataFrame:
    rows = [{"item": "Period", "value": result.period_label}, {"item": "Currency", "value": config.CURRENCY}]
    rows += [{"item": KPI_LABELS[k], "value": format_value(k, result.kpis.get(k))} for k in KPI_LABELS]
    rows += [{"item": RATIO_LABELS[k], "value": format_value(k, result.ratios.get(k))} for k in RATIO_LABELS]
    bs = result.balance_sheet
    rows.append({"item": "Balance sheet", "value": "balanced" if bs.is_balanced() else f"difference {bs.difference:,.2f}"})
    cf = result.cash_flow
    if cf is not None:
        rows.append({"item": "Net cash flow", "value": f"{cf.net_change:,.2f}"})
        rows.append({"item": "Cash flow reconciliation", "value": "reconciled" if cf.is_reconciled() else "difference"})
    return pd.DataFrame(rows)


def _balance_sheet_frame(result: AnalysisResult) -> pd.DataFrame:
    bs = result.balance_sheet
    return pd.DataFrame(
        {
            "item": ["Total assets", "Total liabilities", "Share capital", "Current-period earnings", "Total equity"],
            "amount": [bs.total_assets, bs.total_liabilities, bs.share_capital, bs.current_earnings, bs.total_equity],
        }
    )


def _forecast_frame(result: AnalysisResult) -> list[tuple[str | None, pd.DataFrame]]:
    if result.forecast is None:
        note = pd.DataFrame({"note": [result.forecast_error or "forecast not available"]})
        return [("Forecast", note)]
    table = result.forecast.table[["period", "kind", "value", "lower", "upper"]].rename(
        columns={"value": "revenue"}
    )
    notes = pd.DataFrame(
        {
            "parameter": ["Model", "Residual standard deviation", "Backtest MAPE (6-month holdout)"],
            "value": [
                "trend × seasonal index" if result.forecast.seasonal else "linear trend (under 24 months)",
                result.forecast.residual_sd,
                result.forecast_mape if result.forecast_mape is not None else float("nan"),
            ],
        }
    )
    return [("Monthly revenue", table), ("Model parameters", notes)]


def _audit_frames(result: AnalysisResult) -> list[tuple[str | None, pd.DataFrame]]:
    audit = result.audit
    if audit is None:
        return [("Audit", pd.DataFrame({"note": ["no audit results"]}))]
    b = audit.benford
    benford = pd.DataFrame(
        {
            "measure": ["Amounts tested", "Chi-square", "Critical value (8 df, 5 %)", "Mean absolute deviation", "Conformity"],
            "value": [b.count, b.chi_square, b.critical_value, b.mad, b.conformity],
        }
    )
    return [
        ("Findings by rule", audit.summary),
        ("Benford first-digit test", benford),
        ("Findings", audit.findings),
    ]


def build_workbook(result: AnalysisResult) -> Workbook:
    """Create the eleven-sheet workbook for an :class:`AnalysisResult`."""
    wb = Workbook()
    wb.remove(wb.active)
    sheets: dict[str, list[tuple[str | None, pd.DataFrame]]] = {
        "Summary": [(None, _summary_frame(result))],
        "Income statement": [(None, result.income_monthly)],
        "Cash flow": [
            ("Monthly cash flow (direct method)", result.cash_flow_monthly),
        ],
        "Balance sheet": [(None, _balance_sheet_frame(result))],
        "Trial balance": [(None, result.trial_balance)],
        "Receivables aging": [
            ("Aging summary", result.aging_summary),
            ("Open invoices", result.aging),
        ],
        "Payables aging": [
            ("Aging summary", result.ap_summary),
            ("Open supplier invoices", result.ap_aging),
            ("Reconciliation to GL", result.reconciliation_table),
        ],
        "Budget variance": [(None, result.budget_monthly)],
        "Departments": [
            ("Expenses by department and month", result.departments_monthly),
            ("Share of total expenses", result.departments_summary),
        ],
        "Forecast": _forecast_frame(result),
        "Audit findings": _audit_frames(result),
    }
    for name in SHEET_NAMES:
        ws = wb.create_sheet(title=name)
        row = 1
        for index, (title, frame) in enumerate(sheets[name]):
            if name == "Cash flow" and result.cash_flow is not None and index == 0:
                row = _write_cash_flow_header(ws, row, result)
            # Freeze the header only when the first table starts at the top of the sheet.
            freeze = index == 0 and row == 1 and name != "Summary"
            row = _write_table(ws, row, title, frame, freeze=freeze)
        _autosize(ws)
    return wb


def _write_cash_flow_header(ws, row: int, result: AnalysisResult) -> int:
    cf = result.cash_flow
    ws.cell(row=row, column=1, value="Statement for the selected period").font = TITLE_FONT
    lines = [
        ("Opening cash", cf.opening_cash),
        ("Operating activities", cf.operating),
        ("Investing activities", cf.investing),
        ("Financing activities", cf.financing),
        ("Net change in cash", cf.net_change),
        ("Closing cash", cf.closing_cash),
        ("GL closing cash", cf.gl_closing_cash),
        ("Difference (must be 0)", cf.difference),
    ]
    for offset, (label, value) in enumerate(lines, start=1):
        ws.cell(row=row + offset, column=1, value=label)
        cell = ws.cell(row=row + offset, column=2, value=_clean(float(value)))
        cell.number_format = MONEY_FORMAT
    return row + len(lines) + 3


def workbook_bytes(result: AnalysisResult) -> bytes:
    """The workbook as bytes (used by the dashboard download button)."""
    buffer = io.BytesIO()
    build_workbook(result).save(buffer)
    return buffer.getvalue()


def export_workbook(dataset: Dataset, path: str | Path, start=None, end=None) -> Path:
    """Analyse [start, end] and write the workbook to *path* (folders are created)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    result = analyze(dataset, start, end)
    build_workbook(result).save(out)
    return out


def sheet_names(workbook: Workbook) -> Iterable[str]:
    return list(workbook.sheetnames)
