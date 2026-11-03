"""Data-quality rules.

Each rule appends human-readable messages to a :class:`ValidationResult`.
*Errors* block the analysis; *warnings* are informational only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Mapping

import pandas as pd

from accviz import config

if TYPE_CHECKING:  # pragma: no cover - import only for type checkers
    from accviz.loader import Dataset

MAX_EXAMPLES = 5
_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@dataclass
class ValidationResult:
    """Collected errors and warnings from validating a dataset."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when there are no errors (warnings are allowed)."""
        return not self.errors

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        return self

    def summary(self) -> str:
        if self.ok and not self.warnings:
            return "Validation passed: no errors, no warnings."
        lines = [f"Errors: {len(self.errors)}", f"Warnings: {len(self.warnings)}"]
        lines += [f"  ERROR   {msg}" for msg in self.errors]
        lines += [f"  WARNING {msg}" for msg in self.warnings]
        return "\n".join(lines)


def _examples(values: list[str]) -> str:
    """Format up to MAX_EXAMPLES values for a message."""
    shown = ", ".join(values[:MAX_EXAMPLES])
    extra = len(values) - MAX_EXAMPLES
    return shown + (f" (+{extra} more)" if extra > 0 else "")


def validate_required_columns(raw: Mapping[str, pd.DataFrame]) -> ValidationResult:
    """Check that every required table is present and has its required columns."""
    result = ValidationResult()
    for key, filename in config.DATASET_FILES.items():
        if key not in raw:
            result.error(f"{filename}: file is missing")
            continue
        _check_columns(key, filename, raw[key], result)
    for key, filename in config.OPTIONAL_FILES.items():
        if key not in raw:
            result.warn(f"{filename}: file not found; payables analysis is empty")
            continue
        _check_columns(key, filename, raw[key], result)
        if raw[key].empty:
            result.warn(f"{filename}: file has no rows; payables analysis is empty")
    return result


def _check_columns(key: str, filename: str, table: pd.DataFrame, result: ValidationResult) -> None:
    missing = [c for c in config.REQUIRED_COLUMNS[key] if c not in table.columns]
    if missing:
        result.error(f"{filename}: missing required column(s): {', '.join(missing)}")
    for col in config.OPTIONAL_COLUMNS.get(key, ()):
        if col not in table.columns:
            result.warn(f"{filename}: optional column '{col}' not found; defaults applied")


def validate_dataset(ds: "Dataset") -> ValidationResult:
    """Run all business rules on a normalised dataset."""
    result = ValidationResult()
    _validate_coa(ds.chart_of_accounts, result)
    _validate_journal(ds.journal, ds.chart_of_accounts, result)
    _validate_invoices(ds.invoices, result)
    _validate_budget(ds.budget, ds.chart_of_accounts, result)
    if not ds.supplier_invoices.empty:  # a missing optional file is already reported as a warning
        _validate_invoices(ds.supplier_invoices, result, filename=config.SUPPLIER_INVOICES_FILE)
    return result


def _validate_coa(coa: pd.DataFrame, res: ValidationResult) -> None:
    if coa.empty:
        res.error("chart_of_accounts.csv: no accounts defined")
        return
    dupes = sorted(coa.loc[coa["account_code"].duplicated(keep=False), "account_code"].unique())
    if dupes:
        res.error(f"chart_of_accounts.csv: duplicate account code(s): {_examples(dupes)}")
    bad_type = coa.loc[~coa["account_type"].isin(config.ACCOUNT_TYPES), "account_code"].tolist()
    if bad_type:
        res.error(
            "chart_of_accounts.csv: invalid account_type for account(s) "
            f"{_examples(bad_type)}; allowed: {', '.join(config.ACCOUNT_TYPES)}"
        )
    no_name = coa.loc[coa["account_name"] == "", "account_code"].tolist()
    if no_name:
        res.warn(f"chart_of_accounts.csv: empty account_name for {_examples(no_name)}")
    for _, row in coa.iterrows():
        allowed = config.SUBTYPES_BY_TYPE.get(row["account_type"], frozenset())
        if row["account_type"] in config.ACCOUNT_TYPES and row["subtype"] not in allowed:
            res.warn(
                f"account {row['account_code']} ({row['account_type']}) has subtype "
                f"'{row['subtype']}' which is not a standard subtype for its type"
            )


