"""Animations, videos, and sounds in the simulation: each plays by itself, on
the simulation's clock, as the Editor's simulator played them
(tests/test_playback.py).

A player's run lasts its `stim`: the sum of an animation's frames'
durations, a video's frames at its frame rate, or a sound's samples
(project/media_files.py). Its `tim` is how far into the run it is, in ms,
and its `qty` an animation's or a video's number of frames. A video's
`fps` is its file's frames a second, whatever the page file stores. The
simulation sets `stim`, `qty`, and `fps` from the file as its page opens.
An animation's or a video's run moves on `dis` percent as fast as the
clock. Code may set it outside the 10 to 1000 the Editor's hint gives,
and it plays that fast: 5 half as fast as 10, 2000 twice as fast as 1000.
At 0 it stands still. The Editor's simulator stopped answering at 0. It
keeps `dis` in two bytes, so no number below 0 reaches it. A sound's `dis`
does not change its speed, and its `fps` and `qty` keep what the page file
stores.
  - `en` 1 plays, as every player does from its page's opening by default:
    when a run ends, `playend` runs, and a new run starts at once when
    `loop` is 1. Without `loop`, the last frame stays, `tim` at the run's
    end, and `en` becomes 0. Code setting `en` to 1 then starts a new run.
  - `en` 0, set by code, stops it: `tim` goes back to 0, and the first
    frame shows.
  - `en` 2 pauses it where it is.
  - Code setting `tim` moves the run there.
  - Code setting `vid` to another ID loads that one, from 0: it plays if
    the player played, and stays stopped or paused if not. Set to the ID
    loaded, it changes nothing, playing or not. Code setting `path` loads
    its file and plays it from 0, even the file playing.
A step comes at each change of frame, and at the run's end; between steps,
`tim` is brought up to the clock before code reads it (catch_up). A sound
writes to the log as it starts playing, as code pauses or stops it, and as
a run that does not loop ends; a run that loops does not, so a short
sound's loop does not fill the log.

All of this was seen in the Editor's simulator, which played a sound of
50 ms in about 400 ms a time, and gave each frame a little more time than
its own; nxwright plays them in their own time. A `vid` set while the
player did not play was seen too. Assumed: a run that lasts no time does
not play.
"""
from nxwright.testing.clocked import ClockedComponent

STOP, PLAY, PAUSE = 0, 1, 2
# What a sound's log says as code halts it.
_HALTS = {STOP: "stops", PAUSE: "pauses"}


