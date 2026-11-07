"""The P series' probes: T probes on the P base folder (probes/P), NX8048P050
at 0 degrees: of pages alone, the blank project, three pages with int
variables and code, and pages with resources; then the probes of each
component type matched on P, but one whose code has a command P numbers
its own way; then the probes of if, while, and for; then T's system
variables, colours, and operators in program.s, and P's own system
variables, which T has not; then numbers, hexadecimal numbers, the
assigning operators, and references through the screen's arrays, in events
and program.s, but the probes with a command, which P numbers its own way;
then the attributes of a text, a number, and a button in code; then global
texts, numbers, and buttons, and texts whose rooms keep what the Nextion
Editor's scratch image held (frame._through_the_scratch_image); then the
attributes every object has, of the page, a text, a number, and a button,
but an effect, and of each other type of T's that P takes
(_SHARED_ATTRIBUTE_PROBES), a crop's vvs0 and vvs1 set in code, which T's
rules refuse, a slider of a ch of 100, the most P takes, and a gauge at
its default sta of 3, nothing behind it, which T, K, and F refuse; then a
text of ASCII letters and digits in other encodings
(encoding_probes.ASCII_PROBES); then txts past ASCII letters and digits,
T's probes of them, and of P's own types with a txt in three encodings,
which keep the user code; then the rotations' probes; then the
probes of components that overlap, T's and one of each type of P's own
with a place under a text and over the next, as P writes no ref for them;
then components past the screen's right and bottom edges, which P takes,
up to their entries' highest; then lines longer than T's longest, which P
takes; then nxwright's thermostat example, a real
project of four pages. Each compares the whole file, part by part,
compiled as the compile command compiles it, as a series' probes do. Run
them with `tools.tft.probe run p_probes`.

P writes the user code its own way (ResearchNotes/tft/p-series.md). The probes
of the blank project and of the three pages keep the whole compile's
fixtures, made on zeros for the firmware, each type's probes that keep
fixtures on T keep them on P, and the probes of system variables and
colours keep program.s's blocks, as P numbers most of them its own way,
and the probes of attributes read and set keep their event's blocks, and
those of the scratch image and of a record's head in memory keep the user
code, and so do one of goto and one of macros, and the probes of the
types P has and T has not that keep the user code (switch_probes.py,
external_picture_probes.py, select_probes.py, combo_box_probes.py,
file_stream_probes.py, sliding_text_probes.py, gmov_probes.py,
audio_probes.py, video_probes.py, data_record_probes.py, and
file_browser_probes.py).
"""
from dataclasses import replace
from pathlib import Path
import shutil

from tools.tft.probing import (audio_probes, button_border_and_picture_probes, button_probes,
                           checkbox_probes, code_form_probes, combo_box_probes, compile_probes,
                           crc_command_probes, crop_probes, data_record_probes,
                           device_and_buffer_command_probes, drawing_probes,
                           dual_state_button_probes, eeprom_and_gpio_probes, encoding_probes,
                           external_picture_probes, file_browser_probes, file_stream_probes,
                           for_probes, gauge_probes, gmov_probes, goto_probes, hex_number_probes,
                           hotspot_probes, if_probes, indirect_probes, key_probes, macro_probes,
                           media_probes, number_border_and_picture_probes, number_probes,
                           other_attribute_probes,
                           overlap_probes, page_command_probes, page_probes, picture_probes,
                           pinyin_probes, progress_bar_probes, qr_code_probes, radio_probes,
                           rotation_probes, screen_command_probes, scrolling_text_probes,
                           select_probes, serial_command_probes, slider_probes,
                           sliding_text_probes, statement_probes, switch_probes,
                           text_border_and_picture_probes, text_character_probes,
                           text_command_probes, text_probes, timer_probes, touch_capture_probes,
                           undocumented_command_probes, variable_probes, video_probes,
                           waveform_command_probes, waveform_probes, while_probes, xfloat_probes)
from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.component_probes import (editor_file, on_pages, page_attribute_lines,
                                            user_code_kept, whole_file, with_components)
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (ProgramChange, beside_a_text_and_numbers, event_lines,
                                            ours_in_event, ours_in_program, program_lines,
                                            theirs_in_event, theirs_in_program,
                                            touch_release_code)
from nxwright.tft.statements import SYSTEM_VARIABLES
from tools.tft.probing.text_probes import text_component

FIXTURES = "p"


def _on_p(probe: Probe, fixtures: bool = False) -> Probe:
    """Returns `probe` on the P base folder, compared as a whole file. With
    `fixtures`, it keeps the whole compile's fixtures."""
    return replace(probe, name="p-" + probe.name, base="P", ours=whole_file, theirs=editor_file,
                   fixtures=FIXTURES if fixtures else None,
                   kept=(probe.kept or probe.ours) if fixtures else None)


_KEEPING = {"compile-T-blank", "compile-T-pages-ints-code"}
_PROBES = {probe.name: probe for probe in compile_probes.PROBES}
# The probe of media of each kind keeps the whole compile's fixtures, as the
# compile's own probes above do.
_MEDIA_KEEPING = "media-of-each"

# The types' probe that P's rules do not take: one of `get`, a command P
# numbers its own way.
_LEFT_OUT = {"button-txt-and-val-in-commands"}
# The attributes every component has, away from their defaults, on each type
# of T's that P takes after the text, the number, and the button: its effect
# moves its entries from 19 on two on.
_SHARED_VALUES = dict(aph=50, sendkey=3, drag=1, lockobj=1, movex=5, movey=6, groupid0=1,
                      groupid1=2, effect=2, first=10, time=500)
