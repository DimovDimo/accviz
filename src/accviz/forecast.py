"""Monthly revenue forecast: linear trend, optional seasonal indices, residual band and backtest.

Model
-----
``y_t = (a + b·t) · s_m`` where ``t`` is the month index and ``s_m`` the seasonal index of
the calendar month ``m``. Seasonal indices are estimated only when the history has at least
24 months (``SEASONAL_MIN_HISTORY``); otherwise ``s_m = 1`` (trend only). Indices are the
mean ratio of actual to trend per calendar month, normalised to average 1.

Band
----
``forecast ± 1.96 × s`` where ``s`` is the residual standard deviation of the fitted history
(degrees of freedom = n − 2). The lower bound is not allowed below zero.

Backtest
--------
The last ``holdout`` months are removed, the model is fitted on the rest, and the mean
absolute percentage error (MAPE) of the held-out months is reported.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

MIN_HISTORY = 3
BACKTEST_HOLDOUT = 6  # months withheld for the accuracy backtest
SEASONAL_MIN_HISTORY = 24
SEASONAL_PASSES = 10
BAND_Z = 1.96
MAX_HORIZON = 24
FORECAST_COLUMNS = ["period", "kind", "value", "lower", "upper"]


@dataclass(frozen=True)
class Forecast:
    """Fitted model, forecast table (history and future months) and fit diagnostics."""

    table: pd.DataFrame
    seasonal: bool
    residual_sd: float
    slope: float
    intercept: float
    seasonal_index: dict[int, float]

    @property
    def future(self) -> pd.DataFrame:
        return self.table[self.table["kind"] == "forecast"].reset_index(drop=True)


def _month_numbers(periods: pd.Index) -> np.ndarray:
    return np.array([int(str(p)[5:7]) for p in periods])


def _fit(values: np.ndarray, months: np.ndarray) -> tuple[float, float, dict[int, float], bool, float]:
    """Estimate trend, seasonal indices and the residual standard deviation.

    With seasonality, trend and indices are estimated alternately (a few passes): the trend
    is fitted to the de-seasonalised series, then the indices are the mean ratio of actual to
    trend per calendar month. A single pass would leak the seasonal pattern into the slope.
    """
    n = len(values)
    t = np.arange(n, dtype=float)
    seasonal = n >= SEASONAL_MIN_HISTORY
    index: dict[int, float] = {}
    season_t = np.ones(n)
    passes = SEASONAL_PASSES if seasonal else 1
    for _ in range(passes):
        slope, intercept = np.polyfit(t, values / season_t, 1)
        trend = intercept + slope * t
        if not seasonal:
            break
        ratio = np.where(trend > 0, values / np.where(trend > 0, trend, 1.0), 1.0)
        index = {}
        for m in range(1, 13):
            mask = months == m
            if mask.any():
                index[m] = float(ratio[mask].mean())
        mean_index = float(np.mean(list(index.values())))
        index = {m: v / mean_index for m, v in index.items()}
        season_t = np.array([index.get(m, 1.0) for m in months])
    fitted = trend * season_t
    dof = max(n - 2, 1)
    residual_sd = float(np.sqrt(np.sum((values - fitted) ** 2) / dof))
    return float(slope), float(intercept), index, seasonal, residual_sd


def _future_periods(last: str, horizon: int) -> list[str]:
    return list(pd.period_range(pd.Period(last, freq="M") + 1, periods=horizon, freq="M").strftime("%Y-%m"))


def fit_forecast(revenue: pd.Series, horizon: int = 6) -> Forecast:
    """Fit on a monthly revenue series (index: ``YYYY-MM``) and forecast *horizon* months.

    Raises ``ValueError`` when there are fewer than three months of history.
    """
    if not 1 <= horizon <= MAX_HORIZON:
        raise ValueError(f"horizon must be between 1 and {MAX_HORIZON} months")
    if len(revenue) < MIN_HISTORY:
        raise ValueError(f"at least {MIN_HISTORY} months of revenue history are needed, got {len(revenue)}")
    values = revenue.to_numpy(dtype=float)
    periods = pd.Index(revenue.index.astype(str))
    months = _month_numbers(periods)
    slope, intercept, index, seasonal, sd = _fit(values, months)

    n = len(values)
    t_all = np.arange(n, dtype=float)
    fitted_hist = (intercept + slope * t_all) * (
        np.array([index.get(m, 1.0) for m in months]) if seasonal else 1.0
    )
    hist = pd.DataFrame(
        {
            "period": periods,
            "kind": "actual",
            "value": values,
            "lower": np.nan,
            "upper": np.nan,
        }
    )
    hist["fitted"] = fitted_hist
    future_periods = _future_periods(periods[-1], horizon)
    future_months = _month_numbers(pd.Index(future_periods))
    t_future = np.arange(n, n + horizon, dtype=float)
    point = (intercept + slope * t_future) * (
        np.array([index.get(m, 1.0) for m in future_months]) if seasonal else 1.0
    )
    fut = pd.DataFrame(
        {
            "period": future_periods,
            "kind": "forecast",
            "value": point,
            "lower": np.maximum(point - BAND_Z * sd, 0.0),
            "upper": point + BAND_Z * sd,
            "fitted": np.nan,
        }
    )
    table = pd.concat([hist, fut], ignore_index=True)[FORECAST_COLUMNS + ["fitted"]]
    return Forecast(
        table=table,
        seasonal=seasonal,
        residual_sd=sd,
        slope=slope,
        intercept=intercept,
        seasonal_index=index,
    )


def backtest(revenue: pd.Series, holdout: int = BACKTEST_HOLDOUT) -> dict:
    """Fit on all but the last *holdout* months and score the held-out months.

    Returns ``mape`` (fraction, e.g. 0.03 for 3 %; ``None`` when every held-out month has zero
    revenue; months with zero actual revenue are excluded from the average),
    ``seasonal`` (whether the training
    window was long enough for seasonal indices), and the ``actual``/``predicted`` table.
    """
    if len(revenue) < holdout + MIN_HISTORY:
        raise ValueError(f"backtest needs at least {holdout + MIN_HISTORY} months of history")
    train, test = revenue.iloc[:-holdout], revenue.iloc[-holdout:]
    values = train.to_numpy(dtype=float)
    months = _month_numbers(pd.Index(train.index.astype(str)))
    slope, intercept, index, seasonal, _ = _fit(values, months)
    test_months = _month_numbers(pd.Index(test.index.astype(str)))
    t_test = np.arange(len(train), len(revenue), dtype=float)
    predicted = (intercept + slope * t_test) * (
        np.array([index.get(m, 1.0) for m in test_months]) if seasonal else 1.0
    )
    actual = test.to_numpy(dtype=float)
    # MAPE is undefined for months with zero revenue; those months are left out of the average.
    scored = np.abs(actual) > 0
    mape = float(np.mean(np.abs(actual[scored] - predicted[scored]) / np.abs(actual[scored]))) if scored.any() else None
    return {
        "mape": mape,
        "seasonal": seasonal,
        "actual": pd.DataFrame({"period": test.index.astype(str), "actual": actual, "predicted": predicted}),
    }


def revenue_series(income_monthly: pd.DataFrame) -> pd.Series:
    """Monthly revenue on a continuous calendar, indexed by ``YYYY-MM``.

    A month between the first and last posting with no income-statement activity is filled
    with zero revenue. Gaps would otherwise shift the trend's time axis and misalign the
    seasonal indices, because the model counts months, not table rows.
    """
    if income_monthly.empty:
        return pd.Series(dtype=float)
    values = pd.Series(income_monthly["revenue"].to_numpy(dtype=float), index=income_monthly["period"].to_numpy())
    calendar = pd.period_range(values.index.min(), values.index.max(), freq="M").strftime("%Y-%m")
    return values.reindex(calendar, fill_value=0.0).astype(float)
