"""Helper functions shared by the tests."""

from __future__ import annotations

from pathlib import Path

from remover import CommentFSM, TransitionRecord, process

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = ROOT / "examples"


def run_fsm(source: str) -> list[TransitionRecord]:
    """Run the bare FSM and return every record, end of input included."""
    return list(CommentFSM().run(source))


def clean(source: str, **settings: object) -> str:
    """Cleaned output of the full pipeline."""
    return process(source, **settings).cleaned_source
