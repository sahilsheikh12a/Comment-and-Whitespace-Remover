"""The processing pipeline: the single entry point used by the UI and CLI.

    Input Validation
        -> FSM initialisation and character-by-character scanning
        -> comment recognition and removal      (comment_remover.py, fsm.py)
        -> whitespace processing                (whitespace.py)
        -> result construction                  (statistics, diagnostics)

Example::

    from remover import process

    result = process(source_code, whitespace_mode="normalize")
    print(result.cleaned_source)
"""

from __future__ import annotations

from dataclasses import replace

from .comment_remover import CommentRemovalResult, remove_comments
from .errors import (
    Code,
    Diagnostic,
    ErrorCategory,
    InputValidationError,
    ProcessingError,
    Severity,
)
from .models import CommentKind, LiteralKind, ProcessingOptions, ProcessingResult, Statistics
from .states import State
from .text import count_lines, line_breaks
from .whitespace import WhitespaceResult, process_whitespace


def process(
    source: str,
    options: ProcessingOptions | None = None,
    **settings: object,
) -> ProcessingResult:
    """Run the whole pipeline on ``source``.

    Settings can be passed as a :class:`ProcessingOptions` object, as
    keyword arguments (``whitespace_mode="compact"``), or both, in which
    case the keywords override the object. Problems with the source never
    raise: they are returned in ``result.errors`` and ``result.warnings``.
    """
    if options is None:
        options = ProcessingOptions(**settings)  # type: ignore[arg-type]
    elif settings:
        options = replace(options, **settings)  # type: ignore[arg-type]

    try:
        warnings = validate_source(source, options)
    except InputValidationError as exc:
        return _without_output(source, options, [exc.diagnostic])

    try:
        removal = remove_comments(
            source,
            record_transitions=options.record_transitions,
            max_recorded_transitions=options.max_recorded_transitions,
        )
        layout = process_whitespace(removal.pieces, options.whitespace_mode, options.newline_mode)
    except ProcessingError as exc:
        return _without_output(source, options, [*warnings, exc.diagnostic])
    except Exception as exc:  # noqa: BLE001 - report, never crash the caller
        diagnostic = Diagnostic(
            category=ErrorCategory.PROCESSING,
            severity=Severity.ERROR,
            code=Code.INTERNAL_ERROR,
            message=f"Unexpected internal error: {type(exc).__name__}: {exc}",
            recovery="Processing stopped. This is a fault in the program, not in the source code.",
        )
        return _without_output(source, options, [*warnings, diagnostic])

    diagnostics = [*warnings, *removal.diagnostics]
    if not removal.transitions_complete and options.record_transitions:
        diagnostics.append(
            Diagnostic(
                category=ErrorCategory.PROCESSING,
                severity=Severity.WARNING,
                code=Code.TRANSITION_LOG_CAPPED,
                message=(
                    f"The transition log was capped at {options.max_recorded_transitions:,} "
                    f"of {removal.transition_count:,} transitions."
                ),
                recovery=(
                    "The output and the statistics still cover the whole input; only the "
                    "recorded log is shorter."
                ),
            )
        )
    errors = tuple(d for d in diagnostics if d.is_error)
    warning_list = tuple(d for d in diagnostics if not d.is_error)
    return ProcessingResult(
        original_source=source,
        cleaned_source=layout.text,
        comment_free_source=removal.output,
        options=options,
        transition_log=removal.transitions,
        transition_log_complete=removal.transitions_complete,
        detected_comments=removal.comments,
        detected_literals=removal.literals,
        separators=layout.separators,
        statistics=compute_statistics(source, removal, layout, len(errors), len(warning_list)),
        errors=errors,
        warnings=warning_list,
        final_state=removal.final_state,
        accepted=removal.accepted,
        pieces=removal.pieces,
    )


