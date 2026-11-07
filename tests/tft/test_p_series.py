"""The P series (ResearchNotes/tft/p-series.md, tools/tft/probing/p_probes.py): the user code
the frame writes for pages on the P base folder (probes/P), against the
Nextion Editor's bytes for the blank project, a new project of NX8048P050,
and for the pages of some of the whole compile's probes
(compile_probes.py); and what the check matches on P. The pages are made
in memory (tests/tft/unit_inputs.py).

The fixtures the P probes kept are compared with their whole builds in
tests/tft/test_whole_files.py, until the tests of each type's pieces on P, and
of what the frame writes across objects, take them over.
"""
import struct
import unittest
from unittest import mock

from nxwright.project.editor_language import (EDITOR_COLOURS, EDITOR_SYSTEM_VARIABLES,
                                              SERIES_LACKED_VARIABLES)
from nxwright.tft.compile_context import CompileContext
from nxwright.tft import component_types, frame
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing.external_picture_probes import external_picture
from tools.tft.probing.number_probes import number_component
from nxwright.tft.statements import (COLOURS, MATCHED, SYSTEM_VARIABLES, CodePlace, series_commands,
                              encode_code, encode_line)
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.waveform_probes import waveform_component
from tests.tft.line_context import line_context
from tests.tft.p_components import SEVERAL_TYPES, PTypePieces, p_probe
from tests.tft.t_components import CodePieces, LoadSectionPieces
from tests.tft.unit_inputs import laid_out_pieces, page, project_of


def on_p(*pages):
    """A Project of facts on P (unit_inputs.project_of) of `pages`, each a
    page on P."""
    return project_of(*pages, series="P")


class WithoutP:
    """What describes a type the frame does not write on P: the members of
    `module`, a type's module or variant, but its P_MEMORY_SIZE. Every type
    nxwright writes has P's, so a test of a type without them takes this in
    their place."""

    def __init__(self, module):
        self._module = module

    def __getattr__(self, name: str):
        if name == "P_MEMORY_SIZE":
            raise AttributeError(name)
        return getattr(self._module, name)


def without_p(type_name: str):
    """Returns a patch that makes each component of the type `type_name`
    one the frame does not write on P (WithoutP)."""
    describe = component_types.object_module

    def stand_in(page_object):
        module = describe(page_object)
        name = component_types.type_name(page_object)
        return WithoutP(module) if name == type_name and module is not None else module
    return mock.patch.object(component_types, "object_module", stand_in)


