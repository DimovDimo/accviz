"""Deterministic generator of synthetic, double-entry-consistent accounting data.

The generated company ("Northwind Trading Ltd.", fictional) sells goods and services,
buys stock on credit from suppliers, pays salaries, rent, utilities, marketing, interest
and a 10 % corporate income tax paid quarterly. Every journal entry is balanced by
construction, and both sub-ledgers (receivables and supplier invoices) agree with their
control accounts.

Version 1.1 adds:

* ``supplier_invoices.csv`` – 3–6 supplier invoices per month replace the monthly
  purchase lump; each invoice is paid after 20–70 days with probability 0.97.
* a ``source`` column on journal lines: ``manual`` for depreciation, interest, tax accrual,
  loan principal and opening balances; ``system`` otherwise. Manual postings are made on
  business days.
* ``anomalies=True`` injects nine known audit anomalies and writes their ground truth
  (see :func:`_inject_anomalies`). The injected duplicate postings are not supplier
  invoices, so the AP sub-ledger differs from the GL by exactly their amounts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from accviz import config

DEFAULT_CHART_OF_ACCOUNTS: list[tuple[str, str, str, str]] = [
    ("1000", "Cash at Bank", "Asset", config.SUBTYPE_CASH),
    ("1100", "Accounts Receivable", "Asset", config.SUBTYPE_RECEIVABLES),
    ("1500", "Equipment", "Asset", config.SUBTYPE_FIXED_ASSET),
    ("1590", "Accumulated Depreciation", "Asset", config.SUBTYPE_FIXED_ASSET),
    ("2000", "Accounts Payable", "Liability", config.SUBTYPE_CURRENT_LIABILITY),
    ("2100", "Income Tax Payable", "Liability", config.SUBTYPE_CURRENT_LIABILITY),
    ("2500", "Bank Loan", "Liability", config.SUBTYPE_LONG_TERM_LIABILITY),
    ("3000", "Share Capital", "Equity", config.SUBTYPE_EQUITY),
    ("4000", "Product Sales", "Revenue", config.SUBTYPE_OPERATING_REVENUE),
    ("4100", "Service Revenue", "Revenue", config.SUBTYPE_OPERATING_REVENUE),
    ("5000", "Cost of Goods Sold", "Expense", config.SUBTYPE_COST_OF_SALES),
    ("6000", "Salaries and Wages", "Expense", config.SUBTYPE_OPERATING_EXPENSE),
    ("6100", "Rent", "Expense", config.SUBTYPE_OPERATING_EXPENSE),
    ("6200", "Utilities", "Expense", config.SUBTYPE_OPERATING_EXPENSE),
    ("6300", "Marketing", "Expense", config.SUBTYPE_OPERATING_EXPENSE),
    ("6400", "Office and Supplies", "Expense", config.SUBTYPE_OPERATING_EXPENSE),
    ("6500", "Depreciation", "Expense", config.SUBTYPE_OPERATING_EXPENSE),
    ("7000", "Interest Expense", "Expense", config.SUBTYPE_FINANCIAL_EXPENSE),
    ("8000", "Income Tax Expense", "Expense", config.SUBTYPE_TAX_EXPENSE),
]

CUSTOMERS: list[str] = [
    "Aurora Foods Ltd.",
    "BlueRiver Logistics",
    "Cedar & Oak Retail",
    "Delta Pharma Sp.",
    "Eastgate Hotels",
    "Fjord Marine AS",
    "Granite Construction",
    "Helix Software",
    "Ironbridge Motors",
    "Juniper Health",
    "Kestrel Aviation",
    "Lumen Energy",
    "Meridian Textiles",
    "Nordic Timber",
    "Orchid Cosmetics",
    "Pioneer Agro",
    "Quantum Print",
    "Riverside Dental",
    "Summit Electronics",
    "Tidewater Imports",
]

SUPPLIERS: list[str] = [
    "Alpine Components",
    "Balkan Wholesale",
    "Cobalt Logistics Supplies",
    "Danube Packaging",
    "Evergreen Goods",
    "Falcon Electronics",
    "Gorge Office Supply",
    "Harbor Materials",
]

# Calendar-month demand factor (retail-like seasonality, peak in November/December).
MONTH_SEASONALITY: dict[int, float] = {
    1: 0.92, 2: 0.90, 3: 1.00, 4: 1.02, 5: 1.05, 6: 1.06,
    7: 0.98, 8: 0.90, 9: 1.04, 10: 1.08, 11: 1.12, 12: 1.18,
}  # fmt: skip

CSV_COLUMNS: dict[str, list[str]] = {
    "coa": ["account_code", "account_name", "account_type", "subtype"],
    "journal": [
        "entry_id",
        "date",
        "account_code",
        "description",
        "debit",
        "credit",
        "department",
        "reference",
        "source",
    ],
    "invoices": ["invoice_id", "customer", "issue_date", "due_date", "amount", "paid_date", "paid_amount"],
    "budget": ["period", "account_code", "budget_amount"],
    "supplier_invoices": ["invoice_id", "supplier", "issue_date", "due_date", "amount", "paid_date", "paid_amount"],
    "ground_truth": ["entry_id", "anomaly_type", "description"],
}

# Injected anomalies (per GeneratorConfig.anomalies): type -> count.
ANOMALY_COUNTS: dict[str, int] = {
    "round_amount": 2,
    "weekend_manual": 2,
    "threshold_manual": 2,
    "outlier_expense": 1,
    "duplicate_posting": 2,
}


@dataclass(frozen=True)
class GeneratorConfig:
    """Parameters of the synthetic company. Defaults produce ~2 years of activity."""

    seed: int = 42
    start: str = "2024-11-01"
    months: int = 24
    base_monthly_revenue: float = 95_000.0
    monthly_growth: float = 0.012
    cogs_ratio: float = 0.42
    base_salaries: float = 26_000.0
    rent: float = 4_200.0
    base_utilities: float = 1_800.0
    base_marketing: float = 3_500.0
    base_supplies: float = 900.0
    depreciation: float = 1_200.0
    loan_rate: float = 0.065
    loan_principal_payment: float = 1_000.0
    tax_rate: float = 0.10
    opening_cash: float = 180_000.0
    opening_equipment: float = 90_000.0
    opening_loan: float = 120_000.0
    payment_probability: float = 0.97
    invoices_min: int = 40
    invoices_max: int = 60
    supplier_invoices_min: int = 3
    supplier_invoices_max: int = 6
    budget_noise: float = 0.04
    product_share: float = 0.65
    anomalies: bool = False

    def __post_init__(self) -> None:
        if self.months < 1:
            raise ValueError("months must be at least 1")
        if not 0 < self.payment_probability <= 1:
            raise ValueError("payment_probability must be in (0, 1]")
        if self.invoices_min < 1 or self.invoices_max < self.invoices_min:
            raise ValueError("invalid invoice count range")
        if self.supplier_invoices_min < 1 or self.supplier_invoices_max < self.supplier_invoices_min:
            raise ValueError("invalid supplier invoice count range")


class _Ledger:
    """Collects balanced journal entries; ids are assigned after chronological sorting."""

    def __init__(self) -> None:
        self.entries: list[dict] = []
        self.tagged: list[tuple[str, str, str]] = []  # (anomaly type, entry index, description)

    def post(
        self,
        date: pd.Timestamp,
        description: str,
        lines: list[tuple[str, float, float, str]],
        reference: str = "",
        source: str = "system",
        tag: Optional[str] = None,
    ) -> None:
        # Round every line to cents first, so both sides are summed from the values stored.
        lines = [(account, round(float(dr), 2), round(float(cr), 2), dept) for account, dr, cr, dept in lines]
        debit = round(sum(line[1] for line in lines), 2)
        credit = round(sum(line[2] for line in lines), 2)
        assert abs(debit - credit) < 0.005, f"unbalanced entry: {description}"
        if debit == 0:  # e.g. no tax in a loss-making month: nothing to post
            return
        entry = {
            "date": date,
            "description": description,
            "lines": lines,
            "reference": reference,
            "source": source,
            "tag": tag,
        }
        self.entries.append(entry)

    def to_frame(self) -> pd.DataFrame:
        rows = []
        ordered = sorted(self.entries, key=lambda e: e["date"])  # stable: keeps posting order per day
        for number, entry in enumerate(ordered, start=1):
            entry_id = f"JE-{number:06d}"
            if entry["tag"]:
                self.tagged.append((entry["tag"], entry_id, entry["description"]))
            for account, debit, credit, dept in entry["lines"]:
                rows.append(
                    {
                        "entry_id": entry_id,
                        "date": entry["date"].strftime("%Y-%m-%d"),
                        "account_code": account,
                        "description": entry["description"],
                        "debit": round(float(debit), 2),
                        "credit": round(float(credit), 2),
                        "department": dept,
                        "reference": entry["reference"],
                        "source": entry["source"],
                    }
                )
        return pd.DataFrame(rows, columns=CSV_COLUMNS["journal"])


def _day(month_start: pd.Timestamp, day: int) -> pd.Timestamp:
    """Day *day* of the month (1-based), clipped to the last day of the month."""
    last = (month_start + pd.offsets.MonthEnd(0)).day
    return month_start + pd.Timedelta(days=min(day, last) - 1)


def _business_day(day: pd.Timestamp) -> pd.Timestamp:
    """Move a weekend date back to the preceding Friday (manual postings are made on working days)."""
    while day.weekday() >= 5:
        day = day - pd.Timedelta(days=1)
    return day


def _nth_weekday(month_start: pd.Timestamp, weekday: int, n: int) -> pd.Timestamp:
    """The n-th (1-based) occurrence of *weekday* (0 = Monday) in the month."""
    offset = (weekday - month_start.weekday()) % 7
    return month_start + pd.Timedelta(days=offset + 7 * (n - 1))


def _inject_anomalies(ledger: _Ledger, start: pd.Timestamp, supplier_rows: list[dict]) -> None:
    """Post nine known anomalies on top of the normal ledger.

    * 2 round amounts (system entries of exactly 12,000 and 5,000 on expense accounts)
    * 2 manual entries on a Saturday and a Sunday (amounts 850.40 and 620.00)
    * 2 manual entries just below the 5,000 approval threshold (4,870.00 and 4,960.50)
    * 1 expense outlier (9,137.25 on Utilities; the normal level is about 1,800)
    * 2 duplicate postings: copies of supplier-invoice postings two days after the original,
      with no supplier invoice record (so the AP sub-ledger does not include them)
    """

    def month(index: int) -> pd.Timestamp:
        return start + pd.DateOffset(months=index)

    def expense(account: str, amount: float, cash: str, dept: str) -> list[tuple[str, float, float, str]]:
        return [(account, amount, 0.0, dept), (cash, 0.0, amount, dept)]

    ledger.post(_day(month(4), 12), "Marketing agency retainer", expense("6300", 12_000.0, "1000", "Marketing"),
                "ANOM-R1", tag="round_amount")  # fmt: skip
    ledger.post(_day(month(15), 18), "Office equipment consumables", expense("6400", 5_000.0, "1000", "Administration"),
                "ANOM-R2", tag="round_amount")  # fmt: skip

    saturday = _nth_weekday(month(7), 5, 2)
    sunday = _nth_weekday(month(19), 6, 3)
    ledger.post(saturday, "Manual adjustment - office supplies", expense("6400", 850.40, "1000", "Administration"),
                "ANOM-W1", source="manual", tag="weekend_manual")  # fmt: skip
    ledger.post(sunday, "Manual adjustment - marketing materials", expense("6300", 620.00, "1000", "Marketing"),
                "ANOM-W2", source="manual", tag="weekend_manual")  # fmt: skip

    ledger.post(_business_day(_day(month(9), 10)), "Manual payment - equipment service",
                expense("6400", 4_870.00, "1000", "Administration"), "ANOM-T1", source="manual",
                tag="threshold_manual")  # fmt: skip
    ledger.post(_business_day(_day(month(21), 11)), "Manual payment - software licence",
                expense("6400", 4_960.50, "1000", "Administration"), "ANOM-T2", source="manual",
                tag="threshold_manual")  # fmt: skip

    ledger.post(_day(month(12), 9), "Utility invoice (estimate)", expense("6200", 9_137.25, "1000", "Operations"),
                "ANOM-O1", tag="outlier_expense")  # fmt: skip

    for index in (6, 17):
        key = month(index).strftime("%Y-%m")
        original = next(row for row in supplier_rows if row["issue_date"].startswith(key))
        amount = float(original["amount"])
        posted = pd.Timestamp(original["issue_date"]) + pd.Timedelta(days=2)
        ledger.post(
            posted,
            f"Supplier invoice {original['invoice_id']} - {original['supplier']}",
            [("5000", amount, 0.0, "Operations"), ("2000", 0.0, amount, "Operations")],
            original["invoice_id"],
            tag="duplicate_posting",
        )


def generate_dataset(config_: GeneratorConfig | None = None) -> dict[str, pd.DataFrame]:
    """Generate the raw tables (CSV-ready, dates as ISO strings).

    Keys: ``coa``, ``journal``, ``invoices``, ``budget``, ``supplier_invoices``, and
    ``anomaly_ground_truth`` when ``anomalies`` is enabled.
    """
    cfg = config_ or GeneratorConfig()
    rng = np.random.default_rng(cfg.seed)
    start = pd.Timestamp(cfg.start).replace(day=1)
    end = start + pd.DateOffset(months=cfg.months) - pd.Timedelta(days=1)

    ledger = _Ledger()
    invoices: list[dict] = []
    supplier_rows: list[dict] = []
    budget_rows: list[dict] = []
    tax_accrued: dict[str, float] = {}
    loan_balance = round(cfg.opening_loan, 2)

    # Opening balances, posted the day before the first month. Share capital is the
    # balancing figure: assets (cash + equipment) minus the opening loan.
    opening_cash = round(cfg.opening_cash, 2)
    opening_equipment = round(cfg.opening_equipment, 2)
    opening_loan = round(cfg.opening_loan, 2)
    opening_share_capital = round(opening_cash + opening_equipment - opening_loan, 2)
    ledger.post(
        start - pd.Timedelta(days=1),
        "Opening balances",
        [
            ("1000", opening_cash, 0.0, "Finance"),
            ("1500", opening_equipment, 0.0, "Finance"),
            ("3000", 0.0, opening_share_capital, "Finance"),
            ("2500", 0.0, opening_loan, "Finance"),
        ],
        "OPENING",
        source="manual",
    )

    for i in range(cfg.months):
        ms = start + pd.DateOffset(months=i)
        period = ms.strftime("%Y-%m")
        days_in_month = (ms + pd.offsets.MonthEnd(0)).day
        season = MONTH_SEASONALITY[ms.month]
        target_revenue = cfg.base_monthly_revenue * (1 + cfg.monthly_growth) ** i * season

        # ---- sales and receivables -------------------------------------------------
        revenue_target = target_revenue * rng.normal(1.0, 0.04)
        n_invoices = int(rng.integers(cfg.invoices_min, cfg.invoices_max + 1))
        weights = rng.gamma(2.0, 1.0, size=n_invoices)
        amounts = np.round(revenue_target * weights / weights.sum(), 2)
        # Exact product/service split per month (shuffled), so the mix is stable.
        n_product = int(round(cfg.product_share * n_invoices))
        revenue_accounts = np.array(["4000"] * n_product + ["4100"] * (n_invoices - n_product))
        rng.shuffle(revenue_accounts)

        month_revenue = 0.0
        for idx, amount in enumerate(amounts):
            amount = float(amount)
            issue = ms + pd.Timedelta(days=int(rng.integers(0, days_in_month)))
            terms = int(rng.choice([30, 30, 30, 45, 60]))
            due = issue + pd.Timedelta(days=terms)
            revenue_account = str(revenue_accounts[idx])
            customer = CUSTOMERS[int(rng.integers(len(CUSTOMERS)))]
            invoice_id = f"INV-{len(invoices) + 1:06d}"

            # Most customers pay within 75 days; some pay late (up to 150 days).
            paid_date: pd.Timestamp | None = None
            if rng.random() < cfg.payment_probability:
                delay = int(rng.integers(5, 76)) if rng.random() < 0.85 else int(rng.integers(76, 151))
                candidate = issue + pd.Timedelta(days=delay)
                if candidate <= end:
                    paid_date = candidate

            invoices.append(
                {
                    "invoice_id": invoice_id,
                    "customer": customer,
                    "issue_date": issue.strftime("%Y-%m-%d"),
                    "due_date": due.strftime("%Y-%m-%d"),
                    "amount": round(amount, 2),
                    "paid_date": paid_date.strftime("%Y-%m-%d") if paid_date is not None else "",
                    "paid_amount": round(amount, 2) if paid_date is not None else 0.0,
                }
            )
            ledger.post(
                issue,
                f"Invoice {invoice_id} - {customer}",
                [("1100", amount, 0.0, "Sales"), (revenue_account, 0.0, amount, "Sales")],
                invoice_id,
            )
            if paid_date is not None:
                ledger.post(
                    paid_date,
                    f"Payment received {invoice_id}",
                    [("1000", amount, 0.0, "Finance"), ("1100", 0.0, amount, "Finance")],
                    invoice_id,
                )
            month_revenue += amount

        # ---- cost of sales: supplier invoices (AP sub-ledger) ----------------------
        purchases = round(month_revenue * cfg.cogs_ratio * rng.normal(1.0, 0.03), 2)
        n_suppliers = int(rng.integers(cfg.supplier_invoices_min, cfg.supplier_invoices_max + 1))
        split = rng.gamma(2.0, 1.0, size=n_suppliers)
        parts = np.round(purchases * split / split.sum(), 2)
        parts[-1] = round(purchases - float(parts[:-1].sum()), 2)  # cents go to the last invoice
        for amount in parts:
            amount = float(amount)
            issue = ms + pd.Timedelta(days=int(rng.integers(0, days_in_month)))
            terms = int(rng.choice([30, 45, 60]))
            supplier = SUPPLIERS[int(rng.integers(len(SUPPLIERS)))]
            sup_id = f"SUP-{len(supplier_rows) + 1:06d}"
            paid_date = None
            if rng.random() < cfg.payment_probability:
                candidate = issue + pd.Timedelta(days=int(rng.integers(20, 71)))
                if candidate <= end:
                    paid_date = candidate
            supplier_rows.append(
                {
                    "invoice_id": sup_id,
                    "supplier": supplier,
                    "issue_date": issue.strftime("%Y-%m-%d"),
                    "due_date": (issue + pd.Timedelta(days=terms)).strftime("%Y-%m-%d"),
                    "amount": round(amount, 2),
                    "paid_date": paid_date.strftime("%Y-%m-%d") if paid_date is not None else "",
                    "paid_amount": round(amount, 2) if paid_date is not None else 0.0,
                }
            )
            ledger.post(
                issue,
                f"Supplier invoice {sup_id} - {supplier}",
                [("5000", amount, 0.0, "Operations"), ("2000", 0.0, amount, "Operations")],
                sup_id,
            )
            if paid_date is not None:
                ledger.post(
                    paid_date,
                    f"Payment to supplier {sup_id}",
                    [("2000", amount, 0.0, "Finance"), ("1000", 0.0, amount, "Finance")],
                    sup_id,
                )

        # ---- operating expenses ----------------------------------------------------
        salaries = round(cfg.base_salaries * (1.01**i) * rng.normal(1.0, 0.01), 2)
        winter = ms.month in (12, 1, 2)
        utilities = round(cfg.base_utilities * (1.25 if winter else 1.0) * rng.normal(1.0, 0.08), 2)
        marketing_factor = 1.3 if ms.month in (11, 12) else 1.0
        marketing = round(cfg.base_marketing * marketing_factor * rng.normal(1.0, 0.10), 2)
        supplies = round(cfg.base_supplies * rng.normal(1.0, 0.15), 2)
        depreciation = cfg.depreciation
        interest = round(loan_balance * cfg.loan_rate / 12, 2)
        principal = min(cfg.loan_principal_payment, loan_balance)

        pre_tax = (
            month_revenue
            - purchases
            - (salaries + cfg.rent + utilities + marketing + supplies + depreciation)
            - interest
        )
        tax = round(max(0.0, pre_tax) * cfg.tax_rate, 2)

        ledger.post(_day(ms, 1), f"Rent {period}",
                    [("6100", cfg.rent, 0.0, "Administration"), ("1000", 0.0, cfg.rent, "Administration")])  # fmt: skip
        ledger.post(_day(ms, 15), f"Utilities {period}",
                    [("6200", utilities, 0.0, "Operations"), ("1000", 0.0, utilities, "Operations")])  # fmt: skip
        ledger.post(_day(ms, 20), f"Marketing campaigns {period}",
                    [("6300", marketing, 0.0, "Marketing"), ("1000", 0.0, marketing, "Marketing")])  # fmt: skip
        ledger.post(_day(ms, 25), f"Office supplies {period}",
                    [("6400", supplies, 0.0, "Administration"), ("1000", 0.0, supplies, "Administration")])  # fmt: skip
        month_end = _day(ms, days_in_month)
        manual_day = _business_day(month_end)
        ledger.post(month_end, f"Salaries and wages {period}",
                    [("6000", salaries, 0.0, "Administration"), ("1000", 0.0, salaries, "Administration")])  # fmt: skip
        ledger.post(manual_day, f"Depreciation {period}",
                    [("6500", depreciation, 0.0, "Operations"), ("1590", 0.0, depreciation, "Operations")],
                    source="manual")  # fmt: skip
        ledger.post(manual_day, f"Loan interest {period}",
                    [("7000", interest, 0.0, "Finance"), ("1000", 0.0, interest, "Finance")],
                    source="manual")  # fmt: skip
        ledger.post(manual_day, f"Loan principal repayment {period}",
                    [("2500", principal, 0.0, "Finance"), ("1000", 0.0, principal, "Finance")],
                    source="manual")  # fmt: skip
        ledger.post(manual_day, f"Income tax accrual {period}",
                    [("8000", tax, 0.0, "Finance"), ("2100", 0.0, tax, "Finance")],
                    source="manual")  # fmt: skip
        tax_accrued[period] = tax
        loan_balance -= principal

        # Quarterly payment of tax accrued during the previous three calendar months.
        if ms.month in (1, 4, 7, 10):
            prior = [(ms - pd.DateOffset(months=k)).strftime("%Y-%m") for k in (1, 2, 3)]
            due_tax = round(sum(tax_accrued.get(p, 0.0) for p in prior), 2)
            if due_tax > 0:
                ledger.post(
                    _day(ms, 20),
                    f"Income tax payment (quarter to {prior[0]})",
                    [("2100", due_tax, 0.0, "Finance"), ("1000", 0.0, due_tax, "Finance")],
                    period,
                )

        # ---- budget (set independently of actuals) --------------------------------
        expected = {
            "4000": target_revenue * cfg.product_share,
            "4100": target_revenue * (1 - cfg.product_share),
            "5000": target_revenue * cfg.cogs_ratio,
            "6000": cfg.base_salaries * (1.01**i),
            "6100": cfg.rent,
            "6200": cfg.base_utilities * (1.25 if winter else 1.0),
            "6300": cfg.base_marketing * marketing_factor,
            "6400": cfg.base_supplies,
            "6500": cfg.depreciation,
        }
        expected["7000"] = (loan_balance + principal) * cfg.loan_rate / 12
        opex_expected = sum(expected[a] for a in ("6000", "6100", "6200", "6300", "6400", "6500"))
        pre_tax_expected = target_revenue * (1 - cfg.cogs_ratio) - opex_expected - expected["7000"]
        expected["8000"] = max(0.0, pre_tax_expected) * cfg.tax_rate
        for account, value in expected.items():
            noisy = value * rng.normal(1.0, cfg.budget_noise)
            budget_rows.append({"period": period, "account_code": account, "budget_amount": round(noisy, 2)})

    if cfg.anomalies:
        _inject_anomalies(ledger, start, supplier_rows)

    journal = ledger.to_frame()
    coa = pd.DataFrame(DEFAULT_CHART_OF_ACCOUNTS, columns=CSV_COLUMNS["coa"])
    raw: dict[str, pd.DataFrame] = {
        "coa": coa,
        "journal": journal,
        "invoices": pd.DataFrame(invoices, columns=CSV_COLUMNS["invoices"]),
        "budget": pd.DataFrame(budget_rows, columns=CSV_COLUMNS["budget"]),
        "supplier_invoices": pd.DataFrame(supplier_rows, columns=CSV_COLUMNS["supplier_invoices"]),
    }
    if cfg.anomalies:
        truth = [
            {"entry_id": entry_id, "anomaly_type": tag, "description": description}
            for tag, entry_id, description in ledger.tagged
        ]
        raw[config.GROUND_TRUTH_KEY] = pd.DataFrame(truth, columns=CSV_COLUMNS["ground_truth"])
    return raw


def write_dataset(raw: dict[str, pd.DataFrame], directory: str | Path) -> dict[str, Path]:
    """Write every table in *raw* as a CSV file and return the paths by key."""
    base = Path(directory)
    base.mkdir(parents=True, exist_ok=True)
    filenames = {
        **config.DATASET_FILES,
        **config.OPTIONAL_FILES,
        config.GROUND_TRUTH_KEY: config.ANOMALY_GROUND_TRUTH_FILE,
    }
    paths: dict[str, Path] = {}
    for key, table in raw.items():
        path = base / filenames[key]
        table.to_csv(path, index=False)
        paths[key] = path
    return paths
