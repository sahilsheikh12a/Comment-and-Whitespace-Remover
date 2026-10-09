"""Whitespace processing: the second stage of the pipeline.

It runs on the comment-free output of the FSM, already split into tagged
pieces, so it always knows which characters belong to a string or
character literal (never changed) and where a comment used to be.

The text is first broken into *atoms*:

    SOLID    a run of code characters without whitespace, or a whole literal
    SPACE    a run of spaces, tabs, vertical tabs or form feeds
    BREAK    one line break (LF, CR LF or CR)
    COMMENT  a zero-width marker where a comment was removed

and then into lines. Every whitespace decision is made at a *gap*: the
SPACE and COMMENT atoms between two SOLID atoms on a line. A gap may only
disappear when the tokens on both sides stay separate without it, which
``separator_reason`` decides from C's lexical rules. That is what stops
``int x`` from becoming ``intx`` and ``int/**/value`` from becoming
``intvalue``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from enum import Enum, StrEnum

from .models import Comment, NewlineMode, Piece, PieceKind, SeparatorInsertion, WhitespaceMode
from .text import HORIZONTAL_WHITESPACE, LINE_BREAK_CHARS, line_breaks

# Two-character sequences that lex differently when the characters touch:
# every adjacent pair inside a multi-character C/C++ punctuator (including
# digraphs) plus '**', '?.' and '??' from other C-family languages. Removing
# the space in "a - -b" would produce the token '--'.
FUSING_PAIRS = frozenset(
    {
        "++", "--", "->", "<<", ">>", "<=", ">=", "==", "!=", "&&", "||",
        "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=",
        "##", "::", "..", ".*", ">*", "=>",
        "<:", ":>", "<%", "%>", "%:", ":%",
        "**", "?.", "??",
    }
)
COMMENT_OPENERS = frozenset({"//", "/*"})
QUOTES = frozenset("\"'")


def is_word_char(ch: str) -> bool:
    """Characters that can continue an identifier, keyword or number.

    Non-ASCII characters and the backslash (universal character names such
    as \\u00e9) are included so that whitespace next to them is never
    removed.
    """
    return ch.isalnum() or ch in "_$\\" or ord(ch) > 127


def _trailing_number(token: str) -> str:
    """The number at the end of ``token`` (C 'preprocessing number'), or ''."""
    i = len(token)
    while i > 0 and (token[i - 1].isalnum() or token[i - 1] in "_."):
        i -= 1
    run = token[i:]
    if run[:1].isdigit() or (run[:1] == "." and run[1:2].isdigit()):
        return run
    return ""


def separator_reason(left: str, right: str) -> str | None:
    """Why the tokens ``left`` and ``right`` need whitespace between them.

    Returns ``None`` when they can touch without changing how the code is
    tokenised.
    """
    a, b = left[-1], right[0]
    pair = a + b
    if is_word_char(a) and is_word_char(b):
        return "identifier, keyword or number characters on both sides would merge"
    if pair in COMMENT_OPENERS:
        return f"'{pair}' would start a comment"
    if pair in FUSING_PAIRS:
        return f"'{a}' and '{b}' would merge into the operator '{pair}'"
    if is_word_char(a) and b in QUOTES:
        return "a word before a quote would become a literal prefix (as in L\"x\")"
    if a in QUOTES and is_word_char(b):
        return "a word after a literal would become a literal suffix"
    if _trailing_number(left):
        if b == ".":
            return "the '.' would become part of the number"
        if a in "eEpP" and b in "+-":
            return "the sign would become part of the number's exponent (0xE+1)"
    if a == "." and b.isdigit():
        return "'.' followed by a digit would form a number"
    return None


class _AtomKind(Enum):
    SOLID = "solid"
    SPACE = "space"
    BREAK = "break"
    COMMENT = "comment"


@dataclass(frozen=True, slots=True)
class _Atom:
    kind: _AtomKind
    text: str = ""
    literal: bool = False
    comment: Comment | None = None
    from_comment: bool = False  # a BREAK that was inside a multi-line comment


class LineKind(StrEnum):
    CODE = "code"
    BLANK = "blank"
    COMMENT_ONLY = "comment only"


@dataclass(frozen=True)
class _Line:
    atoms: list[_Atom]
    terminator: str | None
    terminator_from_comment: bool


@dataclass(frozen=True)
class _RenderedLine:
    content: str
    kind: LineKind
    kept_whitespace: int  # original whitespace characters kept in ``content``
    terminator: str | None
    terminator_from_comment: bool
    continues: bool  # ends with a backslash (line continuation)
    separators: tuple[SeparatorInsertion, ...] = ()


@dataclass(frozen=True)
class WhitespaceResult:
    text: str
    whitespace_removed: int
    separators: tuple[SeparatorInsertion, ...]
    comment_line_breaks_kept: int
    comment_line_break_characters_kept: int


def process_whitespace(
    pieces: Iterable[Piece],
    whitespace_mode: WhitespaceMode | str = WhitespaceMode.NORMALIZE,
    newline_mode: NewlineMode | str = NewlineMode.STRUCTURE,
) -> WhitespaceResult:
    """Lay out the comment-free pieces according to the two modes."""
    ws_mode = WhitespaceMode(whitespace_mode)
    nl_mode = NewlineMode(newline_mode)
    atoms = _atomize(pieces, nl_mode)
    renderer = _LineRenderer(ws_mode)
    rendered = [renderer.render(line) for line in _split_lines(atoms)]
    kept = _select_lines(rendered, nl_mode)

    text = "".join(line.content + (line.terminator or "") for line in kept)
    original_whitespace = sum(
        len(atom.text)
        for atom in atoms
        if atom.kind is _AtomKind.SPACE or (atom.kind is _AtomKind.BREAK and not atom.from_comment)
    )
    kept_whitespace = sum(
        line.kept_whitespace
        + (len(line.terminator) if line.terminator and not line.terminator_from_comment else 0)
        for line in kept
    )
    comment_breaks = [line.terminator for line in kept if line.terminator and line.terminator_from_comment]
    return WhitespaceResult(
        text=text,
        whitespace_removed=original_whitespace - kept_whitespace,
        separators=tuple(sep for line in kept for sep in line.separators),
        comment_line_breaks_kept=len(comment_breaks),
        comment_line_break_characters_kept=sum(len(brk) for brk in comment_breaks),
    )


def _atomize(pieces: Iterable[Piece], newline_mode: NewlineMode) -> list[_Atom]:
    atoms: list[_Atom] = []
    for piece in pieces:
        if piece.kind is PieceKind.CODE:
            _atomize_code(piece.text, atoms)
        elif piece.kind is PieceKind.COMMENT:
            # The replacement space the FSM wrote for the comment is ignored:
            # the gap logic decides whether a space is needed here.
            comment = piece.comment
            atoms.append(_Atom(_AtomKind.COMMENT, comment=comment))
            if newline_mode is NewlineMode.PRESERVE and comment is not None:
                for brk in line_breaks(comment.text):
                    atoms.append(_Atom(_AtomKind.BREAK, brk, from_comment=True))
                    atoms.append(_Atom(_AtomKind.COMMENT, comment=comment))
        else:
            atoms.append(_Atom(_AtomKind.SOLID, piece.text, literal=True))
    return atoms


def _atomize_code(text: str, atoms: list[_Atom]) -> None:
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in HORIZONTAL_WHITESPACE:
            j = i + 1
            while j < n and text[j] in HORIZONTAL_WHITESPACE:
                j += 1
            atoms.append(_Atom(_AtomKind.SPACE, text[i:j]))
            i = j
        elif ch == "\r" and i + 1 < n and text[i + 1] == "\n":
            atoms.append(_Atom(_AtomKind.BREAK, "\r\n"))
            i += 2
        elif ch in LINE_BREAK_CHARS:
            atoms.append(_Atom(_AtomKind.BREAK, ch))
            i += 1
        else:
            j = i + 1
            while j < n and text[j] not in HORIZONTAL_WHITESPACE and text[j] not in LINE_BREAK_CHARS:
                j += 1
            atoms.append(_Atom(_AtomKind.SOLID, text[i:j]))
            i = j


def _split_lines(atoms: list[_Atom]) -> list[_Line]:
    lines: list[_Line] = []
    current: list[_Atom] = []
    for atom in atoms:
        if atom.kind is _AtomKind.BREAK:
            lines.append(_Line(current, atom.text, atom.from_comment))
            current = []
        else:
            current.append(atom)
    lines.append(_Line(current, None, False))
    return lines


class _LineRenderer:
    """Renders one line at a time; remembers whether a directive continues."""

    def __init__(self, mode: WhitespaceMode) -> None:
        self.mode = mode
        self._in_directive = False

    def render(self, line: _Line) -> _RenderedLine:
        atoms = line.atoms
        solid_indexes = [i for i, atom in enumerate(atoms) if atom.kind is _AtomKind.SOLID]
        has_comment = any(atom.kind is _AtomKind.COMMENT for atom in atoms)
        if not solid_indexes:
            self._in_directive = False
            content = ""
            if self.mode is WhitespaceMode.PRESERVE and not has_comment:
                content = "".join(atom.text for atom in atoms)
            return _RenderedLine(
                content,
                LineKind.COMMENT_ONLY if has_comment else LineKind.BLANK,
                len(content),
                line.terminator,
                line.terminator_from_comment,
                continues=False,
            )

        first, last = solid_indexes[0], solid_indexes[-1]
        head, tail = atoms[first], atoms[last]
        directive = self._in_directive or (not head.literal and head.text.startswith("#"))
        continues = not tail.literal and tail.text.endswith("\\")
        self._in_directive = directive and continues

        leading = self._leading(atoms[:first])
        parts = [leading, head.text]
        kept = len(leading)
        separators: list[SeparatorInsertion] = []
        previous, gap = head, []
        for atom in atoms[first + 1 : last + 1]:
            if atom.kind is not _AtomKind.SOLID:
                gap.append(atom)
                continue
            text, kept_count, separator = self._gap(gap, previous, atom, directive)
            parts += [text, atom.text]
            kept += kept_count
            if separator is not None:
                separators.append(separator)
            previous, gap = atom, []

        trailing = atoms[last + 1 :]
        trailing_comment = any(atom.kind is _AtomKind.COMMENT for atom in trailing)
        if self.mode is WhitespaceMode.PRESERVE and not trailing_comment:
            # Original trailing whitespace stays; whitespace that only
            # separated the code from a removed comment does not.
            spaces = "".join(atom.text for atom in trailing)
            parts.append(spaces)
            kept += len(spaces)
        return _RenderedLine(
            "".join(parts),
            LineKind.CODE,
            kept,
            line.terminator,
            line.terminator_from_comment,
            continues,
            tuple(separators),
        )

    def _leading(self, atoms: list[_Atom]) -> str:
        if self.mode is WhitespaceMode.PRESERVE:
            return "".join(atom.text for atom in atoms if atom.kind is _AtomKind.SPACE)
        if self.mode is WhitespaceMode.NORMALIZE:
            # Indentation is the whitespace before anything else on the line;
            # whitespace after a comment at the start of the line is dropped.
            indentation = []
            for atom in atoms:
                if atom.kind is not _AtomKind.SPACE:
                    break
                indentation.append(atom.text)
            return "".join(indentation)
        return ""

    def _gap(
        self, gap: list[_Atom], left: _Atom, right: _Atom, directive: bool
    ) -> tuple[str, int, SeparatorInsertion | None]:
        """Render the gap between two solids: (text, original whitespace kept, separator)."""
        if not gap:
            return "", 0, None
        spaces = "".join(atom.text for atom in gap if atom.kind is _AtomKind.SPACE)
        mode = self.mode
        if mode is WhitespaceMode.COMPACT and directive:
            # Whitespace in preprocessor directives can matter:
            # "#define F (x)" and "#define F(x)" define different macros.
            mode = WhitespaceMode.NORMALIZE
        if spaces and mode is WhitespaceMode.PRESERVE:
            return spaces, len(spaces), None
        if spaces and mode is WhitespaceMode.NORMALIZE:
            return " ", 1, None
        reason = separator_reason(left.text, right.text)
        if reason is None:
            return "", 0, None
        if spaces:
            return " ", 1, None
        # Only a removed comment stood between the tokens: keep one space there.
        comment = next(atom.comment for atom in gap if atom.kind is _AtomKind.COMMENT)
        assert comment is not None
        return " ", 0, SeparatorInsertion(comment, left.text[-1], right.text[0], reason)


def _select_lines(lines: list[_RenderedLine], mode: NewlineMode) -> list[_RenderedLine]:
    if mode is NewlineMode.PRESERVE:
        return lines
    selected: list[_RenderedLine] = []
    for line in lines:
        after_continuation = bool(selected) and selected[-1].continues
        if line.kind is LineKind.COMMENT_ONLY:
            if not after_continuation:
                continue
            # The previous line ends with a backslash, which joins it to this
            # one. Deleting this line would join the next one instead.
            line = replace(line, kind=LineKind.BLANK)
        if mode is NewlineMode.COLLAPSE and line.kind is LineKind.BLANK:
            if not after_continuation and (not selected or selected[-1].kind is LineKind.BLANK):
                continue
            line = replace(line, content="", kept_whitespace=0)
        selected.append(line)
    if mode is NewlineMode.COLLAPSE:
        while (
            selected
            and selected[-1].kind is LineKind.BLANK
            and not (len(selected) > 1 and selected[-2].continues)
        ):
            selected.pop()
    return selected
