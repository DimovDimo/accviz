"""Unit tests for reading and normalising input files."""

from __future__ import annotations

import pandas as pd
import pytest

from accviz import config
from accviz.loader import (
    DataValidationError,
    build_dataset,
    load_raw_directory,
    normalize_budget,
    normalize_coa,
    normalize_invoices,
    normalize_journal,
    prepare_dataset,
    read_dataset,
)
from accviz.synthetic import write_dataset
from tests.factories import tiny_raw


def test_load_raw_directory_returns_all_tables_as_text(tmp_path, small_sample_raw):
    write_dataset(small_sample_raw, tmp_path)
    raw = load_raw_directory(tmp_path)
    assert set(raw) == {"coa", "journal", "invoices", "budget"}
    assert all(df.dtypes.eq(object).all() for df in raw.values())
    assert len(raw["journal"]) == len(small_sample_raw["journal"])


def test_load_raw_directory_reports_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="Required file not found"):
        load_raw_directory(tmp_path)


def test_read_dataset_round_trip_preserves_values(tmp_path, small_sample_raw):
    write_dataset(small_sample_raw, tmp_path)
    ds = read_dataset(tmp_path)
    assert len(ds.journal) == len(small_sample_raw["journal"])
    assert pd.api.types.is_datetime64_any_dtype(ds.journal["date"])
    assert pd.api.types.is_float_dtype(ds.journal["debit"])
    assert ds.journal["debit"].sum() == pytest.approx(
        pd.to_numeric(small_sample_raw["journal"]["debit"]).sum()
    )


def test_build_dataset_raises_with_result_on_errors():
    raw = tiny_raw()
    raw["journal"].loc[1, "credit"] = "999"
    with pytest.raises(DataValidationError) as excinfo:
        build_dataset(raw)
    assert not excinfo.value.result.ok
    assert "unbalanced" in str(excinfo.value)


def test_read_dataset_raises_for_unbalanced_csv(tmp_path, small_sample_raw):
    write_dataset(small_sample_raw, tmp_path)
    journal_path = tmp_path / config.JOURNAL_FILE
    df = pd.read_csv(journal_path, dtype=str, keep_default_na=False)
    df.loc[0, "credit"] = "12345.67"  # first line of the opening entry no longer balances
    df.to_csv(journal_path, index=False)
    with pytest.raises(DataValidationError, match="unbalanced"):
        read_dataset(tmp_path)


def test_empty_amount_cells_are_treated_as_zero():
    ds, result = prepare_dataset(tiny_raw())
    assert result.ok
    line = ds.journal[(ds.journal["entry_id"] == "JE-1") & (ds.journal["account_code"] == "1000")]
    assert line["credit"].item() == 0.0
    assert line["debit"].item() == 1000.0


def test_optional_journal_columns_get_defaults():
    raw = tiny_raw()
    raw["journal"] = raw["journal"].drop(columns=["description", "department", "reference"])
    ds, result = prepare_dataset(raw)
    assert result.ok
    assert (ds.journal["department"] == "").all()
    assert (ds.journal["reference"] == "").all()
    assert (ds.journal["description"] == "").all()


def test_missing_payment_columns_default_to_unpaid():
    raw = tiny_raw()
    raw["invoices"] = raw["invoices"].drop(columns=["paid_date", "paid_amount"])
    ds, result = prepare_dataset(raw)
    assert result.ok
    assert (ds.invoices["paid_amount"] == 0.0).all()
    assert ds.invoices["paid_date"].isna().all()


def test_codes_and_text_are_stripped_of_whitespace():
    raw = tiny_raw()
    raw["coa"].loc[0, "account_code"] = "  1000 "
    raw["coa"].loc[0, "account_name"] = " Cash at Bank  "
    ds, _ = prepare_dataset(raw)
    assert ds.chart_of_accounts.loc[0, "account_code"] == "1000"
    assert ds.chart_of_accounts.loc[0, "account_name"] == "Cash at Bank"


def test_invalid_dates_become_missing_values():
    raw = tiny_raw()
    raw["invoices"].loc[0, "issue_date"] = "not a date"
    ds, result = prepare_dataset(raw)
    assert pd.isna(ds.invoices.loc[0, "issue_date"])
    assert not result.ok


def test_start_and_end_dates_of_dataset(tiny_dataset):
    assert tiny_dataset.start_date == pd.Timestamp("2025-01-05")
    assert tiny_dataset.end_date == pd.Timestamp("2025-02-20")


def test_normalizers_keep_row_counts(small_sample_raw):
    raw = small_sample_raw
    assert len(normalize_coa(raw["coa"])) == len(raw["coa"])
    assert len(normalize_journal(raw["journal"])) == len(raw["journal"])
    assert len(normalize_invoices(raw["invoices"])) == len(raw["invoices"])
    assert len(normalize_budget(raw["budget"])) == len(raw["budget"])
