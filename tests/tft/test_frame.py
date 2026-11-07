"""The user code's frame (tft/frame.py): each part it writes across
objects and pages, at the frame's function that writes it, what it reads
and refuses, and the page probes' components at their types' functions.

Each test gives the function it checks its own input: a probe's pages made
in memory, in a Project of the facts it reads, and the places its table
gives (tests/tft/unit_inputs.py). Its expected bytes are the probe's pieces,
the frame's output through frame_probes.stand_in_code, which the probe
runner wrote once each probe matched the Nextion Editor's file. The sample
of whole files is in tests/tft/test_whole_files.py.
"""
import importlib
import pkgutil
import struct
import unittest
from unittest import mock

from nxwright import NxwrightError
from nxwright.project.device_settings import ENCODINGS
from nxwright.tft.compile_context import CompileContext
from nxwright.tft import component_types, frame
import tools.tft.probing
from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, ObjectPlace, progress_bar, timer
from tools.tft.probing import (button_probes, data_record_probes, frame_probes, overlap_probes,
                           p_probes, page_probes, progress_bar_probes, shared_attribute_probes,
                           timer_probes, variable_probes)
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from nxwright.tft.series_differences import DIFFERENCES
from nxwright.tft.statements import CodePlace
from tools.tft.probing.frame_probes import stand_in_code
from tools.tft.probing.progress_bar_probes import progress_bar_component
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from nxwright.tft.tft_file import encode_blocks
from tests.tft.p_components import p_values
from tests.tft.series_comparison import instruction_piece
from tests.tft.t_components import FillStartAndLoadPieces, TypePieces, made_in_memory
from tests.tft.unit_inputs import (blocks_place, laid_out_pieces, page, piece, piece_names,
                               piece_start, place, probe_facts, probe_project, project_of,
                               record_places, user_code_place)


def probe_named(probes, name):
    return next(probe for probe in probes if probe.name == name)


class ComponentsTest(TypePieces, FillStartAndLoadPieces, unittest.TestCase):
    """Each component of each page probe that keeps its whole user code, of
    every type, at its type's functions, against the probe's pieces: its
    memory, its drawing, its entries, its background fill, its events'
    start, and its blocks in its page's load section (tests/tft/t_components.py).

    The frame's own pieces of these probes and of the frame probes have their
    tests below, each at the frame's function that writes it. What no part
    names, the events' code, each page's texts, the blocks the frame
    appends to program.s, and the padding, the sample of whole files
    compares (tests/tft/test_whole_files.py)."""

    PROBES = page_probes.PROBES
    COUNT = 51
    FILL_COUNT = 47
    START_COUNT = 22
    LOAD_COUNT = 6


class ReadTest(unittest.TestCase):
    """What the frame reads from a project."""

    def test_a_page_name_s_crc(self):
        # The CRC the Nextion Editor's page list gave page0, in every probe.
        self.assertEqual(frame.page_name_crc(b"page0"), 0xAC967926)

    def test_what_is_an_int_declaration(self):
        # `int`, then a space or a tab.
        for line, declares in (("int sys0=0", True), ("  int a=5", True), ("int\ta=5", True),
                               ("interval=5", False), ("// int a=5", False)):
            with self.subTest(line=line):
                self.assertEqual(frame.declares_ints(line), declares)

    def test_int_variables_over_two_lines(self):
        project = probe_facts(probe_named(frame_probes.PROBES, "frame-second-int-line"))
        self.assertEqual(frame.int_variables(project),
                         [("sys0", 0), ("sys1", 0), ("sys2", 0), ("c", 3)])

    def test_the_encoder_is_asked_once_for_each_run_in_order(self):
        project = probe_facts(probe_named(frame_probes.PROBES, "frame-page-events"))
        asked = []

        def encode_code(lines, place, project):
            asked.append(([line.strip() for line in lines], place))
            return frame_probes.stand_in_code(lines, place, project)
        frame.user_code(project, encode_code)
        # program.s first, then the events in the order their blocks lie:
        # down, up, unload, then load and loadend.
        self.assertEqual(asked[0][1], CodePlace())
        self.assertIn("int sys0=0,sys1=0,sys2=0", asked[0][0])
        self.assertEqual([(lines, place.event) for lines, place in asked[1:]],
                         [(["sys0=3", "sys1=6"], "down"), (["sys0=4"], "up"),
                          (["sys0=5"], "unload"), (["sys0=1"], "load"),
                          (["sys0=2"], "loadend")])
        self.assertEqual({place for _, place in asked[1:]},
                         {CodePlace(0, "page0", event)
                          for event in ("load", "loadend", "down", "up", "unload")})


