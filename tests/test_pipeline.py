"""The processing pipeline end to end."""

import subprocess
import sys

import pytest

from helpers import ROOT, run_fsm
from remover import (
    CharClass,
    Code,
    CommentFSM,
    ErrorCategory,
    InputValidationError,
    LexicalError,
    NewlineMode,
    ProcessingError,
    ProcessingOptions,
    State,
    WhitespaceMode,
    process,
)
from remover.text import line_breaks
from remover.transitions import TRANSITION_TABLE

SOURCE = "int a = 10; // first\nint b = 20; /* second */\nint sum = a + b;\n"


def test_specification_workflow():
    result = process(SOURCE, whitespace_mode="normalize")
    assert result.cleaned_source == "int a = 10;\nint b = 20;\nint sum = a + b;\n"
    assert [c.text for c in result.detected_comments] == ["// first", "/* second */"]
    assert "first" not in result.cleaned_source and "second" not in result.cleaned_source
    assert len(result.transition_log) == len(SOURCE) + 1
    assert result.transition_log_complete
    assert result.errors == () and result.warnings == ()
    assert result.success and result.output_complete and result.accepted
    assert result.final_state is State.NORMAL

    stats = result.statistics
    assert stats.original_characters == len(SOURCE)
    assert stats.output_characters == len(result.cleaned_source)
    assert stats.characters_removed == len(SOURCE) - len(result.cleaned_source)
    assert (stats.comments_detected, stats.single_line_comments, stats.multi_line_comments) == (2, 1, 1)
    assert stats.comment_characters_removed == len("// first") + len("/* second */")
    assert stats.whitespace_removed == 2  # the spaces before the two comments
    assert stats.fsm_transitions == len(SOURCE) + 1
    assert stats.characters_scanned == len(SOURCE)
    assert (stats.original_lines, stats.output_lines) == (3, 3)
    assert stats.errors == stats.warnings == 0


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("preserve", "int a = 10;\nint b = 20;\nint sum = a + b;\n"),
        ("normalize", "int a = 10;\nint b = 20;\nint sum = a + b;\n"),
        ("compact", "int a=10;\nint b=20;\nint sum=a+b;\n"),
    ],
)
def test_whitespace_modes(mode, expected):
    assert process(SOURCE, whitespace_mode=mode).cleaned_source == expected


def test_modes_accept_enums_and_case_insensitive_strings():
    assert process("a  b", whitespace_mode=WhitespaceMode.COMPACT).cleaned_source == "a b"
    assert process("a  b", whitespace_mode="Compact").cleaned_source == "a b"


def test_unknown_mode_is_a_value_error():
    with pytest.raises(ValueError, match="whitespace_mode"):
        process("x", whitespace_mode="tiny")
    with pytest.raises(ValueError, match="newline_mode"):
        ProcessingOptions(newline_mode="none")


def test_options_object_with_keyword_override():
    options = ProcessingOptions(whitespace_mode="compact")
    result = process("int  x = 1;\n\n\n", options, newline_mode="collapse")
    assert result.options.whitespace_mode is WhitespaceMode.COMPACT
    assert result.options.newline_mode is NewlineMode.COLLAPSE
    assert result.cleaned_source == "int x=1;\n"


def test_comment_free_source_is_the_fsm_output():
    source = "a = b; /* c */ // d\n"
    result = process(source)
    assert result.comment_free_source == "a = b;   \n"
    assert result.comment_free_source == "".join(r.emitted for r in run_fsm(source))
    assert result.cleaned_source == "a = b;\n"


def test_transition_log_is_the_actual_fsm_execution():
    source = 'x = "/*"; // y\nz = a / b;'
    assert list(process(source).transition_log) == run_fsm(source)


def test_capped_log_warns_but_statistics_cover_everything():
    result = process("a = 1; // c\n", max_recorded_transitions=4)
    assert len(result.transition_log) == 4
    assert not result.transition_log_complete
    assert [w.code for w in result.warnings] == [Code.TRANSITION_LOG_CAPPED]
    assert result.statistics.fsm_transitions == 13


def test_recording_can_be_disabled():
    result = process("a // b", record_transitions=False)
    assert result.transition_log == ()
    assert result.warnings == ()
    assert result.statistics.fsm_transitions == 7


def test_errors_and_warnings_are_kept_apart():
    result = process("/* a /* b */ x = 'y;")
    assert [e.code for e in result.errors] == [Code.UNTERMINATED_CHARACTER]
    assert [w.code for w in result.warnings] == [Code.NESTED_COMMENT]
    assert result.warnings[0].format().startswith("Lexical Structure Error (warning):")


def test_raise_for_errors():
    process("ok;").raise_for_errors()
    with pytest.raises(LexicalError):
        process("/* open").raise_for_errors()
    with pytest.raises(InputValidationError):
        process(b"x").raise_for_errors()  # type: ignore[arg-type]


def test_an_incomplete_transition_table_is_refused():
    broken = dict(TRANSITION_TABLE)
    del broken[(State.STRING_LITERAL, CharClass.NEWLINE)]
    with pytest.raises(ProcessingError) as caught:
        CommentFSM(table=broken)
    assert caught.value.diagnostic.category is ErrorCategory.PROCESSING


def test_internal_faults_are_reported_instead_of_raised(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("remover.pipeline.process_whitespace", broken)
    result = process("int x;")
    (error,) = result.errors
    assert error.category is ErrorCategory.PROCESSING
    assert error.code is Code.INTERNAL_ERROR
    assert "boom" in error.message
    assert result.cleaned_source == ""


EXTRA_SOURCES = [
    SOURCE,
    "int/**/value = 1; a = b-/**/-c;\n",
    "x;\r\n/* a\r\n b */ y; // z\r\n\r\n\r\n",
    "  \t lead;   \n\n\n/* only */\n// lines\n\ttrail;  ",
    'char *s = "a  //  b"; char c = \'/\'; /* x\n\n y */ int  q ;',
    "#define F (x) \\\n  /* c */ x\nint y = F (1);\n",
]


@pytest.mark.parametrize("whitespace", list(WhitespaceMode))
@pytest.mark.parametrize("newlines", list(NewlineMode))
def test_statistics_are_consistent(example_sources, whitespace, newlines):
    for source in [*example_sources.values(), *EXTRA_SOURCES]:
        result = process(source, whitespace_mode=whitespace, newline_mode=newlines)
        stats = result.statistics
        comment_breaks = [b for c in result.detected_comments for b in line_breaks(c.text)]
        kept_break_chars = sum(map(len, comment_breaks)) if newlines is NewlineMode.PRESERVE else 0
        assert stats.output_characters == (
            stats.original_characters
            - stats.comment_characters_removed
            - stats.whitespace_removed
            + stats.separators_inserted
            + kept_break_chars
        ), source
        assert stats.characters_removed == stats.original_characters - stats.output_characters
        assert stats.comment_line_breaks_kept == (
            len(comment_breaks) if newlines is NewlineMode.PRESERVE else 0
        )
        assert sum(stats.state_visits.values()) == stats.characters_scanned == len(source)


def test_processing_is_deterministic():
    assert process(SOURCE) == process(SOURCE)


def test_engine_works_without_streamlit():
    code = "import sys, remover; remover.process('x // y'); print('streamlit' in sys.modules)"
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True
    )
    assert completed.stdout.strip() == "False"
