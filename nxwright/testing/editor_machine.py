"""Running Editor code on a PC, as the screen would, for testing a screen's code.

EditorMachine interprets this part of the Editor's language: assignments, if,
while, for, return, goto and labels, click, call, page, vis, prints and
printh, the SD card's commands, file streams, a data record's methods, a
waveform's add and cle, the CRC commands crcrest, crcputs, crcputh, and
crcputu (modbus_crc.py), and the text commands covx (and its older form cov),
substr, spstr, strlen, and btlen. Values live in a dictionary, keyed by name
as the code writes them ("t0.txt", "n0.val", "sys0"). Commands that reach
outside the page, such as page and prints, are recorded in it under names of
their own, listed in EditorMachine's documentation.

It runs an event as the screen does, as lines with jumps (_flattened): an if,
a while, or a for tests and jumps, and a goto jumps to a label anywhere in
its event, into a block too, as the Editor's simulator showed. A return ends
its event, and only its own: a clicked event's ends that event alone, and a
macro's, which `call` runs, the macro alone. An event, a clicked event, and a
called macro each nest one level within what runs them, and the tenth level
stops the run, as it stopped the Editor's simulator (MOST_LEVELS).

It refuses what the Editor refuses, so code that runs here is code the Editor
accepts: parentheses in arithmetic, arithmetic in a condition, a condition
mixing && and ||, joining a number to text, and a goto whose label its event
lacks, or a label twice in one event. Refused code, and code nxwright does
not model, stop the run with RefusedCode. A line it cannot read stops it
with UnreadableLine.
"""
from collections import ChainMap
import functools
import itertools
import re

from nxwright import NxwrightError
from nxwright.drawing.text_pictures import path_lines
from nxwright.language.code_checks import (COMMAND_PARAMETERS, DATA_RECORD_ARGUMENTS,
                                           INVALID_COMMAND, INVALID_VARIABLES, LACKED_INSTRUCTION,
                                           LACKED_VARIABLE, PICTURE_ARGUMENTS, SCREEN_ESCAPES,
                                           XSTR_FONT_ARGUMENT, first_word_refusal, series_lacks)
from nxwright.language.code_lines import (ASSIGNMENT, LABEL, NUMBER, OPERAND, chain_parts,
                                          command_arguments, first_word, goto_label,
                                          holds_own_attribute, split_line)
from nxwright.language.resource_names import ANIMATION, FONT, NOUNS, PICTURE, SOUND, VIDEO
from nxwright.project.attribute_descriptions import code_cannot_change, describe, type_has
from nxwright.project.device_settings import DEFAULT_ENCODING, TextCodec
from nxwright.project.editor_language import (EDITOR_COLOURS, GPIO_VARIABLES, NO_COMMAND_WHEN_ALONE,
                                              NO_NUMERIC_FORM)
from nxwright.project.editor_limits import code_cannot_change_on_series, screen_holds
from nxwright.project.object_types import TYPE_NAMES, TYPES_BY_NAME
from nxwright.project.screen_arithmetic import divide_toward_zero, int32
from nxwright.project.stamp import CRC_START, word_crc
from nxwright.project.zi_font import counted_characters
from nxwright.source.page_source import reference_kind
from nxwright.testing.card_files import (DATA_FILES_HELD, DATA_RECORDS_GIVEN_A_PATH,
                                         DATA_RECORDS_SHUT_OUT, component_attributes,
                                         data_record_values, given_a_path, hold_file,
                                         is_shut_out, let_go_of_files, let_in,
                                         open_data_record, opening_refusal, opens_no_file,
                                         read_card_file, shut_out, write_card_file)
from nxwright.testing.data_files import data_file_for
from nxwright.testing.gpio_pins import PIN_NAMES
from nxwright.testing.list_working import (COMBO_BOX_CHOICES, FILE_BROWSER_LISTINGS, UNSETTLED,
                                           ListWorking)
from nxwright.testing.modbus_crc import CRC_OFF, crc_after, crc_start
from nxwright.testing.pinyin_table import pinyin_table_of
from nxwright.testing.recording import TrackedValues
from nxwright.testing.sd_cards import INVALID_FILE_OPERATION, CardRefusal
from nxwright.testing.serial_buffer import (BUFFER_BYTE, buffer_read, copied_into_number,
                                            copied_into_text, deleted)
from nxwright.testing.serial_line import ADDRESSES
from nxwright.testing.simulation_log import value_bytes

# The EEPROM's size in bytes, on the models that have one.
EEPROM_SIZE = 1024
# The return code the screen gives `newfile` of a size that is no number,
# and `covx` to hex of an odd length: an invalid variable operation, as the
# Editor's simulator answered.
_INVALID_VARIABLE_OPERATION = 0x1B
# The other return codes of a refused line, as the Editor's simulator
# answered them (the vendor's instruction set, section 7).
_INVALID_PICTURE, _INVALID_FONT, _INVALID_WAVEFORM = 0x04, 0x05, 0x12
_FAILED_ASSIGNMENT, _FAILED_EEPROM_ACCESS = 0x1C, 0x1D
# An invalid variable: a name, or an attribute of a component, the screen
# does not have.
_INVALID_VARIABLE = 0x1A
_INVALID_PARAMETER_COUNT, _INVALID_ESCAPE = 0x1E, 0x20
# The kinds of value a `txt` and a `val` take, of any component: the Editor's
# compile refused another kind, and its simulator answered a typed one 0x1C.
# It answered event code giving a text a number 0x1C too, changing nothing:
# the 0 read from an attribute the screen does not hold (_unheld). A `val`
# given a text in event code is taken to be refused alike. Other attributes'
# kinds are not checked.
_ATTRIBUTE_KINDS = {"txt": str, "val": int}
# The resources whose number a store must name in the project, else the
# screen refuses it (_check_resource).
_CHECKED_RESOURCES = (PICTURE, FONT, ANIMATION, VIDEO, SOUND)
# `cle`'s channel standing for every channel.
_EVERY_CHANNEL = 255
# The most bytes `addt` takes at once, as the Nextion Editor's simulator took.
_MOST_ADDT_BYTES = 1024
# The system variables that save a power-on default, each with the current
# value it sets too, as the vendor's instruction set says: dims=32 sets the
# backlight to 32% at once, as dim=32 does, and bauds sets baud. The
# Editor's simulator set dim so, and kept dims into its next start. It keeps
# baud at 9600 whatever code sets, so it cannot show what bauds does: that
# rests on the vendor's instruction set alone. The machine keeps no power-on
# default from one run to the next.
_CURRENT_OF_SAVED = {"dims": "dim", "bauds": "baud"}

# The screen's two pinyin commands, which the machine runs from a pinyin
# table (_pinyin), and only records without one.
PINYIN_COMMANDS = ("pa_q", "pa_txt")
# The commands of the instruction set the machine only records, under
# "other commands": they act on hardware or data the machine does not model.
RECORDED_ONLY = {"touch_j", "com_stop", "com_star", "code_c", "play", "beep", "setlayer",
                 # Undocumented.
                 "lcd_dev", "getpassw", "lcd_refx", "lhmi_cle", "showqq", "getv", "init",
                 "setbaudz", "pa_q", "whmi_cle", "fstr", "nstr", "rfpt", "strsize", "wfpt",
                 "pa_txt", "timerset", "zstr", "comok", "draw3d", "qrcode", "draw_h", "setbrush",
                 "sets", "i", "cfguart", "cuts", "gets", "meup", "xnum", "beepset", "piccolor"}
# What a typed instruction using a command or a system variable the screen's
# series lacks answers, by the kind of word (series_lacks), as the Editor's
# simulator answered: an invalid instruction, or an invalid variable.
_LACKED_ANSWERS = {LACKED_INSTRUCTION: 0x00, LACKED_VARIABLE: 0x1A}
# What a typed instruction whose first word is no command answers, by the
# words the Editor's compile refuses it with (first_word_refusal), as the
# Editor's simulator answered `zork 1`, and `CLS 1` and `movelayer 1`.
_NO_COMMAND_ANSWERS = {INVALID_COMMAND: 0x00, INVALID_VARIABLES: 0x1A}

# The start of the values holding each file stream's open file, such as
# "open file fs0". An app may have several streams, named as it likes.
OPEN_FILE = "open file "
# The names under which the machine records what reaches outside the page
# (EditorMachine), and the starts of those it keeps per component or file
# stream: "vis <name>", "touch <name>", and OPEN_FILE.
RECORDS = frozenset({"page opened", "sent", "replies", "eeprom", "eeprom accesses", "gpio",
                     "rand range", "reset", "other commands", "painted", "waveform",
                     "existing", "file contents", "file errors", "file commands",
                     "serial buffer", "component errors", "refusals", DATA_FILES_HELD,
                     DATA_RECORDS_SHUT_OUT, DATA_RECORDS_GIVEN_A_PATH, FILE_BROWSER_LISTINGS,
                     COMBO_BOX_CHOICES, UNSETTLED})
# A data record's attributes whose setting by code works out its table's values.
_TABLE_ATTRIBUTES = ("format", "hig", "gdw", "gdh")
RECORD_STARTS = ("vis ", "touch ", OPEN_FILE)

_COMPARISON = re.compile(r"^(%s)(==|!=|<=|>=|<|>)(%s)$" % (OPERAND, OPERAND))
# A name alone, not dotted nor indexed: a component's or a variable's.
_PLAIN_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# A text subtraction written out, t0.txt=t0.txt-3: the text, then the count.
_TEXT_SUBTRACTION = re.compile(r"^(%s)-(.+)$" % OPERAND)
# A loop still running after this many turns, or a goto that jumped back as
# many times in one run of its event, is taken to never end.
_MOST_TURNS = 10000
# How deep events, clicked events, and called macros nest, counted together.
# One more stopped the Editor's simulator: "Endless loop was detected, please
# check your code!" (probed with the Editor 1.68.2). An instruction from the
# serial line is no level of its own.
MOST_LEVELS = 9


class UnknownComponentId(Exception):
    """Raised for an instruction from the serial line naming a component by
    an ID that no object of the page has, which the screen answers with
    0x02, an invalid component ID."""


class ScreenRefusal(Exception):
    """Raised for a line the running screen refuses, which it answers with
    `code`: a picture, a font, a waveform, or an EEPROM address the line
    meets as it runs. The line changes nothing, and what runs it goes on
    (EditorMachine._run_simple)."""

    def __init__(self, code: int, reason: str):
        super().__init__(reason)
        self.code = code


class RefusedCode(NxwrightError):
    """Raised for code that stops a run. It is code the Nextion Editor
    refuses, such as a goto whose label its event lacks, or code nxwright
    does not model, such as a covx form other than 0, 1, and 2. It is no
    AssertionError, so a test that meets it stops with an error, not as a
    failed check, and `python -O` keeps the check."""


class UnreadableLine(RefusedCode):
    """Raised for a line the runner cannot read (_unreadable_line). After a
    build, that is a line the build took, so a gap in nxwright. In code
    given to the runner directly, it may be a typo, such as `sys0 = = 2`."""


class ValueNotGiven(NxwrightError, KeyError):
    """Raised as code reads a name that has no value: in a test, one the run
    was not given. Its message starts with the line that read it, as a
    refusal's does (_located).

    It is a KeyError too, so that callers that catch one still do. A line
    typed on the serial line that reads a name without a value answers
    0x1A, an invalid variable (simulation.py)."""

    def __init__(self, name: str):
        super().__init__("%s has no value. In a test, give it in the run's values" % name)
        self.name = name

    # A KeyError's own would quote the message.
    __str__ = BaseException.__str__


def _located(error: NxwrightError, place):
    """Gives `error` the place of the line it stopped at, `place`. Its file
    and line become the place's. Its message then starts with them and the
    line's event or function, while its `reason` stays the message without
    them, as for any NxwrightError. An error that has a place already keeps
    it: one raised in a clicked event has that event's line. The error is
    changed, not copied, so that it keeps its kind and what that holds, as
    a CompileRefusal's code."""
    if error.file is None:
        error.file, error.line = place.file, place.line
        error.args = ("%s line %d (%s): %s" % (place.file, place.line, place.owner, error),)


def _placed(error: NxwrightError, place) -> NxwrightError:
    """Returns `error`, given `place` by _located when there is one."""
    if place is not None:
        _located(error, place)
    return error


def _unreadable_line(reason: str) -> UnreadableLine:
    """Returns the UnreadableLine whose message says the line cannot run,
    then `reason`, which shows the line or the part that does not read."""
    return UnreadableLine("nxwright cannot run this line: " + reason)


class CompileRefusal(RefusedCode):
    """Raised for a line the Editor's compile refuses, with the code the
    screen answers when the serial line brings it, `code`. In event code it
    stops the run, as the other code the Editor would not compile does."""

    def __init__(self, code: int, reason: str):
        super().__init__(reason)
        self.code = code


