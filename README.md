# accviz: Visualization of Accounting Data

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-530%20collected-brightgreen.svg)](#testing)
[![Coverage](https://img.shields.io/badge/coverage-%E2%89%A595%25%20gate-brightgreen.svg)](#testing)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit-ff4b4b.svg)](https://streamlit.io/)
[![Version](https://img.shields.io/badge/version-1.1.0-informational.svg)](CHANGELOG.md)

**accviz** turns the basic accounting records of a small company chart of accounts, general
journal, sales and supplier invoices and budget into **validated financial statements, a cash
flow statement, KPIs, audit analytics, a revenue forecast and interactive charts**.

It ships with a **Streamlit dashboard**, a **multi-sheet Excel export**, a **self-contained HTML
report**, a **command-line interface**, and a **deterministic synthetic data generator** that can
also plant known journal anomalies so the audit rules can be scored.

> accviz is an analysis and visualization tool. It is not a bookkeeping system: it does not post
> entries, file tax returns or connect to banks.

---

## Contents

- [Features](#features)
- [Quick start](#quick-start)
- [Security defaults](#security-defaults)
- [Dashboard tabs](#dashboard-tabs)
- [Data format](#data-format)
- [Financial definitions](#financial-definitions)
- [Journal audit analytics](#journal-audit-analytics)
- [Revenue forecast](#revenue-forecast)
- [Excel export](#excel-export)
- [Using the Python API](#using-the-python-api)
- [Architecture](#architecture)
- [Testing](#testing)
- [Documentation](#documentation)
- [Limitations and roadmap](#limitations-and-roadmap)
- [Contributing](#contributing)

---

## Features

| Area | What you get |
|---|---|
| **Data quality** | Column checks, double-entry checks (every entry must balance), account-code checks, date and amount checks, receivables, payables and budget consistency. Errors block analysis; warnings are shown. |
| **Financial statements** | Monthly income statement, balance sheet at any date, trial balance, cash trend. |
| **Cash flow (v1.1)** | Direct-method cash flow statement, monthly and for any period. Opening cash plus net flows reconciles to the GL cash balance (difference shown as 0.00). |
| **Receivables** | Open-invoice aging (*Not yet due*, *1-30*, *31-60*, *61-90*, *90+ days*), top customers, reconciliation to GL 1100. |
| **Payables (v1.1)** | Supplier-invoice aging from an optional `supplier_invoices.csv`, top suppliers, reconciliation to GL 2000. Duplicate postings show up as a difference. |
| **Journal audit (v1.1)** | Rules for round amounts, weekend manual entries, approval-threshold proximity, expense outliers (robust z-score), possible duplicate postings and a Benford first-digit test. Ground-truth scoring on the demo dataset. |
| **Cost centres (v1.1)** | Expenses by department and month, with shares. |
| **Forecast (v1.1)** | Revenue forecast (linear trend, times a seasonal index once 24 months are available), 95 % band and a holdout MAPE backtest. |
| **Budget control** | Actual vs budget per month and account, variance and variance %, favourable/unfavourable flags. |
| **KPIs & ratios** | Revenue, gross profit, net income, closing cash, receivables, total assets, revenue vs budget; gross/operating/net margin, current ratio, debt-to-equity. |
| **Excel export (v1.1)** | 11-sheet, formatted `.xlsx` workbook (openpyxl), from the CLI or the dashboard sidebar. |
| **Charts (Plotly)** | Revenue/expense/net-income trend, margins, income-statement waterfall, expense donut, cash flow bars, cash line, aging bars, forecast band, cost-centre bars, audit bars, budget variance, balance-sheet composition. Empty data shows a clear "no data" state. |
| **Dashboard** | Streamlit app with a directory or CSV-upload data source, a date-range filter, nine tabs and an Excel download. |
| **HTML report** | One self-contained file (no external scripts; works offline) with KPIs, ratios, tables and all charts. |
| **Synthetic data** | Reproducible (seeded) double-entry data for a fictional company over 24 months: seasonality, credit sales, late payers, supplier invoices with payment terms, bank loan, quarterly tax. An `--anomalies` option plants nine known journal anomalies. |

---

## Quick start

Requirements: **Python 3.10+** (developed and tested on 3.13).

```bash
git clone <your-repo-url> accounting-visualization
cd accounting-visualization

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"            # installs accviz and the test and lint tools
```

The repository already contains two synthetic datasets: `data/sample/` (clean) and
`data/demo_anomalies/` (with planted anomalies and a ground-truth file). Then:

```bash
accviz validate                                  # check the data files
accviz summary                                   # KPIs, cash flow and reconciliation status
accviz audit --data data/demo_anomalies          # journal audit with ground-truth scores
accviz export                                    # write reports/accounting_workbook.xlsx (11 sheets)
accviz report                                    # write reports/accounting_report.html
accviz dashboard                                 # http://127.0.0.1:8501 (localhost only)
```

To generate a different synthetic company:

```bash
accviz generate-data --out data/my_company --seed 7 --start 2023-01-01 --months 36
accviz generate-data --anomalies --out data/demo --seed 42     # with planted anomalies
accviz dashboard --data data/my_company
```

### Command reference

| Command | Purpose | Key options |
|---|---|---|
| `accviz generate-data` | Write synthetic CSV files | `--out`, `--seed`, `--start YYYY-MM-DD`, `--months`, `--anomalies` |
| `accviz validate` | Check data; exit `0` = OK, `1` = errors | `--data` |
| `accviz summary` | Print KPIs, ratios, cash flow and reconciliations | `--data`, `--start`, `--end` |
| `accviz audit` | Run the journal audit rules and the Benford test | `--data`, `--start`, `--end`, `--top` (default 15) |
| `accviz export` | Write the analysis to a multi-sheet Excel workbook | `--data`, `--start`, `--end`, `--out` (default `reports/accounting_workbook.xlsx`) |
| `accviz report` | Write the self-contained HTML report | `--data`, `--start`, `--end`, `--out` |
| `accviz dashboard` | Start the Streamlit dashboard | `--data`, `--port` (default 8501), `--address` (default `127.0.0.1`) |

Exit codes: `0` success · `1` validation failed · `2` usage or I/O error.
You can also run the CLI as `python -m accviz …`.

Example of a validation failure:

```text
$ accviz validate --data broken/
Errors: 2
Warnings: 0
  ERROR   journal_entries.csv: line has both debit and credit (entry JE-000100)
  ERROR   journal_entries.csv: 1 unbalanced entr(y/ies) (debits ≠ credits): JE-000100

Validation FAILED: fix the errors above.
```

Example of the audit output on the demo dataset (abridged):

```text
$ accviz audit --data data/demo_anomalies
Journal audit for 2024-10-31 to 2026-10-31
Entries tested: 2,856  (manual: 100, 3.5%)
...
Benford first digits: 5,548 amounts, chi-square 182.2 (critical 15.507), MAD 0.0183: non-conformity
...
Ground truth: detected 100% of injected anomalies; false positives: 2
  round_amount          2 of 2
  weekend_manual        2 of 2
  threshold_manual      2 of 2
  outlier_expense       1 of 1
  duplicate_posting     2 of 2
```

---

## Security defaults

* The dashboard and the CLI dashboard command bind to **`127.0.0.1`** by default. Other machines
  cannot reach the dashboard unless you ask for it.
* To expose the dashboard on the network (for example in a container or a hosted preview), start
  it explicitly: `accviz dashboard --address 0.0.0.0`. The dashboard has **no authentication**;
  only do this on a network you trust, or put it behind a reverse proxy that handles login.
* The HTML report and the Excel file are written to local paths you choose; they contain the
  full analysis, so treat them like the source data.

---

## Dashboard tabs

| Tab | Shows |
|---|---|
| **Overview** | KPI tiles, revenue/expense/net-income trend, margins |
| **Income statement** | Monthly statement, waterfall, expense breakdown |
| **Cash flow** | Direct-method statement (operating, investing, financing), monthly bars, reconciliation to GL cash |
| **Balance sheet** | Balance sheet at the period end, composition, cash line |
| **Receivables & payables** | AR and AP aging, top customers and suppliers, sub-ledger reconciliations |
| **Budget** | Actual vs budget and variance by account and month |
| **Forecast** | Revenue forecast with 95 % band, horizon slider (3-12 months) |
| **Audit** | Findings by rule and severity, the finding list, Benford test (ground-truth scores are printed by `accviz audit`) |
| **Data quality** | Validation errors and warnings, row counts per table |

The sidebar offers the data source (directory or CSV upload), the period filter and the
**Excel download** button.

---

## Data format

Place UTF-8 CSV files with a header row in one directory. Dates use `YYYY-MM-DD`, periods use
`YYYY-MM`, and decimal points are `.`.

Four files are required. `supplier_invoices.csv` and the journal `source` column are optional,
so v1.0 datasets still load (with warnings).

**`chart_of_accounts.csv`** (required)

| column | required | notes |
|---|---|---|
| `account_code` | yes | unique, e.g. `1000` |
| `account_name` | yes | |
| `account_type` | yes | `Asset`, `Liability`, `Equity`, `Revenue`, `Expense` |
| `subtype` | yes | `Cash`, `Receivables`, `Fixed Asset`, `Current Liability`, `Long-term Liability`, `Equity`, `Operating Revenue`, `Cost of Sales`, `Operating Expense`, `Financial Expense`, `Tax Expense` |

**`journal_entries.csv`** (required) one row per posting line; lines with the same `entry_id` form one entry.

| column | required | notes |
|---|---|---|
| `entry_id` | yes | e.g. `JE-000001` |
| `date` | yes | posting date |
| `account_code` | yes | must exist in the chart of accounts |
| `debit`, `credit` | yes | non-negative; a line has exactly one of them (empty = 0) |
| `description`, `department`, `reference` | no | free text, cost centre, external reference |
| `source` | no (v1.1) | `system` or `manual`. Missing or blank means `system`. Drives the manual-entry audit rules. |

**`invoices.csv`** (required) sales invoices for receivables aging

| column | required | notes |
|---|---|---|
| `invoice_id` | yes | unique |
| `customer` | yes | |
| `issue_date`, `due_date` | yes | `due_date` ≥ `issue_date` |
| `amount` | yes | > 0 |
| `paid_date`, `paid_amount` | no | a payment counts from `paid_date`; `paid_amount` ≤ `amount`; defaults: empty and 0 |

**`supplier_invoices.csv`** (optional, v1.1) purchase invoices for payables aging

| column | required | notes |
|---|---|---|
| `invoice_id` | yes | unique |
| `supplier` | yes | |
| `issue_date`, `due_date` | yes | `due_date` ≥ `issue_date` |
| `amount` | yes | > 0 |
| `paid_date`, `paid_amount` | no | as for sales invoices; a payment counts from `paid_date` |

**`budget.csv`** (required) monthly budget per revenue or expense account

| column | required | notes |
|---|---|---|
| `period` | yes | `YYYY-MM` |
| `account_code` | yes | a `Revenue` or `Expense` account |
| `budget_amount` | yes | ≥ 0, natural sign (revenue and expenses both positive) |

**`anomaly_ground_truth.csv`** (optional, written by `generate-data --anomalies`) the planted
anomalies, used only to score the audit: `entry_id`, `anomaly_type`, `description`.

### Validation rules

*Errors* stop the analysis; *warnings* are informational.

* **Errors:** missing required files or columns · duplicate account codes or invoice IDs (sales or supplier) · invalid account types · unknown account codes · invalid dates or non-numeric amounts · negative amounts · lines with both or neither of debit/credit · **entries whose debits ≠ credits** · paid amount above invoice amount · due date before issue date · `source` not `system` or `manual` · budget period not `YYYY-MM` · budget on a balance-sheet account · duplicate budget rows.
* **Warnings:** optional files or columns missing (for example `supplier_invoices.csv` or `source`) · optional file present but empty · subtype inconsistent with account type · missing department · entries spread over several dates · invoices with an amount paid but no payment date · empty invoice or budget tables.

---

## Financial definitions

| Measure | Definition |
|---|---|
| Natural balance | Debit-normal accounts (assets, expenses): `debit − credit`. Credit-normal accounts (liabilities, equity, revenue): `credit − debit`. |
| Gross profit | Revenue − cost of sales |
| Operating profit | Gross profit − operating expenses (incl. depreciation) |
| Net income | Operating profit − financial expenses − tax expense |
| Balance sheet | Equity = share capital + cumulative net income. Assets must equal liabilities + equity (checked at every date). |
| Gross / operating / net margin | Profit line ÷ revenue |
| Current ratio | Current assets (cash + receivables) ÷ current liabilities |
| Debt-to-equity | Total liabilities ÷ total equity |
| Aging (AR and AP) | Days overdue = report date − due date; a payment counts only if made on or before the report date |
| Budget variance | Actual − budget. Favourable if revenue ≥ budget or expense ≤ budget. |
| **Cash flow (direct method)** | Each cash line is classified by its *counterpart* account: fixed-asset accounts are **investing**; long-term liability and equity accounts are **financing**; everything else is **operating**. Each non-cash line contributes −(debit − credit) to the cash flow of its counterpart. |
| Opening balance | Entries whose description contains "opening balance" (any case) are treated as opening cash, not as period flows. |
| **Cash reconciliation** | Opening cash + operating + investing + financing must equal the GL cash balance at the period end. |
| **Sub-ledger reconciliation** | GL 1100 (receivables) vs the open sales invoices; GL 2000 (payables) vs the open supplier invoices. A difference is reported and explained. |

---

## Journal audit analytics

The audit (v1.1, requirement group AU) tests journal entries against rules that accounting
teams commonly use in journal-entry testing. Each rule is an *indicator*: a finding means
"look at this", not "this is wrong". Opening-balance entries are never tested.

| Rule | Applies to | Parameter | Severity |
|---|---|---|---|
| Round amount | Any line | amount ≥ 5,000 and an exact multiple of 1,000 | medium |
| Manual entry on a weekend | Manual entries only | dated Saturday or Sunday | low |
| Just below approval threshold | Manual entries only | line in [4,750; 5,000), i.e. within 5 % below the approval limit | medium |
| Expense outlier | Expense lines, per account | robust z-score ≥ 4.0 (median and MAD based), at least 5 observations per account | high |
| Possible duplicate posting | Same account, same side, same amount | a different entry within 7 days of an earlier one | high |
| Benford first digits | All amounts (recurring amounts excluded) | chi-square over the first digits, df 8, critical value 15.507 (α = 0.05), plus MAD conformity | informational |

Design choices:

* **Timing rules look at manual entries only.** System-generated postings (invoices, payments)
  have random dates in the synthetic data, so flagging their weekend dates would be noise.
* **Duplicates compare the same side only.** An invoice (debit receivable) and its payment
  (credit receivable) share an account and an amount but are not duplicates.
* **Benford is an indicator, not a verdict.** Recurring fixed amounts (rent, depreciation) break
  the law, so they are excluded. The synthetic amounts cover about one decade, which also gives
  non-conformity. The synthetic generator is *not* tuned to pass the test. The unit tests show
  the test accepts a log-uniform population over several decades and rejects a narrow uniform one.

### Results

| Dataset | Entries tested | Manual entries | Findings | Benford | Ground truth |
|---|---|---|---|---|---|
| `data/sample` (clean) | 2,847 | 96 (3.4 %) | 2 | χ² 188.3, non-conformity | n/a |
| `data/demo_anomalies` | 2,856 | 100 (3.5 %) | 15 | χ² 182.2, non-conformity | **9 of 9 detected** (2 false positives) |

* On the **sample**, the two findings are large cost-of-sales supplier invoices (JE-002140, 30,812.03,
  z = 4.0; JE-002612, 34,216.84, z = 4.6). They are genuine large invoices in the synthetic data,
  so they are reported rather than suppressed.
* On the **demo**, all nine planted anomalies are found: two round amounts, two weekend manual
  entries, two threshold manual entries, one expense outlier and two duplicate postings. The
  two false positives are the same large cost-of-sales invoices as in the sample.
* The duplicate postings also show in the AP reconciliation: GL 2000 is 121,198.20 while the open
  supplier invoices total 90,179.56. The difference of **31,018.64** equals the two duplicate
  amounts exactly.

---

## Revenue forecast

* Linear trend fitted to monthly revenue by least squares.
* With **at least 24 months** of history, a multiplicative seasonal index for each calendar month
  is estimated. Trend and indices are refined alternately, so the seasonal pattern does not
  leak into the trend slope.
* The 95 % band is the point forecast ± 1.96 × the residual standard deviation, with the lower
  bound floored at zero.
* Accuracy is shown as the **holdout MAPE**: the last *k* months are withheld, the model is fitted
  on the rest, and the forecast is compared with the actual values.

On the sample (24 months, seasonal model) the next six months are forecast as:

| Period | Forecast | 95 % band |
|---|---|---|
| 2026-11 | 145,107 | 138,967 151,246 |
| 2026-12 | 153,793 | 147,654 159,933 |
| 2027-01 | 118,394 | 112,254 124,533 |
| 2027-02 | 120,255 | 114,115 126,394 |
| 2027-03 | 128,822 | 122,683 134,962 |
| 2027-04 | 140,089 | 133,950 146,229 |

The six-month holdout MAPE is **6.98 %** against the planned target of under 8 %. Note that this
backtest trains on 18 months, below the 24 months needed for seasonality, so it uses the trend
model only. The seasonal model is used for the live forecast.

---

## Excel export

`accviz export` (or the **Excel download** in the dashboard sidebar) writes one workbook with
eleven sheets, each with a bold header, frozen header row, column widths and number formats
(money to cents, percentages, dates):

`Summary` · `Income statement` · `Cash flow` · `Balance sheet` · `Trial balance` ·
`Receivables aging` · `Payables aging` · `Budget variance` · `Departments` · `Forecast` ·
`Audit findings`

The file is a standard `.xlsx` written with openpyxl.

---

## Using the Python API

```python
from accviz.loader import read_dataset
from accviz.analysis import analyze
from accviz.export import export_workbook
from accviz.report import write_report

ds = read_dataset("data/sample")                        # load + validate
result = analyze(ds, start="2025-01-01", end="2025-12-31")

print(f"Net income 2025: {result.kpis['net_income']:,.2f} EUR")
print("Balance sheet balanced:", result.balance_sheet.is_balanced())
print("Cash flow reconciled:", result.cash_flow.is_reconciled())
print("Net margin:", round(result.ratios["net_margin"] * 100, 1), "%")
print("Audit findings:", result.audit.total_findings)

export_workbook(ds, "reports/2025.xlsx", "2025-01-01", "2025-12-31")
write_report(ds, "reports/2025.html", "2025-01-01", "2025-12-31")
```

Every front-end (CLI, dashboard, report, workbook) calls `accviz.analysis.analyze`, so they always
show the same numbers. The analytics layer does not import Streamlit.

---

## Architecture

| Module | Responsibility |
|---|---|
| `config.py` | constants: currency (EUR), tolerances, file names, opening-balance marker, bind address |
| `validation.py` | data-quality rules returning a `ValidationResult` |
| `loader.py` | reads and normalises CSVs (including optional files) into an immutable `Dataset` |
| `ledger.py` | natural-sign amounts, trial balance, balances as of a date |
| `statements.py` | monthly income statement, balance sheet, cash trend, breakdowns |
| `receivables.py` | invoice-level outstanding amounts and AR aging buckets |
| `payables.py` | supplier-invoice AP aging, top suppliers, totals |
| `reconciliation.py` | GL control accounts against their sub-ledgers (AR and AP) |
| `cashflow.py` | direct-method cash flow statement and monthly table |
| `audit.py` | journal audit rules, Benford test, ground-truth scoring |
| `forecast.py` | trend and seasonal revenue forecast, holdout backtest |
| `departments.py` | expenses by cost centre and month |
| `budget.py` | budget-versus-actual analysis |
| `ratios.py` | margins, liquidity and leverage ratios, KPI summary |
| `analysis.py` | single entry point `analyze()` used by all front-ends |
| `charts.py` | Plotly figure builders with empty-state handling |
| `export.py` | formatted multi-sheet Excel workbook (openpyxl) |
| `report.py` | self-contained HTML report |
| `synthetic.py` | deterministic double-entry data generator, anomaly injection and CSV writer |
| `ui.py` / `dashboard.py` | Streamlit interface (logic / script entry point) |
| `cli.py` | command-line interface |

Project layout:

```
accounting-visualization/
├── README.md
├── CHANGELOG.md
├── pyproject.toml              # packaging, pytest, ruff and coverage configuration
├── requirements.txt            # runtime dependencies
├── requirements-dev.txt        # + test and lint tools
├── .github/workflows/ci.yml    # lint, tests with coverage gate, sample build
├── data/
│   ├── sample/                 # synthetic dataset (24 months, clean)
│   └── demo_anomalies/         # same company with 9 planted anomalies + ground truth
├── docs/
│   ├── RESEARCH.md, PLAN.md, REQUIREMENTS.md                   # v1.0
│   └── IMPROVEMENTS_RESEARCH.md, IMPROVEMENTS_PLAN.md,
│       IMPROVEMENTS_REQUIREMENTS.md                            # v1.1
├── reports/                    # generated HTML report and Excel workbook
├── src/accviz/                 # the package (see table above)
└── tests/
    ├── factories.py            # hand-computed fixture company
    ├── conftest.py             # shared fixtures and layer markers
    ├── unit/                   # one module per file
    ├── integration/            # pipeline, CLI, sample data, backward compatibility, Streamlit UI
    ├── property/               # accounting invariants over random companies
    └── performance/            # timing limits
```

---

## Testing

```bash
pytest                                          # everything, with the coverage gate from pyproject.toml
pytest -m unit                                  # fast, isolated module tests
pytest -m "integration and not ui"              # pipeline, CLI and data tests
pytest -m ui                                    # Streamlit dashboard tests (AppTest, no browser)
pytest -m property                              # invariants over random companies
pytest -m performance                           # timing limits
pytest --cov=accviz --cov-report=term-missing   # coverage report
ruff check src tests                            # lint
```

| Layer | What it proves | Examples |
|---|---|---|
| **Unit** | Each rule and formula in isolation | Every validation rule; aging buckets; natural-sign signs; each audit rule at its threshold boundary; Benford calibration; forecast trend and seasonal recovery; Excel formats |
| **Hand-computed** | Numbers match a calculation done on paper | `tests/factories.py` describes a 2-month company; expected net income 430, balance sheet 1,470 = 1,430, cash flow 1,200 |
| **Integration** | Layers work together | CSV round trip; sub-ledgers reconcile at every month end; demo ground truth fully detected; AP difference equals duplicates; CLI exit codes and outputs; report sections; v1.0 layout still analyses |
| **UI** | Dashboard renders, filters and shows errors | Nine tabs, forecast slider, audit tab, period filter, reversed-date error, upload mode |
| **Property** | Accounting rules hold for random companies | Balanced entries, trial balance, accounting equation at every month end, cash flow reconciles at every month, sub-ledgers reconcile, anomaly recall |
| **Performance** | Speed limits (NFR-02, NFR-11) | 24 months generated, analysed with audit and forecast, and exported within limits |

Current result: **529 tests pass, 1 skipped by design** (a random company with under three months of
revenue, where forecasting is not defined); **line coverage 96.8 %** against a 95 % gate.

Bugs found and fixed during the v1.1 testing round include: an empty-supplier-file state that
hid its warning; the seasonal forecast leaking the seasonal pattern into the trend; the
ground-truth score counting anomalies outside the audited period as misses; and a negative-zero
percentage shown as "-0.0 %".

### Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request, on Python 3.12 and 3.13:

1. `ruff check src tests`
2. `accviz validate` on both committed datasets
3. `pytest` with the coverage gate (`fail_under = 95` in `pyproject.toml`)
4. `accviz export` and `accviz report` on the sample data

---

## Documentation

* [`CHANGELOG.md`](CHANGELOG.md) what changed in each release
* [`docs/RESEARCH.md`](docs/RESEARCH.md), [`docs/PLAN.md`](docs/PLAN.md), [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) v1.0 research, plan and requirements
* [`docs/IMPROVEMENTS_RESEARCH.md`](docs/IMPROVEMENTS_RESEARCH.md), [`docs/IMPROVEMENTS_PLAN.md`](docs/IMPROVEMENTS_PLAN.md), [`docs/IMPROVEMENTS_REQUIREMENTS.md`](docs/IMPROVEMENTS_REQUIREMENTS.md) v1.1 research, plan, requirements and acceptance criteria

---

## Limitations and roadmap

* **Planned for v1.2:** several payments against one invoice (R9). The v1.1 model allows one payment per invoice.
* **Not planned yet:** VAT and sales-tax handling (R10), multi-currency (amounts are EUR by default; set `CURRENCY` in `config.py`).
* The audit rules are **indicators**. The Benford test is weak on data spanning one decade, and the outlier rule flags large legitimate invoices. Review every finding before drawing a conclusion.
* The forecast is a simple trend-and-season model, with no external drivers and no confidence beyond the residual band.
* Synthetic data ships with the repository. Real bank or ERP exports need a mapping to the CSV format above.
* The dashboard is for a single user and has no authentication (see [Security defaults](#security-defaults)).
* Budgets are monthly and at account level. The `department` column gives a cost-centre view of expenses only.

## Contributing

1. Write a failing test first (unit tests in `tests/unit/`, cross-layer tests in `tests/integration/`).
2. Implement the change; keep analytics free of Streamlit imports.
3. Run `pytest` and `ruff check src tests` before opening a pull request.
4. Add an entry to `CHANGELOG.md`.
