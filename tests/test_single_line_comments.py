"""Single-line (//) comments through the full pipeline."""

from helpers import clean
from remover import CommentKind, process


def test_comment_after_a_statement_is_removed():
    assert clean("int x = 10; // comment") == "int x = 10;"


def test_specification_example():
    source = "int x = 10; // This is a comment\nint y = 20; // Another comment\n"
    assert clean(source) == "int x = 10;\nint y = 20;\n"


def test_line_break_after_the_comment_is_kept():
    assert clean("a = 1; // c\nb = 2;") == "a = 1;\nb = 2;"


def test_comment_at_end_of_file_without_line_break():
    assert clean("x = 1; // end") == "x = 1;"


def test_comment_only_line():
    source = "a = 1;\n// a whole line\nb = 2;\n"
    assert clean(source) == "a = 1;\nb = 2;\n"
    assert clean(source, newline_mode="preserve") == "a = 1;\n\nb = 2;\n"


def test_indented_comment_only_line_leaves_no_whitespace():
    assert clean("{\n    // note\n    x();\n}", newline_mode="preserve") == "{\n\n    x();\n}"


def test_block_comment_markers_inside_a_line_comment_are_ignored():
    result = process("a = 1; // has /* and */ inside\nb = 2;")
    assert result.cleaned_source == "a = 1;\nb = 2;"
    assert [c.kind for c in result.detected_comments] == [CommentKind.SINGLE_LINE]


def test_extra_slashes_belong_to_the_comment():
    result = process("/// doc comment\nint f();")
    assert result.cleaned_source == "int f();"
    assert result.detected_comments[0].text == "/// doc comment"


def test_url_inside_a_comment_is_removed_with_it():
    assert clean("x(); // see https://example.com/a//b") == "x();"


def test_windows_line_endings_survive():
    assert clean("a; // one\r\nb; // two\r\n") == "a;\r\nb;\r\n"


def test_comment_records():
    result = process("int a; // first\nint b; // second")
    first, second = result.detected_comments
    assert (first.text, first.start.line, first.start.column) == ("// first", 1, 8)
    assert (second.text, second.start.line, second.start.column) == ("// second", 2, 8)
    assert result.statistics.single_line_comments == 2
    assert result.statistics.multi_line_comments == 0
