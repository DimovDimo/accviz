"""Unit tests for the analysis orchestrator."""

from __future__ import annotations

import pandas as pd
import pytest

from accviz.analysis import analyze


def test_defaults_cover_the_whole_dataset(tiny_dataset):
    result = analyze(tiny_dataset)
    assert result.start == pd.Timestamp("2025-01-05")
    assert result.end == pd.Timestamp("2025-02-20")
    assert result.period_label == "2025-01-05 to 2025-02-20"


def test_kpis_match_hand_calculation(tiny_dataset):
    kpis = analyze(tiny_dataset).kpis
    assert kpis["revenue"] == pytest.approx(800)
    assert kpis["net_income"] == pytest.approx(430)
    assert kpis["closing_cash"] == pytest.approx(1200)
    assert kpis["outstanding_receivables"] == pytest.approx(300)
    assert kpis["total_assets"] == pytest.approx(1470)


def test_sub_period_restricts_income_but_not_balance_sheet(tiny_dataset):
    result = analyze(tiny_dataset, start="2025-02-01", end="2025-02-28")
    assert result.income_monthly["period"].tolist() == ["2025-02"]
    assert result.income_totals["revenue"] == pytest.approx(300)
    # Balance sheet is cumulative since inception.
    assert result.balance_sheet.total_assets == pytest.approx(1470)


def test_start_after_end_is_rejected(tiny_dataset):
    with pytest.raises(ValueError, match="after end date"):
        analyze(tiny_dataset, start="2025-03-01", end="2025-01-01")


def test_ratios_are_present(tiny_dataset):
    ratios = analyze(tiny_dataset).ratios
    assert set(ratios) == {"gross_margin", "operating_margin", "net_margin", "current_ratio", "debt_to_equity"}


def test_result_contains_all_sections(tiny_dataset):
    result = analyze(tiny_dataset)
    assert not result.trial_balance.empty
    assert not result.aging.empty
    assert not result.budget_summary.empty
    assert not result.top_customers.empty
