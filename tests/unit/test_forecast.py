"""Unit tests for the revenue forecast and its backtest (I-5)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from accviz import forecast
from accviz.forecast import backtest, fit_forecast, revenue_series

pytestmark = pytest.mark.unit


def _series(values, start="2025-01"):
    periods = pd.period_range(start, periods=len(values), freq="M").strftime("%Y-%m")
    return pd.Series(values, index=periods, dtype=float)


def test_perfect_linear_trend_is_extrapolated_exactly():
    values = [100 + 10 * t for t in range(12)]
    model = fit_forecast(_series(values), horizon=3)
    assert not model.seasonal
    assert model.residual_sd == pytest.approx(0, abs=1e-9)
    assert model.future["value"].tolist() == pytest.approx([220, 230, 240])
    assert model.future["period"].tolist() == ["2026-01", "2026-02", "2026-03"]


def test_band_is_symmetric_and_never_negative():
    rng = np.random.default_rng(1)
    values = 1000 + rng.normal(0, 200, size=12)
    model = fit_forecast(_series(values), horizon=6)
    future = model.future
    half_width = future["upper"] - future["value"]
    assert np.allclose(half_width, forecast.BAND_Z * model.residual_sd)
    assert (future["lower"] >= 0).all()


def test_lower_bound_is_clipped_at_zero():
    model = fit_forecast(_series([10, 9, 8, 0, 1, 0, 1, 0]), horizon=2)
    assert (model.future["lower"] >= 0).all()


def test_seasonal_indices_are_used_from_24_months_and_recovered():
    pattern = np.array([0.9, 0.9, 1.0, 1.0, 1.05, 1.05, 1.0, 0.9, 1.0, 1.05, 1.1, 1.2])
    values = [(100 + 10 * t) * pattern[t % 12] for t in range(24)]  # multiplicative: trend x season
    model = fit_forecast(_series(values), horizon=12)
    assert model.seasonal
    assert len(model.seasonal_index) == 12
    assert np.mean(list(model.seasonal_index.values())) == pytest.approx(1.0)
    dec = model.seasonal_index[12] / model.seasonal_index[1]
    assert dec == pytest.approx(1.2 / 0.9, rel=0.02)
    assert model.future.loc[11, "value"] > model.future.loc[1, "value"]  # December above January


def test_trend_only_below_24_months():
    model = fit_forecast(_series(list(range(23))), horizon=3)
    assert not model.seasonal
    assert model.seasonal_index == {}


def test_fewer_than_three_months_is_an_error():
    with pytest.raises(ValueError, match="at least 3 months"):
        fit_forecast(_series([1.0, 2.0]), horizon=3)


@pytest.mark.parametrize("horizon", [0, 25])
def test_horizon_bounds(horizon):
    with pytest.raises(ValueError, match="horizon"):
        fit_forecast(_series([1.0, 2.0, 3.0, 4.0]), horizon=horizon)


def test_history_and_future_are_both_in_the_table():
    model = fit_forecast(_series([5, 6, 7, 8]), horizon=2)
    assert model.table["kind"].tolist() == ["actual"] * 4 + ["forecast"] * 2
    assert model.table["period"].iloc[-1] == "2025-06"


def test_backtest_is_zero_for_a_perfect_linear_series():
    result = backtest(_series([100 + 5 * t for t in range(12)]), holdout=4)
    assert result["mape"] == pytest.approx(0, abs=1e-9)
    assert not result["seasonal"]
    assert len(result["actual"]) == 4


def test_backtest_on_noisy_series_is_small():
    rng = np.random.default_rng(5)
    values = 1000 * (1 + 0.01 * np.arange(18)) * (1 + rng.normal(0, 0.02, size=18))
    result = backtest(_series(values), holdout=6)
    assert 0 < result["mape"] < 0.08


def test_backtest_needs_enough_history():
    with pytest.raises(ValueError, match="backtest needs"):
        backtest(_series([1.0, 2.0, 3.0, 4.0]), holdout=6)


def test_revenue_series_from_income_statement():
    income = pd.DataFrame({"period": ["2025-01", "2025-02"], "revenue": [500.0, 300.0]})
    series = revenue_series(income)
    assert series.to_dict() == {"2025-01": 500.0, "2025-02": 300.0}
    assert revenue_series(income.iloc[0:0]).empty
