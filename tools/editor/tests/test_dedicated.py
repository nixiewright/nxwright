"""The dedicated Editor's records (tools/editor/dedicated.py): the state file,
the process told apart from a later one with its ID, and the lock. They need
neither the Editor nor pywinauto, only Windows, as the tool does."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.editor.dedicated import (Busy, HoldRefused, Lock, Recorded, Shown, check_hold,
                                    editor_name, editor_words, private_memory, process_started,
                                    read_placement, read_recorded, read_shown, records_folder,
                                    release_hold, renew_hold, standing_hold, starting_placement,
                                    still_running, take_hold, write_placement, write_recorded,
                                    write_shown)

# Takes the lock and ends without letting it go, as a crashed script would.
_HOLD_AND_END = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from tools.editor.dedicated import Lock
Lock(Path(sys.argv[1]), "a crashed command").__enter__()
"""


class DedicatedTest(unittest.TestCase):

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def test_the_recorded_process_is_read_back(self):
        self.assertIsNone(read_recorded(self.folder))
        recorded = Recorded(1234, 133000000000000000, r"C:\Editor\Nextion Editor.exe")
        write_recorded(self.folder, recorded)
        self.assertEqual(read_recorded(self.folder), recorded)

    def test_the_project_shown_is_read_back(self):
        self.assertIsNone(read_shown(self.folder))
        for shown in (Shown(r"C:\work\demo.HMI", (800, 480)), Shown(r"C:\work\odd.HMI", None)):
            with self.subTest(shown=shown):
                write_shown(self.folder, shown)
                self.assertEqual(read_shown(self.folder), shown)

    def test_the_window_placement_is_read_back(self):
        self.assertIsNone(read_placement(self.folder))
        placement = (2, 1, (-32000, -32000), (-1, -1), (-1, 0, 1483, 997))
        write_placement(self.folder, placement)
        self.assertEqual(read_placement(self.folder), placement)
        for text in ("not json", "[2, 1]", "[2, 1, [0, 0], [0, 0], [0, 0, 1]]"):
            with self.subTest(text=text):
                (self.folder / "placement.json").write_text(text, encoding="utf-8")
                self.assertIsNone(read_placement(self.folder))

    def test_a_damaged_record_of_the_project_shown_reads_as_none(self):
        for text in ("not json", '{"project": "a.HMI"}', '{"project": "a.HMI", "screen": [1]}'):
            with self.subTest(text=text):
                (self.folder / "shown.json").write_text(text, encoding="utf-8")
                self.assertIsNone(read_shown(self.folder))

    def test_a_later_process_with_the_same_id_is_not_the_recorded_one(self):
        recorded = Recorded(1234, 100, "editor.exe")
        self.assertTrue(still_running(recorded, lambda pid: 100))
        self.assertFalse(still_running(recorded, lambda pid: 200))
        self.assertFalse(still_running(recorded, lambda pid: None))

    def test_an_ended_process_is_not_running_while_a_handle_to_it_stays_open(self):
        # Windows keeps an ended process's record, its start included, while
        # any program holds a handle to it. Here, the test holds one.
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        query_limited_information = 0x1000
        handle = kernel.OpenProcess(query_limited_information, False, process.pid)
        try:
            self.assertTrue(handle)
            recorded = Recorded(process.pid, process_started(process.pid), "python.exe")
            self.assertTrue(still_running(recorded))
            process.kill()
            process.wait()
            self.assertIsNone(process_started(process.pid))
            self.assertFalse(still_running(recorded))
        finally:
            process.kill()
            process.wait()
            kernel.CloseHandle(handle)

    def test_a_process_start_is_read_alike_each_time(self):
        started = process_started(os.getpid())
        self.assertIsInstance(started, int)
        self.assertEqual(process_started(os.getpid()), started)

    def test_a_process_private_memory_grows_as_it_takes_more(self):
        before = private_memory(os.getpid())
        held = bytearray(64 * 2 ** 20)
        self.assertGreaterEqual(private_memory(os.getpid()) - before, 60 * 2 ** 20)
        del held

    def test_the_lock_refuses_a_second_holder_and_names_the_first(self):
        with Lock(self.folder, "open demo.HMI"):
            with self.assertRaises(Busy) as refused:
                with Lock(self.folder, "screenshot", wait=0):
                    pass
        self.assertIn("process %d, running 'open demo.HMI'" % os.getpid(),
                      str(refused.exception))
        with Lock(self.folder, "screenshot", wait=0):
            pass

    def test_the_lock_of_a_process_that_ended_is_free(self):
        root = str(Path(__file__).resolve().parents[3])
        subprocess.run([sys.executable, "-c", _HOLD_AND_END, str(self.folder), root],
                       check=True)
        with Lock(self.folder, "screenshot", wait=0):
            pass