def validate_source(source: object, options: ProcessingOptions) -> list[Diagnostic]:
    """Check that ``source`` can be processed.

    Raises :class:`InputValidationError` for input that must be rejected
    and returns warnings for input that is processed anyway.
    """
    if not isinstance(source, str):
        raise _invalid(
            Code.NOT_TEXT,
            f"The source must be text (str), not {type(source).__name__}.",
            "Decode the bytes first, for example with remover.decode_source().",
        )
    if len(source) > options.max_input_characters:
        raise _invalid(
            Code.INPUT_TOO_LARGE,
            f"The source has {len(source):,} characters; the limit is "
            f"{options.max_input_characters:,}.",
            "Process a smaller file, or raise max_input_characters in ProcessingOptions.",
        )
    nul = source.find("\x00")
    if nul != -1:
        line, column = _line_and_column(source, nul)
        raise _invalid(
            Code.NUL_CHARACTER,
            "The input contains a NUL character, so it looks like binary data rather "
            "than source code.",
            "Check that the right file was selected.",
            line=line,
            column=column,
            offset=nul,
        )

    warnings: list[Diagnostic] = []
    if not source:
        warnings.append(
            _validation_warning(Code.EMPTY_INPUT, "The source is empty.", "The output is empty too.")
        )
    endings = {brk for brk in line_breaks(source)}
    if len(endings) > 1:
        names = {"\n": "LF", "\r\n": "CR LF", "\r": "CR"}
        found = ", ".join(sorted(names[ending] for ending in endings))
        warnings.append(
            _validation_warning(
                Code.MIXED_LINE_ENDINGS,
                f"The source mixes line endings ({found}).",
                "Each line keeps its own line ending in the output.",
            )
        )
    return warnings


def decode_source(data: bytes) -> str:
    """Decode an uploaded file as UTF-8 (a byte-order mark is skipped)."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _invalid(
            Code.UNDECODABLE_INPUT,
            f"The file is not valid UTF-8 text (invalid byte at position {exc.start}).",
            "Save the file as UTF-8 and try again.",
        ) from None


def compute_statistics(
    source: str,
    removal: CommentRemovalResult,
    layout: WhitespaceResult,
    errors: int,
    warnings: int,
) -> Statistics:
    """Derive every statistic from the actual results of one run."""
    comments = removal.comments
    literals = removal.literals
    cleaned = layout.text
    return Statistics(
        original_characters=len(source),
        output_characters=len(cleaned),
        characters_removed=len(source) - len(cleaned),
        original_lines=count_lines(source),
        output_lines=count_lines(cleaned),
        comments_detected=len(comments),
        single_line_comments=sum(c.kind is CommentKind.SINGLE_LINE for c in comments),
        multi_line_comments=sum(c.kind is CommentKind.MULTI_LINE for c in comments),
        comment_characters_removed=sum(len(c.text) for c in comments),
        string_literals=sum(lit.kind is LiteralKind.STRING for lit in literals),
        character_literals=sum(lit.kind is LiteralKind.CHARACTER for lit in literals),
        whitespace_removed=layout.whitespace_removed,
        separators_inserted=len(layout.separators),
        comment_line_breaks_kept=layout.comment_line_breaks_kept,
        characters_scanned=removal.characters_scanned,
        fsm_transitions=removal.transition_count,
        state_changes=removal.state_changes,
        errors=errors,
        warnings=warnings,
        state_visits={state.value: removal.state_visits.get(state, 0) for state in State},
    )


def _without_output(
    source: object, options: ProcessingOptions, diagnostics: list[Diagnostic]
) -> ProcessingResult:
    """Result for a run that stopped before producing output."""
    text = source if isinstance(source, str) else ""
    return ProcessingResult(
        original_source=text,
        cleaned_source="",
        comment_free_source="",
        options=options,
        transition_log=(),
        transition_log_complete=False,
        detected_comments=(),
        detected_literals=(),
        separators=(),
        statistics=None,
        errors=tuple(d for d in diagnostics if d.is_error),
        warnings=tuple(d for d in diagnostics if not d.is_error),
        final_state=None,
        accepted=False,
    )


def _invalid(
    code: Code,
    message: str,
    recovery: str,
    *,
    line: int | None = None,
    column: int | None = None,
    offset: int | None = None,
) -> InputValidationError:
    return InputValidationError(
        Diagnostic(
            category=ErrorCategory.INPUT_VALIDATION,
            severity=Severity.ERROR,
            code=code,
            message=message,
            line=line,
            column=column,
            offset=offset,
            recovery=recovery,
        )
    )


def _validation_warning(code: Code, message: str, recovery: str) -> Diagnostic:
    return Diagnostic(
        category=ErrorCategory.INPUT_VALIDATION,
        severity=Severity.WARNING,
        code=code,
        message=message,
        recovery=recovery,
    )


def _line_and_column(source: str, offset: int) -> tuple[int, int]:
    """1-based line and column of ``offset``, counting CR LF as one line break."""
    line, column, i = 1, 1, 0
    while i < offset:
        ch = source[i]
        if ch == "\n" or (ch == "\r" and source[i + 1 : i + 2] != "\n"):
            line, column = line + 1, 1
        else:
            column += 1
        i += 1
    return line, column
