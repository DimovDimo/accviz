"""Cost-centre view: expenses by department and month."""

from __future__ import annotations

import pandas as pd

from accviz.ledger import DateLike, filter_dates, with_account_info

UNASSIGNED = "Unassigned"
DEPARTMENT_COLUMNS = ["period", "department", "amount"]
SUMMARY_COLUMNS = ["department", "amount", "share"]


def expenses_by_department(
    journal: pd.DataFrame, coa: pd.DataFrame, start: DateLike = None, end: DateLike = None
) -> pd.DataFrame:
    """Long table: one row per (month, department) with the expense total in natural sign."""
    df = with_account_info(journal, coa)
    df = df[df["account_type"] == "Expense"]
    df = filter_dates(df, start, end)
    if df.empty:
        return pd.DataFrame(columns=DEPARTMENT_COLUMNS)
    dept = df["department"].where(df["department"] != "", UNASSIGNED)
    out = (
        df.assign(department=dept)
        .groupby(["period", "department"], as_index=False)["natural_amount"]
        .sum()
        .rename(columns={"natural_amount": "amount"})
    )
    return out[out["amount"] != 0].sort_values(["period", "department"]).reset_index(drop=True)[DEPARTMENT_COLUMNS]


def department_summary(by_department: pd.DataFrame) -> pd.DataFrame:
    """Total expense per department and its share of the total, largest first."""
    if by_department.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)
    out = by_department.groupby("department", as_index=False)["amount"].sum()
    total = out["amount"].sum()
    out["share"] = out["amount"] / total if total else 0.0
    return out.sort_values("amount", ascending=False).reset_index(drop=True)[SUMMARY_COLUMNS]


def department_pivot(by_department: pd.DataFrame) -> pd.DataFrame:
    """Months as rows, departments as columns (zeros where a department had no cost)."""
    if by_department.empty:
        return pd.DataFrame()
    return by_department.pivot_table(index="period", columns="department", values="amount", aggfunc="sum").fillna(0.0)
