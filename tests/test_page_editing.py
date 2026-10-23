"""Editing a page from the page preview: the properties panel's list, the edits
of a page file, and finding a component's default event, or another, and
its events."""
import tomllib
import unittest

from nxwright import NxwrightError
from nxwright.language_server.file_texts import FileTexts, uri_of
from nxwright.source.folder_index import FolderIndex
from nxwright.language_server.page_editing import (component_events, default_event,
                                                   key_binding, properties)
from nxwright.source.keyboard_adding import add_keyboard
from nxwright.source.page_edits import attribute_edits, edited_text
from nxwright.source.resource_adding import add_font_file
from tests.language_server_connection import document_item, initialized
from tests.test_folder_check import FolderTestCase, edited_app, fonts_first
from tests.test_zi_font import gb2312_font


class ServerTestCase(FolderTestCase):
    """The folder's page0, with its text "title", as the language server reads it."""

    def setUp(self):
        super().setUp()
        self.documents = FileTexts()

    def index(self) -> FolderIndex:
        return FolderIndex(self.root, self.documents.read)

    def read(self):
        return self.documents.folder_reader(self.root)

    def edited(self, name: str = "title", **values) -> str:
        edits = attribute_edits(self.index(), self.read(), "page0", name, values)
        return edited_text(self.text("pages/page0.page.toml"), edits)

    def request(self, method: str, **params) -> dict:
        """Returns the reply of a new server to a request about page0."""
        connection = initialized()
        params["textDocument"] = {"uri": uri_of(self.root / "pages/page0.page.toml")}
        connection.handle({"jsonrpc": "2.0", "id": 2, "method": method, "params": params})
        return connection.sent[-1]

    def table(self, text: str, name: str = "title") -> dict:
        data = tomllib.loads(text)
        return next(table for table in [data["page"]] + data["component"] if table["name"] == name)


class EditingTestCase(ServerTestCase):
    """The folder's page0, with its text "title", and a picture and a font
    named in app.toml, whose files the folder lacks."""

    def setUp(self):
        super().setUp()
        self.write("app.toml", fonts_first(self.text("app.toml")
                   .replace("pictures = []", 'pictures = ["dot"]'), ["Sans20"]))


class PropertiesTest(EditingTestCase):

    def test_every_attribute_of_the_type(self):
        found = properties(self.index(), self.read(), "page0", "title")
        self.assertEqual((found["type"], found["defaultsFalse"]), ("text", False))
        names = [entry["name"] for entry in found["attributes"]]
        self.assertIn("pco", names)
        self.assertNotIn("id", names)
        by_name = {entry["name"]: entry for entry in found["attributes"]}
        self.assertEqual((by_name["txt"]["value"], by_name["txt"]["given"], by_name["txt"]["kind"]),
                         ("x", True, "text"))
        self.assertEqual((by_name["xcen"]["value"], by_name["xcen"]["default"],
                          by_name["xcen"]["given"]), (1, 1, False))
        self.assertEqual((by_name["pco"]["kind"], by_name["font"]["kind"]), ("colour", "font"))
        self.assertEqual(by_name["pic"]["choices"], ["none", "dot"])
        # The folder's fonts: its own, then the one a new folder starts with.
        self.assertEqual(by_name["font"]["choices"], ["Sans20", "NotoSans24"])
        lines = self.text("pages/page0.page.toml").split("\n")
        self.assertEqual(lines[by_name["txt"]["line"]], 'txt = "x"')
        self.assertEqual(lines[found["nameLine"]][found["nameCharacter"]:], 'title"')

    def test_each_attribute_with_its_description_and_treatment(self):
        found = properties(self.index(), self.read(), "page0", "title")
        by_name = {entry["name"]: entry for entry in found["attributes"]}
        self.assertEqual(by_name["xcen"]["description"],
                         "Where the text sits across the component.\n0: left\n1: centre\n"
                         "2: right\nCan be changed in code.")
        self.assertTrue(by_name["aph"]["description"].endswith(
            "Can be changed in code.\nCode may store 0 to 127. The screen refuses other numbers."))
        self.assertEqual(by_name["txt"]["treatment"], "shown")
        # Left out of the section: the preview shows a lock and a group by
        # itself, and what movex does is not known.
        for attribute in ("lockobj", "groupid0", "groupid1", "movex"):
            self.assertEqual(by_name[attribute]["treatment"], "never-shown")
        # The Editor's "Send Component ID" ticks. The user chose to edit them
        # like any other attribute, by which events send the ID.
        self.assertEqual((by_name["sendkey"]["treatment"], by_name["sendkey"]["labels"]),
                         ("shown", [{"value": 0, "label": "none"},
                                    {"value": 1, "label": "release"},
                                    {"value": 2, "label": "press"},
                                    {"value": 3, "label": "both"}]))

    def test_an_object_the_page_lacks(self):
        with self.assertRaisesRegex(NxwrightError, "page page0 has no object nobody"):
            properties(self.index(), self.read(), "page0", "nobody")

    def test_the_labels_of_an_attributes_choices(self):
        # For a drop-down of their names; none for a number without choices,
        # or for a resource, whose names are its choices.
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml")
                   + '\n[[component]]\nname = "tick"\ntype = "checkbox"\n'
                     'x = 0\ny = 40\nw = 20\nh = 20\n')
        by_name = {entry["name"]: entry for entry in properties(
            self.index(), self.read(), "page0", "title")["attributes"]}
        self.assertEqual(by_name["xcen"]["labels"], [{"value": 0, "label": "left"},
                                                     {"value": 1, "label": "centre"},
                                                     {"value": 2, "label": "right"}])
        self.assertEqual((by_name["x"]["labels"], by_name["pic"]["labels"]), ([], []))
        # A yes or no, whose choices are its two answers.
        ticked = {entry["name"]: entry for entry in properties(
            self.index(), self.read(), "page0", "tick")["attributes"]}["val"]
        self.assertEqual(ticked["labels"], [{"value": 0, "label": "not ticked"},
                                            {"value": 1, "label": "ticked"}])


