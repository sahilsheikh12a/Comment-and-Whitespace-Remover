# Algorithms

This document gives the algorithms of the pipeline in pseudocode, with the
reasoning behind each step. The real implementations are in
[`remover/fsm.py`](../remover/fsm.py),
[`remover/comment_remover.py`](../remover/comment_remover.py),
[`remover/whitespace.py`](../remover/whitespace.py) and
[`remover/pipeline.py`](../remover/pipeline.py).

```text
Source ─▶ Input validation ─▶ FSM scan ─▶ Comment removal ─▶ Whitespace processing ─▶ Result
            pipeline.py         fsm.py     comment_remover.py    whitespace.py           pipeline.py
```

## 1. Input validation

```text
validate(source):
    if source is not a string            → Input Validation Error (NOT_TEXT)
    if length(source) > limit            → Input Validation Error (INPUT_TOO_LARGE)
    if source contains a NUL character   → Input Validation Error (NUL_CHARACTER, with line and column)
    warnings ← []
    if source is empty                   → warning EMPTY_INPUT
    if more than one kind of line ending → warning MIXED_LINE_ENDINGS
    return warnings
```

A rejected input is never scanned; the result carries the error and no output.
The source is not modified before scanning: no line endings are converted and
nothing is trimmed.

## 2. The FSM engine

```text
run(source):
    state ← NORMAL; buffer ← ""; output ← ""; line ← 1; column ← 1
    for each character c at offset i:
        t ← TABLE[state, class(c)]
        case t.output of
            EMIT:               output += c
            DISCARD:            (nothing)
            BUFFER:             buffer ← c
            FLUSH_AND_EMIT:     output += buffer + c;  buffer ← ""
            DISCARD_BUFFER:     buffer ← ""
            REPLACE_WITH_SPACE: output += " "
        assert (buffer ≠ "") = (t.next_state = POSSIBLE_COMMENT)
        yield record(i, line, column, c, state, t, ...)
        state ← t.next_state
        advance line and column past c
    t ← END_OF_INPUT[state]
    if t.output = FLUSH: output += buffer
    yield record(end of input, ...)
```

Each character costs one dictionary lookup and a constant amount of work, so
the scan is **O(n)** in time. Apart from the output and the optional log, the
memory used is constant.

## 3. Comment removal (lexeme collection)

The FSM decides what to copy and what to drop. `comment_remover.py` attaches
the bookkeeping a lexer attaches to its automaton, driven by the event of each
transition:

```text
for each record r produced by run(source):
    case:
        r.output = BUFFER:          remember the position of the held '/'
        r.event  = *_COMMENT_START: start a comment at the held '/' position
        r.output = DISCARD:         append r.character to the open comment;
                                    if it is '*' right after '/' inside a block
                                    comment, warn: comments do not nest
        r.event  = COMMENT_END:     close the comment; for '*/' the piece text is
                                    the replacement space, for '//' it is empty
                                    and the line break that ended it is code
        r.event  = *_START:         start a literal with r.character
        r.event  = *_END:           append r.character, close the literal
        r.event  = UNTERMINATED_*:  close the literal unterminated, report the
                                    error at its opening quote; the line break
                                    is code again (recovery)
        otherwise:                  append to the open literal, or to the code
at end of input:
    release a held '/', close a '//' comment, or report an unterminated
    comment or literal at the position where it started
```

The output of this stage is the FSM output split into **pieces** tagged as code,
string literal, character literal or removed comment. The concatenation of the
pieces equals the FSM output exactly, and the stage checks this.

## 4. Whitespace processing

### Why whitespace cannot simply be deleted

Whitespace separates tokens. Removing it blindly changes how the code is read:

| Source | Blind removal | What goes wrong |
|---|---|---|
| `int x = 10;` | `intx=10;` | `int` and `x` merge into the identifier `intx` |
| `a - -b` | `a--b` | `- -` becomes the decrement operator `--` |
| `x / *p` | `x/*p` | `/ *` becomes the start of a comment |
| `0xE + 1` | `0xE+1` | a single invalid number token (`E+1` is read as an exponent) |
| `#define F (x) x` | `#define F(x) x` | an object-like macro becomes a function-like macro |
| `"a    b"` | `"ab"` | the string's value changes |

### Atoms, lines and gaps

```text
atomize(pieces, newline_mode):
    for each piece:
        code piece      → SOLID runs of non-whitespace characters,
                          SPACE runs of ' ', '\t', '\v', '\f',
                          BREAK for each line break (LF, CR LF, CR)
        literal piece   → one SOLID atom (never split, never changed)
        removed comment → one COMMENT marker; with "preserve original
                          newlines", plus a BREAK (and another marker) for
                          every line break inside the comment
split the atoms into lines at BREAK atoms
```

On each line, a **gap** is the run of SPACE and COMMENT atoms between two
SOLID atoms. Every whitespace decision is made per gap, and only at gaps:
nothing inside a token or literal is ever touched.

