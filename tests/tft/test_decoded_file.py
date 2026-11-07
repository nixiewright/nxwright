"""The decoded file (tft/decompiling/decoded_file.py): a TFT file's user
code read into its pages, objects, int variables, macros, and runs of code,
checked against the pieces of probes' fixtures and the probes' own inputs;
its helpers, where a run of code's blocks lie and a page's memory read by
an object's base; and the error a decoder raises
(tft/decompiling/__init__.py)."""
from dataclasses import replace
import importlib
import pkgutil
import struct
import unittest

from nxwright.source.keyboards import KEYBOARD_PAGES

from nxwright.tft import component_types, frame, label_numbers
from tools.tft import probing
from nxwright.tft.commands.compile import compile_project
from nxwright.tft.component_types import (object_module, p_page_named_entries, p_table,
                                   value_operand)
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling import decoded_file
from nxwright.tft.decompiling.objects import named_entries
from nxwright.tft.decompiling.decoded_file import (CodeRun, DecodedPage, Resource, decoded_user_code,
                                            read_decoded)
from nxwright.tft.firmware import Firmware
from nxwright.tft.packaging import FONT_HEADER, PICTURE_HEADER, PICTURE_PLACE_FIELD, firmware_names
from tools.tft.probing import (button_probes, f_probes, frame_probes, k_probes, key_probes,
                           macro_probes, p_probes, page_command_probes, variable_probes)
from tools.tft.probing import editor_1_60_1_p_probes, editor_1_60_1_probes, older_editor_probes
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.dual_state_button_probes import dual_state_button_component
from tools.tft.probing.probe_runner import FIXTURES
from tools.tft.probing.scrolling_text_probes import scrolling_text_component
from tools.tft.probing.text_probes import text_component
from nxwright.tft.tft_file import byte_form_crc, encode_blocks, read_tft, split_blocks
from tests.tft.made_tft import made_tft, made_user_code
from tests.tft.test_decompiling_resources import p_project_with_media
from tests.tft.unit_inputs import (page, piece, piece_names, place, probe_facts, project_of,
                               user_code_of, whole_file_of, with_font_blocks)


def _page(memory_start: int, memory: bytes) -> DecodedPage:
    """Returns a page of no object whose memory is `memory`, from the place
    `memory_start`."""
    return DecodedPage(0, [], memory_start, memory, CodeRun(0, []))


def _probe(module, name: str):
    """Returns the probe `name` of the probe module `module`."""
    return next(probe for probe in module.PROBES if probe.name == name)


def _decoded_on_t(probe):
    """Returns the decoded file of `probe`'s user code, on the T series'
    base model, as the probes' base folder gives it."""
    return decoded_user_code(user_code_of(probe), "T", "NX4832T035", 0, "iso-8859-1")


def _blocks(probe, name: str) -> list:
    """Returns the blocks of `probe`'s piece `name`, without the 0 word that
    ends them."""
    blocks = split_blocks(piece(probe, name))
    assert blocks[-1] == b"", name
    return blocks[:-1]


def _blocks_by_place(probe) -> dict:
    """Returns {where a block's size word lies: the block} of `probe`'s user
    code."""
    code = user_code_of(probe)
    return dict(zip(code.block_places(), code.blocks))


class CodeRunTest(unittest.TestCase):

    def test_block_places(self):
        # Each block follows the one before it and its 4-byte size word.
        self.assertEqual(CodeRun(0x40, [b"ab", b"", b"cde"]).block_places(),
                         [0x40, 0x46, 0x4A])
        self.assertEqual(CodeRun(0x40, []).block_places(), [])


class MemoryAtTest(unittest.TestCase):

    def test_by_base(self):
        page = _page(20, bytes(range(8)))
        self.assertEqual(page.memory_at(22, 3), bytes([2, 3, 4]))

    def test_outside_the_pages_memory(self):
        # Before its start, or running past its end, as a base of another
        # page's or of the int area's would.
        page = _page(20, bytes(8))
        for base, size in ((19, 1), (26, 4)):
            with self.subTest(base=base, size=size):
                self.assertRaises(IndexError, page.memory_at, base, size)


class DecodeErrorTest(unittest.TestCase):

    def test_message(self):
        error = DecodeError("an unknown command", 0x40, b"\x09\x99")
        self.assertEqual(str(error), "an unknown command, at 0x40: 09 99")
        self.assertEqual((error.place, error.data), (0x40, b"\x09\x99"))

    def test_a_refusal_of_the_whole_file(self):
        # A refusal that is not about one place in the file gives none, and
        # its message is its text alone.
        error = DecodeError("the user code of the X series is not decoded")
        self.assertEqual(str(error), "the user code of the X series is not decoded")
        self.assertEqual((error.place, error.data), (None, b""))