_SHARED_ATTRIBUTE_PROBES = [
    Probe("checkbox-shared-attributes", "P", with_components(
        checkbox_probes.checkbox_component(**_SHARED_VALUES)), whole_file, editor_file),
    Probe("radio-shared-attributes", "P", with_components(
        radio_probes.radio_component(**_SHARED_VALUES)), whole_file, editor_file),
    Probe("dual-state-button-shared-attributes", "P", with_components(
        dual_state_button_probes.dual_state_button_component(**_SHARED_VALUES)), whole_file,
        editor_file),
    Probe("progress-bar-shared-attributes", "P", with_components(
        progress_bar_probes.progress_bar_component(**_SHARED_VALUES)), whole_file,
        editor_file),
    Probe("picture-shared-attributes", "P", picture_probes.with_pictures(
        [("red", (8, 4), (255, 0, 0))], picture_probes.picture_component(**_SHARED_VALUES)),
        whole_file, editor_file),
    Probe("xfloat-shared-attributes", "P", with_components(
        xfloat_probes.xfloat_component(**_SHARED_VALUES)), whole_file, editor_file),
    Probe("qr-code-shared-attributes", "P", with_components(
        qr_code_probes.qr_code_component(**_SHARED_VALUES)), whole_file, editor_file),
    Probe("crop-shared-attributes", "P", picture_probes.with_pictures(
        [("red", (8, 4), (255, 0, 0))], crop_probes.crop_component(picc="red",
                                                                   **_SHARED_VALUES)),
        whole_file, editor_file),
    Probe("slider-shared-attributes", "P", with_components(
        slider_probes.slider_component(**_SHARED_VALUES)), whole_file, editor_file),
    Probe("gauge-shared-attributes", "P", with_components(
        gauge_probes.gauge_component(**_SHARED_VALUES)), whole_file, editor_file),
    Probe("scrolling-text-shared-attributes", "P", with_components(
        scrolling_text_probes.scrolling_text_component(**_SHARED_VALUES)), whole_file,
        editor_file),
    Probe("waveform-shared-attributes", "P", with_components(
        waveform_probes.waveform_component(**_SHARED_VALUES)), whole_file, editor_file),
    Probe("hotspot-shared-attributes", "P", with_components(
        hotspot_probes.hotspot_component(**_SHARED_VALUES)), whole_file, editor_file),
    # The types that have no place have only lockobj, groupid0, and
    # groupid1 of these, beside their vscope: a timer, a variable, a touch
    # capture, an audio, and a file stream, each with all three set.
    Probe("groups-and-locks-of-the-types-without-a-place", "P", with_components(*[
        '\n[[component]]\nname = "%s"\ntype = "%s"\nlockobj = 1\ngroupid0 = 3\ngroupid1 = 4\n'
        % (name, type_name)
        for name, type_name in (("tm0", "timer"), ("va0", "variable"), ("tc0", "touch-capture"),
                                ("wav0", "audio"), ("fs0", "file-stream"))]),
        whole_file, editor_file)]
# A crop's vvs0 and vvs1 set, stepped, and read in code. P's rules take
# setting them, as they lie in its memory there, where T's refuse it.
_CROP_VVS_IN_CODE = Probe("crop-vvs-in-code", "P", picture_probes.with_pictures(
    [("bg", (320, 480), (0, 0, 255))], crop_probes.crop_component(),
    code="on page0.up:\n  q0.vvs0=5\n  q0.vvs1++\n  sys0=q0.vvs0+q0.vvs1\n"),
    whole_file, editor_file)
# A slider's ch at 100, the most the Nextion Editor takes on P, where T takes
# up to 255.
_SLIDER_CH_OF_100 = Probe("slider-ch-of-100", "P", with_components(
    slider_probes.slider_component(ch=100)), whole_file, editor_file)
# A gauge at its default sta of 3, nothing behind it, which T, K, and F
# refuse: with a gauge of a colour and a text after it, whose entries are
# each one down, and its val and theirs read and set in code; then one
# whose bco, which it has no entry for, is set; and one with an effect,
# whose entries move each later one two on.
_GAUGES_OF_NOTHING_BEHIND = [
    Probe("gauge-of-nothing-behind", "P", with_components(
        gauge_probes.gauge_component(sta=3, val=45), gauge_probes.gauge_component(
            "z1", x=150, sta=1), text_component("t0", y=200),
        code="on page0.up:\n  sys0=z0.val\n  z0.val=90\n  z1.val=z0.val\n  t0.txt=\"a\"\n"),
        whole_file, editor_file, FIXTURES, user_code_kept),
    Probe("gauge-of-nothing-behind-with-a-bco", "P", with_components(
        gauge_probes.gauge_component(sta=3, bco=31)), whole_file, editor_file),
    Probe("gauge-of-nothing-behind-with-an-effect", "P", with_components(
        gauge_probes.gauge_component(sta=3, val=45, effect=2, first=10, time=500)),
        whole_file, editor_file)]
# The other types whose sta takes 3 on P and E, nothing behind them, which T,
# K, and F refuse: one of each type, its bco set, which it has no entry for,
# with a text of a colour after it, whose entries are each one down, and
# code reading and setting a value of each, as (type, the component, its
# value). Then a text, a number, and a button at styles other than none,
# which have no entry at that sta either; and a text with an effect, whose
# entries move each later one two on.
_NOTHING_BEHIND = (
    ("text", text_component(sta=3, bco=31), "t0.pco"),
    ("number", number_component(sta=3, bco=31), "n0.val"),
    ("button", button_component(sta=3, bco=31, bco2=63), "b0.pco2"),
    ("xfloat", xfloat_probes.xfloat_component(sta=3, bco=31), "x0.val"),
    ("dual-state-button",
     dual_state_button_probes.dual_state_button_component(sta=3, bco=31, bco2=63), "bt0.val"),
    ("scrolling-text", scrolling_text_probes.scrolling_text_component(sta=3, bco=31), "g0.pco"),
    ("waveform", waveform_probes.waveform_component(sta=3, bco=31), "s0.pco0"))
