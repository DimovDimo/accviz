"""Unit tests for accviz.ledger (natural signs, trial balance, balances as of a date)."""

from __future__ import annotations

import pandas as pd
import pytest

from accviz import ledger
from accviz.ledger import (
    balances_as_of,
    filter_dates,
    is_trial_balance_balanced,
    trial_balance,
    with_account_info,
)


def natural_of(df: pd.DataFrame, account: str) -> float:
    return float(df.loc[df["account_code"] == account, "natural_balance"].item())


def test_with_account_info_adds_signed_and_natural_amounts(tiny_dataset):
    df = with_account_info(tiny_dataset.journal, tiny_dataset.chart_of_accounts)
    # Debit to cash (asset): natural = +1000
    cash_in = df[(df.entry_id == "JE-1") & (df.account_code == "1000")].iloc[0]
    assert cash_in.amount == 1000 and cash_in.natural_amount == 1000
    # Credit to revenue: natural = +500 (revenue is credit-normal)
    revenue = df[(df.entry_id == "JE-2") & (df.account_code == "4000")].iloc[0]
    assert revenue.amount == -500 and revenue.natural_amount == 500
    # Credit to accumulated depreciation (contra asset): natural = -30
    accum = df[(df.entry_id == "JE-8") & (df.account_code == "1590")].iloc[0]
    assert accum.natural_amount == -30
    assert set(df["period"]) == {"2025-01", "2025-02"}


def test_trial_balance_contains_every_account(tiny_dataset):
    tb = trial_balance(tiny_dataset.journal, tiny_dataset.chart_of_accounts)
    assert len(tb) == len(tiny_dataset.chart_of_accounts)
    assert tb["account_code"].is_monotonic_increasing
    unused = tb[tb.account_code == "2000"].iloc[0]
    assert unused.debit == 0 and unused.credit == 0


def test_trial_balance_is_balanced_for_whole_period(tiny_dataset):
    tb = trial_balance(tiny_dataset.journal, tiny_dataset.chart_of_accounts)
    assert tb["debit"].sum() == pytest.approx(tb["credit"].sum())
    assert is_trial_balance_balanced(tb)


def test_trial_balance_natural_balances_match_hand_calculation(tiny_dataset):
    tb = trial_balance(tiny_dataset.journal, tiny_dataset.chart_of_accounts)
    assert natural_of(tb, "1000") == pytest.approx(1200)  # 1000 - 200 - 100 + 500
    assert natural_of(tb, "1100") == pytest.approx(300)  # 500 - 500 + 300
    assert natural_of(tb, "1590") == pytest.approx(-30)
    assert natural_of(tb, "4000") == pytest.approx(500)
    assert natural_of(tb, "4100") == pytest.approx(300)
    assert natural_of(tb, "2100") == pytest.approx(40)
    assert natural_of(tb, "5000") == pytest.approx(200)


def test_trial_balance_respects_date_range(tiny_dataset):
    jan = trial_balance(tiny_dataset.journal, tiny_dataset.chart_of_accounts, end="2025-01-31")
    assert natural_of(jan, "1000") == pytest.approx(700)  # January only
    assert natural_of(jan, "4100") == pytest.approx(0)  # February revenue excluded


def test_unbalanced_trial_balance_is_detected(tiny_dataset):
    tb = trial_balance(tiny_dataset.journal, tiny_dataset.chart_of_accounts)
    tb.loc[0, "debit"] += 5
    assert not is_trial_balance_balanced(tb)


def test_balances_as_of_excludes_later_postings(tiny_dataset):
    bal = balances_as_of(tiny_dataset.journal, tiny_dataset.chart_of_accounts, "2025-01-31")
    assert natural_of(bal, "1100") == pytest.approx(500)  # invoice INV-1 not yet paid
    assert natural_of(bal, "4100") == pytest.approx(0)
    assert list(bal.columns) == ["account_code", "account_name", "account_type", "subtype", "natural_balance"]


def test_filter_dates_is_inclusive_on_both_ends(tiny_dataset):
    journal = tiny_dataset.journal
    subset = filter_dates(journal, "2025-01-10", "2025-01-25")
    assert subset["date"].min() == pd.Timestamp("2025-01-10")
    assert subset["date"].max() == pd.Timestamp("2025-01-25")


def test_filter_dates_without_bounds_returns_everything(tiny_dataset):
    assert len(filter_dates(tiny_dataset.journal)) == len(tiny_dataset.journal)


def test_to_timestamp_handles_none():
    assert ledger.to_timestamp(None) is None
    assert ledger.to_timestamp("2025-03-01") == pd.Timestamp("2025-03-01")
