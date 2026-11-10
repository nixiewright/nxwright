// The Signal generator panel's own rules (media/signal-generators-model.mjs).
// Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  channelCount, fileText, generatorOfSettings, generatorsOfRunning, isRunning, markStopped,
  newGenerator, NUMBER_SETTINGS, setSame, settingsOf, settingsOfAll, settingsOfFileText,
  sketchLength, sketchValues, valuesOfCsv, valuesOfText, WAVE_DEFAULTS,
} from "../media/signal-generators-model.mjs";

const OFFERED = [
  { page: "day", waveform: "chart", channels: 2 },
  { page: "home", waveform: "scope", channels: 4 },
];
// A wave's settings as they are sent when none was changed: every one but a
// custom wave's values, which it has none of.
const { values: noValues, ...SENT_DEFAULTS } = WAVE_DEFAULTS;

test("a new generator sends a sine wave on channel 0 of the app's first waveform", () => {
  const generator = newGenerator(OFFERED);
  assert.equal(generator.same, true);
  assert.equal(isRunning(generator), false);
  assert.deepEqual(settingsOf(generator, OFFERED), { settings: {
    kind: "waveform",
    waveforms: [{ page: "day", waveform: "chart" }],
    ...SENT_DEFAULTS,
    channels: [{ channel: 0 }],
  } });
});

test("the settings are the ones the simulation takes: no phase, and no seed", () => {
  assert.deepEqual(Object.keys(WAVE_DEFAULTS).sort(),
                   ["duty", "interval", "maximum", "minimum", "noise", "period", "shape",
                    "values"]);
  assert.deepEqual(NUMBER_SETTINGS.map((setting) => setting.key),
                   ["minimum", "maximum", "interval", "period", "duty", "noise"]);
});

test("the same wave on every channel is given once", () => {
  const generator = newGenerator(OFFERED);
  generator.common.shape = "square";
  generator.channels[1].on = true;
  // A channel's own wave is not sent while every channel sends the same.
  generator.channels[1].wave.shape = "pulse";
  assert.deepEqual(settingsOf(generator, OFFERED).settings, {
    kind: "waveform",
    waveforms: [{ page: "day", waveform: "chart" }],
    ...SENT_DEFAULTS, shape: "square",
    channels: [{ channel: 0 }, { channel: 1 }],
  });
});

test("a wave for each channel gives each channel its whole wave", () => {
  const generator = newGenerator(OFFERED);
  generator.common.maximum = 200;
  generator.channels[1].on = true;
  setSame(generator, false);
  // Each channel starts from the wave they all sent.
  assert.deepEqual(generator.channels.map((row) => row.wave.maximum), [200, 200, 200, 200]);
  generator.channels[1].wave.shape = "custom";
  generator.channels[1].wave.values = [4, 5];
  assert.deepEqual(settingsOf(generator, OFFERED).settings, {
    kind: "waveform",
    waveforms: [{ page: "day", waveform: "chart" }],
    channels: [{ channel: 0, ...SENT_DEFAULTS, maximum: 200 },
               { channel: 1, ...SENT_DEFAULTS, maximum: 200, shape: "custom", values: [4, 5] }],
  });
});

test("back to the same wave, every channel takes the first channel's that is on", () => {
  const generator = newGenerator(OFFERED);
  setSame(generator, false);
  generator.channels[0].on = false;
  generator.channels[1].on = true;
  generator.channels[1].wave.shape = "triangle";
  setSame(generator, true);
  assert.equal(generator.common.shape, "triangle");
  assert.deepEqual(settingsOf(generator, OFFERED).settings.shape, "triangle");
  // A wave of its own: changing one later leaves the other as it is.
  generator.common.shape = "sine";
  assert.equal(generator.channels[1].wave.shape, "triangle");
});

test("the generator offers as many channels as its waveform with the most", () => {
  const [chart, scope] = OFFERED;
  const gone = { page: "gone", waveform: "w" };
  assert.equal(channelCount([chart], OFFERED), 2);
  assert.equal(channelCount([chart, scope], OFFERED), 4);
  // One the app does not have, as a file may give, counts for nothing,
  // unless it is the only one: then for the most.
  assert.equal(channelCount([chart, gone], OFFERED), 2);
  assert.equal(channelCount([gone], OFFERED), 4);
  assert.equal(channelCount([], OFFERED), 1);
  // A channel turned on past them is not sent.
  const generator = newGenerator(OFFERED);
  generator.channels[3].on = true;
  assert.deepEqual(settingsOf(generator, OFFERED).settings.channels, [{ channel: 0 }]);
  // Past the chart's two, they are the scope's.
  generator.waveforms.push({ page: "home", waveform: "scope" });
  assert.deepEqual(settingsOf(generator, OFFERED).settings.channels,
                   [{ channel: 0 }, { channel: 3 }]);
});

