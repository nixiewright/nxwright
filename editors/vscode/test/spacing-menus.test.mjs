// The page preview's Spacing submenu, whose commands make the gaps between
// the selected components equal, or widen or narrow them. Run with `npm test`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const menus = manifest.contributes.menus;
const SPACING_TITLES = {
  "nxwright.spaceAcross": "Make horizontal spacing equal",
  "nxwright.increaseHorizontalSpacing": "Increase horizontal spacing",
  "nxwright.decreaseHorizontalSpacing": "Decrease horizontal spacing",
  "nxwright.spaceDown": "Make vertical spacing equal",
  "nxwright.increaseVerticalSpacing": "Increase vertical spacing",
  "nxwright.decreaseVerticalSpacing": "Decrease vertical spacing",
};
const SPACING_COMMANDS = Object.keys(SPACING_TITLES);

test("the Spacing submenu shows with two or more components, on an unlocked page", () => {
  assert.deepEqual(manifest.contributes.submenus.find((menu) => menu.id === "nxwright.spacing"),
                   { id: "nxwright.spacing", label: "Spacing" });
  const entries = menus["webview/context"].filter((item) => item.submenu === "nxwright.spacing");
  assert.deepEqual(entries, [{
    submenu: "nxwright.spacing",
    when: "webviewId == 'nxwright.pagePreview' && several && !pageLocked",
    group: "4_arrange@3",
  }]);
});

test("horizontal commands come before vertical ones, and making the spacing equal needs " +
     "three components", () => {
  assert.deepEqual(menus["nxwright.spacing"], [
    { command: "nxwright.spaceAcross", when: "spaceable", group: "1_horizontal@1" },
    { command: "nxwright.increaseHorizontalSpacing", group: "1_horizontal@2" },
    { command: "nxwright.decreaseHorizontalSpacing", group: "1_horizontal@3" },
    { command: "nxwright.spaceDown", when: "spaceable", group: "2_vertical@1" },
    { command: "nxwright.increaseVerticalSpacing", group: "2_vertical@2" },
    { command: "nxwright.decreaseVerticalSpacing", group: "2_vertical@3" },
  ]);
});

test("each spacing command has its title, and is hidden from the Command Palette", () => {
  const titles = Object.fromEntries(manifest.contributes.commands
    .filter((command) => SPACING_COMMANDS.includes(command.command))
    .map((command) => [command.command, command.title]));
  assert.deepEqual(titles, SPACING_TITLES);
  const hidden = menus.commandPalette.filter((item) => SPACING_COMMANDS.includes(item.command));
  assert.deepEqual(hidden.map((item) => [item.command, item.when]).sort(),
                   SPACING_COMMANDS.map((command) => [command, "false"]).sort());
});
