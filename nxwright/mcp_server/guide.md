# About nxwright's MCP tools

You are connected to `nxwright mcp`. Its tools run a Nextion screen app that nxwright keeps as text files, and use the app's screen as a person would. Read this before you change the app or start a simulation. It covers the app's files, how to check a change, how to use the tools, and what to do when one refuses.

## The app's files

The app is a source folder: the folder that contains `app.toml`. The files you will read and change most:

| File | What it contains |
| --- | --- |
| `app.toml` | The language of the code, the screen's model, and the lists of pages, pictures, and fonts, by name. |
| `program.nx` | The code that runs when the screen starts, and the `int` variables that every page shares. |
| `pages/<page>.page.toml` | A page and its components. Each has a table with its name, type, place (`x`, `y`, `w`, `h`), and the attributes that differ from its type's defaults, such as a text's `txt`. |
| `pages/<page>.nx` | The page's event code. |
| `macros.nx` | The macros, which `call` runs, if the app has any. |

- `app.toml`'s `language` gives the language of the code: `"nextion"` for strict Nextion syntax, the Nextion Editor's own language, or `"nxlang"` for the nxwright language. Read it before you write code, and never change it by hand. Switch a folder to nxlang only when the user asks, with `nxwright language`, which rewrites its code to match. Macros are always in strict Nextion syntax.
- In strict Nextion syntax, arithmetic has no parentheses, and operators run left to right: `sys0=a+b*c` computes `(a+b)*c`. Spaces around operators are fine in `.nx` files, as the build removes them.
- An event is a heading with its code under it, indented by two spaces:

  ```
  on save.up:
    sys0 = step.val
    page main
  ```

- Add a page with `nxwright new-page`, and a picture or font with `nxwright picture` or `nxwright font`. Remove a picture or font with `nxwright remove`, which first checks that nothing uses it.
- The order of `app.toml`'s lists sets each page's, picture's, and font's ID. Code may use an ID as a number, so do not reorder the lists unless the user asks.
- `nxwright --help` lists the commands, and `nxwright <command> --help` prints what a command does, with its options.

## Checking a change

After each change, run:

```
nxwright check <source-folder>
```

It runs every check the build makes, and writes nothing. It prints each problem with its file and line, such as `pages/home.nx line 12: error: unknown name speed`, and exits with 1 when there is an error.

- The check reports only the first error of each page, so run it again after a fix.
- Warnings show likely mistakes that the build accepts, such as a line that strict Nextion syntax computes in an unusual order.
- If the project has tests, run them with `nxwright test <tests-folder>`. For how to run and write them, call `about("testing")`.
- `nxwright build <source-folder> <output.HMI>` writes the project file the user opens in the Nextion Editor. Pass `--overwrite`, which replaces an existing project file without asking, only when the user agreed to replace that file. For the rest of what it does, call `about("commands")`.

### Writing a test

A test is a Python `unittest` test that runs a page's events and checks the values they leave. For how to write one, with an example, call `about("testing")`.

## Running the app

A session usually goes:

1. `start_simulation` with the source folder. It returns the simulation's id, which the other tools take, and the page shown.
2. `screen`, to see what the screen shows.
3. `tap` a component by its name, `send` an instruction as if it came on the serial line, or `set_input` the level of a GPIO input. For pins that change together, such as two buttons pressed at once, use `set_inputs`.
4. `wait`, to let the app's timers run.
5. `screen`, `values`, or `log`, to check what happened.
6. `stop_simulation`.

### Where the app runs

- **Without VS Code,** by default. The app runs inside `nxwright mcp`. Its time moves only when you call `wait`: a `wait` of 500 ms runs, at once, everything the app's timers would do in 500 ms. The app has no serial port. Its SD cards start empty, and their files stay in memory.
- **In VS Code,** when you pass `in_vscode` to `start_simulation`. Use it when the user wants to watch the app, or to press the screen too. The user must have turned on the setting `nxwright.agents.allowControl`. The app runs on its own, on the clock on the wall: its timers run between your calls, and a `wait` of 500 ms takes 500 ms. `list_simulations` also lists a simulation the user started, which you can drive.

If you pass `page` to `start_simulation`, the app starts on that page without running `program.nx`. Its `int` variables still start at the values they declare, or 0.

### Reading the screen

`screen` gives the screen's text layout, then, on a last line, the path of a PNG picture of it. For a page with a text, a number, and a button:

