# Project plan: accviz Visualization of Accounting Data

## Goal

Deliver a self-contained Python project that loads a small chart of accounts, a general
journal, receivables invoices and a budget, validates them, computes standard financial
statements and KPIs, and presents them as (a) an interactive Streamlit dashboard, (b) a
self-contained HTML report and (c) console summaries via a CLI.

## Phases

| # | Phase | Activities | Output | Status |
|---|---|---|---|---|
| 1 | Research | Survey reference architectures, chart practice, accounting rules | `docs/RESEARCH.md` | Done |
| 2 | Planning | Phases, milestones, risks, definition of done | `docs/PLAN.md` | Done |
| 3 | Requirements | Functional and non-functional requirements, data schema | `docs/REQUIREMENTS.md` | Done |
| 4 | Synthetic data | Deterministic double-entry generator; 24 months of sample data | `data/sample/*.csv` | Done |
| 5 | Test design | Test pyramid: unit, integration, UI, property, performance | `tests/` | Done |
| 6 | Implementation | Core package, CLI, report, dashboard | `src/accviz/` | Done |
| 7 | Verification | Run the test suite, measure coverage, fix defects, validate sample data | Green test run, coverage ≥ 85 % | Done |
| 8 | Documentation | GitHub-ready README, usage, architecture | `README.md` | Done |

Phases 4 → 5 → 6 follow a test-first rhythm for the analytics: each module's tests (with
hand-computed expected values) were written before its implementation.

## Milestones

* **M1 Data foundation**: schemas, loader, validation, generator. Sample data passes validation.
* **M2 Analytics core**: ledger, statements, balance sheet, receivables, budget, ratios.
* **M3 Presentation**: charts, HTML report, CLI commands.
* **M4 Dashboard**: Streamlit app with filters and tabs; UI test passes.
* **M5 Release candidate**: full test run, coverage, README.

## Work breakdown (module level)

1. `config.py` constants (currency, tolerances, file names, account types, subtypes).
2. `validation.py` rule set that returns a `ValidationResult` (errors and warnings).
3. `loader.py` reads CSVs, normalises types, builds an immutable `Dataset`.
4. `ledger.py` natural-sign amounts, trial balance, balances as of a date.
5. `statements.py` monthly income statement, totals, balance sheet, cash trend, breakdowns.
6. `receivables.py` invoice-level outstanding amounts, aging buckets, top customers.
7. `budget.py` actual vs budget per account and period, favourable/unfavourable flags.
8. `ratios.py` margins, current ratio, debt-to-equity, KPI summary.
9. `analysis.py` single orchestration entry point used by every front-end.
10. `charts.py` Plotly figure builders with empty-state handling.
11. `report.py` self-contained HTML report.
12. `synthetic.py` deterministic synthetic data generator and CSV writer.
13. `cli.py` `generate-data`, `validate`, `summary`, `report`, `dashboard` commands.
14. `dashboard.py` Streamlit application (directory or upload source, date filter, 6 tabs).

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Synthetic data violates double-entry rules | Misleading statements | Generator posts balanced entries by construction; property tests check invariants for several seeds |
| Floating-point rounding causes false imbalance | Spurious validation errors | Amounts rounded to cents; tolerance `BALANCE_TOLERANCE = 0.01` |
| Users upload malformed files | Crashes | Column check first, then per-rule validation with row-level messages; UI shows errors instead of tracebacks |
| Streamlit API changes between versions | Broken dashboard | Pin lower bounds in `requirements.txt`; UI test with `streamlit.testing` |
| Large HTML report size (Plotly JS embedded) | Slow download | Plotly JS embedded once, reused by all charts |
| Scope creep (VAT, multi-currency, real bank feeds) | Delays | Listed as out of scope in `REQUIREMENTS.md` and README roadmap |

## Definition of done

* All functional requirements in `REQUIREMENTS.md` are implemented and traceable to a test.
* `pytest` passes with no failures; line coverage of the `accviz` package is at least 85 %.
* `accviz validate` passes on the committed sample data.
* `accviz report` produces an HTML file that opens offline.
* The dashboard starts with `accviz dashboard` and renders all tabs without exceptions.
* README explains installation, usage, data format, architecture, testing and limitations.
