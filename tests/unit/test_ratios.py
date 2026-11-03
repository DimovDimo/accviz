"""Unit tests for ratios and KPIs."""

from __future__ import annotations

import dataclasses

import pytest

from accviz.analysis import analyze
from accviz.ratios import financial_ratios, kpi_summary, safe_div
from accviz.statements import balance_sheet, income_statement, income_totals


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [
        (10, 4, 2.5),
        (10, 0, None),
        (10, None, None),
        (10, float("nan"), None),
        (0, 5, 0.0),
    ],
)
def test_safe_div(numerator, denominator, expected):
    assert safe_div(numerator, denominator) == expected


def test_financial_ratios_match_hand_calculation(tiny_dataset):
    totals = income_totals(income_statement(tiny_dataset.journal, tiny_dataset.chart_of_accounts))
    bs = balance_sheet(tiny_dataset.journal, tiny_dataset.chart_of_accounts, "2025-02-28")
    ratios = financial_ratios(totals, bs)
    assert ratios["gross_margin"] == pytest.approx(600 / 800)
    assert ratios["operating_margin"] == pytest.approx(470 / 800)
    assert ratios["net_margin"] == pytest.approx(430 / 800)
    assert ratios["current_ratio"] == pytest.approx(1500 / 40)
    assert ratios["debt_to_equity"] == pytest.approx(40 / 1430)


def test_ratios_are_none_when_denominator_is_zero(tiny_dataset):
    totals = {"revenue": 0.0, "gross_profit": 0.0, "operating_profit": 0.0, "net_income": 0.0}
    bs = balance_sheet(tiny_dataset.journal, tiny_dataset.chart_of_accounts, "2025-02-28")
    bs = dataclasses.replace(bs, current_liabilities=0.0, share_capital=0.0, current_earnings=0.0)  # equity = 0
    ratios = financial_ratios(totals, bs)
    assert ratios["gross_margin"] is None
    assert ratios["current_ratio"] is None
    assert ratios["debt_to_equity"] is None


def test_kpi_summary_contains_headline_numbers(tiny_dataset):
    totals = income_totals(income_statement(tiny_dataset.journal, tiny_dataset.chart_of_accounts))
    bs = balance_sheet(tiny_dataset.journal, tiny_dataset.chart_of_accounts, "2025-02-28")
    kpis = kpi_summary(totals, bs, outstanding_receivables=300.0, revenue_budget_variance_pct=None)
    assert kpis["revenue"] == pytest.approx(800)
    assert kpis["net_income"] == pytest.approx(430)
    assert kpis["closing_cash"] == pytest.approx(1200)
    assert kpis["outstanding_receivables"] == 300
    assert kpis["revenue_vs_budget_pct"] is None


def test_analysis_revenue_vs_budget_uses_budgeted_accounts_only(tiny_dataset):
    result = analyze(tiny_dataset)
    # Budgeted revenue: 400 (product, Jan) + 250 (service, Feb) = 650; actual 500 + 300 = 800
    assert result.kpis["revenue_vs_budget_pct"] == pytest.approx(150 / 650)
