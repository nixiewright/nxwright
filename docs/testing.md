# Testing your app

nxwright can run automated tests of your screen's code on your computer. A test compiles a page of your source folder, and runs its events starting from the values you give. Then it checks the values they leave, what they sent on the serial line, or which page they opened.

Tests are ordinary Python `unittest` tests, which run in seconds and work on any continuous integration server.

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

`run` compiles the page `settings`, then runs the events in the order given: here, the page's Preinitialize event, then the Touch Release event of its component `save`.

Values use the same names as your code: `step.val`, `stepText.txt`, `sys0`.

## Running tests

Put your tests in a folder of their own, in files named `test*.py`. Then run them:

```
nxwright test <folder> [-k <pattern>] [--list] [--report <file>]
```

- The folder is the top of the import path, so a test can import the folder's other modules by name alone, and shared helpers can live in a module beside the tests.
- `-k` runs only the tests whose name matches the pattern. You may give it more than once.
  - Plain text matches anywhere in the name: `-k fahrenheit` runs `test_fahrenheit` and `test_choosing_fahrenheit_then_celsius`.
  - If the pattern contains `*`, it must match the whole name, `module.Class.method`, and `*` stands for any text: `-k "test_home.*"` runs every test in `test_home.py`.
- The command exits with 1 when a test fails.
- You get an error if the folder has no tests, or if no test matches `-k`.

Two options let a code editor or another tool run your tests and read the results:

- `--list` prints the ID of each test that would run, such as `test_home.TargetTest.test_raising_holds_the_target`, without running any.
- `--report <file>` also writes each test's result to the file, as JSON:
  - `id`;
  - `outcome`: `passed`, `failed`, `error`, or `skipped`;
  - for a test that did not pass: its `message`, and the `file` and `line` of the test's code where it stopped.

## The values a run starts from

A run starts from:

- the `values` you give;
- the `int` variables of `program.nx`, each at the starting value the build writes for it, or 0;
- the hidden variables that the nxlang compiler adds, at 0 or `""`;
- `dp`, the current page's number.

If the code reads a value that you did not give, the run stops with the error `ValueNotGiven`, even if your page file would normally set that value. The error gives the line that read it:

```
pages/lib/room.nx line 50 (minutesNow): rtc3 has no value. In a test, give it in the run's values
```

If you pass `blank_fields=True`, every `.val` and `.txt` of a component that the code uses, and that you did not give, starts at 0 or `""` instead of stopping the run. You must still give any system variable that the code reads, such as `dim` or the clock's `rtc3`.

nxwright uses the page file for two things:

