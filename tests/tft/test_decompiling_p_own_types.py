"""The decoders of six of the types P has and T has not
(tft/decompiling/component_types/): the select, the combo box, the
sliding text, the file browser, the data record, and the switch.

Each component of each probe of P that keeps its whole user code is read
back, rebuilt from what its decoder gives, and compiled again
(unit_inputs.rebuilt_user_code): the two user codes are the same when the
decoder keeps everything the file keeps of it. The values the probes leave
at their defaults are checked on components compiled in memory.
"""
import unittest

from nxwright.tft import frame
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import decoded_user_code
from nxwright.tft.decompiling.objects import decoded_values
from tools.tft.probing import sliding_text_probes
from tools.tft.probing.combo_box_probes import combo_box_component
from tools.tft.probing.data_record_probes import data_record_component
from tools.tft.probing.file_browser_probes import file_browser_component
from tools.tft.probing.select_probes import select_component
from tools.tft.probing.sliding_text_probes import sliding_text_component
from tools.tft.probing.switch_probes import switch_component
from tests.tft.t_components import made_in_memory
from tests.tft.test_decoded_file import _probes_keeping_their_user_code
from tests.tft.unit_inputs import page, probe_facts, project_of, rebuilt_user_code

_TYPES = ("select", "combo-box", "sliding-text", "file-browser", "data-record", "switch")


def _values_of(decoded_object, decoded_page, decoded_file):
    """Returns the attributes the decoder of `decoded_object`'s type gives,
    for one of _TYPES, or None to keep any other object as it is."""
    if decoded_object.type_name not in _TYPES:
        return None
    return decoded_values(decoded_object, decoded_page, decoded_file).attributes


def _decoded(*components: str):
    """Returns (the decoded page0, the decoded file) of a project of P whose
    page0 has `components`, as the frame writes it."""
    project = project_of(page(*components, series="P"), series="P")
    settings = project.settings
    decoded = decoded_user_code(frame.user_code(project), "P", settings.model.name,
                                settings.rotation, settings.encoding)
    return decoded.pages[0], decoded


class ProbesTest(unittest.TestCase):

    def test_each_component_rebuilt(self):
        rebuilt = 0
        for probe in _probes_keeping_their_user_code(series=("P",)):
            if not made_in_memory(probe):
                continue
            with self.subTest(probe.name):
                code, again, count = rebuilt_user_code(probe_facts(probe), _values_of)
                self.assertEqual(again, code)
            rebuilt += count
        # 16 selects, 24 combo boxes, 25 sliding texts, 19 file browsers,
        # 19 data records, and 10 switches.
        self.assertEqual(rebuilt, 113)


class InMemoryTest(unittest.TestCase):
    """Values the probes leave at their defaults, each compiled in memory,
    read back, and rebuilt."""

    def assert_read(self, component: str, **expected):
        project = project_of(page(component, series="P"), series="P")
        code, again, count = rebuilt_user_code(project, _values_of)
        self.assertEqual((again, count), (code, 1))
        decoded_page, decoded = _decoded(component)
        attributes = decoded_values(decoded_page.objects[1], decoded_page, decoded).attributes
        self.assertEqual({name: attributes.get(name) for name in expected}, expected)

    def test_bytes_no_entry_gives(self):
        # Each is a byte of the memory alone (component_types' P_UNENTERED).
        self.assert_read(combo_box_component(drastate=1), drastate=1)
        self.assert_read(sliding_text_component(leftshow=1), leftshow=1)
        self.assert_read(file_browser_component(autoleft=1), autoleft=1)
        self.assert_read(data_record_component(init=1, autoleft=1), init=1, autoleft=1)

    def test_a_path_whose_room_is_the_txt_s(self):
        # At a path_m of 0, its default, a sliding text's path has its
        # txt_maxl's room, though its entry's code gives a room of 1.
        self.assert_read(sliding_text_component(path="first\r\nsecond"),
                         path=b"first\r\nsecond", path_m=0)
        self.assert_read(sliding_text_component(path="first", path_m=8), path=b"first", path_m=8)

    def test_a_style_of_1_behind_a_picture(self):
        # Behind anything but a colour, a style has no entry, but a style of
        # 1 adds its border's, which show it.
        self.assert_read(select_component(style=1, sta=2, borderc=1234, borderw=3),
                         style=1, borderc=1234, borderw=3)
        self.assert_read(select_component(sta=2), style=None, borderc=None)

    def test_a_sliding_text_s_key(self):
        # A key that opens nxwright's keypad adds the three lines that open
        # it at the end of the Touch Release event (component_types.key_lines).
        probe = next(probe for probe in sliding_text_probes.PROBES
                     if probe.name == "sliding-text-on-the-keypad")
        project = probe_facts(probe)
        code, again, count = rebuilt_user_code(project, _values_of)
        self.assertEqual((again, count), (code, 1))
        settings = project.settings
        decoded = decoded_user_code(code, "P", settings.model.name, settings.rotation,
                                    settings.encoding)
        found = [decoded_values(each, decoded_page, decoded) for decoded_page in decoded.pages
                 for each in decoded_page.objects if each.type_name == "sliding-text"]
        self.assertEqual([(each.attributes["key"], each.added["up"]) for each in found],
                         [(2, (0, 3))])

    def test_a_switch(self):
        self.assert_read(switch_component(txt="Off/On", val=1, dis=40), txt=b"Off/On", val=1,
                         dis=40)

    def test_the_init_block_each_adds(self):
        for component in (select_component(), combo_box_component(), sliding_text_component(),
                          file_browser_component(), data_record_component()):
            decoded_page, decoded = _decoded(component)
            with self.subTest(component.split("\n")[3]):
                each = decoded_page.objects[1]
                self.assertEqual(decoded_values(each, decoded_page, decoded).added,
                                 {"load": (1, 0)})
                decoded_page.load_section.blocks = []
                self.assertRaises(DecodeError, decoded_values, each, decoded_page, decoded)
        decoded_page, decoded = _decoded(switch_component())
        self.assertEqual(decoded_values(decoded_page.objects[1], decoded_page, decoded).added, {})


if __name__ == "__main__":
    unittest.main()
