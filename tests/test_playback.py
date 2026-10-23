"""Animations, videos, and sounds played: their frames read from their files,
drawn in the page preview, and played by the simulation, as the Editor's
simulator showed them.

Beside test_media.py's fixtures, tests/fixtures/media/ holds that probe's:
  - colours.gmov, GmovMaker's file of four frames 80 by 60, red, green,
    blue, and white, their durations edited to 200, 400, 600, and 800 ms,
    and colours.screen.gmov, the form the Editor made of it, which kept
    them;
  - colours.video, VideoBox's file of a clip turning from red to green to
    blue, 19 frames 64 by 48 at 12 a second: frames 0 to 7 red, 8 to 13
    green, and 14 to 18 blue.
On a page playing both and a sound, a timer copied each player's `tim` into
a number every 50 ms, and each `playend` counted. Pictures of the Editor's
simulator then showed which frame each `tim` shows, and what `en`, `loop`,
`dis`, and code setting `tim` do: the readings the tests below hold.
"""
from pathlib import Path
import shutil
import unittest

from nxwright import NxwrightError
from nxwright.testing.preview import Previews
from nxwright.project.media_files import animation_frames, sound_length, video_frames
from nxwright.project.pictures import data_url
from nxwright.source.source_folder import folder_reader, read_page_components
from nxwright.testing.sd_cards import INVALID_FILE_OPERATION
from nxwright.testing.simulation import Simulation
from nxwright.testing.simulation_log import END
from tests.test_media import FIXTURES, MediaFolderTestCase, edit_text

COLOURS = animation_frames((FIXTURES / "colours.screen.gmov").read_bytes())
BLINK = animation_frames((FIXTURES / "blink.screen.gmov").read_bytes())
# What a player answers as it loads a file its card lacks.
MISSING_FILE = bytes([INVALID_FILE_OPERATION]) + END
VIDEO = video_frames((FIXTURES / "colours.video").read_bytes())
# The probe's page: the animation, the video, a sound, and what code reads.
PLAYERS = """
[[component]]
name = "gm0"
type = "gmov"
x = 20
y = 20
w = 80
h = 60
vid = "colours"

[[component]]
name = "video0"
type = "video"
x = 200
y = 20
w = 64
h = 48
vid = "colours"

[[component]]
name = "wav0"
type = "audio"
vid = "beep"

[[component]]
name = "seen"
type = "variable"
"""
# Each player's playend counts in a system variable.
COUNTING = """on gm0.playend:
  sys0=sys0+1

on video0.playend:
  sys1=sys1+1

on wav0.playend:
  sys2=sys2+1
"""


def frame_url(frames, number: int) -> str:
    return data_url(frames.pictures[number], "image/jpeg")


class FramesTest(unittest.TestCase):
    """The frames of the files, and when each shows."""

    def test_an_animations_frames_last_their_durations(self):
        self.assertEqual((COLOURS.width, COLOURS.height, COLOURS.starts, COLOURS.length,
                          COLOURS.end), (80, 60, (0, 200, 600, 1200), 2000, 2000))
        # tim 216 showed green, 604 blue, and 1204 and 1300 white.
        self.assertEqual([COLOURS.at(time) for time in (0, 216, 604, 1204, 1300, 2000)],
                         [0, 1, 2, 3, 3, 3])

    def test_a_videos_frames_follow_its_rate(self):
        # Its stim read 1584, and a run that did not loop stopped at tim 1583.
        self.assertEqual((VIDEO.width, VIDEO.height, len(VIDEO.pictures), VIDEO.length,
                          VIDEO.end), (64, 48, 19, 1584, 1583))
        # tim 0 showed red, 672, 1000, and 1098 green, and 1516 blue.
        self.assertEqual([VIDEO.at(time) for time in (0, 672, 1000, 1098, 1516)],
                         [0, 8, 12, 13, 18])

    def test_each_frame_is_a_whole_jpeg_picture(self):
        blink = animation_frames((FIXTURES / "blink.screen.gmov").read_bytes())
        self.assertEqual((blink.starts, blink.length), ((0, 50, 100), 150))
        for frames in (blink, COLOURS, VIDEO):
            for picture in frames.pictures:
                self.assertEqual((picture[:2], picture[-2:]), (b"\xff\xd8", b"\xff\xd9"))

    def test_a_sound_lasts_its_samples(self):
        # The Editor's simulator read 50 for the 1,100 samples at 22,050 a second.
        self.assertEqual([sound_length((FIXTURES / name).read_bytes())
                          for name in ("beep.wav", "chirp.wav")], [50, 50])

    def test_damaged_files_are_refused(self):
        screen_form = (FIXTURES / "colours.screen.gmov").read_bytes()
        video = (FIXTURES / "colours.video").read_bytes()
        for data, read, message in (
                (screen_form[:3900], animation_frames, "frame 3 lies outside the file"),
                ((FIXTURES / "colours.gmov").read_bytes(), animation_frames, "screen's form"),
                (video[:6] + b"\0" + video[7:], video_frames, "frame rate is 0"),
                (video.replace(b"\xff\xd8", b"\0\0", 1), video_frames, "frame 0 holds no JPEG"),
                (b"RIFF", sound_length, "not a WAV file")):
            with self.subTest(message=message):
                with self.assertRaisesRegex(NxwrightError, message):
                    read(data)


