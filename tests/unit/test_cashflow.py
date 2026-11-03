"""Unit tests for the direct-method cash flow statement (I-1)."""

from __future__ import annotations

import pandas as pd
import pytest

from accviz import cashflow
from accviz.cashflow import cash_flow_statement, monthly_cash_flow

pytestmark = pytest.mark.unit


def _journal(rows):
    """Build a minimal journal: rows of (entry_id, date, account, description, debit, credit)."""
    df = pd.DataFrame(rows, columns=["entry_id", "date", "account_code", "description", "debit", "credit"])
    df["date"] = pd.to_datetime(df["date"])
    df["department"] = ""
    df["reference"] = ""
    df["source"] = "system"
    return df


@pytest.fixture
def coa(tiny_dataset):
    return tiny_dataset.chart_of_accounts


def test_tiny_company_january_and_february_match_hand_calculation(tiny_dataset):
    m = monthly_cash_flow(tiny_dataset.journal, tiny_dataset.chart_of_accounts)
    jan = m[m["period"] == "2025-01"].iloc[0]
    feb = m[m["period"] == "2025-02"].iloc[0]
    assert (jan["operating"], jan["investing"], jan["financing"]) == (-300, 0, 1000)
    assert jan["net_change"] == 700
    assert (feb["operating"], feb["financing"], feb["net_change"]) == (500, 0, 500)
    assert feb["closing_cash"] == 1200 == feb["gl_closing_cash"]


def test_tiny_company_period_totals(tiny_dataset):
    stmt = cash_flow_statement(tiny_dataset.journal, tiny_dataset.chart_of_accounts, "2025-01-01", "2025-02-28")
    assert stmt.operating == 200
    assert stmt.financing == 1000
    assert stmt.investing == 0
    assert stmt.net_change == 1200
    assert stmt.closing_cash == pytest.approx(stmt.gl_closing_cash) == 1200
    assert stmt.is_reconciled()


def test_sub_period_uses_opening_cash_from_earlier_flows(tiny_dataset):
    stmt = cash_flow_statement(tiny_dataset.journal, tiny_dataset.chart_of_accounts, "2025-02-01", "2025-02-28")
    assert stmt.opening_cash == 700
    assert stmt.operating == 500
    assert stmt.net_change == 500
    assert stmt.closing_cash == 1200
    assert stmt.difference == pytest.approx(0)


def test_classification_by_counterpart_account(coa):
    journal = _journal(
        [
            ("E1", "2025-03-01", "1000", "Opening balances", 500, 0),
            ("E1", "2025-03-01", "3000", "Opening balances", 0, 500),
            ("E2", "2025-03-02", "1500", "Equipment purchase", 200, 0),
            ("E2", "2025-03-02", "1000", "Equipment purchase", 0, 200),
            ("E3", "2025-03-03", "2500", "Loan repayment", 100, 0),
            ("E3", "2025-03-03", "1000", "Loan repayment", 0, 100),
            ("E4", "2025-03-04", "1000", "Customer receipt", 300, 0),
            ("E4", "2025-03-04", "4000", "Customer receipt", 0, 300),
            ("E5", "2025-03-05", "2000", "Supplier payment", 50, 0),
            ("E5", "2025-03-05", "1000", "Supplier payment", 0, 50),
        ]
    )
    stmt = cash_flow_statement(journal, coa)
    assert stmt.investing == -200
    assert stmt.financing == -100
    assert stmt.operating == 250  # +300 receipt - 50 supplier payment
    assert stmt.opening_cash == 500  # the opening-balance entry is opening cash, not a flow
    assert stmt.net_change == -50  # -200 investing, -100 financing, +250 operating
    assert stmt.closing_cash == 450
    assert stmt.is_reconciled()


def test_opening_balance_is_excluded_from_flows_even_inside_the_period(coa):
    journal = _journal(
        [
            ("E1", "2024-10-31", "1000", "Opening balances", 1000, 0),
            ("E1", "2024-10-31", "3000", "Opening balances", 0, 1000),
            ("E2", "2024-11-05", "1000", "Sales", 40, 0),
            ("E2", "2024-11-05", "4000", "Sales", 0, 40),
        ]
    )
    stmt = cash_flow_statement(journal, coa, "2024-10-31", "2024-11-30")
    assert stmt.opening_cash == 1000
    assert stmt.operating == 40
    assert stmt.closing_cash == 1040 == stmt.gl_closing_cash


def test_opening_balance_marker_is_case_insensitive(coa):
    journal = _journal(
        [
            ("E1", "2024-10-31", "1000", "OPENING BALANCE cash", 700, 0),
            ("E1", "2024-10-31", "3000", "OPENING BALANCE cash", 0, 700),
        ]
    )
    stmt = cash_flow_statement(journal, coa)
    assert stmt.opening_cash == 700
    assert stmt.net_change == 0


def test_period_without_cash_activity_is_zero(tiny_dataset):
    stmt = cash_flow_statement(tiny_dataset.journal, tiny_dataset.chart_of_accounts, "2026-06-01", "2026-06-30")
    assert stmt.net_change == 0
    assert stmt.lines.empty
    assert stmt.is_reconciled()


def test_entries_without_cash_do_not_contribute(coa):
    journal = _journal(
        [
            ("E1", "2025-01-10", "6500", "Depreciation", 30, 0),
            ("E1", "2025-01-10", "1590", "Depreciation", 0, 30),
        ]
    )
    stmt = cash_flow_statement(journal, coa)
    assert stmt.net_change == 0
    assert stmt.lines.empty


def test_monthly_table_has_one_row_per_month_and_zero_difference(tiny_dataset):
    m = monthly_cash_flow(tiny_dataset.journal, tiny_dataset.chart_of_accounts)
    assert list(m.columns) == cashflow.MONTHLY_COLUMNS
    assert m["period"].tolist() == ["2025-01", "2025-02"]
    assert m["difference"].abs().max() < 0.01


def test_monthly_table_fills_months_without_activity(coa):
    journal = _journal(
        [
            ("E1", "2025-01-10", "1000", "Sales", 100, 0),
            ("E1", "2025-01-10", "4000", "Sales", 0, 100),
            ("E2", "2025-03-10", "1000", "Sales", 50, 0),
            ("E2", "2025-03-10", "4000", "Sales", 0, 50),
        ]
    )
    m = monthly_cash_flow(journal, coa)
    assert m["period"].tolist() == ["2025-01", "2025-02", "2025-03"]
    feb = m[m["period"] == "2025-02"].iloc[0]
    assert feb["net_change"] == 0
    assert feb["closing_cash"] == 100
    assert m["difference"].abs().max() < 0.01


def test_monthly_empty_when_no_cash_entries(coa):
    journal = _journal([("E1", "2025-01-10", "4000", "Sales", 0, 100), ("E1", "2025-01-10", "1100", "Sales", 100, 0)])
    assert monthly_cash_flow(journal, coa).empty


def test_statement_defaults_to_whole_journal(tiny_dataset):
    stmt = cash_flow_statement(tiny_dataset.journal, tiny_dataset.chart_of_accounts)
    assert stmt.start == tiny_dataset.start_date
    assert stmt.end == tiny_dataset.end_date
    assert stmt.closing_cash == 1200