class AttributeEditTest(EditingTestCase):

    def test_setting_a_value(self):
        self.assertEqual(self.table(self.edited(txt="Hello"))["txt"], "Hello")

    def picked(self, **values) -> dict:
        """The title's table once `values` are set, colours asked for as the
        nearest the screen holds, as a picked colour is."""
        edits = attribute_edits(self.index(), self.read(), "page0", "title", values,
                                nearest_colours=True)
        return self.table(edited_text(self.text("pages/page0.page.toml"), edits))

    def test_a_picked_colour_stored_as_the_nearest_the_screen_holds(self):
        # Each channel takes the nearest of its levels as written from 0 to
        # 255: red 1e (30) is nearer 33 (21) than 24 (18), which keeping its
        # top bits would give; green 3e (62) nearer 60 (3c) than 65; blue 7f
        # (127) nearer 123 (7b) than 132.
        self.assertEqual(self.picked(pco="#1e3e7f")["pco"], "#213c7b")
        # Halfway between two levels, the lower: red and blue 20 between 16
        # and 24, green 14 between 12 and 16.
        self.assertEqual(self.picked(pco="#140e14")["pco"], "#100c10")
        # The ends.
        self.assertEqual(self.picked(pco="#fefefe")["pco"], "#ffffff")
        self.assertEqual(self.picked(bco="#010101")["bco"], "#000000")
        # Values other than colours are set as typed.
        self.assertEqual(self.picked(xcen="2", pco="#ffffff")["xcen"], 2)

    def test_a_typed_colour_stored_as_typed(self):
        self.assertEqual(self.table(self.edited(pco="#1e3e7f"))["pco"], "#1e3e7f")

    def test_a_new_key_in_the_types_order(self):
        text = self.edited(pco="#ff0000", xcen="2")
        self.assertEqual((self.table(text)["pco"], self.table(text)["xcen"]), ("#ff0000", 2))
        keys = list(self.table(text))
        self.assertLess(keys.index("pco"), keys.index("xcen"))
        self.assertLess(keys.index("xcen"), keys.index("txt"))

    def test_a_page_file_without_a_final_newline(self):
        # spax goes after txt, the table's last line, and the file's.
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml").rstrip("\n"))
        text = self.edited(spax="3")
        self.assertEqual((self.table(text)["txt"], self.table(text)["spax"]), ("x", 3))

    def test_setting_back_the_default_removes_the_key(self):
        self.write("pages/page0.page.toml", self.edited(xcen="2"))
        self.assertNotIn("xcen", self.table(self.edited(xcen="1")))

    def test_placement_and_defaults_false_tables_keep_their_keys(self):
        self.assertEqual(self.table(self.edited(x="0"))["x"], 0)
        # A table marked defaults = false lists every attribute, as extract writes it.
        full = properties(self.index(), self.read(), "page0", "title")
        lines = ['name = "title"', 'type = "text"', "defaults = false"]
        lines += ["%s = %s" % (entry["name"], _toml(entry["value"]))
                  for entry in full["attributes"]]
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml").split("[[component]]")[0]
                   + "[[component]]\n" + "\n".join(lines) + "\n")
        self.write("pages/page0.page.toml", self.edited(xcen="2"))
        self.assertEqual(self.table(self.edited(xcen="1"))["xcen"], 1)

    def test_pictures_and_fonts_by_name(self):
        # Font 0, Sans20, is the type's default: the table leaves it out.
        text = self.edited(pic="dot", font="Sans20")
        self.assertEqual(self.table(text)["pic"], "dot")
        self.assertNotIn("font", self.table(text))
        self.write("pages/page0.page.toml", text)
        self.assertNotIn("pic", self.table(self.edited(pic="none")))

    def test_numbers_as_typed(self):
        self.assertEqual(self.table(self.edited(x="010", y="0x10"))["x"], 10)
        self.assertEqual(self.table(self.edited(y="0x10"))["y"], 16)

    def test_a_direction_written_as_a_number(self):
        # A scrolling text's dir is a number; a page file nxwright wrote
        # before held it as a text of its byte, which reads as that number.
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml")
                   + '\n[[component]]\nname = "g0"\ntype = "scrolling-text"\nx = 0\ny = 100\n'
                     'w = 100\nh = 30\ndir = "\\u0001"\n')
        self.assertEqual(self.table(self.edited("g0", dir="2"), "g0")["dir"], 2)

    def test_a_picture_named_by_digits(self):
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app["pictures"].append("2")))
        self.assertEqual(self.table(self.edited(pic="2"))["pic"], "2")
        self.assertEqual(self.table(self.edited(pic="0"))["pic"], "dot")

    def test_values_the_build_refuses(self):
        for attribute, value, message in (("x", "left", "x must be a number"),
                                          ("pco", "red", "colour"),
                                          ("pic", "nowhere", "nowhere"),
                                          ("colour", "1", "has no attribute colour")):
            with self.subTest(attribute=attribute), self.assertRaisesRegex(NxwrightError, message):
                self.edited(**{attribute: value})

    def test_a_moved_component(self):
        text = self.edited(x="40", y="50", w="60", h="70")
        self.assertEqual([self.table(text)[key] for key in "xywh"], [40, 50, 60, 70])


