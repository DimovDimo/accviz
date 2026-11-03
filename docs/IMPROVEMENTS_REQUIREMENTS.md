# Technical requirements: v1.1 improvements

Requirement IDs continue the v1.0 list (`REQUIREMENTS.md`, FR-01…FR-26, NFR-01…NFR-08).

## 1. Technical requirements (changes to the environment)

| Area | Requirement |
|---|---|
| Version | `accviz` 1.1.0 |
| Runtime dependency added | `openpyxl >= 3.1` (Excel export) |
| Dev dependency added | `ruff >= 0.5` (lint, already listed) |
| Python | 3.10, 3.12 and 3.13 are tested in CI |
| Default bind address | `127.0.0.1` for the dashboard; `0.0.0.0` only when requested with `--address` |
| Optional inputs | `supplier_invoices.csv`; `source` column in `journal_entries.csv` |
| Output formats | `.xlsx` (Excel 2010+ OOXML) and HTML |

## 2. Data requirements

### 2.1 `supplier_invoices.csv` (optional)

| Column | Required | Rule |
|---|---|---|
| `invoice_id` | yes | unique within the file |
| `supplier` | yes | non-empty name |
| `issue_date`, `due_date` | yes | ISO date; `due_date ≥ issue_date` |
| `amount` | yes | > 0 |
| `paid_date` | no | payment date; empty if unpaid |
| `paid_amount` | no | 0 ≤ paid ≤ amount; default 0 |

### 2.2 `journal_entries.csv` new optional column `source`

Allowed values: `system` (default) or `manual`. Any other value is an error.

### 2.3 Ground-truth file (demo datasets only)

`anomaly_ground_truth.csv` with columns `entry_id`, `anomaly_type`, `description`.
Allowed `anomaly_type` values: `round_amount`, `weekend_manual`, `threshold_manual`,
`outlier_expense`, `duplicate_posting`.

## 3. Functional requirements

### I-1 Cash flow statement

| ID | Requirement | Priority |
|---|---|---|
| CF-01 | Produce a direct-method cash flow statement for any date range with sections *Operating*, *Investing*, *Financing* | Must |
| CF-02 | Each cash movement is classified by its counterpart account (see design decision 1) | Must |
| CF-03 | Opening balance entries form the opening cash position and are not reported as flows | Must |
| CF-04 | Statement shows opening cash, net change per section, net change, closing cash, GL closing cash and the difference (must be 0) | Must |
| CF-05 | Produce a monthly matrix (period × section) | Must |
| CF-06 | Cash flow of a period with no cash activity is zero and does not fail | Must |

### I-2 Accounts payable

| ID | Requirement | Priority |
|---|---|---|
| AP-01 | Load and validate `supplier_invoices.csv` with the same rules as invoices (party = supplier) | Must |
| AP-02 | Missing supplier file: AP aging is empty and a warning is shown; analysis still runs | Must |
| AP-03 | AP aging by bucket as of a date, using the same buckets as receivables | Must |
| AP-04 | Top suppliers by outstanding amount | Should |
| AP-05 | AP sub-ledger reconciliation: GL account 2000 vs open supplier invoices; difference reported | Must |
| AP-06 | AR and AP reconciliation results appear in the Data quality tab and report | Must |

### I-3 Audit analytics

| ID | Requirement | Priority |
|---|---|---|
| AU-01 | Round-amount rule: lines with amount ≥ 1,000 that are exact multiples of 1,000 (severity medium) | Must |
| AU-02 | Weekend-manual rule: manual entries dated Saturday or Sunday (severity low) | Must |
| AU-03 | Threshold rule: manual lines within 5 % below the approval threshold (5,000) (severity medium) | Must |
| AU-04 | Outlier rule: expense lines whose robust z-score (median/MAD) ≥ 4.0 within their account, with ≥ 5 observations (severity high) | Must |
| AU-05 | Duplicate rule: two lines on the same account with the same amount in different entries within 7 days (severity high) | Must |
| AU-06 | Benford rule: first-digit distribution of line amounts ≥ 10; chi-square statistic against critical value 15.507 (df 8, α 0.05) and MAD conformity band | Must |
| AU-07 | Findings table with rule, severity, entry, date, account, amount, description and detail | Must |
| AU-08 | Summary per rule: number of lines and unique entries | Must |
| AU-09 | Evaluation against ground truth: detection rate per injected type | Must |
| AU-10 | Share of manual entries reported | Should |
| AU-11 | `accviz audit` prints the summary and the top findings | Must |

### I-4 Excel export

| ID | Requirement | Priority |
|---|---|---|
| EX-01 | Workbook with sheets: Summary, Income statement, Cash flow, Balance sheet, Trial balance, Receivables aging, Payables aging, Budget variance, Departments, Forecast, Audit findings | Must |
| EX-02 | Header row bold and frozen; money cells formatted `#,##0.00`; percentages formatted `0.0%` | Must |
| EX-03 | Export to a file path or to bytes (for the dashboard download) | Must |
| EX-04 | `accviz export --out PATH` writes the workbook; exit code 0 | Must |
| EX-05 | Dashboard offers a download button for the current period | Must |

### I-5 Forecast

| ID | Requirement | Priority |
|---|---|---|
| FC-01 | Forecast monthly revenue for *h* months (1-24) after the last period | Must |
| FC-02 | Model: linear trend; multiplicative seasonal indices only when ≥ 24 months of history | Must |
| FC-03 | Confidence band ±1.96 × residual standard deviation; lower bound not below zero | Must |
| FC-04 | Holdout backtest returning MAPE | Must |
| FC-05 | Forecast shown in dashboard (slider 3-12 months), report and Excel | Must |
| FC-06 | Fewer than 3 history points raises a clear error | Must |

### I-6 Cost centres

| ID | Requirement | Priority |
|---|---|---|
| CC-01 | Expenses by department and month for the selected period | Must |
| CC-02 | Share of total expenses per department | Must |
| CC-03 | Stacked chart in the dashboard and report | Must |

### I-7 Security, CI and quality

| ID | Requirement | Priority |
|---|---|---|
| SQ-01 | Dashboard and `accviz dashboard` default to `127.0.0.1` | Must |
| SQ-02 | GitHub Actions workflow runs ruff and pytest on Python 3.10, 3.12 and 3.13 | Must |
| SQ-03 | Coverage gate `fail_under = 95` | Must |
| SQ-04 | Ruff configuration in `pyproject.toml`; `ruff check src tests` passes | Must |

## 4. Non-functional requirements

| ID | Requirement | Measure |
|---|---|---|
| NFR-11 | Analysis of 24 months including audit and forecast completes in under 15 s | performance test |
| NFR-12 | Backward compatibility: v1.0 datasets (without supplier file and `source`) analyse without errors | integration test with the v1.0 layout |
| NFR-13 | Audit results are deterministic for a given dataset | unit test |
| NFR-14 | Excel files open with openpyxl and contain the documented sheets | integration test |

## 5. Acceptance criteria

1. `accviz generate-data --anomalies --out data/demo_anomalies` writes a dataset and a ground-truth file.
2. `accviz audit --data data/demo_anomalies` lists findings for every injected anomaly type.
3. `accviz export --data data/sample --out reports/accounting.xlsx` creates the workbook with 11 sheets.
4. `accviz dashboard` starts on localhost by default and shows nine tabs.
5. The cash flow difference is 0.00 for the sample and the demo datasets.
6. AP reconciliation difference is 0.00 for the sample, and equals the injected duplicate amounts for the demo dataset.
