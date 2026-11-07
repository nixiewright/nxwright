"""The F series' probes: T's probes on the F base folder (probes/F),
NX4832F035 at 0 degrees. First, of pages alone: packaging's probes; the
whole compile's of pages, int variables, code, and resources; the frame's;
the probes of program.s's statements, and of statements in a page's
events; a page of swipes; `page` by number, name, and variable;
hexadecimal numbers in program.s; and F's own of the system variables it
has and T has not. Then the probes of each component type matched on F,
and F's own probes of the other attributes of every type, read and set;
then the page's probes of its bco, sta, and pic; then the probes of if,
while, and for, labels and goto, macros, references through the screen's
arrays, and texts past ASCII; then the families of commands, with F's own
probes of the commands F has and T has not; then the probes of encodings
other than iso-8859-1; then the probes of the attributes every object
has, a component's global vscope among them; then the probes of
components that overlap, and of keys; then seven of the probes above on
F's other models and at its other rotations; then the rotation probes, of
a text, of pictures, and of a component of each drawn type, at F's other
rotations. Each compares the whole file, part by part, as a series' probes
do. Run them with `tools.tft.probe run f_probes`.

F writes every part as T does, but for header 2, whose every word is
scrambled (tft_file.py), its firmware files, its fonts, which it writes
at 0 degrees at any rotation (packaging.py), doevents (frame.py), the
numbers of 40 commands of T's (instructions/, and the copies of some in
component_types/), and of 8 commands it has and T has not, and the numbers
of 16 system variables and two colours, beside the 14 system variables it
has and T has not (statements.py) (ResearchNotes/tft/f-series.md). Packaging's
probe and the whole compile of a blank project keep fixtures, made on
zeros for the firmware. F's own probes of the system variables and commands
T has not keep their blocks. The other probes keep none: T's fixtures and
the comparisons in test_series_followers.py guard their user code, allowing
the differences in series_differences.py."""
from dataclasses import replace

from tools.tft.probing import (button_border_and_picture_probes, button_probes, checkbox_probes,
                           code_form_probes, command_operand_probes, compile_probes,
                           condition_probes, crc_command_probes, crop_probes,
                           device_and_buffer_command_probes, drawing_probes,
                           dual_state_button_probes, encoding_probes, for_probes, frame_probes,
                           gauge_probes, goto_probes, hex_number_probes, hotspot_probes, if_probes,
                           indirect_probes, key_probes, macro_probes,
                           number_border_and_picture_probes, number_probes, other_attribute_probes,
                           overlap_probes, packaging_probes, page_command_probes, page_probes,
                           picture_probes, pinyin_probes, progress_bar_probes, qr_code_probes,
                           radio_probes, rotation_probes, screen_command_probes,
                           scrolling_text_probes, serial_command_probes, shared_attribute_probes,
                           slider_probes, statement_probes, text_border_and_picture_probes,
                           text_character_probes, text_command_probes, text_condition_probes,
                           text_probes, text_room_probes, timer_probes, touch_capture_probes,
                           undocumented_command_probes, variable_probes, waveform_command_probes,
                           waveform_probes, while_probes, xfloat_probes)
from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.component_probes import editor_file, whole_file
from tools.tft.probing.model_probes import moved
from tools.tft.probing.probe_runner import Probe
from nxwright.tft.statements import SYSTEM_VARIABLES

FIXTURES = "f"


def _packaged_on_f(probe: Probe) -> Probe:
    """Returns packaging's `probe` on the F base folder, its fixtures, if
    any, kept in F's folder. It still borrows the Nextion Editor's user
    code, so that it shows packaging alone."""
    return replace(probe, name="f-" + probe.name, base="F",
                   fixtures=FIXTURES if probe.fixtures else None)


def _on_f(probe: Probe) -> Probe:
    """Returns `probe` on the F base folder, compared as a whole file. The
    blank project's probe and the probe of F's own system variables keep
    fixtures; the other probes use T's fixtures and the follower test."""
    fixtures = probe.name in _KEEPING
    kept = (probe.kept or probe.ours) if fixtures else None
    return replace(probe, name="f-" + probe.name, base="F", ours=whole_file, theirs=editor_file,
                   fixtures=FIXTURES if fixtures else None, kept=kept)


