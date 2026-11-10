// The page of the Waveform generator panel (src/waveGenerators.ts). The
// panel edits the generator that sends points to the running simulation's
// waveforms: which waveforms it feeds, which channels it sends to, and the
// wave on each channel.
// With "Same wave on every channel" ticked, one row of settings sets the
// wave for every channel. Otherwise each channel has a row of its own.
// Beside each row, a sketch draws the row's wave in one colour per channel,
// each channel a quarter cycle after the one before, the same way the
// generator sends them.
// Start starts the generator in the simulation. A setting changed while it
// runs is sent, and takes effect at the generator's next point. Save writes
// the generator to a settings file, and Open replaces it with the generator
// in a file.
// wave-generators-model.mjs keeps the panel's state and builds the settings
// it sends.
import { element } from "./elements.mjs";
import {
  channelCount, fileText, generatorOfSettings, newGenerator, NUMBER_SETTINGS, sameWaveform,
  setSame, settingsOf, settingsOfFileText, SHAPES, sketchLength, sketchValues, valuesOfCsv,
  valuesOfText,
} from "./wave-generators-model.mjs";

const vscode = acquireVsCodeApi();
const byId = (id) => document.getElementById(id);
const place = byId("generator");
const notice = byId("notice");
const run = byId("run");

// How long the running generator's settings must stay unchanged before
// they are sent, in ms, so that a number being typed is sent once.
const CHANGE_PAUSE = 250;
// The scope that names the wave every channel sends. A channel's own wave
// has the channel's number as its scope.
const COMMON = "common";
// The colour of each channel's line in the sketches, as VS Code's charts
// have them.
const CHANNEL_COLOURS = ["--vscode-charts-blue", "--vscode-charts-red",
                         "--vscode-charts-green", "--vscode-charts-yellow"];

// The app's waveforms, {page, waveform, channels}, and the panel's
// generator, once the simulation has said what it has.
let offered = [];
let generator;
// The change waiting to be sent, if any.
let change;

window.addEventListener("message", ({ data }) => {
  if (data.type === "state") {
    offered = data.waveforms;
    // A panel opened again shows the generator still running.
    if (generator === undefined) {
      generator = data.generator === null ? newGenerator(offered)
        : { ...generatorOfSettings(data.generator), running: true };
    }
    show();
  } else if (data.type === "started" || data.type === "stopped") {
    generator.running = data.type === "started";
    say("");
    show();
  } else if (data.type === "running") {
    // What the simulation says, after it refused something: the generator
    // may have been stopped or started from outside the panel. Before the
    // panel has its generator, there is nothing to show.
    if (generator !== undefined) {
      generator.running = data.running;
      show();
    }
  } else if (data.type === "changed") {
    say("");
  } else if (data.type === "refused" || data.type === "notice") {
    say(data.message);
  } else if (data.type === "opened") {
    open(data.text, data.name);
  } else if (data.type === "csvValues") {
    takeCsv(data);
  }
});

run.addEventListener("click", () => {
  if (generator.running) {
    cancelChange();
    vscode.postMessage({ type: "stop" });
    return;
  }
  const made = settingsOf(generator, offered);
  if (made.error !== undefined) {
    say(made.error);
  } else {
    vscode.postMessage({ type: "start", settings: made.settings });
  }
});
byId("open").addEventListener("click", () => vscode.postMessage({ type: "open" }));
byId("save").addEventListener("click", () => {
  const made = settingsOf(generator, offered);
  if (made.error !== undefined) {
    say(made.error);
  } else {
    say("");
    vscode.postMessage({ type: "save", text: fileText(made.settings) });
  }
});

// Says `message` under the toolbar, or nothing: what the generator needs
// first, or what the simulation refused of it.
function say(message) {
  notice.textContent = message;
}

// Takes the generator of a settings file's `text`, the file named `name`,
// in place of the panel's. While the generator runs, it goes on with the
// file's settings.
function open(text, name) {
  const read = settingsOfFileText(text);
  if (read.error !== undefined) {
    say(`${name}: ${read.error}`);
    return;
  }
  say("");
  generator = { ...generatorOfSettings(read.settings), running: generator.running };
  changed();
  show();
}

// Takes a custom wave's values from a CSV file's text, for the wave the
// file was asked for.
function takeCsv({ scope, text, name }) {
  const read = valuesOfCsv(text);
  if (read.error !== undefined) {
    say(`${name}: ${read.error}`);
    return;
  }
  say("");
  waveIn(scope).values = read.values;
  changed();
  show();
}

// The wave a scope names: the one every channel sends, or a channel's own.
function waveIn(scope) {
  return scope === COMMON ? generator.common : generator.channels[Number(scope)].wave;
}

