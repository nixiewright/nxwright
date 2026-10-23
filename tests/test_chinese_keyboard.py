"""nxwright's Chinese keyboard (source/keyboards.py, keybdAP, `key` 4): laid
out for every screen, added to a gb2312 folder with its font, and run in the
simulator from a pinyin table the tests build (tests/test_pinyin.py)."""
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import io
import itertools
from pathlib import Path
import re
import tempfile
import tomllib
import unittest

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.font_drawing import draw_font_block
from nxwright.project.screen_copy import ROTATIONS
from nxwright.project.screen_models import MODELS, model_named
from nxwright.project.truetype import NOTO_SANS, TrueTypeFont
from nxwright.project.zi_font import decode_font, encode_font
from nxwright.source.keyboards import (CHINESE_INPUT, chinese_font_height, keyboard,
                                       typeface_widths)
from nxwright.source.folder_check import check_folder
from nxwright.source.lint import ERROR
from nxwright.source.project_files import build
from nxwright.source.source_folder import folder_reader, new_source_folder, read_app
from nxwright.source.resource_adding import add_font_file
from nxwright.source.keyboard_adding import add_keyboard, chinese_keyboard_fonts
from nxwright.testing.simulation import Simulation
from tests.test_folder_check import edited_app
from tests.test_keyboards import caller, inside, overlap, page_size
from tests.test_pinyin import MEI, SYLLABLES, TABLE
from tests.test_truetype import GLYPHS, truetype_file
from tests.test_zi_font import gb2312_font, gb2312_glyphs

# The letter keys typing m, e, i, and n, a, by their place.
M, E, I, N, A = "key3_7", "key1_3", "key1_8", "key3_6", "key2_1"


def characters(data: bytes) -> list:
    """The gb2312 characters `data` holds, as the simulator keeps texts."""
    return [data[index:index + 2].decode("gb2312") for index in range(0, len(data), 2)]


def chinese_typeface(characters_held: str) -> bytes:
    """A TrueType file whose ascii letters, digits, and signs, and whose
    `characters_held`, are a square: a typeface with a few Chinese
    characters."""
    held = {chr(code): 1 for code in range(0x20, 0x7f)}
    held.update({character: 1 for character in characters_held})
    return truetype_file(GLYPHS, held, {1: "Test Hanzi", 2: "Regular"})


def chinese_folder(root: Path, language: str = "nextion", encoding: str = "gb2312",
                   model: str = "NX8048P050", font_height: int = 16) -> Path:
    """Writes a source folder whose first page holds a text of global scope
    bound to the Chinese keyboard, `t0` of 6 bytes at most, and whose font
    `Zh`, in gb2312, is the tests' own (tests/test_zi_font.py)."""
    folder = root / ("%s-%s-%s" % (language, encoding, model))
    new_source_folder(folder, DeviceSettings(model_named(model), 0, encoding), language)
    font = root / ("Zh%d.zi" % font_height)
    font.write_bytes(gb2312_font(font_height))
    if encoding == "gb2312":
        add_font_file(folder, font, "Zh")
    page = folder / "pages" / "page0.page.toml"
    page.write_text(page.read_text(encoding="utf-8")
                    + caller("t0", "text", 0, 4, txt="", txt_maxl=6), encoding="utf-8")
    (folder / "program.nx").write_text("page page0\n", encoding="utf-8")
    return folder


