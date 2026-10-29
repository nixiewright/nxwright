# nxwright

**Build and simulate your Nextion HMI screen apps from plain text files: in your own editor, under version control, with tests.**

![VS Code with the thermostat demo: a page's .nx code, its page preview, and the demo's tests passing](https://raw.githubusercontent.com/nixiewright/nxwright/main/editors/vscode/images/vscode.png)

## TL;DR: Quick install

Needs Python 3.11 or later, and Node.js for the VS Code extension.

```
git clone https://github.com/nixiewright/nxwright
cd nxwright
pip install .
cd editors/vscode
npm install
npm run compile
```

In VS Code, run **Developer: Install Extension from Location...** and pick `editors/vscode`.

## Why nxwright

The Nextion Editor keeps your whole app in one binary `.HMI` file. You write code in small event boxes, one component at a time, and the Nextion Editor is strict about every space and brace. You can't see what changed between two versions, merge two people's work, or test a page without running it.

nxwright turns your project into ordinary text files, and back. With it, you can:

- edit your app in the editor you like, with code that is easier to write;
- work on Windows, Linux, or macOS: only the final compile to TFT, in the Nextion Editor, needs Windows;
- keep it in Git, with readable diffs, branches, and reviews;
- test your pages and functions on your PC;
- write in nxlang, a friendlier version of the Nextion language, when you want more;
- use the VS Code extension: a page preview you can edit, a font generator, a simulator, and more.

You keep the Nextion Editor for what it does best: compiling your app for the screen.

## Your project as text files

`nxwright extract screen.HMI app` turns a Nextion Editor project into a source folder:

```
app/
  app.toml              the app's name, its screen and settings, and the lists of pages, pictures, and fonts
  program.nx            the code that runs when the screen starts
  pages/
    home.page.toml      the page's components and their attributes
    home.nx             the code of the page and its components
    settings.page.toml
    settings.nx
  pictures/             your pictures, as PNG, JPEG, or other picture files
  fonts/                your fonts
  animations/, videos/, sounds/
```

A component is a few readable lines, its font, picture, and colours by name:

```toml
[[component]]
name = "clock"
type = "text"
x = 640
y = 20
w = 136
h = 32
font = "SansBold24"
picc = "settings/normal"
pco = "#eff3f7"
txt = "00:00"
```

And a page's code is one file, each event under a heading:

```
on settings.load:
  brightness.val = dim

on celsius.up:
  unit = 0
```

`nxwright build app screen.HMI` turns the folder back into a project file. Open it in the Nextion Editor and compile it, as usual. If you change something in the Nextion Editor, save it, and `nxwright extract` brings the change back into the folder, keeping your code wherever the Nextion Editor didn't change it.

## Write Nextion code comfortably

The Nextion Editor is strict about how code is written: no spaces around `=` or `+`, no space after `if`, and no `{` on the `if` line. nxwright reads Nextion code written comfortably, and turns it into what the Nextion Editor accepts when it builds:

<table>
<tr><th>In the Nextion Editor</th><th>In nxwright</th></tr>
<tr>
<td>

```
if(n0.val>100)
{
  n0.val=100
  t0.txt="Too high"
}else
{
  t0.txt=""
}
```

</td>
<td>

```
if (n0.val > 100) {
  n0.val = 100
  t0.txt = "Too high"
} else {
  t0.txt = ""
}
```

</td>
</tr>
</table>

You can also name pictures and fonts in your code instead of using their numbers: `p0.pic = @pic(icons/back)`. It is still the Nextion language you know, with the same commands. For more than that, see [nxlang](#nxlang), below.

## Use your own tooling

Because your app is now text, you can use the tools you already use for code:

- **Any computer.** Editing, checking, building the HMI file, testing, simulating, and debugging all run on Windows, Linux, and macOS. Only the last step, compiling the HMI file into a TFT file in the Nextion Editor, needs Windows, so you can develop on any machine and compile on a Windows one, or in a Windows virtual machine.
- **Any editor.** VS Code, Neovim, Emacs, or any other. nxwright's language server, `nxwright lsp`, works in every editor that speaks the Language Server Protocol: errors as you type, quick fixes, completion, descriptions on hover, go to definition, find references, rename, and formatting.
- **Version control.** Every change is a diff you can read. Branches merge, and changes can be reviewed before they go in.
- **AI coding agents.** They read and write text files, and nxwright's checks and tests tell them when something is wrong. Through nxwright's MCP server, `nxwright mcp`, they can also run your app and use it: tap the screen, let time pass, and see what it shows ([docs/mcp.md](https://github.com/nixiewright/nxwright/blob/main/docs/mcp.md)).
- **The command line.** `nxwright check app` finds what the build would refuse, without building. `nxwright format app` lays your code out in one consistent style.

## Add functional and unit testing

nxwright runs your pages' code on your PC, as the screen would, from ordinary Python tests. A test sets some values, runs events, and checks what changed. This one is from the demo, `examples/thermostat`:

```python
import unittest
from nxwright.testing import SourceFolderRunner

SCREEN = SourceFolderRunner("app")


class SettingsTest(unittest.TestCase):

    def test_the_slider_dims_the_screen(self):
        # Slide the brightness slider to 40: the screen dims, and its label follows.
        values = SCREEN.run("settings", [("brightness", "slide")], {"brightness.val": 40})
        self.assertEqual(values["dim"], 40)
        self.assertEqual(values["brightnessText.txt"], "40%")
```

Run a folder of tests with `nxwright test tests`. In nxlang, you can also test a function on its own:

```python
    def test_clamp(self):
        values = SCREEN.run_code("r.val = clamp(150, 0, 100)", {"r.val": 0}, "lib/numbers.nx")
        self.assertEqual(values["r.val"], 100)
```

See [docs/testing.md](https://github.com/nixiewright/nxwright/blob/main/docs/testing.md) for everything a test can do.

## nxlang

The Nextion language is small. It has no functions, it calculates strictly from left to right, and it has no constants or local variables. As an app grows, the same code ends up copied across pages and hidden buttons.

nxlang is nxwright's version of the Nextion language. It keeps everything you know, and adds what is missing. When you build, nxlang is compiled into ordinary Nextion code, so your HMI file and the Nextion Editor work as before.

<!-- nxlang-examples: start (written by `python -m tools.readme`; edit nxwright/language/nxlang_samples.py instead) -->

### Functions

Strict Nextion has no functions. To reuse code, you usually put it in a hidden button's event, pass values through variables, and click the button. In nxlang, you write a function and call it.

<table>
<tr><th>Strict Nextion</th><th>nxlang</th></tr>
<tr>
<td>

```
// clampFn is a hidden button:
// it clamps va0 to va1, into va2.
on clampFn.down:
  if (va0.val > va1.val) {
    va2.val = va1.val
  } else {
    va2.val = va0.val
  }

on save.up:
  va0.val = value.val
  va1.val = limit.val
  click clampFn, 1
  result.val = va2.val
```

</td>
<td>

```
function clamp(value: number, limit: number) -> number:
  var result = value
  if (value > limit) {
    result = limit
  }
  return result

on save.up:
  result.val = clamp(value.val, limit.val)
```

</td>
</tr>
</table>

### Calculation order and parentheses

Strict Nextion calculates from left to right, so `a + b * 2` means `(a + b) * 2`, and it does not accept parentheses. You often need an extra line and a spare variable. nxlang calculates the way C and most languages do, multiplication first, and accepts parentheses.

<table>
<tr><th>Strict Nextion</th><th>nxlang</th></tr>
<tr>
<td>

```
on save.up:
  // total = first + (second * 2)
  sys0 = second.val * 2
  total.val = first.val + sys0
  // average = (first + second) / 2
  average.val = first.val + second.val / 2
```

</td>
<td>

```
on save.up:
  // total = first + (second * 2)
  total.val = first.val + second.val * 2
  // average = (first + second) / 2
  average.val = (first.val + second.val) / 2
```

</td>
</tr>
</table>

### Numbers in text

In strict Nextion, you convert a number to text with `covx` before adding it to a text. In nxlang, you add the number directly.

<table>
<tr><th>Strict Nextion</th><th>nxlang</th></tr>
<tr>
<td>

```
on save.up:
  covx speed.val, speedText.txt, 0, 0
  label.txt = "Speed: " + speedText.txt + " mm/s"
```

</td>
<td>

```
on save.up:
  label.txt = "Speed: " + speed.val + " mm/s"
```

</td>
</tr>
</table>

### Constants and local variables

Strict Nextion has no constants or local variables. Programs repeat literal values and use global variables to perform calculations. nxlang has named constants, which take no memory on the screen, and local variables, declared where they are needed.

<table>
<tr><th>Strict Nextion</th><th>nxlang</th></tr>
<tr>
<td>

```
on save.up:
  sys0 = first.val * 2
  if (sys0 > 1200) {
    sys0 = 1200
  }
  total.val = sys0
```

</td>
<td>

```
const LIMIT = 1200

on save.up:
  var speed = first.val * 2
  if (speed > LIMIT) {
    speed = LIMIT
  }
  total.val = speed
```

</td>
</tr>
</table>

### switch, break, and continue

Strict Nextion has no `switch`, `break`, or `continue`. You write chains of `if` and `else if`, and use flags to stop a loop early. nxlang has all three, as in C.

```
on loops.load:
  total.val = 0
  var i = 0
  while (i < 10) {
    i++
    if (i == 3) {
      continue
    }
    if (i == 8) {
      break
    }
    total.val += i
  }
  switch (total.val) {
    case 0:
      label.txt = "none"
      break
    default:
      label.txt = "some"
  }
```

### Sharing code between pages

In strict Nextion, code that several pages need is copied into each page. nxlang lets you put functions in a file and include it on any page.

```
// pages/sharing.nx
include "lib/average.nx"

on sharing.load:
  total.val = average(first.val, second.val)

// pages/lib/average.nx
// The average of two numbers, for any page including this file.
function average(a: number, b: number) -> number:
  return (a + b) / 2
```

### And more

nxlang also lets you:

- calculate inside a condition, as in `if (a.val + b.val > 10)`;
- use `!`, and mix `&&` and `||`, in a condition;
- write a minus in front of a value, as in `-speed.val`;
- test a number on its own, as in `if (flag.val)`, which is true when it is not 0;
- rely on `&&` and `||` to skip their right side when the left already decides, so `b != 0 && a / b > 1` never divides by 0;
- choose a value with `? :`, as in `t0.txt = ready.val ? "Ready" : "Waiting"`;
- write hexadecimal numbers as in C, such as `0x1` or `-0x10`;
- write `x -= a + b`, which means `x = x - (a + b)`.

<!-- nxlang-examples: end -->

### Easier to maintain

Shared code lives in one place: fix a function once, and every page that includes it gets the fix. A page only gets the functions it calls, so a library costs nothing for what a page doesn't use. Errors give the file and the line they come from.

### Switching a project to nxlang

Run `nxwright language app nxlang`, or use "Switch to nxlang" in VS Code, which shows you the examples above and the lines that will change first. Any line of your code that would calculate differently in nxlang gets parentheses, so it keeps giving the same result. There is no command to switch back, but the HMI file nxwright builds can always be extracted into a new folder of plain Nextion code.

See [docs/language.md](https://github.com/nixiewright/nxwright/blob/main/docs/language.md) for the whole language.

## The VS Code extension

The extension brings everything above into VS Code, with tools of its own:

- **Edit pages from a preview.** Each page is drawn as it will appear on the Nextion screen. Select components, drag them to move or resize them, align them, and change their attributes in the Attributes section. A double click opens a component's code.

  ![Selecting the schedule page's four period names in the page preview, moving them, and aligning them, with the page side bar beside it](https://raw.githubusercontent.com/nixiewright/nxwright/main/editors/vscode/images/select-move-align.gif)
- **Fonts.** Generate a font from any typeface installed on your computer, or from a typeface file, at the height you need, and, in a utf-8 project, with only the characters you choose. Open a font file to see it with a sample text, and create a variation of it.

  ![The Fonts panel: a typeface chosen from those installed, its height, and a sample of the font before it is added](https://raw.githubusercontent.com/nixiewright/nxwright/main/editors/vscode/images/fonts-panel.png)
- **Project management.** Two side bars: one for the project, with its settings, Build, media, and simulator; one for the page, with its pages, components, and attributes. Change the screen model, rotation, or encoding from where they show.
- **A simulator.** Run your whole app, or start it on one page. Press the screen, watch timers and pages change, connect a real serial port, and debug the code with breakpoints, stepping, and stepping back.

  ![The simulator running the demo's settings page: a press on the hour's minus button stops at a breakpoint in settings.nx, and the code is then stepped through](https://raw.githubusercontent.com/nixiewright/nxwright/main/editors/vscode/images/debug.gif)
- **Tests.** Your tests appear in Test Explorer, where they run and debug.

  ![Test Explorer listing the demo's tests, one of them failed, with its traceback shown at the failing line](https://raw.githubusercontent.com/nixiewright/nxwright/main/editors/vscode/images/test-explorer.png)

See [editors/vscode/README.md](https://github.com/nixiewright/nxwright/blob/main/editors/vscode/README.md) for everything the extension does, and how to install it.

## Getting started

To install nxwright, follow [Quick install](#tldr-quick-install). Then `nxwright --help` lists its commands. nxwright is tested with projects of Nextion Editor 1.68.2.

**Start a new project:**

```
nxwright new app                      # asks for the screen, its rotation, the encoding, the language, and the app's name
nxwright new-page app settings        # adds a blank page
nxwright build app screen.HMI         # builds the project file, to open and compile in the Nextion Editor
```

`app` is only the folder's name: rename it whenever you like, and the app keeps its own name.

**Or bring in an existing one:**

```
nxwright extract screen.HMI app       # turns your project into a source folder, its app named after the file
nxwright build app screen.HMI         # and back, after you edit it
```

A few more commands you will use:

| Command | What it does |
| --- | --- |
| `nxwright picture app logo.png` | adds pictures |
| `nxwright font app NotoSans-Regular.ttf 20` | adds a font drawn from a typeface file |
| `nxwright keyboard app keyboard` | adds a keyboard page, for components that open one |
| `nxwright animation app frame1.png frame2.png` | makes an animation of pictures |
| `nxwright video app intro.mp4 --size 320,240` | makes a video, through ffmpeg |
| `nxwright sound app beep.wav` | adds a sound |
| `nxwright device app --rotation 90` | changes the screen model, rotation, or encoding |
| `nxwright remove app font NotoSans20` | removes a picture, font, or media file your code no longer uses |
| `nxwright upgrade app` | converts a folder made by an older nxwright |

`nxwright <command> --help` explains each one.

## A demo

[examples/thermostat](https://github.com/nixiewright/nxwright/tree/main/examples/thermostat) is a thermostat screen written with nxwright: four pages in nxlang sharing a library of functions, and tests. Open its `thermostat.HMI` in the Nextion Editor's simulator, then read its source folder.

## Learn more

- [docs/source-folder.md](https://github.com/nixiewright/nxwright/blob/main/docs/source-folder.md): your project as a source folder, and the comfortable form of Nextion code.
- [docs/commands.md](https://github.com/nixiewright/nxwright/blob/main/docs/commands.md): every command.
- [docs/build-rules.md](https://github.com/nixiewright/nxwright/blob/main/docs/build-rules.md): what the build refuses.
- [docs/language.md](https://github.com/nixiewright/nxwright/blob/main/docs/language.md): nxlang.
- [docs/nxlang-compiled.md](https://github.com/nixiewright/nxwright/blob/main/docs/nxlang-compiled.md): how nxlang becomes strict Nextion syntax.
- [docs/testing.md](https://github.com/nixiewright/nxwright/blob/main/docs/testing.md): testing your app.
- [docs/simulator.md](https://github.com/nixiewright/nxwright/blob/main/docs/simulator.md): simulating your app.
- [docs/mcp.md](https://github.com/nixiewright/nxwright/blob/main/docs/mcp.md): letting an AI agent drive your app.
- [docs/screen-code.md](https://github.com/nixiewright/nxwright/blob/main/docs/screen-code.md): how tests and the simulator run Nextion code.
- [docs/format.md](https://github.com/nixiewright/nxwright/blob/main/docs/format.md): what is known of the Nextion Editor's project file. `nxwright dump` writes one out as text, and `nxwright write` writes an edited dump back ([docs/dumps.md](https://github.com/nixiewright/nxwright/blob/main/docs/dumps.md)).
- [ROADMAP.md](https://github.com/nixiewright/nxwright/blob/main/ROADMAP.md): what nxwright may do next.
- [CHANGELOG.md](https://github.com/nixiewright/nxwright/blob/main/CHANGELOG.md): what changed in each version.

## Contributing

See [CONTRIBUTING.md](https://github.com/nixiewright/nxwright/blob/main/CONTRIBUTING.md). From this folder, run the tests with:

```
python -m unittest discover -s tests -t .
```

## License

Apache License 2.0: see [LICENSE](https://github.com/nixiewright/nxwright/blob/main/LICENSE).

nxwright ships the Noto Sans font, by the Noto Project Authors, which is under the SIL Open Font License 1.1: see [its license](https://github.com/nixiewright/nxwright/blob/main/nxwright/project/fonts/OFL.txt).

nxwright is an independent project. It is not affiliated with, or endorsed by, ITEAD or Nextion. "Nextion" names the screens and the Nextion Editor it works with. See [INDEPENDENCE.md](https://github.com/nixiewright/nxwright/blob/main/INDEPENDENCE.md) for what nxwright is built on.
