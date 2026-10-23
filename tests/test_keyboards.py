"""nxwright's keyboard pages (nxwright/source/keyboards.py): laid out for
every screen, built in both languages, and run in the simulator."""
import itertools
from pathlib import Path
import re
import tempfile
import tomllib
import unittest

from nxwright.testing.preview import Previews
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.screen_copy import ROTATIONS
from nxwright.project.screen_models import MODELS, model_named
from nxwright.project.zi_font import decode_font
from nxwright.source.keyboards import CHINESE_INPUT, KEYBOARD_PAGES, keyboard, keyboard_font
from nxwright.source.project_files import build
from nxwright.source.source_folder import new_source_folder
from nxwright.testing.simulation import Simulation
from tests.test_folder_check import edited_app, fonts_first


def caller(name: str, kind: str, y: int, key: int, **values) -> str:
    """Returns the page file's table of a caller: a component of global scope
    bound to the keyboard `key` opens."""
    lines = ['name = "%s"' % name, 'type = "%s"' % kind, "x = 0", "y = %d" % y, "w = 200",
             "h = 40", "vscope = 1", "key = %d" % key]
    lines += ["%s = %s" % (attribute, '"%s"' % value if isinstance(value, str) else value)
              for attribute, value in values.items()]
    return "\n[[component]]\n" + "\n".join(lines) + "\n"


# The callers of the test folder's first page. For each keyboard, by its
# `key`: a text of 3 bytes at most, a number, and an xfloat of one place.
# Then, for the full keyboard, a text, a hidden text, and an xfloat of two
# places; for the keypad, a number and an xfloat; for the speed dial, a text.
CALLERS = "".join(caller("tk%d" % key, "text", 25 * key, key, txt="ab", txt_maxl=3)
                  + caller("nk%d" % key, "number", 100 + 25 * key, key, val=4)
                  + caller("xk%d" % key, "xfloat", 200 + 25 * key, key, vvs1=1)
                  for key in (1, 2, 3))
CALLERS += (caller("t0", "text", 300, 1, txt="hello", txt_maxl=7)
            + caller("secret", "text", 300, 1, pw=1, txt="abc")
            + caller("x0", "xfloat", 300, 1, vvs1=2)
            + caller("n1", "number", 350, 2, val=5)
            + caller("x1", "xfloat", 350, 2, vvs1=1)
            + caller("t3", "text", 400, 3, txt="", txt_maxl=20)
            + '\n[[component]]\nname = "started"\ntype = "variable"\nvscope = 1\n')
# The page's first load gives the xfloats values a page file cannot: page
# files take an xfloat's starting value unsigned.
CALLER_CODE = """\
on page0.load:
  if(started.val==0)
  {
    x0.val=-1234
    x1.val=-15
    xk1.val=-15
    xk2.val=-15
    xk3.val=-15
    started.val=1
  }
"""
# How to type on each keyboard, by its `key`: the keys typing a character
# and the character they type, and those typing the digit 1.
TYPING = {1: (["key1_1"], "q", ["mode", "mode", "key1_1"]),
          2: (["digit1"], "1", ["digit1"]),
          3: (["group1", "choice1"], "a", ["mode", "mode", "group1"])}
PAGES = {1: "keybdA", 2: "keybdB", 3: "keybdC"}
# The keyboards whose font is drawn from Noto Sans: all but the Chinese one,
# which tests/test_chinese_keyboard.py tests.
NOTO_SANS_KEYBOARDS = [kind for kind in KEYBOARD_PAGES if kind != CHINESE_INPUT]


def page_size(model, rotation: int) -> tuple:
    """Returns a screen's page size, width by height, at a rotation."""
    if rotation in (90, 270):
        return model.height, model.width
    return model.width, model.height


