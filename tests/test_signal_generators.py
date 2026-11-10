"""Signal generators (testing/signal_generators.py): a wave's shapes, the
generators' settings and their file, and what a waveform generator and a
value generator send a simulation (testing/simulation.py)."""
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from nxwright import NxwrightError
from nxwright.testing.simulation import Simulation
from nxwright.testing.signal_generators import (ValueGeneratorRun, WaveformGeneratorRun,
                                                generator_settings, generators_from_json,
                                                generators_to_json, instruction_with,
                                                read_generators_file, wave_value)
from tests.test_simulation import SimulationTestCase, placed, table


def settings(**given):
    """The settings of a waveform generator feeding channel 0 of page0's
    chart, with the generator's own settings `given`; `channels`, when
    given, replaces the channel list."""
    channels = given.pop("channels", [{"channel": 0}])
    return generator_settings(dict({"kind": "waveform",
                                    "waveforms": [{"page": "page0", "waveform": "chart"}],
                                    "channels": channels}, **given), "test")


def value_settings(**given):
    """The settings of a value generator that sends `temp.val={value}`, with
    the settings `given`."""
    return generator_settings(dict({"kind": "value", "send": ["temp.val={value}"]}, **given),
                              "test")


def points(generator: WaveformGeneratorRun, count: int) -> list:
    """The next `count` ticks' values of the generator's first channel."""
    return [generator.tick()[0][1] for _ in range(count)]


class ShapeTest(unittest.TestCase):

    def wave(self, **given):
        generator = settings(minimum=0, maximum=100, **given)
        return generator.wave(generator.channels[0])

    def test_each_shape_through_its_cycle(self):
        positions = [Fraction(step, 8) for step in range(8)]
        for shape, expected in (("sine", [0, 15, 50, 85, 100, 85, 50, 15]),
                                ("square", [100, 100, 100, 100, 0, 0, 0, 0]),
                                ("triangle", [0, 25, 50, 75, 100, 75, 50, 25]),
                                ("sawtooth", [0, 13, 25, 38, 50, 63, 75, 88]),
                                ("inverted-sawtooth", [100, 88, 75, 63, 50, 38, 25, 13])):
            with self.subTest(shape=shape):
                self.assertEqual([wave_value(self.wave(shape=shape), at) for at in positions],
                                 expected)

    def test_a_pulse_is_high_for_its_duty(self):
        wave = self.wave(shape="pulse", duty=25)
        self.assertEqual([wave_value(wave, Fraction(step, 8)) for step in range(8)],
                         [100, 100, 0, 0, 0, 0, 0, 0])

    def test_the_sine_starts_at_the_minimum_and_rises(self):
        # As the Nextion Editor's generator draws it.
        run = WaveformGeneratorRun(settings(shape="sine", minimum=10, maximum=50, period=4), 0)
        self.assertEqual(points(run, 5), [10, 30, 50, 30, 10])

    def test_a_custom_wave_plays_its_values_in_a_loop(self):
        run = WaveformGeneratorRun(settings(shape="custom", values=[5, 9, 200]), 0)
        self.assertEqual(points(run, 5), [5, 9, 200, 5, 9])

    def test_random_values_and_noise_are_the_same_each_time_a_generator_starts(self):
        for given in ({"shape": "random", "minimum": 20, "maximum": 30},
                      {"shape": "sine", "noise": 10}):
            with self.subTest(given=given):
                first = points(WaveformGeneratorRun(settings(**given), 0), 50)
                self.assertEqual(points(WaveformGeneratorRun(settings(**given), 0), 50), first)
                self.assertGreater(len(set(first)), 5)
        run = WaveformGeneratorRun(settings(shape="random", minimum=20, maximum=30), 0)
        values = points(run, 200)
        self.assertEqual((min(values), max(values)), (20, 30))

    def test_noise_keeps_points_from_0_to_255(self):
        for shape, value, extreme in (("custom", 250, 255), ("custom", 3, 0)):
            run = WaveformGeneratorRun(settings(shape=shape, values=[value], noise=40), 0)
            self.assertIn(extreme, points(run, 100))
            self.assertTrue(all(0 <= point <= 255 for point in points(run, 100)))

    def test_a_channel_overrides_the_generators_settings(self):
        run = WaveformGeneratorRun(settings(shape="square", maximum=80, period=2, interval=10,
                                            channels=[{"channel": 0},
                                                      {"channel": 1, "shape": "sawtooth",
                                                       "interval": 20}]), 0)
        # Channel 1 starts a quarter into its cycle: a fifth of the way up.
        self.assertEqual([run.tick() for _ in range(3)],
                         [[(0, 80)], [(0, 0), (1, 20)], [(0, 80)]])

    def test_each_channel_starts_a_quarter_cycle_after_the_one_before(self):
        # So that channels with the same wave do not draw over each other.
        four = [{"channel": number} for number in range(4)]
        run = WaveformGeneratorRun(settings(shape="sine", maximum=100, period=4, interval=10,
                                            channels=four), 0)
        self.assertEqual(run.tick(), [(0, 0), (1, 50), (2, 100), (3, 50)])
        self.assertEqual(run.tick(), [(0, 50), (1, 100), (2, 50), (3, 0)])
        # A custom wave starts a quarter of its list further on.
        run = WaveformGeneratorRun(settings(shape="custom", values=list(range(8)),
                                            channels=four), 0)
        self.assertEqual(run.tick(), [(0, 0), (1, 2), (2, 4), (3, 6)])

    def test_a_change_keeps_the_waves_place(self):
        run = WaveformGeneratorRun(settings(shape="sawtooth", maximum=100, period=4), 0)
        self.assertEqual(points(run, 2), [0, 25])
        # A new period moves on from the place reached, half the cycle.
        run.change(settings(shape="sawtooth", maximum=100, period=8), 20)
        self.assertEqual(points(run, 2), [50, 63])
        # A new shape goes on from the same place, three quarters of it.
        run.change(settings(shape="inverted-sawtooth", maximum=100, period=8), 40)
        self.assertEqual(points(run, 1), [25])


