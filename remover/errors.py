"""Error classification and reporting.

Problems are reported as :class:`Diagnostic` objects in three categories:

* Lexical Structure Error: the source breaks a lexical rule, for example
  a comment or literal that is never closed. The scanner reports it with
  its location, recovers, and keeps going.
* Input Validation Error: the input cannot be processed at all (not
  text, too large, binary data). The FSM does not run.
* Processing Error: an internal fault, such as an incomplete transition
  table or a broken state invariant. It should never happen; if it does,
  it is reported instead of crashing the application.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ErrorCategory(StrEnum):
    LEXICAL = "Lexical Structure Error"
    INPUT_VALIDATION = "Input Validation Error"
    PROCESSING = "Processing Error"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class Code(StrEnum):
    """Stable identifiers for every diagnostic the program can produce."""

    UNTERMINATED_COMMENT = "UNTERMINATED_COMMENT"
    UNTERMINATED_STRING = "UNTERMINATED_STRING"
    UNTERMINATED_CHARACTER = "UNTERMINATED_CHARACTER"
    NESTED_COMMENT = "NESTED_COMMENT"
    EMPTY_CHARACTER_LITERAL = "EMPTY_CHARACTER_LITERAL"
    NOT_TEXT = "NOT_TEXT"
    INPUT_TOO_LARGE = "INPUT_TOO_LARGE"
    NUL_CHARACTER = "NUL_CHARACTER"
    UNDECODABLE_INPUT = "UNDECODABLE_INPUT"
    EMPTY_INPUT = "EMPTY_INPUT"
    MIXED_LINE_ENDINGS = "MIXED_LINE_ENDINGS"
    TRANSITION_LOG_CAPPED = "TRANSITION_LOG_CAPPED"
    INVALID_TRANSITION_TABLE = "INVALID_TRANSITION_TABLE"
    INVALID_STATE = "INVALID_STATE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class Diagnostic:
    """One reported problem, with its source location when it has one."""

    category: ErrorCategory
    severity: Severity
    code: Code
    message: str
    line: int | None = None
    column: int | None = None
    offset: int | None = None
    recovery: str = ""

    @property
    def is_error(self) -> bool:
        return self.severity is Severity.ERROR

    @property
    def location(self) -> str:
        if self.line is None:
            return "Not tied to a source position"
        return f"Line {self.line}, Column {self.column}"

    def format(self) -> str:
        """Render the diagnostic as the multi-line report shown to users."""
        heading = self.category.value if self.is_error else f"{self.category.value} (warning)"
        parts = [f"{heading}:", self.message, "", "Location:", self.location]
        if self.recovery:
            parts += ["", "Recovery:", self.recovery]
        return "\n".join(parts)


class RemoverError(Exception):
    """Base class for exceptions that carry a :class:`Diagnostic`."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


class LexicalError(RemoverError):
    """Raised by ``ProcessingResult.raise_for_errors`` for lexical errors."""


class InputValidationError(RemoverError):
    """The input was rejected before the FSM ran."""


class ProcessingError(RemoverError):
    """An internal fault in the processing engine."""


def processing_error(code: Code, message: str) -> ProcessingError:
    """Build a :class:`ProcessingError` with a matching diagnostic."""
    return ProcessingError(
        Diagnostic(
            category=ErrorCategory.PROCESSING,
            severity=Severity.ERROR,
            code=code,
            message=message,
            recovery="Processing stopped. This is a fault in the program, not in the source code.",
        )
    )
