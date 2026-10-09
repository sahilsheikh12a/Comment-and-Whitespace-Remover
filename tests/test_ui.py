"""The Streamlit interface: HTML fragments and the running app (no browser needed)."""

import pytest

from helpers import ROOT
from remover import process
from ui import html as fragments

streamlit_testing = pytest.importorskip("streamlit.testing.v1")


# --- HTML fragments -----------------------------------------------------------


def test_lexeme_classes_mark_comments_and_literals():
    result = process("x = 'a'; // c\ny = \"s\";")
    classes = fragments.lexeme_classes(
        result.original_source, result.detected_comments, result.detected_literals
    )
    assert classes[4:7] == ["character"] * 3
    assert classes[9:13] == ["comment"] * 4
    assert classes[18:21] == ["string"] * 3
    assert classes[0] is None


def test_highlighted_source_escapes_html_and_keeps_line_breaks():
    result = process("#include <stdio.h> // <b>bold</b>\nint x;")
    fragment = fragments.highlighted_source(result)
    assert fragment.startswith("<pre")
    assert "&lt;stdio.h&gt;" in fragment
    assert "<b>" not in fragment
    assert "line-through" in fragment  # the comment is struck through
    assert "\nint x;" in fragment


def test_step_source_boxes_the_current_character_and_marks_the_buffer():
    result = process("a/b; // c\r\nd;")
    second_slash = result.transition_log[6]  # the second '/' of '//'
    fragment = fragments.step_source(result, second_slash)
    current = fragments.STYLES["current"]
    buffered = fragments.STYLES["buffered"]
    assert f'<span style="{current}">/</span>' in fragment
    assert f'<span style="{buffered}">/</span>' in fragment
    assert "\r" not in fragment  # line terminators are never written raw


def test_step_source_shows_the_end_of_input_marker():
    result = process("x;\n")
    fragment = fragments.step_source(result, result.transition_log[-1])
    assert "end of input" in fragment


def test_pipeline_reports_rejected_input():
    fragment = fragments.pipeline(process("bad\x00input"))
    assert "rejected" in fragment
    assert "not run" in fragment


def test_pipeline_uses_the_numbers_of_the_run():
    result = process("int a; // c\n")
    fragment = fragments.pipeline(result)
    assert f"{result.statistics.fsm_transitions:,} transitions" in fragment
    assert "1 comment(s)" in fragment


# --- the app ------------------------------------------------------------------


def app():
    test = streamlit_testing.AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    test.run()
    return test


def button(test, label):
    return next(b for b in test.button if b.label == label)


def displayed(test, text):
    """True if a code block shows ``text`` (st.code drops one final line break)."""
    expected = text[:-1] if text.endswith("\n") else text
    return any(code.value == expected for code in test.code)


def test_app_starts_with_instructions_and_no_errors():
    test = app()
    assert not test.exception
    assert "Process Source" in test.info[0].value


def test_processing_the_starter_code_shows_every_tab():
    test = app()
    button(test, "Process Source").click().run()
    assert not test.exception
    assert [tab.label for tab in test.tabs] == [
        "Source Code",
        "Cleaned Output",
        "FSM States",
        "Transition Log",
        "Step-by-Step",
        "State Diagram",
        "Statistics",
        "Errors",
    ]
    assert displayed(test, process(test.text_area(key="source").value).cleaned_source)


@pytest.mark.parametrize(
    "example",
    [
        "basic.c",
        "single_line_comments.c",
        "multi_line_comments.c",
        "strings_and_characters.c",
        "whitespace.c",
        "edge_cases.c",
        "complete_program.c",
        "errors.c",
        "literal_errors.c",
    ],
)
def test_every_example_loads_and_processes(example):
    test = app()
    test.selectbox(key="example").select(example).run()
    button(test, "Load Example").click().run()
    assert not test.exception
    source = (ROOT / "examples" / example).read_text(encoding="utf-8")
    assert test.text_area(key="source").value == source
    assert displayed(test, process(source).cleaned_source)


def test_changing_the_mode_updates_the_output():
    test = app()
    test.selectbox(key="example").select("whitespace.c").run()
    button(test, "Load Example").click().run()
    test.radio(key="whitespace_mode").set_value("compact").run()
    assert not test.exception
    assert displayed(test, "int a=10;\nint b=20;\nint sum=a+b;\n")


def test_step_by_step_navigation():
    test = app()
    button(test, "Process Source").click().run()
    for _ in range(3):
        button(test, "Next").click().run()
    assert test.session_state["step"] == 3
    button(test, "Previous").click().run()
    assert test.session_state["step"] == 2
    button(test, "Next state change").click().run()
    log = process(test.text_area(key="source").value).transition_log
    assert log[test.session_state["step"]].changed_state
    button(test, "Last").click().run()
    assert test.session_state["step"] == len(log) - 1
    button(test, "Reset").click().run()
    assert test.session_state["step"] == 0
    assert not test.exception


def test_leading_blank_lines_of_the_output_are_displayed():
    test = app()
    test.text_area(key="source").set_value("// header\nint x;\n").run()
    test.radio(key="newline_mode").set_value("preserve").run()
    button(test, "Process Source").click().run()
    assert displayed(test, "\nint x;\n")  # int x; stays on line 2


def test_clear_empties_the_editor_and_hides_results():
    test = app()
    button(test, "Process Source").click().run()
    button(test, "Clear").click().run()
    assert test.text_area(key="source").value == ""
    assert not test.tabs
    button(test, "Process Source").click().run()  # empty input is processed too
    assert not test.exception
