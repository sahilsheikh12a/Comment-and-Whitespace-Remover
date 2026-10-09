"""Small character-level helpers shared by the processing stages.

Whitespace follows the C definition: space, horizontal tab, vertical tab
and form feed separate tokens on a line; LF, CR LF and a lone CR end a
line. Other Unicode space characters are treated as ordinary characters,
as a C compiler would treat them.
"""

from __future__ import annotations

HORIZONTAL_WHITESPACE = frozenset(" \t\v\f")
LINE_BREAK_CHARS = frozenset("\r\n")


def is_whitespace(ch: str) -> bool:
    return ch in HORIZONTAL_WHITESPACE or ch in LINE_BREAK_CHARS


def line_breaks(text: str) -> list[str]:
    """Return the line terminators of ``text`` in order ("\\n", "\\r\\n" or "\\r")."""
    breaks: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\r":
            if i + 1 < n and text[i + 1] == "\n":
                breaks.append("\r\n")
                i += 2
                continue
            breaks.append("\r")
        elif ch == "\n":
            breaks.append("\n")
        i += 1
    return breaks


def count_lines(text: str) -> int:
    """Number of lines as an editor shows them (0 for empty text).

    A final line terminator does not start a new line: "a\\nb" and
    "a\\nb\\n" both have two lines.
    """
    if not text:
        return 0
    breaks = len(line_breaks(text))
    ends_with_break = text[-1] in LINE_BREAK_CHARS
    return breaks if ends_with_break else breaks + 1
