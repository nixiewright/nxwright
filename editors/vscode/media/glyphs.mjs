// The glyphs of the side bar's buttons, by name, which its webview sections
// draw (media/glyph-button.mjs) and its headers show as icons
// (media/glyph-icons.mjs). Each is the inside of an SVG drawing on a 16 by
// 16 grid. Lines are drawn in the button's colour (currentColor) and shapes
// left empty, unless a shape fills itself, as the play button does. Each
// takes the picture most tools use for its action.
export const GLYPHS = {
  // A folder with a plus.
  newProject: '<path d="M1.5 3.5h4l1.5 1.5h7.5v8.5h-13z"/><path d="M8 7v5M5.5 9.5h5"/>',
  // Two folders, one behind the other.
  chooseProject: '<path d="M4 4.5V3h3l1 1h6.5v7.5H13"/><path d="M1.5 5.5h4l1 1H13v7.5H1.5z"/>',
  // An arrow pointing down into a tray.
  importProject: '<path d="M1.5 9.5v4h13v-4"/><path d="M8 1.5v8M5 6.5l3 3 3-3"/>',
  // A pencil, on a slant: its body, and its point.
  edit: '<path d="M10.5 2.5l3 3-7.5 7.5H3v-3z"/><path d="M9 4l3 3"/>',
  // A hammer, on a slant: its head, and its handle.
  build: '<path d="M8.6 2.4l5 5-2.1 2.1-5-5z"/><path d="M8.3 6.5l1.3 1.3-6.5 6.4-1.3-1.3z"/>',
  // A chip, with its pins on each side.
  compile: '<path d="M4.5 4.5h7v7h-7z"/>' +
    '<path d="M6.5 2v2.5M9.5 2v2.5M6.5 11.5V14M9.5 11.5V14M2 6.5h2.5M2 9.5h2.5M11.5 6.5H14' +
    'M11.5 9.5H14"/>',
  // An arrow pointing up, off a line.
  upload: '<path d="M2.5 13.5h11"/><path d="M8 11V2.5M4.5 6L8 2.5 11.5 6"/>',
  // Two links of a chain, joined on a slant.
  link: '<path d="M6.5 9.5l3-3"/><path d="M7.5 4.5l1.2-1.2a2.5 2.5 0 0 1 3.5 3.5L11 8"/>' +
    '<path d="M8.5 11.5l-1.2 1.2a2.5 2.5 0 0 1-3.5-3.5L5 8"/>',
  // A document with a small gear.
  projectFile: '<path d="M8.5 14.5h-5v-13h6l3 3v3"/><path d="M9.5 1.5v3h3"/>' +
    '<circle cx="12" cy="12" r="1.7"/>' +
    '<path d="M12 8.8v1M12 14.2v1M8.8 12h1M14.2 12h1' +
    'M9.7 9.7l.7.7M13.6 13.6l.7.7M9.7 14.3l.7-.7M13.6 10.4l.7-.7"/>',
  // An SD card, with its cut corner and its contacts.
  sdCard: '<path d="M3.5 1.5h7l2.5 2.5v10.5h-9.5z"/><path d="M6 1.5v3M8 1.5v3M10 1.5v3"/>',
  // A triangle pointing right, as a play button.
  simulate: '<path d="M4.5 2.5v11l9-5.5z" fill="currentColor"/>',
  // A gear with a plus: its ring, its hole, its eight thick teeth, and the
  // plus at its corner.
  launchConfiguration: '<circle cx="7" cy="9" r="3"/><circle cx="7" cy="9" r="1"/>' +
    '<path stroke-width="2" stroke-linecap="butt" d="M7 4.6V6M7 12v1.4M2.6 9H4M10 9h1.4' +
    'M3.9 5.9l1 1M9.1 11.1l1 1M3.9 12.1l1-1M9.1 6.9l1-1"/>' +
    '<path d="M13 1.5v4M11 3.5h4"/>',
};
