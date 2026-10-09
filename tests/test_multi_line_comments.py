"""Multi-line (/* */) comments through the full pipeline."""

from helpers import clean
from remover import Code, CommentKind, process
from remover.text import count_lines


def test_specification_example():
    source = "int x = 10;\n\n/*\nThis is a\nmulti-line comment.\n*/\n\nint y = 20;\n"
    assert clean(source) == "int x = 10;\n\n\nint y = 20;\n"


def test_comment_on_its_own_line():
    assert clean("int x = 10;\n/* comment */\nint y = 20;\n") == "int x = 10;\nint y = 20;\n"


def test_comment_between_two_statements_on_one_line():
    assert clean("int b = 10; /* comment */ int c = 20;") == "int b = 10; int c = 20;"


def test_comment_between_tokens_does_not_merge_them():
    result = process("int/**/value = 10;")
    assert result.cleaned_source == "int value = 10;"
    assert result.statistics.separators_inserted == 1


def test_comment_inside_parentheses_leaves_nothing_behind():
    assert clean("call(/* no arguments */);") == "call();"


def test_division_next_to_a_comment():
    assert clean("int result = a / /* comment */ b;") == "int result = a / b;"


def test_closing_delimiter_variants():
    for source in ("/**/x", "/***/x", "/* ** */x", "/*/ */x", "/* * / */x"):
        result = process(source)
        assert result.cleaned_source == "x", source
        assert len(result.detected_comments) == 1, source


def test_comment_spanning_lines_between_code():
    assert clean("a = 1; /* start\nmiddle\nend */ b = 2;") == "a = 1; b = 2;"


def test_preserve_newlines_keeps_every_line_number():
    source = "a = 1;\n/*\n * doc\n */\nb = 2; /* x\n y */ c = 3;\n"
    result = clean(source, newline_mode="preserve")
    assert count_lines(result) == count_lines(source)
    assert result.splitlines()[4] == "b = 2;"
    assert result.splitlines()[5] == "c = 3;"


def test_comments_do_not_nest():
    result = process("/* a /* b */ c */")
    assert result.cleaned_source == "c */"
    assert [w.code for w in result.warnings] == [Code.NESTED_COMMENT]


def test_comment_record():
    result = process("x;\n  /* two\n     lines */\n")
    (comment,) = result.detected_comments
    assert comment.kind is CommentKind.MULTI_LINE
    assert comment.text == "/* two\n     lines */"
    assert (comment.start.line, comment.start.column) == (2, 3)
    assert (comment.end.line, comment.end.column) == (3, 13)
    assert comment.terminated


def test_unterminated_comment_is_an_error_and_keeps_preceding_code():
    result = process("int x = 10;\n\n/* comment that never ends\n")
    assert result.cleaned_source == "int x = 10;\n\n"
    (error,) = result.errors
    assert error.code is Code.UNTERMINATED_COMMENT
    assert (error.line, error.column) == (3, 1)
    assert not result.success
    assert not result.output_complete