test("a generator without a waveform, or without a channel, says what it needs", () => {
  const generator = newGenerator(OFFERED);
  generator.channels[0].on = false;
  assert.deepEqual(settingsOf(generator, OFFERED),
                   { error: "Turn on a channel to send points to." });
  generator.waveforms = [];
  assert.deepEqual(settingsOf(generator, OFFERED),
                   { error: "Choose a waveform to send the points to." });
});

test("a file whose channels change nothing is the same wave on every channel", () => {
  const settings = {
    kind: "waveform",
    waveforms: [{ page: "home", waveform: "scope" }],
    interval: 20, shape: "custom", values: [1, 2, 3],
    channels: [{ channel: 0 }, { channel: 2 }],
  };
  const generator = generatorOfSettings(settings);
  assert.equal(generator.same, true);
  assert.deepEqual(generator.channels.map((row) => row.on), [true, false, true, false]);
  assert.deepEqual(settingsOf(generator, OFFERED).settings, {
    kind: "waveform", waveforms: settings.waveforms, ...SENT_DEFAULTS, interval: 20,
    shape: "custom", values: [1, 2, 3], channels: settings.channels,
  });
});

test("a file whose channel changes a setting is a wave for each channel", () => {
  // As a file written by hand may be: the generator's settings are the
  // ones its channels share, and a channel gives those it changes.
  const generator = generatorOfSettings({
    kind: "waveform", waveforms: [{ page: "home", waveform: "scope" }], maximum: 200, duty: 80,
    channels: [{ channel: 0 }, { channel: 1, shape: "pulse", duty: 10 }],
  });
  assert.equal(generator.same, false);
  // Each channel's own wave is what the file gives it.
  assert.deepEqual(generator.channels[0].wave, { ...WAVE_DEFAULTS, maximum: 200, duty: 80 });
  assert.deepEqual(generator.channels[1].wave,
                   { ...WAVE_DEFAULTS, maximum: 200, shape: "pulse", duty: 10 });
  assert.deepEqual(settingsOf(generator, OFFERED).settings.channels, [
    { channel: 0, ...SENT_DEFAULTS, maximum: 200, duty: 80 },
    { channel: 1, ...SENT_DEFAULTS, maximum: 200, shape: "pulse", duty: 10 },
  ]);
});

test("a sketch follows the shapes the simulation sends", () => {
  // The same cycles as nxwright's own test of the shapes
  // (tests/test_signal_generators.py), eight points to a cycle.
  const wave = (shape, more = {}) => ({ ...WAVE_DEFAULTS, shape, period: 8, ...more });
  assert.deepEqual(sketchValues(wave("sine"), 8), [0, 15, 50, 85, 100, 85, 50, 15]);
  assert.deepEqual(sketchValues(wave("square"), 8), [100, 100, 100, 100, 0, 0, 0, 0]);
  assert.deepEqual(sketchValues(wave("triangle"), 8), [0, 25, 50, 75, 100, 75, 50, 25]);
  assert.deepEqual(sketchValues(wave("sawtooth"), 8), [0, 13, 25, 38, 50, 63, 75, 88]);
  assert.deepEqual(sketchValues(wave("inverted-sawtooth"), 8),
                   [100, 88, 75, 63, 50, 38, 25, 13]);
  assert.deepEqual(sketchValues(wave("pulse", { duty: 25 }), 8), [100, 100, 0, 0, 0, 0, 0, 0]);
  assert.deepEqual(sketchValues(wave("custom", { values: [5, 9] }), 5), [5, 9, 5, 9, 5]);
});

test("a channel's sketch starts a quarter cycle after the channel before it", () => {
  // As the simulation starts each channel (tests/test_signal_generators.py).
  const sine = { ...WAVE_DEFAULTS, period: 4 };
  assert.deepEqual([0, 1, 2, 3].map((channel) => sketchValues(sine, 2, channel)),
                   [[0, 50], [50, 100], [100, 50], [50, 0]]);
  const custom = { ...WAVE_DEFAULTS, shape: "custom", values: [0, 1, 2, 3, 4, 5, 6, 7] };
  assert.deepEqual([0, 1, 2, 3].map((channel) => sketchValues(custom, 1, channel)[0]),
                   [0, 2, 4, 6]);
});

test("a sketch's random values and noise stay in range, and are the same each time", () => {
  const random = { ...WAVE_DEFAULTS, shape: "random", minimum: 20, maximum: 30 };
  const values = sketchValues(random, 200);
  assert.ok(values.every((value) => value >= 20 && value <= 30));
  assert.ok(new Set(values).size > 5);
  assert.deepEqual(sketchValues(random, 200), values);
  const noisy = sketchValues({ ...WAVE_DEFAULTS, shape: "custom", values: [250], noise: 40 }, 100);
  assert.ok(noisy.every((value) => value >= 0 && value <= 255));
  assert.ok(noisy.includes(255));
});

