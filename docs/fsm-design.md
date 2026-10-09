# FSM design

This document explains the finite state machine at the centre of the project:
what it is, why lexical analysis uses one, and how each state and transition of
this machine was chosen. All tables and the trace below are generated from the
code (`tools/sync_docs.py`).

## 1. Finite state machines

A **deterministic finite automaton** (DFA) is a 5-tuple

    M = (Q, Σ, δ, q₀, F)

- **Q**: a finite set of states;
- **Σ**: the input alphabet;
- **δ : Q × Σ → Q**: the transition function, which gives exactly one next
  state for every state and input symbol (that is what *deterministic* means);
- **q₀ ∈ Q**: the start state;
- **F ⊆ Q**: the accepting states.

The automaton reads its input one symbol at a time. Its only memory is the
current state, a finite amount of information however long the input is. The
input is accepted if the machine is in an accepting state when it ends.

A **finite-state transducer** of the Mealy kind adds an output alphabet Γ and
an output function **λ : Q × Σ → Γ\***: every transition also writes a
(possibly empty) string. A comment remover is naturally a transducer: for every
character it must decide where to go next and what to write.

## 2. Why FSMs are used in lexical analysis

The first phase of a compiler, the lexical analyser (scanner), groups
characters into tokens and discards comments and whitespace. The languages of
tokens, such as identifiers, numbers, string literals and comments, are
**regular**, and every regular language is recognised by a DFA. This gives the
scanner three useful properties:

- **one pass**: each character is examined once, left to right;
- **linear time**: O(n) for n characters, one table lookup per character;
- **constant memory**: the state is the only thing remembered.

Tools such as lex and flex build these automata from regular expressions. This
project writes the automaton by hand, so each state and transition can be named,
shown and tested.

C comments are a good example of why the automaton is the clearer
description. The regular expression for a C block comment,
`/\*([^*]|\*+[^*/])*\*+/`, is famously easy to get wrong, while the
two-state loop `MULTI_LINE_COMMENT ⇄ POSSIBLE_COMMENT_END` below says the same
thing directly.

Comments that **nest** would not be regular: matching nested `/* /* */ */`
needs a counter of unbounded size, just like balanced parentheses, and no
finite automaton can count without limit. C comments do not nest, which is
exactly why a finite machine is enough; the first `*/` always ends the comment.

## 3. This machine

The comment remover is the transducer M = (Q, Σ, Γ, δ, λ, q₀, F) where

- Q is the set of nine states below;
- Σ is the set of all characters. δ and λ only need to tell seven **input
  classes** apart, so the table has 9 × 7 = 63 entries;
- Γ is the set of output characters;
- δ and λ are given together by `TRANSITION_TABLE` in `remover/transitions.py`;
- q₀ = `NORMAL`;
- F = {`NORMAL`, `POSSIBLE_COMMENT`, `SINGLE_LINE_COMMENT`}, the states in
  which the input may end.

### Input classes