_OTHERS_OF_NOTHING_BEHIND = [
    Probe("%s-of-nothing-behind" % kind, "P", with_components(
        component, text_component("t1", y=300),
        code="on page0.up:\n  sys0=%s\n  %s=5\n  t1.pco=6\n" % (value, value)),
        whole_file, editor_file, FIXTURES, user_code_kept)
    for kind, component, value in _NOTHING_BEHIND] + [
    Probe("types-of-nothing-behind-with-a-style", "P", with_components(
        text_component(sta=3, style=3), number_component(x=120, sta=3, style=2),
        button_component(x=230, sta=3, style=3), text_component("t1", y=300)),
        whole_file, editor_file),
    # A style of 1 with nothing behind it, which draws no border but gives
    # its borderc's and borderw's entries.
    Probe("types-of-nothing-behind-with-a-border", "P", with_components(
        text_component(sta=3, style=1, borderc=63488, borderw=3),
        number_component(x=120, sta=3, style=1, borderc=31, borderw=7),
        button_component(x=230, sta=3, style=1, borderc=2016, borderw=2),
        text_component("t1", y=300)),
        whole_file, editor_file),
    Probe("text-of-nothing-behind-with-an-effect", "P", with_components(
        text_component(sta=3, effect=2, first=10, time=500), text_component("t1", y=300),
        code="on page0.up:\n  t0.pco=5\n  t1.pco=6\n"),
        whole_file, editor_file)]
# A slider's psta of 2 on P and E, a square cursor, which T, K, and F refuse,
# with a text after it and code reading and setting its val.
_SLIDER_OF_A_SQUARE_CURSOR = Probe("slider-of-a-square-cursor", "P", with_components(
    slider_probes.slider_component(psta=2, pco=31), text_component("t1", y=300),
    code="on page0.up:\n  sys0=h0.val\n  h0.val=20\n  t1.pco=6\n"),
    whole_file, editor_file, FIXTURES, user_code_kept)
# Each type of P's own with a place, a text over its lower right corner, in
# rows of three that fit E's 480 by 480 screen too, each overlapping the
# next in its row. On P, an overlap writes no ref, so the file is as if they
# did not overlap.
_PLACED_P_TYPES = (switch_probes.switch_component, external_picture_probes.external_picture,
                   select_probes.select_component, combo_box_probes.combo_box_component,
                   sliding_text_probes.sliding_text_component, gmov_probes.gmov_component,
                   video_probes.video_component, data_record_probes.data_record_component,
                   file_browser_probes.file_browser_component)
