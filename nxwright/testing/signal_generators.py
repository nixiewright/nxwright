"""A signal generator stands in for a device on the serial line that
sends values to a simulation, following a wave. A simulation
(simulation.py) can run any number of generators, and each generator's kind
decides what it sends. A settings file lists one or more generators in
JSON, such as:

    {"nxwrightSignals": 1,
     "generators": [{"kind": "waveform",
                     "waveforms": [{"page": "day", "waveform": "chart"}],
                     "interval": 20, "shape": "sine", "maximum": 200,
                     "channels": [{"channel": 0},
                                  {"channel": 1, "shape": "square"}]},
                    {"kind": "value",
                     "send": ["temp.val={value}", "click refresh,1"],
                     "onlyWhenChanged": true,
                     "minimum": 180, "maximum": 240, "interval": 1000,
                     "conditions": [{"turnsOnAbove": 220, "turnsOffBelow": 210,
                                     "afterMs": 500,
                                     "whenOn": ["click alarm,1"],
                                     "whenOff": ["click alarm,0"]}]}]}

A waveform generator, whose kind is "waveform", sends points to one or more
waveforms, each named by its page and its name. It sends one point per
interval on each of its channels, in the shape of the channel's wave. A
channel uses the generator's settings, except the ones it sets itself.

A value generator, whose kind is "value", stands for a device that sets a
value the app's code reads. At each point of its one wave, it sends the
instructions of its `send` list, with `{value}` replaced by the point's
value. With `onlyWhenChanged`, it sends them only at a point whose value
differs from the value last sent.

A value generator can also list `conditions`, and then needs no `send`. A
condition is a switch that the wave's value turns on and off. Each time the
switch changes, the condition sends instructions: those of its `whenOn`
list when the switch turns on, and those of its `whenOff` list when it turns
off. The switch starts off, and turns on when the value goes above
`turnsOnAbove`, or below `turnsOnBelow`. It turns off when the value
comes back below `turnsOffBelow`, or above `turnsOffAbove`. Without that
second level, it turns off as soon as the value is no longer past the first.
Setting the second level apart from the first keeps a value that wavers
around the first from turning the switch on and off again and again. With
`afterMs`, a change waits until the value has been past its level at every
point for that many milliseconds. Conditions are checked at every point,
even one that `onlyWhenChanged` skips.

The shapes, at a position in their cycle from 0 up to 1:
  - "sine": from the minimum up to the maximum and back;
  - "square": the maximum for the first half of the cycle, then the
    minimum;
  - "triangle": from the minimum up to the maximum, then back down, in
    straight lines;
  - "sawtooth": from the minimum up to the maximum, then back at once;
  - "inverted-sawtooth": from the maximum down to the minimum, then back
    at once;
  - "pulse": the maximum for the first `duty` percent of the cycle, then
    the minimum;
  - "random": a new value at each point, between the minimum and the
    maximum, as the Nextion Editor's generator gives with Random checked;
  - "custom": the values of its list, one per point, in a loop.

Each channel starts a quarter of its cycle further on than the channel
before it: channel 1 a quarter in, channel 2 half way, channel 3 three
quarters. This keeps channels with the same wave from drawing over each
other. A custom wave starts a quarter of its list further on in the same
way.

Noise adds to each point a random amount, from -noise to +noise, then keeps
the point within the bounds of its generator's kind: 0 to 255 for a
waveform's point, and a whole number of 32 bits for a value. Random values
and noise come from the generator's own random number generator, which is
seeded the same way each time the generator starts, so the same settings
always send the same points.
"""
from dataclasses import dataclass, field
from fractions import Fraction
import json
import math
from pathlib import Path
import random
import re

from nxwright import NxwrightError

# The version of the settings' JSON form.
FORMAT_VERSION = 1
# The key that holds the version, and tells a settings file apart, and the
# key that holds the generators.
_FORMAT_KEY = "nxwrightSignals"
_GENERATORS_KEY = "generators"
# The key that holds a generator's kind, the kind that sends points to
# waveforms, and the kind that sends instructions carrying a value.
_KIND_KEY = "kind"
WAVEFORM = "waveform"
VALUE = "value"