class PagesTest(unittest.TestCase):

    def test_three_pages(self):
        # Each by its ID, its name the Nextion Editor's for a new page, and
        # its own object alone, without code.
        decoded = _decoded_on_t(_probe(frame_probes, "frame-three-pages"))
        self.assertEqual([page.page_id for page in decoded.pages], [0, 1, 2])
        for page in decoded.pages:
            with self.subTest(page.page_id):
                [own] = page.objects
                self.assertEqual((own.object_id, own.type_name, own.name.text, own.name.matched),
                                 (0, "page", "page%d" % page.page_id, True))
                self.assertEqual({name: run.blocks for name, run in own.events.items()},
                                 {"down": [], "up": [], "unload": []})

    def test_events_and_load_section(self):
        # The page's down, up, and unload events, then its load section: its
        # load code, the doevents the Nextion Editor adds, and its loadend
        # code. The probe's fixtures keep a stand-in block for each line.
        probe = _probe(frame_probes, "frame-page-events")
        [page] = _decoded_on_t(probe).pages
        self.assertEqual({name: run.blocks for name, run in page.objects[0].events.items()},
                         {"down": [b"stand-in sys0=3", b"stand-in sys1=6"],
                          "up": [b"stand-in sys0=4"], "unload": [b"stand-in sys0=5"]})
        self.assertEqual(page.load_section.blocks,
                         [b"stand-in sys0=1", frame.DOEVENTS["T"], b"stand-in sys0=2"])
        # Each run's place is where its first block lies.
        blocks = _blocks_by_place(probe)
        for run in list(page.objects[0].events.values()) + [page.load_section]:
            for at, block in zip(run.block_places(), run.blocks):
                self.assertEqual(blocks[at], block)

    def test_program_s(self):
        # Without the page 0 command and the 0 word that the Nextion Editor
        # appends to it.
        probe = _probe(frame_probes, "frame-three-pages")
        blocks = _decoded_on_t(probe).program.blocks
        self.assertTrue(blocks)
        self.assertEqual(blocks + [frame.APPENDED_PAGE_0["T"], b""],
                         split_blocks(piece(probe, "program-s")))


class IntVariablesTest(unittest.TestCase):

    def test_names_and_values(self):
        # sys0 to sys2 by their names; a and b, whose names no guess gives,
        # by readable names; each with its value, in the order declared.
        ints = _decoded_on_t(_probe(frame_probes, "frame-two-more-ints")).ints
        self.assertEqual([(each.name.text, each.name.matched, each.value) for each in ints],
                         [("sys0", True, 0), ("sys1", True, 0), ("sys2", True, 0),
                          ("int3", False, 5), ("int4", False, 6)])

    def test_bounds(self):
        ints = _decoded_on_t(_probe(frame_probes, "frame-int-bounds")).ints
        self.assertEqual([each.value for each in ints][3:], [-2147483648, 2147483647])


class ComponentsTest(unittest.TestCase):

    def test_two_buttons(self):
        # Each button's place, entries, record, memory, drawing, background
        # fill, and events, as the probe's pieces give them.
        probe = _probe(button_probes, "button-two")
        [page] = _decoded_on_t(probe).pages
        self.assertEqual([(each.type_name, each.name.text, each.name.matched)
                          for each in page.objects],
                         [("page", "page0", True), ("button", "b0", True),
                          ("button", "b1", True)])
        for each in page.objects[1:]:
            name = "page0-%d" % each.object_id
            with self.subTest(name):
                where = place(probe, name)
                self.assertEqual((each.first_entry, each.base, each.is_global),
                                 (where.first_entry, where.base, False))
                self.assertEqual(b"".join(each.entries), piece(probe, name + "-entries"))
                self.assertEqual(each.record, piece(probe, name + "-record"))
                memory = piece(probe, name + "-memory")
                self.assertEqual(page.memory_at(each.base, len(memory)), memory)
                self.assertEqual(each.drawing, _blocks(probe, name + "-drawing"))
                self.assertEqual(each.background_fill, _blocks(probe, name + "-background-fill"))
                self.assertEqual(list(each.events), ["down", "up"])

    def test_an_object_not_drawn(self):
        # A variable gives one empty block, its drawing, and no background
        # fill nor event.
        [page] = _decoded_on_t(_probe(variable_probes, "variable-two")).pages
        variable = page.objects[1]
        self.assertEqual((variable.type_name, variable.name.text, variable.drawing,
                          variable.background_fill, variable.events),
                         ("variable", "va0", [], [], {}))