test("a sketch shows two cycles of its wave", () => {
  assert.equal(sketchLength({ ...WAVE_DEFAULTS, period: 50 }), 100);
  assert.equal(sketchLength({ ...WAVE_DEFAULTS, period: 5000 }), 240);
  assert.equal(sketchLength({ ...WAVE_DEFAULTS, shape: "custom", values: [1, 2, 3] }), 6);
});

test("typed values are whole numbers from 0 to 255, apart by commas or spaces", () => {
  assert.deepEqual(valuesOfText("1, 2,3  40\n255"), { values: [1, 2, 3, 40, 255] });
  assert.deepEqual(valuesOfText("  "), { values: [] });
  for (const text of ["1, x", "256", "-1", "1.5"]) {
    assert.deepEqual(valuesOfText(text),
                     { error: "The values must be whole numbers from 0 to 255." });
  }
});

test("a CSV file gives the values of its first column of numbers", () => {
  // The first row's first number is in the second column, so that column
  // is read; the heading and an empty row are passed over.
  const text = "time,level,note\r\n0:00,10.4,start\r\n0:01,20.6,\r\n\r\n0:02,30,end\r\n";
  assert.deepEqual(valuesOfCsv(text), { values: [10, 21, 30] });
  assert.deepEqual(valuesOfCsv("5\n6\n7"), { values: [5, 6, 7] });
  assert.deepEqual(valuesOfCsv("1;2\n3;4"), { values: [1, 3] });
  assert.deepEqual(valuesOfCsv("name\nvalue\n"), { error: "The file has no column of numbers." });
  assert.deepEqual(valuesOfCsv("10\n300\n"),
                   { error: "The file's values must be whole numbers from 0 to 255." });
});

test("a settings file reads back what was written, and other files say why not", () => {
  const second = newGenerator(OFFERED);
  second.common.shape = "square";
  const { settings } = settingsOfAll([newGenerator(OFFERED), second], OFFERED);
  assert.deepEqual(settings.map((one) => one.shape), ["sine", "square"]);
  assert.deepEqual(settingsOfFileText(fileText(settings)), { settings });
  assert.deepEqual(Object.keys(JSON.parse(fileText(settings))),
                   ["nxwrightSignals", "generators"]);
  assert.deepEqual(settingsOfFileText("{"), { error: "The file is not JSON." });
  for (const text of ["[]", '{"nxwrightWaves": 1, "generator": {}}']) {
    assert.deepEqual(settingsOfFileText(text),
                     { error: "The file is not a signal generator settings file." });
  }
  assert.match(settingsOfFileText('{"nxwrightSignals": 2, "generators": [{}]}').error,
               /nxwrightSignals is 2, a version this extension does not read/);
  for (const text of ['{"nxwrightSignals": 1}', '{"nxwrightSignals": 1, "generators": []}']) {
    assert.deepEqual(settingsOfFileText(text), { error: "The file has no generator." });
  }
  // A kind from a later version is reported with its name and its
  // generator's place in the file.
  const later = fileText([settings[0], { kind: "sequence" }]);
  assert.deepEqual(settingsOfFileText(later), {
    error: 'Generator 2 of the file is of a kind this extension does not know: "sequence".',
  });
  for (const lacking of [{ waveforms: [] }, 3, null]) {
    assert.deepEqual(settingsOfFileText(fileText([lacking])),
                     { error: 'Generator 1 in the file has no "kind".' });
  }
});

test("saving says which generator lacks something", () => {
  const lacking = newGenerator(OFFERED);
  lacking.waveforms = [];
  assert.deepEqual(settingsOfAll([newGenerator(OFFERED), lacking], OFFERED),
                   { error: "Generator 2: Choose a waveform to send the points to." });
  assert.deepEqual(settingsOfAll([], OFFERED), { settings: [] });
});

test("a panel opened while generators run shows them as running", () => {
  const settings = settingsOf(newGenerator(OFFERED), OFFERED).settings;
  const shown = generatorsOfRunning([{ number: 2, settings },
                                     { number: 5, settings: { ...settings, shape: "pulse" } }]);
  assert.deepEqual(shown.map((generator) => [generator.number, isRunning(generator),
                                             generator.common.shape]),
                   [[2, true, "sine"], [5, true, "pulse"]]);
});

test("a generator stopped from outside the panel is marked as stopped", () => {
  const generators = [newGenerator(OFFERED), newGenerator(OFFERED), newGenerator(OFFERED)];
  generators[0].number = 1;
  generators[1].number = 2;
  // The simulation runs 2, and 7, which the panel does not have.
  markStopped(generators, [{ number: 2 }, { number: 7 }]);
  assert.deepEqual(generators.map(isRunning), [false, true, false]);
});
