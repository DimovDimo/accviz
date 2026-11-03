"""Control-account reconciliations: sub-ledgers (AR and AP) against the general ledger.

A consistent ledger has a difference of zero. A non-zero difference points to postings
that bypass the sub-ledger, such as the duplicate postings in the demo dataset.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from accviz import config
from accviz.ledger import DateLike, balances_as_of

RECONCILIATION_COLUMNS = ["control", "account_code", "gl_balance", "subledger_balance", "difference", "status"]


@dataclass(frozen=True)
class Reconciliation:
    """GL control balance compared with the total of its sub-ledger at one date."""

    control: str
    account_code: str
    gl_balance: float
    subledger_balance: float

    @property
    def difference(self) -> float:
        return self.gl_balance - self.subledger_balance

    def is_reconciled(self, tolerance: float = config.BALANCE_TOLERANCE) -> bool:
        return abs(self.difference) <= tolerance


def gl_balance(journal: pd.DataFrame, coa: pd.DataFrame, account_code: str, as_of: DateLike) -> float:
    """Natural-sign balance of one account at *as_of* (zero if the account is unknown)."""
    bal = balances_as_of(journal, coa, as_of)
    row = bal.loc[bal["account_code"] == account_code, "natural_balance"]
    return float(row.iloc[0]) if not row.empty else 0.0


def reconcile(
    journal: pd.DataFrame,
    coa: pd.DataFrame,
    as_of: DateLike,
    receivables_total: float,
    payables_total: float,
) -> list[Reconciliation]:
    """Reconcile accounts receivable (1100) and accounts payable (2000) at *as_of*."""
    return [
        Reconciliation(
            "Accounts receivable",
            "1100",
            gl_balance(journal, coa, "1100", as_of),
            float(receivables_total),
        ),
        Reconciliation(
            "Accounts payable",
            "2000",
            gl_balance(journal, coa, "2000", as_of),
            float(payables_total),
        ),
    ]


def reconciliation_table(items: list[Reconciliation]) -> pd.DataFrame:
    """Printable table with one row per control account."""
    if not items:
        return pd.DataFrame(columns=RECONCILIATION_COLUMNS)
    rows = [
        {
            "control": item.control,
            "account_code": item.account_code,
            "gl_balance": item.gl_balance,
            "subledger_balance": item.subledger_balance,
            "difference": item.difference,
            "status": "reconciled" if item.is_reconciled() else "difference",
        }
        for item in items
    ]
    return pd.DataFrame(rows, columns=RECONCILIATION_COLUMNS)
