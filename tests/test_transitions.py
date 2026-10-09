"""The transition table: completeness, determinism and the documented rows."""

import pytest

from remover import (
    EOF_TABLE,
    TRANSITION_TABLE,
    CharClass,
    Code,
    Event,
    OutputAction,
    ProcessingError,
    State,
    classify,
)
from remover.states import ACCEPTING_STATES, STATE_INFO
from remover.transitions import Transition, transition, transitions_from, validate_table

S, C, O = State, CharClass, OutputAction


def test_table_defines_every_state_and_input_class_pair():
    assert len(TRANSITION_TABLE) == len(State) * len(CharClass)
    for state in State:
        for input_class in CharClass:
            row = TRANSITION_TABLE[(state, input_class)]
            assert (row.current_state, row.input_class) == (state, input_class)


def test_real_table_passes_validation():
    validate_table()


def test_validation_reports_a_missing_transition():
    broken = dict(TRANSITION_TABLE)
    del broken[(S.NORMAL, C.SLASH)]
    with pytest.raises(ProcessingError) as caught:
        validate_table(broken, EOF_TABLE)
    assert caught.value.diagnostic.code is Code.INVALID_TRANSITION_TABLE
    assert "NORMAL" in caught.value.diagnostic.message


def test_validation_reports_a_row_that_breaks_the_buffer_invariant():
    broken = dict(TRANSITION_TABLE)
    broken[(S.NORMAL, C.STAR)] = Transition(S.NORMAL, C.STAR, S.NORMAL, O.BUFFER, Event.NONE, "bad")
    with pytest.raises(ProcessingError):
        validate_table(broken, EOF_TABLE)


def test_validation_reports_a_missing_end_of_input_rule():
    broken_eof = dict(EOF_TABLE)
    del broken_eof[S.STRING_LITERAL]
    with pytest.raises(ProcessingError):
        validate_table(TRANSITION_TABLE, broken_eof)


@pytest.mark.parametrize(
    ("ch", "expected"),
    [
        ("/", C.SLASH), ("*", C.STAR), ('"', C.DOUBLE_QUOTE), ("'", C.SINGLE_QUOTE),
        ("\\", C.BACKSLASH), ("\n", C.NEWLINE), ("\r", C.NEWLINE),
        ("a", C.OTHER), (" ", C.OTHER), ("\t", C.OTHER), ("#", C.OTHER), ("é", C.OTHER),
    ],
)
def test_classify(ch, expected):
    assert classify(ch) is expected


# The rows of the state-transition table from the project specification.
@pytest.mark.parametrize(
    ("state", "input_class", "next_state", "output"),
    [
        (S.NORMAL, C.SLASH, S.POSSIBLE_COMMENT, O.BUFFER),
        (S.NORMAL, C.DOUBLE_QUOTE, S.STRING_LITERAL, O.EMIT),
        (S.NORMAL, C.SINGLE_QUOTE, S.CHARACTER_LITERAL, O.EMIT),
        (S.NORMAL, C.OTHER, S.NORMAL, O.EMIT),
        (S.POSSIBLE_COMMENT, C.SLASH, S.SINGLE_LINE_COMMENT, O.DISCARD_BUFFER),
        (S.POSSIBLE_COMMENT, C.STAR, S.MULTI_LINE_COMMENT, O.DISCARD_BUFFER),
        (S.POSSIBLE_COMMENT, C.OTHER, S.NORMAL, O.FLUSH_AND_EMIT),
        (S.SINGLE_LINE_COMMENT, C.NEWLINE, S.NORMAL, O.EMIT),
        (S.SINGLE_LINE_COMMENT, C.OTHER, S.SINGLE_LINE_COMMENT, O.DISCARD),
        (S.MULTI_LINE_COMMENT, C.STAR, S.POSSIBLE_COMMENT_END, O.DISCARD),
        (S.MULTI_LINE_COMMENT, C.NEWLINE, S.MULTI_LINE_COMMENT, O.DISCARD),
        (S.POSSIBLE_COMMENT_END, C.SLASH, S.NORMAL, O.REPLACE_WITH_SPACE),
        (S.POSSIBLE_COMMENT_END, C.STAR, S.POSSIBLE_COMMENT_END, O.DISCARD),
        (S.POSSIBLE_COMMENT_END, C.OTHER, S.MULTI_LINE_COMMENT, O.DISCARD),
        (S.STRING_LITERAL, C.DOUBLE_QUOTE, S.NORMAL, O.EMIT),
        (S.STRING_LITERAL, C.BACKSLASH, S.STRING_ESCAPE, O.EMIT),
        (S.STRING_LITERAL, C.SLASH, S.STRING_LITERAL, O.EMIT),
        (S.STRING_ESCAPE, C.DOUBLE_QUOTE, S.STRING_LITERAL, O.EMIT),
        (S.CHARACTER_LITERAL, C.SINGLE_QUOTE, S.NORMAL, O.EMIT),
        (S.CHARACTER_LITERAL, C.BACKSLASH, S.CHARACTER_ESCAPE, O.EMIT),
        (S.CHARACTER_ESCAPE, C.SINGLE_QUOTE, S.CHARACTER_LITERAL, O.EMIT),
    ],
)
def test_documented_rows(state, input_class, next_state, output):
    row = TRANSITION_TABLE[(state, input_class)]
    assert row.next_state is next_state
    assert row.output is output
    assert row.action  # every row explains itself


def test_comment_states_never_emit_except_the_ending_transitions():
    for state in (S.SINGLE_LINE_COMMENT, S.MULTI_LINE_COMMENT, S.POSSIBLE_COMMENT_END):
        for row in transitions_from(state):
            if row.event is Event.COMMENT_END:
                continue
            assert row.output is O.DISCARD


def test_literal_states_copy_every_character():
    for state in (S.STRING_LITERAL, S.STRING_ESCAPE, S.CHARACTER_LITERAL, S.CHARACTER_ESCAPE):
        for row in transitions_from(state):
            assert row.output is O.EMIT


def test_only_literal_line_breaks_are_error_transitions():
    errors = [row for row in TRANSITION_TABLE.values() if row.event.is_error]
    assert {(row.current_state, row.input_class) for row in errors} == {
        (S.STRING_LITERAL, C.NEWLINE),
        (S.CHARACTER_LITERAL, C.NEWLINE),
    }


def test_end_of_input_table_matches_accepting_states():
    assert set(EOF_TABLE) == set(State)
    for state, row in EOF_TABLE.items():
        assert row.is_end_of_input
        if state in ACCEPTING_STATES:
            assert row.next_state is S.NORMAL and not row.event.is_error
        else:
            assert row.next_state is state and row.event.is_error


def test_accepting_states_are_normal_possible_comment_and_single_line_comment():
    assert ACCEPTING_STATES == {S.NORMAL, S.POSSIBLE_COMMENT, S.SINGLE_LINE_COMMENT}
    assert set(STATE_INFO) == set(State)


def test_lookup_function_agrees_with_the_table():
    for state in State:
        for ch in "/*\"'\\\n\rax ":
            assert transition(state, ch) is TRANSITION_TABLE[(state, classify(ch))]


def test_transitions_from_lists_one_row_per_input_class():
    rows = transitions_from(S.NORMAL)
    assert [row.input_class for row in rows] == list(CharClass)
