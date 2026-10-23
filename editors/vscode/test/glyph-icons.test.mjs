// The icon files of the glyphs section headers show draw those glyphs
// (media/glyph-icons.mjs): a changed glyph needs `npm run icons`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { ICON_COLOURS, ICON_GLYPHS, iconFile, iconPath } from "../media/glyph-icons.mjs";

const extension = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("each icon file draws its glyph, in each theme's colour", () => {
  for (const glyph of ICON_GLYPHS) {
    for (const [theme, colour] of Object.entries(ICON_COLOURS)) {
      const file = path.join(extension, iconPath(glyph, theme));
      assert.equal(readFileSync(file, "utf8"), iconFile(glyph, colour),
                   `${iconPath(glyph, theme)}: run npm run icons`);
    }
  }
});
