// Locking pages: what the Pages section shows of a page, by the server's
// nxwright/pageLocks answer, and the password a lock takes. Run with
// `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { pageItemLook, passwordProblem } from "../out/pageLocking.js";

test("a locked page has a padlock, and the menu that unlocks it", () => {
  const locked = new Set(["home"]);
  assert.deepEqual(pageItemLook("home", locked), { contextValue: "lockedPage", padlock: true });
  assert.deepEqual(pageItemLook("day", locked), { contextValue: "page", padlock: false });
});

test("a page's context value also gives its events, for the Go to Event submenu", () => {
  const events = [{ event: "load", hasCode: true }, { event: "up", hasCode: false }];
  assert.deepEqual(pageItemLook("home", new Set(["home"]), events),
                   { contextValue: "lockedPage hasEvents codeLoad noCodeUp", padlock: true });
  assert.equal(pageItemLook("day", new Set(), events).contextValue,
               "page hasEvents codeLoad noCodeUp");
});

test("a password must have a character, and only ASCII ones", () => {
  assert.equal(passwordProblem("abc"), undefined);
  assert.equal(passwordProblem(""),
               "Type a password, or choose Lock page for a lock without one.");
  assert.equal(passwordProblem("é"),
               "Use only ASCII characters. The Nextion Editor may refuse others when it " +
               "opens the project.");
});
