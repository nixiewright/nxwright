"""A project's encoding (tft/packaging.py, tft/frame.py, tft/matching.py,
and component_types): the pieces the probes of encoding_probes.py kept once
they matched the Nextion Editor's file, the headers and the entries each
encoding gives, as the Nextion Editor's files gave them, and what the
rules take.

Each test gives the function it checks that function's own input: a
probe's pages made in memory, in its encoding, in a Project of the facts
it reads, and each component's place, read from the probe's table
(tests/tft/unit_inputs.py). The sample of whole files is in
tests/tft/test_whole_files.py.
"""
import struct
import unittest

from nxwright.tft import frame
from tools.tft.probing import encoding_probes
from nxwright.tft.component_types import is_global, packed_entries, text_fits
from nxwright.tft.matching import Need, matched_rules, project_needs
from nxwright.tft.packaging import Firmware, package
from tools.tft.probing.statement_probes import touch_release_code
from nxwright.tft.statements import past_ascii_covered
from tools.tft.probing.text_probes import text_component
from nxwright.tft.tft_file import firmware_names, read_tft
from tests.tft.made_tft import made_user_code
from tests.tft.t_components import CodePieces, TypePieces
from tests.tft.unit_inputs import page, place, probe_facts, project_of


def _probe(name: str):
    return next(probe for probe in encoding_probes.PROBES if probe.name == name)


class PieceTest(TypePieces, CodePieces, unittest.TestCase):
    """Each text of each probe that keeps its whole user code, in gb2312,
    utf-8, and koi8-r, whose txt holds the encoding's characters: its
    memory, its drawing, and its entries, whose owners carry the encoding's
    byte. And the blocks of page0's Touch Release event of each probe of
    code that keeps them, in gb2312 and shift-jis."""

    TYPE = "text"
    PROBES = encoding_probes.PROBES
    COUNT = 3
    CODE_COUNT = 2


class HeaderTest(unittest.TestCase):
    """Header 2's word at 0x110 gives the encoding's code in the project file,
    and header 1's byte 0x33 the first byte of its two-byte characters, or
    0, as the Nextion Editor's files gave them."""

    def test_each_kind_of_encoding(self):
        firmware = Firmware((1, 68, 2), {name: bytes(16) for name in firmware_names("T")})
        for encoding, code, start in (("iso-8859-1", 3, 0), ("ascii", 1, 0), ("koi8-r", 22, 0),
                                      ("gb2312", 2, 0xA1), ("big5", 16, 0xA0),
                                      ("shift-jis", 23, 0x81), ("ks_c_5601-1987", 15, 0xA1),
                                      ("utf-8", 24, 0xFF)):
            with self.subTest(encoding):
                project = project_of(page(encoding=encoding), encoding=encoding, fonts=0)
                data = package(project, made_user_code(), firmware)
                tft = read_tft(data, encoding)
                self.assertEqual(tft.header_2_value(0x110), code)
                self.assertEqual(data[0x32:0x34], bytes([0x21, start]))


class EntriesTest(unittest.TestCase):
    """Each entry that gives a value carries the encoding's byte in the third
    byte of its owner, whatever the owner, as in the Nextion Editor's files of
    a component of each type in gb2312. A component's entries are compared
    whole in PieceTest."""

    def test_a_variable_s_third_byte(self):
        # A variable's, which gives 0xFFFF for its ID and its page's, at the
        # place of the text of the probe in gb2312.
        its_place = place(_probe("encoding-gb2312"), "page0-1")
        self.assertEqual(struct.unpack_from("<I", packed_entries(
            {0: (1, 2, 3, 4)}, 1, its_place, 0xFFFF), 16)[0], 0xA1FFFF)

    def test_of_every_object_global_ones_too(self):
        # The probe of global objects on two pages, in gb2312: the entries of
        # its global objects, placed among the int variables, and of every
        # other object give 0xA1.
        project = probe_facts(_probe("encoding-globals-in-gb2312"))
        self.assertTrue(any(is_global(page_object) for made in project.pages
                            for page_object in made.objects))
        data = frame.user_code(project).data
        owners = [struct.unpack_from("<6I", data, at)[4] for at in range(0, len(data), 24)
                  if data[at:at + 24] != bytes(24)]
        self.assertTrue(owners)
        self.assertEqual({owner >> 16 & 0xFF for owner in owners}, {0xA1})


