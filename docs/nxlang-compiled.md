# How nxlang becomes strict Nextion syntax

The build compiles nxlang ([language.md](language.md)) into strict Nextion syntax, which the Nextion Editor accepts. This page describes the code it writes, for when you read that code, as in VS Code's "Show this file in strict Nextion syntax", or when you work on the compiler.

The compiler is `nxwright/language/nxlang.py`. `nxwright/language/editor_code.py` handles code in strict Nextion syntax that comes into a folder in nxlang, as when extracting.

## An example

This nxlang page:

```
const LIMIT = 3000

function showError(message: text):
  error.txt = message
  vis error,1

on save.up:
  var total = first.val + second.val * 2
  if (total > LIMIT || !ready.val) {
    showError("Too high: " + total)
  } else {
    t0.txt = "Total: " + total
  }
```

is built as three events. The Touch Release event of `save`:

```
__g0_1=second.val*2+first.val
if(__g0_1>3000||ready.val==0)
{
  covx __g0_1,__s0.txt,0,0
  __v0.txt="Too high: "+__s0.txt
  __g0_0=0
  click __f0,1
}else
{
  covx __g0_1,__s0.txt,0,0
  t0.txt="Total: "+__s0.txt
}
```

The Touch Press event of the hidden hotspot `__f0`:

```
// function showError(message: text)
if(__g0_0==0)
{
  error.txt=__v0.txt
  vis error,1
}
```

The page's Preinitialize event:

```
tsw __f0,0
```

- `total` is the hidden global `__g0_1`. Its sum is reordered, so that the Nextion Editor's left-to-right order computes it correctly.
- `!ready.val` becomes `ready.val==0`.
- Each number joined to text is first converted with `covx`, into the text temporary `__s0`.
- The call to `showError` sets the parameter `__v0`, then the "which function" global `__g0_0`, then clicks the hidden hotspot `__f0`, whose event holds the function's body.

## What the Nextion Editor cannot do

The Nextion Editor accepts less than nxlang:

- it computes arithmetic from left to right, with no parentheses;
- its conditions can only compare plain values: they cannot contain arithmetic, or mix `&&` and `||`;
- it cannot join a number to text;
- it refuses `-x`.

## How expressions are written

- An expression the Nextion Editor would compute differently is split. A part is computed first into a hidden variable, a **temporary**. `x.val = a.val - b.val * c.val` becomes `__g0_0=b.val*c.val`, then `x.val=a.val-__g0_0`. An expression that already computes correctly from left to right is written unchanged.
- A text assignment that uses its own target anywhere but first, such as `t0.txt = "-" + t0.txt`, is built in a temporary first. On the screen, such a line would keep the old text and append the other pieces.
- A condition's operands are computed into temporaries just before it. A `while` loop computes them again at the end of each pass. A `for` loop whose header needs temporaries becomes a `while` loop.
- A condition mixing `&&` and `||` computes each inner part into a temporary set to 0 or 1.
- `!` is removed by reversing comparisons: `!(a == b)` becomes `a != b`.
- When the right side of `&&` or `||` needs computing first, the whole condition goes into a temporary set to 0 or 1. Nested `if` blocks reach each part only when needed.
- An `else if` whose condition needs temporaries becomes `else`, then a block that computes them and contains the `if`.
- `a ? b : c` becomes an `if` on `a` and its `else`, which put `b` or `c` in a temporary. Each side is computed inside its own block, so only the chosen one runs.
- A number joined to text is converted first, with `covx <number>,<temporary>,0,0`.
- `-x` becomes `0-x`.
- A tab after an `int` line's `int` is written as one space. The Nextion Editor reads a tab there as part of the name, and refuses the declaration.
- The Nextion Editor takes each argument of a data record's call, such as `d0.insert("Total: " + t0.txt)`, only as one text or one number. So an argument of more than one operand is computed into a temporary first. A number given for a text becomes its digits. A text given for a number is refused.
- The Nextion Editor takes the first argument of `get`, `print`, `prints`, and `covx` only as one text or one number. So a first argument of more than one operand is computed into a temporary first: `print x.val + 1` becomes `__g0_0=x.val+1`, then `print __g0_0`. Their other numbers, `prints`' length and `covx`'s length and form, are written as arithmetic, which the Nextion Editor takes there.
- An escape the screen does not read, a variable's `val` while it stores a text or its `txt` while it stores a number, and a command given another number of arguments than it takes are written as they are. The build then refuses them ([build-rules.md](build-rules.md)).

