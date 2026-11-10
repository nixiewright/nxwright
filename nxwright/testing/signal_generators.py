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
                                  {"channel": 1, "shape": "square"}]}]}

A waveform generator, whose kind is "waveform", sends points to one or more
waveforms, each named by its page and its name. It sends one point per
interval on each of its channels, in the shape of the channel's wave. A
channel uses the generator's settings, except the ones it sets itself.

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
the point between 0 and 255. Random values and noise come from the
generator's own random number generator, which is seeded the same way each
time the generator starts, so the same settings always send the same
points.
"""
from dataclasses import dataclass, field
from fractions import Fraction
import json
import math
from pathlib import Path
import random

from nxwright import NxwrightError

# The version of the settings' JSON form.
FORMAT_VERSION = 1
# The key that holds the version, and tells a settings file apart, and the
# key that holds the generators.
_FORMAT_KEY = "nxwrightSignals"
_GENERATORS_KEY = "generators"
# The key that holds a generator's kind, and the kind that sends points to
# waveforms.
_KIND_KEY = "kind"
WAVEFORM = "waveform"

SHAPES = ("sine", "square", "triangle", "sawtooth", "inverted-sawtooth", "pulse", "random",
          "custom")
# The highest channel a waveform has, and the highest value a point takes:
# the values a device sends as one byte each with `addt`.
_LAST_CHANNEL = 3
_LARGEST_VALUE = 255
# A wave's settings when neither the generator nor its channel gives them.
# The minimum and the maximum are the same as in the Nextion Editor's
# generator.
WAVE_DEFAULTS = {"shape": "sine", "minimum": 0, "maximum": 100, "interval": 50, "period": 50,
                 "duty": 50, "noise": 0, "values": ()}
# Where a generator's random numbers start, each time it starts.
_SEED = 0


@dataclass(frozen=True)
class Wave:
    """A channel's wave, every setting known."""
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
        settings = {**WAVE_DEFAULTS, **self.shared, **channel.own}
        settings["values"] = tuple(settings["values"])
        return Wave(**settings)


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


class ChannelRun:
    """A channel of a running generator: where its wave is, and when its
    next point is due."""

    def __init__(self, settings: ChannelSettings, wave: Wave, due: int):
        self.settings, self.wave = settings, wave
        # Where it is in its cycle, from 0 up to 1, and a custom wave's place
        # in its list: each channel a quarter further on than the one before.
        self.position = Fraction(settings.channel, 4) % 1
        self.index = len(wave.values) * settings.channel // 4
        self.due = due          # the simulation's time of its next point

    def next_value(self, rng: random.Random) -> int:
        """Returns the channel's next point, and moves its wave on."""
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
        return min(max(value, 0), _LARGEST_VALUE)

    def change(self, settings: ChannelSettings, wave: Wave, now: int):
        """Takes new settings. The wave goes on from its place in its cycle:
        a new period changes how fast it moves from there. A new interval
        counts from `now`."""
        if wave.interval != self.wave.interval:
            self.due = now + wave.interval
        self.settings, self.wave = settings, wave


class WaveformGeneratorRun:
    """A running waveform generator: its settings, its random numbers, and
    its channels."""

    def __init__(self, settings: WaveformGeneratorSettings, now: int):
        self.settings = settings
        self.random = random.Random(_SEED)
        self.channels = [ChannelRun(channel, settings.wave(channel),
                                    now + settings.wave(channel).interval)
                         for channel in settings.channels]
        # Whether the log said that its points are held (simulation.py).
        self.held_noted = False

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
                       _GENERATORS_KEY: [generator_dict(settings) for settings in generators]},
                      indent=2) + "\n"


def generator_dict(settings: WaveformGeneratorSettings) -> dict:
    """Returns a generator's settings in the form a settings file uses."""
    given = {_KIND_KEY: settings.kind,
             "waveforms": [{"page": name.page, "waveform": name.waveform}
                           for name in settings.waveforms]}
    given.update(_json_settings(settings.shared))
    given["channels"] = [dict({"channel": channel.channel}, **_json_settings(channel.own))
                         for channel in settings.channels]
    return given


def generator_settings(given, where: str) -> WaveformGeneratorSettings:
    """Returns the settings of `given`, a generator's JSON form. Raises
    NxwrightError for a kind this version of nxwright does not know, or for
    a setting that cannot be used. The error starts with `where`, followed
    by the setting's place in `given`."""
    if not isinstance(given, dict):
        raise NxwrightError("%s: a generator must be a JSON object" % where)
    if given.get(_KIND_KEY) != WAVEFORM:
        raise NxwrightError("%s: %s" % (where, _kind_refusal(given)))
    return _waveform_generator_settings(given, where)


def _kind_refusal(given: dict) -> str:
    """Returns why the kind of `given`, a generator's JSON form, cannot be
    used: it is missing, or this version of nxwright does not know it."""
    if _KIND_KEY not in given:
        return 'a generator must give its kind, as "%s": "%s"' % (_KIND_KEY, WAVEFORM)
    # A later version of nxwright may know more kinds. The refusal gives
    # the kind, so that the user can tell a file from a later version apart
    # from a damaged one.
    return "%s %r is not a kind of generator this version of nxwright knows. It knows %s" % (
        _KIND_KEY, given[_KIND_KEY], WAVEFORM)


def _waveform_generator_settings(given: dict, where: str) -> WaveformGeneratorSettings:
    _refuse_unknown(given, set(WAVE_DEFAULTS) | {_KIND_KEY, "waveforms", "channels"}, where)
    waveforms = given.get("waveforms")
    if not isinstance(waveforms, list) or not waveforms:
        raise NxwrightError("%s: waveforms must list one waveform or more" % where)
    names = tuple(_waveform_name(name, "%s.waveforms[%d]" % (where, number))
                  for number, name in enumerate(waveforms))
    if len(set(names)) != len(names):
        raise NxwrightError("%s: waveforms lists a waveform twice" % where)
    shared = _wave_settings(given, where)
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
    return ChannelSettings(channel, _wave_settings(given, where))


def _wave_settings(given: dict, where: str) -> dict:
    """Returns the wave's settings `given` gives, each checked alone."""
    settings = {}
    for key, low, high in (("minimum", 0, _LARGEST_VALUE), ("maximum", 0, _LARGEST_VALUE),
                           ("interval", 1, None), ("period", 1, None), ("duty", 0, 100),
                           ("noise", 0, _LARGEST_VALUE)):
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
                _is_whole(value) and 0 <= value <= _LARGEST_VALUE for value in values):
            raise NxwrightError("%s: values must be a list of whole numbers from 0 to %d"
                                % (where, _LARGEST_VALUE))
        settings["values"] = tuple(values)
    return settings


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
