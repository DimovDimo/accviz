"""Accounts-payable sub-ledger: open supplier invoices, aging and top suppliers.

The aging logic is shared with receivables (:mod:`accviz.receivables`); this module only
adapts the supplier column names.
"""

from __future__ import annotations

import pandas as pd

from accviz import receivables
from accviz.ledger import DateLike

PAYABLE_AGING_COLUMNS = [
    "invoice_id",
    "supplier",
    "issue_date",
    "due_date",
    "amount",
    "paid_as_of",
    "outstanding",
    "days_overdue",
    "bucket",
]


def payables_aging(supplier_invoices: pd.DataFrame, as_of: DateLike) -> pd.DataFrame:
    """Open supplier invoices at *as_of*, with outstanding amount and aging bucket."""
    if supplier_invoices.empty:
        return pd.DataFrame(columns=PAYABLE_AGING_COLUMNS)
    renamed = supplier_invoices.rename(columns={"supplier": "customer"})
    aging = receivables.aging_schedule(renamed, as_of)
    if aging.empty:
        return pd.DataFrame(columns=PAYABLE_AGING_COLUMNS)
    return aging.rename(columns={"customer": "supplier"})[PAYABLE_AGING_COLUMNS]


def payables_summary(aging: pd.DataFrame) -> pd.DataFrame:
    """Outstanding amount and invoice count per aging bucket (all buckets listed)."""
    if aging.empty:
        return receivables.aging_summary(pd.DataFrame(columns=["invoice_id", "customer", "outstanding", "bucket"]))
    return receivables.aging_summary(aging.rename(columns={"supplier": "customer"}))


def top_suppliers(aging: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Suppliers with the largest open balances."""
    if aging.empty:
        return pd.DataFrame(columns=["supplier", "outstanding", "invoice_count"])
    out = receivables.top_customers(aging.rename(columns={"supplier": "customer"}), n)
    return out.rename(columns={"customer": "supplier"})


def total_payable(aging: pd.DataFrame) -> float:
    return float(aging["outstanding"].sum()) if not aging.empty else 0.0
