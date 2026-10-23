# Roadmap

What nxwright will or might do next. None of it has a date, and each item may change once it is designed. If one of them matters to you, or you would like to work on it, open an issue.

## Matching the screen

Tests and the simulator should aim to always behave as a real Nextion screen does. In rare cases, this is not the case. The gaps are of two kinds:

- **The Nextion Editor's simulator.** nxwright has not yet compared some behaviours with it, and a few are known to differ. [How nxwright runs Nextion code](docs/screen-code.md#not-compared-yet) and [Simulating your app](docs/simulator.md#known-differences) list them. Others are not known yet.
- **Real screens.** Nextion publishes no full specification of the language, so nxwright follows the Nextion Editor's simulator. Where that simulator differs from a real screen, nxwright likely differs too, and it may have inherited the Editor's simulator's bugs.

Finding and fixing these mismatches comes first, above all those with real screens. If your app behaves differently on a real screen than in nxwright, please open an issue. You will need to work with contributors to iterate on the fixes since the specific screen(s) may not be available to them.

## Testing the whole app

Today, a test runs the events you choose on one page, from values you give ([docs/testing.md](docs/testing.md)). A timer's event runs only when the test runs it, and a `page` command is recorded without opening the page. So a test cannot check a timer as time passes, or a flow from one page to the next.

The simulator already runs the whole app: `program.nx`, page changes, timers on a clock, and presses. A test could do the same. It would start the app, press and release components, let time pass, and then check the values and the page shown.

A test could also stand in for the device on the other end of the serial line. It would send bytes to the screen, and check the bytes the screen sends back. The test would then check the whole app as that device sees it.

## Pictures kept as SVG files

A screen's design is mostly flat shapes, lines, and text, which SVG describes well. An SVG file is text too, so its changes show in a diff, as your code's do.

Today, the source folder keeps each picture as a PNG or other picture file. If you draw your pictures in SVG, you turn them into PNG files yourself, each time an SVG file changes.

A command could draw the PNG files from SVG files kept in the source folder, as the font generator makes fonts from typefaces. It would draw them again after an SVG file changes. A panel in VS Code could do the same. The build, the preview, and the simulator would go on reading the PNG files, so nothing would change for a project without SVG files.

## Newer versions of the Nextion Editor

nxwright is tested with projects of Nextion Editor 3.1.73. A newer Nextion Editor may add component types and attributes that nxwright does not know. Today, the build refuses them, because nearly every unknown name is a typo. `nxwright extract` also refuses a project whose components have attributes it does not know. So a project cannot use a new type or attribute until nxwright is updated to know it, which could hold the project back.

A build option, off by default, could be a way out until then. With it, the build would write the unknown types and attributes into the project file anyway. The page file would give such an attribute's value as bytes, since nxwright knows neither its size nor whether it is text or a number. `nxwright extract` would bring such attributes back in the same form. Once nxwright knows the new type or attribute, the project would go back to the normal build.
