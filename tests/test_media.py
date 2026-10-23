"""Animations, videos, and sounds: in source folders, dumps, and project files.

The fixtures (tests/fixtures/media/) come from a project the Editor saved
(installer 3.1.73), after its Gmov, Video, and Audio panels added two of
each to a project nxwright built with a picture and a font:
  - blink.gmov, GmovMaker's file of three frames 80 by 60, and
    blink.screen.gmov, the form the Editor made of it;
  - beep.wav and chirp.wav, two short WAV files, 16-bit mono and 8-bit
    stereo, as the Editor stored them, its own chunk added;
  - editor.main, the project's manifest.
clip.video is VideoBox's file of a clip 64 by 48, a second long. The Editor
kept the .video files it was given as they were, so a project holds it so.
"""
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest

from nxwright import NxwrightError
from nxwright.project.container import HmiContainer
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.dumper import ProjectDumper
from nxwright.project.project_writer import ProjectWriter
from nxwright.project.resources import (check_manifest_matches_blocks, parse_manifest,
                                        with_kind_in_order)
from nxwright.project.screen_models import model_named
from nxwright.language_server.completion import completions
from nxwright.source.definitions import definitions
from nxwright.language_server.file_texts import FileTexts
from nxwright.source.folder_index import FolderIndex, Place
from nxwright.language_server.hovers import hover
from nxwright.language_server.page_editing import properties
from nxwright.source.references import references
from nxwright.language_server.rename import rename
from nxwright.source.folder_check import check_folder
from nxwright.source.project_files import build, extract
from nxwright.source.source_folder import folder_reader, new_source_folder
from tests.test_folder_check import edited_app
from tests.test_project_writer import edit_text, sample_png

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "media"
FONT = Path(__file__).resolve().parent / "fixtures" / "fonts" / "Sans16.zi"
# The research project's screen.
SETTINGS = DeviceSettings(model_named("NX8048P050"), 0, "iso-8859-1")
# Its page's components that play: an animation, a video, and a sound.
PLAYERS = """
[[component]]
name = "gm0"
type = "gmov"
x = 20
y = 20
w = 80
h = 60
vid = "blink"

[[component]]
name = "video0"
type = "video"
x = 120
y = 20
w = 64
h = 48
vid = "clip"

[[component]]
name = "wav0"
type = "audio"
vid = "chirp"
"""


def folder_files(folder: Path) -> dict:
    """Returns {relative path: bytes} of every file under `folder`."""
    return {path.relative_to(folder).as_posix(): path.read_bytes()
            for path in folder.rglob("*") if path.is_file()}


class MediaFolderTestCase(unittest.TestCase):
    """A new source folder holding the fixtures `media` names, as `nxwright
    new` starts one, its page holding the `players` tables, an animation, a
    video, and a sound."""
    media = {"animations": ["blink"], "videos": ["clip"], "sounds": ["beep", "chirp"]}
    players = PLAYERS

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)
        self.source = self.folder / "source"
        new_source_folder(self.source, SETTINGS, "nextion")
        self.add_media(self.media)
        with open(self.source / "pages" / "page0.page.toml", "a", encoding="utf-8",
                  newline="\n") as page:
            page.write(self.players)

    def tearDown(self):
        self._folder.cleanup()

    def add_media(self, lists: dict):
        """Copies the fixtures each list names into the folder, under its name
        in the fixtures, and lists them in app.toml."""
        suffixes = {"animations": (".gmov", ".screen.gmov"), "videos": (".video",),
                    "sounds": (".wav",)}
        for kind, names in lists.items():
            (self.source / kind).mkdir(exist_ok=True)
            for name in names:
                for suffix in suffixes[kind]:
                    shutil.copyfile(FIXTURES / (name + suffix),
                                    self.source / kind / (name + suffix))
        self.edit_app(**lists)

    def edit_app(self, **values):
        """Sets keys of the folder's app.toml, as data (edited_app)."""
        app = self.source / "app.toml"
        app.write_text(edited_app(app.read_text(encoding="utf-8"),
                                  lambda data: data.update(values)),
                       encoding="utf-8", newline="\n")

    def build(self, name: str = "built.HMI") -> HmiContainer:
        build(self.source, self.folder / name)
        return HmiContainer.from_file(self.folder / name)

    def app(self, folder: Path) -> dict:
        return tomllib.loads((folder / "app.toml").read_text(encoding="utf-8"))


