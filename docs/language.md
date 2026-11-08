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

See [nxlang-compiled.md](nxlang-compiled.md) for the code the build writes from nxlang.

## Switching to nxlang

A folder extracted from a project starts in strict Nextion syntax, which is `language = "nextion_do_not_change_manually"` in `app.toml`. Its `.nx` files can still use spaces and braces that the Nextion Editor does not accept ([Comfortable code](source-folder.md#comfortable-code)), but they cannot use any of the extended nxlang syntax. To switch the folder to nxlang, run:

```
nxwright language <source-folder> nxlang
```

Always switch with this command, and never by changing the `language` line in `app.toml` by hand. The two languages read some code differently: the Nextion Editor computes `a+b*c` strictly from left to right, as `(a+b)*c`, while nxlang uses the more usual precedence, as `a+(b*c)`. If you only changed the setting, that line would compute something else, with no warning. The command instead rewrites every line that the two read differently, adding the parentheses that keep the Nextion Editor's meaning: `(a+b)*c`. It also writes a hexadecimal number such as `0X10` as `0x10`, the only form nxlang has.

- The rewritten code builds to exactly the same project. If any code would not, the command stops before writing anything.
- There is no command to switch back. If you must, build the project, then extract it into a new folder. That folder is in strict Nextion syntax and builds the same project, but it contains the code the build wrote, with the compiler's hidden variables and hotspots ([nxlang-compiled.md](nxlang-compiled.md)), instead of the nxlang you wrote.

In VS Code, "Switch the source folder to the nxwright language" shows what nxlang adds and each line the switch will rewrite, before you make it. The switch is one edit, so one undo takes it back.

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

The order is the same as in C, so `a & 1 == 1` means `a & (1 == 1)`, which the build refuses. Write `(a & 1) == 1`.

### Numbers

Numbers are 32-bit, and behave as on the screen:

- Division rounds toward zero: `-7/2` is `-3`.
- The remainder takes the sign of the left side: `-7%2` is `-1`.
- `>>` keeps the sign: `-8>>1` is `-4`.

Hexadecimal numbers are written as in C: `0x1F`, `0x1`, `-0x10`.

- A value from `0x80000000` to `0xFFFFFFFF` is negative: `0xFFFFFFFF` is -1.
- The Nextion Editor reads fewer forms ([Hexadecimal numbers](build-rules.md#hexadecimal-numbers)), so the build rewrites the others: `0x1` as `0x01`, `-0x10` as `-16`, and an `int`'s starting value in decimal.

A number that does not fit in 32 bits keeps only its low 32 bits, as in C, and `nxwright check` warns you about it. For example, the build writes `0x0100000005` as `0x00000005`, and `4294967295` as `-1`. The build leaves the arguments of `printh`, `crcputh`, and `lcd_dev` as they are, because they are bytes.

### Text

- `+` joins text. A number joined to text becomes its digits first: `t0.txt = "Speed: " + speed.val + " mm/s"`.
- Putting a number into a text also gives its digits: `t0.txt = n0.val`.
- `t0.txt -= 2` removes the last two characters.

### Assignments and conditions

- `x -= a + b` means `x = x - (a + b)`.
- The conditions of `if`, `else if`, `while`, `for`, and `? :` can contain any expression. They can mix `&&` and `||`, and use `!`.
- A plain number counts as true when it is not 0: `if (flag.val)`.
- Texts compare with `==` and `!=` only.
- `&&` and `||` evaluate their right side only when needed, as in C. So `b != 0 && a / b > 1` never divides by 0. In `ready.val == 1 && save() == 1`, `save` runs only when `ready.val` is 1.
- `? :` chooses a value, as in C, and runs only the chosen side: `t0.txt = ready.val ? "Ready" : "Waiting"`. Both sides must be numbers, or both must be texts. You can use `? :` in a command only as the first argument of `get`, `print`, `prints`, or `covx`. For any other command, such as `vis`, put the value in a local first.

## Constants

```
const SPEED_LIMIT = 1200
const UNIT = " mm/s"
```

A constant's value is a number or a text. The build replaces each use with the value.

- Constants for one page go at the top of its `.nx` file, before the first `on` heading.
- Constants for every page go anywhere in `program.nx`, or in the `[defines]` table of `app.toml`, where a build can change their values with `--define` ([source-folder.md](source-folder.md#apptoml)).
- A constant cannot share its name with another constant, a component of a page, an `int` variable of `program.nx`, a system variable (`dim`, `baud`, ...), or a keyword.

## Local variables

```
on save.up:
  var total = first.val + second.val * 2
  var label = "Total: " + total
  t0.txt = label
```

`var` declares a local variable for the rest of the event.

- A local's first value decides whether it stores a number or a text.
- A `click` that runs another event cannot change a local.
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

A function belongs to one page. It is written between events, in the page's `.nx` file or in a file the page includes ([Includes](#includes)), with its body indented like an event's.

- Parameters are `number` or `text`. `-> number` or `-> text` gives a result. A function without a result is called as a statement.
- A function with a result ends with `return <expression>`, as its last line and outside any block. `return` cannot go anywhere else, in a function or in an event.
- A call can go anywhere an expression can. A function with a result can also be called as a statement, and its result is then not used.
- A number passed for a text becomes its digits, but a text passed for a number is refused.
- A function may call other functions, but never itself, directly or through others. Each function has one set of variables, which a second call would overwrite.
- A function's name follows the rules for a constant's.
- Labels and `goto` work in a function too, but a `goto` can only go to a label in the same function.
- A comment right above a `function` line stays in the source, and is not copied into the Nextion Editor. An event's comment is copied ([Comments](source-folder.md#comments)).

nxlang code can also `call` a macro ([Macros](source-folder.md#macros)). The macro and whatever it runs count toward the [Limits](#limits) on calls and clicks.

`program.nx` cannot call functions. It can `call` a macro, but only one that does not use `click`, directly or through the macros it calls. `program.nx` belongs to no page, so the build could not tell which event such a `click` runs.

Hand-made functions keep working too: a hidden component whose event you run with `click`. The [Limits](#limits) on `click` apply to them.

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

`break`, `continue`, and `switch` work as in C, and a `switch` can also compare texts. Each `case` gives a number, a text, or a constant of the same kind, each value once. Code between `switch (...) {` and the first `case` could never run, so it is refused.

`switch`, `case`, `default`, `break`, and `continue` are keywords only in these forms: `switch (`, `case <value>:`, `default:`, and `break` or `continue` alone on a line. A component can still have one of these names, as in `case.val = 1`, but a constant, local, function, or parameter cannot.

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
- A page gets the events of the files it includes, as if they were in its own file. For example, `on b0.up:` in a shared file defines the `up` event for `b0` on every page where it is included.
- If such a file is included in a page that does not have a `b0` component, a warning is issued ([Warnings](commands.md#warnings)). If the page leaves out `b0` on purpose, write `partial` after the path, as in `include "lib/buttons.nx" partial` to disable the warning.
- If a page must have every component the file has events for, write `strict` after the path, as in `include "lib/buttons.nx" strict`. A missing `b0` then stops the build instead of giving a warning.
- The same event in two of a page's files is refused. So is a constant or a function defined twice.
- A page gets only the functions it calls, directly or through other functions, wherever they are defined. The rest of a library costs it nothing. Constants cost nothing either.
- Every function is still checked, so a mistake in a library shows on every page that includes it. Errors give the file and line they come from, such as `pages/lib/fixed.nx line 12`.
- The build checks that components exist, but only in the code a page uses ([Names](#names)). One file can therefore contain a function for each page, using that page's components.
- A library function that uses a constant only some pages define fails on the other pages. A library should define what it needs.
- Each page runs its own copy of a function, with its own variables. State shared between pages goes in `program.nx`'s `int` variables.
- `program.nx` may include files of constants only.

## Names

A name on its own, without a dot, must be a constant, a local, a function's parameter, an `int` variable declared in `program.nx`, or a system variable. Anything else stops the build with "unknown name". That catches a misspelt constant.

A name with a dot must refer to something that exists ([Names that must exist](build-rules.md#names-that-must-exist)). `t0.txt` is a component of the page, and `settings.t0.txt` is a component of the page `settings`.

Code cannot use a component whose name contains anything other than letters, digits, and `_`, such as `b 0`. Only the headings of that component's events can give its name, in quotes ([Code files](source-folder.md#code-files)).

A local or a function's parameter may share a component's name, so that a new component on a page cannot break a library function that uses the same name.

- Without a dot, the name is the local, even in a command's arguments. With a dot, as in `units.txt`, it is the component.
- A function that also needs the component without a dot, as in `vis units,0`, must give its local another name.

Names starting with `__`, two underscores, are kept for the compiler's own variables and components. No `int` of `program.nx`, constant, function, parameter, local, or component of a page in nxlang may use one. A single `_` is yours to use.

## Limits

The build writes your nxlang into strict Nextion syntax, adding hidden variables and components where the Nextion Editor needs them ([nxlang-compiled.md](nxlang-compiled.md)). That brings some limits:

- **250 components per page.** The Nextion Editor allows 250, and the few components the compiler adds to a page count toward that limit. The build stops if a page would need more.
- **At most 7 calls and clicks in a chain.** For example, an event that calls a function, which calls another function, is a chain of 2. A macro's `call` counts too. The build refuses a longer chain. The limit comes from the screen, which runs events at most 9 levels deep. The event that a press or a timer runs is the first level, and one level is kept free for a `page` command, which runs the new page's `load` event inside the current one. That leaves 7.
- **A hand-made `click` must give its component and 0 or 1**, as in `click b0,1`. The build refuses any other form, such as `click b[3],1` or `click b0,n.val`, because it could not tell which event runs. In a macro that nxlang code calls, a `click` gives the component's ID instead, as in `click 3,1`.
- **No call or click may come back to an event, function, or macro already running**, such as two events clicking each other. An event or a function has one set of variables, which the second run would overwrite. For a macro, the build could not count how deep it nests.
- **A text that nxlang keeps for you has room for 255 bytes.** This is true of a local, a parameter, a function's result, and a joined text, such as a side of a comparison. A longer text is cut. For example, in `if (t1.txt == "Total: " + t0.txt)`, only the first 255 bytes of the joined text are compared.
  - **The exception is a quoted text longer than 255 bytes.** nxlang knows its length, so it gives the text the room it needs.
  - **nxlang does not give more room to a text whose length it cannot know in advance**, such as a component's text, because the screen has little memory. A text built from short texts with several `+=` also has room for only 255 bytes.
  - **You get a warning where a component's text may be cut.** `nxwright check` and the live checks warn on the line (`text-cut`) when a component's text, or a variable that nxlang gave more room, may not fit in one of these texts. For example, `if (t1.txt == "Total: " + t0.txt)` gives a warning when `t0`'s `txt_maxl` is 1000.
  - **To keep a longer text, put it in a variable component** whose `txt_maxl` is large enough.
  - A `print` of joined texts keeps every part whole, because it prints each part in turn.
- **At most 8,000 hidden global variables.** That many are known to work, and the build refuses more.
- **`program.nx` has no hidden variables, and no locals.** The build stops at an expression there that would need a hidden variable, so write it as simpler steps. It also stops at a text assignment that uses its own target anywhere but first, such as `t0.txt = "-" + t0.txt`.
- **A page with functions needs its `load` event.** The build turns off the touches of the hidden hotspots in that event. A page file's `events` list contains `load` by default.
- **The build refuses a text given for a number in a data record's call.** A number given for a text becomes its digits.
- **What the Nextion Editor refuses is refused in nxlang too** ([build-rules.md](build-rules.md)). That includes an escape the screen does not read, such as `\n` in a quoted text, a variable's `val` while the variable stores a text, and a command given the wrong number of arguments.
- **The form `'&name&'` works only in an event's code** ([`'&name&'`](build-rules.md#name-an-attribute-of-the-events-own-object)). The build refuses it elsewhere:
  - in a function, because a function's body runs from a hidden hotspot, so the form would give the hotspot's attributes;
  - in a constant, because a constant's text goes into every line that uses the constant, even outside an event;
  - in `program.nx`, which belongs to no event, and where the Nextion Editor refuses it too.

## Working with the Nextion Editor

You can open the project file nxwright builds in the Nextion Editor and compile it there. Its pages are locked, to show that it is not meant for editing ([build](commands.md#build)). If you need to, you can easily unlock the pages in the Nextion Editor.

To see what changed in a project file, use `nxwright diff` ([diff](commands.md#diff)). To see what it contains, extract it into a new folder. The new folder is in strict Nextion syntax, and contains the code the build wrote, with the compiler's hidden variables and hotspots ([nxlang-compiled.md](nxlang-compiled.md)).