SHAPES = ("sine", "square", "triangle", "sawtooth", "inverted-sawtooth", "pulse", "random",
          "custom")
# The highest channel a waveform has.
_LAST_CHANNEL = 3
# The lowest and the highest value a generator of each kind sends. A
# waveform's point fits in one byte, the size of each value a device sends
# with `addt`. A value is a whole number of 32 bits, the size of a
# component's `val`.
_BOUNDS = {WAVEFORM: (0, 255), VALUE: (-2 ** 31, 2 ** 31 - 1)}
# A wave's settings when neither the generator nor its channel gives them.
# The minimum and the maximum are the same as in the Nextion Editor's
# generator.
WAVE_DEFAULTS = {"shape": "sine", "minimum": 0, "maximum": 100, "interval": 50, "period": 50,
                 "duty": 50, "noise": 0, "values": ()}
# Where a generator's random numbers start, each time it starts.
_SEED = 0
# A name between braces in an instruction, and the one name an instruction
# can use, which stands for the value of the wave's point.
_BRACED_NAME = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_VALUE_NAME = "value"
# The keys of a condition's two levels, (turns on, turns off). True gives
# the keys of a condition that turns on above its level, and False those
# of one that turns on below it.
_LEVEL_KEYS = {True: ("turnsOnAbove", "turnsOffBelow"), False: ("turnsOnBelow", "turnsOffAbove")}


@dataclass(frozen=True)
class Wave:
    """A wave, every setting known."""
    shape: str
    minimum: int
    maximum: int
    interval: int       # milliseconds between two points
    period: int         # points in one cycle
    duty: int           # a pulse's percentage of the cycle at the maximum
    noise: int
    values: tuple       # a custom wave's values, in order


@dataclass(frozen=True)
class WaveformName:
    """A waveform, by its page and its name."""
    page: str
    waveform: str


@dataclass(frozen=True)
class ChannelSettings:
    """A channel a generator feeds, and the settings it gives itself."""
    channel: int
    own: dict = field(default_factory=dict)


@dataclass(frozen=True)
class WaveformGeneratorSettings:
    """A waveform generator's settings: the waveforms it feeds, its
    channels, and the settings its channels share (`shared`)."""
    waveforms: tuple
    channels: tuple
    shared: dict = field(default_factory=dict)
    kind = WAVEFORM

    def wave(self, channel: ChannelSettings) -> Wave:
        """Returns the wave of `channel`, one of the generator's: its own
        settings over the generator's, over WAVE_DEFAULTS."""
        return _whole_wave(self.shared, channel.own)

    def started(self, now: int) -> "WaveformGeneratorRun":
        """Returns the generator running from the simulation's time `now`."""
        return WaveformGeneratorRun(self, now)

    def sends(self) -> str:
        """Returns what the generator sends, in the words of the log's line
        about its start."""
        return "sending to channel%s %s of %s" % (
            "s" if len(self.channels) > 1 else "",
            ", ".join(str(channel.channel) for channel in self.channels),
            ", ".join("%s.%s" % (name.page, name.waveform) for name in self.waveforms))

    def json_form(self) -> dict:
        """Returns the settings in the form a settings file uses."""
        given = {_KIND_KEY: self.kind,
                 "waveforms": [{"page": name.page, "waveform": name.waveform}
                               for name in self.waveforms]}
        given.update(_json_settings(self.shared))
        given["channels"] = [dict({"channel": channel.channel}, **_json_settings(channel.own))
                             for channel in self.channels]
        return given


