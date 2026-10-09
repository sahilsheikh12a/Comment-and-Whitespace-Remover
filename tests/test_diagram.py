"""The state diagram and tables are generated from the transition table."""

import shutil
import subprocess

import pytest

from remover import EOF_TABLE, TRANSITION_TABLE, CharClass, State
from remover.diagram import (
    compact_table_markdown,
    edge_for,
    edges,
    states_markdown,
    to_dot,
    to_mermaid,
    transition_table_markdown,
)
from remover.states import ACCEPTING_STATES


def test_edges_cover_every_transition_exactly_once():
    seen = {}
    for edge in edges():
        for input_class in edge.input_classes:
            key = (edge.source, input_class)
            assert key not in seen
            seen[key] = edge
            row = TRANSITION_TABLE[key]
            assert row.next_state is edge.target
            assert row.output is edge.output
            assert row.event.is_error is edge.is_error
    assert set(seen) == set(TRANSITION_TABLE)


def test_edge_for_finds_the_edge_of_a_transition():
    row = TRANSITION_TABLE[(State.STRING_LITERAL, CharClass.NEWLINE)]
    edge = edge_for(row)
    assert edge.is_error and edge.target is State.NORMAL
    assert edge_for(EOF_TABLE[State.NORMAL]) is None


def test_dot_has_every_state_and_edge():
    dot = to_dot()
    for state in State:
        assert f"  {state.value} [" in dot
    assert dot.count(" -> ") == len(edges()) + 1  # plus the start arrow
    assert dot.count("doublecircle") == len(ACCEPTING_STATES)


def test_dot_highlights_the_active_transition_and_counts_visits():
    edge = edge_for(TRANSITION_TABLE[(State.NORMAL, CharClass.SLASH)])
    dot = to_dot(active_state=State.POSSIBLE_COMMENT, active_edge=edge, visits={State.NORMAL: 7})
    assert 'NORMAL -> POSSIBLE_COMMENT [label="/ ⇒ hold", color="#d97706"' in dot
    assert 'label="NORMAL\\n(7)"' in dot


@pytest.mark.skipif(shutil.which("dot") is None, reason="Graphviz is not installed")
def test_dot_is_valid_graphviz():
    completed = subprocess.run(["dot", "-Tsvg"], input=to_dot(), capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_mermaid_lists_every_edge_and_accepting_state():
    text = to_mermaid()
    assert text.startswith("stateDiagram-v2")
    assert text.count(" --> ") == 1 + len(edges()) + len(ACCEPTING_STATES)
    assert '"' not in text  # quotes would break the Mermaid parser


def test_markdown_tables():
    full = transition_table_markdown().splitlines()
    assert len(full) == 2 + len(TRANSITION_TABLE) + len(EOF_TABLE)
    assert "| NORMAL | `/` | POSSIBLE_COMMENT | `BUFFER` |" in transition_table_markdown()
    compact = compact_table_markdown().splitlines()
    assert len(compact) == 2 + len(edges())
    assert len(states_markdown().splitlines()) == 2 + len(State)
