# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning.

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