- To know each component's type, so that a test can ignore what the simulator ignores, such as a file stream's position below 0.
- To work out the attributes of list components as your code changes them ([Lists](#lists)), and to run a data record's methods.

## What a test can check

`run` returns the values the events leave, with each component's value under the same name as in your code. What the code does outside the page is recorded among them too, under names that no component can have:

| Value | What it contains |
| --- | --- |
| `"page opened"` | The page that a `page` command opened. |
| `"vis <name>"` | Whether a `vis` command showed (1) or hid (0) `<name>`. `<name>` is the component's name, even where the code gave its ID. |
| `"touch <name>"` | Whether a `tsw` command turned `<name>`'s touches on (1) or off (0). `<name>` is the component's name, even where the code gave its ID, or 255 for every component. |
| `"sent"` | What `prints`, `printh`, and `rdfile` sent on the serial line, as a list. An `rdfile` is recorded as `("rdfile", bytes)`. |
| `"replies"` | What the screen sent in answer: `("get", value)`, `("sendme", page number)`, and `("rept", bytes)`. |
| `"serial buffer"` | The bytes of the buffer of protocol reparse mode, which `u[]`, `usize`, `ucopy`, and `udelete` read and change. To start with bytes in it, give them in the run's values, with `recmod` set to 1 ([Protocol reparse mode](screen-code.md#protocol-reparse-mode-u-usize-ucopy-and-udelete)). |
| `"waveform"` | The points `add` put on a waveform, and the channels `cle` cleared, in order: `("add", id, channel, value)` and `("cle", id, channel)`. |
| `"painted"` | What drawing commands painted, in order. Each entry is the command and its computed arguments, such as `("fill", 0, 0, 50, 50, 63488)`. |
| `"file contents"` | The files on the SD card, as `{path: bytes}`. You may give them. Without them, the card starts empty. |
| `"existing"` | Paths that `findfile` and `finddir` find, besides the files of `"file contents"`. You give it. |
| `"open file <name>"` | The file that the file stream `<name>` has open. |
| `"file commands"` | The commands that changed files, in order. |
| `"file errors"` | The file commands the screen ignored, in order, as `(command, path)`. For example, a read or write past the file's end, a read or write with no file open (its path is `None`), a `newfile` whose size is not a number or is below 0, and a `twfile` the screen rejected. When code sets a data record's `path` to a file it cannot open, the entry is `("open", path)` ([Data records](screen-code.md#data-records)). |
| `"data files held"` | The files data records keep open, as `{file: (page, data record)}`. The first data record to open a file keeps it ([Data records](screen-code.md#data-records)). |
| `"data records shut out"` | The data records that could not open their file, as `{(page, data record): True}`. These data records do not read any records until they open a file. |
| `"data records given a path"` | The data records whose `path` was set by code, as `{(page, data record): True}`. A data record whose `init` is 1 does not open a file until code sets its `path`. |
| `"file browser listings"` | What each file browser lists, as `{(page, file browser): [names]}`. A folder's name ends with `/`. A file browser's `val` picks an entry from this list. |
| `"combo box choices"` | Each combo box's last `val` within its items, as `{(page, combo box): number}`. |
| `"component errors"` | Each `click`, `vis`, `tsw`, or `ref` whose ID does not match any object of the page, in order, as `(command, argument as written)`. |
| `"refusals"` | Each other line the running screen ignored, in order, as `(return code, line as written)`. For example, a number its attribute does not take ([screen-code.md](screen-code.md#numbers-an-attribute-takes)). |
| `"eeprom"` | The EEPROM's 1024 bytes. You may give them. Without them, the EEPROM starts empty. |
| `"eeprom accesses"` | Each `wepo` and `repo`, in order: `("wepo", address, bytes written)` and `("repo", address, value read)`. |
| `"gpio"` | `cfgpio`, as `("cfgpio", pin, mode, component)`, and each write and read of `pio0` to `pio7`, `pwm4` to `pwm7`, and `pwmf`, as `("write", name, value)` and `("read", name, value)`. |
| `"rand"` | The value that reading `rand` gives. You give it. |
| `"rand range"` | What `randset` set. |
| `"reset"` | 1, once `rest` ran. |
| `"text limits"` | Limits for texts whose size the page files do not give, as `{"t0.txt": bytes}`: a `txt_maxl`, or the limit of another attribute such as `path_m`. You give this value, and the test uses it along with the limits in the page files. |
| `"other commands"` | The commands that a test records without running them, and `move`, in order. Each entry is the command and its arguments. |

`print` is recorded in `"sent"` as `prints` with a length of 0, because it sends the same bytes. In nxlang, a `print` of joined texts prints each part in turn, so it is recorded as one send for each part.

See [How nxwright runs Nextion code](screen-code.md) for how each command runs and what it records.

## What a test does not do

- Nothing runs by itself. A timer's event or a touch runs only when the test lists it in `events`.
- Nothing is drawn. Drawing commands are recorded, and attributes that change the look, such as `pco` or `pic`, are values like any other.

To run the app as a whole, with timers, touches, and drawing, use the simulator ([Simulating your app](simulator.md)).

## Lists

List components are file browsers, selects, sliding texts, combo boxes, and data records. The screen works out some of their attributes by itself, so a test does too.

Before your events run, a test opens the page and sets up its list components:

- File browsers list their folders.
- Sliding texts work out how far they scroll.
- Data records read their data files from `"file contents"`, the test's SD card. If a data record's file doesn't exist and its `mode` is 1, the test creates a new data file in `"file contents"`, with no records.

The test then sets the values you give again, so they replace anything it worked out.

When your code sets an attribute of a list component, the test updates the component's other attributes. Your code can then read the new values, and `run` returns them.

- **File browser.** Setting `dir` lists that folder, sets `val` to -1 and `txt` to empty, and updates `qty` and `maxval_y`. Calling `up()` goes to the folder above and lists it. Setting `val` sets `txt` to the name of the matching entry. The folders come from `"file contents"` and `"existing"`.
- **Select.** Setting `val` sets `txt` to the matching line of `path`.
- **Sliding text.** Setting `txt` or `font` updates `maxval_y`, using the font in your source folder. `val_y` stops at the limit that code may scroll it to.
- **Combo box.** Setting `val` sets `txt` to the matching item. If `val` is past the last item, the combo box goes back to the item chosen before.
- **Data record.** `val_y` stops 32 pixels past `maxval_y`, and `val_x` stops at `maxval_x`. Setting `format`, `hig`, `gdw`, or `gdh` updates `qty`, `txt`, and both `maxval`s from the data record's file in `"file contents"`.

## SourceFolderRunner

Your tests use a `SourceFolderRunner` to run your screen's code. Make one for your source folder, as in [A first test](#a-first-test).

To share one runner between your test files, make it in a module beside them. The demo's `tests/screen.py` does this:

```python
from pathlib import Path

from nxwright.testing import SourceFolderRunner

APP = Path(__file__).resolve().parent.parent / "app"
SCREEN = SourceFolderRunner(APP)
```

Each test file then imports it with `from screen import SCREEN`.

If your code types Chinese with `pa_q` and `pa_txt`, give the runner the screen's pinyin table: `SourceFolderRunner(<source-folder>, pinyin_table=<file>)`. The file can be either:

- `input.bin`, in the Nextion Editor's installation folder.
- Any TFT file, such as one you built from your project. Every TFT file contains a copy of the table. Use one on a computer without the Nextion Editor, such as a continuous integration server.

A test never looks for an installed Nextion Editor, so its result does not depend on the computer it runs on.

### `run(page, events, values=None, text=None, blank_fields=False)`

`run` runs `events` in turn, and returns the values they leave.

- `events` is a list of (component, event) pairs.
- Events are named as in `.nx` files: `load`, `loadend`, `down`, `up`, `unload`, `timer`, `slide`.
- `values` are the values to start from ([The values a run starts from](#the-values-a-run-starts-from)).
- `text` runs the page with other code in place of its `.nx` file.
- `blank_fields=True` starts every component's `.val` and `.txt` you did not give at 0 or `""`.

### `compile(page, text=None, blank_fields=False)`

`compile` returns each event's code in strict Nextion syntax, and the values `run` starts from. The result is shared between runs, so do not change it.

### What `run` and `compile` refuse

If the build would refuse a page's code, such as code using a component the page does not have, `run` and `compile` stop with an error before any event runs. The test reports that error, with the file and the line the build refused, such as `pages/home.nx line 12:`.

`run` and `compile` do not check the components used by code given as `text`, because that code may be an older version, with components the page no longer has.

If nxwright refuses code as it runs, such as a loop that does not end, the run stops with the error `RefusedCode` ([screen-code.md](screen-code.md#code-that-stops-the-run)). Your test then shows as an error rather than a failure. The error starts with the line's file, number, and event, such as `pages/home.nx line 12 (home.load):`.

### `run_code(code, values=None, include=None)`

`run_code` runs a few lines of nxlang. See [Testing nxlang functions](#testing-nxlang-functions).

### `events_from_text(text)`

Use `events_from_text` to compare a page with an older version of its code, such as a copy kept from before the page moved to nxlang. It takes the text of a `.nx` file that does not use nxlang, and returns each event's code in strict Nextion syntax. You can run that code with `EditorMachine` ([Running code directly](#running-code-directly)).

Because the text does not belong to a page, `events_from_text` refuses a line that uses the form `'&name&'` outside a quoted text ([build-rules.md](build-rules.md#name-an-attribute-of-the-events-own-object)).

### Compiled pages are cached

nxwright keeps each compiled page in memory until your tests finish, since compiling is the slow part of a test. If a test changes one of your source files, nxwright compiles the page again.

## Testing nxlang functions

Use `run_code(code, values=None, include=None)` to test a library's functions. It runs a few lines of nxlang as the only event of a page of its own, and that page includes the file `include`, relative to the `pages` folder.

```python
values = SCREEN.run_code("r.val = clamp(40, 0, 30)", {"r.val": 0}, "lib/numbers.nx")
self.assertEqual(values["r.val"], 30)
```

The demo's `tests/test_library.py` tests its library this way.

- `run_code` only works in a folder in nxlang, because only nxlang has functions.
- Code given to `run_code` is not checked for the components it uses, since its page has no components of its own.

## Debugging a test

nxwright's VS Code extension can debug both a test's own Python and the screen code it runs.

The tests of each folder named `tests` beside a source folder appear in Test Explorer, where you can run or debug them. You can also use the "Debug test" link above each test method.

The debugger runs the test first, and records each line of its Python and each statement of screen code it runs. You then move through the recording, so you can step backward as well as forward.

### Stepping

- You can set breakpoints on lines of `.nx` files, and of the Python files in the folder of tests.
- A step goes from one source line to the next, however many lines of strict Nextion syntax that line compiled into.
- You also step through the test's own lines, including `setUp`, `tearDown`, and the helper modules beside the test, but not nxwright's own code or the standard library.
- To enter the screen code, step into a line that calls `run`.
- Because the lines given to `run_code` do not belong to a file, you can only step through the functions they call.

### The Call Stack and Variables views

VS Code's Call Stack view shows the screen code above the test's own functions.

The Variables view groups the values into Locals, Page, Program, Outside the page, and Generated. Outside the page shows the recorded values, such as `sent` ([What a test can check](#what-a-test-can-check)), and Generated shows the variables the compiler adds. A list, tuple, or dict in the test's Python opens to its first 100 entries.

At a line of the test, the groups other than Locals show what the last run left. That is what the test's assertions read.

### Failures

The debugger stops on the line of a failing assertion, or on the statement where a run stopped with an error, such as a value the test did not set. This happens even while you are stepping over that line.

### Long tests

While it is being debugged, a test stops with an error if it runs more than a million lines and statements. Recording a test's Python also slows it down.

## Running code directly

`EditorMachine` runs code in strict Nextion syntax without a source folder. Use `EditorMachine` for advanced cases, such as comparing a page with an older version of its code ([`events_from_text`](#events_from_texttext)).

```python
from nxwright.testing import EditorMachine

machine = EditorMachine({"n0.val": 2})
values = machine.run(["n0.val=n0.val*3"])
```

`machine.run(lines)` runs a list of code lines, and returns the values. A line that nxwright cannot read, such as `sys0 = = 2`, stops the run with `UnreadableLine`, a kind of `RefusedCode`.

The other arguments of `EditorMachine(values, events=None, page=None, macros=None, pinyin_table=None)` are:

- `events` maps (component, `"down"` or `"up"`) to the code a `click` runs.
- `macros` maps a macro's name to (its code lines, `None`), which a `call` runs.
- `page` lets the code refer to its own page's components as `page.component.attribute`.
- `pinyin_table` gives the screen's pinyin table, as for `SourceFolderRunner`.