class MacrosTest(unittest.TestCase):

    def test_called(self):
        # In the order their blocks lie, which is the macro tab's, each with
        # a readable name, as the Nextion Editor names no new macro. A return
        # inside a macro does not end its run.
        probe = _probe(macro_probes, "macros-called")
        macros = _decoded_on_t(probe).macros
        self.assertEqual([(macro.name.text, macro.name.matched, len(macro.code.blocks))
                          for macro in macros],
                         [("macro0", False, 3), ("macro1", False, 3), ("macro2", False, 0),
                          ("macro3", False, 1)])
        # Each run starts after its "S " block, which gives its label's
        # number.
        blocks = _blocks_by_place(probe)
        for macro in macros:
            start = label_numbers.S_BLOCK_START + value_operand(macro.label_number)
            self.assertEqual(blocks[macro.code.place - 4 - len(start)], start)


class MediaResourcesTest(unittest.TestCase):

    def test_media_on_p(self):
        # A whole file of P, compiled in memory on zeros for the firmware,
        # gives its fonts, then its animations, videos, and sounds, each by
        # its ID and the size of its project block.
        project, media = p_project_with_media()
        firmware = Firmware((1, 68, 2), {name: bytes(16) for name in firmware_names("P")})
        decoded = read_decoded(read_tft(compile_project(project, firmware), "the file"))
        fonts = [project.blocks[name] for kind, name in project.resources if kind == "font"]
        self.assertEqual(
            [(each.kind, each.resource_id, each.size) for each in decoded.resources],
            [("font", number, len(block)) for number, block in enumerate(fonts)]
            + [(kind, number, len(block)) for kind in ("animation", "video", "sound")
               for number, block in enumerate(media[kind])])


class DeviceSettingsTest(unittest.TestCase):

    def test_the_settings_header_1_keeps(self):
        # A whole file of P, compiled in memory on zeros for the firmware,
        # gives its one-time update and its memory file's storage size, which
        # header 1 keeps. One of T keeps no storage size.
        firmware = Firmware((1, 68, 2), {name: bytes(16) for name in firmware_names("P")})
        project, _ = p_project_with_media()
        changed = replace(project, settings=replace(project.settings, one_time_update=True,
                                                    memory_file_storage_size=4096))
        on_t = with_font_blocks(project_of(page(), series="T"), "T")
        on_t = replace(on_t, settings=replace(on_t.settings, memory_file_storage_size=4096))
        t_firmware = Firmware((1, 68, 2), {name: bytes(16) for name in firmware_names("T")})
        for made, kept, expected in ((project, firmware, (False, 0)),
                                     (changed, firmware, (True, 4096)),
                                     (on_t, t_firmware, (False, 0))):
            with self.subTest(expected=expected, series=made.settings.model.series):
                decoded = read_decoded(read_tft(compile_project(made, kept), "the file"))
                self.assertEqual((decoded.one_time_update, decoded.memory_file_storage_size),
                                 expected)


class AttributeNamesTest(unittest.TestCase):

    def test_a_blank_page_on_p(self):
        # P's first block names the attributes a blank page has, by their
        # checksums, smallest first: x's, then y's. T's names none.
        probe = _probe(p_probes, "p-page-of-swipes")
        decoded = decoded_user_code(user_code_of(probe), "P", "NX8048P050", 0, "iso-8859-1")
        self.assertEqual(sorted(decoded.attribute_names), [
            "aph", "bco", "down", "drag", "effect", "endx", "endy", "groupid0", "groupid1", "h",
            "id", "left", "lockobj", "movex", "movey", "objname", "right", "sendkey", "sta",
            "type", "up", "vscope", "w", "x", "y"])
        self.assertEqual(decoded.attribute_names, sorted(
            decoded.attribute_names, key=lambda name: byte_form_crc(name.encode("ascii"))))
        self.assertEqual(decoded.attribute_names[:2], ["x", "y"])
        self.assertIsNone(_decoded_on_t(_probe(frame_probes, "frame-three-pages")).attribute_names)

    def test_a_name_nxwright_does_not_know(self):
        # A checksum of no attribute nxwright knows is refused, with its
        # place in the user code. The first block's head gives where its
        # fourth region, the table, starts, after the block's size word.
        probe = _probe(p_probes, "p-page-of-swipes")
        code = user_code_of(probe)
        first = bytearray(code.blocks[0])
        place, _ = struct.unpack_from("<II", first, 4 + 8 * 3)
        first[place + 4:place + 8] = struct.pack("<I", byte_form_crc(b"no_such_name"))
        code.blocks[0] = bytes(first)
        with self.assertRaises(DecodeError) as raised:
            decoded_user_code(code, "P", "NX8048P050", 0, "iso-8859-1")
        self.assertEqual(raised.exception.place, code.block_places()[0] + 4 + place + 4)

    def test_a_table_without_type(self):
        # Every object's record gives its first entry in its slot of type,
        # so a table that names no type is refused.
        probe = _probe(p_probes, "p-page-of-swipes")
        code = user_code_of(probe)
        decoded = decoded_user_code(code, "P", "NX8048P050", 0, "iso-8859-1")
        first = bytearray(code.blocks[0])
        place, _ = struct.unpack_from("<II", first, 4 + 8 * 3)
        at = place + 4 * decoded.attribute_names.index("type")
        first[at:at + 4] = struct.pack("<I", byte_form_crc(b"txt"))
        code.blocks[0] = bytes(first)
        self.assertRaises(DecodeError, decoded_user_code, code, "P", "NX8048P050", 0,
                          "iso-8859-1")