<!-- BEGIN GENERATED: input-classes -->
| Input class | Characters |
|---|---|
| `/` | the slash '/' |
| `*` | the asterisk '*' |
| `"` | the double quote '"' |
| `'` | the single quote "'" |
| `\` | the backslash '\' |
| newline | a line-feed '\n' or carriage-return '\r' character |
| other | any other character (letters, digits, spaces, tabs, operators, Unicode) |
<!-- END GENERATED: input-classes -->

Spaces and tabs are in the class *other*: the comment remover treats them
like any ordinary character. Whitespace is the business of the second stage
(see [algorithms.md](algorithms.md)).

### States

<!-- BEGIN GENERATED: states -->
| State | Reads | Input may end here | Meaning |
|---|---|---|---|
| NORMAL | code | yes | The start state. Characters are copied to the output. '/' may start a comment, '"' starts a string literal and "'" starts a character literal. |
| POSSIBLE_COMMENT | pending decision | yes | A '/' was read in code. It is held in a one-character buffer because only the next character can tell whether it starts '//' or '/*' or is just a division operator. |
| SINGLE_LINE_COMMENT | comment | yes | Every character is discarded until a line break, which ends the comment and is itself kept as code. The end of input also ends the comment. |
| MULTI_LINE_COMMENT | comment | no | Every character, including line breaks, is discarded. A '*' moves to POSSIBLE_COMMENT_END because it may start the closing '*/'. |
| POSSIBLE_COMMENT_END | comment | no | Inside a multi-line comment, right after a '*'. A '/' closes the comment, another '*' keeps the possibility open and any other character returns to MULTI_LINE_COMMENT. |
| STRING_LITERAL | string literal | no | Characters are copied unchanged, so '//' and '/*' here are text, not comments. Only an unescaped '"' ends the string. A raw line break is a lexical error. |
| STRING_ESCAPE | string literal | no | The previous character was a backslash, so this character is escaped: it is copied and can never end the string. |
| CHARACTER_LITERAL | character literal | no | Characters are copied unchanged until an unescaped "'". A raw line break is a lexical error. |
| CHARACTER_ESCAPE | character literal | no | The previous character was a backslash, so this character is escaped: it is copied and can never end the literal. |
<!-- END GENERATED: states -->

Why each state exists:

| State | Needed because |
|---|---|
| `NORMAL` | the default: ordinary code is copied. |
| `POSSIBLE_COMMENT` | a `/` might start `//` or `/*`, or might be division; only the next character tells. |
| `SINGLE_LINE_COMMENT` | everything up to the line break is discarded, including `/*` and `"`. |
| `MULTI_LINE_COMMENT` | everything up to `*/` is discarded, including line breaks, `//` and `"`. |
| `POSSIBLE_COMMENT_END` | a `*` inside a comment might start `*/`; only the next character tells. |
| `STRING_LITERAL`, `CHARACTER_LITERAL` | inside a literal, comment markers are text and must not be acted on. |
| `STRING_ESCAPE`, `CHARACTER_ESCAPE` | after a backslash the next character must be copied without its usual meaning, so `\"` and `\'` cannot end the literal. |

## 4. The current state decides what a character means

The same input class leads to completely different behaviour depending on the
state. For the slash:

| State | Meaning of `/` | Transition |
|---|---|---|
| `NORMAL` | may start a comment | hold it, go to `POSSIBLE_COMMENT` |
| `POSSIBLE_COMMENT` | completes `//` | discard both, go to `SINGLE_LINE_COMMENT` |
| `SINGLE_LINE_COMMENT`, `MULTI_LINE_COMMENT` | comment text | discard |
| `POSSIBLE_COMMENT_END` | completes `*/` | discard, write one space, go to `NORMAL` |
| `STRING_LITERAL`, `CHARACTER_LITERAL` | literal text | copy |
| `STRING_ESCAPE`, `CHARACTER_ESCAPE` | an escaped character | copy, return to the literal |

and for the line break:

| State | Meaning of a line break |
|---|---|
| `NORMAL` | code: copied |
| `POSSIBLE_COMMENT` | the held `/` was an operator: both are written |
| `SINGLE_LINE_COMMENT` | ends the comment; the line break itself is code and is kept |
| `MULTI_LINE_COMMENT`, `POSSIBLE_COMMENT_END` | comment text: discarded (the line counter still advances) |
| `STRING_LITERAL`, `CHARACTER_LITERAL` | a lexical error: C literals cannot contain a raw line break |
| `STRING_ESCAPE`, `CHARACTER_ESCAPE` | an escaped line break (line continuation inside the literal) |

## 5. Recognising comment delimiters

Both comment openers are two characters long, but the machine reads one
character per step and never looks ahead. The decision is therefore spread over
two steps: the first `/` moves the machine to `POSSIBLE_COMMENT`, and the next
character decides.

**A slash cannot automatically be treated as a comment.** In C, `/` is also the
division operator (`a / b`), the first half of `/=`, and an ordinary character
inside literals (`"https://..."`, `'/'`). If the machine dropped a `/` as soon
as it saw one, `a / b` would lose its operator. So the `/` is *held* in a
one-character buffer:

- next character `/` → `//`: the held `/` and this one are discarded;
- next character `*` → `/*`: both are discarded;
- anything else → the `/` was an operator: the held `/` is written, followed by
  the current character, which is processed as `NORMAL` would (a `"` after the
  `/` therefore starts a string literal at once).