class PlayingFolderTestCase(MediaFolderTestCase):
    """The probe's page in a source folder, with the fixtures it plays."""
    media = {"animations": ["colours"], "videos": ["colours"], "sounds": ["beep"]}
    players = PLAYERS

    def setUp(self):
        super().setUp()
        (self.source / "pages" / "page0.nx").write_text(COUNTING, encoding="utf-8",
                                                         newline="\n")

    def drawn(self, components=None) -> dict:
        """Returns {component: its image} of the page's drawing, as the preview
        draws the page file's values, or as a simulation has `components`."""
        if components is None:
            app, components = read_page_components(folder_reader(self.source), "page0")
        else:
            app = Simulation(self.source).app
        drawing = Previews().drawing_of(self.source, app, components)
        self.notes = drawing["notes"]
        return {shape["component"]: shape for shape in drawing["shapes"]
                if shape["component"] in ("gm0", "video0")}


class PreviewTest(PlayingFolderTestCase):

    def test_the_first_frames_are_drawn_at_the_components_corners(self):
        shapes = self.drawn()
        self.assertEqual({name: (shape["kind"], shape["x"], shape["y"], shape["w"], shape["h"],
                                 shape["image"]) for name, shape in shapes.items()},
                         {"gm0": ("text", 20, 20, 80, 60, frame_url(COLOURS, 0)),
                          "video0": ("text", 200, 20, 64, 48, frame_url(VIDEO, 0))})

    def test_the_page_files_tim_chooses_the_frame(self):
        edit_text(self.source / "pages" / "page0.page.toml", 'vid = "colours"\n\n[[component]]\n'
                  'name = "video0"', 'vid = "colours"\ntim = 650\n\n[[component]]\nname = "video0"')
        self.assertEqual(self.drawn()["gm0"]["image"], frame_url(COLOURS, 2))

    def test_no_animation_draws_nothing_and_an_unknown_one_is_outlined(self):
        page = self.source / "pages" / "page0.page.toml"
        edit_text(page, 'vid = "colours"\n\n[[component]]\nname = "video0"',
                  'vid = 65535\n\n[[component]]\nname = "video0"')
        self.assertNotIn("gm0", self.drawn())
        edit_text(page, "vid = 65535", "vid = 3")
        self.assertEqual(self.drawn()["gm0"]["kind"], "outline")
        self.assertIn("gm0: vid 3 is not an animation of the folder", self.notes)

    def test_a_damaged_file_is_outlined_with_a_note(self):
        path = self.source / "animations" / "colours.screen.gmov"
        # Cut inside the last frame, which ends at byte 3,986, before more
        # bytes of the Editor's own.
        path.write_bytes(path.read_bytes()[:3900])
        self.assertEqual(self.drawn()["gm0"]["kind"], "outline")
        self.assertIn("gm0: its animation cannot be shown: frame 3 lies outside the file",
                      self.notes)

    def test_a_video_on_a_card_is_drawn_only_from_a_card_folder(self):
        edit_text(self.source / "pages" / "page0.page.toml", 'vid = "colours"\n\n[[component]]\n'
                  'name = "wav0"', 'from = 1\npath = "sd0/clip.video"\n\n[[component]]\n'
                  'name = "wav0"')
        self.assertNotIn("video0", self.drawn())


