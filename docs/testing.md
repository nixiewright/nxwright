# Testing your app

Your screen's code normally runs only on the screen, or by hand in the Nextion Editor's simulator. With nxwright, you can run automated tests on your computer. A test compiles a page of your source folder, and runs its events from the values you give. Then it checks the values they leave, what they sent on the serial line, or which page they opened.

Tests are ordinary Python `unittest` tests. They run in seconds, and in any continuous integration.

## A first test

```python
import unittest

from nxwright.testing import SourceFolderRunner

# Runs the code of the source folder "app".
SCREEN = SourceFolderRunner("app")


class SettingsPageTest(unittest.TestCase):

    def test_save_writes_the_step(self):
        # On the page "settings", run the page's load event, then release the
        # button "save". The number "step" starts at 5.
        values = SCREEN.run("settings", [("settings", "load"), ("save", "up")],
                            {"step.val": 5})
        # The text "stepText" now shows the step.
        self.assertEqual(values["stepText.txt"], "5")
        # Saving went back to the page "main".
        self.assertEqual(values["page opened"], "main")
```

`run` compiles the page `settings`, as the build does. Then it runs the events in the order given: here, the page's Preinitialize event, then the Touch Release event of its component `save`.

Values are named as the code names them: `step.val`, `stepText.txt`, `sys0`.

## Running tests

Put your tests in a folder of their own, in files named `test*.py`. Then run them:

```
nxwright test <folder> [-k <pattern>] [--list] [--report <file>]
```

- The folder is the top of the import path. So a test can import the folder's other modules by name alone, and shared helpers can live in a module beside the tests.
- `-k` runs only the tests whose name matches the pattern. You may give it more than once.
  - Plain text matches anywhere in the name: `-k fahrenheit` runs `test_fahrenheit` and `test_choosing_fahrenheit_then_celsius`.
  - If the pattern contains `*`, it must match the whole name, `module.Class.method`, and `*` stands for any text: `-k "test_home.*"` runs every test in `test_home.py`.
- The command exits with 1 when a test fails.
- Testing a folder without tests returns an error, and so does a `-k` that no test matches.

Two options are for code editors:

- `--list` prints the ID of each test it would run, such as `test_home.TargetTest.test_raising_holds_the_target`. No test runs.
- `--report <file>` also writes each test's result to the file, as JSON:
  - `id`;
  - `outcome`: `passed`, `failed`, `error`, or `skipped`;
  - for a test that did not pass: its `message`, and the `file` and `line` of the test's code where it stopped.

## The values a run starts from

A run starts from:

- the `values` you give;
- the `int` variables of `program.nx`, each at the value it declares, or 0;
- the hidden variables that the nxlang compiler adds, at 0 or `""`;
- `dp`, the current page's number.

When the code reads a value that you did not give, the run stops with the error `ValueNotGiven`, which gives the line that read it. This shows what a test forgot to set, such as `pages/lib/room.nx line 50 (minutesNow): rtc3 has no value. In a test, give it in the run's values`. If you pass `blank_fields=True`, every other `.val` and `.txt` of a component that the code names starts at 0 or `""` instead. A system variable that the code reads, such as `dim` or the clock's `rtc3`, must still be given, as the demo's tests give them.

nxwright also reads your page file, but your code doesn't see its values. Only the values you give count: a value you didn't give still stops the run.

The test runner uses the page file the same way the simulator does:

- To know each component's type. So a test ignores what the simulator ignores, such as a file stream's position below 0, even when you don't give the type.
- To work out list components as your code changes them ([Lists](#lists)), and to run a data record's methods.

## Lists

A test starts from the page as it opened, as the simulator opens it. Before your events run:

- each file browser lists its folder;
- each sliding text works out how far it scrolls;
- each data record reads its data file from `"file contents"`, the test's SD card. If the file doesn't exist and the data record's `mode` is 1, the test creates a new data file in `"file contents"`, with no records.

Then the values you give are set again, so they win over what was worked out.

When your code sets an attribute of a list component, a test works out what follows, as the simulator does. Your code can then read what was worked out, and `run` returns it.

- A file browser's new `dir` lists its folder, and sets `qty`, `val` -1, `txt` empty, and `maxval_y`. `up()` goes to the folder above, and lists it. Its `val` gives `txt` the name of that entry. The folders are those of `"file contents"` and `"existing"`.
- A select's `val` gives `txt` its line of `path`.
- A sliding text's new `txt` or `font` works out its `maxval_y`, in your folder's font. Its `val_y` stops where code may scroll it.
- A combo box's `val` gives `txt` its item. A `val` past its last item goes back to the item chosen before.
- A data record's `val_y` stops 32 pixels past `maxval_y`, and its `val_x` at `maxval_x`. A new `format`, `hig`, `gdw`, or `gdh` works out its `qty`, `txt`, and both `maxval`s again from its file, in `"file contents"`.

## What a test can check

`run` returns the values the events leave. A component's value has the same name as in your code: `values["stepText.txt"]`.

What the code does outside the page is recorded among the values too, under names that no component can have:

| Value | What it contains |
| --- | --- |
| `"page opened"` | The page that a `page` command opened. |
| `"vis <name>"` | Whether a `vis` command showed (1) or hid (0) `<name>`. `<name>` is the component's name, even where the code gave its ID. |
| `"touch <name>"` | Whether a `tsw` command turned `<name>`'s touches on (1) or off (0). `<name>` is the component's name, even where the code gave its ID, or 255 for every component. |
| `"sent"` | What `prints`, `printh`, and `rdfile` sent on the serial line, as a list. `rdfile` sends `("rdfile", bytes)`. |
| `"replies"` | What the screen sent in answer: `("get", value)`, `("sendme", page number)`, and `("rept", bytes)`. |
| `"waveform"` | The points `add` put on a waveform, and the channels `cle` cleared, in order: `("add", id, channel, value)` and `("cle", id, channel)`. |
| `"painted"` | What drawing commands painted, in order. Each is its command and its computed arguments, such as `("fill", 0, 0, 50, 50, 63488)`. |
| `"file contents"` | The files on the SD card, as `{path: bytes}`. You may give them. Without them, the card starts empty. |
| `"existing"` | Paths that `findfile` and `finddir` find, besides the files of `"file contents"`. You give it. |
| `"file commands"` | The commands that changed files, in order. |
| `"file errors"` | The file commands the screen ignored, in order, as `(command, path)`. For example, a read or write past the file's end, a read or write with no file open (its path is `None`), a `newfile` whose size is not a number or is below 0, and a `twfile` the screen refused. When code sets a data record's `path` to a file it cannot open, the entry is `("open", path)`. A data record cannot open a file that another data record keeps open, or any new file while other data records keep 8 files open. |
| `"data files held"` | The files data records keep open, as `{file: (page, data record)}`. The first data record to open a file keeps it ([Data records](screen-code.md#data-records)). |
| `"data records shut out"` | The data records that could not open their file, as `{(page, data record): True}`. They read no records from it until they open a file. |
| `"data records given a path"` | The data records whose `path` was set by code, as `{(page, data record): True}`. A data record whose `init` is 1 opens no file until code sets its `path`. |
| `"file browser listings"` | What each file browser lists, as `{(page, file browser): [names]}`, a folder's name ending with `/`. Its `val` picks from it. |
| `"combo box choices"` | Each combo box's last `val` within its items, as `{(page, combo box): number}`. |
| `"open file <name>"` | The file that the file stream `<name>` has open. |
| `"text limits"` | The sizes of texts that the page files do not give: their `txt_maxl`, or another attribute's bound, as `{"t0.txt": bytes}`. You give it. These sizes are added to those the page files give. |
| `"component errors"` | Each `click`, `vis`, `tsw`, or `ref` that gave a component by an ID no object of the page has, in order, as `(command, its argument as written)`. |
| `"refusals"` | Each other line the running screen ignored, in order, as `(return code, line as written)`. For example, a number its attribute does not take ([screen-code.md](screen-code.md#numbers-an-attribute-takes)). |
| `"eeprom"` | The EEPROM's 1024 bytes. You may give them. Without them, the EEPROM starts empty. |
| `"serial buffer"` | The bytes of the buffer of protocol reparse mode, which `u[]`, `usize`, `ucopy`, and `udelete` read and change. To start with bytes in it, give them in the run's values, with `recmod` set to 1 ([Protocol reparse mode](screen-code.md#protocol-reparse-mode-u-usize-ucopy-and-udelete)). |
| `"eeprom accesses"` | Each `wepo` and `repo`, in order: `("wepo", address, bytes written)` and `("repo", address, value read)`. |
| `"gpio"` | `cfgpio`, as `("cfgpio", pin, mode, component)`, and each write and read of `pio0` to `pio7`, `pwm4` to `pwm7`, and `pwmf`, as `("write", name, value)` and `("read", name, value)`. |
| `"rand range"` | What `randset` set. |
| `"reset"` | 1, once `rest` ran. |
| `"other commands"` | The commands recorded but not otherwise run, and `move`, as they ran. |

- `print` is recorded in `"sent"` as `prints` with a length of 0: it sends the same bytes.
- Reading `rand` gives the value of `"rand"` that you set.

How each command runs, and what it records, is in [How nxwright runs Nextion code](screen-code.md).

## What a test does not do

- Nothing runs by itself. A timer's event runs when the test runs it. Touches are the events the test gives.
- Nothing is drawn. Attributes that change the look, such as `pco` or `pic`, are values like any other. Drawing commands are recorded.

To run the app as a whole, with timers, touches, and drawing, use the simulator ([Simulating your app](simulator.md)).

## SourceFolderRunner

Your tests use a `SourceFolderRunner` to run your screen's code. It compiles your pages, runs their events, and returns the values they leave.

Make one for your source folder (for instance, as `SCREEN` like in [A first test](#a-first-test)). Then each test calls its methods, such as `SCREEN.run(...)`.

To share one runner between your test files, make it in a module beside them. The demo's `tests/screen.py` does this:

```python
from pathlib import Path

from nxwright.testing import SourceFolderRunner

APP = Path(__file__).resolve().parent.parent / "app"
SCREEN = SourceFolderRunner(APP)
```

Each test file then imports it with `from screen import SCREEN`.

For code that types Chinese with `pa_q` and `pa_txt`, give it the screen's pinyin table: `SourceFolderRunner(<source-folder>, pinyin_table=<file>)`. The file can be either:

- `input.bin`, in the Nextion Editor's installation folder.
- Any TFT file, such as one you built from your project. Every TFT file contains a copy of the table. Use one on a computer without the Nextion Editor, such as a continuous integration server.

A test never looks for an installed Nextion Editor, so its result does not depend on the computer it runs on.

### `run(page, events, values=None, text=None, blank_fields=False)`

Runs `events` in turn, and returns the values they leave.

- `events` is a list of (component, event) pairs.
- Events are named as in `.nx` files: `load`, `loadend`, `down`, `up`, `unload`, `timer`, `slide`.
- `values` are the values to start from ([The values a run starts from](#the-values-a-run-starts-from)).
- `text` runs the page with other code in place of its `.nx` file.
- `blank_fields=True` starts every component's `.val` and `.txt` you did not give at 0 or `""`.

### `compile(page, text=None, blank_fields=False)`

Returns each event's code in strict Nextion syntax, and the values `run` starts from. The result is shared between runs: do not change it.

### What `run` and `compile` refuse

`run` and `compile` build the page first, as the build does. If the build would refuse the page's code, such as code using a component the page does not have, they stop with an error before any event runs. The test then reports that error, with the file and the line the build refused, as `pages/home.nx line 12:`.

For code given as `text`, they do not check the components used. That code may be an older version, with components the page no longer has.

Code that nxwright refuses as it runs, such as a loop that does not end, stops the run with the error `RefusedCode` ([screen-code.md](screen-code.md#code-that-nxwright-refuses)). Your test then shows as an error, not as a failure. The error starts with the line's file, number, and event, as `pages/home.nx line 12 (home.load):`.

### `run_code(code, values=None, include=None)`

Runs a few lines of nxlang. See [Testing nxlang functions](#testing-nxlang-functions).

### `events_from_text(text)`

Takes the text of a `.nx` file written in Nextion's own language, not nxlang, and returns each event's code in strict Nextion syntax. You can run that code with `EditorMachine` ([Running code directly](#running-code-directly)).

Use it to compare a page with an older version of its code, such as a copy kept from before the page moved to nxlang.

The text belongs to no page. So it refuses a line using the form `'&name&'` outside a quoted text ([build-rules.md](build-rules.md#name-an-attribute-of-the-events-own-object)).

### Compiled pages are cached

Compiling is the slow part of a test, and many tests run the same page. So nxwright caches each compiled page for the rest of the run.

The cache lives in memory only, and is never written to disk. Each run of your tests starts with an empty cache. If a test changes one of your source files during the run, nxwright notices, and compiles the page again.

## Testing nxlang functions

`run_code(code, values=None, include=None)` runs a few lines of nxlang as the only event of a page of its own. That page includes the file `include`, relative to the `pages` folder, such as `"lib/units.nx"`.

```python
values = SCREEN.run_code("r.val = clamp(40, 0, 30)", {"r.val": 0}, "lib/numbers.nx")
self.assertEqual(values["r.val"], 30)
```

This tests a library's functions: the code calls them, and its values show the results. The demo's `tests/test_library.py` tests its library this way.

- Only a folder in nxlang has functions, so `run_code` only works in a folder in nxlang.
- The code given to `run_code` is not checked as a page's code is, since its page has no components of its own.

## Debugging a test

nxwright's VS Code extension can debug a test: both its own Python, and the screen code it runs.

Test Explorer lists the tests of each folder named `tests` beside a source folder. You can run or debug them from Test Explorer. A "Debug test" link also stands above each test method.

The debugger runs the test first, and records each line of its Python and each statement of screen code it runs. Then it moves through the recording. So it can step backward as well as forward.

### Stepping

- You can set breakpoints on lines of `.nx` files, and of the Python files of the folder of tests.
- You can continue, step over, step into, step out, step back, and reverse continue.
- A step goes from one source line to the next, however many lines of strict Nextion syntax that line compiled into.
- The test's own lines are steps too, `setUp`, `tearDown`, and the helper modules beside it included. nxwright's own code and the standard library are not.
- A line that calls `run` runs screen code. Step over goes to the test's next line. Step into enters the screen code, and step out comes back.
- `run_code`'s own lines belong to no file, so they are not stepped through. Only the functions they call are.
- Moving past the recording's last step ends the session.

### The Call Stack view

VS Code's Call Stack view lists what is running, innermost first:

- the event, the functions it calls, the events its clicks run, and the macros its calls run;
- then a label for the run;
- then the test's own functions.

### The Variables view

VS Code's Variables view shows the values in groups:

- **Locals:** the locals and parameters of the event or function, under their nxlang names, and a function's result as `(result)`. In the test's Python, its locals, shown as text. A list, tuple, or dict opens to its first 100 entries.
- **Page:** the components' values.
- **Program:** the `int` globals, and the system variables.
- **Outside the page:** what the run records outside the page, such as `sent` ([What a test can check](#what-a-test-can-check)).
- **Generated:** the variables the compiler adds.

At a line of the test, the groups other than Locals show what the last run left. That is what the test's assertions read.

### Failures

A test that fails, or stops with an error, stops the debugger where it did, as an exception does. This happens even while stepping over that line.

- A failing assertion stops on its line.
- A run that stops with an error, such as a value the test did not set, stops on its statement.

### Long tests

A test that runs more than a million lines and statements stops with an error while it is debugged: a recording that long is no use to step through. Recording its Python also makes it slower.

## Running code directly

`EditorMachine` runs code in strict Nextion syntax without a source folder. Use `EditorMachine` for advanced cases, such as comparing a page with an older version of its code ([`events_from_text`](#events_from_texttext)).

```python
from nxwright.testing import EditorMachine

machine = EditorMachine({"n0.val": 2})
values = machine.run(["n0.val=n0.val*3"])
```

`EditorMachine(values, events=None, page=None, macros=None)`:

- `machine.run(lines)` runs a list of code lines, and returns the values. A line that nxwright cannot read, such as `sys0 = = 2`, stops the run with `UnreadableLine`, a kind of `RefusedCode`.
- `events` maps (component, `"down"` or `"up"`) to the code a `click` runs.
- `macros` maps a macro's name to (its code lines, `None`), which a `call` runs.
- `page` lets the code give its own page's components as `page.component.attribute`.
- `pinyin_table` gives the screen's pinyin table, as for `SourceFolderRunner`.

For the debugger, `EditorMachine` also takes:

- a `recorder` (`nxwright/testing/recording.py`), which it tells of each statement before running it;
- the `places` of the lines of `events`. `run(lines, places)` takes the places of its own lines.

A place is the file, line, and event or function that a line of strict Nextion syntax comes from. Without a recorder, places are not used.
