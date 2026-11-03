"""Command-line interface: ``accviz <command> [options]``."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from accviz import __version__, config
from accviz.analysis import analyze
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

    val = sub.add_parser("validate", help="check data files and report errors/warnings")
    _add_data_arg(val)

    summary = sub.add_parser("summary", help="print key figures to the console")
    _add_data_arg(summary)
    _date_arg(summary, "--start", "period start (YYYY-MM-DD)")
    _date_arg(summary, "--end", "period end (YYYY-MM-DD)")

    rep = sub.add_parser("report", help="write a self-contained HTML report")
    _add_data_arg(rep)
    _date_arg(rep, "--start", "period start (YYYY-MM-DD)")
    _date_arg(rep, "--end", "period end (YYYY-MM-DD)")
    rep.add_argument("--out", type=Path, default=config.DEFAULT_REPORT_PATH, help="output HTML file")

    dash = sub.add_parser("dashboard", help="start the interactive Streamlit dashboard")
    _add_data_arg(dash)
    dash.add_argument("--port", type=int, default=8501, help="port (default: 8501)")
    dash.add_argument("--address", default="0.0.0.0", help="bind address (default: 0.0.0.0)")
    return parser


def _cmd_generate(args: argparse.Namespace) -> int:
    cfg = GeneratorConfig(seed=args.seed, start=args.start, months=args.months)
    raw = generate_dataset(cfg)
    paths = write_dataset(raw, args.out)
    print(f"Generated {args.months} months of synthetic data (seed={args.seed}) in {args.out}")
    for key, path in paths.items():
        print(f"  {key:9s} {len(raw[key]):6d} rows  -> {path.name}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    raw = load_raw_directory(args.data)
    ds, result = prepare_dataset(raw)
    print(result.summary())
    if ds is None or not result.ok:
        print("\nValidation FAILED: fix the errors above.")
        return 1
    print(f"\nValidation OK: {len(ds.journal)} journal lines, {len(ds.invoices)} invoices.")
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
    print(f"Starting dashboard on http://localhost:{args.port} (data: {args.data})")
    return subprocess.call(cmd, env=env)


COMMANDS = {
    "generate-data": _cmd_generate,
    "validate": _cmd_validate,
    "summary": _cmd_summary,
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
