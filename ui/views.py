"""Streamlit views: one function per results tab.

Every function only reads a :class:`ProcessingResult` produced by
``remover.process``; nothing shown here is computed outside the engine
except presentation (formatting, filtering, diffing).
"""

from __future__ import annotations

import difflib
from collections import Counter
from pathlib import PurePath

import altair as alt
import streamlit as st

from remover import (
    EOF_TABLE,
    METRIC_DEFINITIONS,
    STATE_INFO,
    TRANSITION_TABLE,
    CharClass,
    Diagnostic,
    ErrorCategory,
    Event,
    ProcessingResult,
    State,
    TransitionRecord,
)
from remover.diagram import edge_for, to_dot, to_mermaid
from remover.display import excerpt, inline_text, log_to_csv, printable, printable_text, record_row
from remover.states import ACCEPTING_STATES

from . import html as fragments

FORMAL_DEFINITION = """
The comment remover is a **deterministic finite-state transducer** (a Mealy machine):
it reads one character per step and, on every transition, both moves to a next state
and writes output.

**M = (Q, Σ, Γ, δ, λ, q₀, F)**

| Symbol | Meaning in this project |
|---|---|
| **Q** | the 9 states listed below |
| **Σ** | all characters; δ and λ only distinguish the 7 input classes below |
| **Γ** | output characters |
| **δ : Q × Σ → Q** | next state (column *Next State* of the transition table) |
| **λ : Q × Σ → Γ\\*** | output written by the transition (column *Output*) |
| **q₀** | `NORMAL` |
| **F** | `NORMAL`, `POSSIBLE_COMMENT`, `SINGLE_LINE_COMMENT`: the states in which the input may end |
"""

ERROR_CLASSES = [
    (
        ErrorCategory.LEXICAL.value,
        "The source breaks a lexical rule: a comment, string or character literal that is "
        "never closed. The scanner reports the location, recovers and keeps going.",
    ),
    (
        ErrorCategory.INPUT_VALIDATION.value,
        "The input cannot be processed at all (not text, binary data, too large). "
        "The FSM does not run.",
    ),
    (
        ErrorCategory.PROCESSING.value,
        "An internal fault such as an incomplete transition table or a broken state "
        "invariant. Reported instead of crashing; it indicates a bug, not a source problem.",
    ),
]


def cleaned_file_name(file_name: str) -> str:
    path = PurePath(file_name or "source.c")
    suffix = path.suffix or ".c"
    return f"{path.stem}.cleaned{suffix}"


def md_text(text: str) -> str:
    """Escape text so Markdown shows it literally ('*' in '*/' must not start italics)."""
    for ch in "\\`*_[]<>#|":
        text = text.replace(ch, "\\" + ch)
    return text


def md_code(text: str) -> str:
    """Inline code that survives backticks inside ``text``."""
    return f"`` {text} ``" if "`" in text else f"`{text}`"


def show_code(text: str) -> None:
    """Show source code exactly, with line numbers.

    st.code drops one leading and one trailing line break; the extra leading
    line break keeps an initial blank line visible, so line numbers stay true.
    """
    st.code("\n" + text, language="c", line_numbers=True)


# --- Source Code ---------------------------------------------------------------


def render_source_tab(result: ProcessingResult) -> None:
    st.markdown(
        "The original source as entered. The highlighting shows what the FSM recognised "
        "while scanning it."
    )
    st.html(fragments.legend())
    st.html(fragments.highlighted_source(result))

    left, right = st.columns(2)
    with left:
        st.markdown(f"##### Detected comments ({len(result.detected_comments)})")
        if result.detected_comments:
            st.dataframe(
                [
                    {
                        "#": number,
                        "Kind": comment.kind.value,
                        "Starts": f"{comment.start.line}:{comment.start.column}",
                        "Ends": f"{comment.end.line}:{comment.end.column}",
                        "Chars": len(comment.text),
                        "Closed": "yes" if comment.terminated else "NO",
                        "Text": _shorten(comment.text),
                    }
                    for number, comment in enumerate(result.detected_comments, start=1)
                ],
                hide_index=True,
            )
        else:
            st.caption("No comments found.")
    with right:
        st.markdown(f"##### Literals preserved ({len(result.detected_literals)})")
        if result.detected_literals:
            st.dataframe(
                [
                    {
                        "#": number,
                        "Kind": literal.kind.value,
                        "Starts": f"{literal.start.line}:{literal.start.column}",
                        "Closed": "yes" if literal.terminated else "NO",
                        "Text": _shorten(literal.text),
                    }
                    for number, literal in enumerate(result.detected_literals, start=1)
                ],
                hide_index=True,
            )
        else:
            st.caption("No string or character literals found.")