def keyboard_folder(root: Path, language: str) -> Path:
    """Writes a source folder in `language`, NX8048P050 at rotation 0, whose
    first page holds the callers, and which has the three keyboards."""
    folder = root / language
    new_source_folder(folder, DeviceSettings(model_named("NX8048P050"), 0, "iso-8859-1"),
                      language)
    (folder / "fonts").mkdir(exist_ok=True)
    fonts = []
    for kind in NOTO_SANS_KEYBOARDS:
        page = KEYBOARD_PAGES[kind]
        made = keyboard(kind, 800, 480)
        (folder / "pages" / (page + ".page.toml")).write_text(made.page_toml, encoding="utf-8")
        (folder / "pages" / (page + ".nx")).write_text(made.code, encoding="utf-8")
        if made.font_name not in fonts:
            fonts.append(made.font_name)
            (folder / "fonts" / (made.font_name + ".zi")).write_bytes(
                keyboard_font(made, 0, "iso-8859-1"))
    app = (folder / "app.toml").read_text(encoding="utf-8")
    app = edited_app(app, lambda app: app["pages"].extend(["keybdA", "keybdB", "keybdC"]))
    app = fonts_first(app, fonts)
    (folder / "app.toml").write_text(app, encoding="utf-8")
    page = folder / "pages" / "page0.page.toml"
    page.write_text(page.read_text(encoding="utf-8") + CALLERS, encoding="utf-8")
    (folder / "pages" / "page0.nx").write_text(CALLER_CODE, encoding="utf-8")
    (folder / "program.nx").write_text("page page0\n", encoding="utf-8")
    return folder


def overlap(a: dict, b: dict) -> bool:
    return (a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"]
            and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"])


def inside(a: dict, b: dict) -> bool:
    return (b["x"] <= a["x"] and a["x"] + a["w"] <= b["x"] + b["w"]
            and b["y"] <= a["y"] and a["y"] + a["h"] <= b["y"] + b["h"])


class LayoutTest(unittest.TestCase):

    def test_every_keyboard_on_every_screen(self):
        for kind, model, rotation in itertools.product(NOTO_SANS_KEYBOARDS, MODELS, ROTATIONS):
            width, height = page_size(model, rotation)
            with self.subTest(keyboard=kind, screen=model.name, rotation=rotation):
                made = keyboard(kind, width, height)
                self.assertTrue(16 <= made.font_height <= 254)
                page = tomllib.loads(made.page_toml)
                whole = {"x": 0, "y": 0, "w": width, "h": height}
                self.assertEqual((page["page"]["w"], page["page"]["h"]), (width, height))
                placed = {component["name"]: component for component in page["component"]
                          if "x" in component}
                # The Editor refuses a component under 2 pixels wide or high.
                for name, component in placed.items():
                    self.assertGreaterEqual(min(component["w"], component["h"]), 2, name)
                    self.assertTrue(inside(component, whole), name)
                shown = [component for component in placed.values()
                         if component["type"] == "button" or component["name"] == "fieldbox"]
                for first, second in itertools.combinations(shown, 2):
                    self.assertFalse(overlap(first, second), (first["name"], second["name"]))
                field, box = placed["field"], placed["fieldbox"]
                self.assertTrue(box["x"] < field["x"] and inside(field, box))
                # The keypad and the speed dial are panels over the caller's
                # page: their page has no background.
                if kind == "keyboard":
                    self.assertNotIn("panel", placed)
                else:
                    self.assertEqual(page["page"]["sta"], 0)
                    for component in shown:
                        self.assertTrue(inside(component, placed["panel"]), component["name"])


class FontTest(unittest.TestCase):

    def test_the_font_is_in_the_project_encoding(self):
        # Every encoding a project can have: in utf-8, a font of chosen
        # characters, of U+0000 to U+00FF; in a one-byte encoding of
        # characters Noto Sans lacks, as koi8-r's box drawing or windows-874's
        # Thai, a font without them; in a two-byte encoding, with them empty.
        made = keyboard("keypad", 480, 320)
        for project in ("iso-8859-1", "windows-1257", "ascii", "koi8-r", "windows-874", "utf-8",
                        "gb2312", "big5", "shift-jis", "ks_c_5601-1987"):
            with self.subTest(project=project):
                self.assertEqual(decode_font(keyboard_font(made, 0, project)).encoding, project)

    def test_the_font_turned_to_the_rotation(self):
        made = keyboard("keypad", 480, 320)
        font = decode_font(keyboard_font(made, 90, "koi8-r"))
        self.assertEqual((font.name, font.height, font.rotation, font.encoding),
                         (made.font_name, made.font_height, 90, "koi8-r"))


class KeyboardTestCase(unittest.TestCase):
    """The keyboards in a folder of each language, opened by their callers."""

    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name)
        cls.folders = {language: keyboard_folder(cls.root, language)
                       for language in ("nextion", "nxlang")}

    def simulations(self):
        """Yields a new simulation of each folder, within a subtest."""
        for language, folder in self.folders.items():
            with self.subTest(language=language):
                yield Simulation(folder)

    @staticmethod
    def tap(simulation: Simulation, *names: str):
        for name in names:
            simulation.press(name)
            simulation.release()


