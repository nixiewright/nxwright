"""Uploading a TFT file to a screen with Nextion's upload protocol
(tft/upload.py), against a stand-in screen (tests/tft/upload_stand_in.py).
No port is opened."""
from pathlib import Path
import re
import time
import unittest


from nxwright.tft import upload
from nxwright.tft.upload import UploadError, find_screen
from tests.tft.upload_stand_in import END, StandInScreen

CONNECT = b"connect" + END
BROADCAST_CONNECT = b"\xff\xff" + CONNECT


def uploaded(screen: StandInScreen, data: bytes, upload_rate: int = 115200,
             progress=None) -> bool:
    """Finds `screen`, then uploads `data` to it, with waits of a moment, and
    returns whether the screen received the whole of `data`."""
    found = find_screen(screen, upload.RATES_TRIED, pause_of=lambda rate: 0)
    upload.upload(screen, found, data, upload_rate, progress, answer_wait=0.05)
    return screen.uploaded == data


class FindScreenTest(unittest.TestCase):

    def test_the_screen_is_found_at_its_rate_after_the_others(self):
        screen = StandInScreen(rate=38400)
        found = find_screen(screen, upload.RATES_TRIED, pause_of=lambda rate: 0)
        self.assertEqual((found.model, found.rate, found.address, found.takes_every_rate),
                         ("NX4832T035_011R", 38400, None, True))
        rates = []
        for rate, _ in screen.writes:
            if rate not in rates:
                rates.append(rate)
        self.assertEqual(rates[:3], [9600, 115200, 2400])
        self.assertEqual(rates[-1], 38400)
        # At each rate: the end of a reparse mode, then connect, to the
        # screen and to the broadcast address.
        self.assertEqual([data for rate, data in screen.writes if rate == 9600],
                         [upload.END_REPARSE, CONNECT, BROADCAST_CONNECT])

    def test_a_given_rate_alone(self):
        screen = StandInScreen(rate=115200)
        found = find_screen(screen, [115200], pause_of=lambda rate: 0)
        self.assertEqual(found.rate, 115200)
        self.assertEqual({rate for rate, _ in screen.writes}, {115200})
        self.assertIsNone(find_screen(StandInScreen(rate=9600), [115200],
                                      pause_of=lambda rate: 0))

    def test_comok_among_the_app_s_own_bytes(self):
        # A touch event the app sent before.
        screen = StandInScreen(app_bytes=b"\x65\x00\x01\x01" + END)
        self.assertEqual(find_screen(screen, [9600], pause_of=lambda rate: 0).model,
                         "NX4832T035_011R")

    def test_the_address_and_the_seventh_field(self):
        screen = StandInScreen(address=2556, every_rate=False)
        found = find_screen(screen, [9600], pause_of=lambda rate: 0)
        self.assertEqual((found.address, found.takes_every_rate), (2556, False))
        # An address two bytes cannot give is taken as none.
        self.assertIsNone(upload._screen_of("1,38024-70000,NX4832T035_011R,99,61488,D2,1", 9600)
                          .address)

    def test_the_pause_after_each_message(self):
        # The v1.1 and v1.2 pages' table: (1000000 / rate) + 30 ms.
        self.assertEqual([round(upload.pause(rate) * 1000) for rate in (2400, 9600, 921600)],
                         [447, 134, 31])