# The base model of each series' probes, which sets the size of a page that
# nxwright lays a keyboard out on.
_MODELS = {"T": "NX4832T035", "K": "NX4832T035", "F": "NX4832T035", "P": "NX8048P050"}


def _probes_keeping_their_user_code(series: tuple = ("T", "K", "F")) -> list:
    """Returns every probe of `series`, T, K, and F unless given, whose
    fixtures keep its whole user code, in parts, once each."""
    found = {}
    for module_info in pkgutil.iter_modules(probing.__path__):
        if module_info.name.endswith("_probes"):
            module = importlib.import_module("tools.tft.probing." + module_info.name)
            for probe in getattr(module, "PROBES", []):
                # A probe of an older Nextion Editor keeps that Editor's
                # file, of another layout: its `ours` is None.
                if (probe.fixtures and probe.base in series and probe.ours is not None
                        and (FIXTURES / probe.fixtures / probe.name / "records.bin").exists()):
                    found.setdefault(probe.name, probe)
    return list(found.values())


class EveryProbeTest(unittest.TestCase):

    def test_each_objects_named_entries_on_p(self):
        # On P, each object's record gives its entry of each attribute name
        # of the file's table, as the compile's table of its entries gives
        # them: a page's, and each component's (component_types.p_table).
        compared = 0
        for probe in _probes_keeping_their_user_code(("P",)):
            decoded = decoded_user_code(user_code_of(probe), "P", _MODELS["P"], 0, "iso-8859-1")
            project = probe_facts(probe)
            for page, page_block in zip(decoded.pages, project.pages):
                for each, page_object in zip(page.objects, page_block.objects):
                    with self.subTest(probe.name, page=page.page_id, object=each.object_id):
                        if each.object_id == 0:
                            entries = p_page_named_entries(page_object)
                        else:
                            entries = {name: entry for entry, (name, *_) in p_table(
                                object_module(page_object), page_object, project).items()}
                        self.assertEqual(named_entries(each, decoded),
                                         {name: entry for name, entry in entries.items()
                                          if name in decoded.attribute_names})
                        compared += 1
        self.assertGreater(compared, 1000)
        self.assertRaises(ValueError, named_entries, decoded.pages[0].objects[0],
                          _decoded_on_t(_probe(frame_probes, "frame-three-pages")))

    def test_each_objects_pieces(self):
        # For each probe of T, K, F, and P that keeps its user code, each
        # object's record, entries, memory, drawing, background fill, and
        # events are the pieces the frame laid out for it.
        probes = _probes_keeping_their_user_code(tuple(_MODELS))
        on_p = len([probe for probe in probes if probe.base == "P"])
        self.assertGreater(min(on_p, len(probes) - on_p), 100)
        for probe in probes:
            names = set(piece_names(probe))
            decoded = decoded_user_code(user_code_of(probe), probe.base, _MODELS[probe.base],
                                        0, "iso-8859-1")
            for page in decoded.pages:
                for each in page.objects:
                    name = "page%d-%d" % (page.page_id, each.object_id)
                    with self.subTest(probe.name, object=name):
                        self.assertEqual(each.record, piece(probe, name + "-record"))
                        self.assertEqual(b"".join(each.entries), piece(probe, name + "-entries"))
                        # A global object's memory lies in the int area,
                        # which starts at place 0 of the screen's memory.
                        # On P, it starts with its record's head, a piece of
                        # its own.
                        if name + "-memory" in names:
                            memory = piece(probe, name + "-memory")
                            if name + "-head" in names:
                                memory = piece(probe, name + "-head") + memory
                            self.assertEqual(
                                decoded.int_area[each.base:each.base + len(memory)]
                                if each.is_global else page.memory_at(each.base, len(memory)),
                                memory)
                        if name + "-drawing" in names:
                            # On T, K, and F, a page's piece holds its empty
                            # background fill too.
                            ending = ([b"", b""] if each.object_id == 0 and probe.base != "P"
                                      else [b""])
                            self.assertEqual(encode_blocks(each.drawing + ending),
                                             piece(probe, name + "-drawing"))
                        if name + "-background-fill" in names:
                            self.assertEqual(each.background_fill,
                                             _blocks(probe, name + "-background-fill"))
                        for event, run in each.events.items():
                            if "%s-event-%s" % (name, event) in names:
                                self.assertEqual(
                                    encode_blocks([event.encode("ascii")] + run.blocks + [b""]),
                                    piece(probe, "%s-event-%s" % (name, event)))