class EveryKeyboardTest(KeyboardTestCase):
    """Each keyboard opened by a text, a number, and an xfloat."""

    def test_a_text_typed_up_to_its_length(self):
        for simulation in self.simulations():
            for key, (keys, character, _) in TYPING.items():
                with self.subTest(key=key):
                    self.tap(simulation, "tk%d" % key)
                    self.assertEqual((simulation.page, simulation.values()["field.txt"]),
                                     (PAGES[key], "ab"))
                    # The text holds 3 bytes at most: the second is not typed.
                    self.tap(simulation, *keys, *keys, "ok")
                    self.assertEqual((simulation.page, simulation.values()["tk%d.txt" % key]),
                                     ("page0", "ab" + character))

    def test_a_number(self):
        for simulation in self.simulations():
            for key, (_, _, digit_keys) in TYPING.items():
                with self.subTest(key=key):
                    self.tap(simulation, "nk%d" % key)
                    self.assertEqual(simulation.values()["field.txt"], "4")
                    self.tap(simulation, *digit_keys, "ok")
                    self.assertEqual(simulation.values()["nk%d.val" % key], 41)

    def test_an_xfloat(self):
        for simulation in self.simulations():
            for key, (_, _, digit_keys) in TYPING.items():
                with self.subTest(key=key):
                    self.tap(simulation, "xk%d" % key)
                    self.assertEqual(simulation.values()["field.txt"], "-1.5")
                    self.tap(simulation, "back", *digit_keys, "ok")
                    self.assertEqual(simulation.values()["xk%d.val" % key], -11)

    def test_cancel_writes_nothing(self):
        for simulation in self.simulations():
            for key, (keys, _, _) in TYPING.items():
                with self.subTest(key=key):
                    self.tap(simulation, "tk%d" % key, "back", *keys, "cancel")
                    self.assertEqual((simulation.page, simulation.values()["tk%d.txt" % key]),
                                     ("page0", "ab"))


