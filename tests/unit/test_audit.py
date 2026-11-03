"""Unit tests for journal audit rules, the Benford test and ground-truth scoring (I-3)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from accviz import audit
from accviz.audit import (
    RULES,
    benford_test,
    evaluate_against_truth,
    first_digit,
    rule_summary,
    run_audit,
)

pytestmark = pytest.mark.unit


def _journal(entries):
    """entries: list of (entry_id, date, source, description, [(account, debit, credit), ...])."""
    rows = []
    for entry_id, date, source, description, lines in entries:
        for account, debit, credit in lines:
            rows.append(
                {
                    "entry_id": entry_id,
                    "date": pd.Timestamp(date),
                    "account_code": account,
                    "description": description,
                    "debit": float(debit),
                    "credit": float(credit),
                    "department": "",
                    "reference": "",
                    "source": source,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def coa(tiny_dataset):
    return tiny_dataset.chart_of_accounts


def _findings(journal, coa, rule=None):
    result = audit.audit_findings(journal, coa)
    return result if rule is None else result[result["rule"] == rule]


# --------------------------------------------------------------------- round amounts
@pytest.mark.parametrize(
    "amount, flagged",
    [(5000, True), (10000, True), (12000, True), (4999, False), (5500, False), (1000, False), (4000, False)],
)
def test_round_amount_threshold_and_step(coa, amount, flagged):
    journal = _journal([("A", "2025-01-06", "system", "Adj", [("1000", amount, 0), ("4000", 0, amount)])])
    hits = _findings(journal, coa, "round_amount")
    assert (len(hits) > 0) is flagged


def test_round_amount_is_reported_once_per_entry_and_amount(coa):
    journal = _journal([("A", "2025-01-06", "system", "Adj", [("1000", 12000, 0), ("4000", 0, 12000)])])
    hits = _findings(journal, coa, "round_amount")
    assert len(hits) == 1
    assert hits.iloc[0]["amount"] == 12000


# -------------------------------------------------------------------- weekend manual
def test_weekend_rule_applies_only_to_manual_entries(coa):
    saturday = "2025-01-04"  # a Saturday
    journal = _journal(
        [
            ("M", saturday, "manual", "Manual adj", [("6400", 850.4, 0), ("1000", 0, 850.4)]),
            ("S", saturday, "system", "System adj", [("6400", 300.1, 0), ("1000", 0, 300.1)]),
            ("W", "2025-01-06", "manual", "Monday manual", [("6400", 200.2, 0), ("1000", 0, 200.2)]),
        ]
    )
    hits = _findings(journal, coa, "weekend_manual")
    assert set(hits["entry_id"]) == {"M"}
    assert "Saturday" in hits.iloc[0]["detail"]


def test_sunday_is_a_weekend_day(coa):
    journal = _journal([("M", "2025-01-05", "manual", "Sunday", [("6400", 10.5, 0), ("1000", 0, 10.5)])])
    assert len(_findings(journal, coa, "weekend_manual")) == 1


# ----------------------------------------------------------------------- threshold
@pytest.mark.parametrize("amount, flagged", [(4750, True), (4870, True), (4999.99, True), (4749.99, False), (5000, False)])
def test_threshold_band_is_5_percent_below_approval_limit(coa, amount, flagged):
    journal = _journal([("T", "2025-01-06", "manual", "Payment", [("6400", amount, 0), ("1000", 0, amount)])])
    assert (len(_findings(journal, coa, "threshold_manual")) > 0) is flagged


def test_threshold_rule_ignores_system_entries(coa):
    journal = _journal([("T", "2025-01-06", "system", "Payment", [("6400", 4900, 0), ("1000", 0, 4900)])])
    assert _findings(journal, coa, "threshold_manual").empty


# ------------------------------------------------------------------------- outliers
def test_outlier_detected_with_robust_z_score(coa):
    amounts = [100, 101, 99, 102, 98, 100, 1000]
    entries = [(f"U{i}", f"2025-01-{i + 1:02d}", "system", "Utilities", [("6200", a, 0), ("1000", 0, a)]) for i, a in enumerate(amounts)]
    hits = _findings(_journal(entries), coa, "outlier_expense")
    assert list(hits["entry_id"]) == ["U6"]
    assert hits.iloc[0]["amount"] == 1000
    assert "robust z-score" in hits.iloc[0]["detail"]


def test_outlier_needs_five_observations(coa):
    amounts = [100, 101, 99, 1000]
    entries = [(f"U{i}", f"2025-01-{i + 1:02d}", "system", "Utilities", [("6200", a, 0), ("1000", 0, a)]) for i, a in enumerate(amounts)]
    assert _findings(_journal(entries), coa, "outlier_expense").empty


def test_outlier_skipped_for_constant_amounts(coa):
    entries = [(f"R{i}", f"2025-01-{i + 1:02d}", "system", "Rent", [("6100", 4200, 0), ("1000", 0, 4200)]) for i in range(7)]
    assert _findings(_journal(entries), coa, "outlier_expense").empty


def test_outlier_rule_only_looks_at_expense_lines(coa):
    amounts = [100, 101, 99, 102, 98, 100, 1000]
    entries = [(f"R{i}", f"2025-01-{i + 1:02d}", "system", "Sales", [("1100", a, 0), ("4000", 0, a)]) for i, a in enumerate(amounts)]
    assert _findings(_journal(entries), coa, "outlier_expense").empty


# ----------------------------------------------------------------------- duplicates
def test_duplicate_flags_the_later_entry(coa):
    journal = _journal(
        [
            ("D1", "2025-01-10", "system", "Supplier invoice A", [("5000", 500, 0), ("2000", 0, 500)]),
            ("D2", "2025-01-13", "system", "Supplier invoice A again", [("5000", 500, 0), ("2000", 0, 500)]),
        ]
    )
    hits = _findings(journal, coa, "duplicate_posting")
    assert list(hits["entry_id"]) == ["D2"]
    assert "D1" in hits.iloc[0]["detail"]


@pytest.mark.parametrize("days, flagged", [(7, True), (8, False)])
def test_duplicate_window_is_seven_days(coa, days, flagged):
    journal = _journal(
        [
            ("D1", "2025-01-10", "system", "A", [("5000", 500, 0), ("2000", 0, 500)]),
            ("D2", pd.Timestamp("2025-01-10") + pd.Timedelta(days=days), "system", "B", [("5000", 500, 0), ("2000", 0, 500)]),
        ]
    )
    assert (len(_findings(journal, coa, "duplicate_posting")) > 0) is flagged


def test_same_side_is_required(coa):
    # A receipt of an invoice is a credit to receivables; it must not count as a duplicate of the invoice.
    journal = _journal(
        [
            ("I", "2025-01-10", "system", "Invoice", [("1100", 300, 0), ("4000", 0, 300)]),
            ("P", "2025-01-12", "system", "Payment", [("1000", 300, 0), ("1100", 0, 300)]),
        ]
    )
    assert _findings(journal, coa, "duplicate_posting").empty


def test_same_entry_is_not_a_duplicate(coa):
    journal = _journal(
        [("X", "2025-01-10", "system", "Two identical lines", [("6400", 40, 0), ("6400", 40, 0), ("1000", 0, 80)])]
    )
    assert _findings(journal, coa, "duplicate_posting").empty


# ---------------------------------------------------------------- opening balances
def test_opening_balance_entries_are_never_flagged(coa):
    journal = _journal(
        [("OPEN", "2024-10-31", "manual", "Opening balances", [("1000", 180000, 0), ("3000", 0, 180000)])]
    )
    assert audit.audit_findings(journal, coa).empty


# ------------------------------------------------------------------------- Benford
def test_first_digit_helper():
    assert first_digit(4200) == 4
    assert first_digit(0.37) == 3
    assert first_digit(912.5) == 9


def test_benford_passes_for_log_uniform_population():
    rng = np.random.default_rng(3)
    lines = pd.DataFrame({"value": 10 ** rng.uniform(1, 5, size=5000)})
    result = benford_test(lines)
    assert result.passed
    assert result.conformity in {"close conformity", "acceptable conformity"}


def test_benford_fails_for_uniform_population():
    rng = np.random.default_rng(3)
    lines = pd.DataFrame({"value": rng.uniform(2000, 9000, size=5000)})
    result = benford_test(lines)
    assert not result.passed
    assert result.conformity == "non-conformity"


def test_benford_excludes_recurring_amounts():
    lines = pd.DataFrame({"value": [4200.0] * 30 + [123.0, 456.0, 789.0]})
    result = benford_test(lines)
    assert result.excluded_recurring == 30
    assert result.count == 3


def test_benford_with_no_usable_amounts():
    result = benford_test(pd.DataFrame({"value": [0.0, 5.0]}))
    assert result.count == 0
    assert not result.passed
    assert result.conformity == "not assessed"
    assert result.digits["observed"].sum() == 0


def test_benford_digits_table_has_expected_expectations():
    rng = np.random.default_rng(0)
    result = benford_test(pd.DataFrame({"value": 10 ** rng.uniform(1, 5, size=500)}))
    assert list(result.digits["digit"]) == list(range(1, 10))
    assert result.digits["expected_pct"].sum() == pytest.approx(1.0)
    assert result.digits.loc[0, "expected_pct"] == pytest.approx(0.30103, abs=1e-5)


# ------------------------------------------------------------------ bundling
def test_run_audit_counts_manual_entries_and_is_deterministic(coa):
    journal = _journal(
        [
            ("A", "2025-01-06", "manual", "Adj", [("6400", 300, 0), ("1000", 0, 300)]),
            ("B", "2025-01-07", "system", "Sale", [("1100", 800, 0), ("4000", 0, 800)]),
        ]
    )
    first = run_audit(journal, coa)
    second = run_audit(journal, coa)
    assert first.entries_tested == 2
    assert first.manual_entries == 1
    assert first.manual_share == 0.5
    pd.testing.assert_frame_equal(first.findings, second.findings)


def test_run_audit_respects_period_bounds(coa):
    journal = _journal(
        [
            ("A", "2025-01-04", "manual", "Saturday", [("6400", 300, 0), ("1000", 0, 300)]),
            ("B", "2025-02-08", "manual", "Saturday", [("6400", 300, 0), ("1000", 0, 300)]),
        ]
    )
    feb = run_audit(journal, coa, "2025-02-01", "2025-02-28")
    assert list(feb.findings["entry_id"]) == ["B"]
    assert feb.entries_tested == 1


def test_findings_are_sorted_and_have_the_documented_columns(coa):
    journal = _journal(
        [
            ("B", "2025-02-08", "manual", "Sat", [("6400", 300, 0), ("1000", 0, 300)]),
            ("A", "2025-01-04", "manual", "Sat", [("6400", 300, 0), ("1000", 0, 300)]),
        ]
    )
    findings = audit.audit_findings(journal, coa)
    assert list(findings.columns) == audit.FINDING_COLUMNS
    assert findings["date"].is_monotonic_increasing


def test_rule_summary_lists_every_rule(coa):
    summary = rule_summary(pd.DataFrame(columns=audit.FINDING_COLUMNS))
    assert list(summary["rule"]) == list(RULES)
    assert summary["findings"].sum() == 0


def test_empty_journal_gives_empty_audit(coa):
    empty = _journal([("A", "2025-01-06", "system", "x", [("1000", 0, 0)])]).iloc[0:0]
    result = run_audit(empty.assign(date=pd.Series(dtype="datetime64[ns]")), coa, "2025-01-01", "2025-01-31")
    assert result.findings.empty
    assert result.entries_tested == 0
    assert result.manual_share == 0.0


# ------------------------------------------------------------ ground truth scoring
def test_evaluate_against_truth_scores_each_type():
    findings = pd.DataFrame(
        {
            "rule": ["round_amount", "duplicate_posting", "outlier_expense"],
            "entry_id": ["E1", "E9", "E5"],
        }
    )
    truth = pd.DataFrame(
        {
            "entry_id": ["E1", "E2", "E9"],
            "anomaly_type": ["round_amount", "round_amount", "duplicate_posting"],
            "description": ["a", "b", "c"],
        }
    )
    result = evaluate_against_truth(findings, truth)
    table = result["table"].set_index("anomaly_type")
    assert table.loc["round_amount", "detected"] == 1
    assert table.loc["round_amount", "detection_rate"] == 0.5
    assert table.loc["duplicate_posting", "detection_rate"] == 1.0
    assert table.loc["weekend_manual", "detection_rate"] != table.loc["weekend_manual", "detection_rate"]  # NaN
    assert result["false_positives"] == 1  # E5 is not in the ground truth
    assert result["total"] == pytest.approx(2 / 3)


def test_evaluate_against_truth_with_no_findings():
    truth = pd.DataFrame({"entry_id": ["E1"], "anomaly_type": ["round_amount"], "description": ["a"]})
    result = evaluate_against_truth(pd.DataFrame(columns=audit.FINDING_COLUMNS), truth)
    assert result["table"].loc[0, "detected"] == 0
    assert result["false_positives"] == 0
    assert result["total"] == 0