class NamesTest(unittest.TestCase):

    def test_a_readable_name_is_not_one_that_matched(self):
        # Page 0 named home, which no guess gives, and page 1 named page0:
        # page 0's readable name would be page0 too, so it takes another.
        probe = _probe(frame_probes, "frame-three-pages")
        code = user_code_of(probe)
        first = bytearray(code.blocks[0])
        page_list = struct.unpack_from("<II", first, 4 + 8 * 2)[0]
        for row in range(3):
            crc, page_id = struct.unpack_from("<IH", first, page_list + 6 * row)
            name = {0: b"home", 1: b"page0"}.get(page_id)
            if name is not None:
                struct.pack_into("<I", first, page_list + 6 * row, frame.page_name_crc(name))
        code.blocks[0] = bytes(first)
        decoded = decoded_user_code(code, "T", "NX4832T035", 0, "iso-8859-1")
        self.assertEqual([(page.objects[0].name.text, page.objects[0].name.matched)
                          for page in decoded.pages],
                         [("page0_", False), ("page0", True), ("page2", True)])

    def test_a_readable_name_fits_in_14_bytes(self):
        # The Nextion Editor keeps a component's name in 14 bytes, so a
        # readable name cuts its type's name to keep its ID whole: a
        # dual-state button's, of 17 characters, and a scrolling text's, of
        # 14.
        project = project_of(page(dual_state_button_component("Named_by_user"),
                                  scrolling_text_component("Named_too", y=100)))
        decoded = decoded_user_code(frame.user_code(project), "T", "NX4832T035", 0,
                                    "iso-8859-1")
        self.assertEqual([(each.name.text, each.name.matched)
                          for each in decoded.pages[0].objects[1:]],
                         [("dual_state_bu1", False), ("scrolling_tex2", False)])

    def test_names_code_keeps_as_text(self):
        # A page or a component named by the user gets its own name back
        # where the file's code keeps that name as text, as `page settings`,
        # `vis status,0`, or `click status,1` do, and its checksum matches.
        probe = _probe(page_command_probes, "page-by-name")
        project = probe_facts(probe)
        decoded = decoded_user_code(frame.user_code(project), "T", "NX4832T035", 0,
                                    "iso-8859-1")
        self.assertEqual([(page.objects[0].name.text, page.objects[0].name.matched)
                          for page in decoded.pages],
                         [("page0", True), ("page1", True), ("settings", True)])
        project = project_of(page(text_component("status"), button_component(y=60),
                                  text_component("not_in_code", y=120),
                                  code="on b0.up:\n  vis status,0\n  click status,1\n"))
        decoded = decoded_user_code(frame.user_code(project), "T", "NX4832T035", 0,
                                    "iso-8859-1")
        self.assertEqual([(each.name.text, each.name.matched)
                          for each in decoded.pages[0].objects[1:]],
                         [("status", True), ("b0", True), ("text3", False)])

    def test_a_keyboard_page(self):
        # A keyboard page nxwright adds, the keypad, keybdB, and each of its
        # components, by the names nxwright's keyboard gives them.
        probe = _probe(key_probes, "key-text-on-the-keypad")
        decoded = _decoded_on_t(probe)
        [keypad] = [page for page in decoded.pages if page.objects[0].name.text == "keybdB"]
        self.assertTrue(keypad.objects[0].name.matched)
        unmatched = [each.name.text for each in keypad.objects if not each.name.matched]
        self.assertEqual(unmatched, [])
        self.assertIn("loadpageid", [each.name.text for each in keypad.objects])

    def test_each_keyboards_names(self):
        # Each keyboard nxwright adds, the Chinese one among them, laid out
        # on the T base model's screen as it stands and turned 90 degrees,
        # gives its components' names, its two variables of the caller
        # among them.
        for kind in KEYBOARD_PAGES:
            for size in ((320, 480), (480, 320)):
                with self.subTest(kind, size=size):
                    names = decoded_file._keyboard_names(kind, *size)
                    self.assertTrue({"loadpageid", "loadcmpid"} <= set(names))
                    self.assertEqual(len(names), len(set(names)))


