"""Running a source folder's app as the screen does, for the simulator.

A Simulation starts as the screen starts: it runs program.nx's code, which
ends by opening the first page, or it opens a given page. Then it waits for
what happens to a screen: a press on a component, a release, or time
passing, which runs the timers of the page shown. Each of these runs events
of the page's code in an EditorMachine (editor_machine.py), and what the
events leave is the app's state:
  - every page's components, by name and attribute as the page's own code
    names them ("title.txt"), each page's starting from its .page.toml file;
  - the globals: program.nx's `int` variables, the system variables, and
    the variables the compiler adds;
  - what the code did outside the screen, as the machine records it.

Changing page. A `page` command runs the old page's `unload` event, then
the new page's `load` and `loadend` events, inside the event that ran it
(docs/nxlang-compiled.md, Functions). The rest of that event does not
run, nor do the events whose clicks or calls led to it. Entering a page
starts its components from its .page.toml file's values, shown and taking
touches, but for those with global scope (`vscope` 1), which keep theirs;
another page's components of global scope are named after their page. Only
the timers of the page shown run. A component of global scope keeps being
hidden (`vis`) or taking no touches (`tsw`); a `vis 255` or `tsw 255` gives
each such component of the page shown its value too, which it keeps, while
the next page's components start shown and taking touches. A button of
global scope whose press changes page reads `val` 0 on the new page, and
gets no release. All of this was seen in the Editor's simulator, but for a
`vis 255` or `tsw 255` run on another page than a global component's own.

Touches. A press lands on the topmost component under it that shows, or
the page. When the page has a touch capture, its Touch Press event runs
first, its `val` the ID of the component touched, 0 for the page; then the
component's own. A release runs the touch capture's Touch Release event,
then the component's, once a list has taken the touch (release). Of
several touch captures, only the last in ID order runs, and `tsw` does not
turn it off; a `click` runs none. A touch
capture's event that changes page stops the component's own events, as any
event changing page does. A hidden component lets the touch through to
what lies under it; one whose touches `tsw` turned off takes it, and
nothing runs, the page after `tsw 255,0` among them. All of this was seen
in the Editor's simulator.

Time. The simulation's clock counts milliseconds from its start, and moves
only when told to (`advance`) or when the code waits (`delay`). An enabled
timer (`en` 1) runs its `timer` event every `tim` milliseconds from when its
page was entered or it was turned on. While a `delay` waits, nothing else
runs; a timer that fell due meanwhile runs once when the event ends, not
once per period missed. A press during a `delay` waits for it to end.
`sleep` 1 puts the screen to sleep, and its timers stop. A touch then runs
nothing; as it ends, it wakes the screen when `thup` is 1, and the timers
start counting again. `thsp` puts it to sleep after that many seconds
without a press, and `ussp` after that many seconds without serial data.
Instructions from the serial line run while it sleeps; with `usup` 1, one
first wakes it. Falling asleep by `thsp` or `ussp` sends 0x86, and waking by
a touch 0x87, but waking by the serial line sends nothing. However it
wakes, by code too, it then shows the page `wup` names, unless that is 255
(_show_wake_page). `sleep` set by code sends neither 0x86 nor 0x87, as the
vendor's instruction set says too. All of this was seen in the Editor's
simulator.

Touch coordinates. A press at a pixel of the page, as the simulator's panel
makes one, puts its place in `tch0` and `tch1`, and in `tch2` and `tch3`,
before its events run, and a move of the press moves them. A release sets
`tch0` and `tch1` to 0 before its events run, while `tch2` and `tch3` keep
the last place. With `sendxy` 1, each press and release sends its place,
before its events run: 0x67, then x and y, two bytes each, high byte first,
then 1 for a press or 0 for a release. While the screen sleeps, each sends
0x68 in its place, whatever `sendxy` says. All of this was seen in the
Editor's simulator, a touch setting the coordinates while the screen sleeps
too, as a timer read them once the touch had woken it. A press of a
component by its name alone, as a test makes, has no place, and changes
none of them.

The touch event. A component whose `sendkey` holds 2 sends 0x65, its
page's ID, its own, and 1, as it is pressed; one that holds 1 sends the
same with 0 as it is released: the Editor's "Send Component ID" ticks of
its Touch Press and Touch Release events. The Editor's simulator sent them
so: after the touch's 0x67 and before the events, the page as a component
does, its ID 0, and nothing where nothing runs, a component whose touches
are off or a `click`.

Opening effects. As a page opens, its components whose `effect` is 1 to 8
slide in from wholly off the screen, over `time` milliseconds, in turns by
`first`, the highest first, as the Editor's simulator showed
(opening_effects.py). They start as the page is drawn, once its load
event ends, each to where that event left it, before its loadend event
runs. They are drawn where they are, and hidden while they wait their
turn, though code reads their own `x` and `y`. Code hiding or showing one
puts it in its place at once. Code moving one changes what code reads,
but it slides on, and the slide's end puts its `x` and `y` back at the
slide's place. A screen that does not hold `effect`, as those of the
Basic, Enhanced, and Discovery series, slides nothing in.

Drags. A press on a component whose `drag` is 1 that then moves carries
the component with it: its `x` and `y` move as the touch moves, its whole
rectangle kept on the screen, until the release. The press and release
events run as for any press. A type that follows a press itself, a page,
and a hotspot are not dragged. All of this is assumed, as the Editor tool
cannot drag; what `movex` and `movey` do is not known.

Lists. What code setting an attribute of a file browser, a select, a
sliding text, a combo box, or a data record works out, the machine works
after each store, as a test's does (list_working.py, editor_machine.py);
the simulation works them through the same module as a page opens and
under touches, keeping only an open combo box's place (combo_boxes.py).

Sliding texts. A press on a sliding text is followed until its release, as
a file browser's or a select's is: its lines move up and down with it, as
far as `maxval_y` lets them, which is assumed, as the Editor tool cannot
drag. Its `maxval_y` is worked out as its page opens, and as code sets
its `txt` or `font`. Code setting its `val_y` may scroll it a
little further than a touch can (sliding_text_drawing.py).

Combo boxes. A release on a combo box opens or closes its list. While it
is open, the list belongs to its box: a press there runs the box's events,
over components before it in ID order, and its release chooses the item
under it and closes the list, before the box's Touch Release event runs;
a component later in the order, drawn over the list, takes the press as
usual (combo_boxes.py).

Data records. As its page opens, a data record reads its data file, from an
SD card given a folder, or else from the files the code wrote; when there
is none and `mode` is 1, it makes one. Its records are drawn from that
file, and its methods change it (editor_machine.py, data_files.py). The
first record to open a file holds it, across pages, until code changes its
`path`; another naming it opens nothing, answers 0x06 twice as its page
opens, and shows a message until it opens a file. A press on it is followed
until its release, as a file browser's is. A tap chooses the record under
it, as `dis` 1 lets it, after the Touch Press event and before the Touch
Release event; a tap on the titles' row, or below the last record, chooses
nothing. All of this was seen in the Editor's simulator. A drag scrolls the
records, as far as `maxval_y` lets them, and chooses nothing, which is
assumed, as the Editor tool cannot drag.

Some components change on the clock without code: a scrolling text moves
by itself (scrolling_texts.py), and an animation, a video, or a sound plays
(media_players.py), from the project's files or, given a `from` of 1, from
an SD card given a folder. So do the page's moves, which `move` gives
(moves.py). Each is a clocked component (clocked.py), stepped in time order
with the timers, stopping while the screen sleeps, and drawn again at each
step if it has a place.

The real-time clock (`rtc0` to `rtc6`: year, month, day, hour, minute,
second, and day of the week from 0 for Sunday) starts at the computer's
time of day, as a screenshot of the Editor's simulator showed the demo's
clock doing, and moves with the simulation's clock. The code setting one
of `rtc0` to `rtc5` sets that part of the time, from then on; a value the
calendar has no room for, such as a 13th month, is ignored, as the
Editor's simulator ignored it. Starting again keeps it running, as the
screen's clock runs on while the screen is off.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
import itertools
import random
import re
import struct

import tomli_w

from nxwright import NxwrightError
from nxwright.drawing.data_record_drawing import UNOPENED, record_at
from nxwright.drawing.media_drawing import played_animation
from nxwright.drawing.page_drawing import inside_box
from nxwright.drawing.select_drawing import SELECT_DEFAULTS
from nxwright.drawing.slider_drawing import drawn_knob_size
from nxwright.drawing.text_pictures import block_size, path_lines
from nxwright.language.code_preprocessor import preprocess_with_places
from nxwright.language.nxlang import GENERATED_NAME, compile_program
from nxwright.language.resource_names import ANIMATION, LISTS, SOUND, VIDEO, ResourceNames
from nxwright.project.device_settings import TextCodec
from nxwright.project.editor_language import SERIES_LACKED_VARIABLES
from nxwright.project.editor_limits import screen_holds
from nxwright.project.media_files import FROM_CARD, animation_frames, sound_frames, video_frames
from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.project.page_header import SYSTEM_PAGES
from nxwright.source import source_folder as folders
from nxwright.source.device_keys import screen_model, settings_from_keys
from nxwright.source.page_source import Component
from nxwright.testing.card_files import (DATA_FILES_HELD, DATA_RECORDS_GIVEN_A_PATH,
                                         DATA_RECORDS_SHUT_OUT, component_attributes,
                                         data_record_values, is_shut_out, open_data_record,
                                         opens_no_file, read_card_file, write_card_file)
from nxwright.testing.combo_boxes import ComboBoxes
from nxwright.testing.data_files import data_file_for
from nxwright.testing.editor_machine import (EEPROM_SIZE, PINYIN_COMMANDS, RECORD_STARTS, RECORDS,
                                             CompileRefusal, EditorMachine, RefusedCode,
                                             UnknownComponentId, own_page_prefix)
from nxwright.testing.folder_resources import FolderResources
from nxwright.testing.gpio_pins import (PIN_NAMES, UNDRIVEN, GpioPins, checked_level, pin_number,
                                        starting_levels)
from nxwright.testing.list_working import (COMBO_BOX_CHOICES, FILE_BROWSER_LISTINGS, UNSETTLED,
                                           ListWorking)
from nxwright.testing.media_players import MediaPlayer
from nxwright.testing.modbus_crc import CRC_OFF
from nxwright.testing.moves import MOVES, Move, Moves
from nxwright.testing.opening_effects import OpeningEffects
from nxwright.testing.pinyin_table import pinyin_table_of
from nxwright.testing.recording import Place, TrackedValues
from nxwright.testing.scrolling_texts import ScrollingText
from nxwright.testing.sd_cards import INVALID_FILE_OPERATION, CardRefusal, FolderCards
from nxwright.testing.serial_line import (ADDRESSES, BUFFER, DROPPED, INSTRUCTION, NOT_ADDRESSED,
                                          REPARSE_END, SERIAL_BUFFER_SIZE, SerialLine,
                                          Transfer)
from nxwright.testing.simulation_log import END, LOGGED, SENT, hex_bytes, shown
from nxwright.testing.source_runner import (FolderPageTables, SourceFolderRunner,
                                            component_start_values, table_limits)

# The commands of "other commands" that hold and resume the serial line, as
# the machine records them (_take_serial).
_SERIAL_LINE = (("com_stop",), ("com_star",))
# What the log says once when the app runs a pinyin command without a
# pinyin table, which the machine then only records.
_NO_PINYIN_TABLE = ("%s: no pinyin table was found, so Chinese input shows no candidates. To "
                    "give one, set the launch configuration's pinyinTable, or the setting "
                    "nxwright.simulator.pinyinTable, to the Nextion Editor's input.bin or to a "
                    "TFT file.")
# What a GPIO level given to a screen of the Basic series raises.
_NO_GPIO = "the screen's series, the Basic, has no GPIO pins"
# What the screen sends of a touch: the data's first byte, awake or asleep,
# and the touch's event (_note_touch).
_TOUCH_PLACE, _TOUCH_PLACE_ASLEEP = 0x67, 0x68
_TOUCH_PRESSED, _TOUCH_RELEASED = 1, 0
# The touch event a component's `sendkey` asks for (_send_touch_event): its
# first byte, and the bits of `sendkey`, the Editor's "Send Component ID"
# ticks of its Touch Press and Touch Release events.
_TOUCH_EVENT = 0x65
_SENDS_PRESS, _SENDS_RELEASE = 2, 1
# The (width, height) a touch stays within on a screen whose size is not
# known, as app.toml gives none for a model nxwright does not know: what a
# coordinate's two bytes hold.
_UNKNOWN_SCREEN_AREA = (0x10000, 0x10000)
# What it sends as it falls asleep by `thsp`, and wakes by a touch.
_ASLEEP_WHEN_IDLE, _WOKEN_BY_TOUCH = 0x86, 0x87

# The system variables at power-on, the vendor's documented defaults. The
# real-time clock's are worked out from the simulation's time (_clock_values).
# sys0 to sys2 are none: program.nx declares them, as the Editor's new
# project does (editor_language.EDITOR_PROGRAM_VARIABLES).
SYSTEM_START = dict(
    {"dim": 100, "dims": 100, "baud": 9600, "bauds": 9600,
     "spax": 0, "spay": 0, "thc": 0, "thdra": 0, "thsp": 0, "thup": 0, "ussp": 0, "usup": 0,
     "wup": 255, "sendxy": 0, "delay": 0, "sleep": 0, "bkcmd": 2, "rand": 0, "recmod": 0,
     "pwmf": 1000, "lowpower": 0,
     # As the Editor's simulator started them on an Intelligent screen.
     "usize": 0, "volume": 100, "appid": 0, "addr": 0, "audio0": 0, "audio1": 0,
     "eql": 7, "eqm": 7, "eqh": 7, "scache": 0, "bcpu": 0, "tpdir": 0, "runmod": 0,
     "portbusy": 0, "tprc": 0, "aph": 127,
     # Off, as a freshly started Nextion Editor's simulator answered
     # (testing/modbus_crc.py).
     "crcval": CRC_OFF},
    **{"eq%d" % band: 7 for band in range(10)},
    # Pull-up inputs that nothing drives: a start gives each the level it
    # has (gpio_pins.py).
    **{name: UNDRIVEN for name in PIN_NAMES},
    **{"pwm%d" % index: 50 for index in range(4, 8)},
    **{"tch%d" % index: 0 for index in range(4)})

# The types a press and a release draw again, their look changing. Their
# `val` is 1 while pressed and 0 once released, set before the events of
# each, as the Editor's simulator showed (_press_val).
_PRESSED_LOOK = ("button",)
# The types a press flips the `val` of, 0 to 1 and back, before any of its
# events, the touch capture's too, as the Editor's simulator does: a radio
# too, which no other radio turns off, and which a press turns off when it
# is on.
_TOGGLED = ("checkbox", "radio", "dual-state-button", "switch")

# A picture attribute's value for "none".
NO_PICTURE = 65535
# The types that play, by the kind of resource each plays.
_PLAYERS = {"gmov": ANIMATION, "video": VIDEO, "audio": SOUND}
# What steps the opening effects, among the timers and clocked components
# that fall due: no component's name, as a name holds no space.
_OPENING = "opening effects"

# The values a machine is given that belong to no page and are not kept.
_PER_RUN = ("dp", "text limits")


@dataclass
class _Touch:
    """A press on a file browser, a select, a sliding text, a combo box, or a
    data record, until it is released: where it started, on the page; how
    far its browser, sliding text, or data record was scrolled then, or its
    combo box's open list (its first item shown, None when the press was not
    on that list); and whether it scrolled that, or how far it moved its
    select's lines."""
    component: str
    kind: str
    x: int
    y: int
    start_scroll: int | None = 0
    scrolled: bool = False
    moved: int = 0


@dataclass(frozen=True)
class _Drag:
    """A touch dragging `component`: where the press was, on the page, and
    where the component was then, its `x` and `y`."""
    component: str
    x: int
    y: int
    left: int
    top: int


@dataclass
class _HeldDrawing:
    """What the screen keeps showing between `ref_stop` and `ref_star`: the
    page shown then, its components and those hidden as they were at
    `ref_stop`, and the components code changed since."""
    page: str
    components: dict    # {name: Component}
    hidden: set
    changed: set