def _validate_journal(journal: pd.DataFrame, coa: pd.DataFrame, res: ValidationResult) -> None:
    if journal.empty:
        res.error("journal_entries.csv: no journal lines")
        return

    bad_dates = journal.loc[journal["date"].isna()]
    if not bad_dates.empty:
        res.error(
            f"journal_entries.csv: {len(bad_dates)} line(s) with invalid date "
            f"(expected YYYY-MM-DD), e.g. entry {bad_dates['entry_id'].iloc[0]}"
        )

    if journal["debit"].isna().any() or journal["credit"].isna().any():
        res.error("journal_entries.csv: non-numeric debit or credit amount found")
    else:
        negatives = journal.loc[(journal["debit"] < 0) | (journal["credit"] < 0)]
        if not negatives.empty:
            res.error(
                "journal_entries.csv: negative amounts are not allowed "
                f"(entry {negatives['entry_id'].iloc[0]})"
            )
        both = journal.loc[(journal["debit"] > 0) & (journal["credit"] > 0)]
        if not both.empty:
            res.error(
                "journal_entries.csv: line has both debit and credit "
                f"(entry {both['entry_id'].iloc[0]})"
            )
        neither = journal.loc[(journal["debit"] == 0) & (journal["credit"] == 0)]
        if not neither.empty:
            res.error(
                "journal_entries.csv: line has neither debit nor credit "
                f"(entry {neither['entry_id'].iloc[0]})"
            )

    if (journal["entry_id"] == "").any():
        res.error("journal_entries.csv: empty entry_id found")

    unknown = sorted(set(journal["account_code"]) - set(coa["account_code"]))
    if unknown:
        res.error(f"journal_entries.csv: account code(s) not in chart of accounts: {_examples(unknown)}")

    if journal["entry_id"].ne("").all() and journal["debit"].notna().all():
        sums = journal.groupby("entry_id").agg(debit=("debit", "sum"), credit=("credit", "sum"))
        diff = (sums["debit"] - sums["credit"]).abs()
        unbalanced = sums.index[diff > config.BALANCE_TOLERANCE].tolist()
        if unbalanced:
            res.error(
                f"journal_entries.csv: {len(unbalanced)} unbalanced entr(y/ies) "
                f"(debits ≠ credits): {_examples(unbalanced)}"
            )

    date_spread = journal.groupby("entry_id")["date"].nunique()
    multi_date = date_spread.index[date_spread > 1].tolist()
    if multi_date:
        res.warn(f"journal_entries.csv: entries with lines on different dates: {_examples(multi_date)}")

    bad_source = journal.loc[~journal["source"].isin(config.JOURNAL_SOURCES), "entry_id"]
    if not bad_source.empty:
        res.error(
            "journal_entries.csv: source must be 'system' or 'manual' "
            f"(entry {bad_source.iloc[0]})"
        )

    missing_dept = int((journal["department"] == "").sum())
    if missing_dept:
        res.warn(f"journal_entries.csv: {missing_dept} line(s) without department")


def _validate_invoices(
    invoices: pd.DataFrame,
    res: ValidationResult,
    filename: str = "invoices.csv",
    empty_hint: str = "no invoices; receivables aging will be empty",
) -> None:
    """Rules shared by customer invoices and supplier invoices (both are open items)."""
    if invoices.empty:
        res.warn(f"{filename}: {empty_hint}")
        return
    dupes = sorted(invoices.loc[invoices["invoice_id"].duplicated(keep=False), "invoice_id"].unique())
    if dupes:
        res.error(f"{filename}: duplicate invoice_id(s): {_examples(dupes)}")
    if invoices["issue_date"].isna().any():
        res.error(f"{filename}: invalid or missing issue_date")
    if invoices["due_date"].isna().any():
        res.error(f"{filename}: invalid or missing due_date")
    if invoices["amount"].isna().any() or (invoices["amount"] <= 0).any():
        res.error(f"{filename}: amount must be a positive number")
    if invoices["paid_amount"].isna().any():
        res.error(f"{filename}: paid_amount must be numeric")
    else:
        over = invoices.loc[invoices["paid_amount"] > invoices["amount"], "invoice_id"].tolist()
        if over:
            res.error(f"{filename}: paid_amount exceeds amount for {_examples(over)}")
        if (invoices["paid_amount"] < 0).any():
            res.error(f"{filename}: paid_amount cannot be negative")
    late = invoices.loc[invoices["due_date"] < invoices["issue_date"], "invoice_id"].tolist()
    if late:
        res.error(f"{filename}: due_date is before issue_date for {_examples(late)}")
    no_date = invoices.loc[(invoices["paid_amount"] > 0) & invoices["paid_date"].isna(), "invoice_id"]
    if not no_date.empty:
        res.warn(f"{filename}: paid amount without paid_date for {_examples(no_date.tolist())}")


def _validate_budget(budget: pd.DataFrame, coa: pd.DataFrame, res: ValidationResult) -> None:
    if budget.empty:
        res.warn("budget.csv: no budget rows; budget variance will be empty")
        return
    bad_period = budget.loc[~budget["period"].str.match(_PERIOD_RE), "period"].unique().tolist()
    if bad_period:
        res.error(f"budget.csv: period must be YYYY-MM, got {_examples(bad_period)}")
    unknown = sorted(set(budget["account_code"]) - set(coa["account_code"]))
    if unknown:
        res.error(f"budget.csv: account code(s) not in chart of accounts: {_examples(unknown)}")
    types = coa.drop_duplicates("account_code").set_index("account_code")["account_type"]
    known = budget[budget["account_code"].isin(types.index)]
    not_pl = known.loc[~known["account_code"].map(types).isin(config.PROFIT_LOSS_TYPES), "account_code"]
    if not not_pl.empty:
        res.error(f"budget.csv: only Revenue and Expense accounts can be budgeted: {_examples(sorted(set(not_pl)))}")
    if budget["budget_amount"].isna().any() or (budget["budget_amount"] < 0).any():
        res.error("budget.csv: budget_amount must be a non-negative number")
    dupes = budget.duplicated(subset=["period", "account_code"], keep=False)
    if dupes.any():
        res.error("budget.csv: duplicate budget rows for the same period and account")
