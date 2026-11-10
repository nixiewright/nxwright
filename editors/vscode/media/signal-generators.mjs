// The page of the Signal generator panel (src/signalGenerators.ts). The
// panel lists the generators that send values to the running simulation,
// one block for each. Each block has its own Start or Stop button, and
// "Start all" and "Stop all" act on every generator.
//
// A waveform generator sends points to the simulation's waveforms. In its
// block, the user chooses the waveforms it feeds, the channels it sends to,
// and the wave on each channel. With "Same wave on every channel" ticked,
// one row of settings sets the wave for every channel. Otherwise each
// channel has a row of its own. Beside each row, a sketch draws the row's
// wave in one colour per channel, each channel a quarter cycle after the
// one before, the same way the generator sends them.
//
// A value generator sends instructions that carry its wave's value. In its
// block, the user types the instructions, one on each line, and sets its
// wave. Under the wave, the block lists the generator's conditions. For
// each one, the user sets the level that turns its switch on, the level
// that turns it off, and the instructions to send at each change.
//
// A setting changed while its generator runs is sent to the simulation,
// and takes effect at the generator's next point. Save writes every
// generator to one settings file, and Open replaces the panel's generators
// with those of a file.
//
// signal-generators-model.mjs keeps the panel's state and builds the
// settings that the page sends.
import { element } from "./elements.mjs";
import {
  channelCount, fileText, generatorOfSettings, generatorsOfRunning, isRunning, levelBounds,
  markStopped, newCondition, newGenerator, newValueGenerator, numberSettings, sameWaveform,
  setSame, settingsOf,
  settingsOfAll, settingsOfFileText, SHAPES, sketchLength, sketchSpan, sketchValues, VALUE,
  valuesOfCsv, valuesOfText,
} from "./signal-generators-model.mjs";

const vscode = acquireVsCodeApi();
const byId = (id) => document.getElementById(id);
const place = byId("generators");

// How long a running generator's settings must stay unchanged before they
// are sent, in ms, so that a number being typed is sent once.
const CHANGE_PAUSE = 250;
// The scope that names the wave every channel of a waveform generator
// sends. A channel's own wave has the channel's number as its scope. A value
// generator's one wave has the scope WAVE.
const COMMON = "common";
const WAVE = "wave";
// The colour of each channel's line in the sketches, as VS Code's charts
// have them.
const CHANNEL_COLOURS = ["--vscode-charts-blue", "--vscode-charts-red",
                         "--vscode-charts-green", "--vscode-charts-yellow"];

// The app's waveforms, {page, waveform, channels}, and the panel's
// generators, once the simulation has said what it has. Each generator has
// a `key`, which identifies it in the page's fields and in the messages
// about it. A generator gets its key when the panel adds it, but its
// number only when it starts.
let offered = [];
let generators;
let lastKey = 0;
// The change of settings waiting to be sent, and the settings a generator
// was last started with, as text, each by its generator's key.
const changes = new Map();
const startedWith = new Map();

window.addEventListener("message", ({ data }) => {
  if (data.type === "state") {
    offered = data.waveforms;
    if (generators === undefined) {
      // A panel opened while generators run shows them. If none runs and
      // the app has a waveform, the panel starts with one new generator to
      // set up.
      const running = generatorsOfRunning(data.generators);
      generators = (running.length > 0 || offered.length === 0 ? running
        : [newGenerator(offered)]).map(keyed);
    }
    show();
    return;
  }
  if (generators === undefined) {
    // The simulation never sent its waveforms, so the only thing to show is
    // why.
    if (data.type === "refused") {
      say(data.message);
    }
    return;
  }
  const generator = generators.find((one) => one.key === data.key);
  if (data.type === "started") {
    started(generator, data.number);
    show();
  } else if (data.type === "stopped") {
    if (generator !== undefined) {
      Object.assign(generator, { number: null, waiting: false, notice: "" });
    }
    show();
  } else if (data.type === "changed") {
    // The page is left as it is, so that typing goes on.
    if (generator !== undefined) {
      tell(generator, "");
    }
  } else if (data.type === "refused") {
    if (generator === undefined) {
      say(data.message);
    } else {
      Object.assign(generator, { waiting: false, notice: data.message });
    }
    show();
  } else if (data.type === "running") {
    // After a refusal, the simulation's list of running generators comes
    // in, because a generator may have been stopped from outside the panel.
    markStopped(generators, data.generators);
    show();
  } else if (data.type === "opened") {
    open(data.text, data.name);
    show();
  } else if (data.type === "csvValues") {
    if (generator !== undefined) {
      takeCsv(generator, data);
      show();
    }
  }
});

