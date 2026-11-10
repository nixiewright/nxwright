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
                     "minimum": 180, "maximum": 240, "interval": 1000}]}

A waveform generator, whose kind is "waveform", sends points to one or more
waveforms, each named by its page and its name. It sends one point per
interval on each of its channels, in the shape of the channel's wave. A
channel uses the generator's settings, except the ones it sets itself.

A value generator, whose kind is "value", stands for a device that sets a
value the app's code reads. At each point of its one wave, it sends the
instructions of its `send` list, with `{value}` replaced by the point's
value. With `onlyWhenChanged`, it sends them only at a point whose value
differs from the value last sent.

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
class ValueGeneratorSettings:
    """A value generator's settings: the instructions it sends at each
    point (`send`), whether it sends them only at a point whose value
    differs from the value last sent, and the wave settings it gives itself
    (`own`)."""
    send: tuple
    only_when_changed: bool = False
    own: dict = field(default_factory=dict)
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
        return "sending %s" % "; ".join(self.send)

    def json_form(self) -> dict:
        """Returns the settings in the form a settings file uses."""
        given = {_KIND_KEY: self.kind, "send": list(self.send)}
        if self.only_when_changed:
            given["onlyWhenChanged"] = True
        given.update(_json_settings(self.own))
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

    def shift(self, by: int):
        """Moves the time of each channel's next point by `by`
        milliseconds, as the simulation's clock starts again from 0."""
        for channel in self.channels:
            channel.due += by

    def app_started(self):
        """The app started again. A waveform generator keeps nothing of what
        it sent the screen, so nothing changes."""


class ValueGeneratorRun:
    """A running value generator: its settings, its random numbers, its
    wave, and the value it last sent."""

    def __init__(self, settings: ValueGeneratorSettings, now: int):
        self.settings = settings
        self.random = random.Random(_SEED)
        wave = settings.wave()
        self._wave = WaveRun(wave, 0, now + wave.interval, _BOUNDS[VALUE])
        # The value the instructions of `send` last carried, or None when
        # none was sent since the generator, or the app, started.
        self._sent = None

    def due(self) -> int:
        """Returns the simulation's time of the generator's next point."""
        return self._wave.due

    def tick(self) -> list:
        """Moves the wave past the point due now, and returns the
        instructions to send for that point, in order, with the point's
        value in place of `{value}`. Because the run moves on before the
        caller sends any of them, an instruction that affects the generator,
        such as one that starts the app again, finds it already past this
        point."""
        value = self._wave.next_value(self.random)
        self._wave.due += self._wave.wave.interval
        if self.settings.only_when_changed and value == self._sent:
            return []
        self._sent = value
        return [instruction_with(text, value) for text in self.settings.send]

    def change(self, settings: ValueGeneratorSettings, now: int):
        """Takes new settings while running. The wave keeps its place in its
        cycle (WaveRun.change), and the random numbers go on."""
        self._wave.change(settings.wave(), now)
        self.settings = settings

    def shift(self, by: int):
        """Moves the time of the next point by `by` milliseconds, as the
        simulation's clock starts again from 0."""
        self._wave.due += by

    def app_started(self):
        """The app started again, so the screen has lost what it was sent.
        The generator forgets the value it last sent, and so sends its next
        point whatever its value."""
        self._sent = None


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
    _refuse_unknown(given, set(WAVE_DEFAULTS) | {_KIND_KEY, "send", "onlyWhenChanged"}, where)
    send = _instructions(given.get("send"), "%s.send" % where)
    if not send:
        raise NxwrightError("%s: send must list one instruction or more" % where)
    only_when_changed = given.get("onlyWhenChanged", False)
    if not isinstance(only_when_changed, bool):
        raise NxwrightError("%s: onlyWhenChanged must be true or false" % where)
    settings = ValueGeneratorSettings(send, only_when_changed,
                                      _wave_settings(given, where, VALUE))
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
