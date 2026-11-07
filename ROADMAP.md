# Roadmap

What nxwright will or might do next. None of it has a date, and each item may change once it is designed. If one of them matters to you, or you would like to work on it, open an issue.

## Matching the screen

Tests and the simulator are meant to behave as a real Nextion screen does, but in rare cases they do not. Nextion publishes no full specification of the language, so nxwright follows the Nextion Editor's simulator. That leaves two kinds of gaps:

- **Differences from the Nextion Editor's simulator.** nxwright has not yet compared some behaviours with the Nextion Editor's simulator, and a few are known to differ. See [How nxwright runs Nextion code](docs/screen-code.md#not-compared-yet) and [Simulating your app](docs/simulator.md#known-differences) for what is known so far.
- **Differences from real screens.** Where the Nextion Editor's simulator differs from a real screen, nxwright likely differs too, and it may have inherited that simulator's bugs.

Finding and fixing these gaps comes first, above all those with real screens. If your app behaves differently on a real screen than in nxwright, please open an issue. Contributors may not have a screen like yours, so you may need to try out the fixes yourself.

## Testing the whole app

Today, a test runs the events you choose on one page, starting from values you give ([docs/testing.md](docs/testing.md)). A timer's event runs only when the test runs it, and a `page` command is recorded without opening the page. So a test cannot check a timer as time passes, or a flow from one page to the next.

The simulator already runs the whole app: `program.nx`, page changes, timers on a clock, and presses. A test could do the same. It would start the app, press and release components, let time pass, and then check the values and the page shown.

A test could also stand in for the device on the other end of the serial line, sending bytes to the screen and checking the bytes that come back.

## Pictures kept as SVG files

A screen's design is mostly flat shapes, lines, and text, which SVG describes well. An SVG file is also text, so changes to it show up in a diff, like changes to your code.

Today, the source folder keeps each picture as a PNG or other picture file. If you draw your pictures in SVG, you turn them into PNG files yourself, each time an SVG file changes.

A command could generate the PNG files from SVG files kept in the source folder, and keep them up to date as the SVG files change. A panel in VS Code could offer the same thing. The build, the preview, and the simulator would go on reading the PNG files, so nothing would change for a project without SVG files.

## Newer versions of the Nextion Editor

nxwright is tested with one release of the Nextion Editor at a time. As Nextion publishes new releases, nxwright will move to them, to support the component types and attributes they add, and to compile with their firmware. See [tools/editor/RELEASES.md](tools/editor/RELEASES.md) for how that move is made.