@dataclass(frozen=True)
class Condition:
    """A condition of a value generator: a switch that the wave's value
    turns on and off. It turns on when the value goes past `on_level`:
    above it when `above`, and below it otherwise. It turns off when the
    value comes back past `off_level`. If `off_level` is None, it turns off
    as soon as the value is no longer past `on_level`. A change waits until the value has
    stayed past the level for `after` milliseconds. `when_on` and `when_off`
    are the instructions sent when the switch turns on and off."""
    above: bool
    on_level: int
    off_level: int = None
    after: int = 0
    when_on: tuple = ()
    when_off: tuple = ()

    def calls_for_change(self, on: bool, value: int) -> bool:
        """Returns whether `value` calls for the switch to change, that is,
        to turn on if `on` is false, and to turn off if `on` is true."""
        past = value > self.on_level if self.above else value < self.on_level
        if not on:
            return past
        if self.off_level is None:
            return not past
        return value < self.off_level if self.above else value > self.off_level

    def json_form(self) -> dict:
        """Returns the condition in the form a settings file uses."""
        on_key, off_key = _LEVEL_KEYS[self.above]
        given = {on_key: self.on_level}
        if self.off_level is not None:
            given[off_key] = self.off_level
        if self.after:
            given["afterMs"] = self.after
        if self.when_on:
            given["whenOn"] = list(self.when_on)
        if self.when_off:
            given["whenOff"] = list(self.when_off)
        return given


@dataclass(frozen=True)
class ValueGeneratorSettings:
    """A value generator's settings: the instructions it sends at each
    point (`send`), whether it sends them only at a point whose value
    differs from the value last sent, the wave settings it gives itself
    (`own`), and its conditions."""
    send: tuple
    only_when_changed: bool = False
    own: dict = field(default_factory=dict)
    conditions: tuple = ()
    kind = VALUE

    def wave(self) -> Wave:
        """Returns the generator's wave: its own settings, and WAVE_DEFAULTS
        for the others."""
        return _whole_wave(self.own)

    def started(self, now: int) -> "ValueGeneratorRun":
        """Returns the generator running from the simulation's time `now`."""
        return ValueGeneratorRun(self, now)

    def sends(self) -> str:
        """Returns what the generator sends, in the words of the log's line
        about its start."""
        told = []
        if self.send:
            told.append("sending %s" % "; ".join(self.send))
        if self.conditions:
            told.append("with %d condition%s" % (len(self.conditions),
                                                 "s" if len(self.conditions) > 1 else ""))
        return ", ".join(told)

    def json_form(self) -> dict:
        """Returns the settings in the form a settings file uses."""
        given = {_KIND_KEY: self.kind}
        if self.send:
            given["send"] = list(self.send)
        if self.only_when_changed:
            given["onlyWhenChanged"] = True
        given.update(_json_settings(self.own))
        if self.conditions:
            given["conditions"] = [condition.json_form() for condition in self.conditions]
        return given


def wave_value(wave: Wave, position: Fraction) -> int:
    """Returns the value of `wave` at `position` in its cycle, from 0 up to
    1, before noise. Not for "random" or "custom", whose values do not
    follow a position."""
    low, high = wave.minimum, wave.maximum
    span = high - low
    if wave.shape == "sine":
        # From the minimum at 0, as the Nextion Editor's generator starts.
        # The level is rounded because math libraries differ in the last
        # digits: one may give exactly a half where another gives a hair
        # less. Rounding makes each point the same on every computer.
        level = round((1 - math.cos(2 * math.pi * position)) / 2, 9)
    elif wave.shape == "square":
        level = 1 if position < Fraction(1, 2) else 0
    elif wave.shape == "triangle":
        level = 2 * position if position < Fraction(1, 2) else 2 - 2 * position
    elif wave.shape == "sawtooth":
        level = position
    elif wave.shape == "inverted-sawtooth":
        level = 1 - position
    elif wave.shape == "pulse":
        level = 1 if position < Fraction(wave.duty, 100) else 0
    else:
        raise ValueError("a %s wave has no value at a position" % wave.shape)
    return low + math.floor(span * level + Fraction(1, 2))


def instruction_with(text: str, value: int) -> str:
    """Returns the instruction `text` with each `{value}` replaced by
    `value`, in decimal. Other braces stay as they are."""
    return text.replace("{%s}" % _VALUE_NAME, str(value))


