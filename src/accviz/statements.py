"""Financial statements: monthly income statement, balance sheet, cash trend and breakdowns."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from accviz import config
from accviz.ledger import DateLike, balances_as_of, filter_dates, to_timestamp, with_account_info

# Maps account subtypes to income-statement columns.
INCOME_LINES: dict[str, str] = {
    config.SUBTYPE_OPERATING_REVENUE: "revenue",
    config.SUBTYPE_COST_OF_SALES: "cost_of_sales",
    config.SUBTYPE_OPERATING_EXPENSE: "operating_expenses",
    config.SUBTYPE_FINANCIAL_EXPENSE: "financial_expenses",
    config.SUBTYPE_TAX_EXPENSE: "tax_expense",
}
INCOME_COLUMNS: list[str] = [
    "period",
    "revenue",
    "cost_of_sales",
    "gross_profit",
    "operating_expenses",
    "operating_profit",
    "financial_expenses",
    "tax_expense",
    "net_income",
]
TOTAL_KEYS: list[str] = [c for c in INCOME_COLUMNS if c != "period"]


def income_statement(
    journal: pd.DataFrame, coa: pd.DataFrame, start: DateLike = None, end: DateLike = None
) -> pd.DataFrame:
    """Monthly income statement between *start* and *end* (inclusive).

    Revenue and expenses are shown as positive numbers; profit lines are derived.
    """
    df = with_account_info(journal, coa)
    df = df[df["account_type"].isin(config.PROFIT_LOSS_TYPES)]
    df = filter_dates(df, start, end)
    if df.empty:
        return pd.DataFrame(columns=INCOME_COLUMNS)

    grouped = df.groupby(["period", "subtype"])["natural_amount"].sum().unstack(fill_value=0.0)
    grouped = grouped.rename(columns=INCOME_LINES).reindex(columns=list(INCOME_LINES.values()), fill_value=0.0)
    out = grouped.copy()
    out.columns.name = None  # drop the pivot's "subtype" header
    out["gross_profit"] = out["revenue"] - out["cost_of_sales"]
    out["operating_profit"] = out["gross_profit"] - out["operating_expenses"]
    out["net_income"] = out["operating_profit"] - out["financial_expenses"] - out["tax_expense"]
    out = out.reset_index().rename(columns={"index": "period"})
    return out[INCOME_COLUMNS].sort_values("period").reset_index(drop=True)


def income_totals(income: pd.DataFrame) -> dict[str, float]:
    """Sum every income-statement line over all periods."""
    if income.empty:
        return {key: 0.0 for key in TOTAL_KEYS}
    return {key: float(income[key].sum()) for key in TOTAL_KEYS}


def _breakdown(
    journal: pd.DataFrame,
    coa: pd.DataFrame,
    account_type: str,
    start: DateLike,
    end: DateLike,
) -> pd.DataFrame:
    df = with_account_info(journal, coa)
    df = df[df["account_type"] == account_type]
    df = filter_dates(df, start, end)
    columns = ["account_code", "account_name", "subtype", "amount"]
    if df.empty:
        return pd.DataFrame(columns=columns)
    out = (
        df.groupby(["account_code", "account_name", "subtype"], as_index=False)["natural_amount"]
        .sum()
        .rename(columns={"natural_amount": "amount"})
    )
    out = out[out["amount"] != 0]
    return out.sort_values("amount", ascending=False).reset_index(drop=True)[columns]


def expense_breakdown(
    journal: pd.DataFrame, coa: pd.DataFrame, start: DateLike = None, end: DateLike = None
) -> pd.DataFrame:
    """Total expense per account for the period, largest first."""
    return _breakdown(journal, coa, "Expense", start, end)


def revenue_breakdown(
    journal: pd.DataFrame, coa: pd.DataFrame, start: DateLike = None, end: DateLike = None
) -> pd.DataFrame:
    """Total revenue per account for the period, largest first."""
    return _breakdown(journal, coa, "Revenue", start, end)


def cash_trend(
    journal: pd.DataFrame, coa: pd.DataFrame, start: DateLike = None, end: DateLike = None
) -> pd.DataFrame:
    """Monthly net cash movement and closing cash balance.

    The closing balance is always cumulative from the first journal line, so it stays
    correct when the view is restricted to a sub-period.
    """
    columns = ["period", "net_change", "closing_balance"]
    df = with_account_info(journal, coa)
    cash = filter_dates(df[df["subtype"] == config.SUBTYPE_CASH], None, end)
    if cash.empty:
        return pd.DataFrame(columns=columns)
    monthly = cash.groupby("period")["amount"].sum().sort_index()
    out = pd.DataFrame(
        {
            "period": monthly.index,
            "net_change": monthly.to_numpy(),
            "closing_balance": monthly.cumsum().to_numpy(),
        }
    )
    if start is not None:
        first_month = to_timestamp(start).strftime("%Y-%m")
        out = out[out["period"] >= first_month]
    return out[columns].reset_index(drop=True)


@dataclass(frozen=True)
class BalanceSheet:
    """Balance sheet at a single date. Equity includes cumulative profit or loss."""

    as_of: pd.Timestamp
    balances: pd.DataFrame
    total_assets: float
    total_liabilities: float
    share_capital: float
    current_earnings: float
    current_assets: float
    current_liabilities: float
    cash: float
    receivables: float

    @property
    def total_equity(self) -> float:
        return self.share_capital + self.current_earnings

    @property
    def difference(self) -> float:
        """Assets minus (liabilities + equity); zero for a consistent ledger."""
        return self.total_assets - (self.total_liabilities + self.total_equity)

    def is_balanced(self, tolerance: float = config.BALANCE_TOLERANCE) -> bool:
        return abs(self.difference) <= tolerance


def balance_sheet(journal: pd.DataFrame, coa: pd.DataFrame, as_of: DateLike) -> BalanceSheet:
    """Build the balance sheet as of *as_of* (cumulative from inception)."""
    as_of_ts = pd.Timestamp(as_of)
    bal = balances_as_of(journal, coa, as_of_ts)
    by_type = bal.groupby("account_type")["natural_balance"].sum()
    by_subtype = bal.groupby("subtype")["natural_balance"].sum()

    revenue = float(by_type.get("Revenue", 0.0))
    expenses = float(by_type.get("Expense", 0.0))
    current_assets = float(
        bal[(bal["account_type"] == "Asset") & bal["subtype"].isin(config.CURRENT_ASSET_SUBTYPES)][
            "natural_balance"
        ].sum()
    )
    return BalanceSheet(
        as_of=as_of_ts,
        balances=bal,
        total_assets=float(by_type.get("Asset", 0.0)),
        total_liabilities=float(by_type.get("Liability", 0.0)),
        share_capital=float(by_type.get("Equity", 0.0)),
        current_earnings=revenue - expenses,
        current_assets=current_assets,
        current_liabilities=float(by_subtype.get(config.SUBTYPE_CURRENT_LIABILITY, 0.0)),
        cash=float(by_subtype.get(config.SUBTYPE_CASH, 0.0)),
        receivables=float(by_subtype.get(config.SUBTYPE_RECEIVABLES, 0.0)),
    )
