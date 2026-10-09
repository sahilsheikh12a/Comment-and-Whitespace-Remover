# Architecture

This document describes how the project is put together: the layers, the
modules and their responsibilities, the data that flows between them and the
design decisions behind them.

## Layers

```text
 ┌──────────────────────────────────────────────────────────────┐
 │  Presentation            app.py, ui/html.py, ui/views.py      │  Streamlit
 │                          remover/__main__.py (CLI)            │
 ├──────────────────────────────────────────────────────────────┤
 │  Pipeline                remover/pipeline.py                  │
 ├───────────────────────────┬──────────────────────────────────┤
 │  Comment removal          │  Whitespace processing            │
 │  remover/comment_remover  │  remover/whitespace.py            │
 ├───────────────────────────┘                                   │
 │  FSM engine              remover/fsm.py                       │
 │  FSM definition          remover/states.py, transitions.py    │
 ├──────────────────────────────────────────────────────────────┤
 │  Shared                  models.py, errors.py, text.py        │
 │  Generated views         diagram.py, display.py               │
 └──────────────────────────────────────────────────────────────┘
```

The engine (`remover/`) never imports Streamlit. Everything it does can be
used from Python, from the command line or from the tests, and
`tests/test_pipeline.py` checks that processing a source does not load
Streamlit at all. The interface only lays out what the engine returns.

## Modules

| Module | Responsibility |
|---|---|
| `remover/states.py` | The nine states, the region of text each one reads (code, comment, literal...), and which states accept the end of input. |
| `remover/transitions.py` | Input classes, output actions, lexical events, and the transition table `TRANSITION_TABLE` plus the end-of-input table `EOF_TABLE`. `validate_table()` checks completeness and the buffer invariant. This is the only place the machine's behaviour is defined. |
| `remover/fsm.py` | `CommentFSM`: the engine. Classifies each character, looks the transition up, applies the output action, changes state, tracks line and column, and returns a `TransitionRecord`. |
| `remover/comment_remover.py` | Runs the engine over a source and turns the records into lexemes: `Comment` and `Literal` records, tagged output `Piece`s and diagnostics. |
| `remover/whitespace.py` | Lays the comment-free pieces out according to the whitespace and newline modes, keeping tokens apart. |
| `remover/pipeline.py` | `process()`: validation, comment removal, whitespace processing, statistics; converts every failure into a diagnostic. |
| `remover/models.py` | Dataclasses passed between the stages and to the UI, the mode enums and the statistic definitions. |
| `remover/errors.py` | Error categories, diagnostic codes, `Diagnostic` and the exception classes. |
| `remover/text.py` | The C definition of whitespace and line breaks, line counting. |
| `remover/diagram.py` | Graphviz and Mermaid diagrams and Markdown tables generated from the transition table. |
| `remover/display.py` | Visible forms of characters, table rows of transition records, CSV, source excerpts. |
| `remover/__main__.py` | The command-line interface. |
| `app.py` | The Streamlit page: inputs, session state, caching of the current result, tabs. |
| `ui/html.py` | HTML fragments (highlighted source, step view, pipeline banner) as pure, testable functions. |
| `ui/views.py` | One rendering function per results tab. |
| `tools/sync_docs.py` | Regenerates the generated parts of the documentation. |

Dependencies point downwards only: `fsm` depends on `transitions` and `states`;
`comment_remover` on `fsm`; `pipeline` on `comment_remover` and `whitespace`;
the UI on `pipeline`. `whitespace` never sees the FSM, only its output.

## Data flow