class WaveRun:
    """A running wave: where it is in its cycle, and when its next point is
    due. It starts `quarters` quarters of its cycle in. Its points are kept
    within `bounds`, the lowest and the highest value its generator sends."""

    def __init__(self, wave: Wave, quarters: int, due: int, bounds: tuple):
        self.wave = wave
        # Where it is in its cycle, from 0 up to 1, and a custom wave's place
        # in its list.
        self.position = Fraction(quarters, 4) % 1
        self.index = len(wave.values) * quarters // 4
        self.due = due          # the simulation's time of its next point
        self._bounds = bounds

    def next_value(self, rng: random.Random) -> int:
        """Returns the wave's next point, and moves the wave on."""
        wave = self.wave
        if wave.shape == "random":
            value = rng.randint(wave.minimum, wave.maximum)
        elif wave.shape == "custom":
            value = wave.values[self.index % len(wave.values)]
            self.index = (self.index + 1) % len(wave.values)
        else:
            value = wave_value(wave, self.position)
            self.position = (self.position + Fraction(1, wave.period)) % 1
        if wave.noise:
            value += rng.randint(-wave.noise, wave.noise)
        lowest, highest = self._bounds
        return min(max(value, lowest), highest)

    def change(self, wave: Wave, now: int):
        """Takes a new wave. It goes on from its place in its cycle: a new
        period changes how fast it moves from there. A new interval counts
        from `now`."""
        if wave.interval != self.wave.interval:
            self.due = now + wave.interval
        self.wave = wave


class ChannelRun(WaveRun):
    """A channel of a running waveform generator: its settings and its
    wave. Each channel starts a quarter of its cycle further on than the
    one before."""

    def __init__(self, settings: ChannelSettings, wave: Wave, due: int):
        super().__init__(wave, settings.channel, due, _BOUNDS[WAVEFORM])
        self.settings = settings

    def change(self, settings: ChannelSettings, wave: Wave, now: int):
        """Takes new settings, and their wave (WaveRun.change)."""
        super().change(wave, now)
        self.settings = settings


class WaveformGeneratorRun:
    """A running waveform generator: its settings, its random numbers, and
    its channels."""

    def __init__(self, settings: WaveformGeneratorSettings, now: int):
        self.settings = settings
        self.random = random.Random(_SEED)
        self.channels = [ChannelRun(channel, settings.wave(channel),
                                    now + settings.wave(channel).interval)
                         for channel in settings.channels]

    def due(self) -> int:
        """Returns the simulation's time of the generator's next points."""
        return min(channel.due for channel in self.channels)

    def tick(self) -> list:
        """Returns the points due now, [(channel, value)], in the order of
        the generator's channels, and counts each channel's next."""
        now = self.due()
        points = []
        for channel in self.channels:
            if channel.due == now:
                points.append((channel.settings.channel, channel.next_value(self.random)))
                channel.due = now + channel.wave.interval
        return points

    def change(self, settings: WaveformGeneratorSettings, now: int):
        """Takes new settings while running. A channel kept keeps its place
        in its wave (ChannelRun.change); a new channel starts its wave, its
        first point one interval from `now`. The random numbers go on."""
        kept = {channel.settings.channel: channel for channel in self.channels}
        channels = []
        for given in settings.channels:
            wave = settings.wave(given)
            run = kept.get(given.channel)
            if run is None:
                run = ChannelRun(given, wave, now + wave.interval)
            else:
                run.change(given, wave, now)
            channels.append(run)
        self.settings, self.channels = settings, channels

    def app_started(self, shift: int):
        """Moves each channel's next point by `shift` milliseconds, the
        amount the simulation's clock moved when the app started again, so
        that the generator keeps its pace."""
        for channel in self.channels:
            channel.due += shift


