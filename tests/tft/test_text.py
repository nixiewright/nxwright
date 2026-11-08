"""The text component (tft/component_types/text.py): a text's txt as an
operand; its values; the variants of its sta and style; and what the text's
list matched.

Each test gives the function it checks a probe's page, made in memory from
the probe's components, in a Project of the facts it reads
(tests/tft/unit_inputs.py): tools/tft/probing/text_probes.py and
tools/tft/probing/text_border_and_picture_probes.py. The probes' fixtures, and
a text in a second font, which a page in memory cannot hold, are compared
on whole builds in tests/tft/test_whole_files.py.
"""
from dataclasses import replace
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import p_probes, text_border_and_picture_probes, text_probes
from nxwright.tft.component_types import entry_operand, text
from nxwright.tft.matching import Need, unmatched
from nxwright.tft.statements import CodePlace, StatementError, encode_line
from tests.tft.p_components import PTypePieces
from tests.tft.t_components import CodePieces, TypePieces
from tests.tft.unit_inputs import place, probe_facts


_PROBES = text_probes.PROBES + text_border_and_picture_probes.PROBES


def facts(name: str):
    """Returns a Project of facts of the pages of the probe `name`
    (unit_inputs.probe_facts)."""
    return probe_facts(next(probe for probe in _PROBES if probe.name == name))


def place_of(name: str, object_id: int):
    """Returns where the object `object_id` of page0 of the probe `name`
    lies, as the probe's table gives it (unit_inputs.place). A probe that
    keeps no fixtures has no table: its object takes the place of the first
    text of text-two, whose drawing and entries differ from it only in what
    a test of its looks does not read."""
    probe = next(probe for probe in _PROBES if probe.name == name)
    if probe.fixtures is None:
        return place(next(probe for probe in _PROBES if probe.name == "text-two"), "page0-1")
    return place(probe, "page0-%d" % object_id)


def number(value: int) -> bytes:
    return value.to_bytes(2, "little", signed=True)


class OperandTest(unittest.TestCase):
    """A text's txt as an operand: 01, then its entry's number, counted
    across the project's pages and objects."""

    def entry_operand(self, entry: int) -> bytes:
        return b"\x01" + struct.pack("<I", entry) + b'="Yo"'

    def test_counted_across_objects(self):
        # t1's entries follow the page's 33 and t0's 41; txt is its 29th.
        project = facts("text-setting-second-txt")
        self.assertEqual(encode_line('t1.txt="Yo"', CodePlace(0, "t0", "up"),
                                     CompileContext(project)),
                         self.entry_operand(33 + 41 + 28))

    def test_counted_across_pages(self):
        # page1's entries follow page0's 33, then t0's follow page1's own.
        project = facts("text-on-second-page")
        self.assertEqual(encode_line('t0.txt="Yo"', CodePlace(1, "t0", "up"),
                                     CompileContext(project)),
                         self.entry_operand(33 + 33 + 28))

    def test_refused(self):
        project = facts("text-setting-second-txt")
        for line, place, said in (
                ('t0.txt="Yo"', CodePlace(), "attribute in program.s"),
                ('t9.txt="Yo"', CodePlace(0, "t0", "up"), "t9 is no component"),
                ('page0.txt="Yo"', CodePlace(0, "t0", "up"), "page0's txt is not encoded"),
                ("t0.val=5", CodePlace(0, "t0", "up"), "t0's val is not encoded")):
            with self.subTest(line=line):
                with self.assertRaisesRegex(StatementError, said):
                    encode_line(line, place, CompileContext(project))


class ObjectOrderTest(unittest.TestCase):
    """The frame numbers a page's objects by their place, which must be their
    ID, as nxwright writes them."""

    def test_objects_out_of_id_order(self):
        from nxwright.tft import frame
        from tools.tft.probing.frame_probes import stand_in_code
        # The Project is shared with other tests, so this test swaps the objects in a copy.
        project = facts("text-two")
        objects = list(project.pages[0].objects)
        objects[1], objects[2] = objects[2], objects[1]
        project = replace(project, pages=[replace(project.pages[0], objects=objects)]
                          + project.pages[1:])
        with self.assertRaisesRegex(frame.FrameError, "t1's ID is 2, but it is object 1"):
            frame.user_code(project, stand_in_code)


