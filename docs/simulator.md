# Simulating your app

The simulator runs your whole app on your computer in VS Code, which draws the screen in a panel. You can press its components, and watch its timers run and its pages change. The simulator can also talk to a real serial port, and use folders of your computer as its SD cards. You can set breakpoints and step through your code while it runs, forward and back.

The simulator behaves like the Nextion Editor's simulator. The few exceptions are listed under [Known differences](#known-differences).

To see how it runs each command, read [How nxwright runs Nextion code](screen-code.md).

## Starting a simulation

In nxwright's side bar, the Simulator section has two buttons:

- **Simulate project** starts the app from `program.nx`, like a screen being switched on. The code of `program.nx` runs, then the page it opens.
- **Simulate page** starts the app on the page shown, without running `program.nx`.

The commands "nxwright: Simulate the app" and "nxwright: Simulate the app from the page shown" do the same. Above a page's preview, or its page file, the **Simulate this page** button starts the app on that page, as Simulate page does.

An AI agent can also run your app through `nxwright mcp`, on its own or in this simulator ([Letting an agent drive your app](mcp.md)).

To keep a setup, such as the page to start on, a serial port, or SD card folders, save it as a launch configuration of type `nxwright`. The Simulator section shows a button for each one. The extension's README lists the parameters ([A simulation's launch configuration](../editors/vscode/README.md#a-simulations-launch-configuration)). When a configuration leaves a parameter out, the extension's settings provide it ([Settings](../editors/vscode/README.md#settings)).

The Debug Console lists each page compiled, with the full path of each of its `.nx` files: those it includes, and its own. Then it lists `program.nx`'s files, when its code is about to run. Each start lists them again, both when you start again and when the app's code runs `rest`.

Starting again reads your files anew. If they no longer build, the debugger stops on the error, which gives the file and the line, and the app keeps running as it was. Continue, fix the file, then start again.

### Starting on a page

A launch configuration's `page` starts the app on that page. Its `values` are the values to start from, as if they were in the page file. So whatever starts as the page opens starts from them, such as a file browser's listing.

```json
"page": "settings",
"values": {"step.val": 5, "page0.t0.txt": "Hello"}
```

- A value may give the page's own component with the page's name, as the page's code may. Started on `keybdA`, `keybdA.loadcmpid.val` is its `loadcmpid.val`.
- A value giving another page's component, as `page0.t0.txt`, is that page's. That component's scope must be global.
- To start on a keyboard page, give the component that opens it with `loadpageid.val` and `loadcmpid.val`. Without them, the simulator adds a page of its own that opens the keyboard, and shows the text the keyboard returns.

### The EEPROM

Without a file, the EEPROM starts empty at each simulation. A launch configuration's `eeprom` gives a file that keeps it between simulations.

- The simulation starts from the file.
- Each write the app makes, by `wepo` from code or typed, reaches the file at once. So the next simulation starts from what the app wrote.
- A file that does not exist will be made, with an empty EEPROM.
- A file longer than the EEPROM's 1024 bytes stops the launch, since writing it back would cut it.
- When a write fails, for example because another program has the file open, the log shows the error. The next write puts the whole EEPROM in the file again.
- The Nextion Editor's simulator keeps its own EEPROM in `eeprom.bin`. Give that file to share the EEPROM with it, one run after the other.

To start each simulation from the same EEPROM contents, copy a saved file over the EEPROM file before each launch. VS Code's `preLaunchTask` runs a task from `tasks.json` first. In `.vscode/tasks.json`:

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

The task uses Python so that it works on any computer. A `cp` or `Copy-Item` command works just as well.

Then, in the launch configuration:

```json
"eeprom": "${workspaceFolder}/eeprom.bin",
"preLaunchTask": "Reset the EEPROM"
```

### Chinese input

Chinese input (`pa_q` and `pa_txt`) needs the screen's pinyin table. A launch configuration's `pinyinTable` gives it, as either of these:

- `input.bin`, in the Nextion Editor's installation folder.
- Any TFT file, such as one you built from your project. Every TFT file contains a copy of the table. Use one on a computer without the Nextion Editor.

- Without it, the simulation uses the installed Nextion Editor's table, if it finds one.
- Without that either, the log says once that Chinese input will not show any candidates.
- A file without a pinyin table in it stops the launch.

## The panel

The panel draws the page that is showing, the same way the page preview draws it. It also shows anything your code drew with drawing commands, such as `fill`, `line`, or `xstr`. The panel gets darker when your code lowers `dim`.

- An event that runs long, such as one drawing a chart, is shown as it goes, every tenth of a second. When a drawing takes longer than that, it is shown less often, so that the event can go on.
- A stream of work, such as instructions arriving faster than they run, is shown the same way. The last state is drawn once nothing is waiting.
- The zoom bar above it shows the screen larger or smaller, as the page preview's does. The screen is sharp from 100% up, and smoothed below. Ctrl with the mouse wheel zooms about the pointer.
- A press lands on the screen's pixel under the pointer, whatever the zoom.

Closing the panel does not stop the simulation. To open the panel again, use **Show the screen** in the Simulator section, or the command "nxwright: Show the Simulator". The panel opens on the screen as it is now.

## Touches

Press the mouse on the panel to touch the screen.

- The press lands on the topmost component under the pointer that shows, or on the page. Its Touch Press event runs.
- Letting go runs the Touch Release event of the component pressed.
- A hidden component lets the touch through to what lies under it.
- A component whose touches `tsw` turned off takes the touch, but none of its events run.
- After `tsw 255,0`, the page itself does not take touches either: a press on it does not run any of its events.

### Touch captures

A page's touch capture runs its own Touch Press and Touch Release events before the component's.

- The touch capture's `val` is set to the ID of the component touched, or 0 for the page.
- When a page has several touch captures, only the last one runs.
- `tsw` does not turn a touch capture off.
- A `click` does not run the touch capture's events. It runs only the clicked component's event.
- When its event changes page, the component's own event does not run.
- A file browser, select, sliding text, combo box, or data record takes the touch before the Touch Release event runs. So the event reads what the touch chose, such as a combo box's new `val`.

### Keyboards

A component bound to a keyboard by its `key`, 1 to 4, opens that keyboard's page when it is released ([commands.md](commands.md#keyboard)). This happens after its Touch Release event, for a press or a `click`.

- The keyboard's `loadpageid` is set to the caller's page number.
- The keyboard's `loadcmpid` is set to the component's ID.

A keyboard is a page of your project, and you can change it like any other page. Keep what the screen relies on: its `system_page` marker, and its two variables of global scope, `loadpageid` and `loadcmpid`.

What happens on OK or Cancel is up to the keyboard's own code. nxwright's keyboards, and the Nextion Editor's own, do this:

- OK writes the typed text back to the component: its `txt`, or its `val` for a number or an xfloat. Then the keyboard opens the caller's page again, with `page loadpageid.val`.
- Cancel opens the caller's page again without writing anything.

The keyboard reaches the component through `p[loadpageid.val].b[loadcmpid.val]`. From another page, that only reaches components of global scope. That is why a component bound to a keyboard must be of global scope. Opening the caller's page again also runs its `load` event again.

### Touch coordinates

- A press puts its pixel in `tch0` and `tch1`, and in `tch2` and `tch3`, before its events run. A press sets them while the screen sleeps too.
- Moving the press moves them.
- A release sets `tch0` and `tch1` to 0 before its events run. `tch2` and `tch3` keep the last place.
- A test's press gives a component, not a place, so it changes none of them.

When `sendxy` is 1, each press and release sends its place on the serial line, before its events run:

- 0x67;
- then x and y, in two bytes each, high byte first;
- then 1 for a press, or 0 for a release.

While the screen sleeps, each sends 0x68 instead, whatever the value of `sendxy`.

### Sending the component's ID

The Nextion Editor's "Send Component ID" ticks are kept in `sendkey`:

- `sendkey` 1, the Touch Release event's tick: as the component is released, it sends 0x65, its page's ID, its own ID, and 0.
- `sendkey` 2, the Touch Press event's tick: as the component is pressed, it sends 0x65, its page's ID, its own ID, and 1.
- These bytes are sent before the component's events run. When `sendxy` is 1, they come after the touch's coordinates (0x67).
- The page has the same ticks. When it is touched, it sends the same bytes, with 0 as its own ID.
- A component whose touches are off sends nothing. Neither does a `click`.
- When the press changes page, the release sends nothing.

### Drawing with a touch

While `thdra` is 1, a touch draws in the colour `thc`, as drawing commands paint.

- The press draws a dot of 2 by 2 pixels, over the component drawn pressed.
- Each move of the touch draws a line from the last place to the next.
- The touch is handled as usual besides.
- On a sleeping screen, which a touch only wakes, it draws nothing.

### Dragging components

A press on a component whose `drag` is 1, which then moves, carries the component with it.

- The component's `x` and `y` follow the touch.
- The component's whole rectangle stays on the screen.
- The component's press and release events run as for any press.
- A slider, and the other types that follow a press, keep following it instead of being dragged. A page and a hotspot are never dragged.
- `movex` and `movey` are left alone.

## Time and timers

The simulation's time follows the wall clock while it runs.

- Each timer of the page shown that is on (`en` 1) runs its event every `tim` milliseconds.
- A `move` moves its component on the same clock.
- Timers run one at a time. Touches and the serial line take their turns between them.
- When the app's events take longer than its timers' periods, a late timer runs once, straight away. The timer does not run once for each period it missed. The simulation's time then falls behind the wall clock. This can happen while the debugger records every step.
- A `delay` holds the simulation for as long as it lasts. Touches wait for it.
- The real-time clock, `rtc0` to `rtc6`, starts at your computer's time of day. They are the year, month, day, hour, minute, second, and day of the week, from 0 for Sunday. The clock moves with the simulation's time.
- Code setting one of `rtc0` to `rtc5` sets that part of the time. An impossible date or time, such as month 13, is ignored.
- Starting again keeps the clock running, as a screen's clock runs on while the screen is off.

### Sleep

- `sleep=1` puts the screen to sleep. The panel goes dark, and the timers stop.
- `thsp` puts it to sleep after that many seconds without a touch. `ussp` puts it to sleep after that many seconds without serial data.
- While the screen sleeps, events do not run. When `thup` is 1, the touch wakes the screen as the touch ends.
- Instructions from the serial line run while it sleeps. When `usup` is 1, an instruction wakes the screen first, then runs. A `click` among them does not run any event.
- Code that puts the screen to sleep ends its event. The rest of the event does not run, so code after the sleep in that event cannot wake the screen again. The Nextion Editor's simulator does the same in a press's event, a timer's event, and a page's `load` and `unload` events.
  - In a page's `unload` event, the page change stops at that point. The old page stays shown.
  - In a `load` event, the new page shows, but its `loadend` event does not run.
- When a press's event puts the screen to sleep, its release counts as a touch on a sleeping screen. The release sends 0x68, and wakes the screen when `thup` is 1. The component's Touch Release event does not run.
- Falling asleep by `thsp` or `ussp` sends 0x86 on the serial line. Waking by a touch sends 0x87. Waking by the serial line sends nothing. `sleep` set by code sends neither.
- However it wakes, the screen then shows the page that `wup` gives, as a `page` command would. When `wup` is 255, the screen stays on the page it was on.
- The old page's `unload` event does not run then, whether a touch or the serial line woke it.
- A `wup` that does not give a page leaves the page shown as it is.
- Waking by a touch starts the `ussp` count again.

## Changing page

A `page` command gives the page by its name, its number, or a value that contains its number: `page returnPage.val`, or `page appid&0x000000FF`, computed from left to right. A number that no page has answers 0x03, and the page stays.

- The command runs the old page's `unload` event, then the new page's `load` and `loadend` events, inside the event that ran the command.
- The rest of that event does not run. Neither do the events whose clicks or calls led to it.
- A `return` in a page's `load` event keeps its `loadend` event from running. This is also true when the simulation starts.
- The panel keeps showing the old page until the new one's `load` event ends. A real screen also waits until then to draw the new page.
- A page without a background, such as a dialog, is drawn over what the screen showed when it was entered: what the page before left. The first page after the screen starts is drawn over black. A page has no background when its `sta` is 0, or when it is 2 with no picture, or with a picture the folder does not have.
- Entering a page starts its components from its `.page.toml` file, shown and taking touches.
- Components of global scope (`vscope` 1) keep their values instead. They also keep whether they show (`vis`) and take touches (`tsw`).
- A `vis 255` or `tsw 255` also applies to each component of global scope on the page shown, and those components keep it. The next page's other components start from their page file.
- Only the timers of the page shown run.

## Drawing commands

Drawing commands paint over the page, in order.

- A component is drawn again over them when the code changes it, even to the value it had, or shows it with `vis`.
- So is a button that is pressed or released, a slider whose knob a press moves, and a component given to `ref`.
- A component drawn again shows on the page's own background. What drawing commands painted under it goes. On a page without a background, it shows the screen as the page found it there.
- The components it overlaps are drawn again with it, and those they overlap in turn, and so on, in ID order.
- When your code moves or resizes a component, the page's background comes back where it was. The simulator draws the components in that area again, and those they overlap in turn. A `move` does the same at each of its steps, about every 16 ms, so the background comes back all along its path.
- Between `ref_stop` and `ref_star`, a component your code changes keeps showing as it was until `ref_star`. So does a component that `vis` hides. A component that `vis` shows appears at once.
- When your code changes page between `ref_stop` and `ref_star`, the page before keeps showing. Your code runs on the new page meanwhile, and a touch goes to the new page's components. `ref_star` shows the new page, with what your code painted on it, and starts its [opening effects](#opening-effects).
- A new page clears what they painted.

### Opacity

The panel draws each component with opacity `aph`, from 0 (invisible) to 127 (opaque). Each part is blended over what lies under it, in turn: a text's background, then its words.

## Components that act on their own

### Buttons

- A button's `val` is 1 while it is pressed, and 0 once it is released. `val` is set before the press's and the release's events run.
- A button of global scope whose press changes page does not get a release, and its `val` goes back to 0.
- A `click` sets `val` as a press and a release do: `click b0,1` to 1, and `click b0,0` to 0, before the event runs.

### Checkboxes, radios, dual-state buttons, and switches

- They flip their `val` when pressed, from 0 to 1 and back.
- This happens before the press's events run, a touch capture's included, so the events read the new value.
- They are drawn again in their new state.
- A radio is not grouped with the page's other radios. A press turns it off when it is on.

### Sliders

- Pressing a slider puts its knob's middle under the pointer, and dragging moves it along.
- The knob stays where the pointer left it, even when `ref` draws the slider again. When your code sets `val`, even to the value it has, the knob moves back to the place of that value.
- Each move that changes its value runs its Touch Move event (`slide`).

### Scrolling texts

A scrolling text that is on moves its text `dis` pixels every `tim` milliseconds.

- The text starts just outside its component, comes in at its first step, and comes round again once it has gone.
- Code reads where the text is in `vvs0`, or in `vvs1` when it moves up or down.
- Code reads the text's width and height in pixels in `vvs2` and `vvs3`, as it is drawn: with `spax` between characters, `spay` between lines, and the lines `isbr` wraps. The text is measured as its page opens, and at each step before it moves.
- Code setting `vvs0` or `vvs1` moves the text to that place, and the text moves on from that place. A new `txt` or `font` keeps it where it is. `en` 0 stops it where it is.
- A new `txt` or `font` shows at once. Until the next step measures it, `vvs2` and `vvs3` keep the old size, and `xcen` or `ycen` aligns the new text by that old size. A stopped text keeps the old size.
- A new `dir` the other way along the same line, as 1 after 0, turns it round where it is.
- A new `dir` that switches between across and up or down takes effect at the text's next step. That step puts the text just outside its component, where it would come back in, and moves it no further. Until then, the text shows, and code reads its place, as before. A stopped text does not turn.
- While the text moves, code setting `tim`, or setting `en` to 1, does not delay it, even when the value is the same. The text's next step comes `tim` after its last one, or at once if that time has passed. A timer is different: setting its `tim` or `en` starts its count again.
- After `en` 0, code setting `en` to 1 counts `tim` from then.

### Sliding texts

- Their lines are laid out as a text's, from the top inside the border. When `isbr` is 1, the lines wrap at the component's width.
- `maxval_y` is how far a touch scrolls them: how much taller the lines are than the inside of the border. The simulator works out `maxval_y` as the page opens, and again when code sets `txt` or `font`.
- Code setting `val_y` scrolls them up to 32 pixels further than that, and up to 32 pixels above their top. The last line never scrolls above the top.
- What code sets in `val_y` reads back as set until its event ends, or until a `doevents`. The screen then settles it within these limits.
- A drag scrolls them as far as the touch moves, up to `maxval_y`. They stay where the drag leaves them.
- `left` sets when the scroll bar's thumb shows: never, while a touch scrolls them, or always. Pressed without scrolling, they are not drawn again until the touch ends.

### Combo boxes

- A tap on the box opens its list, as the tap ends. The next tap closes it.
- While the list is open, it belongs to its box. A press anywhere on it runs the box's Touch Press event: on an item, a scroll mark, or a gap between items.
- The release chooses the item under it, sets `val` and `txt`, and closes the list. Then the box's Touch Release event runs.
- Under the list, a component that comes before the box in ID order does not take the press.
- A component that comes after it is drawn over the list. That component takes the press as usual, and the list stays open. The list also stays open when the page is pressed elsewhere.
- Code setting `down` opens or closes the list.
- Code setting `val` sets `txt` to its item, and moves an open list to show it. A `val` past the last item is ignored, and the item chosen before stays chosen.
- A new `path` changes neither `val` nor `txt`.
- A drag on the open list scrolls it by a whole item each time the touch moves an item's length. The drag does not choose an item. The list stays open.

### File browsers

- A file browser lists its folder, `dir`, when its page opens, and whenever code sets `dir`.
- `up()` goes to the folder above, and lists it. `up()` goes no higher than the card's own folder.
- The file browser lists the folders first, unless `psta` is 0. Then it lists the files its `filter` lets through. Each group is in alphabetical order, ignoring capitals.
- `qty` counts the entries.
- Each listing clears the selection (`val` -1, `txt` empty), scrolls to the top (`val_y` 0), and sets how far the entries scroll (`maxval_y`). When code sets `dir` or runs `up()`, `maxval_y` takes its new value only once that event ends.
- Code setting `val` selects an entry. `txt` gives its name. A folder's name ends with "/".
- Code setting `val_y` scrolls the entries, up to 32 pixels past `maxval_y`, and up to 32 pixels above their top. In the event that listed the folder, it scrolls them no further than `maxval_y`.
- What code sets in `val_y` reads back as set until its event ends, or until a `doevents`. The screen then settles it within these limits.
- A touch takes effect as it ends, before the `up` event runs. A tap on a file selects it. A tap on a folder opens it.
- A tap on an empty place, past the last entry, sets `val` to the number of entries, and `txt` to nothing.
- A tap between two places, or right of the last column, clears the selection: `val` goes back to -1. A tap left of the first column changes nothing.
- A tap on the border above the entries counts as a tap just inside it, scrolled or not.
- A drag scrolls the entries, and does not select any.

### Selects

- A select's `path` contains its lines, one at each line break.
- Code setting `val` picks a line. `txt` gives its text. A `val` past the last line, or below 0, changes nothing: `val` and `txt` keep theirs.
- Only code setting `val` sets `txt`. Opening the page, or changing `path`, does not.
- A drag turns the lines. As the touch ends, the line left in the middle is picked, before the `up` event runs.
- A tap does nothing.

### Data records

- As its page opens, a data record reads its data file. If the file doesn't exist and `mode` is 1, the data record creates it.
- The data record shows the records in its table. When `order` is 0, the newest record is at the top.
- The data record's methods change the file, and the table follows ([Data records](screen-code.md#data-records)).
- Code setting `val_y` scrolls the records, up to 32 pixels past `maxval_y`, and up to 32 pixels above their top, which leaves an empty band under the titles.
- Code setting `val_x` scrolls the columns, from 0 to `maxval_x`. `maxval_x` counts the line at the right of the last column.
- What code sets in `val_y` or `val_x` reads back as set until its event ends, or until a `doevents`. The screen then settles it within these limits.
- Code changing its `path`, `format`, `hig`, `gdw`, or `gdh` works out `qty`, `txt`, `maxval_y`, and `maxval_x` again. A new `dir` leaves them as they were, until one of those changes.
- When `dis` is 1, a tap chooses the record under it, setting `val` and `txt`. This happens after the Touch Press event and before the Touch Release event.
- A tap on the titles' row, or below the last record, chooses nothing.
- A drag scrolls the records, and does not choose any.

Only one data record can use a data file at a time. When two data records give the same `path`, the first one to open the file keeps it:

- The first data record keeps the file while other pages show, and opens it again when its page opens again. That record lets the file go when code changes its `path`.
- The second data record cannot open the file. The second record shows "Cannot open file:" and the path, in white on black, in its own font. Its `qty` is 0. As its page opens, it sends the error code 0x06 twice ([Return codes](#return-codes)).
- The second record's methods change nothing while the first record keeps the file. Once the file is free, its next method opens it.
- Code setting a data record's `path` to a file another one keeps answers 0x06.

Data records keep at most 8 files at once, across pages. A record that finds 8 kept by others cannot open its own, as if another record kept it. A record that keeps a file can still change its `path`, as it lets the old file go first.

A data record whose `path` is empty does not keep a file, so it does not shut out any other record. Such a record shows "File Lost:", in white on black, in its own font, but does not send an error code. The page preview shows it the same way.

A data record whose `init` is 1 does not open the file its page file gives:

- It shows its titles and no records, and its `qty` is 0. It does not create a missing file.
- It does not keep the file, so another data record can open it.
- Its methods change nothing, and send no error code.
- Once code sets its `path`, even to the same file, it works as when `init` is 0.

### Animations, videos, and sounds

They play from their page's opening.

- A run lasts the component's `stim`: the sum of an animation's frames' durations, a video's frames at its frame rate, or a sound's samples.
- The panel draws the frame that `tim` falls on, in the frame's own colours, not the screen's 16 bits.
- When a run ends, `playend` runs. When `loop` is 1, a new run starts at once. Otherwise the last frame stays, and `en` becomes 0. Setting `en` to 1 then starts a new run.
- Code setting `en` to 0 stops it, back at its start. 2 pauses it, and 1 plays it on.
- Setting `tim` moves the run to that time.
- Setting `vid` to another ID loads that one, at its start. It plays if the player was playing, and stays stopped or paused if not. Setting `vid` to the ID loaded changes nothing, playing or not.
- Setting `path` plays its file from its start, even the file playing.
- An animation's or a video's `dis` is its speed, in percent. The Nextion Editor gives its range as 10 to 1000, but code may set more or less, and it plays that fast. At 0 it stands still. A sound's `dis` does not change its speed.
- A video's `fps` always reads its file's frame rate.
- A sound writes to the log as it starts, pauses, stops, and ends.

A video's or a sound's `from` sets where its file comes from:

- 0, the default: from the project. `vid` gives the video or the sound, by its ID.
- 1: from an SD card. `path` gives the file, such as `sd0/1.wav`.

With `from` 1:

- When the card's folder lacks that file, nothing plays. The component sends the error code 0x06, an invalid file operation ([Return codes](#return-codes)). It sends it as its page opens, and when code sets its `path`.
- When a card has no folder, the simulator keeps the card in memory, as the file commands do. A file missing from that card answers 0x06 too.
- With an empty `path`, nothing plays, and the component does not send an error code.

Unlike a video or a sound, an animation cannot play a file from the SD card. It always plays from the project.

### Waveforms

A waveform draws the points that code adds with `add`, each channel in its colour, one point per column.

- When `dir` is 0, the default, a new point enters at the left and pushes the others right.
- When `dir` is 1, a new point enters at the right and pushes the others left. The first point stays at the left edge until the points fill the waveform.
- When `dir` is 2, the points move as they do for `dir` 1, but the last one is always at the right edge.
- A value of v is drawn v × `dis` / 100 pixels up from the bottom, cut toward zero.
- `cle` clears the points. So does a new page.

### Opening effects

As a page opens, its components whose `effect` is 1 to 8 slide in from wholly off the screen.

This happens on the Edge and Intelligent series only. The Basic, Enhanced, and Discovery series do not support `effect`, so their components are drawn in place at once. The Nextion Editor's simulator did the same on a Basic screen.

- They start once the page's `load` event ends, each sliding to where that event left it. The `loadend` event runs as they start.
- A page entered between `ref_stop` and `ref_star` starts them at `ref_star`, each sliding to where your code left it by then. Its `loadend` event still runs as its `load` event ends.
- Each comes from beyond the edge or corner its effect gives, in a straight line, at a steady speed, over `time` milliseconds.
- The components with the highest `first` slide in together. Then those of the next lower `first`, once those are in place.
- A component waiting its turn is not drawn.
- Meanwhile, code reads each component's own `x` and `y`, and touches land at that place too.
- Code hiding or showing a component puts it in its place at once.
- Code moving a component during its slide, in `loadend` or a timer's event, changes the `x` and `y` that code reads, but the component slides on. When the slide ends, the component stays where the slide took it, and its `x` and `y` go back to that place.
- A component sliding in over what drawing commands painted shows over it, and the page's background comes back along the path it slid.

## The serial line

The log shows what the screen receives and sends on its serial line. A launch configuration's `logReceived` and `logSent` say how: as text (`text`), in hexadecimal (`hex`), or `both`.

- By default, what the screen receives shows as text, and what it sends in hexadecimal.
- As text, the FF FF FF that ends an instruction or a reply is left out. A byte that is not a character shows as `\xNN`.

### Return codes

After an instruction, the screen can send a return code on the serial line, such as 0x01 for success or 0x06 for an invalid file operation. The system variable `bkcmd` decides which codes it sends:

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

A serial port of your computer can carry the screen's serial line, like the "User MCU input" mode of the Nextion Editor's simulator. Give it with a launch configuration's `serialPort`, or connect it from the Simulator section while the simulation runs.

```json
"serialPort": {"name": "COM4", "baud": 115200}
```

On Linux, a port is named as `/dev/ttyUSB0`.

- You set the port's rate with `baud`, in the launch configuration or in the Simulator section. Without it, the rate is 9600, the screen's rate at power-on.
- The line is 8 data bits, no parity, and 1 stop bit.
- Your app's code cannot change the port's rate. On a screen, setting the system variable `baud` or `bauds` changes the screen's rate. In the simulator, the port keeps the rate you set.
- What arrives is cut into instructions at each FF FF FF, and read in the project's encoding. Each one runs in turn, as a typed instruction does.
- When the screen starts again, for example with `rest`, it drops what it has received but not yet run.
- While the simulation is paused, they wait. They do not count against the screen's serial buffer ([Holding instructions](#holding-instructions)).
- Everything the screen sends goes out, in order, its return codes included.
- You can connect the simulator to a program on the same computer by using a virtual pair of ports. On Windows, com0com creates one. On Linux or macOS, `socat -d -d pty,raw,echo=0 pty,raw,echo=0` creates one, and prints the two ports' names.
- When a port cannot open, or is lost, the log shows the reason. The simulation keeps running without the port.
- The simulator sends in pieces of 64 bytes. The port has 20 ms to take each piece, plus the time its bytes take at the port's rate: about 87 ms at 9600, and 26 ms at 115200. When a piece is not taken in time, for example because nothing reads the other end, the simulator drops the rest of the write, and logs it. So a port nobody reads cannot freeze the simulation.

### Typing an instruction

While a simulation runs, the Simulator section has buttons to pause, resume, and start again, to show the screen, and to open the log. The section also shows the serial port and its rate, with a button to connect or disconnect it.

The section's field sends the screen an instruction, as if it came from the serial line. The screen runs it, and the log shows what it sends back:

- a reply, such as `get`'s;
- the instruction's return code, if `bkcmd` is set to send it ([Return codes](#return-codes)).

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
| 0x1B | An operator on a text other than `+` and `-=`. |
| 0x1C | A picture or font ID the project lacks. A `txt` given a number, or a `val` a text. An assignment to an attribute that code cannot change, such as `t0.w=10` ([build-rules.md](build-rules.md#attributes-code-cannot-change)). The attribute keeps its value. `addr` given a number other than 0, or 256 to 2815. |
| 0x1D | An EEPROM access that does not fit in it. `wept` at a place before 0. |
| 0x1E | A command given another number of parameters, or written alone where it takes some. |
| 0x20 | An escape the screen does not read. |
| 0x24 | The screen's serial buffer overflowed ([Holding instructions](#holding-instructions)). |

A name the screen does not know, 0x1A, includes:

- an attribute its component lacks, by its choices or by the screen's series ([build-rules.md](build-rules.md#attributes-a-component-lacks)), such as a variable's `val` while the variable stores text, or `movex` on a Basic screen. A simulation's values leave these out.
- an attribute the screen does not support ([Attributes the screen does not support](screen-code.md#attributes-the-screen-does-not-support)).
- `usize` or `u[]` read while `recmod` is 0 ([Protocol reparse mode](#protocol-reparse-mode)).

- A failure in an event's code answers at once, and the event goes on.
- An ignored SD card command answers its own code ([The SD cards](#the-sd-cards)).
- A `covx` to hexadecimal of an odd length answers 0x1B ([The text commands](screen-code.md#the-text-commands)).

### Holding instructions

`com_stop` holds the instructions that arrive on the serial line, whether it is sent or run by code.

- Held instructions are logged. They neither run nor answer.
- `com_star` runs them, in order.
- On the serial line, `com_star` works while instructions are held. Run by code, it runs them once its event ends.
- Neither command sends a return code, whatever `bkcmd` is set to.
- The screen's serial buffer has room for 1024 bytes. When the held instructions would pass that, the screen drops them, keeps the instruction arriving, and answers 0x24.
- `com_star` with nothing held changes nothing. Neither does a second `com_stop`.
- Touches, timers, and page changes go on meanwhile.
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
- `addr` takes 0, or 256 to 2815, and another number answers 0x1C. Setting it to 0, with the address, ends the mode.
- An instruction you type in the Simulator section runs as if it carried the screen's address.
- `addr` goes back to 0 at each start, as in the Nextion Editor's simulator. A real screen keeps its address when it is turned off.

## GPIO pins

While the app runs, the Simulator section lists the screen's 8 GPIO pins, io0 to io7. For each pin, it shows what code set the pin up as, and its level. Code reads and writes the pins as `pio0` to `pio7`.

- Click an input's level to give it the other one, as a button or a switch wired to the pin would. The app reads the new level.
- A pin bound to a component with `cfgpio` shows the component's name. Setting the pin to 0 presses the component, and setting it back to 1 releases it.
- An output shows what the code last wrote to it.
- A screen of the Basic series has no GPIO pins, and the section does not list any.

Every input reads 1 until you change it, as a pull-up input that nothing drives does. To start the app with other levels, give them in the launch configuration's `gpioInputs`:

```json
"gpioInputs": {"pio2": 0}
```

The levels stay when the app starts again, because they belong to what is wired to the pins. For how code reads and writes the pins, see [GPIO](screen-code.md#gpio).

## The log

The log is in the Debug Console. The log lists, with the simulation's time, what reached outside the screen:

- what it sent on the serial line;
- each EEPROM and GPIO access, with its value;
- the SD card's commands;
- the commands it does not otherwise run.

## The SD cards

The screen's SD cards can be folders of your computer. A launch configuration's `sdCard0` gives one for `sd0/`, and `sdCard1` one for `sd1/`, each by its full path. A drive's root is not taken. The Nextion Editor's simulator keeps its own cards in `sdcard0` and `sdcard1`, in its settings folder.

- `sd0/presets/a.cfg` is then the file `presets/a.cfg` in the folder.
- The app's file commands act on the folder's files, for real. What they change stays after the simulation, whatever stepping back or starting again does.
- To start each simulation with the same files, replace the folder with a saved copy before each launch, with a `preLaunchTask`. See the [The EEPROM](#the-eeprom) section for an example of how to do this for a single file.
- A card given no folder, a `ram/` file, and a path on no card are kept in memory, as in a test.

### External pictures

External pictures show their images from the card: a PNG, a JPEG, or PictureBox's `.xi` file ([format.md, Pictures for the SD card](format.md#pictures-for-the-sd-card)).

- They show in their own colours, and with their transparency.
- On a turned screen, a file made for it shows upright. The screen draws a file as it is stored, so a file for a screen turned by the app's `rotation` is stored turned, and the simulator turns it back. A PNG or a JPEG you saved upright shows turned. `nxwright sd-picture --rotation` writes a `.xi` file stored turned for you.
- The picture starts at the component's top left corner. As much of it shows as the component has room for.
- A picture whose file is missing shows nothing.

### What the file commands do

These folders are real folders on your computer. To keep your files safe, some commands do less than they would on a screen:

- A command cannot reach outside the card's folder. A path that would lead outside it is ignored, whether through `..`, a drive letter such as `C:`, or a link to another folder.
- A card's own folder is never deleted or renamed.
- `deldir` deletes an empty folder only. A screen deletes a full one too.
- `newfile` leaves a file that exists as it is.
- `refile` and `redir` onto a name that exists are ignored.

Beyond these:

- `newdir` makes a missing parent folder.
- `redir` renames a folder with its contents. Both its paths end with `/`.
- `twfile` replaces a file of the same name.

An ignored command sends one of these error codes ([Return codes](#return-codes)):

- 0x06 for a `newfile` into a folder that does not exist, or of a size below 0;
- 0x06 for a `refile` of a file that does not exist, onto one that does, or into a missing folder;
- 0x06 for every ignored `redir`;
- 0x06 for an `rdfile` of a file that does not exist, or of bytes past its end;
- 0x06 for a `twfile` to a path on neither `sd0/` nor `sd1/`, as in `ram/`, of a size of 0 or below, or into a folder that does not exist;
- 0x1A for a `twfile` whose size is not a number;
- 0x01 for a `delfile` or `deldir` of what does not exist;
- 0x01 for the other commands above that are ignored to keep your files safe, such as a path that leaves the card's folder, or a `deldir` of a full folder. A screen deletes a full folder, and answers 0x01 too.

What is ignored goes to the log, and to `"file errors"`.

## Starting again

Starting again is a power cycle, as `rest` is. The EEPROM keeps what the app wrote. The log is not cleared, and says that the app started again.

## Debugging

You can debug the app while it runs.

- Breakpoints stop it. Stepping, the Call Stack view, and the Variables view work the same way they do for a test ([Debugging a test](testing.md#debugging-a-test)).
- Moving back goes through what it recorded: its last 900,000 to a million steps. The oldest tenth is dropped at a time.
- Moving forward past the present lets it go on.
- An error in the code, such as dividing by zero, stops it as an exception does. Continuing goes on from that line.

## Known differences

### Not modelled

- the glide after a drag, on file browsers, selects, sliding texts (`ch`), and combo boxes (`ch`);
- a file browser's scroll bar staying for a second after a drag ends;
- the deep sleep that `lowpower` 1 gives a Discovery screen, from which a screen wakes more slowly;
- the screen's serial buffer filling up while the screen runs the instructions as they arrive, which depends on the screen's speed;
- the commands recorded but not run ([screen-code.md](screen-code.md#commands-recorded-but-not-run)).

### Different from the Nextion Editor's simulator

- Dividing by zero stops the app with an error. The Nextion Editor's simulator gives 0, and goes on.
- A `crcputh` whose text is not hexadecimal stops the app with an error. The Nextion Editor's simulator adds a byte, and goes on.
- A GPIO pin works as the vendor's instruction set describes ([GPIO](screen-code.md#gpio)). An input that nothing drives reads 1, as a pull-up input does. The Nextion Editor's simulator reads 0 from every pin, inputs and outputs alike.
- `crcval` reads -1 at each start, until a `crcrest`. The Nextion Editor's simulator keeps it from one run to the next.
- The bytes that arrive after a transfer's last byte are instructions, as the vendor's instruction set describes ([Transparent data](#transparent-data)). The Nextion Editor's simulator drops the rest of a line typed in its instruction box after the transfer's last byte.
- `addt` or `wept` with a count of 0 sends FE FF FF FF and FD FF FF FF at once. The Nextion Editor's simulator sends FD FF FF FF only when more bytes arrive, and drops those bytes.
- `twfile` takes the file's bytes from the serial line, and writes the file, as the vendor's instruction set describes transparent data. This is not verified. The Nextion Editor's simulator sends FE FF FF FF, then takes none of the bytes, and never writes the file.
- In address mode, an instruction typed in the Simulator section runs as if it carried the screen's address. The Nextion Editor's simulator drops an instruction typed as text, which has no address.
- `u[]` and `ucopy` read 0 past the last byte of the buffer of protocol reparse mode. The Nextion Editor's simulator reads leftover bytes, which depend on what it received before.
- A touch drawing with `thdra` draws its dot in `thc`, as the vendor's instruction set says. The Nextion Editor's simulator draws it black.
- An opening effect takes `time` milliseconds. The Nextion Editor's simulator takes a little longer, a few percent, and now and then runs slower for a few seconds.
- A component that code moves during its opening effect slides on at once. The Nextion Editor's simulator first shows it at its new place for a moment.
- A press on a slider's track can give it a `val` one more, near the track's start, or one less, near its end, than the Nextion Editor's simulator gives.
- A sound plays in its own time. The Nextion Editor's simulator takes about 400 ms for each play of a 50 ms sound.
- An animation or a video plays in its own time too. The Nextion Editor's simulator gives each frame a little longer.
- An animation or a video whose `dis` is 0 stands still. The Nextion Editor's simulator stops answering.
- The screen's serial buffer has room for 1024 bytes, as the vendor gives it ([Holding instructions](#holding-instructions)). The Nextion Editor's simulator held more, and did not answer 0x24.
- `dims` and `bauds` go back to the vendor's defaults at each start. The screen, and the Nextion Editor's simulator, keep them.
- `appid` keeps what code stores in it, through `rest` and a start again, as a screen does ([`appid`](screen-code.md#appid)). The Nextion Editor's simulator ignores what code stores in it: it reads 0.
- The real-time clock starts at your computer's time at each start. The Nextion Editor's simulator keeps a time that code set, from one start to the next.
- Some SD card commands do less, to keep your files safe ([What the file commands do](#what-the-file-commands-do)).
- A data record's `delete` with a count below 0 changes nothing. The Nextion Editor's simulator adds records instead, as many as the count says.

### Not compared yet

nxwright does these things without having compared them with the Nextion Editor's simulator. A screen may behave differently.

- When `thdra` is 1, a touch draws lines as it moves.
- Everything about [dragging components](#dragging-components).
- How a drag scrolls a sliding text, a combo box's list, or a data record.
- A video or a sound sends the error code 0x06 when its file is missing from a card that has no folder.
- A select or a sliding text takes a drag before a touch capture's Touch Release event runs, as a combo box, a file browser, and a data record take a tap.

Beyond these, the source code's comments list what else has not been compared, in `nxwright/testing/simulation.py` and `nxwright/drawing/page_drawing.py`.
