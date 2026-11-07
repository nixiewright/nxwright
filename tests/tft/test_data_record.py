"""The data record (tft/component_types/data_record.py), a type P and E
have and T and K have not: its memory in the int area, its texts' rooms,
its entries by its style, its calls in code, and what its rules cover.

Each test gives the function it checks that function's own input: a page
object of a probe's components, a Project of the facts it reads, and its
place, from the probe's table (tests/tft/unit_inputs.py). A data record on P is
global, so its memory lies in the first block's int area, where its probe's
table gives it pieces of its own, its head and its values, as a local
component's in its page's memory. The tests of its pieces compare each data
record of each probe that keeps fixtures with the probe's pieces
(tests/tft/p_components.py). Its sample of whole files is in
tests/tft/test_whole_files.py.
"""
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft import component_types
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing import data_record_probes, p_probes
from tools.tft.probing.text_probes import text_component
from nxwright.tft.statements import CodePlace, encode_line
from tests.tft.p_components import PTypePieces, p_entries, p_memory, p_probe
from tests.tft.t_components import LoadSectionPieces
from tests.tft.unit_inputs import page, place, project_of

_ENTRY = struct.Struct("<IiiiII")
# A place for a data record of no probe: that of the data record at its
# defaults, from its probe's table.
_PLACE = place(p_probe("p-data-record-at-its-defaults"), "page0-1")


def _data_record(**attributes):
    """Returns the page object of a data record of `attributes` on P."""
    return page(data_record_probes.data_record_component(**attributes), series="P").objects[1]


def _project(series: str = "P", code: str = ""):
    """Returns a Project of the facts of a page on `series` of a text and a
    data record, with the event code `code`, without resources, as the
    match check takes it."""
    return project_of(page(text_component(), data_record_probes.data_record_component(),
                           series=series, code=code), series=series, fonts=0)


class PieceTest(PTypePieces, LoadSectionPieces, unittest.TestCase):
    """Each data record's values in its memory after its head, its entries,
    and its blocks in its page's load section, in each P probe of a data
    record that keeps its user code: one at its defaults, one on each of two
    pages, both global, its memory in the int area, and one of a format of
    two column widths, "100^100", whose text lies among the global texts
    (tests/tft/test_frame.py).

    Its memory, at places counted from its start: its init at 67, its
    autoleft at 110, the places of its texts, and its buffer's size and
    place at 180. In its page's load section, a data record adds `init`
    with its ID."""

    TYPE = "data-record"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-data-record-")]
    COUNT = 17


class MemoryTest(unittest.TestCase):

    def test_its_values_without_entries(self):
        # Its init at 67 and its autoleft at 110; its buffer's size, 10752,
        # at 180, and where its buffer lies, after its texts, at 184.
        memory = p_memory(_data_record(path="sd0/x.data", init=1, autoleft=1), _PLACE)
        self.assertEqual((memory[67], memory[110]), (1, 1))
        size, buffer_place = struct.unpack_from("<2I", memory, 180)
        self.assertEqual(size, 10752)
        self.assertEqual(buffer_place, _PLACE.buffer_place)

    def test_its_texts_rooms(self):
        # Its path, format, dir, filter, and txt, in that order, each in a
        # room of its room attribute + 1 bytes, rounded up to 4.
        record = _data_record()
        module = component_types.object_module(record)
        rooms = [len(component_types.p_text(module, record, attribute, attribute + "_m"))
                 for attribute in ("path", "format", "dir", "filter")]
        self.assertEqual(rooms, [256, 260, 256, 32])

    def test_column_widths_separated_by_carets(self):
        # Its format's room holds its widths as written. E writes its texts
        # as P does, and comes with the tests of E.
        record = _data_record(format="100^100", format_m=7)
        module = component_types.object_module(record)
        self.assertTrue(component_types.p_text(module, record, "format", "format_m")
                        .startswith(b"100^100\x00"))


