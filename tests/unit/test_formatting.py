"""Display formatting shared by the report and the dashboard."""

from __future__ import annotations

import pytest

from accviz.report import format_value

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "key, value, expected",
    [
        ("net_margin", 0.1842, "18.4 %"),
        ("revenue_vs_budget_pct", -0.0, "0.0 %"),
        ("revenue_vs_budget_pct", -0.00001, "0.0 %"),
        ("revenue_vs_budget_pct", -0.031, "-3.1 %"),
        ("current_ratio", 8.2345, "8.23"),
        ("closing_cash", 505137.789, "505,137.79 EUR"),
    ],
)
def test_format_value(key, value, expected):
    assert format_value(key, value) == expected


def test_missing_values_are_dashes():
    assert format_value("net_margin", None) == "–"
    assert format_value("net_margin", float("nan")) == "–"
