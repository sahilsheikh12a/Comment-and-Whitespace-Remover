"""States of the comment-removal finite state machine.

A state answers one question: *how must the next character be read?*
The same character means different things in different states. A ``/``
is a division operator in NORMAL, the second half of ``//`` in
POSSIBLE_COMMENT, plain text in STRING_LITERAL and the end of a comment
in POSSIBLE_COMMENT_END. That context is all the machine remembers: it
has no stack and no counters, only its current state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class State(StrEnum):
    """The nine states of the machine (the set Q)."""

    NORMAL = "NORMAL"
    POSSIBLE_COMMENT = "POSSIBLE_COMMENT"
    SINGLE_LINE_COMMENT = "SINGLE_LINE_COMMENT"
    MULTI_LINE_COMMENT = "MULTI_LINE_COMMENT"
    POSSIBLE_COMMENT_END = "POSSIBLE_COMMENT_END"
    STRING_LITERAL = "STRING_LITERAL"
    STRING_ESCAPE = "STRING_ESCAPE"
    CHARACTER_LITERAL = "CHARACTER_LITERAL"
    CHARACTER_ESCAPE = "CHARACTER_ESCAPE"


class Region(StrEnum):
    """The kind of source text a state is reading."""

    CODE = "code"
    PENDING = "pending decision"
    COMMENT = "comment"
    STRING = "string literal"
    CHARACTER = "character literal"


@dataclass(frozen=True)
class StateInfo:
    """Documentation for one state, shown in the UI and the docs."""

    state: State
    region: Region
    accepting: bool
    summary: str
    description: str


INITIAL_STATE = State.NORMAL

STATE_INFO: dict[State, StateInfo] = {
    info.state: info
    for info in (
        StateInfo(
            State.NORMAL,
            Region.CODE,
            accepting=True,
            summary="Ordinary source code",
            description=(
                "The start state. Characters are copied to the output. "
                "'/' may start a comment, '\"' starts a string literal and "
                "\"'\" starts a character literal."
            ),
        ),
        StateInfo(
            State.POSSIBLE_COMMENT,
            Region.PENDING,
            accepting=True,
            summary="Saw '/', deciding",
            description=(
                "A '/' was read in code. It is held in a one-character buffer "
                "because only the next character can tell whether it starts "
                "'//' or '/*' or is just a division operator."
            ),
        ),
        StateInfo(
            State.SINGLE_LINE_COMMENT,
            Region.COMMENT,
            accepting=True,
            summary="Inside // comment",
            description=(
                "Every character is discarded until a line break, which ends "
                "the comment and is itself kept as code. The end of input "
                "also ends the comment."
            ),
        ),
        StateInfo(
            State.MULTI_LINE_COMMENT,
            Region.COMMENT,
            accepting=False,
            summary="Inside /* */ comment",
            description=(
                "Every character, including line breaks, is discarded. A '*' "
                "moves to POSSIBLE_COMMENT_END because it may start the closing "
                "'*/'."
            ),
        ),
        StateInfo(
            State.POSSIBLE_COMMENT_END,
            Region.COMMENT,
            accepting=False,
            summary="Saw '*' in comment",
            description=(
                "Inside a multi-line comment, right after a '*'. A '/' closes "
                "the comment, another '*' keeps the possibility open and any "
                "other character returns to MULTI_LINE_COMMENT."
            ),
        ),
        StateInfo(
            State.STRING_LITERAL,
            Region.STRING,
            accepting=False,
            summary='Inside "..." string',
            description=(
                "Characters are copied unchanged, so '//' and '/*' here are "
                "text, not comments. Only an unescaped '\"' ends the string. "
                "A raw line break is a lexical error."
            ),
        ),
        StateInfo(
            State.STRING_ESCAPE,
            Region.STRING,
            accepting=False,
            summary="After \\ in string",
            description=(
                "The previous character was a backslash, so this character is "
                "escaped: it is copied and can never end the string."
            ),
        ),
        StateInfo(
            State.CHARACTER_LITERAL,
            Region.CHARACTER,
            accepting=False,
            summary="Inside '...' literal",
            description=(
                "Characters are copied unchanged until an unescaped \"'\". "
                "A raw line break is a lexical error."
            ),
        ),
        StateInfo(
            State.CHARACTER_ESCAPE,
            Region.CHARACTER,
            accepting=False,
            summary="After \\ in char literal",
            description=(
                "The previous character was a backslash, so this character is "
                "escaped: it is copied and can never end the literal."
            ),
        ),
    )
}

#: States in which the input may legally end (the set F).
ACCEPTING_STATES = frozenset(s for s, info in STATE_INFO.items() if info.accepting)
COMMENT_STATES = frozenset(s for s, info in STATE_INFO.items() if info.region is Region.COMMENT)
STRING_STATES = frozenset(s for s, info in STATE_INFO.items() if info.region is Region.STRING)
CHARACTER_STATES = frozenset(
    s for s, info in STATE_INFO.items() if info.region is Region.CHARACTER
)
LITERAL_STATES = STRING_STATES | CHARACTER_STATES


def describe(state: State) -> StateInfo:
    """Return the documentation entry for ``state``."""
    return STATE_INFO[state]
