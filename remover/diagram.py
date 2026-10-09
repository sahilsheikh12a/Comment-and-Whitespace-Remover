"""State diagrams and tables generated from the transition table.

Nothing here is drawn by hand. The Graphviz diagram (UI), the Mermaid
diagram (docs) and the Markdown tables are all built from
``TRANSITION_TABLE`` and ``EOF_TABLE``, so they always match the machine
that actually runs.
"""

from __future__ import annotations

from dataclasses import dataclass

from .states import ACCEPTING_STATES, INITIAL_STATE, STATE_INFO, Region, State
from .transitions import (
    EOF_TABLE,
    TRANSITION_TABLE,
    CharClass,
    Event,
    OutputAction,
    Transition,
)

# Short verbs for the output action, used on diagram edges ("input ⇒ output").
OUTPUT_VERBS = {
    OutputAction.EMIT: "emit",
    OutputAction.DISCARD: "skip",
    OutputAction.BUFFER: "hold",
    OutputAction.FLUSH_AND_EMIT: "emit held / + char",
    OutputAction.DISCARD_BUFFER: "skip both",
    OutputAction.REPLACE_WITH_SPACE: "emit space",
    OutputAction.FLUSH: "emit held /",
    OutputAction.NONE: "nothing",
}

_MERMAID_CLASS_NAMES = {
    CharClass.SLASH: "slash",
    CharClass.STAR: "star",
    CharClass.DOUBLE_QUOTE: "dquote",
    CharClass.SINGLE_QUOTE: "squote",
    CharClass.BACKSLASH: "backslash",
    CharClass.NEWLINE: "newline",
    CharClass.OTHER: "other",
}

_REGION_FILL = {
    Region.CODE: "#dbeafe",
    Region.PENDING: "#fef3c7",
    Region.COMMENT: "#e5e7eb",
    Region.STRING: "#dcfce7",
    Region.CHARACTER: "#ccfbf1",
}


@dataclass(frozen=True)
class Edge:
    """All transitions between two states that share an output and error status."""

    source: State
    target: State
    input_classes: tuple[CharClass, ...]
    output: OutputAction
    is_error: bool

    @property
    def is_else(self) -> bool:
        """True when this edge takes every character no other edge of its state takes."""
        return CharClass.OTHER in self.input_classes

    @property
    def is_any(self) -> bool:
        """True when this is the only edge of its state: it takes every character."""
        return len(self.input_classes) == len(CharClass)

    def input_label(self) -> str:
        if self.is_any:
            return "any"
        if self.is_else:
            return "else"
        return " ".join(_dot_symbol(c) for c in self.input_classes)

    def label(self) -> str:
        text = f"{self.input_label()} ⇒ {OUTPUT_VERBS[self.output]}"
        return text + " (error)" if self.is_error else text


def _dot_symbol(input_class: CharClass) -> str:
    return "newline" if input_class is CharClass.NEWLINE else input_class.symbol


def edges() -> list[Edge]:
    """Group the transition table into diagram edges.

    Within each state the specific edges come first, in input-class order,
    and the catch-all ("else") edge comes last.
    """
    groups: dict[tuple[State, State, OutputAction, bool], list[CharClass]] = {}
    for state in State:
        for input_class in CharClass:
            row = TRANSITION_TABLE[(state, input_class)]
            key = (state, row.next_state, row.output, row.event.is_error)
            groups.setdefault(key, []).append(input_class)
    result = [
        Edge(source, target, tuple(classes), output, is_error)
        for (source, target, output, is_error), classes in groups.items()
    ]
    states = list(State)
    classes = list(CharClass)
    result.sort(
        key=lambda e: (states.index(e.source), e.is_else, classes.index(e.input_classes[0]))
    )
    return result


def edge_for(row: Transition) -> Edge | None:
    """The diagram edge that contains a transition (``None`` for end of input)."""
    if row.input_class is None:
        return None
    for edge in edges():
        if edge.source is row.current_state and row.input_class in edge.input_classes:
            return edge
    return None