class MediaPlayer(ClockedComponent):
    """An animation, video, or sound component of the page shown, playing as
    the module's docstring says. `load(fields)` returns what it plays, as
    media_files.Frames, a sound's having no pictures (sound_frames), or None
    when it plays nothing. `log(text)`, given for a sound, writes to the
    simulation's log. `speed_from_dis` says whether `dis` sets how fast it
    plays, as an animation's and a video's does, and a sound's does not."""

    def __init__(self, name: str, load, log=None, speed_from_dis: bool = True):
        super().__init__(name)
        self.load, self.log = load, log
        self.speed_from_dis = speed_from_dis
        self.run = None             # what it plays: a media_files.Frames, or None
        self.loaded_vid = None      # the `vid` as it last loaded what it plays
        # The clock and the `tim` it counts on from, at its speed.
        self._since = (0, 0)

    def start(self, fields: dict, clock: int):
        self._load(fields)
        self._set(fields, "tim", self._within_run(self._value(fields, "tim", 0)))
        self._count_from(fields, clock, announce=True)

    def resume(self, fields: dict, clock: int):
        self._count_from(fields, clock)

    def changed(self, attribute: str, fields: dict, clock: int):
        # The simulation brings `tim` up to the clock before code runs, so
        # it holds where the run is as the code stores the attribute.
        if attribute == "path" or (attribute == "vid" and
                                   self._value(fields, "vid", None) != self.loaded_vid):
            self._load(fields)
            self._set(fields, "tim", 0)
            self._count_from(fields, clock, announce=True)
        elif attribute == "en":
            state = self._value(fields, "en", PLAY)
            at_end = self.run is not None and self._value(fields, "tim", 0) >= self.run.end
            if state == STOP or (state == PLAY and at_end):
                self._set(fields, "tim", 0)
            playing = self.due is not None
            self._count_from(fields, clock, announce=state == PLAY)
            if playing and state in _HALTS:
                self._say(_HALTS[state])
        elif attribute == "tim":
            self._set(fields, "tim", self._within_run(self._value(fields, "tim", 0)))
            self._count_from(fields, clock)
        elif attribute == "dis":
            self._count_from(fields, clock)

    def catch_up(self, fields: dict, clock: int):
        if self.due is not None:
            self._set(fields, "tim", self._time(fields, clock))

    def step(self, fields: dict, clock: int) -> list:
        time = self._time(fields, clock)
        if time < self.run.end:
            self._set(fields, "tim", time)
            self._schedule(fields, clock)
            return []
        if self._value(fields, "loop", 1):
            self._set(fields, "tim", 0)
            self._count_from(fields, clock)
        else:
            self._set(fields, "tim", self.run.end)
            self._set(fields, "en", STOP)
            self._say("ends")
            self.due = None
        return ["playend"]

    def _load(self, fields: dict):
        """Loads what it plays, and sets its `stim`, `qty`, and `fps` from it."""
        self.run = self.load(fields)
        self.loaded_vid = self._value(fields, "vid", None)
        self._set(fields, "stim", self.run.length if self.run is not None else 0)
        if self.run is not None and self.run.pictures:
            self._set(fields, "qty", len(self.run.pictures))
        if self.run is not None and self.run.rate:
            self._set(fields, "fps", self.run.rate)

    def _count_from(self, fields: dict, clock: int, announce: bool = False):
        """Counts on from `clock` at its `tim`, and sets its next step."""
        self._since = (clock, self._value(fields, "tim", 0))
        playing = self._schedule(fields, clock)
        if playing and announce:
            self._say("plays from %d ms" % self._since[1])

    def _schedule(self, fields: dict, clock: int) -> bool:
        """Sets its next step after `clock`, at the next change of frame or
        the run's end, or none unless it plays and moves on. Returns whether
        it does."""
        if (self.run is None or self.run.end <= 0 or self._speed(fields) == 0
                or self._value(fields, "en", PLAY) != PLAY):
            self.due = None
            return False
        since, time = self._since
        now = self._time(fields, clock)
        target = min([start for start in self.run.starts if start > now] + [self.run.end])
        # The first clock at which the run, counted from `since`, reaches
        # `target`: counting from there rather than from each step keeps
        # the parts of a millisecond a slow or fast run would drop.
        self.due = since + max(-(-(target - time) * 100 // self._speed(fields)), 1)
        return True

    def _time(self, fields: dict, clock: int) -> int:
        """How far into the run it is at `clock`, the run's end at most."""
        since, time = self._since
        return min(time + max(clock - since, 0) * self._speed(fields) // 100, self.run.end)

    def _speed(self, fields: dict) -> int:
        """How fast it plays, in percent, 0 standing still."""
        if not self.speed_from_dis:
            return 100
        return max(self._value(fields, "dis", 100), 0)

    def _within_run(self, time) -> int:
        end = self.run.end if self.run is not None else 0
        return min(max(time, 0), end) if isinstance(time, int) else 0

    def _say(self, what: str):
        if self.log is not None:
            self.log("%s %s" % (self.name, what))

    def _value(self, fields: dict, attribute: str, default):
        return fields.get("%s.%s" % (self.name, attribute), default)

    def _set(self, fields: dict, attribute: str, value):
        fields["%s.%s" % (self.name, attribute)] = value
