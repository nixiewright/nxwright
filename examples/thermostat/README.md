# Thermostat demo

A thermostat screen for an 800 by 480 Nextion Intelligent screen, written with nxwright: its pages are text files, its code is in nxlang, and its tests run on a PC. Open `thermostat.HMI` in the Nextion Editor and run it in the simulator; no screen is needed.

The room is simulated, sixty times faster than real time: each second, it loses or gains a minute's worth of heat, and the heating or cooling makes up for it. The outdoors suits the mode: a 30 degree day while cooling, an 8 degree day otherwise. The clock and the schedule keep real time.

- **Home:** the room, the target with buttons to lower and raise it, the mode (off, heat, or cool), and whether the target follows the schedule.
- **Schedule:** four periods of the day, Wake, Away, Home, and Sleep. Touch one to change its start, by quarter hours, and its target, by half degrees.
- **Day:** a chart of a day under the schedule, simulated from midnight in the current mode: the target, and the room it gives.
- **Settings:** Celsius or Fahrenheit, the screen's brightness, and the clock.

## What to look at

| Path | What it shows |
| --- | --- |
| `app/program.nx` | The state every page shares, as `int` variables, and the constants file it includes. |
| `app/pages/lib/` | The shared code. `text.nx` turns temperatures and times into text, in Celsius or Fahrenheit; `room.nx` simulates the room; `schedule.nx` reads and changes the schedule. Each page gets only the functions it calls. |
| `app/pages/lib/frame.nx` | The navigation bar's events, written once. Every page includes the file and has buttons of the same names. |
| `app/pages/home.nx` | A page in nxlang: events, functions, `switch`, and pictures named with `@pic(...)`. |
| `app/pages/day.nx` | Loops, page constants, and a waveform drawn point by point. |
| `app/pages/home.page.toml` | The page's components, as text. |
| `tests/` | Tests of the shared functions and of every page, run on a PC. |

## Building

Make changes in the source folder, `app/`, then build `thermostat.HMI`. In the `nxwright` folder, run:

```
python run.py build examples/thermostat/app examples/thermostat/thermostat.HMI --overwrite
```

A test checks that `thermostat.HMI` is what `app/` builds, so build again after each change.

If you changed `thermostat.HMI` in the Nextion Editor instead, save it, then bring the change back into the source folder:

```
python run.py extract examples/thermostat/thermostat.HMI examples/thermostat/app
```

## Testing

```
python run.py test examples/thermostat/tests
```

The tests run the pages' code on your PC ([Testing your app](../../docs/testing.md)), and check that `thermostat.HMI` and `app/` describe the same screen.

## Pictures

Each page has two full-screen pictures: its background, and the same with every button pressed. Text and buttons show the part of the background behind them ("crop image" in the Nextion Editor), and a button shows the pressed picture while it is touched. The selected mode, unit, and schedule switch show the pressed picture too, by code, while they are on, and the brightness slider shows it up to its knob. All the pictures are opaque, drawn on the colour they sit on.

## Fonts

The fonts were made with the Nextion Editor's font generator from Noto Sans, by the Noto Project Authors, under the SIL Open Font License 1.1 (`app/fonts/OFL.txt`). They carry plain names, `Sans16` to `Sans100`, after their size in pixels.
