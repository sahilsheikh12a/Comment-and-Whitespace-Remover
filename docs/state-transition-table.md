# State-transition table

The complete transition function of the FSM, generated from
`TRANSITION_TABLE` and `EOF_TABLE` in
[`remover/transitions.py`](../remover/transitions.py) by
`tools/sync_docs.py`. The tests fail if this file and the code disagree.

## How to read it

- **Input** is an input class. *other* means any character not in another
  class, including letters, digits, spaces and tabs (see the class list below).
- **Output** is the action of the output function λ:

  | Output | Effect |
  |---|---|
  | `EMIT` | write the current character |
  | `DISCARD` | drop the current character |
  | `BUFFER` | hold the current `/` until the next character decides |
  | `FLUSH_AND_EMIT` | write the held `/`, then the current character |
  | `DISCARD_BUFFER` | drop the held `/` and the current character |
  | `REPLACE_WITH_SPACE` | drop the current character and write one space in place of the closed comment |
  | `FLUSH` | (end of input) write the held `/` |
  | `NONE` | (end of input) write nothing |

- **Event** names the lexical event the transition signals. The comment
  remover uses it to open and close comment and literal lexemes and to report
  errors.
- Every transition consumes exactly one character; there is no lookahead. The
  only conditions are the current state and the input class: no transition
  depends on a counter, a flag or a later character.
- The *end of input* row of each state is applied once, after the last
  character. It consumes nothing.

## Input classes

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

## Compact view

The rows below merge, for each state, the input classes that lead to the same
next state with the same output.