def memory(page_object, project) -> bytes:
    return text.variant(page_object).memory(page_object, project)


class ValuesTest(unittest.TestCase):
    """A text's attributes that its memory gives, and its spax and spay,
    which its drawing and its entries give, as the Nextion Editor wrote
    them."""

    def test_memory(self):
        # Its font, isbr, pco, bco, xcen, ycen, and pw, then its txt.
        project = facts("text-of-other-looks")
        t0, t1, t2 = project.pages[0].objects[1:]
        for page_object, values in ((t0, "00 01 00 f8 00 00 00 02 01"),
                                    (t1, "00 00 00 00 ff ff 02 00 00"),
                                    (t2, "00 00 ff ff 01 00 01 01 00")):
            with self.subTest(page_object.attribute("objname")):
                self.assertEqual(memory(page_object, project)[:9], bytes.fromhex(values))

    def test_pw_apart_from_isbr(self):
        # Its isbr is its memory's second byte, and its pw its ninth, as the
        # Nextion Editor wrote them for a pw apart from an isbr.
        project = facts("text-of-pw-apart-from-isbr")
        t0, t1 = project.pages[0].objects[1:]
        self.assertEqual(memory(t0, project)[:9], bytes.fromhex("00 00 00 00 ff ff 01 01 01"))
        self.assertEqual(memory(t1, project)[:9], bytes.fromhex("00 01 00 00 ff ff 01 01 00"))

    def test_spacing(self):
        # setbrush gives spax and spay as numbers, after isbr's entry, and so
        # do entries 31 and 32. t0's first entry is 33, after the page's
        # entries, and t1's is 74, after t0's 41. t1's base is 48, after
        # t0's 20 bytes of memory.
        project = facts("text-of-spacing")
        for object_id, spax, spay in ((1, 5, 7), (2, 255, 255)):
            page_object = project.pages[0].objects[object_id]
            place = place_of("text-of-spacing", object_id)
            first_entry = place.first_entry
            with self.subTest(spax):
                setbrush, _ = text.variant(page_object).drawing(page_object, project, place)
                self.assertTrue(setbrush.endswith(
                    entry_operand(first_entry + 30) + b",%d,%d," % (spax, spay)
                    + entry_operand(first_entry + 27) + b",0"))
                data = text.variant(page_object).data(page_object, project, place)
                self.assertEqual([struct.unpack_from("<IiiiII", data, 24 * entry)[1]
                                  for entry in (31, 32)], [spax, spay])