def _toml(value) -> str:
    return '"%s"' % value if isinstance(value, str) else str(value)


class DefaultEventTest(EditingTestCase):

    def test_code_in_the_pages_own_file(self):
        self.write("pages/page0.nx", "on page0.load:\n  sys0 = 1\n\non title.down:\n  sys0 = 2\n")
        found = default_event(self.index(), self.read(), "page0", "title")
        self.assertEqual((found["path"], found["line"], found["character"], found["edit"]),
                         ("pages/page0.nx", 4, 2, None))
        found = default_event(self.index(), self.read(), "page0", "page0")
        self.assertEqual((found["line"], found["edit"]), (1, None))

    def test_code_in_an_included_file(self):
        self.write("pages/lib/shared.nx", "on title.down:\n  sys0 = 3\n")
        self.write("pages/page0.nx", 'include "lib/shared.nx"\n')
        found = default_event(self.index(), self.read(), "page0", "title")
        self.assertEqual((found["path"], found["line"]), ("pages/lib/shared.nx", 1))

    def test_no_code_adds_the_heading(self):
        for text, expected, cursor in (("", "on title.down:\n", 1),
                                       ("on page0.load:\n  sys0 = 1\n",
                                        "on page0.load:\n  sys0 = 1\n\non title.down:\n", 4),
                                       ("on page0.load:\n  sys0 = 1",
                                        "on page0.load:\n  sys0 = 1\n\non title.down:\n", 4),
                                       # One blank line, as pasting leaves, whatever
                                       # blank lines the file ends with.
                                       ("on page0.load:\n  sys0 = 1\n\n\n",
                                        "on page0.load:\n  sys0 = 1\n\non title.down:\n", 4),
                                       ("\n\n", "on title.down:\n", 1)):
            with self.subTest(text=text):
                self.write("pages/page0.nx", text)
                found = default_event(self.index(), self.read(), "page0", "title")
                self.assertEqual(edited_text(text, [found["edit"]]), expected)
                self.assertEqual((found["path"], found["line"], found["character"]),
                                 ("pages/page0.nx", cursor, 0))

    def test_a_type_without_events_has_none(self):
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml")
                   + '\n[[component]]\nname = "count"\ntype = "variable"\n')
        self.assertIsNone(default_event(self.index(), self.read(), "page0", "count"))
        self.assertIsNone(self.request("nxwright/defaultEvent", name="count")["result"])
        self.assertEqual(component_events(self.index(), self.read(), "page0", "count"), [])

    def test_the_first_event_with_code(self):
        # A text's events are down, then up: up's code alone opens up, and
        # with both, down opens, whatever their order in the file.
        self.write("pages/page0.nx", "on title.up:\n  sys0 = 5\n")
        found = default_event(self.index(), self.read(), "page0", "title")
        self.assertEqual((found["path"], found["line"], found["edit"]), ("pages/page0.nx", 1, None))
        self.write("pages/page0.nx", "on title.up:\n  sys0 = 5\n\non title.down:\n  sys0 = 6\n")
        found = default_event(self.index(), self.read(), "page0", "title")
        self.assertEqual((found["line"], found["edit"]), (4, None))

    def test_an_event_asked_for(self):
        self.write("pages/page0.nx", "on title.down:\n  sys0 = 6\n")
        found = default_event(self.index(), self.read(), "page0", "title", "up")
        self.assertEqual(edited_text(self.text("pages/page0.nx"), [found["edit"]]),
                         "on title.down:\n  sys0 = 6\n\non title.up:\n")
        found = default_event(self.index(), self.read(), "page0", "title", "down")
        self.assertEqual((found["line"], found["edit"]), (1, None))
        with self.assertRaisesRegex(NxwrightError, "type text has no event slide"):
            default_event(self.index(), self.read(), "page0", "title", "slide")

    def test_each_event_and_where_its_code_is(self):
        self.write("pages/lib/shared.nx", "on title.up:\n  sys0 = 3\n")
        self.write("pages/page0.nx", 'include "lib/shared.nx"\n')
        self.assertEqual(component_events(self.index(), self.read(), "page0", "title"),
                         [{"event": "down", "path": None},
                          {"event": "up", "path": "pages/lib/shared.nx"}])
        reply = self.request("nxwright/componentEvents", name="title")["result"]
        self.assertEqual(reply, [{"event": "down", "uri": None},
                                 {"event": "up", "uri": uri_of(self.root / "pages/lib/shared.nx")}])
        reply = self.request("nxwright/defaultEvent", name="title", event="up")["result"]
        self.assertEqual((reply["uri"], reply["line"]),
                         (uri_of(self.root / "pages/lib/shared.nx"), 1))