byId("add-waveform").addEventListener("click", () => {
  generators.push(keyed(newGenerator(offered)));
  say("");
  show();
});
byId("add-value").addEventListener("click", () => {
  generators.push(keyed(newValueGenerator()));
  say("");
  show();
});
byId("start-all").addEventListener("click", () => {
  for (const generator of generators.filter((one) => !isRunning(one) && !one.waiting)) {
    start(generator);
  }
  show();
});
byId("stop-all").addEventListener("click", () => {
  for (const generator of generators.filter((one) => isRunning(one) && !one.waiting)) {
    stop(generator);
  }
  show();
});
byId("open").addEventListener("click", () => vscode.postMessage({ type: "open" }));
byId("save").addEventListener("click", () => {
  const made = settingsOfAll(generators, offered);
  if (made.error !== undefined) {
    say(made.error);
  } else {
    say("");
    vscode.postMessage({ type: "save", text: fileText(made.settings) });
  }
});

// Returns `generator` with a key of its own.
function keyed(generator) {
  lastKey += 1;
  return { ...generator, key: lastKey };
}

// Shows `message` under the toolbar, or clears it when `message` is empty.
// This notice is for a problem with a file, or a refusal that belongs to no
// generator in the panel.
function say(message) {
  byId("notice").textContent = message;
}

// Says `message` in a generator's block, or nothing, leaving the rest of
// the page as it is.
function tell(generator, message) {
  generator.notice = message;
  const shown = place.querySelector(`[data-notice="${generator.key}"]`);
  if (shown !== null) {
    shown.textContent = message;
  }
}

// Asks the simulation to start `generator`, if it has what it needs.
function start(generator) {
  const made = settingsOf(generator, offered);
  if (made.error !== undefined) {
    generator.notice = made.error;
    return;
  }
  Object.assign(generator, { waiting: true, notice: "" });
  startedWith.set(generator.key, JSON.stringify(made.settings));
  vscode.postMessage({ type: "start", key: generator.key, settings: made.settings });
}

// The simulation started a generator, as `number`.
function started(generator, number) {
  if (generator === undefined) {
    // The generator was removed from the panel while it started, so it is
    // stopped again.
    vscode.postMessage({ type: "stop", number });
    return;
  }
  Object.assign(generator, { number, waiting: false, notice: "" });
  // Settings changed while it started are sent now.
  const made = settingsOf(generator, offered);
  if (made.error !== undefined ||
      JSON.stringify(made.settings) !== startedWith.get(generator.key)) {
    changed(generator);
  }
}

// Asks the simulation to stop `generator`, which runs.
function stop(generator) {
  cancelChange(generator);
  generator.waiting = true;
  vscode.postMessage({ type: "stop", key: generator.key, number: generator.number });
}

// Takes `generator` out of the panel, and stops it first if it runs.
function remove(generator) {
  if (isRunning(generator) && !generator.waiting) {
    stop(generator);
  }
  startedWith.delete(generator.key);
  generators = generators.filter((one) => one !== generator);
}

// Takes the generators of a settings file's `text`, the file named `name`,
// in place of the panel's. Those running are stopped first.
function open(text, name) {
  const read = settingsOfFileText(text);
  if (read.error !== undefined) {
    say(`${name}: ${read.error}`);
    return;
  }
  say("");
  for (const generator of generators) {
    remove(generator);
  }
  generators = read.settings.map((settings) => keyed(generatorOfSettings(settings)));
}

// Takes a custom wave's values from a CSV file's text, for the wave of
// `generator` the file was asked for.
function takeCsv(generator, { scope, text, name }) {
  const read = valuesOfCsv(text, generator.kind);
  if (read.error !== undefined) {
    generator.notice = `${name}: ${read.error}`;
    return;
  }
  generator.notice = "";
  waveIn(generator, scope).values = read.values;
  changed(generator);
}

// The wave a scope names: a value generator's one wave, the wave every
// channel of a waveform generator sends, or a channel's own.
function waveIn(generator, scope) {
  if (scope === WAVE) {
    return generator.wave;
  }
  return scope === COMMON ? generator.common : generator.channels[Number(scope)].wave;
}

