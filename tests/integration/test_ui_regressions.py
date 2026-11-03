"""Regression tests for dashboard defects found in the v1.1 review."""

from __future__ import annotations

import io
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from accviz import config, ui
from accviz.synthetic import GeneratorConfig, generate_dataset, write_dataset

APP = Path(config.PROJECT_ROOT / "src" / "accviz" / "dashboard.py")

pytestmark = [pytest.mark.integration, pytest.mark.ui]


class _Upload(io.BytesIO):
    name = "upload.csv"


def test_dashboard_reloads_when_the_data_directory_is_regenerated(tmp_path, monkeypatch):
    folder = tmp_path / "live"
    write_dataset(generate_dataset(GeneratorConfig(seed=5, months=6)), folder)
    monkeypatch.setenv("ACCVIZ_DATA_DIR", str(folder))
    app = AppTest.from_file(str(APP), default_timeout=300).run()
    before = app.metric[0].value

    time.sleep(0.01)  # make sure the new files get a different modification time
    write_dataset(generate_dataset(GeneratorConfig(seed=99, months=6, base_monthly_revenue=500_000)), folder)
    app.run()
    after = app.metric[0].value
    assert before != after, "the dashboard kept showing the old data"


def test_directory_signature_changes_when_a_file_changes(tmp_path):
    write_dataset(generate_dataset(GeneratorConfig(seed=5, months=2)), tmp_path)
    first = ui.directory_signature(str(tmp_path))
    time.sleep(0.01)
    path = tmp_path / config.JOURNAL_FILE
    path.write_bytes(path.read_bytes() + b"\n")
    assert ui.directory_signature(str(tmp_path)) != first


def test_empty_uploaded_file_is_reported_not_raised(tmp_path):
    files = {key: _Upload(b"") for key in config.DATASET_FILES}
    ds, result = ui.load_from_uploads(files)
    assert ds is None
    assert not result.ok
    assert any("could not be read as a CSV" in e for e in result.errors)


def test_valid_uploads_are_analysed(tmp_path):
    raw_dir = tmp_path / "src"
    write_dataset(generate_dataset(GeneratorConfig(seed=5, months=3)), raw_dir)
    files = {key: _Upload((raw_dir / name).read_bytes()) for key, name in config.DATASET_FILES.items()}
    ds, result = ui.load_from_uploads(files)
    assert ds is not None and result.ok
