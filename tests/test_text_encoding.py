"""Texts and code in the project's character encoding: extracting reads them as
the characters they are, and the build stores them back as the same bytes."""
from pathlib import Path
import unittest

from nxwright import NxwrightError
from nxwright.project.device_settings import TextCodec, encoding_code
from nxwright.project.dumper import ProjectDumper
from nxwright.project.page_file import write_page_file
from nxwright.project.page_text import escape_string
from nxwright.source.project_files import build
from nxwright.source.source_folder import import_dump
from nxwright.testing.editor_machine import EditorMachine
from tests.test_project_writer import edit_text
from tests.test_source_folder import SourceFolderTestCase


class TextEncodingTest(SourceFolderTestCase):
    """The small test project, with its encoding, a text of its first page,
    and its program.s changed in its dump."""

    def set_dump(self, encoding: str, text: bytes = None, program: bytes = None):
        summary = self.dump / "project.txt"
        lines = summary.read_text(encoding="utf-8").split("\n")
        for index, line in enumerate(lines):
            if line.split()[:1] == ["unknown_header"]:
                # The line shows header bytes 8 to 23 first: byte 13, the encoding, is its 6th.
                shown = bytearray.fromhex(line.split()[1])
                shown[5] = encoding_code(encoding)
                lines[index] = "  unknown_header   %s" % shown.hex()
        summary.write_text("\n".join(lines), encoding="utf-8", newline="\n")
        if text is not None:
            edit_text(self.dump / "pages" / "00-first.txt", 'txt = "hello"',
                      "txt = " + escape_string(text))
        if program is not None:
            (self.dump / "program.s").write_bytes(program)

    def extract(self) -> Path:
        source = self.folder / "extracted"
        import_dump(self.dump, source)
        return source

    def built_dump(self, source: Path) -> Path:
        built = self.folder / "built.HMI"
        build(source, built)
        dump = self.folder / "built-dump"
        ProjectDumper(built, dump).dump()
        return dump

    def assert_same_text_and_program(self, dump: Path):
        line = next(line for line in (self.dump / "pages" / "00-first.txt")
                    .read_text(encoding="utf-8").split("\n") if line.strip().startswith("txt ="))
        self.assertIn(line + "\n", (dump / "pages" / "00-first.txt").read_text(encoding="utf-8"))
        self.assertEqual((dump / "program.s").read_bytes(), (self.dump / "program.s").read_bytes())

    def test_utf8_reads_as_characters_and_builds_back(self):
        self.set_dump("utf-8", "é温度".encode("utf-8"), "//温度".encode("utf-8"))
        source = self.extract()
        self.assertIn('txt = "é温度"', (source / "pages" / "first.page.toml").read_text(encoding="utf-8"))
        self.assertEqual((source / "program.nx").read_text(encoding="utf-8"), "//温度")
        self.assert_same_text_and_program(self.built_dump(source))

    def test_event_code_is_stored_in_the_encoding(self):
        self.set_dump("utf-8")
        source = self.extract()
        edit_text(source / "pages" / "first.page.toml", "events = []", 'events = ["down"]')
        (source / "pages" / "first.nx").write_text('on first.down:\n  sys0=0 //温度\n',
                                                   encoding="utf-8", newline="\n")
        built = self.folder / "built.HMI"
        build(source, built)
        self.assertIn("sys0=0 //温度".encode("utf-8"), built.read_bytes())

    def test_gb2312_is_the_windows_code_page_936(self):
        # 镕 is in code page 936 (GBK), as the Editor stores it, but not in GB2312.
        self.set_dump("gb2312", bytes.fromhex("e946"), b"//" + bytes.fromhex("e946"))
        source = self.extract()
        self.assertIn('txt = "镕"', (source / "pages" / "first.page.toml").read_text(encoding="utf-8"))
        self.assert_same_text_and_program(self.built_dump(source))

    def test_bytes_that_are_not_text_stop_the_extract(self):
        # In code page 932, fa 4a and 87 54 are both U+2160, which encodes as 87 54.
        for encoding, text in (("utf-8", b"\xff"), ("shift-jis", bytes.fromhex("fa4a")),
                               ("ascii", b"\xe9")):
            with self.subTest(encoding=encoding):
                self.set_dump(encoding, text)
                with self.assertRaisesRegex(NxwrightError, "page first, object 0: txt: the bytes "
                                            "%s are not text in %s" % (text.hex(" "), encoding)):
                    self.extract()
                self.assertFalse((self.folder / "extracted").exists())
                edit_text(self.dump / "pages" / "00-first.txt", "txt = " + escape_string(text),
                          'txt = "hello"')

    def test_a_character_the_encoding_cannot_store_stops_the_build(self):
        edit_text(self.source / "pages" / "first.page.toml", 'txt = "hello"', 'txt = "温"')
        output = self.folder / "built.HMI"
        with self.assertRaisesRegex(NxwrightError, "first.page.toml, object 0: txt: iso-8859-1 "
                                                   "cannot store '温'"):
            build(self.source, output)
        self.assertFalse(output.exists())

    def test_a_changed_encoding_stores_the_texts_in_the_new_one(self):
        self.set_dump("iso-8859-1", "é".encode("iso-8859-1"))
        source = self.extract()
        edit_text(source / "app.toml", 'encoding = "iso-8859-1"', 'encoding = "utf-8"')
        page = (self.built_dump(source) / "pages" / "00-first.txt").read_text(encoding="utf-8")
        self.assertIn("txt = " + escape_string("é".encode("utf-8")) + "\n", page)

    def test_a_page_file_names_the_encoding(self):
        # The Editor writes the project's encoding into every page header it
        # writes. Its page files from an iso-8859-1 project held it too (3), so
        # a page file is taken to carry the project's encoding: 24, hex 18, for utf-8.
        self.set_dump("utf-8")
        output = self.folder / "first.page"
        write_page_file(self.dump, 0, output)
        self.assertEqual(output.read_bytes()[40:56], bytes.fromhex("01440218") + bytes(12))