class ConditionRun:
    """A condition of a running value generator: whether its switch is on,
    and since when the wave's value has called for a change."""

    def __init__(self, condition: Condition):
        self.condition = condition
        self.on = False
        # The simulation's time of the first point in the current run of
        # points that call for a change, or None if the last point did not
        # call for one.
        self.calling_since = None

    def point(self, value: int, now: int) -> list:
        """Takes the wave's point `value`, due at the simulation's time
        `now`. Returns the instructions to send if the switch changes at
        this point, with the value in place of `{value}`, or an empty list
        if it does not change."""
        condition = self.condition
        if not condition.calls_for_change(self.on, value):
            self.calling_since = None
            return []
        if self.calling_since is None:
            self.calling_since = now
        if now - self.calling_since < condition.after:
            return []
        self.on, self.calling_since = not self.on, None
        return [instruction_with(text, value)
                for text in (condition.when_on if self.on else condition.when_off)]

    def turn_off(self):
        """Puts the switch back to off, as it was when the generator
        started, without sending the `when_off` instructions."""
        self.on, self.calling_since = False, None


class ValueGeneratorRun:
    """A running value generator: its settings, its random numbers, its
    wave, the value it last sent, and its conditions."""

    def __init__(self, settings: ValueGeneratorSettings, now: int):
        self.settings = settings
        self.random = random.Random(_SEED)
        wave = settings.wave()
        self._wave = WaveRun(wave, 0, now + wave.interval, _BOUNDS[VALUE])
        # The value the instructions of `send` last carried, or None when
        # none was sent since the generator, or the app, started.
        self._sent = None
        self._conditions = [ConditionRun(condition) for condition in settings.conditions]

    def due(self) -> int:
        """Returns the simulation's time of the generator's next point."""
        return self._wave.due

    def tick(self) -> list:
        """Moves the wave past the point due now, and returns the
        instructions to send for that point, with the point's value in place
        of `{value}`. The instructions of `send` come first, then those of
        each condition that changes at this point, in the conditions' order.
        The wave moves on before the caller sends any of them. So if one of
        them affects the generator, for example by starting the app again,
        the generator is already past this point."""
        now = self._wave.due
        value = self._wave.next_value(self.random)
        self._wave.due = now + self._wave.wave.interval
        instructions = []
        if not (self.settings.only_when_changed and value == self._sent):
            self._sent = value
            instructions += [instruction_with(text, value) for text in self.settings.send]
        # A condition is checked at every point, even one that
        # `onlyWhenChanged` skips.
        for condition in self._conditions:
            instructions += condition.point(value, now)
        return instructions

    def change(self, settings: ValueGeneratorSettings, now: int):
        """Takes new settings while running. The wave keeps its place in its
        cycle (WaveRun.change), and the random numbers go on. A condition
        still at the same place in the list keeps its switch as it is, and
        a new one starts off."""
        self._wave.change(settings.wave(), now)
        kept = self._conditions[:len(settings.conditions)]
        for run, condition in zip(kept, settings.conditions):
            run.condition = condition
        self._conditions = kept + [ConditionRun(condition)
                                   for condition in settings.conditions[len(kept):]]
        self.settings = settings

    def app_started(self, shift: int):
        """Moves the next point by `shift` milliseconds, the amount the
        simulation's clock moved when the app started again, so that the
        generator keeps its pace. The screen has lost what it was sent, so
        the generator also forgets the value it last sent and turns every
        condition's switch back to off. The next point is then sent whatever
        its value, and each switch turns on again if the value is still past
        its level."""
        self._wave.due += shift
        self._sent = None
        for condition in self._conditions:
            condition.turn_off()


def generators_from_json(text: str, source: str) -> tuple:
    """Returns the settings of each generator in `text`, a settings file's
    text, in the file's order. Raises NxwrightError if the text is not a
    settings file, or if a setting cannot be used. The error starts with
    `source`, the file's name, and gives the setting's place."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise NxwrightError("%s: not JSON: %s" % (source, error)) from None
    if not isinstance(data, dict) or _FORMAT_KEY not in data:
        raise NxwrightError("%s: not a signal generator settings file" % source)
    if data[_FORMAT_KEY] != FORMAT_VERSION:
        raise NxwrightError("%s: %s %r is not a version nxwright reads; it reads %d"
                            % (source, _FORMAT_KEY, data[_FORMAT_KEY], FORMAT_VERSION))
    generators = data.get(_GENERATORS_KEY)
    if not isinstance(generators, list) or not generators:
        raise NxwrightError("%s: %s must list one generator or more" % (source, _GENERATORS_KEY))
    return tuple(generator_settings(given, "%s: %s[%d]" % (source, _GENERATORS_KEY, number))
                 for number, given in enumerate(generators))


def read_generators_file(path: Path) -> tuple:
    """Returns the settings of each generator of the settings file `path`.
    Raises NxwrightError for a file that cannot be read or used."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise NxwrightError("the signal generator settings file %s cannot be read: %s"
                            % (path, getattr(error, "strerror", None) or error)) from None
    return generators_from_json(text, str(path))


