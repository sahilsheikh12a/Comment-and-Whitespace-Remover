"""Whitespace processing: the three whitespace modes and the three newline modes."""

import pytest

from remover import WhitespaceMode, process_whitespace, remove_comments, separator_reason


def layout(source, whitespace="normalize", newlines="structure"):
    return process_whitespace(remove_comments(source).pieces, whitespace, newlines)


def out(source, whitespace="normalize", newlines="structure"):
    return layout(source, whitespace, newlines).text


def words(text):
    """Maximal runs of identifier/number characters, in order."""
    found, current = [], ""
    for ch in text:
        if ch.isalnum() or ch == "_":
            current += ch
        elif current:
            found.append(current)
            current = ""
    return found + ([current] if current else [])


# --- preserve ---------------------------------------------------------------


def test_preserve_mode_specification_example():
    assert out("int    x = 10;    // comment", "preserve") == "int    x = 10;"


def test_preserve_mode_keeps_trailing_whitespace_not_caused_by_a_comment():
    assert out("int x;   \n", "preserve") == "int x;   \n"


def test_preserve_mode_keeps_whitespace_on_both_sides_of_an_inline_comment():
    assert out("a = 1;  /* c */  b = 2;", "preserve") == "a = 1;    b = 2;"


def test_preserve_mode_keeps_whitespace_only_lines():
    assert out("a;\n   \nb;", "preserve") == "a;\n   \nb;"


# --- normalize ----------------------------------------------------------------


def test_normalize_specification_example():
    assert out("int    x    =    10;\nint       y =       20;") == "int x = 10;\nint y = 20;"


def test_normalize_turns_tabs_between_tokens_into_one_space():
    assert out("int\t\tx\t=\t10;") == "int x = 10;"


def test_normalize_keeps_indentation_verbatim():
    source = "int main() {\n    int value = 10;\n\treturn value;\n}\n"
    assert out(source) == source


def test_normalize_removes_trailing_whitespace():
    assert out("int x;   \t\nint y;  ") == "int x;\nint y;"


def test_normalize_drops_whitespace_after_a_comment_at_line_start():
    assert out("    /* lead */    int x;") == "    int x;"


def test_normalize_whitespace_around_an_inline_comment():
    assert out("a = 1;  /* c */  b = 2;") == "a = 1; b = 2;"


# --- compact ------------------------------------------------------------------


def test_compact_specification_example():
    assert out("int x = 10;\nint y = 20;\n", "compact") == "int x=10;\nint y=20;\n"


def test_compact_removes_indentation_and_space_around_operators():
    source = "int main() {\n    return a + b * c;\n}\n"
    assert out(source, "compact") == "int main(){\nreturn a+b*c;\n}\n"


@pytest.mark.parametrize(
    "source",
    [
        "int x = 10;",
        "unsigned long int count = 0UL;",
        "else if (x) goto end;",
        "return sizeof value;",
        "static const char *name = \"n\";",
        "struct point p; p . x = 1;",
    ],
)
def test_compact_never_merges_identifiers_keywords_or_numbers(source):
    assert words(out(source, "compact")) == words(source)


def test_compact_keeps_spaces_that_stop_operators_merging():
    source = "a = b - -c; x = y + +z; p = q / *r; i = j++ + ++k;"
    assert out(source, "compact") == "a=b- -c;x=y+ +z;p=q/ *r;i=j++ + ++k;"


def test_compact_keeps_spaces_that_protect_numbers_and_literal_prefixes():
    source = "v = 0xE + 1; w = 1 ... 3; s = L \"x\"; vector<vector<int> > m;"
    assert out(source, "compact") == "v=0xE +1;w=1 ... 3;s=L \"x\";vector<vector<int> >m;"


def test_compact_only_normalizes_preprocessor_directives():
    source = "#define  F (x)  x\n#include <stdio.h>\nint  y = F (1) ;\n"
    assert out(source, "compact") == "#define F (x) x\n#include <stdio.h>\nint y=F(1);\n"


def test_compact_treats_directive_continuation_lines_as_directives():
    source = "#define SUM(a, b) \\\n    ( (a) + (b) )\nint  z = SUM (1, 2) ;\n"
    assert out(source, "compact") == "#define SUM(a, b) \\\n( (a) + (b) )\nint z=SUM(1,2);\n"


# --- literals and comments ---------------------------------------------------


