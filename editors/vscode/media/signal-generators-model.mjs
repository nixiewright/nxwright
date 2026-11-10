// The logic of the Signal generator panel (signal-generators.mjs), kept
// apart from the page so that Node's test runner can check it
// (test/signal-generators-model.test.mjs). It covers what the panel keeps
// for each generator, the settings the panel sends to the simulation and
// writes to a file, the values of a custom wave typed or read from a CSV
// file, and the sketch of a wave.
//
// The settings have the form of a generator in a settings file, which
// nxwright/testing/signal_generators.py checks. A waveform generator's
// settings are {kind: "waveform", waveforms: [{page, waveform}], channels:
// [{channel, ...}], and a wave's settings}. In a file, the generator's own
// wave settings are shared by its channels, and a channel gives only the
// settings it changes.
//
// The panel does not show this sharing. Either the generator sends the
// same wave on every channel, or each channel has its own wave. The panel
// keeps a waveform generator as {kind, waveforms, same, common, channels,
// number, waiting, notice}:
//  - `same`: whether every channel sends the same wave;
//  - `common`: that wave, with every setting given;
//  - `channels`: a row {channel, on, wave} for each channel a waveform can
//    have, where `wave` is the channel's own wave, with every setting
//    given, which it sends when `same` is false;
//  - `number`: the number the simulation gave the generator when it
//    started, or null while it does not run;
//  - `waiting`: whether a start or a stop asked of the simulation has not
//    been answered yet;
//  - `notice`: what the generator needs before it can start, or what the
//    simulation refused of it.
//
// A value generator's settings are {kind: "value", send: [instruction],
// onlyWhenChanged, a wave's settings, and conditions: [condition]}. The
// panel keeps one as {kind, send, onlyWhenChanged, wave, conditions, number,
// waiting, notice}, where `send` is the text of its instructions, one on
// each line, and `wave` is its wave, with every setting given.
//
// A condition is a switch that the wave's value turns on and off. Its
// settings are {turnsOnAbove or turnsOnBelow, turnsOffBelow or
// turnsOffAbove, afterMs, whenOn: [instruction], whenOff: [instruction]}.
// The panel keeps one as {above, level, back, after, whenOn, whenOff}:
//  - `above`: whether the switch turns on above its level, or below it;
//  - `level`: the level that turns it on;
//  - `back`: the level that turns it off, or null when the switch turns off
//    as soon as the value is no longer past `level`;
//  - `after`: the milliseconds the value must stay past a level before the
//    switch changes;
//  - `whenOn` and `whenOff`: the text of the instructions sent at each
//    change, one on each line.

// The kind of a generator that sends points to waveforms, and the kind of
// one that sends instructions carrying its wave's value.
export const WAVEFORM = "waveform";
export const VALUE = "value";
// The lowest and the highest value a generator of each kind sends. They
// match _BOUNDS in signal_generators.py.
const BOUNDS = { [WAVEFORM]: [0, 255], [VALUE]: [-2147483648, 2147483647] };

// The wave shapes, each with the name the panel shows.
export const SHAPES = [
  ["sine", "Sine"], ["square", "Square"], ["triangle", "Triangle"], ["sawtooth", "Sawtooth"],
  ["inverted-sawtooth", "Inverted sawtooth"], ["pulse", "Pulse"], ["random", "Random"],
  ["custom", "Custom"],
];

// A wave's settings when neither the generator nor its channel gives them,
// as signal_generators.py has them.
export const WAVE_DEFAULTS = {
  shape: "sine", minimum: 0, maximum: 100, interval: 50, period: 50, duty: 50, noise: 0,
  values: [],
};

// Returns the settings of a wave that are whole numbers, for a generator of
// `kind`, in the order the panel shows them. Each has its label, the range
// of values it takes, and the tooltip that describes it.
export function numberSettings(kind) {
  const [lowest, highest] = BOUNDS[kind];
  return [
    { key: "minimum", label: "Min", low: lowest, high: highest,
      title: "The wave's lowest value" },
    { key: "maximum", label: "Max", low: lowest, high: highest,
      title: "The wave's highest value" },
    { key: "interval", label: "Interval (ms)", low: 1,
      title: "Milliseconds between two points" },
    { key: "period", label: "Period (points)", low: 1,
      title: "Points in one cycle of the wave" },
    { key: "duty", label: "Duty (%)", low: 0, high: 100,
      title: "For a pulse: the percentage of the cycle at the highest value" },
    { key: "noise", label: "Noise", low: 0, high: highest,
      title: "The most that is added to or taken from each point, at random" },
  ];
}

