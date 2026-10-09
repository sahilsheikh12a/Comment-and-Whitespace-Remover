"""The documentation: generated parts match the code, links resolve, sections exist."""

import importlib.util
import re

import pytest

from helpers import ROOT

_spec = importlib.util.spec_from_file_location("sync_docs", ROOT / "tools" / "sync_docs.py")
sync_docs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync_docs)

REQUIRED = [
    "README.md",
    "docs/architecture.md",
    "docs/fsm-design.md",
    "docs/state-transition-table.md",
    "docs/algorithms.md",
]


def test_required_documents_exist():
    for name in REQUIRED:
        assert (ROOT / name).is_file(), name


@pytest.mark.parametrize("path", sync_docs.DOCUMENTS, ids=lambda path: path.name)
def test_generated_blocks_match_the_code(path):
    text = path.read_text(encoding="utf-8")
    assert sync_docs.sync(text) == text, "out of date: run python tools/sync_docs.py"


def test_readme_has_every_required_section():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## (\d+)\. ", readme, flags=re.MULTILINE)
    assert headings == [str(n) for n in range(1, 24)]


@pytest.mark.parametrize("path", sync_docs.DOCUMENTS, ids=lambda path: path.name)
def test_relative_links_point_to_existing_files(path):
    text = path.read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)]+)\)", text):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        assert (path.parent / target.split("#")[0]).exists(), f"{path.name}: broken link {target}"
