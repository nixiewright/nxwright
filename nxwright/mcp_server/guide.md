# About nxwright's MCP tools

You are connected to `nxwright mcp`. Its tools run a Nextion screen app that nxwright keeps as text files, and use the app's screen the way a person would. Read this before you change the app or start a simulation.

## The app's files

The app is a source folder: the folder that contains `app.toml`. The files you will read and change most:

| File | What it contains |
| --- | --- |
| `app.toml` | The language of the code, the screen's model, and the lists of pages, pictures, and fonts, by name. |
| `program.nx` | The code that runs when the screen starts, and the `int` variables that every page shares. |
| `pages/<page>.page.toml` | A page and its components. Each has a table with its name, type, position and size (`x`, `y`, `w`, `h`), and the attributes that differ from its type's defaults, such as a text's `txt`. |
| `pages/<page>.nx` | The page's event code. |
| `macros.nx` | Macros, if the app has any, run with `call`. |

- The `language` setting in `app.toml` is `"nextion_do_not_change_manually"` for strict Nextion syntax, the Nextion Editor's own language, or `"nxlang_do_not_change_manually"` for the nxwright language. A folder from an older nxwright may have just `"nextion"` or `"nxlang"`, with the same meanings. Read the setting before you write code, and never change it by hand. Only when the user asks, switch a folder to nxlang with `nxwright language`, which rewrites the folder's code to match. Macros are always in strict Nextion syntax.
- In strict Nextion syntax, arithmetic has no parentheses, and operators run left to right: `sys0=a+b*c` computes `(a+b)*c`. Spaces around operators are fine in `.nx` files.
- An event is a heading with its code under it, indented by two spaces:

  ```
  on save.up:
    sys0 = step.val
    page main
  ```

- Add a page with `nxwright new-page`, and a picture or font with `nxwright picture` or `nxwright font`. Remove a page, picture, or font with `nxwright remove`, which first checks that nothing uses it, and add `--keep-ids` to leave a placeholder in its place, so that the IDs after it stay the same. `nxwright replace` puts a new file in a resource's place, keeping its ID, and `nxwright rename` renames a page or a resource and each use of its name.
- The order of `app.toml`'s lists sets each page's, picture's, and font's ID. Code may use an ID as a number, so do not reorder the lists unless the user asks.
- `nxwright --help` lists the commands, and `nxwright <command> --help` prints what a command does, with its options.

## Checking a change

After each change, run:

```
nxwright check <source-folder>
```

`nxwright check` runs every check the build makes, and writes nothing. It prints each problem with its file and line, such as `pages/home.nx line 12: error: unknown name speed`, and exits with 1 when there is an error.

- The check reports only the first error of each page, so run it again after a fix.
- Warnings show likely mistakes that the build accepts, such as a line that strict Nextion syntax computes in an unusual order.
- If the project has tests, run them with `nxwright test <tests-folder>`.

When the user wants to open the app in the Nextion Editor, write the project file with `nxwright build <source-folder> <output.HMI>`. `--overwrite` replaces an existing project file without asking, so pass it only when the user has agreed to replace that file. For the rest of what `nxwright build` does, call `about("commands")`.

### Writing a test

A test is a Python `unittest` test that runs a page's events and checks the values they leave. For how to run and write one, with an example, call `about("testing")`.

## Running the app

A session usually goes:

1. `start_simulation` with the source folder. It returns the page shown and the simulation's id, which you pass to the other tools.
2. `screen`, to see what the screen shows.
3. `tap` a component by its name, `send` an instruction as if it came in over the serial line, or set the level of a GPIO input with `set_input`. For pins that change together, such as two buttons pressed at once, use `set_inputs`.
4. `wait`, to let the app's timers run.
5. `screen`, `values`, or `log`, to check what happened.
6. `stop_simulation`.

To fill a waveform with data, such as a sensor's readings, call `start_generator`. It sends points to the waveform as time passes, the way a device on the serial line would, so `wait` before you look at the `screen`.

If you pass `page` to `start_simulation`, the app starts on that page without running `program.nx`. The `int` variables in `program.nx` still start at their declared values, or 0.

### Where the app runs

- **Without VS Code,** by default. The app runs inside `nxwright mcp`, and its time moves only when you call `wait`. A `wait` of 500 ms immediately runs everything the app's timers would do in 500 ms. The app has no serial port, and its SD cards start empty and keep their files in memory.
- **In VS Code,** when you pass `in_vscode` to `start_simulation`. Use it when the user wants to watch the app or press the screen too. The user must have turned on the setting `nxwright.agents.allowControl`. The app runs in real time, so its timers run between your calls, and a `wait` of 500 ms takes 500 ms. To drive a simulation the user started, find it with `list_simulations`.