class BlankProjectTest(unittest.TestCase):
    """The blank project's user code, as the Nextion Editor wrote it."""

    @classmethod
    def setUpClass(cls):
        cls.code = frame.user_code(on_p(page(series="P")))
        cls.parts = cls.code.block_parts()

    def blocks(self, part: str) -> list:
        return [block.hex(" ") for block, its in zip(self.code.blocks, self.parts) if its == part]

    def test_its_first_block(self):
        # Four regions: the 0 word, the int area, the page list, and the
        # table of the attribute names' CRCs, the page's 25.
        self.assertEqual(self.blocks("first block"), [
            "04 00 00 00 24 00 00 00 04 00 00 00 28 00 00 00 10 00 00 00 38 00 00 00 06 00 00 00"
            " 3e 00 00 00 64 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"
            " 26 79 96 ac 00 00 24 2d b8 01 93 30 79 05 86 02 5f 16 48 56 dd 18 ff 4b 1c 1c 44 59"
            " 4c 31 97 43 4f 38 99 90 f7 39 54 f6 a9 4d 71 a0 6a 5c 4d 4e 34 66 68 2f 01 79 df 32"
            " c0 7d 49 ba 76 80 d3 8d ec a4 44 13 86 a6 5b 81 d2 a6 97 41 1a ac 1a 41 61 ac e9 41"
            " 1a b0 5e 5c db b4 55 9f a0 d0 68 69 ee db d8 94 90 f2 1b 70 4b ff"])

    def test_its_program_s(self):
        # baud=9600, dim=100, recmod=0, printh, and page 0, by P's numbers,
        # then the Nextion Editor's own page 0 and the 0 word.
        self.assertEqual(self.blocks("program.s"), [
            "04 04 30 00 00 3d 03 80 25 00 00", "04 04 10 00 00 3d 31 30 30",
            "04 08 0f 00 00 3d 30",
            "09 0f 08 30 30 20 30 30 20 30 30 20 66 66 20 66 66 20 66 66 20 38 38 20 66 66 20 66"
            " 66 20 66 66", "09 0c 04 30", "09 0c 04 30", ""])

    def test_its_page_s_blocks(self):
        # No fill: the page's run is the 0 word alone. Then its events, its
        # objects' table, its memory from its run on, doevents, and the 0
        # word.
        self.assertEqual(self.blocks("page 0"), [
            "", "64 6f 77 6e", "", "75 70", "", "75 6e 6c 6f 61 64", "", "26 79 96 ac 00 00",
            "14 00 00 00 79 00 00 37 ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff"
            " ff ff ff ff 14 00 00 00 00 00 7f 00 00 00 00 00 00 00 00 00 20 03 e0 01 1f 03 df 01"
            " 00 00 00 00 ff ff ff ff 01 00 ff ff 00 00 00 00 00 00 00 00",
            "09 30 08", ""])

    def test_its_page_s_data(self):
        # Every value is a place in the page's memory, its code with 0x20.
        data = self.code.page_data()[0]
        used = [(number,) + struct.unpack_from("<IiiiII", data, 24 * number)
                for number in range(len(data) // 24)
                if any(struct.unpack_from("<IiiiII", data, 24 * number))]
        self.assertEqual(len(data), 33 * 24)
        self.assertEqual(used, [
            (0, 20, 20, 255, 0, 0, 289), (1, 20, 21, 255, 0, 0, 289), (3, 20, 22, 1, 0, 0, 289),
            (9, 20, 60, 6000, -6000, 0, 555), (10, 20, 62, 6000, -6000, 0, 556),
            (11, 20, 64, 2000, -2000, 0, 557), (12, 20, 66, 2000, -2000, 0, 558),
            (13, 20, 68, 32767, -32768, 0, 552), (14, 20, 70, 32767, -32768, 0, 552),
            (15, 20, 72, 10, 0, 0, 305), (19, 20, 76, 255, 0, 0, 305),
            (20, 20, 77, 255, 0, 0, 305), (21, 20, 78, 255, 0, 0, 305),
            (22, 20, 79, 255, 0, 0, 305), (23, 20, 80, 2, 0, 0, 289),
            (24, 20, 82, 65535, 0, 0, 562)])

    def test_its_page_index(self):
        # Its memory, 68: the run and the page's 64 bytes.
        self.assertEqual(self.code.page_index.hex(" "),
                         "00 00 01 00 2d 01 00 00 b6 01 00 00 44 00 00 00")

    def test_its_record(self):
        # T's head, then a slot for each name of the first block's table.
        self.assertEqual(self.code.records[:106].hex(" "),
                         "79 00 00 37 ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff"
                         " ff ff ff ff 14 00 00 00 00 00 7f 00 00 00 00 00 00 00 00 00 20 03 e0 01"
                         " 1f 03 df 01 05 01 00 00 09 00 0a 00 ff ff ff ff ff ff 16 00 15 00 0b 00"
                         " 0c 00 17 00 13 00 ff ff ff ff 03 00 14 00 ff ff ff ff ff ff 0f 00 0d 00"
                         " 0e 00 ff ff 01 00 18 00 00 00")

    def test_its_size(self):
        self.assertEqual(len(self.code.to_bytes()), 1352)


class TextTest(unittest.TestCase):
    """Two texts on P, t0 with code in its up event, as the Nextion Editor
    wrote them: the project of compile_probes' compile-T-texts, on P."""

    @classmethod
    def setUpClass(cls):
        cls.pieces = laid_out_pieces(on_p(page(
            text_component(), text_component("t1", y=60), series="P",
            code='on t0.up:\n  t1.txt="Yo"\n')), encode_code)

    def test_the_run_of_bases(self):
        # After the memory block's size: the page's base, then t0's and
        # t1's, past the page's 64 bytes and t0's 84.
        self.assertEqual(self.pieces["page0-memory-run"][4:].hex(" "),
                         "1c 00 00 00 5c 00 00 00 b0 00 00 00")

    def test_a_text_s_memory(self):
        # The head, its up code's place at +16; then sta 1, bco 65535, xcen
        # and ycen 1, txt_maxl 10, and its txt's place, 264, at +72.
        # The frame's whole memory of t0, its head and its values, as the
        # bytes typed before the plan hold both.
        memory = self.pieces["page0-1-head"] + self.pieces["page0-1-memory"]
        self.assertEqual(memory.hex(" "),
                         "74 01 00 37 ff ff ff ff ff ff ff ff ff ff ff ff 73 01 00 00 ff ff ff ff"
                         " ff ff ff ff 5c 00 00 00 00 00 7f 00 00 00 00 00 0a 00 0a 00 64 00 1e 00"
                         " 6d 00 27 00 00 00 00 00 01 00 00 00 00 00 ff ff 00 00 01 01 00 00 0a 00"
                         " 08 01 00 00 00 00 00 00 00 00 00 00")

    def test_a_text_s_record(self):
        # The head, then a slot for each of the table's 37 names.
        self.assertEqual(self.pieces["page0-1-record"].hex(" "),
                         "74 01 00 37 ff ff ff ff ff ff ff ff ff ff ff ff 73 01 00 00 ff ff ff ff"
                         " ff ff ff ff 5c 00 00 00 00 00 7f 00 00 00 00 00 0a 00 0a 00 64 00 1e 00"
                         " 6d 00 27 00 5d 01 00 00 2a 00 2b 00 39 00 3c 00 25 00 ff ff ff ff ff ff"
                         " ff ff 2c 00 2d 00 3b 00 35 00 34 00 ff ff ff ff 3f 00 ff ff ff ff 24 00"
                         " 37 00 41 00 ff ff ff ff 27 00 40 00 ff ff 30 00 2e 00 3d 00 2f 00 3e 00"
                         " 3a 00 ff ff 22 00 38 00 21 00")


class NumberTest(unittest.TestCase):
    """A number on P, n0, a val of 123 and code in its up event, as the
    Nextion Editor wrote it beside a text: the project of compile_probes'
    compile-T-numbers-and-a-text, on P. Its second page moves where n0's
    code lies, which n0's head gives."""

    def test_its_memory(self):
        # The head, its up code's place at +16; then sta 1, bco 65535, xcen
        # and ycen 1, its val, 123, at +68, and isbr 1 at +76: 80 bytes.
        pieces = laid_out_pieces(on_p(
            page(number_component(val=123), text_component(y=60), series="P",
                 code='on n0.up:\n  t0.txt="Yo"\n'),
            page(number_component(val=-5), series="P", name="page1")), encode_code)
        # The frame's whole memory of n0, its head and its values, as the
        # bytes typed before the plan hold both.
        self.assertEqual((pieces["page0-1-head"] + pieces["page0-1-memory"]).hex(" "),
                         "36 01 00 37 ff ff ff ff ff ff ff ff ff ff ff ff 85 01 00 00 ff ff ff ff"
                         " ff ff ff ff 5c 00 00 00 00 00 7f 00 00 00 00 00 0a 00 0a 00 64 00 1e 00"
                         " 6d 00 27 00 00 00 00 00 01 00 00 00 00 00 ff ff 00 00 01 01 7b 00 00 00"
                         " 00 00 00 00 01 00 00 00")


class TextRoomTest(unittest.TestCase):
    """On P, a text's room keeps what the page before left in it, past its
    txt and the zero after it, as the Nextion Editor wrote them."""

    def test_a_room_after_a_longer_text(self):
        texts = laid_out_pieces(on_p(page(text_component(txt="ABCDEFGHIJ"), series="P"),
                                     page(text_component(), series="P", name="page1")))
        # Page 1's t0, of txt "Hi", in the room of page 0's t0.
        room = texts["page1-texts"]
        room = room[room.index(b"Hi\x00"):][:12]
        self.assertEqual(room, bytes.fromhex("48 69 00 44 45 46 47 48 49 4a 00 00"))


class SeveralTypesTest(PTypePieces, LoadSectionPieces, unittest.TestCase):
    """Each component of each of P's probes of several types (SEVERAL_TYPES),
    at its type's functions on P, against the probe's pieces: its values
    after its record's head and its entries (tests/tft/p_components.py), and
    its blocks in its page's load section, for a type that writes them. Its
    head and its record are the frame's (tests/tft/test_frame.py)."""

    PROBES = [p_probe(name) for name in SEVERAL_TYPES]
    COUNT = 181


class CommandsPHasTest(CodePieces, unittest.TestCase):
    """The probes of the commands of files, sound, motion, and layers that P
    has and T and K have not, each command and its operands, at the
    statement encoder (tests/tft/t_components.py). The first is their family's
    sample of whole files on P. The third gives setlayer's and move's
    components of other forms than a name, and the fourth the file commands'
    operands of any kind."""

    PROBES = [p_probe("p-commands-p-has-each"), p_probe("p-commands-p-has-operands"),
              p_probe("p-commands-p-has-components-of-other-forms"),
              p_probe("p-commands-p-has-files-of-any-kind")]
    CODE_COUNT = 4


class MatchedTest(unittest.TestCase):
    """What the check matches on P."""

    def test_its_system_variables_and_colours(self):
        # Every one the Nextion Editor knows on P, each of its own number.
        self.assertEqual(set(SYSTEM_VARIABLES["P"]),
                         EDITOR_SYSTEM_VARIABLES - SERIES_LACKED_VARIABLES["P"])
        self.assertEqual(set(COLOURS["P"]), set(EDITOR_COLOURS))
        numbers = list(SYSTEM_VARIABLES["P"].values()) + list(COLOURS["P"].values())
        self.assertEqual(len(set(numbers)), len(numbers))

    def test_the_border_and_background_of_its_own_types(self):
        # On P and E, a sta of 0 to 3 and any picture on the combo box, the
        # data record, the file browser, the select, and the sliding text
        # (component_types.p_border_and_background_rules). The three without
        # border rules of their own take a style up to their highest, and
        # the border's width up to 255.
        rules = matched_rules()
        highest_styles = {"combo-box": 3, "sliding-text": 3, "select": 1, "data-record": None,
                          "file-browser": None}
        for name, highest in highest_styles.items():
            values = [("sta", 3, True), ("sta", 4, False), ("pic", 65535, True),
                      ("picc", 0, True)]
            if highest is not None:
                values += [("style", highest, True), ("style", highest + 1, False),
                           ("borderw", 255, True), ("borderw", 256, False)]
            for series in ("P", "E"):
                for attribute, value, taken in values:
                    need = Need("attribute", "%s.%s" % (name, attribute),
                                value.to_bytes(4, "little"), series=series)
                    with self.subTest(series, attribute="%s.%s" % (name, attribute), value=value):
                        self.assertEqual(unmatched([need], rules), [] if taken else [need])

    def test_a_sta_past_3_on_its_own_types(self):
        # A sta past 3, which those five types' entries do not take, is
        # refused by its rule. nxwright's build refuses it first, so the
        # rule is checked on the value alone.
        rules = matched_rules()
        for name in ("combo-box", "data-record", "file-browser", "select", "sliding-text"):
            with self.subTest(name):
                need = Need("attribute", name + ".sta", b"\x04", series="P")
                self.assertEqual(unmatched([need], rules), [need])

    def test_its_commands(self):
        # Each family P's probes showed gives P every command it gives T,
        # each of its own number in its table.
        from nxwright.tft.instructions import (crc_commands, device_and_buffer_commands,
                                        drawing_commands, pinyin_commands, screen_commands,
                                        serial_commands, text_commands)
        for module in (screen_commands, drawing_commands, text_commands, serial_commands,
                       crc_commands, device_and_buffer_commands, pinyin_commands):
            with self.subTest(module.__name__):
                self.assertEqual(set(module.COMMANDS["P"]), set(module.COMMANDS["T"]))
                self.assertEqual({command.table for command in module.COMMANDS["P"].values()},
                                 {command.table for command in module.COMMANDS["T"].values()})
        # The undocumented commands but fstr, which P lacks, and K's commands
        # of the EEPROM and the GPIO pins, which T has not.
        from nxwright.tft.instructions import eeprom_and_gpio_commands, undocumented_commands
        self.assertEqual(set(undocumented_commands.COMMANDS["P"]),
                         set(undocumented_commands.COMMANDS["T"]) - {"fstr"})
        self.assertEqual(set(eeprom_and_gpio_commands.COMMANDS["P"]),
                         set(eeprom_and_gpio_commands.COMMANDS["K"]))
        heads = [(command.number, command.table) for command in series_commands("P").values()]
        self.assertEqual(len(set(heads)), len(heads))

    def test_the_commands_p_has(self):
        # The commands of files, sound, motion, and layers that T and K have
        # not: taken on P and E alone, with components the page has.
        from nxwright.tft.instructions import file_commands, sound_motion_and_layer_commands
        self.assertEqual(len(file_commands.COMMANDS["P"])
                         + len(sound_motion_and_layer_commands.COMMANDS["P"]), 14)
        context = line_context(text_component(), number_component("n0", y=60))
        # A path, and an answer's destination, of any kind, as the Nextion
        # Editor compiled them.
        for line in ('beep 100', 'delfile "sd0/a.txt"', "findfile t0.txt,n0.val",
                     "setlayer t0,n0", "move t0,0,0,10,10,0,10", "delfile b[1].txt",
                     "newdir p[0].b[1].txt", "findfile b[1].txt,n0.val",
                     'findfile "sd0/a.txt",5', 'finddir "sd0/a/",5',
                     'findfile "sd0/a.txt",b[1].val', 'findfile "sd0/a.txt",b[1].txt',
                     "delfile b[1].val", 'findfile "sd0/a.txt",0x05', 'findfile "sd0/a.txt",-5',
                     "delfile 5", "delfile n0.val", 'findfile "sd0/a.txt",t0.txt',
                     'findfile "sd0/a.txt","b"', "move sys0,0,0,10,10,0,100",
                     "setlayer sys0,sys1"):
            with self.subTest(line):
                for series in ("P", "E"):
                    self.assertEqual(unmatched([Need("code", "event", line, context=context,
                                                     series=series)], matched_rules()), [])
                need = Need("code", "event", line, context=context, series="T")
                self.assertEqual(unmatched([need], matched_rules()), [need])
        # Nor a component the page has not, nor another number of arguments;
        # nor an expression where one operand goes ("Invalid Variables"), nor
        # a text or a txt where a number goes ("Invalid variable operation"),
        # which the Nextion Editor refused.
        for line in ("setlayer t0,t9", "move t9,0,0,10,10,0,10", 'newdir "a",1',
                     "delfile sys0+1", 'findfile "sd0/a.txt",sys0+1',
                     'newfile "sd0/a.txt",t0.txt', 'rdfile "sd0/a.txt","0",10,0'):
            with self.subTest(line):
                need = Need("code", "event", line, context=context, series="P")
                self.assertEqual(unmatched([need], matched_rules()), [need])

    def test_variables_as_move_s_and_setlayer_s_components(self):
        # Written as their operands, as the Nextion Editor wrote them in
        # page0's Touch Release event.
        project = project_of(page(strict=True), series="P", strict=True,
                             declarations=("int a=1",))
        for line, block in (("move sys0,0,0,10,10,0,100",
                              "09 0e 04 05 00 00 00 00 2c 30 2c 30 2c 31 30 2c 31 30 2c 30 2c "
                              "31 30 30"),
                             ("setlayer sys0,a", "09 2f 08 05 00 00 00 00 2c 05 0c 00 00 00")):
            with self.subTest(line):
                self.assertEqual(encode_line(line, CodePlace(0, "page0", "up"),
                                             CompileContext(project)),
                                 bytes.fromhex(block))

    def test_the_undocumented_commands_p_has(self):
        # Taken on P and E alone, in the forms the probes showed: beepset,
        # cfguart, cuts, meup, and xnum of numbers, gets of two of any kind,
        # and sets of up to three of any kind, then of numbers. Not an
        # operator where one operand goes, nor a txt where a number goes,
        # which the Nextion Editor refused, nor i's wrong forms, as on T.
        context = line_context(text_component(), number_component("n0", y=60))
        rules = matched_rules()
        for line in ("cuts n0.val,sys0+1,1,2,3,4,5", 'gets "a",t0.txt',
                     "sets t0.txt,n0.val,sys0,1", "beepset 100,sys0+1"):
            with self.subTest(line):
                for series in ("P", "E"):
                    self.assertEqual(unmatched([Need("code", "event", line, context=context,
                                                     series=series)], rules), [])
                need = Need("code", "event", line, context=context, series="T")
                self.assertEqual(unmatched([need], rules), [need])
        for line in ("gets n0.val,sys0+1", "i sys0+1,0,0,0", "sets t0.txt,t0.txt,t0.txt,t0.txt",
                     "cuts t0.txt,0,0,0,0,0,0", "i 0,0,0"):
            with self.subTest(line):
                need = Need("code", "event", line, context=context, series="P")
                self.assertEqual(unmatched([need], rules), [need])

    def test_paths_set_from_txts(self):
        # A path, a text other than a txt, set from a txt and from texts
        # joined with one, added to, and cut, as p-paths-set-from-txts
        # showed; but not set from a number.
        project = project_of(page(text_component(), external_picture(y=60), series="P",
                                  code="on page0.up:\n  sys0=1\n"), series="P", fonts=0)
        context = next(need.context for need in project_needs(project) if need.kind == "code")
        for line in ("xp0.path=t0.txt", 'xp0.path="a"+t0.txt', "xp0.path+=t0.txt",
                     "xp0.path-=1"):
            with self.subTest(line):
                need = Need("code", "event", line, context=context, series="P")
                self.assertEqual(unmatched([need], matched_rules()), [])
        for line in ("xp0.path=1", "xp0.path=sys0"):
            with self.subTest(line):
                need = Need("code", "event", line, context=context, series="P")
                self.assertEqual(unmatched([need], matched_rules()), [need])

    def test_the_code_its_probes_showed(self):
        # A new project's program.s, the assignments of int variables and
        # dim in events of the probe of three pages, the `+=` and `++` of the
        # button's and the for statement's probes, a system variable and a
        # colour of the probes of P's numbers, a hexadecimal number and `*=`
        # of the probes of T's forms, and `page` by a variable and of any
        # value of the page probes.
        for line in ("baud=9600", "dim=100", "recmod=0", "printh 00 ff", "page 0",
                     "page 2", "count=count+1", "limit=limit*2", "dim=50", "// note",
                     "sys0+=1", "sys0++", "dp=1", "sys0=RED", "sys0=0x01", "sys0*=2",
                     "page sys0", "page 1000", "page 007"):
            with self.subTest(line):
                self.assertEqual(unmatched([Need("code", "event", line, series="P")],
                                           MATCHED), [])

    def test_the_code_it_leaves_out(self):
        # lowpower, the one system variable the Nextion Editor knows that P
        # has not, set and as page's value.
        for line in ("lowpower=1", "page lowpower"):
            with self.subTest(line):
                need = Need("code", "event", line, series="P")
                self.assertEqual(unmatched([need], MATCHED), [need])

    def test_the_code_t_takes_that_p_s_probes_did_not_show(self):
        # fstr, which P lacks: the Nextion Editor refuses it there, and so
        # does nxwright's build, so the line is checked beside a text alone.
        page = line_context(text_component())
        needs = {series: Need("code", "event", "fstr t0.txt,RED,0", context=page, series=series)
                 for series in ("T", "P")}
        self.assertEqual(unmatched([needs["T"]], matched_rules()), [])
        self.assertEqual(unmatched([needs["P"]], matched_rules()), [needs["P"]])

    def test_a_global_component(self):
        # The page and a component of each type P has may be global on P,
        # as P's probes of each showed, but a file stream, which the Nextion
        # Editor refuses global there.
        def vscope(subject: str) -> Need:
            return Need("attribute", subject + ".vscope", b"\x01", series="P")
        covered = [vscope(name) for name in ("page", "text", "number", "button", "checkbox",
                                             "waveform", "data-record")]
        self.assertEqual(unmatched(covered, frame.MATCHED), [])
        self.assertEqual(unmatched([vscope("file-stream")], frame.MATCHED),
                         [vscope("file-stream")])

    def test_a_page_of_another_width(self):
        # Written at the screen's width, as on T (page_place_probes.py),
        # whatever its width, even past 2000, its entry's highest.
        taken = [Need("attribute", "page.w", (width).to_bytes(2, "little"), series="P")
                 for width in (320, 2001)]
        self.assertEqual(unmatched(taken, frame.MATCHED), [])

    def test_a_type_without_p_is_refused(self):
        # The frame refuses a type it does not write on P, here a stand-in
        # in the waveform's place (without_p).
        project = on_p(page(waveform_component(), series="P"))
        with without_p("waveform"), self.assertRaisesRegex(
                frame.FrameError, "does not write a waveform on the P series"):
            frame.user_code(project)


if __name__ == "__main__":
    unittest.main()
