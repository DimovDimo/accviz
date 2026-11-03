"""Integration tests for the v1.1 CLI commands: audit, export, dashboard and anomaly data."""

from __future__ import annotations

import re
import subprocess
import sys

import pytest
from openpyxl import load_workbook

from accviz import cli, config
from accviz.cli import build_parser, main

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def anomaly_dir(tmp_path_factory):
    folder = tmp_path_factory.mktemp("anomalies") / "data"
    assert main(["generate-data", "--anomalies", "--out", str(folder), "--months", "24", "--seed", "42"]) == 0
    return folder


def test_generate_anomalies_writes_ground_truth(anomaly_dir, capsys):
    assert (anomaly_dir / config.ANOMALY_GROUND_TRUTH_FILE).is_file()
    assert (anomaly_dir / config.SUPPLIER_INVOICES_FILE).is_file()


def test_audit_prints_ground_truth_scores(anomaly_dir, capsys):
    assert main(["audit", "--data", str(anomaly_dir)]) == 0
    out = capsys.readouterr().out
    assert "Ground truth: detected 100% of injected anomalies; entries flagged without an injected anomaly: 2" in out
    assert "duplicate_posting" in out and "round_amount" in out
    assert "Benford first digits" in out


def test_audit_respects_period_and_top(anomaly_dir, capsys):
    assert main(["audit", "--data", str(anomaly_dir), "--start", "2025-01-01", "--end", "2025-06-30", "--top", "3"]) == 0
    out = capsys.readouterr().out
    assert "2025-01-01 to 2025-06-30" in out
    listed = [line for line in out.splitlines() if line.startswith("  20")]
    assert len(listed) == 3
    assert all("2025-0" in line and line.split()[0] <= "2025-06-30" for line in listed)


def test_ground_truth_scores_only_anomalies_inside_the_period(anomaly_dir, capsys):
    import pandas as pd

    truth = pd.read_csv(anomaly_dir / config.ANOMALY_GROUND_TRUTH_FILE, dtype=str)
    journal = pd.read_csv(anomaly_dir / config.JOURNAL_FILE, dtype=str, usecols=["entry_id", "date"])
    dates = journal.drop_duplicates("entry_id").set_index("entry_id")["date"].reindex(truth["entry_id"])
    expected_in_period = int(((dates >= "2025-01-01") & (dates <= "2025-06-30")).sum())
    assert 0 < expected_in_period < len(truth)  # the period must split the injected anomalies

    assert main(["audit", "--data", str(anomaly_dir), "--start", "2025-01-01", "--end", "2025-06-30"]) == 0
    out = capsys.readouterr().out
    assert "Ground truth: detected 100% of injected anomalies" in out
    rows = re.findall(r"^  \w+\s+(\d+) of (\d+)$", out, flags=re.MULTILINE)
    assert len(rows) == 5  # one row per anomaly type
    assert sum(int(total) for _, total in rows) == expected_in_period


def test_audit_without_findings_says_so(tmp_path, capsys):
    from accviz.synthetic import write_dataset
    from tests.factories import tiny_raw

    write_dataset(tiny_raw(), tmp_path)
    assert main(["audit", "--data", str(tmp_path), "--start", "2025-01-01", "--end", "2025-01-31"]) == 0
    out = capsys.readouterr().out
    assert "No findings in the selected period." in out
    assert "Entries tested: 4" in out


def test_export_writes_eleven_sheet_workbook(anomaly_dir, tmp_path, capsys):
    target = tmp_path / "analysis.xlsx"
    assert main(["export", "--data", str(anomaly_dir), "--out", str(target)]) == 0
    assert "Excel workbook written" in capsys.readouterr().out
    assert len(load_workbook(target).sheetnames) == 11


def test_export_with_missing_data_returns_2(tmp_path, capsys):
    assert main(["export", "--data", str(tmp_path / "nothing"), "--out", str(tmp_path / "x.xlsx")]) == 2
    assert "error" in capsys.readouterr().err


def test_summary_mentions_cash_flow_and_reconciliation(anomaly_dir, capsys):
    assert main(["summary", "--data", str(anomaly_dir)]) == 0
    out = capsys.readouterr().out
    assert "cash flow" in out.lower()
    assert "reconcil" in out.lower()


def test_dashboard_binds_to_localhost_by_default(monkeypatch):
    seen = {}

    def fake_call(cmd, env=None):
        seen["cmd"] = cmd
        return 0

    monkeypatch.setattr(cli.subprocess, "call", fake_call)
    assert main(["dashboard", "--port", "8599"]) == 0
    cmd = seen["cmd"]
    assert cmd[cmd.index("--server.address") + 1] == "127.0.0.1"
    assert cmd[cmd.index("--server.port") + 1] == "8599"
    assert cmd[cmd.index("--server.headless") + 1] == "true"


def test_dashboard_address_can_be_overridden(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli.subprocess, "call", lambda cmd, env=None: seen.setdefault("cmd", cmd) and 0)
    main(["dashboard", "--address", "0.0.0.0"])
    assert seen["cmd"][seen["cmd"].index("--server.address") + 1] == "0.0.0.0"


def test_parser_defaults_are_secure_and_documented():
    parser = build_parser()
    args = parser.parse_args(["dashboard"])
    assert args.address == "127.0.0.1"
    assert config.DEFAULT_BIND_ADDRESS == "127.0.0.1"
    exp = parser.parse_args(["export"])
    assert exp.out == config.DEFAULT_WORKBOOK_PATH


def test_version_flag(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--version"])
    assert "1.1.0" in capsys.readouterr().out


def test_module_entry_point_runs_the_cli():
    result = subprocess.run(
        [sys.executable, "-m", "accviz", "--version"], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0
    assert "accviz 1.1.0" in result.stdout


def test_audit_with_reversed_period_exits_2(anomaly_dir, capsys):
    assert main(["audit", "--data", str(anomaly_dir), "--start", "2025-06-01", "--end", "2025-01-01"]) == 2
    assert "after end date" in capsys.readouterr().err
