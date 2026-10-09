"""HTML fragments for the UI, built from processing results.

These are plain functions (no Streamlit calls) so they can be tested.
Styles are inline and use translucent colours, so the fragments read
well in both the light and the dark Streamlit theme. The app renders
them with ``st.html``; ``st.markdown`` would replace a ``<pre>`` element
with its own code-block component and lose the line breaks.
"""

from __future__ import annotations

import html
from collections.abc import Iterable

from remover import Comment, Literal, LiteralKind, ProcessingResult

PRE_STYLE = (
    "font-family:'Source Code Pro',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;"
    "font-size:0.85rem;line-height:1.5;white-space:pre;"
    "padding:0.75rem 1rem;border:1px solid rgba(128,128,128,0.35);border-radius:0.5rem;"
    "max-height:440px;overflow:auto;margin:0 0 0.75rem 0;"
)

STYLES = {
    "comment": (
        "background:rgba(239,68,68,0.16);text-decoration:line-through;"
        "text-decoration-color:rgba(220,38,38,0.75);"
    ),
    "string": "background:rgba(34,197,94,0.20);",
    "character": "background:rgba(20,184,166,0.22);",
}

LEGEND = [
    ("comment", "comment (removed)"),
    ("string", "string literal"),
    ("character", "character literal"),
]

MAX_HIGHLIGHTED_CHARACTERS = 60_000


def _span(text: str, style: str | None) -> str:
    escaped = html.escape(text, quote=False)
    if not style:
        return escaped
    return f'<span style="{STYLES[style]}">{escaped}</span>'


def lexeme_classes(source: str, comments: Iterable[Comment], literals: Iterable[Literal]) -> list[str | None]:
    """The highlight class of every character: comment, string, character or None (code)."""
    classes: list[str | None] = [None] * len(source)
    for comment in comments:
        for i in range(comment.start.offset, comment.start.offset + len(comment.text)):
            classes[i] = "comment"
    for literal in literals:
        kind = "string" if literal.kind is LiteralKind.STRING else "character"
        for i in range(literal.start.offset, literal.start.offset + len(literal.text)):
            classes[i] = kind
    return classes


def _runs(text: str, classes: list[str | None]) -> str:
    """Merge neighbouring characters with the same class into one span."""
    parts: list[str] = []
    start = 0
    for i in range(1, len(text) + 1):
        if i == len(text) or classes[i] != classes[start]:
            parts.append(_span(text[start:i], classes[start]))
            start = i
    return "".join(parts)


def highlighted_source(result: ProcessingResult) -> str:
    """The original source with comments and literals highlighted."""
    source = result.original_source
    shown = source[:MAX_HIGHLIGHTED_CHARACTERS]
    classes = lexeme_classes(source, result.detected_comments, result.detected_literals)
    body = _runs(shown, classes[: len(shown)]) if shown else "<em>(empty)</em>"
    if len(shown) < len(source):
        body += html.escape(f"\n… {len(source) - len(shown):,} more characters not shown")
    return f'<pre style="{PRE_STYLE}">{body}</pre>'


def legend() -> str:
    items = "".join(
        f'<span style="{STYLES[key]}padding:0 0.35rem;margin-right:0.75rem;border-radius:3px">'
        f"{html.escape(label)}</span>"
        for key, label in LEGEND
    )
    return f'<div style="font-size:0.8rem;margin:0 0 0.4rem 0">{items}</div>'


def pipeline(result: ProcessingResult) -> str:
    """The processing pipeline with the numbers from this run."""
    stats = result.statistics
    validation_failed = any(e.category.name == "INPUT_VALIDATION" for e in result.errors)
    lexical_errors = sum(1 for e in result.errors if e.category.name == "LEXICAL")
    source = result.original_source

    stages: list[tuple[str, str, str, str]] = [
        ("Input", f"{len(source):,} chars", f"{stats.original_lines if stats else 0} lines", "blue"),
    ]
    if validation_failed or stats is None:
        stages.append(("Validation", "rejected", "FSM not run", "red"))
        for name in ("FSM Scan", "Comment Removal", "Whitespace", "Cleaned Code"):
            stages.append((name, "—", "not run", "gray"))
    else:
        stages += [
            ("Validation", "passed", f"{len(result.warnings)} warning(s)", "green"),
            (
                "FSM Scan",
                f"{stats.fsm_transitions:,} transitions",
                f"ended in {result.final_state.value}" if result.final_state else "",
                "red" if lexical_errors else "amber",
            ),
            (
                "Comment Removal",
                f"{stats.comments_detected} comment(s)",
                f"{stats.comment_characters_removed:,} chars removed",
                "gray",
            ),
            (
                "Whitespace",
                f"{stats.whitespace_removed:,} removed",
                f"{result.options.whitespace_mode.label} · {result.options.newline_mode.label}",
                "teal",
            ),
            (
                "Cleaned Code",
                f"{stats.output_characters:,} chars",
                "output may be incomplete" if lexical_errors else f"{stats.output_lines} lines",
                "red" if lexical_errors else "green",
            ),
        ]
    tints = {
        "blue": "59,130,246",
        "green": "34,197,94",
        "red": "239,68,68",
        "amber": "245,158,11",
        "gray": "148,163,184",
        "teal": "20,184,166",
    }
    boxes = []
    for index, (name, value, detail, tint) in enumerate(stages, start=1):
        boxes.append(
            f'<div style="flex:1 1 130px;border:1px solid rgba({tints[tint]},0.55);'
            f"background:rgba({tints[tint]},0.10);border-radius:0.5rem;padding:0.45rem 0.6rem;"
            'min-width:120px">'
            f'<div style="font-size:0.68rem;opacity:0.75;text-transform:uppercase;letter-spacing:0.04em">'
            f"{index} · {html.escape(name)}</div>"
            f'<div style="font-weight:600;font-size:0.95rem">{html.escape(value)}</div>'
            f'<div style="font-size:0.72rem;opacity:0.8">{html.escape(detail)}</div>'
            "</div>"
        )
    arrow = '<div style="align-self:center;opacity:0.55;font-size:1.1rem">→</div>'
    return (
        '<div style="display:flex;flex-wrap:wrap;gap:0.35rem;align-items:stretch;margin:0.25rem 0 0.75rem 0">'
        + arrow.join(boxes)
        + "</div>"
    )