class CodecTest(unittest.TestCase):

    def test_each_encoding_goes_through_a_codec_every_supported_python_has(self):
        # Python before 3.14 has no codec named windows-874, on any system:
        # a windows-874 folder's texts go through cp874, the same code page.
        self.assertEqual(TextCodec("windows-874").codec_name, "cp874")
        self.assertEqual(TextCodec("windows-874").encode("฿", "a text"), b"\xdf")


class TextCommandTest(unittest.TestCase):

    def test_the_text_commands_count_as_the_simulator_does(self):
        # Run in the Editor's simulator, in a utf-8 project, where "aé温" is 3
        # characters in 6 bytes; it sent 03 06 02 05 03. So strlen, substr, and
        # spstr count in characters, and btlen in bytes.
        # In iso-8859-1, which has no 温, each character is one byte.
        cases = (("utf-8", "aé温", [3, 6, 2, 5, 3], ("é温", "温")),
                 ("iso-8859-1", "aéb", [3, 3, 2, 2, 1], ("éb", "b")))
        for encoding, text, numbers, texts in cases:
            with self.subTest(encoding=encoding):
                lines = ['t0.txt="%s"' % text, "strlen t0.txt,n0.val", "btlen t0.txt,n1.val",
                         "substr t0.txt,t1.txt,1,2", "strlen t1.txt,n2.val",
                         "btlen t1.txt,n3.val", 'spstr t0.txt,t2.txt,"é",1',
                         "btlen t2.txt,n4.val"]
                start = {"t0.txt": "", "t1.txt": "", "t2.txt": "",
                         **{"n%d.val" % number: 0 for number in range(5)}}
                values = EditorMachine(start, encoding=encoding).run(lines)
                self.assertEqual([values["n%d.val" % number] for number in range(5)], numbers)
                self.assertEqual((values["t1.txt"], values["t2.txt"]), texts)

    def run_two_byte(self, encoding: str, source: bytes, lines: list) -> dict:
        """Runs `lines` on a machine in `encoding` whose t0.txt holds the
        bytes `source`, and returns its values, each text as its bytes."""
        codec = TextCodec(encoding)
        start = {"t0.txt": codec.decode_keeping_bytes(source), "n0.val": 0,
                 "text limits": {"t%d.txt" % number: 20 for number in range(4)},
                 **{"t%d.txt" % number: "" for number in range(1, 4)}}
        values = EditorMachine(start, encoding=encoding).run(lines)
        return {name: codec.encode_keeping_bytes(value, name) if isinstance(value, str) else value
                for name, value in values.items() if name in start}

    def test_two_byte_texts_count_as_the_simulator_does(self):
        # As the Nextion Editor's simulator ran them: strlen, substr, and
        # -= take a byte above the lowest first byte of the encoding's
        # grid, a1, a0, 81, or a1, as a pair's first, with the byte after
        # it, or alone at the text's end. Any other byte is a character of
        # its own. So shift-jis's half-width katakana take the byte after
        # them, and gb2312's "　", a1 a1, is two characters.
        cases = {"shift-jis": [("b1 41", 1, "b1 41", "", ""), ("41 b1 42", 2, "41", "b1 42", "41"),
                               ("b1 b2", 1, "b1 b2", "", ""), ("41 b1", 2, "41", "b1", "41"),
                               ("88 9f b1 41", 2, "88 9f", "b1 41", "88 9f"),
                               ("b1 88 9f 42", 2, "b1 88", "9f 42", "b1 88"),
                               ("81 41", 2, "81", "41", "81"), ("82 9f", 1, "82 9f", "", "")],
                 "gb2312": [("a1 a1", 2, "a1", "a1", "a1"), ("a1 b0", 2, "a1", "b0", "a1"),
                            ("81 40 42", 3, "81", "40", "81 40"), ("a2 a1", 1, "a2 a1", "", ""),
                            ("b0 a1 a1 b0", 3, "b0 a1", "a1", "b0 a1 a1")],
                 "ks_c_5601-1987": [("a1 b0", 2, "a1", "b0", "a1"),
                                    ("81 41 42", 3, "81", "41", "81 41")],
                 "big5": [("a4 40 42", 2, "a4 40", "42", "a4 40"), ("a1 40", 1, "a1 40", "", "")]}
        lines = ["strlen t0.txt,n0.val", "substr t0.txt,t1.txt,0,1", "substr t0.txt,t2.txt,1,1",
                 "t0.txt-=1"]
        for encoding, texts in cases.items():
            for source, length, first, second, shortened in texts:
                with self.subTest(encoding=encoding, source=source):
                    values = self.run_two_byte(encoding, bytes.fromhex(source), lines)
                    self.assertEqual((values["n0.val"], values["t1.txt"], values["t2.txt"],
                                      values["t0.txt"]),
                                     (length, bytes.fromhex(first), bytes.fromhex(second),
                                      bytes.fromhex(shortened)))

    def test_spstr_finds_its_separator_byte_by_byte(self):
        # As the Nextion Editor's simulator ran it, in each two-byte
        # encoding: inside a pair too, as shift-jis's "ァB", 83 40 42,
        # split at "@" gives 83, then 42.
        cases = [("shift-jis", "83 40 42", "@", ["83", "42"]),
                 ("shift-jis", "83 40 40 42", "@", ["83", "", "42"]),
                 ("shift-jis", "b1 41", "A", ["b1", ""]),
                 ("gb2312", "81 40 42", "@", ["81", "42"]),
                 ("big5", "a4 40 42", "@", ["a4", "42"]),
                 ("ks_c_5601-1987", "81 41 42", "A", ["81", "42"])]
        for encoding, source, separator, parts in cases:
            with self.subTest(encoding=encoding, source=source):
                lines = ['spstr t0.txt,t%d.txt,"%s",%d' % (index + 1, separator, index)
                         for index in range(len(parts))]
                values = self.run_two_byte(encoding, bytes.fromhex(source), lines)
                self.assertEqual([values["t%d.txt" % (index + 1)] for index in range(len(parts))],
                                 [bytes.fromhex(part) for part in parts])

    def test_pieces_joined_compare_as_the_text_they_came_from(self):
        # substr splits shift-jis's "ｱ亜B", b1 88 9f 42, as b1 88 and 9f 42,
        # neither of them whole characters of code page 932. Joined again,
        # they are the text's own bytes, which compare equal.
        lines = ["substr t0.txt,t1.txt,0,1", "substr t0.txt,t2.txt,1,1", "t3.txt=t1.txt+t2.txt",
                 "if(t3.txt==t0.txt)", "{", "n0.val=1", "}"]
        values = self.run_two_byte("shift-jis", bytes.fromhex("b1 88 9f 42"), lines)
        self.assertEqual((values["t3.txt"], values["n0.val"]), (bytes.fromhex("b1 88 9f 42"), 1))

    def test_btlen_counts_bytes_in_the_encoding_and_strlen_characters(self):
        lines = ["btlen t0.txt,n0.val", "strlen t0.txt,n1.val"]
        for encoding, sizes in (("utf-8", (6, 3)), ("iso-8859-1", (2, 2))):
            with self.subTest(encoding=encoding):
                text = "aé温" if encoding == "utf-8" else "aé"
                values = EditorMachine({"t0.txt": text, "n0.val": 0, "n1.val": 0},
                                       encoding=encoding).run(lines)
                self.assertEqual((values["n0.val"], values["n1.val"]), sizes)
