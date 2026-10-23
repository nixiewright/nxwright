// The page preview's menu items that move components up or down the ID
// order, in the order the menu shows them. Run with `npm test`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const ORDER_COMMANDS = ["nxwright.bringToFront", "nxwright.bringForward",
                        "nxwright.sendBackward", "nxwright.sendToBack"];

test("to the front, forward, backward, and to the back, in that order", () => {
  const items = manifest.contributes.menus["webview/context"]
    .filter((item) => ORDER_COMMANDS.includes(item.command));
  assert.deepEqual(items.map((item) => [item.command, item.group]), [
    ["nxwright.bringToFront", "5_order@1"], ["nxwright.bringForward", "5_order@2"],
    ["nxwright.sendBackward", "5_order@3"], ["nxwright.sendToBack", "5_order@4"]]);
  for (const item of items) {
    assert.equal(item.when, "webviewId == 'nxwright.pagePreview' && component");
  }
});

test("each is a command of the menu, not of the Command Palette", () => {
  const titles = Object.fromEntries(manifest.contributes.commands
    .filter((command) => ORDER_COMMANDS.includes(command.command))
    .map((command) => [command.command, command.title]));
  assert.deepEqual(titles, { "nxwright.bringToFront": "Bring to front",
                             "nxwright.bringForward": "Bring forward",
                             "nxwright.sendBackward": "Send backward",
                             "nxwright.sendToBack": "Send to back" });
  const hidden = manifest.contributes.menus.commandPalette
    .filter((item) => ORDER_COMMANDS.includes(item.command));
  assert.deepEqual(hidden.map((item) => [item.command, item.when]),
                   ORDER_COMMANDS.map((command) => [command, "false"]));
});