class BuildAndExtractTest(MediaFolderTestCase):

    def test_build_stores_each_file_as_a_block(self):
        blocks = self.build().blocks
        for block, fixture in (("0.gmovs", "blink.gmov"), ("0.gmov", "blink.screen.gmov"),
                               ("0.v", "clip.video"), ("0.wav", "beep.wav"),
                               ("1.wav", "chirp.wav")):
            with self.subTest(block=block):
                self.assertEqual(blocks[block], (FIXTURES / fixture).read_bytes())
        # The font a new folder starts with comes first.
        self.assertEqual(parse_manifest(blocks["main.HMI"]).resources,
                         [("zi", "0.zi"), ("gmov", "0.gmov"), ("v", "0.v"), ("wav", "0.wav"),
                          ("wav", "1.wav"), ("pa", "0.pa")])

    def test_the_manifest_is_the_editors(self):
        # The research project: a picture and a font, then two of each.
        (self.source / "fonts").mkdir(exist_ok=True)
        shutil.copyfile(FONT, self.source / "fonts" / "Sans16.zi")
        (self.source / "pictures").mkdir(exist_ok=True)
        (self.source / "pictures" / "red.png").write_bytes(sample_png("raw/01-red-8x8"))
        # Its one font, in place of the one a new folder starts with.
        self.edit_app(pictures=["red"], fonts=["Sans16"], animations=["blink", "blink2"],
                      videos=["clip", "clip2"])
        for kind, name, suffixes in (("animations", "blink", (".gmov", ".screen.gmov")),
                                     ("videos", "clip", (".video",))):
            for suffix in suffixes:
                shutil.copyfile(self.source / kind / (name + suffix),
                                self.source / kind / (name + "2" + suffix))
        self.assertEqual(self.build().blocks["main.HMI"], (FIXTURES / "editor.main").read_bytes())

    def test_extract_leaves_the_folder_as_it_was(self):
        before = folder_files(self.source)
        self.build()
        extract(self.folder / "built.HMI", self.source)
        self.assertEqual(folder_files(self.source), before)

    def test_extract_into_a_new_folder_names_them_by_id(self):
        self.build()
        fresh = self.folder / "fresh"
        extract(self.folder / "built.HMI", fresh)
        app = self.app(fresh)
        self.assertEqual((app["animations"], app["videos"], app["sounds"]),
                         (["animation-00"], ["video-00"], ["sound-00", "sound-01"]))
        for path, fixture in (("animations/animation-00.gmov", "blink.gmov"),
                              ("animations/animation-00.screen.gmov", "blink.screen.gmov"),
                              ("videos/video-00.video", "clip.video"),
                              ("sounds/sound-00.wav", "beep.wav"),
                              ("sounds/sound-01.wav", "chirp.wav")):
            with self.subTest(path=path):
                self.assertEqual((fresh / path).read_bytes(), (FIXTURES / fixture).read_bytes())
        page = (fresh / "pages" / "page0.page.toml").read_text(encoding="utf-8")
        for value in ('vid = "animation-00"', 'vid = "video-00"', 'vid = "sound-01"'):
            self.assertIn(value, page)

    def test_identical_ones_keep_their_names_in_order(self):
        shutil.copyfile(FIXTURES / "beep.wav", self.source / "sounds" / "beep2.wav")
        self.edit_app(sounds=["beep", "chirp", "beep2"])
        before = folder_files(self.source)
        self.build()
        extract(self.folder / "built.HMI", self.source)
        self.assertEqual(folder_files(self.source), before)

    def test_a_folder_without_media_lists_none(self):
        plain = self.folder / "plain"
        new_source_folder(plain, SETTINGS, "nextion")
        build(plain, self.folder / "plain.HMI")
        fresh = self.folder / "fresh"
        extract(self.folder / "plain.HMI", fresh)
        text = (fresh / "app.toml").read_text(encoding="utf-8")
        for key in ("animations", "videos", "sounds"):
            self.assertNotIn(key, text)
        self.assertFalse(any((fresh / key).exists() for key in ("animations", "videos", "sounds")))


