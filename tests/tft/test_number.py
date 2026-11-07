"""The number component (tft/component_types/number.py): its memory, the
variants of its sta and style, what the number's list matched, and its
attributes in code.

Each test gives the function it checks a probe's page, made in memory from
the probe's components, in a Project of the facts it reads
(tests/tft/unit_inputs.py): tools/tft/probing/number_probes.py and
tools/tft/probing/number_border_and_picture_probes.py. The probes' fixtures,
and a number in a second font, which a page in memory cannot hold, are
compared on whole builds in tests/tft/test_whole_files.py.
"""
from dataclasses import replace
import unittest

from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import number_border_and_picture_probes, number_probes, p_probes
from nxwright.tft.component_types import entry_operand, number
from nxwright.tft.matching import Need, unmatched
from nxwright.tft.statements import CodePlace, StatementError, encode_line
from tests.tft.p_components import PTypePieces
from tests.tft.t_components import CodePieces, TypePieces
from tests.tft.unit_inputs import place, probe_facts


_PROBES = number_probes.PROBES + number_border_and_picture_probes.PROBES


def value(number_: int, size: int = 2) -> bytes:
    return number_.to_bytes(size, "little", signed=True)


class MemoryTest(unittest.TestCase):
    """A number's starting memory gives its val, 4 bytes, signed."""

    def test_its_val(self):
        class Number:
            # Its val, and its other attributes at a number's defaults.
            DEFAULTS = {"sta": b"\x01", "style": b"\x00", "font": b"\x00",
                        "bco": b"\xff\xff", "pco": b"\x00\x00",
                        "xcen": b"\x01", "ycen": b"\x01", "lenth": b"\x00", "format": b"\x00",
                        "isbr": b"\x01", "spax": b"\x00", "spay": b"\x00"}

            def __init__(self, val: int):
                self.val = val

            def attribute(self, name: str) -> bytes:
                return value(self.val, 4) if name == "val" else self.DEFAULTS[name]
        for val in (0, 123, -5, -2 ** 31, 2 ** 31 - 1):
            with self.subTest(val=val):
                page_object = Number(val)
                memory = number.variant(page_object).memory(page_object, None)
                self.assertEqual(len(memory), 24)
                self.assertEqual(int.from_bytes(memory[12:16], "little", signed=True), val)


def facts(name: str):
    """Returns a Project of facts of the pages of the probe `name`
    (unit_inputs.probe_facts)."""
    return probe_facts(next(probe for probe in _PROBES if probe.name == name))


def memory(page_object, project) -> bytes:
    return number.variant(page_object).memory(page_object, project)


class ValuesTest(unittest.TestCase):
    """A number's attributes that its memory alone gives, as the Nextion
    Editor wrote them."""

    def objects(self, name: str) -> tuple:
        project = facts(name)
        return project, project.pages[0].objects[1:]

    def test_its_looks(self):
        # Its sta and style, 3 zeros, its font, bco, pco, xcen, and ycen; its
        # val, 123; its lenth and format, 2 zeros; then its isbr, spax, and
        # spay, and a zero.
        project, numbers = self.objects("number-of-other-looks")
        for page_object, values in zip(numbers, (
                "01 00 00 00 00 00 00 00 00 f8 00 02 7b 00 00 00 00 00 00 00 00 05 07 00",
                "01 00 00 00 00 00 ff ff 00 00 02 00 7b 00 00 00 00 00 00 00 01 ff ff 00",
                "01 00 00 00 00 00 01 00 ff ff 01 01 7b 00 00 00 00 00 00 00 01 00 00 00")):
            with self.subTest(page_object.attribute("objname")):
                self.assertEqual(memory(page_object, project), bytes.fromhex(values))

    def test_its_lenth_and_format(self):
        project, numbers = self.objects("number-of-lenths-and-formats")
        self.assertEqual([memory(page_object, project)[16:18] for page_object in numbers],
                         [b"\x03\x01", b"\x0f\x02", b"\x01\x00"])



