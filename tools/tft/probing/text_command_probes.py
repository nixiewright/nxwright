"""The probes of the text commands (instructions/text_commands.py): lines
of them added to the T base folder, in strict Nextion syntax, each compared
with the blocks the Nextion Editor wrote, through the statement probes' own
ways of cutting them (statement_probes.py). Run them with
`tools.tft.probe run text_command_probes`.

The probes in page0's Touch Release event put two texts on page0, t0 and
t1, whose txt the lines use. Three of them add components whose val the
lines use: numbers, a variable of a number, a button, a progress bar, a
checkbox, a radio, a slider, an xfloat, a dual-state button, and a gauge.
Two add a picture, a crop, a waveform, and a timer, whose pic, picc, id,
tim, and en the lines use, and one adds a touch capture, whose val they
use. Most keep fixtures: the event's blocks, back to back with their size
words.
"""

from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.checkbox_probes import checkbox_component
from tools.tft.probing.crop_probes import crop_component
from tools.tft.probing.dual_state_button_probes import dual_state_button_component
from tools.tft.probing.gauge_probes import gauge_component
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.picture_probes import picture_component, with_pictures_and_code
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.progress_bar_probes import progress_bar_component
from tools.tft.probing.radio_probes import radio_component
from tools.tft.probing.slider_probes import slider_component
from tools.tft.probing.statement_probes import (ProgramChange, ours_in_event, ours_in_program,
                                            program_lines, theirs_in_event, theirs_in_program,
                                            touch_release_code)
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.touch_capture_probes import touch_capture_component
from tools.tft.probing.variable_probes import variable_component
from tools.tft.probing.waveform_probes import waveform_component
from tools.tft.probing.xfloat_probes import xfloat_component

FIXTURES = "text-commands"


# The texts t0 and t1, whose txt every probe in an event uses.
_TEXTS = [text_component("t0", txt="12"), text_component("t1", y=60, txt="ab")]


def _with_other_attributes(lines: list):
    """Returns a change that gives page0's Touch Release event `lines`, and
    puts on page0 the texts t0 and t1, the picture p0, the crop q0, the
    waveform s0, and the timer tm0, in a project of the two pictures they
    show. A unit test reads what it adds, to make the same page in memory
    (picture_probes.StrictPicturesChange)."""
    return with_pictures_and_code(
        [("red", (8, 4), (255, 0, 0)), ("bg", (320, 480), (0, 0, 255))], lines,
        *_TEXTS, picture_component(x=160, y=10, pic="red"),
        crop_component(x=160, y=60, w=50, h=30, picc="bg"),
        waveform_component(y=150, h=100), timer_component())


def _with_texts(lines: list, declarations: list = ()):
    """Returns a change that gives page0's Touch Release event `lines`, adds
    `declarations` to program.s, and puts the texts t0 and t1 on page0. A
    unit test reads what it adds, to make the same page in memory
    (ProgramChange)."""
    return ProgramChange(declarations=tuple(declarations), components=tuple(_TEXTS),
                         code=touch_release_code(lines))


