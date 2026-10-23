// The Attributes section's page (media/properties.mjs), loaded in a page
// that jsdom makes, as the extension's webview would load it. Run with
// `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM(
  '<!DOCTYPE html><select id="objects" hidden></select>' +
  '<div id="properties"></div><div id="footer" hidden></div>');
const { window } = dom;
const posted = [];
globalThis.window = window;
globalThis.document = window.document;
globalThis.Option = window.Option;
globalThis.acquireVsCodeApi = () => ({ postMessage: (message) => posted.push(message) });
await import("../media/properties.mjs");

const PAGE = "file:///app/main.toml";

// An attribute as the server gives it (page_editing.properties).
function attribute(name, value, extra = {}) {
  return { name, value, kind: "number", labels: [], choices: [], treatment: "shown",
           given: true, line: 1, description: "", ...extra };
}

// The properties of a number component, `values` overriding its attributes'.
function properties(values = {}) {
  return {
    name: "n0", type: "number",
    attributes: [
      attribute("vscope", values.vscope ?? 0, { labels: [{ value: 0, label: "local" },
                                                          { value: 1, label: "global" }] }),
      attribute("x", values.x ?? 10),
      attribute("y", values.y ?? 20),
      attribute("pco", values.pco ?? "#000000", { kind: "colour" }),
    ],
  };
}

// Sends the section an object's properties, as the extension does after an
// edit of its page file.
function send(shown) {
  window.dispatchEvent(new window.MessageEvent("message", {
    data: { type: "properties", page: PAGE, properties: shown, problems: [] } }));
}

// The fields of the row of the attribute `name`.
function fields(name) {
  const heading = [...document.querySelectorAll("#properties th")]
    .find((cell) => cell.textContent === name);
  return [...heading.parentElement.querySelectorAll("input, select")];
}

// A value typed into `field`, then reported as Enter or leaving it reports it.
function typeAndReport(field, value) {
  field.focus();
  field.value = value;
  field.dispatchEvent(new window.Event("change", { bubbles: true }));
}

test("a value typed keeps its field's focus once the attributes come back", () => {
  send(properties());
  const [x] = fields("x");
  typeAndReport(x, "15");
  assert.deepEqual(posted.at(-1), { type: "setAttribute", page: PAGE, name: "n0",
                                    attribute: "x", value: "15", nearest: false });
  send(properties({ x: 15 }));
  const [shown] = fields("x");
  assert.notEqual(shown, x);
  assert.equal(document.activeElement, shown);
});

test("a choice picked keeps its drop-down's focus once the attributes come back", () => {
  send(properties());
  const [scope] = fields("vscope");
  typeAndReport(scope, "1");
  send(properties({ vscope: 1 }));
  assert.equal(document.activeElement, fields("vscope")[0]);
});

test("the field Tab moved to keeps the focus once the attributes come back", () => {
  send(properties());
  const [x] = fields("x");
  typeAndReport(x, "15");
  fields("y")[0].focus();
  send(properties({ x: 15 }));
  assert.equal(document.activeElement, fields("y")[0]);
});

test("a colour's text keeps the focus, rather than its sample before it", () => {
  send(properties());
  const [, text] = fields("pco");
  typeAndReport(text, "#ff0000");
  send(properties({ pco: "#ff0000" }));
  assert.equal(document.activeElement, fields("pco")[1]);
});

test("the focus is not taken back while the section does not have it", () => {
  send(properties());
  const [x] = fields("x");
  typeAndReport(x, "15");
  // As when the user has gone on to the page preview, or to the page file.
  document.hasFocus = () => false;
  try {
    send(properties({ x: 15 }));
  } finally {
    delete document.hasFocus;
  }
  assert.notEqual(document.activeElement, fields("x")[0]);
});

test("the text cursor stays where it was", () => {
  send(properties());
  const [, text] = fields("pco");
  typeAndReport(text, "#ff0000");
  text.setSelectionRange(2, 4);
  send(properties({ pco: "#ff0000" }));
  const [, shown] = fields("pco");
  assert.equal(document.activeElement, shown);
  assert.deepEqual([shown.selectionStart, shown.selectionEnd], [2, 4]);
});
