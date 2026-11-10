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

// The kind of a generator that sends points to waveforms.
export const WAVEFORM = "waveform";

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

// The settings that are whole numbers, in the order the panel shows them:
// the name the panel gives each, the values it takes, and what it is.
export const NUMBER_SETTINGS = [
  { key: "minimum", label: "Min", low: 0, high: 255, title: "The wave's lowest value" },
  { key: "maximum", label: "Max", low: 0, high: 255, title: "The wave's highest value" },
  { key: "interval", label: "Interval (ms)", low: 1, title: "Milliseconds between two points" },
  { key: "period", label: "Period (points)", low: 1,
    title: "Points in one cycle of the wave" },
  { key: "duty", label: "Duty (%)", low: 0, high: 100,
    title: "For a pulse: the percentage of the cycle at the highest value" },
  { key: "noise", label: "Noise", low: 0, high: 255,
    title: "The most that is added to or taken from each point, at random" },
];

// The most channels a waveform has.
export const MOST_CHANNELS = 4;
const LARGEST_VALUE = 255;
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
// settings file take them, or {error}, what the panel must have first.
// `offered` lists the app's waveforms. A generator that sends the same
// wave on every channel gives that wave once, and each channel alone;
// another gives each channel its whole wave.
export function settingsOf(generator, offered) {
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
// file gives it. It sends the same wave on every channel unless one of its
// channels changes a setting. Each channel's own wave is what it sends, so
// that turning the same wave off changes nothing.
export function generatorOfSettings(settings) {
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

// Returns `count` points of `wave` for its sketch, as channel `channel`
// sends it. Each channel starts a quarter of the cycle, or of a custom
// wave's list, further on than the channel before it, as in
// signal_generators.py. The shapes follow signal_generators.py. A random wave and noise are
// drawn from numbers of the sketch's own, so the sketch shows how the wave
// looks, not the very points the simulation sends.
export function sketchValues(wave, count, channel = 0) {
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
    values.push(Math.min(Math.max(value, 0), LARGEST_VALUE));
  }
  return values;
}

// Returns how many points a wave's sketch shows: two of its cycles, within
// what the sketch has room for.
export function sketchLength(wave) {
  const cycle = wave.shape === "custom" ? Math.max(wave.values.length, 1)
    : wave.shape === "random" ? 30 : wave.period;
  return Math.min(Math.max(2 * cycle, 2), 240);
}

// Returns {values}, the whole numbers typed in `text`, separated by commas
// or spaces, or {error}. No numbers at all give no values.
export function valuesOfText(text) {
  const words = text.split(/[\s,;]+/).filter((word) => word !== "");
  return checkedValues(words.map(Number), "The values");
}

// Returns {values}, the numbers of the first column of numbers of `text`,
// the text of a CSV file, each rounded to a whole number, or {error}. The
// column is the first cell that is a number in the first row that has one.
// A row without a number in that column, such as a heading, is skipped.
export function valuesOfCsv(text) {
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
  return checkedValues(numbers, "The file's values");
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
    if (settings.kind !== WAVEFORM) {
      // A later version of the extension may know more kinds.
      return { error: `Generator ${index + 1} of the file is of a kind this extension does ` +
                      `not know: ${JSON.stringify(settings.kind)}.` };
    }
  }
  return { settings: data.generators };
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

function checkedValues(numbers, what) {
  if (!numbers.every((number) => Number.isInteger(number) && number >= 0 &&
                                 number <= LARGEST_VALUE)) {
    return { error: `${what} must be whole numbers from 0 to ${LARGEST_VALUE}.` };
  }
  return { values: numbers };
}
