"""Text formatting for transition records, shared by the UI and the CLI."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable

from .models import TransitionRecord
from .transitions import Event

_VISIBLE = {
    " ": "␣",
    "\t": "\\t",
    "\n": "\\n",
    "\r": "\\r",
    "\f": "\\f",
    "\v": "\\v",
}


def printable(ch: str | None) -> str:
    """A visible representation of one character (``EOF`` for end of input)."""
    if ch is None:
        return "EOF"
    if ch in _VISIBLE:
        return _VISIBLE[ch]
    if not ch.isprintable():
        return f"\\x{ord(ch):02x}" if ord(ch) < 0x100 else f"\\u{ord(ch):04x}"
    return ch


def printable_text(text: str) -> str:
    return "".join(printable(ch) for ch in text)


def inline_text(text: str) -> str:
    """Longer text on one line: spaces stay, line breaks become ↵ and tabs ⇥."""
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "\r\n":
            out.append(" ↵ ")
            if ch == "\r" and text[i + 1 : i + 2] == "\n":
                i += 1
        elif ch == "\t":
            out.append("⇥")
        elif ch == " ":
            out.append(" ")
        else:
            out.append(printable(ch))
        i += 1
    return "".join(out)


def source_lines(source: str) -> list[str]:
    """The lines of ``source`` without terminators (LF, CR LF and CR all end a line)."""
    lines, current, i, n = [], [], 0, len(source)
    while i < n:
        ch = source[i]
        if ch in "\r\n":
            lines.append("".join(current))
            current = []
            if ch == "\r" and i + 1 < n and source[i + 1] == "\n":
                i += 1
        else:
            current.append(ch)
        i += 1
    lines.append("".join(current))
    return lines


def excerpt(source: str, line: int, column: int) -> str:
    """The source line at ``line`` with a caret under ``column``, compiler style."""
    lines = source_lines(source)
    if not 1 <= line <= len(lines):
        return ""
    text = lines[line - 1].replace("\t", " ")
    gutter = f"{line} | "
    return f"{gutter}{text}\n{' ' * (len(gutter) - 2)}| {' ' * (column - 1)}^"


def record_row(record: TransitionRecord) -> dict[str, object]:
    """One transition record as a flat table row."""
    return {
        "Step": record.step,
        "Pos": record.offset,
        "Line": record.line,
        "Col": record.column,
        "Char": printable(record.character),
        "Input Class": record.input_class.value if record.input_class else "END_OF_INPUT",
        "Current State": record.current_state.value,
        "Next State": record.next_state.value,
        "Output": record.output.value,
        "Emitted": printable_text(record.emitted),
        "Discarded": printable_text(record.discarded),
        "Buffer": printable_text(record.buffer),
        "Event": "" if record.event is Event.NONE else record.event.value,
        "Action": record.action,
    }


def log_to_csv(records: Iterable[TransitionRecord]) -> str:
    """The transition log as CSV text."""
    buffer = io.StringIO()
    writer: csv.DictWriter[str] | None = None
    for record in records:
        row = record_row(record)
        if writer is None:
            writer = csv.DictWriter(buffer, fieldnames=list(row))
            writer.writeheader()
        writer.writerow(row)
    return buffer.getvalue()


def format_log(records: Iterable[TransitionRecord]) -> str:
    """The transition log as a fixed-width text table (used by the CLI)."""
    header = f"{'step':>5}  {'line:col':>8}  {'char':<6} {'current state':<21} {'next state':<21} {'output':<18} emitted"
    lines = [header, "-" * len(header)]
    for record in records:
        where = f"{record.line}:{record.column}"
        lines.append(
            f"{record.step:>5}  {where:>8}  {printable(record.character):<6} "
            f"{record.current_state.value:<21} {record.next_state.value:<21} "
            f"{record.output.value:<18} {printable_text(record.emitted)}"
        )
    return "\n".join(lines)
