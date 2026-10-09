"""Formatting helpers shared by the UI and the CLI."""

import csv
import io

from helpers import run_fsm
from remover.display import (
    excerpt,
    format_log,
    inline_text,
    log_to_csv,
    printable,
    printable_text,
    record_row,
    source_lines,
)


def test_printable_makes_invisible_characters_visible():
    assert printable(" ") == "␣"
    assert printable("\n") == "\\n"
    assert printable("\r") == "\\r"
    assert printable("\t") == "\\t"
    assert printable(None) == "EOF"
    assert printable("\x01") == "\\x01"
    assert printable("é") == "é"
    assert printable_text("a b\n") == "a␣b\\n"


def test_inline_text_keeps_spaces_and_marks_line_breaks():
    assert inline_text("/* a\r\n b */") == "/* a ↵  b */"
    assert inline_text("x\ty") == "x⇥y"


def test_source_lines_and_excerpt():
    source = "int a;\r\n\tchar *s = \"x;\nlast"
    assert source_lines(source) == ["int a;", '\tchar *s = "x;', "last"]
    assert excerpt(source, 2, 12) == '2 |  char *s = "x;\n  |            ^'
    assert excerpt(source, 9, 1) == ""


def test_record_rows_and_csv_export():
    records = run_fsm("a/ b")
    row = record_row(records[2])
    assert row["Current State"] == "POSSIBLE_COMMENT"
    assert row["Emitted"] == "/␣"
    assert record_row(records[-1])["Char"] == "EOF"
    parsed = list(csv.DictReader(io.StringIO(log_to_csv(records))))
    assert len(parsed) == len(records)
    assert parsed[1]["Output"] == "BUFFER"


def test_format_log_has_one_line_per_record():
    records = run_fsm("x//y")
    lines = format_log(records).splitlines()
    assert len(lines) == 2 + len(records)
    assert "SINGLE_LINE_COMMENT" in lines[4]