class NamesTest(MediaFolderTestCase):
    """A `vid` names what its component plays: an animation, a video, or a sound."""

    def test_a_vid_given_by_number_builds_the_same(self):
        named = self.build("named.HMI").blocks["0.pa"]
        edit_text(self.source / "pages" / "page0.page.toml", 'vid = "chirp"', "vid = 1")
        self.assertEqual(self.build("numbered.HMI").blocks["0.pa"], named)

    def test_a_vid_naming_another_kind_is_refused(self):
        edit_text(self.source / "pages" / "page0.page.toml", 'vid = "blink"', 'vid = "chirp"')
        with self.assertRaisesRegex(NxwrightError, "vid: no animation is named chirp"):
            self.build()

    def test_a_vid_naming_nothing_is_refused(self):
        edit_text(self.source / "pages" / "page0.page.toml", 'vid = "chirp"', 'vid = "nosuch"')
        with self.assertRaisesRegex(NxwrightError, "vid: no sound is named nosuch"):
            self.build()

    def test_a_name_listed_twice_is_refused(self):
        self.edit_app(sounds=["beep", "Beep"])
        with self.assertRaisesRegex(NxwrightError, "sounds: beep and Beep are the same name"):
            self.build()

    def test_an_invalid_name_is_refused(self):
        self.edit_app(videos=["a clip"])
        with self.assertRaisesRegex(NxwrightError, "videos: 'a clip' is not a valid name"):
            self.build()

    def test_a_missing_file_is_refused_and_reported(self):
        (self.source / "animations" / "blink.screen.gmov").unlink()
        with self.assertRaisesRegex(NxwrightError, "blink.screen.gmov is missing"):
            self.build()

        findings = check_folder(folder_reader(self.source),
                                lambda path: (self.source / path).exists()).findings()
        self.assertEqual([finding.message for finding in findings],
                         ["animations/blink.screen.gmov is missing"])


class DumpTest(MediaFolderTestCase):
    """The dump of a project with media, and `nxwright write` from one."""

    def setUp(self):
        super().setUp()
        self.project = self.folder / "built.HMI"
        self.build()
        self.dump = self.folder / "dump"
        ProjectDumper(self.project, self.dump).dump()

    def test_the_dump_holds_each_block_as_a_file(self):
        for path, fixture in (("animations/00.gmov", "blink.gmov"),
                              ("animations/00.screen.gmov", "blink.screen.gmov"),
                              ("videos/00.video", "clip.video"), ("sounds/01.wav", "chirp.wav")):
            with self.subTest(path=path):
                self.assertEqual((self.dump / path).read_bytes(), (FIXTURES / fixture).read_bytes())
        self.assertEqual((self.dump / "animations" / "index.txt").read_text(encoding="utf-8"),
                         "animation  block      bytes\n00         0.gmovs    8057\n"
                         "00         0.gmov     12829\n")

    def test_an_animation_without_its_gmovmaker_file_is_refused(self):
        container = HmiContainer.from_file(self.project)
        del container.blocks["0.gmovs"]
        with self.assertRaisesRegex(NxwrightError, "do not pair up with the listed .gmov blocks"):
            check_manifest_matches_blocks(parse_manifest(container.blocks["main.HMI"]),
                                          container.blocks)

    def test_write_adds_and_removes_by_their_bytes(self):
        # The sounds swap places, and the animation goes.
        beep, chirp = (self.dump / "sounds" / "00.wav", self.dump / "sounds" / "01.wav")
        first = beep.read_bytes()
        beep.write_bytes(chirp.read_bytes())
        chirp.write_bytes(first)
        for path in (self.dump / "animations").glob("00.*"):
            path.unlink()
        written = self.folder / "written.HMI"
        changes = ProjectWriter(self.project, self.dump, written).write()
        self.assertIn("Removed animation block 0.gmov", changes)
        container = HmiContainer.from_file(written)
        manifest = parse_manifest(container.blocks["main.HMI"])
        self.assertEqual(manifest.block_names("wav"), ["1.wav", "0.wav"])
        self.assertEqual(manifest.block_names("gmov"), [])
        self.assertNotIn("0.gmovs", container.blocks)

    def test_write_adds_an_animation_with_both_its_blocks(self):
        # A second copy of the animation: the first matches the project's,
        # the second is added, its two blocks under one number.
        for suffix in (".gmov", ".screen.gmov"):
            shutil.copyfile(self.dump / "animations" / ("00" + suffix),
                            self.dump / "animations" / ("01" + suffix))
        written = self.folder / "written.HMI"
        changes = ProjectWriter(self.project, self.dump, written).write()
        self.assertIn("Added animation 1 as block 1.gmov", changes)
        container = HmiContainer.from_file(written)
        self.assertEqual(parse_manifest(container.blocks["main.HMI"]).block_names("gmov"),
                         ["0.gmov", "1.gmov"])
        self.assertEqual((container.blocks["1.gmovs"], container.blocks["1.gmov"]),
                         ((FIXTURES / "blink.gmov").read_bytes(),
                          (FIXTURES / "blink.screen.gmov").read_bytes()))

    def test_write_puts_a_first_font_where_the_editor_lists_it(self):
        # A change of behaviour: write put a project's first font last.
        (self.dump / "fonts" / "00.zi").write_bytes(FONT.read_bytes())
        written = self.folder / "written.HMI"
        ProjectWriter(self.project, self.dump, written).write()
        resources = parse_manifest(HmiContainer.from_file(written).blocks["main.HMI"]).resources
        self.assertEqual([kind for kind, _ in resources], ["zi", "gmov", "v", "wav", "wav", "pa"])

    def test_a_first_resource_of_a_kind_goes_where_the_editor_lists_it(self):
        resources = [("i", "0.i"), ("zi", "0.zi"), ("pa", "0.pa")]
        self.assertEqual(with_kind_in_order(resources, "wav", ["0.wav"]),
                         [("i", "0.i"), ("zi", "0.zi"), ("wav", "0.wav"), ("pa", "0.pa")])
        self.assertEqual(with_kind_in_order([("pa", "0.pa")], "zi", ["0.zi"]),
                         [("zi", "0.zi"), ("pa", "0.pa")])