def generators_to_json(generators) -> str:
    """Returns the text of a settings file that contains `generators`, the
    settings of each generator. generators_from_json reads the text back to
    the same settings."""
    return json.dumps({_FORMAT_KEY: FORMAT_VERSION,
                       _GENERATORS_KEY: [settings.json_form() for settings in generators]},
                      indent=2) + "\n"


def generator_settings(given, where: str):
    """Returns the settings of `given`, a generator's JSON form: a
    WaveformGeneratorSettings or a ValueGeneratorSettings, by its kind.
    Raises NxwrightError for a kind this version of nxwright does not know,
    or for a setting that cannot be used. The error starts with `where`,
    followed by the setting's place in `given`."""
    if not isinstance(given, dict):
        raise NxwrightError("%s: a generator must be a JSON object" % where)
    kind = given.get(_KIND_KEY)
    # Only a text can be a kind. A list or an object cannot be looked up in
    # _READERS.
    read = _READERS.get(kind) if isinstance(kind, str) else None
    if read is None:
        raise NxwrightError("%s: %s" % (where, _kind_refusal(given)))
    return read(given, where)


def _kind_refusal(given: dict) -> str:
    """Returns why the kind of `given`, a generator's JSON form, cannot be
    used: it is missing, or this version of nxwright does not know it."""
    if _KIND_KEY not in given:
        return "a generator must give its kind, as %s" % " or ".join(
            '"%s": "%s"' % (_KIND_KEY, kind) for kind in _READERS)
    # A later version of nxwright may know more kinds. The refusal gives
    # the kind, so that the user can tell a file from a later version apart
    # from a damaged one.
    return "%s %r is not a kind of generator this version of nxwright knows. It knows %s" % (
        _KIND_KEY, given[_KIND_KEY], " and ".join(_READERS))


def _waveform_generator_settings(given: dict, where: str) -> WaveformGeneratorSettings:
    _refuse_unknown(given, set(WAVE_DEFAULTS) | {_KIND_KEY, "waveforms", "channels"}, where)
    waveforms = given.get("waveforms")
    if not isinstance(waveforms, list) or not waveforms:
        raise NxwrightError("%s: waveforms must list one waveform or more" % where)
    names = tuple(_waveform_name(name, "%s.waveforms[%d]" % (where, number))
                  for number, name in enumerate(waveforms))
    if len(set(names)) != len(names):
        raise NxwrightError("%s: waveforms lists a waveform twice" % where)
    shared = _wave_settings(given, where, WAVEFORM)
    channels = given.get("channels")
    if not isinstance(channels, list) or not channels:
        raise NxwrightError("%s: channels must list one channel or more" % where)
    settings = WaveformGeneratorSettings(names, tuple(
        _channel_settings(channel, "%s.channels[%d]" % (where, number))
        for number, channel in enumerate(channels)), shared)
    numbers = [channel.channel for channel in settings.channels]
    if len(set(numbers)) != len(numbers):
        raise NxwrightError("%s: channels lists a channel twice" % where)
    for number, channel in enumerate(settings.channels):
        _check_wave(settings.wave(channel), "%s.channels[%d]" % (where, number))
    return settings