// Shows the generator. The field with the focus keeps it, and its place in
// the text, since the page is built again around it.
function show() {
  const focused = document.activeElement?.dataset?.field;
  const selection = focused === undefined ? undefined
    : [document.activeElement.selectionStart, document.activeElement.selectionEnd];
  run.textContent = generator.running ? "Stop" : "Start";
  // Nothing to start, save, or replace in an app without a waveform.
  for (const button of [run, byId("open"), byId("save")]) {
    button.disabled = offered.length === 0;
  }
  byId("state").textContent = generator.running ? "Running" : "Stopped";
  byId("state").className = generator.running ? "state running" : "state";
  if (offered.length === 0) {
    place.replaceChildren(element("p", "hint", "This app has no waveform to send points to."));
  } else {
    place.replaceChildren(...parts());
  }
  if (focused !== undefined) {
    const again = place.querySelector(`[data-field="${focused}"]`);
    again?.focus();
    if (again !== null && selection[0] !== null) {
      try {
        again.setSelectionRange(...selection);
      } catch {
        // A number field has no selection to put back.
      }
    }
  }
}

// Returns the generator's parts: the waveforms it feeds, whether every
// channel sends the same wave, and its channels with their waves.
function parts() {
  const same = tickBox(" Same wave on every channel", generator.same, (ticked) => {
    setSame(generator, ticked);
    changed();
    show();
  });
  same.className = "same";
  const rows = generator.channels.slice(0, channelCount(generator.waveforms, offered));
  const table = element("table");
  table.append(headings());
  if (!generator.same) {
    for (const row of rows) {
      const first = element("td", "name");
      first.append(channelBox(row, `Channel ${row.channel}`));
      table.append(waveRows(String(row.channel), first, row.on));
    }
    return [waveformChoices(), same, table];
  }
  const channels = element("div", "channels");
  channels.append(element("span", "label", "Channels"));
  for (const row of rows) {
    channels.append(channelBox(row, String(row.channel)));
  }
  table.append(waveRows(COMMON, element("td", "name")));
  return [waveformChoices(), same, channels, table];
}

// Returns the boxes that choose the generator's waveforms: the app's, and
// any the generator names that the app does not have, as a file may give.
function waveformChoices() {
  const choices = element("div", "waveforms");
  choices.append(element("span", "label", "Sends to"));
  const missing = generator.waveforms.filter(
    (name) => !offered.some((other) => sameWaveform(other, name)));
  for (const waveform of [...offered, ...missing]) {
    const known = "channels" in waveform;
    const label = tickBox(` ${waveform.waveform} of ${waveform.page}` +
                          (known ? "" : " (not in this app)"),
                          generator.waveforms.some((name) => sameWaveform(name, waveform)),
                          (ticked) => {
                            generator.waveforms = ticked
                              ? [...generator.waveforms,
                                 { page: waveform.page, waveform: waveform.waveform }]
                              : generator.waveforms.filter(
                                (name) => !sameWaveform(name, waveform));
                            changed();
                            show();
                          });
    label.className = known ? "" : "missing";
    choices.append(label);
  }
  return choices;
}

// Returns the box that turns a channel on or off, named `name`.
function channelBox(row, name) {
  return tickBox(` ${name}`, row.on, (ticked) => {
    row.on = ticked;
    changed();
    show();
  });
}

// Returns a box to tick with `text` after it. `take(ticked)` is called as
// it changes.
function tickBox(text, ticked, take) {
  const box = element("input");
  box.type = "checkbox";
  box.checked = ticked;
  box.addEventListener("change", () => take(box.checked));
  const label = element("label");
  label.append(box, text);
  return label;
}

function headings() {
  const row = element("tr");
  row.append(element("th"), element("th", "", "Shape"));
  for (const setting of NUMBER_SETTINGS) {
    const heading = element("th", "", setting.label);
    heading.title = setting.title;
    row.append(heading);
  }
  row.append(element("th", "", "Wave"));
  return row;
}

// Returns the row of a wave's settings, the wave `scope` names: its first
// cell `first`, its shape, its numbers, and the sketch of the wave, dimmed
// when `on` is false, as a channel turned off. A custom wave's values
// follow in a row of their own.
function waveRows(scope, first, on = true) {
  const wave = waveIn(scope);
  const row = element("tr", on ? "" : "off");
  row.append(first);

  const shape = element("select");
  shape.dataset.field = `${scope} shape`;
  for (const [id, label] of SHAPES) {
    const option = element("option", "", label);
    option.value = id;
    shape.append(option);
  }
  shape.value = wave.shape;
  shape.addEventListener("change", () => {
    wave.shape = shape.value;
    changed();
    show();
  });
  const shapeCell = element("td");
  shapeCell.append(shape);
  row.append(shapeCell);

  for (const setting of NUMBER_SETTINGS) {
    const cell = element("td");
    cell.append(numberField(`${scope} ${setting.key}`, wave[setting.key], setting, (value) => {
      wave[setting.key] = value;
      changed();
      redraw();
    }));
    row.append(cell);
  }

  const sketch = element("canvas", "sketch");
  sketch.width = 120;
  sketch.height = 32;
  sketch.dataset.sketch = scope;
  const sketchCell = element("td");
  sketchCell.append(sketch);
  row.append(sketchCell);
  queueMicrotask(() => draw(sketch, scope));

  if (wave.shape !== "custom") {
    return row;
  }
  const rows = document.createDocumentFragment();
  rows.append(row, valuesRow(scope, wave, on));
  return rows;
}

