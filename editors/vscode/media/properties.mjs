// The Attributes section of nxwright's side bar (src/sideBar.ts): a list of
// the page's objects, choosing the one it shows; then the selected object's
// name, which renames it, its type, and each attribute its type has, a
// default the table leaves out shown dimmed. As nxwright's descriptions
// say, an attribute may show its value without a field to edit, or be left
// out unless the table gives it.
//
// An attribute's description shows in a footer under the list, once its
// field has the focus or its row is clicked; its name has it as a tooltip
// too. An attribute with choices is a drop-down of their names
// (properties-model.mjs). A colour has a sample of itself before its field,
// which opens a colour picker: a colour picked is stored as the nearest the
// screen holds, which the server works out.
//
// Changing a value, or the name, goes to the extension, which edits the
// page file through the editor, so undo works there.

import { element } from "./elements.mjs";
import { choiceEntries, listed, rowLines, valueText } from "./properties-model.mjs";

const vscode = acquireVsCodeApi();
const panel = document.getElementById("properties");
const objects = document.getElementById("objects");
const footer = document.getElementById("footer");
// What the footer says before an attribute is reached.
const FOOTER_HINT = "Click an attribute, or move to its field with Tab, to see what it does.";
// A colour as a page file writes it.
const COLOUR = /^#[0-9a-fA-F]{6}$/;
// The page file the list's objects are of, sent back with a choice.
let objectsPage = undefined;

objects.addEventListener("change", () => {
  if (objects.value) {
    vscode.postMessage({ type: "select", page: objectsPage, name: objects.value });
  }
});

// Fills the list with the page's objects, `selected` chosen, or a line
// asking for one; hidden without a page.
function showObjects(message) {
  objectsPage = message.page;
  objects.hidden = message.page === undefined;
  const choices = message.objects.map((entry) =>
    new Option(`${entry.name} (${entry.type})`, entry.name));
  if (!message.selected) {
    choices.unshift(new Option("Choose an object", ""));
  } else if (!message.objects.some((entry) => entry.name === message.selected)) {
    // Selected before the list has it, as just after a rename, until the
    // page's objects are read again: kept, so that the list does not go blank.
    choices.push(new Option(message.selected, message.selected));
  }
  objects.replaceChildren(...choices);
  objects.value = message.selected ?? "";
}
// The kinds of attribute that name one of the folder's resources, chosen
// from a list of their names.
const NAMED_KINDS = new Set(["picture", "font", "animation", "video", "sound"]);

let shown = undefined;      // the name of the object the panel shows
let waiting = undefined;    // its properties, which came while a value was being typed

window.addEventListener("message", (event) => {
  const message = event.data;
  if (message.type === "properties") {
    // A value being typed into the shown object's panel is not wiped out:
    // its update waits for the field to be left. Any other replaces it.
    if (message.error !== undefined) {
      // The object's properties cannot be read, such as while its page file
      // is half typed: the panel keeps them, under a note saying why.
      showPanelNote(`Not read again: ${message.error}`);
    } else if (typing() && message.properties?.name === shown) {
      waiting = message;
    } else {
      waiting = undefined;
      showProperties(message.properties, message.problems, message.page);
    }
  } else if (message.type === "objects") {
    showObjects(message);
  } else if (message.type === "empty") {
    // No object to show: the text says how to choose one.
    waiting = undefined;
    showProperties(undefined, []);
    panel.appendChild(element("p", "hint", message.text));
  }
});

// True while a field of the panel holds a value typed but not yet reported.
function typing() {
  const field = document.activeElement;
  return document.hasFocus() && panel.contains(field) && "reported" in field.dataset &&
    field.value !== field.dataset.reported;
}
panel.addEventListener("focusout", () => {
  // Once the change the field reports has gone, then the waiting properties.
  setTimeout(() => {
    if (waiting && !panel.contains(document.activeElement)) {
      showProperties(waiting.properties, waiting.problems, waiting.page);
      waiting = undefined;
    }
  });
});

// Shows an object's properties. `problems` are the errors found in its
// table, [{line, message}]: each by the attribute whose line it is on, the
// others at the top. `page` is its page file, sent back with each edit.
function showProperties(properties, problems, page) {
  const focused = focusedField();
  panel.textContent = "";
  // The footer keeps its description while the same object shows again, as
  // after an edit; another object starts it afresh.
  if (properties?.name !== shown) {
    footer.replaceChildren(FOOTER_HINT);
  }
  footer.hidden = !properties;
  shown = properties?.name;
  if (!properties) {
    return;
  }
  const byLine = new Map();
  const general = [];
  const lines = rowLines(properties.attributes);
  for (const problem of problems) {
    if (lines.has(problem.line)) {
      byLine.set(problem.line, [...(byLine.get(problem.line) ?? []), problem.message]);
    } else {
      general.push(problem.message);
    }
  }
  for (const message of general) {
    panel.appendChild(element("div", "problem", message));
  }
  const table = element("table");
  table.appendChild(row("name", input("text", properties.name, (value) =>
    vscode.postMessage({ type: "rename", page, name: properties.name, newName: value }))));
  table.appendChild(row("type", element("span", "", properties.type)));
  for (const attribute of properties.attributes) {
    if (!listed(attribute)) {
      continue;
    }
    const field = attribute.treatment === "value-only"
      ? element("span", "", valueText(attribute))
      : attributeField(attribute, (value, nearest = false) => vscode.postMessage({
        type: "setAttribute", page, name: properties.name, attribute: attribute.name, value,
        nearest }));
    const line = row(attribute.name, field, attribute.given ? "" : "default",
                     attribute.description);
    // Reached by the mouse or by the keyboard, its description shows below.
    const describe = () => showDescription(attribute.name, attribute.description);
    line.addEventListener("click", describe);
    line.addEventListener("focusin", describe);
    for (const message of attribute.given ? byLine.get(attribute.line) ?? [] : []) {
      line.lastChild.appendChild(element("div", "problem", message));
    }
    table.appendChild(line);
  }
  panel.appendChild(table);
  refocus(focused);
}

