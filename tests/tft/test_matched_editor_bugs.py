"""Tests the list of the Nextion Editor's bugs that nxwright matches on
purpose (tools/tft/probing/matched_editor_bugs.py).
"""
from pathlib import Path
import unittest

from tools.tft.probing import matched_editor_bugs

_NXWRIGHT = Path(__file__).resolve().parents[2]


class MatchedEditorBugsTest(unittest.TestCase):

    def test_each_bug_is_described(self):
        for bug in matched_editor_bugs.BUGS:
            with self.subTest(bug.what[:40]):
                self.assertTrue(bug.what.strip())
                self.assertTrue(bug.matched_in)
                self.assertTrue(bug.probes)

    def test_the_code_that_matches_each_bug_exists(self):
        # A bug's entry says which code to change once the Nextion Editor
        # fixes the bug, so it must keep pointing at that code.
        for bug in matched_editor_bugs.BUGS:
            for path, name in bug.matched_in:
                with self.subTest(path, name=name):
                    self.assertIn(name, (_NXWRIGHT / path).read_text(encoding="utf-8"))

    def test_its_probes_are_the_ones_its_bugs_list(self):
        listed = [name for bug in matched_editor_bugs.BUGS for name in bug.probes]
        self.assertEqual(len(listed), len(set(listed)))
        self.assertEqual([probe.name for probe in matched_editor_bugs.PROBES], listed)


if __name__ == "__main__":
    unittest.main()
