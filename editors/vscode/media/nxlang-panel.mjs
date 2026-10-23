// The page of the panel explaining the switch to nxlang and making it
// (src/nxlangPanel.ts): a section for each thing nxlang adds, as the server
// gives them, each with how a person writes it in strict Nextion, when there
// is a usual way, beside how they write it in nxlang; what else nxlang lets
// you do, as the server lists it; the lines the switch
// will rewrite, under the section on calculation order, which is why they
// change; for a project in strict Nextion syntax, the button making the
// switch; and once it is made, the offer to format the project's code.
import { element } from "./elements.mjs";

const vscode = acquireVsCodeApi();
const byId = (id) => document.getElementById(id);
// The project's language, and whether the switch's changes are listed: the
// switch is offered only with both.
let language = undefined;
let listed = false;
// The section the lines the switch will rewrite go under.
const CHANGES_SECTION = "calculations";

window.addEventListener("message", (event) => {
  const message = event.data;
  if (message.type === "project") {
    language = message.language;
    const name = message.name ?? "the project";
    for (const shown of document.querySelectorAll(".project-name")) {
      shown.textContent = name;
    }
    showSwitch(name);
  } else if (message.type === "samples") {
    showSections(message);
  } else if (message.type === "changes") {
    showChanges(message);
  } else if (message.type === "note") {
    showNote(message.text);
  } else if (message.type === "switched") {
    showNote(undefined);
    byId("after").hidden = false;
  } else if (message.type === "formatted") {
    showFormatted(message);
  }
});

byId("format").addEventListener("click", () => vscode.postMessage({ type: "format" }));

function showSwitch(name) {
  const place = byId("switch");
  if (language === "nxlang") {
    place.replaceChildren(element("p", "hint", `${name} already uses nxlang.`));
    byId("changes").replaceChildren();
    return;
  }
  const button = element("button", "", "Switch to nxlang");
  button.disabled = !listed;
  button.addEventListener("click", () => vscode.postMessage({ type: "switch" }));
  place.replaceChildren(button);
}

function showChanges(reply) {
  const place = byId("changes");
  listed = reply.changes !== undefined;
  const button = byId("switch").querySelector("button");
  if (button) {
    button.disabled = !listed;
  }
  if (reply.error !== undefined) {
    place.replaceChildren(element("p", "problem", `The switch can't be made: ${reply.error}`));
    return;
  }
  if (!reply.changes) {
    // No switch to list: a project in nxlang, or one not known yet.
    place.replaceChildren();
    return;
  }
  if (reply.changes.length === 0) {
    place.replaceChildren(element("p", "hint",
      "None of your code calculates differently in nxlang, so no line will change."));
    return;
  }
  const byFile = new Map();
  for (const change of reply.changes) {
    byFile.set(change.file, [...(byFile.get(change.file) ?? []), change]);
  }
  place.replaceChildren(element("p", "", "These lines will change:"),
                        ...[...byFile].map(([file, changes]) => {
    const block = element("div", "file");
    const heading = element("h3");
    const open = element("button", "secondary", "Show the diff");
    open.addEventListener("click", () => vscode.postMessage({ type: "openChange", file }));
    heading.append(element("span", "", `${file}, ${changes.length} line(s)`), open);
    const lines = element("pre");
    lines.textContent = changes.map((change) =>
      `${change.line}: ${change.before.trim()}\n  -> ${change.after.trim()}`).join("\n");
    block.append(heading, lines);
    return block;
  }));
}

function showNote(text) {
  const note = byId("note");
  note.hidden = text === undefined;
  note.textContent = text ?? "";
}

function showFormatted(reply) {
  const lines = [reply.offered === 0 ? "No file needed formatting."
    : reply.changed === 0 ? "Nothing was formatted: the changes were not applied."
      : `${reply.changed} file(s) formatted.`];
  if (reply.refused.length > 0) {
    lines.push("These files were left as they are, because they could not be formatted:",
               ...reply.refused);
  }
  const block = element("div");
  block.append(...lines.map((line) => element("p", "hint", line)));
  byId("formatted").replaceChildren(block);
}

// Draws the sections with code, as the server gives them, and moves the
// lines the switch will rewrite under the one on calculation order.
function showSections(reply) {
  const place = byId("sections");
  if (reply.error !== undefined) {
    place.replaceChildren(element("p", "problem",
                                  `The examples could not be loaded: ${reply.error}`));
    return;
  }
  // What else nxlang lets you do, shown once the server has listed it.
  const more = reply.more ?? [];
  byId("more-list").replaceChildren(...more.map((item) => withCode(element("li"), item)));
  byId("more").hidden = more.length === 0;
  place.replaceChildren(...reply.samples.map((section) => {
    const block = element("section");
    block.append(element("h2", "", section.heading), worded(section.words));
    const codes = element("div", section.strict ? "codes" : "codes single");
    if (section.strict) {
      codes.append(codeOf("Strict Nextion", section.strict));
    }
    codes.append(codeOf("nxlang", section.nxlang));
    block.append(codes);
    if (section.after) {
      block.append(worded(section.after));
    }
    if (section.key === CHANGES_SECTION) {
      block.append(byId("changes"));
    }
    return block;
  }));
}

// A paragraph of `text`, its parts in backticks shown as code.
function worded(text) {
  return withCode(element("p"), text);
}

// `parent`, holding `text`, its parts in backticks shown as code.
function withCode(parent, text) {
  text.split("`").forEach((part, index) => {
    parent.append(index % 2 === 1 ? element("code", "", part) : part);
  });
  return parent;
}

// A labelled block of code.
function codeOf(label, text) {
  const block = element("div");
  const code = element("pre");
  code.textContent = text;
  block.append(element("div", "label", label), code);
  return block;
}

vscode.postMessage({ type: "ready" });
