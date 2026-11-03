"""The sample dataset committed to the repository must be valid and analysable."""

from __future__ import annotations

import pytest

from accviz import config
from accviz.analysis import analyze
from accviz.loader import load_raw_directory, prepare_dataset, read_dataset


@pytest.fixture(scope="module")
def sample():
    return read_dataset(config.DEFAULT_DATA_DIR)


def test_sample_files_exist():
    for filename in config.DATASET_FILES.values():
        assert (config.DEFAULT_DATA_DIR / filename).is_file(), filename


def test_sample_passes_validation_without_errors():
    ds, result = prepare_dataset(load_raw_directory(config.DEFAULT_DATA_DIR))
    assert ds is not None
    assert result.ok, result.summary()


def test_sample_covers_two_years(sample):
    months = sample.journal["date"].dt.to_period("M").nunique()
    assert months >= 24


def test_sample_company_is_balanced_at_the_end(sample):
    result = analyze(sample)
    assert result.balance_sheet.is_balanced()
    assert result.kpis["net_income"] > 0
    assert result.kpis["closing_cash"] > 0


def test_sample_budget_covers_the_full_period(sample):
    months = sample.budget["period"].nunique()
    # The journal also contains the opening balances dated the last day of the previous month.
    assert months == sample.journal["date"].dt.to_period("M").nunique() - 1