def _value_generator_settings(given: dict, where: str) -> ValueGeneratorSettings:
    _refuse_unknown(given, set(WAVE_DEFAULTS) | {_KIND_KEY, "send", "onlyWhenChanged",
                                                 "conditions"}, where)
    send = _instructions(given.get("send"), "%s.send" % where)
    conditions = _conditions(given.get("conditions"), "%s.conditions" % where)
    if not send and not conditions:
        raise NxwrightError("%s: a value generator needs an instruction in send, or a "
                            "condition" % where)
    only_when_changed = given.get("onlyWhenChanged", False)
    if not isinstance(only_when_changed, bool):
        raise NxwrightError("%s: onlyWhenChanged must be true or false" % where)
    settings = ValueGeneratorSettings(send, only_when_changed,
                                      _wave_settings(given, where, VALUE), conditions)
    _check_wave(settings.wave(), where)
    return settings


# What reads a generator's JSON form, by its kind.
_READERS = {WAVEFORM: _waveform_generator_settings, VALUE: _value_generator_settings}


def _instructions(given, where: str) -> tuple:
    """Returns the instructions that `given` lists, none when `given` is
    None. Raises NxwrightError, starting with `where` and the instruction's
    place, for anything but a list of instructions. An instruction is one
    line of text, not empty, and the only name it can have between braces is
    `{value}`. Any other name is refused, so that a later version can give
    more names a meaning."""
    if given is None:
        return ()
    if not isinstance(given, list):
        raise NxwrightError("%s must be a list of instructions" % where)
    for number, text in enumerate(given):
        place = "%s[%d]" % (where, number)
        if not isinstance(text, str) or not text.strip() or "\n" in text or "\r" in text:
            raise NxwrightError("%s: an instruction is one line of text, and not empty" % place)
        for name in _BRACED_NAME.findall(text):
            if name != _VALUE_NAME:
                raise NxwrightError("%s: {%s} is not a name an instruction can use. It can "
                                    "use {%s}" % (place, name, _VALUE_NAME))
    return tuple(given)


def _conditions(given, where: str) -> tuple:
    """Returns the conditions that `given` lists, or none if `given` is
    None. Raises NxwrightError for anything but a list of conditions. The
    error's message starts with `where` and the condition's place in the
    list."""
    if given is None:
        return ()
    if not isinstance(given, list):
        raise NxwrightError("%s must be a list of conditions" % where)
    return tuple(_condition(one, "%s[%d]" % (where, number))
                 for number, one in enumerate(given))


def _condition(given, where: str) -> Condition:
    if not isinstance(given, dict):
        raise NxwrightError("%s: a condition must be a JSON object" % where)
    on_keys = [keys[0] for keys in _LEVEL_KEYS.values()]
    off_keys = [keys[1] for keys in _LEVEL_KEYS.values()]
    _refuse_unknown(given, {*on_keys, *off_keys, "afterMs", "whenOn", "whenOff"}, where)
    if sum(key in given for key in on_keys) != 1:
        raise NxwrightError("%s: a condition needs %s or %s, and not both"
                            % (where, *on_keys))
    above = on_keys[0] in given
    on_key, off_key = _LEVEL_KEYS[above]
    other_on, other_off = _LEVEL_KEYS[not above]
    if other_off in given:
        raise NxwrightError("%s: %s goes with %s. With %s, give %s"
                            % (where, other_off, other_on, on_key, off_key))
    on_level = _level(given, on_key, where)
    off_level = _level(given, off_key, where) if off_key in given else None
    if off_level is not None and (off_level > on_level if above else off_level < on_level):
        raise NxwrightError("%s: %s %d is %s %s %d" % (
            where, off_key, off_level, "above" if above else "below", on_key, on_level))
    after = given.get("afterMs", 0)
    if not _is_whole(after) or after < 0:
        raise NxwrightError("%s: afterMs must be a whole number of 0 or more" % where)
    when_on = _instructions(given.get("whenOn"), "%s.whenOn" % where)
    when_off = _instructions(given.get("whenOff"), "%s.whenOff" % where)
    if not when_on and not when_off:
        raise NxwrightError("%s: a condition needs an instruction in whenOn or whenOff"
                            % where)
    return Condition(above, on_level, off_level, after, when_on, when_off)