## The hidden variables and components

A page has at most 256 objects, so the compiler adds as few as it can. Everything it adds has a name starting with `__`.

- **Numbers are globals.** Every number the compiler needs is an `int` global of `program.s`, named after its page: `__g3_17` is page 3's 18th. The build declares them in lines at the top of `program.s`, and extracting leaves those lines out of `program.nx`. Pages never share one, since changing page runs the new page's Preinitialize event in the middle of the old page's event. Up to 8,000 globals are known to work, and the build stops past that.
- **Only text needs a component** on the page: `__s0`, `__s1`, ... for temporaries, and `__v0`, `__v1`, ... for text that lasts longer: locals, parameters, results, and a `switch`'s value. They store up to 255 characters.

### What runs during what

To reuse its hidden variables safely, the compiler works out what may run during each event and function.

- No event runs in the middle of another, except through `click`. Timer events wait, even across `doevents`.
- A call is a `click` too, of a hidden hotspot (below).
- So what may run during an event or a function is what it calls, the events its hand-made clicks run, and what those run in turn. A **chain** is such a run of calls and clicks, such as an event, a function it calls, and a function that one calls.
- A hand-made `click` must give its component and 0 or 1, so that the compiler can tell which event runs ([Limits](language.md#limits)).
- The compiler also works out what may run during a macro's `call`: the macros that macro calls, and the events its clicks run. A macro's `click` gives a component's ID, counted on the page whose code called the macro. A macro has no hidden variables. But its `call` is one level of the chain, as a function's call is, so it counts toward the limit on how deep events nest ([Functions](#functions)).

### How the hidden variables are shared

- **Longer-lived text.** An event's or a function's `__v` variables come just after those of everything that may run during it, so nothing it runs can change them. Two that never run at once may share them. A page needs as many as its heaviest chain.
- **Temporaries.** A temporary lives only within one statement, and a click is a statement of its own. An event that nothing runs has depth 0. An event or a function has a depth one more than its deepest caller or clicker. The events and functions of one depth share one set of temporaries. One that runs during another always has a greater depth, so the two never share one.
- Control variables (below) are globals of their own event or function.

## Functions

- The functions of one depth share a 2 by 2 hotspot in the page's top left corner: `__f0` for the smallest depth, `__f1` for the next, and so on.
- The hotspot's Touch Press event contains their bodies, each after a comment giving the function, inside an `if` on a "which function" global.
- Each function's labels are renamed there, `__l0` and on, so that one function's labels never meet another's.
- The page's Preinitialize event starts with `tsw __f0,0` for each hotspot, turning its touches off. `click` still runs it.
- A call computes all its arguments first, then sets the parameter variables, then the "which function" global, then runs `click __f0,1`, and reads the result.
- When a statement contains two calls or more, each result is copied into a temporary at once. So a later call, which may share its variables, cannot overwrite it.
- `click` nests at most 9 events deep, counting across components. A 10th stops with "Endless loop was detected". The first is the event a press or a timer runs, and each call or hand-made click nests one more. So a chain may have at most 7 calls and clicks, leaving one level for a `page` command, which runs the new page's `load` event inside the current event, where the compiler cannot see it.

## `break`, `continue`, and `switch`

The Nextion Editor has none of them:

- A loop containing a `break` or a `continue` of its own gets a **control variable**, a global: 0 while a pass runs, 1 after `continue`, 2 after `break`.
  - It is set to 0 before the loop and at the start of each pass, and the loop's condition tests it first.
  - Code that could still run in the same pass after a jump goes inside `if` blocks testing it.
  - A `for` loop containing one becomes a `while` loop whose step runs unless the loop is leaving.
- A `switch` puts its value into a variable of its own: a global for a number, or a `__v` variable for a text.
  - It has three control variables: one for its `break`, one set once a case matched, and one telling whether no case can match.
  - Each case's code runs inside an `if` testing them, so falling through and `break` work as in C.
- The hidden variables keep their values between runs of an event. So all of these are set when their loop or `switch` starts.

## `program.nx`

`program.nx` can use constants and expressions, but not locals. It has no page, so no temporaries: an expression there that would need one stops the build, as does a text assignment that uses its own target anywhere but first.