class StandInCallerTest(KeyboardTestCase):
    """A simulation started on a keyboard page, which no caller opened: a
    stand-in text, on a page of the simulation's own after the app's last,
    takes the caller's place, unless the starting values name a caller."""

    def test_the_keyboard_edits_a_stand_in_text_and_goes_back_to_it(self):
        for language, folder in self.folders.items():
            for key, (keys, character, _) in TYPING.items():
                with self.subTest(language=language, key=key):
                    simulation = Simulation(folder, start_page=PAGES[key])
                    values = simulation.values()
                    # The app's pages are page0 and the three keyboards.
                    self.assertEqual((values["loadpageid.val"], values["loadcmpid.val"]), (4, 1))
                    # The stand-in text starts empty.
                    self.assertEqual((simulation.page_names[4], values["field.txt"]),
                                     ("keyboardCaller", ""))
                    self.assertIn("started without a caller", simulation.log[0][1])
                    self.tap(simulation, *keys, "ok")
                    values = simulation.values()
                    self.assertEqual((simulation.page, values["label.txt"], values["t0.txt"]),
                                     ("keyboardCaller", "The keyboard returned:", character))
                    # Drawn as any page is, from the simulation's values.
                    drawing = Previews().drawing_of(folder, simulation.app,
                                                    simulation.components())
                    self.assertIn("text", [shape["kind"] for shape in drawing["shapes"]
                                           if shape["component"] == "t0"])
                    # Opened again, the keyboard starts from what it returned.
                    self.tap(simulation, "again")
                    self.assertEqual((simulation.page, simulation.values()["field.txt"]),
                                     (PAGES[key], character))

    def test_an_empty_text_returned_is_said_so_then_shown_once_typed(self):
        for key, (keys, character, _) in TYPING.items():
            with self.subTest(key=key):
                simulation = Simulation(self.folders["nextion"], start_page=PAGES[key])
                self.tap(simulation, "ok")
                values = simulation.values()
                self.assertEqual((values["label.txt"], values["vis t0"]),
                                 ("The keyboard returned an empty text.", 0))
                # The button opens the keyboard while the text is hidden.
                self.tap(simulation, "again", *keys, "ok")
                values = simulation.values()
                self.assertEqual((values["label.txt"], values["vis t0"], values["t0.txt"]),
                                 ("The keyboard returned:", 1, character))

    def test_the_stand_in_page_takes_the_keyboard_fields_font_and_fits_the_page(self):
        simulation = Simulation(self.folders["nextion"], start_page="keybdA")
        font = simulation.values()["field.font"]
        self.tap(simulation, "ok")
        page, *placed = simulation.components()
        self.assertEqual([component.name for component in placed],
                         ["t0", "title", "label", "again"])
        boxes = [component.values for component in placed]
        for box in boxes:
            self.assertEqual(box["font"], font)
            self.assertTrue(inside(box, page.values), box)
        for first, second in itertools.combinations(boxes, 2):
            self.assertFalse(overlap(first, second), (first, second))

    def test_starting_values_naming_a_caller_win(self):
        folder = self.folders["nextion"]
        ids = [name for name, _, _ in Simulation(folder).pages["page0"].components]
        simulation = Simulation(folder, start_page="keybdA",
                                values={"loadpageid.val": 0, "loadcmpid.val": ids.index("t0")})
        self.assertEqual((simulation.page_names, simulation.values()["field.txt"]),
                         (["page0", "keybdA", "keybdB", "keybdC"], "hello"))
        self.assertEqual(simulation.log, [])

    def test_one_variable_given_names_the_caller(self):
        # loadcmpid alone: loadpageid stays 0, page0, whose t0 is the caller.
        folder = self.folders["nextion"]
        caller = [name for name, _, _ in Simulation(folder).pages["page0"].components].index("t0")
        simulation = Simulation(folder, start_page="keybdA", values={"loadcmpid.val": caller})
        self.assertEqual((simulation.page_names, simulation.values()["field.txt"]),
                         (["page0", "keybdA", "keybdB", "keybdC"], "hello"))

    def test_a_caller_named_with_the_start_pages_name(self):
        # keybdA.loadcmpid.val, as the page's own code may name its
        # component, is its loadcmpid.val. Another page's global, named with
        # its page's name, still goes to that page: the caller's text.
        folder = self.folders["nextion"]
        caller = [name for name, _, _ in Simulation(folder).pages["page0"].components].index("t0")
        simulation = Simulation(folder, start_page="keybdA",
                                values={"keybdA.loadcmpid.val": caller, "page0.t0.txt": "hi"})
        self.assertEqual((simulation.page_names, simulation.values()["field.txt"]),
                         (["page0", "keybdA", "keybdB", "keybdC"], "hi"))
        self.assertNotIn("keybdA.loadcmpid.val", simulation.values())

    def test_a_page_that_is_no_keyboard_gets_no_stand_in(self):
        simulation = Simulation(self.folders["nextion"], start_page="page0")
        self.assertEqual(simulation.page_names, ["page0", "keybdA", "keybdB", "keybdC"])


class CodeTest(unittest.TestCase):

    def test_each_statement_has_one_operator_at_most(self):
        # So that the Editor's order, left to right, and nxlang's agree.
        operator = re.compile(r"\+\+|--|[-+*/]=|==|!=|<=|>=|&&|\|\||[-+*/%<>]")
        for kind in NOTO_SANS_KEYBOARDS:
            for line in keyboard(kind, 800, 480).code.splitlines():
                statement = re.sub(r'"[^"]*"', '""', line.split("//")[0])
                # A minus starting a number is its sign, as in number.val*=-1.
                statement = re.sub(r"([=(,])-(?=\d)", r"\1", statement)
                with self.subTest(keyboard=kind, line=line):
                    self.assertLessEqual(len(operator.findall(statement)), 1)