def c_operation(operator: str, left, right):
    """Returns `left operator right` as the screen computes it: on 32-bit numbers,
    with / and % rounding toward zero as in C. On text, only `+` of two texts is
    accepted; anything else is refused, as the Editor refuses it ("Invalid
    variable operation")."""
    if isinstance(left, str) or isinstance(right, str):
        if operator != "+" or not (isinstance(left, str) and isinstance(right, str)):
            raise CompileRefusal(_INVALID_VARIABLE_OPERATION, "the Nextion Editor refuses %r %s %r"
                                 % (left, operator, right))
        return left + right
    if operator in "/%" and right == 0:
        raise ZeroDivisionError
    if operator == "/":
        return int32(divide_toward_zero(left, right))
    if operator == "%":
        return int32(left - c_operation("/", left, right) * right)
    return int32({"+": lambda: left + right, "-": lambda: left - right,
                  "*": lambda: left * right, "&": lambda: left & right,
                  "|": lambda: left | right, "^": lambda: left ^ right,
                  "<<": lambda: left << right, ">>": lambda: left >> right}[operator]())


def own_page_prefix(page: str):
    """The pattern of `page`'s name and a dot before the name of one of its
    components, as `page0.` in `page0.t0.txt`: on its own page, code may name
    a component so, and page.component.attribute is component.attribute. The
    page's own attribute, `page0.x`, is no component's, and keeps its name."""
    return re.compile(r"^%s\.(?=[A-Za-z_][A-Za-z0-9_]*\.)" % page)


