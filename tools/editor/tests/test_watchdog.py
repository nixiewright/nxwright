"""The watchdog that stops a command whose call into the Editor never returns
(tools/editor/watchdog.py). Each case runs in a process of its own, as the
watchdog ends the process it watches. They need neither the Editor nor
pywinauto, only Windows, as the tool does."""
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from tools.editor.dedicated import Lock

_TOOL_FOLDER = str(Path(__file__).resolve().parents[3])

# Takes the lock, then blocks in one call, as a call into the Editor that
# never returns did, the watchdog watching for `quiet` seconds.
_HUNG = """
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from tools.editor import watchdog
from tools.editor.dedicated import Lock
with Lock(Path(sys.argv[1]), "a hung command"):
    with watchdog.watched(float(sys.argv[3])):
        time.sleep(60)
"""
# Makes progress, a look at a time, for longer than `quiet` seconds.
_MAKING_PROGRESS = """
import sys, time
sys.path.insert(0, sys.argv[2])
from tools.editor import watchdog
with watchdog.watched(float(sys.argv[3])):
    for _ in range(10):
        time.sleep(float(sys.argv[3]) / 5)
        watchdog.progress()
"""
# Tells of progress with nothing watched, then sleeps past `quiet`.
_UNWATCHED = """
import sys, time
sys.path.insert(0, sys.argv[2])
from tools.editor import watchdog
watchdog.progress()
time.sleep(float(sys.argv[3]) * 2)
"""
# Says a step will take longer than `quiet`, then takes it.
_LONG_STEP = """
import sys, time
sys.path.insert(0, sys.argv[2])
from tools.editor import watchdog
quiet = float(sys.argv[3])
with watchdog.watched(quiet):
    watchdog.progress(4 * quiet)
    time.sleep(2 * quiet)
"""


class WatchdogTest(unittest.TestCase):

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)

    def tearDown(self):
        self._folder.cleanup()

    def run_script(self, text: str, quiet: float) -> subprocess.CompletedProcess:
        script = self.folder / "script.py"
        script.write_text(text, encoding="utf-8")
        return subprocess.run([sys.executable, str(script), str(self.folder), _TOOL_FOLDER,
                               str(quiet)], capture_output=True, text=True, timeout=60)

    def test_a_hung_call_stops_the_command_and_frees_the_lock(self):
        started = time.monotonic()
        done = self.run_script(_HUNG, 1)
        self.assertEqual(done.returncode, 1)
        self.assertLess(time.monotonic() - started, 30)
        # Where each thread was, the hung call's line among them.
        self.assertIn("Timeout", done.stderr)
        self.assertIn('script.py", line 9', done.stderr)
        # Windows dropped the lock with the process, and its holder.json,
        # left behind, does not keep the next command out.
        with Lock(self.folder, "the next command", wait=1):
            pass

    def test_a_command_making_progress_runs_to_its_end(self):
        done = self.run_script(_MAKING_PROGRESS, 0.5)
        self.assertEqual((done.returncode, done.stderr), (0, ""))

    def test_progress_with_nothing_watched_arms_nothing(self):
        done = self.run_script(_UNWATCHED, 0.5)
        self.assertEqual((done.returncode, done.stderr), (0, ""))

    def test_a_step_known_to_be_long_is_given_its_time(self):
        done = self.run_script(_LONG_STEP, 0.5)
        self.assertEqual((done.returncode, done.stderr), (0, ""))


if __name__ == "__main__":
    unittest.main()
