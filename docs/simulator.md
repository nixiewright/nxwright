# Simulating your app

The simulator runs your whole app in VS Code, and draws the screen in a panel. You can press the screen's components, and watch timers run and pages change. The simulator can also use a real serial port, and folders on your computer as the screen's SD cards. While the app runs, you can set breakpoints and step through your code, forward and back.

The simulator behaves like the Nextion Editor's simulator, except for the [Known differences](#known-differences). See [How nxwright runs Nextion code](screen-code.md) for how it runs each command.

## Starting a simulation

In nxwright's side bar, the Simulator section has two buttons:

- **Simulate project** starts the app from `program.nx`, like a screen being switched on. The code of `program.nx` runs, then the page it opens.
- **Simulate page** starts the app on the page shown, without running `program.nx`.

The same two actions are also available as the commands "nxwright: Simulate the app" and "nxwright: Simulate the app from the page shown", and from the **Simulate this page** button above a page's preview or its page file.

An AI agent can also run your app through `nxwright mcp`, on its own or in this simulator ([Letting an agent drive your app](mcp.md)).

To keep a setup, such as the page to start on, a serial port, or SD card folders, save it as a launch configuration of type `nxwright`. The Simulator section shows a button for each one. For the parameters, see [A simulation's launch configuration](../editors/vscode/README.md#a-simulations-launch-configuration). If a configuration leaves out a parameter that also exists in the extension's settings, the setting's value is used ([Settings](../editors/vscode/README.md#settings)). If a configuration leaves out `serialPort` and you have chosen a port for the project in the Simulator section, that port is used instead of the setting ([The port a simulation starts with](#the-port-a-simulation-starts-with)).

### Starting on a page

A launch configuration's `page` gives the page to start on, and its `values` give attributes the values to start with. The simulator reads them as if they were in the page file, so anything the page does when it opens, such as listing a file browser's folder, already uses them.

```json
"page": "settings",
"values": {"step.val": 5, "page0.t0.txt": "Hello"}
```

- A key may include the page's own name, the same as in the page's code. When the simulation starts on `keybdA`, `keybdA.loadcmpid.val` is the same as `loadcmpid.val`.
- A key may also give a component of another page, such as `page0.t0.txt`. That component's scope must be global.
- To start on a keyboard page, set `loadpageid.val` and `loadcmpid.val` to the page and the ID of the component that opens it. Without them, the simulator adds a page of its own that opens the keyboard, and shows the text the keyboard returns.

### Changing define values

To simulate with non-default values for the defines of `app.toml`, specify them in a launch configuration's `defines` ([source-folder.md](source-folder.md#apptoml)). For example, to try another colour and a longer title:

```json
"defines": {"ACCENT": "#ff3030", "TITLE": "A much longer application title"}
```

- A define whose default is a number takes a whole number, and one whose default is a text takes a text.
- A name that `app.toml` does not declare, or a value of the wrong type, stops the launch.
- **Simulate page** and the page preview use the defaults. To see other values there, change the defaults in `app.toml` temporarily.

### The EEPROM

A launch configuration's `eeprom` gives a file that keeps the EEPROM between simulations. Without one, the EEPROM starts empty each time.

- Each write the app makes reaches the file at once, whether it comes from `wepo` in code or from a typed instruction.
- If the file does not exist, the simulator creates it, with an empty EEPROM.
- A file longer than the EEPROM's 1024 bytes stops the launch, since writing it back would cut it.
- When a write fails, for example because another program has the file open, the log shows the error. The next write puts the whole EEPROM in the file again.
- The Nextion Editor's simulator keeps its EEPROM in `eeprom.bin`. Give that file in `eeprom` to share the EEPROM with it, one run after the other.

To start each simulation from the same EEPROM contents, add a `preLaunchTask` to the launch configuration that copies a saved file over the EEPROM file. For example, in `.vscode/tasks.json`:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Reset the EEPROM",
      "type": "process",
      "command": "python",
      "args": ["-c", "import shutil, sys; shutil.copyfile(sys.argv[1], sys.argv[2])",
               "${workspaceFolder}/eeprom-start.bin", "${workspaceFolder}/eeprom.bin"]
    }
  ]
}
```

Then, in the launch configuration:

```json
"eeprom": "${workspaceFolder}/eeprom.bin",
"preLaunchTask": "Reset the EEPROM"
```

### Chinese input

Chinese input (`pa_q` and `pa_txt`) needs the screen's pinyin table. You can give it in a launch configuration's `pinyinTable`, with one of these files:

- `input.bin`, in the Nextion Editor's installation folder.
- Any TFT file, such as one you built from your project, because every TFT file contains a copy of the table. Use one on a computer without the Nextion Editor.

A file that does not contain a pinyin table stops the launch. Without `pinyinTable`, the simulation uses the table of the installed Nextion Editor, if it finds one. Without either, Chinese input does not show any candidates.

## The panel

The panel draws the page the same way the page preview does, along with anything your code drew with commands such as `fill`, `line`, or `xstr`. It gets darker when your code lowers `dim`.

- While an event runs long, such as one drawing a chart, or while instructions arrive faster than they run, the panel is updated about every tenth of a second, or less often if drawing takes longer than that. When only a waveform's points change, the panel is updated up to 60 times a second, so that the waveform moves smoothly.
- A zoom bar above the panel works the same way as the page preview's, and Ctrl with the mouse wheel zooms around the pointer.

Closing the panel does not stop the simulation. To open it again, use **Show the screen** in the Simulator section, or the command "nxwright: Show the Simulator".

## The log

The log, in the Debug Console, lists what reached outside the screen, with the simulation's time:

- what it sent on the serial line;
- each EEPROM and GPIO access, with its value;
- the file commands;
- the commands that the simulator records but does not run ([screen-code.md](screen-code.md#commands-recorded-but-not-run)).

## Starting again

Starting again picks up any changes to your files, and is otherwise a power cycle, like `rest`. The EEPROM keeps what the app wrote.

If your files no longer build, the debugger stops on the error, and the app keeps running as it was. Continue, fix the file, then start again.

An MCU emulator stays connected while your app starts again. To restart the emulator, use "Start the emulator again" in the Simulator section ([Started with the simulation](mcu-emulator.md#started-with-the-simulation)).

## Debugging

You can debug the app while it runs.

- Breakpoints stop it. Stepping, the Call Stack view, and the Variables view work the same way they do for a test ([Debugging a test](testing.md#debugging-a-test)).
- You can step back through the app's last 900,000 to a million steps.
- Stepping forward past the last recorded step lets the app run on.
- An error in the code, such as dividing by zero, stops the app the same way as an exception. Continuing goes on from that line.

## Touches

Press the mouse on the panel to touch the screen.

- A press lands on the topmost visible component under the pointer, or on the page if there is none, and runs that component's or the page's Touch Press event.
- Letting go runs the Touch Release event of the component pressed.
- When `tsw` has turned a component's touches off, the component still takes the touch, but none of its events run.
- After `tsw 255,0`, a press on the page itself does not run any of the page's events.

### Touch captures

A page's touch capture runs its own Touch Press and Touch Release events before the component's.

- The touch capture's `val` is set to the ID of the component touched, or 0 for the page.
- When a page has several touch captures, only the last one runs.
- `tsw` does not turn a touch capture off.
- A `click` does not run the touch capture's events. It runs only the clicked component's event.
- When the touch capture's event changes page, the touched component's own event does not run.
- A file browser, select, sliding text, combo box, or data record acts on the touch before the touch capture's Touch Release event runs, so that event reads what the touch chose, such as a combo box's new `val`.

### Keyboards

A component whose `key` is 1 to 4 is bound to the keyboard of that number. When the component is released, by a press or a `click`, its Touch Release event runs, and then the keyboard's page opens. The keyboard's `loadpageid` is set to the number of the component's page, and its `loadcmpid` to the component's ID. See [keyboard](commands.md#keyboard) for how to add a keyboard page to your project.

A keyboard is a page of your project, and you can change it like any other page. Keep what the screen relies on: its `system_page` marker, and its two variables of global scope, `loadpageid` and `loadcmpid`.

What happens on OK or Cancel is up to the keyboard's own code. nxwright's keyboards, and the Nextion Editor's own, do this:

- OK writes the typed text back to the component: its `txt`, or its `val` for a number or an xfloat. Then the keyboard goes back to the component's page with `page loadpageid.val`.
- Cancel goes back to the component's page without writing anything.

A component bound to a keyboard must be of global scope, because the keyboard reaches it through `p[loadpageid.val].b[loadcmpid.val]`, which from another page reaches only components of global scope. Going back to the component's page also runs that page's `load` event again.

### Touch coordinates

`tch0` and `tch1` give the place of the touch going on, and `tch2` and `tch3` the place of the last touch.

- A press sets all four before its events run, even while the screen sleeps, and moving the press updates them.
- A release sets `tch0` and `tch1` to 0 before its events run, and `tch2` and `tch3` keep the last place.
- A press in a test is given only a component, so it changes none of the four.

When `sendxy` is 1, each press and release sends its place on the serial line, before its events run:

- 0x67;
- then x and y, in two bytes each, high byte first;
- then 1 for a press, or 0 for a release.

While the screen sleeps, each sends 0x68 instead, whatever the value of `sendxy`.

### Sending the component's ID

The Nextion Editor's "Send Component ID" ticks are kept in `sendkey`:

- `sendkey` 1, the Touch Release event's tick: when the component is released, it sends 0x65, its page's ID, its own ID, and 0.
- `sendkey` 2, the Touch Press event's tick: when the component is pressed, it sends 0x65, its page's ID, its own ID, and 1.
- These bytes are sent before the component's events run. When `sendxy` is 1, they come after the touch's coordinates (0x67).
- The page has the same ticks. When it is touched, it sends the same bytes, with 0 as its own ID.
- A component whose touches are off sends nothing. Neither does a `click`.
- When the press changes page, the release sends nothing.

### Drawing with a touch

While `thdra` is 1, a touch also draws in the colour `thc`, the same way drawing commands paint.

- The press draws a dot of 2 by 2 pixels, over the component in its pressed state.
- Each move of the touch draws a line from the last position to the new one.
- A touch that only wakes a sleeping screen does not draw.

### Dragging components

When you press a component whose `drag` is 1 and move the pointer, the component moves with it. Its `x` and `y` follow the touch, and the whole component stays on the screen.

- The component's press and release events run the same way as for any other press.
- A slider, and the other types that follow a press, keep following it instead of being dragged. A page and a hotspot are never dragged.
- `movex` and `movey` do not change.

## Time and timers

The simulation's time follows the wall clock while it runs.

- Each timer of the page shown that is on (`en` 1) runs its event every `tim` milliseconds.
- A `move` moves its component on the same clock.
- Timers run one at a time. Touches and the serial line take their turns between them.
- When the app's events take longer than its timers' periods, a late timer runs once, straight away, however many periods it missed, and the simulation's time falls behind the wall clock. This can happen while the debugger records every step.
- A `delay` holds the simulation for as long as it lasts. Touches wait for it.

The real-time clock starts at your computer's time of day, and moves with the simulation's time. `rtc0` to `rtc6` give its year, month, day, hour, minute, second, and day of the week, from 0 for Sunday. Code can set any of `rtc0` to `rtc5`, and the simulator ignores an impossible date or time, such as month 13. Starting again keeps the clock running, the same way a screen's clock runs on while the screen is off.

### Sleep

- `sleep=1` puts the screen to sleep. The panel goes dark, and the timers stop.
- `thsp` puts the screen to sleep after that many seconds without a touch, and `ussp` after that many seconds without serial data.
- While the screen sleeps, events do not run. When `thup` is 1, the touch wakes the screen when it ends.
- Instructions from the serial line run while the screen sleeps. When `usup` is 1, an instruction wakes the screen first, then runs. A `click` among them does not run any event.
- Code that puts the screen to sleep ends its event, so code after the sleep in that event cannot wake the screen again. The Nextion Editor's simulator does the same in a press's event, a timer's event, and a page's `load` and `unload` events.
  - In a page's `unload` event, the page change stops at that point. The old page stays shown.
  - In a `load` event, the new page shows, but its `loadend` event does not run.
- When a press's event puts the screen to sleep, its release counts as a touch on a sleeping screen. The release sends 0x68, and wakes the screen when `thup` is 1. The component's Touch Release event does not run.
- Falling asleep by `thsp` or `ussp` sends 0x86 on the serial line. Waking by a touch sends 0x87. Waking by the serial line sends nothing. `sleep` set by code sends neither.
- However it wakes, the screen then shows the page that `wup` gives, the same way a `page` command does, except that the old page's `unload` event does not run. When `wup` is 255, or does not give a page, the screen stays on the page it was on.
- Waking by a touch starts the `ussp` count again.

## Changing page

A `page` command takes the page's name, its number, or an expression that gives its number, such as `page returnPage.val` or `page appid&0x000000FF`. If no page has that number, the command answers 0x03, and the screen stays on the page it shows.

- The command runs the old page's `unload` event, then the new page's `load` and `loadend` events, inside the event that ran the command.
- The rest of the event that ran the command does not run, and neither do the events whose clicks or calls led to it.
- A `return` in a page's `load` event keeps its `loadend` event from running. This is also true when the simulation starts.
- The panel keeps showing the old page until the new one's `load` event ends.
- A page has no background when its `sta` is 0, or when `sta` is 2 and the page has no picture, or a picture the source folder does not have. Such a page, for example a dialog, is drawn over whatever the screen showed when the page opened. The first page after the screen starts is drawn over black.
- Entering a page starts its components from its `.page.toml` file, shown and taking touches, except those of global scope (`vscope` 1). These keep their values, whether they show (`vis`) and take touches (`tsw`), and a waveform's points ([Waveforms](#waveforms)).
- A `vis 255` or `tsw 255` also applies to each component of global scope on the page shown, and those components keep it. The next page's other components start from their page file.

## Drawing commands

Drawing commands paint over the page, in order, until a new page clears what they painted.

A component is drawn again over the painting when the code changes it, even to the value it had, or shows it with `vis`. A button that is pressed or released, a slider whose knob a press moves, and a component given to `ref` are drawn again too.

When a component is drawn again, it shows on the page's own background, and what drawing commands painted under it disappears. On a page without a background, the component shows over what the screen showed when the page opened. The components it overlaps are drawn again with it, and those they overlap in turn, and so on, in ID order.

- When your code moves or resizes a component, the page's background comes back where the component was. The simulator draws the components in that area again, and those they overlap in turn. A `move` does the same at each of its steps, about every 16 ms, so the background comes back all along its path.
- Between `ref_stop` and `ref_star`, a component your code changes keeps showing as it was until `ref_star`. So does a component that `vis` hides. A component that `vis` shows appears at once.
- When your code changes page between `ref_stop` and `ref_star`, the page before keeps showing. Your code runs on the new page meanwhile, and a touch goes to the new page's components. `ref_star` shows the new page, with what your code painted on it, and starts its [opening effects](#opening-effects).

### Opacity

The panel draws each component with opacity `aph`, from 0 (invisible) to 127 (opaque). Each part is blended over what lies under it, in turn: a text's background, then its words.

## Components that act on their own

### Buttons

- A button's `val` is 1 while it is pressed, and 0 once it is released. `val` is set before the press's and the release's events run.
- A button of global scope whose press changes page does not get a release, and its `val` goes back to 0.
- A `click` sets `val` the same way as a press and a release: `click b0,1` to 1, and `click b0,0` to 0, before the event runs.

### Checkboxes, radios, dual-state buttons, and switches

These components flip their `val` between 0 and 1 when pressed. The flip happens before the press's events run, a touch capture's included, so the events read the new value.

A radio is not grouped with the page's other radios, so a press turns it off when it is on.

### Sliders

- Pressing a slider puts its knob's middle under the pointer, and dragging moves it along.
- The knob stays where the pointer left it, even when `ref` draws the slider again. When your code sets `val`, even to the value it has, the knob moves back to the place of that value.
- Each move that changes the slider's value runs its Touch Move event (`slide`).

### Scrolling texts

A scrolling text that is on moves its text `dis` pixels every `tim` milliseconds.

- The text starts just outside its component, comes in at its first step, and comes round again once it has gone.
- Code reads where the text is in `vvs0`, or in `vvs1` when it moves up or down.
- Code reads the text's width and height in pixels in `vvs2` and `vvs3`, as it is drawn: with `spax` between characters, `spay` between lines, and the lines `isbr` wraps. The text is measured when its page opens, and at each step before it moves.
- Code setting `vvs0` or `vvs1` moves the text to that place, and the text moves on from that place. A new `txt` or `font` keeps it where it is. `en` 0 stops it where it is.
- A new `txt` or `font` shows at once. Until the next step measures it, `vvs2` and `vvs3` keep the old size, and `xcen` or `ycen` aligns the new text by that old size. A stopped text keeps the old size.
- A new `dir` the other way along the same line, such as 1 after 0, turns the text round where it is.
- A new `dir` that switches between across and up or down takes effect at the text's next step. That step puts the text just outside its component, where it would come back in, and moves it no further. Until then, the text shows, and code reads its place, as before. A stopped text does not turn.
- While the text moves, code setting `tim`, or setting `en` to 1, does not delay it, even when the value is the same. The text's next step comes `tim` after its last one, or at once if that time has passed. A timer is different: setting its `tim` or `en` starts its count again.
- After `en` 0, code setting `en` to 1 counts `tim` from then.

### Sliding texts

A sliding text lays out its lines the same way as a text, from the top inside the border, and wraps them at the component's width when `isbr` is 1.

- `maxval_y` is how far a touch can scroll the text: how much taller the lines are than the inside of the border. The simulator works it out when the page opens, and again when code sets `txt` or `font`.
- Code setting `val_y` can scroll the text up to 32 pixels past `maxval_y`, and up to 32 pixels above its top. The last line never scrolls above the top.
- A `val_y` that code sets reads back unchanged until the event ends, or until a `doevents`, when the screen brings it back within these limits.
- A drag scrolls the text as far as the touch moves, up to `maxval_y`, and the text stays where the drag leaves it.
- `left` sets when the scroll bar's thumb shows: never, while a touch scrolls the text, or always.
- A sliding text pressed without scrolling is not drawn again until the touch ends.

### Combo boxes

- A tap on the box opens its list when the tap ends. The next tap closes it.
- While the list is open, a press anywhere on it runs the box's Touch Press event, whether on an item, a scroll mark, or a gap between items.
- The release chooses the item under it, sets `val` and `txt`, and closes the list. Then the box's Touch Release event runs.
- Under the list, a component that comes before the box in ID order does not take the press.
- A component that comes after it is drawn over the list. That component takes the press as usual, and the list stays open. The list also stays open when the page is pressed elsewhere.
- Code setting `down` opens or closes the list.
- Code setting `val` sets `txt` to its item, and moves an open list to show it. A `val` past the last item is ignored, and the item chosen before stays chosen.
- A new `path` changes neither `val` nor `txt`.
- A drag on the open list scrolls it by a whole item each time the touch moves an item's length. The drag does not choose an item. The list stays open.

### File browsers

- A file browser lists its folder, `dir`, when its page opens, and whenever code sets `dir`.
- If `dir` is in `ram/`, the file browser has no entries, even when `ram/` has files.
- `up()` goes to the folder above and lists it, but goes no higher than the card's own folder.
- The file browser lists the folders first, unless `psta` is 0, and then the files its `filter` lets through. Each group is in alphabetical order, ignoring capitals.
- `qty` counts the entries.
- Each listing clears the selection (`val` -1, `txt` empty), scrolls to the top (`val_y` 0), and sets how far the entries scroll (`maxval_y`). When code sets `dir` or runs `up()`, `maxval_y` takes its new value only once that event ends.
- Code setting `val` selects an entry. `txt` gives its name. A folder's name ends with "/".
- Code setting `val_y` scrolls the entries, up to 32 pixels past `maxval_y`, and up to 32 pixels above their top. In the event that listed the folder, it scrolls them no further than `maxval_y`.
- A `val_y` that code sets reads back unchanged until the event ends, or until a `doevents`, when the screen brings it back within these limits.
- A touch takes effect when it ends, before the `up` event runs. A tap on a file selects it. A tap on a folder opens it.
- A tap on an empty place, past the last entry, sets `val` to the number of entries, and `txt` to nothing.
- A tap between two places, or right of the last column, clears the selection: `val` goes back to -1. A tap left of the first column changes nothing.
- A tap on the border above the entries counts as a tap just inside it, scrolled or not.
- A drag scrolls the entries, and does not select any.

### Selects

- A select's `path` contains its lines, one at each line break.
- Code setting `val` picks a line. `txt` gives its text. A `val` past the last line, or below 0, changes nothing: `val` and `txt` keep theirs.
- Only code setting `val` sets `txt`. Opening the page, or changing `path`, does not.
- A drag turns the lines. When the touch ends, the line left in the middle is picked, before the `up` event runs.
- A tap does nothing.

### Data records

- A data record reads its data file when its page opens, and whenever code sets its `path`. If the file doesn't exist and `mode` is 1, the data record creates it.
- When `order` is 0, the newest record is at the top of the table.
- The data record's methods change the file, and the table follows ([Data records](screen-code.md#data-records)).
- Code setting `val_y` scrolls the records, up to 32 pixels past `maxval_y`, and up to 32 pixels above their top, which leaves an empty band under the titles.
- Code setting `val_x` scrolls the columns, from 0 to `maxval_x`. `maxval_x` counts the line at the right of the last column.
- A `val_y` or `val_x` that code sets reads back unchanged until the event ends, or until a `doevents`, when the screen brings it back within these limits.
- Code changing its `path`, `format`, `hig`, `gdw`, or `gdh` works out `qty`, `txt`, `maxval_y`, and `maxval_x` again. A new `dir` leaves them as they were, until one of those changes.
- When `dis` is 1, a tap chooses the record under it, setting `val` and `txt`. This happens after the Touch Press event and before the Touch Release event.
- A tap on the titles' row, or below the last record, chooses nothing.
- A drag scrolls the records, and does not choose any.

Only one data record can use a data file at a time. When two data records give the same `path`, the first one to open the file keeps it:

- The first data record keeps the file while other pages show, and opens it again when its page opens again. It lets the file go when code changes its `path`.
- The second data record cannot open the file. It shows "Cannot open file:" and the path, its `qty` is 0, and it sends the error code 0x06 twice when its page opens ([Return codes](#return-codes)).
- The second data record's methods change nothing while the first one keeps the file. Once the file is free, the next method opens it.
- Code setting a data record's `path` to a file another one keeps answers 0x06.

Data records keep at most 8 files at once, across pages. A data record that finds 8 kept by others cannot open its own, the same as when another data record keeps it. A data record that keeps a file can still change its `path`, because it lets the old file go first.

A data record whose `path` is empty shows "File Lost:". It does not keep a file, so it does not shut out any other data record, and it does not send an error code. A data record also shows "File Lost:", followed by the path, when its file in `ram/` is missing ([Files in `ram/`](#files-in-ram)).

A data record whose `init` is 1 does not open the file its page file gives:

- It shows its titles and no records, and its `qty` is 0. It does not create a missing file.
- It does not keep the file, so another data record can open it.
- Its methods change nothing, and send no error code.
- Once code sets its `path`, even to the same file, it works the same as when `init` is 0.

### Animations, videos, and sounds

Animations, videos, and sounds start playing when their page opens.

- A run lasts the component's `stim`: the sum of an animation's frames' durations, a video's frames at its frame rate, or a sound's samples.
- The panel draws the frame that `tim` falls on, in the frame's own colours, without reducing them to the screen's 16 bits.
- When a run ends, `playend` runs. When `loop` is 1, a new run starts at once. Otherwise the last frame stays, and `en` becomes 0. Setting `en` to 1 then starts a new run.
- Code setting `en` to 0 stops the component and goes back to the start. 2 pauses it, and 1 makes it play on.
- Setting `tim` moves the run to that time.
- Setting `vid` to another ID loads that one, at its start. It plays if the player was playing, and stays stopped or paused if not. Setting `vid` to the ID loaded changes nothing, playing or not.
- Setting `path` plays that file from its start, even if it is the file already playing.
- An animation's or a video's `dis` is its speed, in percent. The Nextion Editor gives its range as 10 to 1000, but code may set more or less, and it plays that fast. At 0 it stands still. A sound's `dis` does not change its speed.
- A video's `fps` always reads its file's frame rate.
- A sound writes to the log when it starts, pauses, stops, or ends.

A video's or a sound's `from` sets where its file comes from:

- 0, the default: from the project. `vid` gives the video or the sound, by its ID.
- 1: from an SD card. `path` gives the file, such as `sd0/1.wav`.

With `from` 1:

- When the card's folder does not have that file, nothing plays, and the component sends the error code 0x06 ([Return codes](#return-codes)) when its page opens and when code sets its `path`.
- When a card has no folder, the simulator keeps the card in memory, the same way the file commands do. A file missing from that card answers 0x06 too.
- With an empty `path`, nothing plays, and the component does not send an error code.

Unlike a video or a sound, an animation cannot play a file from the SD card. It always plays from the project.

### Waveforms

A waveform draws the points that code adds with `add`, each channel in its colour, one point per column.

- When `dir` is 0, the default, a new point enters at the left and pushes the others right.
- When `dir` is 1, a new point enters at the right and pushes the others left. The first point stays at the left edge until the points fill the waveform.
- When `dir` is 2, the points move the same way as for `dir` 1, but the last one is always at the right edge.
- A value of v is drawn v × `dis` / 100 pixels up from the bottom, cut toward zero.
- `cle` clears the points.
- A waveform of global scope (`vscope` 1) keeps its points while another page shows. Other waveforms start empty each time their page opens. Starting the app again clears every waveform.

### The signal generator

The signal generator stands in for devices on the serial line. Open it with **Signal generator** in the Simulator section. It can run several generators at once, of two kinds:

- A waveform generator sends points to your app's waveforms, the same way a device would with `add`, so that you can see a waveform move.
- A value generator sends instructions that carry a value, such as `temp.val=215`, so that you can run the code that reads it.

Each generator follows a wave:

| Setting | What it is |
| --- | --- |
| Shape | Sine, square, triangle, sawtooth, inverted sawtooth, pulse, random, or custom. |
| Min, Max | The wave's lowest and highest values: from 0 to 255 for a waveform generator, and from -2147483648 to 2147483647 for a value generator. |
| Interval | The milliseconds between two points. |
| Period | The number of points in one cycle of the wave. |
| Duty | For a pulse, the percentage of the cycle spent at the highest value. |
| Noise | The most that is added to or taken from each point, at random. |

A custom wave plays a list of values in a loop, one value for each point. You can type the values, or read them from the first column of numbers in a CSV file.

- You can change the settings while a generator runs, and each change takes effect at the next point.
- Generators keep running when the app starts again.

You can save the panel's generators to a file. Opening a file stops the generators that are running, and replaces them with the file's. To start saved generators with the simulation, give their file as the launch configuration's `signalGenerators`.

**A waveform generator** feeds one or more waveforms, on the channels you tick.

- Each channel starts a quarter of its wave's cycle after the channel before it, so that channels with the same wave do not draw over each other.
- If you feed waveforms that have different numbers of channels, each waveform gets only the channels it has.
- A waveform gets points only while its page is shown.

The points arrive the same way as instructions from the serial line:

- `com_stop` holds the points until `com_star`.
- The points count as serial data, so while they arrive, `ussp` does not put the screen to sleep, and a sleeping screen wakes if `usup` is 1.
- The screen answers each point as `bkcmd` specifies. The log shows those answers, but not the points themselves.

At each point of its wave, **a value generator** sends the instructions you type, in order. Type one instruction on each line, and write `{value}` where the wave's value goes:

```
temp.val={value}
click refresh,1
```

A screen has no event for a value that changes, so a device often sends a `click` after the value, to run the event where your code reads it.

- If you tick **Only when the value changes**, the generator skips a point whose value is the same as the last one it sent. The first point after the app starts again is always sent.
- Write the instructions in strict Nextion syntax, the way a device sends them. To put the value in a text, write `{value}` inside the quotes: `t0.txt="x={value}"` sends `t0.txt="x=215"`. Strict Nextion syntax cannot join a number to a text the way nxlang can, so `t0.txt="x="+{value}` gets the return code 0x1B.
- The instructions arrive the same way as an instruction you type ([Typing an instruction](#typing-an-instruction)): the log shows each one, and the screen answers it as `bkcmd` specifies.
- Every instruction is sent whichever page shows, so one for a component of another page gets the return code 0x1A.
- If an instruction such as `rest` starts the app again, the instructions after it are not sent for that point of the wave.

A value generator can also have conditions, for example to stand in for a sensor's alarm line. A condition is a switch that the wave's value turns on and off. Each time the switch changes, the condition sends instructions of its own, such as `click alarm,1`, and these can use `{value}` too. A generator with conditions does not need instructions of its own.

| Setting | What it is |
| --- | --- |
| Turns on above, or below | The level the value must go past for the switch to turn on. |
| And off below, or above | The level the value must come back past for the switch to turn off. Leave it empty for a switch that turns off as soon as the value is no longer past the first level. |
| Each time after | How long the value must stay past a level before the switch changes, in milliseconds. |

- If the value wavers around the first level, set the second level a little apart from it, so that the switch does not turn on and off again and again.
- A switch starts off, and goes back to off when the app starts again. If the value is already past the level, the switch turns on, and the condition sends its instructions for turning on, even if it sent them before the app started again.
- At each point, the generator's own instructions are sent first, then each condition's, so the event that `click alarm,1` runs can read the value the generator just set.
- A condition is checked at every point, including one that **Only when the value changes** skips.

### Opening effects

When a page opens, its components whose `effect` is 1 to 8 slide in from wholly off the screen.

This happens on the Edge and Intelligent series only. The Basic, Enhanced, and Discovery series do not support `effect`, so their components are drawn in place at once.

- The components start sliding once the page's `load` event ends, each to where that event left it. The `loadend` event runs when they start.
- On a page entered between `ref_stop` and `ref_star`, the components start sliding at `ref_star`, each to where your code left it by then. The page's `loadend` event still runs when its `load` event ends.
- Each comes from beyond the edge or corner its effect gives, in a straight line, at a steady speed, over `time` milliseconds.
- The components with the highest `first` slide in together. Then those of the next lower `first`, once those are in place.
- A component waiting its turn is not drawn.
- While a component slides, code reads its own `x` and `y`, and touches land at that position.
- Code hiding or showing a component puts it in its place at once.
- Code moving a component during its slide, in `loadend` or a timer's event, changes the `x` and `y` that code reads, but the component slides on. When the slide ends, the component stays where the slide took it, and its `x` and `y` go back to that place.
- A component sliding in over what drawing commands painted shows over it, and the page's background comes back along the path it slid.

## The serial line

The log shows what the screen receives and sends on its serial line, in lines that start with `SIM RECV:` and `SIM SEND:`. A launch configuration's `logReceived` and `logSent` set how each is shown: as text (`text`), in hexadecimal (`hex`), or `both`.

- By default, what the screen receives shows as text, and what it sends in hexadecimal.
- As text, the FF FF FF that ends an instruction or a reply is left out. A byte that is not a character shows as `\xNN`.
- A note that is not data goes in angle brackets, as in `SIM SEND: <nothing: text 'ā' incompatible with project encoding iso-8859-1>`.

### Return codes

After an instruction, the screen can send a return code on the serial line, such as 0x01 for success or 0x06 for an invalid file operation. The system variable `bkcmd` sets which codes the screen sends:

- 0: none;
- 1: only on success;
- 2: only on failure (the default);
- 3: both.

In this page, "sends the error code 0x06" means the screen sends it when `bkcmd` is 2 or 3.

### Start-up and ready

When your app starts, the screen sends a start-up code (00 00 00 FF FF FF), then "ready" (88 FF FF FF). A program on the other end of the serial line often waits for them before sending anything.

The code of `program.nx` sends both, with this line:

```
printh 00 00 00 ff ff ff 88 ff ff ff
```

- A new project has this line, whether the Nextion Editor or `nxwright new` created it. Without the line, the screen sends neither code.
- The simulator runs the line at each start, `rest` included. A simulation started on a page does not send the codes, because it does not run `program.nx`.

### A serial port

A serial port of your computer can carry the screen's serial line, like the "User MCU input" mode of the Nextion Editor's simulator. The Simulator section and the log call it the MCU port, because a microcontroller (MCU) is usually at its other end. Give the port with a launch configuration's `serialPort`, or connect it from the Simulator section while the simulation runs.

```json
"serialPort": {"name": "COM4", "baud": 115200}
```

On Linux, a port has a name such as `/dev/ttyUSB0`.

- You set the port's rate with `baud`, in the launch configuration or in the Simulator section. Without it, the rate is 9600, the screen's rate at power-on.
- The line is 8 data bits, no parity, and 1 stop bit.
- Setting the system variable `baud` or `bauds` changes a screen's rate, but the simulator's port keeps the rate you set.
- What arrives is cut into instructions at each FF FF FF, and read in the project's encoding. Each one runs in turn, the same way as a typed instruction.
- When the screen starts again, for example with `rest`, it drops what it has received but not yet run.
- While the simulation is paused, instructions that arrive wait, and do not count against the screen's serial buffer ([Holding instructions](#holding-instructions)).
- You can connect the simulator to a program on the same computer by using a virtual pair of ports. On Windows, com0com creates one. On Linux or macOS, `socat -d -d pty,raw,echo=0 pty,raw,echo=0` creates one, and prints the two ports' names.
- When a port cannot open, or is lost, the log shows the reason. The simulation keeps running without the port.
- When the port does not take what the simulator sends in time, for example because nothing reads the other end, the simulator drops the rest of the write and logs it, so that the simulation does not freeze.

### A program over TCP

The screen's serial line can also go to a program over TCP, so a program on your computer needs neither a serial port nor a virtual pair of ports. The program listens at an address, and the simulator connects to it. Give the address with a launch configuration's `serialPort`, or choose TCP in the MCU port list of the Simulator section and enter the address.

```json
"serialPort": {"tcp": "127.0.0.1:7000"}
```

- The address is a host and a port number. The host can be another computer, but the bytes are not encrypted.
- The program must be listening when the simulator connects. If the connection cannot open, or the program closes it, the log shows the reason and the simulation keeps running. You can connect again from the Simulator section.
- A TCP connection has no rate, so setting the system variable `baud` or `bauds` does not affect it.
- You can join a TCP connection to a real screen, the same way as a serial port ([A real screen](#a-real-screen)).

### An MCU emulator

If your project has an MCU emulator ([mcu-emulator.md](mcu-emulator.md)), the simulator can listen on your computer for the emulator to connect. This is the Emulator port, and the project's simulations start with it unless you chose another port or set one in the Simulator settings ([The port a simulation starts with](#the-port-a-simulation-starts-with)). You can also give it with a launch configuration's `serialPort`, or choose Emulator in the MCU port list of the Simulator section.

```json
"serialPort": "emulator"
```

- If you have the Python Debugger extension, the simulation starts the emulator, and your app waits for the emulator to connect before it starts ([Started with the simulation](mcu-emulator.md#started-with-the-simulation)).
- The Simulator section shows the address the simulator listens at, for an emulator you start yourself ([The simulator listens](mcu-emulator.md#the-simulator-listens)).
- The port counts as connected while the simulator listens, so you can join it to a real screen before the emulator starts ([A real screen](#a-real-screen)). Stopping the emulator does not end the join.

### The port a simulation starts with

The port you connect from the MCU port list of the Simulator section is remembered for the project, and the project's next simulations start with it. Choosing None is remembered too, but disconnecting is not, so the next simulation starts with the same port again.

A simulation takes its port from the first of these that is set:

1. The `serialPort` of its launch configuration. `"serialPort": "none"` starts the simulation without a port.
2. The port you last chose in the Simulator section for the project.
3. The serial port of the Simulator settings.
4. Emulator, if the project has an MCU emulator.

### Typing an instruction

While a simulation runs, you can send the screen an instruction from the field in the Simulator section. The screen runs it as if it came from the serial line. The log shows what the screen sends back, such as `get`'s reply, or the instruction's return code if `bkcmd` is set to send it ([Return codes](#return-codes)).

An instruction that answers, such as `get` or `sendme`, does not send a code for its success. Neither does one that changes page. A typed `click` answers its success before its event runs, and what the event sends follows.

A failed instruction has no effect. The screen answers it with one of these codes:

| Code | For |
| --- | --- |
| 0x00 | An instruction the screen does not know: a first word that is no command. A command the screen's series lacks. `add` alone. |
| 0x02 | A component ID the page lacks. |
| 0x03 | A page the app lacks. |
| 0x04 | A drawing command's picture the project lacks. |
| 0x05 | `xstr`'s font the project lacks. |
| 0x12 | A waveform, or a channel, the page lacks. `addt` for more than 1024 bytes. |
| 0x1A | A name the screen does not know (see below). A first word containing a capital letter, or `movelayer`. A system variable the screen's series lacks. A `twfile` size that is not a number. |
| 0x1B | An operator other than `+` or `-=` used on a text. A number joined to a text with `+`. |
| 0x1C | A picture or font ID the project lacks. A `txt` given a number, or a `val` a text. An assignment to an attribute that code cannot change, such as `t0.w=10` ([build-rules.md](build-rules.md#attributes-code-cannot-change)). The attribute keeps its value. `addr` given a number other than 0, or 256 to 2815. |
| 0x1D | An EEPROM access that does not fit in it. `wept` at a place before 0. |
| 0x1E | A command given the wrong number of parameters, or none where it needs some. |
| 0x20 | An escape the screen does not read. |
| 0x24 | The screen's serial buffer overflowed ([Holding instructions](#holding-instructions)). |

A name the screen does not know, 0x1A, includes:

- an attribute that its component does not have, because of how the component is set up or because of the screen's series ([build-rules.md](build-rules.md#attributes-a-component-lacks)), such as a variable's `val` while the variable stores text, or `movex` on a Basic screen. The values a simulation starts from leave these attributes out.
- an attribute the screen does not support ([Attributes the screen does not support](screen-code.md#attributes-the-screen-does-not-support)).
- `usize` or `u[]` read while `recmod` is 0 ([Protocol reparse mode](#protocol-reparse-mode)).

When a line of an event's code fails, the screen answers at once, and the event goes on. An ignored SD card command answers its own code ([The SD cards](#the-sd-cards)), and a `covx` to hexadecimal of an odd length answers 0x1B ([The text commands](screen-code.md#the-text-commands)).

### A real screen

A real screen can run beside the simulation, so that you can compare the two, like the "Simulator and Nextion Device" mode of the Nextion Editor's simulator. You connect it on a serial port of its own, from the Screen port area of the Simulator section. Connecting does not send the screen anything.

- The Find button looks for the screen's rate, which takes a few seconds, then connects at that rate. At each rate it tries, it sends the bytes that end protocol reparse mode ([Protocol reparse mode](#protocol-reparse-mode)), then `connect`.
- The screen port keeps the rate it was connected at. After an instruction changes the screen's rate, such as `baud=115200`, connect again at the new rate, or press Find.
- While the screen is connected, you can send a typed instruction to the simulator, to the screen, or to both, with the two boxes under the Serial input field.
- The log shows what the screen receives and sends in `SCR RECV:` and `SCR SEND:` lines, beside the simulator's, in the forms that `logReceived` and `logSent` set.
- You compare the two yourself, from the log, because nxwright does not match up the screen's replies with the simulator's. They can also drift apart, because a touch on the panel reaches only the simulation, and a touch on the real screen reaches only the screen.
- The Start the screen again button sends `rest` to the screen, and Start both again sends it to the screen and the simulation at once.
- An agent can't reach the real screen. Its instructions go to the simulator only, and the log it reads leaves out the screen's lines.

You can also join the MCU port to the real screen, in place of the simulator. The program on the MCU port then talks to the real screen through nxwright, and the log shows what passes in both directions. To join them, connect both ports, then choose the real screen in the Goes to list, under the MCU port.

- Bytes pass on unchanged, as they arrive.
- To end the join, choose the simulator in Goes to again. Until then, you can't type instructions or change either port.
- Both ports close when either one is closed or lost, or does not take a write within a second. The log gives the reason.
- You can still start the screen again from the Simulator section. The program then receives the screen's start-up bytes, the same as after a power cycle.
- Both ports change to the screen's new rate when the program sends `baud=`, `bauds=`, or `rest`, and when you start the screen again.
- nxwright sends the screen two instructions of its own, and does not pass the screen's answers to them on to the program. When the ports are joined, it asks the screen `get bauds`, to learn the rate the screen starts at. After each change of rate, it sends FF FF FF, so that the screen does not take the stray bytes that the change can put on the line for the start of the program's next instruction. The log shows each of these in a line starting with `bridge:`.
- nxwright cannot see a rate change made by the app's own code, such as `baud=115200` in an event. The line then stops working. To fix it, choose the simulator in Goes to, connect both ports again at the new rate, and join them again.

To compare the simulator and the real screen in the log, you can join the MCU port to both at once. Both then receive the program's bytes, but only one of them answers the program, and Goes to has an entry for each choice. The other one's answers show only in the log. The points about joining the MCU port to the real screen apply here too.

- Sending to both works best for an app used only as a display, because touches make the two drift apart.
- When the simulator answers the program, keep the simulation running while the program changes the rate. If the debugger holds the simulation at that moment, its answer arrives after both ports have changed rate, and the program can't read it.

### Holding instructions

`com_stop` holds the instructions that arrive on the serial line. It works the same whether it arrives on the serial line or is run by code.

- Held instructions are logged. They neither run nor answer.
- `com_star` runs them, in order.
- On the serial line, `com_star` works while instructions are held. Run by code, it runs them once its event ends.
- Neither command sends a return code, whatever `bkcmd` is set to.
- The screen's serial buffer has room for 1024 bytes. When the held instructions would pass that, the screen drops them, keeps the instruction arriving, and answers 0x24.
- `com_star` with nothing held changes nothing. Neither does a second `com_stop`.
- While instructions are held, touches, timers, and page changes go on.
- `rest` drops the held instructions, but the line stays held after the screen starts again, until a `com_star`. Starting the simulation again yourself frees it.

### Transparent data

`addt`, `wept`, and `twfile` take the bytes that come next on the serial line as data, not as instructions.

```
addt 1,0,100
```

After this instruction, the screen adds the next 100 bytes as points to channel 0 of the waveform whose ID is 1. In the same way, `wept 10,100` writes the next 100 bytes to the EEPROM, from byte 10. `twfile "sd0/log.txt",100` writes them as the file `log.txt` on the SD card.

- The screen sends FE FF FF FF when it is ready for the bytes, and FD FF FF FF once it has them all, whatever `bkcmd` is set to.
- Every byte counts as data, FF included. The bytes after the last one are instructions again.
- During a transfer, an instruction you type in the Simulator section is sent as data.
- The screen ignores `addt` for a waveform or a channel the page lacks, or for more than 1024 bytes, and answers 0x12. It ignores `wept` at a place before 0, and answers 0x1D. What it ignores of `twfile` is in [What the file commands do](#what-the-file-commands-do).
- `twfile` writes its file once it has all the bytes. A transfer that another one cuts short writes nothing.
- How `twfile` takes its bytes follows the vendor's instruction set. It has not been checked against a screen ([Different from the Nextion Editor's simulator](#different-from-the-nextion-editors-simulator)).

### Protocol reparse mode

When code or an instruction sets `recmod` to 1, every byte that arrives on the serial line goes into a buffer, and your code reads it there. A program on the other end can then use a protocol of its own.

```
n0.val=usize
ucopy n1.val,0,2,0
udelete 2
```

This code reads how many bytes the buffer has, copies its first 2 bytes into `n1.val`, the first one lowest, and removes them from the buffer.

- `u[0]` reads the buffer's first byte. Past its last byte, `u[]` and `ucopy` read 0.
- `ucopy t0.txt,0,4,0` copies 4 bytes into `t0.txt`, as text in the project's encoding.
- While the mode is on, the screen does not answer anything, apart from 0x24 when the buffer overflows. The buffer has room for 1024 bytes, less any held instructions ([Holding instructions](#holding-instructions)).
- The text `DRAKJHSUYDGBNCJHGJKSHBDN`, then FF FF FF, ends the mode and sets `recmod` to 0. Your code can also end it, by setting `recmod` to 0. Either way, the buffer empties.
- An instruction you type in the Simulator section goes into the buffer.
- While `recmod` is 0, reading `usize` or `u[]` answers 0x1A, and `ucopy` and `udelete` do nothing.

### Address mode

When code or an instruction sets `addr` to an address from 256 to 2815, the screen runs only the instructions that start with that address, low byte first. A program on the other end can then talk to several screens on one serial line.

```
addr=258
```

After this, an instruction runs only when its first two bytes are 02 01, or FF FF, the address of every screen. The screen drops any other, and the log shows it.

- The screen's answers do not carry an address.
- `addr` can be 0, or 256 to 2815, and any other number answers 0x1C. To end the mode, set `addr` to 0 in an instruction that starts with the screen's address.
- An instruction you type in the Simulator section runs as if it carried the screen's address.
- `addr` goes back to 0 at each start, the same as in the Nextion Editor's simulator. A real screen keeps its address when it is turned off.

## GPIO pins

While the app runs, the Simulator section lists the screen's 8 GPIO pins, io0 to io7. For each pin, it shows what code set the pin up as, and its level. Code reads and writes the pins as `pio0` to `pio7`.

- Click an input's level to switch it, the same as a button or a switch wired to the pin.
- A pin bound to a component with `cfgpio` shows the component's name. Setting the pin to 0 presses the component, and setting it back to 1 releases it.
- A screen of the Basic series has no GPIO pins, and the section does not list any.

Every input reads 1 until you change it, like a pull-up input that nothing drives. To start the app with other levels, give them in the launch configuration's `gpioInputs`:

```json
"gpioInputs": {"pio2": 0}
```

The levels stay when the app starts again, because they belong to what is wired to the pins. For how code reads and writes the pins, see [GPIO](screen-code.md#gpio).

## The SD cards

The screen's SD cards can be folders of your computer. A launch configuration's `sdCard0` gives one for `sd0/`, and `sdCard1` one for `sd1/`, each by its full path. A drive's root folder is rejected. The Nextion Editor's simulator keeps its own cards in `sdcard0` and `sdcard1`, in its settings folder.

- `sd0/presets/a.cfg` is the file `presets/a.cfg` in the folder given for `sd0/`.
- The app's file commands act on the folder's files, for real. What they change stays after the simulation, even if you step back or start again.
- To start each simulation with the same files, replace the folder with a saved copy before each launch, with a `preLaunchTask`. See [The EEPROM](#the-eeprom) for an example of how to do this for a single file.
- If a card has no folder, its files are kept in memory, the same way as in a test.
- A file whose path starts with `ram/` is kept in memory too, in the space your project sets aside for `ram/` files ([Files in `ram/`](#files-in-ram)).
- The screen does not create, delete, or rename anything on a path such as `x.bin`, which is neither on a card nor in `ram/`. `sd0/` and `sd1/` must be in lower case, so `SD0/a.bin` is not on a card either.

### External pictures

External pictures show their images from the card: a PNG, a JPEG, or PictureBox's `.xi` file ([format.md, Pictures for the SD card](format.md#pictures-for-the-sd-card)).

- They show in their own colours, and with their transparency.
- The screen draws a picture's file the way it is stored, so on a screen that the app's `rotation` rotates, the file must be stored rotated to show upright. `nxwright sd-picture --rotation` writes such a `.xi` file. A PNG or a JPEG you saved upright shows rotated.
- The picture starts at the component's top left corner. As much of it shows as the component has room for.
- A picture whose file is missing shows nothing.

### What the file commands do

These folders are real folders on your computer. To keep your files safe, some commands do less than they would on a screen:

- A command cannot reach outside the card's folder. A path that would lead outside it is ignored, whether through `..`, a drive letter such as `C:`, or a link to another folder.
- A card's own folder is never deleted or renamed.
- `deldir` deletes an empty folder only. A screen deletes a full one too.
- `newfile` leaves a file that exists as it is.
- `refile` and `redir` onto a name that exists are ignored.

Other commands act on the folder like this:

- `newdir` makes a missing parent folder.
- `redir` renames a folder with its contents. Both its paths end with `/`.
- `twfile` replaces a file of the same name.

An ignored command sends one of these error codes ([Return codes](#return-codes)):

- 0x06 for:
  - a `newfile`, `delfile`, `refile`, `newdir`, `deldir`, or `twfile` on a path that is neither on a card nor in `ram/`;
  - a `newfile` into a folder that does not exist, or of a size below 0;
  - a `twfile` into a folder that does not exist, or of a size of 0 or below;
  - a `refile` of a file that does not exist, onto one that does, or into a missing folder;
  - every ignored `redir`;
  - an `rdfile` of a file that does not exist, or of bytes past its end;
- 0x1B for a `newfile` whose size is not a number;
- 0x1A for a `twfile` whose size is not a number;
- 0x01 for a `delfile` or `deldir` of what does not exist;
- 0x01 for the other commands above that are ignored to keep your files safe, such as a command whose path leaves the card's folder, or a `deldir` of a full folder. A screen deletes a full folder, and answers 0x01 too.

What is ignored goes to the log, and, in a test, to `"file errors"` ([testing.md](testing.md)).

### Files in `ram/`

A file whose path starts with `ram/`, such as `ram/0.jpg`, is kept in the screen's memory. The simulator keeps it in memory too, so it is lost when the simulation starts again.

Your project must set space aside for these files, with `memory_file_storage_size` in `app.toml` ([source-folder.md](source-folder.md#apptoml)). If it sets none, the screen does not create any file in `ram/`.

```toml
memory_file_storage_size = 4096
```

The files share that space. Each file uses 268 bytes on top of its own size, and 16 bytes of the space are never available. With 4096 bytes set aside, a single file can be 3812 bytes at most. `delfile` frees the space that the deleted file used.

The file commands follow these rules in `ram/`:

- `ram/` has no folders.
- `newfile` on a file that exists keeps the file if its size is the same. If the size differs, `newfile` replaces the file with one of the new size, all zero bytes. If the new size does not fit, `newfile` still deletes the old file, and does not create a new one.
- `twfile` needs room for the new file beside every file in `ram/`, including the one it will replace.
- `refile` renames a file within `ram/`.

The screen ignores each of the following in `ram/`, and sends 0x06. The log gives the reason:

- a `newfile` or a `twfile` of a file that does not fit, or of a file in a folder, such as `ram/logs/a.bin`;
- every `newdir`;
- a `refile` of a file that does not exist, onto a name that exists, or to a path outside `ram/`.

If a data record's file in `ram/` is missing, the data record shows "File Lost:" and the file's path. There are two ways for the file to be missing:

- The file did not fit in the space left, so the data record could not create it. The screen sends 0x06 when the page opens and when code sets the data record's `path`, and the log gives the reason. The data record's `qty` is 0, and its methods do not change anything, and do not send an error code.
- `mode` is 0, so the data record does not create the file. The screen does not send an error code.

These rules follow what the Nextion Editor's simulator does, and have not been checked on a real screen.

## Known differences

### Not modelled

The simulator does not model:

- the glide after a drag, on file browsers, selects, sliding texts (`ch`), and combo boxes (`ch`);
- a file browser's scroll bar staying for a second after a drag ends;
- the deep sleep that `lowpower` 1 gives a Discovery screen, from which a screen wakes more slowly;
- the screen's serial buffer filling up while the screen runs the instructions as they arrive, which depends on the screen's speed;
- the commands recorded but not run ([screen-code.md](screen-code.md#commands-recorded-but-not-run)).

### Different from the Nextion Editor's simulator

- Dividing by zero stops the app with an error. The Nextion Editor's simulator gives 0, and goes on.
- A `crcputh` whose text is not hexadecimal stops the app with an error. The Nextion Editor's simulator adds a byte, and goes on.
- A GPIO pin works as the vendor's instruction set describes ([GPIO](screen-code.md#gpio)). An input that nothing drives reads 1, like a pull-up input. The Nextion Editor's simulator reads 0 from every pin, inputs and outputs alike.
- `crcval` reads -1 at each start, until a `crcrest`. The Nextion Editor's simulator keeps it from one run to the next.
- The bytes that arrive after a transfer's last byte are instructions, as the vendor's instruction set describes ([Transparent data](#transparent-data)). The Nextion Editor's simulator drops the rest of a line typed in its instruction box after the transfer's last byte.
- `addt` or `wept` with a count of 0 sends FE FF FF FF and FD FF FF FF at once. The Nextion Editor's simulator sends FD FF FF FF only when more bytes arrive, and drops those bytes.
- `twfile` takes the file's bytes from the serial line, and writes the file, as the vendor's instruction set describes transparent data. This has not been checked against a screen. The Nextion Editor's simulator sends FE FF FF FF, then takes none of the bytes, and never writes the file.
- In address mode, an instruction typed in the Simulator section runs as if it carried the screen's address. The Nextion Editor's simulator drops an instruction typed as text, which has no address.
- `u[]` and `ucopy` read 0 past the last byte of the buffer of protocol reparse mode. The Nextion Editor's simulator reads leftover bytes, which depend on what it received before.
- A touch drawing with `thdra` draws its dot in `thc`, as the vendor's instruction set documents. The Nextion Editor's simulator draws it black.
- An opening effect takes `time` milliseconds. The Nextion Editor's simulator takes a little longer, a few percent, and now and then runs slower for a few seconds.
- A component that code moves during its opening effect slides on at once. The Nextion Editor's simulator first shows it at its new place for a moment.
- A press on a slider's track can give it a `val` one more, near the track's start, or one less, near its end, than the Nextion Editor's simulator gives.
- A sound plays for exactly its length. The Nextion Editor's simulator takes about 400 ms for each play of a 50 ms sound.
- An animation or a video plays at its set speed. The Nextion Editor's simulator gives each frame a little longer.
- An animation or a video whose `dis` is 0 stands still. The Nextion Editor's simulator stops answering.
- The screen's serial buffer has room for 1024 bytes, the size the vendor gives ([Holding instructions](#holding-instructions)). The Nextion Editor's simulator held more, and did not answer 0x24.
- `dims` and `bauds` go back to the vendor's defaults at each start. The screen, and the Nextion Editor's simulator, keep them.
- `appid` keeps what code stores in it, through `rest` and a start again, like a screen ([`appid`](screen-code.md#appid)). The Nextion Editor's simulator ignores what code stores in it: it reads 0.
- The real-time clock starts at your computer's time when you launch a simulation. The Nextion Editor's simulator keeps a time that code set, from one run to the next.
- Some SD card commands do less, to keep your files safe ([What the file commands do](#what-the-file-commands-do)).
- A data record's `delete` with a count below 0 changes nothing. The Nextion Editor's simulator adds records instead, as many as the count says.

### Not compared yet

These behaviours have not been compared with the Nextion Editor's simulator, and a screen may behave differently:

- When `thdra` is 1, a touch draws lines while it moves.
- Everything about [dragging components](#dragging-components).
- How a drag scrolls a sliding text, a combo box's list, or a data record.
- A video or a sound sends the error code 0x06 when its file is missing from a card that has no folder.
- A select or a sliding text takes a drag before a touch capture's Touch Release event runs, the same way that a combo box, a file browser, and a data record act on a tap.

For what else has not been compared, see the comments in `nxwright/testing/simulation.py` and `nxwright/drawing/page_drawing.py`.
