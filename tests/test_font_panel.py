"""The language server's requests for the Fonts panel in VS Code: the
folder's fonts and their samples, the typefaces nxwright can draw from,
samples of fonts about to be added, and adding them. The typefaces are
looked for in a folder the tests make, never among the computer's own."""
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

from nxwright.language_server.file_texts import uri_of
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.font_drawing import code_points_of
from nxwright.project.pictures import data_url
from nxwright.project.screen_models import model_named
from nxwright.project.truetype import NOTO_SANS, TrueTypeFont
from nxwright.project.zi_font import decode_font
from nxwright.drawing.font_samples import font_sample, sample_font
from nxwright.source.source_folder import new_source_folder
from nxwright.source.resource_adding import add_font, add_font_file
from tests.language_server_connection import document_item, initialized
from tests.test_font_command import GENERATORS
from tests.test_installed_typefaces import renamed_noto_sans
from tests.test_zi_font import font_block, gb2312_font, grid_font, utf8_font, utf8_fixture

BLACK = [0, 0, 0]


class FontPanelTest(unittest.TestCase):

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name)
        # The computer's fonts are never looked at: only this folder's.
        installed = self.temp / "installed"
        installed.mkdir()
        (installed / "toto.ttf").write_bytes(renamed_noto_sans("Toto Sans"))
        patcher = mock.patch("nxwright.project.installed_typefaces.font_folders",
                             return_value=[installed])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.connection = initialized()
        self.sent = self.connection.sent

    def new_folder(self, encoding: str = "iso-8859-1", rotation: int = 0) -> Path:
        folder = self.temp / ("folder-%s-%d" % (encoding, rotation))
        new_source_folder(folder, DeviceSettings(model_named("NX4832T035"), rotation, encoding),
                          "nextion")
        return folder

    def font_file(self, name: str, block: bytes) -> Path:
        path = self.temp / name
        path.write_bytes(block)
        return path

    def request(self, method: str, folder: Path, **params) -> dict:
        """Returns the server's reply to a request about `folder`."""
        params["textDocument"] = {"uri": uri_of(folder / "app.toml")}
        self.connection.handle({"jsonrpc": "2.0", "id": 2, "method": method, "params": params})
        return self.sent[-1]

    def test_the_folders_fonts(self):
        folder = self.new_folder()
        add_font(folder, NOTO_SANS, 20)
        add_font(folder, NOTO_SANS, 16, "Keys", smoothed=False)
        reply = self.request("nxwright/fonts", folder, text="Hello", colour=BLACK)["result"]
        self.assertEqual((reply["encoding"], reply["drawable"]), ("iso-8859-1", True))
        # After the font a new folder starts with.
        started, noto, keys = reply["fonts"]
        self.assertEqual(started["name"], "NotoSans24")
        block = (folder / "fonts" / "NotoSans20.zi").read_bytes()
        self.assertEqual(noto, {
            "name": "NotoSans20", "height": 20, "encoding": "iso-8859-1", "rotation": 0,
            "smoothed": True, "characters": 224,
            "sample": data_url(font_sample(decode_font(block), "Hello", "iso-8859-1", (0, 0, 0))),
            # Its characters' code points, through its encoding, which "New
            # font like this" puts in a utf-8 folder's Characters field.
            "ranges": "20-ff",
            # A font drawn from Noto Sans at 20 pixels is named NotoSans20.
            "like": {"name": "Noto Sans", "path": str(NOTO_SANS)}})
        self.assertEqual((keys["height"], keys["smoothed"], keys["like"]), (16, False, None))

    def test_a_font_with_no_sample(self):
        folder = self.new_folder("big5")
        add_font_file(folder, self.font_file("Wide.zi", font_block(
            [(65, 1, 0, 0, bytes([3, 0b00100001]))], 1, encoding=16, name="Wide")))
        reply = self.request("nxwright/fonts", folder, text="Hello", colour=BLACK)["result"]
        self.assertEqual((reply["encoding"], reply["drawable"]), ("big5", True))
        _, wide = reply["fonts"]
        self.assertEqual((wide["encoding"], wide["characters"], wide["like"]), ("big5", 1, None))
        # One character marked as in big5 is no grid of every position.
        self.assertIn("a font in big5 of byte 5 at 0 has not been seen", wide["noSample"])

    def test_a_sample_of_a_big5_font(self):
        # The font the folder started with, Noto Sans in big5, then the one
        # added.
        folder = self.new_folder("big5")
        add_font_file(folder, self.font_file("Ch.zi", grid_font("big5", name="Ch")))
        reply = self.request("nxwright/fonts", folder, text="中a", colour=BLACK)["result"]
        self.assertEqual((reply["encoding"], reply["drawable"]), ("big5", True))
        started, ch = reply["fonts"]
        self.assertEqual(started["name"], "NotoSans24")
        self.assertEqual((ch["encoding"], ch["characters"]), ("big5", 14225))
        self.assertEqual(ch["sample"], data_url(font_sample(
            decode_font(grid_font("big5", name="Ch")), "中a", "big5", (0, 0, 0))))
        self.assertNotIn("ranges", ch)

    def test_a_sample_of_a_gb2312_font(self):
        folder = self.new_folder("gb2312")
        add_font_file(folder, self.font_file("Zh.zi", gb2312_font()))
        reply = self.request("nxwright/fonts", folder, text="中a", colour=BLACK)["result"]
        self.assertEqual((reply["encoding"], reply["drawable"]), ("gb2312", True))
        # The font the folder started with, then the one added.
        started, zh = reply["fonts"]
        self.assertEqual(started["name"], "NotoSans24")
        self.assertEqual((zh["encoding"], zh["characters"]), ("gb2312", 8273))
        self.assertEqual(zh["sample"], data_url(font_sample(decode_font(gb2312_font()), "中a",
                                                            "gb2312", (0, 0, 0))))
        self.assertNotIn("ranges", zh)

    def test_a_sample_of_a_utf8_font(self):
        folder = self.new_folder("utf-8")
        block = utf8_fixture("NotoSans20-cyrillic")
        add_font_file(folder, self.font_file("Cyrillic.zi", block))
        reply = self.request("nxwright/fonts", folder, text="Жук", colour=BLACK)["result"]
        self.assertEqual((reply["encoding"], reply["drawable"]), ("utf-8", True))
        # The font the folder started with, then the one added.
        started, cyrillic = reply["fonts"]
        self.assertEqual(started["name"], "NotoSans24")
        self.assertEqual((cyrillic["encoding"], cyrillic["characters"]), ("utf-8", 384))
        # Its code points, as the form's Characters field takes them.
        self.assertEqual(code_points_of(cyrillic["ranges"]), sorted(decode_font(block).characters))
        self.assertEqual(cyrillic["sample"], data_url(font_sample(decode_font(block), "Жук",
                                                                  "utf-8", (0, 0, 0))))

    def test_the_typefaces(self):
        names = [typeface["name"] for typeface in self.request(
            "nxwright/typefaces", self.new_folder())["result"]["typefaces"]]
        self.assertEqual(names, ["Noto Sans", "Toto Sans"])
        # In utf-8, every typeface: its characters are chosen with the font.
        self.assertEqual([typeface["name"] for typeface in self.request(
            "nxwright/typefaces", self.new_folder("utf-8"))["result"]["typefaces"]],
                         ["Noto Sans", "Toto Sans"])
        # In gb2312, those with every letter of GB2312: Noto Sans first, though
        # it has none of its Chinese characters, and not Toto Sans, Noto Sans
        # by another name.
        self.assertEqual([typeface["name"] for typeface in self.request(
            "nxwright/typefaces", self.new_folder("gb2312"))["result"]["typefaces"]],
                         ["Noto Sans"])
        # And so in big5, shift-jis, and ks_c_5601-1987.
        for encoding in ("big5", "shift-jis", "ks_c_5601-1987"):
            self.assertEqual([typeface["name"] for typeface in self.request(
                "nxwright/typefaces", self.new_folder(encoding))["result"]["typefaces"]],
                             ["Noto Sans"])

    def test_a_sample_of_a_font_to_draw(self):
        # The folder starts with Noto Sans at 24 pixels, NotoSans24.
        folder = self.new_folder()
        noto = TrueTypeFont(NOTO_SANS.read_bytes())

        def sample(**params) -> dict:
            arguments = dict(typeface=str(NOTO_SANS), height=20, smoothed=False, name="",
                             text="Hello", colour=BLACK)
            arguments.update(params)
            return self.request("nxwright/fontSample", folder, **arguments)["result"]
        self.assertEqual(sample(), {
            "name": "NotoSans20", "refusal": None,
            "sample": data_url(font_sample(sample_font(noto, 20, "iso-8859-1", False, "Hello"),
                                           "Hello", "iso-8859-1", (0, 0, 0)))})
        self.assertEqual(sample(height=24)["refusal"], "the folder has a font named NotoSans24")
        self.assertEqual(sample(height=24, name="Big")["refusal"], None)
        # Below the 16 the generator's list starts at: it makes fonts from 12.
        low = sample(height=13)
        self.assertEqual((low["name"], low["refusal"]), ("NotoSans13", None))
        self.assertIn("sample", low)
        too_high = sample(height=300)
        self.assertEqual((too_high["refusal"], too_high["noSample"]),
                         ("height 300 is not from 12 to 254",) * 2)
        self.assertEqual(sample(height="tall")["refusal"], "the height is not a whole number")
        # A typeface that lacks some characters of the encoding: the font
        # leaves them out, which a warning says, and is added.
        koi8 = self.new_folder("koi8-r")
        warning = ("the typeface file lacks 56 characters of koi8-r, such as '─' (U+2500); the "
                   "font leaves them out, and the screen shows the font's first character, the "
                   "space, in their place")
        lacking = self.request("nxwright/fontSample", koi8, typeface=str(NOTO_SANS), height=20,
                               name="", text="Hello", colour=BLACK)["result"]
        self.assertEqual((lacking["refusal"], lacking["warning"]), (None, warning))
        self.assertEqual(self.request("nxwright/addFont", koi8, typeface=str(NOTO_SANS),
                                      height=20, smoothed=True, name="")["result"],
                         {"name": "NotoSans20", "warning": warning})

    def test_a_sample_of_a_gb2312_font_to_draw(self):
        # Noto Sans in gb2312: its α drawn, its 中 lacking, empty, the height
        # wide, as the warning says; and the font added.
        folder = self.new_folder("gb2312")
        noto = TrueTypeFont(NOTO_SANS.read_bytes())
        warning = ("the typeface file lacks 7282 characters of gb2312, such as '\\u3000' "
                   "(U+3000); the font leaves them out, and the screen shows nothing in their "
                   "place, the height wide")
        reply = self.request("nxwright/fontSample", folder, typeface=str(NOTO_SANS), height=16,
                             name="", text="Aα中", colour=BLACK)["result"]
        self.assertEqual(reply, {
            "name": "NotoSans16", "refusal": None, "warning": warning,
            "sample": data_url(font_sample(sample_font(noto, 16, "gb2312", True, "Aα中"),
                                           "Aα中", "gb2312", (0, 0, 0)))})
        self.assertEqual(self.request("nxwright/addFont", folder, typeface=str(NOTO_SANS),
                                      height=16, smoothed=True, name="")["result"],
                         {"name": "NotoSans16", "warning": warning})

    def test_a_sample_of_another_two_byte_font_to_draw(self):
        # As in gb2312: Noto Sans's α drawn, its Chinese character, kana, or
        # Hangul empty, as the warning says; and the font added.
        noto = TrueTypeFont(NOTO_SANS.read_bytes())
        for encoding, text, lacking in (("big5", "Aα中", 13578), ("shift-jis", "Aαあ", 6741),
                                        ("ks_c_5601-1987", "Aα가", 3132)):
            with self.subTest(encoding=encoding):
                folder = self.new_folder(encoding)
                warning = ("the typeface file lacks %d characters of %s, such as '\\u3000' "
                           "(U+3000); the font leaves them out, and the screen shows nothing in "
                           "their place, the height wide" % (lacking, encoding))
                reply = self.request("nxwright/fontSample", folder, typeface=str(NOTO_SANS),
                                     height=16, name="", text=text, colour=BLACK)["result"]
                self.assertEqual(reply, {
                    "name": "NotoSans16", "refusal": None, "warning": warning,
                    "sample": data_url(font_sample(sample_font(noto, 16, encoding, True, text),
                                                   text, encoding, (0, 0, 0)))})
                self.assertEqual(self.request("nxwright/addFont", folder,
                                              typeface=str(NOTO_SANS), height=16, smoothed=True,
                                              name="")["result"],
                                 {"name": "NotoSans16", "warning": warning})

    def test_a_sample_of_a_utf8_font_to_draw(self):
        folder = self.new_folder("utf-8")
        noto = TrueTypeFont(NOTO_SANS.read_bytes())

        def sample(characters: str) -> dict:
            return self.request("nxwright/fontSample", folder, typeface=str(NOTO_SANS),
                                height=20, smoothed=True, name="", text="Жук", colour=BLACK,
                                characters=characters)["result"]
        cyrillic = code_points_of("20-7e,400-4ff")
        self.assertEqual(sample("20-7e,400-4ff"), {
            "name": "NotoSans20", "refusal": None,
            "sample": data_url(font_sample(sample_font(noto, 20, "utf-8", True, "Жук", cyrillic),
                                           "Жук", "utf-8", (0, 0, 0)))})
        # Noto Sans lacks Hebrew; the range is read as nxwright font reads it.
        hebrew = sample("590-5ff")
        self.assertIsNone(hebrew["refusal"])
        self.assertIn("the typeface file lacks 88 of the characters asked for", hebrew["warning"])
        unread = sample("4ff-400")
        self.assertEqual((unread["refusal"], unread["noSample"]),
                         ("the range 4ff-400 ends before it starts",) * 2)
        # Added, it holds the characters asked for.
        self.assertEqual(self.request("nxwright/addFont", folder, typeface=str(NOTO_SANS),
                                      height=20, smoothed=True, name="",
                                      characters="20-7e,400-4ff")["result"]["name"],
                         "NotoSans20")
        self.assertEqual(sorted(decode_font((folder / "fonts" / "NotoSans20.zi").read_bytes())
                                .characters), cyrillic)
        # Its name now taken, the sample is still of the characters asked for.
        taken = sample("400-4ff")
        self.assertEqual(taken["refusal"], "the folder has a font named NotoSans20")
        self.assertEqual(taken["sample"], data_url(font_sample(
            sample_font(noto, 20, "utf-8", True, "Жук", code_points_of("400-4ff")),
            "Жук", "utf-8", (0, 0, 0))))

    def test_a_sample_of_a_font_file(self):
        turned = self.request("nxwright/fontSample", self.new_folder(rotation=90),
                              file=str(GENERATORS), text="Hello", colour=BLACK)["result"]
        self.assertEqual({key: turned[key] for key in ("name", "refusal", "turned", "warning")},
                         {"name": "NotoSans20", "refusal": None, "turned": True, "warning": None})
        self.assertEqual(turned["sample"], data_url(font_sample(
            decode_font(GENERATORS.read_bytes()), "Hello", "iso-8859-1", (0, 0, 0))))
        warned = self.request("nxwright/fontSample", self.new_folder("utf-8"),
                              file=str(GENERATORS), name="Text", text="Hello",
                              colour=BLACK)["result"]
        self.assertEqual((warned["name"], warned["turned"]), ("Text", False))
        self.assertIn("the font Text is in iso-8859-1, not in the folder's utf-8",
                      warned["warning"])
        refused = self.request("nxwright/fontSample", self.new_folder(),
                               file=str(self.font_file("Wide.zi", utf8_font())), text="Hello",
                               colour=BLACK)["result"]
        self.assertEqual(refused["refusal"], "the font is in utf-8, and a folder in iso-8859-1 "
                                             "takes fonts in iso-8859-1 or ascii")

    def test_a_full_table_and_a_note(self):
        folder = self.new_folder("utf-8")

        def sample(**params) -> dict:
            return self.request("nxwright/fontSample", folder, typeface=str(NOTO_SANS),
                                height=20, smoothed=True, name="", text="Ab", colour=BLACK,
                                characters="41-5a", **params)["result"]
        # A character the font would lack is drawn as the screen draws it,
        # and named: in a table of chosen characters, as its first, the
        # space; in a full table, as nothing, half the height wide.
        self.assertEqual(sample()["sampleNote"],
                         "font NotoSans20 lacks U+0062; the screen draws its first character, "
                         "the space, in its place")
        self.assertEqual(sample(fullTable=True)["sampleNote"],
                         "font NotoSans20 lacks U+0062; the screen draws nothing in its place, "
                         "half the height wide")
        self.assertNotIn("sampleNote", self.request(
            "nxwright/fontSample", folder, typeface=str(NOTO_SANS), height=20, smoothed=True,
            name="", text="AB", colour=BLACK, characters="41-5a")["result"])
        # Asked for, the font added is a full table.
        self.assertEqual(self.request("nxwright/addFont", folder, typeface=str(NOTO_SANS),
                                      height=20, smoothed=True, name="", characters="41-5a",
                                      fullTable=True)["result"]["name"], "NotoSans20")
        self.assertGreater(len((folder / "fonts" / "NotoSans20.zi").read_bytes()), 655_360)
        # After the font the folder started with.
        _, noto20 = self.request("nxwright/fonts", folder, text="Ab",
                                 colour=BLACK)["result"]["fonts"]
        self.assertEqual(noto20["sampleNote"], "font NotoSans20 lacks U+0062; the screen draws "
                                               "nothing in its place, half the height wide")

    def test_adding_fonts(self):
        folder = self.new_folder("utf-8")
        reply = self.request("nxwright/addFont", folder, file=str(GENERATORS), name="")["result"]
        self.assertEqual(reply["name"], "NotoSans20")
        self.assertIn("not in the folder's utf-8", reply["warning"])
        folder = self.new_folder()
        self.assertEqual(self.request("nxwright/addFont", folder, typeface=str(NOTO_SANS),
                                      height="18", smoothed=False, name="Small")["result"],
                         {"name": "Small", "warning": None})
        self.assertEqual(tomllib.loads((folder / "app.toml").read_text(encoding="utf-8"))["fonts"],
                         ["NotoSans24", "Small"])
        self.assertEqual(decode_font((folder / "fonts" / "Small.zi").read_bytes()).height, 18)

    def test_a_request_naming_no_font(self):
        folder = self.new_folder()
        for method in ("nxwright/fontSample", "nxwright/addFont"):
            with self.subTest(method=method):
                reply = self.request(method, folder, text="Hello", colour=BLACK)
                self.assertEqual(reply["error"]["message"], 'the request names neither a '
                                 'typeface file ("typeface") nor a font file ("file")')

    def test_a_folder_without_screen_settings(self):
        # Its fonts' encoding and rotation are not known.
        folder = self.temp / "unset"
        folder.mkdir()
        (folder / "app.toml").write_text('format = 1\nlanguage = "nextion"\npages = []\n'
                                         'pictures = []\nfonts = []\n', encoding="utf-8")
        for method, params in (("nxwright/fonts", {}),
                               ("nxwright/fontSample", {"typeface": str(NOTO_SANS), "height": 20}),
                               ("nxwright/addFont", {"typeface": str(NOTO_SANS), "height": 20})):
            with self.subTest(method=method):
                reply = self.request(method, folder, text="Hello", colour=BLACK, **params)
                self.assertIn("app.toml gives no screen settings", reply["error"]["message"])

    def test_unsaved_changes_to_app_toml_are_refused(self):
        folder = self.new_folder()
        app = folder / "app.toml"
        self.connection.handle({"jsonrpc": "2.0", "method": "textDocument/didOpen", "params": {
            "textDocument": document_item(uri_of(app), app.read_text(encoding="utf-8") + "\n")}})
        reply = self.request("nxwright/addFont", folder, typeface=str(NOTO_SANS), height=20)
        self.assertIn("save or revert the changes to app.toml first; adding a font rewrites it",
                      reply["error"]["message"])
        self.assertEqual(tomllib.loads(app.read_text(encoding="utf-8"))["fonts"], ["NotoSans24"])


