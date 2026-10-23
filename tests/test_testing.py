"""nxwright.testing: running a source folder's code, and the test command."""
import contextlib
import io
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.language.code_checks import COMMAND_PARAMETERS
from nxwright.language.resource_names import ResourceNames
from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.source.source_folder import switch_to_nxlang
from nxwright.testing import (EditorMachine, RefusedCode, SourceFolderRunner, UnreadableLine,
                              ValueNotGiven, editor_machine)
from nxwright.testing.editor_machine import EEPROM_SIZE, CompileRefusal
from nxwright.testing.recording import Place, Recorder
from tests.test_project_writer import edit_text
from tests.test_source_folder import SourceFolderTestCase

FIRST_DOWN = "on first.down:\n  if (sys0 == 1) {\n    sys0 = 2\n  }\n"
TWICE = "function twice(n: number) -> number:\n  return n * 2 + bonus\n"


class SourceFolderRunnerTest(SourceFolderTestCase):
    """The small test project's source folder, with code on its first page."""

    def setUp(self):
        super().setUp()
        edit_text(self.source / "pages" / "first.page.toml", 'events = []', 'events = ["down"]')
        (self.source / "pages" / "first.nx").write_text(FIRST_DOWN, encoding="utf-8",
                                                         newline="\n")
        self.runner = SourceFolderRunner(self.source)

    def test_runs_a_page_event(self):
        values = self.runner.run("first", [("first", "down")], {"sys0": 1})
        self.assertEqual((values["sys0"], values["dp"]), (2, 0))
        self.assertEqual(self.runner.run("first", [("first", "down")], {"sys0": 5})["sys0"], 5)

    def test_a_run_stopped_says_where_the_line_is(self):
        # A test run, without the debugger's recording, gives the place too.
        (self.source / "pages" / "first.nx").write_text(
            "on first.down:\n  sys0=1\n  again:\n  goto again\n", encoding="utf-8",
            newline="\n")
        with self.assertRaisesRegex(RefusedCode, r"^pages/first\.nx line 4 \(first\.down\): the "
                                                 r"loop does not end$"):
            self.runner.run("first", [("first", "down")])

    def test_texts_are_cut_to_their_fields_size(self):
        # A text field holds at most its txt_maxl bytes, from the page file or,
        # when the page file leaves it out, from its type's defaults (10 for a
        # text). The second page's field is named after its page.
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "t9"\ntype = "text"\nx = 0\ny = 0\nw = 9\nh = 9\n'
                       'txt_maxl = 3\n\n[[component]]\nname = "t8"\ntype = "text"\nx = 0\n'
                       'y = 0\nw = 9\nh = 9\n')
        with open(self.source / "pages" / "second.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "t7"\ntype = "text"\nx = 0\ny = 0\nw = 9\nh = 9\n'
                       'txt_maxl = 2\n')
        (self.source / "pages" / "first.nx").write_text(
            'on first.down:\n  t9.txt="abcdef"\n  t8.txt="abcdefghijklmn"\n  t8.txt+="z"\n'
            '  second.t7.txt="xyz"\n', encoding="utf-8", newline="\n")
        values = self.runner.run("first", [("first", "down")])
        self.assertEqual((values["t9.txt"], values["t8.txt"], values["second.t7.txt"]),
                         ("abc", "abcdefghij", "xy"))

    def test_an_attribute_is_cut_to_its_m(self):
        # An attribute `X_m` holds the most bytes `X` keeps, as txt_maxl does a
        # txt's: the Editor's simulator kept 8 bytes of a longer path, filter,
        # and folder stored by code, a line break counting its two.
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "xp0"\ntype = "external-picture"\nx = 0\ny = 0\n'
                       'w = 9\nh = 9\npath_m = 8\n\n[[component]]\nname = "cb0"\n'
                       'type = "combo-box"\nx = 0\ny = 0\nw = 90\nh = 30\npath_m = 8\n')
        (self.source / "pages" / "first.nx").write_text(
            'on first.down:\n  xp0.path="sd0/abcdefghij.xi"\n  cb0.path="aaaa\\rbbbb\\rcccc"\n',
            encoding="utf-8", newline="\n")
        values = self.runner.run("first", [("first", "down")])
        self.assertEqual((values["xp0.path"], values["cb0.path"]), ("sd0/abcd", "aaaa\r\nbb"))

    def test_an_attribute_written_to_the_eeprom_takes_its_m(self):
        # wepo writes an attribute `X` as it writes a txt: its `X_m` bytes and
        # one more. The Editor's simulator wrote an animation's path "ab",
        # with path_m 8, as "ab" and seven zero bytes.
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "gm0"\ntype = "gmov"\nx = 0\ny = 0\nw = 9\n'
                       'h = 9\npath_m = 8\n')
        (self.source / "pages" / "first.nx").write_text(
            'on first.down:\n  gm0.path="ab"\n  wepo gm0.path,10\n', encoding="utf-8",
            newline="\n")
        values = self.runner.run("first", [("first", "down")])
        self.assertEqual(values["eeprom accesses"], [("wepo", 10, b"ab" + bytes(7))])

    def test_sizes_given_in_values_add_to_the_page_files(self):
        # An older version of a page may use a field its page file no longer
        # holds; the caller gives that field's size.
        values = self.runner.run("first", [("first", "down")],
                                 {"gone.txt": "", "text limits": {"gone.txt": 2}},
                                 text='on first.down:\n  gone.txt="abc"\n  sys0=1\n')
        self.assertEqual((values["gone.txt"], values["sys0"]), ("ab", 1))

    def test_a_changed_page_file_compiles_again(self):
        self.assertEqual(self.runner.run("first", [("first", "down")], {"sys0": 1})["sys0"], 2)
        (self.source / "pages" / "first.nx").write_text("on first.down:\n  sys0 = 30\n",
                                                         encoding="utf-8", newline="\n")
        self.assertEqual(self.runner.run("first", [("first", "down")], {"sys0": 1})["sys0"], 30)

    def test_a_changed_included_file_compiles_again(self):
        # An include may name any .nx file of the folder, not only those under pages/.
        switch_to_nxlang(self.source)
        (self.source / "values.nx").write_text("const START = 3\n", encoding="utf-8",
                                               newline="\n")
        (self.source / "pages" / "first.nx").write_text(
            'include "../values.nx"\n\non first.down:\n  sys0 = START\n', encoding="utf-8",
            newline="\n")
        runner = SourceFolderRunner(self.source)
        self.assertEqual(runner.run("first", [("first", "down")], {"sys0": 0})["sys0"], 3)
        (self.source / "values.nx").write_text("const START = 40\n", encoding="utf-8",
                                               newline="\n")
        self.assertEqual(runner.run("first", [("first", "down")], {"sys0": 0})["sys0"], 40)

    def test_a_changed_page_file_of_another_page_compiles_again(self):
        # The first page's code sets a field of the second page, cut to the
        # size the second page's file gives it.
        with open(self.source / "pages" / "second.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "t7"\ntype = "text"\nx = 0\ny = 0\nw = 9\nh = 9\n'
                       'txt_maxl = 2\n')
        (self.source / "pages" / "first.nx").write_text(
            'on first.down:\n  second.t7.txt="xyz"\n', encoding="utf-8", newline="\n")
        self.assertEqual(self.runner.run("first", [("first", "down")])["second.t7.txt"], "xy")
        edit_text(self.source / "pages" / "second.page.toml", "txt_maxl = 2", "txt_maxl = 12")
        self.assertEqual(self.runner.run("first", [("first", "down")])["second.t7.txt"], "xyz")

    def test_a_changed_defaults_file_compiles_again(self):
        # A text whose table leaves txt_maxl out has its type's, from defaults.toml.
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "t8"\ntype = "text"\nx = 0\ny = 0\nw = 9\nh = 9\n')
        (self.source / "pages" / "first.nx").write_text(
            'on first.down:\n  t8.txt="abcdefghijklmn"\n', encoding="utf-8", newline="\n")
        self.assertEqual(self.runner.run("first", [("first", "down")])["t8.txt"], "abcdefghij")
        # Every type whose default is 10 changes, the text's among them.
        edit_text(self.source / "defaults.toml", "txt_maxl = 10", "txt_maxl = 4")
        self.assertEqual(self.runner.run("first", [("first", "down")])["t8.txt"], "abcd")

    def test_runs_text_in_place_of_the_page_file(self):
        text = "on first.down:\n  sys0 = 7\n"
        self.assertEqual(self.runner.run("first", [("first", "down")], {"sys0": 0}, text)["sys0"], 7)

    def test_blank_fields_start_empty(self):
        text = "on first.down:\n  t0.txt = t0.txt + \"!\"\n"
        values = self.runner.run("first", [("first", "down")], text=text, blank_fields=True)
        self.assertEqual(values["t0.txt"], "!")

    def test_a_value_not_given_names_the_line_that_reads_it(self):
        # A KeyError too, as before, but its message as written, not quoted.
        text = "on first.down:\n  sys0 = 1\n  t0.txt = t0.txt + \"!\"\n"
        with self.assertRaises(ValueNotGiven) as raised:
            self.runner.run("first", [("first", "down")], {"sys0": 0}, text)
        self.assertIsInstance(raised.exception, KeyError)
        self.assertIsInstance(raised.exception, NxwrightError)
        self.assertEqual(str(raised.exception), "pages/first.nx line 3 (first.down): t0.txt has "
                                                "no value. In a test, give it in the run's values")

    def test_a_refusal_of_the_pages_code_names_its_file(self):
        # As the build names it, so that the file to fix is known.
        (self.source / "pages" / "first.nx").write_text(
            "on first.down:\n  sys0=sys0+\n", encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(NxwrightError, r"^pages/first\.nx line 2: sys0=sys0\+: "):
            SourceFolderRunner(self.source).run("first", [("first", "down")], {"sys0": 0})

    def test_a_refusal_of_nxlang_code_names_its_file(self):
        # The page's own file, or the library file holding the function.
        switch_to_nxlang(self.source)
        (self.source / "pages" / "lib").mkdir()
        (self.source / "pages" / "lib" / "set.nx").write_text(
            "function setNowhere():\n  nowhere.val = 1\n", encoding="utf-8", newline="\n")
        for code, file, line in (
                ("on first.down:\n  nowhere.val = 1\n", "first.nx", 2),
                ('include "lib/set.nx"\n\non first.down:\n  setNowhere()\n', "lib/set.nx", 2)):
            with self.subTest(file=file):
                (self.source / "pages" / "first.nx").write_text(code, encoding="utf-8",
                                                                 newline="\n")
                with self.assertRaisesRegex(NxwrightError,
                                            r"^pages/%s line %d: nowhere is neither"
                                            % (re.escape(file), line)):
                    SourceFolderRunner(self.source).run("first", [("first", "down")])

    def test_refuses_a_missing_page_or_event(self):
        with self.assertRaisesRegex(NxwrightError, "has no page third"):
            self.runner.run("third", [("third", "down")])
        with self.assertRaisesRegex(NxwrightError, "no event first.up"):
            self.runner.run("first", [("first", "up")])

    def test_runs_library_code_in_nxlang(self):
        switch_to_nxlang(self.source)
        (self.source / "pages" / "lib").mkdir()
        (self.source / "pages" / "lib" / "twice.nx").write_text(TWICE, encoding="utf-8",
                                                                newline="\n")
        program = self.source / "program.nx"
        program.write_text("int bonus=1\n" + program.read_text(encoding="utf-8"),
                           encoding="utf-8", newline="\n")
        values = SourceFolderRunner(self.source).run_code("x.val = twice(3)", {"x.val": 0},
                                                          "lib/twice.nx")
        self.assertEqual((values["x.val"], values["bonus"]), (7, 1))

    def test_library_code_needs_nxlang(self):
        with self.assertRaisesRegex(NxwrightError, "does not use nxlang"):
            self.runner.run_code("x.val = 1")

    def test_events_from_text(self):
        events = self.runner.events_from_text("on b0.down:\n  if (sys0 == 1) {\n    sys0 = 2\n  }\n")
        self.assertEqual(events[("b0", "down")], ["if(sys0==1)", "{", "  sys0=2", "}"])

    def test_events_from_text_refuses_a_value_the_editor_refuses(self):
        # Before any event runs, with its line, as the build refuses it.
        with self.assertRaisesRegex(NxwrightError,
                                    r"^line 2: sys0==2: .*\(\"Invalid Variables\"\)$"):
            self.runner.events_from_text("on b0.down:\n  sys0 = = 2\n")


class FileStreamTest(unittest.TestCase):
    """The SD card's file stream, against runs in the Editor's simulator and
    the files they left on its SD card."""

    def test_read_and_write_count_start_within_the_text(self):
        # The simulator sent "cde3456789" and "xycde": write takes 3 bytes of t0
        # from its offset 2, and writes them at the file's position, 0 after
        # open, keeping the rest of the file. read keeps t2's first 2 bytes,
        # then puts 3 bytes of the file after them.
        lines = ['delfile "sd0/t.txt"', 'newfile "sd0/t.txt",10',
                 'file.open("sd0/t.txt")', 't0.txt="0123456789"', "file.write(t0.txt,0,10)",
                 "file.close()",
                 'file.open("sd0/t.txt")', 't0.txt="abcdef"', "file.write(t0.txt,2,3)",
                 "file.close()",
                 'file.open("sd0/t.txt")', "file.read(t1.txt,0,10)", "file.close()",
                 "prints t1.txt,0",
                 'file.open("sd0/t.txt")', 't2.txt="xyzxyz"', "file.read(t2.txt,2,3)",
                 "file.close()", "prints t2.txt,0"]
        values = EditorMachine({"t0.txt": "", "t1.txt": "", "t2.txt": ""}).run(lines)
        self.assertEqual([text for text, _ in values["sent"]], ["cde3456789", "xycde"])
        self.assertEqual(values["file contents"]["sd0/t.txt"], b"cde3456789")

    def test_a_file_has_its_size_and_refuses_what_goes_past_its_end(self):
        # newfile left 5 zero bytes on the SD card. Reading 20 bytes of them and
        # writing 8 were both refused, changing nothing: t1 and t2 kept
        # "newtxt", and the file its zeros. The Nextion Editor's simulator
        # answered such a read 0x01.
        lines = ['newfile "sd0/g.txt",5', 'file.open("sd0/g.txt")', "file.read(t1.txt,0,20)",
                 "file.close()", 'file.open("sd0/g.txt")', 't0.txt="abcdefgh"',
                 "file.write(t0.txt,0,8)", "file.close()", 'file.open("sd0/g.txt")',
                 "file.read(t2.txt,0,20)", "file.close()"]
        values = EditorMachine({"t0.txt": "", "t1.txt": "newtxt", "t2.txt": "newtxt"}).run(lines)
        self.assertEqual(values["file contents"]["sd0/g.txt"], bytes(5))
        self.assertEqual((values["t1.txt"], values["t2.txt"]), ("newtxt", "newtxt"))
        self.assertEqual(values["file errors"],
                         [("read", "sd0/g.txt"), ("write", "sd0/g.txt"), ("read", "sd0/g.txt")])

    def test_a_stream_of_any_name_and_several_at_once(self):
        # The Editor names a new file stream fs0, and an app may have more
        # than one. Each keeps its own open file, as "open file <name>".
        lines = ['fs0.open("sd0/a.txt")', 'log.open("sd0/b.txt")', "fs0.read(t1.txt,0,2)",
                 "log.read(t2.txt,0,2)", "log.close()"]
        values = EditorMachine({"t1.txt": "", "t2.txt": "", "file contents": {
            "sd0/a.txt": b"abcd", "sd0/b.txt": b"wxyz"}}).run(lines)
        self.assertEqual((values["t1.txt"], values["t2.txt"]), ("ab", "wx"))
        self.assertEqual((values["open file fs0"], values["open file log"]), ("sd0/a.txt", None))

    def test_a_stream_with_no_file_open(self):
        # The Editor's simulator answered nothing to a read and a write of a
        # stream never opened, and t1 kept its text. Opened, then closed, a
        # stream does as one never opened, even reading 0 bytes, which would
        # otherwise cut the text at `start`.
        lines = ["fs0.read(t1.txt,0,2)", "fs0.write(t1.txt,0,2)",
                 'fs1.open("sd0/a.txt")', "fs1.close()", "fs1.read(t2.txt,1,0)"]
        values = EditorMachine({"t1.txt": "keep", "t2.txt": "keep", "file contents": {
            "sd0/a.txt": b"abcd"}}).run(lines)
        self.assertEqual((values["t1.txt"], values["t2.txt"]), ("keep", "keep"))
        self.assertEqual(values["file errors"], [("read", None), ("write", None), ("read", None)])

    def test_a_new_file_of_a_size_that_is_not_a_number_or_is_below_0(self):
        # The Editor's simulator answered 0x1B, invalid variable operation, to
        # `newfile "sd0/a.cfg","abc"`, and went on: no file is made. It
        # answered 0x06, invalid file operation, to a size of -1 or -100,
        # making no file either.
        values = EditorMachine({}).run(['newfile "sd0/a.cfg","abc"', 'newfile "sd0/b.cfg",-5'])
        self.assertEqual(values["file errors"], [("newfile", "sd0/a.cfg"), ("newfile", "sd0/b.cfg")])
        self.assertEqual(values.get("file contents", {}), {})
        self.assertEqual(values.get("file commands", []), [])

    def test_twfile_refused_or_recorded(self):
        # The Nextion Editor's simulator refused a path on neither card, as
        # in ram/, and a size of 0 or below, with 0x06, and a size that is no
        # number with 0x1A. Without a screen, a twfile taken is recorded with
        # the other commands, as there is no serial line for its data: it
        # makes no file.
        lines = ['twfile "ram/r.txt",5', 'twfile "r.txt",5', 'twfile "sd0/a.txt",0',
                 'twfile "sd1/b.txt",-1', 'twfile "sd0/c.txt",t0.txt']
        values = EditorMachine({"t0.txt": "abc"}).run(lines + ['twfile "sd0/d.txt",5'])
        self.assertEqual(values["file errors"], [("twfile", "ram/r.txt"), ("twfile", "r.txt"),
                                                 ("twfile", "sd0/a.txt"), ("twfile", "sd1/b.txt"),
                                                 ("twfile", "sd0/c.txt")])
        self.assertEqual(values["other commands"], [("twfile", '"sd0/d.txt"', "5")])
        self.assertEqual(values.get("file contents", {}), {})

    def test_a_read_ends_at_the_first_zero_byte(self):
        values = EditorMachine({"t1.txt": "", "file contents": {"sd0/u.txt": b"ab\0\0cd"}}).run(
            ['file.open("sd0/u.txt")', "file.read(t1.txt,0,6)", "file.close()"])
        self.assertEqual(values["t1.txt"], "ab")

    def test_start_and_count_are_bytes_in_the_encoding(self):
        # In a utf-8 project, the simulator sent b8 a9, then c3 a9, then e6 c3 a9:
        # the middle two bytes of "温" from "温abc", the 2 bytes of "é" from
        # "é温x", and the first byte of "温x" followed by 2 bytes of the file.
        lines = ['newfile "sd0/u.txt",20', 'file.open("sd0/u.txt")', 'v0.txt="温abc"',
                 "file.write(v0.txt,1,2)", "file.close()", 'file.open("sd0/u.txt")',
                 "file.read(v1.txt,0,20)", "file.close()", "prints v1.txt,0",
                 'delfile "sd0/u.txt"', 'newfile "sd0/u.txt",20', 'file.open("sd0/u.txt")',
                 'v0.txt="é温x"', "file.write(v0.txt,0,2)", "file.close()",
                 'file.open("sd0/u.txt")', "file.read(v1.txt,0,20)", "file.close()",
                 "prints v1.txt,0", 'file.open("sd0/u.txt")', 'v2.txt="温x"',
                 "file.read(v2.txt,1,2)", "file.close()", "prints v2.txt,0"]
        values = EditorMachine({"v0.txt": "", "v1.txt": "", "v2.txt": ""},
                               encoding="utf-8").run(lines)
        sent = [text.encode("utf-8", "surrogateescape") for text, _ in values["sent"]]
        self.assertEqual(sent, [b"\xb8\xa9", b"\xc3\xa9", b"\xe6\xc3\xa9"])
        # The SD card's u.txt after the run.
        self.assertEqual(values["file contents"]["sd0/u.txt"], b"\xc3\xa9" + bytes(18))

    def machine(self, **values) -> EditorMachine:
        """A machine with the file stream fs0, its attributes at their
        defaults, and the SD card's file s.txt, "ABCDEFGHIJ"."""
        return EditorMachine(dict({"fs0.val": 0, "fs0.qty": 0, "fs0.en": 0,
                                   "fs0.type": TYPES_BY_NAME["file-stream"],
                                   "file contents": {"sd0/s.txt": b"ABCDEFGHIJ"}}, **values))

    def stream(self, machine: EditorMachine) -> tuple:
        """fs0's val, qty, and en."""
        return tuple(machine.values["fs0." + name] for name in ("val", "qty", "en"))

    def test_reads_and_writes_share_one_position(self):
        # As the Nextion Editor's simulator ran them: each read and write
        # moves the file stream's val, its position, by its count, and code
        # may set it.
        machine = self.machine(**{"t0.txt": "", "t1.txt": "xy"})
        steps = [(['fs0.open("sd0/s.txt")', "fs0.read(t0.txt,0,3)"], "ABC", 3),
                 (["fs0.read(t0.txt,0,3)"], "DEF", 6),
                 (["fs0.val=1", "fs0.read(t0.txt,0,2)"], "BC", 3),
                 (["fs0.write(t1.txt,0,2)"], "BC", 5)]
        for lines, text, position in steps:
            with self.subTest(lines=lines):
                machine.run(lines)
                self.assertEqual((machine.values["t0.txt"], machine.values["fs0.val"]),
                                 (text, position))
        self.assertEqual(machine.values["file contents"]["sd0/s.txt"], b"ABCxyFGHIJ")
        # After a read of 2, a write of 2 goes at 2, and the next read of 2 is
        # past it.
        machine = self.machine(**{"t0.txt": "", "t1.txt": "xy"})
        machine.run(['fs0.open("sd0/s.txt")', "fs0.read(t0.txt,0,2)", "fs0.write(t1.txt,0,2)",
                     "fs0.read(t0.txt,0,2)"])
        self.assertEqual((machine.values["t0.txt"], machine.values["fs0.val"]), ("EF", 6))
        self.assertEqual(machine.values["file contents"]["sd0/s.txt"], b"ABxyEFGHIJ")
        self.assertNotIn("file errors", machine.values)

    def test_qty_and_en_follow_what_is_open(self):
        # Open: en 1, qty the file's size, val 0, again on a second open.
        # Closed: all 0. An open of a file the card lacks closes the file
        # that was open, and is recorded.
        machine = self.machine(**{"t0.txt": "keep"})
        machine.run(['fs0.open("sd0/s.txt")', "fs0.val=4"])
        self.assertEqual(self.stream(machine), (4, 10, 1))
        machine.run(['fs0.open("sd0/s.txt")'])
        self.assertEqual(self.stream(machine), (0, 10, 1))
        machine.run(["fs0.close()"])
        self.assertEqual(self.stream(machine), (0, 0, 0))
        machine.run(['fs0.open("sd0/s.txt")', "fs0.val=3", 'fs0.open("sd0/none.txt")',
                     "fs0.read(t0.txt,0,2)"])
        self.assertEqual(self.stream(machine), (0, 0, 0))
        self.assertEqual(machine.values["t0.txt"], "keep")
        self.assertEqual(machine.values["file errors"], [("open", "sd0/none.txt"),
                                                         ("read", None)])
        # A path a test says exists, with no bytes, is a file of 0 bytes.
        machine = self.machine(existing=["sd0/empty.txt"])
        machine.run(['fs0.open("sd0/empty.txt")'])
        self.assertEqual(self.stream(machine), (0, 0, 1))

    def test_past_the_end_from_the_position(self):
        # A read or a write past the end, from val, does nothing, and is
        # recorded. A read past the end cuts its text after its first start +
        # count bytes, as the Nextion Editor's simulator left "IJ" as "I".
        # val set past the end is taken.
        machine = self.machine(**{"t0.txt": "", "t1.txt": "xy"})
        machine.run(['fs0.open("sd0/s.txt")', "fs0.val=8", "fs0.read(t0.txt,0,2)"])
        self.assertEqual((machine.values["t0.txt"], machine.values["fs0.val"]), ("IJ", 10))
        machine.run(["fs0.read(t0.txt,0,1)"])
        self.assertEqual((machine.values["t0.txt"], machine.values["fs0.val"]), ("I", 10))
        machine.run(["fs0.val=9", "fs0.write(t1.txt,0,2)", "fs0.val=100"])
        self.assertEqual(machine.values["fs0.val"], 100)
        self.assertEqual(machine.values["file contents"]["sd0/s.txt"], b"ABCDEFGHIJ")
        self.assertEqual(machine.values["file errors"], [("read", "sd0/s.txt"),
                                                         ("write", "sd0/s.txt")])

    def test_a_position_below_0_is_refused(self):
        # The Nextion Editor's simulator answered 0x1C, and kept val.
        machine = self.machine()
        machine.run(['fs0.open("sd0/s.txt")', "fs0.val=3", "fs0.val=-1"])
        self.assertEqual(machine.values["fs0.val"], 3)
        self.assertEqual(machine.values["refusals"], [(0x1C, "fs0.val=-1")])

    def test_a_negative_start_or_count_is_not_modelled(self):
        # No probe tried one.
        for line in ("fs0.read(t0.txt,0,-1)", "fs0.read(t0.txt,-1,2)"):
            with self.subTest(line=line), \
                    self.assertRaisesRegex(RefusedCode, "a negative start or count"):
                self.machine(**{"t0.txt": "ab"}).run(['fs0.open("sd0/s.txt")', line])

    def test_find_is_taken_and_changes_nothing(self):
        # As the Nextion Editor's simulator showed, of a file the card has or
        # lacks, with a file open or not.
        machine = self.machine()
        machine.run(['fs0.find("sd0/s.txt")', 'fs0.open("sd0/s.txt")', "fs0.val=7",
                     'fs0.find("sd0/none.txt")'])
        self.assertEqual(self.stream(machine), (7, 10, 1))
        self.assertNotIn("file errors", machine.values)


class RdfileTest(unittest.TestCase):
    """rdfile, against what the Nextion Editor's simulator sent for a file
    holding "hello123"."""

    def sent(self, line: str) -> dict:
        return EditorMachine({"file contents": {"sd0/rd.txt": b"hello123"}}).run([line])

    def test_it_sends_the_bytes_then_the_crc(self):
        cases = [("0,5,0", b"hello"), ("2,3,0", b"llo"), ("0,5,1", b"hello\xf6\x34"),
                 ("0,5,10", b"hello\x2b\x54\x1a\xf6"), ("0,0,0", b"\x08\x00\x00\x00"),
                 ("0,0,1", b"\x08\x00\x00\x00\x02\x44"),
                 ("0,0,10", b"\x08\x00\x00\x00\xe5\xc2\x48\x0e"),
                 # Another crc sends zero bytes: 2 below 10, else 4.
                 ("0,5,2", b"hello\x00\x00"), ("0,2,3", b"he\x00\x00"),
                 ("0,2,11", b"he\x00\x00\x00\x00"), ("0,2,-1", b"he\x00\x00\x00\x00")]
        for arguments, data in cases:
            with self.subTest(arguments=arguments):
                values = self.sent('rdfile "sd0/rd.txt",%s' % arguments)
                self.assertEqual(values["sent"], [("rdfile", data)])
                self.assertEqual(values["file contents"]["sd0/rd.txt"], b"hello123")

    def test_a_missing_file_or_a_range_outside_it_sends_nothing(self):
        for line in ('rdfile "sd0/rd.txt",6,5,0', 'rdfile "sd0/rd.txt",8,0,0',
                     'rdfile "sd0/rd.txt",9,0,0', 'rdfile "sd0/none.txt",0,5,0'):
            with self.subTest(line=line):
                values = self.sent(line)
                self.assertNotIn("sent", values)
                self.assertEqual(values["file errors"], [("rdfile", line[8:line.index('",')])])

    def test_a_negative_offset_or_count_is_not_modelled(self):
        for arguments in ("-1,2,0", "0,-1,0"):
            with self.subTest(arguments=arguments), self.assertRaisesRegex(
                    RefusedCode, "a negative offset or count is not modelled"):
                self.sent('rdfile "sd0/rd.txt",%s' % arguments)


class TextLimitTest(unittest.TestCase):

    def test_a_text_is_cut_to_its_fields_size_in_bytes(self):
        # The screen keeps at most a field's txt_maxl bytes of a text. A text
        # padded past 1024 characters, in a field of 1024 bytes, kept its first
        # 1024 in the simulator. In utf-8, "é" is 2 bytes, so 3 bytes keep "aé".
        limits = {"t0.txt": 3}
        values = EditorMachine({"t0.txt": "", "text limits": limits}, encoding="utf-8").run(
            ['t0.txt="aéb"'])
        self.assertEqual(values["t0.txt"], "aé")
        values = EditorMachine({"t0.txt": "ab", "text limits": limits}).run(['t0.txt+="cd"'])
        self.assertEqual(values["t0.txt"], "abc")


class StringEscapeTest(unittest.TestCase):

    def test_escapes_are_what_the_screen_stores(self):
        # The simulator sent 61 0d 0a 62 for "a\rb", whose strlen and btlen were
        # both 4, then 78 22 79 for "x\"y" and 70 5c 71 for "p\\q".
        values = EditorMachine({"v0.txt": "", "n0.val": 0, "n1.val": 0}).run(
            ['prints "a\\rb",0', 'v0.txt="a\\rb"', "strlen v0.txt,n0.val",
             "btlen v0.txt,n1.val", 'prints "x\\"y",0', 'prints "p\\\\q",0'])
        self.assertEqual([text for text, _ in values["sent"]], ["a\r\nb", 'x"y', "p\\q"])
        self.assertEqual((values["n0.val"], values["n1.val"]), (4, 4))

    def test_an_escape_the_screen_does_not_read_is_refused(self):
        # The Editor's simulator answered "a\nb", "a\tb", and "a\qb" typed with
        # 0x20, and its compile refused "a\qb" in an event.
        for escape in ("n", "t", "q"):
            with self.subTest(escape), self.assertRaises(CompileRefusal) as raised:
                EditorMachine({}).run(['prints "a\\%sb",0' % escape])
            self.assertEqual(raised.exception.code, 0x20)


class WaveformCommandTest(unittest.TestCase):

    def test_points_and_clearings_are_recorded_in_order(self):
        values = EditorMachine({"chart.id": 4, "y.val": 120}).run(
            ["cle chart.id,255", "add chart.id,0,y.val", "add 4,1,30"])
        self.assertEqual(values["waveform"], [("cle", 4, 255), ("add", 4, 0, 120), ("add", 4, 1, 30)])

    def test_arithmetic_in_their_numbers(self):
        # The Editor's simulator ran `add wave.id,1,99-n.val`, drawing its
        # points; `cle` is taken to read its numbers alike.
        values = EditorMachine({"chart.id": 4, "n.val": 9}).run(
            ["add chart.id,1,99-n.val", "add chart.id,n.val-9,n.val*2", "cle chart.id,n.val-8"])
        self.assertEqual(values["waveform"], [("add", 4, 1, 90), ("add", 4, 0, 18), ("cle", 4, 1)])


class ArithmeticInCommandsTest(unittest.TestCase):

    def test_covx_and_newfile_work_out_their_numbers(self):
        # The Editor's simulator showed "12" and "1,234" with n.val 5, and ran
        # the newfile; it refuses arithmetic in covx's source (the build).
        values = EditorMachine({"n.val": 5, "t0.txt": "", "t1.txt": "",
                                "file contents": {}}).run(
            ["covx 1234,t0.txt,n.val-3,0", "covx 1234,t1.txt,0,n.val-4",
             'newfile "sd0/a.txt",n.val+1'])
        self.assertEqual((values["t0.txt"], values["t1.txt"]), ("12", "1,234"))
        self.assertEqual(values["file contents"]["sd0/a.txt"], bytes(6))


class CovxLengthTest(unittest.TestCase):

    def run_covx(self, value: int, length: int, form: int) -> str:
        values = EditorMachine({"n0.val": value, "t0.txt": "", "text limits": {"t0.txt": 40}}).run(
            ["covx n0.val,t0.txt,%d,%d" % (length, form)])
        return values["t0.txt"]

    def test_as_long_as_the_editors_simulator_made_them(self):
        # As it made them: decimal, and with commas, stop at 15 characters, a
        # minus sign beyond them; hexadecimal stops at 8, the number's 32
        # bits.
        self.assertEqual(self.run_covx(5, 20, 0), "0" * 14 + "5")
        self.assertEqual(self.run_covx(-5, 16, 0), "-" + "0" * 14 + "5")
        self.assertEqual(self.run_covx(1234567, 20, 1), "0000001,234,567")
        self.assertEqual(self.run_covx(-1234567, 20, 1), "-0000001,234,567")
        self.assertEqual(self.run_covx(-1234567, 4, 1), "-1,23")
        self.assertEqual(self.run_covx(5, 12, 2), "00000005")
        self.assertEqual(self.run_covx(-1, 10, 2), "FFFFFFFF")
        self.assertEqual(self.run_covx(0x12345678, 16, 2), "12345678")
        self.assertEqual(self.run_covx(0x12345678, 6, 2), "123456")


class PowerOnDefaultTest(unittest.TestCase):

    def test_dims_and_bauds_set_the_current_value_too(self):
        # As the vendor's instruction set says: dims=32 sets the current
        # backlight to 32% and saves it as the power-on default, as the
        # Nextion Editor's simulator did. bauds does so for the baud rate,
        # which that simulator cannot show, as it keeps baud at 9600 whatever
        # code sets. dim and baud save nothing.
        values = EditorMachine({"dim": 100, "dims": 100, "baud": 9600, "bauds": 9600}).run(
            ["dims=32", "bauds=38400"])
        self.assertEqual((values["dim"], values["dims"], values["baud"], values["bauds"]),
                         (32, 32, 38400, 38400))
        values = EditorMachine({"dim": 100, "dims": 100}).run(["dim=50"])
        self.assertEqual((values["dim"], values["dims"]), (50, 100))


class CrcTest(unittest.TestCase):
    """The CRC commands, a Modbus CRC16 that `crcval` reads, as the Nextion
    Editor's simulator ran them."""

    NINE = "crcputh 31 32 33 34 35 36 37 38 39"     # "123456789"

    def crcval_after(self, lines: list, **values) -> int:
        """Returns `crcval` after `lines`, given `values` by name, such as
        t="abc" for `t.txt`."""
        start = {name + (".txt" if isinstance(value, str) else ".val"): value
                 for name, value in values.items()}
        return EditorMachine(start).run(lines)["crcval"]

    def test_the_check_value(self):
        # CRC-16/MODBUS gives 0x4B37 for "123456789".
        self.assertEqual(self.crcval_after(["crcrest 1,0xFFFF", self.NINE]), 0x4B37)

    def test_the_start_value_is_reflected(self):
        # The start value's 16 bits in the opposite order, as Modbus CRC16
        # works on them; a negative one is taken as its low 16 bits.
        self.assertEqual(self.crcval_after(["crcrest 1,0x1234"]), 0x2C48)
        self.assertEqual(self.crcval_after(["crcrest 1,0x0001"]), 0x8000)
        self.assertEqual(self.crcval_after(["crcrest 1,0x1234", self.NINE]), 0xF569)
        self.assertEqual(self.crcval_after(["crcrest 1,-2"]), 0x7FFF)

    def test_a_start_past_16_bits_is_ignored(self):
        # The CRC goes on from 0xBB3D, which `crcrest 1,0` and "123456789" left.
        values = EditorMachine({}).run(["crcrest 1,0", self.NINE, "crcrest 1,0x010000",
                                        self.NINE])
        self.assertEqual(values["crcval"], 0xED7B)
        self.assertEqual(values["refusals"], [(0x1A, "crcrest 1,0x010000")])

    def test_another_type_turns_the_crc_off(self):
        self.assertEqual(self.crcval_after(["crcrest 1,0xFFFF", "crcrest 2,0xFFFF",
                                            "crcputh 31 32 33"]), -1)
        self.assertEqual(self.crcval_after(["crcrest 0,0xFFFF"]), -1)

    def test_off_in_a_test_that_does_not_give_crcval(self):
        self.assertNotIn("crcval", EditorMachine({}).run(["crcputh 31 32 33"]))

    def test_crcputs_adds_the_bytes_prints_sends(self):
        # A text's bytes, and a number's 4 bytes, low byte first:
        # 875770417 is 0x34333231, the bytes of "1234".
        rest = "crcrest 1,0xFFFF"
        self.assertEqual(self.crcval_after([rest, "crcputs t.txt,0"], t="123456789"), 0x4B37)
        self.assertEqual(self.crcval_after([rest, 'crcputs "123456789",0']), 0x4B37)
        self.assertEqual(self.crcval_after([rest, "crcputs n.val,0"], n=875770417), 0x30BA)
        self.assertEqual(self.crcval_after([rest, "crcputs 875770417,0"]), 0x30BA)

    def test_crcputs_with_a_length(self):
        rest = "crcrest 1,0xFFFF"
        self.assertEqual(self.crcval_after([rest, "crcputs n.val,2"], n=875770417), 0xF595)
        self.assertEqual(self.crcval_after([rest, "crcputs t.txt,3"], t="abc"), 0x5749)
        self.assertEqual(self.crcval_after([rest, "crcputs t.txt,2"], t="abc"), 0xC9A9)
        # Past the value's bytes, nothing, where prints sends what there is.
        self.assertEqual(self.crcval_after([rest, "crcputs t.txt,4"], t="abc"), 0xFFFF)
        self.assertEqual(self.crcval_after([rest, "crcputs n.val,5"], n=875770417), 0xFFFF)

    def test_the_crc_goes_on_across_commands(self):
        self.assertEqual(self.crcval_after(["crcrest 1,0xFFFF", "crcputh 31 32 33",
                                            'crcputs "456789",0']), 0x4B37)

    def test_crcputh_reads_either_case(self):
        self.assertEqual(self.crcval_after(["crcrest 1,0xFFFF", "crcputh 0d 0a"]), 0x2785)

    def test_crcputh_refuses_what_is_not_hexadecimal(self):
        # The Nextion Editor's simulator added 0x10 for "3G", by no rule found.
        with self.assertRaisesRegex(RefusedCode, "crcputh 3G: not hexadecimal"):
            EditorMachine({}).run(["crcrest 1,0xFFFF", "crcputh 3G"])

    def test_a_wrong_number_of_arguments_stops_the_run(self):
        # As the Nextion Editor's compile refused each, and its simulator
        # answered each typed 0x1E (COMMAND_PARAMETERS).
        for line in ("crcrest 1", "crcrest 1,0xFFFF,2", "crcputs t.txt", "crcputs t.txt,0,1",
                     "crcputu 0", "crcputu 0,1,2"):
            with self.subTest(line=line), self.assertRaisesRegex(CompileRefusal,
                                                                 "takes 2 parameters"):
                EditorMachine({"t.txt": "abc", "crcval": 0xFFFF}).run([line])

    def test_code_cannot_change_crcval(self):
        self.assertEqual(self.crcval_after(["crcrest 1,0x1234", "crcval=5"]), 0x2C48)

    # The buffer of protocol reparse mode as the probe filled it.
    BUFFER = {"recmod": 1, "serial buffer": b"get 1\xff\xff\xff", "crcval": 0xFFFF}

    def test_crcputu_adds_bytes_of_the_buffer(self):
        # `crcputu start,count`: the CRCs the Nextion Editor's simulator gave.
        cases = [(["crcputu 0,3"], 26859), (["crcputu 2,4"], 52815), (["crcputu 0,8"], 52358),
                 (["crcputu 5,3"], 16448), (["crcputu 7,1"], 255), (["crcputu 0,1"], 43774),
                 (["crcputu 0,3", "crcputu 3,2"], 2711)]
        for lines, crc in cases:
            with self.subTest(lines=lines):
                values = EditorMachine(dict(self.BUFFER)).run(lines)
                self.assertEqual(values["crcval"], crc)
                self.assertEqual(values["serial buffer"], b"get 1\xff\xff\xff")

    def test_crcputu_adds_nothing_outside_the_buffer_or_the_mode(self):
        # A count below 1, or one running past the buffer's end, adds nothing
        # and answers nothing. Neither does crcputu while recmod is 0.
        for line, recmod in (("crcputu 0,0", 1), ("crcputu 0,-1", 1), ("crcputu 6,5", 1),
                             ("crcputu 8,1", 1), ("crcputu 0,9", 1), ("crcputu 0,3", 0)):
            with self.subTest(line=line, recmod=recmod):
                values = EditorMachine(dict(self.BUFFER, recmod=recmod)).run([line])
                self.assertEqual(values["crcval"], 0xFFFF)
                self.assertNotIn("refusals", values)


class AttributeTheScreenDoesNotHoldTest(unittest.TestCase):
    """A gauge's wid, which an Intelligent screen does not hold: code reads
    it as 0 given the screen's series, and as its value in a test run,
    which has none."""

    def test_given_the_series_or_not(self):
        start = {"z0.wid": 2, "z0.type": TYPES_BY_NAME["gauge"], "n0.val": 7}
        self.assertEqual(EditorMachine(dict(start), series="P").run(["n0.val=z0.wid"])["n0.val"], 0)
        self.assertEqual(EditorMachine(dict(start)).run(["n0.val=z0.wid"])["n0.val"], 2)


class RecordedCommandTest(unittest.TestCase):
    """Commands whose effect lies outside the values: drawing, and what
    reaches outside the screen."""

    def test_what_is_painted_is_recorded_in_order(self):
        values = EditorMachine({"n0.val": 7, "t0.txt": "hi"}).run([
            "cls WHITE", "fill 1,2,n0.val,4,RED", "line 0,0,10,n0.val+1,31",
            'xstr 0,0,100,30,0,BLACK,WHITE,1,1,1,t0.txt', "ref_stop", "ref t0", "ref_star",
            "cirs 50,50,10,GREEN", "pic 3,4,0"])
        self.assertEqual(values["painted"], [
            ("cls", 65535), ("fill", 1, 2, 7, 4, 63488), ("line", 0, 0, 10, 8, 31),
            ("xstr", 0, 0, 100, 30, 0, 0, 65535, 1, 1, 1, "hi"), ("ref_stop",), ("ref", "t0"),
            ("ref_star",), ("cirs", 50, 50, 10, 2016), ("pic", 3, 4, 0)])

    def test_what_reaches_outside_the_screen_is_recorded(self):
        values = EditorMachine({"n0.val": -2, "t0.txt": "ab", "dp": 1, "pio3": 1}).run([
            "wepo n0.val,0", 'wepo "x",4', "wepo t0.txt,8", "repo n0.val,4", "print t0.txt",
            "get n0.val", "sendme", "rept 0,2", "cfgpio 3,0,b0", "pio2=pio3", "randset 1,6",
            "touch_j", "rest"])
        self.assertEqual(values["eeprom"][:11], bytes([254, 255, 255, 255]) + b"x\0\0\0ab\0")
        self.assertEqual(values["n0.val"], 120)     # "x" and its zero, read as a number
        self.assertEqual(values["sent"], [("ab", 0)])
        self.assertEqual(values["replies"], [("get", 120), ("sendme", 1),
                                             ("rept", bytes([254, 255]))])
        self.assertEqual(values["gpio"], [("cfgpio", 3, 0, "b0"), ("read", "pio3", 1),
                                          ("write", "pio2", 1)])
        self.assertEqual((values["rand range"], values["other commands"], values["reset"]),
                         ((1, 6), [("touch_j",)], 1))

    def test_a_test_gives_the_serial_buffer(self):
        # The buffer of protocol reparse mode (serial_buffer.py), given with
        # recmod 1, as a screen has it while the mode is on.
        values = EditorMachine({"recmod": 1, "serial buffer": b" 1ABC", "n0.val": 0,
                                "n1.val": 0, "n2.val": 0, "t0.txt": "newtxt"}).run([
            "n0.val=usize", "n1.val=u[2]", "ucopy n2.val,0,2,0", "ucopy t0.txt,2,2,2",
            "udelete 3"])
        self.assertEqual((values["n0.val"], values["n1.val"], values["n2.val"], values["t0.txt"],
                          values["serial buffer"]), (5, 65, 0x3120, "neAB", b"BC"))
        self.assertNotIn("other commands", values)

    def test_the_end_of_the_mode_empties_the_serial_buffer(self):
        # As in a simulation: code setting recmod to 0 empties the buffer
        # given, so that the mode starting again finds it empty.
        values = EditorMachine({"recmod": 1, "serial buffer": b"AB", "n0.val": 5}).run([
            "recmod=0", "recmod=1", "n0.val=usize"])
        self.assertEqual((values["n0.val"], values["serial buffer"]), (0, b""))

    def test_the_serial_buffer_read_while_the_mode_is_off(self):
        # Each read is ignored, with 0x1A, and gives 0, as the Nextion
        # Editor's simulator answered. ucopy copies nothing, as a number of
        # 12345 kept it there, and udelete deletes nothing alike.
        values = EditorMachine({"recmod": 0, "serial buffer": b"AB", "n0.val": 5,
                                "n1.val": 12345}).run([
            "n0.val=usize", "udelete 1", "ucopy n1.val,0,2,0"])
        self.assertEqual((values["n0.val"], values["refusals"], values["serial buffer"],
                          values["n1.val"]), (0, [(0x1A, "usize")], b"AB", 12345))

    def test_lcd_dev_is_recorded(self):
        # Undocumented, it compiled with one argument on every series: a fix
        # of the touch's offsets, which a user's program.s held for one
        # version of a screen.
        values = EditorMachine({}).run(["lcd_dev fffb 0002 0000 0020"])
        self.assertEqual(values["other commands"], [("lcd_dev", "fffb 0002 0000 0020")])

    def test_the_editors_undocumented_commands_are_recorded(self):
        # Each compiled in the Editor 3.1.73, which documents none of them.
        values = EditorMachine({}).run(["zstr 1,2,3,4,5", "showqq", "sets 1,2"])
        self.assertEqual(values["other commands"], [("zstr", "1", "2", "3", "4", "5"),
                                                    ("showqq",), ("sets", "1", "2")])

    def test_words_no_series_takes_are_no_commands(self):
        # The Editor's compile refused them on every series.
        for line in ("movelayer b0,t0", "setlevel b0,1", 'dir "sd0/"'):
            with self.subTest(line=line), self.assertRaisesRegex(UnreadableLine,
                                                                 "not code in strict "
                                                                 "Nextion syntax"):
                EditorMachine({}).run([line])

    def test_holding_the_serial_line_is_recorded(self):
        # A test has no serial line for com_stop to hold.
        values = EditorMachine({}).run(["com_stop", "com_star"])
        self.assertEqual(values["other commands"], [("com_stop",), ("com_star",)])

    def test_a_folder_renamed_in_memory_is_recorded(self):
        # A test's memory holds no folders, so redir is kept, as refile is.
        values = EditorMachine({}).run(['redir "sd0/old/","sd0/new/"'])
        self.assertEqual(values["file commands"], [("redir", "sd0/old/", "sd0/new/")])
        self.assertNotIn("other commands", values)

    def test_touch_switches_are_recorded(self):
        values = EditorMachine({}).run(["tsw b0,0", "tsw 255,1"])
        self.assertEqual((values["touch b0"], values["touch 255"]), (0, 1))


class ParsingTest(unittest.TestCase):

    def test_code_run_again_is_not_parsed_again(self):
        lines = ["if(sys0==0)", "{", "sys0=sys0+1", "}"]
        editor_machine._parsed.cache_clear()
        self.assertEqual(EditorMachine({"sys0": 0}).run(lines)["sys0"], 1)
        self.assertEqual(EditorMachine({"sys0": 0}).run(list(lines))["sys0"], 1)
        info = editor_machine._parsed.cache_info()
        self.assertEqual((info.misses, info.hits), (1, 1))

    def test_a_minus_after_an_operator_is_a_sign(self):
        # Compiled and run in the Editor's simulator.
        for line, value in (("n0.val=2*-16", -32), ("n0.val=5+-16", -11), ("n0.val=5--16", 21)):
            with self.subTest(line=line):
                self.assertEqual(EditorMachine({"n0.val": 0}).run([line])["n0.val"], value)

    def test_text_subtraction_written_out(self):
        # The vendor's instruction set, operators 2.4 and 2.5: t0.txt=t0.txt-3
        # removes three characters from the end, as t0.txt-=3 does. Its first
        # operand must be the text itself.
        for line in ("t0.txt=t0.txt-3", "t0.txt-=3", "t0.txt=t0.txt-n0.val"):
            with self.subTest(line=line):
                values = EditorMachine({"t0.txt": "abcdef", "n0.val": 3}).run([line])
                self.assertEqual(values["t0.txt"], "abc")
        with self.assertRaisesRegex(RefusedCode, "the text itself"):
            EditorMachine({"t0.txt": "abcdef", "t1.txt": "xyz"}).run(["t0.txt=t1.txt-1"])
        # A minus within a quoted text subtracts nothing.
        for line, text in (('t0.txt=t0.txt+"-"', "abcdef-"), ('t0.txt="a-b"', "a-b")):
            with self.subTest(line=line):
                self.assertEqual(EditorMachine({"t0.txt": "abcdef"}).run([line])["t0.txt"], text)

    def test_hex_constants(self):
        # The vendor's instruction set, rule 1.8, with its examples: hex digits
        # in pairs, a byte each, in assignments, arithmetic, and conditions.
        lines = ["n0.val=0x1234", "n1.val=sys0^0x8005", "if(n0.val==0x1234)", "{", "n2.val=1",
                 "}"]
        values = EditorMachine({"sys0": 1, "n0.val": 0, "n1.val": 0, "n2.val": 0}).run(lines)
        self.assertEqual([values["n%d.val" % index] for index in range(3)], [0x1234, 0x8004, 1])
        # Compiled and run in the Editor's simulator: a constant is its 32
        # bits, leading zeros or not, and may be subtracted.
        for line, value in (("n0.val=0x7FFFFFFF", 2147483647), ("n0.val=0x80000000", -2147483648),
                            ("n0.val=0xFFFFFFFF", -1), ("n0.val=0x0000000001", 1), ("n0.val=0X1F", 31),
                            ("n0.val=5-0x10", -11)):
            with self.subTest(line=line):
                self.assertEqual(EditorMachine({"n0.val": 0}).run([line])["n0.val"], value)
        # The Editor refuses digits not in pairs (rule 1.8), and, in the same
        # session, a constant past 32 bits and a sign on one.
        for line, message in (("n0.val=0x123", "0x123: the Nextion Editor wants hex "
                                               "digits in pairs"),
                              ("n0.val=0x0100000000", "0x0100000000: the Nextion Editor refuses a "
                                                      "hex constant past 32 bits"),
                              ("n0.val=-0x10", "-0x10: the Nextion Editor refuses a sign on a "
                                               "hex constant"),
                              ("n0.val=5*-0x10", "-0x10: the Nextion Editor refuses a sign"),
                              ("if(n0.val==-0x10)", "-0x10: the Nextion Editor refuses a sign")):
            with self.subTest(line=line), self.assertRaisesRegex(RefusedCode, message):
                EditorMachine({"n0.val": 0}).run([line, "{", "}"] if line.startswith("if") else [line])


class CallTest(unittest.TestCase):
    """call, which runs one of the project's macros (source/macros_source.py),
    as a probe ran macros in the Editor's simulator."""

    def machine(self, macros: dict, events: dict = None) -> EditorMachine:
        """A machine given `macros`, {name: Editor code lines}, and `events`."""
        return EditorMachine({"sys0": 0}, events,
                             macros={name: (lines, None) for name, lines in macros.items()})

    @staticmethod
    def sent(machine: EditorMachine) -> list:
        """What the machine's code sent with printh."""
        return [text for _, text in machine.values.get("sent", [])]

    def test_a_return_ends_the_macro_alone(self):
        # The probe's event ran `call ret` then `printh 4F`, `ret` printing
        # 4D then returning: 4D 4F. Called from another macro, alike.
        macros = {"ret": ["printh 4D", "return", "printh 4E"], "outer": ["call ret", "printh 50"]}
        machine = self.machine(macros)
        machine.run(["call ret", "printh 4F"])
        machine.run_instruction("call outer")
        self.assertEqual(self.sent(machine), ["4D", "4F", "4D", "50"])

    def test_a_macros_labels_are_its_own(self):
        machine = self.machine({"jumps": ["goto later", "printh 4D", "later:", "printh 4E"]})
        machine.run(["call jumps", "goto later", "printh 41", "later:", "printh 42"])
        self.assertEqual(self.sent(machine), ["4E", "42"])

    def test_a_macro_calling_itself_stops_at_the_ninth(self):
        # The probe's macro calling itself printed 4D nine times, then
        # stopped, though it would have stopped itself at twelve.
        machine = self.machine({"again": ["printh 4D", "sys0++", "if(sys0<12)", "{",
                                          "  call again", "}"]})
        with self.assertRaisesRegex(RefusedCode, "Endless loop was detected"):
            machine.run_instruction("call again")
        self.assertEqual(self.sent(machine), ["4D"] * 9)

    def test_its_comments_and_a_blank_line(self):
        # Its comment, marked, as the build writes it first, and one after
        # code. The build drops a blank line, which the machine skips too.
        machine = self.machine({"noted": ["// ### Says M", "", "printh 4D// the M"]})
        machine.run(["call noted"])
        self.assertEqual(self.sent(machine), ["4D"])

    def test_a_name_with_a_space(self):
        machine = self.machine({"my name": ["printh 4D"]})
        machine.run(["call my name"])
        self.assertEqual(self.sent(machine), ["4D"])

    def test_a_macro_the_project_lacks_is_ignored(self):
        # Typed on the serial line, the Editor's simulator answered nothing
        # to it. The build refuses one in code.
        machine = self.machine({"printm": ["printh 4D"]})
        machine.run_instruction("call nosuch")
        self.assertEqual(self.sent(machine), [])

    def test_nine_levels_and_no_more(self):
        # A chain of twelve macros ran nine from the serial line, which is no
        # level of its own; from a touched event, the event and eight.
        chain = {"m%d" % number: ["printh %02X" % number]
                 + (["call m%d" % (number + 1)] if number < 12 else [])
                 for number in range(1, 13)}
        for start, expected in ((lambda machine: machine.run_instruction("call m1"),
                                 ["%02X" % number for number in range(1, 10)]),
                                (lambda machine: machine.run(["printh 41", "call m1"]),
                                 ["41"] + ["%02X" % number for number in range(1, 9)])):
            machine = self.machine(chain)
            with self.assertRaisesRegex(RefusedCode, "Endless loop was detected"):
                start(machine)
            self.assertEqual(self.sent(machine), expected)

    def test_clicks_count_with_macros(self):
        # The probe's event, macro, and click in turn ran nine. Here an event
        # clicks b1, whose event calls a chain of macros.
        events = {("b1", "down"): ["printh 42", "call m1"]}
        chain = {"m%d" % number: ["printh %02X" % number, "call m%d" % (number + 1)]
                 for number in range(1, 12)}
        machine = self.machine(chain, events)
        with self.assertRaisesRegex(RefusedCode, "Endless loop was detected"):
            machine.run(["printh 41", "click b1,1"])
        self.assertEqual(self.sent(machine),
                         ["41", "42"] + ["%02X" % number for number in range(1, 8)])

    def test_clicks_alone_stop_at_the_tenth(self):
        # An event clicking itself, which ran on before.
        machine = self.machine({}, {("b0", "down"): ["printh 41", "click b0,1"]})
        with self.assertRaisesRegex(RefusedCode, "Endless loop was detected"):
            machine.run_instruction("click b0,1")
        self.assertEqual(self.sent(machine), ["41"] * 9)


class ComponentNumberTest(unittest.TestCase):
    """click, vis, tsw, and ref given a component's number, its ID, as a
    probe ran them in the Editor's simulator: page0 is 0, its text t0 1, and
    its button b0 2. A macro gives numbers alone there."""

    def machine(self, values: dict = None) -> EditorMachine:
        events = {("page0", "down"): ["printh 50"], ("b0", "down"): ["printh 41"]}
        return EditorMachine(dict({"sys0": 0}, **(values or {})), events, "page0",
                             components=["page0", "t0", "b0"])

    @staticmethod
    def sent(machine: EditorMachine) -> list:
        return [text for _, text in machine.values.get("sent", [])]

    def test_each_reaches_the_component_of_that_id(self):
        machine = self.machine()
        machine.run(["click 2,1", "click 0,1", "vis 1,0", "tsw 1,0", "ref 1"])
        self.assertEqual(self.sent(machine), ["41", "50"])      # the page is 0
        self.assertEqual((machine.values["vis t0"], machine.values["touch t0"]), (0, 0))
        self.assertEqual(machine.values["painted"], [("ref", "t0")])

    def test_a_number_a_variable_holds(self):
        machine = self.machine({"sys0": 1})
        machine.run(["vis sys0,0"])
        self.assertEqual(machine.values["vis t0"], 0)

    def test_a_name_the_page_file_does_not_list(self):
        # As nxlang's generated hotspots, which code clicks by name.
        machine = EditorMachine({"sys0": 0}, {("__f0", "down"): ["printh 46"]}, "page0",
                                components=["page0", "t0", "b0"])
        machine.run(["click __f0,1"])
        self.assertEqual(self.sent(machine), ["46"])

    def test_255_stands_for_every_component(self):
        machine = self.machine()
        machine.run(["vis 255,0"])
        self.assertEqual(machine.values["vis 255"], 0)

    def test_an_id_no_component_has(self):
        # The Editor's simulator answered 02, an invalid component ID, and
        # the event went on.
        machine = self.machine()
        machine.run(["vis 99,0", "click 3,1", "printh 4D"])
        self.assertEqual(machine.values["component errors"], [("vis", "99"), ("click", "3")])
        self.assertEqual(self.sent(machine), ["4D"])


class RefusalTest(unittest.TestCase):
    """Lines the running screen refuses, as the Editor's simulator refused
    them in an event: each answered its code at once, changed nothing, and the
    event went on."""

    def machine(self, resources=ResourceNames(["dot"], ["Sans"])) -> EditorMachine:
        values = {"sys0": 0, "t0.txt": "probe", "t0.font": 0, "t0.type": TYPES_BY_NAME["text"],
                  "n0.val": 3, "n1.val": 0, "p0.pic": 0, "p0.type": TYPES_BY_NAME["picture"],
                  "s0.ch": 1, "s0.type": TYPES_BY_NAME["waveform"],
                  "text limits": {"t0.txt": 10}}
        return EditorMachine(values, {}, "page0",
                             components=["page0", "t0", "n0", "n1", "p0", "s0"],
                             resources=resources)

    def test_each_is_recorded_and_the_event_goes_on(self):
        machine = self.machine()
        lines = ["p0.pic=n1.val+9", "p0.pic=65535", "t0.font=255", "pic 0,0,9",
                 "xpic 0,0,10,10,0,0,9", "picq 0,0,10,10,9", 'xstr 0,0,50,20,9,0,0,0,0,1,"a"',
                 "add 5,1,10", "add 9,0,10", "cle 9,0", "repo n0.val,99999", "rept 1024,4"]
        machine.run(lines + ["n0.val=7"])
        self.assertEqual(machine.values["refusals"], list(zip(
            [0x1C, 0x1C, 0x1C, 0x04, 0x04, 0x04, 0x05, 0x12, 0x12, 0x12, 0x1D, 0x1D], lines)))
        self.assertEqual(
            (machine.values["p0.pic"], machine.values["t0.font"], machine.values["n0.val"]),
            (0, 0, 7))
        # xstr paints its background before its font is found missing; the
        # other drawing commands paint nothing.
        self.assertEqual([entry[0] for entry in machine.values["painted"]], ["xstr"])
        self.assertNotIn("waveform", machine.values)
        self.assertNotIn("replies", machine.values)

    def test_transparent_data_refused_and_recorded(self):
        # As the Nextion Editor's simulator answered addt and wept. A negative
        # count is refused alike. Without a screen, the commands taken are
        # recorded with the other commands.
        machine = self.machine()
        lines = ["addt 9,0,3", "addt 5,1,3", "addt 5,0,1025", "addt 5,0,-1", "wept -1,3",
                 "wept 0,-1"]
        machine.run(lines + ["addt 5,0,1024", "wept 1023,3"])
        self.assertEqual(machine.values["refusals"],
                         list(zip([0x12, 0x12, 0x12, 0x12, 0x1D, 0x1D], lines)))
        self.assertEqual(machine.values["other commands"],
                         [("addt", "5", "0", "1024"), ("wept", "1023", "3")])

    def test_an_address_out_of_range(self):
        # As the Nextion Editor's simulator answered addr=100 and addr=3000.
        machine = self.machine()
        lines = ["addr=100", "addr=3000", "addr=255", "addr=2816"]
        machine.run(lines + ["addr=2815", "addr=256"])
        self.assertEqual(machine.values["refusals"], [(0x1C, line) for line in lines])
        self.assertEqual(machine.values["addr"], 256)

    def test_an_eeprom_access_past_its_end(self):
        # A number takes 4 bytes; a text constant its bytes and one more; a
        # text field its txt_maxl bytes and one more to write, and its
        # txt_maxl to read (t0's is 10). Running past the last byte, each was
        # refused, writing and reading nothing.
        machine = self.machine()
        lines = ["wepo n0.val,1021", "repo n1.val,1021", 'wepo "AB",1022', "wepo t0.txt,1014",
                 "repo t0.txt,1015"]
        machine.run(lines)
        self.assertEqual(machine.values["refusals"], [(0x1D, line) for line in lines])
        self.assertEqual((machine.values["n1.val"], machine.values["t0.txt"]), (0, "probe"))
        self.assertNotIn("eeprom accesses", machine.values)
        self.assertEqual(machine.values.get("eeprom", bytes(EEPROM_SIZE)), bytes(EEPROM_SIZE))

    def test_what_the_project_has_is_taken(self):
        machine = self.machine()
        machine.run(["p0.pic=0", "pic 0,0,0", "add 5,0,10", "cle 5,255", "repo n0.val,1020",
                     "wepo n0.val,1020", 'wepo "AB",1021', "wepo t0.txt,1013",
                     "repo t0.txt,1014"])
        self.assertNotIn("refusals", machine.values)

    def test_without_the_projects_resources_any_id_is_taken(self):
        machine = self.machine(resources=None)
        machine.run(["p0.pic=9", "pic 0,0,9"])
        self.assertEqual(machine.values["p0.pic"], 9)
        self.assertNotIn("refusals", machine.values)

    def test_a_value_of_the_other_kind(self):
        # A number stored in a txt, or a text in a val, is refused, as in a
        # typed line. The Editor's simulator refused event code storing in a
        # txt the number read from an attribute the screen does not hold; a
        # text stored in a val is assumed to be refused alike.
        machine = self.machine()
        lines = ["n1.val=t0.txt", "t0.txt=n0.val"]
        machine.run(lines + ["n0.val=7"])
        self.assertEqual(machine.values["refusals"], [(0x1C, line) for line in lines])
        self.assertEqual((machine.values["n1.val"], machine.values["t0.txt"],
                          machine.values["n0.val"]), (0, "probe", 7))

    def test_another_number_of_parameters_stops_event_code(self):
        # The Editor's compile refuses another number of parameters, as the
        # build does, so built code never holds one. Given to the runner
        # directly, event code stops on it, as on other code the compile
        # refuses, and nothing is recorded as the screen's refusal.
        for line in ("cls 1,2", "fill 0,0,10"):
            with self.subTest(line=line):
                machine = self.machine()
                with self.assertRaisesRegex(CompileRefusal, "takes"):
                    machine.run([line, "n0.val=7"])
                self.assertNotEqual(machine.values.get("n0.val"), 7)
                self.assertNotIn("refusals", machine.values)


class RunStoppedTest(unittest.TestCase):
    """The errors that stop a run: RefusedCode for code nxwright refuses or
    does not model, and UnreadableLine, a kind of it, for a line it cannot
    read. Neither is an AssertionError, so a test run reports a test that
    meets one as an error, not as a failed check."""

    def test_each_kind_stops_the_run_with_its_own_error(self):
        cases = [(["again:", "goto again"], RefusedCode, "the loop does not end"),
                 (["covx n0.val,t0.txt,0,3"], RefusedCode, "only covx's forms"),
                 (["sys0 = = 2"], UnreadableLine,
                  "^nxwright cannot run this line: not code in strict Nextion syntax: "
                  "'sys0 = = 2'$"),
                 # A text join ending with "+" reads no more than one ending
                 # with another operator; the runner once took it.
                 (["t0.txt=t0.txt+"], UnreadableLine, "not a chain: 't0.txt\\+'")]
        for lines, error, message in cases:
            with self.subTest(lines=lines):
                with self.assertRaisesRegex(error, message) as raised:
                    EditorMachine({"n0.val": 0, "t0.txt": "", "sys0": 0}).run(lines)
                self.assertNotIsInstance(raised.exception, AssertionError)

    def test_a_run_stopped_on_a_line_says_where_it_is(self):
        # With the lines' places, the error starts with the file, the line,
        # and the event, and keeps its kind, a CompileRefusal its code too.
        cases = [(["sys0=1", "again:", "goto again"], RefusedCode, 4, "the loop does not end"),
                 (["sys0 = = 2"], UnreadableLine, 2, "nxwright cannot run this line"),
                 (["t0.txt*=2"], CompileRefusal, 2, "the Nextion Editor refuses ''"),
                 # A loop's condition, as it is first tested; and the labels,
                 # refused before the event runs.
                 (["sys0=1", "while(sys0)", "{", "}"], RefusedCode, 3,
                  "the Nextion Editor refuses this condition part"),
                 (["up:", "sys0=1", "up:"], RefusedCode, 4, "the label up twice"),
                 (["sys0=1", "while(sys0<1)", "sys0=2"], UnreadableLine, 3,
                  "nxwright cannot run this line"),
                 (["sys0=1", "goto nowhere"], RefusedCode, 3, "no label nowhere")]
        for lines, error, number, message in cases:
            with self.subTest(lines=lines):
                places = [Place("pages/page0.nx", line, "b0.down")
                          for line in range(2, 2 + len(lines))]
                with self.assertRaises(error) as raised:
                    EditorMachine({"t0.txt": "", "sys0": 0}).run(lines, places)
                self.assertTrue(str(raised.exception).startswith(
                    "pages/page0.nx line %d (b0.down): %s" % (number, message)),
                    str(raised.exception))
                self.assertEqual((raised.exception.file, raised.exception.line),
                                 ("pages/page0.nx", number))
        with self.assertRaises(CompileRefusal) as raised:
            EditorMachine({"t0.txt": ""}).run(["t0.txt*=2"], [Place("p.nx", 1, "p.down")])
        self.assertEqual(raised.exception.code, 27)

    def test_a_clicked_event_stopped_says_where_its_own_line_is(self):
        # Two deep: the place is the line that stopped, once, not the clicks'.
        events = {("b1", "down"): ["click b2,1"], ("b2", "down"): ["sys0=1", "again:",
                                                                  "goto again"]}
        places = {("b1", "down"): [Place("pages/page0.nx", 5, "b1.down")],
                  ("b2", "down"): [Place("pages/page0.nx", line, "b2.down")
                                   for line in (8, 9, 10)]}
        machine = EditorMachine({"sys0": 0, "b1.val": 0, "b2.val": 0}, events, "page0",
                                places=places, components=["page0", "b0", "b1", "b2"])
        with self.assertRaisesRegex(RefusedCode, r"^pages/page0\.nx line 10 \(b2\.down\): the "
                                                 r"loop does not end$"):
            machine.run(["click b1,1"], [Place("pages/page0.nx", 2, "b0.down")])

    def test_a_command_given_another_number_of_arguments(self):
        # Code given to the runner directly, as a typed line is, stops on it
        # with CompileRefusal: one argument too few for each command that
        # takes some, and one too many for each that takes none, and for
        # covx. Built code never holds one, as the build refuses it.
        lines = [("%s %s" % (word, ",".join(["1"] * (count - 1)))).strip() if count
                 else word + " 1"
                 for word, count in sorted(COMMAND_PARAMETERS.items())] + ["covx 1,t0.txt,0,0,0"]
        for line in lines:
            with self.subTest(line=line):
                with self.assertRaisesRegex(CompileRefusal, "takes"):
                    EditorMachine({"t0.txt": "", "n0.val": 0, "sys0": 0}).run([line])

    def test_a_line_the_compile_refuses_is_refused_code(self):
        self.assertTrue(issubclass(CompileRefusal, RefusedCode))
        self.assertFalse(issubclass(CompileRefusal, AssertionError))

    def test_python_dropping_asserts_keeps_the_checks(self):
        # python -O drops assert statements. The runner's checks are not
        # asserts, so a hexadecimal number past 32 bits is still refused.
        code = ("from nxwright.testing import EditorMachine, RefusedCode\n"
                "try:\n"
                "    EditorMachine({'n0.val': 0}).run(['n0.val=0x0100000000'])\n"
                "except RefusedCode as error:\n"
                "    print(error)\n")
        result = subprocess.run([sys.executable, "-O", "-c", code], capture_output=True,
                                text=True, cwd=Path(__file__).resolve().parents[1], check=True)
        self.assertIn("refuses a hex constant past 32 bits", result.stdout)


class JumpsTest(unittest.TestCase):
    """return, goto, and labels, as two probes ran them in the Editor's
    simulator: lines with jumps, a goto reaching a label anywhere in its
    event, into a block too."""

    def run_lines(self, lines: list, events: dict = None) -> dict:
        start = {"sys0": 0, "sys1": 0, "sys2": 0}
        return EditorMachine(start, events or {}).run(lines)

    def test_the_vendors_example(self):
        # From the vendor's instruction set, goto (3.55), as written there.
        lines = ["sys0=n0.val%2//0 when even, 1 when odd", "if(sys0==0)", "{",
                 "  goto even// goto label does not have the colon", "}else", "{",
                 "  goto odd// goto label does not have the colon", "}",
                 "goto end// goto label does not have the colon",
                 "even:// label landing point has the colon", '  settings.t0.txt="even"',
                 "  goto end", "odd:// label landing point has the colon",
                 '  settings.t0.txt="odd"', "  goto end", "end:// label landing point has the colon",
                 "return"]
        for number, shown in ((4, "even"), (7, "odd")):
            with self.subTest(number=number):
                values = EditorMachine({"sys0": 0, "n0.val": number,
                                        "settings.t0.txt": ""}).run(lines)
                self.assertEqual(values["settings.t0.txt"], shown)

    def test_a_label_of_any_character_the_editor_takes(self):
        # As the Editor compiled them: $, accented letters, and brackets
        # ( and ) among them; and, in a second probe, braces { and }.
        for label in ("ab$", "été", "a(b)", "a{b", "a}b"):
            with self.subTest(label=label):
                values = self.run_lines(["%s:" % label, "sys0++", "if(sys0<3)", "{",
                                         "  goto %s" % label, "}"])
                self.assertEqual(values["sys0"], 3)

    def test_a_goto_back_loops_and_return_ends_the_event(self):
        values = self.run_lines(["sys0=0", "again:", "sys0=sys0+1", "if(sys0<3)", "{",
                                 "goto again", "}", "return", "sys2=9"])
        self.assertEqual((values["sys0"], values["sys2"]), (3, 0))

    def test_return_ends_only_its_own_event(self):
        # A clicked event's return: the clicking event goes on.
        events = {("b0", "down"): ["sys0=1", "return", "sys0=2"]}
        values = self.run_lines(["click b0,1", "sys1=1"], events)
        self.assertEqual((values["sys0"], values["sys1"]), (1, 1))

    def test_a_goto_leaves_a_loop(self):
        values = self.run_lines(["while(sys1<10)", "{", "sys1=sys1+1", "if(sys1==4)", "{",
                                 "goto out", "}", "}", "out:", "sys2=sys1"])
        self.assertEqual(values["sys2"], 4)

    def test_a_label_within_a_loop_skips_the_rest_of_a_turn(self):
        values = self.run_lines(["while(sys2<3)", "{", "sys2=sys2+1", "if(sys2==2)", "{",
                                 "goto next", "}", "sys0=sys0+10", "next:", "}"])
        self.assertEqual(values["sys0"], 20)

    def test_a_goto_enters_a_block(self):
        # Into an if whose condition is false: the lines after the label run.
        values = self.run_lines(["goto inside", "if(sys0==99)", "{", "inside:", "sys1=7",
                                 "}"])
        self.assertEqual(values["sys1"], 7)
        # Into a for loop's block: its rest, then its step and test, run.
        values = self.run_lines(["goto inside", "for(sys1=0;sys1<3;sys1++)", "{",
                                 "sys0=sys0+1", "inside:", "sys0=sys0+10", "}"])
        self.assertEqual((values["sys0"], values["sys1"]), (32, 3))

    def test_a_label_may_end_with_a_comment(self):
        values = self.run_lines(["goto skip", "sys0=1", "skip:// past sys0=1", "sys1=1"])
        self.assertEqual((values["sys0"], values["sys1"]), (0, 1))

    def test_labels_the_editor_refuses(self):
        # It said "nofind mark" and "repeated mark"; labels are told apart by
        # case, and one event's are one set, whatever block they are in.
        cases = [(["goto nowhere"], "no label nowhere"),
                 (["up:", "goto Up"], "no label Up"),
                 (["if(sys0==0)", "{", "same:", "}", "same:"], "the label same twice")]
        for lines, message in cases:
            with self.subTest(lines=lines):
                with self.assertRaisesRegex(RefusedCode, message):
                    self.run_lines(lines)

    def test_loops_are_stopped_as_before(self):
        # Each loop counts its own turns, from 0 as it is entered: nested
        # loops of 20000 turns together run.
        values = self.run_lines(["while(sys0<200)", "{", "sys0=sys0+1", "sys1=0",
                                 "while(sys1<100)", "{", "sys1=sys1+1", "sys2=sys2+1", "}",
                                 "}"])
        self.assertEqual(values["sys2"], 20000)
        with self.assertRaisesRegex(RefusedCode, "the loop does not end"):
            self.run_lines(["again:", "sys0=sys0+1", "goto again"])

    def test_each_step_through_jumps_is_recorded(self):
        lines = ["sys0=0", "again:", "sys0=sys0+1", "if(sys0<2)", "{", "goto again", "}",
                 "return", "sys2=9"]
        places = [Place("pages/page0.nx", number, "b0.down")
                  for number in range(2, 2 + len(lines))]
        recorder = Recorder()
        recorder.begin("jumps", "folder", {"sys0": 0, "sys2": 0}, {})
        EditorMachine({"sys0": 0, "sys2": 0}, recorder=recorder).run(lines, places)
        # A label, a brace, and what follows a return are no steps.
        self.assertEqual([step.place.line for step in recorder.steps],
                         [2, 4, 5, 7, 4, 5, 9])


class TestCommandTest(unittest.TestCase):
    """`nxwright test` on a folder of tests written for each case.

    Each module gets a name no other test uses: Python keeps the modules it has
    imported for the rest of the run, so a repeated name would find the old one.
    """

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)

    def tearDown(self):
        self._folder.cleanup()

    def write(self, name: str, text: str):
        (self.folder / name).write_text(text, encoding="utf-8", newline="\n")

    def run_command(self, *arguments) -> int:
        output = io.StringIO()
        with contextlib.redirect_stderr(output), contextlib.redirect_stdout(output):
            return main(["test", str(self.folder), *arguments])

    def test_a_passing_folder(self):
        # A test imports a module of its own folder by name alone.
        self.write("shared_values_a.py", "ANSWER = 42\n")
        self.write("test_answer_a.py", "import unittest\nfrom shared_values_a import ANSWER\n\n"
                   "class AnswerTest(unittest.TestCase):\n"
                   "    def test_answer(self):\n        self.assertEqual(ANSWER, 42)\n")
        self.assertEqual(self.run_command(), 0)

    def test_a_failing_folder(self):
        self.write("test_failing_b.py", "import unittest\n\nclass FailingTest(unittest.TestCase):\n"
                   "    def test_fails(self):\n        self.assertEqual(1, 2)\n")
        self.assertEqual(self.run_command(), 1)

    def test_a_pattern_picks_tests(self):
        self.write("test_picked_c.py", "import unittest\n\nclass PickedTest(unittest.TestCase):\n"
                   "    def test_kept(self):\n        pass\n\n"
                   "    def test_left_out(self):\n        self.fail()\n")
        self.assertEqual(self.run_command("-k", "kept"), 0)

    def test_refuses_a_folder_without_tests(self):
        self.write("notes_d.py", "NOTHING = 0\n")
        self.assertEqual(self.run_command(), 1)
        # With a pattern too, as the folder's lack is the truer cause.
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            self.assertEqual(main(["test", str(self.folder), "-k", "zzz"]), 1)
        self.assertIn("%s has no tests" % self.folder, output.getvalue())

    def test_a_pattern_no_test_matches_is_named(self):
        # The folder has a test, so its error is the pattern's.
        self.write("test_unmatched_e.py", "import unittest\n\n"
                   "class PresentTest(unittest.TestCase):\n"
                   "    def test_present(self):\n        pass\n")
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            self.assertEqual(main(["test", str(self.folder), "-k", "zzz", "-k", "yyy"]), 1)
        self.assertIn("no test of %s matches zzz or yyy" % self.folder, output.getvalue())

    def test_refuses_a_missing_folder(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            self.assertEqual(main(["test", str(self.folder / "missing")]), 1)
        self.assertIn("is not a folder", output.getvalue())
