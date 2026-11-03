"""CSV reading: header whitespace and line endings from spreadsheet exports."""

from __future__ import annotations

import io

import pytest

from accviz.loader import read_csv_table

pytestmark = pytest.mark.unit


def test_spaces_around_header_names_are_ignored():
    table = read_csv_table(io.StringIO("account_code, account_name ,account_type\n1000, Cash ,Asset\n"))
    assert list(table.columns) == ["account_code", "account_name", "account_type"]
    assert table.iloc[0]["account_name"] == " Cash "  # values keep their text; only headers are trimmed


def test_windows_line_endings_are_read():
    table = read_csv_table(io.StringIO("a,b\r\n1,2\r\n"))
    assert table.to_dict("records") == [{"a": "1", "b": "2"}]


def test_values_are_read_as_text():
    table = read_csv_table(io.StringIO("amount\n0010\n"))
    assert table.iloc[0]["amount"] == "0010"
