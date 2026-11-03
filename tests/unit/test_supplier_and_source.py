"""Unit tests for the optional v1.1 inputs: supplier_invoices.csv and the journal source column."""

from __future__ import annotations

import pandas as pd
import pytest

from accviz.loader import (
    DataValidationError,
    build_dataset,
    empty_supplier_invoices,
    load_raw_directory,
    normalize_journal,
    prepare_dataset,
    read_dataset,
)
from accviz.synthetic import write_dataset
from accviz.validation import validate_required_columns
from tests.factories import tiny_raw

pytestmark = pytest.mark.unit

SUPPLIER_COLUMNS = ["invoice_id", "supplier", "issue_date", "due_date", "amount", "paid_date", "paid_amount"]


def _suppliers(rows):
    return pd.DataFrame(rows, columns=SUPPLIER_COLUMNS).astype(str)


GOOD_ROWS = [("SUP-1", "Alpha", "2025-01-10", "2025-02-09", "400", "", "0")]


def test_missing_supplier_file_is_only_a_warning():
    raw = tiny_raw()
    ds, result = prepare_dataset(raw)
    assert result.ok
    assert any("supplier_invoices.csv: file not found" in w for w in result.warnings)
    assert ds.supplier_invoices.empty
    assert list(ds.supplier_invoices.columns) == list(empty_supplier_invoices().columns)


def test_supplier_file_is_normalised_when_present():
    raw = tiny_raw()
    raw["supplier_invoices"] = _suppliers(GOOD_ROWS)
    ds = build_dataset(raw)
    assert ds.supplier_invoices.iloc[0]["amount"] == 400
    assert ds.supplier_invoices.iloc[0]["issue_date"] == pd.Timestamp("2025-01-10")
    assert pd.isna(ds.supplier_invoices.iloc[0]["paid_date"])


def test_supplier_file_missing_required_column_is_an_error():
    raw = tiny_raw()
    raw["supplier_invoices"] = _suppliers(GOOD_ROWS).drop(columns=["supplier"])
    ds, result = prepare_dataset(raw)
    assert ds is None
    assert any("missing required column(s): supplier" in e for e in result.errors)


@pytest.mark.parametrize(
    "rows, message",
    [
        ([("SUP-1", "A", "2025-01-10", "2025-02-09", "100", "", "0"), ("SUP-1", "B", "2025-01-11", "2025-02-10", "100", "", "0")], "duplicate invoice_id"),
        ([("SUP-1", "A", "2025-02-10", "2025-01-09", "100", "", "0")], "due_date is before issue_date"),
        ([("SUP-1", "A", "2025-01-10", "2025-02-09", "0", "", "0")], "amount must be a positive number"),
        ([("SUP-1", "A", "2025-01-10", "2025-02-09", "100", "2025-02-01", "150")], "paid_amount exceeds amount"),
        ([("SUP-1", "A", "not-a-date", "2025-02-09", "100", "", "0")], "invalid or missing issue_date"),
    ],
)
def test_supplier_invoice_rules(rows, message):
    raw = tiny_raw()
    raw["supplier_invoices"] = _suppliers(rows)
    ds, result = prepare_dataset(raw)
    assert not result.ok
    assert any(message in e for e in result.errors), result.errors


def test_empty_supplier_file_only_warns():
    raw = tiny_raw()
    raw["supplier_invoices"] = _suppliers([])
    ds, result = prepare_dataset(raw)
    assert result.ok
    assert any("file has no rows" in w for w in result.warnings)
    assert ds.supplier_invoices.empty


def test_journal_without_source_column_defaults_to_system():
    raw = tiny_raw()
    journal = normalize_journal(raw["journal"])
    assert set(journal["source"]) == {"system"}


def test_source_values_are_case_insensitive_and_blank_means_system():
    raw = tiny_raw()
    raw["journal"]["source"] = ["Manual" if i == 0 else "" for i in range(len(raw["journal"]))]
    journal = normalize_journal(raw["journal"])
    assert journal["source"].iloc[0] == "manual"
    assert journal["source"].iloc[1] == "system"


def test_invalid_source_value_is_an_error():
    raw = tiny_raw()
    raw["journal"]["source"] = "system"
    raw["journal"].loc[0, "source"] = "robot"
    with pytest.raises(DataValidationError) as exc:
        build_dataset(raw)
    assert any("source must be 'system' or 'manual'" in e for e in exc.value.result.errors)


def test_v10_layout_loads_without_optional_inputs(tmp_path):
    raw = tiny_raw()
    for key in ("coa", "journal", "invoices", "budget"):
        raw[key].to_csv(tmp_path / {"coa": "chart_of_accounts.csv", "journal": "journal_entries.csv",
                                    "invoices": "invoices.csv", "budget": "budget.csv"}[key], index=False)  # fmt: skip
    ds = read_dataset(tmp_path)
    assert ds.supplier_invoices.empty
    assert set(ds.journal["source"]) == {"system"}


def test_load_raw_directory_reads_optional_files_only_when_present(tmp_path):
    write_dataset({**tiny_raw(), "supplier_invoices": _suppliers(GOOD_ROWS)}, tmp_path)
    assert "supplier_invoices" in load_raw_directory(tmp_path)


def test_required_columns_check_reports_optional_absence_as_warning():
    raw = tiny_raw()
    result = validate_required_columns(raw)
    assert result.ok
    assert any("supplier_invoices.csv" in w for w in result.warnings)
