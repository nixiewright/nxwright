"""The button component (tft/component_types/button.py): its blocks at the
start of its events, its values, its variants, what the button's list
matched, and which of its attributes code may use.

Each test gives the function it checks a probe's page, made in memory from
the probe's components, in a Project of the facts it reads
(tests/tft/unit_inputs.py): tools/tft/probing/button_probes.py and
tools/tft/probing/button_border_and_picture_probes.py. The probes' fixtures,
and a button in a second font, which a page in memory cannot hold, are
compared on whole builds in tests/tft/test_whole_files.py.
"""
from dataclasses import replace
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import button_border_and_picture_probes, button_probes, p_probes
from nxwright.tft.component_types import SETBRUSH, button, entry_operand
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing.probe_runner import Probe
from nxwright.tft.statements import CodePlace, StatementError, encode_line
from tests.tft.p_components import PTypePieces
from tests.tft.t_components import CodePieces, EventStartPieces, TypePieces
from tests.tft.unit_inputs import place, probe_facts, probe_project


_PROBES = button_probes.PROBES + button_border_and_picture_probes.PROBES


def value(number: int, size: int = 2) -> bytes:
    return number.to_bytes(size, "little", signed=True)


class EventStartTest(unittest.TestCase):
    """The blocks the Nextion Editor writes at the start of a button's
    events: its val set, then ref of its ID."""

    def test_down_and_up(self):
        # A page's first button, ID 1: its first entry is 33, so its val's is
        # 61. b0 of button-two, at its place there.
        place = place_of("button-two", 1)
        ref = b"\x09\x03\x04" + b"1+" + b"\x03\xff\xff\x00\x00"
        b0 = facts("button-two").pages[0].objects[1]
        self.assertEqual(button.variant(b0).event_start(b0, None, place, "down"),
                         [b"\x01\x3d\x00\x00\x00=1", ref])
        self.assertEqual(button.variant(b0).event_start(b0, None, place, "up"),
                         [b"\x01\x3d\x00\x00\x00=0", ref])


def facts(name: str):
    """Returns a Project of facts of the pages of the probe `name`
    (unit_inputs.probe_facts)."""
    return probe_facts(next(probe for probe in _PROBES if probe.name == name))


def place_of(name: str, object_id: int):
    """Returns where the object `object_id` of page0 of the probe `name`
    lies, as the probe's table gives it (unit_inputs.place)."""
    return place(next(probe for probe in _PROBES if probe.name == name), "page0-%d" % object_id)


def look_ends(module, project, object_id: int, place) -> list:
    """Returns the ends of the setbrush blocks of the drawing of the
    component `object_id` of page0 of `project`, at `place`, from the entry
    of its isbr on: two, its look pressed and released."""
    page_object = project.pages[0].objects[object_id]
    isbr = entry_operand(place.first_entry + 31)
    drawing = module.variant(page_object).drawing(page_object, project, place)
    return [block[block.index(isbr):] for block in drawing if block.startswith(SETBRUSH["T"])]


def entry_values(module, project, object_id: int, place, numbers: tuple) -> list:
    """Returns the values of the entries `numbers`, within the type, of the
    component `object_id` of page0 of `project`, at `place`."""
    page_object = project.pages[0].objects[object_id]
    data = module.variant(page_object).data(page_object, project, place)
    return [struct.unpack_from("<IiiiII", data, 24 * number)[1] for number in numbers]


class ValuesTest(unittest.TestCase):
    """A button's attributes that its memory alone gives, each pair apart,
    and its spax and spay, which its drawing and its entries give, as the
    Nextion Editor wrote them."""

    def memories(self, name: str) -> list:
        project = facts(name)
        return [button.variant(page_object).memory(page_object, project)[:13]
                for page_object in project.pages[0].objects[1:]]

    def test_its_colours(self):
        # Its font, its val, its bco, bco2, pco, and pco2, then its xcen,
        # ycen, and isbr.
        self.assertEqual(self.memories("button-of-other-colours"), [
            bytes.fromhex("00 00 01 00 02 00 03 00 04 00 01 01 00"),
            bytes.fromhex("00 00 ff ff 00 00 00 f8 1f 00 01 01 00")])

    def test_its_placing_and_val(self):
        self.assertEqual(self.memories("button-of-other-placing"), [
            bytes.fromhex("00 00 18 c6 00 04 00 00 ff ff 00 02 01"),
            bytes.fromhex("00 00 18 c6 00 04 00 00 ff ff 02 00 00")])
        self.assertEqual(self.memories("button-pressed-from-the-start")[0][:2], b"\x00\x01")

    def test_its_spacing(self):
        # Each look's setbrush gives spax and spay as numbers, after isbr's
        # entry; so do entries 32 and 33.
        name = "button-of-spacing"
        project = facts(name)
        for object_id, spacing, values in ((1, b",5,7,0,1", [5, 7]),
                                           (2, b",255,3,0,1", [255, 3])):
            place = place_of(name, object_id)
            with self.subTest(object_id):
                isbr = entry_operand(place.first_entry + 31)
                self.assertEqual(look_ends(button, project, object_id, place),
                                 [isbr + spacing] * 2)
                self.assertEqual(entry_values(button, project, object_id, place, (32, 33)),
                                 values)


