"""Comment and Whitespace Remover using a Finite State Machine.

Where things live:

    states.py           the FSM states (Q) and which of them accept
    transitions.py      the transition table: δ (next state) and λ (output)
    fsm.py              the engine that runs the table one character at a time
    comment_remover.py  runs the FSM and collects comments, literals, errors
    models.py           the data structures passed between the stages
    errors.py           error classification and diagnostics
    text.py             character helpers: whitespace and line breaks
"""

from .comment_remover import CommentRemovalResult, remove_comments
from .errors import (
    Code,
    Diagnostic,
    ErrorCategory,
    InputValidationError,
    LexicalError,
    ProcessingError,
    RemoverError,
    Severity,
)
from .fsm import CommentFSM
from .models import (
    METRIC_DEFINITIONS,
    Comment,
    CommentKind,
    Literal,
    LiteralKind,
    NewlineMode,
    Piece,
    PieceKind,
    Position,
    ProcessingOptions,
    ProcessingResult,
    SeparatorInsertion,
    Statistics,
    TransitionRecord,
    WhitespaceMode,
)
from .states import STATE_INFO, State
from .transitions import (
    EOF_TABLE,
    TRANSITION_TABLE,
    CharClass,
    Event,
    OutputAction,
    classify,
)

__all__ = [
    "CharClass",
    "Code",
    "Comment",
    "CommentFSM",
    "CommentKind",
    "CommentRemovalResult",
    "Diagnostic",
    "EOF_TABLE",
    "ErrorCategory",
    "Event",
    "InputValidationError",
    "LexicalError",
    "Literal",
    "LiteralKind",
    "METRIC_DEFINITIONS",
    "NewlineMode",
    "OutputAction",
    "Piece",
    "PieceKind",
    "Position",
    "ProcessingError",
    "ProcessingOptions",
    "ProcessingResult",
    "RemoverError",
    "STATE_INFO",
    "SeparatorInsertion",
    "Severity",
    "State",
    "Statistics",
    "TRANSITION_TABLE",
    "TransitionRecord",
    "WhitespaceMode",
    "classify",
    "remove_comments",
]
