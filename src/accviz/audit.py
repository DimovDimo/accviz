"""Journal audit analytics: rule-based tests, a Benford first-digit test and ground-truth scoring.

The rules are *indicators*, not proof of fraud or error. Each finding tells an auditor which
entry to look at and why. Rules and thresholds:

========================  =========================================================  ========
rule                      test                                                       severity
========================  =========================================================  ========
round_amount              amount ≥ 5,000 and an exact multiple of 1,000               medium
weekend_manual            manual entry dated on a Saturday or Sunday                  low
threshold_manual          manual line within 5 % below the 5,000 approval threshold   medium
outlier_expense           expense line with robust z-score ≥ 4.0 within its account   high
duplicate_posting         same account, same side and same amount as another entry    high
                          posted within 7 days (the later entry is reported)
========================  =========================================================  ========

Robust z-score: ``0.6745 × (x − median) / MAD`` where MAD is the median absolute deviation.
Accounts with fewer than five observations, or with MAD = 0 (constant amounts), are skipped.

Benford's law: the first-digit distribution of amounts should follow ``log10(1 + 1/d)``.
Recurring fixed amounts (rent, fixed depreciation) break the law, so amounts that repeat
more than five times are excluded from the test. The test reports a chi-square statistic
(8 degrees of freedom, critical value 15.507 at α = 0.05) and the mean absolute deviation
(MAD) of the first-digit proportions, using Nigrini's conformity bands.

Opening-balance entries are excluded from every rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

from accviz import config
from accviz.ledger import DateLike, filter_dates, to_timestamp, with_account_info

RULES: tuple[str, ...] = (
    "round_amount",
    "weekend_manual",
    "threshold_manual",
    "outlier_expense",
    "duplicate_posting",
)
RULE_LABELS: dict[str, str] = {
    "round_amount": "Round amount",
    "weekend_manual": "Manual entry on a weekend",
    "threshold_manual": "Just below approval threshold",
    "outlier_expense": "Expense outlier",
    "duplicate_posting": "Possible duplicate posting",
}
SEVERITY: dict[str, str] = {
    "round_amount": "medium",
    "weekend_manual": "low",
    "threshold_manual": "medium",
    "outlier_expense": "high",
    "duplicate_posting": "high",
}

ROUND_MIN_AMOUNT = 5_000.0
ROUND_STEP = 1_000.0
APPROVAL_THRESHOLD = 5_000.0
THRESHOLD_BAND = 0.05
OUTLIER_Z_THRESHOLD = 4.0
OUTLIER_MIN_OBSERVATIONS = 5
ROBUST_SCALE = 0.6745
DUPLICATE_WINDOW_DAYS = 7
BENFORD_CRITICAL_VALUE = 15.507  # chi-square, 8 degrees of freedom, alpha = 0.05
BENFORD_MIN_AMOUNT = 10.0
BENFORD_RECURRING_MAX = 5  # amounts repeated more often than this are excluded

FINDING_COLUMNS = [
    "rule",
    "severity",
    "entry_id",
    "date",
    "account_code",
    "account_name",
    "amount",
    "description",
    "detail",
]
SUMMARY_COLUMNS = ["rule", "label", "severity", "findings", "entries"]


# ----------------------------------------------------------------------------- data
def _tested_lines(journal: pd.DataFrame, coa: pd.DataFrame) -> pd.DataFrame:
    """Journal lines without opening-balance entries, with ``value`` = the non-zero side."""
    df = with_account_info(journal, coa)
    opening = df["description"].str.contains(config.OPENING_BALANCE_MARKER, case=False, na=False)
    opening_entries = set(df.loc[opening, "entry_id"])
    df = df[~df["entry_id"].isin(opening_entries)].copy()
    df["value"] = df["debit"] + df["credit"]
    df["side"] = np.where(df["debit"] > 0, "debit", "credit")
    return df


def _finding(row_df: pd.DataFrame, rule: str, details: Sequence[str] | pd.Series | str) -> pd.DataFrame:
    detail_col = details if isinstance(details, str) else np.asarray(list(details), dtype=object)
    out = pd.DataFrame(
        {
            "rule": rule,
            "severity": SEVERITY[rule],
            "entry_id": row_df["entry_id"].to_numpy(),
            "date": row_df["date"].to_numpy(),
            "account_code": row_df["account_code"].to_numpy(),
            "account_name": row_df["account_name"].to_numpy(),
            "amount": row_df["value"].to_numpy(),
            "description": row_df["description"].to_numpy(),
            "detail": detail_col,
        }
    )
    return out[FINDING_COLUMNS]


# ---------------------------------------------------------------------------- rules
def round_amount_rule(lines: pd.DataFrame) -> pd.DataFrame:
    value = lines["value"]
    scaled = value / ROUND_STEP
    mask = (value >= ROUND_MIN_AMOUNT) & (np.abs(scaled - np.round(scaled)) < 1e-9)
    hits = lines[mask]
    return _finding(hits, "round_amount", [f"round amount of {v:,.0f}" for v in hits["value"]])


def weekend_manual_rule(lines: pd.DataFrame) -> pd.DataFrame:
    mask = (lines["source"] == "manual") & (lines["date"].dt.dayofweek >= 5)
    hits = lines[mask]
    return _finding(hits, "weekend_manual", [f"manual entry dated {d:%A}" for d in hits["date"]])


def threshold_manual_rule(lines: pd.DataFrame) -> pd.DataFrame:
    low = APPROVAL_THRESHOLD * (1 - THRESHOLD_BAND)
    mask = (lines["source"] == "manual") & (lines["value"] >= low) & (lines["value"] < APPROVAL_THRESHOLD)
    hits = lines[mask]
    return _finding(hits, "threshold_manual", ["manual line just below the 5,000 approval threshold"] * len(hits))


def outlier_rule(lines: pd.DataFrame) -> pd.DataFrame:
    expense = lines[(lines["account_type"] == "Expense") & (lines["value"] > 0)]
    flagged: list[pd.DataFrame] = []
    details: list[str] = []
    for _, group in expense.groupby("account_code"):
        if len(group) < OUTLIER_MIN_OBSERVATIONS:
            continue
        x = group["value"].to_numpy(dtype=float)
        median = np.median(x)
        mad = np.median(np.abs(x - median))
        if mad == 0:  # constant amounts (e.g. fixed rent): nothing to compare against
            continue
        z = ROBUST_SCALE * (x - median) / mad
        mask = z >= OUTLIER_Z_THRESHOLD
        if mask.any():
            flagged.append(group[mask])
            details.extend(f"robust z-score {zz:.1f} (account median {median:,.2f})" for zz in z[mask])
    if not flagged:
        return _finding(lines.iloc[0:0], "outlier_expense", [])
    return _finding(pd.concat(flagged), "outlier_expense", details)


def duplicate_rule(lines: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    details: list[str] = []
    positive = lines[lines["value"] > 0]
    for _, group in positive.groupby(["account_code", "side", "value"]):
        if len(group) < 2:
            continue
        group = group.sort_values(["date", "entry_id"])
        records = list(group.itertuples(index=False))
        for k in range(1, len(records)):
            current = records[k]
            for earlier in records[:k]:
                gap = (current.date - earlier.date).days
                if earlier.entry_id != current.entry_id and gap <= DUPLICATE_WINDOW_DAYS:
                    rows.append(group.iloc[[k]])
                    details.append(f"same account, side and amount as {earlier.entry_id} ({gap} days earlier)")
                    break
    if not rows:
        return _finding(lines.iloc[0:0], "duplicate_posting", [])
    hits = pd.concat(rows)
    return _finding(hits, "duplicate_posting", details)


# -------------------------------------------------------------------------- benford
@dataclass(frozen=True)
class BenfordResult:
    """First-digit test. ``passed`` is True when the chi-square statistic is within the critical value."""

    count: int
    excluded_recurring: int
    chi_square: float
    critical_value: float
    mad: float
    digits: pd.DataFrame

    @property
    def passed(self) -> bool:
        return self.count > 0 and self.chi_square <= self.critical_value

    @property
    def conformity(self) -> str:
        """Nigrini's MAD bands for first digits."""
        if self.count == 0:
            return "not assessed"
        if self.mad < 0.006:
            return "close conformity"
        if self.mad < 0.012:
            return "acceptable conformity"
        if self.mad < 0.015:
            return "marginal conformity"
        return "non-conformity"