@dataclass
class DrawingInputs:
    """Everything the drawing of what a screen shows takes from a simulation
    (page_drawing.draw_page): the page, and which entry of it, counted as
    Simulation.entered counts them; its Components as the screen draws
    them, the page first; those it does not draw; what drawing commands
    painted; the component held down; the waveforms' points; the file
    browsers' entries and the data records' records; how far a press moved
    a select's lines; where the scrolling texts and the combo boxes' open
    lists have scrolled; and the spacing `xstr` takes, `spax` and `spay`."""
    page: str
    entry: int
    components: list
    hidden: set
    painted: list
    pressed: str
    waves: dict
    listings: dict
    select_moves: dict
    scrolled: dict
    spacing: tuple


@dataclass
class _Page:
    """What the simulation knows of one page."""
    name: str
    number: int
    code: dict           # {(component, event): its Editor code lines}
    places: dict         # {(component, event): a Place or None per line}
    start: dict          # the page's own start values: its components' and the generated ones
    text_limits: dict
    components: list     # [(name, type, has a place)], the page first, in ID order
    global_names: set    # the components of global scope
    owned: set           # every name whose values are the page's: its components', generated ones'
    placed: set          # the page and its components with a place on the screen
    local_names: dict    # {owner: {generated variable: nxlang name}}
    # Which of the Editor's system pages it is, by the number a component's
    # `key` names it with (SYSTEM_PAGES: 1 to 4, its four keyboards), or None.
    system_page: int = None


@dataclass
class StartProgress:
    """How far a start of the app has come, as a Simulation tells its
    `starting` callback. Before each page compiles: the page's `number`,
    from 1, of `count` pages, its name, and the full paths of its .nx files,
    its own and those it includes. Once all pages are compiled, `page` is
    None, `number` is `count`, and `files` holds program.nx's files when its
    code is about to compile and run, none when a start page was given."""
    number: int
    count: int
    page: str
    files: list


def read_eeprom_file(path: Path) -> tuple:
    """Returns (the EEPROM a simulation starts from, whether the file was
    made): the bytes of the file `path`, or EEPROM_SIZE zero bytes, written
    to it, when it does not exist. Raises NxwrightError for a file longer
    than the EEPROM, which writing it back would cut, and for one that
    cannot be read or made."""
    path = Path(path)
    if not path.exists():
        try:
            path.write_bytes(bytes(EEPROM_SIZE))
        except OSError as error:
            raise NxwrightError("the EEPROM's file %s cannot be made: %s"
                                % (path, error.strerror or error)) from None
        return bytes(EEPROM_SIZE), True
    try:
        data = path.read_bytes()
    except OSError as error:
        raise NxwrightError("the EEPROM's file cannot be read: %s" % error) from None
    if len(data) > EEPROM_SIZE:
        raise NxwrightError("the EEPROM's file %s holds %d bytes, where the EEPROM holds %d: "
                            "writing it back would cut it" % (path, len(data), EEPROM_SIZE))
    return data, False