class HoldTest(unittest.TestCase):
    """A hold across commands: one holder's probe runs on the Editor as it
    left it, from its first command to its last."""

    NOW = 1_000_000.0

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def test_a_hold_refuses_another_and_lets_its_holder_run(self):
        take_hold(self.folder, "agent-b", 10, self.NOW)
        for name in ("agent-c", None):
            with self.subTest(name=name), self.assertRaises(HoldRefused) as refused:
                check_hold(self.folder, name, self.NOW + 60)
            self.assertIn("agent-b", str(refused.exception))
        # Its own command renews it, for the minutes given to `hold`, and
        # is given the hold, so that it renews it again as it ends: a
        # command longer than the hold would otherwise outlive it.
        held = check_hold(self.folder, "agent-b", self.NOW + 300)
        self.assertEqual(standing_hold(self.folder, self.NOW + 300).until, self.NOW + 900)
        self.assertEqual((held.holder, held.minutes), ("agent-b", 10))
        # Its command outlived the hold; renewed as it ends, the hold stands.
        renew_hold(held, self.folder, self.NOW + 2000)
        self.assertEqual(standing_hold(self.folder, self.NOW + 2000).until, self.NOW + 2600)

    def test_with_no_hold_anyone_runs_and_none_is_taken(self):
        for name in ("agent-c", None):
            check_hold(self.folder, name, self.NOW)
        self.assertIsNone(standing_hold(self.folder, self.NOW))

    def test_a_hold_past_its_time_is_none(self):
        take_hold(self.folder, "agent-b", 1, self.NOW)
        check_hold(self.folder, "agent-c", self.NOW + 61)
        self.assertIsNone(standing_hold(self.folder, self.NOW + 61))

    def test_taken_again_by_its_holder_alone(self):
        take_hold(self.folder, "agent-b", 10, self.NOW)
        with self.assertRaises(HoldRefused):
            take_hold(self.folder, "agent-c", 10, self.NOW)
        take_hold(self.folder, "agent-b", 20, self.NOW + 60)
        hold = standing_hold(self.folder, self.NOW + 60)
        self.assertEqual((hold.holder, hold.minutes, hold.until), ("agent-b", 20, self.NOW + 1260))

    def test_released_by_its_holders_name(self):
        take_hold(self.folder, "agent-b", 10, self.NOW)
        with self.assertRaises(HoldRefused):
            release_hold(self.folder, "agent-c", self.NOW)
        release_hold(self.folder, "agent-b", self.NOW)
        self.assertIsNone(standing_hold(self.folder, self.NOW))
        release_hold(self.folder, "agent-b", self.NOW)      # none: nothing to do

    def test_its_minutes_at_most_an_hour(self):
        for minutes in (0, 61):
            with self.subTest(minutes=minutes), self.assertRaises(ValueError):
                take_hold(self.folder, "agent-b", minutes, self.NOW)


class NamedEditorTest(unittest.TestCase):
    """The Editor that NXWRIGHT_EDITOR_NAME names, each name with its own
    records, so that each agent drives its own; none, the shared one."""

    def setUp(self):
        local = tempfile.TemporaryDirectory()
        self.addCleanup(local.cleanup)
        self.local = Path(local.name)

    def test_the_name_from_the_environment(self):
        self.assertIsNone(editor_name({}))
        self.assertIsNone(editor_name({"NXWRIGHT_EDITOR_NAME": ""}))
        self.assertEqual(editor_name({"NXWRIGHT_EDITOR_NAME": "agent-c"}), "agent-c")

    def test_each_name_its_own_folder(self):
        self.assertEqual(records_folder(None, self.local), self.local / "nxwright" / "editor")
        named = records_folder("agent_c-2", self.local)
        self.assertEqual(named, self.local / "nxwright" / "editor-agent_c-2")
        self.assertTrue(named.is_dir())

    def test_a_name_that_could_lead_elsewhere_is_refused_first(self):
        # The folder holds copies the tool writes over, so a name is refused
        # before any folder is made.
        for name in ("..\\x", "C:\\x", "a/b", "..", "a b", "x" * 33):
            with self.subTest(name=name), self.assertRaises(ValueError):
                records_folder(name, self.local)
        self.assertEqual(list(self.local.iterdir()), [])

    def test_the_words_naming_it(self):
        self.assertEqual(editor_words(None), "the shared Editor")
        self.assertEqual(editor_words("agent-c"), "agent-c's Editor")

    def test_a_fresh_editor_takes_the_shared_placement_until_it_has_its_own(self):
        shared, named = records_folder(None, self.local), records_folder("agent-c", self.local)
        self.assertIsNone(starting_placement(named, shared))
        placement = (2, 1, (-32000, -32000), (-1, -1), (-1, 0, 1483, 997))
        write_placement(shared, placement)
        self.assertEqual(starting_placement(named, shared), placement)
        own = (2, 1, (-32000, -32000), (-1, -1), (100, 50, 900, 700))
        write_placement(named, own)
        self.assertEqual(starting_placement(named, shared), own)


if __name__ == "__main__":
    unittest.main()
