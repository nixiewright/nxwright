// Where package.json offers Go to Definition: the page preview's right-click
// menu, on a component or on the page alone, and the Components list's, on
// either. Run with `npm test`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const menus = manifest.contributes.menus;

function itemsOf(menu) {
  return menus[menu].filter((item) => item.command === "nxwright.goToDefinition");
}

test("Go to Definition is a command of the menus, not of the Command Palette", () => {
  const declared = manifest.contributes.commands
    .find((command) => command.command === "nxwright.goToDefinition");
  assert.equal(declared.title, "Go to Definition");
  assert.deepEqual(itemsOf("commandPalette").map((item) => item.when), ["false"]);
});

test("the preview's menu offers it on a component, and on the page alone", () => {
  assert.deepEqual(itemsOf("webview/context").map((item) => [item.when, item.group]), [
    ["webviewId == 'nxwright.pagePreview' && component || "
     + "webviewId == 'nxwright.pagePreview' && webviewSection == 'page'", "0_open@3"]]);
});

test("the Components list's menu offers it on a component and on the page", () => {
  assert.deepEqual(itemsOf("view/item/context").map((item) => [item.when, item.group]), [
    ["view == nxwright.components && viewItem == component || "
     + "view == nxwright.components && viewItem == page", "0_open@3"]]);
});