```text
source text
   │  validate_source()                    pipeline.py
   ▼
CommentFSM.run(source)                     fsm.py
   │  one TransitionRecord per character + one for the end of input
   ▼
_LexemeCollector.observe(record)           comment_remover.py
   │  Comment, Literal, Piece, Diagnostic
   ▼
CommentRemovalResult
   │  .output   FSM output (comments removed, whitespace untouched)
   │  .pieces   that output split into code / literal / removed-comment pieces
   ▼
process_whitespace(pieces, modes)          whitespace.py
   │  atoms → lines → gaps → rendered lines → selected lines
   ▼
WhitespaceResult
   │
   ▼
compute_statistics(), ProcessingResult     pipeline.py
   │
   ▼
UI tabs / CLI output
```

### Key data structures (`models.py`)

| Structure | Contents |
|---|---|
| `TransitionRecord` | step, offset, line, column, character, input class, current state, next state, output action, lexical event, text emitted, text discarded, buffer after the step, output length after the step, and the explanation from the table. Immutable. |
| `Comment` | kind (single-line or multi-line), full text with delimiters, start and end positions, whether it was terminated. |
| `Literal` | kind (string or character), text, start and end positions, whether it was terminated. |
| `Piece` | a segment of the FSM output tagged as code, string literal, character literal or removed comment, with its source offset. Concatenating all pieces gives the FSM output exactly. |
| `ProcessingOptions` | whitespace mode, newline mode, whether and how many transitions to record, maximum input size. |
| `Statistics` | every number shown in the Statistics tab (see the README for definitions). |
| `ProcessingResult` | the original and cleaned source, the FSM output, the options, the transition log, comments, literals, separator insertions, statistics, errors, warnings, final state and acceptance. |
| `Diagnostic` | category, severity, code, message, line, column, offset and recovery note; `format()` gives the report shown to users. |

## Design decisions

**Table-driven machine.** The behaviour lives in data (`TRANSITION_TABLE`),
not in nested `if` statements. The same table drives the engine, is displayed
in the UI and is turned into the state diagram and the documentation tables, so
these can never disagree with the code. The engine accepts any complete table,
which is also the extension point for other languages.

**One character per transition.** The engine never looks ahead. Decisions that
need the next character are made by intermediate states (`POSSIBLE_COMMENT`,
`POSSIBLE_COMMENT_END`) instead. As a result every character appears in
exactly one transition record, and the log describes what really happened
without reporting any character twice.

**Records are produced by the engine itself.** The UI does not re-simulate the
machine to draw the step-by-step view: it reads the records that the engine
returned while producing the output. The pipeline test
`test_transition_log_is_the_actual_fsm_execution` compares the stored log with
a fresh run.

**Two stages.** Comment removal and whitespace processing are separate.
Comments are removed first, exactly like a C compiler, which replaces each
comment by one space in translation phase 3. The whitespace stage then works on
pieces that already say which text is a literal and where comments were, so it
does not need its own scanner and cannot be confused by `//` inside a string.

**Errors are values.** Lexical errors are recorded as diagnostics while the
scanner recovers and continues; validation and internal faults are caught by
the pipeline and returned as diagnostics too. Nothing in normal use raises, so
the interface cannot crash on malformed input. `ProcessingResult.raise_for_errors()`
is available for callers who prefer exceptions.

**Immutable results and caching.** All records and results are frozen
dataclasses. The interface keeps the result for the current (source, options)
pair in the session and only reprocesses when one of them changes, so moving
through the step-by-step view does not rerun the machine.

**Offline by construction.** The engine uses only the standard library. The
interface uses Streamlit's bundled assets and Graphviz renderer;
`.streamlit/config.toml` turns off usage statistics and the first-run e-mail
prompt, and the page loads no external resources.

## Testing architecture

The tests mirror the layers: the table and the engine are tested directly
(`test_transitions.py`, `test_fsm.py`), the lexeme collection through
`remove_comments` (`test_comment_remover.py`), the whitespace stage through
`process_whitespace` (`test_whitespace.py`), and the behaviour a user sees
through `process` (the remaining files). `test_ui.py` drives the real Streamlit
script with `streamlit.testing.v1.AppTest`, and `test_docs.py` fails if the
generated documentation no longer matches the code.