class FontFileTest(FontPanelTest):
    """nxwright/fontFile, for the font viewer: one font file's details and
    sample, and its source folder when the folder lists it."""

    def font_file_reply(self, path: Path, text: str = "Hello") -> dict:
        self.connection.handle({"jsonrpc": "2.0", "id": 2, "method": "nxwright/fontFile",
                                "params": {"file": str(path), "text": text, "colour": BLACK}})
        return self.sent[-1]["result"]

    def test_a_font_of_a_folder(self):
        folder = self.new_folder()
        add_font(folder, NOTO_SANS, 20)
        path = folder / "fonts" / "NotoSans20.zi"
        reply = self.font_file_reply(path)
        self.assertEqual({key: reply[key] for key in ("name", "height", "encoding", "rotation",
                                                      "smoothed", "characters", "folder")},
                         {"name": "NotoSans20", "height": 20, "encoding": "iso-8859-1",
                          "rotation": 0, "smoothed": True, "characters": 224,
                          "folder": str(folder)})
        self.assertEqual(reply["sample"], data_url(font_sample(
            decode_font(path.read_bytes()), "Hello", "iso-8859-1", (0, 0, 0))))

    def test_a_font_file_outside_a_folder_is_drawn_in_its_own_encoding(self):
        block = utf8_fixture("NotoSans20-cyrillic")
        path = self.font_file("Cyrillic.zi", block)
        reply = self.font_file_reply(path, "Жук")
        self.assertEqual((reply["name"], reply["encoding"], reply["folder"]),
                         ("Cyrillic", "utf-8", None))
        self.assertEqual(reply["sample"], data_url(font_sample(
            decode_font(block), "Жук", "utf-8", (0, 0, 0))))

    def test_a_font_the_folder_does_not_list_has_no_folder(self):
        folder = self.new_folder()
        path = folder / "fonts" / "Stray.zi"
        path.write_bytes((self.temp / "folder-iso-8859-1-0" / "fonts" / "NotoSans24.zi")
                         .read_bytes())
        self.assertIsNone(self.font_file_reply(path)["folder"])

    def test_a_font_of_a_folder_without_screen_settings_is_drawn_in_its_own_encoding(self):
        folder = self.new_folder()
        app = folder / "app.toml"
        app.write_text("\n".join(line for line in app.read_text(encoding="utf-8").split("\n")
                                 if not line.startswith(("screen", "rotation", "encoding"))),
                       encoding="utf-8")
        reply = self.font_file_reply(folder / "fonts" / "NotoSans24.zi")
        self.assertEqual((reply["folder"], reply["encoding"]), (str(folder), "iso-8859-1"))
        self.assertIn("sample", reply)

    def test_a_file_that_is_no_font_says_why(self):
        reply = self.font_file_reply(self.font_file("Broken.zi", b"not a font"))
        self.assertEqual((reply["name"], reply["folder"]), ("Broken", None))
        self.assertIn("noSample", reply)
        self.assertNotIn("height", reply)


if __name__ == "__main__":
    unittest.main()
