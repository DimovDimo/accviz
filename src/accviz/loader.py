"""Reading, normalising and validating the accounting input files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import pandas as pd

from accviz import config
from accviz.validation import ValidationResult, validate_dataset, validate_required_columns


@dataclass(frozen=True)
class Dataset:
    """Immutable, normalised accounting dataset."""

    chart_of_accounts: pd.DataFrame
    journal: pd.DataFrame
    invoices: pd.DataFrame
    budget: pd.DataFrame

    @property
    def start_date(self) -> pd.Timestamp:
        return self.journal["date"].min()

    @property
    def end_date(self) -> pd.Timestamp:
        return self.journal["date"].max()


class DataValidationError(ValueError):
    """Raised when a dataset has validation errors and cannot be analysed."""

    def __init__(self, result: ValidationResult):
        self.result = result
        super().__init__("Invalid accounting data:\n" + "\n".join(result.errors))


# --------------------------------------------------------------------------- helpers
def _text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def _amount(series: pd.Series) -> pd.Series:
    """Convert to float; empty cells become 0, unparsable cells become NaN."""
    text = _text(series)
    cleaned = text.where(text != "", "0")
    return pd.to_numeric(cleaned, errors="coerce").astype(float)


def _date(series: pd.Series) -> pd.Series:
    """Parse ISO dates; empty or invalid cells become NaT."""
    text = _text(series)
    cleaned = text.where(text != "", None)
    return pd.to_datetime(cleaned, format="%Y-%m-%d", errors="coerce")


def _optional(df: pd.DataFrame, col: str, default: str = "") -> pd.Series:
    if col in df.columns:
        return _text(df[col])
    return pd.Series(default, index=df.index, dtype=object)


# ------------------------------------------------------------------- normalisation
def normalize_coa(raw: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "account_code": _text(raw["account_code"]),
            "account_name": _text(raw["account_name"]),
            "account_type": _text(raw["account_type"]),
            "subtype": _text(raw["subtype"]),
        }
    )


def normalize_journal(raw: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "entry_id": _text(raw["entry_id"]),
            "date": _date(raw["date"]),
            "account_code": _text(raw["account_code"]),
            "description": _optional(raw, "description"),
            "debit": _amount(raw["debit"]),
            "credit": _amount(raw["credit"]),
            "department": _optional(raw, "department"),
            "reference": _optional(raw, "reference"),
        }
    )


def normalize_invoices(raw: pd.DataFrame) -> pd.DataFrame:
    paid_amount = _amount(raw["paid_amount"]) if "paid_amount" in raw.columns else pd.Series(0.0, index=raw.index)
    paid_date = _date(raw["paid_date"]) if "paid_date" in raw.columns else pd.Series(pd.NaT, index=raw.index)
    return pd.DataFrame(
        {
            "invoice_id": _text(raw["invoice_id"]),
            "customer": _text(raw["customer"]),
            "issue_date": _date(raw["issue_date"]),
            "due_date": _date(raw["due_date"]),
            "amount": _amount(raw["amount"]),
            "paid_date": paid_date,
            "paid_amount": paid_amount.fillna(0.0).astype(float),
        }
    )


def normalize_budget(raw: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "period": _text(raw["period"]),
            "account_code": _text(raw["account_code"]),
            "budget_amount": _amount(raw["budget_amount"]),
        }
    )


# ------------------------------------------------------------------------ public API
def load_raw_directory(directory: str | Path) -> dict[str, pd.DataFrame]:
    """Read the four CSV files from *directory* as raw text tables."""
    base = Path(directory)
    raw: dict[str, pd.DataFrame] = {}
    for key, filename in config.DATASET_FILES.items():
        path = base / filename
        if not path.is_file():
            raise FileNotFoundError(f"Required file not found: {path}")
        raw[key] = pd.read_csv(path, dtype=str, keep_default_na=False)
    return raw


def prepare_dataset(raw: Mapping[str, pd.DataFrame]) -> tuple[Dataset | None, ValidationResult]:
    """Normalise raw tables and validate them.

    Returns ``(dataset, result)``. The dataset is ``None`` when required columns are
    missing, because nothing can be normalised in that case.
    """
    pre = validate_required_columns(raw)
    if not pre.ok:
        return None, pre

    ds = Dataset(
        chart_of_accounts=normalize_coa(raw["coa"]),
        journal=normalize_journal(raw["journal"]),
        invoices=normalize_invoices(raw["invoices"]),
        budget=normalize_budget(raw["budget"]),
    )
    result = validate_dataset(ds)
    result.warnings = pre.warnings + result.warnings
    return ds, result


def build_dataset(raw: Mapping[str, pd.DataFrame]) -> Dataset:
    """Normalise and validate raw tables; raise :class:`DataValidationError` on errors."""
    ds, result = prepare_dataset(raw)
    if ds is None or not result.ok:
        raise DataValidationError(result)
    return ds


def read_dataset(directory: str | Path) -> Dataset:
    """Load, normalise and validate a dataset directory."""
    return build_dataset(load_raw_directory(directory))