// The most channels a waveform has.
export const MOST_CHANNELS = 4;
const WAVE_KEYS = Object.keys(WAVE_DEFAULTS);
// The run fields of a generator that the simulation is not running.
const NOT_RUNNING = { number: null, waiting: false, notice: "" };

// Returns a new waveform generator for the panel: a sine wave on channel 0
// of the first waveform of `offered`, the app's waveforms, if it has one.
export function newGenerator(offered) {
  return {
    kind: WAVEFORM,
    waveforms: offered.slice(0, 1).map(({ page, waveform }) => ({ page, waveform })),
    same: true,
    common: wholeWave({}),
    channels: channelRows((channel) => ({ channel, on: channel === 0, wave: wholeWave({}) })),
    ...NOT_RUNNING,
  };
}

// Returns a new value generator for the panel, with no instruction yet. Its
// wave sends a value only once a second, because the log shows every
// instruction sent.
export function newValueGenerator() {
  return {
    kind: VALUE,
    send: "",
    onlyWhenChanged: false,
    wave: wholeWave({ interval: 1000, period: 20 }),
    conditions: [],
    ...NOT_RUNNING,
  };
}

// Returns a new condition for the panel: a switch that turns on above 0,
// with no instruction yet.
export function newCondition() {
  return { above: true, level: 0, back: null, after: 0, whenOn: "", whenOff: "" };
}

// Returns the lowest and highest level a condition can have, the same as
// for a value generator's values.
export function levelBounds() {
  const [low, high] = BOUNDS[VALUE];
  return { low, high };
}

// Returns whether the simulation is running `generator`.
export function isRunning(generator) {
  return generator.number !== null;
}

// Returns the panel's generators for `running`, the generators the
// simulation runs, each as {number, settings}. A panel opened while
// generators run shows these.
export function generatorsOfRunning(running) {
  return running.map(({ number, settings }) => ({ ...generatorOfSettings(settings), number }));
}

// Marks as stopped each of `generators` that the simulation no longer
// runs, such as one an agent stopped from outside the panel. `running`
// lists the generators the simulation runs, each as {number}.
export function markStopped(generators, running) {
  const numbers = new Set(running.map(({ number }) => number));
  for (const generator of generators) {
    if (isRunning(generator) && !numbers.has(generator.number)) {
      generator.number = null;
    }
  }
}

// Returns how many channels the panel offers for a generator feeding the
// waveforms `chosen`: as many as the one with the most has. The simulation
// sends a channel only to the waveforms that have it. `offered` lists the
// app's waveforms, {page, waveform, channels}. Waveforms the app does not
// have, which a file can name, are not counted. If waveforms are chosen and
// none of them is in the app, the panel offers MOST_CHANNELS.
export function channelCount(chosen, offered) {
  const counts = channelCounts(chosen, offered);
  if (counts.length > 0) {
    return Math.max(...counts.map(([, count]) => count));
  }
  return chosen.length === 0 ? 1 : MOST_CHANNELS;
}

// Returns [name, its number of channels] for each waveform of `chosen` that
// the app has.
function channelCounts(chosen, offered) {
  return chosen.map((name) => [name, offered.find((other) => sameWaveform(other, name))])
    .filter(([, known]) => known !== undefined)
    .map(([name, known]) => [name, known.channels]);
}

export function sameWaveform(one, other) {
  return one.page === other.page && one.waveform === other.waveform;
}

// Has a generator send the same wave on every channel, or a wave for each.
// Turned on, every channel takes the wave of the first channel that is on,
// so that what that channel showed stays. Turned off, each channel starts
// from the wave they all sent.
export function setSame(generator, same) {
  if (same === generator.same) {
    return;
  }
  if (same) {
    const first = generator.channels.find((row) => row.on);
    if (first !== undefined) {
      generator.common = wholeWave(first.wave);
    }
  } else {
    for (const row of generator.channels) {
      row.wave = wholeWave(generator.common);
    }
  }
  generator.same = same;
}

