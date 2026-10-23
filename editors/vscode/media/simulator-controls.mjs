// The Simulator section of nxwright's side bar (src/simulator.ts). While a
// simulation runs: the line saying that an agent drives it, while one does
// (simulator-agent-model.mjs), its buttons, the field whose text goes to the
// screen as an instruction from the serial line, the serial port the line is
// connected to, and the GPIO pins, whose inputs a click sets. While none
// runs: buttons that simulate the current project with the Simulator
// settings, from program.nx or from the page shown, run each launch
// configuration that simulates it, or create one.
import { glyphButton } from "./glyph-button.mjs";
import { pinRows } from "./gpio-pins-model.mjs";
import { agentLine } from "./simulator-agent-model.mjs";

const vscode = acquireVsCodeApi();

const idle = document.getElementById("idle");
const running = document.getElementById("running");
const idleNote = document.getElementById("idle-note");
const idleButtons = document.getElementById("idle-buttons");

idleButtons.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (button?.dataset.command) {
    vscode.postMessage({ type: "run", command: button.dataset.command });
  } else if (button?.dataset.launch !== undefined) {
    vscode.postMessage({ type: "launch", place: Number(button.dataset.launch) });
  }
});

// Shows the controls of a running simulation, or, while none runs, the
// buttons that start one.
function showIdle(message) {
  running.hidden = !message.simulating;
  idle.hidden = message.simulating;
  if (message.simulating) {
    return;
  }
  if (!message.project) {
    idleNote.textContent =
      "Open a file of a project, or choose one in the Project section, to simulate it.";
    idleButtons.replaceChildren();
    return;
  }
  // What the defaults are, and where: the Simulator settings among VS Code's.
  const settings = document.createElement("a");
  settings.href = "#";
  settings.textContent = "Open the Simulator settings";
  settings.addEventListener("click", (event) => {
    event.preventDefault();
    vscode.postMessage({ type: "openSettings" });
  });
  // Simulate page is offered while a page of the project is shown.
  const fromPage = message.page === undefined ? ""
    : `, and Simulate page starts it on ${message.page}, without running program.nx`;
  idleNote.replaceChildren(
    `Simulate project starts the app from program.nx${fromPage}. Both use the serial port, ` +
    "the SD cards' folders, and the log's formats that the Simulator settings give, in VS " +
    "Code's Settings. A launch configuration can give its own, and also the values a page " +
    "starts from. ", settings);
  idleButtons.replaceChildren(
    glyphButton({ command: "nxwright.simulate" }, "simulate", "Simulate project"),
    ...(message.page === undefined ? []
      : [glyphButton({ command: "nxwright.simulatePage" }, "simulate", "Simulate page")]),
    // By place: two configurations may share a name.
    ...message.configurations.map((name, place) =>
      glyphButton({ launch: String(place) }, "simulate", name, "secondary")),
    glyphButton({ command: "nxwright.addLaunchConfiguration" }, "launchConfiguration",
                "Create a launch configuration", "secondary"),
  );
}

for (const button of running.querySelectorAll("button[data-command]")) {
  button.addEventListener("click", () => vscode.postMessage({ type: button.dataset.command }));
}

const field = document.getElementById("instruction");
document.getElementById("serial").addEventListener("submit", (event) => {
  event.preventDefault();
  if (field.value) {
    vscode.postMessage({ type: "serial", text: field.value });
    field.select();
  }
});

const portList = document.getElementById("port");
const rateList = document.getElementById("rate");
const connectButton = document.getElementById("connect");
const stateLine = document.getElementById("port-state");
let connected = false;

window.addEventListener("message", (event) => {
  const message = event.data;
  if (message.type === "ports") {
    // While not connected, what the user picked stays picked.
    const kept = !message.state.connected;
    fill(portList, message.ports, (kept && portList.value) || message.state.name);
    fill(rateList, message.rates, (kept && rateList.value) || message.state.baud);
    showState(message.state);
  } else if (message.type === "portState") {
    showState(message.state);
  } else if (message.type === "idle") {
    showIdle(message);
  } else if (message.type === "pins") {
    showPins(message.pins);
  } else if (message.type === "agent") {
    showAgent(message);
  }
});

const agent = document.getElementById("agent");
const agentNote = document.getElementById("agent-note");
const agentConnect = document.getElementById("agent-connect");
// The port the line's button connects, or undefined while it shows none.
let agentPort;

function showAgent(message) {
  const line = agentLine(message);
  agent.hidden = !line.shown;
  agentNote.textContent = line.note ?? "";
  agentPort = line.button;
  agentConnect.hidden = !agentPort;
  agentConnect.textContent = agentPort?.label ?? "";
}

agentConnect.addEventListener("click", () => {
  if (agentPort) {
    vscode.postMessage({ type: "connect", name: agentPort.name, baud: agentPort.baud });
  }
});

connectButton.addEventListener("click", () => {
  if (connected) {
    vscode.postMessage({ type: "disconnect" });
  } else {
    connect();
  }
});

// A change while connected applies at once.
for (const list of [portList, rateList]) {
  list.addEventListener("change", () => {
    if (connected) {
      connect();
    }
  });
}

function connect() {
  if (portList.value) {
    vscode.postMessage({ type: "connect", name: portList.value, baud: Number(rateList.value) });
  }
}

// Fills `list` with `values`, `chosen` selected: kept even when it is not
// among them, such as a port the launch configuration names that is gone.
function fill(list, values, chosen) {
  const all = values.map(String);
  if (chosen !== undefined && chosen !== null && chosen !== "" && !all.includes(String(chosen))) {
    all.push(String(chosen));
  }
  list.replaceChildren(...all.map((value) => new Option(value, value)));
  if (chosen !== undefined && chosen !== null && chosen !== "") {
    list.value = String(chosen);
  }
}

function showState(state) {
  connected = state.connected;
  connectButton.textContent = connected ? "Disconnect" : "Connect";
  if (connected) {
    fill(portList, [...portList.options].map((option) => option.value), state.name);
    fill(rateList, [...rateList.options].map((option) => option.value), state.baud);
  }
  stateLine.classList.toggle("problem", Boolean(state.problem));
  if (connected) {
    stateLine.textContent = `Connected to ${state.name} at ${state.baud} bits per second.`;
  } else if (state.problem) {
    stateLine.textContent = `${state.name}: ${state.problem}`;
  } else {
    stateLine.textContent = "Not connected.";
  }
}

const pinsGroup = document.getElementById("pins-group");
const pinList = document.getElementById("pins");

// Lists the GPIO pins, each a row of three cells: its name, what it is, and
// its level, a button for an input. None shows for a screen without GPIO.
function showPins(pins) {
  pinsGroup.hidden = !pins;
  pinList.replaceChildren(...(pins ? pinRows(pins) : []).flatMap(pinCells));
}

function pinCells(row, number) {
  const name = document.createElement("span");
  name.textContent = row.name;
  const kind = document.createElement("span");
  kind.textContent = row.kind;
  let level;
  if (row.settable) {
    level = document.createElement("button");
    level.title = row.title;
    level.addEventListener("click", () =>
      vscode.postMessage({ type: "pin", pin: number, level: 1 - row.level }));
  } else {
    level = document.createElement("span");
  }
  level.textContent = row.level === null ? "" : String(row.level);
  return [name, kind, level];
}

vscode.postMessage({ type: "ready" });