class AnimationFromACardTest(PlayingFolderTestCase):
    """An animation of `from` 1, which has no `vid`: the Editor's simulator
    played the project's first animation, whatever its `vid` named. Here
    gm0's `vid` names colours, the second animation."""
    media = {"animations": ["blink", "colours"], "videos": ["colours"], "sounds": ["beep"]}

    def setUp(self):
        super().setUp()
        edit_text(self.source / "pages" / "page0.page.toml", 'vid = "colours"\n\n[[component]]\n'
                  'name = "video0"', 'vid = "colours"\nfrom = 1\n\n[[component]]\nname = "video0"')

    def test_it_plays_the_first_animation(self):
        simulation = Simulation(self.source)
        self.assertEqual(simulation.values()["gm0.stim"], BLINK.length)
        self.assertNotIn("gm0.vid", simulation.values())
        self.assertEqual(self.drawn(simulation.components())["gm0"]["image"],
                         frame_url(BLINK, 0))

    def test_the_preview_draws_the_first_animation(self):
        self.assertEqual(self.drawn()["gm0"]["image"], frame_url(BLINK, 0))

    def test_it_reads_no_card(self):
        # Its path names no file, and the Editor's simulator answered
        # nothing as its page opened.
        sent = []
        Simulation(self.source, sending=sent.append)
        self.assertNotIn(MISSING_FILE, sent)