class EditorMachine:
    """Runs Editor code as the screen does (checked against the Editor's
    simulator). `values` holds every value the code reads, by name; running
    changes them in place and adds the ones the code sets.

    `events` maps (component, "down" or "up") to the Editor code of that
    component's Touch Press or Touch Release event, which a `click` runs.
    `macros` maps the name of each of the project's macros to (its Editor
    code lines, a place or None per line), which a `call` runs. A `call` of
    one it lacks does nothing, as the Editor's simulator ignored one typed on
    the serial line. `page`, the name of the page the code belongs to, lets
    the code name its own components as `page.component.attribute`.
    `components`, the names of the page's objects in ID order, the page's
    first, let `click`, `vis`, `tsw`, and `ref` name one by its ID, a number
    written or held in a variable or a value, as a macro must (_component).
    `encoding`, the project's character encoding, gives a text's bytes,
    which btlen counts. `resources`, the project's ResourceNames, lets the
    machine refuse a picture or a font the project lacks, as the screen
    does; without it, any ID is taken.

    A line the running screen refuses changes nothing, and the run goes on:
    a picture or font attribute given an ID the project lacks; a drawing
    command naming such a picture, or xstr such a font, though xstr paints
    its background first; `add` or `cle` naming no waveform of the page, or
    a channel past its count; an EEPROM address past its end; a `txt` given
    a number, or a `val` a text, in event code. Each is recorded under
    "refusals", and the screen answers its code (_refused). Of the lines
    the Editor's compile refuses, a typed instruction alone meets some
    (CompileRefusal, run_instruction): a `txt` given a number or a `val` a
    text, a command given another number of parameters than it takes
    (COMMAND_PARAMETERS), and, given `series`, the letter of the screen's
    series, a command or a system variable that series lacks
    (code_checks.series_lacks). Event code runs the last two as it
    always did.

    What reaches outside the page is recorded in `values`, under names no
    component can have:
      - "page opened": the page a `page` command opened.
      - "vis <name>": whether a `vis` command showed (1) or hid (0) <name>,
        the component's name even where the code gave its ID.
      - "touch <name>": whether a `tsw` command turned <name>'s touch on (1)
        or off (0); <name> is the component's, even given by its ID, 255
        standing for every component.
      - "sent" also holds what `print` sent, as `prints` with a length of 0
        would record it, (value, 0).
      - "replies": what the screen sent in answer: `get`, as ("get",
        value); `sendme`, as ("sendme", page number); and `rept`, as
        ("rept", the EEPROM's bytes).
      - "eeprom": the EEPROM's EEPROM_SIZE bytes, given by the caller or
        all zero; "eeprom accesses": each `wepo` and `repo`, in order, as
        ("wepo", address, bytes written) and ("repo", address, value read).
      - "gpio": `cfgpio`, as ("cfgpio", pin, mode, component), and each
        write and read of the GPIO variables (GPIO_VARIABLES), as ("write",
        name, value) and ("read", name, value).
      - "rand range": what `randset` set. Reading `rand` gives "rand" as
        the caller set it; in a simulation, a random number in that range.
      - "reset": 1 once `rest` ran.
      - "other commands": the commands of RECORDED_ONLY, and `move`, as
        they ran; `pa_q` and `pa_txt` among them only without a pinyin table,
        and `addt`, `wept`, and `twfile` only without a screen
        (_transparent_data, _twfile).
      - "painted": what the drawing commands painted, in order, each as its
        command and its computed arguments: ("fill", x, y, w, h, colour),
        ("xstr", x, y, w, h, font, pco, bco, xcen, ycen, sta, text), and so
        for cls, pic, picq, xpic, line, draw, cir, and cirs; ("ref", name) and
        ("ref_stop",) and ("ref_star",) as written.
      - "sent": what `prints`, `printh`, and `rdfile` sent, as a list.
      - "waveform": the points `add` put on a waveform and the channels `cle`
        cleared, in order, as ("add", id, channel, value) and ("cle", id, channel).
      - "existing": given by the caller, the paths `findfile` and `finddir` find
        besides the files of "file contents".
      - "text limits": given by the caller, {name: the most bytes it keeps} of
        the bounded texts, a `txt` by its `txt_maxl`, a `path` by its
        `path_m`, and so on (editor_limits.bounded_attributes): a text stored
        in one keeps at most that many bytes, as on the screen.
        It is taken out of `values` when the machine starts, since the code
        neither reads nor changes it.
      - "file contents": {path: bytes} of the files the file streams read and
        write, `newfile` and `delfile` change, and data records keep their
        records in (data_files.py); given by the caller or empty.
        A file holds its bytes as the SD card does: `newfile` makes one of the
        size it is given, all zero bytes.
      - "serial buffer": the bytes of the buffer of protocol reparse mode,
        which `u[]`, `usize`, `ucopy`, and `udelete` read and change
        (serial_buffer.py); given by the caller, with `recmod` 1, or empty.
      - "file errors": the commands the screen refused, as (command, path),
        in order: a read or write that would go past the end of the file, or
        of a file stream with no file open, its path None; a `newfile` whose
        size is not a number, or is below 0; a `twfile` refused before its
        transfer (_twfile), or whose file a simulation could not write after
        it (Simulation._write_transferred_file); a data record's method that
        could not be done (_data_record); and, as ("open", path), a data
        record's `path` set to a file another holds (_open_named_file). The
        Editor's simulator answered the first nothing, changing nothing, the
        `newfile` 0x1B, or 0x06 for a size below 0, making no file, and the
        `path` 0x06.
      - "file commands": the commands that changed files, a data record's
        methods among them, and a file browser's `up()`, in order.
      - "data files held": the files the data records hold
        (card_files.DATA_FILES_HELD), made as one first opens a file; "data
        records shut out": those that could not open theirs
        (card_files.DATA_RECORDS_SHUT_OUT); "data records given a path":
        those whose `path` code set (card_files.DATA_RECORDS_GIVEN_A_PATH).
      - "file browser listings" and "combo box choices": what each file
        browser lists, and each combo box's last `val` within its items
        (list_working.py), made as they are first worked.
      - "open file <name>": the path the file stream `<name>` has open.
      - "component errors": each `click`, `vis`, `tsw`, or `ref` in an
        event naming a component by an ID no object of the page has, as
        (command, its first argument as written). The Editor's simulator
        answered 0x02 and went on with the event.
      - "refusals": each other line the running screen refused, in order,
        as (its return code, the line as written).

    For the debugger, `recorder`, a Recorder (recording.py), is told of each
    statement before it runs, with its place, and of each event the machine
    enters and leaves. The places of the lines of `events` are in `places`,
    {(component, event): a place or None per line}, and those of the lines
    `run` gets, in its `places`. With or without a recorder, code that stops
    the run raises its error with its line's place (_located).

    For the simulator, `screen` (testing/simulation.py) is told of what a
    test has no use for: `screen.page_changed(name, machine)` at a `page`
    command, once it is recorded; `screen.stored(name, value, machine,
    before)` after each value the code stores, such as `delay` or `sleep`,
    `before` being what the name held, or None; and
    `screen.recorded(record, entry, machine)` after each entry added to a
    record of what reached outside the screen, such as "sent", or to
    "waveform"; `screen.released(component, machine)` after a `click`'s
    Touch Release event; `screen.drawing_stopped(stopped, machine)` at a
    `ref_stop` (True) and a `ref_star` (False); `screen.answer_typed_now()`
    before the event a typed `click` runs, which the screen answers first;
    `screen.refused(code, typed)` for a line it refuses (_refused); and
    `screen.by_index(name, machine)`, for a name of the screen's arrays, `p[1].b[5].txt`,
    `p[1].t0.txt`, or `b[5].txt`, which returns the name it stands for, or
    None to keep it as it is. A page change in the middle of an event gives
    the machine the new page's values and code, for the new page's events
    it runs. `cards`, a
    FolderCards (sd_cards.py), holds the SD cards a simulation gave
    folders: the file commands on their paths act on the folders' files,
    and what they refuse is recorded with the file errors.

    `pinyin_table`, a PinyinTable or the path of one (pinyin_table.py),
    is the screen's pinyin table, which `pa_q` and `pa_txt` read (_pinyin).
    Without it they are recorded with the other commands, changing nothing.

    Given `folder_resources`, the source folder's fonts and pictures
    (folder_resources.py), the machine works the page's list components as
    code sets their attributes, after `screen.stored` (list_working.py), and
    a data record's table (_work). Without them, what code sets stays as
    set. `page_values`, the page's components' values as its page file
    gives them, lie beneath `values` for a test, which gives only some: the
    machine reads them for a component's type (_type_of), for the working,
    and for a data record's methods and file, but code reading a field
    `values` lacks still stops the run.
    """

    def __init__(self, values: dict, events: dict = None, page: str = None,
                 encoding: str = DEFAULT_ENCODING, recorder=None, places: dict = None,
                 screen=None, cards=None, macros: dict = None, components: list = None,
                 resources=None, series: str = None, pinyin_table=None,
                 folder_resources=None, page_values: dict = None):
        # Recorded, the values note what changes, for the recorder to compare.
        self.values = TrackedValues(values) if recorder is not None else dict(values)
        self.resources = resources
        self.text_limits = self.values.pop("text limits", {})
        self._codec = TextCodec(encoding)
        self.events = events or {}
        self.macros = macros or {}
        self.clicks = 0
        self._levels = 0    # how deep events and macros nest now (MOST_LEVELS)
        self.recorder, self.places = recorder, places or {}
        self.screen = screen
        self.cards = cards
        self.series = series
        self.pinyin_table = pinyin_table_of(pinyin_table)
        self.page_values = page_values or {}
        self.list_working = None if folder_resources is None \
            else ListWorking(folder_resources, cards, encoding)
        self.set_page(page, components)

    def _type_of(self, component: str):
        """The type number of `component`, from the values, else from the
        page file's beneath them (page_values); None for no component."""
        found = self.values.get(component + ".type")
        return found if found is not None else self.page_values.get(component + ".type")

    def _layered(self):
        """The values, over the page file's for a test (page_values), as the
        working and a data record's methods read them; the values alone when
        there are none beneath."""
        return ChainMap(self.values, self.page_values) if self.page_values else self.values

    def set_page(self, page: str, components: list = None):
        """Makes `page` the page whose components the code names on their
        own, and by their IDs, `components` naming its objects in ID order."""
        self.page = page
        self.own_page = own_page_prefix(page) if page else None
        self.components = components

    def _component(self, command: str, argument: str):
        """Returns the name of the page's object that a command's first
        argument gives: itself when it names one, "255" for every component,
        or else the object of the ID the argument's value is, a number
        written or held in a variable or a value. A plain name holding no
        value is a component's, though `components` may not list it, as
        nxlang's generated hotspots. Without the page's objects, the
        argument as written. An ID no object of the page has fails as on
        the screen: the serial line's own instruction raises
        UnknownComponentId; a line of an event is recorded under "component
        errors", and None returned, the event going on."""
        if (self.components is None or argument in self.components
                or (_PLAIN_NAME.fullmatch(argument) and argument not in self.values)):
            return argument
        number = self._chain(argument)
        if number == 255:
            return "255"
        if isinstance(number, int) and 0 <= number < len(self.components):
            return self.components[number]
        if self._levels == 0:
            raise UnknownComponentId("%s %s: the page has no component of ID %s"
                                     % (command, argument, number))
        self._record("component errors", (command, argument))
        return None

    def move_arguments(self, arguments: tuple):
        """Returns the arguments of a `move` as it records them, read as the
        screen reads them: (its component's name, x1, y1, x2, y2, priority,
        time), the component given by name or ID as `click` gives it
        (_component), the others numbers, written or held. None for an ID no
        object of the page has, which _component records."""
        if len(arguments) != 7:
            raise RefusedCode("move takes 7 arguments: %r" % (arguments,))
        component = self._component("move", arguments[0])
        if component is None:
            return None
        numbers = [self._chain(argument) for argument in arguments[1:]]
        if not all(isinstance(number, int) for number in numbers):
            raise RefusedCode("move takes numbers after its component: %r" % (arguments,))
        return (component,) + tuple(int32(number) for number in numbers)

    def _move(self, arguments: list):
        """Runs `move`, recorded under "other commands". A move of no time
        puts its component at (x2, y2) at once. It stores them as code
        stores them, so the code after it reads the end. A move over time
        is the screen's, which moves it on its clock (simulation.py). A test
        has no clock, so it moves nothing over time. The screen is told of
        each move. Its arguments are read once, here, so that an ID no object
        has fails only once."""
        self._record("other commands", tuple(["move"] + arguments))
        given = self.move_arguments(tuple(arguments))
        if given is None:
            return
        component, _, _, x2, y2, _, time = given
        # A component whose place the machine does not know, as before any
        # page shows, is not moved.
        if time <= 0 and component + ".x" in self._layered():
            # A move places its component past what code may store, as
            # the Nextion Editor's simulator placed one at x 7000.
            self._store(component + ".x", x2, ranged=False)
            self._store(component + ".y", y2, ranged=False)
        if self.screen is not None:
            self.screen.move_given(given)

    def _on_card(self, path) -> bool:
        """Whether a path is on an SD card the simulation gave a folder."""
        return self.cards is not None and self.cards.owns(path)

    # A file stream, as the Nextion Editor's simulator ran one.
    # Its open file is "open file <name>"; its `val` is the position where
    # the next read or write takes place, `qty` the open file's size, and
    # `en` whether one is open.

    def _open_file(self, stream: str, path):
        """Opens the file `path` on the file stream `stream`, as a file
        command finds one (_file_bytes), its position at 0. A file not found
        closes the one open, and is recorded with the file errors."""
        data = self._file_bytes("open", path)
        if data is None:
            self._close_file(stream)
            return
        self.values[OPEN_FILE + stream] = path
        self._set_stream(stream, 0, len(data), 1)

    def _close_file(self, stream: str):
        """Closes the file stream's open file, if any."""
        self.values[OPEN_FILE + stream] = None
        self._set_stream(stream, 0, 0, 0)

    def _set_stream(self, stream: str, position: int, size: int, opened: int):
        """Sets the file stream's `val`, `qty`, and `en`."""
        for attribute, value in (("val", position), ("qty", size), ("en", opened)):
            self.values["%s.%s" % (stream, attribute)] = value

    def _file_bytes(self, command: str, path, missing: int = None):
        """Returns the bytes of the SD card's file `path`, found as `findfile`
        finds one: on a card given a folder, in that folder; else among the
        files in memory, "file contents", or the paths "existing", each a
        file of 0 bytes. None when there is none, or the card's folder
        refuses it; either is recorded with the file errors, once, as
        `(command, path)`. A file not found answers `missing`, if given; the
        card's folder answers its own refusals (_on_folder)."""
        if self._on_card(path):
            data = self._on_folder(
                command, path,
                lambda: self.cards.read(path) if self.cards.find_file(path) else None, False)
            if data is False:
                return None     # refused, and recorded (_on_folder)
        elif isinstance(path, str):
            existing = b"" if path in self.values.get("existing", ()) else None
            data = self.values.setdefault("file contents", {}).get(path, existing)
        else:
            data = None
        if data is None:
            self._record("file errors", (command, path))
            if missing is not None:
                self._refused(missing)
        return data

    def _rdfile(self, arguments: list):
        """Runs `rdfile <path>,<offset>,<count>,<crc>`, which sends `count`
        bytes of the SD card's file `path` from byte `offset`, or the file's
        size, 4 bytes, low byte first, for a count of 0, then the CRC `crc`
        asks for (_rdfile_crc). They are recorded in "sent", so that the
        success code follows them. A missing file, or a range not inside the
        file, sends nothing, and answers 0x06; for a count of 0, the offset
        must be below the size. The file is never changed."""
        path = self._operand(arguments[0])
        offset, count, crc = (self._chain(argument) for argument in arguments[1:])
        if offset < 0 or count < 0:
            raise RefusedCode("a negative offset or count is not modelled")
        data = self._file_bytes("rdfile", path, INVALID_FILE_OPERATION)
        if data is None:
            return
        if not (offset < len(data) if count == 0 else offset + count <= len(data)):
            self._record("file errors", ("rdfile", path))
            self._refused(INVALID_FILE_OPERATION)
            return
        sent = len(data).to_bytes(4, "little") if count == 0 else data[offset:offset + count]
        self._record("sent", ("rdfile", sent + _rdfile_crc(crc, sent)))

    def _read_or_write(self, stream: str, method: str, text: str, start: str, count: str):
        """Runs the file stream's `read` or `write`. `start` counts within
        the text, not the file, and `start` and `count` are bytes in the
        project's encoding. A read keeps the text's first `start` bytes and
        puts `count` of the file's after them, the text ending at the first
        zero byte; a write takes `count` bytes of the text from `start` and
        writes them over the file's. Both work at the position, `val`, and
        move it by `count`. One with no file open, whose file the card no
        longer gives, or that would go past the end of the file, is recorded
        with the file errors and does nothing, but that a read past the end
        cuts its text after its first `start` + `count` bytes, as the Nextion
        Editor's simulator cut "IJ" to "I"."""
        path = self.values.get(OPEN_FILE + stream)
        if path is None:
            self._record("file errors", (method, None))
            return
        start, count = self._chain(start), self._chain(count)
        if start < 0 or count < 0:
            raise RefusedCode("a negative start or count is not modelled")
        data = self._file_bytes(method, path)
        if data is None:
            return      # recorded (_file_bytes)
        position = self.values.get(stream + ".val", 0)
        own = self._codec.encode_keeping_bytes(self._operand(text), self._name(text))
        if position + count > len(data):
            self._record("file errors", (method, path))
            if method == "read" and len(own) > start + count:
                self._store(self._name(text), self._codec.decode_keeping_bytes(own[:start + count]))
            return
        if method == "read":
            if start > len(own):
                raise RefusedCode("a read past the end of its text is not modelled")
            read = data[position:position + count].split(b"\0", 1)[0]
            self._store(self._name(text), self._codec.decode_keeping_bytes(own[:start] + read))
        else:
            written = own[start:start + count]
            if len(written) != count:
                raise RefusedCode("a write past the end of its text is not modelled")
            changed = data[:position] + written + data[position + count:]
            if self._on_card(path):
                if self._on_folder("write", path, lambda: self.cards.write(path, changed),
                                   False) is False:
                    return      # refused, and recorded: the position stays
            else:
                self.values["file contents"][path] = changed
        self.values[stream + ".val"] = position + count

    def _on_folder(self, command: str, path: str, work, refused=None):
        """Returns `work()` on a card's folder, or on the card in memory,
        which refuses nothing. What the cards refuse, so as to harm nothing,
        is recorded with the file errors, and gives `refused`. So is what the
        disk refuses, such as a name Windows forbids or a file another
        program holds: the command fails, as on the screen, and the event
        goes on."""
        try:
            return work()
        except (CardRefusal, OSError) as error:
            self._record("file errors", (command, path))
            if isinstance(error, CardRefusal) and error.code is not None:
                self._refused(error.code)
            return refused

    def _refused(self, code: int):
        """Tells the simulation's screen, if any, the return code the screen
        gives a command it refuses, and whether the command is the
        instruction typed itself, outside any event, as `_component` tells
        them apart."""
        if self.screen is not None:
            self.screen.refused(code, self._levels == 0)

    def value_of(self, value: str):
        """Returns the value of `value` as the code writes it: an operand, or
        operands joined by operators, computed from left to right (_chain),
        such as the page `page appid&0x000000FF` opens. Raises ValueNotGiven
        for a name with no value, and RefusedCode for a `value` that does not
        read as operands joined by operators."""
        return self._chain(value)

    @property
    def in_event(self) -> bool:
        """Whether the line running is an event's or a macro's, rather than
        one typed on the serial line."""
        return self._levels > 0

    def run(self, lines: list, places: list = None):
        """Runs `lines` of Editor code and returns `values`, as the code left them.
        Comments and blank lines are skipped. Braces must balance. `places`
        gives the place of each line, for the recorder, and for the error of
        code that stops the run."""
        self.run_event(lines, places)
        return self.values

    def run_event(self, lines: list, places: list = None) -> bool:
        """Runs `lines`, an event's Editor code, as run does, and returns
        whether a `return` ended it. A page change leaves a page's `loadend`
        event out after a `load` event that one ended. It nests one level
        within what runs it, and stops the run past MOST_LEVELS."""
        self._levels += 1
        try:
            if self._levels > MOST_LEVELS:
                raise RefusedCode(
                    "Endless loop was detected: events, clicks, and macros nest more than %d "
                    "deep, which stops the screen" % MOST_LEVELS)
            return self._run_lines(lines, places)
        finally:
            self._levels -= 1
            # The outermost event ended, though a page change ended it early.
            if self._levels == 0:
                self._settle_lists()

    def run_instruction(self, text: str):
        """Runs `text`, an instruction typed on the serial line. A `return` or
        a `goto` there is no instruction, and stops it as one the machine
        does not know; a label line, a name it does not know, as the
        Editor's simulator answered them (0x00 and 0x1A). So is the form
        '&name&' outside a quoted text: nothing replaces it in a typed line,
        and the Editor's simulator answered `'&val&'=7` 0x1A. A first word that
        is no command answers as the Editor's compile refuses it
        (first_word_refusal, _NO_COMMAND_ANSWERS). The instruction is no
        level of its own: what it clicks or calls is the first."""
        code = split_line(text, 0)[1]
        if code == "return" or goto_label(code) is not None:
            raise RefusedCode("not an instruction: %r" % text)
        if LABEL.fullmatch(code):
            raise KeyError(code[:-1])
        if holds_own_attribute(code):
            raise KeyError(code)
        lacked = series_lacks(code, self.series) if self.series is not None else None
        if lacked is not None:
            raise CompileRefusal(_LACKED_ANSWERS[lacked[0]],
                                 "the screen's series lacks %s" % lacked[1])
        refusal = first_word_refusal(code)
        if refusal is not None:
            raise CompileRefusal(_NO_COMMAND_ANSWERS[refusal],
                                 "the Nextion Editor has no command %s" % first_word(code))
        # No level of its own, so no frame of the recorder's either.
        try:
            self._execute(_parsed((text,), None))
        finally:
            self._settle_lists()

    def _settle_lists(self):
        """Settles the scroll values of the page's lists that code changed,
        as the screen settles them once an event or a typed instruction
        ends, and at a `doevents` (list_working.py, settle). Until then,
        code reads back what it set."""
        if self.list_working is not None:
            self.list_working.settle(self.page,
                                     lambda name: TYPE_NAMES.get(self._type_of(name)),
                                     self._layered(), self.values)

    def _run_lines(self, lines: list, places: list) -> bool:
        """Runs `lines` of Editor code, telling the recorder, if any, as they
        are entered and left, and returns whether a `return` ended them."""
        ops = _parsed(tuple(lines), tuple(places) if places else None)
        if self.recorder is not None:
            self.recorder.enter()
        try:
            return self._execute(ops)
        finally:
            if self.recorder is not None:
                self.recorder.leave()

    def _execute(self, ops: tuple) -> bool:
        """Runs an event's ops (_flattened), and returns whether a `return`
        ended it. Each loop counts its turns from 0 as it is entered by its
        line, and each goto its jumps back, both stopped at _MOST_TURNS; a
        goto into a loop's block counts on from where its count stood. Code
        that stops the run is raised with the place of the op it stopped at
        (_located)."""
        turns, jumps_back = {}, {}
        index, place = 0, None
        try:
            while index < len(ops):
                op, index = ops[index], index + 1
                # Each op but a jump holds its place last, which the recorder
                # is told of. A loop's first test has none, as entering the
                # loop recorded its step: what stops there keeps the loop's
                # place, for its error.
                own = None if op[0] == "jump" else op[-1]
                if op[0] != "jump" and not (op[0] == "test" and own is None):
                    place = own
                if op[0] == "line":
                    self._step(own)
                    self._run_simple(op[1])
                elif op[0] == "test":
                    _, condition, otherwise, _ = op
                    self._step(own)
                    if not self._condition(condition):
                        index = otherwise
                elif op[0] == "jump":
                    index = op[1]
                elif op[0] == "enter":
                    _, loop, start, _ = op
                    self._step(own)
                    turns[loop] = 0
                    if start:
                        self._run_simple(start)
                elif op[0] == "turn":
                    _, loop, step, test, _ = op
                    if step:
                        self._run_simple(step)
                    turns[loop] = turns.get(loop, 0) + 1
                    if turns[loop] >= _MOST_TURNS:
                        raise RefusedCode("the loop does not end")
                    self._step(own)
                    index = test
                elif op[0] == "goto":
                    _, label, _ = op
                    self._step(own)
                    if label < index:
                        jumps_back[index] = jumps_back.get(index, 0) + 1
                        if jumps_back[index] >= _MOST_TURNS:
                            raise RefusedCode("the loop does not end")
                    index = label
                else:
                    self._step(own)
                    return True
        except (RefusedCode, ValueNotGiven) as error:
            _placed(error, place)
            raise
        return False

    def _step(self, place):
        """Tells the recorder, if any, of a statement about to run at `place`.
        A line with no place, which the compiler added, is no step."""
        if self.recorder is not None and place is not None:
            self.recorder.step(place, self.values)

    def _run_simple(self, line: str):
        """Runs one line that is not an if, while, or for. One the running
        screen refuses changes nothing: it is recorded under "refusals", the
        screen answers its code, and what runs it goes on."""
        try:
            self._simple(line)
        except ScreenRefusal as refusal:
            self._record("refusals", (refusal.code, line))
            self._refused(refusal.code)

    def _check_parameters(self, line: str):
        """Raises CompileRefusal for a command given another number of
        parameters than it takes (COMMAND_PARAMETERS), or written alone where
        it takes some, as the Editor's simulator answered such a typed line:
        0x1E, but 0x00 for add alone, as its compile refuses that as no
        command (NO_COMMAND_WHEN_ALONE). In an event, it stops the run."""
        word, _, rest = line.partition(" ")
        if not rest and word in NO_NUMERIC_FORM:
            raise CompileRefusal(_INVALID_PARAMETER_COUNT, "%s takes parameters: %r"
                                 % (word, line))
        wanted = COMMAND_PARAMETERS.get(word)
        if wanted is not None and len(command_arguments(rest)) != wanted:
            code = _NO_COMMAND_ANSWERS[INVALID_COMMAND] if not rest \
                and word in NO_COMMAND_WHEN_ALONE else _INVALID_PARAMETER_COUNT
            raise CompileRefusal(code, "%s takes %d parameters: %r" % (word, wanted, line))

    def _check_resource(self, kind: str, resource_id, code: int):
        """Raises ScreenRefusal, answering `code`, for a picture, a font, an
        animation, a video, or a sound (`kind`) the project lacks, 65535
        among them: the Editor's simulator refused it too, though a page file
        gives it for no picture. Any ID is taken without the project's
        `resources`."""
        if self.resources is not None and (not isinstance(resource_id, int)
                                           or self.resources.name_of(kind, resource_id) is None):
            raise ScreenRefusal(code, "the project has no %s %r" % (NOUNS[kind], resource_id))

    def _check_waveform(self, command: str, component_id, channel):
        """Raises ScreenRefusal, answering 0x12, for `add` or `cle` naming by
        its ID no waveform of the page, or a channel past its count, 255
        standing for every channel in `cle`. The Editor's simulator answered
        `add` so; `cle` is taken to answer alike. Any is taken without the
        page's objects; the component's type and channels are checked where
        the values give them, as a simulation's do."""
        if self.components is None:
            return
        name = (self.components[component_id] if isinstance(component_id, int)
                and 0 <= component_id < len(self.components) else None)
        kind = self._type_of(name) if name is not None else None
        if name is None or kind not in (None, TYPES_BY_NAME["waveform"]):
            raise ScreenRefusal(_INVALID_WAVEFORM, "%s: the page has no waveform of ID %r"
                                % (command, component_id))
        channels = self.values.get(name + ".ch")
        every = command == "cle" and channel == _EVERY_CHANNEL
        if channels is not None and not every and not (isinstance(channel, int)
                                                       and 0 <= channel < channels):
            raise ScreenRefusal(_INVALID_WAVEFORM, "%s: the waveform %s has no channel %r"
                                % (command, name, channel))

    def _transparent_data(self, word: str, arguments: list):
        """Runs `addt` or `wept`, whose data comes next on the serial line,
        as bytes, not as instructions. As the Nextion Editor's simulator
        did, the screen ignores `addt` for a waveform or a channel the page
        lacks, or a count past _MOST_ADDT_BYTES, answering 0x12, and `wept`
        at a negative address, answering 0x1D (ScreenRefusal). A negative
        count is ignored alike. The screen then takes the bytes
        (Simulation.take_transparent_data).
        Without a screen, as in a test, the command is recorded with the
        other commands."""
        numbers = [self._chain(argument) for argument in arguments]
        if word == "addt":
            component_id, channel, count = numbers
            self._check_waveform(word, component_id, channel)
            if not 0 <= count <= _MOST_ADDT_BYTES:
                raise ScreenRefusal(_INVALID_WAVEFORM, "addt takes 0 to %d bytes, not %d"
                                    % (_MOST_ADDT_BYTES, count))
        else:
            address, count = numbers
            if address < 0 or count < 0:
                raise ScreenRefusal(_FAILED_EEPROM_ACCESS, "wept takes a place and a count "
                                    "from 0, not %d,%d" % (address, count))
        if self.screen is None:
            self._record("other commands", tuple([word] + arguments))
        else:
            self.screen.take_transparent_data(word, numbers)

    def _twfile(self, arguments: list):
        """Runs `twfile <path>,<size>`, whose file's bytes come next on the
        serial line, as `addt`'s do. As the Nextion Editor's simulator did,
        the screen refuses, answering 0x06, a path on neither sd0/ nor
        sd1/, as in ram/; a size of 0 or below; and, on a card given a
        folder, a folder the card lacks. It refuses a size that is no
        number, answering 0x1A. A path the card's folder refuses so as to
        harm nothing, as one leaving it, answers its own code (_on_folder).
        Each refusal is recorded with the file errors, and starts no
        transfer. Otherwise the screen takes the bytes, and writes the file
        once they are in (Simulation.take_transparent_data). Without a
        screen, as in a test, the command is recorded with the other
        commands, and writes nothing."""
        path, size = self._operand(arguments[0]), self._chain(arguments[1])
        code = None
        if not isinstance(size, int):
            code = _INVALID_VARIABLE
        elif not (isinstance(path, str) and path.lower().startswith(("sd0/", "sd1/"))) \
                or size <= 0:
            code = INVALID_FILE_OPERATION
        elif self._on_card(path):
            has_folder = self._on_folder("twfile", path,
                                         lambda: self.cards.local(path).parent.is_dir())
            if has_folder is None:
                return      # refused, and recorded (_on_folder)
            if not has_folder:
                code = INVALID_FILE_OPERATION
        if code is not None:
            self._record("file errors", ("twfile", path))
            self._refused(code)
        elif self.screen is None:
            self._record("other commands", tuple(["twfile"] + arguments))
        else:
            self.screen.take_transparent_data("twfile", [path, size])

    def _ucopy(self, arguments: list):
        """Runs `ucopy <attribute>,<from>,<count>,<to>`, which copies bytes
        of the buffer of protocol reparse mode into a number's bytes or a
        text's characters (serial_buffer.py). Outside the mode it copies
        nothing, as the Editor's simulator copied nothing while `recmod`
        was 0."""
        if not self.values.get("recmod", 0):
            return
        target = arguments[0]
        start, count, to = (self._chain(argument) for argument in arguments[1:])
        buffer = self.values.get("serial buffer", b"")
        name = self._name(target)
        value = self._operand(target)
        if isinstance(value, str):
            text = self._codec.encode_keeping_bytes(value, target)
            value = self._codec.decode_keeping_bytes(
                copied_into_text(text, buffer, start, count, to))
        else:
            value = copied_into_number(value, buffer, start, count, to)
        self._store(name, value)

    def _udelete(self, count: str):
        """Runs `udelete <count>`, which removes the first bytes of the buffer
        of protocol reparse mode (serial_buffer.py). Outside the mode it
        removes nothing, as `ucopy` copies nothing then. No probe can see
        it: the end of the mode empties the buffer, and every read of it is
        blocked until the mode starts again."""
        if self.values.get("recmod", 0):
            buffer = self.values.get("serial buffer", b"")
            self.values["serial buffer"] = deleted(buffer, self._chain(count))

    def _buffer_read(self, name: str) -> int:
        """Reads `usize` or `u[index]` (serial_buffer.py). While `recmod` is
        0, the screen ignores the read, answering 0x1A, and it gives 0, as
        the Nextion Editor's simulator answered at each read."""
        if not self.values.get("recmod", 0):
            self._record("refusals", (_INVALID_VARIABLE, name))
            self._refused(_INVALID_VARIABLE)
            return 0
        return buffer_read(self.values.get("serial buffer", b""), name)

    def _check_eeprom_address(self, address: int, count: int = 1):
        """Raises ScreenRefusal, answering 0x1D, for an access of `count`
        bytes at `address` that does not fit in the EEPROM. The Editor's
        simulator refused a `repo` starting past its last byte, and a `wepo`
        or a `repo` running past it, changing nothing. An address before the
        first byte is taken to answer alike, and so is `rept`, whose count is
        not checked."""
        if not 0 <= address < EEPROM_SIZE or address + count > EEPROM_SIZE:
            missing = address if not 0 <= address < EEPROM_SIZE else EEPROM_SIZE
            raise ScreenRefusal(_FAILED_EEPROM_ACCESS, "the EEPROM has no byte %d" % missing)

    def _simple(self, line: str):
        """Runs one line that is not an if, while, or for."""
        if line.startswith("//"):
            return
        if line == "doevents":
            # The screen draws what code changed, settling its lists.
            self._settle_lists()
            return
        # Built code always holds the number a command takes, as the build
        # refuses another. A typed line, and code given to the runner
        # directly, may not.
        self._check_parameters(line)
        if line.startswith("tsw "):
            name, touch = _arguments(line[4:])
            name = self._component("tsw", name)
            if name is not None:
                self._store("touch " + name, self._chain(touch))
            return
        if line.startswith("page "):
            self.values["page opened"] = line[5:]
            if self.screen is not None:
                self.screen.page_changed(line[5:], self)
            return
        if self._card_command(line) or self._crc_command(line):
            return
        # What prints and printh send over the serial line is recorded in "sent".
        command = re.match(r"prints (.*)$", line)
        if command:
            text, length = _arguments(command[1])
            self._record("sent", (self._operand(text), self._chain(length)))
            return
        command = re.match(r"printh (.*)$", line)
        if command:
            self._record("sent", ("printh", command[1]))
            return
        # A waveform's points and clearings are recorded in "waveform", as
        # ("add", id, channel, value) and ("cle", id, channel). Each number
        # may be arithmetic, as `99-n.val`: the Editor's simulator ran it in
        # `add`, and `cle` is taken to read its numbers alike.
        command = re.match(r"(add|cle) (.*)$", line)
        if command:
            numbers = tuple(self._chain(argument) for argument in _arguments(command[2]))
            if len(numbers) >= 2:
                self._check_waveform(command[1], numbers[0], numbers[1])
            self._record("waveform", (command[1],) + numbers)
            return
        if self._drawing_command(line):
            return
        command = re.match(r"(%s) (.*)$" % "|".join(PINYIN_COMMANDS), line)
        if command and self.pinyin_table is not None:
            self._pinyin(command[1], _arguments(command[2]))
            return
        if self._outside(line):
            return
        if line.startswith("vis "):
            name, shown = line[4:].split(",")
            name = self._component("vis", name)
            if name is not None:
                self._store("vis " + name, self._chain(shown))
            return
        if line.startswith("click "):
            name, which = line[6:].split(",")
            name = self._component("click", name)
            # Typed while the screen sleeps, it runs nothing.
            if name is None or (self.screen is not None and self.screen.asleep):
                return
            self.clicks += 1
            if self._levels == 0 and self.screen is not None:
                # A typed click is answered before its event runs, as the
                # Editor's simulator answered it.
                self.screen.answer_typed_now()
            # `click b0,1` runs the Touch Press event, `click b0,0` the Touch Release
            # event. A button's `val` is set first, as a press and a release set it.
            if self._type_of(name) == TYPES_BY_NAME["button"]:
                self._store(name + ".val", 1 if which == "1" else 0)
            key = (name, "down" if which == "1" else "up")
            self.run(self.events.get(key, []), self.places.get(key))
            if which == "0" and self.screen is not None:
                self.screen.released(name, self)
            return
        if line.startswith("call "):
            # Its labels are its own, and a return ends it alone, as a clicked
            # event's do.
            macro = self.macros.get(line[len("call "):])
            if macro is not None:
                self.run_event(*macro)
            return
        command = re.match(r"(covx|substr|spstr|strlen|btlen) (.*)$", line)
        if command:
            self._command(command[1], _arguments(command[2]))
            return
        # cov is covx's older form, without the format argument.
        command = re.match(r"cov (.*)$", line)
        if command:
            self._command("covx", _arguments(command[1]) + ["0"])
            return
        match = re.match(r"^(%s)(\+\+|--)$" % OPERAND, line)
        if match:
            name = self._name(match[1])
            self._check_assignable(name)
            self._store(name, int32(self._value(name) + (1 if match[2] == "++" else -1)))
            return
        match = ASSIGNMENT.match(line)
        if not match:
            raise _unreadable_line("not code in strict Nextion syntax: %r" % line)
        name, operator, chain = self._name(match[1]), match[2], match[3]
        self._check_assignable(name)
        is_text = isinstance(self.values.get(name), str)
        subtracted = _TEXT_SUBTRACTION.match(chain) if is_text and operator == "=" else None
        if subtracted:
            # The vendor's instruction set (operator 2.4): the text itself first.
            if self._name(subtracted[1]) != name:
                raise RefusedCode("a text subtraction starts with the text itself: %r" % line)
            self._store(name, self._without_last(name, subtracted[2]))
        elif is_text and operator in ("=", "+="):
            self._store(name, self._text_join(name, operator, chain))
        elif operator == "=":
            self._store(name, self._chain(chain))
        elif is_text and operator == "-=":
            self._store(name, self._without_last(name, chain))
        else:
            # The Editor computes x-=a+b as x-a+b, from left to right.
            self._store(name, self._chain(match[1] + operator[:-1] + chain))

    def _crc_command(self, line: str) -> bool:
        """Runs `line` when it is `crcrest`, `crcputs`, `crcputh`, or
        `crcputu`, and returns whether it was one. They update the running
        CRC, which `crcval` contains (modbus_crc.py). `crcrest 1,start` starts
        it. A start above 65535 is ignored, answering 0x1A, and a type other
        than 1 turns the CRC off. `crcputs` adds the bytes `prints` sends for a
        value, or the first of them for a length, but none for a length past
        them. `crcputh` adds bytes written in hexadecimal, and refuses a text
        that is not. `crcputu start,count` adds `count` bytes of the buffer of
        protocol reparse mode, from its byte `start`. It adds none outside the
        mode, for a count below 1, or for bytes past the buffer's end. While
        the CRC is off, or in a test that does not give `crcval`, they add
        nothing."""
        word, _, rest = line.partition(" ")
        # Their number of arguments, two, was checked with every command's
        # (_check_parameters).
        if word in ("crcrest", "crcputs", "crcputu"):
            arguments = _arguments(rest)
        if word == "crcrest":
            kind, start = (self._chain(argument) for argument in arguments)
            if kind != 1:
                self.values["crcval"] = CRC_OFF
            elif start > 0xFFFF:
                raise ScreenRefusal(_INVALID_VARIABLE, "a CRC starts from at most 65535")
            else:
                self.values["crcval"] = crc_start(start)
            return True
        if word == "crcputs":
            operand, length = arguments
            data = value_bytes(self._operand(operand), 0, self._codec.name)
            length = self._chain(length)
            # The Nextion Editor's simulator added nothing for a length past
            # the value's bytes, where `prints` sends what there is.
            added = data if length == 0 else data[:length] if 0 < length <= len(data) else b""
        elif word == "crcputh":
            try:
                added = bytes.fromhex(rest)
            except ValueError:
                raise RefusedCode("crcputh %s: not hexadecimal" % rest) from None
        elif word == "crcputu":
            start, count = (self._chain(argument) for argument in arguments)
            buffer = self.values.get("serial buffer", b"")
            # The vendor gives it in protocol reparse mode only. The Nextion
            # Editor's simulator added nothing for bytes past the buffer's end,
            # where ucopy reads them.
            inside = (self.values.get("recmod", 0) and 0 <= start
                      and 0 < count <= len(buffer) - start)
            added = buffer[start:start + count] if inside else b""
        else:
            return False
        crc = self.values.get("crcval", CRC_OFF)
        if crc != CRC_OFF:
            self.values["crcval"] = crc_after(crc, added)
        return True

    def _card_command(self, line: str) -> bool:
        """Runs `line` when it is a command of the SD card's files, and
        returns whether it was one. findfile and finddir find the paths in
        "existing" and the files in "file contents", {path: bytes}
        (_find_on_card). File streams read and write those files, and data
        records their data files. newfile adds one and delfile removes one
        (_path_command). The commands that change files are recorded in
        "file commands"."""
        contents = self.values.setdefault("file contents", {})
        command = re.match(r"(findfile|finddir) (.*)$", line)
        if command:
            path, target = _arguments(command[2])
            self._find_on_card(command[1], path, target, contents)
            return True
        command = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\.(open|read|write|close|find)\((.*)\)$",
                           line)
        if command:
            stream, method = command[1], command[2]
            arguments = _arguments(command[3]) if command[3] else []
            if method == "open":
                self._open_file(stream, self._operand(arguments[0]))
            elif method == "close":
                self._close_file(stream)
            elif method in ("read", "write"):
                self._read_or_write(stream, method, *arguments)
            # find: the Nextion Editor's simulator answered it as a success
            # and changed nothing seen, of a file the card has or lacks; what
            # a screen does with it is not known.
            return True
        command = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\.(insert|delete|up|clear)\((.*)\)$", line)
        if command and _is_data_record(command[1], self._layered()):
            self._data_record(command[1], command[2],
                              _arguments(command[3]) if command[3] else [])
            return True
        command = re.match(r"(newdir|deldir|delfile|refile|redir|newfile) (.*)$", line)
        if command:
            self._path_command(command[1], _arguments(command[2]), contents)
            return True
        if line.startswith("rdfile "):
            self._rdfile(_arguments(line[len("rdfile "):]))
            return True
        if re.fullmatch(r"[A-Za-z0-9_]+\.up\(\)", line):
            browser = line[:-5]
            self._record("file commands", ("up", browser))
            if self.list_working is not None:
                self.list_working.up(self.page, browser, self._layered(), self.values)
            return True
        return False

    def _find_on_card(self, word: str, path: str, target: str, contents: dict):
        """Runs findfile or finddir, `word`: sets `target` to 1 when the card
        has `path`, else 0. On a card given a folder, the folder answers; on
        the card in memory, the paths in "existing" and the files in
        `contents`, "file contents", do."""
        path = self._operand(path)
        if self._on_card(path):
            find = self.cards.find_file if word == "findfile" else self.cards.find_folder
            found = self._on_folder(word, path, lambda: find(path), False)
        else:
            found = path in self.values.get("existing", ()) or path in contents
        self.values[self._name(target)] = int(found)

    def _path_command(self, word: str, arguments: list, contents: dict):
        """Runs `word`, one of newfile, newdir, delfile, deldir, refile, and
        redir, on its `arguments`, and records it in "file commands". On a
        card given a folder, the folder does it. On the card in memory,
        newfile adds a file of its size, all zero bytes, to `contents`,
        "file contents", and delfile removes one. A newfile whose size is
        no number, or below 0, makes no file, and is recorded with the file
        errors."""
        # newfile's size may be arithmetic, as the Editor's simulator ran it.
        paths = [self._chain(argument) if word == "newfile" and place == 1
                 else self._operand(argument)
                 for place, argument in enumerate(arguments)]
        if word == "newfile" and not isinstance(paths[1], int):
            self._record("file errors", ("newfile", paths[0]))
            self._refused(_INVALID_VARIABLE_OPERATION)
            return
        if word == "newfile" and paths[1] < 0:
            # A size below 0 makes no file, as the Nextion Editor's
            # simulator answered -1 and -100.
            self._record("file errors", ("newfile", paths[0]))
            self._refused(INVALID_FILE_OPERATION)
            return
        self._record("file commands", (word, *paths))
        if self._on_card(paths[0]):
            act = {"newfile": lambda: self.cards.new_file(paths[0], paths[1]),
                   "newdir": lambda: self.cards.new_folder(paths[0]),
                   "delfile": lambda: self.cards.delete_file(paths[0]),
                   "deldir": lambda: self.cards.delete_folder(paths[0]),
                   "refile": lambda: self.cards.rename(paths[0], paths[1]),
                   "redir": lambda: self.cards.rename_folder(paths[0], paths[1])}[word]
            self._on_folder(word, paths[0], act)
            return
        if word == "newfile":
            contents.setdefault(paths[0], bytes(paths[1]))
        if word == "delfile":
            contents.pop(paths[0], None)

    def _drawing_command(self, line: str) -> bool:
        """Runs `line` when it is a drawing command, and returns whether it
        was one. Drawing commands paint on the screen, not on a component:
        what each painted is recorded in "painted", in order, its arguments
        computed. ref_stop and ref_star are recorded there too, and tell the
        screen, if any."""
        command = re.match(r"(cls|picq|pic|xpic|xstr|fill|line|draw|cirs|cir|ref) (.*)$", line)
        if command:
            arguments = _arguments(command[2])
            if command[1] == "ref":
                computed = [self._component("ref", arguments[0])]
                if computed[0] is None:
                    return True
            elif command[1] == "xstr":
                computed = [self._chain(argument) for argument in arguments[:-1]]
                computed.append(self._operand(arguments[-1]))
            else:
                computed = [self._chain(argument) for argument in arguments]
            if command[1] in PICTURE_ARGUMENTS:
                self._check_resource(PICTURE, computed[PICTURE_ARGUMENTS[command[1]]],
                                     _INVALID_PICTURE)
            self.values.setdefault("painted", []).append((command[1], *computed))
            if command[1] == "xstr":
                # Its background was painted when its font was found missing.
                self._check_resource(FONT, computed[XSTR_FONT_ARGUMENT], _INVALID_FONT)
            return True
        if line in ("ref_stop", "ref_star"):
            self.values.setdefault("painted", []).append((line,))
            if self.screen is not None:
                self.screen.drawing_stopped(line == "ref_stop", self)
            return True
        return False

    def _check_assignable(self, name: str):
        """Raises CompileRefusal, a failed assignment, for a typed
        instruction assigning `name`, an attribute that code cannot change on
        its component's type (attribute_descriptions.code_cannot_change), as
        the Nextion Editor's compile refuses it in code. Its simulator
        answered every such attribute so, changing nothing, on each type and
        the page, but those the screen does not hold: they answer as one
        (_store), as `objname` did. So too, given the screen's series, one
        code cannot change on that series
        (editor_limits.code_cannot_change_on_series), as a Basic screen
        answered a typed `x`. Event code, which the build checks, assigns it
        as it runs."""
        if self._levels != 0 or self._unheld(name):
            return
        component, _, attribute = name.rpartition(".")
        type_name = TYPE_NAMES.get(self._type_of(component))
        if type_name is not None and code_cannot_change(type_name, attribute):
            raise CompileRefusal(_FAILED_ASSIGNMENT, "code cannot change %s" % name)
        if (type_name is not None and self.series is not None and type_has(type_name, attribute)
                and code_cannot_change_on_series(type_name, attribute, self.series)):
            raise CompileRefusal(_FAILED_ASSIGNMENT, "code cannot change %s on the screen's "
                                 "series" % name)

    def _outside(self, line: str) -> bool:
        """Runs `line` when it is a command reaching outside the screen: the
        serial line, the EEPROM, GPIO, or one of the rest of the instruction
        set the machine only records. Returns whether it was one."""
        word, _, rest = line.partition(" ")
        arguments = _arguments(rest) if rest else []
        if word == "print":
            # What print sends is what prints sends with a length of 0.
            self._record("sent", (self._operand(arguments[0]), 0))
        elif word == "get":
            self._record("replies", ("get", self._operand(arguments[0])))
        elif line == "sendme":
            self._record("replies", ("sendme", self.values.get("dp", 0)))
        elif word in ("wepo", "repo"):
            self._eeprom(word, arguments[0], self._chain(arguments[1]))
        elif word == "rept":
            address, count = self._chain(arguments[0]), self._chain(arguments[1])
            self._check_eeprom_address(address)
            self._record("replies", ("rept", self._eeprom_bytes()[address:address + count]))
        elif word == "cfgpio":
            self._record("gpio", ("cfgpio", self._chain(arguments[0]),
                                     self._chain(arguments[1]), arguments[2]))
        elif word == "randset":
            self.values["rand range"] = (self._chain(arguments[0]), self._chain(arguments[1]))
        elif word == "rest":
            self.values["reset"] = 1
            if self.screen is not None:
                self.screen.reset_asked()
        elif word == "move":
            self._move(arguments)
        elif word in ("addt", "wept"):
            self._transparent_data(word, arguments)
        elif word == "twfile":
            self._twfile(arguments)
        elif word == "ucopy":
            self._ucopy(arguments)
        elif word == "udelete":
            self._udelete(arguments[0])
        elif word in RECORDED_ONLY or line in RECORDED_ONLY:
            self._record("other commands", tuple([word] + arguments))
        else:
            return False
        return True

    def _record(self, record: str, entry):
        """Adds `entry` to the list `record` of what reached outside the
        screen, and tells the simulation's screen, if any. `record` is one of
        RECORDS, which the debugger and the simulation read to tell records
        from the app's own values."""
        assert record in RECORDS, "%r is not among RECORDS" % record
        self.values.setdefault(record, []).append(entry)
        if self.screen is not None:
            self.screen.recorded(record, entry, self)

    def _data_record(self, record: str, method: str, arguments: list):
        """Runs the method of the data record `record` on its data file,
        `path` (data_files.py): insert(text), delete(number, count),
        up(text, number), or clear(), records being numbered from the
        oldest. A call is refused as the Editor refuses it as it compiles:
        one with too few or too many arguments, a text where a number goes,
        or texts joined. The file is on a card's folder, or in
        "file contents"; a missing one is made first when `mode` is 1. What
        cannot be done is recorded with the file errors, changing nothing: a
        number where a text goes, which the Editor compiles and the screen
        ignores, a missing file with `mode` 0, a damaged one, one the folder
        will not give or take, a record longer than `lenth` bytes, or a
        number past the last record. A record that opens no file, its `init`
        being 1 (_opens_no_file), changes nothing, the call counting as
        done. Afterwards `qty` counts the records, and `txt` holds the
        chosen one's text (`val`), or nothing when `val` names none."""
        values = [self._chain(argument) for argument in arguments]
        kinds = DATA_RECORD_ARGUMENTS[method]
        places = list(zip(arguments, values, kinds))
        refused = len(values) != len(kinds) or any(
            (kind is int and isinstance(value, str))
            or (kind is str and not re.fullmatch(OPERAND, argument))
            for argument, value, kind in places)
        if refused:
            raise RefusedCode("the Nextion Editor refuses %s.%s(%s)"
                              % (record, method, ",".join(arguments)))
        path = self._layered().get(record + ".path", "")
        misplaced = any(kind is str and not isinstance(value, str) for _, value, kind in places)
        if not misplaced and self._opens_no_file(record):
            # Its `init` is 1: done, changing nothing.
            return
        if not misplaced and self._opening_refused(record):
            # Another record holds the file, or 8 others hold theirs. The
            # method changes nothing, and counts as done.
            shut_out(self.values, self._holder(record))
            return
        data_file = None if misplaced else self._data_file(record)
        if data_file is None:
            self._record("file errors", (method, path))
            return
        hold_file(self.cards, path, self.values, self._holder(record))
        let_in(self.values, self._holder(record))
        where = "%s.%s" % (record, method)
        texts = [self._codec.encode_keeping_bytes(value, where) for value in values
                 if isinstance(value, str)]
        numbers = [value for value in values if not isinstance(value, str)]
        if method == "insert":
            done = data_file.insert(texts[0])
        elif method == "delete":
            done = data_file.delete(numbers[0], numbers[1])
        elif method == "up":
            done = data_file.update(texts[0], numbers[0])
        else:
            data_file.clear()
            done = True
        if not done:
            self._record("file errors", (method, path))
            return
        content = data_file.to_bytes()
        # A file the folder will not take is left as it was.
        if self._on_folder(method, path,
                           lambda: write_card_file(self.cards, path, content, self.values),
                           refused=True):
            return
        self._record("file commands", (method, path))
        self._show_record(record, data_file)

    def _data_file(self, record: str):
        """The data file of the data record `record`, on a card's folder or in
        "file contents", made anew when it is missing and `mode` is 1; None
        when it is missing otherwise, damaged, or one the folder will not
        give."""
        attributes = component_attributes(record, self._layered())
        path = attributes.get("path", "")
        found = self._on_folder("read", path,
                                lambda: read_card_file(self.cards, path, self.values),
                                refused=False)
        # Unread is not missing: a file made anew would be written over it.
        if found is False:
            return None
        return data_file_for(attributes, found)

    def _choose_record(self, record: str, number) -> bool:
        """Code sets the data record `record`'s `val` to `number`: its `txt`
        becomes that record's text, or nothing for -1, none. Returns False,
        `val` and `txt` left as they were, for a number past the last record."""
        data_file = self._readable_data_file(record)
        records = data_file.records() if data_file is not None else []
        if number == -1:
            self._store(record + ".txt", "")
            return True
        if not isinstance(number, int) or not 0 <= number < len(records):
            return False
        self._store(record + ".txt", self._codec.decode_keeping_bytes(records[number]))
        return True

    def _holder(self, record: str) -> tuple:
        """Returns the data record `record` as the holdings name it: (its
        page, its own name). Code names a record of another page with that
        page's name first, as page1's code names page0's global d0
        "page0.d0"."""
        page, dot, own = record.rpartition(".")
        return (page, own) if dot else (self.page, record)

    def _opening_refused(self, record: str) -> bool:
        """Whether the data record `record` may not open the file its `path`
        names: another record holds it, or other records hold the most
        files there may be (card_files.opening_refusal)."""
        path = self._layered().get(record + ".path", "")
        return bool(opening_refusal(self.cards, path, self.values, self._holder(record)))

    def _opens_no_file(self, record: str) -> bool:
        """Whether the data record `record` opens no file, its `init` being 1
        (card_files.opens_no_file)."""
        return opens_no_file(component_attributes(record, self._layered()), self.values,
                             self._holder(record))

    def _readable_data_file(self, record: str):
        """The data file the data record `record` reads its records from, as
        _data_file gives it, or None while it opens none (_opens_no_file),
        or is shut out of it: it may not open it now, or could not when it
        last tried, `record` having opened none since (is_shut_out)."""
        holder = self._holder(record)
        if self._opens_no_file(record):
            return None
        if self._opening_refused(record):
            shut_out(self.values, holder)
            return None
        if is_shut_out(self.cards, self._layered().get(record + ".path", ""), self.values,
                       holder):
            return None
        return self._data_file(record)

    def _open_named_file(self, record: str):
        """Code set the data record `record`'s `path`: it lets go of the file
        it held, and opens the one its path names, which it then holds. When
        it may not open that (_opening_refused), it opens nothing, is shut
        out of it, and answers 0x06."""
        holder = self._holder(record)
        given_a_path(self.values, holder)
        let_go_of_files(self.values, holder)
        path = self.values[record + ".path"]
        if self._opening_refused(record):
            shut_out(self.values, holder)
            self._record("file errors", ("open", path))
            self._refused(INVALID_FILE_OPERATION)
            self._show_record(record, None)
            return
        let_in(self.values, holder)
        data_file = self._data_file(record)
        if data_file is not None:
            hold_file(self.cards, path, self.values, holder)
        self._show_record(record, data_file)

    def _show_record(self, record: str, data_file):
        """Sets what follows from the data record `record`'s data file
        `data_file` (data_record_values)."""
        for attribute, value in data_record_values(record, self._layered(), data_file,
                                                   self._codec).items():
            self._store("%s.%s" % (record, attribute), value)

    def _eeprom_bytes(self) -> bytes:
        """The EEPROM, as "eeprom" holds it, or empty: EEPROM_SIZE zero bytes."""
        return self.values.setdefault("eeprom", bytes(EEPROM_SIZE))

    def _eeprom(self, word: str, target: str, address: int):
        """Writes (wepo) or reads (repo) `target` at `address` of the EEPROM.
        A number takes 4 bytes, low byte first; a text field its txt_maxl
        bytes and one more, an attribute X its X_m bytes and one more ("text
        limits"; as the Editor's simulator wrote an animation's path), and a
        text constant its bytes and one more, the text ended by a zero byte,
        as the vendor's instruction set says. A text field's read takes its
        limit's bytes, without the one more. An access running past the
        EEPROM's last byte is refused (_check_eeprom_address)."""
        data = self._eeprom_bytes()
        is_text = target.startswith('"') or isinstance(self._operand(target), str)
        name = None if target.startswith('"') or re.fullmatch(NUMBER, target) \
            else self._name(target)
        if word == "wepo":
            value = self._operand(target)
            if is_text:
                encoded = self._codec.encode_keeping_bytes(value, target)
                size = self.text_limits.get(name, len(encoded)) + 1
                written = encoded[:size - 1].ljust(size, b"\0")
            else:
                written = (value % 2 ** 32).to_bytes(4, "little")
            self._check_eeprom_address(address, len(written))
            self.values["eeprom"] = data[:address] + written + data[address + len(written):]
            self._record("eeprom accesses", ("wepo", address, written))
        else:
            if is_text:
                # A text whose limit is not known is read up to the EEPROM's end.
                size = self.text_limits.get(name)
                self._check_eeprom_address(address, 1 if size is None else size)
                end = EEPROM_SIZE if size is None else address + size
                read = self._codec.decode_keeping_bytes(data[address:end].split(b"\0", 1)[0])
            else:
                self._check_eeprom_address(address, 4)
                read = int32(int.from_bytes(data[address:address + 4], "little"))
            self._store(name, read)
            self._record("eeprom accesses", ("repo", address, read))

    def _pinyin(self, word: str, arguments: list):
        """Runs `pa_q` or `pa_txt` from the pinyin table, as the Nextion
        Editor's simulator ran them. `pa_q pinyin,number` sets the number to
        how many candidates the syllable `pinyin` gives has, matched
        exactly, 0 for one the table lacks. `pa_txt pinyin,text,start,count`
        sets the text to `count` candidates, two bytes each, from candidate
        `start`, counted from 0. The text is emptied when they run past the
        last candidate, for a count of 0, and for a syllable the table lacks.
        A start below 0 reads the table's bytes before the syllable's
        candidates, and a count below 0 copies on to the text's limit, or to
        the table's end, as the screen did. The screen also emptied the text
        when `start` and `count` summed to less than 0, and when the read
        would start before the table's first byte. The text holds gb2312
        bytes, whatever the folder's encoding, cut to its limit as any text
        is (_store)."""
        pinyin = self._operand(arguments[0])
        syllable = self._codec.encode_keeping_bytes(str(pinyin), arguments[0])
        place = self.pinyin_table.place(syllable)
        candidates = 0 if place is None else (place[1] - place[0]) // 2
        if word == "pa_q":
            self._store(self._name(arguments[1]), candidates)
            return
        start, count = self._chain(arguments[2]), self._chain(arguments[3])
        data = b""
        first = None if place is None else place[0] + 2 * start
        if first is not None and first >= 0 and count != 0 and 0 <= start + count <= candidates:
            end = first + 2 * count if count > 0 else len(self.pinyin_table.data)
            data = self.pinyin_table.data[first:end]
        self._store(self._name(arguments[1]), self._codec.decode_keeping_bytes(data))

    def _command(self, word: str, arguments: list):
        """Runs the text command `word` (covx, substr, spstr, strlen, or btlen)."""
        if word == "covx":
            source, target, length, form = arguments
            # Its length and form may be arithmetic, as the Editor's simulator
            # ran them; its source may not (the build refuses it).
            form = self._chain(form)
            if form not in _COVX_FORMS:
                raise RefusedCode("only covx's forms 0, 1, and 2 are modelled")
            value = self._operand(source)
            if isinstance(value, str):
                # Text to number: an optional minus, then the leading digits.
                match = re.match(r"-?[0-9]*", value)
                digits = match[0]
                value = int(digits) if digits not in ("", "-") else 0
            else:
                value = _covx_text(value, self._chain(length), form)
                if value is None:
                    self._refused(_INVALID_VARIABLE_OPERATION)
                    return
            self._store(self._name(target), value)
        elif word == "substr":
            source, target, start, count = arguments
            # Number arguments may be arithmetic, as in substr t.txt,s.txt,n.val+1,2.
            start, count = self._chain(start), self._chain(count)
            characters = self._characters(self._operand(source), source)
            self._store(self._name(target), self._text_of(characters[start:start + count]))
        elif word == "spstr":
            # The separator is found byte by byte, inside a two-byte
            # character too, as the Nextion Editor's simulator found it.
            source, target, separator, index = arguments
            parts = self._codec.encode_keeping_bytes(self._operand(source), source).split(
                self._codec.encode_keeping_bytes(self._operand(separator), separator))
            index = self._chain(index)
            self._store(self._name(target), self._text_of([parts[index]])
                        if index < len(parts) else "")
        else:
            # btlen counts the text's bytes in the project's encoding; strlen, like
            # substr, its characters (_characters). The two agree in an encoding
            # of one byte per character.
            source, target = arguments
            text = self._operand(source)
            self.values[self._name(target)] = (len(self._codec.encode_keeping_bytes(text, source))
                                               if word == "btlen"
                                               else len(self._characters(text, source)))

    def _characters(self, text: str, where: str) -> list:
        """Returns the characters of `text` as the screen's text commands
        count them, each as its bytes (zi_font.counted_characters). In a
        two-byte encoding, they may differ from the code page's characters.
        `where` names the text in a refusal of a character the encoding
        cannot store."""
        return counted_characters(self._codec.encode_keeping_bytes(text, where), self._codec.name)

    def _text_of(self, characters: list) -> str:
        """Returns the text of `characters`, each as its bytes."""
        return self._codec.decode_keeping_bytes(b"".join(characters))

    def _text_join(self, name: str, operator: str, chain: str) -> str:
        """Returns the text that `name operator chain` gives `name`, as the screen
        computes it (worked out in the Editor). It differs from a plain join when
        the right side names the target: `t0.txt="a"+t0.txt` gives the old text
        followed by "a".

        With the target first, or with `+=`, the screen keeps the old text.
        It then appends each further piece in turn. A later mention of the
        target appends the text as it is by then.

        With the target later, the screen keeps the old text and appends the
        other pieces. It drops the mention."""
        pieces = self._join_pieces(chain)
        named = [self._name(piece) == name if not piece.startswith('"') else False
                 for piece in pieces]
        if operator == "+=" or (named and named[0]):
            text = self._value(name)
            for piece, is_target in zip(pieces if operator == "+=" else pieces[1:],
                                        named if operator == "+=" else named[1:]):
                text += text if is_target else self._operand(piece)
            return text
        if any(named):
            return self._value(name) + "".join(self._operand(piece)
                                               for piece, is_target in zip(pieces, named)
                                               if not is_target)
        return self._chain(chain)

    def _without_last(self, name: str, count: str) -> str:
        """Returns the text `name` without its last `count` characters, as
        t0.txt-=2 and t0.txt=t0.txt-2 leave it, counted as strlen counts
        them (_characters)."""
        characters = self._characters(self._value(name), name)
        return self._text_of(characters[:-self._chain(count) or None])

    def _join_pieces(self, chain: str) -> list:
        """Returns the operands of a text join such as `a+b+c`, as written."""
        parts = chain_parts(chain)
        if parts is None:
            raise _unreadable_line("not a chain: %r" % chain)
        if any(operator != "+" for operator in parts[1::2]):
            raise _unreadable_line("not a text join: %r" % chain)
        return parts[::2]

    def _chain(self, text: str):
        """Returns the value of `text`, operands joined by operators such as
        `n0.val*2+1`, computed from left to right as the Editor does. A "-"
        right after an operator starts a negative number: the Editor's
        simulator gave -32 for 2*-16, and 21 for 5--16 (code_lines.chain_parts,
        which the build checks a value with too)."""
        parts = chain_parts(text)
        if parts is None:
            raise _unreadable_line("not a chain: %r" % text)
        value = self._operand(parts[0])
        for operator, operand in zip(parts[1::2], parts[2::2]):
            value = c_operation(operator, value, self._operand(operand))
        return value

    def _condition(self, text: str) -> bool:
        """Returns whether a condition such as `n0.val>3&&t0.txt!="a"` holds.
        Each comparison joins two operands, with no arithmetic. The
        comparisons are read from left to right, and reading stops once the
        result is known: at a false one for &&, and a true one for ||. A
        comparison whose operand the running screen refuses to read, such as
        an attribute a component lacks read through b[], counts as true. The
        Nextion Editor's simulator ran it so: it answered the refusal's
        code, which is recorded as a refused line's is (_run_simple)."""
        if "&&" in text and "||" in text:
            raise RefusedCode("the Nextion Editor refuses mixed && and ||: %r" % text)
        every = "&&" in text
        for part in text.split("&&" if every else "||"):
            match = _COMPARISON.match(part)
            if not match:
                raise RefusedCode("the Nextion Editor refuses this condition part: %r" % part)
            try:
                left, right = self._operand(match[1]), self._operand(match[3])
                result = {"==": left == right, "!=": left != right, "<": left < right,
                          ">": left > right, "<=": left <= right, ">=": left >= right}[match[2]]
            except ScreenRefusal as refusal:
                self._record("refusals", (refusal.code, text))
                self._refused(refusal.code)
                result = True
            # A false part decides an &&, and a true one an ||.
            if result != every:
                return result
        return every

    def _store(self, name: str, value, ranged: bool = True):
        """Stores `value` in `name`. A text is cut to its limit ("text
        limits"), a `txt`'s `txt_maxl`, a `path`'s `path_m`, as the screen
        keeps them. A component's number is kept as its description says
        (_kept): cut to its bytes, or, where `ranged`, refused outside its
        range; a `move` of no time does not refuse its end. A data record's
        `val` chooses a record (_choose_record). A select's `val` past its
        last line, or below 0, changes nothing. For a name the screen has,
        refuses, changing nothing, a resource the project lacks
        (_check_resource), and a value of the other kind for a `txt` or a
        `val` (_ATTRIBUTE_KINDS), in a typed instruction as the compile
        does. A name it lacks is an unknown name, which the screen answers
        otherwise. `dims` and `bauds` set `dim` and `baud` too
        (_CURRENT_OF_SAVED). An attribute the screen does not hold (_unheld)
        it refuses, changing nothing: in a typed instruction as an unknown
        name, and in event code as a failed assignment. `crcval` is left as
        it is, and so is an input pin, given a screen that says so."""
        component, _, attribute = name.rpartition(".")
        if name == "crcval":
            # The CRC commands set it (_crc_command). The Nextion Editor's
            # simulator answered code setting it with success, and kept the CRC.
            return
        if name in PIN_NAMES and self.screen is not None and not self.screen.takes_pin_write(name):
            # An input pin: its level comes from outside the screen (gpio_pins.py).
            return
        if self._unheld(name):
            # The screen does not hold it: a typed line meets an invalid
            # variable, and event code a failed assignment, changing nothing.
            if self._levels == 0:
                raise KeyError(name)
            raise ScreenRefusal(_FAILED_ASSIGNMENT, "the screen does not hold %s" % name)
        if name == "addr" and value != 0 and value not in ADDRESSES:
            # As the Nextion Editor's simulator answered addr=100 and addr=3000.
            raise ScreenRefusal(_FAILED_ASSIGNMENT, "addr takes 0, or %d to %d, not %r"
                                % (ADDRESSES[0], ADDRESSES[-1], value))
        # A name the screen has: the values', or the page file's beneath a test's.
        if name in self._layered():
            wanted = _ATTRIBUTE_KINDS.get(attribute)
            if wanted is not None and not isinstance(value, wanted):
                refusal = CompileRefusal if self._levels == 0 else ScreenRefusal
                raise refusal(_FAILED_ASSIGNMENT, "%s takes a %s, not %r"
                              % (name, "text" if wanted is str else "number", value))
            if (attribute == "val" and isinstance(value, int) and value < 0
                    and self._type_of(component) == TYPES_BY_NAME["file-stream"]):
                # A file stream's position: the Nextion Editor's simulator
                # refused one below 0, and kept its own.
                raise ScreenRefusal(_FAILED_ASSIGNMENT, "%s is a position, from 0" % name)
            object_type = self._type_of(component)
            described = _kept_by(object_type, attribute)
            if described is not None and isinstance(value, int):
                value = self._kept(name, described, value, ranged)
            kind = reference_kind(object_type, attribute)
            # A number the screen cuts to its bytes names nothing it checks.
            if kind in _CHECKED_RESOURCES and (described is None or described.code_wraps is None):
                self._check_resource(kind, value, _FAILED_ASSIGNMENT)
        limit = self.text_limits.get(name)
        if isinstance(value, str) and limit is not None:
            # The screen keeps a text as its bytes, at most its limit, as a
            # simulation gives every `txt`. Read back from them, a text with
            # a limit, joined from pieces that split a character, compares
            # equal to one of the same bytes.
            data = self._codec.encode_keeping_bytes(value, name)
            value = self._codec.decode_keeping_bytes(data[:limit])
        if name.endswith(".val") and _is_data_record(name[:-len(".val")], self._layered()):
            if not self._choose_record(name[:-len(".val")], value):
                return
        if (attribute == "val" and self._type_of(component) == TYPES_BY_NAME["select"]
                and not (isinstance(value, int) and
                         0 <= value < len(path_lines(self._layered().get(component + ".path",
                                                                         ""))))):
            # Past the select's last line, or below 0: the Nextion Editor's
            # simulator kept its `val` and `txt`, and answered nothing.
            return
        # What the name held, the page file's beneath a test's own, which the
        # screen needs to draw where a component was.
        before = self._layered().get(name)
        self.values[name] = value
        if attribute == "path" and _is_data_record(component, self._layered()):
            self._open_named_file(component)
        if name in GPIO_VARIABLES:
            self._record("gpio", ("write", name, value))
        current = _CURRENT_OF_SAVED.get(name)
        if current is not None:
            self._store(current, value)
        if name == "recmod" and not value:
            # The end of protocol reparse mode empties its buffer.
            self.values["serial buffer"] = b""
        if self.screen is not None:
            self.screen.stored(name, value, self, before)
        self._work(component, attribute)

    @staticmethod
    def _kept(name: str, described, value: int, ranged: bool) -> int:
        """What the screen keeps of `value` stored in `name`, as `described`
        says (AttributeDescription.kept): cut to its bytes, or, where
        `ranged`, refused outside its range, answering 0x1C and changing
        nothing."""
        kept = described.kept(value)
        if kept is None and ranged:
            raise ScreenRefusal(_FAILED_ASSIGNMENT, "%s takes %d to %d"
                                % ((name,) + described.code_range))
        return value if kept is None else kept

    def _work(self, component: str, attribute: str):
        """Works the page's list component `component` after code set its
        `attribute`, as the simulator does, when the machine has the
        folder's resources (list_working.py): last, after `screen.stored`,
        as the simulation worked it there before. A data record's new
        `format`, `hig`, `gdw`, or `gdh` works out its `qty`, `txt`, and
        both `maxval`s again, from its file, unless it is shut out of it.
        What follows is written to the values directly, not stored, so that
        it is not worked again. Another page's component, named with its
        page, is not worked, as the simulation worked none."""
        if self.list_working is None or not component or "." in component:
            return
        kind = TYPE_NAMES.get(self._type_of(component))
        if kind == "data-record" and attribute in _TABLE_ATTRIBUTES:
            self.values.update({"%s.%s" % (component, key): value for key, value in
                                data_record_values(component, self._layered(),
                                                   self._readable_data_file(component),
                                                   self._codec).items()})
        elif self.list_working.works(kind, attribute):
            self.list_working.stored(self.page, component, kind, attribute, self._layered(),
                                     self.values)

    def open_page(self):
        """Works the page's list components as the page opens, as the
        simulator works them, when the machine has the folder's resources:
        a browser lists its folder, a sliding text works out how far it
        scrolls, a combo box keeps its `val` as its last within its items
        (list_working.py), and a data record opens its file
        (open_data_record). Each in ID order, as `components` names them.
        A test runs it before its events."""
        if self.list_working is None or not self.components:
            return
        layered = self._layered()
        for name in self.components[1:]:
            kind = TYPE_NAMES.get(self._type_of(name))
            if kind == "data-record":
                open_data_record(name, layered, self.values, self.cards, self._holder(name),
                                 self._codec)
            self.list_working.opened(self.page, name, kind, layered, self.values)

    def _operand(self, text: str):
        """Returns the value of a number, a quoted text, or a name. An
        attribute the screen does not hold (_unheld) reads 0 in event code,
        and is an unknown name in a typed instruction."""
        if re.fullmatch(NUMBER, text):
            if "x" not in text.lower():
                return int(text)
            # The Editor wants hex digits in pairs, a byte each (the vendor's
            # rule 1.8). Compiled and run in the Editor: a constant is its 32
            # bits, so 0xFFFFFFFF is -1; one past 32 bits, or with a sign, is
            # refused. A "-" that subtracts is an operator, not part of this.
            # Its simulator read 0X10 as 0x10.
            digits = text.lower().split("x", 1)[1]
            if len(digits) % 2:
                raise RefusedCode(
                    "%s: the Nextion Editor wants hex digits in pairs, a byte each" % text)
            if text.startswith("-"):
                raise RefusedCode("%s: the Nextion Editor refuses a sign on a hex constant"
                                  % text)
            value = int(digits, 16)
            if value > 0xFFFFFFFF:
                raise RefusedCode(
                    "%s: the Nextion Editor refuses a hex constant past 32 bits" % text)
            return int32(value)
        if text.startswith('"'):
            return re.sub(r"\\(.)", _escaped, text[1:-1])
        name = self._name(text)
        if self._unheld(name):
            # The screen does not hold it: a typed line meets an invalid
            # variable, and event code reads 0, whatever the page file says.
            if self._levels == 0:
                raise KeyError(name)
            return 0
        if name in EDITOR_COLOURS and name not in self.values:
            return EDITOR_COLOURS[name]
        if name == "rand" and self.screen is not None:
            return self.screen.random(*self.values.get("rand range", (0, 2 ** 31 - 1)))
        if name == "usize" or BUFFER_BYTE.fullmatch(name):
            return self._buffer_read(name)
        value = self._value(name)
        if name in GPIO_VARIABLES:
            self._record("gpio", ("read", name, value))
        return value

    def _value(self, name: str):
        """Returns the value of `name`, as code reads it. Raises
        ValueNotGiven when it has none."""
        try:
            return self.values[name]
        except KeyError:
            raise ValueNotGiven(name) from None

    def _unheld(self, name: str) -> bool:
        """Returns whether `name` is an attribute the screen does not hold,
        though code may name it (editor_limits.screen_holds), by the
        screen's series and its component's `type`; never without a series,
        as in a test run."""
        if self.series is None:
            return False
        component, _, attribute = name.rpartition(".")
        type_name = TYPE_NAMES.get(self._type_of(component))
        return type_name is not None and not screen_holds(type_name, attribute, self.series)

    def _name(self, text: str) -> str:
        """Returns the key in `values` of a name as the code writes it. On page
        main, `main.t0.txt` gives "t0.txt". Each index is computed: `va[n0.val]`
        gives "va[2]" when n0.val is 2. Raises ScreenRefusal for an attribute
        a component of the page lacks, reached through the screen's arrays."""
        if self.own_page:
            text = self.own_page.sub("", text)
        name = re.sub(r"\[([^\]]*)\]", lambda match: "[%d]" % self._chain(match[1]), text)
        if self.screen is not None and "]." in name:
            # The screen's arrays: a page by its index, a component by its ID.
            resolved = self.screen.by_index(name, self)
            reached = resolved or name
            component, _, attribute = reached.rpartition(".")
            # An attribute a component the page has lacks, or that the
            # screen does not hold, which the build cannot check here: the
            # screen answers an invalid variable, and the event goes on.
            if component + ".type" in self.values and (reached not in self.values
                                                       or self._unheld(reached)):
                raise ScreenRefusal(_INVALID_VARIABLE, "%s has no %s" % (component, attribute))
            # Of another page, only the components of global scope are held.
            # For one that is not, and for the page itself, the Editor's
            # simulator answered an invalid variable too.
            if (resolved is not None and "." in component
                    and component + ".type" not in self.values):
                raise ScreenRefusal(_INVALID_VARIABLE, "%s is on another page and not of "
                                                       "global scope" % component)
            return reached
        return name