class RefusedTest(unittest.TestCase):
    """What the frame refuses, as the match check (matching.py) refuses it
    first."""

    def test_its_refusals_are_reported_as_nxwright_s(self):
        # So that compile reports them, as it does nxwright's own refusals.
        self.assertTrue(issubclass(frame.FrameError, NxwrightError))

    def test_a_component_whose_type_has_no_module(self):
        project = project_of(page('\n[[component]]\nname = "g0"\ntype = "scrolling-text"\n'
                                  'x = 10\ny = 10\nw = 200\nh = 100\n'))
        # Every type nxwright builds on T has a module now, so the scrolling
        # text's is taken away here, and every other type keeps its own.
        real = component_types.type_module
        with mock.patch.object(component_types, "type_module",
                               side_effect=lambda name: None if name == "scrolling-text"
                               else real(name)):
            with self.assertRaisesRegex(frame.FrameError,
                                        "no module for the type scrolling-text, of g0"):
                frame.user_code(project, frame_probes.stand_in_code)

    def test_the_forms_of_int_declarations(self):
        # The Nextion Editor writes each as its plain form: a space after a
        # comma, an indented line, a comment after it, and a name without a
        # value, which starts at 0. code_lines drops the indentation and the
        # comment.
        project = project_of(page())
        project.program = b"int a=1, b=2\r\n  int c\r\nint d=4 // a comment\r\nint e, f=6"
        self.assertEqual(frame.int_variables(project),
                         [("a", 1), ("b", 2), ("c", 0), ("d", 4), ("e", 0), ("f", 6)])

    def test_an_int_declaration_it_does_not_write(self):
        # A name past 32 characters and a colour's, which the Nextion Editor
        # refuses, and a value past 4 bytes.
        project = project_of(page())
        for line in ("int %s=1" % ("n" * 33), "int RED=1", "int a=2147483648"):
            with self.subTest(line=line):
                project.program = line.encode("ascii")
                with self.assertRaisesRegex(frame.FrameError,
                                            "does not write the int declaration"):
                    frame.int_variables(project)
        project.program = b"int a=1\r\nint b=2,a=3"
        with self.assertRaisesRegex(frame.FrameError, "declares a more than once"):
            frame.int_variables(project)

    def test_int_variables_of_other_forms(self):
        # Names up to 32 characters; spaces after int, around a name, its
        # "=", and its value; and values with leading zeros, a sign, or -0.
        ints = [("sys0", 0), ("sys1", 0), ("sys2", 0)]
        for name, more in (
                ("frame-int-names-past-14", [("abcdefghijklmno", 4), ("settingsPending", 1),
                                             ("pic_buttonNumpadBackspacePressed", 3)]),
                ("frame-int-declarations-with-spaces", [("count", 7), ("b", 3), ("c", 4),
                                                        ("d", 5), ("e", 5), ("f", 6)]),
                ("frame-int-values-of-other-forms", [("a", 7), ("b", 5), ("c", 0)])):
            with self.subTest(name):
                project = probe_facts(probe_named(frame_probes.PROBES, name))
                self.assertEqual(frame.int_variables(project), ints + more)

    def test_a_program_s_without_code(self):
        # The Nextion Editor writes a program.s of comments alone as one of
        # no lines: the page 0 it appends alone, and no int variable. It
        # writes one of no lines, or of blank lines alone, as a new
        # project's.
        project = project_of(page())
        for program, name in ((b"// only a comment\r\n", "frame-program-s-of-a-comment-alone"),
                              (b"", "frame-program-s-empty"),
                              (b"\r\n\r\n", "frame-program-s-empty")):
            with self.subTest(program=program):
                project.program = program
                self.assertEqual(laid_out_pieces(project)["program-s"],
                                 piece(probe_named(frame_probes.PROBES, name), "program-s"))

    def test_an_int_declaration_after_code(self):
        # The Nextion Editor refuses to compile one, saying "Global variable
        # definitions must precede all code in the program".
        project = project_of(page())
        project.program = b"// a comment\r\nint a=1\r\nbaud=9600\r\nint b=2"
        with self.assertRaisesRegex(frame.FrameError, "int b=2.* after code"):
            frame.int_variables(project)