// Shows the generators. The field with the focus keeps it, and its place in
// the text, since the page is built again around it.
function show() {
  const focused = document.activeElement?.dataset?.field;
  const selection = focused === undefined ? undefined
    : [document.activeElement.selectionStart, document.activeElement.selectionEnd];
  // A waveform generator has nothing to feed in an app without a waveform.
  byId("add-waveform").disabled = offered.length === 0;
  byId("add-hint").textContent = offered.length === 0
    ? "This app has no waveform to send points to." : "";
  byId("add-value").disabled = false;
  byId("start-all").disabled = !generators.some((one) => !isRunning(one) && !one.waiting);
  byId("stop-all").disabled = !generators.some((one) => isRunning(one) && !one.waiting);
  // A file can be opened once the simulation has said what it has.
  byId("open").disabled = false;
  byId("save").disabled = generators.length === 0;
  place.replaceChildren(...generators.map(block));
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

// Returns a generator's block: its Start or Stop, whether it runs, Remove,
// what it needs or what the simulation refused of it, then its settings.
function block(generator) {
  const running = isRunning(generator);
  const run = element("button", "run", running ? "Stop" : "Start");
  run.disabled = generator.waiting;
  run.addEventListener("click", () => {
    if (running) {
      stop(generator);
    } else {
      start(generator);
    }
    show();
  });
  // The log identifies the generator by this number.
  const state = element("span", running ? "state running" : "state",
                        running ? `Running, as generator ${generator.number}` : "Stopped");
  const removal = element("button", "secondary", "Remove");
  removal.addEventListener("click", () => {
    remove(generator);
    show();
  });
  const value = generator.kind === VALUE;
  const head = element("div", "head");
  head.append(element("span", "title", value ? "Value generator" : "Waveform generator"),
              run, state, removal);
  const notice = element("p", "problem", generator.notice);
  notice.dataset.notice = String(generator.key);
  const made = element("section", "generator");
  made.append(head, notice, ...(value ? valueParts(generator) : waveformParts(generator)));
  return made;
}

// Returns a value generator's parts: the instructions it sends, whether it
// sends them only when its value changes, its wave, and its conditions.
function valueParts(generator) {
  const sends = instructionsField(
    generator, "send", "Sends", generator.send, "temp.val={value}",
    "The instructions sent at each point, one on each line, in strict Nextion syntax. " +
    "{value} stands for the wave's value.",
    (text) => {
      generator.send = text;
    });
  const only = tickBox(" Only when the value changes", generator.onlyWhenChanged, (ticked) => {
    generator.onlyWhenChanged = ticked;
    changed(generator);
    show();
  });
  only.className = "same";
  const table = element("table");
  table.append(headings(VALUE), waveRows(generator, WAVE, element("td", "name")));
  const add = element("button", "secondary", "Add condition");
  add.addEventListener("click", () => {
    generator.conditions.push(newCondition());
    changed(generator);
    show();
  });
  return [sends, only, table,
          ...generator.conditions.map((condition, index) => conditionPart(generator, index)),
          add];
}

// Returns a field for instructions, one on each line, labelled `label`. It
// is named `name` among the fields of `generator`, starts with `text`, and
// shows `example` while empty. `take(text)` is called as the user types.
function instructionsField(generator, name, label, text, example, title, take) {
  const field = element("textarea");
  field.dataset.field = `${generator.key} ${name}`;
  field.rows = Math.max(text.split("\n").length, 2);
  field.value = text;
  field.placeholder = example;
  field.title = title;
  field.addEventListener("input", () => {
    take(field.value);
    changed(generator);
  });
  const labelled = element("label", "send", label);
  labelled.append(field);
  return labelled;
}

// Returns the part of a value generator's condition `index`: the levels
// that turn its switch on and off, how long the value must stay past a
// level, the instructions sent at each change, and Remove.
function conditionPart(generator, index) {
  const condition = generator.conditions[index];
  const named = `${generator.key} condition ${index}`;
  const direction = element("select");
  direction.dataset.field = `${named} direction`;
  for (const side of ["above", "below"]) {
    const option = element("option", "", side);
    option.value = side;
    direction.append(option);
  }
  direction.value = condition.above ? "above" : "below";
  direction.addEventListener("change", () => {
    condition.above = direction.value === "above";
    changed(generator);
    show();
  });
  const bounds = levelBounds();
  const level = numberField(`${named} level`, condition.level, {
    ...bounds, title: "The level the value must go past for the switch to turn on",
  }, (value) => {
    condition.level = value;
    changed(generator);
  });
  const back = numberField(`${named} back`, condition.back, {
    ...bounds, optional: true,
    title: "The level the value must come back past for the switch to turn off. If you " +
      "leave it empty, the switch turns off as soon as the value is no longer past the " +
      "first level.",
  }, (value) => {
    condition.back = value;
    changed(generator);
  });
  const after = numberField(`${named} after`, condition.after, {
    low: 0, title: "How long the value must stay past a level before the switch changes",
  }, (value) => {
    condition.after = value;
    changed(generator);
  });
  const removal = element("button", "secondary", "Remove");
  removal.addEventListener("click", () => {
    generator.conditions.splice(index, 1);
    changed(generator);
    show();
  });
  const levels = element("div", "levels");
  levels.append(element("span", "title", `Condition ${index + 1}`), "turns on", direction,
                level, condition.above ? "and off below" : "and off above", back,
                "each time after", after, "ms", removal);
  const made = element("div", "condition");
  made.append(
    levels,
    instructionsField(generator, `condition ${index} whenOn`, "When on, sends",
                      condition.whenOn, "click alarm,1",
                      "The instructions sent when the switch turns on, one on each line",
                      (text) => {
                        condition.whenOn = text;
                      }),
    instructionsField(generator, `condition ${index} whenOff`, "When off, sends",
                      condition.whenOff, "click alarm,0",
                      "The instructions sent when the switch turns off, one on each line",
                      (text) => {
                        condition.whenOff = text;
                      }));
  return made;
}

// Returns a waveform generator's parts: the waveforms it feeds, whether
// every channel sends the same wave, and its channels with their waves.
function waveformParts(generator) {
  const same = tickBox(" Same wave on every channel", generator.same, (ticked) => {
    setSame(generator, ticked);
    changed(generator);
    show();
  });
  same.className = "same";
  const rows = generator.channels.slice(0, channelCount(generator.waveforms, offered));
  const table = element("table");
  table.append(headings(generator.kind));
  if (!generator.same) {
    for (const row of rows) {
      const first = element("td", "name");
      first.append(channelBox(generator, row, `Channel ${row.channel}`));
      table.append(waveRows(generator, String(row.channel), first, row.on));
    }
    return [waveformChoices(generator), same, table];
  }
  const channels = element("div", "channels");
  channels.append(element("span", "label", "Channels"));
  for (const row of rows) {
    channels.append(channelBox(generator, row, String(row.channel)));
  }
  table.append(waveRows(generator, COMMON, element("td", "name")));
  return [waveformChoices(generator), same, channels, table];
}

// Returns the boxes that choose a generator's waveforms: the app's, and any
// the generator names that the app does not have, as a file may give.
function waveformChoices(generator) {
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
                            changed(generator);
                            show();
                          });
    label.className = known ? "" : "missing";
    choices.append(label);
  }
  return choices;
}