```
page main (800 x 480), background colour #ffffff
t0  text    20,20   300x40  "Home"
n0  number  20,80   120x40  "2"
b0  button  20,400  160x60  "Next"
```

- After the page's line, each line is a component that shows: its name, type, place, size, and what it shows. They come in the order they are drawn, so a later line lies on top of an earlier one.
- Then come what the code painted on the page, such as with `xstr`, and the names of the components that do not show.
- A picture is given by its ID, which code uses, and by its name in `app.toml`, which page files use: `picture 9 "state/heating"`.
- Read the text for what the screen shows. Look at the picture when the look matters, such as colours or what overlaps.
- The picture has one pixel for each of the page's. Pass `picture` as false when the text is enough.

`components` lists each component of the page shown with its box, as numbers, and whether it shows. A component without a place, such as a timer, has no box.

### Pressing

- Points and boxes are in the page's pixels, from its top left corner. `20,400  160x60` is a box 160 pixels wide and 60 high, 20 from the left edge and 400 from the top.
- A component given by name is pressed at the centre of its box. The press reaches whatever shows on top at that point, which may be another component lying over it. A component without a place cannot be pressed, and neither can one that does not show.
- `tap` presses and releases. For a drag, use `press`, then `move`, then `release`.
- The screen takes one touch at a time, on the page. A press while one is held is refused, and so is a move while none is, or a point off the page.
- If the app's code stops with an error as the screen is pressed, the press stays held. Call `release` to let it go.

### Time, values, and the log

- A `wait` lasts at most 60000 ms. For longer, call it again.
- The real-time clock, `rtc0` to `rtc6`, starts at your computer's time. To try another time of day, send `rtc3=6`, which sets the hour to 6.
- `send` answers with the log's lines since your last `send` or `log`, or since the start, the last 10 at most. They give what the screen sent back, such as a return code or what `get` asked for, and why an instruction did not run.
- `values` reads values by the names the page's code uses, such as `t0.txt` or `sys0`. Give it the names you want, or none for every value. A component's name alone, such as `t0`, gives each of its attributes. It refuses a name that the page's code does not know.
- `log` lists what the screen received and sent on its serial line, and what else happened outside the screen, such as a start again. Each line has a number, counted from 1. To read only what is new, give `after` the number of the last line you read.

### After you change the app

The simulation does not follow your edits while it runs. Run `nxwright check`, then `start_again`, which reads the folder anew and starts the app again, as a screen switched off and on. The EEPROM keeps what the app wrote, and the log is kept too. Without VS Code, a new simulation starts with an empty EEPROM.

If the folder no longer builds, `start_again` refuses with the file and the line at fault. Without VS Code, the app runs on as it was. In VS Code, the debugger stops on it, as on an error in the app's code.

## When a tool refuses

Each refusal is a plain sentence written for you, often with what to do next. Some need the user. While a simulation refuses your actions, you can still read its screen, values, and log.

- **No VS Code window lets an agent start the folder.** The user must open the folder in VS Code, and turn on `nxwright.agents.allowControl` in their user settings. Ask them to. The choice is theirs, so do not change their settings yourself. A workspace's settings cannot turn it on.
- **VS Code waits for the user's answer.** The simulation's serial port is connected, so what the app sends reaches a real device. VS Code is waiting for the user to allow or refuse your actions. Tell the user, and try again once they have answered.
- **The user did not allow agents to act on this simulation.** Their answer stands until the simulation ends. Stop acting on it, and tell the user.
- **A simulation already runs in the window.** A VS Code window runs one simulation at a time. Drive it, or ask the user before you stop it, since it may be theirs.
- **The app's code stopped with an error.** Without VS Code, the simulation stays as the error left it, and goes on with your next action. In VS Code, the debugger stops the simulation at the error, and the refusal gives it. The simulation then handles no action until the user lets the debugger go on: tell the user, or stop the simulation and start it again.
- **The simulation is stopped in the debugger.** It does not handle any action until the user resumes it in VS Code. The user may be debugging it, or the app's code may have stopped on an error. Tell the user.
- **The VS Code window did not answer within 60 s.** VS Code may still do what you asked. Look with `screen` or `list_simulations` before you try again. If you asked for a start, VS Code may be waiting for the user to answer a question first, such as whether to trust the folder, or to connect a serial port. The simulation starts once they answer.
