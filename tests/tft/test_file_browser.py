"""The file browser (tft/component_types/file_browser.py), a type P and E
have and T and K have not: its memory and buffer on P, its entries by its
psta and its style, its up's call, and what its rules cover.

Each test gives the function it checks that function's own input: a page
object of a probe's components, a Project of the facts it reads, and its
place, from the probe's table (tests/tft/unit_inputs.py). On P, a file
browser's memory starts with its record's head, which the frame writes, so
the tests of its pieces compare the values its type writes after the head
(tests/tft/p_components.py), each file browser of each probe that keeps
fixtures. Its sample of whole files is in tests/tft/test_whole_files.py.
"""
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft import component_types
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing import file_browser_probes, p_probes
from tools.tft.probing.text_probes import text_component
from nxwright.tft.statements import CodePlace, encode_line
from tests.tft.p_components import PTypePieces, p_entries, p_memory, p_probe
from tests.tft.t_components import LoadSectionPieces
from tests.tft.unit_inputs import page, place, project_of

_ENTRY = struct.Struct("<IiiiII")
# A place for a file browser of no probe: that of the file browser at its
# defaults, from its probe's table.
_PLACE = place(p_probe("p-file-browser-at-its-defaults"), "page0-1")


def _file_browser(**attributes):
    """Returns the page object of a file browser of `attributes` on P."""
    return page(file_browser_probes.file_browser_component(**attributes),
                series="P").objects[1]


def _entries(**attributes) -> list:
    """Returns the file browser's entries, at _PLACE."""
    data = p_entries(_file_browser(**attributes), _PLACE)
    return [_ENTRY.unpack_from(data, entry * _ENTRY.size)
            for entry in range(len(data) // _ENTRY.size)]


class PieceTest(PTypePieces, LoadSectionPieces, unittest.TestCase):
    """Each file browser's values in its memory after its head, its entries,
    and its blocks in its page's load section, in each P probe of a file
    browser that keeps its user code: one at its defaults, two beside a
    text, and one of no buffer, its buffsize 0, beside a text.

    Its memory, at places counted from its start: its autoleft at 71, the
    places of its texts, its buffsize at 128, and where its buffer lies. In
    its page's load section, a file browser adds `init` with its ID."""

    TYPE = "file-browser"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-file-browser-")]
    COUNT = 16


class MemoryTest(unittest.TestCase):

    def test_its_buffer_and_autoleft(self):
        # Its autoleft at 71; its buffsize at 128, and where its buffer lies,
        # its place's, after its texts; its buffer's size, rounded up to 4.
        browser = _file_browser(autoleft=1, buffsize=1001)
        memory = p_memory(browser, _PLACE)
        self.assertEqual(memory[71], 1)
        self.assertEqual(struct.unpack_from("<2I", memory, 128), (1001, _PLACE.buffer_place))
        module = component_types.object_module(browser)
        self.assertEqual(module.buffer_size(browser, project_of(series="P")), 1004)

    def test_no_buffer_at_a_buffsize_of_0(self):
        # Its buffsize, 0, and where its buffer lies, 0, as it has none, as
        # the Nextion Editor wrote them (file-browser-of-no-buffer); no
        # buffer at the end of its page's memory.
        browser = _file_browser(buffsize=0)
        self.assertEqual(struct.unpack_from("<2I", p_memory(browser, _PLACE), 128), (0, 0))
        module = component_types.object_module(browser)
        self.assertEqual(module.buffer_size(browser, project_of(series="P")), 0)


class EntriesTest(unittest.TestCase):

    def test_by_its_psta_and_style(self):
        # 60 entries; one less without folders listed, its pic1 gone; two
        # more with a border of one colour, after its style's.
        self.assertEqual(len(_entries()), 60)
        without_folders = _entries(psta=0)
        self.assertEqual(len(without_folders), 59)
        self.assertEqual(without_folders[44][1] - without_folders[44][0], 120)
        bordered = _entries(style=1, borderc=1111, borderw=3)
        self.assertEqual(len(bordered), 62)
        self.assertEqual(bordered[21][1] - bordered[21][0], 58)

    def test_its_icons_highest(self):
        # Its pic1's and pic2's highest is the project's last picture: -1
        # without pictures.
        entries = _entries()
        self.assertEqual((entries[44][2], entries[45][2]), (-1, -1))


class CodeTest(unittest.TestCase):

    def test_its_up(self):
        # up is its entry 50, after the page's 33, then `()`.
        project = project_of(page(file_browser_probes.file_browser_component(), series="P"),
                             series="P")
        self.assertEqual(encode_line("fbrowser0.up()", CodePlace(0, "page0", "up"),
                                     CompileContext(project)),
                         b"\x01" + (33 + 50).to_bytes(4, "little") + b"()")


class RuleTest(unittest.TestCase):

    def test_the_attributes_every_component_has(self):
        # On P and E, as for the other types P has and T has not.
        rules = matched_rules()
        for name, value in (("aph", 50), ("effect", 2), ("drag", 1)):
            for series in ("P", "E"):
                with self.subTest(name, series=series):
                    need = Need("attribute", "file-browser." + name, value.to_bytes(4, "little"),
                                series=series)
                    self.assertEqual(unmatched([need], rules), [])

    def test_its_values_at_their_entries_limits(self):
        # Each takes any value from -2147483648 to 2147483647, its qty too.
        rules = matched_rules()

        def need(name: str, value: int) -> Need:
            return Need("attribute", "file-browser." + name,
                        value.to_bytes(4, "little", signed=True), series="P")
        for name in ("val", "qty", "maxval_y", "val_y"):
            for value in (-2 ** 31, -1, 2 ** 31 - 1):
                with self.subTest(name, value=value):
                    self.assertEqual(unmatched([need(name, value)], rules), [])

    def test_on_p_and_e_alone(self):
        rules = matched_rules()
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("type", "file-browser", series=series)
                self.assertEqual(unmatched([need], rules), [])
        for series in ("T", "K"):
            with self.subTest(series):
                need = Need("type", "file-browser", series=series)
                self.assertEqual(unmatched([need], rules), [need])

    def test_its_texts(self):
        # Of any characters, within their rooms.
        rules = matched_rules()

        def need(name: str, value: bytes, **context) -> Need:
            return Need("attribute", "file-browser." + name, value, series="P",
                        context={key: (room).to_bytes(2, "little")
                                 for key, room in context.items()})
        for covered in (need("filter", b"*.txt|*.data", filter_m=20),
                        need("dir", b"sd0/a/", dir_m=40), need("dir", b"sd0/a b/", dir_m=40)):
            with self.subTest(covered.subject):
                self.assertEqual(unmatched([covered], rules), [])
        for refused in (need("filter", b"*.txt|*.data", filter_m=5),):
            with self.subTest(refused.subject):
                self.assertEqual(unmatched([refused], rules), [refused])

    def test_its_up(self):
        # up() alone, as the probes showed: no argument.
        project = project_of(page(text_component(), file_browser_probes.file_browser_component(),
                                  series="P", code="on page0.up:\n  sys0=1\n"),
                             series="P", fonts=0)
        context = next(need.context for need in project_needs(project)
                       if need.kind == "code" and need.subject == "event")
        rules = matched_rules()
        covered = Need("code", "event", "fbrowser0.up()", context=context, series="P")
        self.assertEqual(unmatched([covered], rules), [])
        for line in ("fbrowser0.up(1)", "fbrowser0.up=1"):
            with self.subTest(line):
                refused = Need("code", "event", line, context=context, series="P")
                self.assertEqual(unmatched([refused], rules), [refused])


if __name__ == "__main__":
    unittest.main()