class FullKeyboardTest(KeyboardTestCase):

    def test_each_folder_builds(self):
        for language, folder in self.folders.items():
            with self.subTest(language=language):
                build(folder, self.root / ("%s.HMI" % language))

    def test_a_hidden_text_shows_hidden(self):
        for simulation in self.simulations():
            self.tap(simulation, "secret")
            self.assertEqual((simulation.values()["field.txt"], simulation.values()["field.pw"]),
                             ("abc", 1))

    def test_an_xfloat(self):
        for simulation in self.simulations():
            self.tap(simulation, "x0")
            self.assertEqual(simulation.values()["field.txt"], "-12.34")
            self.tap(simulation, "back", "mode", "mode", "key1_5", "ok")
            self.assertEqual(simulation.values()["x0.val"], -1235)
            # Places left untyped are zeros.
            self.tap(simulation, "x0", "back", "back", "ok")
            self.assertEqual(simulation.values()["x0.val"], -1200)

    def test_the_mode_key(self):
        for simulation in self.simulations():
            self.tap(simulation, "t0")
            shown = []
            for _ in range(4):
                values = simulation.values()
                shown.append((values["key1_1.txt"], values["key2_1.txt"], values["mode.txt"]))
                self.tap(simulation, "mode")
            self.assertEqual(shown, [("q", "a", "ABC"), ("Q", "A", "123"), ("1", "@", "abc"),
                                     ("q", "a", "ABC")])


class KeypadTest(KeyboardTestCase):

    def test_a_number_holds_a_sign_and_ten_digits(self):
        for simulation in self.simulations():
            self.tap(simulation, "n1", "back", "minus", *["digit1"] * 11)
            self.assertEqual(simulation.values()["field.txt"], "-1111111111")

    def test_a_negative_number(self):
        for simulation in self.simulations():
            self.tap(simulation, "n1")
            self.assertEqual((simulation.page, simulation.values()["field.txt"]), ("keybdB", "5"))
            self.tap(simulation, "back", "minus", "digit7", "digit0", "ok")
            self.assertEqual((simulation.page, simulation.values()["n1.val"]), ("page0", -70))

    def test_an_xfloat(self):
        for simulation in self.simulations():
            self.tap(simulation, "x1")
            self.assertEqual(simulation.values()["field.txt"], "-1.5")
            # Digits past the caller's one place are left out.
            self.tap(simulation, "digit2", "ok")
            self.assertEqual(simulation.values()["x1.val"], -15)
            self.tap(simulation, "x1", "back", "back", "back", "back", "digit3", "point",
                     "digit2", "ok")
            self.assertEqual(simulation.values()["x1.val"], 32)


class SpeedDialTest(KeyboardTestCase):

    def choices(self, simulation: Simulation) -> list:
        values = simulation.values()
        return [values["choice%d.txt" % number] for number in range(1, 5)]

    def test_a_group_then_a_letter(self):
        for simulation in self.simulations():
            self.tap(simulation, "t3")
            self.assertEqual(simulation.page, "keybdC")
            self.tap(simulation, "group1")
            self.assertEqual(self.choices(simulation), ["a", "b", "c", ""])
            self.tap(simulation, "choice2", "group6", "choice4", "space", "group9", "choice4")
            self.assertEqual(simulation.values()["field.txt"], "bs @")
            self.tap(simulation, "ok")
            self.assertEqual(simulation.values()["t3.txt"], "bs @")

    def test_capitals_then_digits(self):
        for simulation in self.simulations():
            self.tap(simulation, "t3", "group1", "mode")
            values = simulation.values()
            # The choices are emptied, and the groups show capitals.
            self.assertEqual((values["group1.txt"], values["mode.txt"], self.choices(simulation)),
                             ("ABC", "123", ["", "", "", ""]))
            self.tap(simulation, "group3", "choice1", "mode")
            # In digits, a group key types its digit, and space a zero.
            self.tap(simulation, "group1", "group9", "space", "back", "space")
            self.assertEqual(simulation.values()["field.txt"], "G190")
            self.tap(simulation, "mode")
            self.assertEqual(simulation.values()["group1.txt"], "abc")
