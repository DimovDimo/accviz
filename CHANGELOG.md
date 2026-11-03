# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning.

## [1.1.1] 2026-11-03

Fixes from a review of the v1.1.0 code. Each fix has a regression test.

### Fixed
- **Invalid payment values were treated as unpaid.** A non-numeric `paid_amount` was silently read as
  `0`, and a non-empty `paid_date` that is not `YYYY-MM-DD` was silently read as blank. Both are now
  validation errors (`invoices.csv` and `supplier_invoices.csv`). Blank values are still allowed.
- **False cash-flow difference for entries dated across two months.** A flow is now dated with the
  cash line of its entry, so the monthly and period statements reconcile to the GL. The ledger was
  never wrong; only the statement's attribution was.
- **Dashboard showed stale data after the files changed.** The data cache is now keyed on each file's
  size and modification time as well as the directory path.
- **Empty or unreadable uploads crashed the dashboard** with an uncaught `EmptyDataError`. They now
  produce a validation error that names the file.
- **Forecast backtest returned `inf`** when a held-out month had zero revenue. Zero-revenue months are
  now left out of the MAPE, and the MAPE is `None` (shown as "-") when every held-out month is zero.
- **Forecast trend could be misaligned by a missing month.** The trend and seasonal indices count
  calendar months, so a month with no postings between the first and last posting is now zero revenue
  rather than being dropped.
- **Forecast error handling.** The backtest now runs only after a model has been fitted, so a failure
  can no longer leave a model and an error message together. The current length guard already made
  this path unreachable, so the change is defensive and has no effect on results.
- **False positives were counted per finding.** An entry with two findings counted twice. The count
  is now per entry, and the CLI text says "entries flagged without an injected anomaly".
- **`accviz audit` accepted a reversed period** and printed an empty audit with exit code 0. It now
  fails with exit code 2, as `summary` already does.
- **Spaces after commas in the header row** (for example `account_code, account_name`) made required
  columns look missing. Header names are now trimmed when reading CSV files.
- **Unhelpful message for semicolon-separated files.** The error now says the file uses `;` and must be
  comma-separated, instead of listing missing columns.

### Changed
- Validation is stricter for invalid `paid_amount` and `paid_date` values. A v1.1.0 dataset that contains
  such values, which were previously accepted as unpaid, now fails validation. Fix the cells or leave
  them blank.
- The validation warning for a paid invoice without a payment date now reads "without a valid
  paid_date".
- `accviz audit` prints "entries flagged without an injected anomaly" in place of "false positives".

### Tests
- 19 regression tests were added (unit, integration and dashboard). The suite has 548 passing tests and
  1 skipped by design, with 96.9 % line coverage.

## [1.1.0] 2026-11-03

### Added
- **Direct-method cash flow statement** (`cashflow.py`) for any period and per month. Opening cash
  plus operating, investing and financing flows reconciles to the GL cash balance. Opening-balance
  entries (description containing "opening balance") are treated as opening cash.
- **Accounts payable aging** (`payables.py`) from the optional `supplier_invoices.csv`, with top
  suppliers and a **sub-ledger reconciliation** of GL 2000 (`reconciliation.py`). Receivables are
  reconciled to GL 1100 in the same way.
- **Journal audit analytics** (`audit.py`): round amounts, weekend manual entries, approval-threshold
  proximity (manual entries, 5 % band below 5,000), robust z-score expense outliers (threshold 4.0),
  possible duplicate postings (same account, side and amount within 7 days), and a Benford
  first-digit test (chi-square critical value 15.507, df 8, plus MAD conformity).
  Ground-truth scoring for the demo dataset.
- Optional journal **`source`** column (`system` or `manual`); missing means `system`.
- **Excel export** (`export.py`, openpyxl): eleven formatted sheets, `accviz export` command and a
  download button in the dashboard sidebar.
- **Revenue forecast** (`forecast.py`): linear trend, seasonal index when 24 months are available,
  95 % band and holdout MAPE backtest. Horizon slider (3-12 months) in the dashboard.
- **Cost-centre view** (`departments.py`): expenses by department and month, with shares.
- `accviz audit` command (`--top`, `--start`, `--end`) and `accviz generate-data --anomalies`, which
  plants nine known anomalies and writes `anomaly_ground_truth.csv`.
- Demo dataset `data/demo_anomalies/` with ground truth; regenerated sample `data/sample/`.
- Dashboard tabs: **Cash flow**, **Receivables & payables**, **Forecast** and **Audit** (nine tabs in total).
- Report sections for cash flow, payables, forecast, cost centres and audit.
- Continuous integration (`.github/workflows/ci.yml`): ruff, dataset validation, tests with coverage
  gate, export and report build.
- Ruff configuration and a coverage gate (`fail_under = 95`) in `pyproject.toml`.

### Changed
- **Secure defaults:** the dashboard and the CLI dashboard command bind to `127.0.0.1`. Use
  `--address 0.0.0.0` to expose it.
- The synthetic generator produces supplier invoices (3-6 per month, terms of 30, 45 or 60 days,
  payment probability 0.97, payment delay 20-70 days) in place of one monthly purchase posting.
  Manual entries (depreciation, interest, tax accrual, loan principal, opening balances) are tagged
  `manual`. The sample data was regenerated because the random sequence changed.
- Audit findings are deduplicated per (rule, entry, amount). The summary column `lines` is renamed
  `findings`.
- Analysis results keep all v1.0 fields; new fields are added.
- Package version is 1.1.0 (`accviz --version`).

### Compatibility
- Datasets from v1.0 still load. A missing `supplier_invoices.csv` or `source` column produces a
  warning, not an error, and the v1.1 sections are shown as empty.

### Fixed
- Seasonal forecast: the trend and the seasonal indices are now estimated alternately, so the
  seasonal pattern no longer biases the trend slope (a single pass gave about 6 % error on a known
  pattern; the refined estimate is exact on that test).
- An empty but present `supplier_invoices.csv` now produces a warning instead of passing silently.
- Ground-truth scoring for a period-limited audit counts only anomalies inside that period.
- A percentage of zero displayed as `-0.0 %`.

### Known limitations
- Several payments per invoice (planned for v1.2, requirement R9), VAT and multi-currency are not supported.
- Audit rules are indicators. On the synthetic sample, the two outlier findings are large but
  legitimate cost-of-sales invoices.

## [1.0.0]

### Added
- Data validation (double entry, account codes, dates, amounts, receivables and budget consistency).
- Income statement, balance sheet, trial balance, cash trend and KPI ratios.
- Receivables aging, budget variance and Plotly charts.
- Streamlit dashboard with a directory or upload data source, period filter and six tabs.
- Self-contained HTML report and command-line interface (`generate-data`, `validate`, `summary`,
  `report`, `dashboard`).
- Deterministic synthetic data generator (24 months, seeded).
- Test suite: unit, integration, property, performance and UI tests (285 tests, 97 % line coverage).