class VariantTest(unittest.TestCase):
    """A button of each style, and with pictures or crops behind it, as the
    Nextion Editor wrote them, each at its place in its probe (place_of)."""

    PROBES = {"styles": "button-of-each-style", "pictures": "button-of-pictures-and-crops"}

    @classmethod
    def setUpClass(cls):
        for name, probe_name in cls.PROBES.items():
            setattr(cls, name, facts(probe_name))

    def place(self, project, page_object):
        probe_name = next(self.PROBES[name] for name in self.PROBES
                          if getattr(self, name) is project)
        return place_of(probe_name, project.pages[0].objects.index(page_object))

    def drawing(self, project, page_object) -> list:
        return button.variant(page_object).drawing(page_object, project,
                                                   self.place(project, page_object))

    def test_a_border_behind_pictures_or_crops(self):
        # A style of 1 gives its borderc and borderw entries behind pictures
        # or crops too, though it draws no border there: 20 and 21, so its
        # font is 22, its pic or picc 23, its pic2 or picc2 24, and its val
        # 29, each two on from theirs at another style there; 43 entries.
        made = facts("button-of-a-border-behind-pictures-and-crops")
        picture, crop = (button.variant(page_object)
                         for page_object in made.pages[0].objects[1:3])
        self.assertEqual([picture.ENTRIES, crop.ENTRIES], [43, 43])
        self.assertEqual([picture.attribute_place(name)
                          for name in ("borderc", "borderw", "font", "pic", "pic2", "val")],
                         [20, 21, 22, 23, 24, 29])
        self.assertEqual([crop.attribute_place(name) for name in ("picc", "picc2")], [23, 24])

    def test_its_entries_and_slots(self):
        # A style of 1 gives its borderc and borderw entries 21 and 22, right
        # after its style's, so its font is 23 and its val 30, two on; 44
        # entries. Pictures or crops behind it give its style none, so its
        # font is 20, its pic or picc 21, its pic2 or picc2 22, and its val
        # 27, one back; 41 entries.
        bordered = button.variant(self.styles.pages[0].objects[2])
        picture, crop = (button.variant(page_object)
                         for page_object in self.pictures.pages[0].objects[1:3])
        self.assertEqual([one.ENTRIES for one in (bordered, picture, crop)], [44, 41, 41])
        self.assertEqual([bordered.attribute_place(name) for name in
                          ("style", "borderc", "borderw", "font", "bco", "bco2", "val")],
                         [20, 21, 22, 23, 24, 25, 30])
        self.assertEqual([picture.attribute_place(name) for name in ("font", "pic", "pic2", "val")],
                         [20, 21, 22, 27])
        self.assertEqual([crop.attribute_place(name) for name in ("picc", "picc2")], [21, 22])
        slots = bordered.record_slots()
        self.assertEqual([slots[slot] for slot in (4, 24, 59, 60, 61)], [24, 25, 20, 21, 22])
        slots = picture.record_slots()
        self.assertEqual([slots[6], slots[17]] + [slots.get(slot) for slot in (4, 24, 59)],
                         [21, 22, None, None, None])
        slots = crop.record_slots()
        self.assertEqual([slots[5], slots[23]], [21, 22])

    def test_its_drawing_by_style(self):
        # Each look is setbrush and zstr, the pressed one first. At its
        # default style, each ends with its own 3D border, sunken pressed
        # and raised released; at a style of 1 to 3, one border follows
        # both; at 0, none. Its setbrushes end with its border's width.
        b0, b1, b2, b3, b4 = self.styles.pages[0].objects[1:6]
        flat, bordered, sunken, raised, pressed_in = (self.drawing(self.styles, page_object)
                                                     for page_object in (b0, b1, b2, b3, b4))
        self.assertEqual([len(drawing) for drawing in (flat, bordered, sunken, raised,
                                                       pressed_in)], [6, 7, 7, 7, 8])
        self.assertEqual([drawing[1][-4:] for drawing in (flat, bordered, sunken, pressed_in)],
                         [b",0,0", b",0,3", b",0,1", b",0,1"])
        self.assertEqual(bordered[-1], b"\x09\x07\x0810,70,100,50,"
                         b"\x03\x00\xf8\x00\x00,\x03\x00\xf8\x00\x00,3")
        self.assertEqual(sunken[-1], b"\x09\x07\x0810,130,100,50,"
                         b"\x03\x28\x42\x00\x00,\x03\x1c\xe7\x00\x00,1")
        self.assertEqual(raised[-1], b"\x09\x07\x0810,190,100,50,"
                         b"\x03\x1c\xe7\x00\x00,\x03\x28\x42\x00\x00,1")
        self.assertEqual([pressed_in[3], pressed_in[7]],
                         [b"\x09\x07\x0810,250,100,50,"
                          b"\x03\x28\x42\x00\x00,\x03\x1c\xe7\x00\x00,1",
                          b"\x09\x07\x0810,250,100,50,"
                          b"\x03\x1c\xe7\x00\x00,\x03\x28\x42\x00\x00,1"])

    def test_its_drawing_behind_a_picture(self):
        # Each look is its setbrush alone, which gives its sta after its
        # ycen's entry, 26; one zstr follows both, and no border.
        picture = self.pictures.pages[0].objects[1]
        drawing = self.drawing(self.pictures, picture)
        self.assertEqual(len(drawing), 5)
        self.assertTrue(drawing[4].startswith(b"\x09\x13\x04"))
        first_entry = self.place(self.pictures, picture).first_entry
        for setbrush in (drawing[1], drawing[3]):
            self.assertIn(entry_operand(first_entry + 26) + b",2,", setbrush)
            self.assertTrue(setbrush.endswith(b",0,0"))

    def test_its_memory_behind_pictures(self):
        # The pictures' IDs lie where its bco and bco2 lie: bg, picture 0,
        # then bg2, picture 1, for the first, which starts pressed; then the
        # crops of bg2 and bg.
        picture, crop = self.pictures.pages[0].objects[1:3]
        self.assertEqual([button.variant(page_object).memory(page_object, self.pictures)[:6]
                          for page_object in (picture, crop)],
                         [bytes.fromhex("00 01 00 00 01 00"), bytes.fromhex("00 00 01 00 00 00")])