// Returns {settings}, the generator's settings as the simulation and a
// settings file take them, or {error}, which says what the user must set
// first. `offered` lists the app's waveforms. If a waveform generator sends
// the same wave on every channel, the settings give that wave once, and
// list each channel by its number alone. Otherwise each channel gets its
// whole wave. A value generator's settings list its conditions, and one
// instruction for each line typed that is not empty.
export function settingsOf(generator, offered) {
  if (generator.kind === VALUE) {
    const send = instructionsOf(generator.send);
    if (send.length === 0 && generator.conditions.length === 0) {
      return { error: "Type an instruction to send, such as temp.val={value}, or add a " +
                      "condition." };
    }
    const conditions = [];
    for (const [index, condition] of generator.conditions.entries()) {
      const made = conditionSettings(condition);
      if (made.error !== undefined) {
        return { error: `Condition ${index + 1}: ${made.error}` };
      }
      conditions.push(made.settings);
    }
    return { settings: {
      kind: VALUE, ...(send.length > 0 ? { send } : {}),
      ...(generator.onlyWhenChanged ? { onlyWhenChanged: true } : {}),
      ...sentWave(generator.wave), ...(conditions.length > 0 ? { conditions } : {}),
    } };
  }
  if (generator.waveforms.length === 0) {
    return { error: "Choose a waveform to send the points to." };
  }
  const count = channelCount(generator.waveforms, offered);
  const channels = generator.channels.filter((row) => row.on && row.channel < count);
  if (channels.length === 0) {
    return { error: "Turn on a channel to send points to." };
  }
  const settings = {
    kind: generator.kind,
    waveforms: generator.waveforms.map(({ page, waveform }) => ({ page, waveform })),
    ...(generator.same ? sentWave(generator.common) : {}),
    channels: channels.map((row) => ({
      channel: row.channel, ...(generator.same ? {} : sentWave(row.wave)),
    })),
  };
  return { settings };
}

// Returns the panel's generator for `settings`, a generator as a settings
// file gives it. A waveform generator sends the same wave on every channel
// unless one of its channels changes a setting. Each channel's own wave
// starts as the wave the channel sends, so that turning off "Same wave on
// every channel" changes nothing.
export function generatorOfSettings(settings) {
  if (settings.kind === VALUE) {
    return {
      kind: VALUE,
      send: (settings.send ?? []).join("\n"),
      onlyWhenChanged: settings.onlyWhenChanged === true,
      wave: wholeWave(waveSettings(settings)),
      conditions: (settings.conditions ?? []).map(conditionOfSettings),
      ...NOT_RUNNING,
    };
  }
  const listed = new Map((settings.channels ?? []).map((given) => [given.channel, given]));
  const common = wholeWave(waveSettings(settings));
  return {
    kind: WAVEFORM,
    waveforms: (settings.waveforms ?? []).map(({ page, waveform }) => ({ page, waveform })),
    same: [...listed.values()].every((given) => Object.keys(waveSettings(given)).length === 0),
    common,
    channels: channelRows((channel) => ({
      channel, on: listed.has(channel),
      wave: wholeWave({ ...common, ...waveSettings(listed.get(channel) ?? {}) }),
    })),
    ...NOT_RUNNING,
  };
}

// Returns {settings}, the settings of each of `generators` in order, in the
// form a settings file lists them. If a generator lacks something, returns
// {error} instead, which says what is missing and gives the generator's
// place in the panel.
export function settingsOfAll(generators, offered) {
  const settings = [];
  for (const [index, generator] of generators.entries()) {
    const made = settingsOf(generator, offered);
    if (made.error !== undefined) {
      return { error: `Generator ${index + 1}: ${made.error}` };
    }
    settings.push(made.settings);
  }
  return { settings };
}

