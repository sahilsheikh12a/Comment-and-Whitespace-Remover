"""Shared fixtures for the test suite."""

from __future__ import annotations

import pytest

from helpers import EXAMPLES_DIR


@pytest.fixture
def example_sources() -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(EXAMPLES_DIR.glob("*.c"))}