class PiecesTest(TypePieces, CodePieces, EventStartPieces, unittest.TestCase):
    """Each button of each probe that keeps its whole user code, at its type's
    functions, its events' start among them, and each probe of code, at the
    statement encoder, against the probe's pieces (tests/tft/t_components.py)."""

    TYPE = "button"
    PROBES = _PROBES
    COUNT = 19
    CODE_COUNT = 4


class PPiecesTest(PTypePieces, CodePieces, unittest.TestCase):
    """Each button of each of its probes on P that keeps its whole user code, at
    its type's functions on P, against the probe's pieces
    (tests/tft/p_components.py)."""

    TYPE = "button"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-button-")]
    COUNT = 20
    CODE_COUNT = 3


class MatchedTest(unittest.TestCase):
    """The needs button.MATCHED covers (matching.py)."""

    def need(self, attribute: str, raw: bytes, **context) -> Need:
        attributes = {"x": value(10), "y": value(10), "w": value(100), "h": value(50),
                      "txt_maxl": value(10)}
        attributes.update({name: value(number) for name, number in context.items()})
        return Need("attribute", "button." + attribute, raw, context=attributes)

    def test_what_it_covers(self):
        covered = [Need("type", "button"), Need("attribute", "button.objname", b"b0"),
                   self.need("x", value(220), x=220, y=430),
                   self.need("w", value(2), x=0, y=0, w=2, h=2),
                   self.need("txt", b""), self.need("txt", b"Go12"),
                   self.need("txt", b"Press", txt_maxl=5), self.need("txt", b"Press!"),
                   self.need("txt", "Ünï".encode("iso-8859-1")),
                   self.need("txt_maxl", value(1)), self.need("txt_maxl", value(200)),
                   self.need("font", b"\x01"), self.need("val", b"\x01")]
        # The values its memory alone gives, at their ends.
        for name, ends in (("bco", (0, 0xFFFF)), ("bco2", (0, 0xFFFF)), ("pco", (0, 0xFFFF)),
                           ("pco2", (0, 0xFFFF)), ("xcen", (0, 2)), ("ycen", (0, 2)),
                           ("isbr", (0, 1)), ("spax", (0, 255)), ("spay", (0, 255))):
            covered += [self.need(name, end.to_bytes(2, "little")) for end in ends]
        # What lies behind it, its border, and its pictures, on T and K: each
        # style at each sta.
        looks = [self.need("sta", value(sta)) for sta in (0, 2)]
        looks += [self.need("style", value(style)) for style in (0, 1, 2, 3)]
        looks += [self.need("style", value(style), sta=sta) for sta in (0, 2)
                  for style in (0, 1, 2, 3, 4)]
        looks += [self.need(name, end.to_bytes(2, "little")) for name, ends in (
            ("borderc", (0, 0xFFFF)), ("borderw", (0, 255)), ("pic", (0, 0xFFFF)),
            ("pic2", (0, 0xFFFF)), ("picc", (0, 0xFFFF)), ("picc2", (0, 0xFFFF)))
            for end in ends]
        covered += looks + [replace(need, series="K") for need in looks]
        # On P and E, a sta of 3 too, nothing behind it, at any style.
        covered += [replace(self.need("sta", value(3)), series=series) for series in "PE"]
        covered += [replace(self.need("style", value(style), sta=3), series="P")
                    for style in (0, 1, 2, 3, 4)]
        self.assertEqual(unmatched(covered, button.MATCHED), [])

    def test_a_txt_maxl_its_txt_does_not_fit(self):
        # A txt of 6 characters, as the default "newtxt", and a txt_maxl of 5:
        # the Nextion Editor refuses it.
        need = self.need("txt_maxl", value(5))
        need.context["txt"] = b"newtxt"
        self.assertEqual(unmatched([need], button.MATCHED), [need])

    def test_what_it_leaves_out(self):
        left = [self.need("txt", b"Pressed", txt_maxl=5), self.need("spax", value(256))]
        # Past what the probes showed: a style past 4, on T and on P; and a
        # sta past 2 on T, and past 3 on P.
        past = [self.need("style", value(5)), self.need("borderw", value(256))]
        left += past + [replace(need, series="P") for need in past]
        left += [self.need("sta", value(3)), replace(self.need("sta", value(4)), series="P")]
        self.assertEqual(unmatched(left, button.MATCHED), left)


