"""Integration tests for the command-line interface."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from accviz import config
from accviz.cli import build_parser, main

SRC = Path(__file__).resolve().parents[2] / "src"


@pytest.fixture(scope="module")
def generated_dir(tmp_path_factory):
    folder = tmp_path_factory.mktemp("cli") / "data"
    assert main(["generate-data", "--out", str(folder), "--months", "6", "--seed", "3"]) == 0
    return folder


def test_generate_data_writes_csv_files(generated_dir):
    for filename in config.DATASET_FILES.values():
        assert (generated_dir / filename).is_file()


def test_generate_data_prints_row_counts(tmp_path, capsys):
    main(["generate-data", "--out", str(tmp_path / "d"), "--months", "2"])
    out = capsys.readouterr().out
    assert "journal" in out and "invoices" in out and "2 months" in out


def test_validate_succeeds_on_generated_data(generated_dir, capsys):
    assert main(["validate", "--data", str(generated_dir)]) == 0
    assert "Validation OK" in capsys.readouterr().out


def test_validate_fails_on_unbalanced_journal(tmp_path, generated_dir, capsys):
    broken = tmp_path / "broken"
    shutil.copytree(generated_dir, broken)
    journal = broken / config.JOURNAL_FILE
    lines = journal.read_text(encoding="utf-8").splitlines()
    # Change the first debit amount line so that its entry no longer balances.
    header, *rows = lines
    index = next(i for i, row in enumerate(rows) if row.split(",")[2] == "1000")
    parts = rows[index].split(",")
    parts[4] = "12345.67"
    rows[index] = ",".join(parts)
    journal.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")

    assert main(["validate", "--data", str(broken)]) == 1
    captured = capsys.readouterr()
    assert "unbalanced" in captured.err or "unbalanced" in captured.out


def test_summary_prints_kpis_and_balance_status(generated_dir, capsys):
    assert main(["summary", "--data", str(generated_dir)]) == 0
    out = capsys.readouterr().out
    assert "Net income" in out
    assert "Balance sheet as of" in out and "balanced" in out


def test_summary_accepts_a_period(generated_dir, capsys):
    assert main(["summary", "--data", str(generated_dir), "--start", "2025-01-01", "--end", "2025-01-31"]) == 0
    assert "2025-01-01 to 2025-01-31" in capsys.readouterr().out


def test_report_command_writes_html(tmp_path, generated_dir, capsys):
    out_file = tmp_path / "out" / "report.html"
    assert main(["report", "--data", str(generated_dir), "--out", str(out_file)]) == 0
    assert out_file.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
    assert str(out_file) in capsys.readouterr().out


def test_missing_data_directory_returns_error_code(tmp_path, capsys):
    assert main(["summary", "--data", str(tmp_path / "missing")]) == 2
    assert "not found" in capsys.readouterr().err


def test_invalid_period_returns_error_code(generated_dir, capsys):
    assert main(["summary", "--data", str(generated_dir), "--start", "2026-01-01", "--end", "2025-01-01"]) == 2
    assert "after end date" in capsys.readouterr().err


def test_validation_error_returns_exit_code_one(tmp_path, generated_dir, capsys):
    bad = tmp_path / "bad"
    shutil.copytree(generated_dir, bad)
    (bad / config.INVOICES_FILE).write_text("invoice_id,customer\nINV-1,Foo\n", encoding="utf-8")
    assert main(["report", "--data", str(bad), "--out", str(tmp_path / "r.html")]) == 1
    assert "missing required column" in capsys.readouterr().err


def test_parser_accepts_dashboard_options():
    args = build_parser().parse_args(["dashboard", "--port", "8600", "--data", "x"])
    assert args.command == "dashboard"
    assert args.port == 8600


def test_version_flag_and_module_entry_point():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    result = subprocess.run(
        [sys.executable, "-m", "accviz", "--version"], capture_output=True, text=True, env=env, timeout=120
    )
    assert result.returncode == 0
    assert "accviz 1.1.0" in result.stdout
