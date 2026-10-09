"""Regenerate the generated blocks in README.md and docs/*.md.

Tables, the Mermaid state diagram, the example trace and the example
outputs in the documentation are not written by hand. Each lives between
markers such as

    <!-- BEGIN GENERATED: transition-table -->
    ...
    <!-- END GENERATED: transition-table -->

and is rebuilt from the code by this script, so the documentation always
describes the machine that actually runs:

    python tools/sync_docs.py          # rewrite the generated blocks
    python tools/sync_docs.py --check  # exit 1 if any block is out of date
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from remover import METRIC_DEFINITIONS, process  # noqa: E402
from remover.diagram import (  # noqa: E402
    compact_table_markdown,
    eof_table_markdown,
    input_classes_markdown,
    states_markdown,
    to_mermaid,
    transition_table_markdown,
)
from remover.display import printable, printable_text  # noqa: E402

DOCUMENTS = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
TRACE_SOURCE = 'a/b/*c*/"/"'
BEGIN = "<!-- BEGIN GENERATED: "
END = "<!-- END GENERATED: "


def _trace_table() -> str:
    result = process(TRACE_SOURCE)
    rows = [
        "| Step | Char | Current State | Next State | Output | Emitted | Discarded | Buffer |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for record in result.transition_log:
        cells = [
            str(record.step),
            f"`{printable(record.character)}`" if record.character is not None else "end of input",
            record.current_state.value,
            record.next_state.value,
            f"`{record.output.value}`",
            f"`{printable_text(record.emitted)}`" if record.emitted else "",
            f"`{printable_text(record.discarded)}`" if record.discarded else "",
            f"`{record.buffer}`" if record.buffer else "",
        ]
        rows.append("| " + " | ".join(cells) + " |")
    rows.append("")
    rows.append(f"FSM output: `{result.comment_free_source}`")
    return "\n".join(rows)


def _metrics_table() -> str:
    rows = ["| Statistic | Definition |", "|---|---|"]
    rows += [f"| {label} | {definition} |" for label, definition in METRIC_DEFINITIONS.values()]
    return "\n".join(rows)


def _example(spec: str) -> str:
    """``example:<file>[:<whitespace>[:<newlines>]]`` -> the cleaned output."""
    name, *modes = spec.split(":")[1:]
    whitespace = modes[0] if modes else "normalize"
    newlines = modes[1] if len(modes) > 1 else "structure"
    source = (ROOT / "examples" / name).read_text(encoding="utf-8")
    cleaned = process(source, whitespace_mode=whitespace, newline_mode=newlines).cleaned_source
    return f"```c\n{cleaned}```" if cleaned.endswith("\n") else f"```c\n{cleaned}\n```"


def render(name: str) -> str:
    """The content of the generated block called ``name``."""
    builders = {
        "input-classes": input_classes_markdown,
        "states": states_markdown,
        "compact-table": compact_table_markdown,
        "transition-table": transition_table_markdown,
        "eof-table": eof_table_markdown,
        "mermaid": lambda: f"```mermaid\n{to_mermaid()}\n```",
        "trace": _trace_table,
        "metrics": _metrics_table,
    }
    if name.startswith("example:"):
        return _example(name)
    if name not in builders:
        raise KeyError(f"unknown generated block {name!r}")
    return builders[name]()


def sync(text: str) -> str:
    """Return ``text`` with every generated block rebuilt."""
    out: list[str] = []
    position = 0
    while (start := text.find(BEGIN, position)) != -1:
        name_end = text.index(" -->", start)
        name = text[start + len(BEGIN) : name_end]
        end_marker = f"{END}{name} -->"
        end = text.index(end_marker, name_end)
        out.append(text[position : name_end + len(" -->")])
        out.append("\n" + render(name) + "\n")
        out.append(end_marker)
        position = end + len(end_marker)
    out.append(text[position:])
    return "".join(out)


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for path in DOCUMENTS:
        text = path.read_text(encoding="utf-8")
        updated = sync(text)
        if updated != text:
            stale.append(path.relative_to(ROOT))
            if not check:
                path.write_text(updated, encoding="utf-8")
    if stale:
        verb = "out of date" if check else "updated"
        print(f"{verb}: " + ", ".join(str(p) for p in stale))
    return 1 if check and stale else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
