"""General-ledger helpers: natural-sign amounts, trial balance and balances as of a date."""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from accviz import config

DateLike = Any  # str, date, datetime or pd.Timestamp; None means unbounded

ACCOUNT_COLUMNS = ["account_code", "account_name", "account_type", "subtype"]


def to_timestamp(value: DateLike) -> Optional[pd.Timestamp]:
    """Convert a date-like value to a Timestamp (None stays None)."""
    return None if value is None else pd.Timestamp(value)


def filter_dates(
    df: pd.DataFrame, start: DateLike = None, end: DateLike = None, column: str = "date"
) -> pd.DataFrame:
    """Keep rows whose *column* lies in the inclusive range [start, end]."""
    mask = pd.Series(True, index=df.index)
    start_ts, end_ts = to_timestamp(start), to_timestamp(end)
    if start_ts is not None:
        mask &= df[column] >= start_ts
    if end_ts is not None:
        mask &= df[column] <= end_ts
    return df.loc[mask]


def with_account_info(journal: pd.DataFrame, coa: pd.DataFrame) -> pd.DataFrame:
    """Join journal lines with account information and add calculated columns.

    Added columns:

    * ``amount`` – signed amount, ``debit - credit``
    * ``natural_amount`` – amount in the account's natural sign (positive when the
      account carries its normal balance)
    * ``period`` – calendar month as ``YYYY-MM``
    """
    df = journal.merge(coa[ACCOUNT_COLUMNS], on="account_code", how="left")
    df["amount"] = df["debit"] - df["credit"]
    debit_normal = df["account_type"].isin(config.DEBIT_NORMAL_TYPES)
    df["natural_amount"] = df["amount"].where(debit_normal, -df["amount"])
    df["period"] = df["date"].dt.strftime("%Y-%m")
    return df


def trial_balance(
    journal: pd.DataFrame, coa: pd.DataFrame, start: DateLike = None, end: DateLike = None
) -> pd.DataFrame:
    """Return one row per account with debit/credit totals and balances.

    ``balance`` is ``debit - credit``; ``natural_balance`` uses the account's normal side.
    Accounts without movements are included with zeros.
    """
    j = filter_dates(journal, start, end)
    totals = j.groupby("account_code")[["debit", "credit"]].sum()
    tb = coa[ACCOUNT_COLUMNS].merge(totals, left_on="account_code", right_index=True, how="left")
    tb[["debit", "credit"]] = tb[["debit", "credit"]].fillna(0.0).astype(float)
    tb["balance"] = tb["debit"] - tb["credit"]
    debit_normal = tb["account_type"].isin(config.DEBIT_NORMAL_TYPES)
    tb["natural_balance"] = tb["balance"].where(debit_normal, -tb["balance"])
    return tb.sort_values("account_code").reset_index(drop=True)


def is_trial_balance_balanced(tb: pd.DataFrame, tolerance: float = config.BALANCE_TOLERANCE) -> bool:
    """True when total debits equal total credits within *tolerance*."""
    return abs(float(tb["debit"].sum()) - float(tb["credit"].sum())) <= tolerance


def balances_as_of(journal: pd.DataFrame, coa: pd.DataFrame, as_of: DateLike) -> pd.DataFrame:
    """Cumulative natural-sign balance of every account up to and including *as_of*."""
    tb = trial_balance(journal, coa, end=as_of)
    return tb[ACCOUNT_COLUMNS + ["natural_balance"]]
