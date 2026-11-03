"""Unit tests for accviz.statements, using the hand-computed tiny company."""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from accviz.statements import (
    INCOME_COLUMNS,
    balance_sheet,
    cash_trend,
    expense_breakdown,
    income_statement,
    income_totals,
    revenue_breakdown,
)


@pytest.fixture
def income(tiny_dataset):
    return income_statement(tiny_dataset.journal, tiny_dataset.chart_of_accounts)


def row(df: pd.DataFrame, period: str) -> pd.Series:
    return df.loc[df["period"] == period].iloc[0]


def test_income_statement_january_matches_hand_calculation(income):
    jan = row(income, "2025-01")
    assert jan.revenue == pytest.approx(500)
    assert jan.cost_of_sales == pytest.approx(200)
    assert jan.gross_profit == pytest.approx(300)
    assert jan.operating_expenses == pytest.approx(100)
    assert jan.operating_profit == pytest.approx(200)
    assert jan.tax_expense == pytest.approx(0)
    assert jan.net_income == pytest.approx(200)


def test_income_statement_february_matches_hand_calculation(income):
    feb = row(income, "2025-02")
    assert feb.revenue == pytest.approx(300)
    assert feb.operating_expenses == pytest.approx(30)  # depreciation
    assert feb.tax_expense == pytest.approx(40)
    assert feb.net_income == pytest.approx(230)


def test_income_statement_has_expected_columns_and_order(income):
    assert list(income.columns) == INCOME_COLUMNS


def test_income_statement_respects_period_bounds(tiny_dataset):
    feb_only = income_statement(tiny_dataset.journal, tiny_dataset.chart_of_accounts, "2025-02-01", "2025-02-28")
    assert feb_only["period"].tolist() == ["2025-02"]


def test_income_statement_for_empty_range_is_empty(tiny_dataset):
    empty = income_statement(tiny_dataset.journal, tiny_dataset.chart_of_accounts, "2030-01-01", "2030-12-31")
    assert empty.empty
    assert list(empty.columns) == INCOME_COLUMNS


def test_income_totals_sum_every_month(income):
    totals = income_totals(income)
    assert totals["revenue"] == pytest.approx(800)
    assert totals["net_income"] == pytest.approx(430)
    assert totals["gross_profit"] == pytest.approx(600)


def test_income_totals_of_empty_statement_are_zero():
    totals = income_totals(pd.DataFrame(columns=INCOME_COLUMNS))
    assert all(value == 0 for value in totals.values())


def test_expense_breakdown_is_sorted_largest_first(tiny_dataset):
    exp = expense_breakdown(tiny_dataset.journal, tiny_dataset.chart_of_accounts)
    assert exp["account_name"].tolist() == [
        "Cost of Goods Sold",
        "Salaries and Wages",
        "Income Tax Expense",
        "Depreciation",
    ]
    assert exp["amount"].tolist() == pytest.approx([200, 100, 40, 30])


def test_revenue_breakdown_by_account(tiny_dataset):
    rev = revenue_breakdown(tiny_dataset.journal, tiny_dataset.chart_of_accounts)
    assert dict(zip(rev["account_name"], rev["amount"])) == pytest.approx(
        {"Product Sales": 500, "Service Revenue": 300}
    )


def test_cash_trend_monthly_values(tiny_dataset):
    cash = cash_trend(tiny_dataset.journal, tiny_dataset.chart_of_accounts)
    assert cash["period"].tolist() == ["2025-01", "2025-02"]
    assert cash["net_change"].tolist() == pytest.approx([700, 500])
    assert cash["closing_balance"].tolist() == pytest.approx([700, 1200])


def test_cash_trend_closing_balance_is_cumulative_even_in_sub_period(tiny_dataset):
    cash = cash_trend(tiny_dataset.journal, tiny_dataset.chart_of_accounts, start="2025-02-01")
    assert cash["period"].tolist() == ["2025-02"]
    assert cash["closing_balance"].iloc[0] == pytest.approx(1200)


def test_cash_trend_is_empty_without_cash_postings(tiny_dataset):
    journal = tiny_dataset.journal[tiny_dataset.journal["account_code"] != "1000"]
    journal = journal[~journal["entry_id"].isin(["JE-1", "JE-3", "JE-4", "JE-5"])]
    cash = cash_trend(journal, tiny_dataset.chart_of_accounts)
    assert cash.empty


def test_balance_sheet_at_end_of_february(tiny_dataset):
    bs = balance_sheet(tiny_dataset.journal, tiny_dataset.chart_of_accounts, "2025-02-28")
    assert bs.total_assets == pytest.approx(1470)
    assert bs.total_liabilities == pytest.approx(40)
    assert bs.share_capital == pytest.approx(1000)
    assert bs.current_earnings == pytest.approx(430)
    assert bs.total_equity == pytest.approx(1430)
    assert bs.cash == pytest.approx(1200)
    assert bs.receivables == pytest.approx(300)
    assert bs.current_assets == pytest.approx(1500)
    assert bs.current_liabilities == pytest.approx(40)
    assert bs.is_balanced()
    assert bs.difference == pytest.approx(0)


def test_balance_sheet_at_end_of_january_balances(tiny_dataset):
    bs = balance_sheet(tiny_dataset.journal, tiny_dataset.chart_of_accounts, "2025-01-31")
    assert bs.total_assets == pytest.approx(1200)  # cash 700 + receivables 500
    assert bs.total_liabilities == pytest.approx(0)
    assert bs.total_equity == pytest.approx(1200)  # capital 1000 + January profit 200
    assert bs.is_balanced()


def test_balance_sheet_detects_inconsistency(tiny_dataset):
    bs = balance_sheet(tiny_dataset.journal, tiny_dataset.chart_of_accounts, "2025-02-28")
    broken = dataclasses.replace(bs, total_assets=bs.total_assets + 1)
    assert not broken.is_balanced()
    assert broken.difference == pytest.approx(1)