class LayoutTest(unittest.TestCase):

    def test_on_every_screen(self):
        typeface = typeface_widths(TrueTypeFont(NOTO_SANS.read_bytes()))
        for model, rotation in itertools.product(MODELS, ROTATIONS):
            width, height = page_size(model, rotation)
            with self.subTest(screen=model.name, rotation=rotation):
                font_height = chinese_font_height(width, height, typeface)
                self.assertTrue(16 <= font_height <= 24, font_height)
                made = keyboard(CHINESE_INPUT, width, height, ("Zh", font_height))
                self.assertEqual((made.page, made.font_name, made.font_height),
                                 ("keybdAP", "Zh", font_height))
                page = tomllib.loads(made.page_toml)
                self.assertEqual(page["page"]["system_page"], CHINESE_INPUT)
                whole = {"x": 0, "y": 0, "w": width, "h": height}
                placed = {component["name"]: component for component in page["component"]
                          if "x" in component}
                for name, component in placed.items():
                    self.assertGreaterEqual(min(component["w"], component["h"]), 2, name)
                    self.assertTrue(inside(component, whole), name)
                shown = [component for component in placed.values()
                         if component["type"] == "button"
                         or component["name"] in ("fieldbox", "syllable")]
                for first, second in itertools.combinations(shown, 2):
                    self.assertFalse(overlap(first, second), (first["name"], second["name"]))
                # The Nextion Editor's compile warns of hotspots that overlap.
                hotspots = [component for component in placed.values()
                            if component["type"] == "hotspot"]
                self.assertEqual(len(hotspots), 3)
                for first, second in itertools.combinations(hotspots, 2):
                    self.assertFalse(overlap(first, second), (first["name"], second["name"]))
                self.assertEqual([name for name in placed if name.startswith("candidate")],
                                 ["candidate%d" % number for number in range(1, 7)])


    def test_each_statement_has_one_operator_at_most(self):
        # So that the Editor's order, left to right, and nxlang's agree.
        operator = re.compile(r"\+\+|--|[-+*/]=|==|!=|<=|>=|&&|\|\||[-+*/%<>]")
        for line in keyboard(CHINESE_INPUT, 800, 480, ("Zh", 16)).code.splitlines():
            statement = re.sub(r'"[^"]*"', '""', line.split("//")[0])
            statement = re.sub(r"([=(,])-(?=\d)", r"\1", statement)
            with self.subTest(line=line):
                self.assertLessEqual(len(operator.findall(statement)), 1)

    def test_its_memory_on_every_series(self):
        # The build's check of each page's memory, on a model of each series.
        with tempfile.TemporaryDirectory() as temporary:
            for model in ("NX3224T024", "NX3224K024", "NX3224F024", "NX4848E021",
                          "NX4827P043"):
                with self.subTest(model=model):
                    folder = chinese_folder(Path(temporary), model=model)
                    add_keyboard(folder, CHINESE_INPUT, font="Zh")
                    result = check_folder(folder_reader(folder),
                                          lambda path, root=folder: (root / path).is_file())
                    errors = [finding for finding in result.findings()
                              if finding.severity == ERROR]
                    self.assertEqual(errors, [])

class KeyboardTestCase(unittest.TestCase):
    """The Chinese keyboard in a folder of each language, its font Zh."""

    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name)
        cls.folders = {}
        for language in ("nextion", "nxlang"):
            folder = chinese_folder(cls.root, language)
            add_keyboard(folder, CHINESE_INPUT, font="Zh")
            cls.folders[language] = folder

    def simulations(self, table=TABLE):
        """Yields a new simulation of each folder, the keyboard opened, within
        a subtest."""
        for language, folder in self.folders.items():
            with self.subTest(language=language):
                simulation = Simulation(folder, pinyin_table=table)
                self.tap(simulation, "t0")
                self.assertEqual(simulation.page, "keybdAP")
                yield simulation

    @staticmethod
    def tap(simulation: Simulation, *names: str):
        for name in names:
            simulation.press(name)
            simulation.release()

    @staticmethod
    def candidates(simulation: Simulation) -> list:
        values = simulation.values()
        return [values["candidate%d.txt" % number] for number in range(1, 7)]


