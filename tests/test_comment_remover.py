"""The comment-removal stage: lexemes, pieces and diagnostics built from FSM runs."""

from remover import (
    Code,
    CommentKind,
    ErrorCategory,
    LiteralKind,
    PieceKind,
    Severity,
    State,
    remove_comments,
)


def test_output_is_the_concatenation_of_the_pieces():
    result = remove_comments('x = "a" /* b */ + \'c\'; // d\ny')
    assert "".join(piece.text for piece in result.pieces) == result.output


def test_block_comment_becomes_one_space_in_the_fsm_output():
    assert remove_comments("a/**/b").output == "a b"


def test_line_comment_is_removed_and_its_line_break_kept():
    assert remove_comments("a // c\nb").output == "a \nb"


def test_comments_are_recorded_with_text_and_positions():
    result = remove_comments("int a; // first\n/* second\n line */ int b;")
    first, second = result.comments
    assert first.kind is CommentKind.SINGLE_LINE
    assert first.text == "// first"
    assert (first.start.line, first.start.column, first.start.offset) == (1, 8, 7)
    assert (first.end.line, first.end.column) == (1, 15)
    assert first.terminated
    assert second.kind is CommentKind.MULTI_LINE
    assert second.text == "/* second\n line */"
    assert (second.start.line, second.start.column) == (2, 1)
    assert (second.end.line, second.end.column) == (3, 8)
    assert second.line_breaks == 1


def test_pieces_are_tagged_by_kind():
    result = remove_comments("x = \"s\" /* c */ + 'c'; // d")
    assert [piece.kind for piece in result.pieces] == [
        PieceKind.CODE,
        PieceKind.STRING_LITERAL,
        PieceKind.CODE,
        PieceKind.COMMENT,
        PieceKind.CODE,
        PieceKind.CHARACTER_LITERAL,
        PieceKind.CODE,
        PieceKind.COMMENT,
    ]


def test_division_slash_stays_in_the_code_piece():
    result = remove_comments("a = b / c;")
    assert [(piece.kind, piece.text) for piece in result.pieces] == [(PieceKind.CODE, "a = b / c;")]


def test_slash_before_a_string_is_code_and_the_string_a_literal():
    result = remove_comments('x/"y"')
    assert [(piece.kind, piece.text) for piece in result.pieces] == [
        (PieceKind.CODE, "x/"),
        (PieceKind.STRING_LITERAL, '"y"'),
    ]


def test_literals_are_recorded():
    result = remove_comments("s = \"a\\\"b\"; c = '\\n';")
    string, character = result.literals
    assert string.kind is LiteralKind.STRING and string.text == '"a\\"b"'
    assert character.kind is LiteralKind.CHARACTER and character.text == "'\\n'"
    assert string.terminated and character.terminated
    assert (string.start.column, string.end.column) == (5, 10)


def test_unterminated_comment_is_reported_where_it_starts():
    result = remove_comments("int x = 10;\n\n/* comment that never ends\n")
    (diagnostic,) = result.diagnostics
    assert diagnostic.category is ErrorCategory.LEXICAL
    assert diagnostic.severity is Severity.ERROR
    assert diagnostic.code is Code.UNTERMINATED_COMMENT
    assert (diagnostic.line, diagnostic.column) == (3, 1)
    assert not result.comments[0].terminated
    assert not result.accepted
    assert result.final_state is State.MULTI_LINE_COMMENT
    report = diagnostic.format()
    assert report.startswith("Lexical Structure Error:\nUnterminated multi-line comment.")
    assert "Location:\nLine 3, Column 1" in report
    assert "Recovery:\nReached end of input while inside a multi-line comment." in report


def test_unterminated_string_at_end_of_line_recovers_on_the_next_line():
    result = remove_comments('char* text = "Hello;\nint y; // gone\n')
    (diagnostic,) = result.diagnostics
    assert diagnostic.code is Code.UNTERMINATED_STRING
    assert (diagnostic.line, diagnostic.column) == (1, 14)
    assert "Line 1 ended before the closing" in diagnostic.recovery
    assert result.literals[0].text == '"Hello;'
    assert not result.literals[0].terminated
    assert len(result.comments) == 1  # the next line was scanned normally
    assert result.accepted


def test_unterminated_character_literal_at_end_of_input():
    result = remove_comments("char symbol = 'a")
    (diagnostic,) = result.diagnostics
    assert diagnostic.code is Code.UNTERMINATED_CHARACTER
    assert (diagnostic.line, diagnostic.column) == (1, 15)
    assert result.final_state is State.CHARACTER_LITERAL


def test_nested_comment_opener_is_a_warning_at_its_position():
    result = remove_comments("/* outer\n  /* inner */ x;")
    (warning,) = result.diagnostics
    assert warning.code is Code.NESTED_COMMENT
    assert warning.severity is Severity.WARNING
    assert (warning.line, warning.column) == (2, 3)
    assert result.output.endswith(" x;")


def test_empty_character_literal_is_a_warning():
    (warning,) = remove_comments("c = '';").diagnostics
    assert warning.code is Code.EMPTY_CHARACTER_LITERAL


def test_counts_cover_the_whole_run():
    source = "a /* b */ c // d\n"
    result = remove_comments(source)
    assert result.transition_count == len(source) + 1
    assert result.characters_scanned == len(source)
    assert sum(result.state_visits.values()) == len(source)
    assert result.state_visits[State.MULTI_LINE_COMMENT] == 4  # " b *" after the opener
    assert result.transitions_complete
    assert len(result.transitions) == result.transition_count


def test_transition_log_can_be_capped_without_affecting_the_counts():
    source = "int a; // comment"
    result = remove_comments(source, max_recorded_transitions=5)
    assert len(result.transitions) == 5
    assert not result.transitions_complete
    assert result.transition_count == len(source) + 1
    assert result.output == "int a; "


def test_transition_recording_can_be_switched_off():
    result = remove_comments("a // b", record_transitions=False)
    assert result.transitions == ()
    assert result.transition_count == 7
