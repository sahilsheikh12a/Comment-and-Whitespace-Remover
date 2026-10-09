"""Comment removal: run the FSM and collect the lexemes it recognises.

The FSM decides, character by character, what is copied and what is
discarded. This module runs it over the whole source and attaches the
actions a lexer attaches to its automaton. When a transition signals that
a comment or literal starts or ends, the matching lexeme is opened or
closed, and lexical errors become diagnostics with source locations.

The result splits the FSM output into tagged pieces (code, string
literal, character literal, removed comment), so the whitespace stage
knows which text it may change without scanning the source again.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .errors import Code, Diagnostic, ErrorCategory, Severity, processing_error
from .fsm import CommentFSM
from .models import (
    Comment,
    CommentKind,
    Literal,
    LiteralKind,
    Piece,
    PieceKind,
    Position,
    TransitionRecord,
)
from .states import ACCEPTING_STATES, State
from .transitions import Event, OutputAction


@dataclass(frozen=True)
class CommentRemovalResult:
    """Output of the comment-removal stage."""

    source: str
    output: str  # the FSM output: comments removed, all other text unchanged
    pieces: tuple[Piece, ...]
    comments: tuple[Comment, ...]
    literals: tuple[Literal, ...]
    transitions: tuple[TransitionRecord, ...]
    transitions_complete: bool  # False if the log was capped
    transition_count: int  # transitions executed, including end of input
    characters_scanned: int
    state_changes: int
    state_visits: dict[State, int]  # characters consumed in each state
    final_state: State
    accepted: bool  # the input ended in an accepting state
    diagnostics: tuple[Diagnostic, ...]


def remove_comments(
    source: str,
    *,
    record_transitions: bool = True,
    max_recorded_transitions: int | None = None,
) -> CommentRemovalResult:
    """Remove the comments from ``source`` with the FSM.

    Every transition is counted. With ``record_transitions`` the records
    are also kept, up to ``max_recorded_transitions`` of them (``None``
    keeps all); the counts always cover the whole run.
    """
    fsm = CommentFSM()
    collector = _LexemeCollector()
    log: list[TransitionRecord] = []
    visits: Counter[State] = Counter()
    count = changes = scanned = 0
    last: TransitionRecord | None = None

    for record in fsm.run(source):
        count += 1
        changes += record.changed_state
        if not record.is_end_of_input:
            scanned += 1
            visits[record.current_state] += 1
        if record_transitions and (
            max_recorded_transitions is None or len(log) < max_recorded_transitions
        ):
            log.append(record)
        collector.observe(record)
        last = record

    assert last is not None  # run() always yields the end-of-input record
    output = fsm.output
    pieces = collector.finish()
    if "".join(piece.text for piece in pieces) != output:
        raise processing_error(
            Code.INVALID_STATE, "Collected pieces do not reproduce the FSM output."
        )
    return CommentRemovalResult(
        source=source,
        output=output,
        pieces=pieces,
        comments=tuple(collector.comments),
        literals=tuple(collector.literals),
        transitions=tuple(log),
        transitions_complete=len(log) == count,
        transition_count=count,
        characters_scanned=scanned,
        state_changes=changes,
        state_visits=dict(visits),
        final_state=fsm.state,
        accepted=last.current_state in ACCEPTING_STATES,
        diagnostics=tuple(collector.diagnostics),
    )


@dataclass
class _OpenLexeme:
    kind: CommentKind | LiteralKind
    start: Position
    last: Position
    chars: list[str] = field(default_factory=list)


_COMMENT_START_KIND = {
    Event.SINGLE_LINE_COMMENT_START: CommentKind.SINGLE_LINE,
    Event.MULTI_LINE_COMMENT_START: CommentKind.MULTI_LINE,
}
_LITERAL_START_KIND = {
    Event.STRING_START: LiteralKind.STRING,
    Event.CHARACTER_START: LiteralKind.CHARACTER,
}
_LITERAL_END = frozenset({Event.STRING_END, Event.CHARACTER_END})
_LITERAL_UNTERMINATED = frozenset({Event.UNTERMINATED_STRING, Event.UNTERMINATED_CHARACTER})
_LITERAL_PIECE = {
    LiteralKind.STRING: PieceKind.STRING_LITERAL,
    LiteralKind.CHARACTER: PieceKind.CHARACTER_LITERAL,
}
_LITERAL_NAME = {LiteralKind.STRING: "string", LiteralKind.CHARACTER: "character"}
_LITERAL_QUOTE = {LiteralKind.STRING: '"', LiteralKind.CHARACTER: "'"}
_LITERAL_CODE = {
    LiteralKind.STRING: Code.UNTERMINATED_STRING,
    LiteralKind.CHARACTER: Code.UNTERMINATED_CHARACTER,
}


class _LexemeCollector:
    """Builds comments, literals and output pieces from transition records."""

    def __init__(self) -> None:
        self.comments: list[Comment] = []
        self.literals: list[Literal] = []
        self.diagnostics: list[Diagnostic] = []
        self._pieces: list[Piece] = []
        self._code: list[str] = []
        self._code_start = 0
        self._slash: Position | None = None  # where the buffered '/' was read
        self._comment: _OpenLexeme | None = None
        self._literal: _OpenLexeme | None = None

    def observe(self, record: TransitionRecord) -> None:
        if record.is_end_of_input:
            self._end_of_input(record)
            return
        position = record.position
        output = record.output
        if output is OutputAction.BUFFER:
            self._slash = position
        elif output is OutputAction.DISCARD_BUFFER:
            # '//' or '/*': the comment starts at the buffered slash.
            start = self._take_slash()
            self._flush_code()
            self._comment = _OpenLexeme(
                _COMMENT_START_KIND[record.event], start, position, list(record.discarded)
            )
        elif output is OutputAction.DISCARD:
            self._extend_comment(record)
        elif output is OutputAction.REPLACE_WITH_SPACE:
            self._extend_comment(record)
            self._close_comment(terminated=True, replacement=record.emitted)
        elif output is OutputAction.FLUSH_AND_EMIT:
            # The buffered '/' was an operator after all: it is code.
            slash = self._take_slash()
            self._emit_code("/", slash.offset)
            self._emit_character(record)
        elif output is OutputAction.EMIT:
            self._emit_character(record)
        else:
            raise processing_error(
                Code.INVALID_STATE, f"Unexpected output action {output} at {position}."
            )

    def finish(self) -> tuple[Piece, ...]:
        self._flush_code()
        return tuple(self._pieces)

    # -- record handlers ---------------------------------------------------

    def _emit_character(self, record: TransitionRecord) -> None:
        ch = record.character
        assert ch is not None
        event = record.event
        if event is Event.COMMENT_END:
            # A line break ended a // comment; the line break itself is code.
            self._close_comment(terminated=True, replacement="")
            self._emit_code(ch, record.offset)
        elif event in _LITERAL_START_KIND:
            self._flush_code()
            self._literal = _OpenLexeme(
                _LITERAL_START_KIND[event], record.position, record.position, [ch]
            )
        elif event in _LITERAL_END:
            self._extend_literal(record)
            self._close_literal(terminated=True)
        elif event in _LITERAL_UNTERMINATED:
            # Error recovery: the literal ends before the line break, which is
            # code again (the FSM is back in NORMAL).
            self._close_literal(terminated=False, line_break_at=record.position)
            self._emit_code(ch, record.offset)
        elif self._literal is not None:
            self._extend_literal(record)
        else:
            self._emit_code(ch, record.offset)

    def _end_of_input(self, record: TransitionRecord) -> None:
        if record.output is OutputAction.FLUSH:
            slash = self._take_slash()
            self._emit_code("/", slash.offset)
        event = record.event
        if event is Event.COMMENT_END:
            self._close_comment(terminated=True, replacement="")
        elif event is Event.UNTERMINATED_COMMENT:
            self._close_comment(terminated=False, replacement="")
        elif event in _LITERAL_UNTERMINATED:
            self._close_literal(terminated=False)

    # -- lexeme bookkeeping ------------------------------------------------

    def _extend_comment(self, record: TransitionRecord) -> None:
        comment = self._comment
        if comment is None:
            raise processing_error(
                Code.INVALID_STATE, f"Discarded text outside a comment at {record.position}."
            )
        ch = record.character
        assert ch is not None
        if (
            comment.kind is CommentKind.MULTI_LINE
            and ch == "*"
            and len(comment.chars) > 2
            and comment.chars[-1] == "/"
        ):
            self._warn_nested(comment.last)
        comment.chars.append(ch)
        comment.last = record.position

    def _close_comment(self, *, terminated: bool, replacement: str) -> None:
        open_comment = self._comment
        if open_comment is None:
            raise processing_error(Code.INVALID_STATE, "A comment ended that never started.")
        self._comment = None
        assert isinstance(open_comment.kind, CommentKind)
        comment = Comment(
            kind=open_comment.kind,
            text="".join(open_comment.chars),
            start=open_comment.start,
            end=open_comment.last,
            terminated=terminated,
        )
        self.comments.append(comment)
        self._pieces.append(Piece(PieceKind.COMMENT, replacement, comment.start.offset, comment=comment))
        if not terminated:
            self.diagnostics.append(
                Diagnostic(
                    category=ErrorCategory.LEXICAL,
                    severity=Severity.ERROR,
                    code=Code.UNTERMINATED_COMMENT,
                    message="Unterminated multi-line comment.",
                    line=comment.start.line,
                    column=comment.start.column,
                    offset=comment.start.offset,
                    recovery=(
                        "Reached end of input while inside a multi-line comment. "
                        "Everything from the '/*' to the end of the input was treated "
                        "as comment text and removed; the output holds only the code "
                        "before it."
                    ),
                )
            )

    def _extend_literal(self, record: TransitionRecord) -> None:
        literal = self._literal
        if literal is None:
            raise processing_error(
                Code.INVALID_STATE, f"Literal text outside a literal at {record.position}."
            )
        assert record.character is not None
        literal.chars.append(record.character)
        literal.last = record.position

    def _close_literal(self, *, terminated: bool, line_break_at: Position | None = None) -> None:
        open_literal = self._literal
        if open_literal is None:
            raise processing_error(Code.INVALID_STATE, "A literal ended that never started.")
        self._literal = None
        assert isinstance(open_literal.kind, LiteralKind)
        literal = Literal(
            kind=open_literal.kind,
            text="".join(open_literal.chars),
            start=open_literal.start,
            end=open_literal.last,
            terminated=terminated,
        )
        self.literals.append(literal)
        self._pieces.append(
            Piece(_LITERAL_PIECE[literal.kind], literal.text, literal.start.offset, literal=literal)
        )
        if terminated:
            if literal.kind is LiteralKind.CHARACTER and literal.text == "''":
                self._warn(
                    Code.EMPTY_CHARACTER_LITERAL,
                    "Empty character literal ''. C requires a character between the quotes.",
                    literal.start,
                    "The literal was kept unchanged.",
                )
            return
        name = _LITERAL_NAME[literal.kind]
        quote = _LITERAL_QUOTE[literal.kind]
        if line_break_at is None:
            recovery = (
                f"Reached end of input while inside a {name} literal. "
                "The partial literal was kept unchanged in the output."
            )
        else:
            recovery = (
                f"Line {line_break_at.line} ended before the closing {quote}. "
                f"A {name} literal cannot contain a raw line break, so the scanner "
                "ended the literal there and resumed in NORMAL; the following lines "
                "were processed normally."
            )
        self.diagnostics.append(
            Diagnostic(
                category=ErrorCategory.LEXICAL,
                severity=Severity.ERROR,
                code=_LITERAL_CODE[literal.kind],
                message=f"Unterminated {name} literal.",
                line=literal.start.line,
                column=literal.start.column,
                offset=literal.start.offset,
                recovery=recovery,
            )
        )

    def _warn_nested(self, position: Position) -> None:
        self._warn(
            Code.NESTED_COMMENT,
            "'/*' inside a multi-line comment. C comments do not nest: the comment "
            "ends at the first '*/'.",
            position,
            "Nothing was changed. Check that the comment ends where you expect.",
        )

    def _warn(self, code: Code, message: str, position: Position, recovery: str) -> None:
        self.diagnostics.append(
            Diagnostic(
                category=ErrorCategory.LEXICAL,
                severity=Severity.WARNING,
                code=code,
                message=message,
                line=position.line,
                column=position.column,
                offset=position.offset,
                recovery=recovery,
            )
        )

    def _take_slash(self) -> Position:
        if self._slash is None:
            raise processing_error(Code.INVALID_STATE, "No buffered '/' to release.")
        slash, self._slash = self._slash, None
        return slash

    def _emit_code(self, text: str, offset: int) -> None:
        if not self._code:
            self._code_start = offset
        self._code.append(text)

    def _flush_code(self) -> None:
        if self._code:
            self._pieces.append(Piece(PieceKind.CODE, "".join(self._code), self._code_start))
            self._code = []