class ChineseKeyboardTest(KeyboardTestCase):

    def test_each_folder_builds(self):
        for language, folder in self.folders.items():
            with self.subTest(language=language):
                build(folder, self.root / ("%s.HMI" % language))

    def test_a_syllable_shows_its_candidates(self):
        mei = characters(MEI)
        for simulation in self.simulations():
            self.tap(simulation, M, E, I)
            self.assertEqual(simulation.values()["syllable.txt"], "mei")
            self.assertEqual(self.candidates(simulation), mei[:6])

    def test_paging_through_the_candidates(self):
        mei = characters(MEI)
        for simulation in self.simulations():
            self.tap(simulation, M, E, I, "next", "next", "next", "next")
            self.assertEqual(self.candidates(simulation), mei[24:] + ["", "", "", ""])
            # Past the last six, next does nothing.
            self.tap(simulation, "next")
            self.assertEqual(self.candidates(simulation), mei[24:] + ["", "", "", ""])
            self.tap(simulation, "previous")
            self.assertEqual(self.candidates(simulation), mei[18:24])
            self.tap(simulation, "previous", "previous", "previous", "previous")
            self.assertEqual(self.candidates(simulation), mei[:6])

    def test_a_candidate_is_typed_and_the_syllable_emptied(self):
        mei = characters(MEI)
        for simulation in self.simulations():
            self.tap(simulation, M, E, I, "candidate2")
            values = simulation.values()
            self.assertEqual((values["field.txt"], values["syllable.txt"]), (mei[1], ""))
            self.assertEqual(self.candidates(simulation), [""] * 6)
            # An empty candidate types nothing.
            self.tap(simulation, "candidate1")
            self.assertEqual(simulation.values()["field.txt"], mei[1])
            self.tap(simulation, "ok")
            self.assertEqual((simulation.page, simulation.values()["t0.txt"]),
                             ("page0", mei[1]))

    def test_a_chinese_character_is_typed_whole_or_not_at_all(self):
        # t0 holds 6 bytes: a letter, then two characters, then no third.
        mei = characters(MEI)
        for simulation in self.simulations():
            self.tap(simulation, "mode", A, "mode", "mode", "mode")
            self.tap(simulation, M, E, I, "candidate1", M, E, I, "candidate2")
            self.tap(simulation, M, E, I, "candidate3")
            self.assertEqual(simulation.values()["field.txt"], "a" + mei[0] + mei[1])

    def test_delete_takes_a_letter_then_a_character(self):
        mei = characters(MEI)
        for simulation in self.simulations():
            self.tap(simulation, M, E, I, "candidate1", M, E, "back")
            values = simulation.values()
            self.assertEqual((values["syllable.txt"], values["field.txt"]), ("m", mei[0]))
            # "m" alone has one candidate.
            self.assertEqual(self.candidates(simulation),
                             characters(SYLLABLES["m"]) + [""] * 5)
            self.tap(simulation, "back", "back")
            values = simulation.values()
            self.assertEqual((values["syllable.txt"], values["field.txt"]), ("", ""))

    def test_a_syllable_holds_six_letters(self):
        for simulation in self.simulations():
            self.tap(simulation, M, E, I, M, E, I, N)
            self.assertEqual(simulation.values()["syllable.txt"], "meimei")

    def test_the_mode_key(self):
        # Pinyin, small letters, capitals, then numbers and signs; each
        # change empties the syllable.
        for simulation in self.simulations():
            self.tap(simulation, M, "mode")
            values = simulation.values()
            self.assertEqual((values["syllable.txt"], values["mode.txt"], values["key1_1.txt"]),
                             ("", "ABC", "q"))
            self.tap(simulation, "key1_1", "mode", "key1_1", "mode", "key1_1")
            values = simulation.values()
            self.assertEqual((values["field.txt"], values["mode.txt"]), ("qQ1", "中"))
            self.tap(simulation, "mode", M)
            self.assertEqual(simulation.values()["syllable.txt"], "m")

    def test_without_a_pinyin_table_no_candidates_show(self):
        for simulation in self.simulations(table=None):
            self.tap(simulation, M, E, I)
            self.assertEqual(self.candidates(simulation), [""] * 6)