class PlaybackTest(PlayingFolderTestCase):

    def fields(self, simulation, *names) -> tuple:
        values = simulation.values()
        return tuple(values[name] for name in names)

    def test_stim_and_qty_come_from_the_files(self):
        simulation = Simulation(self.source)
        self.assertEqual(self.fields(simulation, "gm0.stim", "gm0.qty", "video0.stim",
                                     "video0.qty", "wav0.stim"), (2000, 4, 1584, 19, 50))

    def test_the_frame_follows_the_clock(self):
        simulation = Simulation(self.source)
        simulation.advance(650)
        self.assertEqual(self.fields(simulation, "gm0.tim", "video0.tim"), (650, 650))
        shapes = self.drawn(simulation.components())
        self.assertEqual((shapes["gm0"]["image"], shapes["video0"]["image"]),
                         (frame_url(COLOURS, 2), frame_url(VIDEO, 7)))

    def test_code_reads_tim_between_two_frames(self):
        simulation = Simulation(self.source)
        simulation.advance(250)
        simulation.serial_input("seen.val=gm0.tim")
        self.assertEqual(simulation.fields["page0"]["seen.val"], 250)

    def test_a_typed_instruction_reads_tim_between_two_frames(self):
        # The sound stopped, no playend brings the players up to the clock
        # between two frames: a typed instruction does, as a screen's code
        # reads `tim` where the run is. Paused so, the run stays there.
        simulation = Simulation(self.source)
        simulation.serial_input("wav0.en=0")
        simulation.advance(250)
        simulation.serial_input("seen.val=gm0.tim")
        simulation.serial_input("gm0.en=2")
        simulation.advance(500)
        self.assertEqual((simulation.fields["page0"]["seen.val"],
                          self.fields(simulation, "gm0.tim")), (250, (250,)))

    def test_players_stand_still_while_the_screen_sleeps(self):
        # As its timers do, from where they were as it fell asleep.
        simulation = Simulation(self.source)
        simulation.advance(250)
        simulation.serial_input("sleep=1")
        simulation.advance(1000)
        simulation.serial_input("seen.val=gm0.tim")
        self.assertEqual(simulation.fields["page0"]["seen.val"], 250)
        simulation.serial_input("sleep=0")
        simulation.advance(100)
        self.assertEqual(self.fields(simulation, "gm0.tim"), (350,))

    def test_each_run_ends_with_playend_and_loops(self):
        simulation = Simulation(self.source)
        simulation.advance(4100)
        self.assertEqual((simulation.globals["sys0"], simulation.globals["sys1"]), (2, 2))
        # The video loops at its end, 1583: 4100 - 2 x 1583.
        self.assertEqual(self.fields(simulation, "gm0.tim", "video0.tim"), (100, 934))

    def test_without_loop_a_run_ends_on_its_last_frame(self):
        simulation = Simulation(self.source)
        simulation.serial_input("gm0.loop=0")
        simulation.serial_input("video0.loop=0")
        simulation.advance(5000)
        self.assertEqual(self.fields(simulation, "gm0.tim", "gm0.en", "video0.tim", "video0.en"),
                         (2000, 0, 1583, 0))
        self.assertEqual((simulation.globals["sys0"], simulation.globals["sys1"]), (1, 1))
        shapes = self.drawn(simulation.components())
        self.assertEqual(shapes["gm0"]["image"], frame_url(COLOURS, 3))

    def test_en_0_stops_at_the_first_frame_and_2_pauses(self):
        simulation = Simulation(self.source)
        simulation.advance(700)
        simulation.serial_input("gm0.en=0")
        simulation.serial_input("video0.en=2")
        simulation.advance(500)
        self.assertEqual(self.fields(simulation, "gm0.tim", "video0.tim"), (0, 700))
        simulation.serial_input("video0.en=1")
        simulation.advance(100)
        self.assertEqual(self.fields(simulation, "gm0.tim", "video0.tim"), (0, 800))

    def test_code_setting_tim_moves_the_run_there(self):
        simulation = Simulation(self.source)
        simulation.advance(100)
        simulation.serial_input("gm0.tim=1300")
        self.assertEqual(self.drawn(simulation.components())["gm0"]["image"],
                         frame_url(COLOURS, 3))
        simulation.advance(100)
        self.assertEqual(self.fields(simulation, "gm0.tim"), (1400,))

    def test_dis_is_the_speed_in_percent(self):
        simulation = Simulation(self.source)
        simulation.serial_input("gm0.dis=200")
        simulation.serial_input("video0.dis=50")
        simulation.advance(400)
        self.assertEqual(self.fields(simulation, "gm0.tim", "video0.tim"), (800, 200))

    def test_a_dis_outside_its_hints_range_is_the_speed_still(self):
        # The Nextion Editor's hint gives 10 to 1000. Its simulator, given
        # 5 by code, played half as fast as at 10, and given 2000, about
        # twice as fast as at 1000.
        simulation = Simulation(self.source)
        simulation.serial_input("gm0.dis=2000")
        simulation.serial_input("video0.dis=5")
        simulation.advance(50)
        self.assertEqual(self.fields(simulation, "gm0.tim", "video0.tim"), (1000, 2))
        simulation.advance(350)
        self.assertEqual(self.fields(simulation, "video0.tim"), (20,))

    def test_a_dis_of_0_stands_still(self):
        # The Nextion Editor's simulator stopped answering at 0. A `dis`
        # below 0 cannot be: the screen keeps two bytes of it, -50 reading
        # 65486, which plays that fast.
        simulation = Simulation(self.source)
        simulation.advance(300)
        simulation.serial_input("gm0.dis=0")
        simulation.serial_input("video0.dis=-50")
        simulation.advance(1000)
        self.assertEqual(self.fields(simulation, "gm0.tim", "gm0.en", "video0.dis"),
                         (300, 1, 65486))
        simulation.serial_input("gm0.dis=100")
        simulation.advance(100)
        self.assertEqual(self.fields(simulation, "gm0.tim"), (400,))

    def test_a_new_vid_plays_from_its_start(self):
        self.add_media({"animations": ["colours", "blink"], "videos": ["colours", "clip"]})
        simulation = Simulation(self.source)
        simulation.advance(300)
        simulation.serial_input("gm0.vid=1")
        simulation.serial_input("video0.vid=1")
        simulation.advance(100)
        self.assertEqual(self.fields(simulation, "gm0.stim", "gm0.tim", "video0.stim",
                                     "video0.tim"), (150, 100, 1000, 100))

    def test_a_vid_set_to_the_one_playing_plays_on(self):
        # Unlike a path set again.
        simulation = Simulation(self.source)
        simulation.advance(300)
        simulation.serial_input("gm0.vid=0")
        simulation.serial_input("video0.vid=0")
        simulation.advance(100)
        self.assertEqual(self.fields(simulation, "gm0.tim", "video0.tim"), (400, 400))

    def test_a_vid_set_while_it_does_not_play(self):
        # As the Nextion Editor's simulator showed, on an animation, a
        # video, and a sound. Stopped, paused, or at a run's end, a player
        # set to the ID it has loaded kept its `tim` and `en`. Set to
        # another ID, it loaded that one, its `tim` back to 0, and stayed
        # stopped or paused.
        self.add_media({"animations": ["colours", "blink"], "videos": ["colours", "clip"]})
        simulation = Simulation(self.source)
        simulation.serial_input("wav0.en=0")
        simulation.serial_input("video0.loop=0")
        simulation.advance(300)
        simulation.serial_input("gm0.en=2")
        simulation.advance(2000)
        for line in ("gm0.vid=0", "video0.vid=0", "wav0.vid=0"):
            simulation.serial_input(line)
        simulation.advance(100)
        self.assertEqual(self.fields(simulation, "gm0.tim", "gm0.en", "video0.tim", "video0.en",
                                     "wav0.tim", "wav0.en"), (300, 2, 1583, 0, 0, 0))
        simulation.serial_input("gm0.vid=1")
        simulation.serial_input("video0.vid=1")
        simulation.advance(100)
        self.assertEqual(self.fields(simulation, "gm0.stim", "gm0.tim", "gm0.en", "video0.stim",
                                     "video0.tim", "video0.en"), (150, 0, 2, 1000, 0, 0))

    def test_a_sound_says_what_it_does(self):
        simulation = Simulation(self.source)
        simulation.advance(120)
        simulation.serial_input("wav0.en=0")
        said = [line for _, line in simulation.log if line.startswith("wav0")]
        # Its loops, every 50 ms, are not written.
        self.assertEqual(said, ["wav0 plays from 0 ms", "wav0 stops"])
        self.assertEqual(simulation.globals["sys2"], 2)

    def test_a_card_file_its_card_lacks_answers_06(self):
        # As the Editor's simulator answered as the page opened: a video's
        # and a sound's of from 1, each 06, an invalid file operation, as
        # bkcmd asks, and neither plays.
        card = self.folder / "card"
        card.mkdir()
        page = self.source / "pages" / "page0.page.toml"
        edit_text(page, 'vid = "colours"\n\n[[component]]\nname = "wav0"',
                  'from = 1\npath = "sd0/missing.video"\n\n[[component]]\nname = "wav0"')
        edit_text(page, 'vid = "beep"', 'from = 1\npath = "sd0/missing.wav"')
        sent = []
        simulation = Simulation(self.source, cards={"sd0/": card}, sending=sent.append)
        self.assertEqual(sent.count(MISSING_FILE), 2)
        self.assertEqual(self.fields(simulation, "video0.stim", "wav0.stim"), (0, 0))
        # Code setting the path to another missing file answers again.
        simulation.serial_input('video0.path="sd0/other.video"')
        self.assertEqual(sent.count(MISSING_FILE), 3)

    def test_an_empty_card_path_answers_nothing(self):
        # As the Editor's simulator answered nothing for a video of from 1
        # with no path.
        edit_text(self.source / "pages" / "page0.page.toml", 'vid = "colours"\n\n[[component]]\n'
                  'name = "wav0"', 'from = 1\n\n[[component]]\nname = "wav0"')
        sent = []
        Simulation(self.source, cards={"sd0/": self.folder}, sending=sent.append)
        self.assertNotIn(MISSING_FILE, sent)

    def test_a_video_plays_from_a_card_folder(self):
        card = self.folder / "card"
        card.mkdir()
        shutil.copyfile(Path(FIXTURES / "colours.video"), card / "clip.video")
        edit_text(self.source / "pages" / "page0.page.toml", 'vid = "colours"\n\n[[component]]\n'
                  'name = "wav0"', 'from = 1\npath = "sd0/clip.video"\n\n[[component]]\n'
                  'name = "wav0"')
        simulation = Simulation(self.source, cards={"sd0/": card})
        simulation.advance(672)
        self.assertEqual(self.fields(simulation, "video0.stim", "video0.tim"), (1584, 672))

    def test_a_path_set_again_plays_from_its_start(self):
        # Even the path it plays, unlike a `vid`.
        card = self.folder / "card"
        card.mkdir()
        shutil.copyfile(Path(FIXTURES / "colours.video"), card / "clip.video")
        edit_text(self.source / "pages" / "page0.page.toml", 'vid = "colours"\n\n[[component]]\n'
                  'name = "wav0"', 'from = 1\npath = "sd0/clip.video"\n\n[[component]]\n'
                  'name = "wav0"')
        simulation = Simulation(self.source, cards={"sd0/": card})
        simulation.advance(300)
        simulation.serial_input('video0.path="sd0/clip.video"')
        simulation.advance(100)
        self.assertEqual(self.fields(simulation, "video0.tim"), (100,))


