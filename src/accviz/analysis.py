"""Single entry point that bundles every analytic result for a period.

Dashboard, report and CLI all call :func:`analyze`, so they always agree on the numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from accviz import audit as audit_mod
from accviz import budget as budget_mod
from accviz import cashflow, departments, forecast, ledger, payables, ratios, receivables, reconciliation, statements
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
    # v1.1 additions (appended, so existing fields keep their positions)
    cash_flow: cashflow.CashFlowStatement | None = None
    cash_flow_monthly: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=cashflow.MONTHLY_COLUMNS))
    ap_aging: pd.DataFrame = field(default_factory=pd.DataFrame)
    ap_summary: pd.DataFrame = field(default_factory=pd.DataFrame)
    top_suppliers: pd.DataFrame = field(default_factory=pd.DataFrame)
    reconciliations: list = field(default_factory=list)
    reconciliation_table: pd.DataFrame = field(default_factory=pd.DataFrame)
    audit: audit_mod.AuditResult | None = None
    forecast: forecast.Forecast | None = None
    forecast_mape: float | None = None
    forecast_error: str | None = None
    departments_monthly: pd.DataFrame = field(default_factory=pd.DataFrame)
    departments_summary: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def period_label(self) -> str:
        return f"{self.start:%Y-%m-%d} to {self.end:%Y-%m-%d}"

    @property
    def net_cash_flow(self) -> float:
        return self.cash_flow.net_change if self.cash_flow is not None else 0.0


def _revenue_budget_variance_pct(budget_summary: pd.DataFrame) -> float | None:
    rev = budget_summary[budget_summary["account_type"] == "Revenue"]
    if rev.empty or rev["budget"].sum() == 0:
        return None
    return float((rev["actual"].sum() - rev["budget"].sum()) / rev["budget"].sum())


def analyze(dataset: Dataset, start=None, end=None, horizon: int = 6) -> AnalysisResult:
    """Compute all statements, schedules, ratios, KPIs and v1.1 analyses for [start, end].

    Missing bounds default to the first and last journal date. Balance-sheet, receivables,
    payables and reconciliation figures are measured at *end*. The revenue forecast uses
    all monthly revenue up to *end* and projects *horizon* months beyond it.
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

    cf_statement = cashflow.cash_flow_statement(journal, coa, start_ts, end_ts)
    cf_monthly = cashflow.monthly_cash_flow(journal, coa, start_ts, end_ts)

    ap = payables.payables_aging(dataset.supplier_invoices, end_ts)
    ap_sum = payables.payables_summary(ap)
    suppliers = payables.top_suppliers(ap)
    recs = reconciliation.reconcile(
        journal, coa, end_ts, outstanding, payables.total_payable(ap)
    )

    audit_result = audit_mod.run_audit(journal, coa, start_ts, end_ts)

    income_to_end = statements.income_statement(journal, coa, None, end_ts)
    revenue_hist = forecast.revenue_series(income_to_end)
    fc_model: forecast.Forecast | None = None
    fc_mape: float | None = None
    fc_error: str | None = None
    try:
        fc_model = forecast.fit_forecast(revenue_hist, horizon)
        fc_mape = forecast.backtest(revenue_hist)["mape"] if len(revenue_hist) >= 9 else None
    except ValueError as exc:
        fc_error = str(exc)

    dept_monthly = departments.expenses_by_department(journal, coa, start_ts, end_ts)
    dept_sum = departments.department_summary(dept_monthly)

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
        cash_flow=cf_statement,
        cash_flow_monthly=cf_monthly,
        ap_aging=ap,
        ap_summary=ap_sum,
        top_suppliers=suppliers,
        reconciliations=recs,
        reconciliation_table=reconciliation.reconciliation_table(recs),
        audit=audit_result,
        forecast=fc_model,
        forecast_mape=fc_mape,
        forecast_error=fc_error,
        departments_monthly=dept_monthly,
        departments_summary=dept_sum,
    )