class DamagedUserCodeTest(unittest.TestCase):

    def test_refused(self):
        # A first block cut short, and records cut short, are refused, not
        # read past their end.
        probe = _probe(frame_probes, "frame-three-pages")
        for part in ("first block", "records"):
            with self.subTest(part):
                code = user_code_of(probe)
                if part == "first block":
                    code.blocks[0] = code.blocks[0][:6]
                else:
                    code.records = code.records[:100]
                self.assertRaises(DecodeError, decoded_user_code, code, "T", "NX4832T035", 0,
                                  "iso-8859-1")


class ResourcesTest(unittest.TestCase):

    def test_sizes_of_two_pictures(self):
        # Their headers first, each giving where its rest lies in the part,
        # then their rests: each picture's size is its header's and its
        # rest's.
        header_size = PICTURE_HEADER
        rests = [b"a" * 10, b"b" * 6]
        headers = b""
        for number, rest in enumerate(rests):
            header = bytearray(header_size)
            struct.pack_into("<I", header, PICTURE_PLACE_FIELD,
                             2 * header_size + sum(map(len, rests[:number])))
            headers += bytes(header)
        tft = read_tft(made_tft("T", user_code_of(_probe(frame_probes, "frame-three-pages")),
                                pictures=headers + b"".join(rests)), "made.tft", check=False)
        self.assertEqual(
            decoded_file._resources(tft, "picture", 2, 7, PICTURE_HEADER, PICTURE_PLACE_FIELD),
            [Resource("picture", 0, header_size + 10), Resource("picture", 1, header_size + 6)])


class WholeFileTest(unittest.TestCase):

    def test_k_and_f(self):
        # The settings from the headers, and a blank project's page, int
        # variables, and font, on K and F, whose user code is laid out as T's.
        for module, series, model in ((k_probes, "K", "NX4832K035"),
                                      (f_probes, "F", "NX4832F035")):
            with self.subTest(series):
                probe = _probe(module, "%s-compile-T-blank" % series.lower())
                decoded = read_decoded(read_tft(whole_file_of(probe), probe.name, check=False))
                self.assertEqual((decoded.series, decoded.model, decoded.rotation,
                                  decoded.encoding), (series, model, 0, "iso-8859-1"))
                self.assertEqual([page.objects[0].name.text for page in decoded.pages],
                                 ["page0"])
                self.assertEqual([each.name.text for each in decoded.ints],
                                 ["sys0", "sys1", "sys2"])
                self.assertEqual([(each.kind, each.resource_id) for each in decoded.resources],
                                 [("font", 0)])


