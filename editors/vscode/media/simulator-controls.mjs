// The Simulator section of nxwright's side bar (src/simulator.ts).
// While a simulation runs, it shows:
//  - the line saying that an agent drives it, while one does
//    (simulator-agent-model.mjs);
//  - its buttons, including the one that opens the Signal generator panel;
//  - the field whose text goes to the screen as an instruction from the
//    serial line;
//  - the MCU port, which the serial line is connected to: none, a serial
//    port, or a program that listens at an address, over TCP
//    (simulator-port-model.mjs);
//  - the screen port, for a real screen beside the simulation. The field
//    can send that screen instructions too, and the MCU port can be joined
//    to it in place of the simulator;
//  - the GPIO pins, whose inputs a click sets.
// While none runs, it shows buttons that simulate the current project with
// the MCU port last chosen for it and the Simulator settings, from
// program.nx or from the page shown, run each launch configuration that
// simulates it, or create one.
import { glyphButton } from "./glyph-button.mjs";
import { pinRows } from "./gpio-pins-model.mjs";
import { agentLine } from "./simulator-agent-model.mjs";
import { bridgeControls } from "./simulator-bridge-model.mjs";
import { NONE, besideList, connectionOf, entryOfState, portOptions, serialName, stateLine }
  from "./simulator-port-model.mjs";

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
    `Simulate project starts the app from program.nx${fromPage}. A simulation started here ` +
    "uses the MCU port you last chose for this project, or else the serial port of the " +
    "Simulator settings. The SD cards' folders and the log's formats come from those " +
    "settings too. A launch configuration can give its own, and also the values a page " +
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

// The MCU port, which the simulation's serial line is connected to. Its
// list also has None and TCP. Choosing None posts "noPort".
const mcuPort = portControls({
  portList: document.getElementById("port"),
  rateList: document.getElementById("rate"),
  addressField: document.getElementById("address"),
  connectButton: document.getElementById("connect"),
  stateLine: document.getElementById("port-state"),
  connectType: "connect", disconnectType: "disconnect", noneType: "noPort",
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
  for (const id of ["port", "rate", "address", "screen-port", "screen-rate"]) {
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
    vscode.postMessage({ type: "connect", ...agentPort.connection });
  }
});

// The controls of a port: its list of ports, its list of rates, its Connect
// button, and the line saying its state (simulator-port-model.mjs). The
// button posts `connectType` with the port chosen, or `disconnectType` while
// connected. Each time the controls show a state, they call
// `shown(connected)`.
//
// Given `addressField` and `noneType`, as for the MCU port, the list also
// has None and TCP. TCP shows the field, for the address of the program to
// connect to, in place of the rates. Choosing None posts `noneType`.
function portControls({ portList, rateList, addressField, connectButton, stateLine: line,
                        connectType, disconnectType, noneType, shown = () => {} }) {
  const kinds = addressField !== undefined;
  let connected = false;
  // The serial ports last offered, which the list shows.
  let offered = [];

  // Posts the port chosen to connect. Returns false when there is none to
  // connect, as for TCP while its address is empty.
  function connect() {
    const port = connectionOf(portList.value, Number(rateList.value), addressField?.value);
    if (port) {
      vscode.postMessage({ type: connectType, ...port });
    }
    return port !== undefined;
  }

  // Shows the rates or the address field, whichever the port chosen has.
  // Connect is disabled while None is chosen and no port is connected,
  // because it would have nothing to connect.
  function showBeside() {
    const beside = besideList(portList.value);
    rateList.hidden = kinds && !beside.rateShown;
    if (addressField) {
      addressField.hidden = !beside.addressShown;
    }
    if (kinds) {
      connectButton.disabled = !connected && portList.value === NONE;
    }
  }

  connectButton.addEventListener("click", () => {
    if (connected) {
      vscode.postMessage({ type: disconnectType });
    } else {
      connect();
    }
  });

  portList.addEventListener("change", () => {
    showBeside();
    if (portList.value === NONE) {
      vscode.postMessage({ type: noneType });
    } else if (connected && !connect()) {
      // TCP has no address yet, and the port connected is no longer the one
      // chosen.
      vscode.postMessage({ type: disconnectType });
    }
  });

  // A change of rate or of address while connected applies at once.
  for (const control of [rateList, ...(addressField ? [addressField] : [])]) {
    control.addEventListener("change", () => {
      if (connected) {
        connect();
      }
    });
  }

  // Enter in the address field connects.
  addressField?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !connected) {
      connect();
    }
  });

  function show(state) {
    connected = state.connected;
    connectButton.textContent = connected ? "Disconnect" : "Connect";
    if (connected) {
      const entry = entryOfState(state);
      fillPorts(portList, portOptions(offered, kinds, entry), entry);
      fill(rateList, [...rateList.options].map((option) => option.value), state.baud);
    }
    // A program's address shows in the field: the one connected, or the one
    // that could not connect, unless the user has typed another.
    if (addressField && state.kind === "tcp" && state.name
        && (connected || !addressField.value)) {
      addressField.value = state.name;
    }
    const words = stateLine(state);
    line.classList.toggle("problem", words.problem);
    line.textContent = words.text;
    showBeside();
    shown(connected);
  }

  return {
    show,
    // Lists the computer's ports and the rates. While not connected, what
    // the user picked stays picked.
    offer(ports, rates, state) {
      const kept = !state.connected;
      offered = ports;
      const chosen = (kept && portList.value) || entryOfState(state);
      fillPorts(portList, portOptions(ports, kinds, chosen), chosen);
      fill(rateList, rates, (kept && rateList.value) || state.baud);
      show(state);
    },
    // The name of the serial port chosen, or undefined when none is.
    chosenPort: () => serialName(portList.value),
    // Shows `text` in place of the state, until the next state.
    note(text) {
      line.classList.remove("problem");
      line.textContent = text;
    },
  };
}

// Fills `list`, a list of ports, with `options`, each a value and a label
// (portOptions), and selects the entry `chosen`. Without one, the list's
// first option stays selected.
function fillPorts(list, options, chosen) {
  list.replaceChildren(...options.map((option) => new Option(option.label, option.value)));
  if (chosen) {
    list.value = chosen;
  }
}

// Fills `list` with `values`, `chosen` selected: kept even when it is not
// among them, such as a rate the launch configuration gives that the list
// does not have.
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