def first_digit(value: float) -> int:
    text = f"{value:.2f}".replace(".", "").lstrip("0")
    return int(text[0])


def benford_test(lines: pd.DataFrame) -> BenfordResult:
    """First-digit test on line amounts (debit or credit side), excluding recurring amounts."""
    values = lines.loc[lines["value"] >= BENFORD_MIN_AMOUNT, "value"].round(2)
    counts = values.map(values.value_counts())
    recurring = counts > BENFORD_RECURRING_MAX
    used = values[~recurring]
    digits_seen = used.map(first_digit) if len(used) else pd.Series([], dtype=int)
    observed = np.array([(digits_seen == d).sum() for d in range(1, 10)], dtype=float)
    n = float(observed.sum())
    expected_prop = np.log10(1 + 1 / np.arange(1, 10))
    expected = expected_prop * n
    chi = float(((observed - expected) ** 2 / expected).sum()) if n else 0.0
    obs_prop = observed / n if n else np.zeros(9)
    mad = float(np.mean(np.abs(obs_prop - expected_prop))) if n else 0.0
    digits = pd.DataFrame(
        {
            "digit": np.arange(1, 10),
            "observed": observed.astype(int),
            "expected": expected,
            "observed_pct": obs_prop,
            "expected_pct": expected_prop,
        }
    )
    return BenfordResult(
        count=int(n),
        excluded_recurring=int(recurring.sum()),
        chi_square=chi,
        critical_value=BENFORD_CRITICAL_VALUE,
        mad=mad,
        digits=digits,
    )