PROBES = [
    # Each command, from one text to another or to a variable.
    Probe("text-commands-each", "T", _with_texts([
        "covx t0.txt,sys0,0,0", "covx sys0,t1.txt,0,0", "cov t0.txt,sys0,0",
        "strlen t1.txt,sys1", "btlen t1.txt,sys2", "substr t1.txt,t0.txt,0,1",
        'spstr t1.txt,t0.txt,",",1']),
        ours_in_event, theirs_in_event, FIXTURES),
    # Each kind of operand in each place: numbers, long and negative ones,
    # texts with a comma, int variables, system variables, a colour, and
    # texts' txt; kinds the Nextion Editor does not check, as a number for a
    # text; and a space after each comma.
    Probe("text-commands-operands", "T", _with_texts([
        "covx sys0,sys1,0,0", "covx t0.txt,t1.txt,0,0", 'covx "12",a,0,0', "covx 123,t0.txt,0,0",
        "covx -5,t0.txt,3,1", "covx 1000,t0.txt,sys1,sys2", "covx RED,t0.txt,-1,0",
        'strlen "abc",sys0', "strlen sys0,sys1", "strlen t1.txt,dim", "strlen t1.txt,5",
        'btlen "abc",a', 'substr "hello",t0.txt,1,2', "substr t1.txt,sys0,0,1",
        "substr t1.txt,t0.txt,sys0,sys1", 'spstr "a,b",t0.txt,",",0',
        "spstr t1.txt,t0.txt,sys0,0", "spstr t1.txt,t0.txt,t0.txt,0", "cov 123,t0.txt,0",
        "covx t0.txt, sys0, 0, 0"], ["int a=1"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # The commands in program.s, before its page 0, without a text's txt.
    Probe("text-commands-in-program", "T", program_lines([
        "covx sys0,sys1,0,0", 'covx "12",sys0,0,0', "cov 5,sys1,0", 'strlen "abc",sys0',
        'btlen "abc",sys1', 'substr "hello",sys2,1,2', 'spstr "a,b",sys0,",",1']),
        ours_in_program, theirs_in_program),
    # Components' vals: a number's into a txt and back, as a length and a
    # form, and as substr's and spstr's numbers, and the vals of a variable
    # of a number, a button, and a progress bar.
    Probe("text-commands-vals", "T", with_attributes([
        "covx n0.val,t0.txt,0,0", "covx t0.txt,n0.val,0,0", "cov n0.val,t0.txt,0",
        "cov t1.txt,n1.val,0", "covx n0.val,t0.txt,n1.val,n1.val", "cov n0.val,t0.txt,n1.val",
        "covx va0.val,t1.txt,0,1", "covx b0.val,t0.txt,0,0", "covx t1.txt,j0.val,0,0",
        "strlen t0.txt,n0.val", "btlen t1.txt,va0.val", "substr t0.txt,t1.txt,n0.val,n1.val",
        'spstr t0.txt,t1.txt,",",n0.val', "strlen n0.val,sys0", "covx n0.val, t0.txt, 0, 0"],
        _TEXTS + [number_component(x=160), number_component("n1", x=160, y=60),
                  variable_component(), button_component(y=110),
                  progress_bar_component(y=170)]),
        ours_in_event, theirs_in_event, FIXTURES),
    # The vals of the other types that give code a val, as an operand and as
    # numbers: a checkbox, a radio, a slider, an xfloat, and a dual-state
    # button.
    Probe("text-commands-vals-of-more-types", "T", with_attributes([
        "covx c0.val,t0.txt,0,0", "covx r0.val,t1.txt,0,0", "covx h0.val,t0.txt,0,0",
        "covx x0.val,t0.txt,0,0", "covx bt0.val,t1.txt,0,0", "covx t0.txt,h0.val,0,0",
        "cov h0.val,t0.txt,x0.val", "substr t0.txt,t1.txt,c0.val,r0.val"],
        _TEXTS + [checkbox_component(x=160), radio_component(x=200),
                  slider_component(y=110), xfloat_component(y=150),
                  dual_state_button_component(y=200)]),
        ours_in_event, theirs_in_event, FIXTURES),
    # A gauge's val, in a probe of its own.
    Probe("text-commands-gauge-val", "T", with_attributes(
        ["covx z0.val,t0.txt,0,0", "covx t0.txt,z0.val,0,0"],
        _TEXTS + [gauge_component(x=160, y=60)]),
        ours_in_event, theirs_in_event),
    # A timer's tim and en, a picture's pic, a crop's picc, and a waveform's
    # id, as each command's source, as spstr's separator, and where a number
    # goes.
    Probe("text-commands-other-attributes", "T", _with_other_attributes([
        "covx tm0.tim,t0.txt,0,0", "covx tm0.en,t0.txt,0,0", "covx p0.pic,t0.txt,0,0",
        "covx q0.picc,t1.txt,0,0", "covx s0.id,t1.txt,0,0", "cov tm0.tim,t0.txt,0",
        "cov p0.pic,t1.txt,0", "strlen tm0.tim,sys0", "covx sys0,t0.txt,tm0.tim,tm0.en",
        "cov sys0,t0.txt,p0.pic", "substr t0.txt,t1.txt,q0.picc,tm0.tim",
        'spstr t0.txt,t1.txt,",",p0.pic', "substr t0.txt,t1.txt,s0.id,1",
        "btlen tm0.en,sys1", "substr q0.picc,t0.txt,0,1", 'spstr s0.id,t0.txt,",",0',
        "spstr t0.txt,t1.txt,tm0.tim,0", "covx tm0.tim, t0.txt, 0, 0"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # The same attributes as each command's destination, a waveform's id
    # among them, which an assignment may not set.
    Probe("text-commands-other-attributes-as-destinations", "T", _with_other_attributes([
        "covx t0.txt,tm0.tim,0,0", "covx t0.txt,tm0.en,0,0", "covx t0.txt,p0.pic,0,0",
        "covx t1.txt,q0.picc,0,0", "cov t0.txt,tm0.tim,0", "strlen t0.txt,tm0.tim",
        "btlen t1.txt,p0.pic", "strlen t0.txt,q0.picc", "btlen t0.txt,tm0.en",
        "strlen t0.txt,s0.id", "covx t0.txt,s0.id,0,0", "substr t0.txt,p0.pic,0,1",
        'spstr t0.txt,tm0.en,",",0', "substr t1.txt,s0.id,0,1"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # A touch capture's val, as a source, as a destination, which an
    # assignment may not set, and where a number goes.
    Probe("text-commands-touch-capture-val", "T", with_attributes([
        "covx tc0.val,t0.txt,0,0", "cov tc0.val,t1.txt,0", "strlen t0.txt,tc0.val",
        "covx t0.txt,tc0.val,0,0", "covx sys0,t0.txt,tc0.val,0",
        "substr t0.txt,t1.txt,tc0.val,1"],
        _TEXTS + [touch_capture_component(val=5)]),
        ours_in_event, theirs_in_event, FIXTURES),
]