def _escaped(match) -> str:
    """Returns what the escape `match` (a backslash, then its character)
    stands for in a quoted text, as the screen stores it (SCREEN_ESCAPES)."""
    if match[1] not in SCREEN_ESCAPES:
        # The Editor's compile refused `\q` ("Improper use of escape
        # characters"), and its simulator answered `\q`, `\n`, and `\t` typed
        # 0x20; the others it lacks are taken to be refused alike.
        raise CompileRefusal(_INVALID_ESCAPE, "the escape \\%s is not one the screen reads"
                             % match[1])
    return SCREEN_ESCAPES[match[1]]


@functools.lru_cache(maxsize=2048)
def _parsed(lines: tuple, places: tuple) -> tuple:
    """Returns the ops of `lines` of Editor code (_flattened), `places` giving
    the place of each line (or None). Comments and blank lines are skipped.
    Braces must balance.

    Tests run the same events many times, so the parsed form of each is kept,
    for the lines run most recently. It is built of tuples, so running it
    cannot change it."""
    kept = [(split_line(line, 0)[1], place)
            for line, place in zip(lines, places or [None] * len(lines))]
    kept = [(code, place) for code, place in kept if code]
    code = [line for line, _ in kept] + ["}"]
    statements, end = _block(code, [place for _, place in kept] + [None], 0)
    if end != len(code) - 1:
        raise _unreadable_line("unbalanced braces")
    return _flattened(statements)


