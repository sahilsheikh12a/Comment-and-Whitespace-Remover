"""Command-line interface: python -m remover."""

import io
import subprocess
import sys

from helpers import EXAMPLES_DIR, ROOT
from remover.__main__ import main


def test_cleans_a_file(capsys):
    status = main([str(EXAMPLES_DIR / "single_line_comments.c")])
    captured = capsys.readouterr()
    assert status == 0
    assert captured.out == "int a = 10;\nint b = 20;\nint sum = a + b;\n"
    assert captured.err == ""


def test_whitespace_and_newline_options(capsys):
    main([str(EXAMPLES_DIR / "whitespace.c"), "--whitespace", "compact"])
    assert capsys.readouterr().out == "int a=10;\nint b=20;\nint sum=a+b;\n"
    main([str(EXAMPLES_DIR / "multi_line_comments.c"), "-n", "collapse"])
    assert capsys.readouterr().out == "int a = 10;\n\nint b = 20;\n"


def test_errors_are_reported_with_location_and_exit_status_1(capsys):
    status = main([str(EXAMPLES_DIR / "errors.c")])
    captured = capsys.readouterr()
    assert status == 1
    assert "Unterminated multi-line comment." in captured.err
    assert "Line 3, Column 1" in captured.err
    assert "3 | /* This comment never ends\n  | ^" in captured.err
    assert captured.out == "int a = 10;\n\n"


def test_trace_prints_the_transition_log(capsys):
    main([str(EXAMPLES_DIR / "basic.c"), "--trace"])
    out = capsys.readouterr().out
    source = (EXAMPLES_DIR / "basic.c").read_text()
    assert out.splitlines()[0].split()[:3] == ["step", "line:col", "char"]
    assert len(out.splitlines()) == 2 + len(source) + 1


def test_statistics_go_to_standard_error(capsys):
    main([str(EXAMPLES_DIR / "basic.c"), "--stats"])
    err = capsys.readouterr().err
    assert "FSM Transitions:" in err
    assert "Comments Detected:" in err


def test_reads_standard_input(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"x; /* c */ y;\n")))
    assert main([]) == 0
    assert capsys.readouterr().out == "x; y;\n"


def test_writes_an_output_file(tmp_path):
    target = tmp_path / "clean.c"
    assert main([str(EXAMPLES_DIR / "edge_cases.c"), "-o", str(target)]) == 0
    assert target.read_text() == 'int a = 10 / 2;\nint b = 10; int c = 20;\nchar* text = "escaped quote: \\"";\n'


def test_missing_file(capsys):
    assert main(["does-not-exist.c"]) == 1
    assert "cannot read" in capsys.readouterr().err


def test_module_entry_point():
    completed = subprocess.run(
        [sys.executable, "-m", "remover", "--help"], cwd=ROOT, capture_output=True, text=True
    )
    assert completed.returncode == 0
    assert "--whitespace" in completed.stdout