class SettingsFileTest(unittest.TestCase):

    def test_a_file_reads_back_what_was_written(self):
        given = (settings(shape="custom", values=[1, 2], interval=5,
                          channels=[{"channel": 0}, {"channel": 2, "noise": 4}]),
                 settings(shape="square"))
        text = generators_to_json(given)
        self.assertEqual(generators_from_json(text, "test"), given)
        written = json.loads(text)
        self.assertEqual(written["nxwrightSignals"], 1)
        self.assertEqual([generator["kind"] for generator in written["generators"]],
                         ["waveform", "waveform"])

    def test_a_file_on_disk(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        path = Path(folder) / "signals.json"
        path.write_text(generators_to_json([settings()]), encoding="utf-8")
        self.assertEqual(read_generators_file(path), (settings(),))
        with self.assertRaisesRegex(NxwrightError, "cannot be read"):
            read_generators_file(path.with_name("missing.json"))

    def test_settings_are_refused_with_their_place(self):
        generator = {"kind": "waveform", "waveforms": [{"page": "page0", "waveform": "chart"}],
                     "channels": [{"channel": 0}]}
        for change, refusal in (
                ({"channels": [{"channel": 0}, {"channel": 1, "shape": "saw"}]},
                 r"\.channels\[1\]: shape 'saw' is not a shape"),
                ({"minimum": 90, "maximum": 10},
                 r"\.channels\[0\]: minimum 90 is above maximum 10"),
                ({"shape": "custom"},
                 r"\.channels\[0\]: a custom wave needs values"),
                ({"interval": 0}, r": interval must be a whole number of 1"),
                ({"maximum": 256},
                 r": maximum must be a whole number from 0 to 255"),
                ({"channels": [{"channel": 4}]},
                 r"\.channels\[0\]: channel must be from 0 to 3"),
                ({"channels": [{"channel": 1}, {"channel": 1}]},
                 r": channels lists a channel twice"),
                ({"waveforms": []}, r": waveforms must list one waveform or more"),
                # Settings the generator once had are settings no more.
                ({"phase": 25}, r": phase is not a setting"),
                ({"seed": 3}, r": seed is not a setting"),
                ({"speed": 2}, r": speed is not a setting")):
            with self.subTest(change=change):
                # The second generator of the file is the one at fault.
                text = json.dumps({"nxwrightSignals": 1,
                                   "generators": [generator, dict(generator, **change)]})
                with self.assertRaisesRegex(NxwrightError,
                                            r"^signals.json: generators\[1\]" + refusal):
                    generators_from_json(text, "signals.json")

    def test_a_generator_says_its_kind(self):
        generator = {"waveforms": [{"page": "page0", "waveform": "chart"}],
                     "channels": [{"channel": 0}]}
        with self.assertRaisesRegex(NxwrightError, "^test: a generator must give its kind, as "
                                                   '"kind": "waveform" or "kind": "value"$'):
            generator_settings(generator, "test")
        # A kind from a later version of nxwright is refused, and the error
        # gives its name.
        with self.assertRaisesRegex(NxwrightError, "^test: kind 'sequence' is not a kind of "
                                                   "generator this version of nxwright knows. "
                                                   "It knows waveform and value$"):
            generator_settings(dict(generator, kind="sequence"), "test")
        # So is a kind that is no text at all.
        for kind in ([], {"value": 1}, 3, None):
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(NxwrightError, "^test: kind .* is not a kind of "
                                                           "generator this version of nxwright "
                                                           "knows"):
                    generator_settings(dict(generator, kind=kind), "test")
        self.assertEqual(settings().json_form()["kind"], "waveform")

    def test_a_custom_wave_ignores_the_minimum_and_the_maximum(self):
        # Its values are played as given, so a minimum above the maximum,
        # here the default of 100, refuses nothing.
        run = WaveformGeneratorRun(settings(shape="custom", minimum=150, values=[7, 8]), 0)
        self.assertEqual(points(run, 2), [7, 8])

    def test_other_files_are_refused(self):
        for text, refusal in (("{", "not JSON"),
                              ("{}", "not a signal generator settings file"),
                              # The form the waveform generator saved before
                              # generators had kinds.
                              ('{"nxwrightWaves": 1, "generator": {}}',
                               "not a signal generator settings file"),
                              ('{"nxwrightSignals": 2, "generators": [{}]}',
                               "nxwrightSignals 2 is not a version nxwright reads"),
                              ('{"nxwrightSignals": 1}',
                               "generators must list one generator or more"),
                              ('{"nxwrightSignals": 1, "generators": []}',
                               "generators must list one generator or more"),
                              ('{"nxwrightSignals": 1, "generators": [3]}',
                               r"generators\[0\]: a generator must be a JSON object")):
            with self.subTest(text=text):
                with self.assertRaisesRegex(NxwrightError, refusal):
                    generators_from_json(text, "signals.json")


class ValueGeneratorSettingsTest(unittest.TestCase):

    def test_a_file_reads_back_generators_of_both_kinds(self):
        given = (settings(shape="square"),
                 value_settings(send=["temp.val={value}", "click refresh,1"], minimum=180,
                                maximum=240, interval=1000, onlyWhenChanged=True),
                 value_settings())
        text = generators_to_json(given)
        self.assertEqual(generators_from_json(text, "test"), given)
        written = json.loads(text)["generators"]
        self.assertEqual(written[1], {"kind": "value",
                                      "send": ["temp.val={value}", "click refresh,1"],
                                      "onlyWhenChanged": True, "minimum": 180, "maximum": 240,
                                      "interval": 1000})
        # A setting left at its default is not written.
        self.assertEqual(written[2], {"kind": "value", "send": ["temp.val={value}"]})

    def test_the_value_takes_the_place_of_its_name_in_an_instruction(self):
        for text, sent in (("temp.val={value}", "temp.val=215"),
                           # In a quoted text too, and wherever it stands.
                           ('t0.txt="{value} C"', 't0.txt="215 C"'),
                           ("add 1,0,{value}", "add 1,0,215"),
                           ("n0.val={value}+{value}", "n0.val=215+215"),
                           # Braces that hold no name are sent as they are.
                           ('t0.txt="{} { 3 } {1a} {"', 't0.txt="{} { 3 } {1a} {"'),
                           ("click refresh,1", "click refresh,1")):
            with self.subTest(text=text):
                self.assertEqual(instruction_with(text, 215), sent)
                self.assertEqual(value_settings(send=[text]).send, (text,))
        self.assertEqual(instruction_with("temp.val={value}", -40), "temp.val=-40")

    def test_a_value_generators_settings_are_refused_with_their_place(self):
        for change, refusal in (
                # Any other name between braces is refused, so that it can be
                # given a meaning later.
                ({"send": ["temp.val={value}", "t0.txt={state}"]},
                 r"test\.send\[1\]: \{state\} is not a name an instruction can use\. It can "
                 r"use \{value\}"),
                ({"send": ["temp.val={Value}"]},
                 r"test\.send\[0\]: \{Value\} is not a name an instruction can use"),
                ({"send": ["temp.val={_x1}"]}, r"test\.send\[0\]: \{_x1\} is not a name"),
                ({"send": ["temp.val=1", " "]},
                 r"test\.send\[1\]: an instruction is one line of text, and not empty"),
                ({"send": ["temp.val=1\nclick b0,1"]},
                 r"test\.send\[0\]: an instruction is one line of text, and not empty"),
                ({"send": [3]},
                 r"test\.send\[0\]: an instruction is one line of text, and not empty"),
                ({"send": "temp.val={value}"}, r"test\.send must be a list of instructions"),
                ({"send": []},
                 r"test: a value generator needs an instruction in send, or a condition"),
                ({"onlyWhenChanged": 1}, r"test: onlyWhenChanged must be true or false"),
                # A waveform generator's settings are not a value generator's.
                ({"waveforms": [{"page": "page0", "waveform": "chart"}]},
                 r"test: waveforms is not a setting"),
                ({"channels": [{"channel": 0}]}, r"test: channels is not a setting"),
                ({"shape": "saw"}, r"test: shape 'saw' is not a shape"),
                ({"minimum": 90, "maximum": 10}, r"test: minimum 90 is above maximum 10"),
                ({"shape": "custom"}, r"test: a custom wave needs values")):
            with self.subTest(change=change):
                with self.assertRaisesRegex(NxwrightError, "^" + refusal):
                    value_settings(**change)
        with self.assertRaisesRegex(NxwrightError, "^test: a value generator needs an "
                                                   "instruction in send, or a condition$"):
            generator_settings({"kind": "value"}, "test")

    def test_a_value_is_a_whole_number_of_32_bits(self):
        lowest, highest = -2147483648, 2147483647
        wide = value_settings(minimum=lowest, maximum=highest, noise=highest,
                              shape="custom", values=[lowest, highest])
        self.assertEqual((wide.wave().minimum, wide.wave().maximum, wide.wave().values),
                         (lowest, highest, (lowest, highest)))
        bounds = "from -2147483648 to 2147483647"
        for change, refusal in (({"minimum": lowest - 1},
                                 "minimum must be a whole number " + bounds),
                                ({"maximum": highest + 1},
                                 "maximum must be a whole number " + bounds),
                                ({"noise": -1},
                                 "noise must be a whole number from 0 to 2147483647"),
                                ({"values": [highest + 1]},
                                 "values must be a list of whole numbers " + bounds),
                                ({"maximum": 1.5}, "maximum must be a whole number " + bounds)):
            with self.subTest(change=change):
                with self.assertRaisesRegex(NxwrightError, refusal):
                    value_settings(**change)
        # A waveform's point stays one of the values a device sends as a byte.
        with self.assertRaisesRegex(NxwrightError, "maximum must be a whole number from 0 to 255"):
            settings(maximum=256)
        with self.assertRaisesRegex(NxwrightError, "whole numbers from 0 to 255"):
            settings(shape="custom", values=[-1])

    def test_noise_keeps_a_value_within_32_bits(self):
        for value, extreme in ((2147483640, 2147483647), (-2147483640, -2147483648)):
            run = ValueGeneratorRun(value_settings(shape="custom", values=[value], noise=40), 0)
            sent = [int(run.tick()[0].split("=")[1]) for _ in range(100)]
            self.assertIn(extreme, sent)
            self.assertTrue(all(-2147483648 <= one <= 2147483647 for one in sent))

    def test_a_value_generator_sends_its_instructions_at_each_point(self):
        run = ValueGeneratorRun(value_settings(
            send=["temp.val={value}", "click refresh,1"], shape="custom", values=[5, -7],
            interval=30), 100)
        self.assertEqual(run.due(), 130)
        self.assertEqual(run.tick(), ["temp.val=5", "click refresh,1"])
        self.assertEqual(run.due(), 160)
        self.assertEqual(run.tick(), ["temp.val=-7", "click refresh,1"])

    def test_only_when_changed_sends_a_value_once_until_it_changes(self):
        run = ValueGeneratorRun(value_settings(shape="square", maximum=1, period=4,
                                               onlyWhenChanged=True), 0)
        # The first point is sent, then each point whose value changed.
        self.assertEqual([run.tick() for _ in range(6)],
                         [["temp.val=1"], [], ["temp.val=0"], [], ["temp.val=1"], []])
        # Once the app started again, the screen has lost the value: the next
        # point is sent whatever its value.
        run.app_started(0)
        self.assertEqual([run.tick() for _ in range(2)], [["temp.val=0"], []])
        # Without onlyWhenChanged, every point is sent.
        run = ValueGeneratorRun(value_settings(shape="square", maximum=1, period=4), 0)
        self.assertEqual([run.tick() for _ in range(3)],
                         [["temp.val=1"], ["temp.val=1"], ["temp.val=0"]])

    def test_a_value_generators_change_keeps_the_waves_place(self):
        run = ValueGeneratorRun(value_settings(shape="sawtooth", maximum=100, period=4), 0)
        self.assertEqual([run.tick() for _ in range(2)], [["temp.val=0"], ["temp.val=25"]])
        run.change(value_settings(send=["n0.val={value}"], shape="sawtooth", maximum=1000,
                                  period=4), 100)
        self.assertEqual(run.tick(), ["n0.val=500"])


class ConditionTest(unittest.TestCase):
    """A value generator's conditions, on waves that play a list of values,
    one every 10 ms."""

    ALARM = {"turnsOnAbove": 20, "whenOn": ["on={value}"], "whenOff": ["off={value}"]}

    def run_of(self, values: list, *conditions, **given) -> ValueGeneratorRun:
        """A running value generator that plays `values`, with `conditions`
        and the settings `given`, and no `send` unless given."""
        return ValueGeneratorRun(generator_settings(dict(
            {"kind": "value", "shape": "custom", "values": values, "interval": 10,
             "conditions": list(conditions)}, **given), "test"), 0)

    def sent(self, values: list, *conditions, **given) -> list:
        """What the generator sends at each point of `values`."""
        run = self.run_of(values, *conditions, **given)
        return [run.tick() for _ in values]

    def test_a_switch_turns_on_above_its_level_and_off_once_no_longer_above(self):
        self.assertEqual(self.sent([10, 30, 30, 10, 30], self.ALARM),
                         [[], ["on=30"], [], ["off=10"], ["on=30"]])
        # Above means greater than the level: a value at the level is not.
        self.assertEqual(self.sent([20, 21, 20], self.ALARM), [[], ["on=21"], ["off=20"]])

    def test_a_switch_turns_on_below_its_level(self):
        low = {"turnsOnBelow": 5, "whenOn": ["on={value}"], "whenOff": ["off={value}"]}
        self.assertEqual(self.sent([9, 5, 3, 3, 5, -2], low),
                         [[], [], ["on=3"], [], ["off=5"], ["on=-2"]])

    def test_a_first_value_past_the_level_turns_the_switch_on_at_once(self):
        self.assertEqual(self.sent([30], self.ALARM), [["on=30"]])

    def test_a_second_level_keeps_a_wavering_value_from_switching_again_and_again(self):
        wavering = [215, 221, 219, 222, 218, 211, 209, 215, 221]
        alarm = {"turnsOnAbove": 220, "whenOn": ["on"], "whenOff": ["off"]}
        self.assertEqual(self.sent(wavering, alarm),
                         [[], ["on"], ["off"], ["on"], ["off"], [], [], [], ["on"]])
        # With turnsOffBelow at 210, the switch turns off only at 209.
        self.assertEqual(self.sent(wavering, dict(alarm, turnsOffBelow=210)),
                         [[], ["on"], [], [], [], [], ["off"], [], ["on"]])
        # The same the other way up.
        low = {"turnsOnBelow": 10, "turnsOffAbove": 20, "whenOn": ["on"], "whenOff": ["off"]}
        self.assertEqual(self.sent([15, 9, 12, 20, 21, 12, 9], low),
                         [[], ["on"], [], [], ["off"], [], ["on"]])

    def test_a_change_waits_until_the_value_has_stayed_past_the_level(self):
        patient = dict(self.ALARM, afterMs=20)
        # The points are 10 ms apart. The switch turns on at the third point
        # above the level, 20 ms after the first. A point back above the
        # level makes turning off wait from the start again.
        self.assertEqual(self.sent([30, 30, 30, 30, 10, 30, 10, 10, 10], patient),
                         [[], [], ["on=30"], [], [], [], [], [], ["off=10"]])
        # A first value past the level waits too.
        self.assertEqual(self.sent([30, 10, 30, 30, 30], patient),
                         [[], [], [], [], ["on=30"]])

    def test_a_point_sends_its_own_instructions_then_its_conditions_in_order(self):
        first = {"turnsOnAbove": 20, "whenOn": ["click a,1", "click a,0"]}
        second = {"turnsOnAbove": 25, "whenOn": ["click b,1"]}
        self.assertEqual(self.sent([30], first, second, send=["temp.val={value}"]),
                         [["temp.val=30", "click a,1", "click a,0", "click b,1"]])

    def test_a_condition_is_checked_at_a_point_whose_value_is_not_sent(self):
        patient = dict(self.ALARM, afterMs=10)
        self.assertEqual(self.sent([30, 30, 30], patient, send=["temp.val={value}"],
                                   onlyWhenChanged=True),
                         [["temp.val=30"], ["on=30"], []])

    def test_a_start_of_the_app_puts_every_switch_back_to_off(self):
        run = self.run_of([30, 30, 30, 30], self.ALARM, send=["temp.val={value}"],
                          onlyWhenChanged=True)
        self.assertEqual([run.tick(), run.tick()], [["temp.val=30", "on=30"], []])
        # The screen has lost the value and the alarm: both are sent again.
        run.app_started(-20)
        self.assertEqual([run.tick(), run.tick()], [["temp.val=30", "on=30"], []])

    def test_new_settings_keep_the_switch_of_a_condition_at_the_same_place(self):
        run = self.run_of([30, 30, 30], self.ALARM)
        self.assertEqual(run.tick(), ["on=30"])
        added = {"turnsOnAbove": 25, "whenOn": ["second"]}
        run.change(generator_settings(
            {"kind": "value", "shape": "custom", "values": [30, 30, 30], "interval": 10,
             "conditions": [dict(self.ALARM, whenOn=["again"]), added]}, "test"), 10)
        # The first condition's switch is still on. The new one starts off.
        self.assertEqual(run.tick(), ["second"])
        # A condition taken away takes its switch with it.
        run.change(generator_settings(
            {"kind": "value", "shape": "custom", "values": [30, 30, 30], "interval": 10,
             "conditions": [added]}, "test"), 20)
        self.assertEqual(run.tick(), [])

    def test_conditions_are_written_back_as_they_were_read(self):
        conditions = [
            {"turnsOnAbove": 220, "turnsOffBelow": 210, "afterMs": 500,
             "whenOn": ["click alarm,1"], "whenOff": ["click alarm,0"]},
            {"turnsOnBelow": -5, "whenOff": ["frost.val=0"]}]
        read = generator_settings({"kind": "value", "conditions": conditions}, "test")
        # A value generator with conditions needs no `send`.
        self.assertEqual(read.json_form(), {"kind": "value", "conditions": conditions})
        self.assertEqual(generators_from_json(generators_to_json([read]), "test"), (read,))
        self.assertEqual(read.sends(), "with 2 conditions")
        both = generator_settings({"kind": "value", "send": ["temp.val={value}"],
                                   "conditions": conditions[:1]}, "test")
        self.assertEqual(both.sends(), "sending temp.val={value}, with 1 condition")

    def test_conditions_are_refused_with_their_place(self):
        alarm = {"turnsOnAbove": 20, "whenOn": ["click alarm,1"]}
        for conditions, refusal in (
                ({"turnsOnAbove": 20}, r"test\.conditions must be a list of conditions"),
                ([3], r"test\.conditions\[0\]: a condition must be a JSON object"),
                ([alarm, dict(alarm, turnsOnBelow=5)],
                 r"test\.conditions\[1\]: a condition needs turnsOnAbove or turnsOnBelow, and "
                 r"not both"),
                ([{"whenOn": ["click alarm,1"]}],
                 r"test\.conditions\[0\]: a condition needs turnsOnAbove or turnsOnBelow"),
                ([dict(alarm, turnsOffBelow=21)],
                 r"test\.conditions\[0\]: turnsOffBelow 21 is above turnsOnAbove 20"),
                ([{"turnsOnBelow": 5, "turnsOffAbove": 4, "whenOn": ["x=1"]}],
                 r"test\.conditions\[0\]: turnsOffAbove 4 is below turnsOnBelow 5"),
                ([dict(alarm, turnsOffAbove=30)],
                 r"test\.conditions\[0\]: turnsOffAbove goes with turnsOnBelow\. With "
                 r"turnsOnAbove, give turnsOffBelow"),
                ([{"turnsOnAbove": 20}],
                 r"test\.conditions\[0\]: a condition needs an instruction in whenOn or "
                 r"whenOff"),
                ([dict(alarm, whenOn=[])],
                 r"test\.conditions\[0\]: a condition needs an instruction"),
                ([dict(alarm, afterMs=-1)],
                 r"test\.conditions\[0\]: afterMs must be a whole number of 0 or more"),
                ([dict(alarm, turnsOnAbove=2147483648)],
                 r"test\.conditions\[0\]: turnsOnAbove must be a whole number from "
                 r"-2147483648 to 2147483647"),
                ([dict(alarm, turnsOffBelow=1.5)],
                 r"test\.conditions\[0\]: turnsOffBelow must be a whole number"),
                ([dict(alarm, whenOff=["t0.txt={state}"])],
                 r"test\.conditions\[0\]\.whenOff\[0\]: \{state\} is not a name an instruction "
                 r"can use"),
                ([dict(alarm, whenOn="click alarm,1")],
                 r"test\.conditions\[0\]\.whenOn must be a list of instructions"),
                ([dict(alarm, sustain=3)], r"test\.conditions\[0\]: sustain is not a setting")):
            with self.subTest(conditions=conditions):
                with self.assertRaisesRegex(NxwrightError, "^" + refusal):
                    generator_settings({"kind": "value", "conditions": conditions}, "test")
        # Two levels that are the same are accepted, even though they leave
        # no room for a wavering value.
        same = generator_settings({"kind": "value", "conditions": [
            dict(alarm, turnsOffBelow=20)]}, "test")
        self.assertEqual(same.conditions[0].off_level, 20)


class GeneratorInSimulationTest(SimulationTestCase):
    """A chart of two channels, 10 points wide, on page0; another on second."""

    def setUp(self):
        super().setUp()
        self.program("page page0\n")
        self.page("page0", [table("chart", "waveform", x=0, y=0, w=10, h=50, ch=2),
                            placed("go", "button", 300, 0)], """\
on go.down:
  page second
""")
        self.page("second", [table("other", "waveform", x=0, y=0, w=10, h=50, ch=1)])

    def sine(self, **given):
        return settings(**dict({"shape": "sine", "minimum": 0, "maximum": 100, "period": 4,
                                "interval": 20}, **given))

    def test_points_arrive_on_time_through_add(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine())
        simulation.advance(19)
        self.assertEqual(simulation.waves(), {})
        simulation.advance(61)
        self.assertEqual(simulation.waves(), {"chart": {0: [0, 50, 100, 50]}})

    def test_points_count_apart_from_the_pages_other_changes(self):
        # So that the generator's points bring no drawing of the whole page.
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine(channels=[{"channel": 0}, {"channel": 1}]))
        changes, points = simulation.changes, simulation.wave_changes
        simulation.advance(100)
        self.assertEqual((simulation.changes, simulation.wave_changes), (changes, points + 10))
        # A typed add is an instruction like any other: the page is drawn.
        simulation.serial_input("add 1,0,5")
        self.assertEqual((simulation.changes, simulation.wave_changes),
                         (changes + 1, points + 11))
        simulation.serial_input("cle 1,255")
        self.assertEqual(simulation.wave_changes, points + 12)
        # A point the screen refuses counts as a change of the page, because
        # nothing tells that its instruction changed nothing. The generator
        # never sends such a point, since it skips a channel that a waveform
        # lacks, so this test runs one directly.
        changes = simulation.changes
        simulation._run_points(["add 1,0,5", "add 1,3,5"])
        self.assertEqual(simulation.changes, changes + 1)

    def test_a_tick_runs_its_points_on_one_view(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine(channels=[{"channel": 0}, {"channel": 1}]))
        with mock.patch.object(Simulation, "_view", autospec=True,
                               side_effect=Simulation._view) as view:
            simulation.advance(20)
        self.assertEqual(view.call_count, 1)
        self.assertEqual(simulation.waves(), {"chart": {0: [0], 1: [50]}})

    def test_the_log_tells_the_start_and_the_stop_not_each_point(self):
        simulation = Simulation(self.root)
        feeding = self.sine(channels=[{"channel": 0}, {"channel": 1}])
        number = simulation.start_generator(feeding)
        simulation.advance(100)
        self.assertEqual(simulation.generators(), {1: feeding})
        simulation.stop_generator(number)
        simulation.advance(100)
        self.assertEqual([line for _, line in simulation.log],
                         ["waveform generator 1 starts, sending to channels 0, 1 of "
                          "page0.chart", "waveform generator 1 stops"])
        self.assertEqual(len(simulation.waves()["chart"][0]), 5)
        self.assertEqual(simulation.generators(), {})

    def test_generators_run_side_by_side(self):
        simulation = Simulation(self.root)
        sawtooth = self.sine(shape="sawtooth")
        square = self.sine(shape="square", channels=[{"channel": 1}])
        self.assertEqual(simulation.start_generator(sawtooth), 1)
        simulation.advance(40)
        self.assertEqual(simulation.start_generator(square), 2)
        simulation.advance(40)
        # The first one went on, and the second one's wave started.
        self.assertEqual(simulation.waves(), {"chart": {0: [0, 25, 50, 75], 1: [100, 0]}})
        self.assertEqual(simulation.generators(), {1: sawtooth, 2: square})
        # Stopping one leaves the other running.
        simulation.stop_generator(1)
        simulation.advance(20)
        self.assertEqual(simulation.waves(), {"chart": {0: [0, 25, 50, 75], 1: [100, 0, 0]}})
        self.assertEqual(simulation.generators(), {2: square})
        # A number is not given twice.
        self.assertEqual(simulation.start_generator(sawtooth), 3)

    def test_generators_due_together_send_in_the_order_of_their_numbers(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine(shape="custom", values=[1]))
        simulation.start_generator(self.sine(shape="custom", values=[2]))
        simulation.start_generator(self.sine(shape="custom", values=[3], interval=40))
        simulation.advance(40)
        self.assertEqual(simulation.waves(), {"chart": {0: [1, 2, 1, 2, 3]}})

    def change_while_points_arrive(self, simulation: Simulation, change):
        """Has `change(simulation)` run once, while the next points arrive.
        This stands in for the debugger holding the simulation inside the
        code a point runs, as when a point wakes the screen and its wake page
        loads: the panel can stop and start generators meanwhile."""
        arrived = Simulation._serial_arrived
        changed = []

        def change_meanwhile(simulation):
            arrived(simulation)
            if not changed:
                changed.append(True)
                change(simulation)
        patch = mock.patch.object(Simulation, "_serial_arrived", autospec=True,
                                  side_effect=change_meanwhile)
        patch.start()
        self.addCleanup(patch.stop)

    def test_a_generator_stopped_while_points_go_out_sends_no_more(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine(shape="custom", values=[1]))
        second = simulation.start_generator(self.sine(shape="custom", values=[2]))
        self.change_while_points_arrive(simulation,
                                        lambda simulation: simulation.stop_generator(second))
        simulation.advance(40)
        self.assertEqual(simulation.waves(), {"chart": {0: [1, 1]}})

    def test_a_generator_started_while_points_go_out_waits_for_its_interval(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine(shape="custom", values=[1]))
        other = self.sine(shape="custom", values=[2])
        self.change_while_points_arrive(simulation,
                                        lambda simulation: simulation.start_generator(other))
        simulation.advance(20)
        self.assertEqual(simulation.waves(), {"chart": {0: [1]}})
        simulation.advance(20)
        self.assertEqual(simulation.waves(), {"chart": {0: [1, 1, 2]}})

    def test_each_generator_keeps_its_own_random_numbers(self):
        # A generator sends the same points whether or not another runs.
        alone = Simulation(self.root)
        alone.start_generator(self.sine(shape="random"))
        alone.advance(200)
        beside = Simulation(self.root)
        beside.start_generator(self.sine(shape="random", channels=[{"channel": 1}]))
        beside.start_generator(self.sine(shape="random"))
        beside.advance(200)
        self.assertEqual(beside.waves()["chart"][0], alone.waves()["chart"][0])

    def test_each_point_is_answered_as_bkcmd_asks(self):
        simulation = Simulation(self.root)
        simulation.serial_input("bkcmd=3")
        simulation.start_generator(self.sine(channels=[{"channel": 0}, {"channel": 1}]))
        before = len(simulation.log)
        simulation.advance(20)
        self.assertEqual([line for _, line in simulation.log[before:]],
                         ["SIM SEND: 01 ff ff ff", "SIM SEND: 01 ff ff ff"])

    def test_com_stop_holds_the_points(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine())
        simulation.serial_input("com_stop")
        simulation.advance(60)
        self.assertEqual(simulation.waves(), {})
        simulation.serial_input("com_star")
        self.assertEqual(simulation.waves(), {"chart": {0: [0, 50, 100]}})
        self.assertEqual([line for _, line in simulation.log if "held" in line],
                         ["waveform generator 1's points are held: the serial line is "
                          "stopped", "waveform generator 1's held points run"])

    def test_a_hold_is_told_for_each_generator(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine())
        simulation.start_generator(self.sine(channels=[{"channel": 1}]))
        simulation.serial_input("com_stop")
        simulation.advance(40)
        simulation.serial_input("com_star")
        self.assertEqual(simulation.waves(), {"chart": {0: [0, 50], 1: [50, 100]}})
        self.assertEqual([line for _, line in simulation.log if "held" in line],
                         ["waveform generator 1's points are held: the serial line is stopped",
                          "waveform generator 2's points are held: the serial line is stopped",
                          "waveform generator 1's held points run",
                          "waveform generator 2's held points run"])

    def test_each_hold_is_told_in_the_log(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine())
        simulation.serial_input("com_stop")
        simulation.advance(40)
        # A start again ends the hold, and drops the points it held.
        simulation.start_again()
        simulation.serial_input("com_stop")
        simulation.advance(40)
        self.assertEqual(len([line for _, line in simulation.log
                              if "points are held" in line]), 2)

    def test_during_a_transfer_the_points_arrive_as_bytes(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine())
        # The chart's ID is 1: the transfer takes the next 4 bytes as points.
        simulation.serial_input("addt 1,1,4")
        before = len(simulation.log)
        simulation.advance(20)
        self.assertEqual(simulation.waves(), {"chart": {1: list(b"add ")}})
        # The rest of the point arrives as an instruction the screen refuses,
        # which the log shows as it shows any.
        self.assertEqual([line for _, line in simulation.log[before:]],
                         ["SIM SEND: fd ff ff ff", "SIM RECV: 1,0,0", "SIM SEND: 00 ff ff ff"])

    def test_a_page_not_shown_gets_nothing_and_its_wave_goes_on(self):
        simulation = Simulation(self.root)
        simulation.start_generator(settings(
            waveforms=[{"page": "second", "waveform": "other"}], shape="sawtooth",
            maximum=100, period=4, interval=20))
        simulation.advance(40)
        self.assertEqual(simulation.waves(), {})
        simulation.press("go", 300, 0)
        simulation.release()
        simulation.advance(40)
        # Two points went by unsent, at 20 and 40.
        self.assertEqual(simulation.waves(), {"other": {0: [50, 75]}})

    def test_a_global_waveforms_new_points_follow_those_it_kept(self):
        self.page("page0", [table("chart", "waveform", x=0, y=0, w=10, h=50, ch=2, vscope=1)])
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine())
        simulation.advance(40)
        simulation.serial_input("page second")
        # The points at 60 and 80 go by unsent.
        simulation.advance(40)
        simulation.serial_input("page page0")
        simulation.advance(20)
        self.assertEqual(simulation.waves(), {"chart": {0: [0, 50, 0]}})

    def test_a_timer_of_the_same_moment_runs_first(self):
        self.page("page0", [table("chart", "waveform", x=0, y=0, w=10, h=50, ch=2),
                            table("tick", "timer", tim=60, en=1)], """\
on tick.timer:
  cle chart.id,0
""")
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine(interval=60))
        simulation.advance(60)
        # The timer cleared the channel, then the generator's point came.
        self.assertEqual(simulation.waves(), {"chart": {0: [0]}})

    def test_points_keep_the_screen_awake_and_wake_it(self):
        simulation = Simulation(self.root)
        simulation.serial_input("ussp=1")
        simulation.start_generator(self.sine())
        simulation.advance(3000)
        self.assertFalse(simulation.asleep)
        simulation.serial_input("sleep=1")
        simulation.advance(40)
        self.assertTrue(simulation.asleep)       # usup is 0: the points run asleep
        self.assertEqual(len(simulation.waves()["chart"][0]), 10)
        simulation.serial_input("usup=1")
        simulation.advance(20)
        self.assertFalse(simulation.asleep)

    def test_a_start_again_keeps_the_generators_pace(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine())
        simulation.advance(30)
        simulation.start_again()
        # Its next point was due at 40, 10 after the start again.
        self.assertEqual(simulation.next_due(), 10)
        simulation.advance(10)
        self.assertEqual(simulation.waves(), {"chart": {0: [50]}})

    def test_a_generator_is_refused_for_a_waveform_or_channel_the_app_lacks(self):
        simulation = Simulation(self.root)
        for given, refusal in (
                ({"waveforms": [{"page": "third", "waveform": "chart"}]}, "has no page third"),
                ({"waveforms": [{"page": "page0", "waveform": "go"}]}, "has no waveform go"),
                ({"channels": [{"channel": 2}]},
                 "none of its waveforms has a channel 2. The most channels any of them has "
                 "is 2")):
            with self.subTest(given=given):
                with self.assertRaisesRegex(NxwrightError, refusal):
                    simulation.start_generator(settings(**given))
        self.assertEqual(simulation.generators(), {})
        number = simulation.start_generator(self.sine())
        simulation.stop_generator(number)
        for act in (lambda: simulation.stop_generator(number),
                    lambda: simulation.change_generator(number, self.sine()),
                    lambda: simulation.stop_generator(7)):
            with self.assertRaisesRegex(NxwrightError, "generator [17] is not running"):
                act()

    def test_a_channel_goes_only_to_the_waveforms_that_have_it(self):
        self.page("page0", [table("chart", "waveform", x=0, y=0, w=10, h=50, ch=2),
                            table("strip", "waveform", x=0, y=100, w=10, h=50, ch=1)])
        simulation = Simulation(self.root)
        simulation.serial_input("bkcmd=3")
        simulation.start_generator(settings(
            waveforms=[{"page": "page0", "waveform": "chart"},
                       {"page": "page0", "waveform": "strip"}],
            shape="square", period=4, interval=20, channels=[{"channel": 0}, {"channel": 1}]))
        before = len(simulation.log)
        simulation.advance(40)
        # Channel 1 is a quarter cycle ahead of channel 0.
        self.assertEqual(simulation.waves(), {"chart": {0: [100, 100], 1: [100, 0]},
                                              "strip": {0: [100, 100]}})
        # Nothing went to the channel the strip lacks: three points a tick,
        # each answered as bkcmd asks, and no refusal.
        self.assertEqual([line for _, line in simulation.log[before:]],
                         ["SIM SEND: 01 ff ff ff"] * 6)
        # Its `ch` is looked at as the points go: a channel the chart's code
        # takes away gets no more points.
        simulation.fields["page0"]["chart.ch"] = 1
        simulation.advance(20)
        self.assertEqual(simulation.waves()["chart"][1], [100, 0])

    def test_a_change_takes_effect_at_the_next_point(self):
        simulation = Simulation(self.root)
        number = simulation.start_generator(self.sine())
        simulation.advance(40)
        simulation.change_generator(number, self.sine(maximum=50))
        simulation.advance(40)
        # Half way through its cycle, with a lower maximum.
        self.assertEqual(simulation.waves(), {"chart": {0: [0, 50, 50, 25]}})


