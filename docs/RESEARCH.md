# Research: how accounting-data visualization projects are built

This note summarises what we looked at before choosing the architecture, stack and
features of **accviz**.

## 1. Common architecture

Public tutorials and reference projects almost always separate the work into layers:

* **Data layer** load and clean the raw files (CSV/Excel/bank exports).
* **Analytics layer** pure functions that turn transactions into statements and KPIs.
* **Visualization layer** chart builders that return figures, not UI code.
* **Presentation layer** a dashboard (or report) that calls the layers above.

A reference project on personal finance uses exactly this split: `config.py`,
`preprocessing.py` (auto-detect CSV formats and normalise data), `visualizations.py`
(Plotly charts such as pie, bar, timeline and heat-map), and `app.py` (the Streamlit UI)
[KDnuggets Vibe Coding a Private AI Financial Analyst](https://www.kdnuggets.com/vibe-coding-a-private-ai-financial-analyst-with-python-and-local-llms).

A step-by-step Streamlit/Plotly financial dashboard tutorial uses the same idea: a `src/`
package with `data_processing.py` and `visualizations.py`, plus a top-level `dashboard.py`
entry point and a `requirements.txt`
[Medium Building an Interactive Financial Dashboard with Streamlit and Plotly](https://reddykarthikeya1.medium.com/building-an-interactive-financial-dashboard-with-streamlit-and-plotly-a-step-by-step-tutorial-4b9973b62be5).

**Decision:** keep the analytics and charts in a plain Python package that does not depend on
the UI. The Streamlit dashboard, the CLI and the static HTML report are thin front-ends on top
of it. This makes the core logic testable with ordinary unit tests.

## 2. Technology stack

* **pandas / NumPy** tabular transformations (group-by, pivots, merges) are the core of
  ledger analysis.
* **Plotly** interactive charts (hover, zoom, legend toggling) that work both inside
  Streamlit and as standalone HTML.
* **Streamlit** fastest route to an interactive, filterable dashboard written in Python.
* **pytest** (+ `pytest-cov`) unit, integration, property-style and UI tests.

## 3. Accounting-specific visualization practice

An accountants' guide to financial data visualization recommends:

* A **flat table structure** (one row per transaction line) with calculated columns such as
  *Net amount = Debit − Credit*
  [MindMapNote Financial Data Visualization for Accountants](https://www.mindmapnote.com/pdf/en/Financial%20Data%20Visualization%20for%20Accountants.pdf).
* A **waterfall chart** to show how revenue becomes net income, with contrasting colours for
  positive and negative steps (same source).
* **Stacked bars** for inflows/outflows and a **line chart** for the cash balance over time
  (same source).
* **Consistent colour coding** (for example green = favourable, red = unfavourable) and a
  limited palette (same source).
* **Grouped ratios** liquidity ratios together, profitability ratios together and
  **progressive disclosure**: summary first, drill-down through filters
  (same source).
* **Data cleaning before charting**: standardise dates, remove duplicates, flag missing values
  for review (same source).

## 4. Domain rules we turn into tests

Double-entry bookkeeping gives us invariants that a good accounting tool must never break:

1. Every journal entry balances (total debits = total credits).
2. The trial balance balances.
3. Assets = Liabilities + Equity at every balance-sheet date, where equity includes current
   period earnings.
4. The accounts-receivable control account in the ledger equals the sum of outstanding
   invoices in the receivables sub-ledger (aging report).

These rules are used both as validation checks on user data and as property tests on the
synthetic data generator.

## 5. Summary of findings

| Question | Finding | Consequence for accviz |
|---|---|---|
| How to structure code? | Layered, UI-independent core | `accviz` package + thin CLI/dashboard |
| Which charts? | Revenue/expense trend, waterfall, donut, cash line, aging bars, budget variance | Seven chart builders in `charts.py` |
| Which checks? | Balanced entries, valid codes, date sanity, reconciliation | `validation.py` + invariant tests |
| How to test? | Unit + integration + UI + property tests | `tests/` split into those layers |
