# nxwright for VS Code

**Design, write, simulate, and test Nextion screen apps in VS Code.** The extension brings nxwright's toolchain into the editor: a page preview you can edit, help while you write code, a font generator, a simulator, and your tests in Test Explorer.

![VS Code with the thermostat demo: a page's .nx code, its page preview, and the demo's tests passing](https://raw.githubusercontent.com/nixiewright/nxwright/main/editors/vscode/images/vscode.png)

It works with nxwright's source folders, the text files created from your Nextion project ([README](https://github.com/nixiewright/nxwright/blob/main/README.md)). It needs nxwright to be installed (see [Getting started](#getting-started)). Without nxwright, only the syntax highlighting works. With an nxwright older than the extension works with, it warns you once, and says how to update it.

## What it does

### Edit pages visually

Open a page, and it is displayed the same way as it would be on the Nextion screen, with your project's own fonts, pictures, and colours. The preview is updated whenever the page's source file changes.

- Click a component to select it, Ctrl+click to select several, or drag a box across them, from an empty spot, or from anywhere with Shift.
- Drag a component to move it, drag a handle to resize it, or use the arrow keys.
- Right-click to add a component, align or space out several components, give them the same size, lock them, or group them.
- If a text has characters its font does not have, the preview lists them, with what the screen will show instead.
- Change any attribute in the Attributes section. Click an attribute, or move to its field with Tab, and what it does shows at the bottom of the section. The section leaves out a component's lock and group, which the preview shows, and the attributes that have no known effect.
- An attribute with a few choices, such as where a text sits or whether a checkbox is ticked, is a list of their names.
- A colour has a sample in front of it. Click the sample to pick a colour. The screen can't show every colour, so the one you pick is stored as the nearest one it can.
- Cut, copy, paste, duplicate, and delete components, along with their code.
- Right-click the page and choose Paste Here to paste where you clicked.
- Right-click a component and choose Paste Special to give the selected components parts of the one you copied: its size, its position, its other attributes, or its code. For example, copy a button you have styled, select three others, and paste its other attributes to give them the same colours and font.
- Right-click an empty part of the page, or the page in the Components list, and choose Paste Special to paste new copies. They go where you clicked, or where Paste puts them from the Components list. Tick Position to put them exactly where you copied them from instead, or untick Code to paste them without their code.
- Double click a component to open its code: the first of its events that has some. If none has code yet, its first event is added to the page's `.nx` file.
- Right-click a component and choose Go to Event... to open any of its events, or add one without code. Edit Attributes shows the component in the Attributes section. Go to Definition, or F12, opens the page file as text at the component's table, or at the page's when you right-click the page. Clear events deletes all of its code and keeps the component.

Every change edits the page file, so the preview and the text editor share the same undo history.

![Selecting the schedule page's four period names in the page preview, moving them, and aligning them, with the page side bar beside it](https://raw.githubusercontent.com/nixiewright/nxwright/main/editors/vscode/images/select-move-align.gif)

### Write code with help

- Errors show as you type, along with warnings about likely mistakes.
- When an error has one sure fix, the light bulb offers it, or press Ctrl+. on the line. For example, it can declare `sys0` in `program.nx`, or make a component global so that a keyboard can open from it.
- Completion suggests attributes, components, functions, and constants. In page files, it also suggests your project's pictures and fonts.
- Hover over a name for its description, attributes, and allowed values, such as the numbers code may store in an attribute.
- Ctrl+click goes to a name's definition, and Shift+F12 finds all its references.
- F2 renames a component, function, or constant everywhere it is used.
- The Outline view lists a file's events, functions, and constants, or a page file's components. Ctrl+T finds any page, component, function, or constant in your project.
- Format Document formats your code in nxwright's standard style.
- "Show this file in strict Nextion syntax" shows, next to your code, the code the Nextion Editor will receive ([How nxlang becomes strict Nextion syntax](https://github.com/nixiewright/nxwright/blob/main/docs/nxlang-compiled.md)).

![Completion after `sleepTemp.` in a .nx file, listing a text's attributes, with the description of `aph` beside the list](https://raw.githubusercontent.com/nixiewright/nxwright/main/editors/vscode/images/completion.png)

### Your project at a glance

The extension adds two side bars, each with its own icon:

- **nxwright**, for the project: its settings, a Build button, its pictures, fonts, and media, and the simulator.
- **nxwright page**, for the page you are working on: the list of pages, the page's components, and the attributes of the selected component.

From the Project section, you can change the screen model, the rotation, and the encoding. When no project is open, you can create a new one, or import one from an HMI file, as authored with the Nextion Editor.

![The nxwright side bar: the Project section with the screen settings and the Build button, the Media section, and the Simulator section](https://raw.githubusercontent.com/nixiewright/nxwright/main/editors/vscode/images/project-side-bar.png)

![The nxwright page side bar: the list of pages, the page's components, and the attributes of the selected button, with the description of `picc`](https://raw.githubusercontent.com/nixiewright/nxwright/main/editors/vscode/images/page-side-bar.png)

### Fonts

The Fonts panel generates fonts from any typeface installed on your computer, or from a typeface file. You choose the height, and whether the edges are smoothed. In a utf-8 project, you can also choose exactly which characters the font contains, to keep it small.

Open a font file to see it with a sample text, and to create a variation of it.

![The Fonts panel: a typeface chosen from those installed, its height, and a sample of the font before it is added](https://raw.githubusercontent.com/nixiewright/nxwright/main/editors/vscode/images/fonts-panel.png)

### Pictures, animations, videos, and sounds

From the Media section, you can add pictures, and make animations, videos, and sounds from ordinary files. Animations and videos play in a viewer, and sounds play in VS Code's audio player.

### Simulate your app

Run your whole app, or start it on one page. A panel draws the screen. You can press its components, watch timers run and pages change, and see what the app sends on its serial line in the Debug Console.

- Connect the simulation to a real serial port, to talk to a program on the other end.
- Flip the screen's GPIO inputs, as buttons or switches wired to them would.
- Use folders on your computer as the screen's SD cards, so the app reads and writes real files.
- Set breakpoints in your code, step through it, and step back.

Start a simulation from the Simulator section. From there, you can also pause, resume, and restart it, and send the screen an instruction as if it came from the serial line. The Simulate this page button, above a page's preview or its page file, starts a simulation on that page. If you close the simulator's panel, the simulation keeps running, and the Show the screen button in the Simulator section opens the panel again.

An AI agent can drive the simulator too, through `nxwright mcp`, once you turn on `nxwright.agents.allowControl` (see [Settings](#settings)). While an agent drives a simulation, the Simulator section shows it. If the simulation has no serial port, a button there connects the one the Simulator settings give. If you connect a port while an agent drives the simulation, VS Code takes that as your yes, and the agent may act on the simulation with that port without being asked.

To keep a simulation's setup, such as the page it starts on, its serial port, or its SD card folders, save it as a launch configuration. The Simulator section creates one for you, with every option listed, and shows a button for each one you have (see [A simulation's launch configuration](#a-simulations-launch-configuration)).

![The simulator running the demo's settings page: a press on the hour's minus button stops at a breakpoint in settings.nx, and the code is then stepped through](https://raw.githubusercontent.com/nixiewright/nxwright/main/editors/vscode/images/debug.gif)

### Test your app

Your tests appear in Test Explorer. You can run them, and see each failure at the line where it happened. You can also debug a test: both its Python code and the screen code it runs, with breakpoints in both, stepping forward and back.

![Test Explorer listing the demo's tests, one of them failed, with its traceback shown at the failing line](https://raw.githubusercontent.com/nixiewright/nxwright/main/editors/vscode/images/test-explorer.png)

### Switch to nxlang

You can switch a project to nxlang from the extension, and see the lines of your code that will change as a result. Once you have switched, you can start using nxlang's extended syntax: functions, includes, local variables, standard operator precedence, and more ([nxlang](https://github.com/nixiewright/nxwright/blob/main/README.md#nxlang)).

## Getting started

You need nxwright, which needs Python 3.11 or later. See the [README](https://github.com/nixiewright/nxwright/blob/main/README.md#getting-started).

Optionally, install a TOML extension, such as Even Better TOML, to highlight the page files.

The extension is not published yet. To install it from a copy of nxwright's repository, see the [quick install](https://github.com/nixiewright/nxwright/blob/main/README.md#tldr-quick-install).

Then open your nxwright project's folder in VS Code. If you don't have one yet, use the nxwright side bar to create a new project, or to import one from an HMI file, as authored with the Nextion Editor.

## Reference

### Commands

All commands are in the command palette, under "nxwright:". Three of them only show at certain times: "Stop the simulation" and "Show the Simulator" while a simulation runs, and "Open the page file as text" while a page preview is active.

| Command | What it does |
| --- | --- |
| Create a new nxwright project | Asks for the screen, rotation, encoding, language, folder, and name, then creates the project. |
| Import a Nextion Editor project | Extracts a `.HMI` file into a new folder, and remembers the file for Build. |
| Choose the project | Chooses which project the side bars show, when the workspace has several. |
| Build the project file | Builds the `.HMI` file. The first time, it asks where to save it. |
| Extract the project file into the source folder | Brings changes made in the Nextion Editor back into your files, after asking you to confirm. |
| Choose the project HMI file for the source folder | Chooses the `.HMI` file that Build writes and Extract reads. |
| Change the screen model | Changes the screen, and resizes every page. |
| Change the rotation | Changes the rotation, resizes every page, and rotates fonts and videos. |
| Change the character encoding | Changes the encoding, and converts the fonts. |
| Upgrade the source folder to the current format | Converts a folder made by an older version of nxwright. |
| Switch the source folder to the nxwright language | Opens the Switch to nxlang page. |
| New page | Adds a blank page. |
| Add a component | Adds a component to the page shown. |
| Show the page preview | Opens the page's preview next to its code. |
| Open the page file as text | Opens the page's `.page.toml` file as text. |
| Show this file in strict Nextion syntax | Shows, next to a `.nx` file, the code the Nextion Editor will receive. |
| Add pictures | Adds pictures to the project. |
| Fonts | Opens the Fonts panel. |
| Add a font | Opens the Fonts panel on its form for a new font. |
| Add a keyboard page | Adds one of nxwright's keyboard pages. For the Chinese keyboard, you also choose a font with Chinese characters. |
| Add an animation | Makes an animation from pictures, or from a GmovMaker file. |
| Add a video | Makes a video from a video file or from pictures. |
| Add a sound | Adds a sound, and converts it if you ask. |
| Write pictures for the SD card | Writes picture files that the screen can show from an SD card. |
| Simulate the app | Simulates the project from the start. |
| Simulate the app from the page shown | Simulates the project, starting on the page shown. |
| Stop the simulation | Stops the simulation. |
| Show the Simulator | Shows the simulator's panel, and opens it again if you closed it. |
| Add a launch configuration | Adds a configuration to `launch.json` that simulates the project, with every parameter listed and commented out. |

### A simulation's launch configuration

A launch configuration of type `nxwright` simulates the source folder given by `sourceFolder`. All its other parameters are optional:

| Parameter | What it does |
| --- | --- |
| `page` | The page to start on, instead of running program.nx. |
| `values` | With `page`, the values to start with, such as `{"t0.txt": "Hello"}`. |
| `eeprom` | A file that keeps the EEPROM's contents between simulations. It is created if missing. Without it, the EEPROM starts empty every time. |
| `serialPort` | The serial port connected to the screen's serial line, such as `{"name": "COM4", "baud": 115200}`. |
| `gpioInputs` | The levels the GPIO inputs start at, such as `{"pio2": 0}`. Without it, every input reads 1, as a pull-up input that nothing drives does. |
| `sdCard0`, `sdCard1` | The full paths of folders on your computer to use as the screen's SD cards. Without them, each card is kept in memory. |
| `logReceived`, `logSent` | How the log shows the serial line: `text`, `hex`, or `both`. |
| `pinyinTable` | The screen's pinyin table, for Chinese input: the Nextion Editor's `input.bin`, or a TFT file. Without it, the installed Nextion Editor's table is used, if one is found. |
| `stopOnEntry` | Stops at the first line that runs. |

When a configuration leaves a parameter out, the Simulator settings provide it (see [Settings](#settings)).

### What Ctrl+click opens

- A component's name, in code or in an event's heading: its table in the page file.
- A page's name: its page file.
- A function, constant, local variable, or `int` variable: its declaration.
- An `include` path: the included file.
- `@pic(...)`: the picture. `@font(...)`, `@animation(...)`, `@video(...)`, `@sound(...)`: its entry in `app.toml`.
- A macro's name in a `call`: the macro.
- In a page file, a picture, font, or media value: the picture, or its entry in `app.toml`.

### The page preview's keys and mouse

| Action | What it does |
| --- | --- |
| Click | Selects the component under the pointer. |
| Ctrl+click | Adds a component to the selection, or removes it. |
| Drag from an empty spot | Selects every component the box overlaps, even in part. |
| Shift+drag | Draws the box wherever the drag starts, even on a component. With Ctrl too, adds what it overlaps to the selection. |
| Escape | Keeps only the first selected component. |
| Drag a selected component | Moves the selection. |
| Drag a handle | Resizes the component. |
| Arrow keys | Move the selection by 1 pixel. |
| Shift+arrow keys | Move the selection by 10 pixels. |
| Delete | Deletes the selection. |
| Ctrl+C, Ctrl+X, Ctrl+V, Ctrl+D | Copy, cut, paste, duplicate. |
| Ctrl+Z, Ctrl+Y | Undo, redo. |
| Ctrl+S | Saves the page file. |
| Double click | Opens the component's code: the first of its events that has some, or else its first event. |
| F12 | Opens the page file as text at the selected component's table, or at the page's. |
| Right-click | Opens a menu: Go to Event..., Edit Attributes, Go to Definition, Add a component here, Paste Here, Paste Special, Clear events, Align, Make the same size, Space evenly, Bring to front, Bring forward, Send backward, Send to back, Lock, Group, and the edits above. |
| Ctrl+mouse wheel | Zooms in or out around the pointer. |

On a Mac, use Cmd instead of Ctrl, and the delete key to delete.

The toolbar above the page has buttons to zoom in and out, to fit the page in the window, and to show each component's name.

### What the page preview does not show

- Values that your code sets while the page runs. The preview shows the values in the page file. To see the page running, use the simulator.
- External pictures, and the files listed by file browsers, because they come from the SD card.
- A scrolling text's movement. It is drawn standing still.
- Hotspots, because the screen does not show them either. You can still click one to select it.

### Before you edit a page

- Deleting a component, or moving it forward or backward, changes the IDs of the components after it. If your code or attributes use an ID as a number, that number then points to a different component.
- You can't delete a component whose code is in a file that other pages include. If other code uses the component, you are asked to confirm, and that code then shows errors until you fix it.
- Clear events works the same way: it can't delete code in a file that other pages include. For several components at once, you are asked to confirm first.
- Paste Here keeps the components on the page: near its right or bottom edge, they move back inside.
- The code of the components you copy is kept until you copy something else. After that, pasting brings no code, and Paste Special tells you so.
- Paste Special on a component takes one copied component. Between two types, it gives only the attributes that mean the same on both, such as colours, pictures, fonts, and `txt`. A message lists what was left out.
- Paste Special's code replaces the selected component's code for the same events. In that code, the copied component's name becomes the selected one's: `b0.bco=RED`, pasted from b0 onto b1, becomes `b1.bco=RED`. Paste leaves the code as it was copied. Paste Special can't change code in a file that other pages include.
- Setting a component's `key` to a keyboard adds nxwright's keyboard page, if the project doesn't have it yet. Its files are written right away, and undo does not remove them.
- A keyboard only opens from a component of global scope. For a local component, you are asked to make it global first.
- `key` 4 opens the Chinese keyboard. It only works in a gb2312 project, and you will be asked for a font with Chinese characters.
- Rename changes your code and page files, but not strings, comments, or your Python tests. Change those by hand.

### Good to know

- The status bar shows how many objects the page has, out of the 256 allowed, and its longest chain of calls and clicks, out of the 7 allowed. (A Nextion screen lets events nest 9 deep. The event that starts the chain takes one level, and one more is kept free for a page change, which runs the new page's load event.)
- Save your changes first. Adding a page, a font, pictures, an animation, a video, a sound, or a keyboard page is refused while `app.toml` has unsaved changes. Extracting, switching to nxlang, and changing the screen, rotation, or encoding are refused while any file of the project has unsaved changes.
- Some of the extension's own edits check the result before they are applied, and are refused with a message if the project would no longer build: Rename (for example, to a name already in use), adding or pasting a component (for example, on a page that is full), and Format Document (on a file with errors).
- VS Code saves `.nx` files in UTF-8, as nxwright reads them, and never guesses another encoding for them, whatever you set `files.encoding` and `files.autoGuessEncoding` to for all files. This only covers VS Code. A `.nx` file that another program saved in another encoding may not be valid UTF-8. The build then refuses it, with a message that it is not UTF-8 text.
- Page files open in the preview. To switch between the preview and the text, use the editor picker at the top right of the editor, which shows "nxwright page preview" or "Text Editor". Its "Set Default" item chooses which one page files open in.

## Settings

nxwright's settings are grouped in five categories in VS Code's Settings: General, Page preview, Simulator, Agents, and Tests.

- `nxwright.command`: the command that runs nxwright, as a list: the program, then its first arguments. It is empty by default, and the extension then looks for the `nxwright` command, or for a Python that can run nxwright, starting with the interpreter chosen in VS Code. To use a copy of nxwright's repository, you can set it to `["python", "${workspaceFolder}/nxwright/run.py"]`. If you opened a `.code-workspace` file, put this setting in that file's `settings`.
- `nxwright.previewGrid`: the size of the grid, in pixels, that dragged components snap to. The default is 1, which means no grid.
- `nxwright.testFolders`: the folders of tests that Test Explorer lists. By default, it lists every folder named `tests` next to a source folder.
- The Simulator settings, used when a launch configuration doesn't set its own value:
  - `nxwright.simulator.serialPort` and `nxwright.simulator.serialBaud`: the serial port, such as `COM4`, and its speed. Leave the port empty for none.
  - `nxwright.simulator.sdCard0` and `nxwright.simulator.sdCard1`: the full paths of the folders to use as SD cards. Leave one empty to keep that card in memory.
  - `nxwright.simulator.logReceived` and `nxwright.simulator.logSent`: how the log shows what the screen receives and sends: `text`, `hex`, or `both`. By default, what it receives is shown as text, and what it sends in hexadecimal.
  - `nxwright.simulator.pinyinTable`: the full path of the screen's pinyin table, for Chinese input: the Nextion Editor's `input.bin`, or a TFT file. Leave it empty to use the installed Nextion Editor's table, if one is found.
- The Agents settings, which only your user settings can hold, never a workspace's:
  - `nxwright.agents.allowControl`: lets `nxwright mcp`, through which an AI agent drives your app, start and drive this window's simulator. Only a program that can read a file of your own account can connect. It is off by default.
  - `nxwright.agents.startWithoutSerialPort`: a simulation an agent starts has no serial port. It is on by default. Turned off, the simulation takes the Simulator settings' port, and you are asked first unless `nxwright.agents.askBeforeSerialActions` is off.
  - `nxwright.agents.askBeforeSerialActions`: asks you before an agent acts on a simulation whose serial port is connected, since what the app sends then reaches the device on that port. It is on by default. Your answer holds until the simulation ends.

## Building from VS Code

A VS Code task can run `nxwright check` or `nxwright build`, and show their errors in the Problems panel with the `$nxwright` problem matcher. The errors give file paths inside the source folder, so tell the problem matcher where that folder is:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "nxwright: check",
      "type": "process",
      "command": "nxwright",
      "args": ["check", "app"],
      "problemMatcher": {
        "base": "$nxwright",
        "fileLocation": ["relative", "${workspaceFolder}/app"]
      },
      "group": "build"
    }
  ]
}
```

`nxwright build` reports an error in a page file by the component's name, not by line, so it only shows in the terminal. `nxwright check` reports the same error with its line. A task that builds into an existing project file passes `--overwrite`, or the build asks before it replaces the file.
