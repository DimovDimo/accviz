"""A v1.0 dataset (no supplier_invoices.csv, no journal source column) must still analyse."""

from __future__ import annotations

import shutil

import pytest

from accviz import config
from accviz.analysis import analyze
from accviz.loader import prepare_dataset, read_dataset

pytestmark = pytest.mark.integration


@pytest.fixture
def v10_directory(tmp_path):
    folder = tmp_path / "v10"
    shutil.copytree(config.DEFAULT_DATA_DIR, folder)
    (folder / config.SUPPLIER_INVOICES_FILE).unlink()
    journal_path = folder / config.JOURNAL_FILE
    import pandas as pd

    journal = pd.read_csv(journal_path, dtype=str, keep_default_na=False)
    journal.drop(columns=["source"]).to_csv(journal_path, index=False)
    return folder


def test_v10_layout_loads_with_warnings_only(v10_directory):
    from accviz.loader import load_raw_directory

    ds, result = prepare_dataset(load_raw_directory(v10_directory))
    assert ds is not None and result.ok
    assert any("supplier_invoices.csv" in w for w in result.warnings)
    assert any("'source' not found" in w for w in result.warnings)


def test_v10_layout_analyses_with_empty_v11_sections(v10_directory):
    ds = read_dataset(v10_directory)
    result = analyze(ds)
    assert result.balance_sheet.is_balanced()
    assert result.ap_aging.empty
    assert result.cash_flow.is_reconciled()
    assert result.audit.manual_entries == 0  # everything is a system entry in v1.0 data
    assert result.kpis["net_income"] == pytest.approx(analyze(read_dataset(config.DEFAULT_DATA_DIR)).kpis["net_income"], rel=0.5)


def test_v10_layout_keeps_the_v10_analysis_fields(v10_directory):
    result = analyze(read_dataset(v10_directory))
    for name in ("income_monthly", "balance_sheet", "cash", "aging", "aging_summary", "budget_summary", "trial_balance", "ratios", "kpis"):
        assert getattr(result, name) is not None
