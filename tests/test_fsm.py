"""The FSM engine: states, transitions, buffering, end of input, the log."""

import pytest

from helpers import run_fsm
from remover import CommentFSM, Event, OutputAction, ProcessingError, State

S = State


def path(source: str) -> list[State]:
    """The state after each character of ``source``."""
    return [record.next_state for record in run_fsm(source)[:-1]]


def test_initial_state_is_normal_with_empty_buffer_and_output():
    fsm = CommentFSM()
    assert fsm.state is S.NORMAL
    assert fsm.buffer == ""
    assert fsm.output == ""
    assert not fsm.finished


def test_ordinary_characters_are_copied_in_normal():
    records = run_fsm("int x = 10;")
    for record in records[:-1]:
        assert record.current_state is S.NORMAL and record.next_state is S.NORMAL
        assert record.output is OutputAction.EMIT
        assert record.emitted == record.character
    assert "".join(r.emitted for r in records) == "int x = 10;"


def test_slash_is_buffered_until_the_next_character():
    fsm = CommentFSM()
    record = fsm.feed("/")
    assert (record.current_state, record.next_state) == (S.NORMAL, S.POSSIBLE_COMMENT)
    assert record.output is OutputAction.BUFFER
    assert record.emitted == "" and record.buffer == "/"
    assert fsm.output == ""


def test_double_slash_starts_a_single_line_comment():
    records = run_fsm("//")
    second = records[1]
    assert (second.current_state, second.next_state) == (S.POSSIBLE_COMMENT, S.SINGLE_LINE_COMMENT)
    assert second.output is OutputAction.DISCARD_BUFFER
    assert second.event is Event.SINGLE_LINE_COMMENT_START
    assert second.discarded == "//" and second.buffer == ""


def test_slash_star_starts_a_multi_line_comment():
    second = run_fsm("/*")[1]
    assert (second.current_state, second.next_state) == (S.POSSIBLE_COMMENT, S.MULTI_LINE_COMMENT)
    assert second.event is Event.MULTI_LINE_COMMENT_START
    assert second.discarded == "/*"


def test_slash_followed_by_anything_else_is_an_operator():
    records = run_fsm("a/b")
    flush = records[2]
    assert (flush.current_state, flush.next_state) == (S.POSSIBLE_COMMENT, S.NORMAL)
    assert flush.output is OutputAction.FLUSH_AND_EMIT
    assert flush.emitted == "/b"
    assert "".join(r.emitted for r in records) == "a/b"


@pytest.mark.parametrize("follower", [" ", "=", "\n", "\\", "1"])
def test_division_slash_is_never_lost(follower):
    records = run_fsm("a/" + follower)
    assert "".join(r.emitted for r in records) == "a/" + follower


def test_single_line_comment_ends_at_newline_which_is_kept():
    records = run_fsm("// hi\nx")
    assert path("// hi\nx") == [
        S.POSSIBLE_COMMENT, S.SINGLE_LINE_COMMENT, S.SINGLE_LINE_COMMENT,
        S.SINGLE_LINE_COMMENT, S.SINGLE_LINE_COMMENT, S.NORMAL, S.NORMAL,
    ]
    newline = records[5]
    assert newline.event is Event.COMMENT_END
    assert newline.output is OutputAction.EMIT and newline.emitted == "\n"
    assert "".join(r.emitted for r in records) == "\nx"


def test_multi_line_comment_closes_only_on_star_slash():
    assert path("/* a*b */") == [
        S.POSSIBLE_COMMENT, S.MULTI_LINE_COMMENT, S.MULTI_LINE_COMMENT, S.MULTI_LINE_COMMENT,
        S.POSSIBLE_COMMENT_END, S.MULTI_LINE_COMMENT, S.MULTI_LINE_COMMENT,
        S.POSSIBLE_COMMENT_END, S.NORMAL,
    ]


def test_repeated_stars_before_the_closing_slash():
    assert path("/***/")[-3:] == [S.POSSIBLE_COMMENT_END, S.POSSIBLE_COMMENT_END, S.NORMAL]


def test_line_breaks_inside_multi_line_comment_are_discarded():
    records = run_fsm("/*\n\n*/")
    for record in records[2:4]:
        assert record.current_state is S.MULTI_LINE_COMMENT
        assert record.output is OutputAction.DISCARD


def test_closing_a_multi_line_comment_emits_one_space():
    records = run_fsm("a/**/b")
    close = records[4]
    assert close.output is OutputAction.REPLACE_WITH_SPACE
    assert close.event is Event.COMMENT_END
    assert close.emitted == " " and close.discarded == "/"
    assert "".join(r.emitted for r in records) == "a b"


def test_string_literal_ignores_comment_markers():
    source = '"// /* */"'
    states = path(source)
    assert states[0] is S.STRING_LITERAL
    assert all(state is S.STRING_LITERAL for state in states[1:-1])
    assert states[-1] is S.NORMAL
    assert "".join(r.emitted for r in run_fsm(source)) == source


def test_escaped_quote_does_not_end_the_string():
    assert path(r'"a\"b"') == [
        S.STRING_LITERAL, S.STRING_LITERAL, S.STRING_ESCAPE,
        S.STRING_LITERAL, S.STRING_LITERAL, S.NORMAL,
    ]


