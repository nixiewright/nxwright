"""What `nxwright test` tells a code editor: the ids of a folder's tests, and
each test's result, for VS Code's Test Explorer.

A test's id is the one unittest gives it, as
"test_home.TargetTest.test_raising_holds_the_target": its module, within the
folder of tests, its class, and its method.
"""
from pathlib import Path
import re
import unittest

_TRACE_PLACE = re.compile(r'File "(.+)", line (\d+)')


def test_ids(suite) -> list:
    """Returns the ids of the tests a suite holds, in order."""
    ids = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            ids += test_ids(item)
        else:
            ids.append(item.id())
    return ids


class RecordingResult(unittest.TextTestResult):
    """A test result that also keeps the tests that passed."""

    def __init__(self, *arguments, **keywords):
        super().__init__(*arguments, **keywords)
        self.passed = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed.append(test)


def results(result: RecordingResult, folder) -> list:
    """Returns each test's result as a dict: its "id"; its "outcome", one of
    "passed", "failed", "error", and "skipped"; and for a test that did not
    pass, its "message", and the "file" and "line" of the test's code where
    it stopped, the last line of the trace in the folder of tests.

    A test marked as expected to fail passes when it fails, and fails when
    it passes. A failing subTest fails its test, under the test's id."""
    found = [{"id": test.id(), "outcome": "passed"}
             for test in result.passed + [test for test, _ in result.expectedFailures]]
    found += [{"id": test.id(), "outcome": "failed",
               "message": "It passed, but is marked as expected to fail."}
              for test in result.unexpectedSuccesses]
    for outcome, entries in (("failed", result.failures), ("error", result.errors),
                             ("skipped", result.skipped)):
        for test, text in entries:
            # A subTest stands for its test, `test_case`.
            test = getattr(test, "test_case", test)
            entry = {"id": test.id(), "outcome": outcome, "message": text.strip()}
            places = [(file, int(line)) for file, line in _TRACE_PLACE.findall(text)
                      if _inside(file, folder)]
            if places:
                entry["file"], entry["line"] = places[-1]
            found.append(entry)
    return found


def _inside(file: str, folder) -> bool:
    """True when the file `file` lies inside `folder`."""
    try:
        Path(file).resolve().relative_to(Path(folder).resolve())
    except ValueError:
        return False
    return True