def _flattened(statements: tuple) -> tuple:
    """Returns an event's statements (_block) as lines with jumps, as the
    screen runs them: a tuple of ops, which _execute runs from the first.
    An op is a tuple, its first item what it does:
      - ("line", code, place): runs a line of code.
      - ("test", condition, otherwise, place): goes on to the next op when
        `condition` holds, else to the op `otherwise`, as an if's branch or a
        loop's condition does.
      - ("jump", to): goes on at the op `to`, as an if's branch does past
        the branches after it.
      - ("enter", loop, start, place): a while or for loop entered by its
        line: its count of turns from 0, then its start.
      - ("turn", loop, step, test, place): the end of a loop's block: its
        step, a turn counted, then its test again.
      - ("goto", label, place): goes on at the op after the label.
      - ("return", place): ends the event.
    A label is no op. A loop's places record a step as its line ran before:
    as it is entered, and before each turn's test but the first. Raises
    RefusedCode for a goto whose label the event lacks, and for a label
    twice in one event, whatever block it is in, as the Editor refused them
    as it compiled ("nofind mark", "repeated mark")."""
    ops, labels, gotos = [], {}, []
    loops = itertools.count()

    def add(statements: tuple):
        for statement in statements:
            if statement[0] == "simple":
                _, code, place = statement
                label = LABEL.fullmatch(code)
                if label:
                    if label[1] in labels:
                        raise _placed(RefusedCode("the label %s twice" % label[1]), place)
                    labels[label[1]] = len(ops)
                elif goto_label(code) is not None:
                    gotos.append(len(ops))
                    ops.append(("goto", goto_label(code), place))
                elif code == "return":
                    ops.append(("return", place))
                else:
                    ops.append(("line", code, place))
            elif statement[0] == "if":
                past = []
                for condition, body, place in statement[1]:
                    test = len(ops)
                    ops.append(None)
                    add(body)
                    past.append(len(ops))
                    ops.append(None)
                    ops[test] = ("test", condition, len(ops), place)
                add(statement[2])
                for jump in past:
                    ops[jump] = ("jump", len(ops))
            else:
                _, start, condition, step, body, place = statement
                loop = next(loops)
                ops.append(("enter", loop, start, place))
                test = len(ops)
                ops.append(None)
                add(body)
                ops.append(("turn", loop, step, test, place))
                # The first turn's test records no step: entering the loop did.
                ops[test] = ("test", condition, len(ops), None)

    add(statements)
    for index in gotos:
        _, name, place = ops[index]
        if name not in labels:
            raise _placed(RefusedCode("no label %s in this event" % name), place)
        ops[index] = ("goto", labels[name], place)
    return tuple(ops)


