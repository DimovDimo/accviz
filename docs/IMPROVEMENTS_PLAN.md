# Implementation plan: v1.1 improvements

Target release: **accviz 1.1.0**. Starting point: v1.0.0 (285 tests, 97 % coverage).

## Phases

| # | Phase | Output | Exit criterion |
|---|---|---|---|
| 1 | Review and research | `docs/IMPROVEMENTS_RESEARCH.md` | Findings R1-R10 recorded; improvements selected |
| 2 | Plan | this document | Phases, dependencies and risks agreed |
| 3 | Requirements | `docs/IMPROVEMENTS_REQUIREMENTS.md` | Each improvement has testable requirements |
| 4 | Data | regenerated `data/sample/` (with supplier invoices and `source`), new `data/demo_anomalies/` with ground truth | Validation passes; reconciliations hold |
| 5 | Tests first | new unit, integration, property and UI tests; updated tests for changed contracts | Tests fail for the right reason before implementation |
| 6 | Implementation | new modules and extensions (see below) | Tests pass |
| 7 | Verification | full test run, coverage ≥ 95 %, lint, manual CLI and dashboard checks, bug fixes | Green pipeline |
| 8 | Documentation | GitHub-formatted README, CHANGELOG entry | README matches behaviour and numbers |

## Dependency order

```
I-7 config (version, paths, bind default)
  └─▶ data model: supplier_invoices (optional), journal.source (optional)  [loader, validation, synthetic]
        ├─▶ I-2 payables.py  (uses generalised open-item logic from receivables.py)
        ├─▶ I-1 cashflow.py  (uses ledger.with_account_info + opening-balance rule)
        ├─▶ I-3 audit.py     (uses journal.source, Benford, ground-truth matching)
        ├─▶ I-5 forecast.py  (uses income_statement monthly revenue)
        └─▶ I-6 departments.py
              └─▶ analysis.py (adds fields) ─▶ charts.py ─▶ export.py (I-4)
                                                    └─▶ cli.py, ui.py (tabs), report.py
```

## Module-level work

| Module | Change | Improvement |
|---|---|---|
| `config.py` | version constant, optional-file mapping, audit thresholds, default bind address | I-2, I-3, I-7 |
| `validation.py` | generalise invoice rules to any party; supplier file rules; `source` values | I-2, I-3 |
| `loader.py` | optional supplier file; optional `source` column; empty default table | I-2, I-3 |
| `synthetic.py` | supplier invoices replace the monthly purchase lump; `source` flag; optional anomaly injection with ground-truth output | all (data) |
| `receivables.py` | generic `open_items(invoices, as_of, party_column)`; AR functions delegate to it | I-2 |
| `payables.py` (new) | AP aging, supplier summary, AP reconciliation difference | I-2 |
| `cashflow.py` (new) | direct-method statement for a period, monthly matrix, reconciliation | I-1 |
| `audit.py` (new) | rules, Benford test, findings summary, ground-truth evaluation | I-3 |
| `forecast.py` (new) | trend-seasonal forecast, residual band, MAPE backtest | I-5 |
| `departments.py` (new) | expenses by cost centre and month | I-6 |
| `analysis.py` | adds cash flow, AP aging, audit, forecast, department and reconciliation fields | all |
| `charts.py` | cash flow by section, forecast band, department stack, audit severity, AP aging | all |
| `export.py` (new) | multi-sheet `.xlsx` workbook (bytes or file) | I-4 |
| `report.py` | new sections: cash flow, forecast, departments, audit summary | I-1, I-3, I-5, I-6 |
| `cli.py` | `export`, `audit` commands; `--anomalies` for generator; localhost default | I-4, I-3, I-7 |
| `ui.py` / `dashboard.py` | tabs: Cash flow, Receivables & payables, Forecast, Audit; download button; cost-centre chart | all |
| `pyproject.toml` | version 1.1.0, `openpyxl` dependency, ruff settings, coverage gate | I-4, I-7 |
| `.github/workflows/ci.yml` (new) | lint and tests on Python 3.10, 3.12, 3.13 | I-7 |

## Key design decisions

1. **Cash flow classification by counterpart line.** For each entry containing a cash
   line, every non-cash line contributes `-(debit − credit)` to cash flow, classified by its
   account: fixed assets → investing; long-term liabilities and equity → financing; everything
   else → operating. Balanced entries make the total equal to the change in cash.
2. **Opening balances.** Entries whose description contains "opening balance" are the
   opening position. They are treated as opening cash, not as flows, so a period that
   includes the first day still reconciles.
3. **Manual entries.** Timing rules (weekend, threshold) apply to `source = manual`
   entries only, because those are the entries an auditor focuses on. Round-amount,
   outlier and duplicate rules apply to all lines.
4. **Outliers.** Robust z-score per expense account, using median and median absolute
   deviation (MAD), with threshold 4.0. This is less sensitive to the outlier itself than a
   mean-and-standard-deviation test.
5. **Benford.** Chi-square on first digits (8 degrees of freedom, critical value 15.507 at
   α = 0.05) plus the mean absolute deviation (MAD) conformity bands. Reported as an indicator, not a verdict.
6. **Forecast.** `y_t = (a + b·t) · s_month`, where the seasonal indices `s` are only fitted
   when there are at least 24 months of history. The band is ±1.96 residual standard
   deviations. Backtests use a holdout period and report MAPE.
7. **Reconciliation as a feature.** AR and AP sub-ledgers are reconciled to their control
   accounts and the difference is shown in the Data quality tab. The demo dataset's injected
   duplicate supplier posting therefore produces a visible AP difference.
8. **Backward compatibility.** Optional files and columns default to empty or `system`.
   Existing v1.0 datasets keep working.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Changing the generator changes all sample numbers | Regenerate once; update README; tests assert properties, not hard-coded totals |
| Outlier rule flags legitimate seasonal spikes | Threshold 4.0 on MAD; demo ground truth measures recall; sample findings are reviewed and documented |
| Benford misread as proof of fraud | Output wording says "indicator"; explanation in README |
| Forecast overfits short history | Trend-only model below 24 months; holdout MAPE reported; band shown |
| openpyxl formatting differences across Excel versions | Tests read the workbook back with openpyxl and check sheets, headers and numbers |
| Security change breaks the preview | Preview run explicitly passes `--address 0.0.0.0`; default is localhost |

## Definition of done

* All improvements meet their requirements (see `IMPROVEMENTS_REQUIREMENTS.md`).
* `pytest` passes; coverage ≥ 95 %; `ruff check` clean.
* Demo anomaly detection reaches recall 100 % for every injected type.
* Cash flow reconciles to GL cash at every month end in the property tests.
* `accviz export` produces an `.xlsx` that opens and contains all sheets.
* README is updated for GitHub: badges, quick start, features, examples, architecture, testing, roadmap.