class AddingTest(unittest.TestCase):

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.folder = chinese_folder(self.root)

    def app(self) -> dict:
        return tomllib.loads((self.folder / "app.toml").read_text(encoding="utf-8"))

    def test_a_font_the_folder_holds(self):
        self.assertEqual(add_keyboard(self.folder, CHINESE_INPUT, font="Zh"),
                         ("keybdAP", "Zh", None))
        self.assertEqual(self.app()["pages"][-1], "keybdAP")
        self.assertEqual(self.app()["fonts"].count("Zh"), 1)

    def test_a_font_without_the_keys_labels_is_warned_of(self):
        # Its ascii characters drawn empty: the letter keys would show nothing.
        glyphs = [replace(glyph, coverages=(0,) * len(glyph.coverages)) if glyph.code < 0x80
                  else glyph for glyph in gb2312_glyphs(16)]
        font = self.root / "Hanzi16.zi"
        font.write_bytes(encode_font("Hanzi", "gb2312", 16, 0, glyphs))
        add_font_file(self.folder, font, "Hanzi")
        warning = add_keyboard(self.folder, CHINESE_INPUT, font="Hanzi")[2]
        self.assertRegex(warning, "the font Hanzi has nothing to show for some of the keys' "
                                  "labels, such as '.'. Those keys will look empty")

    def test_a_font_drawn_from_a_typeface(self):
        typeface = self.root / "hanzi.ttf"
        typeface.write_bytes(chinese_typeface("".join(characters(MEI))))
        page, font, warning = add_keyboard(self.folder, CHINESE_INPUT, typeface=typeface)
        made = decode_font((self.folder / "fonts" / (font + ".zi")).read_bytes())
        self.assertEqual((page, font, made.encoding), ("keybdAP", "TestHanzi%d" % made.height,
                                                       "gb2312"))
        self.assertTrue(16 <= made.height <= 24)
        self.assertIn("the typeface file lacks", warning)
        self.assertEqual(self.app()["fonts"][-1], font)

    def test_the_fonts_it_takes(self):
        # Of the folder's fonts, only Zh: not the Noto Sans a new folder starts
        # with, which has no Chinese characters, nor one too tall, nor one in
        # iso-8859-1. A folder in another encoding takes none.
        tall = self.root / "tall.zi"
        tall.write_bytes(gb2312_font(60))
        add_font_file(self.folder, tall, "Tall")
        latin = self.root / "Latin16.zi"
        latin.write_bytes(draw_font_block("Latin16", TrueTypeFont(NOTO_SANS.read_bytes()), 16,
                                          "iso-8859-1", 0))
        add_font_file(self.folder, latin, "Latin16")
        self.assertEqual(self.app()["fonts"], ["NotoSans24", "Zh", "Tall", "Latin16"])
        self.assertEqual(chinese_keyboard_fonts(self.folder, self.app()), ["Zh"])
        other = chinese_folder(self.root, encoding="iso-8859-1")
        self.assertEqual(chinese_keyboard_fonts(other, read_app(other)), [])

    def test_refusals(self):
        typeface = self.root / "hanzi.ttf"
        typeface.write_bytes(chinese_typeface("".join(characters(MEI))))
        other = chinese_folder(self.root, encoding="iso-8859-1")
        tall = self.root / "tall.zi"
        tall.write_bytes(gb2312_font(60))
        add_font_file(self.folder, tall, "Tall")
        latin = self.root / "Latin16.zi"
        latin.write_bytes(draw_font_block("Latin16", TrueTypeFont(NOTO_SANS.read_bytes()), 16,
                                          "iso-8859-1", 0))
        add_font_file(self.folder, latin, "Latin16")
        cases = [
            ((other, CHINESE_INPUT), {"font": "Zh"}, "only works in a gb2312 folder, and this "
                                                     "one is in iso-8859-1"),
            ((self.folder, CHINESE_INPUT), {}, "needs a font with Chinese characters"),
            ((self.folder, CHINESE_INPUT), {"font": "Zh", "typeface": typeface},
             "takes --typeface or --font, not both"),
            ((self.folder, CHINESE_INPUT), {"font": "Nope"}, "the folder has no font Nope"),
            ((self.folder, CHINESE_INPUT), {"font": "Latin16"},
             "Latin16 is in iso-8859-1, not gb2312"),
            ((self.folder, CHINESE_INPUT), {"font": "NotoSans24"},
             "NotoSans24 holds no Chinese characters"),
            ((self.folder, CHINESE_INPUT), {"font": "Tall"},
             "Tall is 60 pixels tall, but the keys fit a font of \\d+ pixels at most"),
            ((self.folder, CHINESE_INPUT), {"typeface": NOTO_SANS},
             "has no Chinese characters"),
            ((self.folder, "keyboard"), {"font": "Zh"},
             "only the Chinese keyboard takes --typeface or --font"),
        ]
        for (folder, kind), options, message in cases:
            with self.subTest(message):
                pages = self.app()["pages"]
                with self.assertRaisesRegex(NxwrightError, message):
                    add_keyboard(folder, kind, **options)
                self.assertEqual(self.app()["pages"], pages)
        # A typeface whose font's name the folder has: use that font instead.
        page, font, _ = add_keyboard(self.folder, CHINESE_INPUT, typeface=typeface)
        (self.folder / "pages" / "keybdAP.page.toml").unlink()
        (self.folder / "pages" / "keybdAP.nx").unlink()
        app = (self.folder / "app.toml").read_text(encoding="utf-8")
        (self.folder / "app.toml").write_text(
            edited_app(app, lambda app: app["pages"].remove("keybdAP")), encoding="utf-8")
        with self.assertRaisesRegex(NxwrightError, "the folder has a font %s already: add the "
                                                   "keyboard with that font instead" % font):
            add_keyboard(self.folder, CHINESE_INPUT, typeface=typeface)

    def test_the_command(self):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(["keyboard", str(self.folder), CHINESE_INPUT, "--font", "Zh"])
        self.assertEqual(code, 0, errors.getvalue())
        size = (self.folder / "fonts" / "Zh.zi").stat().st_size
        self.assertIn("Added the keyboard page keybdAP, with the font Zh (%d KB), to %s"
                      % (round(size / 1024), self.folder), output.getvalue())