<!-- BEGIN GENERATED: compact-table -->
| Current State | Input | Next State | Output |
|---|---|---|---|
| NORMAL | `/` | POSSIBLE_COMMENT | hold |
| NORMAL | `"` | STRING_LITERAL | emit |
| NORMAL | `'` | CHARACTER_LITERAL | emit |
| NORMAL | any other | NORMAL | emit |
| POSSIBLE_COMMENT | `/` | SINGLE_LINE_COMMENT | skip both |
| POSSIBLE_COMMENT | `*` | MULTI_LINE_COMMENT | skip both |
| POSSIBLE_COMMENT | `"` | STRING_LITERAL | emit held / + char |
| POSSIBLE_COMMENT | `'` | CHARACTER_LITERAL | emit held / + char |
| POSSIBLE_COMMENT | any other | NORMAL | emit held / + char |
| SINGLE_LINE_COMMENT | newline | NORMAL | emit |
| SINGLE_LINE_COMMENT | any other | SINGLE_LINE_COMMENT | skip |
| MULTI_LINE_COMMENT | `*` | POSSIBLE_COMMENT_END | skip |
| MULTI_LINE_COMMENT | any other | MULTI_LINE_COMMENT | skip |
| POSSIBLE_COMMENT_END | `/` | NORMAL | emit space |
| POSSIBLE_COMMENT_END | `*` | POSSIBLE_COMMENT_END | skip |
| POSSIBLE_COMMENT_END | any other | MULTI_LINE_COMMENT | skip |
| STRING_LITERAL | `"` | NORMAL | emit |
| STRING_LITERAL | `\` | STRING_ESCAPE | emit |
| STRING_LITERAL | newline (lexical error) | NORMAL | emit |
| STRING_LITERAL | any other | STRING_LITERAL | emit |
| STRING_ESCAPE | any character | STRING_LITERAL | emit |
| CHARACTER_LITERAL | `'` | NORMAL | emit |
| CHARACTER_LITERAL | `\` | CHARACTER_ESCAPE | emit |
| CHARACTER_LITERAL | newline (lexical error) | NORMAL | emit |
| CHARACTER_LITERAL | any other | CHARACTER_LITERAL | emit |
| CHARACTER_ESCAPE | any character | CHARACTER_LITERAL | emit |
<!-- END GENERATED: compact-table -->

## Complete table

One row for every (state, input class) pair, followed by the state's
end-of-input row: 9 × 7 = 63 transitions and 9 end-of-input rules.

<!-- BEGIN GENERATED: transition-table -->
| Current State | Input | Next State | Output | Event | Action |
|---|---|---|---|---|---|
| NORMAL | `/` | POSSIBLE_COMMENT | `BUFFER` |  | '/' may start a comment: hold it and decide on the next character |
| NORMAL | `*` | NORMAL | `EMIT` |  | Ordinary source character: copy it to the output |
| NORMAL | `"` | STRING_LITERAL | `EMIT` | `STRING_START` | Opening '"' starts a string literal: copy it |
| NORMAL | `'` | CHARACTER_LITERAL | `EMIT` | `CHARACTER_START` | Opening "'" starts a character literal: copy it |
| NORMAL | `\` | NORMAL | `EMIT` |  | Ordinary source character: copy it to the output |
| NORMAL | newline | NORMAL | `EMIT` |  | Ordinary source character: copy it to the output |
| NORMAL | other | NORMAL | `EMIT` |  | Ordinary source character: copy it to the output |
| NORMAL | end of input | NORMAL | `NONE` |  | End of input in NORMAL: the source is lexically complete |
| POSSIBLE_COMMENT | `/` | SINGLE_LINE_COMMENT | `DISCARD_BUFFER` | `SINGLE_LINE_COMMENT_START` | '//' recognised: a single-line comment starts; discard both slashes |
| POSSIBLE_COMMENT | `*` | MULTI_LINE_COMMENT | `DISCARD_BUFFER` | `MULTI_LINE_COMMENT_START` | '/*' recognised: a multi-line comment starts; discard '/' and '*' |
| POSSIBLE_COMMENT | `"` | STRING_LITERAL | `FLUSH_AND_EMIT` | `STRING_START` | The held '/' was an operator: emit it, then start a string literal |
| POSSIBLE_COMMENT | `'` | CHARACTER_LITERAL | `FLUSH_AND_EMIT` | `CHARACTER_START` | The held '/' was an operator: emit it, then start a character literal |
| POSSIBLE_COMMENT | `\` | NORMAL | `FLUSH_AND_EMIT` |  | Not a comment: the held '/' is an operator (e.g. division); emit it and this character |
| POSSIBLE_COMMENT | newline | NORMAL | `FLUSH_AND_EMIT` |  | Not a comment: the held '/' is an operator (e.g. division); emit it and this character |
| POSSIBLE_COMMENT | other | NORMAL | `FLUSH_AND_EMIT` |  | Not a comment: the held '/' is an operator (e.g. division); emit it and this character |
| POSSIBLE_COMMENT | end of input | NORMAL | `FLUSH` |  | End of input right after '/': the held '/' is code; emit it |
| SINGLE_LINE_COMMENT | `/` | SINGLE_LINE_COMMENT | `DISCARD` |  | Comment text: discard it |
| SINGLE_LINE_COMMENT | `*` | SINGLE_LINE_COMMENT | `DISCARD` |  | Comment text: discard it |
| SINGLE_LINE_COMMENT | `"` | SINGLE_LINE_COMMENT | `DISCARD` |  | Comment text: discard it |
| SINGLE_LINE_COMMENT | `'` | SINGLE_LINE_COMMENT | `DISCARD` |  | Comment text: discard it |
| SINGLE_LINE_COMMENT | `\` | SINGLE_LINE_COMMENT | `DISCARD` |  | Comment text: discard it |
| SINGLE_LINE_COMMENT | newline | NORMAL | `EMIT` | `COMMENT_END` | Line break ends the single-line comment; the line break is code and is kept |
| SINGLE_LINE_COMMENT | other | SINGLE_LINE_COMMENT | `DISCARD` |  | Comment text: discard it |
| SINGLE_LINE_COMMENT | end of input | NORMAL | `NONE` | `COMMENT_END` | End of input also ends a single-line comment |
| MULTI_LINE_COMMENT | `/` | MULTI_LINE_COMMENT | `DISCARD` |  | Comment text: discard it |
| MULTI_LINE_COMMENT | `*` | POSSIBLE_COMMENT_END | `DISCARD` |  | '*' may start the closing '*/': discard it and check the next character |
| MULTI_LINE_COMMENT | `"` | MULTI_LINE_COMMENT | `DISCARD` |  | Comment text: discard it |
| MULTI_LINE_COMMENT | `'` | MULTI_LINE_COMMENT | `DISCARD` |  | Comment text: discard it |
| MULTI_LINE_COMMENT | `\` | MULTI_LINE_COMMENT | `DISCARD` |  | Comment text: discard it |
| MULTI_LINE_COMMENT | newline | MULTI_LINE_COMMENT | `DISCARD` |  | Line break inside the comment: discard it (the line counter still advances) |
| MULTI_LINE_COMMENT | other | MULTI_LINE_COMMENT | `DISCARD` |  | Comment text: discard it |
| MULTI_LINE_COMMENT | end of input | MULTI_LINE_COMMENT | `NONE` | `UNTERMINATED_COMMENT` | Lexical error: end of input inside a multi-line comment (no closing '*/') |
| POSSIBLE_COMMENT_END | `/` | NORMAL | `REPLACE_WITH_SPACE` | `COMMENT_END` | '*/' closes the comment: discard '/' and emit one space in place of the comment |
| POSSIBLE_COMMENT_END | `*` | POSSIBLE_COMMENT_END | `DISCARD` |  | Another '*': the comment may still close with '/' (as in '**/') |
| POSSIBLE_COMMENT_END | `"` | MULTI_LINE_COMMENT | `DISCARD` |  | '*' was not followed by '/': still inside the comment |
| POSSIBLE_COMMENT_END | `'` | MULTI_LINE_COMMENT | `DISCARD` |  | '*' was not followed by '/': still inside the comment |
| POSSIBLE_COMMENT_END | `\` | MULTI_LINE_COMMENT | `DISCARD` |  | '*' was not followed by '/': still inside the comment |
| POSSIBLE_COMMENT_END | newline | MULTI_LINE_COMMENT | `DISCARD` |  | '*' was not followed by '/': still inside the comment |
| POSSIBLE_COMMENT_END | other | MULTI_LINE_COMMENT | `DISCARD` |  | '*' was not followed by '/': still inside the comment |
| POSSIBLE_COMMENT_END | end of input | POSSIBLE_COMMENT_END | `NONE` | `UNTERMINATED_COMMENT` | Lexical error: end of input inside a multi-line comment (no closing '*/') |
| STRING_LITERAL | `/` | STRING_LITERAL | `EMIT` |  | String content (comment markers here are plain text): copy it unchanged |
| STRING_LITERAL | `*` | STRING_LITERAL | `EMIT` |  | String content (comment markers here are plain text): copy it unchanged |
| STRING_LITERAL | `"` | NORMAL | `EMIT` | `STRING_END` | Closing '"' ends the string literal: copy it |
| STRING_LITERAL | `'` | STRING_LITERAL | `EMIT` |  | String content (comment markers here are plain text): copy it unchanged |
| STRING_LITERAL | `\` | STRING_ESCAPE | `EMIT` |  | Backslash: the next character is escaped and cannot end the string |
| STRING_LITERAL | newline | NORMAL | `EMIT` | `UNTERMINATED_STRING` | Lexical error: a raw line break cannot appear in a string literal; report it and resume in NORMAL |
| STRING_LITERAL | other | STRING_LITERAL | `EMIT` |  | String content (comment markers here are plain text): copy it unchanged |
| STRING_LITERAL | end of input | STRING_LITERAL | `NONE` | `UNTERMINATED_STRING` | Lexical error: end of input inside a string literal (no closing '"') |
| STRING_ESCAPE | `/` | STRING_LITERAL | `EMIT` |  | Escaped character (such as \" or \\): copy it and continue the string |
| STRING_ESCAPE | `*` | STRING_LITERAL | `EMIT` |  | Escaped character (such as \" or \\): copy it and continue the string |
| STRING_ESCAPE | `"` | STRING_LITERAL | `EMIT` |  | Escaped character (such as \" or \\): copy it and continue the string |
| STRING_ESCAPE | `'` | STRING_LITERAL | `EMIT` |  | Escaped character (such as \" or \\): copy it and continue the string |
| STRING_ESCAPE | `\` | STRING_LITERAL | `EMIT` |  | Escaped character (such as \" or \\): copy it and continue the string |
| STRING_ESCAPE | newline | STRING_LITERAL | `EMIT` |  | Escaped character (such as \" or \\): copy it and continue the string |
| STRING_ESCAPE | other | STRING_LITERAL | `EMIT` |  | Escaped character (such as \" or \\): copy it and continue the string |
| STRING_ESCAPE | end of input | STRING_ESCAPE | `NONE` | `UNTERMINATED_STRING` | Lexical error: end of input inside a string literal (no closing '"') |
| CHARACTER_LITERAL | `/` | CHARACTER_LITERAL | `EMIT` |  | Character-literal content: copy it unchanged |
| CHARACTER_LITERAL | `*` | CHARACTER_LITERAL | `EMIT` |  | Character-literal content: copy it unchanged |
| CHARACTER_LITERAL | `"` | CHARACTER_LITERAL | `EMIT` |  | Character-literal content: copy it unchanged |
| CHARACTER_LITERAL | `'` | NORMAL | `EMIT` | `CHARACTER_END` | Closing "'" ends the character literal: copy it |
| CHARACTER_LITERAL | `\` | CHARACTER_ESCAPE | `EMIT` |  | Backslash: the next character is escaped and cannot end the literal |
| CHARACTER_LITERAL | newline | NORMAL | `EMIT` | `UNTERMINATED_CHARACTER` | Lexical error: a raw line break cannot appear in a character literal; report it and resume in NORMAL |
| CHARACTER_LITERAL | other | CHARACTER_LITERAL | `EMIT` |  | Character-literal content: copy it unchanged |
| CHARACTER_LITERAL | end of input | CHARACTER_LITERAL | `NONE` | `UNTERMINATED_CHARACTER` | Lexical error: end of input inside a character literal (no closing "'") |
| CHARACTER_ESCAPE | `/` | CHARACTER_LITERAL | `EMIT` |  | Escaped character (such as \' or \\): copy it and continue the literal |
| CHARACTER_ESCAPE | `*` | CHARACTER_LITERAL | `EMIT` |  | Escaped character (such as \' or \\): copy it and continue the literal |
| CHARACTER_ESCAPE | `"` | CHARACTER_LITERAL | `EMIT` |  | Escaped character (such as \' or \\): copy it and continue the literal |
| CHARACTER_ESCAPE | `'` | CHARACTER_LITERAL | `EMIT` |  | Escaped character (such as \' or \\): copy it and continue the literal |
| CHARACTER_ESCAPE | `\` | CHARACTER_LITERAL | `EMIT` |  | Escaped character (such as \' or \\): copy it and continue the literal |
| CHARACTER_ESCAPE | newline | CHARACTER_LITERAL | `EMIT` |  | Escaped character (such as \' or \\): copy it and continue the literal |
| CHARACTER_ESCAPE | other | CHARACTER_LITERAL | `EMIT` |  | Escaped character (such as \' or \\): copy it and continue the literal |
| CHARACTER_ESCAPE | end of input | CHARACTER_ESCAPE | `NONE` | `UNTERMINATED_CHARACTER` | Lexical error: end of input inside a character literal (no closing "'") |
<!-- END GENERATED: transition-table -->

## End of input

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
