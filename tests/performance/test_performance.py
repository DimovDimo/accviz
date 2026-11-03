"""Timing tests with generous limits (NFR-02: analysis of 24 months in under 10 seconds)."""

from __future__ import annotations

import time

import pytest

from accviz.analysis import analyze
from accviz.loader import prepare_dataset
from accviz.report import render_report
from accviz.synthetic import GeneratorConfig, generate_dataset


@pytest.fixture(scope="module")
def dataset_24_months():
    start = time.perf_counter()
    raw = generate_dataset(GeneratorConfig(seed=42, months=24))
    generation_seconds = time.perf_counter() - start
    ds, result = prepare_dataset(raw)
    assert ds is not None and result.ok
    return ds, generation_seconds


def test_generation_of_24_months_is_fast(dataset_24_months):
    _, seconds = dataset_24_months
    assert seconds < 10, f"generation took {seconds:.2f}s"


def test_analysis_of_24_months_is_fast(dataset_24_months):
    ds, _ = dataset_24_months
    start = time.perf_counter()
    analyze(ds)
    elapsed = time.perf_counter() - start
    assert elapsed < 10, f"analysis took {elapsed:.2f}s"


def test_report_rendering_is_fast(dataset_24_months):
    ds, _ = dataset_24_months
    start = time.perf_counter()
    html = render_report(ds)
    elapsed = time.perf_counter() - start
    assert len(html) > 100_000
    assert elapsed < 30, f"report took {elapsed:.2f}s"
