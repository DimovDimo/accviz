"""Unit tests for the data-quality rules in accviz.validation."""

from __future__ import annotations

import pandas as pd
import pytest

from accviz.loader import prepare_dataset
from accviz.validation import ValidationResult, validate_dataset, validate_required_columns
from tests.factories import tiny_raw


def run(raw):
    """Prepare a dataset and return the validation result (dataset may be None)."""
    _, result = prepare_dataset(raw)
    return result


def has(messages, fragment: str) -> bool:
    return any(fragment in m for m in messages)


def test_tiny_dataset_is_valid_without_errors():
    result = run(tiny_raw())
    assert result.ok
    assert result.errors == []


def test_missing_required_column_is_reported():
    raw = tiny_raw()
    raw["journal"] = raw["journal"].drop(columns=["debit"])
    result = validate_required_columns(raw)
    assert not result.ok
    assert has(result.errors, "journal_entries.csv: missing required column(s): debit")


def test_missing_required_column_prevents_normalisation():
    raw = tiny_raw()
    raw["invoices"] = raw["invoices"].drop(columns=["amount"])
    ds, result = prepare_dataset(raw)
    assert ds is None
    assert not result.ok


def test_missing_table_is_reported():
    raw = tiny_raw()
    del raw["budget"]
    result = validate_required_columns(raw)
    assert has(result.errors, "budget.csv: file is missing")


def test_missing_optional_column_is_a_warning_only():
    raw = tiny_raw()
    raw["journal"] = raw["journal"].drop(columns=["reference"])
    result = validate_required_columns(raw)
    assert result.ok
    assert has(result.warnings, "optional column 'reference'")


def test_unbalanced_entry_is_detected():
    raw = tiny_raw()
    raw["journal"].loc[1, "credit"] = "999"  # JE-1 now debits 1000 and credits 999
    result = run(raw)
    assert not result.ok
    assert has(result.errors, "unbalanced entr")
    assert has(result.errors, "JE-1")


def test_unknown_account_code_is_detected():
    raw = tiny_raw()
    raw["journal"].loc[0, "account_code"] = "9999"
    result = run(raw)
    assert has(result.errors, "not in chart of accounts: 9999")


def test_line_with_debit_and_credit_is_rejected():
    raw = tiny_raw()
    raw["journal"].loc[0, "credit"] = "5"
    result = run(raw)
    assert has(result.errors, "both debit and credit")


def test_line_with_neither_debit_nor_credit_is_rejected():
    raw = tiny_raw()
    raw["journal"].loc[0, "debit"] = "0"
    result = run(raw)
    assert has(result.errors, "neither debit nor credit")


def test_negative_amount_is_rejected():
    raw = tiny_raw()
    raw["journal"].loc[0, "debit"] = "-1000"
    result = run(raw)
    assert has(result.errors, "negative amounts")


def test_non_numeric_amount_is_rejected():
    raw = tiny_raw()
    raw["journal"].loc[0, "debit"] = "abc"
    result = run(raw)
    assert has(result.errors, "non-numeric")


def test_invalid_date_is_rejected():
    raw = tiny_raw()
    raw["journal"].loc[0, "date"] = "05/01/2025"
    result = run(raw)
    assert has(result.errors, "invalid date")


def test_empty_entry_id_is_rejected():
    raw = tiny_raw()
    raw["journal"].loc[0, "entry_id"] = ""
    result = run(raw)
    assert has(result.errors, "empty entry_id")


def test_duplicate_account_code_is_rejected():
    raw = tiny_raw()
    raw["coa"] = pd.concat([raw["coa"], raw["coa"].iloc[[0]]], ignore_index=True)
    result = run(raw)
    assert has(result.errors, "duplicate account code(s): 1000")


def test_invalid_account_type_is_rejected():
    raw = tiny_raw()
    raw["coa"].loc[0, "account_type"] = "Bogus"
    result = run(raw)
    assert has(result.errors, "invalid account_type")


def test_subtype_inconsistent_with_type_is_a_warning():
    raw = tiny_raw()
    raw["coa"].loc[0, "subtype"] = "Operating Revenue"  # Cash at Bank tagged as revenue
    result = run(raw)
    assert result.ok
    assert has(result.warnings, "not a standard subtype")


def test_empty_chart_of_accounts_is_rejected():
    raw = tiny_raw()
    raw["coa"] = raw["coa"].iloc[0:0]
    result = run(raw)
    assert has(result.errors, "no accounts defined")


def test_empty_journal_is_rejected():
    raw = tiny_raw()
    raw["journal"] = raw["journal"].iloc[0:0]
    result = run(raw)
    assert has(result.errors, "no journal lines")