class OlderLayoutTest(unittest.TestCase):

    def test_p_before_1_63_refuses_a_slot_without_a_name(self):
        # Before 1.63, a record of P has 98 slots, of which the decoded file
        # names those 1.63.3's table names. A record that fills another, such
        # as slot 63, is refused rather than its value dropped.
        code = user_code_of(_older_probe("editor-1-60-1-p-compile-T-blank"), (1, 60, 1))
        decoded = decoded_user_code(code, "P", "NX8048P050", 0, "iso-8859-1", (1, 60, 1))
        self.assertEqual(len(decoded.attribute_names), 98)
        self.assertIsNone(decoded.attribute_names[63])
        records = bytearray(code.records)
        struct.pack_into("<H", records, decoded_file.RECORD_HEAD.size + 2 * 63, 5)
        with self.assertRaisesRegex(DecodeError, "fills slot 63"):
            decoded_user_code(replace(code, records=bytes(records)), "P", "NX8048P050", 0,
                              "iso-8859-1", (1, 60, 1))

    def test_a_gmov_before_1_63_keeps_its_from_in_slot_2(self):
        # Before 1.63, a gmov keeps its from in slot 2, which gives sta on
        # every other type, and leaves slot 96 empty. From 1.63 on, its from
        # is in slot 96, as a video's is.
        probe = next(each for each in editor_1_60_1_p_probes.PROBES
                     if each.name.endswith("-p-media-an-animation"))
        decoded = decoded_user_code(user_code_of(probe, (1, 60, 1)), "P", "NX8048P050", 0,
                                    "iso-8859-1", (1, 60, 1))
        entries = {each.type_name: named_entries(each, decoded)
                   for each in decoded.pages[0].objects}
        self.assertIn("from", entries["gmov"])
        self.assertNotIn("sta", entries["gmov"])
        self.assertIn("sta", entries["page"])

    def test_the_slots_named_before_1_63_are_those_the_probes_fill(self):
        # The decoded file names a slot of P before 1.63 only where a probe of
        # 1.60.1, of a page or of a component type, fills it, so that no slot
        # is named on 1.63.3's word alone, and every slot a probe fills is
        # named.
        filled = set()
        for probe in editor_1_60_1_probes.PROBES + editor_1_60_1_p_probes.PROBES:
            if probe.base != "P":
                continue
            code = user_code_of(probe, (1, 60, 1))
            size = decoded_file.RECORD_HEAD.size + 2 * 98
            for at in range(0, len(code.records) - size + 1, size):
                slots = struct.unpack_from("<98H", code.records,
                                           at + decoded_file.RECORD_HEAD.size)
                filled |= {slot for slot, value in enumerate(slots)
                           if value != decoded_file.NO_SLOT}
        named = decoded_file._P_SLOTS_BEFORE_1_63
        self.assertEqual(filled, {slot for slot, name in enumerate(named) if name is not None})

    def test_a_file_before_1_63(self):
        # The Nextion Editors before 1.63 start the user code with two blocks:
        # the int area and the page list, without a 0 word before them. Their
        # page index takes 12 bytes a page. A file of K of 1.61.2, of the
        # project of pages, ints, and code that 1.60.1 kept, is read whole.
        code = user_code_of(_older_probe("editor-1-60-1-k-compile-T-pages-ints-code"),
                            (1, 60, 1))
        font = struct.pack("<24xI16x", FONT_HEADER) + b"a font"
        tft = read_tft(made_tft("K", code, fonts=font, version=(1, 61, 2), macros_unset=True,
                                first_blocks=2), "older")
        decoded = decoded_file.read_decoded(tft)
        self.assertEqual(decoded.int_area, code.blocks[0])
        self.assertEqual([page.objects[0].name.text for page in decoded.pages],
                         ["page0", "page1", "page2"])
        self.assertEqual([(each.name.text, each.value) for each in decoded.ints],
                         [("sys0", 0), ("sys1", 0), ("sys2", 0), ("int3", 5), ("int4", -7)])

    def test_a_file_of_1_63_3(self):
        # The Nextion Editor 1.63.3's user code starts with three blocks: a 0
        # word, the int area, and the page list. Its file of K is read
        # whole. The file's one font is a header, which places its rest
        # right after it, then the rest.
        code = user_code_of(_older_probe("editor-1-63-3-k-compile-T-pages-ints-code"))
        font = struct.pack("<24xI16x", FONT_HEADER) + b"a font"
        tft = read_tft(made_tft("K", code, fonts=font, version=(1, 63, 3), macros_unset=True,
                                first_blocks=3), "older")
        decoded = decoded_file.read_decoded(tft)
        self.assertEqual(decoded.int_area, code.blocks[1])
        # The probe's pages are page0, settings, and about, and its ints count
        # and limit, of 5 and -7, after the system's sys0 to sys2. The file
        # keeps only their names' checksums, and its code does not hold them
        # as text, so all but page0 and the system's take readable names.
        self.assertEqual([page.objects[0].name.text for page in decoded.pages],
                         ["page0", "page1", "page2"])
        self.assertEqual([(each.name.text, each.value) for each in decoded.ints],
                         [("sys0", 0), ("sys1", 0), ("sys2", 0), ("int3", 5), ("int4", -7)])

    def test_a_filled_slot_of_no_name_on_p_of_1_63_3(self):
        # On P, the Nextion Editor 1.63.3 writes 108 slots a record, named by
        # the decoded file's own table. A record that fills a slot the table
        # does not name, here slot 0, is refused, as its value would be lost.
        code = user_code_of(_older_probe("editor-1-63-3-p-compile-T-blank"))
        records = bytearray(code.records)
        struct.pack_into("<H", records, decoded_file.RECORD_HEAD.size, 3)
        code = replace(code, records=bytes(records))
        with self.assertRaisesRegex(DecodeError, "fills slot 0"):
            decoded_user_code(code, "P", "NX8048P050", 0, "iso-8859-1", (1, 63, 3))


