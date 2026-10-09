"""Edge cases: empty and odd input, malformed input, newlines, Unicode, validation."""

import pytest

from helpers import clean
from remover import (
    Code,
    ErrorCategory,
    InputValidationError,
    State,
    decode_source,
    process,
)


def test_empty_source():
    result = process("")
    assert result.cleaned_source == ""
    assert result.success
    assert [w.code for w in result.warnings] == [Code.EMPTY_INPUT]
    assert len(result.transition_log) == 1  # only the end-of-input transition
    assert result.final_state is State.NORMAL


def test_whitespace_only_source():
    source = "   \n\t\n  "
    assert clean(source) == "\n\n"
    assert clean(source, newline_mode="collapse") == ""
    assert clean(source, whitespace_mode="preserve") == source


def test_source_with_only_comments():
    source = "// a\n/* b */\n// c"
    assert clean(source) == ""
    assert clean(source, newline_mode="preserve") == "\n\n"
    assert process(source).statistics.comments_detected == 3


@pytest.mark.parametrize(
    "source",
    ["a / b", "a /= b;", "x = y/z;", "p = 1 / 2 / 3;", "q = a/ b;", "r = (a)/(b);", "int a = 10 / 2;"],
)
def test_slash_that_does_not_start_a_comment(source):
    result = process(source)
    assert result.cleaned_source == source
    assert result.detected_comments == ()


def test_source_ending_with_a_slash():
    result = process("x = a /")
    assert result.cleaned_source == "x = a /"
    assert result.success


def test_star_slash_outside_a_comment_is_ordinary_code():
    assert clean("x = a */ b;") == "x = a */ b;"


def test_adjacent_comments():
    result = process("a/* one *//* two */b")
    assert len(result.detected_comments) == 2
    assert result.cleaned_source == "a b"
    assert clean("x; /* one */// two\ny;") == "x;\ny;"


def test_comment_at_the_beginning_of_the_file():
    assert clean("/* header */\nint x;\n") == "int x;\n"
    assert clean("// header\nint x;\n") == "int x;\n"
    assert clean("/* header */ int x;\n") == "int x;\n"


def test_comment_at_the_end_of_the_file():
    assert clean("int x;\n/* trailer */") == "int x;\n"
    assert clean("int x; // trailer") == "int x;"


def test_unterminated_multi_line_comment_report():
    result = process("int x = 10;\n\n/* comment that never ends\n")
    (error,) = result.errors
    assert error.category is ErrorCategory.LEXICAL
    report = error.format()
    assert report.startswith(
        "Lexical Structure Error:\nUnterminated multi-line comment.\n\nLocation:\nLine 3, Column 1\n\nRecovery:\n"
    )
    assert "Reached end of input while inside a multi-line comment." in report
    assert not result.output_complete


def test_unterminated_string_and_character_literals():
    assert [e.code for e in process('char* text = "Hello;').errors] == [Code.UNTERMINATED_STRING]
    assert [e.code for e in process("char symbol = 'a;").errors] == [Code.UNTERMINATED_CHARACTER]


def test_every_error_is_reported_in_source_order():
    result = process("a = \"x;\nb = 'y;\n/* never")
    assert [(e.code, e.line) for e in result.errors] == [
        (Code.UNTERMINATED_STRING, 1),
        (Code.UNTERMINATED_CHARACTER, 2),
        (Code.UNTERMINATED_COMMENT, 3),
    ]


def test_unicode_in_comments_and_strings():
    result = process('int x = 1; // café ☕ 日本語\nchar *s = "naïve ✓"; /* Ω */\n')
    assert result.cleaned_source == 'int x = 1;\nchar *s = "naïve ✓";\n'
    first, second = result.detected_comments
    assert first.text == "// café ☕ 日本語"
    assert (second.start.line, second.start.column) == (2, 22)


def test_unix_and_windows_line_endings_give_the_same_code():
    unix = "int a = 1; // one\n/* two */\nint b = 2;\n\n/*\n three\n*/\nint c;\n"
    windows = unix.replace("\n", "\r\n")
    for mode in ("structure", "preserve", "collapse"):
        assert clean(windows, newline_mode=mode) == clean(unix, newline_mode=mode).replace("\n", "\r\n")


def test_classic_mac_line_endings():
    assert clean("a; // c\rb;\r") == "a;\rb;\r"


def test_mixed_line_endings_are_kept_with_a_warning():
    result = process("a; // x\nb;\r\n")
    assert result.cleaned_source == "a;\nb;\r\n"
    assert [w.code for w in result.warnings] == [Code.MIXED_LINE_ENDINGS]


def test_positions_after_windows_line_endings():
    result = process("a;\r\n  /* c */\r\n")
    comment = result.detected_comments[0]
    assert (comment.start.line, comment.start.column) == (2, 3)


def test_text_that_is_not_a_string_is_rejected():
    result = process(b"int x;")  # type: ignore[arg-type]
    (error,) = result.errors
    assert error.code is Code.NOT_TEXT
    assert error.category is ErrorCategory.INPUT_VALIDATION
    assert not result.fsm_ran
    assert result.transition_log == ()


def test_binary_data_is_rejected_with_its_location():
    result = process("int x;\nab\x00c")
    (error,) = result.errors
    assert error.code is Code.NUL_CHARACTER
    assert (error.line, error.column) == (2, 3)


def test_oversized_input_is_rejected():
    result = process("x" * 11, max_input_characters=10)
    assert [e.code for e in result.errors] == [Code.INPUT_TOO_LARGE]
    assert result.statistics is None


def test_decoding_uploaded_bytes():
    assert decode_source("int x; // é".encode()) == "int x; // é"
    assert decode_source(b"\xef\xbb\xbfint x;") == "int x;"
    with pytest.raises(InputValidationError) as caught:
        decode_source(b"int \xff x;")
    assert caught.value.diagnostic.code is Code.UNDECODABLE_INPUT


def test_large_input_is_processed_completely():
    source = "int a = 1; /* note */ // tail\n" * 3000
    result = process(source, record_transitions=False)
    assert result.cleaned_source == "int a = 1;\n" * 3000
    assert result.statistics.fsm_transitions == len(source) + 1
    assert result.statistics.comments_detected == 6000
