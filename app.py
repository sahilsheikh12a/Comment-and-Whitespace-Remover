"""Comment and Whitespace Remover Using FSM: the Streamlit interface.

Run with:

    streamlit run app.py

This file only lays out the page and keeps the session state. All
processing is done by the remover package (remover.process); every
output, table and number shown comes from the actual FSM run on the
current source.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from remover import (
    InputValidationError,
    NewlineMode,
    ProcessingOptions,
    ProcessingResult,
    WhitespaceMode,
    decode_source,
    process,
)
from ui import html as fragments
from ui import views

EXAMPLES_DIR = Path(__file__).resolve().parent / "examples"
MAX_RECORDED_TRANSITIONS = 50_000

EXAMPLES = {
    "basic.c": "no comments",
    "single_line_comments.c": "// comments",
    "multi_line_comments.c": "/* */ over several lines",
    "strings_and_characters.c": "markers inside literals",
    "whitespace.c": "irregular spacing",
    "edge_cases.c": "division, inline comment, escaped quote",
    "complete_program.c": "full program, every feature",
    "errors.c": "unterminated comment",
    "literal_errors.c": "unterminated literals",
}

STARTER_SOURCE = """int a = 10; // variable a
int b = 20;
/* Calculate the sum */
int sum = a + b;
"""

PAGE_STYLE = """
<style>
.stTextArea textarea {
    font-family: "Source Code Pro", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.875rem;
    line-height: 1.5;
}
</style>
"""

IMPLEMENTATION_MAP = """
| Question | File |
|---|---|
| Where are the states defined? | `remover/states.py` |
| Where is the transition logic? | `remover/transitions.py` |
| Where is the FSM implemented? | `remover/fsm.py` |
| Where is comment removal? | `remover/comment_remover.py` |
| Where is whitespace processing? | `remover/whitespace.py` |
| Where is the pipeline? | `remover/pipeline.py` |
| How are literals protected? | `STRING_LITERAL` / `CHARACTER_LITERAL` rows in `transitions.py`, tests in `tests/test_strings.py` |
"""


def available_examples() -> list[str]:
    on_disk = {path.name for path in EXAMPLES_DIR.glob("*.c")}
    ordered = [name for name in EXAMPLES if name in on_disk]
    return ordered + sorted(on_disk - set(ordered))


def init_state(examples: list[str]) -> None:
    defaults = {
        "source": STARTER_SOURCE,
        "file_name": "source.c",
        "processed": False,
        "upload_error": None,
        "example": examples[0] if examples else None,
        "whitespace_mode": WhitespaceMode.NORMALIZE.value,
        "newline_mode": NewlineMode.STRUCTURE.value,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


# --- callbacks (run before the next script run) --------------------------------


def on_process() -> None:
    st.session_state.processed = True


def on_clear() -> None:
    st.session_state.source = ""
    st.session_state.file_name = "source.c"
    st.session_state.processed = False
    st.session_state.upload_error = None


def on_load_example() -> None:
    name = st.session_state.example
    if not name:
        return
    st.session_state.source = (EXAMPLES_DIR / name).read_text(encoding="utf-8")
    st.session_state.file_name = name
    st.session_state.processed = True
    st.session_state.upload_error = None


def on_upload() -> None:
    uploaded = st.session_state.get("upload")
    if uploaded is None:
        return
    try:
        st.session_state.source = decode_source(uploaded.getvalue())
    except InputValidationError as exc:
        st.session_state.upload_error = exc.diagnostic
        return
    st.session_state.file_name = uploaded.name
    st.session_state.upload_error = None
    st.session_state.processed = True


# --- page sections ---------------------------------------------------------------


def render_about() -> None:
    with st.expander("About this tool, supported syntax and where things are implemented"):
        left, right = st.columns(2, gap="large")
        with left:
            st.markdown(
                "Comments are recognised by an explicit **finite state machine** that reads "
                "the source one character at a time. Whitespace is processed afterwards by a "
                "separate stage that knows where every literal and removed comment was."
            )
            st.markdown(
                "**Supported syntax**\n"
                "- `//` single-line comments\n"
                "- `/* */` multi-line comments (they do not nest, as in C)\n"
                "- `\"...\"` string and `'...'` character literals with backslash escapes\n"
                "- LF, CR LF and CR line endings\n\n"
                "C is the reference language. C++, Java, C# and JavaScript code that uses "
                "the same comment and literal rules is handled too; see the README for the "
                "documented limitations."
            )
        with right:
            st.markdown(IMPLEMENTATION_MAP)


def render_input(examples: list[str]) -> None:
    editor, settings = st.columns([3, 2], gap="large")
    with editor:
        st.text_area(
            "Enter source code",
            key="source",
            height=300,
            placeholder="Paste C, C++, Java or JavaScript source code here…",
        )
        buttons = st.columns(3)
        buttons[0].button(
            "Process Source", type="primary", icon=":material/play_arrow:",
            on_click=on_process, width="stretch",
        )
        buttons[1].button("Clear", icon=":material/delete:", on_click=on_clear, width="stretch")
        with buttons[2].popover("Upload file", icon=":material/upload_file:", width="stretch"):
            st.file_uploader(
                "Source file (UTF-8 text)",
                type=["c", "h", "cpp", "hpp", "cc", "java", "js", "cs", "txt"],
                key="upload",
                on_change=on_upload,
            )
        if st.session_state.upload_error is not None:
            st.error(st.session_state.upload_error.format())

    with settings:
        whitespace = st.radio(
            "Whitespace mode",
            [mode.value for mode in WhitespaceMode],
            format_func=lambda value: WhitespaceMode(value).label,
            key="whitespace_mode",
            horizontal=True,
        )
        st.caption(WhitespaceMode(whitespace).description)
        newlines = st.radio(
            "Newline handling",
            [mode.value for mode in NewlineMode],
            format_func=lambda value: NewlineMode(value).label,
            key="newline_mode",
        )
        st.caption(NewlineMode(newlines).description)
        st.selectbox(
            "Example programs",
            examples,
            format_func=lambda name: f"{name} — {EXAMPLES.get(name, 'example')}",
            key="example",
        )
        st.button(
            "Load Example", icon=":material/description:", on_click=on_load_example,
            disabled=not examples, width="stretch",
        )


def current_result() -> ProcessingResult:
    """Process the current source with the current options (cached per input)."""
    source = st.session_state.source
    options = ProcessingOptions(
        whitespace_mode=st.session_state.whitespace_mode,
        newline_mode=st.session_state.newline_mode,
        max_recorded_transitions=MAX_RECORDED_TRANSITIONS,
    )
    key = (source, options)
    if st.session_state.get("result_key") != key:
        if st.session_state.get("result_source") != source:
                st.session_state.result = process(source, options)
        st.session_state.result_key = key
    return st.session_state.result


def render_results(result: ProcessingResult) -> None:
    st.markdown("#### Processing pipeline")
    st.html(fragments.pipeline(result))
    if result.errors:
        st.error(
            f"{len(result.errors)} error(s) reported. The output may be incomplete; "
            "see the Errors tab for locations and recovery.",
            icon=":material/error:",
        )
    tabs = st.tabs(
        [
            "Source Code",
            "Cleaned Output",
            "FSM States",
            "Transition Log",
            "State Diagram",
            "Statistics",
            "Errors",
        ],
        key="results_tab",
    )
    with tabs[0]:
        views.render_source_tab(result)
    with tabs[1]:
        views.render_output_tab(result, st.session_state.file_name)
    with tabs[2]:
        views.render_states_tab(result)
    with tabs[3]:
        views.render_log_tab(result)
    with tabs[4]:
        views.render_diagram_tab(result)
    with tabs[5]:
        views.render_statistics_tab(result)
    with tabs[6]:
        views.render_errors_tab(result)


def main() -> None:
    # No custom page icon: Material page icons are fetched from Google at run
    # time, and the app must work offline.
    st.set_page_config(page_title="Comment & Whitespace Remover (FSM)", layout="wide")
    examples = available_examples()
    init_state(examples)
    st.title("Comment and Whitespace Remover Using FSM")
    st.caption(
        "Compiler Construction Laboratory mini project. A finite state machine scans the "
        "source one character at a time and removes comments; whitespace is then processed "
        "according to the selected mode."
    )
    st.html(PAGE_STYLE)
    render_about()
    render_input(examples)
    st.divider()
    if not st.session_state.processed:
        st.info("Enter source code or load an example, then click **Process Source**.")
        return
    render_results(current_result())


main()
