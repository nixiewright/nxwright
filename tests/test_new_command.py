"""nxwright new: its questions, and the source folder it starts."""
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import tomllib
import unittest

from nxwright import NxwrightError
from nxwright.cli import main, new_folder_name, new_folder_settings
from nxwright.language.code_lines import split_line
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.dumper import ProjectDumper
from nxwright.project.screen_models import model_named
from nxwright.project.zi_font import decode_font
from nxwright.source.project_files import build
from nxwright.source.source_folder import folder_device_settings, new_source_folder
from tests.test_build_checks import add_component

NO_OPTIONS = Namespace(screen=None, rotation=None, encoding=None, language=None)


def answering(*answers: str):
    """Returns an ask function giving `answers` in turn, then ending its input,
    and the list of questions it was asked."""
    questions, remaining = [], list(answers)

    def ask(question: str) -> str:
        questions.append(question)
        if not remaining:
            raise EOFError
        return remaining.pop(0)
    return ask, questions


class NewFolderSettingsTest(unittest.TestCase):

    def settings(self, arguments: Namespace, ask) -> tuple:
        # A wrong answer prints the choices; keep that out of the test output.
        with redirect_stdout(io.StringIO()):
            return new_folder_settings(arguments, ask)

    def test_options_are_not_asked_again(self):
        ask, questions = answering()
        arguments = Namespace(screen="NX3224T024", rotation=270, encoding="utf-8",
                              language="nextion")
        self.assertEqual(self.settings(arguments, ask),
                         (DeviceSettings(model_named("NX3224T024"), 270, "utf-8"), "nextion"))
        self.assertEqual(questions, [])

    def test_answers(self):
        ask, questions = answering("NX8048P070", "180", "koi8-r", "nextion")
        self.assertEqual(self.settings(NO_OPTIONS, ask),
                         (DeviceSettings(model_named("NX8048P070"), 180, "koi8-r"), "nextion"))
        self.assertEqual(len(questions), 4)

    def test_a_wrong_answer_is_asked_again_and_an_empty_one_is_the_default(self):
        ask, questions = answering("NX9999X999", " NX8048P050 ", "45", "", "", "")
        self.assertEqual(self.settings(NO_OPTIONS, ask),
                         (DeviceSettings(model_named("NX8048P050"), 0, "iso-8859-1"), "nxlang"))
        self.assertEqual(len(questions), 6)

    def test_without_anyone_to_ask_the_defaults_apply(self):
        arguments = Namespace(screen="NX4832F035", rotation=None, encoding=None, language=None)
        for ask in (None, answering()[0]):
            with self.subTest(ask=ask):
                self.assertEqual(
                    self.settings(arguments, ask),
                    (DeviceSettings(model_named("NX4832F035"), 0, "iso-8859-1"), "nxlang"))

    def test_without_anyone_to_ask_the_screen_model_is_refused(self):
        for ask in (None, answering()[0]):
            with self.subTest(ask=ask):
                with self.assertRaisesRegex(NxwrightError, "give one with --screen"):
                    self.settings(NO_OPTIONS, ask)


