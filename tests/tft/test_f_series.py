"""The F series (tools/tft/probing/f_probes.py): the blocks of its probes of its
own system variables and of the commands it has, as they kept them once
they matched the Nextion Editor's files, what the check matches on F and
what it still refuses, F's tables beside T's, and the drawing commands F
numbers its own way.

Each test gives the function it checks its own input: a probe's page and
program.s made in memory, or the base folder's facts, in a Project of the
facts it reads (tests/tft/unit_inputs.py). The packaging of a project of two
of each resource and the whole compile of a blank project on F, and the
fonts the packaging writes on F, are compared whole in
tests/tft/test_whole_files.py.
"""
import unittest

from nxwright.project.device_settings import ENCODINGS
from nxwright.project.editor_language import EDITOR_SYSTEM_VARIABLES, SERIES_LACKED_VARIABLES

from nxwright.tft import frame, statements
from tools.tft.probing import f_probes
from nxwright.tft.matching import Need, matched_rules, unmatched
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.scrolling_text_probes import scrolling_text_component
from tools.tft.probing.statement_probes import kept_blocks
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.touch_capture_probes import touch_capture_component
from tests.tft.line_context import line_context
from tests.tft.unit_inputs import page, piece, piece_names, probe_project, project_of


class PiecesTest(unittest.TestCase):
    """The probes of F that keep fixtures: the packaging of a project of two
    of each resource and the whole compile of a blank project, compared
    whole as F's samples, and the probes of F's own system variables and of
    the commands F has, whose blocks the encoder gives on their page and
    program.s made in memory."""

    def test_the_probes_that_keep_fixtures(self):
        self.assertEqual({probe.name for probe in f_probes.PROBES if probe.fixtures}, {
            "f-packaging-T-two-each",
            "f-compile-T-blank",
            "f-statements-own-system-variables",
            "f-commands-f-has-each",
        })

    def test_the_encoder_s_blocks(self):
        for name in ("f-statements-own-system-variables", "f-commands-f-has-each"):
            probe = next(probe for probe in f_probes.PROBES if probe.name == name)
            with self.subTest(name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {each: piece(probe, each) for each in piece_names(probe)})


class MatchedTest(unittest.TestCase):

    def test_the_series_and_its_base_model(self):
        rules = matched_rules()
        for need in (Need("series", "F"), Need("model", "NX4832F035", series="F"),
                     Need("rotation", "0", series="F")):
            with self.subTest(need.subject):
                self.assertTrue(any(rule.matches(need) for rule in rules))

    def test_a_page_s_background(self):
        # Its colour, whether it shows a colour or a picture, and its picture.
        needs = [Need("attribute", "page.bco", (31).to_bytes(2, "little"), series="F"),
                 Need("attribute", "page.sta", b"\x02", series="F"),
                 Need("attribute", "page.pic", b"\x00\x00", series="F")]
        self.assertEqual(unmatched(needs, matched_rules()), [])

    def test_every_encoding(self):
        # Each of the Nextion Editor's 24 encodings, as on T.
        needs = [Need("encoding", name, series="F") for name in ENCODINGS.values()]
        self.assertEqual(len(needs), 24)
        self.assertEqual(unmatched(needs, matched_rules()), [])

    def test_keys_and_overlaps(self):
        # Each key of each keyed type, and two components that overlap, as
        # on T.
        needs = [Need("attribute", name, bytes([key]), series="F")
                 for name in ("text.key", "number.key", "xfloat.key", "scrolling-text.key")
                 for key in (1, 2, 3, 4)]
        needs.append(Need("overlap", "text and gauge", context={"types": ("text", "gauge")},
                          series="F"))
        self.assertEqual(unmatched(needs, matched_rules()), [])

    def test_what_f_s_probes_have_not_shown(self):
        # A component of a type of P and E alone.
        needs = [Need("type", "select", context={"components": {}}, series="F")]
        self.assertEqual(unmatched(needs, matched_rules()), needs)

    def test_lines_of_code(self):
        # On a page of a text and a number, F takes lines of code, and the
        # lines of if, while, and for, labels, goto, call, and return, as T
        # does, references through the screen's arrays and texts past ASCII
        # among them, and F's own system variables, such as pio0. It refuses
        # a system variable its tables lack, such as P's audio0 or K's rtc0,
        # in a line and in a head.
        context = line_context(text_component(), number_component())

        def code(line: str) -> Need:
            return Need("code", "event", line, context=context, series="F")

        taken = ['t0.txt="a"', "sys0=n0.val", "sys0=baud+1", "b[1].val=1", 't0.txt="é"',
                 "if(sys0==baud)", "}else if(p[0].b[1].val!=2)", "}else", 'while(t0.txt=="é")',
                 "for(b[1].val=0;b[1].val<3;b[1].val++)", "{", "}", "loop:", "goto loop",
                 "call m0", "return", "sys0=pio0", "lowpower=1", "while(pwmf>0)"]
        self.assertEqual(unmatched([code(line) for line in taken], matched_rules()), [])
        refused = ["sys0=audio0", "if(sys0==audio0)", "while(audio0>0)",
                   "for(sys0=audio0;sys0<3;sys0++)", "sys0=rtc0", "if(rtc0==1)"]
        self.assertEqual(unmatched([code(line) for line in refused], matched_rules()),
                         [code(line) for line in refused])

    def test_commands(self):
        # F takes each family of T's commands, and wepo, repo, cfgpio, beep,
        # cuts, gets, sets, xnum, and piccolor, which T has not. It refuses
        # those its series lacks, which nxwright's build refuses there too,
        # piccolor at another number of arguments than its four, and a
        # command naming a system variable its tables lack, such as audio0.
        context = line_context(text_component(), number_component())

        def code(line: str) -> Need:
            return Need("code", "event", line, context=context, series="F")

        taken = ["vis t0,0", "cls RED", "covx sys0,t0.txt,0,0", "print n0.val",
                 "crcrest 1,0xFFFF", "rest", "getv 0", "i 0,0,0,0", "pa_q t0.txt,n0.val",
                 "cle 1,0", "wepo 5,0", "repo sys0,0", "cfgpio 0,0,0", "beep 100",
                 "cuts 0,0,0,0,0,0,0", "gets 0,0", "sets 0", "xnum 0,0,0,0,0,0,0,0,0,0",
                 "piccolor 0,0,0,sys0"]
        self.assertEqual(unmatched([code(line) for line in taken], matched_rules()), [])
        refused = ["wept 0,10", "rept 0,10", "cfguart 0,0,0,0", "meup 0,0", "beepset 0,0",
                   "play 0,0,0", "piccolor 1,2", "wepo audio0,0", "cls audio0"]
        self.assertEqual(unmatched([code(line) for line in refused], matched_rules()),
                         [code(line) for line in refused])