class MemoryRunTest(unittest.TestCase):
    """A page's memory starts with a run of 0xFF bytes, one per object, the
    page included, rounded up to a multiple of 4. The run moves the page's
    base, and so its components', and counts in the page index's memory.
    The values are those of the Nextion Editor's files of a page of 3, 4,
    and 8 texts, each of 20 bytes of memory, and of 250 small texts."""

    def test_pages_of_more_than_four_objects(self):
        for texts, page_base, memory in ((3, 20, 72), (4, 24, 96), (8, 28, 180)):
            components = [text_component("t%d" % number, x=10 + 150 * (number % 2),
                                         y=10 + 50 * (number // 2)) for number in range(texts)]
            code = frame.user_code(project_of(page(*components)), frame_probes.stand_in_code)
            with self.subTest(texts=texts):
                self.assertEqual(struct.unpack_from("<I", code.data, 0)[0], page_base)
                # The first text's memory follows the page's 8 bytes.
                self.assertEqual(struct.unpack_from("<I", code.data, 24 * 33)[0], page_base + 8)
                self.assertEqual(struct.unpack_from("<I", code.page_index, 12)[0], memory)

    def test_a_page_of_250_texts(self):
        # The most components on a page: a run of 252 bytes, for 251 objects.
        code = frame.user_code(project_of(page(*page_probes.small_texts(250))),
                               frame_probes.stand_in_code)
        self.assertEqual(struct.unpack_from("<I", code.data, 0)[0], 268)
        self.assertEqual(struct.unpack_from("<I", code.data, 24 * 33)[0], 276)
        self.assertEqual(struct.unpack_from("<I", code.page_index, 12)[0], 3260)

    def test_each_page_its_own_run(self):
        # A page of 1 text, then one of 4: 4 bytes of 0xFF, then 8.
        code = frame.user_code(project_of(
            page(text_component()),
            page(*[text_component("t%d" % number, y=10 + 50 * number) for number in range(4)],
                 name="page1")), frame_probes.stand_in_code)
        # Page 1's data follows page 0's, a page's 33 entries and a text's 41.
        self.assertEqual(struct.unpack_from("<I", code.data, 0)[0], 20)
        self.assertEqual(struct.unpack_from("<I", code.data, 24 * (33 + 41))[0], 24)


class ScratchImageTest(unittest.TestCase):
    """What a page's memory block shows of the Nextion Editor's scratch
    image on P, where a local txt's room leaves its bytes, over a global
    object's memory in the int area."""

    def test_a_global_variable_keeps_its_values(self):
        # A global variable of a text, 16 bytes: its head of 4 bytes, type
        # 0x34, ID 12, vscope 1, and kind 7, then its sta, 1, its txt_maxl,
        # 255, and its txt's place, 0x3570. Only its kind, the one byte of
        # its head the Nextion Editor fills in late, is 0 there: its values
        # show through, as in a TFT file the Nextion Editor wrote for a real
        # project.
        variable = bytes.fromhex("34 0c 01 07 01 00 ff 00 70 35 00 00 00 00 00 00")
        int_area = bytes(16) + variable
        layout = mock.Mock(memory_block=0, rooms=[(0, 0, 32)], heads=[])
        blocks = [bytes(32)]
        frame._through_the_scratch_image(blocks, [layout], [0], int_area, [(16, 4)])
        self.assertEqual(blocks[0][16:], bytes.fromhex(
            "34 0c 01 00 01 00 ff 00 70 35 00 00 00 00 00 00"))

    def test_global_variables_under_a_room(self):
        # The probe's page, made in memory: a global variable of a text, va0,
        # ID 4, and one of a number, va1, ID 5, of val 7, show through a
        # local text's room of 1001 bytes, each with its values and only its
        # kind at 0, as in the Nextion Editor's file.
        code = frame.user_code(probe_project(next(
            probe for probe in p_probes.PROBES
            if probe.name == "p-globals-variables-under-a-wide-room")))
        pages_blocks = b"".join(code.blocks[1:])
        self.assertIn(bytes.fromhex("34 04 01 00 01 00 0a 00"), pages_blocks)
        self.assertIn(bytes.fromhex("34 05 01 00 00 00 00 00 00 00 00 00 07 00 00 00"),
                      pages_blocks)

    def test_a_whole_head_is_filled_late(self):
        # A global text's head, of 52 bytes: its bytes from 3 to 31 are 0.
        head = bytes(range(1, 53))
        layout = mock.Mock(memory_block=0, rooms=[(0, 0, 52)], heads=[])
        blocks = [bytes(52)]
        frame._through_the_scratch_image(blocks, [layout], [0], head, [(0, 52)])
        self.assertEqual(blocks[0], head[:3] + bytes(29) + head[32:])


class PageValuesTest(unittest.TestCase):
    """A page's attributes that its memory gives on T, as the Nextion Editor
    wrote them: its swipe targets up, down, left, and right, then its sta, 2
    bytes, then its background, 2 bytes."""

    def memories(self, name: str) -> list:
        project = probe_facts(probe_named(page_probes.PROBES, name))
        return [frame.page_memory_of(made.objects[0]) for made in project.pages[:3]]

    def test_its_background(self):
        # No background gives 0; a picture its pic, 1, 2, or 65535 for none.
        self.assertEqual(self.memories("page-of-no-background"),
                         [bytes.fromhex("ff ff ff ff 00 00 00 00"),
                          bytes.fromhex("ff ff ff ff 01 00 e0 07")])
        self.assertEqual(self.memories("page-of-pictures"),
                         [bytes.fromhex("ff ff ff ff 02 00 01 00"),
                          bytes.fromhex("ff ff ff ff 02 00 02 00"),
                          bytes.fromhex("ff ff ff ff 02 00 ff ff")])
        # A pic past the project's last picture is written as it is.
        self.assertEqual(self.memories("page-of-a-picture-past-the-last"),
                         [bytes.fromhex("ff ff ff ff 02 00 05 00")])
        # A bco or a pic that its sta does not show is not kept.
        self.assertEqual(self.memories("page-of-hidden-backgrounds"),
                         [bytes.fromhex("ff ff ff ff 02 00 01 00"),
                          bytes.fromhex("ff ff ff ff 00 00 00 00"),
                          bytes.fromhex("ff ff ff ff 01 00 00 f8")])

    def test_its_bco(self):
        self.assertEqual(self.memories("page-of-other-colours"),
                         [bytes.fromhex("ff ff ff ff 01 00 00 00"),
                          bytes.fromhex("ff ff ff ff 01 00 00 f8")])

    def test_its_swipe_targets(self):
        # page2's up is 200, which no page of the project has.
        self.assertEqual(self.memories("page-of-swipes"),
                         [bytes.fromhex("01 02 03 00 01 00 ff ff"),
                          bytes.fromhex("03 00 02 01 01 00 ff ff"),
                          bytes.fromhex("c8 ff ff ff 01 00 ff ff")])


class PageBackgroundTest(unittest.TestCase):
    """What a page's sta changes past its memory, as the Nextion Editor
    wrote it on T: its entries, and its components' background fills."""

    def test_its_entries(self):
        # A page with no background has 32 entries, and those of the pages
        # and components after it are numbered one down.
        project = probe_facts(probe_named(page_probes.PROBES, "page-of-no-background"))
        self.assertEqual([component_types.page_entries(made.objects[0])
                          for made in project.pages], [32, 33])
        # page0's text, number, and button take 41, 41, and 42.
        first = component_types.first_entries(project)
        self.assertEqual((first[(0, "t0")], first[(1, "page1")]), (32, 32 + 41 + 41 + 42))

    def test_its_components_background_fills(self):
        # A fill with the page's bco, entry 24; the same part of the page's
        # pic, with xpic; and none on a page with no background. Each text's
        # place is its probe's table's.
        for name, fill in (
                ("page-of-other-colours", b"\x09\x0d\x0410,10,100,30,"),
                ("page-of-pictures", b"\x09\x0a\x0410,10,100,30,10,10,"),
                ("page-of-no-background", None)):
            probe = probe_named(page_probes.PROBES, name)
            project = probe_facts(probe)
            text = project.pages[0].objects[1]
            with self.subTest(name):
                self.assertEqual(component_types.background_fill(text, project,
                                                                 place(probe, "page0-1")),
                                 [fill + b"\x01\x18\x00\x00\x00"] if fill else [])


class MatchedTest(unittest.TestCase):
    """The needs frame.MATCHED covers (matching.py)."""

    def test_what_it_covers(self):
        covered = [Need("type", "page"), Need("encoding", "iso-8859-1"),
                   Need("attribute", "page.objname", b"Main_Screen_14"),
                   Need("attribute", "page.w", (320).to_bytes(2, "little")),
                   Need("code", "program.s", "int sys0=0,sys1=0,sys2=0"),
                   Need("code", "program.s", "int lo=-2147483648,hi=2147483647"),
                   Need("code", "program.s", "int %s=1" % ("n" * 32)),
                   Need("code", "program.s", "int e = 5 , f = 6"),
                   Need("code", "program.s", "int a=007,b=+5,c=-0,d=0xFFFFFFFF"),
                   Need("code", "program.s", "int\ta=1 ")]
        # Its values, at their ends, and each sta.
        for name, ends in (("bco", (0, 0xFFFF)), ("up", (0, 255)), ("down", (0, 255)),
                           ("left", (0, 255)), ("right", (0, 255)), ("sta", (0, 1, 2)),
                           ("pic", (0, 0xFFFF))):
            covered += [Need("attribute", "page." + name, end.to_bytes(2, "little"))
                        for end in ends]
        self.assertEqual(unmatched(covered, frame.MATCHED), [])

    def test_a_declaration_past_767_characters(self):
        # The Nextion Editor compiled declarations of up to 1500 characters,
        # past the 767 it holds other lines to on T.
        for length in (768, 1000, 1500):
            line = frame_probes.int_declaration_of(length)
            with self.subTest(length=length):
                self.assertEqual(len(line), length)
                self.assertEqual(unmatched([Need("code", "program.s", line)], frame.MATCHED), [])

    def test_each_encoding_of_the_nextion_editor(self):
        covered = [Need("encoding", name) for name in ENCODINGS.values()]
        self.assertEqual(len(covered), 24)
        self.assertEqual(unmatched(covered, frame.MATCHED), [])
        left = [Need("encoding", "latin-1"), Need("encoding", "cp936")]
        self.assertEqual(unmatched(left, frame.MATCHED), left)

    def test_code_past_ascii(self):
        # The line's own rule checks the rest of it. In shift-jis and big5,
        # 表 and 許 end in 0x5C, as ソ and 能 do. A line of 769 bytes and one
        # of 4095 are taken, as nxwright's build refuses a line longer than
        # its series takes, 767 bytes on T and 4095 on P.
        covered = [Need("text in code", encoding, line) for encoding, line in (
            ("iso-8859-1", 't0.txt="é"'), ("gb2312", 't0.txt="中文"'),
            ("utf-8", 'xstr 0,0,9,9,0,RED,WHITE,0,0,1,"é中\U0001F600"'),
            ("shift-jis", 'if(t0.txt=="表日ソ能a")'), ("big5", 't0.txt="許中"'),
            ("gb2312", 't0.txt="%s"' % ("中" * 380)),
            ("gb2312", 't0.txt="%s"' % ("中" * 2043)),
            # The Nextion Editor refuses these, as it misreads their texts by
            # their bytes, but nxwright's build refuses them first.
            ("shift-jis", 'if(t0.txt=="日本表")'), ("big5", 'prints "中許",0'),
            ("shift-jis", 't0.txt="aｱ"'))]
        self.assertEqual(unmatched(covered, frame.MATCHED), [])
        # A character the encoding does not write.
        left = [Need("text in code", encoding, line) for encoding, line in (
            ("iso-8859-1", 't0.txt="中"'), ("iso-8859-2", 't0.txt="ñ"'))]
        self.assertEqual(unmatched(left, frame.MATCHED), left)

    def test_what_it_leaves_out(self):
        left = [# Its values past their ends.
                Need("attribute", "page.sta", (3).to_bytes(2, "little")),
                Need("attribute", "page.up", (256).to_bytes(2, "little")),
                Need("attribute", "page.down", (256).to_bytes(2, "little")),
                Need("attribute", "page.left", (256).to_bytes(2, "little")),
                Need("attribute", "page.right", (256).to_bytes(2, "little")),
                Need("attribute", "page.bco", (65536).to_bytes(4, "little")),
                Need("code", "program.s", "  int a=1"),
                # What the Nextion Editor refuses: a name twice, a colour's,
                # and one past 32 characters.
                Need("code", "program.s", "int a=1,a=2"),
                Need("code", "program.s", "int RED=1"),
                Need("code", "program.s", "int %s=1" % ("n" * 33)),
                Need("code", "program.s", "int a=2147483648"),
                Need("code", "program.s", "baud=9600")]
        self.assertEqual(unmatched(left, frame.MATCHED), left)

    def test_the_groups_and_lock_of_the_types_without_a_place_on_p(self):
        # Their lockobj, groupid0, and groupid1, which change nothing in the
        # file, on P and E; not the other attributes every object has.
        for type_name in ("timer", "variable", "touch-capture", "audio", "file-stream"):
            for series in ("P", "E"):
                with self.subTest(type_name, series=series):
                    covered = [Need("attribute", "%s.%s" % (type_name, name),
                                    value.to_bytes(4, "little"), series=series)
                               for name, value in (("lockobj", 1), ("groupid0", 3),
                                                   ("groupid1", 4))]
                    self.assertEqual(unmatched(covered, frame.MATCHED), [])
                    left = [Need("attribute", type_name + ".drag", b"\x01", series=series)]
                    self.assertEqual(unmatched(left, frame.MATCHED), left)

    def test_a_page_of_any_number_of_components(self):
        # nxwright's build refuses a page of more than 250 components, as the
        # Nextion Editor does, so nxwright takes any page it is given.
        def page(components: int) -> Need:
            return Need("type", "page", context={"components": {
                "t%d" % number: 116 for number in range(components)}})
        self.assertEqual(unmatched([page(250), page(251)], frame.MATCHED), [])


class PiecesTest(unittest.TestCase):
    """Where frame.laid_out says each piece lies: its pieces cover each part
    of the user code, and an object's pieces hold what its type gives, on a
    page of two progress bars, j0 and j1, as the probe progress-bar-two has
    them."""

    @classmethod
    def setUpClass(cls):
        cls.project = project_of(page(progress_bar_component(),
                                      progress_bar_component("j1", y=60)))
        cls.code, pieces, cls.places = frame.laid_out(cls.project, stand_in_code)
        cls.pieces = {piece.name: piece for piece in pieces}
        cls.parts = {"blocks": encode_blocks(cls.code.blocks), "variables": cls.code.variables,
                     "data": cls.code.data, "page index": cls.code.page_index,
                     "records": cls.code.records, "macros": cls.code.macros}

    def bytes_of(self, name: str) -> bytes:
        piece = self.pieces[name]
        return self.parts[piece.part][piece.start:piece.end]

    def test_they_cover_each_part(self):
        for part, data in self.parts.items():
            with self.subTest(part):
                # Each starts where the one before ends, from 0 to the
                # part's end; an empty part, such as the macros' table of a
                # project without macros, has none.
                ends = [0] + [end for _, end in sorted((piece.start, piece.end)
                                                       for piece in self.pieces.values()
                                                       if piece.part == part)]
                starts = sorted(piece.start for piece in self.pieces.values()
                                if piece.part == part)
                self.assertEqual(starts, ends[:-1])
                self.assertEqual(ends[-1], len(data))

    def test_the_shared_helper_gives_each_piece_where_it_lies(self):
        # unit_inputs.laid_out_pieces, which the tests of pieces compare.
        pieces = laid_out_pieces(self.project)
        self.assertEqual(sorted(pieces), sorted(self.pieces))
        for name, data in pieces.items():
            with self.subTest(name):
                self.assertEqual(data, self.bytes_of(name))

    def test_an_object_s_pieces(self):
        # Each progress bar's memory, its drawing and a 0 word, its entries,
        # and its record. j0's first entry is 33 and its base 28; j1's 66
        # and 36.
        page_objects = frame._at_the_screen(self.project).pages[0].objects
        for object_id, place in ((1, ObjectPlace(0, 1, 33, 0, 28)),
                                 (2, ObjectPlace(0, 2, 66, 0, 36))):
            bar = page_objects[object_id]
            variant = progress_bar.variant(bar)
            name = "page0-%d-" % object_id
            with self.subTest(object_id):
                self.assertEqual(self.bytes_of(name + "memory"), variant.memory(bar, None))
                self.assertEqual(self.bytes_of(name + "entries"),
                                 variant.data(bar, self.project, place))
                self.assertEqual(self.bytes_of(name + "drawing"), encode_blocks(
                    variant.drawing(bar, self.project, place) + [b""]))
                # Its record starts with its type and its ID.
                self.assertEqual(self.bytes_of(name + "record")[:2],
                                 bytes([bar.attribute("type")[0], object_id]))

    def test_the_project_s_pieces(self):
        # The first block's pieces, which together give it, then program.s
        # up to the page's blocks; the variables and the page index; and the
        # page's own pieces.
        first_block = ("first-block-head", "int-variables", "global-texts", "page-list")
        self.assertEqual(b"".join(self.bytes_of(name) for name in first_block),
                         encode_blocks(self.code.blocks[:1]))
        self.assertEqual(self.pieces["program-s"].start, self.pieces["page-list"].end)
        self.assertEqual(self.pieces["program-s"].end, self.pieces["page0-0-drawing"].start)
        self.assertEqual(self.bytes_of("variables"), self.code.variables)
        self.assertEqual(self.bytes_of("page-index"), self.code.page_index)
        self.assertEqual(sorted(name for name in self.pieces if name.startswith("page0-0-")),
                         ["page0-0-drawing", "page0-0-entries", "page0-0-event-down",
                          "page0-0-event-loadend", "page0-0-event-unload", "page0-0-event-up",
                          "page0-0-memory", "page0-0-record"])


class PlacesTest(unittest.TestCase):
    """Where the page and each component lie, as frame.laid_out gives it,
    and as a probe's pieces.json keeps it for the tests of its type and of
    the page's own pieces (unit_inputs.place)."""

    def test_each_object_s_place(self):
        # page0 of progress-bar-two: its first entry 0, and its base 20, after
        # the int area's 16 bytes, the base's three ints and the buffers'
        # total, and its run of 0xFF, 4 bytes for its three objects. Then j0
        # and j1: their first entries 33 and 66, after the page's 33 and
        # j0's 33, and their bases 28 and 36, after the page's 8 bytes.
        _, _, places = frame.laid_out(project_of(page(
            progress_bar_component(), progress_bar_component("j1", y=60))), stand_in_code)
        self.assertEqual(sorted(places), ["page0-0", "page0-1", "page0-2"])
        self.assertEqual([(place.object_id, place.first_entry, place.base)
                          for place in places.values()], [(0, 0, 20), (1, 33, 28), (2, 66, 36)])

    def test_a_probe_keeps_each_place(self):
        probe = next(probe for probe in progress_bar_probes.PROBES
                     if probe.name == "progress-bar-two")
        self.assertEqual(place(probe, "page0-1"), ObjectPlace(0, 1, 33, 0, 28))
        self.assertEqual(place(probe, "page0-2"), ObjectPlace(0, 2, 66, 0, 36))


class PMemoryPiecesTest(unittest.TestCase):
    """On P, a component's memory starts with its record's head, which the
    frame writes: the head is a piece of its own, and the memory piece holds
    what the type writes after it (component_types.p_component_memory)."""

    def test_the_head_and_the_type_s_values(self):
        # A progress bar's memory holds a whole head; a timer's its own 28
        # bytes (P_HEAD_SIZE).
        for component, head_size in ((progress_bar_component(), frame._HEAD_SIZE),
                                     (timer_component(), timer.P_HEAD_SIZE)):
            with self.subTest(component):
                project = project_of(page(component, series="P"), series="P")
                page_object = project.pages[0].objects[1]
                module = component_types.object_module(page_object)
                pieces = laid_out_pieces(project)
                self.assertEqual(len(pieces["page0-1-head"]), head_size)
                values = component_types.p_component_memory(
                    page_object, bytes(head_size),
                    component_types.p_table(module, page_object, project), module.P_MEMORY_SIZE)
                self.assertEqual(pieces["page0-1-memory"], values[head_size:])
                # The page's own memory starts with a whole head.
                self.assertEqual(len(pieces["page0-0-head"]), frame._HEAD_SIZE)


class FirstBlockPiecesTest(unittest.TestCase):
    """The first block's pieces, which together give it: its head, its int
    area's, a global object's memory among them, named as a local object's,
    its page list, and on P its table of attribute names."""

    def first_block(self, project) -> tuple:
        """Returns the user code of `project`, its pieces by name, and the
        names of those of its first block, in order."""
        code, laid, _ = frame.laid_out(project, stand_in_code)
        end = len(encode_blocks(code.blocks[:1]))
        return (code, laid_out_pieces(project),
                [piece.name for piece in laid if piece.part == "blocks" and piece.end <= end])

    def test_a_global_variable_on_t(self):
        # Its memory, the type's, after the int variables.
        project = project_of(page(variable_probes.variable_component(val=5) + "vscope = 1\n"))
        code, pieces, names = self.first_block(project)
        self.assertEqual(names, ["first-block-head", "int-variables", "page0-1-memory",
                                 "global-texts", "page-list"])
        self.assertEqual(b"".join(pieces[name] for name in names),
                         encode_blocks(code.blocks[:1]))
        va0 = project.pages[0].objects[1]
        self.assertEqual(pieces["page0-1-memory"],
                         component_types.object_module(va0).memory(va0, project))

    def test_a_global_data_record_on_p(self):
        # Its head, of a whole head's size, then its values, as its type
        # writes them; the table of attribute names last.
        project = project_of(page(data_record_probes.data_record_component(), series="P"),
                             series="P")
        code, pieces, names = self.first_block(project)
        self.assertEqual(names, ["first-block-head", "int-variables", "page0-1-head",
                                 "page0-1-memory", "global-texts", "page-list",
                                 "attribute-names"])
        self.assertEqual(b"".join(pieces[name] for name in names),
                         encode_blocks(code.blocks[:1]))
        self.assertEqual(len(pieces["page0-1-head"]), frame._HEAD_SIZE)
        _, _, places = frame.laid_out(project, stand_in_code)
        self.assertEqual(pieces["page0-1-memory"],
                         p_values(project.pages[0].objects[1], places["page0-1"], project))


def _probes_of_the_user_code() -> list:
    """Returns each probe of tools/tft/probing that keeps the whole user code as
    its pieces, and whose pages are made in memory, once by its name. Each
    is a condition of the tests of the frame's parts below: one page or
    several, of every type, background, and effect, with code or without,
    global or local, on T and on P."""
    found = {}
    for module in pkgutil.iter_modules(tools.tft.probing.__path__):
        for probe in getattr(importlib.import_module("tools.tft.probing." + module.name), "PROBES",
                             ()):
            if (probe.fixtures is not None and made_in_memory(probe)
                    and "first-block-head" in piece_names(probe)):
                found[probe.name] = probe
    return list(found.values())


def _facts(probe):
    """Returns the Project of facts of `probe`'s pages, each at its screen's
    place and size, as the frame lays a page out (frame._at_the_screen)."""
    return frame._at_the_screen(probe_facts(probe))


def page_record_places(probe, number: int, on_p: bool) -> dict:
    """Returns the places the record of the page `number` of `probe` gives,
    as the frame notes them while it lays out the page's blocks: where its
    drawing starts among the user code's blocks; its first block's place,
    when its drawing has blocks; and each of its down, up, and unload
    events' code's, after the event's name, when the event has blocks. Each
    is read from where `probe`'s table puts the page's pieces
    (blocks_place). A drawing without blocks is a 0 word on P, and on T,
    K, and F a 0 word and an empty background fill's."""
    name = "page%d-0" % number
    places = {"drawing": blocks_place(probe, name + "-drawing")}
    if piece(probe, name + "-drawing") != encode_blocks([b""] if on_p else [b"", b""]):
        places[frame._FIRST_BLOCK] = places["drawing"]
    for event in frame.NAMED_EVENTS:
        label = encode_blocks([event.encode("ascii")])
        each = "%s-event-%s" % (name, event)
        if piece(probe, each) != label + encode_blocks([b""]):
            places[event] = blocks_place(probe, each) + len(label)
    return places


class PageTest(unittest.TestCase):
    """A page's own pieces, each at the frame's function that writes it,
    against each page of each probe of the whole user code: its drawing
    (page_drawing), its memory (page_memory_of, and on P _p_page_memory,
    its record's head and its values each a piece), its entries
    (_page_entries and _p_page_entries), and its record (_page_record). Its
    first entry and its memory's base are its place in the probe's
    table."""

    @classmethod
    def setUpClass(cls):
        # (the probe, the page's number, its page object, its place, the
        # Project of facts, whether it is on P), for each page of each probe.
        cls.pages = []
        for probe in _probes_of_the_user_code():
            project = _facts(probe)
            on_p = project.settings.model.series in SERIES_WRITTEN_AS_P
            cls.pages += [(probe, number, made.objects[0], place(probe, "page%d-0" % number),
                           project, on_p) for number, made in enumerate(project.pages)]

    def assert_each(self, kind: str, function):
        for probe, number, page_object, its_place, project, on_p in self.pages:
            with self.subTest(probe.name, page=number):
                self.assertEqual(function(probe, number, page_object, its_place, project, on_p),
                                 piece(probe, "page%d-0-%s" % (number, kind)))

    def test_its_pages(self):
        self.assertEqual((len({probe.name for probe, *_ in self.pages}), len(self.pages)),
                         (439, 518))

    def test_its_drawing(self):
        # Its blocks, then its 0 word and an empty background fill; on P, its
        # 0 word alone.
        self.assert_each("drawing", lambda probe, number, page_object, its_place, project, on_p:
                         encode_blocks([b""]) if on_p else encode_blocks(
                             frame.page_drawing(page_object, its_place.first_entry)
                             + frame.AFTER_PAGE_DRAWING))

    def test_its_memory(self):
        def memory(probe, number, page_object, its_place, project, on_p):
            if not on_p:
                return frame.page_memory_of(page_object)
            places = page_record_places(probe, number, on_p)
            return frame._p_page_memory(page_object, places, its_place.base)[frame._HEAD_SIZE:]
        self.assert_each("memory", memory)

    def test_its_memory_s_head_on_p(self):
        # On P, the page's memory starts with its record's head, with its
        # drag, its movex, and its movey (_p_page_memory), a piece of its own.
        compared = 0
        for probe, number, page_object, its_place, project, on_p in self.pages:
            if not on_p:
                continue
            with self.subTest(probe.name, page=number):
                places = page_record_places(probe, number, on_p)
                self.assertEqual(
                    frame._p_page_memory(page_object, places, its_place.base)[:frame._HEAD_SIZE],
                    piece(probe, "page%d-0-head" % number))
            compared += 1
        self.assertEqual(compared, 309)

    def test_its_entries(self):
        self.assert_each("entries", lambda probe, number, page_object, its_place, project, on_p: (
            frame._p_page_entries if on_p else frame._page_entries)(
                page_object, number, its_place.base, project))

    def test_its_record(self):
        self.assert_each("record", lambda probe, number, page_object, its_place, project, on_p:
                         frame._page_record(page_object, page_record_places(probe, number, on_p),
                                            its_place.base,
                                            frame._attribute_names(project) if on_p else None))


class FirstBlockTest(unittest.TestCase):
    """The first block's own pieces, at the frame's functions that write
    it, against each probe of the whole user code: its head (_first_block),
    the int variables and the global objects' texts and buffers' total
    (_GlobalMemory, int_variables), the page list (_first_block_regions),
    and on P the table of attribute names (_attribute_names), where
    _first_block_pieces puts each. A global object's memory there is its
    type's, which its type's tests compare."""

    OWN = ("first-block-head", "int-variables", "global-texts", "page-list", "attribute-names")

    def test_each_probe(self):
        compared = 0
        for probe in _probes_of_the_user_code():
            project = _facts(probe)
            names = (frame._attribute_names(project)
                     if project.settings.model.series in SERIES_WRITTEN_AS_P else None)
            memory = frame._GlobalMemory(CompileContext(project), frame.int_variables(project))
            pages = [made.objects[0] for made in project.pages]
            block = encode_blocks([frame._first_block(memory.int_area, pages, names)])
            laid = [each for each in frame._first_block_pieces(
                memory, frame._first_block_regions(memory.int_area, pages, names))
                if each.name in self.OWN]
            with self.subTest(probe.name):
                self.assertEqual(sorted(each.name for each in laid),
                                 sorted(name for name in piece_names(probe) if name in self.OWN))
            for each in laid:
                with self.subTest(probe.name, piece=each.name):
                    self.assertEqual(block[each.start:each.end], piece(probe, each.name))
                compared += 1
        self.assertEqual(compared, 2030)


class VariablesTest(unittest.TestCase):
    """The table of the int variables, at the frame's function that writes it
    (_variable_table), for the variables it reads (int_variables), against
    each probe of the whole user code."""

    def test_each_probe(self):
        compared = 0
        for probe in _probes_of_the_user_code():
            with self.subTest(probe.name):
                self.assertEqual(frame._variable_table(frame.int_variables(_facts(probe))),
                                 piece(probe, "variables"))
            compared += 1
        self.assertEqual(compared, 439)


def _probes(*names: str) -> list:
    """Returns the probes of tools/tft/probing named `names`, from the modules
    of RecordTest's and PageIndexTest's conditions."""
    by_name = {probe.name: probe for module in (shared_attribute_probes, timer_probes,
                                                button_probes, overlap_probes, page_probes,
                                                p_probes)
               for probe in module.PROBES}
    return [by_name[name] for name in names]


class RecordTest(unittest.TestCase):
    """Each component's record, at the frame's function that writes it,
    frame._component_record: on T, its head then its slots, each slot its
    type's entry counted from its page's; on P, its head, then the entries
    of the attributes P's table names. Each takes the component's page object,
    its place from its probe's table (unit_inputs.place), and the places of
    its blocks, read from where the table puts its pieces
    (unit_inputs.record_places), against its piece pageP-N-record. The
    page's own record is left to the tests of the page's own pieces."""

    # The conditions that vary a record on T, each by the probes that show
    # it.
    CONDITIONS = {
        # Every type, drawn and not, with events and without, with its aph
        # and its sendkey across their range.
        "every type": _probes("shared-attributes-aph-and-sendkey-of-each-type"),
        # An effect, whose two more entries move the slots, and a second page.
        "effects and a second page": _probes("shared-attributes-effects-of-each-type",
                                             "timer-on-two-pages", "button-on-second-page"),
        # Global objects, whose bases lie in the int area, on one page and on
        # two.
        "global objects": _probes("shared-attributes-every-type-global",
                                  "shared-attributes-globals-on-two-pages"),
        # Code in events, which gives the places of their code.
        "code in events": _probes("timer-event-code", "button-event-code"),
        # A background fill that holds refs, and IDs past 9.
        "refs and IDs past 9": _probes("overlap-two", "overlap-ids-past-9"),
    }

    @staticmethod
    def record(probe, project, name: str, page_object) -> bytes:
        """Returns the record frame._component_record gives the component
        `name` of `probe`, `page_object`, in `project`: on P, with the
        attributes the records name and the component's P table."""
        its_place = place(probe, name)
        module = component_types.object_module(page_object)
        options = {}
        if project.settings.model.series in component_types.SERIES_WRITTEN_AS_P:
            options = {"names": frame._attribute_names(project),
                       "table": component_types.p_table(module, page_object, project)}
        return frame._component_record(page_object, module, its_place,
                                       record_places(probe, name, page_object), **options)

    def assert_each_record(self, probes: list) -> int:
        """Checks each component's record in `probes`, and returns how many
        there are."""
        compared = 0
        for probe in probes:
            project = probe_facts(probe)
            for number, made in enumerate(project.pages):
                for object_id, page_object in enumerate(made.objects[1:], 1):
                    name = "page%d-%d" % (number, object_id)
                    with self.subTest(probe.name, component=name):
                        self.assertEqual(self.record(probe, project, name, page_object),
                                         piece(probe, name + "-record"))
                    compared += 1
        return compared

    def test_on_t(self):
        # Each condition's records, by how many each condition's probes
        # hold.
        counts = {condition: self.assert_each_record(probes)
                  for condition, probes in self.CONDITIONS.items()}
        self.assertEqual(counts, {"every type": 19, "effects and a second page": 24,
                                  "global objects": 42, "code in events": 3,
                                  "refs and IDs past 9": 15})

    def test_on_p(self):
        # Every probe of P whose pages are made in memory and whose pieces
        # give a component's record, which only a probe that keeps its whole
        # user code has: each of P's types, on one page and on two, global
        # or not.
        self.assertEqual(self.assert_each_record(self.p_probes()), 719)

    @staticmethod
    def p_probes() -> list:
        """Returns every probe of P whose pages are made in memory and whose
        pieces give a component's record, which only a probe that keeps its
        whole user code has."""
        return [probe for probe in p_probes.PROBES if probe.fixtures and made_in_memory(probe)
                and any(name.endswith("-record") and not name.startswith("page0-0")
                        for name in piece_names(probe))]

    def test_its_memory_s_head_on_p(self):
        # On P, a component's memory starts with a head, a piece of its own
        # (frame._p_component_memory). The head is its record's head but for
        # its last place, with its drag, its movex, and its movey, or as
        # much of it as its type gives. A type may write bytes there too, as
        # a hotspot its aph's. Each component of each probe of test_on_p.
        compared = 0
        for probe in self.p_probes():
            project = probe_facts(probe)
            for number, made in enumerate(project.pages):
                for object_id, page_object in enumerate(made.objects[1:], 1):
                    name = "page%d-%d" % (number, object_id)
                    module = component_types.object_module(page_object)
                    memory = frame._p_component_memory(page_object, module, place(probe, name),
                                                       record_places(probe, name, page_object),
                                                       project)
                    with self.subTest(probe.name, component=name):
                        self.assertEqual(memory[:frame._p_head_size(module)],
                                         piece(probe, name + "-head"))
                    compared += 1
        self.assertEqual(compared, 719)


class PageIndexTest(unittest.TestCase):
    """The page index, at the frame's function that writes it
    (frame._page_index), against its piece page-index.

    Each page's number of objects comes from its page made in memory. The
    rest is read from the probe's table:
    - where its objects table lies among the user code's blocks;
    - the size of its entries, the sum of its entries pieces;
    - the size of its memory. The piece of its memory's run starts at the
      memory block's size word, and the memory runs from after that word to
      the page's texts;
    - where the first page's entries start in the user code
      (unit_inputs.user_code_place)."""

    # The conditions that vary the page index, each by the probes that show
    # it.
    CONDITIONS = {
        # One page.
        "one page": _probes("overlap-two"),
        # Several pages, with components and without, whose objects and
        # entries add up page after page.
        "several pages": _probes("page-of-swipes", "page-of-pictures",
                                 "page-of-no-background"),
        # Many objects, past 9.
        "many objects": _probes("page-every-type-on-a-picture", "overlap-ids-past-9"),
        # Global objects, whose memory their page's leaves out, on one page
        # and on two, and a global page, whose memory is the int area's.
        "global objects": _probes("shared-attributes-globals-on-two-pages",
                                  "shared-attributes-every-type-global"),
        # On P, whose pages' memory and entries differ: several pages, and
        # global objects.
        "on P": _probes("p-page-of-swipes", "p-text-on-two-pages", "p-globals-beside-a-text",
                        "p-data-record-on-two-pages"),
    }

    @staticmethod
    def index(probe) -> bytes:
        """Returns the page index frame._page_index gives `probe`'s pages."""
        names, pages = piece_names(probe), []
        for number, made in enumerate(probe_facts(probe).pages):
            prefix = "page%d-" % number
            entries = sum(len(piece(probe, name)) for name in names
                          if name.startswith(prefix) and name.endswith("-entries"))
            memory = (user_code_place(probe, prefix + "texts")
                      - user_code_place(probe, prefix + "memory-run") - len(encode_blocks([b""])))
            pages.append((len(made.objects), blocks_place(probe, prefix + "objects-table"),
                          entries, memory))
        return frame._page_index(pages, user_code_place(probe, "page0-0-entries"))

    def test_each_condition(self):
        # Each probe's page index, as the frame writes it, is its piece.
        for condition, probes in self.CONDITIONS.items():
            for probe in probes:
                with self.subTest(condition, probe=probe.name):
                    self.assertEqual(self.index(probe), piece(probe, "page-index"))


class EntriesAndRunsTest(unittest.TestCase):
    """How the entries are numbered across objects and pages
    (component_types.first_entries), and what starts and ends each page's
    runs of memory and of its load section: its memory run
    (frame._memory_run, frame._p_memory_run), its objects' table
    (frame._objects_table), and the doevents its load code ends with
    (frame.DOEVENTS), at their functions, against the pieces of each probe
    that keeps its whole user code."""

    @classmethod
    def setUpClass(cls):
        cls.probes = [(probe, probe_facts(probe)) for probe in _probes_of_the_user_code()]

    def test_its_probes(self):
        self.assertEqual(len(self.probes), 439)

    def test_each_object_s_first_entry(self):
        # Each object's first entry is where its entries' piece starts in the
        # data, 24 bytes an entry: the pages' and their objects' entries, in
        # order, across pages.
        compared = 0
        for probe, project in self.probes:
            firsts = component_types.first_entries(project)
            kept = piece_names(probe)
            for number, made in enumerate(project.pages):
                for object_id, page_object in enumerate(made.objects):
                    name = "page%d-%d-entries" % (number, object_id)
                    if name not in kept:
                        continue
                    with self.subTest(probe.name, piece=name):
                        self.assertEqual(firsts[number, component_types.object_name(page_object)],
                                         piece_start(probe, name) // 24)
                    compared += 1
        self.assertEqual(compared, 1882)

    def test_each_page_s_objects_table(self):
        compared = 0
        for probe, project in self.probes:
            for number, made in enumerate(project.pages):
                with self.subTest(probe.name, page=number):
                    self.assertEqual(encode_blocks([frame._objects_table(made.objects)]),
                                     piece(probe, "page%d-objects-table" % number))
                compared += 1
        self.assertEqual(compared, 518)

    def test_each_page_s_memory_run(self):
        # After the memory's block's size word: on T, K, and F, its run of
        # 0xFF bytes; on the series written as P, the place of the page's
        # own memory, then each of its components' memories', each from its
        # place in the probe's table.
        compared = 0
        for probe, project in self.probes:
            for number, made in enumerate(project.pages):
                with self.subTest(probe.name, page=number):
                    if project.settings.model.series not in SERIES_WRITTEN_AS_P:
                        run = frame._memory_run(len(made.objects))
                    else:
                        run = frame._p_memory_run(
                            place(probe, "page%d-0" % number).base,
                            [place(probe, "page%d-%d" % (number, object_id)).base
                             for object_id in range(1, len(made.objects))])
                    self.assertEqual(piece(probe, "page%d-memory-run" % number)[
                        len(encode_blocks([b""])):], run)
                compared += 1
        self.assertEqual(compared, 518)

    def test_each_page_s_doevents(self):
        compared = 0
        for probe, project in self.probes:
            for number, _ in enumerate(project.pages):
                with self.subTest(probe.name, page=number):
                    self.assertEqual(encode_blocks([frame.DOEVENTS[probe.base]]),
                                     piece(probe, "page%d-doevents" % number))
                compared += 1
        self.assertEqual(compared, 518)

    def test_the_followers_doevents(self):
        # K and F as T's doevents, and E as P's, as each table of differences
        # changes it, as no follower's probe keeps the piece.
        leaders = {"T": "text-two", "P": "p-text-two"}
        for follower, leader in (("K", "T"), ("F", "T"), ("E", "P")):
            probe = next(probe for probe, _ in self.probes if probe.name == leaders[leader])
            with self.subTest(follower):
                self.assertEqual(encode_blocks([frame.DOEVENTS[follower]]), instruction_piece(
                    piece(probe, "page0-doevents"), DIFFERENCES[follower], set()))


if __name__ == "__main__":
    unittest.main()
