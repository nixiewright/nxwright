# How nxlang becomes strict Nextion syntax

The build compiles nxlang ([language.md](language.md)) into strict Nextion syntax, which the Nextion Editor accepts. This page describes the code the build writes. It can help when you read that code, for example with VS Code's "Show this file in strict Nextion syntax", or when you work on the compiler.

The compiler is `nxwright/language/nxlang.py`. `nxwright/language/editor_code.py` rewrites strict Nextion syntax when you switch a folder to nxlang.

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
- Each number joined to text is first converted with `covx` into the hidden text variable `__s0`.
- The call to `showError` sets the parameter `__v0`, then the "which function" global `__g0_0`, then clicks the hidden hotspot `__f0`, whose event contains the function's body.
- The `tsw` line in the Preinitialize event turns off the touches of `__f0`, and `click` still runs its event.

## What the Nextion Editor cannot do

The Nextion Editor accepts less than nxlang:

- Arithmetic is computed from left to right, with no parentheses.
- Conditions can only compare plain values. They cannot contain arithmetic, or mix `&&` and `||`.
- A number cannot be joined to text.
- `-x` is refused.

## How expressions are written

### Arithmetic and text

- An expression the Nextion Editor would compute differently is split. A part is computed first into a hidden variable, a **temporary**. `x.val = a.val - b.val * c.val` becomes `__g0_0=b.val*c.val`, then `x.val=a.val-__g0_0`. An expression that already computes correctly from left to right is written unchanged.
- `-x` becomes `0-x`.
- A number too large for 32 bits keeps its low 32 bits, as in C. For example, `4294967295` becomes `-1`, and `0x0100000005` becomes `0x00000005` ([language.md](language.md)).
- A number joined to text is converted first, with `covx <number>,<temporary>,0,0`.
- A text assignment that uses its own target anywhere but first, such as `t0.txt = "-" + t0.txt`, is built in a temporary first. On the screen, such a line would keep the old text and append the other pieces.

### Long lines

