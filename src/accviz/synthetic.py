"""Deterministic generator of synthetic, double-entry-consistent accounting data.

The generated company ("Northwind Trading Ltd.", fictional) sells goods and services,
buys stock on credit, pays salaries, rent, utilities, marketing, interest and a 10 %
corporate income tax paid quarterly. Every journal entry is balanced by construction,
and the receivables sub-ledger is consistent with the AR control account.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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

# Calendar-month demand factor (retail-like seasonality, peak in November/December).
MONTH_SEASONALITY: dict[int, float] = {
    1: 0.92, 2: 0.90, 3: 1.00, 4: 1.02, 5: 1.05, 6: 1.06,
    7: 0.98, 8: 0.90, 9: 1.04, 10: 1.08, 11: 1.12, 12: 1.18,
}  # fmt: skip

CSV_COLUMNS: dict[str, list[str]] = {
    "coa": ["account_code", "account_name", "account_type", "subtype"],
    "journal": ["entry_id", "date", "account_code", "description", "debit", "credit", "department", "reference"],
    "invoices": ["invoice_id", "customer", "issue_date", "due_date", "amount", "paid_date", "paid_amount"],
    "budget": ["period", "account_code", "budget_amount"],
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
    budget_noise: float = 0.04
    product_share: float = 0.65

    def __post_init__(self) -> None:
        if self.months < 1:
            raise ValueError("months must be at least 1")
        if not 0 < self.payment_probability <= 1:
            raise ValueError("payment_probability must be in (0, 1]")
        if self.invoices_min < 1 or self.invoices_max < self.invoices_min:
            raise ValueError("invalid invoice count range")


class _Ledger:
    """Collects balanced journal entries; ids are assigned after chronological sorting."""

    def __init__(self) -> None:
        self.entries: list[dict] = []

    def post(
        self,
        date: pd.Timestamp,
        description: str,
        lines: list[tuple[str, float, float, str]],
        reference: str = "",
    ) -> None:
        # Round every line to cents first, so both sides are summed from the values stored.
        lines = [(account, round(float(dr), 2), round(float(cr), 2), dept) for account, dr, cr, dept in lines]
        debit = round(sum(line[1] for line in lines), 2)
        credit = round(sum(line[2] for line in lines), 2)
        assert abs(debit - credit) < 0.005, f"unbalanced entry: {description}"
        if debit == 0:  # e.g. no tax in a loss-making month: nothing to post
            return
        self.entries.append({"date": date, "description": description, "lines": lines, "reference": reference})

    def to_frame(self) -> pd.DataFrame:
        rows = []
        ordered = sorted(self.entries, key=lambda e: e["date"])  # stable: keeps posting order per day
        for number, entry in enumerate(ordered, start=1):
            entry_id = f"JE-{number:06d}"
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
                    }
                )
        return pd.DataFrame(rows, columns=CSV_COLUMNS["journal"])


def _day(month_start: pd.Timestamp, day: int) -> pd.Timestamp:
    """Day *day* of the month (1-based), clipped to the last day of the month."""
    last = (month_start + pd.offsets.MonthEnd(0)).day
    return month_start + pd.Timedelta(days=min(day, last) - 1)


def generate_dataset(config_: GeneratorConfig | None = None) -> dict[str, pd.DataFrame]:
    """Generate the four raw tables (CSV-ready, dates as ISO strings)."""
    cfg = config_ or GeneratorConfig()
    rng = np.random.default_rng(cfg.seed)
    start = pd.Timestamp(cfg.start).replace(day=1)
    end = start + pd.DateOffset(months=cfg.months) - pd.Timedelta(days=1)

    ledger = _Ledger()
    invoices: list[dict] = []
    budget_rows: list[dict] = []
    tax_accrued: dict[str, float] = {}
    loan_balance = round(cfg.opening_loan, 2)
    purchases_prev = 0.0

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

        # ---- cost of sales and supplier payments ----------------------------------
        purchases = round(month_revenue * cfg.cogs_ratio * rng.normal(1.0, 0.03), 2)
        ledger.post(
            _day(ms, 14),
            f"Stock purchases {period}",
            [("5000", purchases, 0.0, "Operations"), ("2000", 0.0, purchases, "Operations")],
            period,
        )
        if purchases_prev > 0:
            ledger.post(
                _day(ms, 5),
                f"Supplier payments for {(ms - pd.DateOffset(months=1)).strftime('%Y-%m')}",
                [("2000", purchases_prev, 0.0, "Finance"), ("1000", 0.0, purchases_prev, "Finance")],
                period,
            )
        purchases_prev = purchases

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
        ledger.post(month_end, f"Salaries and wages {period}",
                    [("6000", salaries, 0.0, "Administration"), ("1000", 0.0, salaries, "Administration")])  # fmt: skip
        ledger.post(month_end, f"Depreciation {period}",
                    [("6500", depreciation, 0.0, "Operations"), ("1590", 0.0, depreciation, "Operations")])  # fmt: skip
        ledger.post(month_end, f"Loan interest {period}",
                    [("7000", interest, 0.0, "Finance"), ("1000", 0.0, interest, "Finance")])  # fmt: skip
        ledger.post(month_end, f"Loan principal repayment {period}",
                    [("2500", principal, 0.0, "Finance"), ("1000", 0.0, principal, "Finance")])  # fmt: skip
        ledger.post(month_end, f"Income tax accrual {period}",
                    [("8000", tax, 0.0, "Finance"), ("2100", 0.0, tax, "Finance")])  # fmt: skip
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

    journal = ledger.to_frame()
    coa = pd.DataFrame(DEFAULT_CHART_OF_ACCOUNTS, columns=CSV_COLUMNS["coa"])
    return {
        "coa": coa,
        "journal": journal,
        "invoices": pd.DataFrame(invoices, columns=CSV_COLUMNS["invoices"]),
        "budget": pd.DataFrame(budget_rows, columns=CSV_COLUMNS["budget"]),
    }


def write_dataset(raw: dict[str, pd.DataFrame], directory: str | Path) -> dict[str, Path]:
    """Write the four tables as CSV files and return their paths."""
    base = Path(directory)
    base.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for key, filename in config.DATASET_FILES.items():
        path = base / filename
        raw[key].to_csv(path, index=False)
        paths[key] = path
    return paths

