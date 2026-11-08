"""The upload command (tft/commands/upload.py): what it prints, when it
prompts, and what it sends, against a stand-in screen
(tests/tft/upload_stand_in.py) in place of the port it opens. No port is
opened, and the file is one the tests make (tests/tft/made_tft.py), not a TFT
file of the vendor's."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


from nxwright.project.screen_models import model_named

from nxwright.tft.commands import upload as command
from nxwright.tft.tft_file import TftFileError
from tests.tft.made_tft import made_tft
from tests.tft.upload_stand_in import END, StandInScreen

# The place of the device ID in a TFT file's header 1.
DEVICE_ID = 0x2E


# A file for the stand-in screen's model, the NX4832T035.
FILE = made_tft("T")
# A file for the NX8048P050.
OTHER_MODEL_FILE = made_tft("P")


def stand_in_file(model: str = "NX4832T035", size: int = 10000) -> bytes:
    """Returns `size` bytes that give the device ID of `model` where a TFT
    file does. They are not a TFT file, so nxwright cannot read them."""
    data = bytearray(size)
    data[DEVICE_ID:DEVICE_ID + 4] = model_named(model).device_id
    return bytes(data)


class UploadCommandTest(unittest.TestCase):

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)
        self.opened = []

    def tearDown(self):
        self._folder.cleanup()

    def run_upload(self, screen: StandInScreen, *options: str, data: bytes = None,
                   at_terminal: bool = False, answers: list = (),
                   one_stream: bool = False) -> tuple:
        """Runs the command on a file of `data`, with `screen` in place of
        the port COM5, and returns its exit code, and what it printed and
        wrote as errors. When `at_terminal`, it can prompt, and takes
        `answers` in turn. With `one_stream`, both go to one stream, in the
        order a terminal shows them, returned as what it printed."""
        file = self.folder / "app.tft"
        file.write_bytes(FILE if data is None else data)

        def opened(name: str):
            self.opened.append(name)
            return screen
        printed = io.StringIO()
        errors = printed if one_stream else io.StringIO()
        given = iter(answers)
        with mock.patch("nxwright.tft.commands.upload.at_terminal", lambda: at_terminal), \
                mock.patch("builtins.input", lambda prompt="": next(given)), \
                redirect_stdout(printed), redirect_stderr(errors):
            code = command.main([str(file), "--port", "COM5", "--baud", "9600", *options],
                                open_port=opened, pause_of=lambda rate: 0, settle=0,
                                answer_wait=0.05)
        return code, printed.getvalue(), errors.getvalue()

    def assert_nothing_past_connect(self, screen: StandInScreen):
        sent = [data for _, data in screen.writes if not data.endswith(b"connect" + END)]
        self.assertEqual(sent, [b"DRAKJHSUYDGBNCJHGJKSHBDN" + END])

    def test_an_upload_the_user_agrees_to(self):
        screen = StandInScreen()
        code, printed, errors = self.run_upload(screen, at_terminal=True, answers=["y"])
        self.assertEqual(code, 0, errors)
        self.assertEqual(self.opened, ["COM5"])
        self.assertTrue(screen.closed)
        self.assertEqual(screen.uploaded, FILE)
        self.assertIn("NX4832T035_011R on COM5", printed)
        self.assertIn("115200", printed)
        self.assertIn("100%", printed)
        # The file's model matches the screen's, though the screen gives its model with a
        # suffix.
        self.assertEqual(errors, "")

    def test_the_fast_upload_by_default_and_full_with_its_option(self):
        screen = StandInScreen(skip_to=8192)
        code, printed, _ = self.run_upload(screen, "--yes")
        self.assertEqual(code, 0)
        self.assertTrue(screen.fast)
        self.assertEqual(screen.uploaded, FILE[:4096] + FILE[8192:])
        self.assertIn("The screen already had 4096 bytes of the file, which were not sent.",
                      printed)
        self.assertIn("100%", printed)
        screen = StandInScreen(skip_to=8192)
        code, _, _ = self.run_upload(screen, "--yes", "--full")
        self.assertEqual(code, 0)
        self.assertFalse(screen.fast)
        self.assertEqual(screen.uploaded, FILE)

    def test_no_sends_nothing(self):
        screen = StandInScreen()
        code, _, errors = self.run_upload(screen, at_terminal=True, answers=["n"])
        self.assertEqual(code, 1)
        self.assertIn("the file was not sent", errors)
        self.assert_nothing_past_connect(screen)

    def test_no_terminal_sends_nothing_without_yes(self):
        screen = StandInScreen()
        code, _, errors = self.run_upload(screen)
        self.assertEqual(code, 3)
        self.assertIn("--yes", errors)
        self.assert_nothing_past_connect(screen)
        code, _, _ = self.run_upload(StandInScreen(), "--yes")
        self.assertEqual(code, 0)

    def assert_cancelled(self, screen: StandInScreen, errors: str, reason: str):
        """Checks that the command printed `reason` as its error, and sent
        nothing past `connect` to `screen`."""
        self.assertIn("nxwright upload: %s" % reason, errors)
        self.assert_nothing_past_connect(screen)

    def test_a_file_for_another_model_cancels_the_upload(self):
        reason = ("app.tft is for the NX8048P050, but the screen on COM5 is the NX4832T035. "
                  "Compile the project for the NX4832T035, or connect the screen the file is "
                  "for.")
        # At a terminal, no answer is given, so a prompt would stop the test.
        for options, at_terminal in (((), True), (("--yes",), True), (("--yes",), False),
                                     (("--find",), True)):
            screen = StandInScreen()
            code, printed, errors = self.run_upload(screen, *options, data=OTHER_MODEL_FILE,
                                                    at_terminal=at_terminal)
            self.assertEqual(code, 1, options)
            self.assert_cancelled(screen, errors, reason)
            self.assertNotIn("Upload", printed)
            self.assertTrue(screen.closed)

    def test_a_file_of_a_model_nxwright_does_not_know_cancels_the_upload(self):
        screen = StandInScreen()
        with mock.patch("nxwright.tft.commands.upload.model_with_id", lambda device_id: None):
            code, _, errors = self.run_upload(screen, "--yes")
        self.assertEqual(code, 1)
        self.assert_cancelled(screen, errors, (
            "nxwright does not know which model app.tft is for. The screen on COM5 is the "
            "NX4832T035, so compile the project for that model."))

    def test_a_screen_that_does_not_give_its_model_cancels_the_upload(self):
        screen = StandInScreen(model="_011R")
        code, _, errors = self.run_upload(screen, "--yes")
        self.assertEqual(code, 1)
        self.assert_cancelled(screen, errors, (
            "nxwright cannot tell whether app.tft is for the screen on COM5, as the screen did not "
            "answer with its model."))

    def test_a_file_nxwright_cannot_read_cancels_the_upload_before_the_port_is_opened(self):
        code, _, errors = self.run_upload(StandInScreen(), "--yes", data=stand_in_file())
        self.assertEqual(code, 1)
        self.assertIn("nxwright upload: %s was made by a Nextion Editor older than 1.60.1. "
                      "nxwright reads only files made by the Nextion Editor 1.60.1 or later. "
                      "Compile the project again with nxwright, or with the Nextion Editor."
                      % (self.folder / "app.tft"), errors)
        self.assertEqual(self.opened, [])

    def test_a_file_whose_checksum_does_not_match_cancels_the_upload(self):
        # The reader's error for a file it reads, as the command gets it.
        error = TftFileError("app.tft: the file's checksum does not match")
        with mock.patch("nxwright.tft.commands.upload.read_tft", side_effect=error):
            code, _, errors = self.run_upload(StandInScreen(), "--yes", at_terminal=True)
        self.assertEqual(code, 1)
        self.assertIn("nxwright upload: app.tft: the file's checksum does not match. Compile the "
                      "project again", errors)
        self.assertEqual(self.opened, [])

    def test_any_model_is_no_longer_an_option(self):
        with redirect_stderr(io.StringIO()) as errors, self.assertRaises(SystemExit) as stopped:
            command.main([str(self.folder / "app.tft"), "--port", "COM5", "--yes",
                          "--any-model"], open_port=lambda name: self.fail(name))
        self.assertEqual(stopped.exception.code, 2)
        self.assertIn("unrecognized arguments: --any-model", errors.getvalue())

    def test_a_high_rate_to_an_older_screen(self):
        code, _, errors = self.run_upload(StandInScreen(every_rate=False), "--yes",
                                          "--upload-baud", "921600")
        self.assertEqual(code, 0)
        self.assertIn("nxwright upload: warning: this screen may not take uploads faster than "
                      "115200 baud. If the upload fails, upload the file again at 115200 baud.",
                      errors)

    def test_no_screen_answers(self):
        screen = StandInScreen(rate=115200)
        code, _, errors = self.run_upload(screen, "--yes")
        self.assertEqual(code, 1)
        self.assertIn("no screen answered on COM5 at 9600", errors)

    def test_a_file_too_short_for_its_header(self):
        code, _, errors = self.run_upload(StandInScreen(), "--yes", data=bytes(20))
        self.assertEqual(code, 1)
        self.assertIn("too short", errors)
        self.assertEqual(self.opened, [])
        code, printed, _ = self.run_upload(StandInScreen(), "--yes", "--json", data=bytes(20))
        self.assertEqual(code, 1)
        self.assertEqual([json.loads(line)["event"] for line in printed.splitlines()],
                         ["cancelled"])

    def test_stopped_by_the_user_during_the_upload(self):
        # Ctrl-C during the packets: the screen waits for the rest.
        screen = StandInScreen()
        original_write = screen.write

        def write(data):
            # After the first packet, once its progress is printed.
            if len(screen.uploaded) >= 4096:
                raise KeyboardInterrupt
            return original_write(data)
        screen.write = write
        code, shown, _ = self.run_upload(screen, "--yes", one_stream=True)
        self.assertEqual(code, 1)
        # The progress line is ended before the advice, which starts its own.
        self.assertIn("%\nnxwright upload: stopped during the upload; the screen now needs to be "
                      "powered off and on, and the file uploaded again", shown)
        self.assertTrue(screen.closed)

    def test_a_screen_that_stops_answering(self):
        code, _, errors = self.run_upload(StandInScreen(answered_packets=1), "--yes")
        self.assertEqual(code, 1)
        self.assertIn("did not answer after 8192 of %d bytes" % len(FILE), errors)
        # The progress line is ended, so that the error starts a line of its
        # own at a terminal.
        code, printed, _ = self.run_upload(StandInScreen(answered_packets=1), "--yes")
        self.assertTrue(printed.endswith("%\n"), repr(printed[-20:]))

    def test_find_sends_nothing_past_finding_the_screen(self):
        # Not even at a terminal, where the upload would prompt.
        screen = StandInScreen()
        code, printed, errors = self.run_upload(screen, "--find", at_terminal=True)
        self.assertEqual(code, 0, errors)
        self.assertIn("to the screen NX4832T035_011R on COM5", printed)
        self.assert_nothing_past_connect(screen)
        self.assertTrue(screen.closed)

    def found(self, **changes) -> dict:
        """Returns the found event of the file FILE and the stand-in screen,
        with `changes`."""
        event = {"event": "found", "file": str(self.folder / "app.tft"), "size": len(FILE),
                 "file_model": "NX4832T035", "port": "COM5", "screen": "NX4832T035_011R",
                 "screen_rate": 9600, "takes_every_rate": True, "upload_rate": 115200,
                 "warnings": []}
        event.update(changes)
        return event

    def test_json_gives_each_step(self):
        screen = StandInScreen(skip_to=8192)
        code, printed, errors = self.run_upload(screen, "--yes", "--json")
        self.assertEqual(code, 0, errors)
        events = [json.loads(line) for line in printed.splitlines()]
        self.assertEqual(events[0], self.found())
        # The screen skips to 8192 once it has the first packet.
        self.assertEqual(events[1], {"event": "skipped", "bytes": 4096})
        self.assertEqual(events[2], {"event": "progress", "sent": 8192, "size": len(FILE)})
        self.assertEqual(events[-2], {"event": "progress", "sent": len(FILE), "size": len(FILE)})
        self.assertEqual(events[-1], {"event": "uploaded"})
        # The words for people go to standard error.
        self.assertIn("to the screen NX4832T035_011R on COM5", errors)
        self.assertEqual(screen.uploaded, FILE[:4096] + FILE[8192:])

    def test_json_with_find_and_a_warning(self):
        code, printed, errors = self.run_upload(StandInScreen(every_rate=False), "--find",
                                                "--json", "--upload-baud", "921600")
        self.assertEqual(code, 0, errors)
        found = self.found(takes_every_rate=False, upload_rate=921600, warnings=[
            "this screen may not take uploads faster than 115200 baud. If the upload fails, "
            "upload the file again at 115200 baud"])
        self.assertEqual([json.loads(line) for line in printed.splitlines()], [found])

    def test_json_gives_the_cancelled_upload_after_the_screen_it_found(self):
        screen = StandInScreen()
        code, printed, errors = self.run_upload(screen, "--yes", "--json", data=OTHER_MODEL_FILE)
        self.assertEqual(code, 1)
        events = [json.loads(line) for line in printed.splitlines()]
        self.assertEqual(events[0], self.found(file_model="NX8048P050",
                                               size=len(OTHER_MODEL_FILE)))
        self.assertEqual(events[1:], [{"event": "cancelled", "reason": (
            "app.tft is for the NX8048P050, but the screen on COM5 is the NX4832T035. Compile "
            "the project for the NX4832T035, or connect the screen the file is for.")}])
        self.assert_cancelled(screen, errors, events[1]["reason"])

    def test_json_gives_the_cancelled_upload_alone_for_a_file_that_fails_its_checks(self):
        code, printed, _ = self.run_upload(StandInScreen(), "--yes", "--json",
                                           data=stand_in_file())
        self.assertEqual(code, 1)
        self.assertEqual([json.loads(line)["event"] for line in printed.splitlines()],
                         ["cancelled"])
        self.assertEqual(self.opened, [])

    def test_json_never_prompts(self):
        # Without --yes, nothing is sent, even at a terminal.
        screen = StandInScreen()
        code, printed, errors = self.run_upload(screen, "--json", at_terminal=True)
        self.assertEqual(code, 3)
        self.assertIn("--yes", errors)
        self.assertEqual([json.loads(line)["event"] for line in printed.splitlines()], ["found"])
        self.assert_nothing_past_connect(screen)


if __name__ == "__main__":
    unittest.main()