class EntriesTest(unittest.TestCase):

    def test_by_its_style(self):
        # 74 entries, 76 with a border of one colour, whose borderc's and
        # borderw's entries follow its style's; its vscope's lowest is 1.
        def entries(**attributes):
            data = p_entries(_data_record(path="sd0/x.data", **attributes), _PLACE)
            return [_ENTRY.unpack_from(data, entry * _ENTRY.size)
                    for entry in range(len(data) // _ENTRY.size)]
        plain, bordered = entries(), entries(style=1, borderc=1111, borderw=3)
        self.assertEqual((len(plain), len(bordered)), (74, 76))
        self.assertEqual(plain[3][3], 1)
        self.assertEqual(bordered[21][1] - bordered[21][0], 58)
        self.assertEqual(bordered[23][1] - bordered[23][0], 61)
        self.assertEqual([entry[4] >> 24 for entry in plain[55:59]], [0x9C, 0x9D, 0x9E, 0x9F])


class CodeTest(unittest.TestCase):

    def test_its_calls(self):
        # After the page's 33 entries and the text's 41: delete is its 57th,
        # its arguments as a command's.
        place_in_code = CodePlace(0, "page0", "up")
        self.assertEqual(encode_line("data0.delete(0,1)", place_in_code,
                                     CompileContext(_project())),
                         b"\x01" + (33 + 41 + 56).to_bytes(4, "little") + b"(0,1)")


class RuleTest(unittest.TestCase):

    def test_its_mode(self):
        # 0, its file read only if it exists, and 1, its default, created if
        # not, on P and E, and any other value, written as it is.
        rules = matched_rules()
        for series in ("P", "E"):
            for mode, taken in ((0, True), (1, True), (2, True)):
                with self.subTest(series, mode=mode):
                    need = Need("attribute", "data-record.mode", bytes([mode]), series=series)
                    self.assertEqual(unmatched([need], rules), [] if taken else [need])

    def test_column_widths_exceeding_format_room_are_refused(self):
        rules = matched_rules()
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("attribute", "data-record.format", b"100^100", series=series,
                            context={"format_m": (6).to_bytes(2, "little")})
                self.assertEqual(unmatched([need], rules), [need])

    def test_the_attributes_every_component_has(self):
        # On P and E, as for the other types P has and T has not.
        rules = matched_rules()
        for name, value in (("aph", 50), ("effect", 2), ("drag", 1)):
            for series in ("P", "E"):
                with self.subTest(name, series=series):
                    need = Need("attribute", "data-record." + name, value.to_bytes(4, "little"),
                                series=series)
                    self.assertEqual(unmatched([need], rules), [])

    def test_on_p_and_e_alone(self):
        rules = matched_rules()
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("type", "data-record", series=series)
                self.assertEqual(unmatched([need], rules), [])
        for series in ("T", "K"):
            with self.subTest(series):
                need = Need("type", "data-record", series=series)
                self.assertEqual(unmatched([need], rules), [need])

    def test_its_values(self):
        # Its dir's headings lie between "^".
        rules = matched_rules()

        def need(name: str, value, **context) -> Need:
            value = value if isinstance(value, bytes) else value.to_bytes(4, "little")
            return Need("attribute", "data-record." + name, value, series="P", context=context)
        for covered in (need("style", 1), need("lenth", 30), need("lenth", 1),
                        need("dir", b"h0^h1", dir_m=(40).to_bytes(2, "little")),
                        need("dir", b"h0 h1", dir_m=(40).to_bytes(2, "little"))):
            with self.subTest(covered.subject):
                self.assertEqual(unmatched([covered], rules), [])
        for refused in (need("dir", b"h0^h1", dir_m=(4).to_bytes(2, "little")),):
            with self.subTest(refused.subject):
                self.assertEqual(unmatched([refused], rules), [refused])

    def test_its_values_at_their_entries_limits(self):
        rules = matched_rules()
        for name in ("val", "qty", "maxval_y", "val_y", "maxval_x", "val_x"):
            for value in (-2 ** 31, 2 ** 31 - 1):
                with self.subTest(name, value=value):
                    need = Need("attribute", "data-record." + name,
                                value.to_bytes(4, "little", signed=True), series="P")
                    self.assertEqual(unmatched([need], rules), [])

    def test_its_calls(self):
        # Its calls on P and E, a record as a text, a txt, or a number; not
        # delete of one number, nor its txt set.
        rules = matched_rules()
        context = next(need.context for need in project_needs(_project(
            code="on page0.up:\n  sys0=1\n")) if need.kind == "code" and need.subject == "event")
        for line in ('data0.insert("a^b^c")', "data0.insert(t0.txt)", "data0.delete(sys0,1)",
                     'data0.up("x^y",0)', "data0.clear()", "data0.insert(5)",
                     "data0.up(t0.txt,0)", "data0.up(5,0)"):
            for series in ("P", "E"):
                with self.subTest(line, series=series):
                    need = Need("code", "event", line, context=context, series=series)
                    self.assertEqual(unmatched([need], rules), [])
        for line in ("data0.delete(0)", "data0.insert=1"):
            with self.subTest(line):
                need = Need("code", "event", line, context=context, series="P")
                self.assertEqual(unmatched([need], rules), [need])


if __name__ == "__main__":
    unittest.main()
