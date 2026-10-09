"""The example programs, processed by the real pipeline."""

import shutil
import subprocess

import pytest

from remover import Code, ErrorCategory, NewlineMode, WhitespaceMode, process

EXPECTED_FILES = {
    "basic.c",
    "single_line_comments.c",
    "multi_line_comments.c",
    "strings_and_characters.c",
    "whitespace.c",
    "edge_cases.c",
    "errors.c",
    "literal_errors.c",
    "complete_program.c",
}
ALL_MODES = [(ws, nl) for ws in WhitespaceMode for nl in NewlineMode]


def words(text):
    found, current = [], ""
    for ch in text:
        if ch.isalnum() or ch == "_":
            current += ch
        elif current:
            found.append(current)
            current = ""
    return found + ([current] if current else [])


def test_example_files_exist(example_sources):
    assert EXPECTED_FILES <= set(example_sources)


@pytest.mark.parametrize(("whitespace", "newlines"), ALL_MODES)
def test_every_example_runs_through_the_fsm(example_sources, whitespace, newlines):
    for name, source in example_sources.items():
        result = process(source, whitespace_mode=whitespace, newline_mode=newlines)
        assert result.fsm_ran, name
        assert not [e for e in result.errors if e.category is ErrorCategory.PROCESSING], name
        assert len(result.transition_log) == len(source) + 1, name


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("basic.c", "int a = 10;\nint b = 20;\nint sum = a + b;\n"),
        ("single_line_comments.c", "int a = 10;\nint b = 20;\nint sum = a + b;\n"),
        ("multi_line_comments.c", "int a = 10;\n\n\nint b = 20;\n"),
        (
            "strings_and_characters.c",
            'char* url = "https://example.com";\n'
            'char* text = "This contains // and /* markers */";\n'
            "char symbol = '/';\n",
        ),
        ("whitespace.c", "int a = 10;\nint b = 20;\nint sum = a + b;\n"),
        (
            "edge_cases.c",
            'int a = 10 / 2;\nint b = 10; int c = 20;\nchar* text = "escaped quote: \\"";\n',
        ),
    ],
)
def test_example_output_with_default_settings(example_sources, name, expected):
    result = process(example_sources[name])
    assert result.cleaned_source == expected
    assert result.success


def test_whitespace_example_in_each_mode(example_sources):
    source = example_sources["whitespace.c"]
    assert process(source, whitespace_mode="preserve").cleaned_source == source
    assert process(source, whitespace_mode="compact").cleaned_source == (
        "int a=10;\nint b=20;\nint sum=a+b;\n"
    )


def test_error_examples_report_their_errors(example_sources):
    result = process(example_sources["errors.c"])
    assert [(e.code, e.line, e.column) for e in result.errors] == [(Code.UNTERMINATED_COMMENT, 3, 1)]

    result = process(example_sources["literal_errors.c"])
    assert [(e.code, e.line, e.column) for e in result.errors] == [
        (Code.UNTERMINATED_STRING, 1, 18),
        (Code.UNTERMINATED_CHARACTER, 2, 15),
    ]
    assert "comment" not in result.cleaned_source


def test_compact_mode_never_merges_words_in_any_example(example_sources):
    for name, source in example_sources.items():
        normalized = process(source, whitespace_mode="normalize").cleaned_source
        compacted = process(source, whitespace_mode="compact").cleaned_source
        assert words(compacted) == words(normalized), name


def _c_compiler():
    return next((cc for cc in ("gcc", "clang", "cc") if shutil.which(cc)), None)


@pytest.mark.skipif(_c_compiler() is None, reason="no C compiler installed")
@pytest.mark.parametrize(("whitespace", "newlines"), ALL_MODES)
def test_cleaned_program_compiles_and_behaves_like_the_original(
    example_sources, tmp_path, whitespace, newlines
):
    compiler = _c_compiler()
    source = example_sources["complete_program.c"]
    cleaned = process(source, whitespace_mode=whitespace, newline_mode=newlines).cleaned_source

    outputs = []
    for label, text in (("original", source), ("cleaned", cleaned)):
        c_file = tmp_path / f"{label}.c"
        binary = tmp_path / label
        c_file.write_text(text, encoding="utf-8")
        subprocess.run(
            [compiler, "-std=c11", "-Wall", "-Werror", "-o", str(binary), str(c_file)],
            check=True,
            capture_output=True,
        )
        outputs.append(subprocess.run([str(binary)], capture_output=True, text=True, check=True).stdout)
    assert outputs[0] == outputs[1]