def _level(given: dict, key: str, where: str) -> int:
    """Returns the level `given` has under `key`. Raises NxwrightError for
    anything but a whole number a value can be."""
    lowest, highest = _BOUNDS[VALUE]
    level = given[key]
    if not _is_whole(level) or not lowest <= level <= highest:
        raise NxwrightError("%s: %s must be a whole number from %d to %d"
                            % (where, key, lowest, highest))
    return level


def _waveform_name(given, where: str) -> WaveformName:
    if not isinstance(given, dict) or set(given) != {"page", "waveform"} or not all(
            isinstance(given[key], str) and given[key] for key in given):
        raise NxwrightError('%s: a waveform is named as {"page": "...", "waveform": "..."}'
                            % where)
    return WaveformName(given["page"], given["waveform"])


def _channel_settings(given, where: str) -> ChannelSettings:
    if not isinstance(given, dict):
        raise NxwrightError("%s: a channel must be a JSON object" % where)
    _refuse_unknown(given, set(WAVE_DEFAULTS) | {"channel"}, where)
    channel = given.get("channel")
    if not _is_whole(channel) or not 0 <= channel <= _LAST_CHANNEL:
        raise NxwrightError("%s: channel must be from 0 to %d" % (where, _LAST_CHANNEL))
    return ChannelSettings(channel, _wave_settings(given, where, WAVEFORM))


def _wave_settings(given: dict, where: str, kind: str) -> dict:
    """Returns the wave's settings that `given` gives, each checked alone.
    The wave's values must be within the bounds of a generator of `kind`."""
    lowest, highest = _BOUNDS[kind]
    settings = {}
    for key, low, high in (("minimum", lowest, highest), ("maximum", lowest, highest),
                           ("interval", 1, None), ("period", 1, None), ("duty", 0, 100),
                           ("noise", 0, highest)):
        if key in given:
            value = given[key]
            if not _is_whole(value) or value < low or (high is not None and value > high):
                raise NxwrightError("%s: %s must be a whole number %s" % (
                    where, key, "from %d to %d" % (low, high) if high is not None
                    else "of %d or more" % low))
            settings[key] = value
    if "shape" in given:
        if given["shape"] not in SHAPES:
            raise NxwrightError("%s: shape %r is not a shape; the shapes are %s"
                                % (where, given["shape"], ", ".join(SHAPES)))
        settings["shape"] = given["shape"]
    if "values" in given:
        values = given["values"]
        if not isinstance(values, list) or not all(
                _is_whole(value) and lowest <= value <= highest for value in values):
            raise NxwrightError("%s: values must be a list of whole numbers from %d to %d"
                                % (where, lowest, highest))
        settings["values"] = tuple(values)
    return settings


def _whole_wave(*given) -> Wave:
    """Returns the wave that the settings `given` make, starting from
    WAVE_DEFAULTS. Each dict of settings overrides those before it."""
    settings = dict(WAVE_DEFAULTS)
    for own in given:
        settings.update(own)
    settings["values"] = tuple(settings["values"])
    return Wave(**settings)


def _check_wave(wave: Wave, where: str):
    """Raises NxwrightError for settings that are each right but do not go
    together."""
    if wave.shape == "custom":
        # Its values are played as given: the minimum and the maximum do
        # not apply to it.
        if not wave.values:
            raise NxwrightError("%s: a custom wave needs values" % where)
    elif wave.minimum > wave.maximum:
        raise NxwrightError("%s: minimum %d is above maximum %d"
                            % (where, wave.minimum, wave.maximum))


def _refuse_unknown(given: dict, known: set, where: str):
    unknown = sorted(set(given) - known)
    if unknown:
        raise NxwrightError("%s: %s is not a setting" % (where, unknown[0]))


def _is_whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _json_settings(settings: dict) -> dict:
    """Returns wave settings as their JSON form gives them: a custom wave's
    values as a list."""
    return {key: list(value) if key == "values" else value for key, value in settings.items()}
