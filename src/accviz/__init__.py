"""accviz – visualization of accounting data.

The package is organised in layers so that the analytics can be tested without a UI:

* :mod:`accviz.config`      – constants (currency, tolerances, file names, account rules)
* :mod:`accviz.validation`  – data-quality rules returning errors and warnings
* :mod:`accviz.loader`      – CSV reading, type normalisation, the immutable ``Dataset``
* :mod:`accviz.ledger`      – natural-sign amounts, trial balance, balances as of a date
* :mod:`accviz.statements`  – income statement, balance sheet, cash trend, breakdowns
* :mod:`accviz.receivables` – accounts-receivable aging
* :mod:`accviz.payables`    – accounts-payable aging and top suppliers (v1.1)
* :mod:`accviz.reconciliation` – sub-ledger to GL control reconciliations (v1.1)
* :mod:`accviz.cashflow`    – direct-method cash flow statement (v1.1)
* :mod:`accviz.audit`       – journal audit rules, Benford test and ground-truth scoring (v1.1)
* :mod:`accviz.forecast`    – revenue trend and seasonal forecast with backtest (v1.1)
* :mod:`accviz.departments` – expenses by cost centre (v1.1)
* :mod:`accviz.export`      – multi-sheet Excel workbook (v1.1)
* :mod:`accviz.budget`      – actual versus budget
* :mod:`accviz.ratios`      – margins, liquidity and leverage ratios, KPIs
* :mod:`accviz.analysis`    – single entry point that bundles all of the above
* :mod:`accviz.charts`      – Plotly figure builders
* :mod:`accviz.report`      – self-contained HTML report
* :mod:`accviz.synthetic`   – deterministic double-entry sample-data generator
* :mod:`accviz.cli`         – command-line interface
* :mod:`accviz.dashboard`   – Streamlit application
"""

__version__ = "1.1.0"

__all__ = ["__version__"]
