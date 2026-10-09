"""The transition function and output function of the FSM.

The comment remover is a deterministic finite-state transducer (a Mealy
machine), formally

    M = (Q, Σ, Γ, δ, λ, q0, F)

    Q    the states in :class:`remover.states.State`
    Σ    every character; δ and λ only need to tell apart the seven input
         classes of :class:`CharClass`
    Γ    output characters
    δ    Q × CharClass → Q       the next state     (Transition.next_state)
    λ    Q × CharClass → Γ*      the output action  (Transition.output)
    q0   NORMAL
    F    the states where the input may end (see ``ACCEPTING_STATES``)

Every transition consumes exactly one character; the machine never looks
ahead. Where a decision needs the next character (is this '/' a comment
or a division?), the machine moves to an intermediate state
(POSSIBLE_COMMENT, POSSIBLE_COMMENT_END) and decides on the following
step.

``TRANSITION_TABLE`` below is the only definition of the machine's
behaviour. The engine (fsm.py) looks every step up in it, and the UI
table, the state diagram and docs/state-transition-table.md are all
generated from it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .errors import Code, processing_error
from .states import State


class CharClass(StrEnum):
    """Input classes: characters the machine treats identically."""

    SLASH = "SLASH"
    STAR = "STAR"
    DOUBLE_QUOTE = "DOUBLE_QUOTE"
    SINGLE_QUOTE = "SINGLE_QUOTE"
    BACKSLASH = "BACKSLASH"
    NEWLINE = "NEWLINE"
    OTHER = "OTHER"

    @property
    def symbol(self) -> str:
        """Short label used in tables and diagrams."""
        return _CLASS_SYMBOLS[self]

    @property
    def members(self) -> str:
        """Plain-language description of the characters in this class."""
        return _CLASS_MEMBERS[self]


_CLASS_SYMBOLS = {
    CharClass.SLASH: "/",
    CharClass.STAR: "*",
    CharClass.DOUBLE_QUOTE: '"',
    CharClass.SINGLE_QUOTE: "'",
    CharClass.BACKSLASH: "\\",
    CharClass.NEWLINE: "newline",
    CharClass.OTHER: "other",
}

_CLASS_MEMBERS = {
    CharClass.SLASH: "the slash '/'",
    CharClass.STAR: "the asterisk '*'",
    CharClass.DOUBLE_QUOTE: "the double quote '\"'",
    CharClass.SINGLE_QUOTE: "the single quote \"'\"",
    CharClass.BACKSLASH: "the backslash '\\'",
    CharClass.NEWLINE: "a line-feed '\\n' or carriage-return '\\r' character",
    CharClass.OTHER: "any other character (letters, digits, spaces, tabs, operators, Unicode)",
}

_CLASS_OF = {
    "/": CharClass.SLASH,
    "*": CharClass.STAR,
    '"': CharClass.DOUBLE_QUOTE,
    "'": CharClass.SINGLE_QUOTE,
    "\\": CharClass.BACKSLASH,
    "\n": CharClass.NEWLINE,
    "\r": CharClass.NEWLINE,
}


def classify(ch: str) -> CharClass:
    """Map a character to its input class."""
    return _CLASS_OF.get(ch, CharClass.OTHER)


class OutputAction(StrEnum):
    """The output function λ: what a transition writes to the output."""

    EMIT = "EMIT"  # write the current character
    DISCARD = "DISCARD"  # drop the current character
    BUFFER = "BUFFER"  # hold the current character until the next step
    FLUSH_AND_EMIT = "FLUSH_AND_EMIT"  # write the held character, then the current one
    DISCARD_BUFFER = "DISCARD_BUFFER"  # drop the held character and the current one
    REPLACE_WITH_SPACE = "REPLACE_WITH_SPACE"  # drop the current character, write one space
    FLUSH = "FLUSH"  # end of input only: write the held character
    NONE = "NONE"  # end of input only: write nothing

    @property
    def effect(self) -> str:
        """Plain-language description of the effect on the output."""
        return _OUTPUT_EFFECTS[self]


_OUTPUT_EFFECTS = {
    OutputAction.EMIT: "Character copied to the output.",
    OutputAction.DISCARD: "Character discarded (comment text).",
    OutputAction.BUFFER: "Character temporarily buffered.",
    OutputAction.FLUSH_AND_EMIT: "Buffered '/' released to the output, followed by this character.",
    OutputAction.DISCARD_BUFFER: "Comment delimiter discarded (the buffered '/' and this character).",
    OutputAction.REPLACE_WITH_SPACE: "Closing '/' discarded; one space written in place of the comment.",
    OutputAction.FLUSH: "Buffered '/' released to the output.",
    OutputAction.NONE: "Nothing written.",
}


class Event(StrEnum):
    """Lexical event signalled by a transition (used to build lexemes)."""

    NONE = "NONE"
    SINGLE_LINE_COMMENT_START = "SINGLE_LINE_COMMENT_START"
    MULTI_LINE_COMMENT_START = "MULTI_LINE_COMMENT_START"
    COMMENT_END = "COMMENT_END"
    STRING_START = "STRING_START"
    STRING_END = "STRING_END"
    CHARACTER_START = "CHARACTER_START"
    CHARACTER_END = "CHARACTER_END"
    UNTERMINATED_COMMENT = "UNTERMINATED_COMMENT"
    UNTERMINATED_STRING = "UNTERMINATED_STRING"
    UNTERMINATED_CHARACTER = "UNTERMINATED_CHARACTER"

    @property
    def is_error(self) -> bool:
        return self in _ERROR_EVENTS


_ERROR_EVENTS = frozenset(
    {Event.UNTERMINATED_COMMENT, Event.UNTERMINATED_STRING, Event.UNTERMINATED_CHARACTER}
)


@dataclass(frozen=True)
class Transition:
    """One row of the transition table.

    ``input_class`` is ``None`` for an end-of-input transition.
    """

    current_state: State
    input_class: CharClass | None
    next_state: State
    output: OutputAction
    event: Event
    action: str

    @property
    def is_end_of_input(self) -> bool:
        return self.input_class is None


# Each state lists the input classes it treats specially; ``default``
# covers every remaining class. The expansion below produces the complete
# table: one entry for every (state, input class) pair.
_N, _PC, _SLC, _MLC, _PCE = (
    State.NORMAL,
    State.POSSIBLE_COMMENT,
    State.SINGLE_LINE_COMMENT,
    State.MULTI_LINE_COMMENT,
    State.POSSIBLE_COMMENT_END,
)
_STR, _STR_ESC, _CHR, _CHR_ESC = (
    State.STRING_LITERAL,
    State.STRING_ESCAPE,
    State.CHARACTER_LITERAL,
    State.CHARACTER_ESCAPE,
)
_O, _E = OutputAction, Event

_SPECIFICATION: dict[State, dict[CharClass | str, tuple[State, OutputAction, Event, str]]] = {
    _N: {
        CharClass.SLASH: (
            _PC, _O.BUFFER, _E.NONE,
            "'/' may start a comment: hold it and decide on the next character",
        ),
        CharClass.DOUBLE_QUOTE: (
            _STR, _O.EMIT, _E.STRING_START,
            "Opening '\"' starts a string literal: copy it",
        ),
        CharClass.SINGLE_QUOTE: (
            _CHR, _O.EMIT, _E.CHARACTER_START,
            "Opening \"'\" starts a character literal: copy it",
        ),
        "default": (
            _N, _O.EMIT, _E.NONE,
            "Ordinary source character: copy it to the output",
        ),
    },
    _PC: {
        CharClass.SLASH: (
            _SLC, _O.DISCARD_BUFFER, _E.SINGLE_LINE_COMMENT_START,
            "'//' recognised: a single-line comment starts; discard both slashes",
        ),
        CharClass.STAR: (
            _MLC, _O.DISCARD_BUFFER, _E.MULTI_LINE_COMMENT_START,
            "'/*' recognised: a multi-line comment starts; discard '/' and '*'",
        ),
        CharClass.DOUBLE_QUOTE: (
            _STR, _O.FLUSH_AND_EMIT, _E.STRING_START,
            "The held '/' was an operator: emit it, then start a string literal",
        ),
        CharClass.SINGLE_QUOTE: (
            _CHR, _O.FLUSH_AND_EMIT, _E.CHARACTER_START,
            "The held '/' was an operator: emit it, then start a character literal",
        ),
        "default": (
            _N, _O.FLUSH_AND_EMIT, _E.NONE,
            "Not a comment: the held '/' is an operator (e.g. division); emit it and this character",
        ),
    },
    _SLC: {
        CharClass.NEWLINE: (
            _N, _O.EMIT, _E.COMMENT_END,
            "Line break ends the single-line comment; the line break is code and is kept",
        ),
        "default": (
            _SLC, _O.DISCARD, _E.NONE,
            "Comment text: discard it",
        ),
    },
    _MLC: {
        CharClass.STAR: (
            _PCE, _O.DISCARD, _E.NONE,
            "'*' may start the closing '*/': discard it and check the next character",
        ),
        CharClass.NEWLINE: (
            _MLC, _O.DISCARD, _E.NONE,
            "Line break inside the comment: discard it (the line counter still advances)",
        ),
        "default": (
            _MLC, _O.DISCARD, _E.NONE,
            "Comment text: discard it",
        ),
    },
    _PCE: {
        CharClass.SLASH: (
            _N, _O.REPLACE_WITH_SPACE, _E.COMMENT_END,
            "'*/' closes the comment: discard '/' and emit one space in place of the comment",
        ),
        CharClass.STAR: (
            _PCE, _O.DISCARD, _E.NONE,
            "Another '*': the comment may still close with '/' (as in '**/')",
        ),
        "default": (
            _MLC, _O.DISCARD, _E.NONE,
            "'*' was not followed by '/': still inside the comment",
        ),
    },
    _STR: {
        CharClass.DOUBLE_QUOTE: (
            _N, _O.EMIT, _E.STRING_END,
            "Closing '\"' ends the string literal: copy it",
        ),
        CharClass.BACKSLASH: (
            _STR_ESC, _O.EMIT, _E.NONE,
            "Backslash: the next character is escaped and cannot end the string",
        ),
        CharClass.NEWLINE: (
            _N, _O.EMIT, _E.UNTERMINATED_STRING,
            "Lexical error: a raw line break cannot appear in a string literal; "
            "report it and resume in NORMAL",
        ),
        "default": (
            _STR, _O.EMIT, _E.NONE,
            "String content (comment markers here are plain text): copy it unchanged",
        ),
    },
    _STR_ESC: {
        "default": (
            _STR, _O.EMIT, _E.NONE,
            "Escaped character (such as \\\" or \\\\): copy it and continue the string",
        ),
    },
    _CHR: {
        CharClass.SINGLE_QUOTE: (
            _N, _O.EMIT, _E.CHARACTER_END,
            "Closing \"'\" ends the character literal: copy it",
        ),
        CharClass.BACKSLASH: (
            _CHR_ESC, _O.EMIT, _E.NONE,
            "Backslash: the next character is escaped and cannot end the literal",
        ),
        CharClass.NEWLINE: (
            _N, _O.EMIT, _E.UNTERMINATED_CHARACTER,
            "Lexical error: a raw line break cannot appear in a character literal; "
            "report it and resume in NORMAL",
        ),
        "default": (
            _CHR, _O.EMIT, _E.NONE,
            "Character-literal content: copy it unchanged",
        ),
    },
    _CHR_ESC: {
        "default": (
            _CHR, _O.EMIT, _E.NONE,
            "Escaped character (such as \\' or \\\\): copy it and continue the literal",
        ),
    },
}

# End of input is not a character. It is handled as one final pseudo-transition
# on a virtual end marker: it finishes pending work or reports an unterminated
# construct. In the error rows the machine halts in a non-accepting state.
_EOF_SPECIFICATION: dict[State, tuple[State, OutputAction, Event, str]] = {
    _N: (_N, _O.NONE, _E.NONE, "End of input in NORMAL: the source is lexically complete"),
    _PC: (_N, _O.FLUSH, _E.NONE, "End of input right after '/': the held '/' is code; emit it"),
    _SLC: (_N, _O.NONE, _E.COMMENT_END, "End of input also ends a single-line comment"),
    _MLC: (
        _MLC, _O.NONE, _E.UNTERMINATED_COMMENT,
        "Lexical error: end of input inside a multi-line comment (no closing '*/')",
    ),
    _PCE: (
        _PCE, _O.NONE, _E.UNTERMINATED_COMMENT,
        "Lexical error: end of input inside a multi-line comment (no closing '*/')",
    ),
    _STR: (
        _STR, _O.NONE, _E.UNTERMINATED_STRING,
        "Lexical error: end of input inside a string literal (no closing '\"')",
    ),
    _STR_ESC: (
        _STR_ESC, _O.NONE, _E.UNTERMINATED_STRING,
        "Lexical error: end of input inside a string literal (no closing '\"')",
    ),
    _CHR: (
        _CHR, _O.NONE, _E.UNTERMINATED_CHARACTER,
        "Lexical error: end of input inside a character literal (no closing \"'\")",
    ),
    _CHR_ESC: (
        _CHR_ESC, _O.NONE, _E.UNTERMINATED_CHARACTER,
        "Lexical error: end of input inside a character literal (no closing \"'\")",
    ),
}


def _expand(
    specification: dict[State, dict[CharClass | str, tuple[State, OutputAction, Event, str]]],
) -> dict[tuple[State, CharClass], Transition]:
    table: dict[tuple[State, CharClass], Transition] = {}
    for state, rows in specification.items():
        default = rows.get("default")
        for input_class in CharClass:
            row = rows.get(input_class, default)
            if row is None:
                continue  # left undefined; validate_table() reports it
            next_state, output, event, action = row
            table[(state, input_class)] = Transition(
                state, input_class, next_state, output, event, action
            )
    return table


#: δ and λ combined: (current state, input class) -> Transition.
TRANSITION_TABLE: dict[tuple[State, CharClass], Transition] = _expand(_SPECIFICATION)

#: End-of-input behaviour for every state.
EOF_TABLE: dict[State, Transition] = {
    state: Transition(state, None, next_state, output, event, action)
    for state, (next_state, output, event, action) in _EOF_SPECIFICATION.items()
}

_CHARACTER_OUTPUTS = frozenset(
    {
        OutputAction.EMIT,
        OutputAction.DISCARD,
        OutputAction.BUFFER,
        OutputAction.FLUSH_AND_EMIT,
        OutputAction.DISCARD_BUFFER,
        OutputAction.REPLACE_WITH_SPACE,
    }
)
_END_OUTPUTS = frozenset({OutputAction.FLUSH, OutputAction.NONE})
_USES_BUFFER = frozenset(
    {OutputAction.FLUSH_AND_EMIT, OutputAction.DISCARD_BUFFER, OutputAction.FLUSH}
)


def validate_table(
    table: dict[tuple[State, CharClass], Transition] = TRANSITION_TABLE,
    eof_table: dict[State, Transition] = EOF_TABLE,
) -> None:
    """Check that the machine is complete and deterministic.

    Raises :class:`ProcessingError` if any (state, input) pair has no
    transition, a row is filed under the wrong key, or a row would break
    the buffer invariant: the buffer holds a '/' exactly while the
    machine is in POSSIBLE_COMMENT.
    """
    problems: list[str] = []
    for state in State:
        for input_class in CharClass:
            row = table.get((state, input_class))
            if row is None:
                problems.append(f"no transition for ({state}, {input_class})")
                continue
            if (row.current_state, row.input_class) != (state, input_class):
                problems.append(f"row for ({state}, {input_class}) is filed under the wrong key")
            if row.output not in _CHARACTER_OUTPUTS:
                problems.append(f"({state}, {input_class}) uses end-of-input output {row.output}")
            if (row.output is OutputAction.BUFFER) != (row.next_state is State.POSSIBLE_COMMENT):
                problems.append(f"({state}, {input_class}) breaks the buffer invariant")
            if row.output in _USES_BUFFER and state is not State.POSSIBLE_COMMENT:
                problems.append(f"({state}, {input_class}) releases a buffer that cannot exist")
        end = eof_table.get(state)
        if end is None:
            problems.append(f"no end-of-input transition for {state}")
            continue
        if end.output not in _END_OUTPUTS:
            problems.append(f"end of input in {state} uses character output {end.output}")
        if end.output is OutputAction.FLUSH and state is not State.POSSIBLE_COMMENT:
            problems.append(f"end of input in {state} releases a buffer that cannot exist")
    if problems:
        raise processing_error(
            Code.INVALID_TRANSITION_TABLE,
            "The transition table is invalid: " + "; ".join(problems),
        )


def transition(state: State, ch: str) -> Transition:
    """Return the transition taken from ``state`` on character ``ch``."""
    return TRANSITION_TABLE[(state, classify(ch))]


def transitions_from(state: State) -> list[Transition]:
    """All character transitions leaving ``state``, in input-class order."""
    return [TRANSITION_TABLE[(state, input_class)] for input_class in CharClass]