class TypesTest(unittest.TestCase):
    """The component types matched on F (f_probes.py)."""

    def test_each_type_is_matched_on_f(self):
        for type_name in ("text", "number", "button", "checkbox", "radio", "dual-state-button",
                          "progress-bar", "xfloat", "qr-code", "slider", "gauge"):
            with self.subTest(type_name):
                self.assertEqual(unmatched([Need("type", type_name, series="F")],
                                           matched_rules()), [])


class TableTest(unittest.TestCase):
    """F has every system variable, colour, and command of program.s that T
    has, numbered its own way only where the probes showed it, and the
    system variables nxwright gives F and not T."""

    # The GPIO pins' system variables and lowpower, which F has and T has
    # not.
    NOT_ON_T = {"pio%d" % pin for pin in range(8)} | {"pwm4", "pwm5", "pwm6", "pwm7", "pwmf",
                                                       "lowpower"}

    def test_the_same_names(self):
        for table in (statements.COLOURS, statements.COMMANDS):
            self.assertEqual(set(table["F"]), set(table["T"]))
        self.assertEqual(statements.COMMANDS["F"], statements.COMMANDS["T"])

    def test_the_system_variables_nxwright_gives_f(self):
        given = set(EDITOR_SYSTEM_VARIABLES) - set(SERIES_LACKED_VARIABLES["F"])
        self.assertEqual(set(statements.SYSTEM_VARIABLES["F"]), given)
        self.assertEqual(given - set(statements.SYSTEM_VARIABLES["T"]), self.NOT_ON_T)

    def test_f_s_own_numbers(self):
        own = {name for name, number in statements.SYSTEM_VARIABLES["F"].items()
               if number != statements.SYSTEM_VARIABLES["T"].get(name)}
        self.assertEqual(own, {"sya1", "tch1", "tch2", "tch3", "rand", "baud", "thsp", "ussp",
                               "thup", "usup", "addr", "dims", "bcpu", "spax", "spay",
                               "portbusy"} | self.NOT_ON_T)
        own = {name for name, number in statements.COLOURS["F"].items()
               if number != statements.COLOURS["T"][name]}
        self.assertEqual(own, {"BLUE", "GRAY"})


class DrawingTest(unittest.TestCase):
    """A text's and a number's drawing on F: F numbers setbrush, zstr, and
    the command that draws a number its own way, and the 3D border as T
    does (component_types, component_types/number.py)."""

    def test_their_commands(self):
        code = frame.user_code(project_of(page(text_component(style=2),
                                               number_component(y=60), series="F"),
                                          series="F"))
        starts = {block[:3] for block, part in zip(code.blocks, code.block_parts())
                  if part == "page 0"}
        # setbrush, zstr, the number's drawing, and the 3D border.
        self.assertTrue({b"\x09\x1d\x08", b"\x09\x17\x04", b"\x09\x15\x04",
                         b"\x09\x07\x08"} <= starts)
        # T's setbrush, zstr, and number's drawing.
        self.assertFalse({b"\x09\x1c\x08", b"\x09\x13\x04", b"\x09\x11\x04"} & starts)

    def test_the_commands_of_types_that_load_or_scroll(self):
        # F numbers timerset 0x24 in table 8, the command a touch capture
        # and a waveform add to their page's load section 0x1D in table 4,
        # and the command a scrolling text measures its txt with 0x13 in
        # table 8, as K does.
        code = frame.user_code(project_of(page(timer_component(), touch_capture_component("tc0"),
                                               scrolling_text_component(y=100), series="F"),
                                          series="F"))
        starts = {block[:3] for block, part in zip(code.blocks, code.block_parts())
                  if part == "page 0"}
        self.assertTrue({b"\x09\x24\x08", b"\x09\x1d\x04", b"\x09\x13\x08"} <= starts)
        # T's timerset, load command, and measuring command.
        self.assertFalse({b"\x09\x22\x08", b"\x09\x16\x04", b"\x09\x12\x08"} & starts)


if __name__ == "__main__":
    unittest.main()
