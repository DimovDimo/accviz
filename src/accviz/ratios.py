"""Financial ratios and headline KPIs."""

from __future__ import annotations

import math
from typing import Mapping

from accviz.statements import BalanceSheet


def safe_div(numerator: float, denominator: float | None) -> float | None:
    """Divide, returning ``None`` instead of raising or producing infinity."""
    if denominator is None or math.isnan(denominator) or abs(denominator) < 1e-12:
        return None
    return numerator / denominator


def financial_ratios(totals: Mapping[str, float], bs: BalanceSheet) -> dict[str, float | None]:
    """Profitability and liquidity/leverage ratios.

    * ``gross_margin``, ``operating_margin``, ``net_margin`` – share of revenue (0–1)
    * ``current_ratio`` – current assets / current liabilities
    * ``debt_to_equity`` – total liabilities / total equity
    """
    revenue = totals["revenue"]
    return {
        "gross_margin": safe_div(totals["gross_profit"], revenue),
        "operating_margin": safe_div(totals["operating_profit"], revenue),
        "net_margin": safe_div(totals["net_income"], revenue),
        "current_ratio": safe_div(bs.current_assets, bs.current_liabilities),
        "debt_to_equity": safe_div(bs.total_liabilities, bs.total_equity),
    }


def kpi_summary(
    totals: Mapping[str, float],
    bs: BalanceSheet,
    outstanding_receivables: float,
    revenue_budget_variance_pct: float | None,
) -> dict[str, float | None]:
    """Headline numbers shown at the top of the dashboard and report."""
    return {
        "revenue": totals["revenue"],
        "gross_profit": totals["gross_profit"],
        "net_income": totals["net_income"],
        "closing_cash": bs.cash,
        "outstanding_receivables": outstanding_receivables,
        "total_assets": bs.total_assets,
        "revenue_vs_budget_pct": revenue_budget_variance_pct,
    }
