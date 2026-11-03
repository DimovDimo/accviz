"""Property-style tests: accounting invariants must hold for many random datasets.

Each generated dataset is a fresh random company (seed, growth, cost ratio, collection
behaviour, ...). The invariants are the rules a double-entry ledger must always obey.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from accviz import ledger
from accviz.analysis import analyze
from accviz.loader import prepare_dataset
from accviz.receivables import aging_schedule
from accviz.statements import balance_sheet, income_statement, income_totals
from accviz.synthetic import GeneratorConfig, generate_dataset


def random_configs(n: int, seed: int) -> list[GeneratorConfig]:
    """Draw *n* plausible but random company configurations, reproducibly."""
    rng = np.random.default_rng(seed)
    configs = []
    for _ in range(n):
        configs.append(
            GeneratorConfig(
                seed=int(rng.integers(1, 10_000)),
                start=f"{int(rng.integers(2022, 2026))}-{int(rng.integers(1, 13)):02d}-01",
                months=int(rng.integers(2, 9)),
                base_monthly_revenue=float(rng.uniform(20_000, 150_000)),
                monthly_growth=float(rng.uniform(-0.01, 0.03)),
                cogs_ratio=float(rng.uniform(0.2, 0.7)),
                payment_probability=float(rng.uniform(0.7, 1.0)),
                opening_cash=float(rng.uniform(50_000, 300_000)),
                opening_loan=float(rng.uniform(0, 100_000)),
            )
        )
    return configs


CONFIGS = [GeneratorConfig(seed=s, months=6) for s in (1, 2, 3, 4, 5)] + random_configs(6, seed=99)


@pytest.fixture(scope="module", params=range(len(CONFIGS)), ids=lambda i: f"config{i}")
def dataset_case(request):
    cfg = CONFIGS[request.param]
    ds, result = prepare_dataset(generate_dataset(cfg))
    assert ds is not None and result.ok, result.summary()
    return ds


def test_every_journal_entry_balances(dataset_case):
    sums = dataset_case.journal.groupby("entry_id")[["debit", "credit"]].sum()
    assert ((sums["debit"] - sums["credit"]).abs() < 0.01).all()


def test_trial_balance_balances(dataset_case):
    tb = ledger.trial_balance(dataset_case.journal, dataset_case.chart_of_accounts)
    assert tb["debit"].sum() == pytest.approx(tb["credit"].sum(), abs=0.01)


def test_accounting_equation_holds_at_every_month_end(dataset_case):
    coa, journal = dataset_case.chart_of_accounts, dataset_case.journal
    for day in pd.date_range(dataset_case.start_date, dataset_case.end_date, freq="ME"):
        assert balance_sheet(journal, coa, day).is_balanced(), day


def test_cumulative_net_income_equals_current_earnings(dataset_case):
    coa, journal = dataset_case.chart_of_accounts, dataset_case.journal
    end = dataset_case.end_date
    totals = income_totals(income_statement(journal, coa, end=end))
    bs = balance_sheet(journal, coa, end)
    assert bs.current_earnings == pytest.approx(totals["net_income"], abs=0.01)


def test_receivables_reconcile_with_control_account_at_end(dataset_case):
    coa, journal = dataset_case.chart_of_accounts, dataset_case.journal
    end = dataset_case.end_date
    gl = ledger.balances_as_of(journal, coa, end)
    gl_ar = float(gl.loc[gl.account_code == "1100", "natural_balance"].item())
    assert gl_ar == pytest.approx(aging_schedule(dataset_case.invoices, end)["outstanding"].sum(), abs=0.01)


def test_no_invoice_is_paid_more_than_it_is_worth(dataset_case):
    inv = dataset_case.invoices
    assert (inv["paid_amount"] <= inv["amount"] + 1e-9).all()
    assert (inv["paid_amount"] >= 0).all()


def test_analysis_totals_are_internally_consistent(dataset_case):
    result = analyze(dataset_case)
    t = result.income_totals
    assert t["gross_profit"] == pytest.approx(t["revenue"] - t["cost_of_sales"], abs=0.01)
    assert t["net_income"] == pytest.approx(
        t["revenue"] - t["cost_of_sales"] - t["operating_expenses"] - t["financial_expenses"] - t["tax_expense"],
        abs=0.01,
    )


def test_sub_period_income_never_exceeds_full_period_revenue(dataset_case):
    full = analyze(dataset_case).income_totals["revenue"]
    midpoint = dataset_case.start_date + (dataset_case.end_date - dataset_case.start_date) / 2
    part = analyze(dataset_case, end=midpoint).income_totals["revenue"]
    assert part <= full + 1e-6