# ------------------------------------------------------------------------ bundling
@dataclass(frozen=True)
class AuditResult:
    """Findings for a period plus summary and the Benford test."""

    start: pd.Timestamp
    end: pd.Timestamp
    findings: pd.DataFrame
    summary: pd.DataFrame
    benford: BenfordResult
    lines_tested: int
    entries_tested: int
    manual_entries: int

    @property
    def manual_share(self) -> float:
        return self.manual_entries / self.entries_tested if self.entries_tested else 0.0

    @property
    def total_findings(self) -> int:
        return len(self.findings)


def audit_findings(journal: pd.DataFrame, coa: pd.DataFrame, start: DateLike = None, end: DateLike = None) -> pd.DataFrame:
    """All findings dated in [start, end], sorted by date. Baselines use the whole journal."""
    lines = _tested_lines(journal, coa)
    parts = [
        round_amount_rule(lines),
        weekend_manual_rule(lines),
        threshold_manual_rule(lines),
        outlier_rule(lines),
        duplicate_rule(lines),
    ]
    found = pd.concat(parts, ignore_index=True)
    # One finding per entry, rule and amount: a posting appears on both its debit and credit line.
    found = found.drop_duplicates(subset=["rule", "entry_id", "amount"], keep="first")
    found["date"] = pd.to_datetime(found["date"])
    found = filter_dates(found, start, end)
    if found.empty:
        return pd.DataFrame(columns=FINDING_COLUMNS)
    order = {rule: i for i, rule in enumerate(RULES)}
    found = found.assign(_order=found["rule"].map(order))
    return found.sort_values(["date", "entry_id", "_order"]).drop(columns="_order").reset_index(drop=True)


def rule_summary(findings: pd.DataFrame) -> pd.DataFrame:
    """One row per rule (all rules listed, zeros included): findings and distinct entries."""
    rows = []
    for rule in RULES:
        part = findings[findings["rule"] == rule] if not findings.empty else findings
        rows.append(
            {
                "rule": rule,
                "label": RULE_LABELS[rule],
                "severity": SEVERITY[rule],
                "findings": int(len(part)),
                "entries": int(part["entry_id"].nunique()) if len(part) else 0,
            }
        )
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def run_audit(journal: pd.DataFrame, coa: pd.DataFrame, start: DateLike = None, end: DateLike = None) -> AuditResult:
    """Run every rule and the Benford test for [start, end]."""
    start_ts = to_timestamp(start) if start is not None else journal["date"].min()
    end_ts = to_timestamp(end) if end is not None else journal["date"].max()
    lines = _tested_lines(journal, coa)
    period = filter_dates(lines, start_ts, end_ts)
    findings = audit_findings(journal, coa, start_ts, end_ts)
    entries = period.groupby("entry_id")["source"].first() if not period.empty else pd.Series(dtype=object)
    return AuditResult(
        start=start_ts,
        end=end_ts,
        findings=findings,
        summary=rule_summary(findings),
        benford=benford_test(period),
        lines_tested=int(len(period)),
        entries_tested=int(len(entries)),
        manual_entries=int((entries == "manual").sum()),
    )


# ------------------------------------------------------------------ ground truth
def evaluate_against_truth(findings: pd.DataFrame, truth: pd.DataFrame) -> dict:
    """Score the findings against injected anomalies.

    Returns a dict with ``table`` (per anomaly type: injected, detected, detection rate),
    ``false_positives`` (findings on entries that are not in the ground truth) and
    ``total`` (overall detection rate).
    """
    rows = []
    for anomaly_type in RULES:
        injected = truth[truth["anomaly_type"] == anomaly_type]
        detected_ids = set(findings.loc[findings["rule"] == anomaly_type, "entry_id"]) if not findings.empty else set()
        hits = int(injected["entry_id"].isin(detected_ids).sum())
        rows.append(
            {
                "anomaly_type": anomaly_type,
                "injected": int(len(injected)),
                "detected": hits,
                "detection_rate": hits / len(injected) if len(injected) else float("nan"),
            }
        )
    table = pd.DataFrame(rows, columns=["anomaly_type", "injected", "detected", "detection_rate"])
    truth_ids = set(truth["entry_id"])
    false_positives = int((~findings["entry_id"].isin(truth_ids)).sum()) if not findings.empty else 0
    total_injected = int(table["injected"].sum())
    total_detected = int(table["detected"].sum())
    return {
        "table": table,
        "false_positives": false_positives,
        "total": total_detected / total_injected if total_injected else float("nan"),
    }