Ending a block comment is the mirror image. A `*` inside a comment moves to
`POSSIBLE_COMMENT_END`. There, `/` closes the comment, another `*` keeps the
possibility open (so `**/` and `/***/` close correctly), and anything else goes
back to `MULTI_LINE_COMMENT`.

C99 introduced `//` comments. Because the machine sees `//` before anything
else, `a //* c */ b` is `a` followed by a line comment, as in C99 and later
(C89, which had no `//`, would read it as `a / b`).

## 6. Why literals need their own states

Without literal states the machine would see `//` in `"https://example.com"`
and delete the rest of the line. The literal states make the machine *remember
that it is inside a literal*: in `STRING_LITERAL` the only characters with a
special meaning are `"` (end of the string), `\` (escape) and a raw line break
(error). Every other character, including `/` and `*`, is copied. Character
literals work the same way with `'`. Because `"` inside a character literal
and `'` inside a string are ordinary characters there, `'"'` and `"it's"` are
handled correctly.

## 7. Escape sequences

A backslash inside a literal changes the meaning of the next character. This is
modelled with an explicit state rather than a flag: `\` moves from
`STRING_LITERAL` to `STRING_ESCAPE`, and *any* character in `STRING_ESCAPE` is
copied and returns to `STRING_LITERAL`. Consequently:

- `"a\"b"`: the `"` after `\` is read in `STRING_ESCAPE` and cannot end the
  string;
- `"a\\"`: the second `\` is the escaped character, so the machine is back in
  `STRING_LITERAL` when the final `"` arrives, and the string ends there.

The escape states only decide where a literal ends. They do not interpret the
escape (`\n`, `\x41`, ...); the text is copied unchanged.

## 8. Output function and the buffer

Each transition has one output action:

| Output | Effect |
|---|---|
| `EMIT` | write the current character |
| `DISCARD` | drop the current character |
| `BUFFER` | hold the current character (always a `/`) |
| `FLUSH_AND_EMIT` | write the held `/`, then the current character |
| `DISCARD_BUFFER` | drop the held `/` and the current character (a comment opener) |
| `REPLACE_WITH_SPACE` | drop the current character (the `/` of `*/`) and write one space |
| `FLUSH` | end of input only: write the held `/` |
| `NONE` | end of input only: write nothing |

The buffer looks like extra memory, but it holds a `/` exactly when the machine
is in `POSSIBLE_COMMENT` and is empty otherwise. Its content is therefore
determined by the state, and the machine is still finite. `validate_table()`
rejects any table that could break this rule, and the engine checks it again on
every step.

A closed block comment is replaced by **one space**, as in C (ISO C11
§5.1.1.2, translation phase 3). Without it, `int/**/value` would become
`intvalue`. The whitespace stage later keeps or drops that space depending on
whether the neighbouring tokens need it.

## 9. End of input and acceptance

End of input is handled as a final pseudo-transition on a virtual end marker.
It consumes no character, so it is never counted as one:

<!-- BEGIN GENERATED: eof-table -->
| State at end of input | Accepted | Final state | Output | Event | Meaning |
|---|---|---|---|---|---|
| NORMAL | yes | NORMAL | `NONE` |  | End of input in NORMAL: the source is lexically complete |
| POSSIBLE_COMMENT | yes | NORMAL | `FLUSH` |  | End of input right after '/': the held '/' is code; emit it |
| SINGLE_LINE_COMMENT | yes | NORMAL | `NONE` | `COMMENT_END` | End of input also ends a single-line comment |
| MULTI_LINE_COMMENT | no | MULTI_LINE_COMMENT | `NONE` | `UNTERMINATED_COMMENT` | Lexical error: end of input inside a multi-line comment (no closing '*/') |
| POSSIBLE_COMMENT_END | no | POSSIBLE_COMMENT_END | `NONE` | `UNTERMINATED_COMMENT` | Lexical error: end of input inside a multi-line comment (no closing '*/') |
| STRING_LITERAL | no | STRING_LITERAL | `NONE` | `UNTERMINATED_STRING` | Lexical error: end of input inside a string literal (no closing '"') |
| STRING_ESCAPE | no | STRING_ESCAPE | `NONE` | `UNTERMINATED_STRING` | Lexical error: end of input inside a string literal (no closing '"') |
| CHARACTER_LITERAL | no | CHARACTER_LITERAL | `NONE` | `UNTERMINATED_CHARACTER` | Lexical error: end of input inside a character literal (no closing "'") |
| CHARACTER_ESCAPE | no | CHARACTER_ESCAPE | `NONE` | `UNTERMINATED_CHARACTER` | Lexical error: end of input inside a character literal (no closing "'") |
<!-- END GENERATED: eof-table -->