class NewSourceFolderTest(unittest.TestCase):

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)

    def tearDown(self):
        self._folder.cleanup()

    def built_page(self, source: Path) -> str:
        """Builds `source`, and returns the dump of its one page."""
        built = self.folder / "built.HMI"
        build(source, built)
        ProjectDumper(built, self.folder / "dump").dump()
        return (self.folder / "dump" / "pages" / "00-page0.txt").read_text(encoding="utf-8")

    def test_the_command_starts_a_folder_that_builds(self):
        source = self.folder / "app"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["new", str(source), "--screen", "NX8048P050", "--rotation",
                                   "90", "--encoding", "utf-8", "--language", "nxlang"]), 0)
        self.assertEqual(folder_device_settings(source),
                         DeviceSettings(model_named("NX8048P050"), 90, "utf-8"))
        page = self.built_page(source)
        # The screen turned a quarter: the page is as wide as the screen is high.
        self.assertIn("  w = 480\n  h = 800\n", page)
        # The page header repeats the encoding: utf-8 is 24 (0x18).
        self.assertIn("header_40 = 01440218", page)

    def test_the_apps_name(self):
        # Its own setting, the folder's name by default, so that renaming the
        # folder later keeps it.
        settings = DeviceSettings(model_named("NX3224T024"), 0, "iso-8859-1")
        named = self.folder / "app"
        new_source_folder(named, settings, "nextion", "Thermostat: v2")
        self.assertEqual(tomllib.loads((named / "app.toml").read_text(encoding="utf-8"))["name"],
                         "Thermostat: v2")
        plain = self.folder / "clock"
        new_source_folder(plain, settings, "nextion")
        self.assertEqual(tomllib.loads((plain / "app.toml").read_text(encoding="utf-8"))["name"],
                         "clock")
        with self.assertRaisesRegex(NxwrightError, "name must be a text of one line"):
            new_source_folder(self.folder / "spaced", settings, "nextion", " Clock")
        self.assertFalse((self.folder / "spaced").exists())
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["new", str(self.folder / "cli"), "--screen", "NX8048P050",
                                   "--language", "nextion", "--name", "Kitchen"]), 0)
        self.assertEqual(tomllib.loads((self.folder / "cli" / "app.toml")
                                       .read_text(encoding="utf-8"))["name"], "Kitchen")

    def test_the_name_asked(self):
        # Asked with the others, the folder's name by default.
        ask, questions = answering("  Kitchen clock  ")
        self.assertEqual(new_folder_name(Namespace(name=None), ask, Path("x") / "clock"),
                         "Kitchen clock")
        self.assertEqual(questions, ["App name [clock]: "])
        ask, _ = answering("")
        self.assertEqual(new_folder_name(Namespace(name=None), ask, Path("clock")), "clock")
        self.assertEqual(new_folder_name(Namespace(name=None), None, Path("clock")), "clock")
        ask, questions = answering()
        self.assertEqual(new_folder_name(Namespace(name="Given"), ask, Path("clock")), "Given")
        self.assertEqual(questions, [])

    def test_the_command_says_what_the_font_lacks(self):
        source = self.folder / "koi8"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as said:
            self.assertEqual(main(["new", str(source), "--screen", "NX8048P050", "--encoding",
                                   "koi8-r", "--language", "nextion"]), 0)
        self.assertEqual(said.getvalue(),
                         "nxwright new: warning: the font NotoSans24 is drawn from Noto Sans, "
                         "which lacks 56 characters of koi8-r, such as '─' (U+2500): text "
                         "in them shows the font's first character, the space, in their place\n")

    def test_a_screen_not_turned_keeps_its_size(self):
        source = self.folder / "app"
        new_source_folder(source, DeviceSettings(model_named("NX3224T024"), 180, "iso-8859-1"),
                          "nextion")
        # The Editor holds this screen upright: 240 wide, 320 high.
        self.assertIn("  w = 240\n  h = 320\n", self.built_page(source))

    def test_declares_sys0_to_sys2_as_the_editors_new_project_does(self):
        # The Editor refuses code naming them unless program.nx declares them.
        editors = Path(__file__).resolve().parent / "fixtures" / "every-component" / "program.s"
        declaration = split_line(editors.read_text(encoding="utf-8").splitlines()[1], 2)[1]
        source = self.folder / "app"
        new_source_folder(source, DeviceSettings(model_named("NX3224T024"), 0, "iso-8859-1"),
                          "nextion")
        code = [split_line(line, number)[1] for number, line in
                enumerate((source / "program.nx").read_text(encoding="utf-8").splitlines(), 1)]
        self.assertEqual(declaration, "int sys0=0,sys1=0,sys2=0")
        self.assertEqual([line for line in code if line][0], declaration)

    def test_starts_with_a_font_where_nxwright_draws_one(self):
        # The Editor refuses a text whose font the project lacks, and so does
        # the build: a first text builds in the font the folder starts with.
        # In koi8-r, Noto Sans lacks the box-drawing characters, which the
        # font leaves out, as a warning says; in utf-8, it is of U+0000 to
        # U+00FF; in the two-byte encodings, it lacks the Chinese characters,
        # the kana, and the Hangul, which the font leaves empty.
        lacks = ("the font NotoSans24 is drawn from Noto Sans, which lacks %d characters of %s, "
                 "such as '\\u3000' (U+3000): text in them shows nothing in their place, the "
                 "height wide")
        for encoding, fonts, warning in (
                ("iso-8859-1", ["NotoSans24"], None),
                ("koi8-r", ["NotoSans24"], "the font NotoSans24 is drawn from Noto Sans, which "
                                           "lacks 56 characters of koi8-r, such as '─' "
                                           "(U+2500): text in them shows the font's first "
                                           "character, the space, in their place"),
                ("utf-8", ["NotoSans24"], None),
                ("gb2312", ["NotoSans24"], lacks % (7282, "gb2312")),
                ("big5", ["NotoSans24"], lacks % (13578, "big5")),
                ("shift-jis", ["NotoSans24"], lacks % (6741, "shift-jis")),
                ("ks_c_5601-1987", ["NotoSans24"], lacks % (3132, "ks_c_5601-1987"))):
            with self.subTest(encoding=encoding):
                source = self.folder / encoding
                self.assertEqual(new_source_folder(
                    source, DeviceSettings(model_named("NX3224T024"), 90, encoding), "nextion"),
                    warning)
                app = tomllib.loads((source / "app.toml").read_text(encoding="utf-8"))
                self.assertEqual(app["fonts"], fonts)
                self.assertEqual([path.stem for path in (source / "fonts").glob("*.zi")], fonts)
        font = decode_font((self.folder / "iso-8859-1" / "fonts" / "NotoSans24.zi").read_bytes())
        self.assertEqual((font.height, font.encoding, font.rotation), (24, "iso-8859-1", 90))
        utf8 = decode_font((self.folder / "utf-8" / "fonts" / "NotoSans24.zi").read_bytes())
        self.assertEqual((utf8.encoding, sorted(utf8.characters), utf8.advances),
                         ("utf-8", list(range(0x100)), None))
        add_component(self.folder / "iso-8859-1" / "pages" / "page0.page.toml", "t0", "x")
        self.built_page(self.folder / "iso-8859-1")

    def test_a_text_without_a_font_is_refused(self):
        # A folder whose one font was taken out.
        source = self.folder / "app"
        new_source_folder(source, DeviceSettings(model_named("NX3224T024"), 0, "iso-8859-1"),
                          "nextion")
        app = source / "app.toml"
        app.write_text(app.read_text(encoding="utf-8").replace(
            'fonts = [\n    "NotoSans24",\n]', "fonts = []"), encoding="utf-8", newline="\n")
        (source / "fonts" / "NotoSans24.zi").unlink()
        add_component(source / "pages" / "page0.page.toml", "t0", "x")
        with self.assertRaisesRegex(NxwrightError, 'component t0: its font is number 0, and the '
                                    'project has no fonts; the Nextion Editor refuses it, saying '
                                    '"Invalid Font ID". `nxwright font` adds one'):
            build(source, self.folder / "built.HMI")

    def test_refuses_a_folder_that_is_not_empty(self):
        source = self.folder / "app"
        source.mkdir()
        (source / "notes.txt").write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(NxwrightError, "is not empty"):
            new_source_folder(source, DeviceSettings(model_named("NX3224T024"), 0, "iso-8859-1"),
                              "nxlang")
        self.assertEqual([path.name for path in source.iterdir()], ["notes.txt"])

    def test_refuses_an_unknown_encoding_before_writing(self):
        source = self.folder / "app"
        with self.assertRaisesRegex(NxwrightError, "encoding"):
            new_source_folder(source, DeviceSettings(model_named("NX3224T024"), 0, "latin-9"),
                              "nxlang")
        self.assertFalse(source.exists())


if __name__ == "__main__":
    unittest.main()