class Simulation:
    """The app of the source folder `source_folder`, running.

    `start_page`, when given, opens that page rather than running
    program.nx's code, from program.nx's `int` variables and `values`, which
    also set those of other names, as a test's do. `recorder`, a Recorder
    (recording.py), records each statement, for the debugger. `eeprom` is
    what the EEPROM starts with; with `eeprom_file`, the path of the file it
    came from (read_eeprom_file), each write the app makes to it reaches
    that file at once, whole, as the Nextion Editor's simulator kept its
    EEPROM in its file from one run to the next. `time` is the real-time
    clock's time at the start, the computer's when not given. `sending`,
    when given, is called with the bytes the screen sends on its serial
    line, in order: the bytes the log describes. It returns None, or a line
    for the log saying what could not be sent. `leaving`, when given, is
    called before the page shown changes, once its `unload` event has run:
    the screen still shows it, as its code left it. `cards`, {card: folder}
    such as {"sd0/": folder}, gives SD cards folders of the computer
    (sd_cards.py). `log_formats`, {"received": form, "sent": form}, says how
    the log shows what the screen receives and sends (simulation_log.py,
    shown): by default, the first as text and the second in hexadecimal.
    `starting`, when given, is called with a StartProgress as each start
    compiles the app's pages: the first start, a start again, and the app's
    own `rest`. `pinyin_table`, a PinyinTable or the path of one
    (pinyin_table.py), is the screen's pinyin table, which `pa_q` and
    `pa_txt` read; without one, the log says so once, at the first of them.
    A path that holds no pinyin table raises NxwrightError. `inputs`, such
    as {"pio2": 0}, gives the GPIO inputs' starting levels, as a `pio` name
    in `values` does too; both count at the first start alone, as the levels
    belong to the world outside the screen (gpio_pins.py). A level other
    than 0 or 1, a name other than `pio0` to `pio7`, a pin the two give
    different levels, or a screen without GPIO raises NxwrightError."""

    def __init__(self, source_folder: Path, start_page: str = None, values: dict = None,
                 recorder=None, eeprom: bytes = b"", time: datetime = None, sending=None,
                 leaving=None, cards: dict = None, log_formats: dict = None, starting=None,
                 eeprom_file: Path = None, pinyin_table=None, inputs: dict = None):
        self.source_folder = Path(source_folder).resolve()
        self.eeprom_file = None if eeprom_file is None else Path(eeprom_file)
        self.pinyin_table = pinyin_table_of(pinyin_table)
        # Whether the log said that no pinyin table was given (recorded).
        self._said_no_pinyin_table = False
        self.recorder = recorder
        self.sending = sending
        self.leaving = leaving
        self.starting = starting
        self.cards = FolderCards(cards) if cards else None
        self.log_formats = dict({"received": "text", "sent": "hex"}, **(log_formats or {}))
        # The real-time clock: its time when the simulation's clock was at a
        # given point.
        self._time_at = ((time or datetime.now()).replace(microsecond=0), 0)
        # How many times the state changed: a drawing is needed again once it grows.
        self.changes = 0
        self.log = []                # [(clock, line)]: what reached outside the screen
        # Whether a page's load event runs: until it ends, the screen still
        # shows the page before.
        self.loading = False
        # Whether the page changes as the screen wakes, which runs no unload.
        self._waking = False
        # How many times the screen started, and pages were entered, since
        # the simulation began: what a drawing is drawn over follows them.
        self.starts = 0
        self.entered = 0
        # {path: ((modified time, size), Font)} of the fonts decoded (_font),
        # kept across starts, as a file unchanged decodes alike.
        self._decoded_fonts = {}
        # The GPIO pins, which outlive each start. A pio start value gives a
        # level, and leaves the start values, so that a start again keeps
        # the level the pin has then.
        values = dict(values or {})
        levels = dict(inputs or {})
        for name in [name for name in PIN_NAMES if name in values]:
            given = values.pop(name)
            if levels.get(name, given) != given:
                raise NxwrightError("%s starts at %r in the inputs, and at %r in the values: "
                                    "give it one starting level" % (name, levels[name], given))
            levels[name] = given
        self._pins = GpioPins(starting_levels(levels))
        self._levels_given = bool(levels)
        # The serial line's bytes not yet used (serial_line.py), which each
        # start empties (_begin).
        self._line = SerialLine()
        self._start = (start_page, values, eeprom)
        self._begin()

    def _begin(self, eeprom: bytes = None, said: str = None, appid: int = None):
        """Starts the app, as the screen starts on power-on, its EEPROM as
        it started or `eeprom`, and `appid` at 0 or as given: what a screen
        keeps through a restart. The folder is read and compiled first
        (_read_start), and the simulation changes only once all of it has
        built. So a start again that the build refuses raises NxwrightError,
        and leaves the app running as it was. `said`, the log's line for a
        start again, is written once it has built."""
        source_folder = self.source_folder
        start_page, _, start_eeprom = self._start
        starting = self._read_start()
        if hasattr(self, "clock"):
            # Starting again: the real-time clock runs on from where it is.
            self._time_at = (self._time_now(), 0)
        if said is not None:
            self._write_log(said)
        eeprom = start_eeprom if eeprom is None else eeprom
        self.app = starting.app
        # The pictures and fonts the code may name, which the machines check.
        self._resources = ResourceNames.of_app(self.app)
        # Their files, for the layouts of list components and keyboards.
        self._folder_resources = starting.folder_resources
        # The screen's (width, height) as it is turned, which a touch stays within.
        self._touch_area = starting.touch_area
        # The screen's series, whose lacked commands and system variables a
        # typed instruction is refused for.
        self._series = starting.series
        self.pages = starting.pages
        self.encoding = starting.encoding
        self._lists = ListWorking(self._folder_resources, self.cards, self.encoding)
        # The folder's macros, which a `call` runs, from any page or the serial line.
        self.macros = starting.macros
        # The pages by number: the app's, then a keyboard's stand-in caller, if
        # any, which the simulation alone has.
        self.page_names = starting.page_names
        values = starting.values
        program_start = starting.program_start
        # Each page's component types, by name, in ID order, with the page
        # itself first. _of_kind reads a page's components of one type from
        # this map.
        self._kinds = {name: {component: kind for component, kind, _ in page.components}
                       for name, page in self.pages.items()}
        # The globals: program.nx's, the generated ones, and the system variables.
        self.globals = dict(SYSTEM_START)
        self.globals.update({name: value for name, value in program_start.items()
                             if "." not in name and name not in _PER_RUN})
        # Every pin is a pull-up input again, reading the level it has.
        self._pins.start()
        self.globals.update(zip(PIN_NAMES, self._pins.levels))
        self.globals["eeprom"] = bytes(eeprom[:EEPROM_SIZE]).ljust(EEPROM_SIZE, b"\0")
        if appid is not None:
            self.globals["appid"] = appid
        # The records of what stays between stores, made at the start, so
        # that every event's values share them; a new start holds none:
        # the files the data records hold, those shut out of theirs, and
        # those whose `path` code set (card_files.py); each file browser's
        # listing, each combo box's last `val` within its items, and the
        # lists whose scroll values wait to settle (list_working.py).
        for record in (DATA_FILES_HELD, DATA_RECORDS_SHUT_OUT, DATA_RECORDS_GIVEN_A_PATH,
                       FILE_BROWSER_LISTINGS, COMBO_BOX_CHOICES, UNSETTLED):
            self.globals[record] = {}
        self.fields = {name: dict(page.start) for name, page in self.pages.items()}
        self.clock = 0
        self.page = None
        self.starts += 1
        self.asleep = False
        self._due = {}               # {timer: when its event runs next}, on the page shown
        self._clocked = {}           # {name: ClockedComponent} of the page shown (clocked.py)
        # The page shown's slides as it opens, and when they step next (opening_effects.py).
        self._opening = OpeningEffects([], (0, 0), 0)
        self._opening_due = None
        self._slid = {}              # {component: (x, y)} where its slide drew it at its last step
        self._last_press = 0
        self._last_serial = 0        # when serial data last arrived, for `ussp`
        self._pressed = None         # (page, component) pressed, until released
        self._drawing_held = None    # a _HeldDrawing from `ref_stop` until `ref_star`
        # The DrawingInputs of the page shown before a page change while
        # `ref_stop` held, which the screen shows until `ref_star`.
        self._kept_drawing = None
        # {slider: its knob's start along its track} where a touch put it on
        # the page shown, until code stores its `val` (_slide).
        self._knobs = {}
        # Whether the page shown, entered while `ref_stop` held, waits for
        # `ref_star` to start its slides (page_changed).
        self._slides_wait = False
        self._touch_at = None        # (x, y): where a press with a place is, until released
        self._touched_asleep = False  # whether the touch lasting began while the screen slept
        self._touch = None           # a list or a sliding text pressed: a _Touch
        self._drag = None            # a component a touch drags: a _Drag, until released
        self._combos = ComboBoxes()  # the combo boxes of the page shown (combo_boxes.py)
        self._reset = False          # whether the code ran `rest`
        self._running = None         # the machine running an event, if any
        self._answered = False       # whether the screen answered the instruction typed
        # The return code a refusal gave the instruction typed, in place of success.
        self._refused = None
        # The serial instructions com_stop holds, until com_star; None when the
        # line is not stopped. `rest` drops them, the line staying stopped
        # (_start_again_by_rest).
        self._held = None
        self._resuming = False       # whether code ran com_star, which runs them once it ends
        self._overflowed = False     # whether the piece arriving has overflowed the buffer
        # A screen that starts again has an empty serial buffer: the bytes
        # waiting are dropped, and so are a transfer under way and the
        # buffer of protocol reparse mode.
        self._line.empty()
        self.globals["serial buffer"] = b""
        self._waves = {}             # {waveform: {channel: [points]}} of the page shown
        self._random = random.Random(0)
        if self.recorder is not None:
            # One run from start to end: a run per event would keep a copy of
            # every value for each, without end.
            local_names = {}
            for page in self.pages.values():
                local_names.update(page.local_names)
            self.recorder.begin("simulation of %s" % folders.app_name(self.app, source_folder),
                                str(source_folder),
                                self._view(None), local_names,
                                self.app["language"] == folders.NXLANG)
        if starting.stand_in:
            self._write_log("%s started without a caller: a stand-in text, t0 of %s, a page "
                            "of the simulation's own, takes its place"
                            % (start_page, self.page_names[-1]))
        if starting.page is None:
            lines, places = starting.program
            self._run(None, lines, places, given=values)
        else:
            page = starting.page
            self._enter(page, values)
            self.loading = True
            try:
                returned = self._run_event(page, (page, "load"))
            finally:
                self.loading = False
            if self.page == page:
                # Drawn once its load event ends, as after a page change.
                self.globals["painted"] = []
                self._start_opening(self.fields[page])
            if not returned:
                self._run_event(page, (page, "loadend"))
        # Start values, which no code stored, may give `recmod` and `addr`.
        if self.globals.get("recmod") and not self._line.in_reparse():
            self._line.start_reparse()
        if self.globals.get("addr") in ADDRESSES:
            self._line.set_address(self.globals["addr"])

    def _read_start(self) -> "_StartingApp":
        """Returns what a start takes from the source folder: the app read
        and compiled, the page it starts on, and its start values. Changes
        nothing of the simulation. Raises NxwrightError for a folder the
        build refuses, or a start page the app no longer has."""
        source_folder = self.source_folder
        start_page, values, _ = self._start
        runner = SourceFolderRunner(source_folder, self.pinyin_table)
        read = folders.folder_reader(source_folder)
        # Shared with the runner's compiles, and kept between starts: never changed here.
        tables = runner.folder_page_tables()
        app = tables.app
        settings = settings_from_keys(app)
        series = settings.model.series if settings is not None else None
        if self._levels_given and not _series_has_gpio(series):
            raise NxwrightError(_NO_GPIO)
        files = folders.code_files(app, read) if self.starting is not None else {}
        count = len(app["pages"])
        pages = {}
        for number, name in enumerate(app["pages"]):
            self._tell_start(number + 1, count, name, files.get(name, []))
            pages[name] = _read_page(runner, tables, name, number)
        self._tell_start(count, count, None, files.get(None, []) if start_page is None else [])
        program_start = {}
        for page in pages.values():
            program_start.update(runner.runnable_page(page.name, None, False).start)
        starting = _StartingApp(
            app, FolderResources(source_folder, app, self._decoded_fonts),
            settings.page_size if settings is not None else _UNKNOWN_SCREEN_AREA, series,
            pages, list(app["pages"]), program_start,
            runner.runnable_page(app["pages"][0], None, False).encoding, runner.macros(),
            values)
        if start_page is None:
            starting.program = _program_code(source_folder, read, app)
            return starting
        starting.page = _page_by_name(str(start_page), starting.page_names)
        # A value may name the start page's component with the page's name,
        # as the page's code may: it is that component's.
        own = own_page_prefix(starting.page)
        starting.values = {own.sub("", name): value for name, value in values.items()}
        stand_in = _stand_in_caller(tables, starting)
        if stand_in is not None:
            starting.values = dict(starting.values, **stand_in)
            starting.stand_in = True
        return starting

    def _tell_start(self, number: int, count: int, page: str, files: list):
        """Tells the `starting` callback, if any, how far the start has come
        (StartProgress), `files` given within the source folder. A start
        again the build refuses has told it of the pages compiled until
        then."""
        if self.starting is not None:
            self.starting(StartProgress(number, count, page,
                                        [str(self.source_folder / path) for path in files]))

    def start_again(self):
        """Starts the app again from the beginning, as the screen does when
        turned off and on, and as `rest` starts it: its EEPROM and `appid`
        keep what the app wrote, as a screen keeps them. Says so in the log,
        which is kept. Raises NxwrightError, the app left running as it was,
        when the folder no longer builds."""
        self._begin(self.globals["eeprom"], "started again, the EEPROM kept",
                    self.globals["appid"])

    def _start_again_by_rest(self):
        """Starts the app again as `rest` does: as start_again, but a serial
        line `com_stop` held stays held, its instructions dropped, until a
        `com_star`."""
        held = self._held is not None
        self._begin(self.globals["eeprom"], "rest: the screen starts again",
                    self.globals["appid"])
        if held:
            self._held = []

    # What happens to the screen.

    def serial_input(self, text: str):
        """Runs `text` as an instruction arriving on the serial line, and
        logs what the screen sends back: a reply such as `get`'s, and the
        instruction's return code, as `bkcmd` asks (0 none, 1 on success, 2 on
        failure, 3 both), as the Editor's simulator does: 01 for success,
        but none for an instruction that answers, such as `get` or
        `sendme`, or changes page; a typed `click`'s success before its
        event runs (answer_typed_now). A failure answers the code the
        Editor's simulator answered, and changes nothing: 00 for an
        instruction it does not know, 02 for a component given by an ID no
        object of the page has, 03 for a page, 1A for a name; a refusal of
        the running screen its own code (editor_machine.ScreenRefusal); and
        one the Editor's compile would make, its code (CompileRefusal). The
        instruction is no line of a file, so it is no step of a recording;
        what it changes is, with the next step. It runs while the screen
        sleeps too, and first wakes it when `usup` is 1 (_serial_arrived).
        After `com_stop`, it is held until `com_star` (_take_serial). While
        a transfer takes the serial line's bytes as data, or in protocol
        reparse mode, the instruction arrives as its bytes in the project's
        encoding, then FF FF FF, in one piece, as it would from the serial
        line. A text the encoding cannot store does not arrive. In address
        mode, the instruction is taken as having the screen's address, so
        that the Simulator section can still reach the screen."""
        if self._line.transfer() is not None or self._line.in_reparse():
            self._typed_as_bytes(text)
            return
        self._overflowed = False
        self._instruction_received(text)

    def _instruction_received(self, text: str):
        """Takes an instruction that arrived on the serial line, typed or as
        bytes, as serial_input says."""
        self._serial_arrived()
        self._write_log("receives %s" % self._received(text))
        self._take_serial(text)

    def _typed_as_bytes(self, text: str):
        """Hands a typed instruction to the serial line as bytes, as
        serial_input says."""
        try:
            data = TextCodec(self.encoding).encode_keeping_bytes(text, "the instruction")
        except NxwrightError as error:
            self._write_log("receives nothing: %s" % error)
            return
        self._write_log("receives %s as bytes, not as an instruction" % self._received(text))
        self.serial_received(data + END)

    def _take_serial(self, text: str):
        """Takes an instruction from the serial line. `com_stop`, sent or run
        by code, holds the instructions after it, logging each, and `com_star`
        runs them, in order. On the serial line, `com_star` is taken while the
        line is held. Neither answers, whatever `bkcmd` asks."""
        word = text.strip()
        if word == "com_star":
            self._resume_serial()
        elif word == "com_stop":
            self._stop_serial()
        elif self._held is not None:
            if self._held and (self._waiting_size() + self._held_size(text)
                               > SERIAL_BUFFER_SIZE):
                # As the vendor says: the overflow loses the instructions
                # held before, and the screen goes on receiving this one.
                self._overflow(sum(map(self._held_size, self._held)), "held instructions")
                self._held = []
            self._held.append(text)
            self._write_log("held: the serial line is stopped")
        else:
            self._run_serial(text)

    def _stop_serial(self):
        """Holds the serial line's instructions from now on, as `com_stop`
        does; a second `com_stop` changes nothing."""
        if self._held is None:
            self._held = []

    def _resume_serial(self):
        """Runs the serial instructions `com_stop` held, in order. One that
        starts the screen again drops those after it, as `rest` does; one
        whose code runs `com_stop` holds them again."""
        held, self._held = self._held or [], None
        starts = self.starts
        for position, text in enumerate(held):
            if self.starts != starts:
                return
            if self._held is not None:
                self._held.extend(held[position:])
                return
            self._write_log("runs %s, held until com_star" % self._received(text))
            self._run_serial(text)

    def _resume_when_asked(self):
        """Runs the held serial instructions when the code that just ran
        ran `com_star`: once its event has ended, as code has the screen until
        then."""
        if self._resuming:
            self._resuming = False
            self._resume_serial()

    def _run_serial(self, text: str):
        """Runs an instruction of the serial line, and sends its answer, as
        serial_input says."""
        page = self.page
        # As before an event's code (_run), the page's clocked components are
        # brought up to the clock: a player's `tim` reads where its run is.
        if page is not None:
            self._catch_up(self.fields[page])
        # Before any page shows, it runs as program.nx's code does.
        machine = self._machine(page, self._view(page))
        known = set(machine.values)
        self._answered = False
        self._refused = None
        code = 0x01
        try:
            self._running = machine
            try:
                machine.run_instruction(text)
            except _EventEnded:
                pass
            # The screen refuses to store in a name it does not know. A new
            # page brings its own names.
            added = {name for name in set(machine.values) - known - RECORDS
                     if not name.startswith(RECORD_STARTS)}
            if added and self.page == page:
                code = 0x1a
        except KeyError:
            code = 0x1a         # an invalid variable name or attribute
        except UnknownComponentId:
            code = 0x02         # an invalid component ID
        # A refusal is an NxwrightError, but answers its own code or 0x00.
        except CompileRefusal as refusal:
            code = refusal.code
        except RefusedCode:
            code = 0x00         # an invalid instruction
        except NxwrightError:
            code = 0x03         # an invalid page
        except (AssertionError, ValueError, IndexError):
            code = 0x00         # an invalid instruction
        finally:
            self._running = None
        succeeded = code == 0x01
        changed_page = self.page != page
        if succeeded or changed_page:
            self._commit(machine.values, self.page)
        if succeeded and (self._answered or changed_page):
            code = None     # the answer, or the new page's events, stand for it
        if succeeded and self._refused is not None:
            code, succeeded = self._refused, False
        self._after_code(lambda: self._return_code(code, succeeded))

    def _serial_arrived(self):
        """Serial data arrived: `ussp` counts again from now, and a sleeping
        screen wakes when `usup` is 1, sending nothing, then shows the page
        `wup` names (_show_wake_page)."""
        self._last_serial = self.clock
        if self.asleep and self.globals.get("usup") == 1:
            self._wake()
            self._show_wake_page()

    def _received(self, text: str) -> str:
        """An instruction as the log shows it: as text, the instruction as it
        is; else its bytes, with the FF FF FF that ended them. One typed with a
        character the project's encoding cannot write, which the screen
        could not have received, shows as text whatever the form."""
        form = self.log_formats["received"]
        if form == "text":
            return text
        try:
            data = TextCodec(self.encoding).encode_keeping_bytes(text, "the instruction")
        except NxwrightError:
            return text
        return shown(data + END, form, self.encoding)

    def serial_received(self, data: bytes):
        """Takes `data`, a piece of the serial line: bytes that arrived at
        once (serial_line.py). Each instruction they end runs as
        `serial_input` runs a text. A transfer's bytes are its data, and the
        transfer ends once they are in (take_transparent_data). In protocol
        reparse mode, the bytes go into the buffer, and the text ending the
        mode sets `recmod` to 0. In address mode, an instruction runs only
        with the screen's address. The log notes bytes the line dropped.
        What waits in the screen's serial buffer, held instructions and the
        buffer of protocol reparse mode, keeps at most SERIAL_BUFFER_SIZE
        bytes (_overflow)."""
        self._overflowed = False
        if self._line.transfer() is not None or self._line.in_reparse():
            self._serial_arrived()
        for kind, taken in self._line.receive(data):
            if kind == INSTRUCTION:
                self._serial_bytes(taken)
            elif kind == BUFFER:
                self._buffer_received(taken)
            elif kind == REPARSE_END:
                self.globals["recmod"] = 0
                self.globals["serial buffer"] = b""
                self._write_log("recmod: protocol reparse mode ends")
            elif kind == NOT_ADDRESSED:
                self._write_log("serial line: dropped %s, without the screen's address"
                                % hex_bytes(taken))
            elif kind == DROPPED:
                self._write_log("serial line: dropped %d bytes with no FF FF FF after them"
                                % taken)
            else:
                self._end_transfer(taken)

    def _buffer_received(self, data: bytes):
        """Adds `data` to the buffer of protocol reparse mode, as far as the
        screen's serial buffer has room (_overflow)."""
        room = max(SERIAL_BUFFER_SIZE - self._waiting_size(), 0)
        if len(data) > room:
            self._overflow(len(data) - room, "protocol reparse mode")
        self.globals["serial buffer"] += data[:room]

    def _waiting_size(self) -> int:
        """The bytes waiting in the screen's serial buffer: the instructions
        `com_stop` holds, each with its FF FF FF, and the buffer of protocol
        reparse mode."""
        return sum(map(self._held_size, self._held or [])) + len(self.globals["serial buffer"])

    def _held_size(self, text: str) -> int:
        """The bytes a held instruction takes: its text in the project's
        encoding, or in UTF-8 when the encoding cannot store it, as a typed
        instruction may hold, then FF FF FF."""
        try:
            data = TextCodec(self.encoding).encode_keeping_bytes(text, "the instruction")
        except NxwrightError:
            data = text.encode("utf-8")
        return len(data) + len(END)

    def _overflow(self, dropped: int, what: str):
        """Notes `dropped` bytes of `what` that the screen's serial buffer had
        no room for. The log says how many, and the screen answers 0x24 once
        for the piece that overflowed, when `bkcmd` reports failures."""
        self._write_log("serial line: the serial buffer overflowed, %d bytes of %s dropped"
                        % (dropped, what))
        if not self._overflowed:
            self._overflowed = True
            self._return_code(0x24, False)

    def _serial_bytes(self, data: bytes):
        """Runs `data`, an instruction's bytes as they arrived on the serial
        line without the FF FF FF that ended them, as `serial_input` runs
        a text. Bytes the project's encoding cannot read are an invalid
        instruction."""
        try:
            text = TextCodec(self.encoding).decode(data, "the instruction")
        except NxwrightError:
            # Data arrived all the same (serial_input notes the rest).
            self._serial_arrived()
            self._write_log("receives %s, which %s cannot read" % (hex_bytes(data),
                                                                   self.encoding))
            self._return_code(0x00, False)
            return
        self._instruction_received(text)

    def _return_code(self, code, succeeded: bool):
        """Sends an instruction's return code, as `bkcmd` asks; None sends none."""
        wanted = (1, 3) if succeeded else (2, 3)
        if code is not None and self.globals.get("bkcmd", 2) in wanted:
            self._send_logged(bytes([code]) + END)

    def _send_logged(self, data: bytes):
        """Sends `data` on the serial line, as the screen sends what is not
        the code's own, logging it."""
        self._write_log("sends %s" % shown(data, self.log_formats["sent"], self.encoding))
        self._send(data)

    def _send(self, data: bytes):
        """Hands what the screen sends to `sending`, logging what it could not send."""
        if self.sending is not None:
            problem = self.sending(data)
            if problem:
                self._write_log(problem)

    def press(self, component: str, x: int = None, y: int = None):
        """Presses `component` of the page shown, at the page's pixel (x, y)
        when given: runs the page's touch capture's `down` event (_capture),
        then the component's own. A checkbox, radio, dual-state button, or
        switch first flips its `val` (_toggle). A slider's knob first moves
        there, as in the Editor's simulator: a press at x 400 on a slider 400
        wide at x 100, its round knob 40 wide, gave `val` 78 in both. A
        component whose touches `tsw` turned off takes the press, and nothing
        runs, as the Editor's simulator did for a text. On a sleeping screen,
        nothing runs: the release wakes it. A place given sets the touch
        coordinates first (_note_touch)."""
        self._last_press = self.clock
        if self.page is None:
            return      # nothing shows yet to press
        if x is not None and y is not None:
            self._note_touch(x, y, _TOUCH_PRESSED)
        # A touch on a sleeping screen only wakes it, as it ends (release).
        self._touched_asleep = self.asleep
        if self.asleep:
            return
        self._pressed = None
        self._touch = None
        self._drag = None
        # The page too: after `tsw 255,0`, the Nextion Editor's simulator ran
        # nothing for a press on it.
        if not self._switched("touch", component):
            self._touch_dot()
            return
        self._pressed = (self.page, component)
        self._send_touch_event(component, _TOUCH_PRESSED)
        if x is not None and y is not None:
            self._slide(component, x, y)
            kind = self._kinds[self.page].get(component)
            if kind in _FOLLOWING:
                # A list changes only as the touch ends, or as it scrolls
                # (_follow), so one with a scroll bar is not drawn again
                # while it is pressed and not scrolled (_drawn_pressed).
                fields = self.fields[self.page]
                start = self._combos.first_under(component, component_attributes(component, fields),
                                                 x, y) if kind == "combo-box" else \
                    fields.get(component + ".val_y", 0)
                self._touch = _Touch(component, kind, x, y, start)
                if kind not in _WITH_SCROLL_BAR:
                    self._changed(component)
            elif kind not in _UNDRAGGED and self.fields[self.page].get(component + ".drag") == 1:
                fields = self.fields[self.page]
                self._drag = _Drag(component, x, y, fields.get(component + ".x", 0),
                                   fields.get(component + ".y", 0))
        self._toggle(component)
        self._press_val(component, True)
        self._draw_pressed(component)
        self._touch_dot()
        page = self.page
        self._capture(component, "down")
        if self.page == page:
            self._run_event(page, (component, "down"))
        if self.page != page:
            # The press changed page: the button's `val` went back to 0, as
            # the Nextion Editor's simulator showed for one of global scope.
            self._press_val(component, False, page)

    def move(self, x: int, y: int):
        """Moves the press to the page's pixel (x, y): a slider pressed
        follows it, running its `slide` event when its value changes; a file
        browser's entries, a select's lines, a sliding text's lines, or a
        data record's records follow it up and down, and a combo box's open
        list its way. A component a press drags goes with it (_carry). While
        `thdra` is 1, the move draws a line (_touch_dot)."""
        if self._touch_at is not None:
            self._note_touch(x, y)
        pressed = self._pressed
        if pressed is None or pressed[0] != self.page:
            return
        if self._slide(pressed[1], x, y):
            self._run_event(self.page, (pressed[1], "slide"))
        elif self._touch is not None and self._touch.component == pressed[1]:
            self._follow(self._touch, x, y)
        elif self._drag is not None and self._drag.component == pressed[1]:
            self._carry(self._drag, x, y)

    def release(self):
        """Releases the component pressed. A file browser, select, sliding
        text, combo box, or data record takes what the touch did; then the
        page's touch capture's `up` event runs (_capture); then the
        component's `up` event runs, unless its page is no longer shown, as
        when its press changed page. So the Nextion Editor's simulator ran
        them: a touch capture's `up` event read the item a combo box's
        release chose, and a file browser's and a data record's;
        a select's and a sliding text's, which a drag changes, are taken
        alike. The touch coordinates are set first (_note_touch). A touch
        begun while the screen slept, or whose press put it to sleep, runs
        nothing, and wakes it, when `thup` is 1, sending 0x87."""
        if self._touch_at is not None:
            self._note_touch(*self._touch_at, _TOUCH_RELEASED)
        # A touch that began asleep, or whose press put the screen to sleep,
        # ends as a touch on a sleeping screen: no release runs.
        if self._touched_asleep or self.asleep:
            self._touched_asleep = False
            self._pressed = self._touch = self._drag = None
            if self.asleep and self.globals.get("thup") == 1:
                self._wake()
                self._send_logged(bytes([_WOKEN_BY_TOUCH]) + END)
                self._show_wake_page()
            return
        pressed, self._pressed = self._pressed, None
        touch, self._touch = self._touch, None
        self._drag = None
        if pressed is None or pressed[0] != self.page:
            return
        self._send_touch_event(pressed[1], _TOUCH_RELEASED)
        self._press_val(pressed[1], False)
        # A list takes the touch first, so that the touch capture's event
        # reads what it chose.
        if touch is not None and touch.component == pressed[1]:
            self._touched(touch)
        self._capture(pressed[1], "up")
        if pressed[0] != self.page:
            return
        self._run_event(self.page, (pressed[1], "up"))
        if pressed[0] == self.page:
            self._draw_pressed(pressed[1])
            # A component bound to a keyboard opens it.
            lines = self._keyboard_lines(pressed[1], self.fields[self.page])
            if lines:
                self._run(self.page, lines, [None] * len(lines))

    def _send_touch_event(self, component: str, event: int):
        """Sends the touch event, 0x65, the page's ID, the component's (0 for
        the page), and the touch's `event`, 1 for a press or 0 for a release,
        when the component's `sendkey` asks for it: 2 for a press, 1 for a
        release, the page as a component does. A release whose press changed
        the page sends nothing, as it runs nothing (release)."""
        ticks = self.fields[self.page].get(component + ".sendkey", 0)
        wanted = _SENDS_PRESS if event == _TOUCH_PRESSED else _SENDS_RELEASE
        if isinstance(ticks, int) and ticks & wanted:
            self._send_logged(bytes([_TOUCH_EVENT, self.pages[self.page].number,
                                     self._ids(self.page).index(component), event]) + END)

    def _note_touch(self, x: int, y: int, event: int = None):
        """Notes a touch at the page's pixel (x, y), kept on the screen, as
        the screen's touch never leaves it: pressed (_TOUCH_PRESSED), moved
        (None), or released (_TOUCH_RELEASED). Sets the touch coordinates, and
        sends a press or a release when `sendxy` is 1 or the screen sleeps,
        as the module's docstring says. A move draws by touch, while `thdra`
        is 1: a line from the touch's last place (_touch_dot)."""
        width, height = self._touch_area
        x, y = min(max(x, 0), width - 1), min(max(y, 0), height - 1)
        lasting = event != _TOUCH_RELEASED
        if event is None and self._touch_at is not None and self._drawing_by_touch():
            # Drawing by touch: a line from the touch's last place (_touch_dot).
            self._paint_by_touch(("line", *self._touch_at, x, y, self.globals.get("thc", 0)))
        self._touch_at = (x, y) if lasting else None
        self.globals.update(tch0=x if lasting else 0, tch1=y if lasting else 0, tch2=x, tch3=y)
        if event is not None and (self.asleep or self.globals.get("sendxy") == 1):
            first = _TOUCH_PLACE_ASLEEP if self.asleep else _TOUCH_PLACE
            self._send_logged(bytes([first]) + struct.pack(">HHB", x, y, event) + END)

    def _drawing_by_touch(self) -> bool:
        """Whether a touch draws, in the colour `thc`: while `thdra` is 1, and
        the screen is awake."""
        return self.globals.get("thdra") == 1 and not self.asleep

    def _touch_dot(self):
        """Draws by touch, at a press with a place: a dot of 2 by 2 pixels,
        painted as `fill` paints, over the component pressed drawn pressed.
        Each move then draws a line from the touch's last place (_note_touch).
        The Editor's simulator drew black whatever `thc` was; the vendor's
        instruction set gives `thc`, which is taken."""
        if self._touch_at is not None and self._drawing_by_touch():
            self._paint_by_touch(("fill", *self._touch_at, 2, 2, self.globals.get("thc", 0)))

    def _paint_by_touch(self, entry: tuple):
        """Paints what a touch draws. A long drag, with no event to end, would
        paint without bound, so what was painted keeps only what still shows,
        as after an event (_commit)."""
        self.globals["painted"] = _compacted(self.globals.get("painted", []) + [entry],
                                             self.page)

    def _capture(self, component: str, event: str):
        """Runs the `event`, "down" or "up", of the touch capture of the page
        shown, if it has one, its `val` set to the ID of `component`, the
        component touched, 0 for the page itself. Of several, only the last
        in ID order runs. A component's `click` runs none (editor_machine.py
        runs it apart)."""
        captures = self._of_kind(self.page, "touch-capture")
        if not captures:
            return
        self.fields[self.page][captures[-1] + ".val"] = self._ids(self.page).index(component)
        self._run_event(self.page, (captures[-1], event))

    def _toggle(self, component: str):
        """Flips the `val` of a checkbox, radio, dual-state button, or switch
        pressed, 0 to 1 and any other value to 0, and draws it again."""
        if self._kinds[self.page].get(component) not in _TOGGLED:
            return
        fields = self.fields[self.page]
        fields[component + ".val"] = 0 if fields.get(component + ".val", 0) else 1
        self._changed(component)

    def _draw_pressed(self, component: str):
        """Draws a button again, pressed or released, over what drawing
        commands painted."""
        if self._kinds[self.page].get(component) in _PRESSED_LOOK:
            self.globals.setdefault("painted", []).append(("redraw", component))
            self.changes += 1

    def _press_val(self, component: str, pressed: bool, page: str = None):
        """Sets the `val` of a button pressed (1) or released (0), on `page`,
        or the page shown. Its drawing again is _draw_pressed's."""
        page = page or self.page
        if self._kinds[page].get(component) in _PRESSED_LOOK:
            self.fields[page][component + ".val"] = int(pressed)

    def _slide(self, component: str, x: int, y: int) -> bool:
        """Sets a slider's value to where (x, y) puts its knob's middle, as
        slider_drawing.py places the knob; returns whether it changed. Any
        other component is left alone. The knob stays centred under the
        touch, kept on the track, until code stores the slider's `val`, as
        the Nextion Editor's simulator drew it, though its `val` would place
        it a pixel or so off (scrolled). A knob the touch moved draws the
        slider again, its value changed or not."""
        if self._kinds[self.page].get(component) != "slider":
            return False
        fields = self.fields[self.page]
        value = lambda attribute, default=0: fields.get("%s.%s" % (component, attribute), default)
        vertical = value("mode") == 1
        start, length = (value("y"), value("h")) if vertical else (value("x"), value("w"))
        knob = self._knob_length(component, vertical)
        room = max(length - knob, 1)
        # Counted from the slider's first pixel: its left column, or its
        # bottom row when upright, as the Editor's simulator counts.
        along = (start + length - 1 - y if vertical else x - start) - knob // 2
        low, high = value("minval"), value("maxval", 100)
        new = low + round(min(max(along, 0), room) / room * (high - low))
        place = min(max(along, 0), max(length - knob, 0))
        moved = self._knobs.get(component) != place
        self._knobs[component] = place
        changed = new != value("val")
        if changed:
            fields[component + ".val"] = new
        if changed or moved:
            self.globals.setdefault("painted", []).append(("redraw", component))
            self.changes += 1
        return changed

    def _knob_length(self, component: str, vertical: bool) -> int:
        """A slider knob's length along its track (drawn_knob_size): `wid`
        (or `hig` when vertical), 255 standing for its picture's, or the
        track's breadth."""
        fields = self.fields[self.page]
        psta = fields.get(component + ".psta")
        length = fields.get(component + (".hig" if vertical else ".wid"), 255)
        if length == 255:
            length = fields.get(component + (".w" if vertical else ".h"), 0)
            if psta == 1:
                size = self._folder_resources.picture_size(
                    fields.get(component + ".pic2", NO_PICTURE))
                if size is not None:
                    length = size[1] if vertical else size[0]
        return drawn_knob_size(length, psta)

    def component_at(self, x: int, y: int):
        """Returns the name of the component a press at (x, y) of the page
        shown reaches: the topmost one under it that shows, or the page
        itself; None before any page shows. One whose touches are off still
        takes the press, which then runs nothing (press)."""
        if self.page is None:
            return None
        page = self.pages[self.page]
        fields = self.fields[self.page]
        for name, kind, placed in reversed(page.components[1:]):
            if not placed or not self._switched("vis", name):
                continue
            areas = [{key: fields.get("%s.%s" % (name, key), 0) for key in ("x", "y", "w", "h")}]
            if kind == "combo-box":
                # An open list belongs to its box, over what lies before it.
                areas.append(self._combos.list_area(name, component_attributes(name, fields)))
            if any(area and area["x"] <= x < area["x"] + area["w"]
                   and area["y"] <= y < area["y"] + area["h"] for area in areas):
                return name
        return self.page

    def advance(self, milliseconds: int):
        """Lets `milliseconds` pass: the timers of the page shown fall due and
        run, and its clocked components (clocked.py) step, in time order, and
        a screen idle for `thsp` seconds sleeps."""
        end = self.clock + milliseconds
        while True:
            due = [(when, name) for name, when in self._dues() if when <= end]
            if not due:
                break
            when, name = min(due)
            self.clock = max(self.clock, when)
            self._check_sleep()
            if self.asleep:
                break       # nothing steps while the screen sleeps
            if name in self._clocked:
                self._step(name)
            elif name == _OPENING:
                self._mark_slides()
                # A slide ends at its place, wherever code moved its component meanwhile.
                fields = self.fields[self.page]
                for ended, (x, y) in self._opening.ended(self.clock):
                    fields[ended + ".x"], fields[ended + ".y"] = x, y
                self._opening_due = self._opening.next_step(self.clock)
                self.changes += 1
            else:
                self._due[name] = self.clock + max(self._timer_period(name), 1)
                self._run_event(self.page, (name, "timer"))
        self.clock = max(self.clock, end)
        self._check_sleep()

    def _mark_slides(self):
        """At a step of the slides, has each component the step moved drawn
        again (_mark_moved). A first step leaves a box wholly off the
        screen, so it has none to give back."""
        places = self._opening.drawn_at(self.clock)
        self._mark_moved([(name, self._slid.get(name), place) for name, place in places.items()])
        self._slid.update(places)

    def _mark_moved(self, moved: list):
        """Has each component of `moved`, (name, the place it was drawn at,
        or None, the place it is drawn at now), drawn again, as a move by
        code is: the box it was drawn in brings back the page's background,
        the components linked to that box are drawn again, then it, at its
        new place (page_drawing.py). So it shows over what drawing commands
        painted, and what they painted goes where it has been, as the
        Nextion Editor's simulator drew a slide and a `move`. While nothing
        they painted shows, nothing is marked, as the drawing would be the
        same."""
        painted = self.globals.get("painted", [])
        if not any(entry[0] not in _DRAWING_AGAIN for entry in painted):
            return
        fields, placed, marks = self.fields[self.page], self.pages[self.page].placed, []
        hidden = self.hidden()
        for name, before, place in moved:
            # One with no place on the page is not drawn (_redraw), nor one
            # `vis` hid, which gives back no background where it was
            # (_left_box).
            if place == before or name not in placed or name in hidden:
                continue
            if before is not None:
                marks.append(("left", name, (*before, fields[name + ".w"], fields[name + ".h"])))
            marks.append(("redraw", name))
        if marks:
            self.globals["painted"] = _compacted(painted + marks, self.page)

    def next_due(self):
        """Returns when the next timer of the page shown runs, or its next
        clocked component steps, or None, as while the screen sleeps."""
        return None if self.asleep else min((when for _, when in self._dues()), default=None)

    def _dues(self) -> list:
        """Returns (name, when it next falls due) for each timer of the page
        shown that is on, and each clocked component that is stepping."""
        opening = [(_OPENING, self._opening_due)] if self._opening_due is not None else []
        return list(self._due.items()) + [(name, clocked.due)
                                          for name, clocked in self._clocked.items()
                                          if clocked.due is not None] + opening

    def _step(self, name: str):
        """Steps the clocked component `name` of the page shown: what it
        changed is drawn again, if it has a place, and what it moved at its
        new place, then the events it asks for run."""
        clocked = self._clocked[name]
        events = clocked.step(self.fields[self.page], self.clock)
        self._redraw(clocked.drawn)
        self._mark_moved(clocked.moved)
        self.changes += 1
        for event in events:
            self._run_event(self.page, (name, event))

    def _redraw(self, names: list):
        """Draws the components `names` of the page shown again, those with a
        place, over what was painted."""
        placed = [name for name in names if name in self.pages[self.page].placed]
        if placed:
            self.globals["painted"] = _compacted(
                self.globals.get("painted", []) + [("redraw", name) for name in placed],
                self.page)

    def scrolled(self) -> dict:
        """Returns where each scrolling text of the page shown has moved its
        text, how far each open list of a combo box has scrolled, and where
        a touch put each slider's knob, as page_drawing.draw_page takes
        them: {name: its text's left, or its top when it moves up or down;
        or its list's first item shown; or its knob's start along its track,
        from its start, or its bottom when upright (_slide)}."""
        return dict({name: clocked.place(self.fields[self.page])
                     for name, clocked in self._clocked.items()
                     if isinstance(clocked, ScrollingText)}, **self._combos.scrolled(),
                    **self._knobs)

    def values(self) -> dict:
        """Returns every value, as the shown page's code names them, what
        code would read of its clocked components brought up to the clock,
        as a player's `tim` (clocked.py). While an event runs, as when the
        debugger stops in it, they are the event's as they stand, as the
        debugger shows them. Only the copy returned is brought up: reading
        changes nothing."""
        if self._running is not None:
            return dict(self._running.values)
        view = self._view(self.page)
        if self.page is not None:
            self._catch_up(view)
        return view

    def components(self) -> list:
        """Returns the Components of the page shown, as page_drawing.py draws
        them: the page first, then every component, in ID order, with its
        values now, an event's in progress included, and where it is drawn
        while it slides in as its page opens, though code reads its own `x`
        and `y` (opening_effects.py). A scrolling text is drawn in the way
        it shows, which a `dir` code stored changes only at its next step,
        though code reads the `dir` it stored (scrolling_texts.py). `hidden`
        says which do not show."""
        values = {}
        for key, value in self._fields_now().items():
            if "." in key and not key.startswith(("vis ", "touch ")):
                component, attribute = key.split(".", 1)
                values.setdefault(component, {})[attribute] = value
        for name, own in values.items():
            place = self._opening.place(name, self.clock)
            if place is not None:
                values[name] = dict(own, x=place[0], y=place[1])
        for name, clocked in self._clocked.items():
            if isinstance(clocked, ScrollingText) and name in values:
                values[name] = dict(values[name], dir=clocked.way)
        return [Component(name, kind, values.get(name, {}))
                for name, kind, _ in self.pages[self.page].components]

    def drawing_inputs(self) -> DrawingInputs:
        """Returns what the screen shows, for the drawing: the page shown, as
        drawn while `ref_stop` holds (_drawn_components, _drawn_hidden). After
        a page change while it held, the page before, as it showed then,
        until `ref_star`: the Nextion Editor's simulator kept showing it,
        even once code changed the new page (tests/fixtures/
        drawing-assumptions/, page30)."""
        if self._kept_drawing is not None:
            return self._kept_drawing
        return DrawingInputs(self.page, self.entered, self._drawn_components(),
                             self._drawn_hidden(), self.painted(), self._drawn_pressed(),
                             self.waves(),
                             self.listings(), self.select_moves(), self.scrolled(),
                             (self.globals.get("spax", 0), self.globals.get("spay", 0)))

    def _drawn_pressed(self):
        """The component the drawing shows held down: the one held, but for
        a file browser, a sliding text, or a data record a touch has not
        scrolled. `left` 1 shows their scroll bar's thumb while a touch
        scrolls them, and the Nextion Editor's simulator showed none, nor
        drew them again, while they were only held (tests/fixtures/
        drawing-assumptions/, page44 and page45)."""
        pressed, touch = self.pressed(), self._touch
        if (pressed is not None and touch is not None and touch.component == pressed
                and touch.kind in _WITH_SCROLL_BAR and not touch.scrolled):
            return None
        return pressed

    def _drawn_components(self) -> list:
        """Returns the Components of the page shown as the screen draws them:
        as components() gives them, but for those code changed between
        `ref_stop` and `ref_star`, drawn as they were at `ref_stop`."""
        components, held = self.components(), self._drawing_held
        if held is None or held.page != self.page:
            return components
        return [held.components.get(component.name, component)
                if component.name in held.changed else component for component in components]

    def _drawn_hidden(self) -> set:
        """Returns the components of the page shown that the screen does not
        draw: as hidden() gives them, but one `vis` hid between `ref_stop` and
        `ref_star` still shows until `ref_star`; one it showed then shows at
        once."""
        hidden, held = self.hidden(), self._drawing_held
        if held is None or held.page != self.page:
            return hidden
        return hidden & held.hidden

    def drawing_stopped(self, stopped: bool, machine: EditorMachine):
        """At `ref_stop` (`stopped`), keeps the page shown's components and
        those hidden as they are, for the drawing (_drawn_components); at
        `ref_star`, lets them go, and the page before a page change with
        them (drawing_inputs). A second `ref_stop` keeps what the first
        kept. The `ref_star` that shows a page entered meanwhile starts its
        slides, from the values `machine` holds then (page_changed)."""
        if not stopped:
            self._drawing_held = self._kept_drawing = None
            if self._slides_wait:
                self._slides_wait = False
                self._start_opening(machine.values)
        elif self._drawing_held is None and self.page is not None:
            self._drawing_held = _HeldDrawing(
                self.page, {component.name: component for component in self.components()},
                self.hidden(), set())

    def pressed(self):
        """Returns the component of the page shown held down, or None."""
        pressed = self._pressed
        return pressed[1] if pressed is not None and pressed[0] == self.page else None

    def hidden(self) -> set:
        """Returns the components of the page shown that `vis` hid, and those
        waiting their turn to slide in as the page opens."""
        return {name for name in self._ids(self.page)[1:]
                if not self._switched("vis", name)} | self._opening.waiting(self.clock)

    def touch_held(self) -> bool:
        """Returns whether a press given a place is held: from press until
        release, or until the app starts again. A press whose event stopped
        with an error stays held."""
        return self._touch_at is not None

    def touch_area(self) -> tuple:
        """Returns the (width, height) of the screen's touch, in the page's
        pixels: the size of every page."""
        return self._touch_area

    def _switched(self, kind: str, name: str) -> int:
        """Returns whether `vis` (kind "vis") shows, or `tsw` ("touch") lets
        take touches, a component of the page shown: as the last command
        naming it, or 255 for every component, left it; at first, yes."""
        fields = self._fields_now()
        return fields.get("%s %s" % (kind, name), fields.get("%s 255" % kind, 1))

    def painted(self) -> list:
        """Returns what drawing commands painted on the page shown, in order,
        with where the code had a component drawn again (page_drawing.py),
        an event's in progress included."""
        running = self._running
        source = running.values if running is not None else self.globals
        return list(source.get("painted", []))

    def _fields_now(self) -> dict:
        """Returns the values of the page shown, with those of the event
        running, if any, as it would keep them."""
        fields = self.fields[self.page]
        running = self._running
        if running is None:
            return fields
        own = self.pages[self.page].owned
        now = {key: value for key, value in fields.items()
               if not key.startswith(("vis ", "touch ")) or key in running.values}
        for name, value in running.values.items():
            if (name.split(".", 1)[0] in own and "." in name) or \
                    name.startswith(("vis ", "touch ")):
                now[name] = value
        return now

    # The machine's hooks (EditorMachine's `screen`).

    def page_changed(self, name: str, machine: EditorMachine):
        """Changes page in the middle of the event `machine` runs, as the
        module's docstring says."""
        new = self._page_named(name, machine)
        old = self.page
        # Waking into the page `wup` gives runs no unload event. A page
        # change the wake page's own events make is an ordinary one.
        waking, self._waking = self._waking, False
        if old is not None and not waking:
            key = (old, "unload")
            if key in self.pages[old].code:
                machine.run(self.pages[old].code[key], self.pages[old].places.get(key))
        self._commit(machine.values, old)
        # While `ref_stop` holds, the screen keeps showing the page before,
        # as it showed then, its unload event's painting included, until
        # `ref_star`. A second page change keeps what the first kept.
        if self._drawing_held is not None and self._kept_drawing is None:
            self._kept_drawing = self.drawing_inputs()
        self._drawing_held = None
        if old is not None and self.leaving is not None:
            self.leaving()
        self._enter(new)
        self._switch(machine, new)
        code, places = self.pages[new].code, self.pages[new].places
        self.loading = True
        try:
            returned = (new, "load") in code and \
                machine.run_event(code[(new, "load")], places.get((new, "load")))
        finally:
            self.loading = False
        # The screen draws the page once its load event ends. The page covers
        # what the event painted, and shows what it changed. While the page
        # before still shows, what the new page's code changes or paints waits.
        machine.values["painted"] = [("ref_stop",)] if self._kept_drawing is not None else []
        # A page whose page before still shows once its load event ends
        # slides in at `ref_star` (drawing_stopped). A `ref_star` in the load
        # event let the hold go.
        self._slides_wait = self._kept_drawing is not None
        if not self._slides_wait:
            self._start_opening(machine.values)
        # A load event that a return ended leaves out loadend.
        if (new, "loadend") in code and not returned:
            machine.run(code[(new, "loadend")], places.get((new, "loadend")))
        # The old page's event ends here: the code after the command does not run.
        raise _EventEnded()

    def stored(self, name: str, value, machine: EditorMachine, before=None):
        """Acts on a value the code stored, `before` being what the name
        held: the clock moves on during a `delay`, `sleep` sleeps or wakes, a
        timer turned on or given another period starts counting again, and
        a clocked component (clocked.py) hears of a change to one of its
        attributes."""
        head = name.split(".", 1)[0] if "." in name else None
        if self._drawing_held is not None and head is not None:
            self._drawing_held.changed.add(head)
        if name == "%s.val" % head:
            # Its `val` places a slider's knob again, even storing the value it
            # had (_slide).
            self._knobs.pop(head, None)
        if self.page is not None and name.startswith("vis "):
            # Code hiding or showing a component puts it in its place at
            # once; `vis 255` puts every one. A move does not end its slide.
            target = name[4:]
            for ended in self.pages[self.page].placed if target == "255" else [target]:
                self._opening.end(ended)
        if name in ("vis 255", "touch 255"):
            # 255 stands for every component: what each was given before no
            # longer counts.
            kind = name[:-3]
            for earlier in [key for key in machine.values if key.startswith(kind)]:
                if earlier != name:
                    del machine.values[earlier]
            # Each component of global scope of the page shown takes it as its
            # own, and keeps it on another page. Those of the other pages keep
            # what they had.
            if self.page is not None:
                for kept in self.pages[self.page].global_names:
                    machine.values[kind + kept] = value
        if self.page is not None and (head in self.pages[self.page].placed or
                                      (name.startswith("vis ") and value == 1)):
            # A component the code changed, or showed, is drawn again over
            # what drawing commands painted, even to the value it held, as the
            # Editor's simulator drew each type tried. Every component shown
            # is the page drawn again. One that code moved or resized first
            # marks the box it left (_left_box).
            shown = head if head is not None else name[4:]
            if shown == "255":
                shown = self.page
            painted = machine.values.setdefault("painted", [])
            left = self._left_box(head, name[len(head) + 1:] if head else "", before,
                                  machine.values)
            if left is not None:
                painted.append(("left", head, left))
            if not painted or painted[-1] != ("redraw", shown):
                painted.append(("redraw", shown))
        if name in _TIME_PARTS:
            self._set_time(name, value)
        if name == "recmod":
            self._reparse_mode(value, before, machine)
        elif name == "addr" and value != before:
            self._line.set_address(value)
            self._write_log("addr: address mode is on, for the address %d" % value if value
                            else "addr: address mode is off")
        if name == "delay":
            self.clock += max(value, 0)
            self._catch_up(machine.values)
        elif name == "sleep":
            if self.asleep and not value:
                self._wake()
                self._show_wake_page(machine)
            elif value and not self.asleep:
                # Asleep from now: its players stop where they are.
                self._catch_up(machine.values)
                self.asleep = True
                # Code putting the screen to sleep runs no more of its event,
                # as the Nextion Editor's simulator ran no more of a press's,
                # a timer's, or a page's load or unload event. After a load,
                # the page's loadend did not run; after an unload, the page
                # change did not happen.
                if machine.in_event:
                    raise _EventEnded()
        elif self.page is not None and (name.endswith(".en") or name.endswith(".tim")):
            timer = name.rsplit(".", 1)[0]
            if (timer, "timer") in self.pages[self.page].code:
                self._schedule(timer, machine.values)
        if head in self._clocked:
            self._clocked[head].changed(name[len(head) + 1:], machine.values, self.clock)
        if head is not None and self.page is not None and name[len(head) + 1:] in _LIST_MOVED:
            self._worked(head, name[len(head) + 1:], machine.values)

    def _reparse_mode(self, value: int, before, machine: EditorMachine):
        """Turns protocol reparse mode on when `recmod` becomes other than 0,
        or off when it becomes 0 (serial_line.py). Turned on by a typed
        instruction, the mode takes that instruction's answer too: the
        Nextion Editor's simulator answered nothing to a typed `recmod=2`,
        whatever `bkcmd` was set to. Turned on by an event's code, it leaves
        the answers as they are: a typed `click` whose event turned it on
        answered its success first in that simulator, as a typed `click`
        answers before its event runs. Turned off, the machine empties the
        buffer (EditorMachine._store)."""
        if value and not before:
            self._line.start_reparse()
            if not machine.in_event:
                self._answered = True
            self._write_log("recmod: protocol reparse mode starts: the serial line's bytes go "
                            "into the buffer")
        elif before and not value:
            self._line.end_reparse()
            self._write_log("recmod: protocol reparse mode ends")

    # File browsers, selects, sliding texts, combo boxes, and data records.

    def _worked(self, component: str, attribute: str, values: dict):
        """Moves a combo box of the page shown's open list after the code set
        its `val`, `down`, `path`, or `qty`, as its drawing shows it
        (combo_boxes.py). The machine then works the box's values
        (list_working.py), which a `val` within its items, a `down` of 1, or
        a new `path` or `qty`, the ones that move the list, leave as they
        are: so the list moves by what the code set."""
        if self._kinds[self.page].get(component) == "combo-box":
            self._combos.code_set(component, attribute, component_attributes(component, values))

    def _follow(self, touch: _Touch, x: int, y: int):
        """A press on a list or a sliding text moved to the page's pixel
        (x, y): the browser's entries, the sliding text's lines, or the data
        record's records follow it, as far as `maxval_y` lets them scroll;
        the select's lines follow it, to be settled at the release; a combo
        box's open list follows it an item at a time (combo_boxes.py). A
        sliding text's lines, a combo box's list, and a data record's
        records following a drag is assumed: the Editor's simulator could
        not be dragged (tools/editor/README.md)."""
        fields, name = self.fields[self.page], touch.component
        if touch.kind == "combo-box":
            if self._combos.follow(name, component_attributes(name, fields), touch.start_scroll,
                                   x - touch.x, y - touch.y):
                touch.scrolled = True
                self._changed(name)
        elif touch.kind in ("file-browser", "sliding-text", "data-record"):
            scroll = min(max(touch.start_scroll - (y - touch.y), 0),
                         fields.get(name + ".maxval_y", 0))
            if scroll != fields.get(name + ".val_y", 0):
                fields[name + ".val_y"] = scroll
                touch.scrolled = True
                self._changed(name)
        elif y - touch.y != touch.moved:
            touch.moved = y - touch.y
            self._changed(name)

    def _touched(self, touch: _Touch):
        """What a touch on a list or a sliding text does as it ends, before
        the `up` event runs. On a browser, a press that scrolled
        nothing is a tap on the entry under it: a file is selected, a folder
        opened; a press that scrolled selects nothing (assumed). A select's
        lines settle on the one nearest its middle: `val` goes forward a
        line for each `hig` the press moved up, back for each down, rounded,
        counted round. A press that did not move changes nothing. A sliding
        text's lines stay where the press left them; it is drawn again, its
        scroll bar's thumb hidden unless `left` is 2. A combo box opens or
        closes its list, or chooses an item of it (combo_boxes.py). On a data
        record, a press that scrolled nothing is a tap on the record under
        it (_tap_record); one that scrolled chooses nothing (assumed)."""
        fields, name = self.fields[self.page], touch.component
        if touch.kind == "combo-box":
            changes = self._combos.released(name, component_attributes(name, fields), touch.x,
                                            touch.y, touch.scrolled)
            fields.update({"%s.%s" % (name, key): value for key, value in changes.items()})
            if "val" in changes:
                self._lists.chose(self.page, name, changes["val"], self.globals)
        elif touch.kind == "file-browser":
            if not touch.scrolled:
                self._tap(name, touch.x - fields.get(name + ".x", 0),
                          touch.y - fields.get(name + ".y", 0))
        elif touch.kind == "data-record":
            if not touch.scrolled:
                self._tap_record(name, touch.y)
        elif touch.kind == "select" and touch.moved:
            lines = path_lines(fields.get(name + ".path", SELECT_DEFAULTS["path"]))
            height = max(fields.get(name + ".hig", SELECT_DEFAULTS["hig"]), 1)
            steps = (height // 2 - touch.moved) // height
            val = fields.get(name + ".val", 0)
            if lines and isinstance(val, int):
                fields[name + ".val"] = (val + steps) % len(lines)
                fields[name + ".txt"] = lines[fields[name + ".val"]]
        self._changed(name)

    def _tap_record(self, record: str, y: int):
        """A tap on the data record `record` at the page's row `y`: chooses
        the record under it, its `val` and `txt`, when `dis` is 1
        (data_record_drawing.record_at)."""
        fields = self.fields[self.page]
        attributes = component_attributes(record, fields)
        if attributes.get("dis", 1) != 1:
            return
        data_file = self._data_file(record, fields, self.globals)
        count = len(data_file.records()) if data_file is not None else 0
        number = record_at(attributes, count, inside_box(attributes), y)
        if number is not None:
            fields[record + ".val"] = number
            self._show_data_file(record, fields, data_file)

    def _tap(self, browser: str, x: int, y: int):
        """A tap on a file browser at its pixel (x, y). On a file, it selects
        it; on a folder, it opens it. On a cell past the last entry, `val` is
        the number of entries, and `txt` empty. Between two cells, or right of
        the last column, `val` is -1, and `txt` empty, whatever was chosen.
        Left of the first column, and on a browser that draws no entry, it
        does nothing. Above the first row, on the border, it counts as just
        inside it (BrowserLayout.place_at)."""
        fields = self.fields[self.page]
        entries = self._lists.listing(self.page, browser, self.globals)
        layout = self._lists.browser_layout(browser, fields)
        index = None if layout is None else layout.place_at(
            x, y, fields.get(browser + ".val_y", 0))
        if index is None:
            return
        if not 0 <= index < len(entries):
            fields[browser + ".val"] = -1 if index < 0 else len(entries)
            fields[browser + ".txt"] = ""
            return
        if entries[index].endswith("/"):
            folder = str(fields.get(browser + ".dir", ""))
            if folder and not folder.endswith("/"):
                folder += "/"
            fields[browser + ".dir"] = folder + entries[index]
            self._lists.list_folder(self.page, browser, fields, self.globals)
        else:
            fields[browser + ".val"] = index
            fields[browser + ".txt"] = entries[index]

    def _carry(self, drag: _Drag, x: int, y: int):
        """A drag moved to the page's pixel (x, y): its component goes with
        it, its `x` and `y` moving as the touch moved, its whole rectangle
        kept on the screen, or its left and top when it is larger, and its
        slide in as its page opens, if any, ended. All of this is assumed:
        the Editor tool cannot drag."""
        fields, name = self.fields[self.page], drag.component
        width, height = self._touch_area
        place = (max(min(drag.left + x - drag.x, width - fields.get(name + ".w", 0)), 0),
                 max(min(drag.top + y - drag.y, height - fields.get(name + ".h", 0)), 0))
        if place != (fields.get(name + ".x"), fields.get(name + ".y")):
            fields[name + ".x"], fields[name + ".y"] = place
            self._opening.end(name)
            self._changed(name)

    def _left_box(self, component, attribute: str, before, values: dict):
        """The box (x, y, w, h) that a component of the page shown had before
        code stored its `attribute`, which held `before`, for the drawing to
        put the page's background back there. None when no box was left:
        another attribute than x, y, w, or h, the value it held, or the page
        itself. None too for a component not shown, and for one its opening
        effect slides in, as it is drawn where it slides, as the Editor's
        simulator showed (tests/fixtures/drawing-assumptions/, page37 and
        page41)."""
        if (attribute not in _PLACE_KEYS or not isinstance(before, int)
                or component in (None, self.page)
                or component not in self.pages[self.page].placed):
            return None
        box = {key: values.get("%s.%s" % (component, key)) for key in _PLACE_KEYS}
        if box[attribute] == before or not all(isinstance(side, int) for side in box.values()):
            return None
        if component in self.hidden() or self._opening.place(component, self.clock) is not None:
            return None
        box[attribute] = before
        return tuple(box[key] for key in _PLACE_KEYS)

    def _changed(self, component: str):
        """Has a component the simulation itself changed drawn again."""
        self.globals.setdefault("painted", []).append(("redraw", component))
        self.changes += 1

    def listings(self) -> dict:
        """Returns the entries each file browser of the page shown lists,
        {browser: [names, a folder's ending with "/"]}, and the records each
        data record shows, {data record: [texts, the oldest first]}, as
        page_drawing.draw_page takes them."""
        found = {browser: list(entries) for (page, browser), entries
                 in self.globals[FILE_BROWSER_LISTINGS].items() if page == self.page}
        if self.page is not None:
            codec = TextCodec(self.encoding)
            fields = self.fields[self.page]
            for name in self._of_kind(self.page, "data-record"):
                if self._is_shut_out(name, fields, self.globals):
                    found[name] = UNOPENED
                else:
                    data_file = self._data_file(name, fields, self.globals)
                    found[name] = [codec.decode_keeping_bytes(record)
                                   for record in (data_file.records() if data_file else [])]
        return found

    def select_moves(self) -> dict:
        """Returns how far a press has moved the lines of the select it
        holds, in pixels, down being more: {select: pixels}, or none."""
        touch = self._touch
        if touch is None or touch.kind != "select" or not touch.moved:
            return {}
        return {touch.component: touch.moved}

    def by_index(self, name: str, machine: EditorMachine):
        """Returns the name a name of the screen's arrays stands for, as the
        page's code names it: `p[1].b[5].txt` or `p[1].t0.txt`, a page by its
        number, then a component by its ID or its name; `b[5].txt`, a
        component of the page shown by its ID. Another page's component
        goes by its page's name, which reaches only those of global scope,
        as on the screen. None for none such."""
        match = _BY_INDEX.fullmatch(name)
        if match is None or match[1] is None and match[2] is None or self.page is None:
            return None
        number = int(match[1]) if match[1] is not None else self.pages[self.page].number
        if number >= len(self.page_names):
            return None
        page = self.pages[self.page_names[number]]
        if match[2] is None:
            component = match[3]
        elif int(match[2]) < len(page.components):
            component = page.components[int(match[2])][0]
        else:
            return None
        if page.name == self.page:
            return "%s.%s" % (component, match[4])
        return "%s.%s.%s" % (page.name, component, match[4])

    def released(self, component: str, machine: EditorMachine):
        """After a `click` releases `component`: opens its keyboard, if any."""
        lines = self._keyboard_lines(component, machine.values)
        if lines:
            machine.run(lines)

    def _keyboard_lines(self, component: str, values: dict) -> list:
        """Returns the code the screen runs on the release of a component
        bound to a keyboard by its `key`: it gives the Editor's system page
        of that number, one of its four keyboards, the caller's page number
        and the component's ID, in its `loadpageid` and `loadcmpid`, then
        opens it, as the keyboard's own code expects. It follows the
        component's Touch Release event, as in the Editor's simulator: a
        number's release event setting its `val` gave the keypad that value."""
        kind = values.get(component + ".key")
        keyboard = next((page for page in self.pages.values()
                         if kind is not None and page.system_page == kind), None)
        if keyboard is None or self.page is None or keyboard.name == self.page:
            return []
        shown = self.pages[self.page]
        ids = self._ids(self.page)
        if component not in ids:
            return []
        lines = ["%s.%s.val=%d" % (keyboard.name, name, value)
                 for name, value in (("loadpageid", shown.number),
                                     ("loadcmpid", ids.index(component)))
                 if name in keyboard.global_names]
        return lines + ["page %s" % keyboard.name]

    def random(self, low: int, high: int) -> int:
        """Returns what reading `rand` gives: a number from `low` to `high`,
        from a generator seeded alike at each start, so that a run repeats."""
        return self._random.randint(min(low, high), max(low, high))

    def takes_pin_write(self, name: str) -> bool:
        """Returns whether the GPIO pin code names `name`, such as "pio2",
        takes what code writes to it. An output does. An input does not: it
        reads its level (gpio_pins.py). The log notes a write it does not take.
        A screen without GPIO has no inputs: the build and a typed line's
        check refuse its code naming a pin, before it comes here."""
        if self._has_gpio() and self._pins.is_input(pin_number(name)):
            self._write_log("GPIO: %s is an input, and keeps its level" % name)
            return False
        return True

    def set_input(self, pin: int, level: int):
        """Sets the level something outside the screen gives the GPIO pin
        `pin`, 0 to 7, as a button or a switch wired to it would. An input
        reads it. A bound pin's falling level runs its component's Press
        event, and its rising level its Release event, as `click` runs them
        (gpio_pins.py). Raises NxwrightError for a pin outside 0 to 7, a
        level other than 0 or 1, or a screen without GPIO."""
        if not self._has_gpio():
            raise NxwrightError(_NO_GPIO)
        level = checked_level(pin, level)
        edge = self._pins.set_level(pin, level)
        if self._pins.is_input(pin):
            self.globals[PIN_NAMES[pin]] = level
        if edge is not None and self.page is not None:
            component, event = edge
            self._run(self.page, ["click %s,%d" % (component, event == "down")], [None])

    def pins(self):
        """Returns each GPIO pin as {"mode", "component", "level"}, by pin
        number (gpio_pins.py), or None for a screen without GPIO. The level
        is what the pin reads: an input's level, or what code last wrote to
        an output."""
        if not self._has_gpio():
            return None
        view = self._pins.view()
        for pin, entry in enumerate(view):
            if not self._pins.is_input(pin):
                entry["level"] = self.globals[PIN_NAMES[pin]]
        return view

    def _has_gpio(self) -> bool:
        """Returns whether the screen has GPIO pins (_series_has_gpio)."""
        return _series_has_gpio(self._series)

    def _configure_pin(self, entry: tuple, machine: EditorMachine):
        """Runs a `cfgpio` the machine recorded, ("cfgpio", pin, mode,
        component). A pin it makes an input reads its level at once."""
        _, pin, mode, component = entry
        if self._pins.configure(pin, mode, component) and self._pins.is_input(pin):
            machine.values[PIN_NAMES[pin]] = self._pins.levels[pin]

    def reset_asked(self):
        """Notes that the code ran `rest`: the app starts again once the
        event ends, its EEPROM kept, as the screen's is."""
        self._reset = True

    # The work.

    def _run_event(self, page: str, key: tuple) -> bool:
        """Runs one event of `page`, if it has code, as a top-level event.
        Returns whether a return ended it."""
        code = self.pages[page].code
        return key in code and self._run(page, code[key], self.pages[page].places.get(key))

    def _run(self, page: str, lines: list, places: list, given: dict = None) -> bool:
        """Runs `lines` on `page`'s machine, or on program.nx's when `page` is
        None, and keeps what they leave. `given` values are set first.
        Returns whether a return ended them."""
        returned = False
        if self.page is not None:
            self._catch_up(self.fields[self.page])
        values = self._view(page)
        values.update(given or {})
        machine = self._machine(page, values)
        try:
            self._running = machine
            returned = machine.run_event(lines, places)
        except _EventEnded:
            pass
        finally:
            self._running = None
            self._commit(machine.values, self.page)
        self._after_code()
        return returned

    def _machine(self, page: str, values: dict) -> EditorMachine:
        """The machine that runs code on `page`, or program.nx's when `page`
        is None, from `values`: the same for an event and for a typed line,
        the screen's series and the debugger's recorder among what it takes."""
        return EditorMachine(values, self.pages[page].code if page else {}, page,
                             self.encoding, self.recorder,
                             self.pages[page].places if page else {}, screen=self,
                             cards=self.cards, macros=self.macros, components=self._ids(page),
                             resources=self._resources, series=self._series,
                             pinyin_table=self.pinyin_table,
                             folder_resources=self._folder_resources)

    def _after_code(self, answer=None):
        """What follows code the screen ran, an event's or a typed line's, its
        values kept: the screen starts again if it ran `rest`; then
        `answer()`, a typed line's answer, if given; then the serial
        instructions held, if it ran `com_star`; then the moves it queued."""
        if self._reset:
            self._start_again_by_rest()
        if answer is not None:
            answer()
        self._resume_when_asked()
        self._start_moves()

    def answer_typed_now(self):
        """Answers the instruction typed with its success now, as `bkcmd`
        asks, as a typed `click` is answered before its event runs; what the
        event sends follows. Nothing is answered after it."""
        self._return_code(0x01, True)
        self._answered = True

    def take_transparent_data(self, word: str, numbers: list):
        """Starts the transfer of `addt`, `wept`, or `twfile`, with its
        arguments checked (EditorMachine._transparent_data, _twfile). The
        screen answers FE FF FF FF, whatever `bkcmd` asks, in place of the
        command's success, and takes the next bytes of the serial line as
        data. Once they are in, it answers FD FF FF FF, and `addt` adds each
        byte as a point, as `add` does, `wept` writes them to the EEPROM, or
        `twfile` writes them as its file (_end_transfer). A count of 0
        answers both at once."""
        self._answered = True
        *place, count = numbers
        if word == "addt":
            self._write_log("addt: the next %d bytes are points of channel %d of the waveform "
                            "of ID %d" % (count, place[1], place[0]))
            done = partial(self._add_points, *place)
        elif word == "wept":
            self._write_log("wept: the next %d bytes go to the EEPROM at %d" % (count, place[0]))
            done = partial(self._write_transferred, place[0])
        else:
            self._write_log("twfile: the next %d bytes are the file %s" % (count, place[0]))
            done = partial(self._write_transferred_file, place[0])
        under_way = self._line.transfer()
        if under_way is not None:
            self._write_log("serial line: the transfer under way ends, %d bytes short"
                            % under_way.left)
            self._line.drop_transfer()
        self._send_logged(bytes([0xFE]) + END)
        transfer = Transfer(count, done)
        if count == 0:
            self._end_transfer(transfer)
        else:
            self._line.start_transfer(transfer)

    def _end_transfer(self, transfer: Transfer):
        """Ends a transfer that has its bytes: answers FD FF FF FF, then does
        what its command does with them."""
        self._send_logged(bytes([0xFD]) + END)
        transfer.done(bytes(transfer.data))

    def _add_points(self, component_id: int, channel: int, data: bytes):
        """Adds each byte of `data` as a point of `channel` of the waveform
        of ID `component_id`, as `add` adds one (_wave)."""
        if self.page is None:
            return
        values = self._view(self.page)
        for byte in data:
            self._wave(("add", component_id, channel, byte), values)

    def _write_transferred_file(self, path: str, data: bytes):
        """Writes `data` as the SD card's file `path`, for `twfile`: made when
        it is missing, then written, so that a file of that name is
        replaced. What the card's folder or the disk refuses, as a path that
        names a folder, writes nothing, and is recorded with the file
        errors. The screen has answered FD FF FF FF by then."""
        try:
            write_card_file(self.cards, path, data, self.globals)
        except (CardRefusal, OSError):
            record, entry = "file errors", ("twfile", path)
        else:
            record, entry = "file commands", ("twfile", path, len(data))
        self.globals.setdefault(record, []).append(entry)
        self._write_log(LOGGED[record](entry, self.encoding))

    def _write_transferred(self, address: int, data: bytes):
        """Writes `data` to the EEPROM at `address`, and to its file, as
        `wepo` writes. A range past the EEPROM's last byte writes nothing."""
        if not data:
            return
        if address + len(data) > EEPROM_SIZE:
            self._write_log("wept: the EEPROM has no byte %d, so nothing was written"
                            % EEPROM_SIZE)
            return
        eeprom = self.globals["eeprom"]
        self.globals["eeprom"] = eeprom[:address] + data + eeprom[address + len(data):]
        self._write_log(LOGGED["eeprom accesses"](("wepo", address, data), self.encoding))
        if self.eeprom_file is not None:
            self._save_eeprom(self.globals["eeprom"])

    def refused(self, code: int, typed: bool):
        """Answers a command the screen refuses with its return code, as
        `bkcmd` asks: in place of success for the instruction typed itself,
        `typed`; at once for a line of an event's code, whose event goes on,
        one a typed `click` runs too (editor_machine.py)."""
        if typed:
            self._refused = code
        else:
            self._return_code(code, False)

    def move_given(self, given: tuple):
        """Logs a `move` of the page shown, `given` as the machine read its
        arguments (EditorMachine.move_arguments), and queues one over time
        (moves.py). It starts in its turn, once the code that gave it has
        ended (_start_moves). The machine has put a move of no time at its
        end already. A move for a component that already has a move of its
        priority is dropped, and the log says so."""
        moves = self._clocked.get(MOVES)
        if moves is None:
            self._write_log("move %s: no page shows yet, so nothing moves" % given[0])
            return
        component, x1, y1, x2, y2, priority, time = given
        said = "move %s from (%d, %d) to (%d, %d) in %d ms, priority %d" \
            % (component, x1, y1, x2, y2, time, priority)
        if time > 0 and not moves.add(Move(component, (x1, y1), (x2, y2), priority, time)):
            said += ": dropped, as %s has a move of that priority" % component
        self._write_log(said)

    def _start_moves(self):
        """Starts what the moves queued, once the code that queued them has
        ended, so that one event's moves compete by priority (moves.py)."""
        moves = self._clocked.get(MOVES)
        if moves is not None and moves.choose(self.fields[self.page], self.clock):
            self._mark_moved(moves.moved)
            self.changes += 1

    def recorded(self, record: str, entry, machine: EditorMachine):
        """Logs what reached outside the screen, as the machine records it,
        and keeps the points of the page's waveforms. Code's `com_stop` and
        `com_star` hold and resume the serial line (_take_serial)."""
        serial_line = record == "other commands" and entry in _SERIAL_LINE
        # A move is logged as the screen takes it (move_given).
        moved = record == "other commands" and entry[0] == "move"
        describe = LOGGED.get(record)
        if (record == "other commands" and entry[0] in PINYIN_COMMANDS
                and not self._said_no_pinyin_table):
            # The machine records them only without a pinyin table.
            self._said_no_pinyin_table = True
            self._write_log(_NO_PINYIN_TABLE % entry[0])
        if describe is not None and not serial_line and not moved:
            self._write_log(describe(entry, self.encoding, self.log_formats["sent"])
                            if record in SENT else describe(entry, self.encoding))
        if record in SENT and self.sending is not None:
            try:
                data = SENT[record](entry, self.encoding)
            except NxwrightError:
                pass        # the log says it could not be written
            else:
                self._send(data)
        if record == "replies":
            self._answered = True
        if record == "gpio" and entry[0] == "cfgpio":
            self._configure_pin(entry, machine)
        if record == "eeprom accesses" and entry[0] == "wepo" \
                and self.eeprom_file is not None:
            self._save_eeprom(machine.values["eeprom"])
        if record == "component errors":
            # The Editor's simulator answered 02, an invalid component ID, as
            # `bkcmd` asks, and went on with the event.
            self._return_code(0x02, False)
        if serial_line:
            if entry == ("com_stop",):
                self._write_log("com_stop: the serial line's instructions are held")
                self._stop_serial()
            else:
                self._write_log("com_star: the held instructions run once this event ends")
                self._resuming = True
        if record == "waveform" and self.page is not None:
            self._wave(entry, machine.values)
        # The recorder copies a list that changed at each step, so a record
        # growing through a long event would cost time and memory without
        # bound: each keeps its last entries as they come, and the waveforms'
        # points, kept apart, need no record at all.
        entries = machine.values[record]
        keep = 0 if record == "waveform" else _MOST_KEPT
        if len(entries) > keep:
            del entries[:len(entries) - keep]

    def _wave(self, entry: tuple, values: dict):
        """Adds a point to a waveform's channel (`add`), or clears channels
        (`cle`, 255 for all). A channel keeps as many points as the waveform
        is wide: the latest."""
        names = {values.get(name + ".id"): name for name in self._of_kind(self.page, "waveform")}
        component = names.get(entry[1])
        if component is None:
            return
        channels = self._waves.setdefault(component, {})
        if entry[0] == "cle":
            if entry[2] == 255:
                channels.clear()
            else:
                channels.pop(entry[2], None)
        else:
            points = channels.setdefault(entry[2], [])
            points.append(entry[3])
            del points[:max(len(points) - max(values.get(component + ".w", 0), 1), 0)]
        self.changes += 1

    def waves(self) -> dict:
        """Returns the points of the waveforms of the page shown, as
        {waveform: {channel: [values, oldest first]}}."""
        return {name: {channel: list(points) for channel, points in channels.items()}
                for name, channels in self._waves.items()}

    def _save_eeprom(self, eeprom: bytes):
        """Writes the whole EEPROM to its file, in place: Windows refuses a
        new file put in the place of one another program holds open. A write
        refused is said in the log, and the simulation goes on: the next
        write puts the whole EEPROM in the file again."""
        try:
            self.eeprom_file.write_bytes(eeprom)
        except OSError as error:
            self._write_log("EEPROM: the file %s could not be written: %s"
                            % (self.eeprom_file, error.strerror or error))

    def _write_log(self, line: str):
        self.log.append((self.clock, line))

    def _time_now(self) -> datetime:
        """The real-time clock's time now."""
        time, clock = self._time_at
        return time + timedelta(milliseconds=self.clock - clock)

    def _set_time(self, name: str, value: int):
        """Sets one part of the real-time clock's time, from now on."""
        try:
            time = self._time_now().replace(**{_TIME_PARTS[name]: value})
        except (ValueError, OverflowError):
            return
        self._time_at = (time, self.clock)

    def _view(self, page: str) -> dict:
        """Returns the values as `page`'s code names them, or program.nx's
        when `page` is None: the globals, the real-time clock, the page's own
        values, and the components of global scope of the other pages, after
        their page."""
        values = dict(self.globals)
        values.update(_clock_values(self._time_now()))
        for other in self.pages.values():
            if other.name != page:
                values.update({"%s.%s" % (other.name, name): value
                               for name, value in self.fields[other.name].items()
                               if name.split(".", 1)[0] in other.global_names})
        if page is not None:
            values.update(self.fields[page])
            values["dp"] = self.pages[page].number
            values["text limits"] = dict(self.pages[page].text_limits)
        return values

    def _commit(self, values: dict, page: str):
        """Keeps the values a machine left, as `page`'s code names them."""
        self.changes += 1
        own = self.pages[page].owned if page else set()
        if page:
            # A `vis 255` or `tsw 255` takes back what each component was given.
            for key in [key for key in self.fields[page]
                        if key.startswith(("vis ", "touch ")) and key not in values]:
                del self.fields[page][key]
        for name, value in values.items():
            head = name.split(".", 1)[0] if "." in name else None
            if name in _PER_RUN:
                continue
            if page and (head in own or name.startswith("vis ") or name.startswith("touch ")):
                self.fields[page][name] = value
            elif head in self.pages and name[len(head) + 1:].split(".", 1)[0] in \
                    self.pages[head].global_names:
                self.fields[head][name[len(head) + 1:]] = value
            else:
                self.globals[name] = value
        # A simulation never ends: its records keep only their last entries,
        # the log having them all, and what was painted only what still shows.
        for record in _TRIMMED:
            entries = self.globals.get(record)
            if entries is not None and len(entries) > _MOST_KEPT:
                self.globals[record] = entries[-_MOST_KEPT:]
        if self.globals.get("painted") and self.page is not None:
            self.globals["painted"] = _compacted(self.globals["painted"], self.page)

    def _enter(self, name: str, given: dict = None):
        """Makes `name` the page shown: its local components start again from
        its .page.toml file, shown and taking touches, and its timers and
        clocked components start. Its components of global scope keep what
        they had, whether they show and take touches included. `given` holds
        the values given to the page the simulation starts on. They take the
        place of its file's, so everything that starts as the page opens
        starts from them."""
        page = self.pages[name]
        kept = {key: value for key, value in self.fields[name].items()
                if _owner(key) in page.global_names}
        self.fields[name] = dict(page.start, **kept)
        self.page = name
        # A page change ends the GPIO pins' bindings (gpio_pins.py).
        self._pins.unbind()
        self.entered += 1
        if given is not None:
            self._commit(given, name)
        # The screen lists each file browser's folder as the page opens, and
        # works out how far each sliding text's lines scroll; each combo box
        # starts with its list as its page file has it; each data record
        # reads its data file, made when it is missing. Their scroll values
        # settle, as the page is drawn.
        self._combos = ComboBoxes()
        for component, kind, _ in page.components:
            if kind == "combo-box":
                self._combos.enter(component, component_attributes(component, self.fields[name]))
            if kind == "data-record":
                self._open_data_record(component, self.fields[name])
            self._lists.opened(name, component, kind, self.fields[name], self.globals)
        # The new page is drawn whole, over anything painted before, its
        # waveforms empty.
        self.globals["painted"] = []
        self._waves = {}
        self._start_timers()
        self._start_clocked()
        # No slide runs until the page is drawn, once its load event ends.
        self._opening = OpeningEffects([], (0, 0), self.clock)
        self._opening_due = None
        self._slid = {}
        self._slides_wait = False
        # Its sliders' knobs are placed by `val` again.
        self._knobs = {}

    def _start_opening(self, values: dict):
        """Starts the slides of the page shown as it is drawn, once its load
        event ends, or at the `ref_star` that shows it when `ref_stop` held
        then (page_changed), by its components' `effect`, `time`, and `first`
        (opening_effects.py), from their `values` as code left them by then,
        on a screen of the page's size, or of the screen's own when the page
        file gives none. A component the load event moved slides to its new
        place. A screen that does not hold `effect` slides nothing in
        (editor_limits.screen_holds): the Editor's simulator drew each
        component in its place at once on a Basic screen. Without a screen
        model, when app.toml names no screen, the slides run."""
        kinds = self._kinds[self.page]
        placed = [(name, component_attributes(name, values))
                  for name in self._ids(self.page)[1:]
                  if name in self.pages[self.page].placed
                  and (self._series is None
                       or screen_holds(kinds[name], "effect", self._series))]
        self._opening = OpeningEffects(
            [(name, own) for name, own in placed if {"x", "y", "w", "h"} <= set(own)],
            (values.get(self.page + ".w", self._touch_area[0]),
             values.get(self.page + ".h", self._touch_area[1])), self.clock)
        self._opening_due = self._opening.next_step(self.clock)
        self._slid = {}

    def _start_clocked(self):
        """Starts each clocked component of the page shown (clocked.py): its
        scrolling texts, its animations, videos, and sounds, and its moves
        (moves.py)."""
        self._clocked = {}
        for component, kind, _ in self.pages[self.page].components:
            if kind == "scrolling-text":
                self._clocked[component] = ScrollingText(component, self._laid_out_size)
            elif kind in _PLAYERS:
                sound = _PLAYERS[kind] == SOUND
                self._clocked[component] = MediaPlayer(
                    component, self._loader(component, _PLAYERS[kind]),
                    self._write_log if sound else None, speed_from_dis=not sound)
        # The page's own moves: those of the page before are dropped.
        self._clocked[MOVES] = Moves()
        for clocked in self._clocked.values():
            clocked.start(self.fields[self.page], self.clock)

    def _catch_up(self, values: dict, clock: int = None):
        """Brings what code may read of the clocked components of the page
        shown up to `clock`, the simulation's by default, in `values`
        (clocked.py, catch_up). While the screen sleeps they stand still, as
        its timers do, so there is nothing to bring."""
        if self.asleep:
            return
        for clocked in self._clocked.values():
            clocked.catch_up(values, self.clock if clock is None else clock)

    def _card_file(self, component: str, path: str) -> bytes:
        """Returns the bytes of the file the player `component` plays from an
        SD card, its `path`, read as the file commands read one
        (card_files.read_card_file): from a card given a folder, or else
        from the card in memory. Or none: a file its card lacks answers 06,
        an invalid file operation, as `bkcmd` asks, and is logged, as the
        Editor's simulator answered for a card's folder lacking it, as such
        a player's page opened and as code set its path. A card in memory
        lacking it, and a path that would leave its card's folder
        (sd_cards.py), are taken to answer alike. An empty path answers
        nothing, as it did not either."""
        if not path:
            return b""
        try:
            data = read_card_file(self.cards, path, self.globals)
        except CardRefusal:
            data = None
        if data is None:
            self._write_log("%s cannot play: its card holds no %s" % (component, path))
            self._return_code(INVALID_FILE_OPERATION, False)
            return b""
        return data

    def _loader(self, component: str, kind: str):
        """Returns the loader of what the player `component` plays, as
        MediaPlayer takes it: the animation, video, or sound (`kind`) its
        `vid` names, or the file its `path` names on an SD card given a
        folder, when its `from` is 1. What cannot be read is logged, and
        plays nothing; a file its card lacks also answers 06 (_card_file)."""
        def load(fields: dict):
            def value(attribute: str, default):
                return fields.get("%s.%s" % (component, attribute), default)
            try:
                if kind != ANIMATION and value("from", 0) == FROM_CARD:
                    data = self._card_file(component, value("path", ""))
                    if not data:
                        return None
                else:
                    names = self.app[LISTS[kind]]
                    # A `vid` of 65535, none, names no resource either. An
                    # animation lacking its `vid` plays the first.
                    media_id = (played_animation(lambda attribute: value(attribute, None))
                                if kind == ANIMATION else value("vid", None))
                    if not isinstance(media_id, int) or not 0 <= media_id < len(names):
                        return None
                    data = (self.source_folder / folders.played_file(kind, names[media_id])
                            ).read_bytes()
                read = {ANIMATION: animation_frames, VIDEO: video_frames,
                        SOUND: sound_frames}[kind]
                return read(data)
            except (NxwrightError, OSError) as error:
                self._write_log("%s cannot play: %s" % (component, error))
                return None
        return load

    def _resume_clocked(self):
        """Lets each clocked component of the page shown count again from now,
        as the screen wakes."""
        for clocked in self._clocked.values():
            clocked.resume(self.fields[self.page], self.clock)

    def _laid_out_size(self, values: dict) -> tuple:
        """The (width, height) of a component's text as its drawing lays it
        out (text_pictures.block_size), from `values`, its attributes by
        their own names: in the folder's font, spaced, and wrapped at the
        width inside its border. (0, 0) when the font cannot be read or lacks
        a character."""
        decoded = self._folder_resources.font(values.get("font", 0))
        try:
            return (0, 0) if decoded is None else block_size(
                values.get("txt", ""), decoded, self.encoding, values, inside_box(values)["w"])
        except NxwrightError:
            return 0, 0

    def _data_file(self, record: str, values: dict, card_values: dict):
        """The data file of the data record `record`, from its attributes in
        `values` (data_files.data_file_for); None when the folder will not
        give it, when `record` opens no file, its `init` being 1
        (card_files.opens_no_file), or when it is shut out of it
        (_is_shut_out). `card_values` hold the card in memory."""
        attributes = component_attributes(record, values)
        if opens_no_file(attributes, card_values, (self.page, record)) or \
                self._is_shut_out(record, values, card_values):
            return None
        path = attributes.get("path", "")
        try:
            return data_file_for(attributes, read_card_file(self.cards, path, card_values))
        except (CardRefusal, OSError):
            return None

    def _open_data_record(self, record: str, values: dict):
        """As its page opens, a data record reads its data file, whose
        `qty`, `txt`, `maxval_y`, and `maxval_x` follow from it
        (card_files.data_record_values). A missing file is made, when
        `mode` is 1. One the folder will not give is left as it is, and the
        table shows no records: `qty` 0, `val` -1, and `txt` empty. What
        cannot be read or made is logged. The record holds the file it opened.
        A file it may not open, as another record holds it, or 8 others are
        open (card_files.opening_refusal), it does not open: it shows a
        message instead of its table, and answers 0x06 twice, as `bkcmd`
        asks."""
        shut, notes = open_data_record(record, values, self.globals, self.cards,
                                       (self.page, record), TextCodec(self.encoding))
        for note in notes:
            self._write_log(note)
        if shut:
            for _ in range(2):
                self._return_code(INVALID_FILE_OPERATION, False)

    def _is_shut_out(self, record: str, values: dict, card_values: dict) -> bool:
        """Whether the data record `record` of the page shown is shut out of
        its file: it could not open it (card_files.opening_refusal), and has
        not opened it since. It opens it by a method, once it may
        (editor_machine), by a new `path`, or as its page opens again."""
        return is_shut_out(self.cards, values.get(record + ".path", ""), card_values,
                           (self.page, record))

    def _show_data_file(self, record: str, values: dict, data_file):
        """Sets the data record `record`'s values in `values` that follow from
        its data file, `data_file`, or None for none
        (card_files.data_record_values)."""
        values.update({"%s.%s" % (record, attribute): value for attribute, value in
                       data_record_values(record, values, data_file,
                                          TextCodec(self.encoding)).items()})

    def _start_timers(self):
        """Starts counting each timer of the page shown that is on."""
        self._due = {}
        for timer in self._of_kind(self.page, "timer"):
            self._schedule(timer, self.fields[self.page])

    def _switch(self, machine: EditorMachine, page: str):
        """Gives `machine`, in the middle of an event, the values and code of
        the page now shown."""
        values = self._view(page)
        machine.text_limits = values.pop("text limits")
        # Recorded, the values note what changes, as the machine's own do.
        machine.values = TrackedValues(values) if machine.recorder is not None else values
        machine.events = self.pages[page].code
        machine.places = self.pages[page].places
        machine.set_page(page, self._ids(page))

    def _ids(self, page: str) -> list:
        """Returns the names of `page`'s objects in ID order, the page's first,
        which code may name by their IDs; None before any page shows."""
        return [name for name, _, _ in self.pages[page].components] if page else None

    def _of_kind(self, page: str, kind: str) -> list:
        """Returns the names of `page`'s components of `kind`, such as
        "timer", in ID order."""
        return [name for name, its_kind in self._kinds[page].items() if its_kind == kind]

    def _schedule(self, timer: str, values: dict):
        """Starts a timer counting from now, or stops it when it is off."""
        if values.get(timer + ".en", 1) == 1:
            self._due[timer] = self.clock + max(values.get(timer + ".tim", 400), 1)
        else:
            self._due.pop(timer, None)

    def _timer_period(self, timer: str) -> int:
        return self.fields[self.page].get(timer + ".tim", 400)

    def _check_sleep(self):
        """Puts an idle screen to sleep after `thsp` seconds without a press,
        or `ussp` seconds without serial data, whichever comes first."""
        if self.asleep:
            return
        sleep_deadlines = [since + seconds * 1000
                           for since, seconds in ((self._last_press, self.globals.get("thsp", 0)),
                                                  (self._last_serial, self.globals.get("ussp", 0)))
                           if seconds > 0]
        if sleep_deadlines and self.clock >= min(sleep_deadlines):
            if self.page is not None:
                # Its players stop where they were as it fell asleep.
                self._catch_up(self.fields[self.page], min(sleep_deadlines))
            self.asleep = True
            self.globals["sleep"] = 1
            self.changes += 1
            self._send_logged(bytes([_ASLEEP_WHEN_IDLE]) + END)

    def _wake(self):
        """Wakes the screen: its timers and clocked components start
        counting again. It is idle from now, as after a press: its `thsp`
        count starts again, as the Editor's simulator showed for a waking by
        code and by the serial line, and so does its `ussp` count, as it
        showed for a touch's waking."""
        self._last_press = self._last_serial = self.clock
        self.asleep = False
        self.globals["sleep"] = 0
        self.changes += 1
        self._start_timers()
        self._resume_clocked()

    def _show_wake_page(self, machine: EditorMachine = None):
        """Shows the page `wup` names as the screen wakes, unless it is 255,
        as a `page` command shows it: in the event `machine` runs, which it
        then ends, or else on its own. The Editor's simulator showed it so,
        the page's load events running, whether a touch or the serial line
        woke the screen. The old page's unload event does not run, as the
        Editor's simulator showed for both wakings. A number naming no page
        leaves the page shown as it is."""
        number = (machine.values if machine is not None else self.globals).get("wup", 255)
        if not isinstance(number, int) or not 0 <= number < len(self.page_names):
            return
        self._waking = True
        try:
            if machine is not None:
                self.page_changed(str(number), machine)
            else:
                self._run(self.page, ["page %d" % number], [None])
        finally:
            self._waking = False

    def _page_named(self, name: str, machine: EditorMachine = None) -> str:
        """Returns the page a `page` command names (_page_by_name)."""
        return _page_by_name(name, self.page_names, machine)


def _page_by_name(name: str, page_names: list, machine: EditorMachine = None) -> str:
    """Returns the page of `page_names`, the pages by number, that a `page`
    command names: by its name, its number, or a value giving its number,
    such as `returnPage.val` or `appid&0x000000FF`, which `machine` works
    out."""
    if name in page_names:
        return name
    number = name
    if not name.isdigit() and machine is not None:
        try:
            number = machine.value_of(name)
        except (KeyError, RefusedCode):
            pass
    if not isinstance(number, int) and not str(number).isdigit():
        raise NxwrightError("the app has no page %s" % name)
    number = int(number)
    if not 0 <= number < len(page_names):
        raise NxwrightError("the app has no page %d" % number)
    return page_names[number]


def _series_has_gpio(series: str) -> bool:
    """Returns whether a screen of `series` has GPIO pins: every series but
    the Basic does, and so does a screen of no known model, None."""
    return series is None or PIN_NAMES[0] not in SERIES_LACKED_VARIABLES[series]


def _owner(key: str) -> str:
    """Returns the component a value of a page belongs to: "t0" for "t0.txt",
    and for "vis t0" and "touch t0", whether it shows and takes touches."""
    if key.startswith(("vis ", "touch ")):
        return key.split(" ", 1)[1]
    return key.split(".", 1)[0]


def _read_page(runner: SourceFolderRunner, tables: FolderPageTables, name: str,
               number: int) -> _Page:
    """Returns what the simulation needs of one page: its compiled code, and
    its components' start values from its .page.toml file, as `tables`, the
    folder's FolderPageTables, holds it."""
    compiled = runner.runnable_page(name, None, False)
    components = compiled.components
    # The generated components, such as a longer-lived text, start empty.
    generated = {key: value for key, value in compiled.start.items()
                 if "." in key and GENERATED_NAME.fullmatch(key.split(".", 1)[0])}
    return _page_of(name, number, components, screen_model(tables.app), generated, compiled,
                    SYSTEM_PAGES.get(tables.system_pages[name]))


def _stand_in_caller(tables: FolderPageTables, starting: "_StartingApp") -> dict:
    """Gives the page `starting` starts on a stand-in caller when it is a
    keyboard page that has none: its `loadpageid` and `loadcmpid` are of
    global scope, and the start values give neither. The stand-in is a page
    of the simulation alone, numbered after the app's last page, holding
    one text component of global scope, which the keyboard edits, then goes
    back to. It is added to the pages of `starting`. Returns the start
    values naming that text as the caller, or None."""
    keyboard, values = starting.page, starting.values
    page = starting.pages[keyboard]
    if page.system_page is None or not {"loadpageid", "loadcmpid"} <= page.global_names \
            or set(values or {}) & {"loadpageid.val", "loadcmpid.val"}:
        return None
    name = next(name for name in ("keyboardCaller%s" % (count or "")
                                  for count in itertools.count())
                if name not in starting.pages)
    number = len(starting.page_names)
    # The keyboard's own field: its text of the largest txt_maxl. The
    # stand-in holds whatever it can, as a keyboard cuts what it writes
    # back at its caller's txt_maxl, and takes its font, which whoever
    # made the keyboard sized for the screen.
    fields = {key[:-len(".txt")]: limit for key, limit in tables.text_limits[keyboard].items()
              if key.endswith(".txt")}
    field = max(fields, key=fields.get, default=None)
    font = page.start.get(field + ".font", 0) if field is not None else 0
    starting.pages[name] = _stand_in_page(
        tables, _StandIn(name, number, keyboard, page.system_page,
                         (page.start[keyboard + ".w"], page.start[keyboard + ".h"]),
                         fields.get(field), font,
                         starting.folder_resources.font_height(font)),
        starting.encoding)
    starting.page_names.append(name)
    # Its text is component 1, after the page itself.
    return {"loadpageid.val": number, "loadcmpid.val": 1}


@dataclass
class _StartingApp:
    """What a start takes from the source folder, read and compiled before
    the simulation changes (Simulation._read_start)."""
    app: dict
    folder_resources: FolderResources
    touch_area: tuple        # the screen's (width, height), as it is turned
    series: str              # the screen's series, None for no known model
    pages: dict              # {name: _Page}, a keyboard's stand-in caller among them
    page_names: list         # the pages by number
    program_start: dict      # the start values of program.nx and the pages' code
    encoding: str
    macros: dict
    values: dict             # the start values given, for the start page's own
    page: str = None         # the start page, or None to run program.nx
    program: tuple = None    # program.nx's (lines, places), when it runs
    stand_in: bool = False   # whether the start page has a stand-in caller


@dataclass
class _StandIn:
    """What a keyboard's stand-in caller page is made from
    (_stand_in_caller)."""
    name: str            # the page's, one the app's pages do not have
    number: int          # the page's, after the app's last
    keyboard: str        # the keyboard page it calls
    kind: int            # the keyboard's kind, the `key` a field opens it by (SYSTEM_PAGES)
    size: tuple          # the page's (width, height): the keyboard page's
    txt_maxl: int        # the stand-in text's, or None for a new text's
    font: int            # the font of its texts and button
    font_height: int     # that font's height, or 0 when it cannot be read


# The stand-in page's words.
_STAND_IN_TITLE = "Simulated keyboard page caller"
_RETURNED = "The keyboard returned:"
_RETURNED_EMPTY = "The keyboard returned an empty text."
_OPEN_AGAIN = "Open the keyboard again"
# A light grey, in the screen's 16-bit colours, behind the text the keyboard returned.
_STAND_IN_TEXT_COLOUR = 50712


def _stand_in_page(tables: FolderPageTables, stand_in: _StandIn, encoding: str) -> _Page:
    """Returns the page, of the simulation alone, that stands in for a
    keyboard's caller. From the top: a title; a label saying what the
    keyboard returned; t0, the text it returned, component 1, of global
    scope, which the keyboard edits; and at the bottom, a button opening the
    keyboard again. Each is as the Nextion Editor adds it, but for its place,
    its words, and its font. The page's load event sets the label, and hides
    t0 when it is empty."""
    width, height = stand_in.size
    font_height = stand_in.font_height or int.from_bytes(
        dict(tables.defaults[TYPES_BY_NAME["text"]].attributes)["h"], "little")
    margin = max(4, font_height // 2)
    row = font_height + margin

    def placed(name: str, kind: str, top: int, **values) -> dict:
        return {"name": name, "type": kind, "x": margin, "y": top, "w": width - 2 * margin,
                "h": row, "font": stand_in.font, **values}

    def worded(name: str, kind: str, top: int, words: str, **values) -> dict:
        return placed(name, kind, top, txt=words, txt_maxl=len(words), **values)

    # The text the keyboard returned stays component 1, the caller it writes back to.
    returned = placed("t0", "text", margin + 2 * (row + margin), vscope=1, key=stand_in.kind,
                      txt="", xcen=0, bco=_STAND_IN_TEXT_COLOUR)
    if stand_in.txt_maxl is not None:
        returned["txt_maxl"] = stand_in.txt_maxl
    tables_of_page = [
        {"name": stand_in.name, "type": "page", "x": 0, "y": 0, "w": width, "h": height},
        returned,
        worded("title", "text", margin, _STAND_IN_TITLE),
        worded("label", "text", margin + row + margin, _RETURNED_EMPTY, xcen=0),
        worded("again", "button", height - margin - row, _OPEN_AGAIN),
    ]
    page_toml = folders.PageToml(tables.app, ResourceNames.of_app(tables.app), tables.defaults,
                                 encoding, tomli_w.dumps({"page": tables_of_page[0],
                                                          "component": tables_of_page[1:]}))
    components = folders.page_toml_components(page_toml, stand_in.name)
    # Editor code, which needs no compiling. The label says what came back,
    # and t0 shows only when it holds something; vis is set both ways, as a
    # component of global scope keeps it from one visit to the next.
    code = {
        (stand_in.name, "load"): [
            'if(t0.txt=="")', "{", 'label.txt="%s"' % _RETURNED_EMPTY, "vis t0,0",
            "}else", "{", 'label.txt="%s"' % _RETURNED, "vis t0,1", "}"],
        # The lines a tap on a field bound to the keyboard runs
        # (Simulation._keyboard_lines), which work while t0 is hidden too.
        ("again", "up"): [
            "%s.loadpageid.val=%d" % (stand_in.keyboard, stand_in.number),
            "%s.loadcmpid.val=1" % stand_in.keyboard,
            "page %s" % stand_in.keyboard],
    }
    stand_in_code = _StandInCode(code, {key: [None] * len(lines) for key, lines in code.items()},
                                 {"text limits": table_limits(tables_of_page, tables.defaults)},
                                 {})
    return _page_of(stand_in.name, stand_in.number, components, screen_model(tables.app), {},
                    stand_in_code, None)


@dataclass
class _StandInCode:
    """What _page_of takes of a page's compiled code, for the stand-in
    page, whose code is given as Editor code."""
    code: dict
    places: dict
    start: dict
    local_names: dict


def _page_of(name: str, number: int, components: list, screen, generated: dict, compiled,
             system_page: int) -> _Page:
    """Returns what the simulation needs of one page, from its Components,
    the start values of its `generated` components, and `compiled`, its
    compiled code: its code and places, its start's text limits, and its
    local names."""
    start = component_start_values(components, screen)
    shown = [(component.name, component.type,
              all(key in component.values for key in ("x", "y", "w", "h")))
             for component in components]
    start.update(generated)
    owned = {component.name for component in components} | \
        {key.split(".", 1)[0] for key in generated}
    global_names = {component.name for component in components[1:]
                    if component.values.get("vscope") == 1}
    return _Page(name, number, compiled.code, compiled.places, start,
                 compiled.start.get("text limits", {}), shown, global_names, owned,
                 {component for component, _, has_place in shown if has_place},
                 compiled.local_names, system_page)


def _program_code(source_folder: Path, read, app: dict) -> tuple:
    """Returns program.nx's code as the build compiles it, with its `int`
    declarations left out, and the place of each line."""
    text = read("program.nx")
    lines = folders.numbered_lines(text)
    if app["language"] == folders.NXLANG:
        lines = compile_program(lines, folders.program_names(text, read))
    placed = preprocess_with_places(lines, ResourceNames.of_app(app))
    kept = [(number, line) for number, line in placed if not line.startswith("int ")]
    return ([line for _, line in kept],
            [Place("program.nx", number, "program") if number else None for number, _ in kept])


class _EventEnded(Exception):
    """Raised to end the event running, and the events whose clicks or calls
    led to it: once a `page` command's new page has started, or once code
    has put the screen to sleep."""


# How many of its last entries each record keeps in a simulation, and the records.
_MOST_KEPT = 200
_TRIMMED = tuple(LOGGED) + ("waveform",)
# How many entries of what was painted a page keeps, at most: the oldest
# painting of a page drawn on more often, without a `cls`, is forgotten.
_MOST_PAINTED = 5000
# The entries of "painted" that draw a component again, rather than paint:
# ("left", component, box) marks the box a component code moved or resized
# left, which the drawing gives the page's background back.
_DRAWING_AGAIN = ("redraw", "left", "ref", "ref_stop", "ref_star")
# A component's place on the page.
_PLACE_KEYS = ("x", "y", "w", "h")


def _compacted(painted: list, page: str) -> list:
    """Returns what was painted on `page`, without what no longer shows:
    what a `cls`, or the page drawn again whole, painted over; a
    component's marks to be drawn again since the last painting command,
    but for its last; and a box a component left marked twice since then,
    but once."""
    page_names = (page, "0")
    # Between ref_stop and ref_star, a mark to draw again waits: it neither
    # covers what came before nor merges with another.
    stopped = _stopped_before(painted)
    for index in range(len(painted) - 1, -1, -1):
        command = painted[index]
        page_drawn = command[0] == "ref" or (command[0] == "redraw" and not stopped[index])
        if command[0] == "cls" or (page_drawn and command[1] in page_names):
            start = index if command[0] == "cls" else index + 1
            # A stop still on at the cut is kept, with the marks waiting on it.
            kept = []
            if stopped[start]:
                begun = max(at for at in range(start) if painted[at][0] == "ref_stop")
                waiting = [entry for entry in painted[begun:start]
                           if entry[0] in ("redraw", "left")]
                kept = [("ref_stop",)] + list(dict.fromkeys(waiting))
            painted = kept + painted[start:]
            stopped = [False] + [True] * (len(kept) - 1) + stopped[start:] if kept \
                else stopped[start:]
            break
    last_paint = max((index for index, command in enumerate(painted)
                      if command[0] not in _DRAWING_AGAIN), default=-1)
    tail, seen = [], set()
    for index in range(len(painted) - 1, last_paint, -1):
        command = painted[index]
        if command[0] == "redraw" and not stopped[index]:
            if command[1] in seen:
                continue
            seen.add(command[1])
        elif command[0] == "left":
            # One box left twice gets the background back once.
            if command in seen:
                continue
            seen.add(command)
        tail.append(command)
    return _within_bound(painted[:last_paint + 1] + tail[::-1])


def _within_bound(painted: list) -> list:
    """Returns `painted`, a compacted record, kept to _MOST_PAINTED entries.
    Past that, its oldest boxes left ("left") go first: the start of a long
    move's or slide's trail shows the paint again, but the paint stays. A
    ("redraw", ...) mark is kept: after the last painting there is one for
    each component, which may be all that draws it over the paint. Then, if
    need be, the oldest entries go."""
    excess = len(painted) - _MOST_PAINTED
    if excess <= 0:
        return painted
    kept = []
    for entry in painted:
        if excess > 0 and entry[0] == "left":
            excess -= 1
        else:
            kept.append(entry)
    return kept[-_MOST_PAINTED:]


def _stopped_before(painted: list) -> list:
    """Returns, for each entry of `painted` and for its end, whether drawing
    again was stopped (between ref_stop and ref_star) when it came."""
    stopped, flags = False, []
    for command in painted:
        flags.append(stopped)
        if command[0] in ("ref_stop", "ref_star"):
            stopped = command[0] == "ref_stop"
    return flags + [stopped]


# A name of the screen's arrays: a page by its index, then a component by
# its ID or its name, or a component of the page shown by its ID.
_BY_INDEX = re.compile(r"(?:p\[(\d+)\]\.)?(?:b\[(\d+)\]|([A-Za-z_]\w*))\.(\w+)")
# The component types whose content follows a press until its release: the
# lists of a file browser, a select, and a combo box, and a sliding text's
# lines. And the attributes whose setting by the code sets them going
# (_worked).
_FOLLOWING = ("file-browser", "select", "sliding-text", "combo-box", "data-record")
# The lists whose `left` gives them a scroll bar's thumb.
_WITH_SCROLL_BAR = ("file-browser", "sliding-text", "data-record")
# The types a touch never drags, whatever their `drag` (assumed): those
# that follow a press themselves, a slider and _FOLLOWING's, and a page and
# a hotspot, whose `drag` the Editor's panel never shows.
_UNDRAGGED = ("slider", "page", "hotspot") + _FOLLOWING
# What code sets of a combo box that moves its open list (_worked).
_LIST_MOVED = ("val", "down", "path", "qty")


# The parts of the real-time clock's time the code may set, by variable.
_TIME_PARTS = {"rtc0": "year", "rtc1": "month", "rtc2": "day", "rtc3": "hour",
               "rtc4": "minute", "rtc5": "second"}


def _clock_values(time: datetime) -> dict:
    """Returns rtc0 to rtc6 for a time: rtc6 is the day of the week, from 0
    for Sunday."""
    values = {name: getattr(time, part) for name, part in _TIME_PARTS.items()}
    values["rtc6"] = (time.weekday() + 1) % 7
    return values
