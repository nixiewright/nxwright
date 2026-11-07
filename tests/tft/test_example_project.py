"""nxwright's example project in the match check.

The check must take nxwright's thermostat example, examples/thermostat/app,
built as the compile command builds a source folder (tft/commands/compile.py).
What it refuses today is listed below, each kind of need by what takes it up.
A kind that the check no longer refuses must be taken off the list, so that
the test checks it from then on.
"""
from pathlib import Path
import tempfile
import unittest

import nxwright
from nxwright.source.project_files import build

from nxwright.tft.matching import matched_rules, project_needs, unmatched
from nxwright.tft.project import Project

_EXAMPLE = Path(nxwright.__file__).resolve().parents[1] / "examples" / "thermostat" / "app"

# What the check refuses today, each kind of need by what takes it up: its
# words, which needs are of that kind, and the work that will take it.
_KNOWN_FAILURES = []


class ExampleProjectTest(unittest.TestCase):

    def test_the_check_takes_the_thermostat_example(self):
        with tempfile.TemporaryDirectory() as work:
            project_file = Path(work) / "project.HMI"
            build(_EXAMPLE, project_file)
            project = Project.from_file(project_file)
        refused = unmatched(project_needs(project), matched_rules())
        unexplained = [need.described() for need in refused
                       if not any(fits(need) for _, fits, _ in _KNOWN_FAILURES)]
        self.assertEqual(unexplained, [])
        stale = [words for words, fits, _ in _KNOWN_FAILURES
                 if not any(fits(need) for need in refused)]
        self.assertEqual(stale, [], "the check takes these now, so take them off the list")


if __name__ == "__main__":
    unittest.main()