// The panel's field that has the focus, by its key (see row), with its text
// cursor; undefined when the focus is elsewhere. Drawing the panel again
// replaces each field, as after every edit, so the focus is put back on the
// new field with the same key (refocus). Only while the section has the
// focus: putting it back otherwise would take it from where the user is.
function focusedField() {
  const field = document.activeElement;
  if (!document.hasFocus() || !panel.contains(field) || !("key" in field.dataset)) {
    return undefined;
  }
  return { key: field.dataset.key, start: field.selectionStart, end: field.selectionEnd };
}

function refocus(focused) {
  const field = focused &&
    [...panel.querySelectorAll("input, select")].find((each) => each.dataset.key === focused.key);
  if (!field) {
    return;
  }
  field.focus();
  // Only a text field has a cursor: a number's, a colour's sample, or a
  // drop-down has none.
  if (typeof focused.start === "number") {
    field.setSelectionRange(focused.start, focused.end);
  }
}

function showPanelNote(text) {
  panel.querySelector(".note")?.remove();
  panel.prepend(element("div", "problem note", text));
}

// Shows an attribute's name, then its description, in the footer. A long
// description scrolls within the footer, and each new one starts at the
// footer's top.
function showDescription(name, description) {
  footer.replaceChildren(element("strong", "", name));
  if (description) {
    footer.appendChild(element("div", "", description));
  }
  footer.scrollTop = 0;
}

// A field for an attribute's value, which calls `changed(value, nearest)`
// once it changes, `nearest` true for a colour picked rather than typed.
function attributeField(attribute, changed) {
  if (attribute.labels.length > 0) {
    const field = document.createElement("select");
    for (const entry of choiceEntries(attribute)) {
      const option = new Option(entry.text, entry.value);
      option.selected = entry.selected;
      field.appendChild(option);
    }
    return reporting(field, changed);
  }
  if (attribute.kind === "colour") {
    return colourField(attribute, changed);
  }
  if (NAMED_KINDS.has(attribute.kind)) {
    const field = document.createElement("select");
    const current = attribute.value === 65535 ? "none" : String(attribute.value);
    const choices = attribute.choices.includes(current) ? attribute.choices
      : [current, ...attribute.choices];
    for (const choice of choices) {
      const option = element("option", "", choice);
      option.selected = choice === current;
      field.appendChild(option);
    }
    return reporting(field, changed);
  }
  return input(attribute.kind === "number" ? "number" : "text", String(attribute.value), changed);
}

// A colour's field, after a sample of the colour the page file gives, which
// opens the webview's colour picker, by a click, Enter, or Space. A colour
// picked is reported once the picker closes, so that each pick is one edit;
// while it is open, the section is not drawn again (see typing).
function colourField(attribute, changed) {
  const value = String(attribute.value);
  const sample = document.createElement("input");
  sample.type = "color";
  sample.className = COLOUR.test(value) ? "sample" : "sample empty";
  sample.title = "Pick a colour";
  if (COLOUR.test(value)) {
    sample.value = value.toLowerCase();
  }
  const wrapper = element("span", "colour");
  wrapper.appendChild(reporting(sample, (picked) => changed(picked, true)));
  wrapper.appendChild(input("text", value, changed));
  return wrapper;
}

// An input that reports its value once it changes: on Enter, or on leaving it.
function input(kind, value, changed) {
  const field = document.createElement("input");
  field.type = kind;
  field.value = value;
  return reporting(field, changed);
}

// Reports a field's value as it changes, and keeps the value last reported,
// which tells a value being typed (see typing).
function reporting(field, changed) {
  field.dataset.reported = field.value;
  field.addEventListener("change", () => {
    field.dataset.reported = field.value;
    changed(field.value);
  });
  return field;
}

// A row of the panel, its heading `label`. Each of its fields is keyed by
// the label and the field's place in the row, as "pco 1" for a colour's
// text after its sample, so that the focus can be put back on it.
function row(label, field, kind = "", tooltip = "") {
  const line = element("tr", kind);
  const heading = element("th", "", label);
  if (tooltip) {
    heading.title = tooltip;
  }
  line.appendChild(heading);
  const cell = element("td");
  cell.appendChild(field);
  cell.querySelectorAll("input, select").forEach((each, place) => {
    each.dataset.key = `${label} ${place}`;
  });
  line.appendChild(cell);
  return line;
}

vscode.postMessage({ type: "ready" });