// Returns `count` points of `wave` for its sketch, as channel `channel` of a
// generator of `kind` sends it. Each channel starts a quarter of the cycle,
// or of a custom wave's list, further on than the channel before it. The
// shapes, and the bounds each kind keeps its values within, follow
// signal_generators.py. A random wave and noise use the sketch's own random
// numbers, so the sketch shows the wave's shape but not the exact points
// the simulation sends.
export function sketchValues(wave, count, channel = 0, kind = WAVEFORM) {
  const [lowest, highest] = BOUNDS[kind];
  const start = Math.floor(wave.values.length * channel / 4);
  const random = sketchRandom();
  const values = [];
  for (let point = 0; point < count; point += 1) {
    let value;
    if (wave.shape === "random") {
      value = wave.minimum + Math.floor(random() * (wave.maximum - wave.minimum + 1));
    } else if (wave.shape === "custom") {
      value = wave.values.length === 0 ? 0
        : wave.values[(start + point) % wave.values.length];
    } else {
      const position = (channel / 4 + point / wave.period) % 1;
      value = wave.minimum + Math.floor(
        (wave.maximum - wave.minimum) * shapeLevel(wave, position) + 0.5);
    }
    if (wave.noise > 0) {
      value += Math.floor(random() * (2 * wave.noise + 1)) - wave.noise;
    }
    values.push(Math.min(Math.max(value, lowest), highest));
  }
  return values;
}

// Returns [lowest, highest], the values drawn at the bottom and the top of
// a sketch of `values`, the points of a generator of `kind`. A waveform
// generator's sketch always spans 0 to 255, every value a point can take. A
// value generator's sketch spans only its points, because the range of a
// value is too wide to draw.
export function sketchSpan(kind, values) {
  if (kind === WAVEFORM) {
    return BOUNDS[WAVEFORM];
  }
  const lowest = Math.min(...values);
  const highest = Math.max(...values);
  // A flat wave is drawn half way up.
  return lowest === highest ? [lowest - 1, highest + 1] : [lowest, highest];
}

// Returns how many points a wave's sketch shows: two of its cycles, within
// what the sketch has room for.
export function sketchLength(wave) {
  const cycle = wave.shape === "custom" ? Math.max(wave.values.length, 1)
    : wave.shape === "random" ? 30 : wave.period;
  return Math.min(Math.max(2 * cycle, 2), 240);
}

// Returns {values}, the whole numbers typed in `text`, separated by commas
// or spaces. Returns {error} if one is not a whole number within the bounds
// of a generator of `kind`. Text without any number gives no values.
export function valuesOfText(text, kind = WAVEFORM) {
  const words = text.split(/[\s,;]+/).filter((word) => word !== "");
  return checkedValues(words.map(Number), "The values", kind);
}

// Returns {values}, the numbers in the first column of numbers of `text`, a
// CSV file's text, each rounded to a whole number. That column is where the
// first row with a number has its first number. A row without a number in
// that column, such as a heading, is skipped. Returns {error} if no row has
// a number, or if a value is outside the bounds of a generator of `kind`.
export function valuesOfCsv(text, kind = WAVEFORM) {
  const rows = text.split(/\r?\n/).map((row) => row.split(/[,;\t]/).map((cell) => cell.trim()));
  let column;
  for (const row of rows) {
    column = row.findIndex(isNumber);
    if (column !== -1) {
      break;
    }
  }
  if (column === undefined || column === -1) {
    return { error: "The file has no column of numbers." };
  }
  const numbers = rows.filter((row) => isNumber(row[column] ?? ""))
    .map((row) => Math.round(Number(row[column])));
  return checkedValues(numbers, "The file's values", kind);
}

// Returns the text of a settings file that contains `settings`, the
// settings of each generator in order.
export function fileText(settings) {
  return `${JSON.stringify({ nxwrightSignals: 1, generators: settings }, null, 2)}\n`;
}

// Returns {settings}, the settings of each generator in `text`, a settings
// file's text, or {error}. The simulation checks each setting when its
// generator starts.
export function settingsOfFileText(text) {
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    return { error: "The file is not JSON." };
  }
  if (data === null || typeof data !== "object" || !("nxwrightSignals" in data)) {
    return { error: "The file is not a signal generator settings file." };
  }
  if (data.nxwrightSignals !== 1) {
    return { error: `The file's nxwrightSignals is ${JSON.stringify(data.nxwrightSignals)}, ` +
                    "a version this extension does not read. It reads 1." };
  }
  if (!Array.isArray(data.generators) || data.generators.length === 0) {
    return { error: "The file has no generator." };
  }
  for (const [index, settings] of data.generators.entries()) {
    if (settings === null || typeof settings !== "object" || !("kind" in settings)) {
      return { error: `Generator ${index + 1} in the file has no "kind".` };
    }
    if (typeof settings.kind !== "string" || !Object.hasOwn(BOUNDS, settings.kind)) {
      // A later version of the extension may know more kinds.
      return { error: `Generator ${index + 1} of the file is of a kind this extension does ` +
                      `not know: ${JSON.stringify(settings.kind)}.` };
    }
  }
  return { settings: data.generators };
}

