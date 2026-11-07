// The right-click menus of a locked page: the page preview's offers only
// what does not change the page, and Unlock page, and the Pages section's
// offers Lock page or Unlock page. Run with `npm test`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const menus = manifest.contributes.menus;
const PAGE_COMMANDS = ["nxwright.lockPage", "nxwright.lockPageWithPassword",
                       "nxwright.unlockPage"];
// What the page preview's menu still offers on a locked page.
const READING = ["nxwright.goToEvent", "nxwright.editAttributes", "nxwright.goToDefinition",
                 "nxwright.copyComponent"];

test("on a locked page, the page preview's menu hides what changes the page", () => {
  for (const item of menus["webview/context"]) {
    const name = item.command ?? item.submenu;
    if (READING.includes(name) || PAGE_COMMANDS.includes(name)) {
      continue;
    }
    // Every alternative of the condition needs the page unlocked.
    for (const alternative of item.when.split("||")) {
      assert.match(alternative, /&& !pageLocked\s*$/, name);
    }
  }
  for (const name of READING) {
    const item = menus["webview/context"].find((each) => each.command === name);
    assert.doesNotMatch(item.when, /pageLocked/, name);
  }
});

test("the page preview offers locking on the page, and unlocking on a locked one", () => {
  const items = menus["webview/context"].filter((item) => PAGE_COMMANDS.includes(item.command));
  assert.deepEqual(items.map((item) => [item.command, item.when]), [
    ["nxwright.lockPage",
     "webviewId == 'nxwright.pagePreview' && webviewSection == 'page' && !pageLocked"],
    ["nxwright.lockPageWithPassword",
     "webviewId == 'nxwright.pagePreview' && webviewSection == 'page' && !pageLocked"],
    ["nxwright.unlockPage",
     "webviewId == 'nxwright.pagePreview' && webviewSection == 'page' && pageLocked"]]);
});

test("the Pages section offers the same, by whether the page is locked", () => {
  const items = menus["view/item/context"].filter((item) => PAGE_COMMANDS.includes(item.command));
  assert.deepEqual(items.map((item) => [item.command, item.when]), [
    ["nxwright.lockPage", "view == nxwright.pages && viewItem == page"],
    ["nxwright.lockPageWithPassword", "view == nxwright.pages && viewItem == page"],
    ["nxwright.unlockPage", "view == nxwright.pages && viewItem == lockedPage"]]);
});

test("they are commands of the menus, not of the Command Palette", () => {
  const titles = Object.fromEntries(manifest.contributes.commands
    .filter((command) => PAGE_COMMANDS.includes(command.command))
    .map((command) => [command.command, command.title]));
  assert.deepEqual(titles, { "nxwright.lockPage": "Lock page",
                             "nxwright.lockPageWithPassword": "Lock page with password",
                             "nxwright.unlockPage": "Unlock page" });
  const hidden = menus.commandPalette.filter((item) => PAGE_COMMANDS.includes(item.command));
  assert.deepEqual(hidden.map((item) => [item.command, item.when]),
                   PAGE_COMMANDS.map((command) => [command, "false"]));
});
