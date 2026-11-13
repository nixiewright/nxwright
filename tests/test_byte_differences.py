"""The differences between two sets of named bytes, and the text that gives
where bytes differ (project/byte_differences.py)."""
import unittest

from nxwright.project.byte_differences import (ADDED, CHANGED, REMOVED, Difference,
                                               compare_by_name, differing_ranges,
                                               differing_runs, ranges_text)


class ByteRunsTest(unittest.TestCase):

    def test_neighbouring_bytes_that_differ_make_one_run(self):
        self.assertEqual(differing_runs(b"abcdef", b"aXYdeZ"),
                         ((1, b"bc", b"XY"), (5, b"f", b"Z")))

    def test_a_longer_side_ends_in_a_run_of_its_own(self):
        self.assertEqual(differing_runs(b"abc", b"abcde"), ((3, b"", b"de"),))
        self.assertEqual(differing_runs(b"abcd", b"ab"), ((2, b"cd", b""),))

    def test_the_same_bytes_have_no_run(self):
        self.assertEqual(differing_runs(b"abc", b"abc"), ())


class CompareByNameTest(unittest.TestCase):

    def test_each_block_added_removed_or_changed(self):
        built = {"main.HMI": b"\x01\x02\x03", "0.pa": b"page", "1.i": b"picture"}
        saved = {"main.HMI": b"\x01\x09\x03", "0.pa": b"page", "2.i": b"picture"}
        self.assertEqual(compare_by_name(built, saved), [
            Difference("1.i", REMOVED),
            Difference("2.i", ADDED),
            Difference("main.HMI", CHANGED, ((1, b"\x02", b"\x09"),))])


class RangesTest(unittest.TestCase):

    def test_each_run_gives_its_first_and_last_place(self):
        runs = ((0, b"abcd", b"wxyz"), (41, b"\x3d", b"\x44"), (50, b"", b"tail"))
        self.assertEqual(differing_ranges(runs), [(0, 3), (41, 41), (50, 53)])

    def test_ranges_are_given_as_text(self):
        self.assertEqual(ranges_text([(0, 3), (41, 41), (43, 43)]), "0 to 3, 41, 43")
        self.assertEqual(ranges_text([]), "")

    def test_ranges_that_touch_are_joined(self):
        self.assertEqual(ranges_text([(0, 0), (1, 1), (2, 3), (9, 9)]), "0 to 3, 9")

    def test_the_text_stops_after_the_most_ranges_asked_for(self):
        ranges = [(place, place) for place in range(0, 20, 2)]
        self.assertEqual(ranges_text(ranges, most=3), "0, 2, 4, and 7 more ranges")
        self.assertEqual(ranges_text(ranges[:4], most=3), "0, 2, 4, and 1 more range")
        self.assertEqual(ranges_text(ranges[:3], most=3), "0, 2, 4")


if __name__ == "__main__":
    unittest.main()