// Returns the instructions typed in `text`, one for each line that is not
// empty.
function instructionsOf(text) {
  return text.split("\n").map((line) => line.trim()).filter((line) => line !== "");
}

// Returns {settings}, the condition in the form a settings file uses, or
// {error}, which says what the user must set first. Settings left at their
// default are left out, the same way signal_generators.py writes a
// condition.
function conditionSettings(condition) {
  const whenOn = instructionsOf(condition.whenOn);
  const whenOff = instructionsOf(condition.whenOff);
  if (whenOn.length === 0 && whenOff.length === 0) {
    return { error: "Type an instruction to send when it turns on or off." };
  }
  const { above, level, back } = condition;
  if (back !== null && (above ? back > level : back < level)) {
    return { error: `The level that turns it off cannot be ${above ? "above" : "below"} ` +
                    "the level that turns it on." };
  }
  return { settings: {
    [above ? "turnsOnAbove" : "turnsOnBelow"]: level,
    ...(back === null ? {} : { [above ? "turnsOffBelow" : "turnsOffAbove"]: back }),
    ...(condition.after > 0 ? { afterMs: condition.after } : {}),
    ...(whenOn.length > 0 ? { whenOn } : {}),
    ...(whenOff.length > 0 ? { whenOff } : {}),
  } };
}

// Returns the panel's condition for `settings`, a condition in the form a
// settings file uses.
function conditionOfSettings(settings) {
  const above = "turnsOnAbove" in settings;
  return {
    above,
    level: above ? settings.turnsOnAbove : settings.turnsOnBelow,
    back: (above ? settings.turnsOffBelow : settings.turnsOffAbove) ?? null,
    after: settings.afterMs ?? 0,
    whenOn: (settings.whenOn ?? []).join("\n"),
    whenOff: (settings.whenOff ?? []).join("\n"),
  };
}

function channelRows(row) {
  return Array.from({ length: MOST_CHANNELS }, (_, channel) => row(channel));
}

// Returns the wave settings `given` has, a generator's or a channel's.
function waveSettings(given) {
  return Object.fromEntries(WAVE_KEYS.filter((key) => key in given)
    .map((key) => [key, key === "values" ? [...given.values] : given[key]]));
}

// Returns a wave with every setting: those of `given`, and the defaults of
// the others. Its values are a list of its own.
function wholeWave(given) {
  const wave = { ...WAVE_DEFAULTS, ...given };
  return { ...wave, values: [...wave.values] };
}

// Returns a wave as the settings give it: every setting, but a custom
// wave's values only when it has some.
function sentWave(wave) {
  const { values, ...sent } = wave;
  return values.length > 0 ? { ...sent, values: [...values] } : sent;
}

// Returns a shape's level at `position` in its cycle, from 0 up to 1: 0
// for the lowest value and 1 for the highest (signal_generators.wave_value).
function shapeLevel(wave, position) {
  switch (wave.shape) {
    case "sine":
      return Math.round((1 - Math.cos(2 * Math.PI * position)) / 2 * 1e9) / 1e9;
    case "square":
      return position < 0.5 ? 1 : 0;
    case "triangle":
      return position < 0.5 ? 2 * position : 2 - 2 * position;
    case "sawtooth":
      return position;
    case "inverted-sawtooth":
      return 1 - position;
    default:    // a pulse
      return position < wave.duty / 100 ? 1 : 0;
  }
}

// Returns a source of numbers from 0 up to 1 that gives the same numbers
// each time, so that a sketch does not change as it is drawn again.
function sketchRandom() {
  let state = 12345;
  return () => {
    state = (state * 1103515245 + 12345) % 2147483648;
    return state / 2147483648;
  };
}

function isNumber(cell) {
  return cell !== "" && Number.isFinite(Number(cell));
}

function checkedValues(numbers, what, kind) {
  const [lowest, highest] = BOUNDS[kind];
  if (!numbers.every((number) => Number.isInteger(number) && number >= lowest &&
                                 number <= highest)) {
    return { error: `${what} must be whole numbers from ${lowest} to ${highest}.` };
  }
  return { values: numbers };
}
