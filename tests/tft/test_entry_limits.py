"""The attributes at the limits their entries give (tools/tft/probing/entry_limit_probes.py):
each component of the probes that kept the whole user code once they
matched the Nextion Editor's files, at its type's functions, and the
check's taking every probe's project.

Each test gives the function it checks its own input: a probe's pages made
in memory, in a Project of the facts it reads, and each component's place,
read from the probe's table (tests/tft/unit_inputs.py). A page's own effect lies
in what the frame writes for the page, its record and the head of its
memory, which is compared by the samples of whole files
(tests/tft/test_whole_files.py) until the frame's tests take it.
"""
import unittest

from tools.tft.probing import entry_limit_probes
from nxwright.tft.component_types import object_module
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from nxwright.tft.tft_file import encode_blocks
from tests.tft.p_components import p_entries, p_values
from tests.tft.t_components import t_drawing, t_entries, t_memory
from tests.tft.unit_inputs import piece, piece_names, place, probe_facts, probe_project


def _background_fill(page_object, project, its_place) -> bytes:
    """Returns what the component's type fills its area with, then a 0 word,
    as the piece page0-N-background-fill holds it."""
    return encode_blocks(object_module(page_object).background_fill(page_object, project,
                                                                    its_place) + [b""])


def _load(page_object, project, its_place) -> bytes:
    """Returns the blocks the component's type writes in its page's load
    section, as the piece page0-N-load holds them: none for a type without
    a load_start, as the frame writes none."""
    module = object_module(page_object)
    if not hasattr(module, "load_start"):
        return b""
    return encode_blocks(module.load_start(page_object, project, its_place, {}))


# The pieces of a component on each series, and the type's functions that
# write them, each called with the component, its Project of facts, and its
# place. On P, a component's drawing is its 0 word alone, and its memory's
# head is the frame's.
_FUNCTIONS = {
    "T": (("memory", t_memory), ("drawing", t_drawing), ("entries", t_entries),
          ("background-fill", _background_fill), ("load", _load)),
    "P": (("memory", lambda page_object, project, its_place: p_values(page_object, its_place,
                                                                      project)),
          ("entries", lambda page_object, project, its_place: p_entries(page_object, its_place,
                                                                        project))),
}


class PiecesTest(unittest.TestCase):
    """Each component of each probe that keeps the whole user code, at its
    type's functions, against the probe's pieces: on T, a text of a txt_maxl
    of 0 and of 3000, a scrolling text of vvs past 32767, and a text on each
    of two pages of effects 9 and 10; on P, a text of a txt_maxl of 0, and
    the two pages of effects. Each component's record, its memory's head on
    P, and its page's texts are the frame's, compared by the samples of
    whole files."""

    PROBES = [probe for probe in entry_limit_probes.PROBES if probe.fixtures]

    def test_its_probes(self):
        self.assertEqual(len(self.PROBES), 6)

    def test_each_component(self):
        compared = 0
        for probe in self.PROBES:
            project = probe_facts(probe)
            kept = piece_names(probe)
            for number, made in enumerate(project.pages):
                for object_id, page_object in enumerate(made.objects[1:], 1):
                    name = "page%d-%d" % (number, object_id)
                    its_place = place(probe, name)
                    module = object_module(page_object)
                    for kind, function in _FUNCTIONS[probe.base]:
                        wanted = "%s-%s" % (name, kind)
                        with self.subTest(probe.name, piece=wanted):
                            if kind == "load" and not hasattr(module, "load_start"):
                                # A type without a load_start, as a text,
                                # writes nothing in its page's load section,
                                # so its probe keeps no such piece.
                                self.assertNotIn(wanted, kept)
                                expected = b""
                            else:
                                expected = piece(probe, wanted)
                            self.assertEqual(function(page_object, project, its_place),
                                             expected)
                        compared += 1
        # 5 components on T, 5 kinds each, and 3 on P, 2 each.
        self.assertEqual(compared, 31)


class MatchedTest(unittest.TestCase):

    def test_each_probe_s_project(self):
        rules = matched_rules()
        for probe in entry_limit_probes.PROBES:
            with self.subTest(probe.name):
                self.assertEqual(unmatched(project_needs(probe_project(probe)), rules), [])

    def test_past_the_entries(self):
        # A value one past its entry's highest is taken when it fits in its
        # bytes. Here that is a txt_maxl of 65535, a page's effect of 11, and
        # a component's effect of 9.
        rules = matched_rules()
        taken = [Need("attribute", "text.txt_maxl", b"\xff\xff", context={"txt": b""},
                      series="T"),
                 Need("attribute", "page.effect", b"\x0b", series="P"),
                 Need("attribute", "text.effect", b"\x09", series="P")]
        self.assertEqual(unmatched(taken, rules), [])


if __name__ == "__main__":
    unittest.main()