class SlotsOf163Test(unittest.TestCase):

    def test_t_s_slot_of_each_attribute(self):
        # On P of the Nextion Editor 1.63.3, each attribute takes T's slot
        # for it, so the decoded file's table of slots gives every name at
        # the slot the compile's tables of T give it. A probe fills only the
        # slots its components use, so this checks the others too.
        expected = _t_slots()
        # A slot of each kind of table, so that a table renamed in the
        # compile is not left out of the check unseen.
        for anchor in ((2, "sta"), (60, "borderc"), (38, "bco1"), (4, "bco"), (31, "bpic"),
                       (10, "pco0")):
            self.assertIn(anchor, expected)
        table = decoded_file._P_SLOTS_OF_1_63
        for (slot, name), where in sorted(expected.items()):
            with self.subTest(slot=slot, name=name, where=where):
                self.assertEqual(table[slot], name)
        # No slot has two names among T's tables, as one name a slot is all
        # the decoded file's table can give.
        self.assertEqual(len({slot for slot, _ in expected}), len(expected))


def _t_slots() -> dict:
    """Returns {(slot, attribute name): the table giving it} from each table
    of a record's slots that the compile keeps for T: each type's, by slot
    or by name, a progress bar's by the part each slot gives, a page's
    background's, and those a type works out from a first slot."""
    found = {}
    for info in pkgutil.iter_modules(component_types.__path__):
        module = importlib.import_module("nxwright.tft.component_types." + info.name)
        where = info.name
        for table in ("_SLOTS", "_BORDER_SLOTS"):
            found.update({(slot, name): where
                          for slot, name in getattr(module, table, {}).items()})
        for table in ("_ATTRIBUTE_SLOTS", "_BACKGROUND_SLOTS"):
            found.update({(slot, name): where
                          for name, slot in getattr(module, table, {}).items()})
        for sta, parts in getattr(module, "_PART_SLOTS", {}).items():
            names = dict(zip(("empty", "filled"), module.PARTS[sta]))
            found.update({(slot, names.get(part, part)): where for slot, part in parts.items()})
    found.update({(slot, name): "page" for name, slot in frame._PAGE_BACKGROUND_SLOTS.items()})
    # Slots a type works out rather than lists: a waveform's channel colours,
    # pco0 to pco3 from its first colour's slot, and a QR code's logo.
    waveform = importlib.import_module("nxwright.tft.component_types.waveform")
    found.update({(waveform._FIRST_COLOUR_SLOT + number, "pco%d" % number): "waveform"
                  for number in range(waveform.MOST_CHANNELS)})
    qr_code = importlib.import_module("nxwright.tft.component_types.qr_code")
    found[(qr_code._PIC_SLOT, "pic")] = "qr_code"
    return found


class OlderEdgeTest(unittest.TestCase):

    def test_a_file_of_e_on_an_older_layout(self):
        # The Nextion Editors before 1.68.1 write no files of E, so user code
        # of E of 1.63.3 is refused rather than read by 1.68.2's numbers.
        code = user_code_of(_older_probe("editor-1-63-3-p-compile-T-blank"))
        with self.assertRaisesRegex(DecodeError, "Edge series of the Nextion Editor 1.63.3"):
            decoded_user_code(code, "E", "NX8048P050", 0, "iso-8859-1", (1, 63, 3))


class LaterVersionTest(unittest.TestCase):

    def test_a_file_of_a_later_nextion_editor(self):
        # A later Nextion Editor may number its commands differently. Read
        # with 1.68.2's numbers, its code could decode into the wrong
        # commands. Those compile back into the same bytes, so the round trip
        # would not catch the error.
        code = user_code_of(_probe(p_probes, "p-page-of-swipes"))
        with self.assertRaisesRegex(DecodeError, r"^the file was made by the Nextion Editor "
                                                 r"1\.69\.0, but nxwright decompiles only files "
                                                 r"made by the Nextion Editor 1\.68\.2 or "
                                                 r"older\. A later version may number its "
                                                 r"commands differently$"):
            decoded_user_code(code, "P", "NX8048P050", 0, "iso-8859-1", (1, 69, 0))


def _older_probe(name: str):
    """Returns the probe of an older Nextion Editor named `name`, of 1.63.3
    or 1.60.1."""
    return next(probe for probe in older_editor_probes.PROBES + editor_1_60_1_probes.PROBES
                if probe.name == name)


if __name__ == "__main__":
    unittest.main()
