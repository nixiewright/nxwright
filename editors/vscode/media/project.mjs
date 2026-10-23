// The Project section of nxwright's side bar (src/projectView.ts): the
// current project's settings and a Build button, or, without a project,
// buttons to create, import, or choose one. Drawn again each time the
// extension sends what to show. A button or link asks the extension to run
// its command.
import { glyphButton, glyphDrawing } from "./glyph-button.mjs";
import { projectLines } from "./project-lines.mjs";

const vscode = acquireVsCodeApi();
const section = document.getElementById("project");

window.addEventListener("message", (event) => {
  if (event.data.type === "project") {
    draw(event.data.shown);
  }
});

section.addEventListener("click", (event) => {
  const control = event.target.closest("[data-command]");
  if (control) {
    event.preventDefault();
    vscode.postMessage({ type: "run", command: control.dataset.command });
  }
});

function draw(shown) {
  section.replaceChildren(...(shown.project ? projectParts(shown.project)
                                            : withoutProjectParts(shown.folders)));
}

// The project's name, its path as the name's tooltip, its lines of
// settings (project-lines.mjs), and the Build button.
function projectParts(project) {
  const shown = projectLines(project);
  const name = element("h2", shown.name);
  name.title = shown.path;
  const parts = [name];
  if (shown.note) {
    parts.push(element("p", shown.note, "note"));
  }
  for (const line of shown.lines) {
    const drawn = element("div", "", "line");
    drawn.append(...line.flatMap(part));
    parts.push(drawn);
  }
  parts.push(buttons([glyphButton({ command: "nxwright.build" }, "build", "Build")]));
  return parts;
}

// The nodes of one part of a line of settings: words, a link, or a pencil.
// Words are split at their " · " separators, each value kept whole, so that
// a narrow section wraps the line only between values; a pencil follows its
// value with no space, so it stays beside it.
function part(shown) {
  if (shown.edit) {
    return [editButton(shown.edit, shown.title)];
  }
  if (shown.link) {
    const link = element("a", shown.text, "value");
    link.href = "#";
    link.dataset.command = shown.link;
    link.title = shown.title;
    return [link];
  }
  return shown.text.split(" · ").flatMap((value, index) => {
    const words = element("span", value, "value");
    if (shown.title) {
      words.title = shown.title;
    }
    return index === 0 ? (value ? [words] : []) : [document.createTextNode(" · "), words];
  });
}

// Without a project: what to do, and the buttons that do it.
function withoutProjectParts(folders) {
  const choices = [
    glyphButton({ command: "nxwright.newSourceFolder" }, "newProject",
                "Create a new nxwright project"),
    glyphButton({ command: "nxwright.importProject" }, "importProject",
                "Import a Nextion Editor project", "secondary"),
  ];
  let note = "No project is open. Create one, or import a Nextion Editor project.";
  if (folders > 1) {
    note = "The workspace holds several projects. Choose the one to show, or open a file of one.";
    choices.unshift(glyphButton({ command: "nxwright.chooseProject" }, "chooseProject",
                                "Choose the project"));
  }
  return [element("p", note, "note"), buttons(choices)];
}

// A small button with a pencil, after a setting, running the command that
// changes it, `title` saying what it does.
function editButton(command, title) {
  const button = document.createElement("button");
  button.className = "edit";
  button.dataset.command = command;
  button.title = title;
  button.setAttribute("aria-label", button.title);
  button.append(glyphDrawing("edit"));
  return button;
}

function buttons(children) {
  const row = document.createElement("div");
  row.className = "buttons";
  row.append(...children);
  return row;
}

function element(tag, text, className) {
  const made = document.createElement(tag);
  made.textContent = text;
  if (className) {
    made.className = className;
  }
  return made;
}

vscode.postMessage({ type: "ready" });
