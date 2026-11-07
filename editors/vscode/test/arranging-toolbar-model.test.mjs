// The buttons of the page preview's arranging toolbar
// (media/arranging-toolbar-model.mjs). Run with `npm test`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { arrangement } from "../media/arranging.mjs";
import { isEnabled, TOOLBAR_GROUPS } from "../media/arranging-toolbar-model.mjs";
import { GLYPHS } from "../media/glyphs.mjs";

const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const buttons = TOOLBAR_GROUPS.flat();
const button = (glyph) => buttons.find((entry) => entry.glyph === glyph);

test("the groups are ordering, aligning, sizing, then spacing, with no command twice", () => {
  assert.deepEqual(TOOLBAR_GROUPS.map((group) => group.length), [4, 6, 3, 6]);
  assert.equal(new Set(buttons.map((entry) => entry.command)).size, buttons.length);
});

test("each button has a glyph, and does what an arrangement or an ID-order move does", () => {
  const rects = [0, 20, 40].map((x, index) => ({ name: `r${index}`, x, y: 0, w: 10, h: 5 }));
  for (const entry of buttons) {
    assert.ok(GLYPHS[entry.glyph], entry.glyph);
    if (entry.how) {
      // `arrangement` throws on an arrangement it does not know.
      assert.doesNotThrow(() => arrangement(rects, entry.how), entry.how);
    } else {
      assert.ok(["front", "forward", "backward", "back"].includes(entry.direction), entry.glyph);
    }
  }
});

test("a button is enabled when the selection allows its command, on an unlocked page", () => {
  const enabled = (selection) => buttons.filter((entry) => isEnabled(entry, selection))
    .map((entry) => entry.glyph);
  const ordering = ["bringToFront", "bringForward", "sendBackward", "sendToBack"];
  const equalSpacing = ["spaceAcross", "spaceDown"];
  // Before the first drawing, and with nothing selected.
  assert.deepEqual(enabled(undefined), []);
  assert.deepEqual(enabled({ components: 0, placed: 0, pageLocked: false }), []);
  // With one component selected, on the strip under the page or on the page,
  // only the buttons that move it up or down the ID order are enabled.
  assert.deepEqual(enabled({ components: 1, placed: 0, pageLocked: false }), ordering);
  assert.deepEqual(enabled({ components: 1, placed: 1, pageLocked: false }), ordering);
  // Two on the page: everything but making the spacing equal.
  assert.deepEqual(enabled({ components: 2, placed: 2, pageLocked: false }),
                   buttons.map((entry) => entry.glyph)
                     .filter((glyph) => !equalSpacing.includes(glyph)));
  // Three on the page enable every button, and a locked page enables none.
  assert.equal(enabled({ components: 3, placed: 3, pageLocked: false }).length, buttons.length);
  assert.deepEqual(enabled({ components: 3, placed: 3, pageLocked: true }), []);
  assert.equal(isEnabled(button("spaceAcross"), { components: 3, placed: 2 }), false);
});

test("each button needs what the menu item of its command needs", () => {
  const menus = manifest.contributes.menus;
  // The `when` clause of a command's item in the preview's menu, joined with
  // its submenu's when the item is in a submenu.
  const whenOf = (command) => {
    const direct = menus["webview/context"].find((item) => item.command === command);
    if (direct) {
      return direct.when;
    }
    const submenu = manifest.contributes.submenus.map((declared) => declared.id)
      .find((id) => menus[id].some((item) => item.command === command));
    const items = menus[submenu];
    const opening = menus["webview/context"].find((item) => item.submenu === submenu);
    return `${opening.when} && ${items.find((item) => item.command === command).when ?? ""}`;
  };
  for (const entry of buttons) {
    const keys = whenOf(entry.command).split(/\s*&&\s*/);
    assert.ok(keys.includes("!pageLocked"), entry.command);
    // Of the keys the menu checks, the button needs the one that takes the most
    // selected components.
    const needed = ["spaceable", "several", "component"].find((key) => keys.includes(key));
    assert.equal(entry.needs, needed, entry.command);
  }
});