def _shorten(text: str, limit: int = 70) -> str:
    shown = inline_text(text[:limit])
    return shown + ("…" if len(text) > limit else "")


# --- Cleaned Output ------------------------------------------------------------


def render_output_tab(result: ProcessingResult, file_name: str) -> None:
    if not result.fsm_ran:
        st.error("The input was rejected before the FSM ran, so there is no output. See the Errors tab.")
        return
    stats = result.statistics
    if result.errors:
        st.warning(
            "The input contains lexical errors (see the Errors tab). The output below was "
            "produced with error recovery and may be incomplete or unreliable.",
            icon=":material/warning:",
        )
    show_code(result.cleaned_source)
    st.download_button(
        "Download cleaned source",
        data=result.cleaned_source.encode("utf-8"),
        file_name=cleaned_file_name(file_name),
        mime="text/plain",
        type="primary",
        icon=":material/download:",
    )

    st.markdown("##### Compare original and cleaned code")
    left, right = st.columns(2)
    with left:
        st.caption(f"Original: {stats.original_characters:,} characters, {stats.original_lines} lines")
        show_code(result.original_source)
    with right:
        st.caption(f"Cleaned: {stats.output_characters:,} characters, {stats.output_lines} lines")
        show_code(result.cleaned_source)

    with st.expander("Unified diff"):
        diff = "\n".join(
            difflib.unified_diff(
                result.original_source.splitlines(),
                result.cleaned_source.splitlines(),
                "original",
                "cleaned",
                lineterm="",
            )
        )
        st.code(diff or "(no differences)", language="diff")

    with st.expander("Intermediate result: FSM output before whitespace processing"):
        st.caption(
            "The text the FSM emitted: comments removed, each /* */ comment replaced by one "
            "space (as a C compiler does), all other whitespace untouched. The whitespace "
            "stage starts from this."
        )
        show_code(result.comment_free_source)

    if result.separators:
        st.markdown("##### Token boundaries protected")
        st.caption(
            "A removed comment was the only thing between these tokens, so one space was "
            "kept in its place."
        )
        st.dataframe(
            [
                {
                    "Comment at": f"line {sep.comment.start.line}, column {sep.comment.start.column}",
                    "Between": f"'{sep.left}' and '{sep.right}'",
                    "Reason": sep.reason,
                }
                for sep in result.separators
            ],
            hide_index=True,
        )


# --- FSM States ----------------------------------------------------------------


def render_states_tab(result: ProcessingResult) -> None:
    st.markdown(FORMAL_DEFINITION)
    visits = result.statistics.state_visits if result.statistics else {}

    st.markdown("##### States (Q)")
    st.dataframe(
        [
            {
                "State": state.value,
                "Reads": info.region.value,
                "Input may end here": "yes" if info.accepting else "no",
                "Characters consumed in this run": visits.get(state.value, 0),
                "Meaning": info.description,
            }
            for state, info in STATE_INFO.items()
        ],
        hide_index=True,
        column_config={"Meaning": st.column_config.TextColumn(width="large")},
    )

    st.markdown("##### Input classes")
    st.dataframe(
        [{"Class": c.value, "Symbol": c.symbol, "Characters": c.members} for c in CharClass],
        hide_index=True,
    )

    st.markdown("##### Transition table (δ and λ)")
    used = Counter((r.current_state, r.input_class) for r in result.transition_log)
    choice = st.selectbox(
        "Show transitions from",
        ["All states", *[state.value for state in State]],
        key="table_state",
    )
    rows = []
    for state in State:
        if choice != "All states" and state.value != choice:
            continue
        for input_class in CharClass:
            rows.append(_table_row(TRANSITION_TABLE[(state, input_class)], used))
        rows.append(_table_row(EOF_TABLE[state], used))
    st.dataframe(
        rows,
        hide_index=True,
        height=min(38 + 35 * len(rows), 560),
        column_config=_WIDE_COLUMNS,
    )
    note = "" if result.transition_log_complete else " (counted over the recorded part of the log)"
    st.caption(
        "Generated from TRANSITION_TABLE and EOF_TABLE in remover/transitions.py, the same "
        f"table the engine looks every step up in. *Used* counts this run{note}."
    )


