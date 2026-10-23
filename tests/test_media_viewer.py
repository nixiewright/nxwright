"""The language server's nxwright/mediaFrames request: the frames of an
animation or a video file and their timing, for the media viewer in VS Code."""
from pathlib import Path
import shutil
import tempfile
import unittest

from nxwright.project.media_files import animation_frames, video_frames
from nxwright.project.pictures import data_url
from tests.language_server_connection import initialized

MEDIA = Path(__file__).parent / "fixtures" / "media"


def frames_reply(path: Path) -> dict:
    connection = initialized()
    connection.handle({"jsonrpc": "2.0", "id": 2, "method": "nxwright/mediaFrames",
                       "params": {"file": str(path)}})
    return connection.sent[-1]


class MediaFramesTest(unittest.TestCase):

    def assertFramesOf(self, reply: dict, frames):
        self.assertEqual(reply, {
            "width": frames.width, "height": frames.height, "rotation": frames.rotation,
            "pictures": [data_url(picture, "image/jpeg") for picture in frames.pictures],
            "starts": list(frames.starts), "length": frames.length})

    def test_an_animation_in_the_screens_form(self):
        path = MEDIA / "blink.screen.gmov"
        self.assertFramesOf(frames_reply(path)["result"], animation_frames(path.read_bytes()))

    def test_an_animation_in_gmovmakers_form_plays_its_screens_form_beside_it(self):
        reply = frames_reply(MEDIA / "blink.gmov")["result"]
        self.assertFramesOf(reply, animation_frames((MEDIA / "blink.screen.gmov").read_bytes()))

    def test_a_video(self):
        path = MEDIA / "clip.video"
        self.assertFramesOf(frames_reply(path)["result"], video_frames(path.read_bytes()))

    def test_gmovmakers_form_alone_says_what_is_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            alone = Path(folder) / "blink.gmov"
            shutil.copy(MEDIA / "blink.gmov", alone)
            message = frames_reply(alone)["error"]["message"]
        self.assertIn("blink.screen.gmov", message)

    def test_a_file_that_is_neither_says_why(self):
        self.assertIn("beep.wav is neither an animation nor a video",
                      frames_reply(MEDIA / "beep.wav")["error"]["message"])


if __name__ == "__main__":
    unittest.main()