def to_dot(
    *,
    active_state: State | None = None,
    active_edge: Edge | None = None,
    visits: dict[State, int] | None = None,
) -> str:
    """Graphviz DOT source for the state diagram.

    ``active_state``/``active_edge`` highlight one step of a run;
    ``visits`` adds per-state character counts from a run.
    """
    lines = [
        "digraph FSM {",
        '  graph [rankdir=LR, bgcolor="#ffffff", pad=0.3, nodesep=0.5, ranksep=0.7, '
        'fontname="Helvetica"];',
        '  node [shape=circle, style=filled, fontname="Helvetica", fontsize=10, '
        'color="#334155", fontcolor="#0f172a", penwidth=1.2, width=1.3, fixedsize=true];',
        '  edge [fontname="Helvetica", fontsize=9, color="#64748b", fontcolor="#334155", '
        "arrowsize=0.7];",
        '  start [shape=point, width=0.12, color="#0f172a", label=""];',
        f"  start -> {INITIAL_STATE.value};",
    ]
    for state in State:
        info = STATE_INFO[state]
        label = _wrap(state.value)
        if visits is not None:
            label += f"\\n({visits.get(state, 0)})"
        attributes = [
            f'label="{label}"',
            f'fillcolor="{_REGION_FILL[info.region]}"',
            f'tooltip="{_dot_escape(info.summary)}"',
        ]
        if state in ACCEPTING_STATES:
            attributes.append("shape=doublecircle")
            attributes.append("width=1.15")
        if state is active_state:
            attributes += ['color="#d97706"', "penwidth=3.5"]
        lines.append(f"  {state.value} [{', '.join(attributes)}];")
    for edge in edges():
        label = _dot_escape(edge.label())
        attributes = [f'label="{label}"']
        if edge.is_error:
            attributes += ['style=dashed', 'color="#dc2626"', 'fontcolor="#b91c1c"']
        if edge == active_edge:
            attributes += ['color="#d97706"', 'fontcolor="#b45309"', "penwidth=3"]
        lines.append(f"  {edge.source.value} -> {edge.target.value} [{', '.join(attributes)}];")
    lines.append("}")
    return "\n".join(lines)


def _wrap(name: str) -> str:
    """Break a long state name at the underscore nearest its middle."""
    if len(name) <= 10:
        return name
    cuts = [i for i, ch in enumerate(name) if ch == "_"]
    cut = min(cuts, key=lambda i: max(i, len(name) - i - 1))
    return name[:cut] + "\\n" + name[cut + 1 :]


def _dot_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def to_mermaid() -> str:
    """Mermaid ``stateDiagram-v2`` source (rendered by GitHub in Markdown)."""
    lines = ["stateDiagram-v2", "    direction LR", f"    [*] --> {INITIAL_STATE.value}"]
    for edge in edges():
        if edge.is_any:
            label = "any"
        elif edge.is_else:
            label = "other"
        else:
            label = ", ".join(_MERMAID_CLASS_NAMES[c] for c in edge.input_classes)
        if edge.is_error:
            label += " (error)"
        lines.append(f"    {edge.source.value} --> {edge.target.value}: {label}")
    for state in State:
        if state in ACCEPTING_STATES:
            lines.append(f"    {state.value} --> [*]: end of input")
    return "\n".join(lines)


def _md_input(input_class: CharClass | None) -> str:
    if input_class is None:
        return "end of input"
    if input_class in (CharClass.NEWLINE, CharClass.OTHER):
        return input_class.symbol
    return f"`{input_class.symbol}`"


def _md_event(event: Event) -> str:
    return "" if event is Event.NONE else f"`{event.value}`"


def transition_table_markdown() -> str:
    """Every transition, one row per (state, input class), then end of input."""
    rows = [
        "| Current State | Input | Next State | Output | Event | Action |",
        "|---|---|---|---|---|---|",
    ]
    for state in State:
        for input_class in CharClass:
            row = TRANSITION_TABLE[(state, input_class)]
            rows.append(_md_row(row))
        rows.append(_md_row(EOF_TABLE[state]))
    return "\n".join(rows)


def _md_row(row: Transition) -> str:
    action = row.action.replace("|", "\\|")
    return (
        f"| {row.current_state.value} | {_md_input(row.input_class)} | {row.next_state.value} "
        f"| `{row.output.value}` | {_md_event(row.event)} | {action} |"
    )


def eof_table_markdown() -> str:
    """What the machine does when the input ends in each state."""
    rows = [
        "| State at end of input | Accepted | Final state | Output | Event | Meaning |",
        "|---|---|---|---|---|---|",
    ]
    for state in State:
        row = EOF_TABLE[state]
        rows.append(
            f"| {state.value} | {'yes' if state in ACCEPTING_STATES else 'no'} "
            f"| {row.next_state.value} | `{row.output.value}` | {_md_event(row.event)} | {row.action} |"
        )
    return "\n".join(rows)


def compact_table_markdown() -> str:
    """The table with each state's 'other' characters merged into one row."""
    rows = ["| Current State | Input | Next State | Output |", "|---|---|---|---|"]
    for edge in edges():
        if edge.is_any:
            inputs = "any character"
        elif edge.is_else:
            inputs = "any other"
        else:
            inputs = ", ".join(_md_input(c) for c in edge.input_classes)
        if edge.is_error:
            inputs += " (lexical error)"
        rows.append(
            f"| {edge.source.value} | {inputs} | {edge.target.value} | {OUTPUT_VERBS[edge.output]} |"
        )
    return "\n".join(rows)


def states_markdown() -> str:
    rows = ["| State | Reads | Input may end here | Meaning |", "|---|---|---|---|"]
    for state, info in STATE_INFO.items():
        rows.append(
            f"| {state.value} | {info.region.value} | {'yes' if info.accepting else 'no'} "
            f"| {info.description} |"
        )
    return "\n".join(rows)


def input_classes_markdown() -> str:
    rows = ["| Input class | Characters |", "|---|---|"]
    for input_class in CharClass:
        rows.append(f"| {_md_input(input_class)} | {input_class.members} |")
    return "\n".join(rows)