def test_escaped_backslash_lets_the_next_quote_end_the_string():
    assert path(r'"a\\"x') == [
        S.STRING_LITERAL, S.STRING_LITERAL, S.STRING_ESCAPE, S.STRING_LITERAL, S.NORMAL, S.NORMAL,
    ]


def test_character_literal_holding_a_slash():
    assert path("'/'") == [S.CHARACTER_LITERAL, S.CHARACTER_LITERAL, S.NORMAL]


def test_escaped_single_quote_in_character_literal():
    assert path(r"'\''") == [S.CHARACTER_LITERAL, S.CHARACTER_ESCAPE, S.CHARACTER_LITERAL, S.NORMAL]


def test_double_quote_inside_character_literal_is_plain_text():
    assert path("'\"'") == [S.CHARACTER_LITERAL, S.CHARACTER_LITERAL, S.NORMAL]


def test_raw_newline_in_string_is_an_error_and_scanning_recovers():
    records = run_fsm('"abc\n//x')
    newline = records[4]
    assert newline.event is Event.UNTERMINATED_STRING
    assert (newline.current_state, newline.next_state) == (S.STRING_LITERAL, S.NORMAL)
    assert records[6].event is Event.SINGLE_LINE_COMMENT_START


def test_raw_newline_in_character_literal_is_an_error():
    newline = run_fsm("'a\n")[2]
    assert newline.event is Event.UNTERMINATED_CHARACTER
    assert newline.next_state is S.NORMAL


@pytest.mark.parametrize(
    ("source", "state_before_end", "final_state", "event", "emitted"),
    [
        ("", S.NORMAL, S.NORMAL, Event.NONE, ""),
        ("x", S.NORMAL, S.NORMAL, Event.NONE, ""),
        ("a/", S.POSSIBLE_COMMENT, S.NORMAL, Event.NONE, "/"),
        ("// c", S.SINGLE_LINE_COMMENT, S.NORMAL, Event.COMMENT_END, ""),
        ("/* c", S.MULTI_LINE_COMMENT, S.MULTI_LINE_COMMENT, Event.UNTERMINATED_COMMENT, ""),
        ("/* c *", S.POSSIBLE_COMMENT_END, S.POSSIBLE_COMMENT_END, Event.UNTERMINATED_COMMENT, ""),
        ('"abc', S.STRING_LITERAL, S.STRING_LITERAL, Event.UNTERMINATED_STRING, ""),
        ('"ab\\', S.STRING_ESCAPE, S.STRING_ESCAPE, Event.UNTERMINATED_STRING, ""),
        ("'a", S.CHARACTER_LITERAL, S.CHARACTER_LITERAL, Event.UNTERMINATED_CHARACTER, ""),
        ("'\\", S.CHARACTER_ESCAPE, S.CHARACTER_ESCAPE, Event.UNTERMINATED_CHARACTER, ""),
    ],
)
def test_end_of_input(source, state_before_end, final_state, event, emitted):
    end = run_fsm(source)[-1]
    assert end.is_end_of_input
    assert end.character is None and end.input_class is None
    assert end.current_state is state_before_end
    assert end.next_state is final_state
    assert end.event is event
    assert end.emitted == emitted
    assert end.offset == len(source)


def test_every_character_is_consumed_exactly_once():
    source = 'int a = 1; /* x */ // y\n"s" \'c\' a/b'
    records = run_fsm(source)
    consumed = records[:-1]
    assert [r.offset for r in consumed] == list(range(len(source)))
    assert "".join(r.character for r in consumed) == source
    assert [r.step for r in records] == list(range(len(source) + 1))


def test_output_length_matches_the_emitted_text():
    total = 0
    for record in run_fsm("a /* b */ c // d\ne/f"):
        total += len(record.emitted)
        assert record.output_length == total


def test_buffer_is_non_empty_exactly_in_possible_comment():
    for record in run_fsm("a/b//c\n/*d*/e/"):
        assert (record.buffer == "/") == (record.next_state is S.POSSIBLE_COMMENT)


def test_line_and_column_tracking_with_unix_windows_and_old_mac_breaks():
    records = run_fsm("ab\ncd\r\nef\rg")
    positions = {r.offset: (r.line, r.column) for r in records}
    assert positions[0] == (1, 1)
    assert positions[2] == (1, 3)  # '\n'
    assert positions[3] == (2, 1)
    assert positions[5] == (2, 3)  # '\r' of CR LF
    assert positions[6] == (2, 4)  # '\n' of CR LF: same line
    assert positions[7] == (3, 1)
    assert positions[9] == (3, 3)  # lone '\r'
    assert positions[10] == (4, 1)


def test_end_of_input_after_a_lone_carriage_return_is_on_the_next_line():
    end = run_fsm("a\r")[-1]
    assert (end.line, end.column) == (2, 1)


def test_feed_after_finish_is_rejected():
    fsm = CommentFSM()
    fsm.finish()
    with pytest.raises(ProcessingError):
        fsm.feed("a")
    with pytest.raises(ProcessingError):
        fsm.finish()


def test_feed_takes_exactly_one_character():
    with pytest.raises(ProcessingError):
        CommentFSM().feed("ab")
    with pytest.raises(ProcessingError):
        CommentFSM().feed("")


def test_run_starts_from_a_clean_machine_each_time():
    fsm = CommentFSM()
    first = list(fsm.run("a /* b"))
    second = list(fsm.run("a /* b"))
    assert first == second
    assert fsm.output == "a "
