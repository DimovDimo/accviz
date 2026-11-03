"""Unit tests for expenses by cost centre (I-6)."""

from __future__ import annotations

import pytest

from accviz.departments import UNASSIGNED, department_pivot, department_summary, expenses_by_department

pytestmark = pytest.mark.unit


def test_expenses_by_department_and_month_for_tiny_company(tiny_dataset):
    # Tiny company expenses: Jan salaries 100 (Administration) and COGS 200 (Operations);
    # Feb tax 40 (Finance) and depreciation 30 (Operations).
    out = expenses_by_department(tiny_dataset.journal, tiny_dataset.chart_of_accounts)
    got = {(r.period, r.department): r.amount for r in out.itertuples()}
    assert got == {
        ("2025-01", "Administration"): 100,
        ("2025-01", "Operations"): 200,
        ("2025-02", "Finance"): 40,
        ("2025-02", "Operations"): 30,
    }


def test_summary_shares_sum_to_one(tiny_dataset):
    out = expenses_by_department(tiny_dataset.journal, tiny_dataset.chart_of_accounts)
    summary = department_summary(out)
    assert summary["share"].sum() == pytest.approx(1.0)
    assert summary.iloc[0]["department"] == "Operations"  # 230 is the largest total
    assert summary.iloc[0]["amount"] == 230


def test_pivot_has_months_as_rows_and_zero_fill(tiny_dataset):
    pivot = department_pivot(expenses_by_department(tiny_dataset.journal, tiny_dataset.chart_of_accounts))
    assert list(pivot.index) == ["2025-01", "2025-02"]
    assert pivot.loc["2025-01", "Finance"] == 0
    assert pivot.loc["2025-02", "Administration"] == 0


def test_blank_department_is_unassigned(tiny_dataset):
    journal = tiny_dataset.journal.copy()
    journal.loc[journal["account_code"] == "6000", "department"] = ""
    out = expenses_by_department(journal, tiny_dataset.chart_of_accounts)
    assert UNASSIGNED in set(out["department"])


def test_period_bounds_and_empty_results(tiny_dataset):
    out = expenses_by_department(tiny_dataset.journal, tiny_dataset.chart_of_accounts, "2025-02-01", "2025-02-28")
    assert set(out["period"]) == {"2025-02"}
    none = expenses_by_department(tiny_dataset.journal, tiny_dataset.chart_of_accounts, "2030-01-01", "2030-12-31")
    assert none.empty
    assert department_summary(none).empty
    assert department_pivot(none).empty
