"""The rooms of P's types (tools/tft/probing/room_probes.py): each room takes from 0 to
the most the Nextion Editor takes, on P and on E, and one more is
refused, except a select's txt_maxl, which takes any value that fits.

The match check over each probe reads the probe's pages made in memory
(tests/tft/unit_inputs.py), as a compile reads its project."""
import unittest

from tools.tft.probing import room_probes
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tests.tft.unit_inputs import probe_project


class MatchedTest(unittest.TestCase):

    def test_each_probe_s_project(self):
        # Every need of each probe's pages is matched, as a compile checks
        # them: its rooms at their most, and filled to 1000.
        rules = matched_rules()
        for probe in room_probes.PROBES:
            with self.subTest(probe.name):
                self.assertEqual(unmatched(project_needs(probe_project(probe)), rules), [])


class RoomTest(unittest.TestCase):

    def test_each_room_to_the_most_the_nextion_editor_takes(self):
        rules = matched_rules()
        for type_name, rooms in room_probes.ROOMS.items():
            for room, _, most in rooms:
                for series in ("P", "E"):
                    with self.subTest(type=type_name, room=room, series=series):
                        def need(value: int) -> Need:
                            return Need("attribute", "%s.%s" % (type_name, room),
                                        value.to_bytes(2, "little"), series=series)
                        self.assertEqual(unmatched([need(0), need(most)], rules), [])
                        if (type_name, room) == ("select", "txt_maxl"):
                            # A txt_maxl fits in its 2 bytes up to 65535, so
                            # one more is taken.
                            self.assertEqual(unmatched([need(most + 1)], rules), [])
                        else:
                            self.assertEqual(unmatched([need(most + 1)], rules),
                                             [need(most + 1)])

    def test_the_most_of_each(self):
        # 65534 but a select's path_m, 8192.
        mosts = {(type_name, room): most for type_name, rooms in room_probes.ROOMS.items()
                 for room, _, most in rooms}
        self.assertEqual({key: most for key, most in mosts.items() if most != 0xFFFE},
                         {("select", "path_m"): 8192})


if __name__ == "__main__":
    unittest.main()
