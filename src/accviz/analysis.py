"""Single entry point that bundles every analytic result for a period.

Dashboard, report and CLI all call :func:`analyze`, so they always agree on the numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from accviz import budget as budget_mod
from accviz import ledger, ratios, receivables, statements
from accviz.loader import Dataset
from accviz.statements import BalanceSheet


@dataclass(frozen=True)
class AnalysisResult:
    start: pd.Timestamp
    end: pd.Timestamp
    income_monthly: pd.DataFrame
    income_totals: dict[str, float]
    balance_sheet: BalanceSheet
    cash: pd.DataFrame
    revenues: pd.DataFrame
    expenses: pd.DataFrame
    aging: pd.DataFrame
    aging_summary: pd.DataFrame
    top_customers: pd.DataFrame
    budget_monthly: pd.DataFrame
    budget_summary: pd.DataFrame
    trial_balance: pd.DataFrame
    ratios: dict[str, float | None] = field(default_factory=dict)
    kpis: dict[str, float | None] = field(default_factory=dict)

    @property
    def period_label(self) -> str:
        return f"{self.start:%Y-%m-%d} to {self.end:%Y-%m-%d}"


def _revenue_budget_variance_pct(budget_summary: pd.DataFrame) -> float | None:
    rev = budget_summary[budget_summary["account_type"] == "Revenue"]
    if rev.empty or rev["budget"].sum() == 0:
        return None
    return float((rev["actual"].sum() - rev["budget"].sum()) / rev["budget"].sum())


def analyze(dataset: Dataset, start=None, end=None) -> AnalysisResult:
    """Compute all statements, schedules, ratios and KPIs for [start, end].

    Missing bounds default to the first and last journal date. Balance-sheet and
    receivables figures are measured at *end*.
    """
    start_ts = pd.Timestamp(start) if start is not None else dataset.start_date
    end_ts = pd.Timestamp(end) if end is not None else dataset.end_date
    if start_ts > end_ts:
        raise ValueError(f"start date {start_ts:%Y-%m-%d} is after end date {end_ts:%Y-%m-%d}")

    journal, coa = dataset.journal, dataset.chart_of_accounts

    income = statements.income_statement(journal, coa, start_ts, end_ts)
    totals = statements.income_totals(income)
    bs = statements.balance_sheet(journal, coa, end_ts)
    cash = statements.cash_trend(journal, coa, start_ts, end_ts)
    revenues = statements.revenue_breakdown(journal, coa, start_ts, end_ts)
    expenses = statements.expense_breakdown(journal, coa, start_ts, end_ts)
    tb = ledger.trial_balance(journal, coa, start_ts, end_ts)

    aging = receivables.aging_schedule(dataset.invoices, end_ts)
    aging_sum = receivables.aging_summary(aging)
    customers = receivables.top_customers(aging)
    outstanding = receivables.total_outstanding(aging)

    budget_monthly = budget_mod.budget_variance(journal, coa, dataset.budget, start_ts, end_ts)
    budget_sum = budget_mod.budget_summary(budget_monthly)

    ratio_values = ratios.financial_ratios(totals, bs)
    kpi_values = ratios.kpi_summary(totals, bs, outstanding, _revenue_budget_variance_pct(budget_sum))

    return AnalysisResult(
        start=start_ts,
        end=end_ts,
        income_monthly=income,
        income_totals=totals,
        balance_sheet=bs,
        cash=cash,
        revenues=revenues,
        expenses=expenses,
        aging=aging,
        aging_summary=aging_sum,
        top_customers=customers,
        budget_monthly=budget_monthly,
        budget_summary=budget_sum,
        trial_balance=tb,
        ratios=ratio_values,
        kpis=kpi_values,
    )
