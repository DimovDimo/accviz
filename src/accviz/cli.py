"""Command-line interface: ``accviz <command> [options]``."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import pandas as pd

from accviz import __version__, audit, config
from accviz.analysis import analyze
from accviz.export import export_workbook
from accviz.loader import DataValidationError, load_raw_directory, prepare_dataset, read_dataset
from accviz.report import KPI_LABELS, RATIO_LABELS, format_value, write_report
from accviz.synthetic import GeneratorConfig, generate_dataset, write_dataset

DASHBOARD_PATH = Path(__file__).resolve().parent / "dashboard.py"
DATA_ENV_VAR = "ACCVIZ_DATA_DIR"


def _add_data_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--data",
        type=Path,
        default=config.DEFAULT_DATA_DIR,
        help=f"directory with the four CSV files (default: {config.DEFAULT_DATA_DIR})",
    )


def _date_arg(parser: argparse.ArgumentParser, name: str, help_text: str) -> None:
    parser.add_argument(name, default=None, help=help_text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="accviz",
        description="Visualize accounting data: validation, financial statements, KPIs and charts.",
    )
    parser.add_argument("--version", action="version", version=f"accviz {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    gen = sub.add_parser("generate-data", help="create synthetic sample data (CSV files)")
    gen.add_argument("--out", type=Path, default=config.DEFAULT_DATA_DIR, help="output directory")
    gen.add_argument("--seed", type=int, default=42, help="random seed (default: 42)")
    gen.add_argument("--start", default="2024-11-01", help="first month, YYYY-MM-DD (default: 2024-11-01)")
    gen.add_argument("--months", type=int, default=24, help="number of months (default: 24)")
    gen.add_argument(
        "--anomalies",
        action="store_true",
        help="inject nine known audit anomalies and write anomaly_ground_truth.csv (demo data)",
    )

    val = sub.add_parser("validate", help="check data files and report errors/warnings")
    _add_data_arg(val)

    summary = sub.add_parser("summary", help="print key figures to the console")
    _add_data_arg(summary)
    _date_arg(summary, "--start", "period start (YYYY-MM-DD)")
    _date_arg(summary, "--end", "period end (YYYY-MM-DD)")

    aud = sub.add_parser("audit", help="run journal audit rules and the Benford test")
    _add_data_arg(aud)
    _date_arg(aud, "--start", "period start (YYYY-MM-DD)")
    _date_arg(aud, "--end", "period end (YYYY-MM-DD)")
    aud.add_argument("--top", type=int, default=10, help="number of findings to list (default: 10)")

    exp = sub.add_parser("export", help="write the analysis to a multi-sheet Excel workbook (.xlsx)")
    _add_data_arg(exp)
    _date_arg(exp, "--start", "period start (YYYY-MM-DD)")
    _date_arg(exp, "--end", "period end (YYYY-MM-DD)")
    exp.add_argument("--out", type=Path, default=config.DEFAULT_WORKBOOK_PATH, help="output .xlsx file")

    rep = sub.add_parser("report", help="write a self-contained HTML report")
    _add_data_arg(rep)
    _date_arg(rep, "--start", "period start (YYYY-MM-DD)")
    _date_arg(rep, "--end", "period end (YYYY-MM-DD)")
    rep.add_argument("--out", type=Path, default=config.DEFAULT_REPORT_PATH, help="output HTML file")

    dash = sub.add_parser("dashboard", help="start the interactive Streamlit dashboard")
    _add_data_arg(dash)
    dash.add_argument("--port", type=int, default=8501, help="port (default: 8501)")
    dash.add_argument(
        "--address",
        default=config.DEFAULT_BIND_ADDRESS,
        help=f"bind address (default: {config.DEFAULT_BIND_ADDRESS}; use 0.0.0.0 to allow other machines)",
    )
    return parser


def _cmd_generate(args: argparse.Namespace) -> int:
    cfg = GeneratorConfig(seed=args.seed, start=args.start, months=args.months, anomalies=args.anomalies)
    raw = generate_dataset(cfg)
    paths = write_dataset(raw, args.out)
    kind = "demo data with injected anomalies" if args.anomalies else "synthetic data"
    print(f"Generated {args.months} months of {kind} (seed={args.seed}) in {args.out}")
    for key, path in paths.items():
        print(f"  {key:22s} {len(raw[key]):6d} rows  -> {path.name}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    raw = load_raw_directory(args.data)
    ds, result = prepare_dataset(raw)
    print(result.summary())
    if ds is None or not result.ok:
        print("\nValidation FAILED: fix the errors above.")
        return 1
    print(
        f"\nValidation OK: {len(ds.journal)} journal lines, {len(ds.invoices)} customer invoices, "
        f"{len(ds.supplier_invoices)} supplier invoices."
    )
    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    ds = read_dataset(args.data)
    result = analyze(ds, args.start, args.end)
    print(f"Accounting summary for {result.period_label}  ({config.CURRENCY})")
    print("-" * 60)
    for key, value in result.kpis.items():
        print(f"{KPI_LABELS.get(key, key):<28}{format_value(key, value):>30}")
    print("-" * 60)
    for key, value in result.ratios.items():
        print(f"{RATIO_LABELS.get(key, key):<28}{format_value(key, value):>30}")
    bs = result.balance_sheet
    status = "balanced" if bs.is_balanced() else f"NOT balanced (difference {bs.difference:,.2f})"
    print("-" * 60)
    print(f"Balance sheet as of {bs.as_of:%Y-%m-%d}: {status}")
    if result.cash_flow is not None:
        cf = result.cash_flow
        cf_status = "reconciled" if cf.is_reconciled() else f"difference {cf.difference:,.2f}"
        print(f"Net cash flow: {cf.net_change:,.2f} {config.CURRENCY}  (cash flow {cf_status})")
    for rec in result.reconciliations:
        state = "reconciled" if rec.is_reconciled() else f"difference {rec.difference:,.2f}"
        print(f"{rec.control} (GL {rec.account_code}) vs sub-ledger: {state}")
    if result.audit is not None:
        print(f"Audit findings: {result.audit.total_findings} (run 'accviz audit' for details)")
    return 0


def _load_ground_truth(directory: Path) -> pd.DataFrame | None:
    path = Path(directory) / config.ANOMALY_GROUND_TRUTH_FILE
    if not path.is_file():
        return None
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _truth_in_period(truth: pd.DataFrame, ds, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Keep only the injected anomalies whose entry date falls in the audited period."""
    entry_dates = ds.journal.groupby("entry_id")["date"].first()
    dates = pd.to_datetime(entry_dates.reindex(truth["entry_id"]).to_numpy())
    keep = (dates >= start) & (dates <= end)
    return truth.loc[keep]


