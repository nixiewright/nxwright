// The Simulator section of nxwright's side bar (src/simulator.ts).
// While a simulation runs, it shows:
//  - the line saying that an agent drives it, while one does
//    (simulator-agent-model.mjs);
//  - its buttons, including the one that opens the Signal generator panel;
//  - the field whose text goes to the screen as an instruction from the
//    serial line;
//  - the MCU port, which the serial line is connected to;
//  - the screen port, for a real screen beside the simulation. The field
//    can send that screen instructions too, and the MCU port can be joined
//    to it in place of the simulator;
//  - the GPIO pins, whose inputs a click sets.
// While none runs, it shows buttons that simulate the current project with
// the Simulator settings, from program.nx or from the page shown, run each
// launch configuration that simulates it, or create one.
import { glyphButton } from "./glyph-button.mjs";
import { pinRows } from "./gpio-pins-model.mjs";
import { agentLine } from "./simulator-agent-model.mjs";
import { bridgeControls } from "./simulator-bridge-model.mjs";

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
const destinations = document.getElementById("destinations");
const toSimulator = document.getElementById("to-simulator");
const toScreen = document.getElementById("to-screen");
document.getElementById("serial").addEventListener("submit", (event) => {
  event.preventDefault();
  // While no screen is connected, the instruction goes to the simulator.
  const to = destinations.hidden ? ["simulator"]
    : [...(toSimulator.checked ? ["simulator"] : []), ...(toScreen.checked ? ["screen"] : [])];
  if (field.value && to.length > 0) {
    vscode.postMessage({ type: "serial", text: field.value, to });
    field.select();
  }
});

// The choice of where the MCU port goes (showBridge).
const bridgeRow = document.getElementById("bridge-row");
const bridgeChoice = document.getElementById("bridge");
const sendButton = document.querySelector("#serial button[type=submit]");
bridgeChoice.addEventListener("change", () =>
  vscode.postMessage({ type: "bridge", choice: bridgeChoice.value }));

// Whether each port is connected, and whether the bridge joins the MCU port
// to the real screen, in place of the simulator.
let mcuConnected = false;
let screenConnected = false;
let bridged = false;
// While joined, whether the simulation "listens" or "answers" too, or null.
let simulator = null;

// The MCU port, which the simulation's serial line is connected to.
const mcuPort = portControls({
  portList: document.getElementById("port"),
  rateList: document.getElementById("rate"),
  connectButton: document.getElementById("connect"),
  stateLine: document.getElementById("port-state"),
  connectType: "connect", disconnectType: "disconnect",
  shown: (connected) => {
    mcuConnected = connected;
    showBridge();
  },
});

// The screen port, which a real screen beside the simulation is on. While
// it is connected, the field's instruction can go to the screen too, and the
// screen can be started again.
const screenStarts = document.getElementById("screen-starts");
const findButton = document.getElementById("screen-find");
findButton.title = "Finds the screen's rate and connects at it. Tries each rate by sending the "
  + "bytes that end protocol reparse mode, then the instruction \"connect\".";
const screenConnect = document.getElementById("screen-connect");
// Whether Find is still looking for the screen. It stops when the next screen
// state arrives.
let finding = false;
const screenPort = portControls({
  portList: document.getElementById("screen-port"),
  rateList: document.getElementById("screen-rate"),
  connectButton: screenConnect,
  stateLine: document.getElementById("screen-state"),
  connectType: "connectScreen", disconnectType: "disconnectScreen",
  shown: (connected) => {
    // Both boxes are ticked again each time a screen connects.
    if (connected && destinations.hidden) {
      toSimulator.checked = toScreen.checked = true;
    }
    destinations.hidden = !connected;
    screenStarts.hidden = !connected;
    screenConnected = connected;
    showBridge();
  },
});

// Shows the choice of where the MCU port goes, and enables or disables the
// controls the bridge affects (simulator-bridge-model.mjs). Called from the
// message handlers only, because it uses controls declared further down,
// such as `findButton`.
function showBridge() {
  const shown = bridgeControls({ bridged, simulator, mcuConnected, screenConnected, finding });
  bridgeRow.hidden = !shown.choiceShown;
  bridgeChoice.value = shown.choice;
  for (const control of [field, sendButton, toSimulator, toScreen]) {
    control.disabled = shown.typingDisabled;
  }
  for (const id of ["port", "rate", "screen-port", "screen-rate"]) {
    document.getElementById(id).disabled = shown.listsDisabled;
  }
  findButton.disabled = shown.findDisabled;
}

findButton.addEventListener("click", () => {
  const name = screenPort.chosenPort();
  if (name && !finding) {
    setFinding(true);
    screenPort.note(`Looking for a screen on ${name}…`);
    vscode.postMessage({ type: "findScreen", name });
  }
});

function setFinding(value) {
  finding = value;
  screenConnect.disabled = value;
  showBridge();
}
// The buttons that start the screen again work while the bridge runs too.
// A real screen can start again without the program on the MCU port
// knowing, and that program then receives the screen's start-up bytes.
document.getElementById("start-screen").addEventListener("click", () =>
  vscode.postMessage({ type: "startScreen" }));
document.getElementById("start-both").addEventListener("click", () =>
  vscode.postMessage({ type: "startBoth" }));

window.addEventListener("message", (event) => {
  const message = event.data;
  if (message.type === "ports") {
    bridged = message.bridged === true;
    simulator = message.simulator ?? null;
    mcuPort.offer(message.ports, message.rates, message.state);
    // While Find is looking, leave its "Looking for a screen" note in place
    // until Find answers.
    if (message.screen && !finding) {
      screenPort.offer(message.ports, message.rates, message.screen);
    }
  } else if (message.type === "portState") {
    mcuPort.show(message.state);
  } else if (message.type === "screenState") {
    setFinding(false);
    screenPort.show(message.state);
  } else if (message.type === "bridgeState") {
    bridged = message.bridged === true;
    simulator = message.simulator ?? null;
    showBridge();
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

// The controls of a serial port: its list of ports, its list of rates, its
// Connect button, and the line saying its state. The button posts
// `connectType` with the port and rate chosen, or `disconnectType` while
// connected. Each time it shows a state, it calls `shown(connected)`.
function portControls({ portList, rateList, connectButton, stateLine, connectType,
                        disconnectType, shown = () => {} }) {
  let connected = false;

  function connect() {
    if (portList.value) {
      vscode.postMessage({ type: connectType, name: portList.value,
                           baud: Number(rateList.value) });
    }
  }

  connectButton.addEventListener("click", () => {
    if (connected) {
      vscode.postMessage({ type: disconnectType });
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

  function show(state) {
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
    shown(connected);
  }

  return {
    show,
    // Lists the computer's ports and the rates. While not connected, what
    // the user picked stays picked.
    offer(ports, rates, state) {
      const kept = !state.connected;
      fill(portList, ports, (kept && portList.value) || state.name);
      fill(rateList, rates, (kept && rateList.value) || state.baud);
      show(state);
    },
    chosenPort: () => portList.value,
    // Shows `text` in place of the state, until the next state.
    note(text) {
      stateLine.classList.remove("problem");
      stateLine.textContent = text;
    },
  };
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
