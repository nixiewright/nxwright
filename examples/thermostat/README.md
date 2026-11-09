# Thermostat demo

This demo shows what working with nxwright looks like, through a thermostat for an 800 by 480 Nextion Intelligent screen. To try it without a screen, open `thermostat.HMI` in the Nextion Editor and run it in the simulator.

The demo has five pages:

- **Home:** the room and target temperatures, the mode (off, heat, or cool), and whether the target follows the schedule.
- **Schedule:** four periods of the day, Wake, Away, Home, and Sleep, each with a start time and a target temperature you can change.
- **Day:** a chart of the target and room temperatures over a day that follows the schedule, simulated from midnight in the current mode.
- **Settings:** Celsius or Fahrenheit, the screen's brightness, and the clock.
- **About:** what the demo is made with, opened from the About card of the settings page.

The demo simulates the room sixty times faster than real time, but the clock and the schedule run at normal speed. The weather depends on the mode: a 30 degree day while cooling, and an 8 degree day otherwise.

## What to look at

| Path | What it shows |
| --- | --- |
| `app/program.nx` | The state every page shares, as `int` variables, and the constants file it includes. |
| `app/pages/lib/` | The shared code. `text.nx` turns temperatures and times into text, in Celsius or Fahrenheit. `room.nx` simulates the room, and `schedule.nx` reads and changes the schedule. Each page gets only the functions it calls. |
| `app/pages/lib/frame.nx` | The navigation bar's events, written once. Every page includes this file, and has buttons with the names the file uses. |
| `app/pages/home.nx` | A page in nxlang: events, functions, `switch`, and pictures named with `@pic(...)`. |
| `app/pages/day.nx` | Loops, page constants, and a waveform drawn point by point. |
| `app/pages/home.page.toml` | The page's components, as text. |
| `app/pictures/` | The pictures, as SVG files that share a style sheet and shapes, and nxwright's logo as a PNG file ([Pictures](#pictures)). |
| `app/app.toml`, `[defines]` | The theme's colours and the app's name, which the pictures and the components share. |
| `tests/` | Tests of the shared functions and of every page, run on a PC. |

## Building

Make changes in the source folder, `app/`, then build `thermostat.HMI`. In the `nxwright` folder, run:

```
python run.py build examples/thermostat/app examples/thermostat/thermostat.HMI --overwrite
```

A test checks that `thermostat.HMI` matches what `app/` builds, so build again after each change.

To see `thermostat.HMI` in strict Nextion syntax, extract it into a new folder:

```
python run.py extract examples/thermostat/thermostat.HMI thermostat-extracted
```

... or simply load the HMI file into the Nextion Editor and inspect the strict Nextion code.

## Testing

```
python run.py test examples/thermostat/tests
```

See [Testing your app](../../docs/testing.md) for how the tests run the pages' code on your PC.

## Pictures

Each page has two full-screen pictures: its background, and the same background with every button pressed. Text and buttons show the part of the background behind them ("crop image" in the Nextion Editor), and a button shows the pressed picture while it is touched. The pages' code also shows the pressed picture on the selected mode and unit, and on the schedule switch while it is on. The brightness slider shows it up to its knob. All the pictures are opaque, so the smaller ones include the colour that appears behind them.

The pictures are SVG files, which nxwright draws when it builds the project. A page's drawing is in its normal picture, such as `pictures/home/normal.svg`. Its pressed picture, `pictures/home/pressed.svg`, reuses and tweaks the normal version with `<use href="normal.svg#home"/>`. The pictures also share:

- `css/theme.css`, the style sheet every picture links. Its colours for the background, the text, and the accent are the defines `BACKGROUND`, `TEXT`, and `ACCENT` of `app.toml`, which the components use too. Try `--define ACCENT=#3aa8ff` when you build.
- `shapes.svg`, the icons and the frame of every page: its background and its navigation bar.
- Classes on a picture's root. `css/theme.css` styles an element by the class of the root it sits in, with a selector such as `.pressed .only-pressed`. For instance, `page-home` lights up the page's tab, and `pressed` shows the parts marked `only-pressed`, which the other pictures hide.

The About page shows both kinds of picture. Its title is the define `APP_NAME`, which nxwright draws into the page's SVG picture, and its logo is a PNG picture, `pictures/nxwright.png`.

## Fonts

The fonts were made with the Nextion Editor's font generator from Noto Sans, a typeface by the Noto Project Authors, and are under the SIL Open Font License 1.1 (`app/fonts/OFL.txt`). Each font is named after its size in pixels, from `Sans16` to `Sans100`.
