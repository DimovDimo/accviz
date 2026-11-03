"""Budget versus actual analysis for revenue and expense accounts."""

from __future__ import annotations

import numpy as np
import pandas as pd

from accviz import config
from accviz.ledger import DateLike, filter_dates, with_account_info

VARIANCE_COLUMNS = [
    "period",
    "account_code",
    "account_name",
    "account_type",
    "budget",
    "actual",
    "variance",
    "variance_pct",
    "favorable",
]


def budget_variance(
    journal: pd.DataFrame,
    coa: pd.DataFrame,
    budget: pd.DataFrame,
    start: DateLike = None,
    end: DateLike = None,
) -> pd.DataFrame:
    """Actual versus budget per month and account.

    ``variance = actual - budget`` in natural sign. A revenue variance is favourable when
    it is non-negative; an expense variance is favourable when it is non-positive.
    Rows that exist only in the budget (no actual) and vice versa are kept.
    """
    df = with_account_info(journal, coa)
    df = df[df["account_type"].isin(config.PROFIT_LOSS_TYPES)]
    df = filter_dates(df, start, end)
    actual = (
        df.groupby(["period", "account_code"], as_index=False)["natural_amount"].sum()
        .rename(columns={"natural_amount": "actual"})
    )

    b = budget[["period", "account_code", "budget_amount"]].rename(columns={"budget_amount": "budget"})
    if start is not None:
        b = b[b["period"] >= pd.Timestamp(start).strftime("%Y-%m")]
    if end is not None:
        b = b[b["period"] <= pd.Timestamp(end).strftime("%Y-%m")]

    merged = actual.merge(b, on=["period", "account_code"], how="outer")
    if merged.empty:
        return pd.DataFrame(columns=VARIANCE_COLUMNS)
    merged[["actual", "budget"]] = merged[["actual", "budget"]].fillna(0.0).astype(float)
    merged = merged.merge(coa[["account_code", "account_name", "account_type"]], on="account_code", how="left")
    merged = merged[merged["account_type"].isin(config.PROFIT_LOSS_TYPES)]

    merged["variance"] = merged["actual"] - merged["budget"]
    merged["variance_pct"] = merged["variance"] / merged["budget"].replace(0, np.nan)
    is_revenue = merged["account_type"] == "Revenue"
    merged["favorable"] = np.where(is_revenue, merged["variance"] >= 0, merged["variance"] <= 0)
    return merged[VARIANCE_COLUMNS].sort_values(["period", "account_code"]).reset_index(drop=True)


def budget_summary(variance: pd.DataFrame) -> pd.DataFrame:
    """Totals per account over the whole selected period."""
    columns = ["account_code", "account_name", "account_type", "budget", "actual", "variance", "variance_pct", "favorable"]
    if variance.empty:
        return pd.DataFrame(columns=columns)
    out = variance.groupby(["account_code", "account_name", "account_type"], as_index=False)[
        ["budget", "actual"]
    ].sum()
    out["variance"] = out["actual"] - out["budget"]
    out["variance_pct"] = np.where(out["budget"] != 0, out["variance"] / out["budget"].replace(0, np.nan), np.nan)
    is_revenue = out["account_type"] == "Revenue"
    out["favorable"] = np.where(is_revenue, out["variance"] >= 0, out["variance"] <= 0)
    return out[columns].sort_values("account_code").reset_index(drop=True)