_WIDE_COLUMNS = {
    "Current State": st.column_config.TextColumn(width="medium"),
    "Next State": st.column_config.TextColumn(width="medium"),
    "Output": st.column_config.TextColumn(width="medium"),
    "Event": st.column_config.TextColumn(width="medium"),
    "Action": st.column_config.TextColumn(width="large"),
}


def _table_row(row, used: Counter) -> dict[str, object]:
    return {
        "Current State": row.current_state.value,
        "Input": row.input_class.symbol if row.input_class else "end of input",
        "Next State": row.next_state.value,
        "Output": row.output.value,
        "Event": "" if row.event is Event.NONE else row.event.value,
        "Used": used.get((row.current_state, row.input_class), 0),
        "Action": row.action,
    }


# --- Transition Log ------------------------------------------------------------

_LOG_FILTERS = {
    "All transitions": lambda r: True,
    "State changes only": lambda r: r.changed_state,
    "Lexical events only": lambda r: r.event is not Event.NONE,
}


def render_log_tab(result: ProcessingResult) -> None:
    log = result.transition_log
    if not log:
        st.info("No transitions were recorded for this input.")
        return
    stats = result.statistics
    st.caption(
        f"{len(log):,} transitions recorded from the actual FSM run: one per input character "
        "plus the final end-of-input transition. Emitted, Discarded and Buffer show exactly "
        "what each step did with its character."
    )
    if not result.transition_log_complete:
        st.warning(
            f"The log was capped at {len(log):,} of {stats.fsm_transitions:,} transitions. "
            "The output and statistics still cover the whole input."
        )
    choice = st.radio("Show", list(_LOG_FILTERS), horizontal=True, key="log_filter")
    rows = [record_row(r) for r in log if _LOG_FILTERS[choice](r)]
    st.dataframe(rows, hide_index=True, height=480, column_config=_WIDE_COLUMNS)
    st.download_button(
        "Download transition log (CSV)",
        data=log_to_csv(log),
        file_name="transition_log.csv",
        mime="text/csv",
        icon=":material/table_view:",
    )


# --- Step-by-Step --------------------------------------------------------------


def _set_step(value: int) -> None:
    st.session_state.step = value


def _shift_step(delta: int, last: int) -> None:
    st.session_state.step = max(0, min(last, st.session_state.get("step", 0) + delta))


def _next_change(log: tuple[TransitionRecord, ...]) -> None:
    current = st.session_state.get("step", 0)
    for index in range(current + 1, len(log)):
        if log[index].changed_state:
            st.session_state.step = index
            return
    st.session_state.step = len(log) - 1