// Returns the row of a custom wave's values: a field to type them in, and
// a button that reads them from a CSV file.
function valuesRow(scope, wave, on) {
  const row = element("tr", on ? "values" : "values off");
  const cell = element("td");
  cell.colSpan = NUMBER_SETTINGS.length + 3;
  const field = element("input");
  field.type = "text";
  field.dataset.field = `${scope} values`;
  field.value = wave.values.join(", ");
  field.placeholder = "The wave's values, from 0 to 255, such as 10, 20, 30";
  field.title = "The values the wave plays in a loop, one for each point";
  field.addEventListener("change", () => {
    const read = valuesOfText(field.value);
    if (read.error !== undefined) {
      say(read.error);
    } else {
      say("");
      wave.values = read.values;
      changed();
    }
    show();
  });
  const label = element("label", "", "Values ");
  label.append(field);
  const fromFile = element("button", "secondary", "From a CSV file…");
  fromFile.addEventListener("click", () => vscode.postMessage({ type: "csv", scope }));
  cell.append(label, fromFile);
  row.append(cell);
  return row;
}

// Returns a field for a whole number, `value`, named `name`, of a setting
// that takes the values from `low` to `high`. `take(number)` is called as
// it changes to such a number. The field keeps its number until another is
// typed: an empty one, or one out of range, is marked and not taken.
function numberField(name, value, { low, high, title }, take) {
  const field = element("input");
  field.type = "number";
  field.dataset.field = name;
  field.title = title;
  field.required = true;
  field.min = String(low);
  if (high !== undefined) {
    field.max = String(high);
  }
  field.value = String(value);
  field.addEventListener("input", () => {
    if (field.validity.valid && Number.isInteger(field.valueAsNumber)) {
      take(field.valueAsNumber);
    }
  });
  return field;
}

// Draws each sketch again, as a number changed: the fields stay as they
// are, so that typing goes on.
function redraw() {
  for (const sketch of place.querySelectorAll("canvas[data-sketch]")) {
    draw(sketch, sketch.dataset.sketch);
  }
}

// Draws the sketch of the wave `scope` names: two of its cycles, the values
// from 0 at the bottom to 255 at the top, a line in its colour for each
// channel that sends it. The wave every channel sends is drawn for each
// channel turned on, or for channel 0 when none is.
function draw(sketch, scope) {
  const wave = waveIn(scope);
  let channels = [Number(scope)];
  if (scope === COMMON) {
    const count = channelCount(generator.waveforms, offered);
    channels = generator.channels.filter((row) => row.on && row.channel < count)
      .map((row) => row.channel);
    if (channels.length === 0) {
      channels = [0];
    }
  }
  const context = sketch.getContext("2d");
  const { width, height } = sketch;
  context.clearRect(0, 0, width, height);
  const styles = getComputedStyle(document.documentElement);
  for (const channel of channels) {
    const values = sketchValues(wave, sketchLength(wave), channel);
    context.strokeStyle = styles.getPropertyValue(CHANNEL_COLOURS[channel]).trim() ||
      getComputedStyle(sketch).color;
    context.lineWidth = 1;
    context.beginPath();
    values.forEach((value, point) => {
      const x = 0.5 + point * (width - 1) / Math.max(values.length - 1, 1);
      const y = 0.5 + (height - 1) * (1 - value / 255);
      if (point === 0) {
        context.moveTo(x, y);
      } else {
        context.lineTo(x, y);
      }
    });
    context.stroke();
  }
}

// A setting of the generator changed: while it runs, its new settings are
// sent once they have stayed unchanged for CHANGE_PAUSE.
function changed() {
  if (!generator.running) {
    return;
  }
  cancelChange();
  change = setTimeout(() => {
    change = undefined;
    const made = settingsOf(generator, offered);
    if (made.error !== undefined) {
      say(`${made.error} The generator keeps its previous settings.`);
    } else if (generator.running) {
      vscode.postMessage({ type: "change", settings: made.settings });
    }
  }, CHANGE_PAUSE);
}

function cancelChange() {
  clearTimeout(change);
  change = undefined;
}

vscode.postMessage({ type: "ready" });