class UploadTest(unittest.TestCase):

    def test_every_byte_sent_in_order(self):
        data = bytes(range(256)) * 39 + bytes(16)
        self.assertEqual(len(data), 10000)
        screen = StandInScreen()
        progress = []
        self.assertTrue(uploaded(screen, data, progress=lambda sent, size: progress.append(sent)))
        # The screen answered the first connect, so nothing else was tried.
        self.assertEqual([data for _, data in screen.writes[:2]], [upload.END_REPARSE, CONNECT])
        # At the screen's rate: the wake-up, and the move to the upload rate.
        # Then, at the upload rate: the screen found again, and the upload
        # command, which gives the rate the screen is at.
        self.assertEqual(screen.writes[2:8], [
            (9600, b"sleep=0" + END), (9600, b"thsp=0" + END), (9600, b"baud=115200" + END),
            (115200, upload.END_REPARSE), (115200, CONNECT),
            (115200, b"whmi-wri 10000,115200,0" + END)])
        pieces = screen.writes[8:]
        self.assertTrue(all(rate == 115200 for rate, _ in pieces))
        self.assertTrue(all(len(piece) == upload.PIECE_SIZE for _, piece in pieces[:-1]))
        self.assertEqual(b"".join(piece for _, piece in pieces), data)
        self.assertEqual(screen.uploaded, data)
        self.assertEqual(progress, [4096, 8192, 10000])
        # The port's output is emptied after each piece, and before the rate
        # changes.
        self.assertGreaterEqual(screen.flushes, len(pieces) + 1)

    def test_a_screen_slow_to_move(self):
        # The user's screen did not answer at the new rate for a moment
        # after `baud=`: it is asked again until it does.
        screen = StandInScreen(deaf_after_move=4)
        found = find_screen(screen, [9600], pause_of=lambda rate: 0)
        # Long enough for a second round of find_screen at the new rate.
        upload.upload(screen, found, bytes(100), 115200, answer_wait=1.0)
        self.assertEqual(screen.uploaded, bytes(100))

    def test_no_move_at_the_screen_s_own_rate(self):
        screen = StandInScreen(rate=115200)
        self.assertTrue(uploaded(screen, bytes(100), upload_rate=115200))
        self.assertNotIn(b"baud=", screen.sent())

    def test_a_screen_that_does_not_answer_at_the_new_rate(self):
        # A screen that ignores baud=, which looks the same as an adapter
        # that cannot take the rate.
        screen = StandInScreen()
        original_take = screen._take

        def take(instruction):
            if not instruction.startswith(b"baud="):
                original_take(instruction)
        screen._take = take
        with self.assertRaises(UploadError) as raised:
            uploaded(screen, bytes(100), upload_rate=921600)
        self.assertIn("did not answer at 921600 bauds once moved to that rate",
                      str(raised.exception))
        self.assertEqual(screen.uploaded, b"")

    def test_the_input_is_emptied_before_the_upload_command(self):
        # A 05 the app sent must not be taken for the screen's answer to the
        # upload command, which this screen never gives.
        screen = StandInScreen(takes_upload=False)
        found = find_screen(screen, [9600], pause_of=lambda rate: 0)
        screen.app_sends(b"\x05")
        with self.assertRaises(UploadError) as raised:
            upload.upload(screen, found, bytes(5000), 9600, answer_wait=0.05)
        self.assertEqual(str(raised.exception),
                         "the screen did not answer the upload command; power it off and on "
                         "before you try again")
        self.assertEqual(screen.uploaded, b"")

    def test_a_screen_that_ignores_the_fast_upload(self):
        # An older firmware may not take whmi-wris: the error points at --full.
        screen = StandInScreen(takes_upload=False)
        with self.assertRaises(UploadError) as raised:
            self.fast_upload(screen, bytes(100))
        self.assertIn("the screen did not answer the upload command; power it off and on, "
                      "then try again, or with --full, which sends the whole file",
                      str(raised.exception))

    def test_what_came_in_place_of_an_answer(self):
        # An error code, such as 1A for an invalid variable, is given in the
        # error, to tell a screen that answered otherwise from a silent one.
        screen = StandInScreen(takes_upload=False)
        found = find_screen(screen, [9600], pause_of=lambda rate: 0)
        original_write = screen.write

        def write(data):
            original_write(data)
            if data.startswith(b"whmi-wri"):
                screen.app_sends(b"\x1a" + END)
        screen.write = write
        with self.assertRaises(UploadError) as raised:
            upload.upload(screen, found, bytes(10), 9600, answer_wait=0.05)
        self.assertIn("it sent 1a ff ff ff instead", str(raised.exception))

    def test_the_rate_changes_once_the_command_is_out(self):
        # The port changes rate only once its output is empty.
        screen = StandInScreen()
        found = find_screen(screen, [9600], pause_of=lambda rate: 0)
        waiting = [3, 2, 0]
        type(screen).out_waiting = property(lambda self: waiting.pop(0) if waiting else 0)
        try:
            upload.upload(screen, found, bytes(10), 115200, answer_wait=0.05)
        finally:
            del type(screen).out_waiting
        self.assertEqual(waiting, [])
        self.assertEqual(screen.uploaded, bytes(10))

    def fast_upload(self, screen: StandInScreen, data: bytes) -> tuple:
        """Finds `screen`, then uploads `data` to it with whmi-wris at
        115200, and returns (the places progress gave, the bytes on_skip
        gave as skipped)."""
        found = find_screen(screen, [9600], pause_of=lambda rate: 0)
        places, skipped = [], []
        upload.upload(screen, found, data, 115200, lambda place, size: places.append(place),
                      answer_wait=0.05, fast=True, on_skip=skipped.append)
        return places, skipped

    def test_the_fast_upload_skips_what_the_screen_has(self):
        data = bytes(range(256)) * 78 + bytes(32)
        self.assertEqual(len(data), 20000)
        screen = StandInScreen(skip_to=12288)
        places, skipped = self.fast_upload(screen, data)
        self.assertIn(b"whmi-wris 20000,115200,0" + END, screen.sent())
        # The first packet, then from the place the screen gave.
        self.assertEqual(screen.uploaded, data[:4096] + data[12288:])
        self.assertEqual(places, [12288, 16384, 20000])
        self.assertEqual(skipped, [8192])

    def test_the_fast_upload_of_a_file_the_screen_lacks(self):
        # Without an 08, every packet is sent, as with whmi-wri.
        screen = StandInScreen()
        places, skipped = self.fast_upload(screen, bytes(10000))
        self.assertTrue(screen.fast)
        self.assertEqual((screen.uploaded, places, skipped),
                         (bytes(10000), [4096, 8192, 10000], []))

    def test_a_place_of_zero_goes_on_with_the_next_packet(self):
        screen = StandInScreen(skip_answer=b"\x08" + bytes(4))
        places, skipped = self.fast_upload(screen, bytes(10000))
        self.assertEqual((screen.uploaded, places, skipped),
                         (bytes(10000), [4096, 8192, 10000], []))

    def test_a_place_outside_the_file_stops_the_upload(self):
        # Four bytes read the low one first give a place past the file:
        # nothing is sent from it, and the raw answer is given.
        screen = StandInScreen(skip_answer=b"\x08\x00\x30\x00\x00")
        with self.assertRaises(UploadError) as raised:
            self.fast_upload(screen, bytes(10000))
        self.assertEqual(str(raised.exception),
                         "the screen gave a place in the file nxwright cannot go on from, after "
                         "4096 of 10000 bytes; it sent 08 00 30 00 00; it now needs to be "
                         "powered off and on, and the file uploaded again")
        self.assertEqual(screen.uploaded, bytes(4096))

    def test_a_place_after_a_later_packet(self):
        # The screen may answer 08 after any packet, not the first alone.
        data = bytes(range(256)) * 78 + bytes(32)
        screen = StandInScreen(skip_to=16384, skip_packet=2)
        places, skipped = self.fast_upload(screen, data)
        self.assertEqual(screen.uploaded, data[:8192] + data[16384:])
        self.assertEqual((places, skipped), ([4096, 16384, 20000], [8192]))

    def test_a_place_behind_what_was_sent_or_cut_short_stops_the_upload(self):
        # Going back, or on from a place of fewer than four bytes, could send
        # the file wrongly: the upload stops, giving the raw answer.
        for answer, shown in ((b"\x08" + (100).to_bytes(4, "little"), "08 64 00 00 00"),
                              (b"\x08\x00\x30", "08 00 30")):
            with self.subTest(shown):
                screen = StandInScreen(skip_answer=answer)
                with self.assertRaises(UploadError) as raised:
                    self.fast_upload(screen, bytes(10000))
                self.assertIn("it sent %s;" % shown, str(raised.exception))
                self.assertEqual(screen.uploaded, bytes(4096))

    def test_a_screen_that_stops_answering(self):
        screen = StandInScreen(answered_packets=2)
        with self.assertRaises(UploadError) as raised:
            uploaded(screen, bytes(10000))
        self.assertEqual(str(raised.exception),
                         "the screen did not answer after 10000 of 10000 bytes; it now needs to "
                         "be powered off and on, and the file uploaded again")

    def test_the_address_before_each_instruction(self):
        screen = StandInScreen(address=2556)
        self.assertTrue(uploaded(screen, bytes(100)))
        # The instructions the upload sends, past those that find the screen.
        finding = (upload.END_REPARSE, CONNECT, BROADCAST_CONNECT)
        commands = [data for _, data in screen.writes
                    if data.endswith(END) and data not in finding]
        self.assertEqual(commands[0], b"\xfc\x09sleep=0" + END)
        self.assertTrue(all(command.startswith(b"\xfc\x09") for command in commands))
        self.assertEqual(screen.uploaded, bytes(100))

    def test_done_at_the_last_packet_s_answer(self):
        # The screen restarts with the file; nothing is waited for after the
        # last 05, though each answer may take 5 seconds.
        screen = StandInScreen()
        found = find_screen(screen, [9600], pause_of=lambda rate: 0)
        start = time.monotonic()
        upload.upload(screen, found, bytes(100), 9600, answer_wait=5.0)
        self.assertLess(time.monotonic() - start, 1.0)
        self.assertEqual(screen.uploaded, bytes(100))


class ExtensionRatesTest(unittest.TestCase):
    """The VS Code extension offers the rates the upload takes
    (editors/vscode/src/tftCommands.ts, UPLOAD_RATES), which it cannot read
    from here."""

    def test_the_extension_offers_the_upload_s_rates(self):
        source = (Path(__file__).resolve().parents[2] / "editors" / "vscode" / "src"
                  / "tftCommands.ts").read_text(encoding="utf-8")
        listed = re.search(r"const UPLOAD_RATES = \[([^\]]*)\]", source).group(1)
        self.assertEqual(sorted(int(rate) for rate in re.findall(r"\d+", listed)),
                         sorted(upload.RATES))


if __name__ == "__main__":
    unittest.main()