### Reading the screen

`screen` gives the screen's layout as text, followed by the path of a PNG image of the screen. For a page with a text, a number, and a button, the text looks like this:

```
page main (800 x 480), background colour #ffffff
t0  text    20,20   300x40  "Home"
n0  number  20,80   120x40  "2"
b0  button  20,400  160x60  "Next"
```

- After the page's line, each line is a visible component. The lines come in the order the components are drawn, so a later component lies on top of an earlier one.
- The component lines are followed by anything the code painted on the page, such as with `xstr`, and by the names of the components that are not visible.
- A picture from the app appears as its ID and its name: `picture 9 "state/heating"`. Code uses the ID, and page files use the name from `app.toml`.
- Read the text for what the screen shows, and pass `picture` as false when the text is enough. Look at the PNG when the appearance matters, such as colours or what overlaps.

`components` lists each component of the page shown, with its box (position and size) as numbers, and whether it is visible. A component that is not placed on the page, such as a timer, has no box.

### Pressing

- Points and boxes are in the page's pixels, from its top left corner. `20,400  160x60` is a box 160 pixels wide and 60 high, 20 from the left edge and 400 from the top.
- A component given by name is pressed at the centre of its box. The press reaches whatever is on top at that point, which may be another component. A component cannot be pressed if it has no box or is not visible.
- `tap` presses and releases. For a drag, use `press`, then `move`, then `release`.
- The screen takes one touch at a time. A tool refuses a press while another is held, a move while nothing is pressed, and a point off the page.
- If the app's code stops with an error as the screen is pressed, the press stays held. Call `release` to let it go.

### Time, values, and the log

- A `wait` lasts at most 60000 ms. For longer, call it again.
- The real-time clock, `rtc0` to `rtc6`, starts at your computer's time. To try another time of day, send `rtc3=6`, which sets the hour to 6.
- `values` reads values by the names the page's code uses, such as `t0.txt` or `sys0`. Give it the names you want, or none for every value. A component's name alone, such as `t0`, gives each of its attributes. A name that the page's code does not know is refused.
- `log` lists what the screen received and sent on its serial line, and what else happened outside the screen, such as a restart. Each line has a number, counted from 1. To read only what is new, give `after` the number of the last line you read.
- `send` returns the log lines added since your last `send` or `log`, the last 10 at most. They show what the screen sent back, such as a return code or the value from a `get`, and why an instruction did not run.

### After you change the app

The simulation does not pick up your edits while it runs. To apply them, run `nxwright check`, then `start_again`, which reads the folder again and restarts the app as if the screen had been switched off and on. The EEPROM and the log are kept. Without VS Code, a new simulation starts with an empty EEPROM.

If the folder no longer builds, `start_again` refuses, and gives the file and line of the error. Without VS Code, the app keeps running as it was. In VS Code, the debugger stops on the build error. See "The simulation is stopped in the debugger" under "When a tool refuses".

## When a tool refuses

A refusal often says what to do next, and some need the user. While a simulation refuses your actions, you can still read its screen, values, and log.

- **No VS Code window lets an agent start the folder.** Ask the user to open the folder in VS Code and turn on `nxwright.agents.allowControl` in their user settings. A workspace's settings cannot turn it on. The choice is the user's, so do not change their settings yourself.
- **VS Code waits for the user's answer.** The simulation's serial port is connected, so what the app sends reaches a real device, and the user must first allow or refuse your actions. Tell the user, and try again once they have answered.
- **The user did not allow agents to act on this simulation.** Their answer stands until the simulation ends. Stop acting on it, and tell the user.
- **A simulation already runs in the window.** A VS Code window runs one simulation at a time. Drive that simulation, or ask the user before you stop it, since it may be theirs.
- **The app's code stopped with an error.** Without VS Code, the simulation stays as the error left it, and goes on with your next action. In VS Code, the debugger stops the simulation at the error, and the refusal gives the error. The simulation then does not handle any action until the user resumes it in VS Code, so tell the user, or stop the simulation and start it again.
- **The simulation is stopped in the debugger.** It does not handle any action until the user resumes it in VS Code. The user may be debugging it, or the app's code may have stopped on an error. Tell the user.
- **The VS Code window did not answer within 60 s.** VS Code may still do what you asked. Look with `screen` or `list_simulations` before you try again. If you asked VS Code to start a simulation, it may be waiting for the user to answer a question first, such as whether to trust the folder, or to connect a serial port. The simulation starts once they answer.