class ServerRequestTest(EditingTestCase):

    def test_requests(self):
        reply = self.request("nxwright/setAttributes", name="title", values={"txt": "Hi"})
        uri = uri_of(self.root / "pages/page0.page.toml")
        self.assertEqual(list(reply["result"]["changes"]), [uri])
        self.assertEqual(self.request("nxwright/componentProperties", name="title")
                         ["result"]["type"], "text")
        found = self.request("nxwright/defaultEvent", name="title")["result"]
        self.assertEqual(found["uri"], uri_of(self.root / "pages/page0.nx"))
        self.assertIn("error", self.request("nxwright/setAttributes", name="title",
                                            values={"x": "left"}))
        # A picked colour, asked for as the nearest the screen holds.
        reply = self.request("nxwright/setAttributes", name="title", values={"pco": "#1e3e7f"},
                             nearestColours=True)
        self.assertIn('pco = "#213c7b"', reply["result"]["changes"][uri][0]["newText"])

    def test_the_pages_objects(self):
        found = self.request("nxwright/pageObjects")["result"]
        self.assertEqual(found["page"], "page0")
        self.assertEqual([(entry["name"], entry["type"]) for entry in found["objects"]],
                         [("page0", "page"), ("title", "text")])
        title = found["objects"][1]
        lines = self.text("pages/page0.page.toml").split("\n")
        # A table's lines run to the next table, or the end of the file.
        self.assertEqual((lines[title["firstLine"]], title["lastLine"]),
                         ("[[component]]", len(lines) - 1))

    def test_the_objects_of_a_half_typed_page_file(self):
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml") + "[[component]]\nname = ")
        found = self.request("nxwright/pageObjects")["result"]
        self.assertEqual([entry["name"] for entry in found["objects"]], ["page0", "title"])

    def test_no_objects_outside_a_page(self):
        connection = initialized()
        connection.handle({"jsonrpc": "2.0", "id": 2, "method": "nxwright/pageObjects",
                           "params": {"textDocument": {"uri": uri_of(self.root / "app.toml")}}})
        self.assertIsNone(connection.sent[-1]["result"])


