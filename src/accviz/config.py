"""Central configuration constants for accviz."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR: Path = PROJECT_ROOT / "data" / "sample"
DEFAULT_REPORT_PATH: Path = PROJECT_ROOT / "reports" / "accounting_report.html"

# Reporting currency (Bulgaria adopted the euro on 1 January 2026).
CURRENCY: str = "EUR"

# Amounts whose difference is at most this value are treated as equal (cents).
BALANCE_TOLERANCE: float = 0.01

# Input file names.
COA_FILE = "chart_of_accounts.csv"
JOURNAL_FILE = "journal_entries.csv"
INVOICES_FILE = "invoices.csv"
BUDGET_FILE = "budget.csv"

DATASET_FILES: dict[str, str] = {
    "coa": COA_FILE,
    "journal": JOURNAL_FILE,
    "invoices": INVOICES_FILE,
    "budget": BUDGET_FILE,
}

# Account types and their natural (normal) balance side.
ACCOUNT_TYPES: tuple[str, ...] = ("Asset", "Liability", "Equity", "Revenue", "Expense")
DEBIT_NORMAL_TYPES: frozenset[str] = frozenset({"Asset", "Expense"})
PROFIT_LOSS_TYPES: frozenset[str] = frozenset({"Revenue", "Expense"})

# Subtypes group accounts into statement lines.
SUBTYPE_CASH = "Cash"
SUBTYPE_RECEIVABLES = "Receivables"
SUBTYPE_FIXED_ASSET = "Fixed Asset"
SUBTYPE_CURRENT_LIABILITY = "Current Liability"
SUBTYPE_LONG_TERM_LIABILITY = "Long-term Liability"
SUBTYPE_EQUITY = "Equity"
SUBTYPE_OPERATING_REVENUE = "Operating Revenue"
SUBTYPE_COST_OF_SALES = "Cost of Sales"
SUBTYPE_OPERATING_EXPENSE = "Operating Expense"
SUBTYPE_FINANCIAL_EXPENSE = "Financial Expense"
SUBTYPE_TAX_EXPENSE = "Tax Expense"

SUBTYPES_BY_TYPE: dict[str, frozenset[str]] = {
    "Asset": frozenset({SUBTYPE_CASH, SUBTYPE_RECEIVABLES, SUBTYPE_FIXED_ASSET}),
    "Liability": frozenset({SUBTYPE_CURRENT_LIABILITY, SUBTYPE_LONG_TERM_LIABILITY}),
    "Equity": frozenset({SUBTYPE_EQUITY}),
    "Revenue": frozenset({SUBTYPE_OPERATING_REVENUE}),
    "Expense": frozenset(
        {
            SUBTYPE_COST_OF_SALES,
            SUBTYPE_OPERATING_EXPENSE,
            SUBTYPE_FINANCIAL_EXPENSE,
            SUBTYPE_TAX_EXPENSE,
        }
    ),
}

# Assets that count as "current" for the current ratio.
CURRENT_ASSET_SUBTYPES: frozenset[str] = frozenset({SUBTYPE_CASH, SUBTYPE_RECEIVABLES})

# Aging buckets for receivables, in order (days overdue).
AGING_BUCKETS: tuple[str, ...] = (
    "Not yet due",
    "1-30 days",
    "31-60 days",
    "61-90 days",
    "90+ days",
)
AGING_BIN_EDGES: tuple[float, ...] = (float("-inf"), 0, 30, 60, 90, float("inf"))

REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "coa": ("account_code", "account_name", "account_type", "subtype"),
    "journal": ("entry_id", "date", "account_code", "debit", "credit"),
    "invoices": ("invoice_id", "customer", "issue_date", "due_date", "amount"),
    "budget": ("period", "account_code", "budget_amount"),
}
OPTIONAL_COLUMNS: dict[str, tuple[str, ...]] = {
    "journal": ("description", "department", "reference"),
    "invoices": ("paid_date", "paid_amount"),
}
