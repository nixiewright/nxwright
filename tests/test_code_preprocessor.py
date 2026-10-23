"""The code preprocessor, which turns comfortable code (Editor code written more
freely, such as `if (a == 1) {`) into code the Editor accepts."""
import re
import unittest

from nxwright import NxwrightError
from nxwright.language.code_preprocessor import Owner, preprocess
from nxwright.language.resource_names import ResourceNames


def run(*lines: str) -> list:
    """Returns `lines` preprocessed, numbered from line 1."""
    return preprocess(list(enumerate(lines, start=1)))


class RuleTest(unittest.TestCase):

    def test_spaces_in_expressions(self):
        self.assertEqual(run("sys0 = 1 + 2", "sys0 += 2", "t0.txt = \"a  b\""),
                         ["sys0=1+2", "sys0+=2", 't0.txt="a  b"'])

    def test_control_statements(self):
        self.assertEqual(run("if (sys0 == 1 && sys1 == 2)", "while (sys0 < 3)",
                             "for (sys0 = 0; sys0 < 3; sys0++)"),
                         ["if(sys0==1&&sys1==2)", "while(sys0<3)", "for(sys0=0;sys0<3;sys0++)"])

    def test_brace_on_the_head_line(self):
        self.assertEqual(run("  if (a == 1) {", "    b = 2", "  }"),
                         ["  if(a==1)", "  {", "    b=2", "  }"])
        self.assertEqual(run("while (a) {", "}", "for (a = 0; a < 2; a++) {", "}"),
                         ["while(a)", "{", "}", "for(a=0;a<2;a++)", "{", "}"])

    def test_else_forms(self):
        self.assertEqual(run("if(a==1) {", "} else if (a == 2) {", "} else {", "}"),
                         ["if(a==1)", "{", "}else if(a==2)", "{", "}else", "{", "}"])
        self.assertEqual(run("if(a==1)", "{", "}", "else", "{", "}"),
                         ["if(a==1)", "{", "}else", "{", "}"])
        self.assertEqual(run("if(a==1)", "{", "}", "else if (a == 2)", "{", "}"),
                         ["if(a==1)", "{", "}else if(a==2)", "{", "}"])

    def test_else_after_a_commented_brace(self):
        self.assertEqual(run("if(a==1)", "{", "}  // done", "else {", "}"),
                         ["if(a==1)", "{", "}else  // done", "{", "}"])

    def test_word_starting_with_else_is_not_joined(self):
        self.assertEqual(run("}", "elsewhere = 1"), ["}", "elsewhere=1"])

    def test_commands(self):
        self.assertEqual(run("covx sys0, t0.txt, 0, 0", 'prints "a, b", 0', "printh 00 00 0d",
                             "click b0 , 1", "doevents"),
                         ["covx sys0,t0.txt,0,0", 'prints "a, b",0', "printh 00 00 0d",
                          "click b0,1", "doevents"])

    def test_a_command_keeps_its_spaces_but_by_its_commas(self):
        self.assertEqual(run("cls BLACK", "printh 0d 0a", "vis b0 , 0"),
                         ["cls BLACK", "printh 0d 0a", "vis b0,0"])

    def test_a_commands_arguments_lose_the_spaces_by_their_operators(self):
        # The Nextion Editor refused each of these with the spaces, as
        # "Invalid Page ID" or "Invalid Variables", and compiled them without.
        self.assertEqual(run("page appid & 0x000000FF", "vis b0,sys0 + 1",
                             "fill 0, 0, 10 + 1, 10, 0", "cirs 10,10,5 << 1,0"),
                         ["page appid&0x000000FF", "vis b0,sys0+1", "fill 0,0,10+1,10,0",
                          "cirs 10,10,5<<1,0"])
        # Bytes keep the spaces between them, and a quoted text its own.
        self.assertEqual(run("printh 2b 2d", 'prints "a + b", 0', "lcd_dev fffb 0002 0000 0020"),
                         ["printh 2b 2d", 'prints "a + b",0', "lcd_dev fffb 0002 0000 0020"])

    def test_a_first_word_that_is_no_command(self):
        # The Editor's commands are listed (editor_language.EDITOR_COMMANDS):
        # any other first word is refused, with the Editor's words.
        for line, words in (("somecommand a , b c", "Invalid command"),
                            ("doevent", "Invalid command"), ("Cls BLACK", "Invalid Variables")):
            with self.subTest(line=line), self.assertRaisesRegex(NxwrightError, words):
                run(line)

    def test_command_word_used_as_a_variable(self):
        self.assertEqual(run("pic = 3"), ["pic=3"])

    def test_declarations_are_left_as_written(self):
        self.assertEqual(run("int a = 1, b = 2"), ["int a = 1, b = 2"])

    def test_indentation_comments_and_blank_lines(self):
        self.assertEqual(run("\tsys0 = 1  // keep  this", "", "   ", 'x = "a // b"', "// alone"),
                         ["\tsys0=1  // keep  this", 'x="a // b"', "// alone"])

    def test_spaces_ending_a_line_are_dropped(self):
        # The Nextion Editor's compile drops them: after code, after a
        # comment, on a declaration, on a "}" an "else" joins, and on the line
        # whose "{" moves to its own line.
        self.assertEqual(run("sys0=1 ", "printh 01 02\t", "x=1 // c \t", "int a=1 ",
                             "if (a == 1) {  ", "}  ", "else \t", "{", "}"),
                         ["sys0=1", "printh 01 02", "x=1 // c", "int a=1", "if(a==1)", "{",
                          "}else", "{", "}"])

    def test_picture_and_font_names(self):
        names = ResourceNames(["a", "mono-dark/toast"], ["Impact16"])
        self.assertEqual(preprocess(list(enumerate([
            "pic_toast = @pic(mono-dark/toast)", "t0.font=@font( Impact16 )",
            'x = "@pic(a)" // @pic(zzz)', "int pic_a = @pic(a)"], start=1)), names),
            ["pic_toast=1", "t0.font=0", 'x="@pic(a)" // @pic(zzz)', "int pic_a = 0"])
        with self.assertRaisesRegex(NxwrightError, "line 2: no picture is named zzz"):
            preprocess([(1, "x=1"), (2, "x=@pic(zzz)")], names)
        with self.assertRaisesRegex(NxwrightError, "line 1: @font\\(a\\) needs the app's"):
            run("x=@font(a)")

    def test_hex_constants(self):
        # The Editor wants a hex constant's digits in pairs, a byte each, and
        # no hex in an int's starting value (the vendor's instruction set,
        # rule 1.8). Compiled in the Editor: it also refuses a constant past
        # 32 bits, and a sign on one, after =, ==, or *; it accepts leading
        # zeros, and subtracting one. Text is not code.
        self.assertEqual(run("n0.val = 0x0123", 'n1.val = 0x0000000001', "n2.val = 5 - 0x10",
                             't0.txt = "-0x1"', "int dow=6"),
                         ["n0.val=0x0123", "n1.val=0x0000000001", "n2.val=5-0x10",
                          't0.txt="-0x1"', "int dow=6"])
        for lines, message in ((("sys0=1", "n0.val=0x123"),
                                "line 2: 0x123: the Nextion Editor wants hex digits in pairs"),
                               (("int dow=0x06",),
                                "line 1: an int's starting value cannot be hex, as 0x06 is"),
                               (("n0.val=0x0100000000",),
                                "line 1: 0x0100000000: the Nextion Editor refuses a hex constant "
                                "past 32 bits"),
                               (("n0.val = -0x10",),
                                "line 1: -0x10: the Nextion Editor refuses a sign on a "
                                "hex constant"),
                               (("n0.val=5*-0x10",), "line 1: -0x10: the Nextion Editor "
                                                     "refuses a sign"),
                               (("if (n0.val == -0x10) {", "}"),
                                "line 1: -0x10: the Nextion Editor refuses a sign")):
            with self.subTest(lines=lines):
                with self.assertRaisesRegex(NxwrightError, message):
                    run(*lines)

    def test_hex_constants_written_0X(self):
        # An upper-case X, which the Editor compiled and read as a lower-case
        # one, and refused alike.
        self.assertEqual(run("n0.val = 0X0123"), ["n0.val=0X0123"])
        for line, message in (("n0.val=0X123", "0X123: the Nextion Editor wants hex digits in "
                                               "pairs"),
                              ("n0.val=0X0100000000", "0X0100000000: the Nextion Editor refuses "
                                                      "a hex constant past 32 bits"),
                              ("n0.val=5*-0X10", "-0X10: the Nextion Editor refuses a sign"),
                              ("int dow=0X06", "an int's starting value cannot be hex, as 0X06")):
            with self.subTest(line=line):
                with self.assertRaisesRegex(NxwrightError, "line 1: " + message):
                    run(line)

    def test_labels(self):
        # A label line keeps its comment, as the vendor's example has one. As
        # the Editor compiled them: a goto needs its label in the same event,
        # with the same case; an event has each label once, whatever block it
        # is in; a label may be longer than a name's 14 bytes.
        self.assertEqual(run("up:", "  sys0 += 1", "  goto up  // again", "end: // done",
                             "return", "label_twenty_two_chars:", "goto label_twenty_two_chars"),
                         ["up:", "  sys0+=1", "  goto up  // again", "end: // done", "return",
                          "label_twenty_two_chars:", "goto label_twenty_two_chars"])
        for lines, message in ((("sys0=1", "goto end"),
                                "line 2: goto end: the Nextion Editor finds no label end in "
                                "this event"),
                               (("up:", "goto Up"), "line 2: goto Up: the Nextion Editor finds no "
                                                    "label Up"),
                               (("up:", "sys0=1", "up:"),
                                "line 3: up: the Nextion Editor refuses a label twice in "
                                "one event"),
                               (("if (sys0 == 1) {", "  up:", "}", "up:"),
                                "line 4: up: the Nextion Editor refuses a label twice")):
            with self.subTest(lines=lines):
                with self.assertRaisesRegex(NxwrightError, message):
                    run(*lines)

    def test_the_characters_of_a_label(self):
        # As the Editor compiled them: a label may hold any character but a
        # first digit, and + - * / % = , . [ ] & ' \, which it refused
        # ("the make is invalid"); 120 of them too. In a second probe it
        # compiled { and } in a label too.
        taken = ["ab$", "été", "a(", "a<", "@a", "if", "x" * 120, "a{b", "a}b"]
        lines = [line for label in taken for line in ("%s:" % label, "goto %s" % label)]
        self.assertEqual(run(*lines), lines)
        for label in ("1abc", "a-b", "a+", "a%", "a=", "a,", "a.", "a[", "a&", "a'", "a\\"):
            with self.subTest(label=label):
                with self.assertRaisesRegex(NxwrightError, "line 1: %s: the Nextion Editor "
                                            "refuses this label" % re.escape(label)):
                    run("%s:" % label, "goto %s" % label)
        # It compiled a label starting with a brace too, but nxwright reads a
        # line starting with one as a block's brace, so it refuses it.
        for label in ("{a", "}a", "{", "}"):
            with self.subTest(label=label):
                with self.assertRaisesRegex(NxwrightError, "line 1: %s: a label cannot start "
                                            "with \\{ or \\} in nxwright" % re.escape(label)):
                    run("%s:" % label)
        # It refused a " in a label too, which nxwright reads as a text not
        # closed.
        for label in ('a"b', '"ab'):
            with self.subTest(label=label):
                with self.assertRaisesRegex(NxwrightError, "line 1: a string is not closed"):
                    run("%s:" % label, "goto %s" % label)

    def test_a_form_naming_no_attribute(self):
        # As the Editor compiled them: '&1a&' and '&a-b&' name no attribute
        # ("Invalid Variables"). Its spaces it drops, as nxwright does with
        # every line's: '& val &' is '&val&', in an event of n0.
        for line in ("sys0='&1a&'", "sys0='&a-b&'"):
            with self.subTest(line=line):
                with self.assertRaisesRegex(NxwrightError, "line 1: %s: the Nextion Editor "
                                            "reads no attribute" % re.escape(line)):
                    run(line)
        self.assertEqual(preprocess([(1, "sys0='& v al &'+1")], owner=Owner("n0", 1)),
                         ["sys0='&val&'+1"])

    def test_a_form_with_spaces_where_no_event_holds_the_line(self):
        # Refused as '&val&' is there: the Editor drops the spaces first.
        with self.assertRaisesRegex(NxwrightError, r"line 1: sys0='&val&'\+1: the form '&name&' "
                                                   r"stands for an attribute"):
            run("sys0='& v al &'+1")

    def test_refusals(self):
        for lines, message in ((('x = "open',), "line 1: a string is not closed"),
                               (("sys0 = 1", "x = 1 {"), "line 2: .* can only end")):
            with self.subTest(lines=lines):
                with self.assertRaisesRegex(NxwrightError, message):
                    run(*lines)


if __name__ == "__main__":
    unittest.main()