class CodeTest(unittest.TestCase):
    """Code may use a button's txt, its val, and any other attribute it
    writes."""

    @classmethod
    def setUpClass(cls):
        cls.project = facts("button-one")

    def test_its_txt_and_val(self):
        # b0 is page0's first button: its first entry is 33, so its txt's is
        # 62 and its val's 61.
        place = CodePlace(0, "b0", "up")
        self.assertEqual(encode_line('b0.txt="Yo"', place, CompileContext(self.project)),
                         b'\x01\x3e\x00\x00\x00="Yo"')
        self.assertEqual(encode_line("b0.val=1", place, CompileContext(self.project)),
                         b"\x01\x3d\x00\x00\x00=1")

    def test_its_other_attributes(self):
        # Any attribute it writes, such as its bco, entry 22 within the type,
        # 55 counted from the page's; but not one it does not write.
        place = CodePlace(0, "b0", "up")
        self.assertEqual(encode_line("b0.bco=5", place,
                                     CompileContext(self.project)), b"\x01\x37\x00\x00\x00=5")
        with self.assertRaisesRegex(StatementError, "b0's pw is not encoded"):
            encode_line("b0.pw=5", place, CompileContext(self.project))

    def test_the_check_takes_its_attributes(self):
        # The page of a probe of button_probes.with_button_code.
        lines = ['b0.txt="Yo"', "b0.val=1", "sys0=b0.val", "b0.bco=5", "get b0.val",
                 "strlen b0.txt,sys0", "sys0=b0.x", *button_probes.VAL_IN_CONDITIONS]
        project = probe_project(Probe("code", "T", button_probes.with_button_code(lines),
                                      None, None))
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
