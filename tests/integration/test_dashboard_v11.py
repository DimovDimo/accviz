"""Dashboard tests for the v1.1 tabs, run through Streamlit's AppTest on the demo dataset."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from accviz import config, ui

APP = Path(config.PROJECT_ROOT / "src" / "accviz" / "dashboard.py")

pytestmark = [pytest.mark.integration, pytest.mark.ui]


@pytest.fixture
def demo_app(monkeypatch):
    monkeypatch.setenv("ACCVIZ_DATA_DIR", str(config.DEMO_DATA_DIR))
    return AppTest.from_file(str(APP), default_timeout=300).run()


def test_nine_tabs_with_the_v11_labels(demo_app):
    assert not demo_app.exception
    labels = [t.label for t in demo_app.tabs]
    assert labels == list(ui.TAB_NAMES)
    assert len(labels) == 9
    assert labels[6:8] == ["Forecast", "Audit"]


def test_forecast_horizon_slider_is_in_range(demo_app):
    sliders = [s for s in demo_app.slider if "horizon" in (s.label or "").lower() or "forecast" in (s.label or "").lower()]
    assert sliders, [s.label for s in demo_app.slider]
    slider = sliders[0]
    assert slider.min == 3 and slider.max == 12
    slider.set_value(9).run()
    assert not demo_app.exception


def test_audit_tab_lists_findings_and_benford(demo_app):
    assert not demo_app.exception
    texts = " ".join([m.value for m in demo_app.markdown] + [c.value for c in demo_app.caption])
    assert "Benford" in texts


def test_switching_period_recomputes_the_v11_sections(demo_app):
    import datetime as dt

    demo_app.sidebar.date_input[0].set_value((dt.date(2025, 1, 1), dt.date(2025, 3, 31))).run()
    assert not demo_app.exception
    assert "2025-01-01 to 2025-03-31" in demo_app.caption[0].value


def test_upload_mode_reports_missing_optional_inputs(monkeypatch):
    monkeypatch.delenv("ACCVIZ_DATA_DIR", raising=False)
    app = AppTest.from_file(str(APP), default_timeout=300).run()
    app.sidebar.radio[0].set_value("Upload CSV files").run()
    assert not app.exception
    assert any("Upload the four required files" in i.value for i in app.sidebar.info)
