"""Integration tests: generator -> CSV -> loader -> analytics -> report."""

from __future__ import annotations

import pandas as pd
import pytest

from accviz import config
from accviz.analysis import analyze
from accviz.ledger import balances_as_of, is_trial_balance_balanced, trial_balance
from accviz.loader import read_dataset
from accviz.receivables import aging_schedule
from accviz.report import render_report, write_report
from accviz.statements import balance_sheet, cash_trend
from accviz.synthetic import write_dataset


@pytest.fixture(scope="module")
def pipeline_dataset(tmp_path_factory, small_sample_raw):
    folder = tmp_path_factory.mktemp("pipeline") / "data"
    write_dataset(small_sample_raw, folder)
    return read_dataset(folder)


def test_csv_round_trip_keeps_every_journal_line(pipeline_dataset, small_sample_raw):
    assert len(pipeline_dataset.journal) == len(small_sample_raw["journal"])
    assert len(pipeline_dataset.invoices) == len(small_sample_raw["invoices"])


def test_trial_balance_balances_for_the_full_period(pipeline_dataset):
    tb = trial_balance(pipeline_dataset.journal, pipeline_dataset.chart_of_accounts)
    assert is_trial_balance_balanced(tb)


def test_balance_sheet_balances_at_every_month_end(pipeline_dataset):
    month_ends = pd.date_range(pipeline_dataset.start_date, pipeline_dataset.end_date, freq="ME")
    assert len(month_ends) >= 6
    for day in month_ends:
        bs = balance_sheet(pipeline_dataset.journal, pipeline_dataset.chart_of_accounts, day)
        assert bs.is_balanced(), f"not balanced at {day:%Y-%m-%d}: {bs.difference}"


def test_receivables_subledger_reconciles_to_gl_control_account(pipeline_dataset):
    """The AR control account must equal the sum of open invoices at every month end."""
    coa, journal = pipeline_dataset.chart_of_accounts, pipeline_dataset.journal
    for day in pd.date_range(pipeline_dataset.start_date, pipeline_dataset.end_date, freq="ME"):
        gl = balances_as_of(journal, coa, day)
        gl_ar = float(gl.loc[gl.account_code == "1100", "natural_balance"].item())
        subledger = aging_schedule(pipeline_dataset.invoices, day)["outstanding"].sum()
        assert gl_ar == pytest.approx(subledger, abs=0.01), day


def test_cash_trend_closing_matches_balance_sheet_cash(pipeline_dataset):
    coa, journal = pipeline_dataset.chart_of_accounts, pipeline_dataset.journal
    cash = cash_trend(journal, coa)
    bs = balance_sheet(journal, coa, pipeline_dataset.end_date)
    assert cash["closing_balance"].iloc[-1] == pytest.approx(bs.cash)


def test_income_totals_equal_sum_of_monthly_rows(pipeline_dataset):
    result = analyze(pipeline_dataset)
    monthly = result.income_monthly
    assert result.income_totals["net_income"] == pytest.approx(monthly["net_income"].sum())
    assert result.income_totals["revenue"] == pytest.approx(monthly["revenue"].sum())


def test_sub_period_totals_are_a_subset_of_full_period(pipeline_dataset):
    ds = pipeline_dataset
    full = analyze(ds).income_totals["revenue"]
    midpoint = ds.start_date + (ds.end_date - ds.start_date) / 2
    first_half = analyze(ds, end=midpoint).income_totals["revenue"]
    assert 0 < first_half < full


def test_report_is_self_contained_html(tmp_path, pipeline_dataset):
    out = write_report(pipeline_dataset, tmp_path / "report.html")
    html = out.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert "Key figures" in html and "Receivables aging" in html and "Balance sheet" in html
    assert html.count('class="plotly-graph-div"') == 13  # one per chart section
    assert "Balanced" in html
    assert '<script src="https://cdn.plot.ly' not in html  # Plotly JS is embedded, no network needed


def test_report_for_custom_period_mentions_period(pipeline_dataset):
    html = render_report(pipeline_dataset, "2025-01-01", "2025-03-31")
    assert "2025-01-01 to 2025-03-31" in html


def test_currency_is_shown_in_report(pipeline_dataset):
    html = render_report(pipeline_dataset)
    assert config.CURRENCY in html