class VariantTest(unittest.TestCase):
    """A text of each style, and with a picture or a crop behind it, as the
    Nextion Editor wrote them, each at its place in its probe (place_of)."""

    PROBES = {"styles": "text-of-each-style", "borders": "text-of-borders",
              "pictures": "text-of-a-picture-and-a-crop"}

    @classmethod
    def setUpClass(cls):
        for name, probe_name in cls.PROBES.items():
            setattr(cls, name, facts(probe_name))

    def drawing(self, project, page_object) -> list:
        probe_name = next(self.PROBES[name] for name in self.PROBES
                          if getattr(self, name) is project)
        place = place_of(probe_name, project.pages[0].objects.index(page_object))
        return text.variant(page_object).drawing(page_object, project, place)

    def test_a_border_behind_a_picture_or_a_crop(self):
        # A style of 1 gives its borderc and borderw entries behind a
        # picture or a crop too, though it draws no border there: 21 and 22,
        # so its font is 23, its pic or picc 24, and its txt 29, each two on
        # from theirs at a style of 0 there; 42 entries.
        made = facts("text-of-a-border-behind-a-picture-and-a-crop")
        picture, crop = (text.variant(page_object) for page_object in made.pages[0].objects[1:3])
        self.assertEqual([picture.ENTRIES, crop.ENTRIES], [42, 42])
        self.assertEqual([picture.attribute_place(name)
                          for name in ("borderc", "borderw", "font", "pic", "txt")],
                         [21, 22, 23, 24, 29])
        self.assertEqual(crop.attribute_place("picc"), 24)
        self.assertRaises(KeyError, picture.attribute_place, "style")

    def test_its_entries_and_slots(self):
        # A style of 1 gives its borderc and borderw entries 22 and 23, so
        # its font is 24 and its txt 30, two on; 43 entries. A picture or a
        # crop behind it gives its style none, so its font is 21, its pic or
        # picc 22, and its txt 27, one back; 40 entries.
        bordered, sunken = (text.variant(page_object)
                            for page_object in self.styles.pages[0].objects[1:3])
        picture, crop = (text.variant(page_object)
                         for page_object in self.pictures.pages[0].objects[1:3])
        self.assertEqual([one.ENTRIES for one in (bordered, sunken, picture, crop)],
                         [43, 41, 40, 40])
        self.assertEqual([bordered.attribute_place(name) for name in
                          ("style", "borderc", "borderw", "font", "bco", "pw", "txt", "isbr")],
                         [20, 22, 23, 24, 25, 29, 30, 32])
        self.assertEqual([picture.attribute_place(name) for name in ("font", "pic", "txt")],
                         [21, 22, 27])
        self.assertEqual(crop.attribute_place("picc"), 22)
        for one, name in ((picture, "style"), (picture, "bco"), (sunken, "borderc")):
            with self.subTest(name), self.assertRaises(KeyError):
                one.attribute_place(name)
        slots = bordered.record_slots()
        self.assertEqual([slots[slot] for slot in (4, 59, 60, 61)], [25, 20, 22, 23])
        slots = picture.record_slots()
        self.assertEqual((slots[6], slots.get(4), slots.get(59)), (22, None, None))
        self.assertEqual(crop.record_slots()[5], 22)

    def test_its_border(self):
        # Its setbrush ends with its border's width: its borderw, 3, at a
        # style of 1, 1 at 2 and 3, and 0 at 0. Its border's block follows
        # its zstr: its borderc twice and its borderw, as numbers, at 1; 3D,
        # dark then light at 2, and light then dark at 3; none at 0.
        drawings = [self.drawing(self.styles, page_object)
                    for page_object in self.styles.pages[0].objects[1:5]]
        self.assertEqual([drawing[0][-2:] for drawing in drawings],
                         [b",3", b",1", b",1", b",0"])
        self.assertEqual(drawings[0][2], b"\x09\x07\x0810,10,100,30,"
                         b"\x03\x00\xf8\x00\x00,\x03\x00\xf8\x00\x00,3")
        self.assertEqual(drawings[1][2], b"\x09\x07\x0810,60,100,30,"
                         b"\x03\x28\x42\x00\x00,\x03\x1c\xe7\x00\x00,1")
        self.assertEqual(drawings[2][2], b"\x09\x07\x0810,110,100,30,"
                         b"\x03\x1c\xe7\x00\x00,\x03\x28\x42\x00\x00,1")
        self.assertEqual(len(drawings[3]), 2)

    def test_its_border_s_numbers(self):
        # A number of up to 3 characters is written as digits, a longer one
        # as a value.
        blocks = [self.drawing(self.borders, page_object)[2]
                  for page_object in self.borders.pages[0].objects[1:4]]
        self.assertEqual([block[3:].split(b",", 4)[4] for block in blocks],
                         [b"999,999,0", b"\x03\xe8\x03\x00\x00,\x03\xe8\x03\x00\x00,255",
                          b"0,0,1"])

    def test_what_lies_behind_it(self):
        # Its setbrush gives its sta after its ycen's entry, 25 behind a
        # picture, where a colour gives 1. Its memory gives the picture's ID
        # where its bco lies: picture 1, then a crop of picture 0.
        picture, crop = self.pictures.pages[0].objects[1:3]
        for page_object, sta in ((picture, b",2,"), (crop, b",0,")):
            first_entry = place_of(self.PROBES["pictures"],
                                   self.pictures.pages[0].objects.index(page_object)).first_entry
            self.assertIn(entry_operand(first_entry + 25) + sta,
                          self.drawing(self.pictures, page_object)[0])
        self.assertEqual([memory(page_object, self.pictures)[4:6]
                          for page_object in (picture, crop)], [b"\x01\x00", b"\x00\x00"])


class PiecesTest(TypePieces, CodePieces, unittest.TestCase):
    """Each text of each probe that keeps its whole user code, at its type's
    functions, and each probe of code, at the statement encoder, against the
    probe's pieces (tests/tft/t_components.py)."""

    TYPE = "text"
    PROBES = _PROBES
    COUNT = 21
    CODE_COUNT = 1


