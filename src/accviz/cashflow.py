"""Direct-method cash flow statement, reconciled to the general-ledger cash balance.

Classification (by the counterpart line of each entry that moves cash):

* fixed-asset accounts → **investing**
* long-term liabilities and equity → **financing**
* everything else → **operating**

Entries whose description contains "opening balance" (case-insensitive) are the opening
position. They are not flows: their cash is the opening cash of the period.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from accviz import config
from accviz.ledger import DateLike, to_timestamp, with_account_info

SECTIONS: tuple[str, ...] = ("operating", "investing", "financing")
SECTION_LABELS: dict[str, str] = {
    "operating": "Operating activities",
    "investing": "Investing activities",
    "financing": "Financing activities",
}

MONTHLY_COLUMNS = [
    "period",
    "opening_cash",
    "operating",
    "investing",
    "financing",
    "net_change",
    "closing_cash",
    "gl_closing_cash",
    "difference",
]


@dataclass(frozen=True)
class CashFlowStatement:
    """Cash flow for [start, end]. ``difference`` must be zero for a consistent ledger."""

    start: pd.Timestamp
    end: pd.Timestamp
    opening_cash: float
    sections: dict[str, float]
    gl_closing_cash: float
    lines: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["section", "account_code", "account_name", "amount"]))

    @property
    def operating(self) -> float:
        return self.sections["operating"]

    @property
    def investing(self) -> float:
        return self.sections["investing"]

    @property
    def financing(self) -> float:
        return self.sections["financing"]

    @property
    def net_change(self) -> float:
        return sum(self.sections.values())

    @property
    def closing_cash(self) -> float:
        return self.opening_cash + self.net_change

    @property
    def difference(self) -> float:
        return self.closing_cash - self.gl_closing_cash

    def is_reconciled(self, tolerance: float = config.BALANCE_TOLERANCE) -> bool:
        return abs(self.difference) <= tolerance


def _cash_lines(journal: pd.DataFrame, coa: pd.DataFrame) -> pd.DataFrame:
    """Lines of every entry that touches cash, with section and flow sign.

    ``amount`` is ``debit - credit``. ``flow`` is the cash effect of a non-cash line,
    ``-(debit - credit)``; cash lines have flow 0 because they are the cash balance itself.
    """
    df = with_account_info(journal, coa)
    is_opening_line = df["description"].str.contains(config.OPENING_BALANCE_MARKER, case=False, na=False)
    opening_entries = set(df.loc[is_opening_line, "entry_id"])
    cash_entries = set(df.loc[df["subtype"] == config.SUBTYPE_CASH, "entry_id"])
    df = df[df["entry_id"].isin(cash_entries)].copy()
    df["is_opening"] = df["entry_id"].isin(opening_entries)
    df["is_cash"] = df["subtype"] == config.SUBTYPE_CASH
    # A flow belongs to the date of its entry's cash line, so an entry dated across two months
    # does not split its cash effect from the cash balance it moves.
    entry_cash_date = df.loc[df["is_cash"]].groupby("entry_id")["date"].min()
    df["flow_date"] = df["entry_id"].map(entry_cash_date)
    df["flow_period"] = df["flow_date"].dt.strftime("%Y-%m")
    investing = df["subtype"] == config.SUBTYPE_FIXED_ASSET
    financing = (df["subtype"] == config.SUBTYPE_LONG_TERM_LIABILITY) | (df["account_type"] == "Equity")
    df["section"] = np.select([investing, financing], ["investing", "financing"], default="operating")
    df["flow"] = np.where(df["is_cash"], 0.0, -df["amount"])
    return df


def cash_flow_statement(
    journal: pd.DataFrame, coa: pd.DataFrame, start: DateLike = None, end: DateLike = None
) -> CashFlowStatement:
    """Direct-method statement for [start, end] (defaults: the whole journal)."""
    start_ts = to_timestamp(start) if start is not None else journal["date"].min()
    end_ts = to_timestamp(end) if end is not None else journal["date"].max()
    cl = _cash_lines(journal, coa)
    cash = cl[cl["is_cash"]]

    opening_mask = cash["is_opening"] | (cash["date"] < start_ts)
    opening_cash = float(cash.loc[opening_mask, "amount"].sum())
    gl_closing = float(cash.loc[cash["is_opening"] | (cash["date"] <= end_ts), "amount"].sum())

    flows = cl[~cl["is_cash"] & ~cl["is_opening"] & (cl["flow_date"] >= start_ts) & (cl["flow_date"] <= end_ts)]
    by_section = flows.groupby("section")["flow"].sum()
    sections = {key: float(by_section.get(key, 0.0)) for key in SECTIONS}

    lines = (
        flows.groupby(["section", "account_code", "account_name"], as_index=False)["flow"]
        .sum()
        .rename(columns={"flow": "amount"})
    )
    lines = lines[lines["amount"].abs() > 0].reset_index(drop=True)
    return CashFlowStatement(
        start=start_ts,
        end=end_ts,
        opening_cash=opening_cash,
        sections=sections,
        gl_closing_cash=gl_closing,
        lines=lines,
    )


def monthly_cash_flow(
    journal: pd.DataFrame, coa: pd.DataFrame, start: DateLike = None, end: DateLike = None
) -> pd.DataFrame:
    """One row per calendar month in [start, end], with sections and a GL reconciliation.

    ``opening_cash`` is the GL cash balance before the month, plus any opening-balance
    cash dated in the month. ``difference`` compares the closing cash with the GL closing
    cash for the month and must be zero.
    """
    cl = _cash_lines(journal, coa)
    if cl.empty:
        return pd.DataFrame(columns=MONTHLY_COLUMNS)
    start_ts = to_timestamp(start) if start is not None else journal["date"].min()
    end_ts = to_timestamp(end) if end is not None else journal["date"].max()

    cash = cl[cl["is_cash"]]
    first = min(cash["period"].min(), start_ts.strftime("%Y-%m"))
    last = max(cash["period"].max(), end_ts.strftime("%Y-%m"))
    months = pd.period_range(first, last, freq="M").strftime("%Y-%m")

    gl_month = cash.groupby("period")["amount"].sum().reindex(months, fill_value=0.0)
    gl_cum = gl_month.cumsum()
    gl_before = gl_cum.shift(1, fill_value=0.0)
    opening_adj = cash[cash["is_opening"]].groupby("period")["amount"].sum().reindex(months, fill_value=0.0)

    flows = cl[~cl["is_cash"] & ~cl["is_opening"]]
    section_month = flows.pivot_table(index="flow_period", columns="section", values="flow", aggfunc="sum")
    section_month = section_month.reindex(index=months, columns=list(SECTIONS), fill_value=0.0).fillna(0.0)

    out = pd.DataFrame({"period": months})
    out["opening_cash"] = (gl_before + opening_adj).to_numpy()
    for key in SECTIONS:
        out[key] = section_month[key].to_numpy()
    out["net_change"] = out[list(SECTIONS)].sum(axis=1)
    out["closing_cash"] = out["opening_cash"] + out["net_change"]
    out["gl_closing_cash"] = gl_cum.to_numpy()
    out["difference"] = out["closing_cash"] - out["gl_closing_cash"]
    window = out[(out["period"] >= start_ts.strftime("%Y-%m")) & (out["period"] <= end_ts.strftime("%Y-%m"))]
    return window[MONTHLY_COLUMNS].reset_index(drop=True)
