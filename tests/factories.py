"""Hand-computed fixtures shared by the test-suite.

The "tiny" company has two invoices, a handful of journal entries and a small budget.
All expected values in the tests are worked out by hand from the rows below:

Income statement
    Jan 2025: revenue 500, cost of sales 200, operating expenses 100 -> net income 200
    Feb 2025: revenue 300, operating expenses 30 (depreciation), tax 40 -> net income 230

Balance sheet at 28 Feb 2025 (and at 20 Feb, the last posting date)
    Cash 1,200 + receivables 300 - accumulated depreciation 30 = assets 1,470
    Tax payable 40 = liabilities 40
    Share capital 1,000 + cumulative earnings 430 = equity 1,430
"""

from __future__ import annotations

import pandas as pd

from accviz.loader import Dataset, prepare_dataset
from accviz.synthetic import CSV_COLUMNS, DEFAULT_CHART_OF_ACCOUNTS

JOURNAL_COLUMNS = CSV_COLUMNS["journal"]
INVOICE_COLUMNS = CSV_COLUMNS["invoices"]
BUDGET_COLUMNS = CSV_COLUMNS["budget"]

JOURNAL_ROWS: list[tuple[str, ...]] = [
    # entry_id, date, account, description, debit, credit, department, reference
    ("JE-1", "2025-01-05", "1000", "Capital injection", "1000", "", "Finance", "CAP"),
    ("JE-1", "2025-01-05", "3000", "Capital injection", "", "1000", "Finance", "CAP"),
    ("JE-2", "2025-01-10", "1100", "Invoice INV-1", "500", "", "Sales", "INV-1"),
    ("JE-2", "2025-01-10", "4000", "Invoice INV-1", "", "500", "Sales", "INV-1"),
    ("JE-3", "2025-01-20", "5000", "Stock purchase", "200", "", "Operations", "PO-1"),
    ("JE-3", "2025-01-20", "1000", "Stock purchase", "", "200", "Operations", "PO-1"),
    ("JE-4", "2025-01-25", "6000", "January salaries", "100", "", "Administration", "PAY-1"),
    ("JE-4", "2025-01-25", "1000", "January salaries", "", "100", "Administration", "PAY-1"),
    ("JE-5", "2025-02-03", "1000", "Payment INV-1", "500", "", "Finance", "INV-1"),
    ("JE-5", "2025-02-03", "1100", "Payment INV-1", "", "500", "Finance", "INV-1"),
    ("JE-6", "2025-02-10", "1100", "Invoice INV-2", "300", "", "Sales", "INV-2"),
    ("JE-6", "2025-02-10", "4100", "Invoice INV-2", "", "300", "Sales", "INV-2"),
    ("JE-7", "2025-02-15", "8000", "Tax accrual", "40", "", "Finance", "TAX-1"),
    ("JE-7", "2025-02-15", "2100", "Tax accrual", "", "40", "Finance", "TAX-1"),
    ("JE-8", "2025-02-20", "6500", "Depreciation", "30", "", "Operations", "DEP-1"),
    ("JE-8", "2025-02-20", "1590", "Depreciation", "", "30", "Operations", "DEP-1"),
]

INVOICE_ROWS: list[tuple[str, ...]] = [
    ("INV-1", "Aurora Foods Ltd.", "2025-01-10", "2025-02-09", "500", "2025-02-03", "500"),
    ("INV-2", "BlueRiver Logistics", "2025-02-10", "2025-03-12", "300", "", "0"),
]

BUDGET_ROWS: list[tuple[str, ...]] = [
    ("2025-01", "4000", "400"),
    ("2025-01", "6000", "150"),
    ("2025-02", "4100", "250"),
    ("2025-02", "6100", "80"),
]


def coa_frame() -> pd.DataFrame:
    """Default chart of accounts as raw (string) data."""
    return pd.DataFrame(DEFAULT_CHART_OF_ACCOUNTS, columns=CSV_COLUMNS["coa"]).astype(str)


def tiny_raw() -> dict[str, pd.DataFrame]:
    """Raw string tables for the hand-computed company. Safe to mutate (fresh copies)."""
    return {
        "coa": coa_frame(),
        "journal": pd.DataFrame(JOURNAL_ROWS, columns=JOURNAL_COLUMNS),
        "invoices": pd.DataFrame(INVOICE_ROWS, columns=INVOICE_COLUMNS),
        "budget": pd.DataFrame(BUDGET_ROWS, columns=BUDGET_COLUMNS),
    }


def tiny_dataset() -> Dataset:
    """Normalised, validated version of :func:`tiny_raw`."""
    ds, result = prepare_dataset(tiny_raw())
    assert ds is not None and result.ok, result.summary()
    return ds