### Rendering a line

```text
render(line, mode):
    if the line has no SOLID atom:
        it is COMMENT_ONLY if it contains a comment marker, otherwise BLANK
        content ← "" (Preserve mode keeps a BLANK line's spaces)
    else:
        leading:   Preserve  → all spaces before the first token
                   Normalize → the indentation (spaces before anything else)
                   Compact   → ""
        each gap between tokens L and R:
                   Preserve  → its spaces exactly; if it had only a comment,
                               " " when L and R would merge, else ""
                   Normalize → " " if it had spaces; if only a comment, as above
                   Compact   → " " if L and R would merge, else ""
                               (on preprocessor lines: as Normalize)
        trailing:  Preserve  → kept, unless a removed comment follows the code
                   otherwise → ""
```

### When would two tokens merge?

`separator_reason(left, right)` looks at the last character `a` of the left
token and the first character `b` of the right token:

```text
a and b are identifier/number characters           (int x, 10 L)          → keep a space
a b starts a comment                                (/ *, / /)             → keep a space
a b is inside a multi-character operator            (- -, + +, < <, & &,
                                                     - >, = =, digraphs)   → keep a space
a is a word character and b a quote, or vice versa  (L "x", "x" _s)        → keep a space
left ends with a number and b is '.'                (1 .5)                 → keep a space
left ends with a number ending in e/E/p/P, b is +/- (0xE + 1)              → keep a space
a is '.' and b is a digit                           (. 5)                  → keep a space
otherwise                                                                  → no space needed
```

Non-ASCII characters count as identifier characters, so whitespace next to
them is never removed. The rules are deliberately conservative: compact mode
may keep a space that is not strictly needed, but never removes one that is.

### Preprocessor lines and continuations

A line whose first token starts with `#`, and every line joined to it by a
trailing backslash, is a preprocessor line. In compact mode its gaps are only
normalized, because whitespace in a directive can change its meaning (the
`#define F (x)` case above).

A line ending in a backslash is joined to the next line by the C compiler. If
the next line were deleted (a comment-only line in *Preserve line structure*
mode), the backslash would join a different line. So a comment-only line that
follows a continuation is kept as an empty line instead of being removed.

### Selecting lines (newline modes)

```text
select(lines, newline_mode):
    Preserve original newlines: keep every line; COMMENT_ONLY lines are empty
        (the comment's own line breaks were turned into BREAK atoms, so every
         line keeps its original number)
    Preserve line structure: drop COMMENT_ONLY lines (unless they follow a
        continuation); keep CODE and BLANK lines; line breaks inside comments
        were removed with the comment, which joins the code around a
        multi-line comment exactly as the C compiler does
    Normalize blank lines: as Preserve line structure, then collapse each run
        of BLANK lines to one and drop BLANK lines at the start and end
output ← concatenation of (content + original line terminator) of the kept lines
```

Each kept line keeps its own original terminator, so LF, CR LF and CR files
come out with the same line endings they went in with.

### How comment removal and whitespace processing stay separate

The FSM never looks at whitespace: spaces and tabs are in the input class
*other*, and line breaks only matter for ending `//` comments and catching
broken literals. The whitespace stage never looks for comments: it receives
pieces that already say where comments were and which text is a literal. The
only information passed between them is that piece list, so each stage can be
tested and explained on its own.

## 5. Statistics

```text
original_characters        = len(source)
output_characters          = len(cleaned)
characters_removed         = original_characters − output_characters
comments_detected          = number of comments (single-line + multi-line)
comment_characters_removed = Σ len(comment text, delimiters included)
whitespace_removed         = whitespace characters of the code that are not
                             in the output (a run of N reduced to one space
                             counts N − 1)
separators_inserted        = spaces kept where only a comment separated two
                             tokens that would merge
fsm_transitions            = characters + 1 (end of input)
state_changes              = transitions whose next state differs
state_visits[q]            = characters consumed in state q
```

Every character of the source is either comment text, literal text, a code
character that is not whitespace, or code whitespace. The first group is
removed, the second and third are always kept, and part of the fourth is
removed. Hence the identity checked by the tests for every example and mode:

    output = original − comment characters − whitespace removed
             + separators inserted + comment line-break characters kept

The last term is non-zero only with *Preserve original newlines*, which keeps
the line breaks found inside comments.

## 6. Complexity

| Stage | Time | Extra memory |
|---|---|---|
| Validation | O(n) | O(1) |
| FSM scan and lexeme collection | O(n) | O(1) besides the output, the lexemes and the optional log |
| Whitespace processing | O(n) | O(n) for the atoms and lines |
| Statistics | O(n) | O(1) |

The whole pipeline is linear in the length of the input. The transition log is
the only part that grows with the input faster than the output, which is why
the interface caps it (50,000 records by default) while the statistics are
always counted over the whole input.
