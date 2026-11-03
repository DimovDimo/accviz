"""Accounts-receivable (sub-ledger) analysis: outstanding invoices and aging."""

from __future__ import annotations

import numpy as np
import pandas as pd

from accviz import config
from accviz.ledger import DateLike

AGING_COLUMNS = [
    "invoice_id",
    "customer",
    "issue_date",
    "due_date",
    "amount",
    "paid_as_of",
    "outstanding",
    "days_overdue",
    "bucket",
]


def bucket_for_days(days_overdue: pd.Series | np.ndarray | float) -> pd.Categorical:
    """Map days overdue to an aging bucket label (days ≤ 0 means not yet due)."""
    values = pd.Series(np.asarray(days_overdue, dtype=float))
    return pd.Categorical(
        pd.cut(values, bins=list(config.AGING_BIN_EDGES), labels=list(config.AGING_BUCKETS)),
        categories=list(config.AGING_BUCKETS),
    )


def aging_schedule(invoices: pd.DataFrame, as_of: DateLike) -> pd.DataFrame:
    """Open invoices at *as_of* with outstanding amount and aging bucket.

    Only invoices issued on or before *as_of* are considered. A payment counts only if it
    was made on or before *as_of*. Fully settled invoices are excluded.
    """
    as_of_ts = pd.Timestamp(as_of)
    inv = invoices[invoices["issue_date"] <= as_of_ts].copy()
    paid_by_then = inv["paid_date"].notna() & (inv["paid_date"] <= as_of_ts)
    inv["paid_as_of"] = inv["paid_amount"].where(paid_by_then, 0.0)
    inv["outstanding"] = (inv["amount"] - inv["paid_as_of"]).clip(lower=0.0)
    inv = inv[inv["outstanding"] > config.BALANCE_TOLERANCE].copy()
    if inv.empty:
        return pd.DataFrame(columns=AGING_COLUMNS)
    inv["days_overdue"] = (as_of_ts - inv["due_date"]).dt.days
    inv["bucket"] = bucket_for_days(inv["days_overdue"])
    return inv[AGING_COLUMNS].sort_values(["days_overdue", "invoice_id"], ascending=[False, True]).reset_index(
        drop=True
    )


def aging_summary(aging: pd.DataFrame) -> pd.DataFrame:
    """Outstanding amount and invoice count per bucket, including empty buckets."""
    out = pd.DataFrame({"bucket": list(config.AGING_BUCKETS)})
    if aging.empty:
        out["invoice_count"] = 0
        out["outstanding"] = 0.0
    else:
        grouped = aging.groupby("bucket", observed=False).agg(
            invoice_count=("invoice_id", "count"), outstanding=("outstanding", "sum")
        )
        out = out.merge(grouped, left_on="bucket", right_index=True, how="left")
        out["invoice_count"] = out["invoice_count"].fillna(0).astype(int)
        out["outstanding"] = out["outstanding"].fillna(0.0)
    total = out["outstanding"].sum()
    out["share"] = out["outstanding"] / total if total else 0.0
    return out


def top_customers(aging: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Customers with the largest outstanding balances."""
    if aging.empty:
        return pd.DataFrame(columns=["customer", "outstanding", "invoice_count"])
    out = (
        aging.groupby("customer", as_index=False)
        .agg(outstanding=("outstanding", "sum"), invoice_count=("invoice_id", "count"))
        .sort_values("outstanding", ascending=False)
        .head(n)
    )
    return out.reset_index(drop=True)


def total_outstanding(aging: pd.DataFrame) -> float:
    return float(aging["outstanding"].sum()) if not aging.empty else 0.0
