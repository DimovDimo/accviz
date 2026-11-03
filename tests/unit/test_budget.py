"""Unit tests for budget-versus-actual analysis."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from accviz.budget import VARIANCE_COLUMNS, budget_summary, budget_variance


@pytest.fixture
def variance(tiny_dataset) -> pd.DataFrame:
    return budget_variance(tiny_dataset.journal, tiny_dataset.chart_of_accounts, tiny_dataset.budget)


def cell(df: pd.DataFrame, period: str, account: str, column: str):
    return df.loc[(df["period"] == period) & (df["account_code"] == account), column].item()


def test_columns_are_stable(variance):
    assert list(variance.columns) == VARIANCE_COLUMNS


def test_revenue_over_budget_is_favourable(variance):
    assert cell(variance, "2025-01", "4000", "actual") == pytest.approx(500)
    assert cell(variance, "2025-01", "4000", "variance") == pytest.approx(100)
    assert cell(variance, "2025-01", "4000", "variance_pct") == pytest.approx(0.25)
    assert cell(variance, "2025-01", "4000", "favorable") in (True, 1)


def test_expense_under_budget_is_favourable(variance):
    assert cell(variance, "2025-01", "6000", "variance") == pytest.approx(-50)
    assert cell(variance, "2025-01", "6000", "favorable") in (True, 1)


def test_service_revenue_above_budget(variance):
    assert cell(variance, "2025-02", "4100", "variance") == pytest.approx(50)
    assert cell(variance, "2025-02", "4100", "favorable") in (True, 1)


def test_budget_without_actuals_is_kept(variance):
    rent = variance[(variance.period == "2025-02") & (variance.account_code == "6100")].iloc[0]
    assert rent.actual == 0
    assert rent.budget == 80
    assert rent.variance == -80


def test_actuals_without_budget_are_kept_and_unfavourable_when_expense(variance):
    depreciation = variance[(variance.period == "2025-02") & (variance.account_code == "6500")].iloc[0]
    assert depreciation.budget == 0
    assert depreciation.actual == 30
    assert math.isnan(depreciation.variance_pct)
    assert depreciation.favorable in (False, 0)


def test_period_bounds_restrict_rows(tiny_dataset):
    feb = budget_variance(
        tiny_dataset.journal,
        tiny_dataset.chart_of_accounts,
        tiny_dataset.budget,
        start="2025-02-01",
        end="2025-02-28",
    )
    assert set(feb["period"]) == {"2025-02"}


def test_empty_budget_still_shows_actuals(tiny_dataset):
    empty = tiny_dataset.budget.iloc[0:0]
    result = budget_variance(tiny_dataset.journal, tiny_dataset.chart_of_accounts, empty)
    assert not result.empty
    assert (result["budget"] == 0).all()


def test_summary_aggregates_over_periods(variance):
    summary = budget_summary(variance).set_index("account_code")
    assert summary.loc["4000", "budget"] == pytest.approx(400)
    assert summary.loc["4000", "actual"] == pytest.approx(500)
    assert summary.loc["4000", "variance"] == pytest.approx(100)
    assert summary.loc["4100", "favorable"] in (True, 1)


def test_summary_of_empty_variance_is_empty():
    assert budget_summary(pd.DataFrame(columns=VARIANCE_COLUMNS)).empty
