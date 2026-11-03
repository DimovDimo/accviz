"""Property tests for the v1.1 features over many random companies.

The configurations are the same random companies used by ``test_invariants.py``, plus a
demo run with injected anomalies for every seed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from accviz import audit, cashflow, config, forecast, ledger, payables, receivables, statements
from accviz.analysis import analyze
from accviz.loader import prepare_dataset
from accviz.synthetic import GeneratorConfig, generate_dataset
from tests.property.test_invariants import CONFIGS

pytestmark = pytest.mark.property


@pytest.fixture(scope="module", params=range(len(CONFIGS)), ids=lambda i: f"config{i}")
def case(request):
    raw = generate_dataset(CONFIGS[request.param])
    ds, result = prepare_dataset(raw)
    assert ds is not None and result.ok, result.summary()
    return raw, ds


def test_cash_flow_reconciles_for_the_whole_period(case):
    _, ds = case
    stmt = cashflow.cash_flow_statement(ds.journal, ds.chart_of_accounts)
    assert stmt.difference == pytest.approx(0, abs=0.01)


def test_cash_flow_reconciles_at_every_month_end(case):
    _, ds = case
    monthly = cashflow.monthly_cash_flow(ds.journal, ds.chart_of_accounts)
    assert monthly["difference"].abs().max() < 0.01
    assert monthly["closing_cash"].iloc[-1] == pytest.approx(
        ledger.balances_as_of(ds.journal, ds.chart_of_accounts, ds.end_date).set_index("account_code").loc["1000", "natural_balance"],
        abs=0.01,
    )


def test_cash_flow_sections_sum_to_cash_movement_in_any_subperiod(case):
    _, ds = case
    mid = ds.start_date + (ds.end_date - ds.start_date) / 2
    stmt = cashflow.cash_flow_statement(ds.journal, ds.chart_of_accounts, mid, ds.end_date)
    assert stmt.is_reconciled()


def test_sub_ledgers_reconcile_to_control_accounts_without_anomalies(case):
    _, ds = case
    end = ds.end_date
    ar = receivables.aging_schedule(ds.invoices, end)
    ap = payables.payables_aging(ds.supplier_invoices, end)
    gl_ar = ledger.balances_as_of(ds.journal, ds.chart_of_accounts, end).set_index("account_code").loc["1100", "natural_balance"]
    gl_ap = ledger.balances_as_of(ds.journal, ds.chart_of_accounts, end).set_index("account_code").loc["2000", "natural_balance"]
    assert gl_ar == pytest.approx(receivables.total_outstanding(ar), abs=0.01)
    assert gl_ap == pytest.approx(payables.total_payable(ap), abs=0.01)


def test_supplier_invoices_equal_monthly_stock_postings(case):
    raw, _ = case
    s = raw["supplier_invoices"]
    j = raw["journal"]
    stock = j[j["account_code"] == "5000"]
    gl = stock.groupby(stock["date"].str[:7])["debit"].sum()
    sub = s.groupby(s["issue_date"].str[:7])["amount"].sum().astype(float)
    assert (gl - sub.reindex(gl.index).fillna(0)).abs().max() < 0.01


def test_audit_findings_stay_inside_the_period_and_are_deterministic(case):
    _, ds = case
    mid = ds.start_date + (ds.end_date - ds.start_date) / 3
    first = audit.run_audit(ds.journal, ds.chart_of_accounts, mid, ds.end_date)
    second = audit.run_audit(ds.journal, ds.chart_of_accounts, mid, ds.end_date)
    assert (first.findings["date"] >= mid).all() and (first.findings["date"] <= ds.end_date).all()
    pd.testing.assert_frame_equal(first.findings, second.findings)


def test_forecast_band_contains_the_point_forecast(case):
    _, ds = case
    income = statements.income_statement(ds.journal, ds.chart_of_accounts)
    revenue = forecast.revenue_series(income)
    if len(revenue) < forecast.MIN_HISTORY:
        pytest.skip("too little history")
    model = forecast.fit_forecast(revenue, 3)
    fut = model.future
    assert (fut["lower"] <= fut["value"] + 1e-9).all()
    assert (fut["value"] <= fut["upper"] + 1e-9).all()
    assert (fut["lower"] >= 0).all()


# ----------------------------------------------------------------- anomaly runs
@pytest.fixture(scope="module", params=[3, 11, 27], ids=lambda s: f"seed{s}")
def anomaly_case(request):
    raw = generate_dataset(GeneratorConfig(seed=request.param, months=24, anomalies=True))
    ds, result = prepare_dataset(raw)
    assert ds is not None and result.ok, result.summary()
    return raw, ds


def test_every_injected_anomaly_is_detected(anomaly_case):
    raw, ds = anomaly_case
    result = audit.run_audit(ds.journal, ds.chart_of_accounts)
    ev = audit.evaluate_against_truth(result.findings, raw[config.GROUND_TRUTH_KEY])
    assert ev["total"] == 1.0, ev["table"]


def test_ap_difference_equals_injected_duplicates(anomaly_case):
    raw, ds = anomaly_case
    end = ds.end_date
    truth = raw[config.GROUND_TRUTH_KEY]
    dup_ids = set(truth.loc[truth["anomaly_type"] == "duplicate_posting", "entry_id"])
    ap = payables.payables_aging(ds.supplier_invoices, end)
    gl_ap = ledger.balances_as_of(ds.journal, ds.chart_of_accounts, end).set_index("account_code").loc["2000", "natural_balance"]
    dup_total = ds.journal[(ds.journal["entry_id"].isin(dup_ids)) & (ds.journal["account_code"] == "2000")]["credit"].sum()
    assert gl_ap - payables.total_payable(ap) == pytest.approx(dup_total, abs=0.01)


def test_anomalies_do_not_break_the_accounting_equation(anomaly_case):
    _, ds = anomaly_case
    result = analyze(ds)
    assert result.balance_sheet.is_balanced()
    assert result.cash_flow.is_reconciled()


def test_random_seed_changes_the_data_but_not_the_rules():
    a = generate_dataset(GeneratorConfig(seed=1, months=6))["journal"]
    b = generate_dataset(GeneratorConfig(seed=2, months=6))["journal"]
    assert not a["debit"].equals(b["debit"])
    assert np.isclose(a["debit"].sum() - a["credit"].sum(), 0, atol=0.01)