def render_step_tab(result: ProcessingResult) -> None:
    log = result.transition_log
    if not log:
        st.info("No transitions were recorded for this input.")
        return
    last = len(log) - 1
    st.session_state.step = max(0, min(st.session_state.get("step", 0), last))
    step = st.session_state.step

    buttons = st.columns(6)
    buttons[0].button("First", icon=":material/first_page:", on_click=_set_step, args=(0,),
                      disabled=step == 0, width="stretch")
    buttons[1].button("Previous", icon=":material/chevron_left:", on_click=_shift_step,
                      args=(-1, last), disabled=step == 0, width="stretch")
    buttons[2].button("Next", icon=":material/chevron_right:", on_click=_shift_step,
                      args=(1, last), disabled=step == last, type="primary", width="stretch")
    buttons[3].button("Last", icon=":material/last_page:", on_click=_set_step, args=(last,),
                      disabled=step == last, width="stretch")
    buttons[4].button("Next state change", icon=":material/fast_forward:", on_click=_next_change,
                      args=(log,), disabled=step == last, width="stretch")
    buttons[5].button("Reset", icon=":material/restart_alt:", on_click=_set_step, args=(0,),
                      width="stretch")
    if last > 0:
        st.slider("Transition", 0, last, key="step")

    record = log[st.session_state.step]
    columns = st.columns(4)
    columns[0].metric(
        "Step",
        f"{record.step} / {last}",
        help="Steps are numbered from 0; the last step is the end-of-input transition.",
    )
    columns[1].metric("Position", record.offset, help="0-based index of the character in the source.")
    columns[2].metric("Line : Column", f"{record.line} : {record.column}")
    columns[3].metric(
        "Input character",
        printable(record.character),
        help=record.input_class.members if record.input_class else "End of input: no character is consumed.",
    )

    with st.container(border=True):
        input_class = record.input_class.value if record.input_class else "END_OF_INPUT"
        st.markdown(
            f"**Current state:** `{record.current_state.value}` &nbsp;→&nbsp; "
            f"**Next state:** `{record.next_state.value}` &nbsp;&nbsp; "
            f"(input class `{input_class}`)"
        )
        st.markdown(f"**Action:** {md_text(record.action)}")
        details = [f"**Output:** {md_text(record.output.effect)}"]
        if record.emitted:
            details.append(f"Emitted {md_code(printable_text(record.emitted))}")
        if record.discarded:
            details.append(f"Discarded {md_code(printable_text(record.discarded))}")
        details.append(f"Buffer {md_code(printable_text(record.buffer) or 'empty')}")
        st.markdown(" &nbsp;·&nbsp; ".join(details))
        if record.event is not Event.NONE:
            st.markdown(f"**Lexical event:** `{record.event.value}`")
        if record.is_end_of_input:
            verdict = "accepted" if record.current_state in ACCEPTING_STATES else "rejected (lexical error)"
            st.markdown(f"**End of input:** the input is {verdict}.")

    left, right = st.columns(2, gap="medium")
    with left:
        st.markdown("##### Source")
        st.html(fragments.step_source(result, record))
        st.caption(
            "Boxed: the character this step consumes. Struck through: comment text already "
            "discarded. Amber: the '/' held in the buffer. Faded: not read yet."
        )
    with right:
        st.markdown("##### FSM output so far")
        emitted = result.comment_free_source[: record.output_length]
        if emitted:
            show_code(emitted)
        else:
            st.caption("Nothing has been emitted yet.")

    st.markdown("##### Machine")
    st.graphviz_chart(
        to_dot(active_state=record.next_state, active_edge=edge_for(_row_of(record))),
        width="stretch",
    )
    st.caption("Highlighted in amber: the transition just taken and the state it leads to.")

    st.markdown("##### Neighbouring transitions")
    first = max(0, st.session_state.step - 3)
    window = log[first : st.session_state.step + 4]
    st.dataframe(
        [{"": "▶" if r.step == record.step else "", **record_row(r)} for r in window],
        hide_index=True,
        column_config=_WIDE_COLUMNS,
    )


def _row_of(record: TransitionRecord):
    if record.input_class is None:
        return EOF_TABLE[record.current_state]
    return TRANSITION_TABLE[(record.current_state, record.input_class)]


# --- State Diagram -------------------------------------------------------------


