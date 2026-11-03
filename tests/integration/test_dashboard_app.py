"""UI tests of the Streamlit dashboard using streamlit.testing.AppTest (no browser needed)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from accviz import config

APP = Path(config.PROJECT_ROOT / "src" / "accviz" / "dashboard.py")

pytestmark = [pytest.mark.integration, pytest.mark.ui]


def run_app(monkeypatch, data_dir: Path) -> AppTest:
    monkeypatch.setenv("ACCVIZ_DATA_DIR", str(data_dir))
    app = AppTest.from_file(str(APP), default_timeout=180)
    app.run()
    return app


def test_dashboard_renders_all_tabs_for_sample_data(monkeypatch):
    app = run_app(monkeypatch, config.DEFAULT_DATA_DIR)
    assert not app.exception, [e.value for e in app.exception]
    assert len(app.tabs) == 9
    assert [t.label for t in app.tabs] == [
        "Overview",
        "Income statement",
        "Cash flow",
        "Balance sheet",
        "Receivables & payables",
        "Budget",
        "Forecast",
        "Audit",
        "Data quality",
    ]


def test_dashboard_shows_kpi_metrics(monkeypatch):
    app = run_app(monkeypatch, config.DEFAULT_DATA_DIR)
    labels = [m.label for m in app.metric]
    assert {"Revenue", "Net income", "Closing cash", "Outstanding receivables"} <= set(labels)


def test_dashboard_reports_balanced_sheet(monkeypatch):
    app = run_app(monkeypatch, config.DEFAULT_DATA_DIR)
    success_texts = [s.value for s in app.success]
    assert any("is balanced" in text for text in success_texts)


def test_dashboard_shows_error_for_missing_directory(monkeypatch, tmp_path):
    app = run_app(monkeypatch, tmp_path / "does-not-exist")
    assert not app.exception
    assert len(app.error) >= 1
    assert "not found" in app.error[0].value
    assert len(app.tabs) == 0


def test_dashboard_shows_validation_errors_instead_of_crashing(monkeypatch, tmp_path):
    broken = tmp_path / "broken"
    shutil.copytree(config.DEFAULT_DATA_DIR, broken)
    journal = broken / config.JOURNAL_FILE
    df = pd.read_csv(journal, dtype=str, keep_default_na=False)
    df.loc[0, "debit"] = "99999.99"  # unbalance the opening entry
    df.to_csv(journal, index=False)

    app = run_app(monkeypatch, broken)
    assert not app.exception
    assert any("unbalanced" in e.value for e in app.error)
    assert len(app.tabs) == 0
