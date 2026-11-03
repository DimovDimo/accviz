"""Unit tests for accounts payable aging and control reconciliations (I-2)."""

from __future__ import annotations

import pandas as pd
import pytest

from accviz import config
from accviz.loader import normalize_supplier_invoices
from accviz.payables import PAYABLE_AGING_COLUMNS, payables_aging, payables_summary, top_suppliers, total_payable
from accviz.reconciliation import Reconciliation, reconcile, reconciliation_table

pytestmark = pytest.mark.unit


def _supplier_frame(rows):
    raw = pd.DataFrame(
        rows, columns=["invoice_id", "supplier", "issue_date", "due_date", "amount", "paid_date", "paid_amount"]
    ).astype(str)
    return normalize_supplier_invoices(raw)


@pytest.fixture
def suppliers():
    return _supplier_frame(
        [
            ("S1", "Alpha", "2025-01-10", "2025-02-09", "1000", "2025-02-01", "1000"),  # paid
            ("S2", "Beta", "2025-01-20", "2025-02-19", "400", "", "0"),  # open, 30 days overdue at 2025-03-21
            ("S3", "Alpha", "2025-03-01", "2025-03-31", "250", "", "0"),  # open, not yet due at 2025-03-21
            ("S4", "Gamma", "2025-03-05", "2025-04-04", "600", "2025-04-10", "600"),  # paid after as-of
            ("S5", "Beta", "2025-03-15", "2025-04-14", "300", "", "0"),  # open, not yet due
        ]
    )


def test_aging_includes_only_open_invoices_at_the_as_of_date(suppliers):
    aging = payables_aging(suppliers, "2025-03-21")
    assert list(aging.columns) == PAYABLE_AGING_COLUMNS
    assert set(aging["invoice_id"]) == {"S2", "S3", "S4", "S5"}
    s4 = aging[aging["invoice_id"] == "S4"].iloc[0]
    assert s4["outstanding"] == 600  # the payment came after the as-of date
    assert "customer" not in aging.columns


def test_buckets_and_totals(suppliers):
    aging = payables_aging(suppliers, "2025-03-21")
    summary = payables_summary(aging)
    assert list(summary["bucket"]) == list(config.AGING_BUCKETS)
    by_bucket = dict(zip(summary["bucket"], summary["outstanding"]))
    assert by_bucket["Not yet due"] == pytest.approx(250 + 600 + 300)  # S3, S4, S5 are not yet due
    assert by_bucket["1-30 days"] == pytest.approx(400)  # S2 is 30 days overdue
    assert total_payable(aging) == pytest.approx(1550)


def test_top_suppliers_are_ranked_by_balance(suppliers):
    aging = payables_aging(suppliers, "2025-03-21")
    top = top_suppliers(aging, 2)
    assert list(top["supplier"]) == ["Beta", "Gamma"]  # Beta: 400 + 300; Gamma: 600 (paid after the as-of date)
    assert top["outstanding"].tolist() == [700, 600]


def test_empty_inputs_give_empty_results():
    empty = normalize_supplier_invoices(pd.DataFrame(columns=["invoice_id", "supplier", "issue_date", "due_date", "amount"]))
    aging = payables_aging(empty, "2025-03-21")
    assert aging.empty and list(aging.columns) == PAYABLE_AGING_COLUMNS
    summary = payables_summary(aging)
    assert summary["outstanding"].sum() == 0
    assert top_suppliers(aging).empty
    assert total_payable(aging) == 0


def test_reconciliation_difference_and_status():
    item = Reconciliation("Accounts payable", "2000", gl_balance=1050.0, subledger_balance=1000.0)
    assert item.difference == 50
    assert not item.is_reconciled()
    table = reconciliation_table([item, Reconciliation("Accounts receivable", "1100", 10.0, 10.004)])
    assert table["status"].tolist() == ["difference", "reconciled"]
    assert reconciliation_table([]).empty


def test_reconcile_reads_gl_balances_of_control_accounts(tiny_dataset):
    items = reconcile(
        tiny_dataset.journal,
        tiny_dataset.chart_of_accounts,
        "2025-02-28",
        receivables_total=300.0,
        payables_total=40.0,
    )
    by_code = {i.account_code: i for i in items}
    assert by_code["1100"].gl_balance == 300  # invoice INV-2 is still open
    assert by_code["2000"].gl_balance == 0  # the tiny company has no supplier invoices
    assert all(i.is_reconciled() is (abs(i.gl_balance - i.subledger_balance) < 0.01) for i in items)
    assert by_code["2000"].subledger_balance == 40.0
    assert not by_code["2000"].is_reconciled()
