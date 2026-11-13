"""A video that plays a file kept in memory: in `ram/`, or on an SD card that
was given no folder. The Nextion Editor's simulator played a video file
from `ram/`, for an NX8048P050."""
from pathlib import Path

from nxwright.testing.preview import Previews
from nxwright.testing.simulation import Simulation
from tests.test_folder_check import edited_app
from tests.test_simulation import SimulationTestCase, table

MEDIA = Path(__file__).resolve().parent / "fixtures" / "media"
COLOURS = (MEDIA / "colours.video").read_bytes()
CLIP = (MEDIA / "clip.video").read_bytes()
IGNORED = bytes.fromhex("06 ff ff ff")


class VideoInMemoryTest(SimulationTestCase):

    def started(self, path: str, files: dict) -> Simulation:
        """Starts a simulation whose page has a video, `v0`, that plays the
        file at `path`. `files` are the files kept in memory, {path: bytes},
        and the project sets 32768 bytes aside for `ram/` files. The bytes
        the simulation sends are in `self.sent`."""
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(memory_file_storage_size=32768)))
        self.page("page0", [table("v0", "video", x=300, y=100, w=320, h=240, path=path,
                                  **{"from": 1})])
        self.sent = []
        self.previews = Previews()
        return Simulation(self.root, sending=self.sent.append,
                          values={"file contents": dict(files)})

    def frame(self, simulation: Simulation):
        """The picture the drawing shows for the video, as a data URL, or
        None when it shows none."""
        drawing = self.previews.simulation_drawing(simulation, simulation.drawing_inputs())
        images = [shape.get("image") for shape in drawing["shapes"]
                  if shape["component"] == "v0"]
        return images[0] if images else None

    def test_a_video_file_in_ram_or_on_a_card_given_no_folder_shows_a_frame(self):
        for path in ("ram/v.video", "sd0/v.video"):
            with self.subTest(path=path):
                simulation = self.started(path, {path: COLOURS})
                self.assertTrue(self.frame(simulation).startswith("data:image/jpeg;base64,"))
                self.assertEqual(self.sent.count(IGNORED), 0)

    def test_a_file_in_memory_is_kept_open(self):
        # A video keeps its file open whether the file is in memory or in a
        # card's folder (test_playback.KeptFileTest).
        for path in ("ram/v.video", "sd0/v.video"):
            with self.subTest(path=path):
                simulation = self.started(path, {path: COLOURS})
                self.sent.clear()
                simulation.serial_input('delfile "%s"' % path)
                self.assertEqual(self.sent, [IGNORED])
                simulation.serial_input('v0.path=""')
                self.sent.clear()
                simulation.serial_input('rdfile "%s",0,0,0' % path)
                self.assertEqual(self.sent, [len(COLOURS).to_bytes(4, "little")])

    def test_new_bytes_show_in_the_next_drawing(self):
        # Both files are on a card, because `ram/` has room for only one of them.
        simulation = self.started("sd0/v.video", {"sd0/v.video": COLOURS, "sd0/c.video": CLIP})
        first = self.frame(simulation)
        simulation.serial_input('v0.path="sd0/c.video"')
        self.assertNotEqual(self.frame(simulation), first)
        # Now the file at the same path gets the bytes of the first file.
        simulation.serial_input('twfile "sd0/c.video",%d' % len(COLOURS))
        simulation.serial_received(COLOURS)
        simulation.serial_input('v0.path="sd0/c.video"')
        self.assertEqual(self.frame(simulation), first)

    def test_a_file_that_is_not_a_video_shows_no_frame(self):
        simulation = self.started("ram/v.video", {"ram/v.video": b"not a video"})
        self.assertIsNone(self.frame(simulation))

    def test_a_file_neither_on_a_card_nor_in_ram_shows_no_frame(self):
        simulation = self.started("v.video", {"v.video": COLOURS})
        self.assertIsNone(self.frame(simulation))
