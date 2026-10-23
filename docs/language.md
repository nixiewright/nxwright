# nxlang

nxlang, the nxwright language, is Nextion syntax with the parts a programmer expects. You write your event code in it, and the build compiles it into code the Nextion Editor accepts.

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

What nxlang adds:

- arithmetic in the usual order, with parentheses: `a + b * c` is `a + (b * c)`;
- text joined to numbers: `"Total: " + total`;
- conditions with any expression, mixing `&&` and `||`, and `!`;
- constants, local variables, and functions;
- `break`, `continue`, and `switch`;
- including other `.nx` files, such as a library shared by pages.

[nxlang-compiled.md](nxlang-compiled.md) describes the code the build writes from it.

## Switching to nxlang

```
nxwright language <source-folder> nxlang
```

Every source folder gives its language in `app.toml`: `language = "nextion"` for strict Nextion syntax, or `language = "nxlang"`. A folder extracted from a project starts in strict Nextion syntax. Even there, you can write code comfortably, with spaces and braces where the Nextion Editor wants none ([Comfortable code](source-folder.md#comfortable-code)).

Always switch with the command, never by changing `app.toml` by hand. The two languages read some code differently: the Nextion Editor computes `a+b*c` as `(a+b)*c`, strictly from left to right, while nxlang computes it with the more usual precedence, as `a+(b*c)`. So the command rewrites every line that the two read differently, adding the parentheses that keep the Nextion Editor's meaning: `(a+b)*c`.

- The rewritten code builds to exactly the same project. If any code would not, the command stops before writing anything.
- There is no command to switch back. If you must, build the project, then extract it into a new folder. You get a folder in strict Nextion syntax that builds the same project. Its code is the code the build wrote, with the compiler's hidden variables and hotspots ([nxlang-compiled.md](nxlang-compiled.md)), not the nxlang you wrote.

In VS Code, "Switch the source folder to the nxwright language" opens a panel that explains the switch before you make it:

- what nxlang adds, each beside how you write the same thing in strict Nextion syntax;
- each line of your code that the switch will rewrite, before and after, with each file's changes.

Its button makes the switch in one edit, which one undo takes back. It refuses while a file of the project has unsaved changes. After the switch, it offers to format the project's code.

## Expressions

Operators, from the tightest binding to the loosest:

| Operators | Meaning |
| --- | --- |
| `-x`, `!x` | minus; not (conditions only) |
| `*` `/` `%` | multiply, divide, remainder |
| `+` `-` | add, subtract; `+` also joins text |
| `<<` `>>` | shift |
| `<` `>` `<=` `>=` | compare (conditions only) |
| `==` `!=` | compare (conditions only) |
| `&` | bitwise and |
| `^` | bitwise exclusive or |
| `\|` | bitwise or |
| `&&` | and (conditions only) |
| `\|\|` | or (conditions only) |
| `? :` | `a ? b : c` is `b` when `a` is true, else `c` |

This is C's order. So `a & 1 == 1` means `a & (1 == 1)`, which the build refuses. Write `(a & 1) == 1`.

### Numbers

- Parentheses group as usual.
- Numbers are 32-bit, and behave as on the screen.
- Division rounds toward zero: `-7/2` is `-3`.
- The remainder takes the sign of the left side: `-7%2` is `-1`.
- `>>` keeps the sign: `-8>>1` is `-4`.

Hexadecimal numbers are written as in C: `0x1F`, `0x1`, `-0x10`.

- A value past `0x7FFFFFFF` stands for its 32 bits, so `0xFFFFFFFF` is -1, as on the screen.
- The Nextion Editor reads fewer forms: digits in pairs, without a sign, within 32 bits, and no hexadecimal number in an `int`'s starting value. So the build rewrites the other forms: `0x1` as `0x01`, `-0x10` as `-16`, and an `int`'s starting value in decimal.
- A number too large for 32 bits, such as `0x0100000005`, keeps its low 32 bits, `0x00000005`, as C keeps them. `nxwright check` warns of it.

### Text

- `+` joins text. A number joined to text becomes its digits first: `t0.txt = "Speed: " + speed.val + " mm/s"`.
- Putting a number into a text converts it the same way: `t0.txt = n0.val`.
- `t0.txt -= 2` removes the last two characters.

### Assignments and conditions

- `x -= a + b` means `x = x - (a + b)`.
- The conditions of `if`, `else if`, `while`, `for`, and `? :` can contain any expression. They can mix `&&` and `||`, and use `!`.
- A plain number counts as true when it is not 0: `if (flag.val)`.
- Texts compare with `==` and `!=` only.
- `&&` and `||` evaluate their right side only when needed, as in C. So `b != 0 && a / b > 1` never divides by 0. In `ready.val == 1 && save() == 1`, `save` runs only when `ready.val` is 1.
- `? :` chooses a value, as in C: `t0.txt = ready.val ? "Ready" : "Waiting"`. Only the chosen side runs. Both sides are numbers, or both texts. Among commands, only the first argument of `get`, `print`, `prints`, and `covx` takes it. For another command, such as `vis`, put the value in a local first.

## Constants

```
const SPEED_LIMIT = 1200
const UNIT = " mm/s"
```

A constant's value is a number or a text. The build replaces each use with the value.

- Constants for one page go at the top of its `.nx` file, before the first `on` heading.
- Constants for every page go in `program.nx`, anywhere.
- A constant cannot share its name with another constant, a component of a page, an `int` variable of `program.nx`, a system variable (`dim`, `baud`, ...), or a keyword.

## Local variables

```
on save.up:
  var total = first.val + second.val * 2
  var label = "Total: " + total
  t0.txt = label
```

`var` declares a local variable for the rest of the event.

- Its first value decides whether it stores a number or a text.
- A `click` that runs another event cannot change it.
- If your code reads a local where its `var` line did not run, for example one declared inside an `if` that was skipped, the local has whatever value another event or function last left there.
- A local's name follows the same rules as a constant's, with one exception: it may share a component's name ([Names](#names)).

## Functions

```
function toFixed(value: text) -> number:
  var whole = 0
  ...
  return whole * 1000 + part

function showError(message: text):
  error.txt = message
  vis error,1

on save.up:
  fixed.val = toFixed(t0.txt) + 1
  showError("No paper")
```

A function belongs to one page. It is written in the page's `.nx` file, between events, with its body indented like an event's.

- Parameters are `number` or `text`. `-> number` or `-> text` gives a result. A function without a result is called as a statement.
- A function with a result ends with `return <expression>`, as its last line and outside any block. `return` can go nowhere else, in a function or in an event.
- A call can go anywhere an expression can. A function with a result can also be called as a statement, and its result is then not used.
- Arguments are converted as assignments are: a number passed for a text becomes its digits. A text passed for a number is refused.
- A function may call other functions, but never itself, directly or through others. Each function has one set of variables, which a second call would overwrite.
- A function's name follows the rules for a constant's.
- A function may contain a `goto` and labels, as an event may. A `goto` goes to a label of its own function.
- A comment right above a `function` line stays in the source. An event's comment, right above its heading, is copied into the Nextion Editor as the event's first lines ([Comments](source-folder.md#comments)), but a function's is not.
- `program.nx` cannot call functions. It can `call` a macro, but only one that does not use `click`, directly or through the macros it calls. `program.nx` belongs to no page, so the build could not tell which event such a `click` runs.
- nxlang code can `call` a macro ([Macros](source-folder.md#macros)). The build counts what the macro runs, so the macro and what it runs come under the [Limits](#limits) on calls and clicks.

Hand-made functions keep working too: a hidden component whose event you run with `click`. Each `click` must give its component and 0 or 1, and the clicks must not come back to an event already running ([Limits](#limits)).

## `break`, `continue`, and `switch`

```
while (i.val < 10) {
  i.val++
  if (skip.val == i.val) {
    continue
  }
  if (found.val) {
    break
  }
  total.val += i.val
}

switch (mode.val) {
  case 1:
    t0.txt = "one"
    break
  case 2:
  case 3:
    t0.txt = "two or three"
    break
  default:
    t0.txt = "other"
}
```

They work as in C:

- `break` leaves the innermost `while`, `for`, or `switch`.
- `continue` goes to the next pass of the innermost loop. A `for` loop runs its step first.
- `switch` computes its value once. The value can be a number or a text.
- Each `case` gives a number, a text, or a constant of the same kind, each value once.
- `default:` is optional, at most one, and can come anywhere.
- A case without `break` falls through into the next one.
- `continue` inside a `switch` goes to the next pass of the loop around it.
- Code between `switch (...) {` and the first `case` could never run, so it is refused.

These words count only in their own forms: `switch (`, `case <value>:`, `default:`, and `break` or `continue` alone on a line. A component may keep such a name, as in `case.val = 1`. A constant, local, function, or parameter may not.

## Includes

```
include "lib/fixed.nx"
include "home/keypad.nx"
const LIMIT = 40

on save.up:
  fixed.val = toFixed(t0.txt)
```

A `.nx` file can include others: a library of functions shared by pages, or parts of one large page split into files.

- `include "<path>"` lines go at the top of a file, with its constants. The path is relative to the file containing the line, ends in `.nx`, and stays inside the source folder. `lib/` is only a habit for shared code.
- An included file has the same form as a page's file: includes and constants at the top, then functions and events. It may include other files. A page takes each file once, however often it is included.
- An event in an included file belongs to each page that includes it, and must use that page's components.
- The same event in two of a page's files is refused. So is a constant or a function defined twice.
- A page gets only the functions it calls, directly or through other functions, wherever they are defined. The rest of a library costs it nothing. Constants cost nothing either.
- Every function is still checked, so a mistake in a library shows on every page that includes it. Errors give the file and line they come from, such as `pages/lib/fixed.nx line 12`.
- Which components exist is checked only in the code a page uses ([Names](#names)). So one file can contain a function for each page, each using its own page's components.
- A library function that uses a constant only some pages define fails on the other pages. A library should define what it needs.
- Each page runs its own copy of a function, with its own variables. State shared between pages goes in `program.nx`'s `int` variables.
- `program.nx` may include files of constants only.

## Names

A name on its own, without a dot, must be a constant, a local, an `int` variable declared in `program.nx`, or a system variable. Anything else stops the build with "unknown name". That catches a misspelt constant.

A name with a dot must be something that exists, as in strict Nextion syntax ([Names that must exist](build-rules.md#names-that-must-exist)): `t0.txt` a component of the page, and `settings.t0.txt` a component of another page, after its page's name.

A local or a function's parameter may share a component's name:

- Without a dot, the name is the local. With one, such as `units.txt`, it is the component.
- This also applies in command arguments. So a function that also needs the component without a dot, as in `vis units,0`, must give its local another name.
- This rule exists because a library function cannot know which components the pages including it have, now or later. A new component could otherwise break it.

Names starting with `__`, two underscores, are kept for the compiler's own variables and components. No `int` of `program.nx`, constant, function, parameter, local, or component of a page in nxlang may use one. A single `_` is yours to use.

## Limits

The build writes your nxlang into strict Nextion syntax, adding hidden variables and components where the Nextion Editor needs them ([nxlang-compiled.md](nxlang-compiled.md)). That brings some limits:

- **256 objects per page.** The compiler adds a few objects of its own to a page: text variables for text worked out on the way, and a hidden hotspot for each depth of functions. The build stops if a page would need more than 256 objects.
- **At most 7 calls and clicks in a chain.** A chain is a run of calls and clicks, such as an event, a function it calls, and a function that one calls. A macro's `call` counts as one level of the chain too. The screen runs events at most 9 deep, and the event a press or a timer runs is the first level. One level is kept free for a `page` command, which runs the new page's `load` event inside the current one. The build refuses a longer chain. Its message shows the chain, call by call.
- **A hand-made `click` must give its component and 0 or 1**, as in `click b0,1`. 1 runs the component's Touch Press event, and 0 its Touch Release event. The build refuses any other form, such as `click b[3],1` or `click b0,n.val`, since it could not tell which event runs. In a macro that nxlang code calls, a `click` gives the component's ID instead, as in `click 3,1`.
- **No call or click may come back to an event, function, or macro already running**, such as two events clicking each other. An event or a function has one set of variables, which the second run would overwrite. For a macro, the build could not count how deep it nests.
- **Text worked out on the way keeps up to 255 characters.** For example, in `print "Total: " + t0.txt`, the joined text is cut after 255 characters, where the Nextion Editor would refuse the line.
- **At most 8,000 hidden globals.** That many are known to work. The build stops past that.
- **`program.nx` has no hidden variables, and no locals.** An expression there that would need a hidden variable stops the build: write it as simpler steps. So does a text assignment that uses its own target anywhere but first, such as `t0.txt = "-" + t0.txt`.
- **A page with functions needs its `load` event.** The build turns off the touches of the hidden hotspots there. The `load` event is listed by default.
- **A data record's call takes a number for a number.** A text given for a number is refused. A number given for a text becomes its digits.
- **What the Nextion Editor refuses is refused in nxlang too.** An escape the screen does not read, such as `\n` in a quoted text, a variable's `val` while it stores a text, or a command given another number of arguments than it takes, is written as it is, and the build refuses it ([build-rules.md](build-rules.md)).
- **The form `'&name&'` works only in an event's code** ([`'&name&'`](build-rules.md#name-an-attribute-of-the-events-own-object)). The build refuses it elsewhere:
  - in a function, because a function's body runs from a hidden hotspot, so the form would give the hotspot's attributes;
  - in a constant, because a constant's text goes into every line that uses the constant, even outside an event;
  - in `program.nx`, which belongs to no event, and where the Nextion Editor refuses it too.

## Extracting from the Nextion Editor

Extracting keeps the source of every event whose compiled code the Nextion Editor did not change, as it does for comfortable code. The compiler's hidden variables are left out of the page files.

- An event the Nextion Editor changed takes the Nextion Editor's code, with the parentheses that keep its meaning.
- The Nextion Editor's `x-=a+b` computes `(x-a)+b`. nxlang reads `x -= a + b` differently, so extracting writes the Nextion Editor's line as `x=x-a+b`. That computes the same, and builds to `x=x-a+b`.
- The Nextion Editor reads a hexadecimal number written `0X10` as `0x10`, the only way nxlang writes one. So extracting, and switching to nxlang, write it `0x10`.
- An event that was compiled from nxlang uses hidden variables. If the Nextion Editor changed it, extracting stops. Its message shows which event. Make the change in the source folder instead. The same goes for a function's body, in the event of its hotspot.
- Extracting compares the Nextion Editor's code with what the current nxwright compiles. After nxwright changes how it compiles, build the project once before its next extract. Otherwise extracting takes every compiled event for a change made in the Nextion Editor, and stops.
- The `tsw` lines at the start of a page's Preinitialize event are left out. The build adds them again.
- An event the Nextion Editor changed is rewritten in the file that contains it, which may be an included file. An event it emptied is removed from that file. An event it added goes into the page's own file. Included files are never deleted.
- A file with events included by several pages changes only where the Nextion Editor left them the same on every page. If an event differs between the pages, extracting stops, since writing either version would change the other pages' build. Its message shows which event.
- The constants of `program.nx` and of each page's `.nx` file are kept.
- A component added to a page in the Nextion Editor comes after the compiler's hidden variables. Extracting removes those, so the new component's ID moves down to where the next build puts it.
