"""Command-line interface: ``python -m remover [FILE]``.

Prints the cleaned source (or, with ``--trace``, the FSM transition log)
to standard output and diagnostics to standard error. The exit status is
1 when an error was reported.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .display import excerpt, format_log
from .errors import InputValidationError
from .models import METRIC_DEFINITIONS, NewlineMode, WhitespaceMode
from .pipeline import decode_source, process


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m remover",
        description="Remove comments and unnecessary whitespace from C-like source code using an FSM.",
    )
    parser.add_argument("file", nargs="?", help="source file to process (default: standard input)")
    parser.add_argument(
        "-w", "--whitespace", choices=[m.value for m in WhitespaceMode], default="normalize",
        help="whitespace mode (default: normalize)",
    )
    parser.add_argument(
        "-n", "--newlines", choices=[m.value for m in NewlineMode], default="structure",
        help="newline mode (default: structure)",
    )
    parser.add_argument("-o", "--output", help="write the cleaned source to this file")
    parser.add_argument("--trace", action="store_true", help="print the FSM transition log instead")
    parser.add_argument("--stats", action="store_true", help="print statistics to standard error")
    args = parser.parse_args(argv)

    try:
        data = Path(args.file).read_bytes() if args.file else sys.stdin.buffer.read()
        source = decode_source(data)
    except OSError as exc:
        print(f"error: cannot read {args.file}: {exc.strerror}", file=sys.stderr)
        return 1
    except InputValidationError as exc:
        print(exc.diagnostic.format(), file=sys.stderr)
        return 1

    result = process(
        source,
        whitespace_mode=args.whitespace,
        newline_mode=args.newlines,
        record_transitions=args.trace,
        max_recorded_transitions=len(source) + 1,
        max_input_characters=max(len(source), 1),
    )
    for diagnostic in (*result.errors, *result.warnings):
        print(diagnostic.format(), file=sys.stderr)
        if diagnostic.line is not None and diagnostic.column is not None:
            print("\n" + excerpt(source, diagnostic.line, diagnostic.column), file=sys.stderr)
        print(file=sys.stderr)

    if args.trace:
        print(format_log(result.transition_log))
    elif args.output:
        Path(args.output).write_text(result.cleaned_source, encoding="utf-8", newline="")
    else:
        sys.stdout.write(result.cleaned_source)

    if args.stats and result.statistics is not None:
        for key, (label, _) in METRIC_DEFINITIONS.items():
            print(f"{label + ':':<28} {getattr(result.statistics, key)}", file=sys.stderr)
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