def test_missing_department_is_a_warning():
    raw = tiny_raw()
    raw["journal"].loc[0, "department"] = ""
    result = run(raw)
    assert result.ok
    assert has(result.warnings, "without department")


def test_entry_with_lines_on_different_dates_is_a_warning():
    raw = tiny_raw()
    raw["journal"].loc[1, "date"] = "2025-01-06"
    result = run(raw)
    assert has(result.warnings, "different dates")


def test_paid_amount_above_invoice_amount_is_rejected():
    raw = tiny_raw()
    raw["invoices"].loc[0, "paid_amount"] = "9999"
    result = run(raw)
    assert has(result.errors, "paid_amount exceeds amount")


def test_due_date_before_issue_date_is_rejected():
    raw = tiny_raw()
    raw["invoices"].loc[1, "due_date"] = "2025-01-01"
    result = run(raw)
    assert has(result.errors, "due_date is before issue_date")


def test_duplicate_invoice_id_is_rejected():
    raw = tiny_raw()
    raw["invoices"].loc[1, "invoice_id"] = "INV-1"
    result = run(raw)
    assert has(result.errors, "duplicate invoice_id")


def test_non_positive_invoice_amount_is_rejected():
    raw = tiny_raw()
    raw["invoices"].loc[0, "amount"] = "0"
    result = run(raw)
    assert has(result.errors, "amount must be a positive number")


def test_paid_amount_without_paid_date_is_a_warning():
    raw = tiny_raw()
    raw["invoices"].loc[1, "paid_amount"] = "100"
    result = run(raw)
    assert result.ok
    assert has(result.warnings, "paid amount without paid_date")


def test_empty_invoices_is_a_warning():
    raw = tiny_raw()
    raw["invoices"] = raw["invoices"].iloc[0:0]
    result = run(raw)
    assert result.ok
    assert has(result.warnings, "no invoices")


def test_invalid_budget_period_is_rejected():
    raw = tiny_raw()
    raw["budget"].loc[0, "period"] = "2025-13"
    result = run(raw)
    assert has(result.errors, "period must be YYYY-MM")


def test_balance_sheet_account_cannot_be_budgeted():
    raw = tiny_raw()
    raw["budget"].loc[0, "account_code"] = "1000"
    result = run(raw)
    assert has(result.errors, "only Revenue and Expense accounts can be budgeted")


def test_negative_budget_is_rejected():
    raw = tiny_raw()
    raw["budget"].loc[0, "budget_amount"] = "-5"
    result = run(raw)
    assert has(result.errors, "budget_amount must be a non-negative number")


def test_duplicate_budget_row_is_rejected():
    raw = tiny_raw()
    raw["budget"] = pd.concat([raw["budget"], raw["budget"].iloc[[0]]], ignore_index=True)
    result = run(raw)
    assert has(result.errors, "duplicate budget rows")


def test_empty_budget_is_a_warning():
    raw = tiny_raw()
    raw["budget"] = raw["budget"].iloc[0:0]
    result = run(raw)
    assert result.ok
    assert has(result.warnings, "no budget rows")


def test_validate_dataset_collects_several_problems_at_once():
    raw = tiny_raw()
    raw["journal"].loc[1, "credit"] = "999"
    raw["invoices"].loc[0, "paid_amount"] = "9999"
    ds, _ = prepare_dataset(raw)
    result = validate_dataset(ds)
    assert len(result.errors) >= 2


def test_long_example_lists_are_truncated():
    raw = tiny_raw()
    extra = []
    for n in range(7):
        extra.append(("JE-9", "2025-03-01", f"77{n:02d}", "Bad", "1", "", "Sales", "X"))
        extra.append(("JE-9", "2025-03-01", "1000", "Bad", "", "1", "Sales", "X"))
    raw["journal"] = pd.concat([raw["journal"], pd.DataFrame(extra, columns=raw["journal"].columns)], ignore_index=True)
    result = run(raw)
    assert has(result.errors, "(+2 more)")


def test_summary_text_lists_errors_and_warnings():
    result = ValidationResult()
    assert result.summary().startswith("Validation passed")
    result.error("boom")
    result.warn("careful")
    text = result.summary()
    assert "ERROR   boom" in text
    assert "WARNING careful" in text
    assert not result.ok


@pytest.mark.parametrize("message_count", [0, 1])
def test_merge_combines_results(message_count):
    a = ValidationResult(errors=["e1"] * message_count)
    b = ValidationResult(warnings=["w1"])
    a.merge(b)
    assert a.warnings == ["w1"]
    assert len(a.errors) == message_count