def _cmd_audit(args: argparse.Namespace) -> int:
    ds = read_dataset(args.data)
    result = audit.run_audit(ds.journal, ds.chart_of_accounts, args.start, args.end)
    print(f"Journal audit for {result.start:%Y-%m-%d} to {result.end:%Y-%m-%d}")
    print(f"Entries tested: {result.entries_tested:,}  (manual: {result.manual_entries:,}, {result.manual_share:.1%})")
    print("-" * 78)
    for _, row in result.summary.iterrows():
        print(f"{row['label']:<30}{row['severity']:>8}{row['findings']:>10} findings{row['entries']:>8} entries")
    b = result.benford
    print("-" * 78)
    print(
        f"Benford first digits: {b.count:,} amounts, chi-square {b.chi_square:,.1f} "
        f"(critical {b.critical_value}), MAD {b.mad:.4f}: {b.conformity}"
    )
    if result.findings.empty:
        print("\nNo findings in the selected period.")
    else:
        top = result.findings.head(args.top)
        print(f"\nTop {len(top)} of {len(result.findings)} findings:")
        for _, row in top.iterrows():
            print(f"  {row['date']:%Y-%m-%d}  {row['entry_id']}  {row['rule']:<18} {row['amount']:>14,.2f}  {row['detail']}")
    truth = _load_ground_truth(args.data)
    if truth is not None and not truth.empty:
        truth = _truth_in_period(truth, ds, result.start, result.end)
        ev = audit.evaluate_against_truth(result.findings, truth)
        print("-" * 78)
        print(
            f"Ground truth: detected {ev['total']:.0%} of injected anomalies; "
            f"entries flagged without an injected anomaly: {ev['false_positives']}"
        )
        for _, row in ev["table"].iterrows():
            print(f"  {row['anomaly_type']:<20}{row['detected']:>3} of {row['injected']}")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    ds = read_dataset(args.data)
    out = export_workbook(ds, args.out, args.start, args.end)
    print(f"Excel workbook written to {out}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    ds = read_dataset(args.data)
    out = write_report(ds, args.out, args.start, args.end)
    print(f"Report written to {out}")
    return 0


def _cmd_dashboard(args: argparse.Namespace) -> int:
    env = dict(os.environ)
    env[DATA_ENV_VAR] = str(Path(args.data).resolve())
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(DASHBOARD_PATH),
        "--server.port",
        str(args.port),
        "--server.address",
        args.address,
        "--server.headless",
        "true",
    ]
    print(f"Starting dashboard on http://{args.address}:{args.port} (data: {args.data})")
    return subprocess.call(cmd, env=env)


COMMANDS = {
    "generate-data": _cmd_generate,
    "validate": _cmd_validate,
    "summary": _cmd_summary,
    "audit": _cmd_audit,
    "export": _cmd_export,
    "report": _cmd_report,
    "dashboard": _cmd_dashboard,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except DataValidationError as exc:
        print(exc.result.summary(), file=sys.stderr)
        print("\nAnalysis stopped because of validation errors.", file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
