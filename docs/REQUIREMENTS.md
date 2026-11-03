# Requirements: accviz

## 1. Scope

accviz turns the four basic accounting datasets of a small company (chart of accounts,
general journal, sales invoices and budget) into validated financial statements, KPIs and
interactive visualizations. It is an analysis and visualization tool. It is **not** a
bookkeeping system: it does not post entries, file tax returns or connect to banks.

## 2. Technical requirements

| Area | Requirement |
|---|---|
| Language | Python 3.10 or newer (developed and tested on 3.13) |
| Core libraries | `pandas >= 2.0`, `numpy >= 1.24`, `plotly >= 5.18`, `streamlit >= 1.36` |
| Test libraries | `pytest >= 8`, `pytest-cov >= 5` |
| Packaging | `pyproject.toml` (setuptools, `src/` layout), console script `accviz` |
| Operating systems | Linux, macOS, Windows (paths handled with `pathlib`) |
| Browser | Any modern browser for the dashboard and the HTML report (no internet needed; Plotly JS is embedded) |
| Input encoding | UTF-8 CSV files with a header row |
| Currency | Single currency per dataset, default `EUR` (configurable in `config.py`) |
| Date format | ISO 8601 (`YYYY-MM-DD`) |
| Period format | `YYYY-MM` |
| Determinism | Synthetic data generation is reproducible for the same seed |

## 3. Data requirements

### 3.1 `chart_of_accounts.csv`

| Column | Required | Description |
|---|---|---|
| `account_code` | yes | Unique code, e.g. `1000` |
| `account_name` | yes | Human-readable name |
| `account_type` | yes | One of `Asset`, `Liability`, `Equity`, `Revenue`, `Expense` |
| `subtype` | yes | Statement grouping (see §3.5) |

### 3.2 `journal_entries.csv`

| Column | Required | Description |
|---|---|---|
| `entry_id` | yes | Groups the lines of one journal entry |
| `date` | yes | Posting date |
| `account_code` | yes | Must exist in the chart of accounts |
| `debit` | yes | Non-negative amount (empty = 0) |
| `credit` | yes | Non-negative amount (empty = 0) |
| `description` | no | Free text |
| `department` | no | Cost centre (e.g. Sales, Operations) |
| `reference` | no | External reference (e.g. invoice number) |

### 3.3 `invoices.csv`

| Column | Required | Description |
|---|---|---|
| `invoice_id` | yes | Unique invoice number |
| `customer` | yes | Customer name |
| `issue_date` | yes | Invoice date |
| `due_date` | yes | Payment due date (≥ issue date) |
| `amount` | yes | Invoice total (> 0) |
| `paid_date` | no | Date of (full) payment; empty if unpaid |
| `paid_amount` | no | Amount paid (0 ≤ paid ≤ amount); default 0 |

### 3.4 `budget.csv`

| Column | Required | Description |
|---|---|---|
| `period` | yes | `YYYY-MM` |
| `account_code` | yes | A Revenue or Expense account |
| `budget_amount` | yes | Non-negative amount in natural sign (revenue and expense both positive) |

### 3.5 Subtypes

| Account type | Subtypes |
|---|---|
| Asset | `Cash`, `Receivables`, `Fixed Asset` |
| Liability | `Current Liability`, `Long-term Liability` |
| Equity | `Equity` |
| Revenue | `Operating Revenue` |
| Expense | `Cost of Sales`, `Operating Expense`, `Financial Expense`, `Tax Expense` |

## 4. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | Load the four CSV files from a directory | Must |
| FR-02 | Check that required columns exist before parsing | Must |
| FR-03 | Validate the data and return **errors** (block analysis) and **warnings** (informational) with row-level detail | Must |
| FR-04 | Detect unbalanced journal entries (|Σdebit − Σcredit| > 0.01) | Must |
| FR-05 | Detect unknown account codes, duplicate codes, invalid types and subtype/type mismatches | Must |
| FR-06 | Detect lines with both debit and credit, or with neither | Must |
| FR-07 | Detect invalid dates, negative amounts, due-before-issue, paid-above-amount | Must |
| FR-08 | Compute the natural-sign balance of each account (debit-normal for assets and expenses, credit-normal otherwise) | Must |
| FR-09 | Produce a trial balance for any date range; it must balance | Must |
| FR-10 | Produce a monthly income statement: revenue, cost of sales, gross profit, operating expenses, operating profit, financial expenses, tax, net income | Must |
| FR-11 | Produce a balance sheet at any date with current-period earnings included in equity; it must balance | Must |
| FR-12 | Produce a monthly cash balance trend (closing balance, net change) | Must |
| FR-13 | Produce revenue and expense breakdowns by account for a period | Must |
| FR-14 | Produce an accounts-receivable aging schedule as of a date, with buckets *Not yet due*, *1-30*, *31-60*, *61-90*, *90+* days | Must |
| FR-15 | Produce a summary of outstanding receivables by bucket and the top customers | Must |
| FR-16 | Compare actual to budget per account and month, with variance, variance % and favourable flag | Must |
| FR-17 | Compute ratios: gross, operating and net margin; current ratio; debt-to-equity | Must |
| FR-18 | Compute headline KPIs for the selected period | Must |
| FR-19 | Charts: revenue/expense/net-income trend, margin trend, expense donut, income-statement waterfall, cash line, aging bars, budget variance bars, balance-sheet composition | Must |
| FR-20 | Charts show a clear "no data" state instead of failing on empty input | Must |
| FR-21 | Generate a self-contained HTML report with KPIs, tables and charts | Must |
| FR-22 | CLI: `generate-data`, `validate`, `summary`, `report`, `dashboard` | Must |
| FR-23 | Streamlit dashboard with a data-source selector (directory or uploaded files), a period filter and six tabs | Must |
| FR-24 | Dashboard shows validation errors and warnings instead of a traceback | Must |
| FR-25 | Generate synthetic, double-entry-consistent sample data for a configurable seed, start month and length | Must |
| FR-26 | Analysis for an invalid period (start after end) is rejected with a clear error | Should |

## 5. Non-functional requirements

| ID | Requirement | Measure |
|---|---|---|
| NFR-01 | Correctness: accounting invariants hold for all generated datasets | Property tests over multiple seeds |
| NFR-02 | Performance: analysis of 24 months (≈ 5 000 journal lines) completes in under 10 s on a laptop | Performance test |
| NFR-03 | Testability: analytics do not depend on Streamlit or the file system except in the loader | Module structure |
| NFR-04 | Test coverage of the `accviz` package | ≥ 85 % line coverage |
| NFR-05 | Reproducibility: same seed → identical data | Unit test |
| NFR-06 | Usability: all user-visible errors are human-readable | Review and UI tests |
| NFR-07 | Portability: no network access required at run time | Plotly JS embedded in reports |
| NFR-08 | Maintainability: type hints and docstrings on public functions | Code review |

## 6. Acceptance criteria

1. `pip install -e ".[dev]"` succeeds and `accviz --help` lists all commands.
2. `pytest` passes; the coverage report shows at least 85 %.
3. `accviz validate --data data/sample` exits with code 0.
4. `accviz report` writes `reports/accounting_report.html` that contains KPI tables and charts.
5. `accviz dashboard` serves a page where all six tabs render.
6. Corrupting a CSV file (for example, unbalancing an entry) makes `accviz validate` exit with code 1 and print the offending entry.

## 7. Out of scope (future work)

* VAT / sales-tax handling and multi-currency conversion.
* Bank statement parsing and automatic reconciliation.
* Accounts payable aging and cash-flow statement (indirect method).
* Multi-user authentication and cloud deployment.