class HiddenAttributesTest(PlayingFolderTestCase):
    """A video's and a sound's fps, and a sound's dis and qty, which the
    Nextion Editor's panel never shows, as its simulator and its compile
    showed them."""

    def setUp(self):
        super().setUp()
        # The probe's page file stored the same: fps 24 on the video and
        # on the sound, and qty 7 on the sound.
        page = self.source / "pages" / "page0.page.toml"
        edit_text(page, 'vid = "colours"\n\n[[component]]\nname = "wav0"',
                  'vid = "colours"\nfps = 24\n\n[[component]]\nname = "wav0"')
        edit_text(page, 'vid = "beep"', 'vid = "beep"\nfps = 24\nqty = 7')

    def fields(self, simulation, *names) -> tuple:
        values = simulation.values()
        return tuple(values[name] for name in names)

    def test_a_videos_fps_is_its_files_frame_rate(self):
        # colours.video holds 12 frames a second: fps read 12, though the
        # page file stores 24. A sound keeps what its page file stores.
        simulation = Simulation(self.source)
        self.assertEqual(self.fields(simulation, "video0.fps", "wav0.fps", "wav0.qty"),
                         (12, 24, 7))

    def test_a_sounds_dis_does_not_change_its_speed(self):
        # Its tim went on as fast at dis 50 as at 100, where a video's went
        # half as fast.
        simulation = Simulation(self.source)
        simulation.serial_input("wav0.dis=50")
        simulation.advance(40)
        self.assertEqual(self.fields(simulation, "wav0.dis", "wav0.tim"), (50, 40))

    def test_code_cannot_change_fps_or_a_sounds_qty(self):
        # Typed, each answered 1C, a failed assignment, and changed nothing.
        sent = []
        simulation = Simulation(self.source, sending=sent.append)
        for line in ("video0.fps=30", "wav0.fps=30", "wav0.qty=30"):
            simulation.serial_input(line)
        self.assertEqual(sent.count(bytes([0x1C]) + END), 3)
        self.assertEqual(self.fields(simulation, "video0.fps", "wav0.fps", "wav0.qty"),
                         (12, 24, 7))

    def test_the_build_refuses_code_changing_them(self):
        # The Nextion Editor's compile refused each: "Assignment operation
        # failed". It compiled a sound's dis.
        code = self.source / "pages" / "page0.nx"
        for number, (line, what) in enumerate((("video0.fps=24", "fps of page0's video video0"),
                                               ("wav0.fps=24", "fps of page0's audio wav0"),
                                               ("wav0.qty=7", "qty of page0's audio wav0"))):
            with self.subTest(line=line):
                code.write_text(COUNTING.replace("sys0=sys0+1", "sys0=sys0+1\n  " + line),
                                encoding="utf-8", newline="\n")
                with self.assertRaisesRegex(NxwrightError, "the Nextion Editor refuses to "
                                            "assign to %s, which code cannot change" % what):
                    self.build("refused%d.HMI" % number)
        code.write_text(COUNTING.replace("sys0=sys0+1", "sys0=sys0+1\n  wav0.dis=50"),
                        encoding="utf-8", newline="\n")
        self.build("taken.HMI")


if __name__ == "__main__":
    unittest.main()