class VariantTest(unittest.TestCase):
    """A number of each style, and with a picture or a crop behind it, as
    the Nextion Editor wrote them, each at its place in its probe, as the
    probe's table gives it (unit_inputs.place)."""

    PROBES = {"styles": "number-of-each-style", "pictures": "number-of-a-picture-and-a-crop"}

    @classmethod
    def setUpClass(cls):
        for name, probe_name in cls.PROBES.items():
            setattr(cls, name, facts(probe_name))

    def place(self, project, page_object):
        probe_name = next(self.PROBES[name] for name in self.PROBES
                          if getattr(self, name) is project)
        return place(next(probe for probe in _PROBES if probe.name == probe_name),
                     "page0-%d" % project.pages[0].objects.index(page_object))

    def drawing(self, project, page_object) -> list:
        return number.variant(page_object).drawing(page_object, project,
                                                   self.place(project, page_object))

    def test_its_entries_and_slots(self):
        # A style of 1 gives its borderc and borderw entries 22 and 23, so
        # its font is 24 and its val 29, two on; 43 entries. A picture or a
        # crop behind it gives its style none, so its font is 21, its pic or
        # picc 22, and its val 26, one back; 40 entries.
        bordered, sunken = (number.variant(page_object)
                            for page_object in self.styles.pages[0].objects[1:3])
        picture, crop = (number.variant(page_object)
                         for page_object in self.pictures.pages[0].objects[1:3])
        self.assertEqual([one.ENTRIES for one in (bordered, sunken, picture, crop)],
                         [43, 41, 40, 40])
        self.assertEqual([bordered.attribute_place(name) for name in
                          ("style", "borderc", "borderw", "font", "bco", "val", "isbr", "spax")],
                         [20, 22, 23, 24, 25, 29, 32, 33])
        self.assertEqual([picture.attribute_place(name) for name in ("font", "pic", "val")],
                         [21, 22, 26])
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
        # the command that draws its val: its borderc's entry, 22, twice and
        # its borderw's, 23, at 1; 3D, dark then light at 2, and light then
        # dark at 3; none at 0.
        drawings = [self.drawing(self.styles, page_object)
                    for page_object in self.styles.pages[0].objects[1:5]]
        self.assertEqual([drawing[0][-4:] for drawing in drawings],
                         [b",0,3", b",0,1", b",0,1", b",0,0"])
        self.assertEqual(drawings[0][2], b"\x09\x07\x0810,10,100,30," + entry_operand(55)
                         + b"," + entry_operand(55) + b"," + entry_operand(56))
        self.assertEqual(drawings[1][2], b"\x09\x07\x0810,60,100,30,"
                         b"\x03\x28\x42\x00\x00,\x03\x1c\xe7\x00\x00,1")
        self.assertEqual(drawings[2][2], b"\x09\x07\x0810,110,100,30,"
                         b"\x03\x1c\xe7\x00\x00,\x03\x28\x42\x00\x00,1")
        self.assertEqual(len(drawings[3]), 2)

    def test_its_memory_with_a_border_behind_a_picture_or_a_crop(self):
        # A style of 1 behind a picture or a crop: its style 0, as it draws
        # no border there, but its borderc and borderw all the same, 63488
        # and 3, then 31 and 7, and the picture's ID where its bco lies.
        made = facts("number-of-a-border-behind-a-picture-and-a-crop")
        for page_object, start in zip(made.pages[0].objects[1:3],
                                      ("02 00 00 f8 03 00 01 00", "00 00 1f 00 07 00 00 00")):
            with self.subTest(start):
                self.assertEqual(memory(page_object, made)[:8], bytes.fromhex(start))

    def test_its_memory(self):
        # Its sta and style, then its borderc, 63488, and borderw, 3, at a
        # style of 1, and zeros there at another, though the page files of
        # the other three give them. Behind a picture or a crop, its style
        # is 0, though the last two give 3 and 2, and the picture's ID lies
        # where its bco lies: picture 1, 0, 0, then 1.
        for project, values in ((self.styles, ("01 01 00 f8 03 00 ff ff",
                                               "01 02 00 00 00 00 ff ff",
                                               "01 03 00 00 00 00 ff ff",
                                               "01 00 00 00 00 00 ff ff")),
                                (self.pictures, ("02 00 00 00 00 00 01 00",
                                                 "00 00 00 00 00 00 00 00",
                                                 "02 00 00 00 00 00 00 00",
                                                 "00 00 00 00 00 00 01 00"))):
            for page_object, start in zip(project.pages[0].objects[1:5], values):
                with self.subTest(start):
                    self.assertEqual(memory(page_object, project)[:8], bytes.fromhex(start))

    def test_its_sta_in_its_setbrush(self):
        # Its setbrush gives its sta after its ycen's entry, 25 behind a
        # picture, where a colour gives 1.
        picture, crop = self.pictures.pages[0].objects[1:3]
        for page_object, sta in ((picture, b",2,"), (crop, b",0,")):
            first_entry = self.place(self.pictures, page_object).first_entry
            self.assertIn(entry_operand(first_entry + 25) + sta,
                          self.drawing(self.pictures, page_object)[0])


