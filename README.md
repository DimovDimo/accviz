# accviz: Visualization of Accounting Data

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-285%20passing-brightgreen.svg)](#testing)
[![Coverage](https://img.shields.io/badge/coverage-97%25-brightgreen.svg)](#testing)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit-ff4b4b.svg)](https://streamlit.io/)

**accviz** turns the basic accounting records of a small company chart of accounts,
general journal, sales invoices and budget into **validated financial statements, KPIs
and interactive charts**. It ships with a **Streamlit dashboard**, a **self-contained HTML
report**, a **command-line interface**, and a **deterministic synthetic data generator**
so you can explore the project without any real company data.

> accviz is an analysis and visualization tool. It is not a bookkeeping system: it does not
> post entries, file tax returns or connect to banks.

---

## Features

| Area | What you get |
|---|---|
| **Data quality** | Column checks, double-entry checks (every entry must balance), account-code checks, date and amount checks, receivables and budget consistency. Errors block analysis; warnings are shown. |
| **Financial statements** | Monthly income statement (revenue → gross profit → operating profit → net income), balance sheet at any date, trial balance, cash trend. |
| **Receivables** | Open-invoice aging (*Not yet due*, *1-30*, *31-60*, *61-90*, *90+ days*), outstanding by bucket, top customers. |
| **Budget control** | Actual vs budget per month and account, variance and variance %, favourable/unfavourable flags. |
| **KPIs & ratios** | Revenue, gross profit, net income, closing cash, receivables, total assets, revenue vs budget; gross/operating/net margin, current ratio, debt-to-equity. |
| **Charts (Plotly)** | Revenue/expense/net-income trend, margin trend, income-statement waterfall, expense donut, cash line, aging bars, budget variance bars, balance-sheet composition. Empty data shows a clear "no data" state. |
| **Dashboard** | Streamlit app with a directory or CSV-upload data source, a date-range filter, and six tabs (Overview, Income statement, Balance sheet & cash, Receivables, Budget, Data quality). |
| **HTML report** | One self-contained file (works offline) with KPIs, ratios, tables and all charts. |
| **Synthetic data** | Reproducible (seeded) double-entry data for a fictional company over 24 months, including seasonality, credit sales, late payers, bank loan, quarterly tax. |

---

## Quick start

Requirements: **Python 3.10+** (developed and tested on 3.13).

```bash
git clone <your-repo-url> accounting-visualization
cd accounting-visualization

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"            # installs accviz and the test tools
```

The repository already contains a sample dataset in `data/sample/`. Then:

```bash
accviz validate                    # check the data files
accviz summary                     # print KPIs and ratios to the console
accviz report                      # write reports/accounting_report.html
accviz dashboard                   # open the dashboard at http://localhost:8501
```

To generate a different synthetic company:

```bash
accviz generate-data --out data/my_company --seed 7 --start 2023-01-01 --months 36
accviz dashboard --data data/my_company
```

### Command reference

| Command | Purpose | Key options |
|---|---|---|
| `accviz generate-data` | Write synthetic CSV files | `--out`, `--seed`, `--start YYYY-MM-DD`, `--months` |
| `accviz validate` | Check data; exit code `0` = OK, `1` = errors | `--data` |
| `accviz summary` | Print KPIs, ratios and balance-sheet status | `--data`, `--start`, `--end` |
| `accviz report` | Write the self-contained HTML report | `--data`, `--start`, `--end`, `--out` |
| `accviz dashboard` | Start the Streamlit dashboard | `--data`, `--port` (default 8501), `--address` |

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

---

## Using the Python API

```python
from accviz.loader import read_dataset
from accviz.analysis import analyze
from accviz.report import write_report

ds = read_dataset("data/sample")                       # load + validate
result = analyze(ds, start="2025-01-01", end="2025-12-31")

print(f"Net income 2025: {result.kpis['net_income']:,.2f} EUR")
print("Balance sheet balanced:", result.balance_sheet.is_balanced())
print("Net margin:", round(result.ratios["net_margin"] * 100, 1), "%")

write_report(ds, "reports/2025.html", "2025-01-01", "2025-12-31")
```

Output of the snippet on the sample data:

```text
Net income 2025: 244,886.95 EUR
Balance sheet balanced: True
Net margin: 18.7 %
```

Every front-end (CLI, dashboard, report) calls `accviz.analysis.analyze`, so they always show
the same numbers.

---

## Data format

Place four UTF-8 CSV files with a header row in one directory. Dates use `YYYY-MM-DD`, periods
use `YYYY-MM`, and decimal points are `.`.

**`chart_of_accounts.csv`**

| column | required | notes |
|---|---|---|
| `account_code` | yes | unique, e.g. `1000` |
| `account_name` | yes | |
| `account_type` | yes | `Asset`, `Liability`, `Equity`, `Revenue`, `Expense` |
| `subtype` | yes | `Cash`, `Receivables`, `Fixed Asset`, `Current Liability`, `Long-term Liability`, `Equity`, `Operating Revenue`, `Cost of Sales`, `Operating Expense`, `Financial Expense`, `Tax Expense` |

**`journal_entries.csv`** one row per posting line; lines with the same `entry_id` form one entry.

| column | required | notes |
|---|---|---|
| `entry_id` | yes | e.g. `JE-000001` |
| `date` | yes | posting date |
| `account_code` | yes | must exist in the chart of accounts |
| `debit`, `credit` | yes | non-negative; a line has exactly one of them (empty = 0) |
| `description`, `department`, `reference` | no | free text, cost centre, external reference |

**`invoices.csv`** sales invoices for receivables aging

| column | required | notes |
|---|---|---|
| `invoice_id` | yes | unique |
| `customer` | yes | |
| `issue_date`, `due_date` | yes | `due_date` ≥ `issue_date` |
| `amount` | yes | > 0 |
| `paid_date`, `paid_amount` | no | a payment counts from `paid_date`; `paid_amount` ≤ `amount`; defaults: empty and 0 |

**`budget.csv`** monthly budget per revenue or expense account

| column | required | notes |
|---|---|---|
| `period` | yes | `YYYY-MM` |
| `account_code` | yes | a `Revenue` or `Expense` account |
| `budget_amount` | yes | ≥ 0, natural sign (revenue and expenses both positive) |

### Validation rules

*Errors* stop the analysis; *warnings* are informational.

* **Errors:** missing files or required columns · duplicate account codes or invoice IDs · invalid account types · unknown account codes · invalid dates or non-numeric amounts · negative amounts · lines with both or neither of debit/credit · **entries whose debits ≠ credits** · paid amount above invoice amount · due date before issue date · budget period not `YYYY-MM` · budget on a balance-sheet account · duplicate budget rows.
* **Warnings:** optional columns missing · subtype inconsistent with account type · missing department · entries spread over several dates · invoices with an amount paid but no payment date · empty invoice or budget tables.

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
| Aging | Days overdue = report date − due date; a payment counts only if made on or before the report date |
| Budget variance | Actual − budget. Favourable if revenue ≥ budget or expense ≤ budget. |

---

## Architecture

| Module | Responsibility |
|---|---|
| `config.py` | constants: currency (EUR), tolerances, file names, account rules |
| `validation.py` | data-quality rules returning a `ValidationResult` |
| `loader.py` | reads and normalises CSVs into an immutable `Dataset` |
| `ledger.py` | natural-sign amounts, trial balance, balances as of a date |
| `statements.py` | monthly income statement, balance sheet, cash trend, breakdowns |
| `receivables.py` | invoice-level outstanding amounts and aging buckets |
| `budget.py` | budget-versus-actual analysis |
| `ratios.py` | margins, liquidity and leverage ratios, KPI summary |
| `analysis.py` | single entry point `analyze()` used by all front-ends |
| `charts.py` | Plotly figure builders with empty-state handling |
| `report.py` | self-contained HTML report |
| `synthetic.py` | deterministic double-entry data generator and CSV writer |
| `ui.py` / `dashboard.py` | Streamlit interface (logic / script entry point) |
| `cli.py` | command-line interface |

The analytics layer does not depend on Streamlit or on the file system (except the loader),
which keeps it easy to test and reuse.

Project layout:

```
accounting-visualization/
├── README.md
├── pyproject.toml              # packaging, pytest and coverage configuration
├── requirements.txt            # runtime dependencies
├── requirements-dev.txt        # + test and lint tools
├── data/sample/                # synthetic dataset (24 months, 1,147 invoices, 4,934 journal lines)
├── docs/
│   ├── RESEARCH.md             # how such projects are built (sources)
│   ├── PLAN.md                 # execution plan, milestones, risks
│   └── REQUIREMENTS.md         # technical requirements and data specification
├── src/accviz/                 # the package (see table above)
└── tests/
    ├── factories.py            # hand-computed fixture company
    ├── conftest.py             # shared fixtures and layer markers
    ├── unit/                   # 151 tests one module each
    ├── integration/            # pipeline, CLI, sample data, Streamlit UI tests
    ├── property/               # accounting invariants over random companies
    └── performance/            # timing limits (24 months < 10 s)
```

---

## Testing

```bash
pytest                                    # run everything (about 30 s)
pytest -m unit                            # fast, isolated module tests
pytest -m "integration and not ui"        # pipeline and CLI tests
pytest -m ui                              # Streamlit dashboard tests (AppTest, no browser)
pytest -m property                        # invariants over random companies
pytest --cov=accviz --cov-report=term-missing   # coverage report
ruff check src tests                      # lint
```

| Layer | What it proves | Examples |
|---|---|---|
| **Unit** (151) | Each rule and formula in isolation | Every validation rule; aging bucket boundaries; natural-sign signs; income statement by month |
| **Hand-computed** | Numbers match a calculation done on paper | `tests/factories.py` describes a 2-month company; expected net income 430, balance sheet 1,470 = 1,430 |
| **Integration** (in `integration/`) | Layers work together | CSV round trip; AR sub-ledger equals the GL control account at every month end; CLI exit codes; report contents |
| **UI** | Dashboard renders, filters and shows errors | Six tabs, KPI metrics, period filter, reversed-date error, upload mode, corrupt-data messages |
| **Property** | Accounting rules hold for random companies | Balanced entries, balanced trial balance, accounting equation at every month end, reconciliation |
| **Performance** | Speed limits (NFR-02) | 24 months generated, analysed and reported within limits |

Current result: **285 tests pass; line coverage 97 %** (branch coverage is also measured).
The only file below 90 % is the 5-line Streamlit entry script `dashboard.py`, whose logic
lives in `ui.py` and is covered by the UI tests.

Bugs found and fixed during testing include: duplicate account codes crashing the budget
check, zero-value tax accruals creating invalid journal lines, and per-line rounding in the
generator producing one-cent imbalances.

---

## Documentation

* [`docs/RESEARCH.md`](docs/RESEARCH.md) how accounting-visualization projects are built, with sources
* [`docs/PLAN.md`](docs/PLAN.md) phases, milestones, risks and definition of done
* [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) technical requirements, data specification and acceptance criteria

---

## Limitations and roadmap

* No VAT / sales-tax handling; amounts are net and single-currency (EUR by default; set `CURRENCY` in `config.py`).
* Receivables only; accounts payable aging and a cash-flow statement (indirect method) are planned.
* Synthetic data only ships with the repository. Real bank or ERP exports need a mapping to the four-file format.
* The dashboard is designed for a single user; there is no authentication.
* Budgets are monthly, at account level, with no cost-centre dimension yet (the `department` column is kept for future drill-downs).

## Contributing

1. Write a failing test first (unit tests go in `tests/unit/`, cross-layer tests in `tests/integration/`).
2. Implement the change; keep analytics free of Streamlit imports.
3. Run `pytest` and `ruff check src tests` before opening a pull request.
