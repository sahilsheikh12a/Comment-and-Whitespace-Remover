"""Data structures shared by the FSM, the processing stages and the UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .errors import (
    Diagnostic,
    ErrorCategory,
    InputValidationError,
    LexicalError,
    ProcessingError,
)
from .states import State
from .text import line_breaks
from .transitions import CharClass, Event, OutputAction


@dataclass(frozen=True, slots=True)
class Position:
    """A location in the source.

    ``offset`` is the 0-based index of the character. ``line`` and
    ``column`` are 1-based; columns count characters, so a tab is one
    column.
    """

    offset: int
    line: int
    column: int

    def __str__(self) -> str:
        return f"line {self.line}, column {self.column}"


@dataclass(frozen=True, slots=True)
class TransitionRecord:
    """One step of an actual FSM run, as recorded by the engine.

    For the final end-of-input step ``character`` and ``input_class`` are
    ``None`` and ``offset``/``line``/``column`` give the position just
    past the last character. Every source character appears in exactly one
    record; a character is never reported as consumed twice.
    """

    step: int
    offset: int
    line: int
    column: int
    character: str | None
    input_class: CharClass | None
    current_state: State
    next_state: State
    output: OutputAction
    event: Event
    emitted: str  # text appended to the FSM output by this step
    discarded: str  # source text dropped by this step
    buffer: str  # contents of the one-character buffer after this step
    output_length: int  # length of the FSM output after this step
    action: str  # explanation from the transition table

    @property
    def is_end_of_input(self) -> bool:
        return self.character is None

    @property
    def changed_state(self) -> bool:
        return self.current_state is not self.next_state

    @property
    def position(self) -> Position:
        return Position(self.offset, self.line, self.column)


class CommentKind(StrEnum):
    SINGLE_LINE = "single-line"
    MULTI_LINE = "multi-line"


@dataclass(frozen=True, slots=True)
class Comment:
    """A comment recognised (and removed) by the FSM.

    ``text`` includes the delimiters. A single-line comment does not
    include the line break that ends it: that line break is code.
    ``end`` is the position of the comment's last character.
    """

    kind: CommentKind
    text: str
    start: Position
    end: Position
    terminated: bool

    @property
    def line_breaks(self) -> int:
        return len(line_breaks(self.text))


class LiteralKind(StrEnum):
    STRING = "string"
    CHARACTER = "character"


@dataclass(frozen=True, slots=True)
class Literal:
    """A string or character literal; its text is never modified."""

    kind: LiteralKind
    text: str
    start: Position
    end: Position
    terminated: bool


class PieceKind(StrEnum):
    CODE = "code"
    STRING_LITERAL = "string literal"
    CHARACTER_LITERAL = "character literal"
    COMMENT = "comment"


@dataclass(frozen=True, slots=True)
class Piece:
    """A segment of the FSM output, tagged with the kind of text it is.

    Concatenating the ``text`` of all pieces gives exactly the FSM output.
    A COMMENT piece stands for a removed comment: its ``text`` is the
    single space a multi-line comment is replaced by (empty for a
    single-line or unterminated comment) and ``comment`` holds what was
    removed.
    """

    kind: PieceKind
    text: str
    start: int  # source offset where this piece begins
    comment: Comment | None = None
    literal: Literal | None = None


class WhitespaceMode(StrEnum):
    PRESERVE = "preserve"
    NORMALIZE = "normalize"
    COMPACT = "compact"

    @property
    def label(self) -> str:
        return _WHITESPACE_LABELS[self][0]

    @property
    def description(self) -> str:
        return _WHITESPACE_LABELS[self][1]


_WHITESPACE_LABELS = {
    WhitespaceMode.PRESERVE: (
        "Preserve",
        "Only comments are removed. All other whitespace stays exactly as "
        "written, except whitespace left dangling at the end of a line whose "
        "comment was removed.",
    ),
    WhitespaceMode.NORMALIZE: (
        "Normalize",
        "Indentation is kept. Every other run of spaces or tabs between "
        "tokens becomes one space, and trailing whitespace is removed.",
    ),
    WhitespaceMode.COMPACT: (
        "Compact",
        "Indentation and trailing whitespace are removed, and the space "
        "between two tokens is dropped wherever they stay separate without "
        "it (int x=10;). Preprocessor lines are only normalized.",
    ),
}


class NewlineMode(StrEnum):
    PRESERVE = "preserve"
    STRUCTURE = "structure"
    COLLAPSE = "collapse"

    @property
    def label(self) -> str:
        return _NEWLINE_LABELS[self][0]

    @property
    def description(self) -> str:
        return _NEWLINE_LABELS[self][1]


_NEWLINE_LABELS = {
    NewlineMode.PRESERVE: (
        "Preserve original newlines",
        "Every line break is kept, including those inside multi-line "
        "comments, so every line keeps its original line number. Lines that "
        "held only a comment become blank lines.",
    ),
    NewlineMode.STRUCTURE: (
        "Preserve line structure",
        "Comments are removed together with the line breaks inside them. "
        "Lines of code and the blank lines you wrote are kept; lines that "
        "held only a comment are removed.",
    ),
    NewlineMode.COLLAPSE: (
        "Normalize blank lines",
        "As 'Preserve line structure', and every run of blank lines becomes "
        "a single blank line; blank lines at the start and end are removed.",
    ),
}


@dataclass(frozen=True)
class ProcessingOptions:
    """Settings for one run of the pipeline.

    Modes may be given as enum members or as their string values
    (``"normalize"``).
    """

    whitespace_mode: WhitespaceMode = WhitespaceMode.NORMALIZE
    newline_mode: NewlineMode = NewlineMode.STRUCTURE
    record_transitions: bool = True
    max_recorded_transitions: int = 50_000
    max_input_characters: int = 200_000

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "whitespace_mode", _coerce(WhitespaceMode, self.whitespace_mode, "whitespace_mode")
        )
        object.__setattr__(
            self, "newline_mode", _coerce(NewlineMode, self.newline_mode, "newline_mode")
        )
        if self.max_recorded_transitions < 0:
            raise ValueError("max_recorded_transitions must not be negative")
        if self.max_input_characters < 1:
            raise ValueError("max_input_characters must be at least 1")


def _coerce(enum_type: type[StrEnum], value: object, name: str) -> StrEnum:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(str(value).strip().lower())
    except ValueError:
        choices = ", ".join(member.value for member in enum_type)
        raise ValueError(f"invalid {name} {value!r}; choose one of: {choices}") from None


@dataclass(frozen=True, slots=True)
class SeparatorInsertion:
    """A space kept where a removed comment separated two tokens."""

    comment: Comment
    left: str  # last character before the comment
    right: str  # first character after the comment
    reason: str


@dataclass(frozen=True)
class Statistics:
    """Counts computed from one actual run (see ``METRIC_DEFINITIONS``)."""

    original_characters: int
    output_characters: int
    characters_removed: int
    original_lines: int
    output_lines: int
    comments_detected: int
    single_line_comments: int
    multi_line_comments: int
    comment_characters_removed: int
    string_literals: int
    character_literals: int
    whitespace_removed: int
    separators_inserted: int
    comment_line_breaks_kept: int
    characters_scanned: int
    fsm_transitions: int
    state_changes: int
    errors: int
    warnings: int
    state_visits: dict[str, int] = field(default_factory=dict)


METRIC_DEFINITIONS: dict[str, tuple[str, str]] = {
    "original_characters": (
        "Original Characters",
        "Number of characters in the source as entered.",
    ),
    "output_characters": (
        "Output Characters",
        "Number of characters in the final cleaned output.",
    ),
    "characters_removed": (
        "Characters Removed",
        "Original Characters minus Output Characters: a plain length "
        "difference, so it already accounts for the separator spaces and "
        "comment line breaks that are kept.",
    ),
    "original_lines": ("Original Lines", "Lines in the source (a final line break does not start a new line)."),
    "output_lines": ("Output Lines", "Lines in the cleaned output, counted the same way."),
    "comments_detected": ("Comments Detected", "Comments recognised by the FSM (both kinds)."),
    "single_line_comments": ("Single-Line Comments", "Comments starting with //."),
    "multi_line_comments": ("Multi-Line Comments", "Comments starting with /*, including an unterminated one."),
    "comment_characters_removed": (
        "Comment Characters Removed",
        "Characters inside comments, delimiters included. The line break "
        "that ends a // comment is code and is not counted.",
    ),
    "string_literals": ("String Literals", "Double-quoted literals preserved unchanged."),
    "character_literals": ("Character Literals", "Single-quoted literals preserved unchanged."),
    "whitespace_removed": (
        "Whitespace Removed",
        "Whitespace characters of the code (spaces, tabs, form feeds, "
        "vertical tabs and line-break characters outside comments and "
        "literals) that are not in the output. A run of N characters "
        "reduced to one space counts as N - 1.",
    ),
    "separators_inserted": (
        "Separators Inserted",
        "Spaces kept where a removed comment was the only thing between two "
        "tokens that would otherwise merge (int/**/x becomes int x).",
    ),
    "comment_line_breaks_kept": (
        "Comment Line Breaks Kept",
        "Line breaks from inside multi-line comments kept in the output "
        "(only with 'Preserve original newlines').",
    ),
    "characters_scanned": ("Characters Scanned", "Characters consumed by the FSM; each exactly once."),
    "fsm_transitions": (
        "FSM Transitions",
        "Transitions executed: one per character plus the final end-of-input transition.",
    ),
    "state_changes": (
        "State Changes",
        "Transitions whose next state differs from the current state (the rest are self-loops).",
    ),
    "errors": ("Errors", "Error diagnostics reported."),
    "warnings": ("Warnings", "Warning diagnostics reported."),
}


@dataclass(frozen=True)
class ProcessingResult:
    """Everything one run of the pipeline produced."""

    original_source: str
    cleaned_source: str
    comment_free_source: str  # FSM output, before whitespace processing
    options: ProcessingOptions
    transition_log: tuple[TransitionRecord, ...]
    transition_log_complete: bool
    detected_comments: tuple[Comment, ...]
    detected_literals: tuple[Literal, ...]
    separators: tuple[SeparatorInsertion, ...]
    statistics: Statistics | None
    errors: tuple[Diagnostic, ...]
    warnings: tuple[Diagnostic, ...]
    final_state: State | None  # None when the FSM never ran
    accepted: bool
    pieces: tuple[Piece, ...] = ()

    @property
    def fsm_ran(self) -> bool:
        return self.final_state is not None

    @property
    def success(self) -> bool:
        """True when the FSM ran and nothing was reported as an error."""
        return self.fsm_ran and not self.errors

    @property
    def output_complete(self) -> bool:
        """False when an error means the output may be incomplete or unreliable."""
        return self.success and self.accepted

    def raise_for_errors(self) -> None:
        """Raise the exception matching the first error, if there is one."""
        if not self.errors:
            return
        first = self.errors[0]
        exception = {
            ErrorCategory.LEXICAL: LexicalError,
            ErrorCategory.INPUT_VALIDATION: InputValidationError,
            ErrorCategory.PROCESSING: ProcessingError,
        }[first.category]
        raise exception(first)