class PiecesTest(TypePieces, CodePieces, unittest.TestCase):
    """Each number of each probe that keeps its whole user code, at its type's
    functions, and each probe of code, at the statement encoder, against the
    probe's pieces (tests/tft/t_components.py)."""

    TYPE = "number"
    PROBES = _PROBES
    COUNT = 15
    CODE_COUNT = 1


class PPiecesTest(PTypePieces, CodePieces, unittest.TestCase):
    """Each number of each of its probes on P that keeps its whole user code, at
    its type's functions on P, against the probe's pieces
    (tests/tft/p_components.py)."""

    TYPE = "number"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-number-")]
    COUNT = 16
    CODE_COUNT = 1

class MatchedTest(unittest.TestCase):
    """The needs number.MATCHED covers (matching.py)."""

    def need(self, attribute: str, raw: bytes, **context) -> Need:
        attributes = {"x": value(10), "y": value(10), "w": value(100), "h": value(30)}
        attributes.update({name: value(number_) for name, number_ in context.items()})
        return Need("attribute", "number." + attribute, raw, context=attributes)

    def test_what_it_covers(self):
        covered = [Need("type", "number"), Need("attribute", "number.objname", b"n0"),
                   self.need("x", value(220), x=220, y=450),
                   self.need("w", value(2), x=0, y=0, w=2, h=2),
                   self.need("val", value(-2 ** 31, 4)), self.need("val", value(2 ** 31 - 1, 4)),
                   self.need("font", b"\x01")]
        # The values its memory alone gives, at their ends.
        for name, ends in (("bco", (0, 0xFFFF)), ("pco", (0, 0xFFFF)), ("xcen", (0, 2)),
                           ("ycen", (0, 2)), ("isbr", (0, 1)), ("spax", (0, 255)),
                           ("spay", (0, 255)), ("lenth", (0, 15)), ("format", (0, 2))):
            covered += [self.need(name, end.to_bytes(2, "little")) for end in ends]
        # What lies behind it, its border, and its pictures, on T and K: each
        # style at each sta.
        looks = [self.need("sta", value(sta)) for sta in (0, 2)]
        looks += [self.need("style", value(style)) for style in (1, 2, 3)]
        looks += [self.need("style", value(style), sta=sta) for sta in (0, 2)
                  for style in (0, 1, 2, 3)]
        looks += [self.need(name, end.to_bytes(2, "little")) for name, ends in (
            ("borderc", (0, 0xFFFF)), ("borderw", (0, 255)), ("pic", (0, 0xFFFF)),
            ("picc", (0, 0xFFFF))) for end in ends]
        covered += looks + [replace(need, series="K") for need in looks]
        # On P and E, a sta of 3 too, nothing behind it, at any style.
        covered += [replace(self.need("sta", value(3)), series=series) for series in "PE"]
        covered += [replace(self.need("style", value(style), sta=3), series="P")
                    for style in (0, 1, 2, 3)]
        self.assertEqual(unmatched(covered, number.MATCHED), [])

    def test_what_it_leaves_out(self):
        left = [self.need("y", value(-1), y=-1),
                self.need("spax", value(256)), self.need("spay", value(256))]
        # Past what the probes showed: a style past 3, on T and on P; a sta
        # past 2 on T, and past 3 on P; and a keyboard, which no case tried.
        past = [self.need("style", value(4)), self.need("borderw", value(256))]
        left += past + [replace(need, series="P") for need in past]
        left += [self.need("sta", value(3)), replace(self.need("sta", value(4)), series="P")]
        left.append(self.need("key", value(1)))
        self.assertEqual(unmatched(left, number.MATCHED), left)


class CodeTest(unittest.TestCase):
    """Code may refer to a number's val (tools/tft/probing/attribute_probes.py), and to any
    other attribute it writes (tools/tft/probing/other_attribute_probes.py)."""

    def test_its_attributes(self):
        project = facts("number-one")
        # n0's entries follow the page's 33; val is its 28th, and bco its
        # 24th. A number writes no pw.
        self.assertEqual(encode_line("n0.val=5", CodePlace(0, "n0", "up"), CompileContext(project)),
                         b"\x01" + (33 + 27).to_bytes(4, "little") + b"=5")
        self.assertEqual(encode_line("n0.bco=5", CodePlace(0, "n0", "up"), CompileContext(project)),
                         b"\x01" + (33 + 23).to_bytes(4, "little") + b"=5")
        with self.assertRaisesRegex(StatementError, "n0's pw is not encoded"):
            encode_line("n0.pw=5", CodePlace(0, "n0", "up"), CompileContext(project))


if __name__ == "__main__":
    unittest.main()