A `//` comment may end at the end of the input, and a trailing `/` is simply an
operator. Ending anywhere else means a comment or literal was never closed, a
lexical error reported at the position where that comment or literal started.

## 10. Error recovery

Errors inside the input are handled with **panic-mode recovery**, as real
compilers do. A raw line break inside a string or character literal is an error
(C does not allow it), so the transition `STRING_LITERAL --newline--> NORMAL`
reports the error at the opening quote, ends the literal at the line break and
resumes scanning in `NORMAL`. One missing quote therefore does not swallow the
rest of the file, and the comments on the following lines are still found:

```c
char* greeting = "Hello;
int total = 0; // this comment is still removed
```

Here the error is reported at the opening quote on line 1 (column 18), the
literal ends with line 1, and line 2 is scanned normally.

An unterminated multi-line comment cannot be recovered from: everything to the
end of the input is comment text. The error is reported where the `/*` is, and
the output contains the code before it.

## 11. Determinism, completeness and lookahead

- **Deterministic:** the table is a dictionary keyed by (state, input class),
  so there is exactly one transition for every pair.
- **Complete:** `validate_table()` checks that all 63 pairs and all nine
  end-of-input rules are defined before the engine starts; the engine cannot
  reach an undefined transition.
- **No lookahead:** each transition consumes exactly one character. Every
  source character appears in exactly one transition record, and no character
  is reported twice. Decisions that need more context are made by moving to an
  intermediate state.

Line and column numbers are tracked alongside. A CR LF pair is one line break;
because the engine does not look ahead, a CR is only known to be a line break
on its own when the next character is not LF.

## 12. A traced example

The real transitions for `a/b/*c*/"/"` (division, a block comment and a string
containing a slash):

<!-- BEGIN GENERATED: trace -->
| Step | Char | Current State | Next State | Output | Emitted | Discarded | Buffer |
|---|---|---|---|---|---|---|---|
| 0 | `a` | NORMAL | NORMAL | `EMIT` | `a` |  |  |
| 1 | `/` | NORMAL | POSSIBLE_COMMENT | `BUFFER` |  |  | `/` |
| 2 | `b` | POSSIBLE_COMMENT | NORMAL | `FLUSH_AND_EMIT` | `/b` |  |  |
| 3 | `/` | NORMAL | POSSIBLE_COMMENT | `BUFFER` |  |  | `/` |
| 4 | `*` | POSSIBLE_COMMENT | MULTI_LINE_COMMENT | `DISCARD_BUFFER` |  | `/*` |  |
| 5 | `c` | MULTI_LINE_COMMENT | MULTI_LINE_COMMENT | `DISCARD` |  | `c` |  |
| 6 | `*` | MULTI_LINE_COMMENT | POSSIBLE_COMMENT_END | `DISCARD` |  | `*` |  |
| 7 | `/` | POSSIBLE_COMMENT_END | NORMAL | `REPLACE_WITH_SPACE` | `␣` | `/` |  |
| 8 | `"` | NORMAL | STRING_LITERAL | `EMIT` | `"` |  |  |
| 9 | `/` | STRING_LITERAL | STRING_LITERAL | `EMIT` | `/` |  |  |
| 10 | `"` | STRING_LITERAL | NORMAL | `EMIT` | `"` |  |  |
| 11 | end of input | NORMAL | NORMAL | `NONE` |  |  |  |

FSM output: `a/b "/"`
<!-- END GENERATED: trace -->

Step 1 holds the `/`; step 2 shows it was division. Step 4 shows the next `/`
was the start of a comment. Steps 6 and 7 recognise `*/`, and step 7 writes one
space in place of the comment. Steps 8 to 10 copy a string whose `/` is text.