def _block(lines: list, places: list, position: int) -> tuple:
    """Returns the statements of `lines` from `position` up to the `}` that
    closes them, and that `}`'s position. A statement is ("simple", line,
    place), ("if", ((condition, body, place), ...), else body), or ("for",
    start, condition, step, body, place). A while loop is a for loop with no
    start or step. A place is the line's, from `places`, for the recorder."""
    statements = []
    while not lines[position].startswith("}"):
        line, place = lines[position], places[position]
        if line.startswith("if("):
            branches, else_body = [], ()
            # The line heading the branch read: the if, then each else if.
            condition, head = line[3:-1], line
            while True:
                if lines[position + 1] != "{":
                    raise _placed(_unreadable_line(head), place)
                body, end = _block(lines, places, position + 2)
                branches.append((condition, body, place))
                position = end
                close, place = lines[position], places[position]
                if close.startswith("}else if("):
                    condition, head = close[9:-1], close
                    continue
                if close == "}else":
                    if lines[position + 1] != "{":
                        raise _placed(_unreadable_line(close), place)
                    else_body, position = _block(lines, places, position + 2)
                    if lines[position] != "}":
                        raise _placed(_unreadable_line(close), place)
                elif close != "}":
                    raise _placed(_unreadable_line(close), place)
                break
            statements.append(("if", tuple(branches), else_body))
        elif line.startswith("while(") or line.startswith("for("):
            if lines[position + 1] != "{":
                raise _placed(_unreadable_line(line), place)
            body, position = _block(lines, places, position + 2)
            if lines[position] != "}":
                raise _placed(_unreadable_line(line), place)
            if line.startswith("while("):
                statements.append(("for", "", line[6:-1], "", body, place))
            else:
                start, condition, step = line[4:-1].split(";")
                statements.append(("for", start, condition, step, body, place))
        else:
            statements.append(("simple", line, place))
        position += 1
    return tuple(statements), position


