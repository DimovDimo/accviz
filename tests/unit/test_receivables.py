"""Unit tests for accounts-receivable aging."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from accviz import config
from accviz.receivables import (
    AGING_COLUMNS,
    aging_schedule,
    aging_summary,
    bucket_for_days,
    top_customers,
    total_outstanding,
)


@pytest.fixture
def invoices() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "invoice_id": ["INV-1", "INV-2", "INV-3"],
            "customer": ["Alpha", "Beta", "Gamma"],
            "issue_date": pd.to_datetime(["2025-01-10", "2025-02-10", "2025-01-05"]),
            "due_date": pd.to_datetime(["2025-02-09", "2025-03-12", "2025-01-20"]),
            "amount": [500.0, 300.0, 200.0],
            "paid_date": pd.to_datetime(["2025-02-03", None, "2025-01-25"]),
            "paid_amount": [500.0, 0.0, 50.0],
        }
    )


def test_fully_paid_invoices_are_excluded_and_partial_payments_reduce_balance(invoices):
    aging = aging_schedule(invoices, "2025-03-31")
    assert set(aging["invoice_id"]) == {"INV-2", "INV-3"}
    gamma = aging.set_index("invoice_id").loc["INV-3"]
    assert gamma.outstanding == pytest.approx(150)
    assert gamma.days_overdue == 70
    assert gamma.bucket == "61-90 days"


def test_invoice_not_yet_due_is_in_first_bucket_at_earlier_date(invoices):
    aging = aging_schedule(invoices, "2025-02-01").set_index("invoice_id")
    # INV-1 was paid on 3 Feb, which is after 1 Feb, so it is still open and not yet due.
    assert aging.loc["INV-1", "outstanding"] == pytest.approx(500)
    assert aging.loc["INV-1", "bucket"] == "Not yet due"
    assert aging.loc["INV-3", "bucket"] == "1-30 days"
    assert "INV-2" not in aging.index  # issued after the reporting date


def test_summary_totals_per_bucket_and_shares(invoices):
    summary = aging_summary(aging_schedule(invoices, "2025-03-31")).set_index("bucket")
    assert summary.loc["1-30 days", "outstanding"] == pytest.approx(300)
    assert summary.loc["61-90 days", "outstanding"] == pytest.approx(150)
    assert summary.loc["Not yet due", "outstanding"] == 0
    assert summary["share"].sum() == pytest.approx(1.0)
    assert list(summary.index) == list(config.AGING_BUCKETS)


def test_summary_of_empty_schedule_has_all_buckets_at_zero():
    summary = aging_summary(pd.DataFrame(columns=AGING_COLUMNS))
    assert len(summary) == len(config.AGING_BUCKETS)
    assert (summary["outstanding"] == 0).all()
    assert (summary["share"] == 0).all()


def test_schedule_with_no_open_items_is_empty(invoices):
    fully_paid = invoices.assign(paid_amount=invoices["amount"], paid_date=pd.Timestamp("2025-01-31"))
    assert aging_schedule(fully_paid, "2025-03-31").empty


@pytest.mark.parametrize(
    ("days", "bucket"),
    [
        (-5, "Not yet due"),
        (0, "Not yet due"),
        (1, "1-30 days"),
        (30, "1-30 days"),
        (31, "31-60 days"),
        (60, "31-60 days"),
        (61, "61-90 days"),
        (90, "61-90 days"),
        (91, "90+ days"),
        (365, "90+ days"),
    ],
)
def test_bucket_boundaries(days, bucket):
    assert list(bucket_for_days([days])) == [bucket]


def test_bucket_for_days_handles_arrays():
    result = list(bucket_for_days(np.array([0.0, 45.0, 120.0])))
    assert result == ["Not yet due", "31-60 days", "90+ days"]


def test_top_customers_sorted_by_outstanding(invoices):
    aging = aging_schedule(invoices, "2025-03-31")
    top = top_customers(aging, n=1)
    assert top["customer"].tolist() == ["Beta"]
    assert top["outstanding"].iloc[0] == pytest.approx(300)


def test_top_customers_of_empty_schedule_is_empty():
    assert top_customers(pd.DataFrame(columns=AGING_COLUMNS)).empty


def test_total_outstanding(invoices):
    assert total_outstanding(aging_schedule(invoices, "2025-03-31")) == pytest.approx(450)
    assert total_outstanding(pd.DataFrame(columns=AGING_COLUMNS)) == 0.0
