"""Further dashboard tests: sidebar interactions, uploads and empty-data states."""

from __future__ import annotations

import datetime as dt
import io
import runpy
import sys
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from accviz import cli, config, ui
from accviz.synthetic import GeneratorConfig, generate_dataset, write_dataset
from tests.factories import tiny_raw

APP = Path(config.PROJECT_ROOT / "src" / "accviz" / "dashboard.py")

pytestmark = [pytest.mark.integration, pytest.mark.ui]


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("ACCVIZ_DATA_DIR", str(config.DEFAULT_DATA_DIR))
    return AppTest.from_file(str(APP), default_timeout=180).run()


def test_period_filter_changes_the_analysed_period(app):
    before = {m.label: m.value for m in app.metric}
    app.sidebar.date_input[0].set_value((dt.date(2025, 1, 1), dt.date(2025, 1, 31))).run()
    assert not app.exception
    after = {m.label: m.value for m in app.metric}
    assert after["Revenue"] != before["Revenue"]
    assert "2025-01-01 to 2025-01-31" in app.caption[0].value


def test_reversed_period_shows_an_error(app):
    app.sidebar.date_input[0].set_value((dt.date(2025, 6, 1), dt.date(2025, 1, 1))).run()
    assert not app.exception
    assert any("must not be after" in e.value for e in app.error)


def test_upload_mode_asks_for_all_files(app):
    app.sidebar.radio[0].set_value("Upload CSV files").run()
    assert not app.exception
    assert any("Upload the four required files" in i.value for i in app.sidebar.info)


def test_warnings_are_shown_in_an_expander(monkeypatch, tmp_path):
    folder = tmp_path / "data"
    write_dataset(generate_dataset(GeneratorConfig(months=2)), folder)
    journal = pd.read_csv(folder / config.JOURNAL_FILE, dtype=str, keep_default_na=False)
    journal = journal.drop(columns=["reference"])
    journal.to_csv(folder / config.JOURNAL_FILE, index=False)
    monkeypatch.setenv("ACCVIZ_DATA_DIR", str(folder))
    app = AppTest.from_file(str(APP), default_timeout=180).run()
    assert not app.exception
    assert len(app.tabs) == 9  # data is still usable
    assert any("optional column 'reference'" in w.value for w in app.warning)


def test_empty_budget_shows_info_message(monkeypatch, tmp_path):
    folder = tmp_path / "data"
    raw = tiny_raw()
    raw["budget"] = raw["budget"].iloc[0:0]
    folder.mkdir()
    for key, filename in config.DATASET_FILES.items():
        raw[key].to_csv(folder / filename, index=False)
    monkeypatch.setenv("ACCVIZ_DATA_DIR", str(folder))
    app = AppTest.from_file(str(APP), default_timeout=180).run()
    assert not app.exception
    assert any("No budget rows" in i.value for i in app.info)


def test_load_from_uploads_builds_a_dataset(tmp_path):
    raw = tiny_raw()
    files = {}
    for key, filename in config.DATASET_FILES.items():
        buffer = io.BytesIO(raw[key].to_csv(index=False).encode("utf-8"))
        buffer.name = filename
        files[key] = buffer
    ds, result = ui.load_from_uploads(files)
    assert result.ok
    assert len(ds.journal) == len(raw["journal"])


def test_load_from_directory_reports_missing_folder(tmp_path):
    ds, result = ui.load_from_directory(str(tmp_path / "missing"))
    assert ds is None
    assert not result.ok


def test_money_formats_none_as_dash():
    assert ui.money(None) == "–"
    assert ui.money(1234.5).startswith("1,234.50")


def test_default_directory_respects_environment(monkeypatch):
    monkeypatch.setenv("ACCVIZ_DATA_DIR", "/tmp/custom")
    assert ui._default_data_dir() == "/tmp/custom"
    monkeypatch.delenv("ACCVIZ_DATA_DIR")
    assert ui._default_data_dir() == str(config.DEFAULT_DATA_DIR)


def test_dashboard_command_starts_streamlit_with_data_dir(monkeypatch, tmp_path):
    captured = {}

    def fake_call(cmd, env=None):
        captured["cmd"] = cmd
        captured["env"] = env
        return 0

    monkeypatch.setattr(cli.subprocess, "call", fake_call)
    assert cli.main(["dashboard", "--data", str(tmp_path), "--port", "8600"]) == 0
    assert "streamlit" in captured["cmd"]
    assert "8600" in captured["cmd"]
    assert captured["env"][cli.DATA_ENV_VAR] == str(tmp_path.resolve())


def test_python_m_accviz_runs_the_cli(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["accviz", "--version"])
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("accviz", run_name="__main__")
    assert excinfo.value.code == 0
    assert "accviz 1.1.0" in capsys.readouterr().out
