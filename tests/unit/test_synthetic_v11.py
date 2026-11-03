"""Unit tests for the v1.1 generator features: supplier invoices, source tags and anomalies."""

from __future__ import annotations

import pandas as pd
import pytest

from accviz import config
from accviz.synthetic import ANOMALY_COUNTS, CSV_COLUMNS, GeneratorConfig, generate_dataset, write_dataset

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def raw():
    return generate_dataset(GeneratorConfig(seed=21, months=24))


@pytest.fixture(scope="module")
def raw_anomalies():
    return generate_dataset(GeneratorConfig(seed=21, months=24, anomalies=True))


def test_supplier_invoices_per_month_within_configured_range(raw):
    counts = raw["supplier_invoices"].groupby(raw["supplier_invoices"]["issue_date"].str[:7]).size()
    assert counts.min() >= 3
    assert counts.max() <= 6
    assert len(counts) == 24


def test_supplier_invoices_replace_the_monthly_purchase_lump(raw):
    s = raw["supplier_invoices"]
    j = raw["journal"]
    stock = j[(j["account_code"] == "5000")].copy()
    stock["month"] = stock["date"].str[:7]
    monthly_gl = stock.groupby("month")["debit"].sum()
    monthly_sub = s.groupby(s["issue_date"].str[:7])["amount"].sum()
    assert (monthly_gl - monthly_sub).abs().max() < 0.01


def test_ap_control_account_equals_open_supplier_invoices(raw):
    j = raw["journal"]
    s = raw["supplier_invoices"]
    gl_ap = float((j.loc[j["account_code"] == "2000", "credit"] - j.loc[j["account_code"] == "2000", "debit"]).sum())
    open_amount = float(s.loc[s["paid_date"] == "", "amount"].astype(float).sum())
    assert gl_ap == pytest.approx(open_amount, abs=0.01)


def test_supplier_payment_terms_and_timing(raw):
    s = raw["supplier_invoices"].copy()
    issue = pd.to_datetime(s["issue_date"])
    due = pd.to_datetime(s["due_date"])
    assert set(((due - issue).dt.days).unique()) <= {30, 45, 60}
    paid = s[s["paid_date"] != ""]
    delay = (pd.to_datetime(paid["paid_date"]) - pd.to_datetime(paid["issue_date"])).dt.days
    assert delay.min() >= 20 and delay.max() <= 70


def test_source_column_marks_manual_postings(raw):
    j = raw["journal"]
    manual = set(j.loc[j["source"] == "manual", "description"].str.split(" ").str[0])
    assert {"Depreciation", "Loan", "Income", "Opening"} <= manual
    assert set(j["source"]) == {"system", "manual"}
    system_only = j.loc[j["source"] == "system", "description"]
    assert not system_only.str.startswith("Depreciation").any()
    assert not system_only.str.startswith("Loan interest").any()


def test_manual_postings_are_made_on_business_days(raw):
    j = raw["journal"]
    manual = j[(j["source"] == "manual") & (~j["description"].str.startswith("Opening"))]
    assert not pd.to_datetime(manual["date"]).dt.dayofweek.isin([5, 6]).any()


def test_journal_columns_include_source(raw):
    assert list(raw["journal"].columns) == CSV_COLUMNS["journal"]
    assert "source" in raw["journal"].columns


def test_no_ground_truth_without_anomalies(raw):
    assert config.GROUND_TRUTH_KEY not in raw


def test_anomalies_add_nine_known_entries(raw_anomalies):
    truth = raw_anomalies[config.GROUND_TRUTH_KEY]
    assert len(truth) == sum(ANOMALY_COUNTS.values()) == 9
    assert truth["anomaly_type"].value_counts().to_dict() == ANOMALY_COUNTS
    assert set(truth["entry_id"]) <= set(raw_anomalies["journal"]["entry_id"])
    assert list(truth.columns) == CSV_COLUMNS["ground_truth"]


def test_anomaly_amounts_and_timing_follow_their_rules(raw_anomalies):
    j = raw_anomalies["journal"]
    truth = raw_anomalies[config.GROUND_TRUTH_KEY]
    dates = j.groupby("entry_id")["date"].first()
    for _, row in truth.iterrows():
        entry = j[j["entry_id"] == row["entry_id"]]
        date = pd.Timestamp(dates[row["entry_id"]])
        kind = row["anomaly_type"]
        if kind == "weekend_manual":
            assert date.dayofweek >= 5
            assert (entry["source"] == "manual").all()
        if kind == "threshold_manual":
            amount = entry["debit"].max()
            assert 4750 <= amount < 5000
            assert (entry["source"] == "manual").all()
        if kind == "round_amount":
            amount = entry["debit"].max()
            assert amount >= 5000 and amount % 1000 == 0
        if kind == "outlier_expense":
            assert entry["debit"].max() > 9000


def test_duplicate_postings_mirror_an_original_supplier_invoice(raw_anomalies):
    j = raw_anomalies["journal"]
    s = raw_anomalies["supplier_invoices"]
    truth = raw_anomalies[config.GROUND_TRUTH_KEY]
    dup_ids = truth.loc[truth["anomaly_type"] == "duplicate_posting", "entry_id"]
    for entry_id in dup_ids:
        entry = j[j["entry_id"] == entry_id]
        reference = entry["reference"].iloc[0]
        assert reference in set(s["invoice_id"])  # same reference as the original
        amount = float(entry.loc[entry["account_code"] == "5000", "debit"].iloc[0])
        assert amount == pytest.approx(float(s.loc[s["invoice_id"] == reference, "amount"].iloc[0]))


def test_ap_difference_equals_the_duplicate_amounts(raw_anomalies):
    j = raw_anomalies["journal"]
    truth = raw_anomalies[config.GROUND_TRUTH_KEY]
    gl_ap = float((j.loc[j["account_code"] == "2000", "credit"] - j.loc[j["account_code"] == "2000", "debit"]).sum())
    s = raw_anomalies["supplier_invoices"]
    sub_open = float(s.loc[s["paid_date"] == "", "amount"].astype(float).sum())
    dup_ids = set(truth.loc[truth["anomaly_type"] == "duplicate_posting", "entry_id"])
    dup_total = float(j.loc[(j["entry_id"].isin(dup_ids)) & (j["account_code"] == "2000"), "credit"].sum())
    assert gl_ap - sub_open == pytest.approx(dup_total, abs=0.01)


def test_generation_is_deterministic(raw):
    again = generate_dataset(GeneratorConfig(seed=21, months=24))
    pd.testing.assert_frame_equal(raw["journal"], again["journal"])
    pd.testing.assert_frame_equal(raw["supplier_invoices"], again["supplier_invoices"])


@pytest.mark.parametrize("overrides", [{"supplier_invoices_min": 0}, {"supplier_invoices_max": 1, "supplier_invoices_min": 3}])
def test_invalid_supplier_invoice_range_is_rejected(overrides):
    with pytest.raises(ValueError):
        GeneratorConfig(**overrides)


def test_write_dataset_writes_optional_files(tmp_path, raw_anomalies):
    paths = write_dataset(raw_anomalies, tmp_path)
    assert (tmp_path / "supplier_invoices.csv").exists()
    assert (tmp_path / "anomaly_ground_truth.csv").exists()
    assert set(paths) == set(raw_anomalies)