class CodeAndLanguageServerTest(MediaFolderTestCase):
    """Code names media as it names pictures, and the language server knows
    their names as it knows pictures'."""

    CODE = ("on page0.load:\n  gm0.vid=@animation(blink)\n  video0.vid=@video(clip)\n"
            "  wav0.vid=@sound(chirp)\n")

    def setUp(self):
        super().setUp()
        (self.source / "pages" / "page0.nx").write_text(self.CODE, encoding="utf-8", newline="\n")
        self.documents = FileTexts()

    def index(self) -> FolderIndex:
        return FolderIndex(self.source, self.documents.read)

    def find(self, path: str, needle: str, inside: str) -> Place:
        """Returns the place of `inside` within the first `needle` in `path`."""
        for number, line in enumerate((self.source / path).read_text(encoding="utf-8").split("\n")):
            if needle in line:
                column = line.index(needle) + needle.index(inside)
                return Place(path, number, column, column + len(inside))
        raise AssertionError("%r not in %s" % (needle, path))

    def test_code_names_them_by_their_ids(self):
        self.build()
        ProjectDumper(self.folder / "built.HMI", self.folder / "dump").dump()
        page = next((self.folder / "dump" / "pages").glob("*.txt")).read_text(encoding="utf-8")
        for line in ("| gm0.vid=0", "| video0.vid=0", "| wav0.vid=1"):
            self.assertIn(line, page)

    def test_a_vid_is_offered_the_names_of_its_kind(self):
        page = "pages/page0.page.toml"
        for needle, offered in (('vid = "blink"', ["blink"]), ('vid = "clip"', ["clip"]),
                                ('vid = "chirp"', ["beep", "chirp"])):
            place = self.find(page, needle, '"')
            with self.subTest(needle=needle):
                self.assertEqual([item.label for item in completions(
                    self.index(), page, place.line, place.end)], offered)

    def test_a_vid_and_a_reference_lead_to_the_name_in_app_toml(self):
        blink, chirp = (self.find("app.toml", '"%s"' % name, name) for name in ("blink", "chirp"))
        place = self.find("pages/page0.page.toml", 'vid = "blink"', "blink")
        self.assertEqual(definitions(self.index(), place.path, place.line, place.start), [blink])
        place = self.find("pages/page0.nx", "@sound(chirp)", "chirp")
        self.assertEqual(definitions(self.index(), place.path, place.line, place.start), [chirp])

    def test_references_and_hover_of_a_name(self):
        blink = self.find("app.toml", '"blink"', "blink")
        found = references(self.index(), blink.path, blink.line, blink.start,
                           with_declarations=False)
        self.assertEqual(found, [self.find("pages/page0.nx", "@animation(blink)", "blink"),
                                 self.find("pages/page0.page.toml", 'vid = "blink"', "blink")])
        place = self.find("pages/page0.nx", "@animation(blink)", "blink")
        self.assertEqual(hover(self.index(), place.path, place.line, place.start),
                         "Animation `blink`, in `animations/blink.gmov` and "
                         "`animations/blink.screen.gmov`")

    def test_the_properties_panel_chooses_among_the_names(self):
        found = properties(self.index(), self.documents.folder_reader(self.source), "page0",
                           "wav0")
        vid = next(entry for entry in found["attributes"] if entry["name"] == "vid")
        self.assertEqual((vid["kind"], vid["value"], vid["choices"]),
                         ("sound", "chirp", ["none", "beep", "chirp"]))

    def test_a_name_is_renamed_by_hand(self):
        place = self.find("pages/page0.nx", "@animation(blink)", "blink")
        with self.assertRaisesRegex(NxwrightError, "animations, videos, sounds, and files are "
                                                   "renamed by hand"):
            rename(self.index(), place.path, place.line, place.start, "wink",
                   self.documents.folder_reader(self.source), lambda path: True)


if __name__ == "__main__":
    unittest.main()
