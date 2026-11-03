"""Unit tests for the Excel export (I-4)."""

from __future__ import annotations

import io
import math

import pandas as pd
import pytest
from openpyxl import Workbook, load_workbook

from accviz import export
from accviz.analysis import analyze

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def result(small_sample_dataset):
    return analyze(small_sample_dataset)


@pytest.fixture(scope="module")
def workbook(result):
    return load_workbook(io.BytesIO(export.workbook_bytes(result)))


def test_eleven_sheets_in_the_documented_order(workbook):
    assert tuple(workbook.sheetnames) == export.SHEET_NAMES
    assert len(workbook.sheetnames) == 11


def test_header_row_is_bold_shaded_and_frozen(workbook):
    ws = workbook["Income statement"]
    header = ws["A1"]
    assert header.font.bold
    assert header.fill.fgColor.rgb.endswith("1F3A5F")
    assert ws.freeze_panes == "A2"


def test_money_and_percent_formats(workbook):
    ws = workbook["Income statement"]
    assert ws["B2"].number_format == export.MONEY_FORMAT
    audit_ws = workbook["Departments"]
    shares = [c for row in audit_ws.iter_rows() for c in row if c.value == "Share"]
    assert shares  # header present
    # The share table sits below the monthly table: find a cell with a percent format.
    percent_cells = [c for row in audit_ws.iter_rows() for c in row if c.number_format == export.PERCENT_FORMAT]
    assert percent_cells


def test_values_round_trip_and_match_the_analysis(result, workbook):
    ws = workbook["Income statement"]
    headers = [c.value for c in ws[1]]
    revenue_col = headers.index("Revenue") + 1
    first_row = [c.value for c in ws[2]]
    assert first_row[0] == result.income_monthly.iloc[0]["period"]
    assert first_row[revenue_col - 1] == pytest.approx(result.income_monthly.iloc[0]["revenue"], abs=0.01)


def test_cash_flow_sheet_has_statement_block_with_zero_difference(workbook):
    ws = workbook["Cash flow"]
    labels = {ws.cell(row=r, column=1).value: ws.cell(row=r, column=2).value for r in range(1, 12)}
    assert labels["Opening cash"] is not None
    assert abs(labels["Difference (must be 0)"]) < 0.01
    assert any(c.value == "GL closing cash" for row in ws.iter_rows() for c in row)


def test_forecast_and_audit_sheets_are_populated(workbook):
    forecast_values = [c.value for row in workbook["Forecast"].iter_rows() for c in row]
    assert "forecast" in forecast_values
    audit_values = [c.value for row in workbook["Audit findings"].iter_rows() for c in row]
    assert "Findings by rule" in audit_values


def test_export_writes_file_and_creates_folders(tmp_path, small_sample_dataset):
    out = export.export_workbook(small_sample_dataset, tmp_path / "nested" / "book.xlsx")
    assert out.exists()
    assert len(load_workbook(out).sheetnames) == 11


def test_forecast_unavailable_is_explained(small_sample_dataset):
    result = analyze(small_sample_dataset)
    broken = result.__class__(**{**result.__dict__, "forecast": None, "forecast_error": "too short"})
    wb = export.build_workbook(broken)
    values = [c.value for row in wb["Forecast"].iter_rows() for c in row]
    assert "too short" in values


def test_header_labels_keep_gl_upper_case():
    assert export._header_label("gl_closing_cash") == "GL closing cash"
    assert export._header_label("invoice_count") == "Invoice count"


def test_clean_converts_numpy_and_nan_values():
    assert export._clean(float("nan")) is None
    assert export._clean(pd.NaT) is None
    assert export._clean(pd.Timestamp("2025-01-02")).year == 2025
    assert export._clean(1.23456, decimals=2) == 1.23
    assert export._clean(__import__("numpy").int64(7)) == 7
    assert export._clean(__import__("numpy").bool_(True)) is True
    assert export._clean("text") == "text"
    assert math.isclose(export._clean(__import__("numpy").float64(2.5)), 2.5)


def test_write_table_handles_empty_frame_without_columns():
    ws = Workbook().active
    assert export._write_table(ws, 1, None, pd.DataFrame()) == 2