def _named(module, *names: str) -> list:
    """Returns the probes of `module` named `names`, in that order."""
    probes = {probe.name: probe for probe in module.PROBES}
    return [probes[name] for name in names]


# The blank project and F's own system variables keep fixtures through _on_f.
_KEEPING = {"compile-T-blank", "statements-own-system-variables"}

PROBES = [_packaged_on_f(probe) for probe in packaging_probes.PROBES] + [
    _on_f(probe) for probe in (
        _named(compile_probes, "compile-T-blank", "compile-T-pages-ints-code",
               "compile-T-resources-and-pages", "compile-T-the-most-pages",
               "compile-T-eight-hundred-ints", "compile-T-forty-pictures-and-eight-fonts")
        + frame_probes.PROBES
        # The statements' probes but the one with components.
        + [probe for probe in statement_probes.PROBES
           if probe.name != "statements-compound-assignments-in-an-event"]
        + _named(page_probes, "page-of-swipes")
        + _named(page_command_probes, "page-by-number", "page-by-name", "page-of-ten",
                 "page-past-the-last", "page-by-variable", "page-in-program-s")
        + _named(hex_number_probes, "hex-numbers-in-program"))]

# F's own system variables, which T has not, each read into sys0 and set
# from it in program.s, as k_probes.py's probe of K's own. It keeps
# fixtures, as it shows F's own numbers.
_OWN_VARIABLES = sorted(set(SYSTEM_VARIABLES["F"]) - set(SYSTEM_VARIABLES["T"]))
PROBES.append(_on_f(Probe(
    "statements-own-system-variables", "F", statement_probes.program_lines(
        ["sys0=%s" % name for name in _OWN_VARIABLES]
        + ["%s=sys0" % name for name in _OWN_VARIABLES]),
    statement_probes.ours_in_program, statement_probes.theirs_in_program)))

# The component probes run on F without copying T's fixtures.
PROBES += [_on_f(probe)
           for module in (text_probes, text_border_and_picture_probes, number_probes,
                          number_border_and_picture_probes, button_probes,
                          button_border_and_picture_probes, checkbox_probes, radio_probes,
                          dual_state_button_probes, progress_bar_probes, xfloat_probes,
                          qr_code_probes, slider_probes, gauge_probes, picture_probes,
                          crop_probes, hotspot_probes, timer_probes, variable_probes,
                          touch_capture_probes, scrolling_text_probes, waveform_probes,
                          text_room_probes)
           for probe in module.PROBES]


def _plain_code(name: str, lines: list, components: list) -> Probe:
    """Returns F's own probe `name`: `components` on page0, and `lines` in
    its Touch Release event, compared as a whole file."""
    return Probe("f-" + name, "F", with_attributes(lines, components), whole_file, editor_file)


# The other attributes of every type, as other_attribute_probes.py's probes
# on T show them: one component of each type, where it is on T but the
# xfloat, which overlaps the gauge there; every attribute each writes read
# into sys0; and every one code can change on F set, then some added to,
# cut, stepped, and set from others. Then those of a picture, a crop, a QR
# code with a logo, and a waveform of 4 channels, read, as on T.
_ONE_OF_EACH = [
    text_probes.text_component(), number_probes.number_component(y=50),
    button_probes.button_component(y=90), checkbox_probes.checkbox_component(y=150),
    radio_probes.radio_component(y=180),
    dual_state_button_probes.dual_state_button_component(y=210),
    gauge_probes.gauge_component(x=150, y=10), hotspot_probes.hotspot_component(x=150, y=120),
    progress_bar_probes.progress_bar_component(x=150, y=180),
    qr_code_probes.qr_code_component(x=150, y=220),
    scrolling_text_probes.scrolling_text_component(y=330), slider_probes.slider_component(y=370),
    timer_probes.timer_component(), variable_probes.variable_component(),
    variable_probes.text_variable_component("va1"),
    waveform_probes.waveform_component(x=10, y=400, h=60),
    xfloat_probes.xfloat_component(x=220, y=410), touch_capture_probes.touch_capture_component()]