@functools.cache
def _kept_by(object_type, attribute: str):
    """The description saying what a component of `object_type`, a type
    number, keeps of a number stored in `attribute`; None for the page, whose
    own attributes keep any number, and for a type not known. Read once for
    each, as every store asks."""
    type_name = TYPE_NAMES.get(object_type)
    if type_name is None or type_name == "page":
        return None
    return describe(type_name, attribute)


def _is_data_record(component: str, values: dict) -> bool:
    """Whether `component` is a data record: the one type with an `insert`,
    its method's place."""
    return component + ".insert" in values


# covx's forms of a number as text: 0 decimal, 1 with commas between
# thousands, 2 hexadecimal.
_COVX_FORMS = (0, 1, 2)
# The most characters covx writes, a minus sign aside, in decimal and with
# commas, and in hexadecimal, whatever length code asks for, as the Nextion
# Editor's simulator stopped them.
_COVX_MOST_DIGITS, _COVX_MOST_HEX_DIGITS = 15, 8


def _covx_text(value: int, length: int, form: int):
    """Returns the text covx makes of the number `value` in its form `form`;
    None where the screen leaves the text as it was. A length other than 0
    keeps that many characters from the left, or pads with zeros on the
    left up to it.
      - Decimal and with commas: a minus sign goes in front, beyond the
        length. With commas, the length counts the commas, and padding adds
        zeros, not commas: 1234567 at 4 is "1,23", and 5 at 4 "0005". A
        length past 15 counts as 15 (_COVX_MOST_DIGITS).
      - Hexadecimal: the number's 32 bits, in capitals, in whole bytes at
        least: 5 is "05", and -1 "FFFFFFFF". An odd length, not a whole
        number of bytes, fails: the screen answers 0x1B. An even length
        past 8 counts as 8, the 32 bits' digits."""
    if form == 2:
        if length % 2:
            return None
        length = min(length, _COVX_MOST_HEX_DIGITS)
        digits = "%X" % (value & 0xFFFFFFFF)
        digits = digits.rjust(len(digits) + len(digits) % 2, "0")
        return digits[:length].rjust(length, "0") if length else digits
    digits = "{:,}".format(abs(value)) if form == 1 else str(abs(value))
    if length:
        length = min(length, _COVX_MOST_DIGITS)
        digits = digits[:length].rjust(length, "0")
    return ("-" if value < 0 else "") + digits


def _rdfile_crc(kind: int, data: bytes) -> bytes:
    """Returns the check rdfile sends after `data`, low byte first: none for
    `kind` 0, the Modbus CRC16 for 1 (modbus_crc.py), and the screen's CRC32
    for 10, each byte a 32-bit word of its own (stamp.word_crc). Another
    kind sends zero bytes in their place: 2 for a kind below 10, else 4, as
    for 2, 3, 11, and -1."""
    if kind == 0:
        return b""
    if kind == 1:
        return crc_after(crc_start(0xFFFF), data).to_bytes(2, "little")
    if kind == 10:
        return word_crc(CRC_START, data).to_bytes(4, "little")
    return bytes(2 if 0 <= kind < 10 else 4)


def _arguments(text: str) -> list:
    """Returns a command's arguments, split at commas outside strings."""
    return [part for part in re.findall(r'"(?:\\.|[^"\\])*"|[^,]+', text)]
