"""The FSM engine.

:class:`CommentFSM` runs the transition table over the source one
character at a time. For each character it

1. classifies the character into its input class,
2. looks up the transition for (current state, input class),
3. applies the output action (emit, discard, buffer, ...),
4. moves to the next state, and
5. returns a :class:`TransitionRecord` of exactly what happened.

The engine knows nothing about comments or whitespace beyond what the
table says. Its only memory besides the current state is a
one-character buffer, and that buffer is non-empty exactly while the
machine is in POSSIBLE_COMMENT, so the state alone already determines it
(which is why this is still a finite-state machine). The engine checks
that invariant on every step.
"""

from __future__ import annotations

from collections.abc import Iterator

from .errors import Code, processing_error
from .models import TransitionRecord
from .states import INITIAL_STATE, State
from .transitions import (
    EOF_TABLE,
    TRANSITION_TABLE,
    CharClass,
    OutputAction,
    Transition,
    classify,
    validate_table,
)


class CommentFSM:
    """Character-by-character comment-recognising finite-state transducer.

    The engine runs whatever table it is given; by default the C-like
    table of transitions.py. A table is checked for completeness before it
    is used, so an undefined transition can never be reached mid-run.
    """

    def __init__(
        self,
        table: dict[tuple[State, CharClass], Transition] = TRANSITION_TABLE,
        eof_table: dict[State, Transition] = EOF_TABLE,
    ) -> None:
        validate_table(table, eof_table)
        self._table = table
        self._eof_table = eof_table
        self.reset()

    def reset(self) -> None:
        """Return to the initial state with empty output."""
        self._state = INITIAL_STATE
        self._buffer = ""
        self._output: list[str] = []
        self._output_length = 0
        self._offset = 0
        self._line = 1
        self._column = 1
        self._after_cr = False
        self._finished = False

    @property
    def state(self) -> State:
        return self._state

    @property
    def buffer(self) -> str:
        return self._buffer

    @property
    def output(self) -> str:
        return "".join(self._output)

    @property
    def finished(self) -> bool:
        return self._finished

    def feed(self, ch: str) -> TransitionRecord:
        """Consume one character and return the record of the transition taken."""
        if self._finished:
            raise processing_error(Code.INVALID_STATE, "The FSM already reached the end of input.")
        if len(ch) != 1:
            raise processing_error(
                Code.INVALID_STATE, f"feed() takes exactly one character, got {len(ch)}."
            )
        line, column = self._locate(ch)
        rule = self._table[(self._state, classify(ch))]
        emitted, discarded = self._apply(rule.output, ch)
        record = self._record(rule, ch, line, column, emitted, discarded)
        self._move_to(rule.next_state)
        self._advance(ch)
        return record

    def finish(self) -> TransitionRecord:
        """Apply the end-of-input transition (no character is consumed)."""
        if self._finished:
            raise processing_error(Code.INVALID_STATE, "The FSM already reached the end of input.")
        if self._after_cr:
            # The source ended with a lone carriage return: it ended a line.
            self._after_cr = False
            self._line += 1
            self._column = 1
        rule = self._eof_table[self._state]
        emitted = ""
        if rule.output is OutputAction.FLUSH:
            emitted = self._take_buffer()
            self._write(emitted)
        record = self._record(rule, None, self._line, self._column, emitted, "")
        self._move_to(rule.next_state)
        self._finished = True
        return record

    def run(self, source: str) -> Iterator[TransitionRecord]:
        """Reset, then yield one record per character and a final end-of-input record."""
        self.reset()
        for ch in source:
            yield self.feed(ch)
        yield self.finish()

    # -- internals ---------------------------------------------------------

    def _locate(self, ch: str) -> tuple[int, int]:
        # A CR followed by LF is one line break; a lone CR is a line break by
        # itself. That is only known at the next character, so a pending CR is
        # resolved here instead of peeking ahead.
        if self._after_cr:
            self._after_cr = False
            if ch != "\n":
                self._line += 1
                self._column = 1
        return self._line, self._column

    def _advance(self, ch: str) -> None:
        self._offset += 1
        if ch == "\n":
            self._line += 1
            self._column = 1
        elif ch == "\r":
            self._column += 1
            self._after_cr = True
        else:
            self._column += 1

    def _apply(self, output: OutputAction, ch: str) -> tuple[str, str]:
        """Perform the output action; return (emitted text, discarded text)."""
        if output is OutputAction.EMIT:
            self._write(ch)
            return ch, ""
        if output is OutputAction.DISCARD:
            return "", ch
        if output is OutputAction.BUFFER:
            if self._buffer:
                raise processing_error(
                    Code.INVALID_STATE, f"Buffer already holds {self._buffer!r}; cannot buffer {ch!r}."
                )
            self._buffer = ch
            return "", ""
        if output is OutputAction.FLUSH_AND_EMIT:
            text = self._take_buffer() + ch
            self._write(text)
            return text, ""
        if output is OutputAction.DISCARD_BUFFER:
            return "", self._take_buffer() + ch
        if output is OutputAction.REPLACE_WITH_SPACE:
            self._write(" ")
            return " ", ch
        raise processing_error(
            Code.INVALID_STATE, f"Output action {output} cannot be applied to a character."
        )

    def _take_buffer(self) -> str:
        if not self._buffer:
            raise processing_error(
                Code.INVALID_STATE, f"State {self._state} tried to release an empty buffer."
            )
        held, self._buffer = self._buffer, ""
        return held

    def _write(self, text: str) -> None:
        self._output.append(text)
        self._output_length += len(text)

    def _move_to(self, next_state: State) -> None:
        if bool(self._buffer) != (next_state is State.POSSIBLE_COMMENT):
            raise processing_error(
                Code.INVALID_STATE,
                f"Invalid processing state: entering {next_state} with buffer {self._buffer!r}.",
            )
        self._state = next_state

    def _record(
        self,
        rule: Transition,
        ch: str | None,
        line: int,
        column: int,
        emitted: str,
        discarded: str,
    ) -> TransitionRecord:
        return TransitionRecord(
            step=self._offset,
            offset=self._offset,
            line=line,
            column=column,
            character=ch,
            input_class=rule.input_class,
            current_state=self._state,
            next_state=rule.next_state,
            output=rule.output,
            event=rule.event,
            emitted=emitted,
            discarded=discarded,
            buffer=self._buffer,
            output_length=self._output_length,
            action=rule.action,
        )