PROBES += [
    _plain_code("other-attributes-read",
                other_attribute_probes.reads(other_attribute_probes.ATTRIBUTES), _ONE_OF_EACH),
    _plain_code("other-attributes-set",
                other_attribute_probes.sets(other_attribute_probes.ATTRIBUTES, "F") + [
                    "t0.bco+=1", "t0.pco-=n0.font", "b0.bco2++", "h0.maxval--",
                    "n0.lenth=t0.bco*2+n0.font", "g0.vvs2=g0.vvs3",
                    "va0.val=va1.txt_maxl+va1.sta"], _ONE_OF_EACH)] + [
    _on_f(probe) for probe in _named(other_attribute_probes,
                                     "other-attributes-read-of-pictures-and-variants")]

# The page's bco, sta, and pic, but not the page of swipes already listed.
PROBES += [_on_f(probe) for probe in page_probes.PROBES if probe.name != "page-of-swipes"]

# The probes of if, while, and for, of their conditions, labels and goto,
# and macros, call, and return, on F, and the probes of references through
# the screen's arrays and of txts past ASCII, but the one of K's commands of
# the EEPROM and the GPIO pins, among them wept and rept, which F lacks (its
# lines without those run below). F writes them as T does, allowing for
# the command numbers in series_differences.py.
PROBES += [_on_f(probe) for module in (if_probes, while_probes, for_probes, condition_probes,
                                       text_condition_probes, goto_probes, macro_probes,
                                       indirect_probes, text_character_probes)
           for probe in module.PROBES if probe.name != "indirect-in-eeprom-commands"]

# The families of commands on F, followed by their operand probes and the
# probes of attributes in commands. K-only wept and rept are left out.
_COMMAND_MODULES = (screen_command_probes, drawing_probes, text_command_probes,
                    serial_command_probes, crc_command_probes,
                    device_and_buffer_command_probes, pinyin_probes, waveform_command_probes,
                    undocumented_command_probes)
PROBES += [_on_f(probe) for module in _COMMAND_MODULES for probe in module.PROBES]
PROBES += [_on_f(probe) for probe in command_operand_probes.PROBES
           if probe.name != "command-operands-eeprom-and-gpio"]
PROBES += [_on_f(probe) for probe in _named(page_command_probes, "page-values")]
PROBES += [
    _plain_code("other-attributes-in-commands", other_attribute_probes.IN_COMMANDS,
                _ONE_OF_EACH),
    _plain_code("other-attributes-in-f-commands",
                [line for line in other_attribute_probes.IN_K_COMMANDS
                 if line.split(" ", 1)[0] not in ("wept", "rept")], _ONE_OF_EACH),
    _plain_code("command-operands-in-f-commands",
                [line for line in command_operand_probes.EEPROM_AND_GPIO
                 if line.split(" ", 1)[0] not in ("wept", "rept")],
                command_operand_probes.COMPONENTS),
    # References through the screen's arrays in them, as indirect_probes.py's
    # probe of K's commands shows them, but wept and rept.
    Probe("f-indirect-in-f-commands", "F", statement_probes.beside_a_text_and_numbers([
        "wepo b[2].val,0", "wepo b[1].txt,0", "repo b[2].val,0", "cfgpio b[2].val,b[3].val,n0",
        "cfgpio 2,1,b[sys0]", "cfgpio 2,1,b[n0.val+1]"]), whole_file, editor_file)]

# F's own probes of the commands F has and T has not, which F numbers its
# own way: K's wepo, repo, and cfgpio, P's beep, cuts, gets, sets, and xnum,
# and piccolor, which F alone has, each with each kind of operand it takes,
# beside a text and two numbers, keeping their blocks; and some in
# program.s.
_COMMANDS_F_HAS = [
    "wepo 5,0", "wepo sys0,10", "wepo n0.val,20", "wepo t0.txt,30", 'wepo "abc",40',
    "repo sys0,0", "repo n0.val,10", "repo t0.txt,20", "repo 5,0", "cfgpio 0,0,0",
    "cfgpio 1,1,0", "cfgpio 4,3,0", "cfgpio 2,1,n0", "beep 100", "beep n0.val*2",
    "beep 0x10", "beep sys0", "cuts 0,0,0,0,0,0,0", "cuts n0.val,sys0+1,1,2,3,4,5",
    "gets 0,0", "gets n0.val,sys0", 'gets "a",t0.txt', "sets 0", 'sets "a",t0.txt,n0.val',
    "sets t0.txt,n0.val,sys0,1", "sets 0,0,0,0,0,0,0,0,0,0,0,0",
    "xnum 0,0,0,0,0,0,0,0,0,sys0*2", "piccolor 1,2,3,4", "piccolor 0,0,0,sys0",
    "piccolor sys0,n0.val,n1.val+1,n0.val", "piccolor 0x10,-5,799,t0.txt",
    'piccolor 65535,0,0,"a"']