class KeyBindingTest(EditingTestCase):
    """What setting a component's `key` means, for the properties panel."""

    def binding(self, key, name: str = "title", fonts=()) -> dict:
        """What setting `key` on `name` means, less "fonts", the fonts the
        Chinese keyboard takes, which must be `fonts`."""
        found = key_binding(self.index(), self.read(), "page0", name, key)
        self.assertEqual(found.pop("fonts"), list(fonts))
        return found

    def test_what_setting_key_means(self):
        # The folder's title is of local scope, which a keyboard does not take.
        self.assertEqual(self.binding(1), {"keyboard": "keyboard", "present": False,
                                           "local": True, "chinese": False})
        self.assertEqual((self.binding(2)["keyboard"], self.binding(3)["keyboard"]),
                         ("keypad", "speed-dial"))
        # Chinese input, whose keyboard nxwright adds to a gb2312 folder alone.
        self.assertEqual(self.binding(4), {"keyboard": None, "present": False, "local": True,
                                           "chinese": True})
        # No keyboard: the scope does not matter.
        self.assertEqual(self.binding(255), {"keyboard": None, "present": False,
                                             "local": False, "chinese": False})

    def test_chinese_input_in_a_gb2312_folder(self):
        self.write("app.toml", self.text("app.toml").replace('"iso-8859-1"', '"gb2312"'))
        # The folder's fonts, in iso-8859-1, are no font for the keyboard.
        self.assertEqual(self.binding(4), {"keyboard": "chinese-input", "present": False,
                                           "local": True, "chinese": True})
        font = self.root.parent / "Zh.zi"
        font.write_bytes(gb2312_font(16))
        add_font_file(self.root, font, "Zh")
        self.assertEqual(self.binding(4, fonts=["Zh"])["keyboard"], "chinese-input")
        listed = self.request("nxwright/chineseKeyboardFonts", folder=str(self.root))
        self.assertEqual(listed["result"], {"fonts": ["Zh"]})
        added = self.request("nxwright/addKeyboard", keyboard="chinese-input", font="Zh")
        self.assertEqual((added["result"]["page"], added["result"]["font"]), ("keybdAP", "Zh"))
        self.assertTrue(self.binding(4, fonts=["Zh"])["present"])

    def test_a_global_component_and_a_keyboard_the_folder_has(self):
        add_keyboard(self.root, "keypad")
        self.write("pages/page0.page.toml", self.edited(vscope="1"))
        self.assertEqual(self.binding(2), {"keyboard": "keypad", "present": True,
                                           "local": False, "chinese": False})
        self.assertFalse(self.binding(1)["present"])

    def test_an_object_without_key(self):
        with self.assertRaisesRegex(NxwrightError, "type page has no attribute key"):
            self.binding(1, "page0")

    def test_the_value_as_typed(self):
        self.assertEqual(self.binding(" 2 ")["keyboard"], "keypad")
        # An emptied field is no key, as setting the attribute would say.
        with self.assertRaisesRegex(NxwrightError, "key must be a number"):
            self.binding("")

    def test_the_requests(self):
        binding = self.request("nxwright/keyBinding", name="title", key=1)["result"]
        self.assertEqual(binding["keyboard"], "keyboard")
        added = self.request("nxwright/addKeyboard", keyboard="keyboard")["result"]
        self.assertEqual((added["page"], added["font"].startswith("NotoSans"), added["warning"]),
                         ("keybdA", True, None))
        self.assertTrue((self.root / "pages" / "keybdA.page.toml").is_file())
        self.assertTrue(self.request("nxwright/keyBinding", name="title", key=1)
                        ["result"]["present"])
        self.assertIn("the folder has the keyboard already",
                      self.request("nxwright/addKeyboard", keyboard="keyboard")["error"]["message"])

    def test_a_font_in_another_encoding_comes_with_the_warning(self):
        # koi8-r, some of whose characters Noto Sans lacks.
        self.write("app.toml", self.text("app.toml").replace('"iso-8859-1"', '"koi8-r"'))
        warning = self.request("nxwright/addKeyboard", keyboard="keypad")["result"]["warning"]
        self.assertIn("is in iso-8859-1, not in the folder's koi8-r", warning)

    def test_unsaved_changes_to_app_toml_are_refused(self):
        connection = initialized()
        app = uri_of(self.root / "app.toml")
        connection.handle({"jsonrpc": "2.0", "method": "textDocument/didOpen", "params": {
            "textDocument": document_item(app, self.text("app.toml") + "\n")}})
        connection.handle({"jsonrpc": "2.0", "id": 2, "method": "nxwright/addKeyboard", "params": {
            "textDocument": {"uri": uri_of(self.root / "pages/page0.page.toml")},
            "keyboard": "keypad"}})
        self.assertIn("save or revert the changes to app.toml first",
                      connection.sent[-1]["error"]["message"])
        self.assertFalse((self.root / "pages" / "keybdB.page.toml").exists())


if __name__ == "__main__":
    unittest.main()