class PPiecesTest(PTypePieces, CodePieces, unittest.TestCase):
    """Each text of each of its probes on P that keeps its whole user code, at
    its type's functions on P, against the probe's pieces
    (tests/tft/p_components.py)."""

    TYPE = "text"
    # A text's probes, but those of the text commands' family and of txts'
    # characters, which their own tests take.
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-text-")
              and not probe.name.startswith(("p-text-commands-", "p-text-characters-"))]
    COUNT = 29
    CODE_COUNT = 1

class MatchedTest(unittest.TestCase):
    """The needs text.MATCHED covers (matching.py)."""

    def need(self, attribute: str, value: bytes, **context) -> Need:
        attributes = {"x": number(10), "y": number(10), "w": number(100), "h": number(30),
                      "txt_maxl": number(10)}
        attributes.update({name: number(value) for name, value in context.items()})
        return Need("attribute", "text." + attribute, value, context=attributes)

    def test_what_it_covers(self):
        covered = [Need("type", "text"), Need("attribute", "text.objname", b"t0"),
                   self.need("x", number(220), x=220, y=450),
                   self.need("w", number(320), x=0, y=0, w=320, h=480),
                   self.need("h", number(2), h=2, w=2),
                   self.need("txt", b""), self.need("txt", b"0123456789"),
                   # On T, a txt of printable ASCII characters and of those
                   # from U+00A0 to U+00FF, in iso-8859-1.
                   self.need("txt", b'a "b" \\c!'),
                   self.need("txt", "é ü ©".encode("iso-8859-1")),
                   self.need("txt_maxl", number(1)), self.need("txt_maxl", number(200)),
                   self.need("font", b"\x01")]
        # The values its memory and entries give, at their ends.
        for name, values in (("bco", (0, 0xFFFF)), ("pco", (0, 0xFFFF)), ("xcen", (0, 2)),
                             ("ycen", (0, 2)), ("isbr", (0, 1)), ("pw", (0, 1)),
                             ("spax", (0, 255)), ("spay", (0, 255))):
            covered += [self.need(name, value.to_bytes(2, "little")) for value in values]
        # What lies behind it, its border, and its pictures, on T and K: each
        # style at each sta.
        looks = [self.need("sta", number(sta)) for sta in (0, 2)]
        looks += [self.need("style", number(style)) for style in (1, 2, 3)]
        looks += [self.need("style", number(style), sta=sta) for sta in (0, 2)
                  for style in (0, 1, 2, 3)]
        looks += [self.need(name, value.to_bytes(2, "little")) for name, values in (
            ("borderc", (0, 0xFFFF)), ("borderw", (0, 255)), ("pic", (0, 0xFFFF)),
            ("picc", (0, 0xFFFF))) for value in values]
        covered += looks + [replace(need, series="K") for need in looks]
        # On P and E, a sta of 3 too, nothing behind it, at any style.
        covered += [replace(self.need("sta", number(3)), series=series) for series in "PE"]
        covered += [replace(self.need("style", number(style), sta=3), series="P")
                    for style in (0, 1, 2, 3)]
        self.assertEqual(unmatched(covered, text.MATCHED), [])

    def test_a_txt_maxl_its_txt_does_not_fit(self):
        # A txt of 6 characters, as the default "newtxt", and a txt_maxl of 5:
        # the Nextion Editor refuses it.
        need = self.need("txt_maxl", number(5))
        need.context["txt"] = b"newtxt"
        self.assertEqual(unmatched([need], text.MATCHED), [need])

    def test_what_it_leaves_out(self):
        left = [self.need("y", number(0), y=-1),
                self.need("txt", b"0123456789A"), self.need("spax", number(256)),
                self.need("spay", number(256))]
        # Past what the probes showed: a style past 3, on T and on P; a sta
        # past 2 on T, and past 3 on P; and a keyboard, which no case tried.
        past = [self.need("style", number(4)), self.need("borderw", number(256))]
        left += past + [replace(need, series="P") for need in past]
        left += [self.need("sta", number(3)), replace(self.need("sta", number(4)), series="P")]
        left.append(self.need("key", number(1)))
        self.assertEqual(unmatched(left, text.MATCHED), left)


if __name__ == "__main__":
    unittest.main()