_P_TYPES_UNDER_TEXTS = Probe("overlap-p-types-under-texts", "P", with_components(*[
    component for number, make in enumerate(_PLACED_P_TYPES)
    for x, y in [(10 + 150 * (number % 3), 10 + 155 * (number // 3))]
    for component in (make(x=x, y=y, w=160, h=80),
                      text_probes.text_component("t%d" % number, x=x + 60, y=y + 50, w=80))]),
    whole_file, editor_file, FIXTURES, user_code_kept)
# Each type with a place, T's drawn types and P's own: on P and E, a
# component may reach past the screen's right and bottom edges, up to its
# entries' highest, x and y of 6000 and w and h of 2000.
_PLACED_TYPES = (text_probes.text_component, number_probes.number_component,
                 button_probes.button_component, checkbox_probes.checkbox_component,
                 radio_probes.radio_component, dual_state_button_probes.dual_state_button_component,
                 progress_bar_probes.progress_bar_component, xfloat_probes.xfloat_component,
                 qr_code_probes.qr_code_component, slider_probes.slider_component,
                 gauge_probes.gauge_component, hotspot_probes.hotspot_component,
                 scrolling_text_probes.scrolling_text_component, waveform_probes.waveform_component,
                 lambda **place: picture_probes.picture_component(pic="a", **place),
                 lambda **place: crop_probes.crop_component(picc="a", **place)) + _PLACED_P_TYPES


def _sum_of(target: str, size: int) -> str:
    """Returns an assignment to `target` of `size` characters, such as
    `sys0=1+1+11`."""
    last = "1" if (size - len(target) - 1) % 2 else "11"
    return target + "=" + "1+" * ((size - len(target) - 1 - len(last)) // 2) + last


# Lines past 767 bytes, the longest T takes, up to 4095, the longest P
# takes: in program.s, in page0's Touch Release event, and a for's start
# and step, which the Nextion Editor holds to the same limit.
_LONG_LINES = Probe("statements-long-lines", "P", ProgramChange(
    program=(_sum_of("sys0", 4095),),
    code=touch_release_code([_sum_of("sys1", 768), _sum_of("sys2", 4095),
                             "for(%s;sys1<0;%s)" % (_sum_of("sys1", 4095), _sum_of("sys1", 4095)),
                             "{", "sys2++", "}"])),
    ours_in_event, theirs_in_event)
_PAST_THE_SCREEN = [
    # A text past the right edge, a number past the bottom, and a button past
    # both, on P's 800 by 480 screen and on E's 480 by 480.
    Probe("place-past-the-screen-s-edges", "P", with_components(
        text_probes.text_component(x=750), number_probes.number_component(y=450, h=60),
        button_probes.button_component(x=760, y=440, h=100)),
        whole_file, editor_file, FIXTURES, user_code_kept),
    # One of each type with a place at x and y of 6000, their entries'
    # highest, at its own size. Every type's place has the same entries on P.
    Probe("place-every-type-at-the-entries-highest", "P", picture_probes.with_pictures(
        [("a", (8, 4), (255, 0, 0))], *[make(x=6000, y=6000) for make in _PLACED_TYPES]),
        whole_file, editor_file, FIXTURES, user_code_kept),
    # A text and a waveform of 2000 by 2000, their entries' highest. The
    # Nextion Editor runs out of memory showing a page of 25 such
    # components, so only two are probed.
    Probe("place-sizes-at-the-entries-highest", "P", with_components(
        text_probes.text_component(x=0, y=0, w=2000, h=2000),
        waveform_probes.waveform_component(x=6000, y=6000, w=2000, h=2000)),
        whole_file, editor_file, FIXTURES, user_code_kept)]
# nxwright's example project, a thermostat of four pages written in nxlang.
# It is a real project, not a probe, so it shows whether the rules take
# what people write.
_THERMOSTAT_SOURCE = Path(__file__).resolve().parents[3] / "examples" / "thermostat" / "app"


def _thermostat(folder: Path):
    """Copies the thermostat example's source folder over the base folder
    `folder`. The base folder's own page and font stay, but the example's
    app.toml lists neither, so its build leaves them out."""
    shutil.copytree(_THERMOSTAT_SOURCE, folder, dirs_exist_ok=True)


# On P alone: e_probes.py leaves it out.
THERMOSTAT_PROBE = _on_p(Probe("example-thermostat", "P", _thermostat, whole_file, editor_file))
# Txts past ASCII letters and digits: T's probes of every printable ASCII
# character and of those from U+00A0 to U+00FF, in iso-8859-1, on each of
# T's types with a txt, and of four other encodings' characters on them.
_TXT_PROBES = ([probe for probe in text_character_probes.PROBES
                if probe.kept is user_code_kept]
               + [probe for probe in encoding_probes.PROBES
                  if probe.name.startswith("encoding-every-txt-in-")])
# A txt of each of P's own types with one, a select, a combo box, and a
# switch, whose txt gives its two labels separated by "/": in iso-8859-1,
# of marks and characters from U+00A0 to U+00FF, and in gb2312 and utf-8,
# of their characters.
_P_TYPES_TXTS = {"iso-8859-1": "a b, é ñ ©!", "gb2312": encoding_probes.encoded_text("gb2312"),
                 "utf-8": encoding_probes.encoded_text("utf-8")}
_P_TYPES_TXT_PROBES = [
    Probe("txts-past-ascii-of-p-types-in-" + encoding, "P", encoding_probes.in_encoding(
        encoding, with_components(
            select_probes.select_component(txt=txt, txt_maxl=30),
            combo_box_probes.combo_box_component(x=200, txt=txt, txt_maxl=30),
            switch_probes.switch_component(x=400, txt=txt + "/" + txt, txt_maxl=60))),
        whole_file, editor_file, None, user_code_kept)
    for encoding, txt in _P_TYPES_TXTS.items()]
_STATEMENTS = {probe.name: probe for probe in statement_probes.PROBES}
# The probes of references through the screen's arrays with no command; and
# those of program.s, but its commands, which P numbers its own way.
_REFERENCES_WITHOUT_COMMANDS = {"indirect-assignments", "indirect-indexes",
                                "indirect-across-pages", "indirect-conditions"}
_REFERENCES_IN_PROGRAM = Probe(
    "indirect-in-program-s-without-commands", "P",
    program_lines(['p[0].b[1].txt="a"', "p[0].b[2].val=5", "sys0=p[0].b[1].val",
                   "if(p[0].b[2].val==1)", "{", "sys0=1", "}"]),
    ours_in_program, theirs_in_program)
# P's own system variables, which T has not, each read into sys0 and set from
# it in program.s, as statement_probes.py's probe of T's.
_OWN_VARIABLES = sorted(set(SYSTEM_VARIABLES["P"]) - set(SYSTEM_VARIABLES["T"]))
_OWN_VARIABLES_PROBE = Probe(
    "statements-own-system-variables", "P",
    program_lines(["sys0=%s" % name for name in _OWN_VARIABLES]
                  + ["%s=sys0" % name for name in _OWN_VARIABLES]),
    ours_in_program, theirs_in_program)
# The attributes of a text, a number, and a button, the types the frame
# writes on P, in page0's Touch Release event: each read into sys0, each
# that code can change on P set from it, and some in the conditions of if,
# while, and for, as other_attribute_probes.py's probes of each type.
_TYPES = [text_component(), number_component(y=50), button_component(y=90)]
_ATTRIBUTES = {key: names for key, names in other_attribute_probes.ATTRIBUTES.items()
               if key[1] in ("text", "number", "button")}
_ATTRIBUTE_PROBES = [
    Probe("attributes-read", "P",
          with_attributes(other_attribute_probes.reads(_ATTRIBUTES), _TYPES),
          ours_in_event, theirs_in_event),
    Probe("attributes-set", "P", with_attributes(
        other_attribute_probes.sets(_ATTRIBUTES, "P")
        + ["t0.bco+=1", "t0.pco-=n0.font", "b0.bco2++", "n0.lenth=t0.bco*2+n0.font",
           "b0.pco2*=2"], _TYPES),
          ours_in_event, theirs_in_event),
    Probe("attributes-in-conditions", "P", with_attributes([
        "if(t0.bco==1)", "{", "sys0=1", "}else if(n0.lenth>b0.pco2&&b0.bco2!=t0.pco)", "{",
        "sys0=2", "}", "while(n0.x<10)", "{", "n0.x++", "}",
        "for(t0.bco=0;t0.bco<n0.font;t0.bco+=1)", "{", "sys0++", "}"], _TYPES),
          ours_in_event, theirs_in_event)]

# Global components on P, and local texts whose rooms keep what lay in the
# Nextion Editor's scratch image: the globals' memory, before their heads
# are filled in, and what the page before left. A room of 201 bytes shows
# a global text's whole memory, and the page before's.
_GLOBAL = "vscope = 1\n"


# page0's global text t0 and number n1, with code naming page1's globals, in
# strict Nextion syntax; page1's global number n0, its text t1, and its
# global button b0.
_GLOBALS_ON_TWO_PAGES = on_pages(
    ProgramChange(components=(text_component() + _GLOBAL, number_component("n1", y=60)),
                  code=touch_release_code(["sys0=page1.n0.val", "page1.n0.val=5",
                                           'page1.b0.txt="a"', 'page0.t0.txt="b"',
                                           "t0.txt=page1.b0.txt"])),
    with_components(number_component("n0", y=60) + _GLOBAL, text_component("t1", y=110),
                    button_component("b0", y=160) + _GLOBAL, page="page1"))

# page0's global number and three texts, then page1's text of a wide room,
# which shows page0's memory.
_ROOMS_AFTER_A_LONG_PAGE = on_pages(
    with_components(number_component("n0", y=10) + _GLOBAL,
                    *(text_component("t%d" % n, y=60 + 50 * n, txt="ABCDEFGHIJ")
                      for n in range(1, 4))),
    with_components(text_component("t9", y=160, txt="", txt_maxl=200), page="page1"))

# page0, global, with its global text t0 and its number n0; page1, global,
# with its text t1, whose code names page0's t0 by its page.
_GLOBAL_PAGES = on_pages(
    with_components(text_component() + _GLOBAL, number_component("n0", y=60),
                    attributes=page_attribute_lines(vscope=1)),
    with_components(text_component("t1", y=110), page="page1",
                    code='on t1.up:\n  page0.t0.txt="b"\n',
                    attributes=page_attribute_lines(vscope=1)))

# A text on page0, and one of a shorter txt in its place on page1.
_ROOMS_ACROSS_PAGES = on_pages(with_components(text_component(txt="ABCDEFGHIJ")),
                               with_components(text_component(), page="page1"))


_SCRATCH_PROBES = [Probe(name, "P", change, whole_file, editor_file, None, user_code_kept)
                   for name, change in (
    ("globals-text", with_components(text_component() + _GLOBAL)),
    ("globals-number", with_components(number_component() + _GLOBAL)),
    ("globals-button", with_components(button_component() + _GLOBAL)),
    ("globals-and-locals", with_components(
        text_component() + _GLOBAL, number_component("n0", y=60),
        button_component("b0", y=110) + _GLOBAL, text_component("t1", y=160))),
    ("globals-beside-a-text", with_components(
        number_component("n0", y=60) + _GLOBAL, text_component("t1", y=110),
        button_component("b0", y=160) + _GLOBAL)),
    ("globals-on-two-pages", _GLOBALS_ON_TWO_PAGES),
    ("globals-under-a-wide-room", with_components(
        number_component("n0", y=10) + _GLOBAL, button_component("b0", y=60) + _GLOBAL,
        text_component("t2", y=110) + _GLOBAL,
        text_component("t9", y=160, txt="", txt_maxl=200))),
    ("text-rooms-after-a-long-page", _ROOMS_AFTER_A_LONG_PAGE),
    ("text-rooms-across-pages", _ROOMS_ACROSS_PAGES),
    # Global variables of a text and of a number past three globals, under
    # a room that shows their memory: their values, and their heads of 4
    # bytes but for their kind.
    ("globals-variables-under-a-wide-room", with_components(
        number_component("n0", y=10) + _GLOBAL, button_component("b0", y=60) + _GLOBAL,
        text_component("t2", y=110) + _GLOBAL,
        variable_probes.text_variable_component("va0") + _GLOBAL,
        variable_probes.variable_component("va1", val=7) + _GLOBAL,
        text_component("t9", y=160, txt="", txt_maxl=1000))))]
# The scratch image's probes that keep the user code.
_SCRATCH_KEEPING = {"globals-beside-a-text", "globals-on-two-pages", "globals-under-a-wide-room",
                    "text-rooms-after-a-long-page", "text-rooms-across-pages"}

# A component of each type P has but the text, the number, and the button,
# at its defaults, global. The data record is always global, and the Nextion
# Editor refuses a global file stream on P and E, as nxwright's memory table
# records.
GLOBAL_TYPES = {
    "checkbox": checkbox_probes.checkbox_component(),
    "radio": radio_probes.radio_component(),
    "dual-state-button": dual_state_button_probes.dual_state_button_component(),
    "progress-bar": progress_bar_probes.progress_bar_component(),
    "xfloat": xfloat_probes.xfloat_component(),
    "qr-code": qr_code_probes.qr_code_component(),
    "slider": slider_probes.slider_component(),
    "gauge": gauge_probes.gauge_component(),
    "waveform": waveform_probes.waveform_component(),
    "scrolling-text": scrolling_text_probes.scrolling_text_component(),
    "hotspot": hotspot_probes.hotspot_component(),
    "timer": timer_probes.timer_component(),
    "variable": variable_probes.variable_component(),
    "touch-capture": touch_capture_probes.touch_capture_component(),
    "picture": picture_probes.picture_component(pic="bg"),
    "crop": crop_probes.crop_component(picc="bg"),
    "switch": switch_probes.switch_component(),
    "external-picture": external_picture_probes.external_picture(),
    "select": select_probes.select_component(),
    "combo-box": combo_box_probes.combo_box_component(),
    "sliding-text": sliding_text_probes.sliding_text_component(),
    "gmov": gmov_probes.gmov_component(),
    "video": video_probes.video_component(),
    "audio": audio_probes.audio_component(),
    "file-browser": file_browser_probes.file_browser_component(),
}


def _global_beside_a_text(name: str):
    """Returns a probe's change: the component of the type `name` of
    GLOBAL_TYPES, global, on page0, beside a local text below it, whose
    memory follows the page's run. A picture and a crop show the screen's
    picture bg."""
    components = (GLOBAL_TYPES[name] + _GLOBAL, text_component("t9", y=400))
    if name in ("picture", "crop"):
        return picture_probes.with_pictures(picture_probes.SCREEN_PICTURES[:1], *components)
    return with_components(*components)


_GLOBAL_TYPE_PROBES = [Probe("globals-" + name, "P", _global_beside_a_text(name), whole_file,
                             editor_file, None, user_code_kept) for name in GLOBAL_TYPES]

# The attributes every object has, of the page, a text, a number, and a
# button: an aph and a sendkey, in their records; and those that change
# nothing in the file on T, of which an object's memory gives its drag, its
# movex, and its movey in its record's head (frame._p_memory_head).
def _with_shared(attributes: dict, page: dict, code: str = ""):
    def lines(component: str) -> str:
        return component + "".join("%s = %d\n" % item for item in attributes.items())

    return with_components(lines(text_component()), lines(number_component(y=60)),
                           lines(button_component(y=110)), code=code,
                           attributes=page_attribute_lines(**page))


# Each type and the page with an effect, and code in a text's event naming a
# txt and a val, entries the effect moves; and a text on page1, which has an
# effect alone, its first and its time at their defaults.
_EFFECTS_AND_A_SECOND_PAGE = on_pages(
    _with_shared({"effect": 3, "first": 6, "time": 1150},
                 {"effect": 2, "first": 9, "time": 777},
                 'on t0.up:\n  t0.txt="Yo"\n  n0.val=5\n'),
    with_components(text_component(), page="page1", code='on t0.up:\n  t0.txt="Hi"\n',
                    attributes=page_attribute_lines(effect=4)))


_SHARED_PROBES = [Probe("shared-attributes-" + name, "P", change, whole_file, editor_file, None,
                        user_code_kept) for name, change in (
    ("aph-and-sendkey", _with_shared({"aph": 50, "sendkey": 3}, {"aph": 90, "sendkey": 1})),
    ("that-change-nothing-on-t", _with_shared(
        {"drag": 1, "lockobj": 1, "movex": 5, "movey": 7, "groupid0": 3, "groupid1": 9},
        {"lockobj": 1, "movex": 2, "groupid0": 1})),
    ("drag-and-moves", _with_shared({"movex": 65535, "movey": 32768},
                                    {"drag": 1, "movey": 3, "groupid1": 7})),
    # Global objects, whose memory lies in the first block's int area.
    ("of-globals", _with_shared({"vscope": 1, "drag": 1, "movex": 5, "movey": 7, "aph": 40,
                                 "sendkey": 2}, {})),
    # An effect, its first, and its time, which then take two entries after
    # its effect's (component_types.with_p_effect); with code naming
    # attributes past them, and a second page; and without an effect, when
    # they change nothing in the file.
    ("effects", _with_shared({"effect": 3, "first": 6, "time": 1150},
                             {"effect": 2, "first": 9, "time": 777})),
    ("effects-and-a-second-page", _EFFECTS_AND_A_SECOND_PAGE),
    ("first-and-time-without-an-effect", _with_shared({"first": 6, "time": 1150},
                                                      {"first": 9, "time": 777})),
    # A global page, whose memory lies in the int area as a global
    # component's does, with local components; and two global pages, the
    # first's text global, which code on the second names by its page.
    ("a-global-page", _with_shared({}, {"vscope": 1})),
    ("global-pages-on-two-pages", _GLOBAL_PAGES),
    # A dragged text with a disup of 1. The Nextion Editors 1.60.1 and 1.63.3
    # keep disup, and 1.68.2 has none: it writes the same file as without it.
    ("a-drag-and-a-disup", with_components(text_component(drag=1, disup=1))))]
# The probes of a record's head in memory, and of the entries an effect
# moves, that keep the user code.
_SHARED_KEEPING = {"shared-attributes-that-change-nothing-on-t",
                   "shared-attributes-drag-and-moves", "shared-attributes-of-globals",
                   "shared-attributes-effects", "shared-attributes-effects-and-a-second-page",
                   "shared-attributes-global-pages-on-two-pages"}

# The families of commands P numbers its own way, in the same tables, and
# their probes. Those of each command keep their blocks.
_COMMAND_MODULES = (screen_command_probes, drawing_probes, text_command_probes,
                    serial_command_probes, crc_command_probes,
                    device_and_buffer_command_probes, pinyin_probes, waveform_command_probes)
_COMMANDS_KEEPING = {"screen-commands-each", "drawing-each-command", "text-commands-each",
                     "serial-commands-each", "crc-commands-each",
                     "device-and-buffer-commands-each", "pinyin-in-an-event", "page-values",
                     "eeprom-and-gpio-each", "undocumented-commands-each",
                     "commands-p-has-each", "commands-p-has-operands",
                     "commands-p-has-components-of-other-forms",
                     "commands-p-has-files-of-any-kind",
                     "undocumented-commands-p-has-each", "waveform-commands-each"}


def _page_of_another_page(folder):
    """page1's global number n0, whose val page0's code gives `page`."""
    event_lines(["page page1.n0.val+1"])(folder)
    with_components(text_component())(folder)
    with_components(number_component("n0", y=60) + _GLOBAL, page="page1")(folder)


# The commands P has and T and K have not, of files on the SD card, of
# sound, of motion, and of layers (instructions/file_commands.py and
# sound_motion_and_layer_commands.py): each, with texts and numbers; each
# with txts, operands joined by arithmetic, variables, attributes, IDs, and
# `b[i]`; and some in program.s. Then the undocumented ones.
_COMMANDS_P_HAS = [
    Probe("commands-p-has-each", "P", beside_a_text_and_numbers([
        'beep 100', 'newdir "sd0/a/"', 'deldir "sd0/a/"', 'delfile "sd0/a.txt"',
        'refile "sd0/a.txt","sd0/b.txt"', 'redir "sd0/a/","sd0/b/"', 'newfile "sd0/a.txt",10',
        'findfile "sd0/a.txt",n0.val', 'finddir "sd0/a/",n0.val', 'rdfile "sd0/a.txt",0,10,0',
        'twfile "sd0/a.txt",10', 'move t0,0,0,100,100,0,10', 'setlayer t0,n0', 'play 0,0,0']),
        ours_in_event, theirs_in_event),
    Probe("commands-p-has-operands", "P", beside_a_text_and_numbers([
        'newdir t0.txt', 'deldir t0.txt', 'delfile t0.txt', 'refile t0.txt,t0.txt',
        'redir t0.txt,"sd0/b/"', 'newfile t0.txt,n0.val+1', 'findfile t0.txt,sys0',
        'finddir t0.txt,sys0', 'rdfile t0.txt,n0.val,n1.val*2,1', 'twfile t0.txt,sys0',
        'move 1,n0.val,0,100,100,1,sys0', 'setlayer 1,2', 'play sys0,n0.val,1',
        'beep n0.val*2', 'beep 0x10', 'move b[1],0,0,1,1,0,1']),
        ours_in_event, theirs_in_event),
    # setlayer's components and move's as IDs past 255, in hexadecimal, and
    # as operands joined by the arithmetic operators, each written as any
    # number argument is.
    Probe("commands-p-has-components-of-other-forms", "P", beside_a_text_and_numbers([
        'setlayer 256,1', 'setlayer 0x01,2', 'setlayer 1,1000', 'move 0x01,0,0,10,10,0,10',
        'move sys0+1,0,0,10,10,0,10']),
        ours_in_event, theirs_in_event),
    # Variables as move's and setlayer's components, each written as its
    # operand.
    Probe("commands-p-has-variables-as-components", "P", beside_a_text_and_numbers([
        'move sys0,0,0,10,10,0,100', 'setlayer sys0,a']),
        ours_in_event, theirs_in_event),
    # The file commands' paths and answers' destinations, each one operand
    # of any kind.
    Probe("commands-p-has-files-of-any-kind", "P", beside_a_text_and_numbers([
        "delfile b[1].txt", "delfile b[1].val", "newdir p[0].b[1].txt",
        "findfile b[1].txt,n0.val", 'findfile "sd0/a.txt",b[1].val',
        'findfile "sd0/a.txt",b[1].txt', 'findfile "sd0/a.txt",5', 'finddir "sd0/a/",5',
        'findfile "sd0/a.txt",0x05', 'findfile "sd0/a.txt",-5', "delfile 5", "delfile n0.val",
        'findfile "sd0/a.txt",t0.txt', 'findfile "sd0/a.txt","b"']),
        ours_in_event, theirs_in_event),
    Probe("commands-p-has-in-program", "P", program_lines([
        'beep 100', 'newdir "sd0/x/"', 'play 0,0,0', 'move 1,0,0,10,10,0,10', 'setlayer 1,2',
        'findfile "sd0/x.txt",sys0']), ours_in_program, theirs_in_program),
    # The undocumented commands P has and T and K have not
    # (instructions/p_undocumented_commands.py): each, with numbers, operands
    # joined by arithmetic, variables, attributes, txts, and texts where they
    # take any kind, sets of 1 to 12; and some in program.s.
    Probe("undocumented-commands-p-has-each", "P", beside_a_text_and_numbers([
        'cuts 0,0,0,0,0,0,0', 'cuts n0.val,sys0+1,1,2,3,4,5', 'gets 0,0', 'gets n0.val,sys0',
        'gets "a",t0.txt', 'sets 0', 'sets "a",t0.txt,n0.val', 'sets t0.txt,n0.val,sys0,1',
        'sets 0,0,0,0,0,0,0,0,0,0,0,0', 'xnum 0,0,0,0,0,0,0,0,0,sys0*2', 'cfguart sys0,1,2,3',
        'meup n0.val,1', 'beepset 100,sys0+1']),
        ours_in_event, theirs_in_event),
    Probe("undocumented-commands-p-has-in-program", "P", program_lines([
        'gets 0,0', 'beepset 0,0', 'sets 1,2', 'xnum 0,0,0,0,0,0,0,0,0,0']),
        ours_in_program, theirs_in_program)]

# A text attribute other than a txt, each type's path, set from a text, from
# a txt, and from texts joined with one, added to, and cut, and a txt added
# to from it; a video and an audio from a file, where their path has an
# entry.
_PATH_HOLDERS = {
    "xp0": external_picture_probes.external_picture(y=60),
    "select0": select_probes.select_component(x=150),
    "cb0": combo_box_probes.combo_box_component(x=260),
    "gm0": gmov_probes.gmov_component(x=260, y=60),
    "vd0": video_probes.video_component(x=260, y=200, **{"from": 1}),
    "wav0": audio_probes.audio_component(**{"from": 1}),
    "slt0": sliding_text_probes.sliding_text_component(y=220)}
_PATHS_FROM_TXTS = Probe("paths-set-from-txts", "P", with_components(
    text_component(), *_PATH_HOLDERS.values(), code="on page0.up:\n" + "".join(
        "  %s\n" % line.format(name) for name in _PATH_HOLDERS for line in (
            '{0}.path="c"', "{0}.path=t0.txt", '{0}.path=t0.txt+"a"', '{0}.path="a"+t0.txt',
            "{0}.path+=t0.txt", '{0}.path+="b"', "{0}.path-=1", "t0.txt+={0}.path"))),
    whole_file, editor_file)

# `page` with a reference through the screen's arrays, and with another
# page's global, which T's page probes give beside commands P lacks.
_PAGE_PROBES = [
    Probe("page-references", "P", beside_a_text_and_numbers(
        ["page b[sys0].val+1", "page 1+b[n0.val].val"]), ours_in_event, theirs_in_event),
    Probe("page-of-another-page", "P", _page_of_another_page, ours_in_event, theirs_in_event)]

# Labels and goto, as on T, beside the types the frame writes on P, timers
# and scrolling texts among them; then in a page's load and loadend events
# and on a second page beside buttons, as the T probe's are beside timers;
# and macros, call, and return, as on T.
_GOTO_ON_P = {"goto-in-an-event", "goto-labels-then-gotos", "goto-across-program-and-events",
              "goto-beside-a-timer-and-a-button", "goto-in-load-loadend-and-a-second-page",
              "goto-beside-a-scrolling-text"}
_GOTO_IN_LOAD = Probe(
    "goto-in-load-loadend-and-a-second-page-beside-buttons", "P",
    goto_probes.project_with_code(
        [text_component(), button_component(y=300)],
        {"page0.load": ["l1:"], "page0.up": ["u1:", "goto u1"], "page0.loadend": ["e1:"],
         "b0.down": ["b1:", "goto b1"]},
        page1=[text_component("t5"), button_component("b5", y=300)],
        events1={"page1.up": ["p1:"], "b5.up": ["q1:"]}),
    whole_file, editor_file)
_GOTO_AND_MACROS_KEEPING = {"goto-across-program-and-events", "macros-called"}

PROBES = ([_on_p(_PROBES[name], name in _KEEPING)
           for name in ("compile-T-blank", "compile-T-pages-ints-code",
                        "compile-T-resources-and-pages", "compile-T-the-most-pages",
                        "compile-T-eight-hundred-ints",
                        "compile-T-forty-pictures-and-eight-fonts")]
          + [_on_p(probe, probe.fixtures is not None)
             for module in (text_probes, number_probes, button_probes, checkbox_probes,
                            radio_probes, dual_state_button_probes, progress_bar_probes,
                            xfloat_probes, qr_code_probes, slider_probes, page_probes,
                            variable_probes, timer_probes, picture_probes, crop_probes,
                            hotspot_probes, gauge_probes, touch_capture_probes,
                            text_border_and_picture_probes,
                            number_border_and_picture_probes,
                            button_border_and_picture_probes,
                            scrolling_text_probes, waveform_probes)
             for probe in module.PROBES
             if probe.name not in _LEFT_OUT]
          # A key on P, its three lines in the Touch Release event, whose
          # pieces T's fixtures keep.
          + [_on_p(probe) for probe in key_probes.PROBES]
          + [_on_p(probe) for module in (if_probes, while_probes, for_probes)
             for probe in module.PROBES]
          + [_on_p(_STATEMENTS[name], name != "statements-operators")
             for name in ("statements-system-variables", "statements-colours",
                          "statements-operators")]
          + [_on_p(_OWN_VARIABLES_PROBE, True)]
          + [_on_p(_STATEMENTS[name])
             for name in ("statements-numbers", "statements-compound-assignments",
                          "statements-compound-assignments-in-an-event")]
          + [_on_p(probe) for probe in hex_number_probes.PROBES]
          + [_on_p(probe) for probe in indirect_probes.PROBES
             if probe.name in _REFERENCES_WITHOUT_COMMANDS]
          + [_on_p(_REFERENCES_IN_PROGRAM)]
          + [_on_p(probe, probe.name != "attributes-in-conditions")
             for probe in _ATTRIBUTE_PROBES]
          + [_on_p(probe, probe.name in _SCRATCH_KEEPING) for probe in _SCRATCH_PROBES]
          + [_on_p(probe, True) for probe in _GLOBAL_TYPE_PROBES]
          + [_on_p(probe, probe.name in _SHARED_KEEPING) for probe in _SHARED_PROBES]
          + [_on_p(probe, probe.name in _COMMANDS_KEEPING) for module in _COMMAND_MODULES
             for probe in module.PROBES]
          + [_on_p(probe, probe.name in _COMMANDS_KEEPING)
             for probe in page_command_probes.PROBES + _PAGE_PROBES + eeprom_and_gpio_probes.PROBES
             + undocumented_command_probes.probes_without({"fstr"}) + _COMMANDS_P_HAS]
          + [_on_p(_PATHS_FROM_TXTS)]
          + [_on_p(probe) for probe in _SHARED_ATTRIBUTE_PROBES
             + [_CROP_VVS_IN_CODE, _SLIDER_CH_OF_100]]
          + [_on_p(probe, probe.fixtures is not None)
             for probe in _GAUGES_OF_NOTHING_BEHIND + _OTHERS_OF_NOTHING_BEHIND
             + [_SLIDER_OF_A_SQUARE_CURSOR]]
          + [_on_p(replace(probe, kept=compile_probes._kept), True)
             if probe.name == _MEDIA_KEEPING else _on_p(probe) for probe in media_probes.PROBES]
          + [_on_p(probe, probe.name in _GOTO_AND_MACROS_KEEPING)
             for probe in [probe for probe in goto_probes.PROBES if probe.name in _GOTO_ON_P]
             + [_GOTO_IN_LOAD] + macro_probes.PROBES]
          + [_on_p(probe, probe.kept is not None)
             for probe in switch_probes.PROBES + external_picture_probes.PROBES
             + select_probes.PROBES + combo_box_probes.PROBES + file_stream_probes.PROBES
             + sliding_text_probes.PROBES + gmov_probes.PROBES + audio_probes.PROBES
             + video_probes.PROBES + data_record_probes.PROBES + file_browser_probes.PROBES]
          + [_on_p(probe) for probe in encoding_probes.ASCII_PROBES]
          + [_on_p(probe, True) for probe in _TXT_PROBES + _P_TYPES_TXT_PROBES]
          + [_on_p(probe) for probe in rotation_probes.PROBES]
          # The forms of code the Nextion Editor writes as plainer ones.
          + [_on_p(probe) for probe in code_form_probes.PROBES]
          # Components that overlap, which write no ref on P.
          + [_on_p(probe, probe.fixtures is not None) for probe in overlap_probes.PROBES]
          + [_on_p(_P_TYPES_UNDER_TEXTS, True)]
          # Components past the screen's edges, which P and E take.
          + [_on_p(probe, True) for probe in _PAST_THE_SCREEN]
          + [_on_p(_LONG_LINES)]
          + [THERMOSTAT_PROBE])