PROBES += [
    Probe("f-commands-f-has-each", "F",
          statement_probes.beside_a_text_and_numbers(_COMMANDS_F_HAS), whole_file,
          editor_file, FIXTURES, statement_probes.ours_in_event),
    Probe("f-commands-f-has-in-program", "F", statement_probes.program_lines([
        "wepo 5,0", "repo sys0,0", "cfgpio 0,0,0", "beep 100", "cuts 0,0,0,0,0,0,0",
        "gets 0,0", "sets 1,2", "xnum 0,0,0,0,0,0,0,0,0,0", "piccolor 0,0,0,sys0"]),
          whole_file, editor_file)]

# The probes of encodings other than iso-8859-1: T's of a text and code in
# each of the 24 encodings, of every txt in four, of texts the Nextion
# Editor reads in pairs, and of a page of every type. F writes them as T
# does, so none keeps fixtures.
PROBES += [_on_f(probe) for probe in encoding_probes.PROBES if probe.base == "T"]

# The attributes every object has, a page's among them: aph and sendkey;
# drag, lockobj, the groups, movex, and movey; effects, their first, and
# their time; and vscope, of every type global, and on two pages.
PROBES += [_on_f(probe) for probe in shared_attribute_probes.PROBES]

# Components that overlap, whose background fills end in ref commands, which
# F numbers as T does; and a key of each keyed type, beside nxwright's
# keyboard pages, whose components overlap.
PROBES += [_on_f(probe) for probe in overlap_probes.PROBES + key_probes.PROBES]

# The forms of code the Nextion Editor writes as plainer ones, as on T.
PROBES += [_on_f(probe) for probe in code_form_probes.PROBES]

# F's other models, NX3224F024 and NX3224F028, at 0 degrees, and its base
# model at 90, 180, and 270 degrees, as nxwright's device command moves and
# turns the base folder (model_probes.moved). On each, the probes of a blank
# project, of pictures, fonts, and pages, of pages with ints and code, and of
# a page of swipes: they show header 1, the section's resources, and the
# pages at that screen's size.
_ELSEWHERE = [("NX3224F024", None), ("NX3224F028", None)] + [
    ("NX4832F035", degrees) for degrees in (90, 180, 270)]


def _elsewhere(probe: Probe, model: str, degrees) -> Probe:
    """Returns `probe` on the F base folder moved to `model` and turned to
    `degrees`, when given, compared as a whole file."""
    where = "model-%s" % model if degrees is None else "at-%d" % degrees
    # A blank project's probe changes nothing before the move.
    change = probe.change or (lambda folder: None)
    return replace(probe, name="f-%s-%s" % (where, probe.name), base="F",
                   change=moved(model, change, degrees), ours=whole_file,
                   theirs=editor_file, fixtures=None, kept=None)


PROBES += [_elsewhere(probe, model, degrees) for model, degrees in _ELSEWHERE
           for probe in (_named(compile_probes, "compile-T-blank",
                                "compile-T-resources-and-pages", "compile-T-pages-ints-code")
                         + _named(page_probes, "page-of-swipes"))]
# On each of them too, the probes of two texts, two numbers, and two
# buttons, whose drawings show the component types there.
PROBES += [_elsewhere(probe, model, degrees) for model, degrees in _ELSEWHERE
           for probe in (_named(text_probes, "text-two") + _named(number_probes, "number-two")
                         + _named(button_probes, "button-two"))]


# Every drawn type at F's other rotations too, as rotation_probes.py shows
# them on T: T's probes of a text at each rotation, of pages of pictures at
# 90 and 270 degrees, and of a page of a component of each drawn type, a text
# over two others among them, on a picture at each rotation and on no
# background at 90 degrees.
PROBES += [_on_f(probe) for probe in rotation_probes.PROBES]
