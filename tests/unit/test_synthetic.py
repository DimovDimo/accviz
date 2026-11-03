"""Unit tests for the synthetic data generator."""

from __future__ import annotations

import pandas as pd
import pytest

from accviz import config
from accviz.loader import prepare_dataset
from accviz.synthetic import CSV_COLUMNS, DEFAULT_CHART_OF_ACCOUNTS, GeneratorConfig, generate_dataset, write_dataset


@pytest.fixture(scope="module")
def raw():
    return generate_dataset(GeneratorConfig(seed=11, months=3))


def test_generates_all_tables_with_expected_columns(raw):
    assert set(raw) == {"coa", "journal", "invoices", "budget", "supplier_invoices"}
    for key in raw:
        assert list(raw[key].columns) == CSV_COLUMNS[key], key
    assert "source" in raw["journal"].columns


def test_chart_of_accounts_is_complete_and_unique(raw):
    coa = raw["coa"]
    assert len(coa) == len(DEFAULT_CHART_OF_ACCOUNTS)
    assert coa["account_code"].is_unique
    assert set(coa["account_type"]) == set(config.ACCOUNT_TYPES)


def test_every_journal_code_exists_in_chart_of_accounts(raw):
    assert set(raw["journal"]["account_code"]) <= set(raw["coa"]["account_code"])


def test_same_seed_gives_identical_data():
    a = generate_dataset(GeneratorConfig(seed=5, months=2))
    b = generate_dataset(GeneratorConfig(seed=5, months=2))
    for key in a:
        pd.testing.assert_frame_equal(a[key], b[key])


def test_different_seed_gives_different_data():
    a = generate_dataset(GeneratorConfig(seed=5, months=2))
    b = generate_dataset(GeneratorConfig(seed=6, months=2))
    assert not a["journal"].equals(b["journal"])


def test_opening_balances_are_posted_before_first_month(raw):
    opening = raw["journal"][raw["journal"]["reference"] == "OPENING"]
    assert set(opening["date"]) == {"2024-10-31"}
    assert opening["debit"].sum() == pytest.approx(opening["credit"].sum())


def test_invoices_per_month_are_within_configured_range(raw):
    counts = raw["invoices"]["issue_date"].str[:7].value_counts()
    assert len(counts) == 3
    assert counts.between(40, 60).all()


def test_paid_invoices_have_consistent_payment_fields(raw):
    inv = raw["invoices"]
    paid = inv[inv["paid_date"] != ""]
    unpaid = inv[inv["paid_date"] == ""]
    assert (paid["paid_amount"] == paid["amount"]).all()
    assert (unpaid["paid_amount"] == 0).all()


def test_no_payment_is_dated_after_last_journal_date(raw):
    last_day = raw["journal"]["date"].max()
    paid_dates = raw["invoices"].loc[raw["invoices"]["paid_date"] != "", "paid_date"]
    assert paid_dates.max() <= last_day


def test_generated_data_passes_validation(raw):
    ds, result = prepare_dataset(raw)
    assert ds is not None
    assert result.ok, result.summary()


def test_journal_entries_are_balanced_by_construction(raw):
    sums = raw["journal"].assign(d=lambda df: df.debit.astype(float), c=lambda df: df.credit.astype(float))
    per_entry = sums.groupby("entry_id")[["d", "c"]].sum()
    assert ((per_entry["d"] - per_entry["c"]).abs() < 0.005).all()


def test_budget_covers_each_month_and_budgeted_account(raw):
    budget = raw["budget"]
    # 9 operating lines plus interest (7000) and income tax (8000) per month.
    assert budget.groupby("period").size().eq(11).all()
    assert {"7000", "8000"} <= set(budget["account_code"])
    assert budget["budget_amount"].astype(float).ge(0).all()


@pytest.mark.parametrize(
    "overrides",
    [
        {"months": 0},
        {"payment_probability": 0.0},
        {"invoices_min": 10, "invoices_max": 5},
        {"invoices_min": 0},
    ],
)
def test_invalid_configuration_is_rejected(overrides):
    with pytest.raises(ValueError):
        GeneratorConfig(**overrides)


def test_write_dataset_creates_csv_files(tmp_path, raw):
    paths = write_dataset(raw, tmp_path / "out")
    assert set(paths) == {"coa", "journal", "invoices", "budget", "supplier_invoices"}
    assert all(p.exists() and p.suffix == ".csv" for p in paths.values())
    reread = pd.read_csv(paths["budget"], dtype=str)
    assert len(reread) == len(raw["budget"])
