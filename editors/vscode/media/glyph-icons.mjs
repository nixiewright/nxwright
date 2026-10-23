// The glyphs (media/glyphs.mjs) that section headers show as icons, where
// VS Code's own icons have none that fits. VS Code draws a header's icon as
// a picture, not in the theme's colour, so each is a file per theme, in
// media/icons/, which `npm run icons` writes (scripts/write-icons.mjs) and
// test/glyph-icons.test.mjs checks.
import { GLYPHS } from "./glyphs.mjs";

// The glyphs written as icon files.
export const ICON_GLYPHS = ["build", "extract", "projectFile", "importProject",
                            "launchConfiguration", "sdCard"];

// The colour of icons in VS Code's light and dark themes (its
// icon.foreground).
export const ICON_COLOURS = { light: "#424242", dark: "#C5C5C5" };

// Returns the path of a glyph's icon file for a theme, from the extension's
// folder.
export function iconPath(glyph, theme) {
  return `media/icons/${glyph}-${theme}.svg`;
}

// Returns the text of a glyph's icon file in `colour`, drawn as the
// sections' webviews draw the glyph.
export function iconFile(glyph, colour) {
  return '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" ' +
    `color="${colour}" fill="none" stroke="currentColor" stroke-width="1.2" ` +
    `stroke-linecap="round" stroke-linejoin="round">${GLYPHS[glyph]}</svg>\n`;
}
