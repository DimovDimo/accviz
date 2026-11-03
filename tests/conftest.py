"""Shared pytest fixtures and automatic test-layer markers."""

from __future__ import annotations

import pytest

from accviz import config
from accviz.analysis import analyze
from accviz.loader import Dataset, prepare_dataset
from accviz.synthetic import GeneratorConfig, generate_dataset
from tests.factories import tiny_dataset as _tiny_dataset

LAYER_BY_FOLDER = {
    "unit": pytest.mark.unit,
    "integration": pytest.mark.integration,
    "property": pytest.mark.property,
    "performance": pytest.mark.performance,
}


def pytest_collection_modifyitems(config, items):
    """Tag every test with its layer based on the folder it lives in."""
    for item in items:
        for part in item.path.parts:
            if part in LAYER_BY_FOLDER:
                item.add_marker(LAYER_BY_FOLDER[part])
                break


@pytest.fixture
def tiny_dataset() -> Dataset:
    """Hand-computed company (see tests/factories.py)."""
    return _tiny_dataset()


@pytest.fixture(scope="session")
def small_sample_raw():
    """Six months of synthetic data, fast to generate and analyse."""
    return generate_dataset(GeneratorConfig(seed=7, months=6))


@pytest.fixture(scope="session")
def small_sample_dataset(small_sample_raw) -> Dataset:
    ds, result = prepare_dataset(small_sample_raw)
    assert ds is not None and result.ok, result.summary()
    return ds


@pytest.fixture(scope="session")
def small_sample_analysis(small_sample_dataset):
    return analyze(small_sample_dataset)


@pytest.fixture(scope="session")
def committed_sample_dir():
    """The sample dataset shipped in data/sample."""
    return config.DEFAULT_DATA_DIR
