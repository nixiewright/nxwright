// Writes the icon files of the glyphs section headers show (media/glyph-icons.mjs):
// `npm run icons`, after changing a glyph or the list.
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ICON_COLOURS, ICON_GLYPHS, iconFile, iconPath } from "../media/glyph-icons.mjs";

const extension = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
mkdirSync(path.join(extension, "media", "icons"), { recursive: true });
for (const glyph of ICON_GLYPHS) {
  for (const [theme, colour] of Object.entries(ICON_COLOURS)) {
    writeFileSync(path.join(extension, iconPath(glyph, theme)), iconFile(glyph, colour));
  }
}
