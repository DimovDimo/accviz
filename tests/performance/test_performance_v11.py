"""Timing tests for the v1.1 analyses (NFR-11: 24 months with audit and forecast in under 15 s)."""

from __future__ import annotations

import io
import time

import pytest
from openpyxl import load_workbook

from accviz.analysis import analyze
from accviz.export import workbook_bytes
from accviz.loader import prepare_dataset
from accviz.synthetic import GeneratorConfig, generate_dataset

pytestmark = pytest.mark.performance


@pytest.fixture(scope="module")
def dataset():
    ds, result = prepare_dataset(generate_dataset(GeneratorConfig(seed=42, months=24, anomalies=True)))
    assert ds is not None and result.ok
    return ds


def test_full_analysis_with_audit_and_forecast_is_under_15_seconds(dataset):
    start = time.perf_counter()
    analyze(dataset)
    seconds = time.perf_counter() - start
    assert seconds < 15, f"analysis took {seconds:.2f}s"


def test_excel_export_is_under_15_seconds(dataset):
    result = analyze(dataset)
    start = time.perf_counter()
    data = workbook_bytes(result)
    seconds = time.perf_counter() - start
    assert seconds < 15, f"export took {seconds:.2f}s"
    assert len(load_workbook(io.BytesIO(data)).sheetnames) == 11
