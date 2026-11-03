"""Integration tests for the v1.1 pipeline on the committed sample and demo datasets."""

from __future__ import annotations

import io

import pytest
from openpyxl import load_workbook

from accviz import audit, config, export
from accviz.analysis import analyze
from accviz.loader import read_dataset
from accviz.report import render_report

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sample():
    return read_dataset(config.DEFAULT_DATA_DIR)


@pytest.fixture(scope="module")
def demo():
    return read_dataset(config.DEMO_DATA_DIR)


@pytest.fixture(scope="module")
def sample_result(sample):
    return analyze(sample)


@pytest.fixture(scope="module")
def demo_result(demo):
    return analyze(demo)


def test_sample_contains_the_v11_inputs(sample):
    assert not sample.supplier_invoices.empty
    assert set(sample.journal["source"]) == {"system", "manual"}
    assert (config.DEFAULT_DATA_DIR / config.SUPPLIER_INVOICES_FILE).is_file()


def test_demo_dataset_has_ground_truth_and_matching_counts(demo):
    truth_path = config.DEMO_DATA_DIR / config.ANOMALY_GROUND_TRUTH_FILE
    assert truth_path.is_file()
    import pandas as pd

    truth = pd.read_csv(truth_path, dtype=str)
    assert len(truth) == 9
    assert set(truth["entry_id"]) <= set(demo.journal["entry_id"])


def test_sample_cash_flow_reconciles_to_gl_cash(sample_result):
    cf = sample_result.cash_flow
    assert cf.is_reconciled()
    assert cf.closing_cash == pytest.approx(sample_result.kpis["closing_cash"], abs=0.01)
    assert sample_result.cash_flow_monthly["difference"].abs().max() < 0.01


def test_sample_control_accounts_reconcile(sample_result):
    for rec in sample_result.reconciliations:
        assert rec.is_reconciled(), (rec.control, rec.difference)


def test_sample_audit_flags_only_large_cost_of_sales_invoices(sample_result):
    # Documented in the README: the two findings are large supplier invoices on cost of sales.
    findings = sample_result.audit.findings
    assert set(findings["rule"]) <= {"outlier_expense"}
    assert set(findings["account_code"]) <= {"5000"}
    assert len(findings) <= 2


def test_demo_audit_detects_every_injected_anomaly(demo, demo_result):
    import pandas as pd

    truth = pd.read_csv(config.DEMO_DATA_DIR / config.ANOMALY_GROUND_TRUTH_FILE, dtype=str, keep_default_na=False)
    ev = audit.evaluate_against_truth(demo_result.audit.findings, truth)
    assert ev["total"] == 1.0
    assert ev["table"]["detected"].tolist() == ev["table"]["injected"].tolist()


def test_demo_ap_difference_equals_duplicate_postings(demo, demo_result):
    import pandas as pd

    truth = pd.read_csv(config.DEMO_DATA_DIR / config.ANOMALY_GROUND_TRUTH_FILE, dtype=str, keep_default_na=False)
    ap_rec = next(r for r in demo_result.reconciliations if r.account_code == "2000")
    dup_ids = set(truth.loc[truth["anomaly_type"] == "duplicate_posting", "entry_id"])
    dup_total = demo.journal[demo.journal["entry_id"].isin(dup_ids) & (demo.journal["account_code"] == "2000")][
        "credit"
    ].sum()
    assert ap_rec.difference == pytest.approx(dup_total, abs=0.01)
    assert not ap_rec.is_reconciled()
    ar_rec = next(r for r in demo_result.reconciliations if r.account_code == "1100")
    assert ar_rec.is_reconciled()


def test_sample_forecast_is_seasonal_and_within_the_accuracy_target(sample_result):
    assert sample_result.forecast is not None
    assert sample_result.forecast.seasonal
    assert sample_result.forecast_mape is not None
    assert sample_result.forecast_mape < 0.08  # planned acceptance target (holdout MAPE)


def test_departments_cover_all_expenses(sample_result):
    total_expense = sample_result.expenses["amount"].sum()
    assert sample_result.departments_monthly["amount"].sum() == pytest.approx(total_expense, abs=0.01)
    assert sample_result.departments_summary["share"].sum() == pytest.approx(1.0)


def test_workbook_from_full_analysis_has_all_sheets(sample_result):
    wb = load_workbook(io.BytesIO(export.workbook_bytes(sample_result)))
    assert len(wb.sheetnames) == 11


def test_report_contains_the_v11_sections(sample):
    html = render_report(sample)
    for heading in (
        "Cash flow statement (direct method)",
        "Payables aging and reconciliation",
        "Revenue forecast",
        "Cost centres (expenses by department)",
        "Journal audit analytics",
    ):
        assert heading in html
    assert html.count('class="plotly-graph-div"') == 13
