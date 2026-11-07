// The Go to Event submenu: the keys made from an object's events
// (src/eventMenu.ts, compiled to out/ before the tests run), and the
// commands and conditions in package.json that read them. Run with `npm test`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { CAN_ADD_EVENTS, EVENT_NAMES, HAS_EVENTS, addEventEnablement, eventCommand,
         eventCommandCondition, eventCommandTitle, eventMenuKeys, itemContextValue,
         itemKeyCondition, itemKindCondition } from "../out/eventMenu.js";

const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const menus = manifest.contributes.menus;
const PAGE = [{ event: "load", hasCode: true }, { event: "loadend", hasCode: false },
              { event: "down", hasCode: false }, { event: "up", hasCode: false },
              { event: "unload", hasCode: false }];
const BUTTON = [{ event: "down", hasCode: false }, { event: "up", hasCode: true }];

test("an object's events become keys, with or without code", () => {
  assert.deepEqual(eventMenuKeys(PAGE), {
    hasEvents: true, canAddEvents: true, codeLoad: true, noCodeLoadend: true, noCodeDown: true,
    noCodeUp: true, noCodeUnload: true,
  });
  assert.deepEqual(eventMenuKeys(BUTTON),
                   { hasEvents: true, canAddEvents: true, noCodeDown: true, codeUp: true });
  // A variable has no events, and no submenu.
  assert.deepEqual(eventMenuKeys([]), {});
  // A defaults.toml could list an event name that has no command. Such an
  // event is left out.
  assert.deepEqual(eventMenuKeys([{ event: "", hasCode: false },
                                  { event: "swipe", hasCode: true }]), {});
  assert.deepEqual(eventMenuKeys([{ event: "swipe", hasCode: true }, ...BUTTON]),
                   eventMenuKeys(BUTTON));
});

test("a Components section item's context value starts with its kind", () => {
  assert.equal(itemContextValue("component", BUTTON),
               "component hasEvents canAddEvents noCodeDown codeUp");
  assert.equal(itemContextValue("component", []), "component");
  assert.equal(itemContextValue("page", PAGE).split(" ")[0], "page");
});

test("a locked object's events can be opened, and none can be added", () => {
  assert.deepEqual(eventMenuKeys(BUTTON, true), { hasEvents: true, noCodeDown: true, codeUp: true });
  assert.equal(itemContextValue("component", BUTTON, true), "component hasEvents noCodeDown codeUp");
  assert.deepEqual(eventMenuKeys([], false), {});
});

test("the commands for events without code are greyed out when none can be added", () => {
  const enablement = Object.fromEntries(manifest.contributes.commands.map((entry) =>
    [entry.command, entry.enablement]));
  for (const event of EVENT_NAMES) {
    assert.equal(enablement[eventCommand(event, false)], addEventEnablement(), event);
    assert.equal(enablement[eventCommand(event, true)], undefined, event);
  }
  const condition = addEventEnablement();
  assert.ok(condition.startsWith(`${CAN_ADD_EVENTS} || `));
  const pattern = new RegExp(condition.match(/=~ \/(.*)\/$/)[1]);
  assert.match(itemContextValue("component", BUTTON), pattern);
  assert.doesNotMatch(itemContextValue("component", BUTTON, true), pattern);
});

test("each event has a command without code and one with code, hidden from the palette", () => {
  const titles = Object.fromEntries(manifest.contributes.commands.map((entry) =>
    [entry.command, entry.title]));
  const hidden = menus.commandPalette.filter((entry) => entry.when === "false")
    .map((entry) => entry.command);
  for (const event of EVENT_NAMES) {
    for (const hasCode of [false, true]) {
      const command = eventCommand(event, hasCode);
      assert.equal(titles[command], eventCommandTitle(event, hasCode), command);
      assert.ok(hidden.includes(command), command);
    }
  }
  assert.equal(eventCommandTitle("up", true), "up ✓");
  assert.equal(eventCommandTitle("up", false), "up");
});

test("the submenu's commands show for the keys an object has, in the events' order", () => {
  const entries = menus["nxwright.events"];
  assert.equal(entries.length, EVENT_NAMES.length * 2);
  for (const [index, event] of EVENT_NAMES.entries()) {
    for (const hasCode of [false, true]) {
      const entry = entries.find((each) => each.command === eventCommand(event, hasCode));
      assert.equal(entry.when, eventCommandCondition(event, hasCode));
      assert.equal(entry.group, `1_event@${index + 1}`);
    }
  }
  // The condition is true for the key in the preview's menu, and for the
  // word in a Components section item.
  const condition = eventCommandCondition("up", true);
  assert.ok(condition.startsWith("codeUp || "));
  const pattern = new RegExp(condition.match(/=~ \/(.*)\/$/)[1]);
  assert.match(itemContextValue("component", BUTTON), pattern);
  assert.doesNotMatch(itemContextValue("component", [{ event: "up", hasCode: false }]), pattern);
});

test("the submenu takes the place of Go to Event... in both menus", () => {
  assert.deepEqual(manifest.contributes.submenus.find((entry) => entry.id === "nxwright.events"),
                   { id: "nxwright.events", label: "Go to Event" });
  const preview = menus["webview/context"].find((entry) => entry.submenu === "nxwright.events");
  assert.deepEqual(preview, { submenu: "nxwright.events", group: "0_open@1",
                              when: `webviewId == 'nxwright.pagePreview' && ${HAS_EVENTS}` });
  const components = menus["view/item/context"]
    .find((entry) => entry.submenu === "nxwright.events"
          && entry.when.includes("nxwright.components"));
  assert.deepEqual(components, {
    submenu: "nxwright.events", group: "0_open@1",
    when: `view == nxwright.components && ${itemKeyCondition(HAS_EVENTS)}`,
  });
  const pages = menus["view/item/context"].filter((entry) => entry.submenu === "nxwright.events"
                                                   && entry.when.includes("nxwright.pages"));
  assert.deepEqual(pages, [{
    submenu: "nxwright.events", group: "0_open@1",
    when: `view == nxwright.pages && ${itemKeyCondition(HAS_EVENTS)}`,
  }]);
  assert.doesNotMatch(JSON.stringify(manifest), /nxwright\.goToEvent/);
});

test("the Components section's conditions still match its items, whatever their events", () => {
  assert.equal(itemKindCondition("component"), "viewItem =~ /^component( |$)/");
  for (const entry of menus["view/item/context"]) {
    if (!entry.when.includes("view == nxwright.components")) {
      continue;
    }
    assert.doesNotMatch(entry.when, /viewItem ==/, entry.command ?? entry.submenu);
    for (const kind of ["component", "page"]) {
      if (entry.when.includes(itemKindCondition(kind))) {
        const pattern = new RegExp(`^${kind}( |$)`);
        assert.match(itemContextValue(kind, BUTTON), pattern);
        assert.match(itemContextValue(kind, []), pattern);
      }
    }
  }
});