- A text assignment longer than 767 bytes in utf-8 is written in several lines: the first assigns, and each one after it appends with `+=`. `t0.txt = "…"` with 1000 ASCII characters becomes `t0.txt="…"`, then `t0.txt+="…"`. Every series of Nextion screen accepts lines of at least 767 bytes, and no encoding uses more bytes than utf-8 for a character. So each line fits on every screen ([build-rules.md](build-rules.md#long-lines)).
  - In shift-jis, the Nextion Editor reads a text in pairs of bytes, and pairs a half-width katakana with the byte after it. So after a katakana, nxlang waits for a plain ASCII character before it splits the text.
- A `print` of a text longer than 767 bytes becomes several `print` lines, split the same way as a long text assignment. A long `prints` is not split.
- A number assignment longer than 767 bytes is computed in steps through a temporary, which receives the start of the value: `__g0_0=a.val+b.val+…`, then `x.val=__g0_0+…`. A compound assignment is split with its target first, because the Nextion Editor computes it in that order: `x.val += …` becomes `__g0_0=x.val+…`, then `x.val=__g0_0+…`.

### Conditions and loops

- A condition's operands are computed into temporaries just before it. A `while` loop computes them again at the end of each pass. A `for` loop whose header needs temporaries becomes a `while` loop.
- The Nextion Editor refuses a text containing a semicolon anywhere in a `for`'s header, though it takes one in a `while`'s condition. So such a `for` loop becomes a `while` loop.
- `!` is removed by reversing comparisons: `!(a == b)` becomes `a != b`.
- A condition mixing `&&` and `||` computes each inner part into a temporary set to 0 or 1.
- When the right side of `&&` or `||` needs computing first, the whole condition goes into a temporary set to 0 or 1. Nested `if` blocks compute each part only when it is needed.
- An `else if` whose condition needs temporaries becomes `else`, then a block that computes them and contains the `if`.
- `a ? b : c` becomes an `if` on `a` and its `else`, which put `b` or `c` in a temporary. Each side is computed inside its own block, so only the chosen one runs.
- The Nextion Editor refuses a text that ends in an escaped backslash in a condition, though it takes one in an assignment. So such a text is put into a text temporary first: `if (t0.txt == "a\\")` becomes `__s0.txt="a\\"`, then `if(t0.txt==__s0.txt)`. A `switch` case of such a text is compared the same way.
- In gb2312, big5, and shift-jis, a few characters, such as 表 in shift-jis, end in the byte 0x5C, the code of a backslash. In a condition, and before a comma in `prints`, `spstr`, `strlen`, `btlen`, and `crcputs`, the Nextion Editor takes that byte for a backslash before the closing quote. So in an event, nxlang puts a text that ends in one of these characters into a text temporary first: `prints "日表", 0` becomes `__s0.txt="日表"`, then `prints __s0.txt,0`. In `program.nx`, the build refuses the line ([build-rules.md](build-rules.md#texts-in-gb2312-big5-and-shift-jis)).

### Arguments of commands

The Nextion Editor accepts only one text or one number in many command arguments, so nxlang computes an argument of more than one operand into a temporary first. For example, `print x.val + 1` becomes `__g0_0=x.val+1`, then `print __g0_0`, and `strlen t0.txt + "a", n0.val` becomes `__s0.txt=t0.txt+"a"`, then `strlen __s0.txt,n0.val`. nxlang does this for:

- Each argument of a data record's call, such as `d0.insert("Total: " + t0.txt)`. A number given for a text becomes its digits, and a text given for a number is refused.
- The first argument of `get`, `print`, `prints`, and `covx`. The other numbers of these commands, `prints`' length and `covx`'s length and form, are written as arithmetic, which the Nextion Editor accepts in those arguments.
- The text of `xstr`, its last argument. A minus before a name in that text also goes into a temporary first. The other arguments of `xstr` are written as they are.
- The value `wepo` writes, the value `crcputs` sends, the file `delfile` deletes, the text that `strlen`, `substr`, `spstr`, and `btlen` read, and the separator `spstr` splits on. A minus before a name in these arguments also goes into a temporary first, because the Nextion Editor refuses it there: `strlen -n0.val, n0.val` becomes `__g0_0=0-n0.val`, then `strlen __g0_0,n0.val`.

Two cases differ:

- **A `print` of joined texts** is written as one `print` for each part, so no temporary is needed and no part is cut short. `print "Total: " + t0.txt` becomes `print "Total: "`, then `print t0.txt`. Every part is worked out first, then each is printed.
- **Joined texts given to `wepo`** are refused, as in `wepo t0.txt + "a", 0`. When `wepo` saves a text, it writes as many bytes as the text field has room for, plus one. A temporary has room for 255 bytes, so `wepo` would write 256 bytes, far more than the text. A number, as in `wepo n0.val * 2, 0`, is put in a temporary as usual.

The Nextion Editor does not read a minus before a name where a command takes a number, as in `cls -x.val` or `cls 2*-x.val`. So nxlang computes such a value into a temporary first: `cls -x.val` becomes `__g0_0=0-x.val`, then `cls __g0_0`.

nxlang does not compute an expression where a command puts its result, as in `cov n0.val, sys0 + 1, 0`, or in a command the vendor does not document, such as `getv`. The build refuses these lines ([build-rules.md](build-rules.md#first-arguments)).

### Other lines

- A tab after `int` in a declaration is written as one space. The Nextion Editor reads a tab there as part of the name, and refuses the declaration.
- nxlang writes these as they are, and the build then refuses them ([build-rules.md](build-rules.md)):
  - an escape the screen does not read
  - a variable's `val` while the variable stores a text, or its `txt` while it stores a number
  - a command given the wrong number of arguments

## The hidden variables and components

A page has at most 250 components, so the compiler adds as few as it can. Everything it adds has a name starting with `__`.

- **Numbers are globals.** Every number the compiler needs is an `int` global of `program.s`, named after its page: `__g3_17` is page 3's 18th. The build declares them in lines at the top of `program.s`. Pages never share a global, since changing page runs the new page's Preinitialize event in the middle of the old page's event. Up to 8,000 globals are known to work, and the build refuses more.
- **Only text needs a component** on the page. Temporaries are `__s0`, `__s1`, and so on. Text that lasts longer, such as a local, a parameter, a result, or a `switch`'s value, is kept in `__v0`, `__v1`, and so on. Each has room for 255 bytes unless nxlang gives it more, and a text too long for its variable is cut.
  - **A longer quoted text gets the room it needs.** When a variable is given a quoted text longer than 255 bytes, it gets room for that text, plus 255 bytes for each other part joined to it.
  - **Several events or functions can share a variable**, for example as a local in each. The variable gets the most room any of them needs. When a text is copied from it, only the texts written for the same local or parameter count toward the copy's room. For a local, those are the texts its own event or function writes. For a parameter, they are the texts that its function and the function's callers write.
  - **Short texts added one by one with `+=` share 255 bytes.** nxlang counts the text already in the variable as filling the variable's room. It gives more room only when that room, or a part added, is over 255 bytes.
  - **Inside a function, a copy of a parameter keeps only 255 bytes**, even when a caller gives the parameter a longer text. nxlang compiles the function before its callers, so it does not know yet how long that text is. The copy's variable can still have more room, if another local sharing it needs more.
  - **A cut that nxlang can foresee gives a warning.** `nxwright check` and the live checks show the warning `text-cut` on a line that puts a text into a variable with less room than the text's parts may need together. One of those parts must be a component's text, or a variable that nxlang gave more than 255 bytes, such as a parameter that a caller gave a longer text. Short texts added with `+=`, and other joins of parts of 255 bytes or less, do not give the warning, because otherwise almost every join would. For a longer text, use a variable component.

### What runs during what

To reuse its hidden variables safely, the compiler works out what may run during each event and function. No event runs in the middle of another except through `click`, and timer events wait, even across `doevents`. A function call is a `click` too, of a hidden hotspot ([Functions](#functions)). So what may run during an event or a function is what it calls, the events its hand-made clicks run, and what those run in turn. A **chain** is one such run of calls and clicks, for example an event, a function it calls, and a function called by that function.

A hand-made `click` must give its component and 0 or 1, so that the compiler can tell which event runs ([Limits](language.md#limits)).

The compiler also works out what may run during a macro's `call`: the macros that macro calls, and the events its clicks run. A macro's `click` gives a component's ID, counted on the page whose code called the macro. A macro has no hidden variables, but its `call` is one level of the chain, so it counts toward the limit on how deep events nest ([Functions](#functions)).

### How the hidden variables are shared

- **Longer-lived text.** The compiler numbers the `__v` variables of an event or a function just after those of everything that may run during it, so nothing it runs can change them. Two events or functions that never run at once may use the same `__v` variables. A page needs as many `__v` variables as the chain that uses the most.
- **Temporaries.** A temporary lives only within one statement, and a click is a statement of its own. Each event or function has a **depth**: 0 for an event that nothing calls or clicks, and otherwise one more than the deepest event or function that calls or clicks it. All the events and functions of one depth share a set of temporaries. An event or a function that runs during another always has a greater depth, so the two never share a set.
- Control variables ([`break`, `continue`, and `switch`](#break-continue-and-switch)) are globals of their own event or function.

## Functions

- The functions of one depth share a 2 by 2 hotspot in the page's top left corner: `__f0` for the smallest depth, `__f1` for the next, and so on.
- The hotspot's Touch Press event contains their bodies, each after a comment giving the function, inside an `if` on a "which function" global.
- Each function's labels are renamed in the hotspot's event, to `__l0`, `__l1`, and so on, so that two functions never use the same label.
- The page's Preinitialize event starts with one `tsw` line for each hotspot, such as `tsw __f0,0`, to turn off its touches. `click` still runs the hotspot's event.
- A call computes all its arguments first, then sets the parameter variables, then the "which function" global, then runs `click __f0,1`, and reads the result.
- When a statement contains two or more calls, each result is copied into a temporary right after its call. Otherwise a later call that shares the same variables could overwrite it.
- `click` nests at most 9 events deep, counting across components. A 10th event stops with "Endless loop was detected". The first level is the event a press or a timer runs, and each call or hand-made click nests one more. So a chain may have at most 7 calls and clicks. That leaves one level for a `page` command, which runs the new page's Preinitialize event inside the current event, where the compiler cannot see it.

## `break`, `continue`, and `switch`

The Nextion Editor has no `break`, `continue`, or `switch`, so nxlang builds them from hidden variables.

- A loop containing a `break` or a `continue` of its own gets a **control variable**, a global: 0 while a pass runs, 1 after `continue`, 2 after `break`.
  - The control variable is set to 0 before the loop and at the start of each pass, and the loop's condition tests it first.
  - Code that could still run in the same pass after a jump goes inside `if` blocks testing the control variable.
  - A `for` loop with a control variable becomes a `while` loop whose step runs unless the loop is leaving.
- A `switch` puts its value into a variable of its own: a global for a number, or a `__v` variable for a text.
  - A `switch` also has three control variables: one for its `break`, one set once a case matched, and one telling whether no case can match.
  - Each case's code runs inside an `if` testing these control variables, so falling through and `break` work as in C.
- Hidden variables keep their values between runs of an event, so all the variables above are set when their loop or `switch` starts.

## `program.nx`

`program.nx` can use constants and expressions, but not locals. It has no page, and so no temporaries. The build refuses any line of `program.nx` that would need a temporary, such as a text assignment that uses its own target anywhere but first.

In `program.nx`, nxlang turns `vis b[1], 0` into `vis 1,0`, and `vis b[n], 0` into `vis n,0`. The Nextion Editor refuses `b[1]` in `program.s`, but takes `1`. Both mean the component with ID 1 on the page that is showing.

`p[0].b[1]` is still refused, because page 0 may not be the page showing.

An `int` line can go anywhere in `program.nx`. The Nextion Editor only takes declarations before other code, so nxlang moves each later `int` line up to just before the first line of code, without its indent. For example, `dim=100` then `int late=1` becomes `int late=1` then `dim=100`. The variable still starts at the same value, even if the `int` was inside an `if` block. An error still gives the line where you wrote the `int`.
