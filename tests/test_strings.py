"""String and character literals: comment markers inside them are text."""

import pytest

from helpers import clean
from remover import Code, LiteralKind, process


@pytest.mark.parametrize(
    "source",
    [
        'char* text = "// not a comment";',
        'char* text = "/* not a comment */";',
        'char* url = "https://example.com";',
        'char* message = "This is not a // comment";',
        'char* text = "This contains // and /* markers */";',
        "char symbol = '/';",
        "char star = '*';",
        "char quote = '\"';",
        'char* path = "C:\\\\temp\\\\";',
    ],
)
@pytest.mark.parametrize("mode", ["preserve", "normalize"])
def test_literal_is_unchanged(source, mode):
    assert clean(source, whitespace_mode=mode) == source


def test_escaped_quotes_do_not_end_the_string():
    source = 'char* text = "A quote: \\" and a slash: \\\\";'
    assert clean(source) == source


def test_escaped_quote_followed_by_comment_marker_stays_in_the_string():
    source = 'char* s = "say \\"hi\\" // not a comment";'
    assert clean(source) == source


def test_escaped_backslash_closes_the_string_before_a_real_comment():
    assert clean('s = "a\\\\"; // comment') == 's = "a\\\\";'


def test_escaped_single_quote_in_a_character_literal():
    assert clean("char q = '\\''; // quote") == "char q = '\\'';"


def test_comment_right_after_a_string():
    assert clean('puts("x");// done') == 'puts("x");'


def test_string_right_after_a_comment():
    assert clean('/* c */"s"') == '"s"'


def test_whitespace_inside_literals_survives_compact_mode():
    source = "s = \"a    b\";  c = ' ';"
    assert clean(source, whitespace_mode="compact") == "s=\"a    b\";c=' ';"


def test_prefixed_and_adjacent_literals():
    assert clean('w = L"wide"; u = u8"utf8"; s = "a" "b";') == 'w = L"wide"; u = u8"utf8"; s = "a" "b";'


def test_backslash_newline_inside_a_string_continues_it():
    result = process('s = "abc\\\ndef"; // c\n')
    assert result.cleaned_source == 's = "abc\\\ndef";\n'
    assert not result.errors


def test_literals_are_reported():
    result = process("char* a = \"x\"; char b = 'y'; char c = '\\n';")
    assert [(lit.kind, lit.text) for lit in result.detected_literals] == [
        (LiteralKind.STRING, '"x"'),
        (LiteralKind.CHARACTER, "'y'"),
        (LiteralKind.CHARACTER, "'\\n'"),
    ]
    assert result.statistics.string_literals == 1
    assert result.statistics.character_literals == 2


def test_unterminated_string_at_end_of_input():
    result = process('char* text = "Hello;')
    (error,) = result.errors
    assert error.code is Code.UNTERMINATED_STRING
    assert (error.line, error.column) == (1, 14)
    assert result.cleaned_source == 'char* text = "Hello;'


def test_unterminated_string_at_end_of_line_does_not_swallow_the_file():
    result = process('char* text = "Hello;\nint y = 2; // comment\n')
    assert result.cleaned_source == 'char* text = "Hello;\nint y = 2;\n'
    assert [e.code for e in result.errors] == [Code.UNTERMINATED_STRING]


def test_unterminated_character_literal():
    result = process("char symbol = 'a;\nint z; // ok\n")
    (error,) = result.errors
    assert error.code is Code.UNTERMINATED_CHARACTER
    assert (error.line, error.column) == (1, 15)
    assert result.cleaned_source == "char symbol = 'a;\nint z;\n"
