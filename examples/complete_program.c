/*
 * complete_program.c
 * A small C program that uses every feature the scanner must handle.
 */
#include <stdio.h>

#define SQUARE(x) ((x) * (x))   /* function-like macro */
#define LIMIT  10               // object-like macro

/* Prints the squares from 1 to LIMIT. */
int main(void)
{
    int    total   = 0;         // running sum
    char   slash   = '/';       /* a character literal holding a slash */
    char  *url     = "https://example.com/a//b";  // "//" here is text
    char  *banner  = "/* not a comment */";

    for (int i = 1; i <= LIMIT; i++) {
        total += SQUARE(i);     /* accumulate */
    }

    int half = total / 2;       // division, not a comment
    int/**/count = LIMIT;       /* the comment separates two tokens */

    printf("total=%d half=%d count=%d %c\n", total, half, count, slash);
    printf("%s %s\n", url, banner);
    printf("quote: \" backslash: \\ tab:\t end\n");
    return 0;
}