// Returns the box that turns a channel on or off, named `name`.
function channelBox(generator, row, name) {
  return tickBox(` ${name}`, row.on, (ticked) => {
    row.on = ticked;
    changed(generator);
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

// Returns the headings of the table of waves of a generator of `kind`.
function headings(kind) {
  const row = element("tr");
  row.append(element("th"), element("th", "", "Shape"));
  for (const setting of numberSettings(kind)) {
    const heading = element("th", "", setting.label);
    heading.title = setting.title;
    row.append(heading);
  }
  row.append(element("th", "", "Wave"));
  return row;
}

// Returns the row of a wave's settings, the wave of `generator` that
// `scope` names: its first cell `first`, its shape, its numbers, and the
// sketch of the wave, dimmed when `on` is false, as a channel turned off. A
// custom wave's values follow in a row of their own.
function waveRows(generator, scope, first, on = true) {
  const wave = waveIn(generator, scope);
  const named = `${generator.key} ${scope}`;
  const row = element("tr", on ? "" : "off");
  row.append(first);

  const shape = element("select");
  shape.dataset.field = `${named} shape`;
  for (const [id, label] of SHAPES) {
    const option = element("option", "", label);
    option.value = id;
    shape.append(option);
  }
  shape.value = wave.shape;
  shape.addEventListener("change", () => {
    wave.shape = shape.value;
    changed(generator);
    show();
  });
  const shapeCell = element("td");
  shapeCell.append(shape);
  row.append(shapeCell);

  for (const setting of numberSettings(generator.kind)) {
    const cell = element("td");
    cell.append(numberField(`${named} ${setting.key}`, wave[setting.key], setting, (value) => {
      wave[setting.key] = value;
      changed(generator);
      redraw();
    }));
    row.append(cell);
  }

  const sketch = element("canvas", "sketch");
  sketch.width = 120;
  sketch.height = 32;
  sketch.dataset.generator = String(generator.key);
  sketch.dataset.sketch = scope;
  const sketchCell = element("td");
  sketchCell.append(sketch);
  row.append(sketchCell);
  queueMicrotask(() => draw(sketch, generator, scope));

  if (wave.shape !== "custom") {
    return row;
  }
  const rows = document.createDocumentFragment();
  rows.append(row, valuesRow(generator, scope, wave, on));
  return rows;
}

// Returns the row of a custom wave's values: a field to type them in, and
// a button that reads them from a CSV file.
function valuesRow(generator, scope, wave, on) {
  const row = element("tr", on ? "values" : "values off");
  const cell = element("td");
  cell.colSpan = numberSettings(generator.kind).length + 3;
  const field = element("input");
  field.type = "text";
  field.dataset.field = `${generator.key} ${scope} values`;
  field.value = wave.values.join(", ");
  field.placeholder = "The wave's values, such as 10, 20, 30";
  field.title = "The values the wave plays in a loop, one for each point";
  field.addEventListener("change", () => {
    const read = valuesOfText(field.value, generator.kind);
    if (read.error !== undefined) {
      generator.notice = read.error;
    } else {
      generator.notice = "";
      wave.values = read.values;
      changed(generator);
    }
    show();
  });
  const label = element("label", "", "Values ");
  label.append(field);
  const fromFile = element("button", "secondary", "From a CSV file…");
  fromFile.addEventListener("click", () => vscode.postMessage(
    { type: "csv", key: generator.key, scope }));
  cell.append(label, fromFile);
  row.append(cell);
  return row;
}

// Returns a field named `name` for a whole-number setting that takes the
// values from `low` to `high`, and starts at `value`. Each time the user
// types a number in that range, the field calls `take(number)`. If the user
// empties the field, or types a number out of range, the field is marked
// and `take` is not called, so the setting keeps its last number. If
// `optional` is true, the field may be empty: `value` can then be null,
// and emptying the field calls `take(null)`.
function numberField(name, value, { low, high, title, optional = false }, take) {
  const field = element("input");
  field.type = "number";
  field.dataset.field = name;
  field.title = title;
  field.required = !optional;
  field.min = String(low);
  if (high !== undefined) {
    field.max = String(high);
  }
  field.value = value === null ? "" : String(value);
  field.addEventListener("input", () => {
    if (optional && field.value === "" && field.validity.valid) {
      take(null);
    } else if (field.validity.valid && Number.isInteger(field.valueAsNumber)) {
      take(field.valueAsNumber);
    }
  });
  return field;
}

// Draws each sketch again, as a number changed: the fields stay as they
// are, so that typing goes on.
function redraw() {
  for (const sketch of place.querySelectorAll("canvas[data-sketch]")) {
    const generator = generators.find((one) => String(one.key) === sketch.dataset.generator);
    draw(sketch, generator, sketch.dataset.sketch);
  }
}

// Draws the sketch of the wave of `generator` that `scope` names: two of
// its cycles, one line for each channel that sends it, in the channel's
// colour. The wave every channel sends is drawn for each channel turned on,
// or for channel 0 when none is. A value generator's wave is drawn in
// channel 0's colour. The sketch's height spans the values sketchSpan gives
// for the generator's kind.
function draw(sketch, generator, scope) {
  const wave = waveIn(generator, scope);
  let channels = [scope === WAVE ? 0 : Number(scope)];
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
    const values = sketchValues(wave, sketchLength(wave), channel, generator.kind);
    const [lowest, highest] = sketchSpan(generator.kind, values);
    context.strokeStyle = styles.getPropertyValue(CHANNEL_COLOURS[channel]).trim() ||
      getComputedStyle(sketch).color;
    context.lineWidth = 1;
    context.beginPath();
    values.forEach((value, point) => {
      const x = 0.5 + point * (width - 1) / Math.max(values.length - 1, 1);
      const y = 0.5 + (height - 1) * (1 - (value - lowest) / (highest - lowest));
      if (point === 0) {
        context.moveTo(x, y);
      } else {
        context.lineTo(x, y);
      }
    });
    context.stroke();
  }
}

// A setting of `generator` changed: while it runs, its new settings are
// sent once they have stayed unchanged for CHANGE_PAUSE.
function changed(generator) {
  if (!isRunning(generator)) {
    return;
  }
  cancelChange(generator);
  changes.set(generator.key, setTimeout(() => {
    changes.delete(generator.key);
    const made = settingsOf(generator, offered);
    if (made.error !== undefined) {
      tell(generator, `${made.error} The generator keeps its previous settings.`);
    } else if (isRunning(generator)) {
      vscode.postMessage({ type: "change", key: generator.key, number: generator.number,
                           settings: made.settings });
    }
  }, CHANGE_PAUSE));
}

function cancelChange(generator) {
  clearTimeout(changes.get(generator.key));
  changes.delete(generator.key);
}

vscode.postMessage({ type: "ready" });
