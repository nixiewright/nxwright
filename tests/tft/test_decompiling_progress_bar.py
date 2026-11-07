"""The progress bar's decoder
(tft/decompiling/component_types/progress_bar.py): each progress bar of
each probe of T, K, and F that keeps its whole user code, decoded from that
user code (decoded_file.decoded_user_code), against the probe's own
progress bar. A progress bar's effect is kept only as whether it has one,
and its dis only when it is drawn in colours.
"""
import unittest

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft import frame
from nxwright.tft.component_types import has_effect
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import decoded_user_code
from nxwright.tft.decompiling.objects import decoded_values
from tools.tft.probing.progress_bar_probes import progress_bar_component
from tests.tft.t_components import made_in_memory
from tests.tft.test_decoded_file import _probes_keeping_their_user_code
from tests.tft.unit_inputs import page, probe_facts, project_of, user_code_of

# The attributes the progress bar's decoder gives that its record keeps as
# the Nextion Editor's defaults when the progress bar has none: its aph and
# its sendkey.
_RECORD_DEFAULTS = {"aph": 127, "sendkey": 0}
# The attributes the file always keeps of a progress bar, but its effect,
# and those of its parts, by its sta: its dis, bco, and pco in colours, or
# its bpic and ppic in pictures.
_ALWAYS = ("vscope", "x", "y", "w", "h", "aph", "sendkey", "sta", "dez", "val")
_PARTS = {0: ("dis", "bco", "pco"), 1: ("bpic", "ppic")}


def _decoded(project):
    """Returns the decoded file of the user code the compile writes for
    `project`, on T."""
    return decoded_user_code(frame.user_code(project), "T", "NX4832T035", 0, "iso-8859-1")


class ProgressBarTest(unittest.TestCase):

    def test_each_progress_bar(self):
        bars = effects = in_pictures = 0
        for probe in _probes_keeping_their_user_code():
            if not made_in_memory(probe):
                continue
            project = probe_facts(probe)
            decoded = decoded_user_code(user_code_of(probe), probe.base, "NX4832T035", 0,
                                        "iso-8859-1")
            for decoded_page, made in zip(decoded.pages, project.pages):
                for each, page_object in zip(decoded_page.objects[1:], made.objects[1:]):
                    if each.type_name != "progress-bar":
                        continue
                    attributes = dict(decoded_values(each, decoded_page, decoded).attributes)
                    with self.subTest(probe.name, page=decoded_page.page_id,
                                      object_id=each.object_id):
                        # The file keeps only whether it has an effect.
                        self.assertEqual(bool(attributes.pop("effect")), has_effect(page_object))
                        self.assertEqual(sorted(attributes),
                                         sorted(_ALWAYS + _PARTS[attributes["sta"]]))
                        self.assertEqual(attributes, {
                            name: (_RECORD_DEFAULTS[name] if page_object.attribute(name) is None
                                   else number_from_bytes(page_object.attribute(name)))
                            for name in attributes})
                    bars += 1
                    effects += has_effect(page_object)
                    in_pictures += attributes["sta"] == 1
        # 21 progress bars, of which 1 has an effect and 2 are drawn in pictures.
        self.assertEqual((bars, effects, in_pictures), (21, 1, 2))

    def test_in_pictures_and_with_an_effect(self):
        # The compile writes a progress bar in pictures, with a bpic of 0 and
        # a ppic of 1, upward, at a val of 70, with an effect of 3 and
        # without one. It keeps no dis.
        for effect in (0, 3):
            project = project_of(page(progress_bar_component(
                val=70, sta=1, dez=1, effect=effect, pictures={"bpic": "p0", "ppic": "p1"}),
                pictures=("p0", "p1")), pictures=2)
            decoded = _decoded(project)
            attributes = decoded_values(decoded.pages[0].objects[1], decoded.pages[0],
                                        decoded).attributes
            with self.subTest(effect=effect):
                self.assertEqual({name: attributes[name] for name in
                                  ("sta", "dez", "val", "bpic", "ppic")},
                                 {"sta": 1, "dez": 1, "val": 70, "bpic": 0, "ppic": 1})
                self.assertNotIn("dis", attributes)
                self.assertNotIn("bco", attributes)
                self.assertEqual(attributes["effect"] != 0, effect != 0)

    def test_entries_of_no_variant(self):
        decoded = _decoded(project_of(page(progress_bar_component())))
        bar = decoded.pages[0].objects[1]
        bar.entries = bar.entries[:-1]
        self.assertRaises(DecodeError, decoded_values, bar, decoded.pages[0], decoded)


if __name__ == "__main__":
    unittest.main()