def render_diagram_tab(result: ProcessingResult) -> None:
    visits = None
    if result.statistics is not None:
        visits = {State(name): count for name, count in result.statistics.state_visits.items()}
    st.graphviz_chart(to_dot(visits=visits), width="stretch")
    st.markdown(
        "- **Double circle**: an accepting state, where the input may end. Ending anywhere "
        "else is a lexical error (unterminated comment or literal).\n"
        "- **Edge label** `input ⇒ output`: *else* means every character not on another "
        "edge leaving that state; *hold* puts the '/' in the one-character buffer.\n"
        "- **Dashed red edge**: a lexical error transition (a line break inside a literal); "
        "the machine reports it and recovers in NORMAL.\n"
        "- **Number in brackets**: characters consumed in that state during this run.\n"
        "- **Colours**: blue code, yellow pending decision, grey comment, green string, "
        "teal character literal."
    )
    st.caption("Generated from the transition table at run time, so it always matches the code.")
    with st.expander("Diagram source (Graphviz DOT)"):
        st.code(to_dot(), language="dot")
    with st.expander("Mermaid version (used in the documentation)"):
        st.code(to_mermaid(), language="text")


# --- Statistics ----------------------------------------------------------------

_HEADLINE_METRICS = [
    "original_characters",
    "output_characters",
    "characters_removed",
    "comments_detected",
    "single_line_comments",
    "multi_line_comments",
    "whitespace_removed",
    "fsm_transitions",
]


def render_statistics_tab(result: ProcessingResult) -> None:
    stats = result.statistics
    if stats is None:
        st.info("No statistics: the FSM did not run.")
        return
    for start in range(0, len(_HEADLINE_METRICS), 4):
        columns = st.columns(4)
        for column, key in zip(columns, _HEADLINE_METRICS[start : start + 4]):
            label, definition = METRIC_DEFINITIONS[key]
            column.metric(label, f"{getattr(stats, key):,}", help=definition, border=True)

    st.markdown("##### Characters consumed in each state")
    values = [{"State": s.value, "Characters": stats.state_visits[s.value]} for s in State]
    chart = (
        alt.Chart(alt.Data(values=values))
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X("Characters:Q", title="Characters consumed"),
            y=alt.Y("State:N", sort=None, title=None, axis=alt.Axis(labelLimit=260)),
            tooltip=[alt.Tooltip("State:N"), alt.Tooltip("Characters:Q")],
        )
        .properties(height=300)
    )
    st.altair_chart(chart, width="stretch")
    st.caption(
        "Each character is consumed in exactly one state; the bars add up to "
        f"{stats.characters_scanned:,} characters scanned."
    )

    st.markdown("##### All metrics")
    st.dataframe(
        [
            {"Metric": label, "Value": getattr(stats, key), "Definition": definition}
            for key, (label, definition) in METRIC_DEFINITIONS.items()
        ],
        hide_index=True,
        column_config={"Definition": st.column_config.TextColumn(width="large")},
    )


# --- Errors --------------------------------------------------------------------


def render_errors_tab(result: ProcessingResult) -> None:
    if not result.errors and not result.warnings:
        state = result.final_state.value if result.final_state else "NORMAL"
        st.success(
            f"No errors or warnings. The FSM ended in the accepting state {state}, so the "
            "whole source was processed.",
            icon=":material/check_circle:",
        )
    for diagnostic in result.errors:
        _render_diagnostic(diagnostic, result.original_source, error=True)
    for diagnostic in result.warnings:
        _render_diagnostic(diagnostic, result.original_source, error=False)
    with st.expander("How errors are classified"):
        st.dataframe(
            [{"Category": name, "Meaning": meaning} for name, meaning in ERROR_CLASSES],
            hide_index=True,
            column_config={"Meaning": st.column_config.TextColumn(width="large")},
        )


def _render_diagnostic(diagnostic: Diagnostic, source: str, *, error: bool) -> None:
    with st.container(border=True):
        colour = "red" if error else "orange"
        kind = "Error" if error else "Warning"
        st.markdown(f":{colour}[**{kind}: {diagnostic.category.value}**] &nbsp; `{diagnostic.code.value}`")
        st.code(diagnostic.format(), language="text", wrap_lines=True)
        if diagnostic.line is not None and diagnostic.column is not None:
            st.code(excerpt(source, diagnostic.line, diagnostic.column), language="text")