class NeedsTest(unittest.TestCase):
    """A project's needs carry its encoding, and each line of code past ASCII
    gives a need, which the frame's rule covers when the Nextion Editor
    takes the line in that encoding."""

    def test_every_need_gives_the_encoding(self):
        project = project_of(page(text_component("t0"), encoding="utf-8"), encoding="utf-8",
                             fonts=0)
        self.assertEqual({need.encoding for need in project_needs(project)}, {"utf-8"})

    @staticmethod
    def with_code(encoding: str, lines: list):
        """Returns a Project of the facts of page0 in `encoding`, with the
        text t0, and `lines` in its Touch Release event, in strict Nextion
        syntax, as the match check reads it."""
        made = page(text_component("t0"), code=touch_release_code(lines), strict=True,
                    encoding=encoding)
        return project_of(made, strict=True, encoding=encoding, fonts=0)

    def test_a_line_past_ascii(self):
        project = self.with_code("iso-8859-1", ['t0.txt="é"', "// é", 't0.txt="e"'])
        needs = [need for need in project_needs(project) if need.kind == "text in code"]
        self.assertEqual([(need.subject, need.value, need.where) for need in needs],
                         [("iso-8859-1", 't0.txt="é"', "page0: page0, up, line 1")])

    def test_a_comment_past_ascii_gives_none(self):
        # The Nextion Editor drops a comment whole, in shift-jis too when it
        # ends in 表, whose last byte is a backslash's.
        project = self.with_code("shift-jis", ["// 日本表", 't0.txt="e"'])
        self.assertEqual([need for need in project_needs(project)
                          if need.kind == "text in code"], [])


class TextsInCodeTest(unittest.TestCase):
    """In an encoding of two-byte characters, the Nextion Editor reads a text
    in code in pairs, and a text in a condition or a command's arguments
    also without them. It refused some of the lines below
    (ResearchNotes/tft/encodings.md). nxwright's build refuses those first, so
    nxwright takes each line, in shift-jis unless it says, as its characters
    are ones the encoding writes."""

    # 表 and 許 end in 0x5C, a backslash's byte; ｱ is one byte from 0xA1 up;
    # gb2312's 乗 is 81 5c, its first byte below gb2312's two-byte start.
    LINES = (
        't0.txt="表"', 't0.txt+="表"', 'print "日表"',
        'get "日表"', 'xstr 0,0,100,30,0,RED,BLACK,0,0,1,"表"',
        't0.txt="日表"+t0.txt', 't0.txt="日表"+"日表"',
        't0.txt="a"+"表"+t0.txt', 'b[1].txt="日表"+t0.txt',
        'p[0].b[1].txt="表"', 'b[1].txt+="表"', 'if(t0.txt=="表a")',
        'page1.va1.txt="日表"+t0.txt', 'page1.va1.txt+="表"',
        'prints "日表",0', 'spstr t0.txt,t0.txt,"表",0',
        'strlen "日表",sys0', 'btlen "日表",sys0',
        'crcputs "日表",0', 'if(t0.txt=="表")',
        'while(t0.txt!="日表")', 'for(sys0=0;t0.txt=="日表";sys0++)',
        'prints "ｱa",0', 'print "ｱa"', 'spstr t0.txt,t0.txt,"ｱa",0',
        'crcputs "ｱa",0', 'if(t0.txt=="ｱa")', 't0.txt+="ｱa"',
        't0.txt="ｱ日a"', 't0.txt="ｱｱ"', 't0.txt="表\\""',
        't0.txt="ソ能"',
        't0.txt="aｱ"', 't0.txt="ｱ"', 't0.txt="ｱ日"',
        't0.txt="ｱｱｱ"', 't0.txt="ｱ表"', 't0.txt="ｱ\\""',
        'prints "ｱ",0',
        ("gb2312", 't0.txt="乗"'), ("gb2312", 'prints "乗a",0'),
        ("gb2312", 'prints "乗",0'), ("big5", 'prints "許a",0'),
        ("big5", 'if(t0.txt=="中文許中")'), ("big5", 'prints "中許",0'),
        ("big5", 'if(t0.txt=="中文許")'))

    def test_each_line(self):
        for case in self.LINES:
            encoding, line = case if isinstance(case, tuple) else ("shift-jis", case)
            with self.subTest(encoding=encoding, line=line):
                self.assertTrue(past_ascii_covered(Need("text in code", encoding, line)))


class TxtTest(unittest.TestCase):
    """On T and K, a txt may hold any bytes, written as they are, up to its
    txt_maxl."""

    @staticmethod
    def need(value: bytes, encoding: str, maxl: int = 100) -> Need:
        return Need("attribute", "text.txt", value, context={"txt_maxl": bytes([maxl])},
                    series="T", encoding=encoding)

    def test_its_encoding_s_characters(self):
        for encoding, text in (("gb2312", "中文，。"), ("utf-8", "é中€"), ("koi8-r", "Привет"),
                               ("shift-jis", "日本表ｱ")):
            with self.subTest(encoding):
                value = text.encode({"shift-jis": "cp932", "gb2312": "gb2312"}.get(
                    encoding, encoding))
                self.assertTrue(text_fits(self.need(value, encoding)))

    def test_what_it_leaves_out(self):
        # A txt of more bytes than its txt_maxl, though of fewer characters.
        self.assertFalse(text_fits(self.need("中中".encode("utf-8"), "utf-8", 5)))

    def test_any_bytes(self):
        # A txt is written as its bytes, so a control character, and bytes
        # utf-8 does not decode, are taken too.
        for value, encoding in ((b"a\x01", "gb2312"), (b"\xff\xfe", "utf-8")):
            with self.subTest(value=value):
                self.assertTrue(text_fits(self.need(value, encoding, 100)))


if __name__ == "__main__":
    unittest.main()