class ValueGeneratorInSimulationTest(SimulationTestCase):
    """page0 has a number, "temp", and a hotspot, "refresh", whose press
    copies temp's value into the number "seen"; the page "second" has a
    number, "other"."""

    def setUp(self):
        super().setUp()
        self.program("page page0\n")
        self.page("page0", [placed("temp", "number", 0, 0), placed("seen", "number", 0, 100),
                            placed("refresh", "hotspot", 300, 0),
                            table("chart", "waveform", x=0, y=200, w=10, h=50, ch=1)], """\
on refresh.down:
  seen.val = temp.val
""")
        self.page("second", [placed("other", "number", 0, 0)])

    def value(self, simulation: Simulation, name: str):
        return simulation.fields[simulation.page][name + ".val"]

    def received(self, simulation: Simulation) -> list:
        """The instructions the log shows the screen received."""
        return [line[len("SIM RECV: "):] for _, line in simulation.log
                if line.startswith("SIM RECV: ")]

    def feeding(self, **given):
        return value_settings(**dict({"shape": "custom", "values": [5, 7], "interval": 20},
                                     **given))

    def test_the_instructions_arrive_on_time_in_order_and_show_in_the_log(self):
        simulation = Simulation(self.root)
        number = simulation.start_generator(self.feeding(
            send=["temp.val={value}", "click refresh,1"]))
        simulation.advance(19)
        self.assertEqual(self.received(simulation), [])
        simulation.advance(1)
        # The click's event read the value its point had just set.
        self.assertEqual((self.value(simulation, "temp"), self.value(simulation, "seen")),
                         (5, 5))
        simulation.advance(20)
        self.assertEqual((self.value(simulation, "temp"), self.value(simulation, "seen")),
                         (7, 7))
        self.assertEqual(self.received(simulation),
                         ["temp.val=5", "click refresh,1", "temp.val=7", "click refresh,1"])
        simulation.stop_generator(number)
        simulation.advance(100)
        self.assertEqual(len(self.received(simulation)), 4)
        self.assertEqual([line for _, line in simulation.log if "generator" in line],
                         ["value generator 1 starts, sending temp.val={value}; click refresh,1",
                          "value generator 1 stops"])

    def test_each_instruction_is_answered_as_bkcmd_asks(self):
        simulation = Simulation(self.root)
        simulation.serial_input("bkcmd=3")
        # A component of a page not shown is a name the screen does not know.
        simulation.start_generator(self.feeding(send=["temp.val={value}", "other.val={value}"]))
        before = len(simulation.log)
        simulation.advance(20)
        self.assertEqual([line for _, line in simulation.log[before:]],
                         ["SIM RECV: temp.val=5", "SIM SEND: 01 ff ff ff",
                          "SIM RECV: other.val=5", "SIM SEND: 1a ff ff ff"])

    def test_a_value_generator_sends_whichever_page_shows(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.feeding(send=["other.val={value}"]))
        simulation.serial_input("page second")
        simulation.advance(20)
        self.assertEqual(self.value(simulation, "other"), 5)

    def test_com_stop_holds_the_instructions(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.feeding())
        simulation.serial_input("com_stop")
        simulation.advance(40)
        self.assertEqual(self.value(simulation, "temp"), 0)
        self.assertEqual([line for _, line in simulation.log if "held" in line],
                         ["held: the serial line is stopped"] * 2)
        simulation.serial_input("com_star")
        self.assertEqual(self.value(simulation, "temp"), 7)

    def test_the_instructions_run_while_the_screen_sleeps_and_keep_it_awake(self):
        simulation = Simulation(self.root)
        simulation.serial_input("ussp=1")
        simulation.start_generator(self.feeding())
        simulation.advance(3000)
        self.assertFalse(simulation.asleep)
        simulation.serial_input("sleep=1")
        simulation.advance(20)
        self.assertTrue(simulation.asleep)       # usup is 0: the instruction runs asleep
        self.assertEqual(len(self.received(simulation)), 3000 // 20 + 3)

    def test_a_start_of_the_app_has_the_next_point_sent_again(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.feeding(values=[5], onlyWhenChanged=True))
        simulation.advance(60)
        self.assertEqual(self.received(simulation), ["temp.val=5"])
        simulation.start_again()
        self.assertEqual(self.value(simulation, "temp"), 0)
        # The generator kept its pace, and the screen is sent the value it lost.
        simulation.advance(20)
        self.assertEqual(self.value(simulation, "temp"), 5)
        simulation.advance(40)
        self.assertEqual(self.received(simulation), ["temp.val=5", "temp.val=5"])

    def test_an_instruction_that_starts_the_app_again_drops_those_after_it(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.feeding(
            values=[5], onlyWhenChanged=True, send=["temp.val={value}", "rest", "temp.val=99"]))
        simulation.advance(20)
        self.assertEqual(self.received(simulation), ["temp.val=5", "rest"])
        self.assertEqual(self.value(simulation, "temp"), 0)
        # The next point is sent again, though its value is the same.
        simulation.advance(20)
        self.assertEqual(self.received(simulation),
                         ["temp.val=5", "rest", "temp.val=5", "rest"])

    def test_a_change_takes_new_settings_of_the_same_kind(self):
        simulation = Simulation(self.root)
        number = simulation.start_generator(self.feeding(values=[1, 2, 3, 4]))
        simulation.advance(20)
        simulation.change_generator(number, self.feeding(values=[10, 20, 30, 40],
                                                         send=["seen.val={value}"]))
        simulation.advance(20)
        # The wave went on from its place, with its new values and instruction.
        self.assertEqual(self.received(simulation), ["temp.val=1", "seen.val=20"])
        chart = settings(waveforms=[{"page": "page0", "waveform": "chart"}])
        with self.assertRaisesRegex(NxwrightError, "^generator 1 is a value generator, so it "
                                                   "cannot take the settings of a waveform "
                                                   "generator$"):
            simulation.change_generator(number, chart)
        other = simulation.start_generator(chart)
        with self.assertRaisesRegex(NxwrightError, "^generator 2 is a waveform generator, so it "
                                                   "cannot take the settings of a value "
                                                   "generator$"):
            simulation.change_generator(other, self.feeding())
        self.assertEqual(simulation.generators(), {1: self.feeding(
            values=[10, 20, 30, 40], send=["seen.val={value}"]), 2: chart})

    def test_generators_of_both_kinds_send_in_the_order_of_their_numbers(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.feeding(send=["add chart.id,0,{value}"], values=[1]))
        simulation.start_generator(settings(waveforms=[{"page": "page0", "waveform": "chart"}],
                                            shape="custom", values=[2], interval=20))
        simulation.start_generator(self.feeding(send=["add chart.id,0,{value}"], values=[3]))
        simulation.advance(40)
        self.assertEqual(simulation.waves(), {"chart": {0: [1, 2, 3, 1, 2, 3]}})

    def test_a_conditions_click_runs_an_event_that_reads_the_points_value(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.feeding(conditions=[
            {"turnsOnAbove": 6, "whenOn": ["click refresh,1"]}]))
        simulation.advance(40)
        # At the second point, the value is set, then the condition clicks.
        self.assertEqual(self.received(simulation),
                         ["temp.val=5", "temp.val=7", "click refresh,1"])
        self.assertEqual(self.value(simulation, "seen"), 7)
        self.assertIn("value generator 1 starts, sending temp.val={value}, with 1 condition",
                      [line for _, line in simulation.log])

    def test_a_start_of_the_app_has_a_condition_send_its_instructions_again(self):
        simulation = Simulation(self.root)
        simulation.start_generator(generator_settings(
            {"kind": "value", "shape": "custom", "values": [7], "interval": 20,
             "conditions": [{"turnsOnAbove": 6, "whenOn": ["seen.val={value}"]}]}, "test"))
        simulation.advance(60)
        self.assertEqual(self.received(simulation), ["seen.val=7"])
        simulation.start_again()
        self.assertEqual(self.value(simulation, "seen"), 0)
        simulation.advance(20)
        self.assertEqual(self.value(simulation, "seen"), 7)

    def test_a_generator_stopped_inside_a_point_sends_the_rest_of_that_point_alone(self):
        # The debugger can hold the simulation inside the code an instruction
        # runs, and the panel can stop the generator meanwhile. The point
        # under way was settled before it was sent, so its instructions
        # still go, and nothing follows them.
        simulation = Simulation(self.root)
        number = simulation.start_generator(self.feeding(
            send=["temp.val={value}", "seen.val={value}"]))
        arrived = Simulation._serial_arrived
        stopped = []

        def stop_at_the_first(simulation):
            arrived(simulation)
            if not stopped:
                stopped.append(True)
                simulation.stop_generator(number)

        with mock.patch.object(Simulation, "_serial_arrived", autospec=True,
                               side_effect=stop_at_the_first):
            simulation.advance(100)
        self.assertEqual(self.received(simulation), ["temp.val=5", "seen.val=5"])
        self.assertEqual(simulation.generators(), {})


if __name__ == "__main__":
    unittest.main()