@pytest.mark.parametrize("mode", list(WhitespaceMode))
def test_whitespace_inside_literals_is_never_changed(mode):
    source = "char *s = \"a    b\t c\";  char t = ' ';"
    result = out(source, mode)
    assert '"a    b\t c"' in result
    assert "' '" in result


def test_removed_comment_between_tokens_leaves_one_space_only_when_needed():
    result = layout("int/**/value = 1;", "compact")
    assert result.text == "int value=1;"
    (separator,) = result.separators
    assert (separator.left, separator.right) == ("t", "v")
    assert separator.comment.text == "/**/"
    assert out("f(/* none */);") == "f();"
    assert out("x = 1;/* c */y = 2;") == "x = 1;y = 2;"


def test_removed_comment_between_operators_keeps_them_apart():
    assert out("a = b-/**/-c;") == "a = b- -c;"
    assert out("n = 1/**/.5;") == "n = 1 .5;"


# --- line breaks --------------------------------------------------------------


def test_blank_lines_kept_by_structure_and_collapsed_by_collapse():
    source = "a;\n\n\n\nb;\n"
    assert out(source) == source
    assert out(source, newlines="preserve") == source
    assert out(source, newlines="collapse") == "a;\n\nb;\n"


def test_collapse_removes_blank_lines_at_the_start_and_end():
    assert out("\n\n  \nint x;\n\n\n", newlines="collapse") == "int x;\n"


def test_comment_only_lines_are_removed_or_blanked():
    source = "a;\n// c\n\nb;\n"
    assert out(source) == "a;\n\nb;\n"
    assert out(source, newlines="preserve") == "a;\n\n\nb;\n"
    assert out(source, newlines="collapse") == "a;\n\nb;\n"


def test_preserve_newlines_keeps_the_lines_of_a_block_comment():
    source = "a;\n/* 1\n2\n3 */\nb;\n"
    assert out(source, newlines="preserve") == "a;\n\n\n\nb;\n"
    assert out(source) == "a;\nb;\n"


def test_block_comment_spanning_lines_joins_the_code_around_it():
    assert out("a = 1; /* x\ny */ b = 2;") == "a = 1; b = 2;"


def test_line_after_a_backslash_continuation_is_never_removed():
    source = "#define X 1 \\\n// note\nint y;\n"
    assert out(source) == "#define X 1 \\\n\nint y;\n"
    assert out(source, newlines="collapse") == "#define X 1 \\\n\nint y;\n"


def test_windows_line_endings_are_preserved():
    assert out("a  =  1;\r\nb = 2; // c\r\n") == "a = 1;\r\nb = 2;\r\n"


def test_form_feed_and_vertical_tab_are_whitespace_but_no_break_space_is_not():
    assert out("a\f\vb") == "a b"
    assert out("a b") == "a b"


# --- accounting ---------------------------------------------------------------


def test_whitespace_removed_is_counted_per_character():
    result = layout("int    x  =  1;   \n\n\n", "normalize", "collapse")
    assert result.text == "int x = 1;\n"
    # 11 spaces and 3 line feeds; 3 spaces and 1 line feed remain.
    assert result.whitespace_removed == 10


def test_comment_line_breaks_kept_are_counted():
    result = layout("a;\n/* 1\r\n2 */\nb;", "normalize", "preserve")
    assert result.comment_line_breaks_kept == 1
    assert result.comment_line_break_characters_kept == 2


@pytest.mark.parametrize(
    ("left", "right", "needed"),
    [
        ("int", "x", True),
        ("10", "L", True),
        ("café", "x", True),
        ("x", "=", False),
        ("=", "10", False),
        (";", "int", False),
        (")", "{", False),
        ("a", "(", False),
        ("+", "+", True),
        ("-", "-", True),
        ("-", ">", True),
        ("<", "<", True),
        (">", ">", True),
        ("&", "&", True),
        ("=", "=", True),
        ("/", "*p", True),
        ("/", "/", True),
        ("L", '"x"', True),
        ('"x"', "_s", True),
        ('"a"', '"b"', False),
        ("1", ".5", True),
        (".", "5", True),
        ("0xE", "+1", True),
        ("1e", "-", True),
        ("x", "-", False),
    ],
)
def test_separator_reason(left, right, needed):
    assert (separator_reason(left, right) is not None) is needed
