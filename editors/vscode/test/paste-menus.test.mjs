// The paste items of the page preview's and the Components list's
// right-click menus, as package.json declares them.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf-8"));

// The paste items a menu lists, in the order declared: the command, when
// it shows, and its place in the menu.
function pasteItems(menu) {
  return manifest.contributes.menus[menu]
    .filter((item) => item.command?.startsWith("nxwright.paste"))
    .map((item) => [item.command, item.when, item.group]);
}

const titleOf = (command) =>
  manifest.contributes.commands.find((entry) => entry.command === command)?.title;

test("the preview's menu lists Paste, Paste Here, and Paste Special alone", () => {
  assert.deepEqual(pasteItems("webview/context"), [
    ["nxwright.pasteComponents", "webviewId == 'nxwright.pagePreview'", "2_clipboard@3"],
    ["nxwright.pasteHere", "webviewId == 'nxwright.pagePreview' && webviewSection == 'page'",
     "2_clipboard@4"],
    ["nxwright.pasteSpecial", "webviewId == 'nxwright.pagePreview'", "2_clipboard@5"],
  ]);
});

test("the Components list's menu lists Paste and Paste Special on every row", () => {
  assert.deepEqual(pasteItems("view/item/context"), [
    ["nxwright.pasteComponents", "view == nxwright.components", "1_clipboard@3"],
    ["nxwright.pasteSpecial", "view == nxwright.components", "1_clipboard@4"],
  ]);
});

test("the paste items' names", () => {
  assert.deepEqual(["nxwright.pasteComponents", "nxwright.pasteHere", "nxwright.pasteSpecial"]
    .map(titleOf), ["Paste", "Paste Here", "Paste Special..."]);
});

test("Paste in place and Paste without code stay commands, for a keybinding", () => {
  for (const command of ["nxwright.pasteInPlace", "nxwright.pasteWithoutCode"]) {
    assert.ok(titleOf(command), `${command} is declared`);
    assert.deepEqual(manifest.contributes.menus.commandPalette
      .filter((item) => item.command === command), [{ command, when: "false" }]);
  }
});
