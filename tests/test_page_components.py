"""Adding components to a page from the page preview, deleting them,
copying and pasting them, pasting parts of one onto others, and grouping
them: the edits of the language server's nxwright/addComponent,
nxwright/deleteComponents, nxwright/copyComponents,
nxwright/pasteComponents, nxwright/pasteParts, and nxwright/groupComponents
requests."""
import tomllib
import unittest

import tomli_w

from nxwright import NxwrightError
from nxwright.language_server.file_texts import uri_of
from nxwright.language_server.page_components import (add_component, clear_events,
                                                       component_types, copy_components,
                                                       delete_components,
                                                       group_components, line_edits,
                                                       paste_components, paste_parts,
                                                       lock_components, place_components,
                                                       reorder_components)
from tests.test_folder_check import edited_app
from tests.test_page_editing import ServerTestCase


def applied(text: str, edits: list) -> str:
    """Returns `text` with the protocol's TextEdits applied, as an editor
    applies them: each range from its start up to its end, in a text of
    plain ASCII, where a character is a column."""
    lines = text.split("\n")

    def offset(position: dict) -> int:
        return sum(len(line) + 1 for line in lines[:position["line"]]) + position["character"]
    for edit in sorted(edits, key=lambda edit: offset(edit["range"]["start"]), reverse=True):
        start, end = offset(edit["range"]["start"]), offset(edit["range"]["end"])
        text = text[:start] + edit["newText"] + text[end:]
    return text


class ComponentsTestCase(ServerTestCase):
    """page0 holds the text "title"; page "second" has one of its own."""

    def exists(self, path: str) -> bool:
        return (self.root / path).is_file()

    def add(self, type_name: str, x: int = 0, y: int = 0) -> str:
        """Adds a component to page0's file, and returns its name."""
        found = add_component(self.index(), self.read(), self.exists, "page0", type_name, x, y)
        self.assertEqual(list(found["edits"]), ["pages/page0.page.toml"])
        self.write("pages/page0.page.toml", applied(self.text("pages/page0.page.toml"),
                                                    found["edits"]["pages/page0.page.toml"]))
        return found["name"]

    def delete(self, *names: str) -> list:
        """Deletes components of page0, and returns the places naming them elsewhere."""
        found = delete_components(self.index(), self.read(), "page0", list(names))
        for path, edits in found["edits"].items():
            self.write(path, applied(self.text(path), edits))
        return found["namedElsewhere"]

    def tables(self) -> list:
        return tomllib.loads(self.text("pages/page0.page.toml"))["component"]

    def set_group(self, page: str, name: str, groupid0: int, groupid1: int = 0):
        """Writes a group's pair into the table of `name`, as the Editor or a
        hand would, a groupid1 of 0, the default, left out."""
        path = "pages/%s.page.toml" % page
        heading = 'name = "%s"\n' % name
        pair = "groupid0 = %d\n" % groupid0 + ("groupid1 = %d\n" % groupid1 if groupid1 else "")
        self.write(path, self.text(path).replace(heading, heading + pair))


class AddTest(ComponentsTestCase):

    def test_a_gauge_as_the_editor_adds_one_on_its_series(self):
        # The Editor 1.68.2 added a gauge with sta 1, a colour, on the basic,
        # Enhanced, and Discovery series, whose compile refuses nxwright's
        # default, 3; on an Intelligent screen it keeps it.
        self.add("gauge")
        self.assertNotIn("sta", self.tables()[-1])
        for model in ("NX4832T035", "NX4832K035", "NX4832F035"):
            with self.subTest(model=model):
                self.write("app.toml", edited_app(self.text("app.toml"),
                                                  lambda app, model=model: app.update(
                                                      screen=model)))
                self.add("gauge")
                self.assertEqual(self.tables()[-1]["sta"], 1)

    def test_named_and_sized_as_the_editor_makes_it(self):
        self.assertEqual(self.add("text", 40, 50), "t0")
        self.assertEqual(self.tables()[-1], {"name": "t0", "type": "text", "x": 40, "y": 50,
                                             "w": 100, "h": 30})
        # The table follows the last one after a blank line, as extract writes them.
        self.assertTrue(self.text("pages/page0.page.toml").endswith(
            'txt = "x"\n\n[[component]]\nname = "t0"\ntype = "text"\nx = 40\ny = 50\nw = 100\n'
            'h = 30\n'))
        self.assertEqual(self.add("gauge"), "z0")
        self.assertEqual(self.tables()[-1], {"name": "z0", "type": "gauge", "x": 0, "y": 0,
                                             "w": 220, "h": 220})
        self.assertEqual(self.check(["page0"]).errors(), [])

    def test_the_lowest_number_no_object_and_no_page_has(self):
        self.write("pages/t1.page.toml", self.text("pages/second.page.toml")
                   .replace('name = "second"', 'name = "t1"'))
        self.write("pages/t1.nx", "")
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app["pages"].append("t1")))
        self.assertEqual([self.add("text") for _ in range(3)], ["t0", "t2", "t3"])
        self.delete("t2")
        self.assertEqual(self.add("text"), "t2")

    def test_a_component_without_a_place(self):
        self.assertEqual(self.add("timer", 40, 50), "tm0")
        self.assertEqual(self.tables()[-1], {"name": "tm0", "type": "timer"})

    def test_what_is_no_type_of_component(self):
        for type_name in ("page", "label"):
            with self.subTest(type_name=type_name), \
                    self.assertRaisesRegex(NxwrightError, "%s is not a type of component" % type_name):
                self.add(type_name)

    def test_a_page_that_would_no_longer_build(self):
        # A page holds at most 256 objects: here the page, title, and 254 more.
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml") + "".join(
            '\n[[component]]\nname = "v%d"\ntype = "variable"\n' % number for number in range(254)))
        with self.assertRaisesRegex(NxwrightError, "the page would not build after adding va0: "
                                                   "pages/page0.page.toml"):
            self.add("variable")

    def test_a_page_that_did_not_build_takes_it_still(self):
        self.write("pages/page0.nx", "on page0.load:\n  nobody.txt = 1\n")
        self.assertEqual(self.add("text"), "t0")

    def test_the_types_offered(self):
        types = component_types(self.read(), "page0")
        self.assertEqual(types[0], {"type": "audio", "placed": False})
        self.assertIn({"type": "text", "placed": True}, types)
        self.assertNotIn("page", [entry["type"] for entry in types])
        self.assertEqual(len(types), 30)


class DeleteTest(ComponentsTestCase):

    def test_the_table_and_its_code_with_the_comment_above_it(self):
        self.add("button")
        self.write("pages/page0.nx", "on page0.load:\n  sys0 = 1\n\n// Says hello\non title.down:\n"
                                     "  sys0 = 2\n\n// The button\non b0.down:\n  sys0 = 3\n")
        self.assertEqual(self.delete("title"), [])
        self.assertEqual([table["name"] for table in self.tables()], ["b0"])
        self.assertEqual(self.text("pages/page0.nx"),
                         "on page0.load:\n  sys0 = 1\n\n// The button\non b0.down:\n  sys0 = 3\n")
        self.assertEqual(self.check(["page0"]).errors(), [])

    def test_the_first_and_the_last_events(self):
        self.add("button")
        for code, left in (("on title.down:\n  sys0 = 2\n\non b0.down:\n  sys0 = 3\n",
                            "on b0.down:\n  sys0 = 3\n"),
                           ("on b0.down:\n  sys0 = 3\n\non title.down:\n  sys0 = 2\n",
                            "on b0.down:\n  sys0 = 3\n"),
                           ("on title.down:\n  sys0 = 2\n", "")):
            with self.subTest(code=code):
                self.write("pages/page0.nx", code)
                found = delete_components(self.index(), self.read(), "page0", ["title"])
                self.assertEqual(applied(code, found["edits"]["pages/page0.nx"]), left)

    def test_the_last_table_of_the_page(self):
        self.add("text")
        self.delete("t0")
        self.assertTrue(self.text("pages/page0.page.toml").endswith('txt = "x"\n'))

    def test_a_tables_comment_goes_with_it_and_the_next_ones_stays(self):
        # The comment lines right above a table's header are its own, as
        # those above an event's heading are.
        self.add("button")
        text = self.text("pages/page0.page.toml")
        self.write("pages/page0.page.toml", text.replace(
            '[[component]]\nname = "title"', '# The title\n[[component]]\nname = "title"').replace(
            '[[component]]\nname = "b0"', '# The button\n[[component]]\nname = "b0"'))
        self.delete("title")
        self.assertTrue(self.text("pages/page0.page.toml").endswith(
            'h = 480\n\n# The button\n[[component]]\nname = "b0"\ntype = "button"\nx = 0\ny = 0\n'
            'w = 100\nh = 50\n'))

    def test_the_rest_of_the_files_is_left_as_it_is(self):
        # Two blank lines elsewhere are the user's: only the deleted lines go.
        self.add("button")
        code = "on page0.load:\n  sys0 = 1\n\n\non title.down:\n  sys0 = 2\n\non b0.down:\n  sys0 = 3\n"
        self.write("pages/page0.nx", code)
        self.delete("b0")
        self.assertEqual(self.text("pages/page0.nx"),
                         "on page0.load:\n  sys0 = 1\n\n\non title.down:\n  sys0 = 2\n")

    def test_code_in_a_file_only_this_page_includes(self):
        self.write("pages/lib/mine.nx", "on title.down:\n  sys0 = 2\n")
        self.write("pages/page0.nx", 'include "lib/mine.nx"\n')
        self.delete("title")
        self.assertEqual(self.text("pages/lib/mine.nx"), "")

    def test_code_in_a_file_other_pages_include_is_refused(self):
        self.write("pages/lib/shared.nx", "on title.down:\n  sys0 = 2\n")
        for page in ("page0", "second"):
            self.write("pages/%s.nx" % page, 'include "lib/shared.nx"\n')
        with self.assertRaisesRegex(NxwrightError, "the code of title is in pages/lib/shared.nx, "
                                                   "which other pages include too"):
            self.delete("title")

    def test_the_places_other_code_names_it(self):
        # Code naming it in its own events goes with them; elsewhere it stays.
        self.write("pages/page0.nx", 'on page0.load:\n  title.txt = "a"\n\non title.down:\n'
                                     '  title.txt = "b"\n')
        self.write("pages/second.nx", 'on second.load:\n  page0.title.txt = "c"\n')
        self.assertEqual(self.delete("title"), [{"path": "pages/page0.nx", "line": 1},
                                                {"path": "pages/second.nx", "line": 1}])

    def test_the_page_and_an_object_it_lacks(self):
        with self.assertRaisesRegex(NxwrightError, "a page is not deleted here"):
            self.delete("page0")
        with self.assertRaisesRegex(NxwrightError, "page page0 has no object nobody"):
            self.delete("nobody")


class CopyPasteTest(ComponentsTestCase):
    """page0 holds the text "title", at (0, 0), whose down event says hello,
    and the button b0; page "second" has a "title" of its own, at (0, 0)."""

    def setUp(self):
        super().setUp()
        self.add("button", 200, 100)
        self.write("pages/page0.nx", "on page0.load:\n  sys0 = 1\n\n// Says hello\non title.down:\n"
                                     '  title.txt = "hello"\n')

    def copy(self, *names: str) -> dict:
        return copy_components(self.index(), self.read(), "page0", list(names))

    def paste(self, page: str, copied: dict, **where) -> dict:
        """Pastes into `page`, where `where` says, writing the files, and
        returns the reply."""
        found = paste_components(self.index(), self.read(), self.exists, page, copied["text"],
                                 copied.get("code", []), **where)
        for path, edits in found["edits"].items():
            self.write(path, applied(self.text(path) if self.exists(path) else "", edits))
        return found

    def tables_of(self, page: str) -> list:
        return tomllib.loads(self.text("pages/%s.page.toml" % page))["component"]

    def test_copied_tables_as_the_page_file_holds_them_and_their_code(self):
        copied = self.copy("b0", "title")
        # In ID order, a blank line apart, as a page file holds them.
        self.assertEqual(copied["text"], '[[component]]\nname = "title"\ntype = "text"\nx = 0\n'
                                         'y = 0\nw = 100\nh = 30\ntxt = "x"\n\n[[component]]\n'
                                         'name = "b0"\ntype = "button"\nx = 200\ny = 100\n'
                                         'w = 100\nh = 50\n')
        self.assertEqual(copied["code"], ['// Says hello\non title.down:\n  title.txt = "hello"\n'])

    def test_a_copied_table_takes_its_own_comment_alone(self):
        text = self.text("pages/page0.page.toml")
        self.write("pages/page0.page.toml", text.replace(
            '[[component]]\nname = "title"', '# The title\n[[component]]\nname = "title"').replace(
            '[[component]]\nname = "b0"', '# The button\n[[component]]\nname = "b0"'))
        copied = self.copy("title", "b0")
        self.assertEqual(copied["text"],
                         '# The title\n[[component]]\nname = "title"\ntype = "text"\nx = 0\ny = 0\n'
                         'w = 100\nh = 30\ntxt = "x"\n\n# The button\n[[component]]\nname = "b0"\n'
                         'type = "button"\nx = 200\ny = 100\nw = 100\nh = 50\n')
        # Pasted, each keeps its comment; moved, as the page has a title at
        # the place this one was copied from.
        self.paste("second", copied)
        self.assertTrue(self.text("pages/second.page.toml").endswith(
            '\n\n# The title\n[[component]]\nname = "title0"\ntype = "text"\nx = 10\ny = 10\n'
            'w = 100\nh = 30\ntxt = "x"\n\n# The button\n[[component]]\nname = "b0"\n'
            'type = "button"\nx = 210\ny = 110\nw = 100\nh = 50\n'))

    def test_pasted_into_the_same_page_renamed_and_moved(self):
        found = self.paste("page0", self.copy("title"))
        self.assertEqual((found["names"], found["created"]), (["title0"], []))
        self.assertEqual(self.tables_of("page0")[-1], {"name": "title0", "type": "text", "x": 10,
                                                       "y": 10, "w": 100, "h": 30, "txt": "x"})
        # The heading follows the new name; the code under it is as copied.
        self.assertTrue(self.text("pages/page0.nx").endswith(
            '  title.txt = "hello"\n\n// Says hello\non title0.down:\n  title.txt = "hello"\n'))
        self.assertEqual(self.check(["page0"]).errors(), [])

    def test_code_copied_from_an_included_file(self):
        self.write("pages/lib/hello.nx", "on title.down:\n  sys0 = 4\n")
        self.write("pages/page0.nx", 'include "lib/hello.nx"\n')
        self.assertEqual(self.copy("title")["code"], ["on title.down:\n  sys0 = 4\n"])

    def test_pasted_copies_are_regrouped(self):
        # Unlike the Editor, which keeps the pair: copies of several members
        # of one group form a new group of their own, and a member copied
        # alone joins none. So no paste joins a group already on the page.
        self.add("button", 300, 100)
        for name in ("title", "b0"):
            self.set_group("page0", name, 2987306302, 2958789535)
        self.set_group("page0", "b1", 1)
        self.paste("page0", self.copy("title", "b0", "b1"))
        self.assertEqual([(table["name"], table.get("groupid0"), table.get("groupid1"))
                          for table in self.tables_of("page0")[3:]],
                         [("title0", 2, None), ("b2", 2, None), ("b3", None, None)])
        # Into another page, whose own title holds the very pair copied: the
        # copies form a group of their own rather than join it.
        self.set_group("second", "title", 2987306302, 2958789535)
        self.paste("second", self.copy("title", "b0"))
        self.assertEqual([(table.get("groupid0"), table.get("groupid1"))
                          for table in self.tables_of("second")],
                         [(2987306302, 2958789535), (1, None), (1, None)])

    def test_pasted_into_another_page_where_it_fits(self):
        found = self.paste("second", self.copy("b0"))
        self.assertEqual(found["names"], ["b0"])
        self.assertEqual(self.tables_of("second")[-1]["x"], 200)

    def test_moved_only_while_an_original_is_at_its_place(self):
        copied = self.copy("title")
        self.write("pages/page0.page.toml", self.edited(x="40"))
        self.paste("page0", copied)
        self.assertEqual([self.tables_of("page0")[-1][key] for key in ("name", "x", "y")],
                         ["title0", 0, 0])

    def test_pasted_code_naming_what_the_page_lacks(self):
        # Code is better pasted and mended than lost: the checks then show it.
        self.write("pages/page0.nx", "on b0.down:\n  title.txt = \"b\"\n  sys0 = 1\n")
        self.paste("second", self.copy("b0"))
        self.assertEqual(self.text("pages/second.nx"), 'on b0.down:\n  title.txt = "b"\n  sys0 = 1\n')

    def test_the_pages_own_code_file_made_when_it_has_none(self):
        (self.root / "pages" / "second.nx").unlink()
        found = self.paste("second", self.copy("title"))
        self.assertEqual(found["created"], ["pages/second.nx"])
        self.assertEqual(self.text("pages/second.nx"),
                         '// Says hello\non title0.down:\n  title.txt = "hello"\n')

    def test_a_name_too_long_to_number_and_names_the_editor_refuses(self):
        long_name = '[[component]]\nname = "abcdefghijklmn"\ntype = "text"\nx = 0\ny = 0\nw = 9\nh = 9\n'
        self.paste("page0", {"text": long_name})
        self.assertEqual(self.paste("page0", {"text": long_name})["names"], ["t0"])
        audio = long_name.replace("abcdefghijklmn", "audio")
        self.paste("page0", {"text": audio})
        self.assertEqual(self.paste("page0", {"text": audio})["names"], ["audio2"])

    def test_tables_typed_by_hand(self):
        # Lines ended as Windows ends them, and two tables of one name.
        text = ('[[component]]\r\nname = "title"\r\ntype = "text"\r\nx = 0\r\ny = 0\r\nw = 9\r\n'
                'h = 9\r\n\r\n[[component]]\r\nname = "title"\r\ntype = "text"\r\nx = 0\r\n'
                'y = 5\r\nw = 9\r\nh = 9\r\n')
        self.assertEqual(self.paste("page0", {"text": text})["names"], ["title0", "title1"])
        self.assertEqual([(table["x"], table["y"]) for table in self.tables_of("page0")[-2:]],
                         [(10, 10), (10, 15)])
        # A table without its y is the build's to refuse.
        with self.assertRaisesRegex(NxwrightError, "title3 needs its place on the screen; y missing"):
            self.paste("page0", {"text": text.replace("y = 5\r\n", "")})

    def test_a_page_file_that_does_not_read(self):
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml") + "[[component]]\nname = ")
        with self.assertRaisesRegex(NxwrightError, "pages/page0.page.toml: "):
            self.paste("page0", self.copy("title"))

    def test_text_that_is_not_components_tables(self):
        for text, message in (('[page]\nname = "x"\n', "holds no components' tables, but page"),
                              ("hello there", "holds no components' tables"),
                              ("component = 5", "holds no components' tables"),
                              ('[[component]]\nname = "a"\n', "no type of component"),
                              ('[[component]]\nname = "a"\ntype = "page"\n',
                               "no type of component"),
                              ('[[component]]\nname = "a"\ntype = [1]\n',
                               "no type of component")):
            with self.subTest(text=text), self.assertRaisesRegex(NxwrightError, message):
                self.paste("page0", {"text": text})

    def test_pasted_here_keeping_their_places_to_each_other(self):
        # The box holding the copies with a place, its corner at (0, 0),
        # moves to the point; a copy without a place stays without.
        self.add("timer")
        found = self.paste("page0", self.copy("title", "b0", "tm0"), at=(300, 200))
        self.assertEqual(found["names"], ["title0", "b1", "tm1"])
        self.assertEqual([(table.get("x"), table.get("y")) for table in self.tables_of("page0")[-3:]],
                         [(300, 200), (500, 300), (None, None)])

    def test_pasted_here_near_the_bottom_right_corner(self):
        # The box, 300 by 150, would pass the page's edges: it moves back in.
        self.paste("page0", self.copy("title", "b0"), at=(700, 400))
        self.assertEqual([(table["x"], table["y"]) for table in self.tables_of("page0")[-2:]],
                         [(500, 330), (700, 430)])

    def test_pasted_here_wider_than_the_page(self):
        # At the page's left edge, its height fitting where it was pasted.
        # The folder's screen takes a component reaching past it.
        text = '[[component]]\nname = "wide"\ntype = "text"\nx = 50\ny = 0\nw = 900\nh = 9\n'
        self.paste("page0", {"text": text}, at=(300, 200))
        self.assertEqual([self.tables_of("page0")[-1][key] for key in ("x", "y")], [0, 200])

    def test_pasted_in_place_over_the_original(self):
        self.paste("page0", self.copy("title"), in_place=True)
        self.assertEqual([self.tables_of("page0")[-1][key] for key in ("name", "x", "y")],
                         ["title0", 0, 0])

    def test_tables_that_would_stop_the_page_building(self):
        text = self.copy("title")["text"].replace('txt = "x"', 'txt = "far too long a text"')
        with self.assertRaisesRegex(NxwrightError, "the page would not build after pasting"):
            self.paste("second", {"text": text})


class ClearEventsTest(ComponentsTestCase):
    """Clearing the code of components' events, the components kept. page0
    holds the text "title", whose down and up have code, and the button b0,
    whose down has."""

    def setUp(self):
        super().setUp()
        self.add("button", 200, 100)
        self.write("pages/page0.nx", 'on page0.load:\n  sys0 = 1\n\n// Says hello\non title.down:\n'
                                     '  title.txt = "hello"\n\non title.up:\n  sys0 = 2\n\n'
                                     'on b0.down:\n  sys0 = 3\n')

    def clear(self, *names: str) -> dict:
        """Clears the events of components of page0, writing the files, and
        returns the edits."""
        found = clear_events(self.index(), self.read(), "page0", list(names))
        for path, edits in found.items():
            self.write(path, applied(self.text(path), edits))
        return found

    def test_every_event_with_the_comment_above_it(self):
        self.clear("title")
        self.assertEqual(self.text("pages/page0.nx"),
                         "on page0.load:\n  sys0 = 1\n\non b0.down:\n  sys0 = 3\n")
        self.assertEqual([table["name"] for table in self.tables()], ["title", "b0"])

    def test_several_at_once(self):
        self.clear("title", "b0")
        self.assertEqual(self.text("pages/page0.nx"), "on page0.load:\n  sys0 = 1\n")

    def test_code_in_a_file_only_this_page_includes(self):
        self.write("pages/lib/mine.nx", "on b0.up:\n  sys0 = 4\n")
        self.write("pages/page0.nx", 'include "lib/mine.nx"\n\n' + self.text("pages/page0.nx"))
        self.clear("b0")
        self.assertEqual(self.text("pages/lib/mine.nx"), "")
        self.assertNotIn("b0.down", self.text("pages/page0.nx"))

    def test_code_in_a_file_other_pages_include_is_refused(self):
        self.write("pages/lib/shared.nx", "on b0.up:\n  sys0 = 4\n")
        for page in ("page0", "second"):
            self.write("pages/%s.nx" % page, 'include "lib/shared.nx"\n')
        with self.assertRaisesRegex(NxwrightError, "the code of b0 is in pages/lib/shared.nx, "
                                                   "which other pages include too"):
            self.clear("b0")

    def test_nothing_to_clear(self):
        self.clear("b0")
        self.assertEqual(self.clear("b0"), {})


class PasteSpecialTest(ComponentsTestCase):
    """page0 holds the text "title", at (0, 0), 100 by 30, whose down event
    says hello, and the buttons b0, at (200, 100), and b1, at (300, 100),
    each 100 by 50."""

    def setUp(self):
        super().setUp()
        self.add("button", 200, 100)
        self.add("button", 300, 100)
        self.write("pages/page0.nx", "on page0.load:\n  sys0 = 1\n\n// Says hello\non title.down:\n"
                                     '  title.txt = "hello"\n')

    def copy(self, *names: str) -> dict:
        return copy_components(self.index(), self.read(), "page0", list(names))

    def paste_parts(self, names: list, copied: dict, *parts: str) -> dict:
        """Pastes `parts` of `copied` onto the components `names` of page0,
        writing the files, and returns the reply."""
        found = paste_parts(self.index(), self.read(), self.exists, "page0", names,
                            copied["text"], copied.get("code", []), list(parts))
        for path, edits in found["edits"].items():
            self.write(path, applied(self.text(path) if self.exists(path) else "", edits))
        return found

    def notes(self, names: list, copied: dict, *parts: str) -> list:
        return self.paste_parts(names, copied, *parts)["notes"]

    def table_of(self, name: str) -> dict:
        return next(table for table in self.tables() if table["name"] == name)

    def set(self, name: str, **values):
        self.write("pages/page0.page.toml", self.edited(name, **values))

    def test_paste_without_code_changes_the_page_file_alone(self):
        found = paste_components(self.index(), self.read(), self.exists, "page0",
                                 self.copy("title")["text"], [])
        self.assertEqual(list(found["edits"]), ["pages/page0.page.toml"])

    def test_size_and_position_onto_one_and_onto_two(self):
        copied = self.copy("title")
        self.assertEqual(self.notes(["b0"], copied, "size"), [])
        self.assertEqual([self.table_of("b0")[key] for key in "xywh"], [200, 100, 100, 30])
        self.notes(["b0", "b1"], copied, "position")
        self.assertEqual([[self.table_of(name)[key] for key in "xywh"] for name in ("b0", "b1")],
                         [[0, 0, 100, 30], [0, 0, 100, 50]])

    def test_size_and_position_onto_a_component_without_a_place(self):
        timer = self.add("timer")
        before = self.text("pages/page0.page.toml")
        self.assertEqual(self.notes([timer], self.copy("title"), "size", "position"),
                         ["tm0 has no place on the screen, so no size or position was pasted "
                          "onto it"])
        self.assertEqual(self.text("pages/page0.page.toml"), before)

    def test_other_attributes_of_one_type(self):
        # A button describes bco and txt in words of its own: between two
        # buttons they mean the same.
        self.set("b0", bco="#ff0000", txt="go")
        self.set("b1", pco="#00ff00", lockobj="1")
        self.set_group("page0", "b1", 7)
        self.assertEqual(self.notes(["b1"], self.copy("b0"), "attributes"), [])
        b1 = self.table_of("b1")
        self.assertEqual((b1["bco"], b1["txt"]), ("#ff0000", "go"))
        # b0's pco is the type's default, which a table leaves out.
        self.assertNotIn("pco", b1)
        # Its name, place, size, lock, and group stay its own.
        self.assertEqual([b1[key] for key in ("name", "x", "y", "w", "h", "lockobj", "groupid0")],
                         ["b1", 300, 100, 100, 50, 1, 7])

    def test_other_attributes_across_two_types(self):
        # A colour and the text shown mean the same on a text and a button; a
        # button's style is another than a text's.
        self.set("title", bco="#ff0000", style="2")
        notes = self.notes(["b0", "b1"], self.copy("title"), "attributes")
        for name in ("b0", "b1"):
            table = self.table_of(name)
            self.assertEqual((table["bco"], table["txt"]), ("#ff0000", "x"))
            self.assertNotIn("style", table)
        self.assertEqual(notes, ["Not pasted onto %s, because they mean something else on a "
                                 "button: style" % name for name in ("b0", "b1")])

    def test_a_number_and_a_text_of_two_meanings(self):
        bar, slider = self.add("progress-bar"), self.add("slider")
        self.set(bar, dis="10")
        notes = self.notes([slider], self.copy(bar), "attributes")
        self.assertNotEqual(self.table_of(slider).get("dis"), 10)
        self.assertRegex(notes[0], r"^Not pasted onto h0, because .*: .*\bdis\b")
        picture, video = self.add("external-picture"), self.add("video")
        self.set(picture, path="sd0/a.jpg")
        notes = self.notes([video], self.copy(picture), "attributes")
        self.assertNotIn("path", self.table_of(video))
        self.assertRegex(notes[0], r"^Not pasted onto v0, because .*: .*\bpath\b")
        # "an" before a vowel's sound.
        number, xfloat = self.add("number"), self.add("xfloat")
        self.set(number, val="5")
        self.assertEqual(self.notes([xfloat], self.copy(number), "attributes"),
                         ["Not pasted onto %s, because they mean something else on an xfloat: val"
                          % xfloat])

    def test_a_value_the_selected_type_cannot_hold(self):
        # A number and a text share the meaning of style, but a text refuses
        # style 4, a button's 3D look.
        number = self.add("number")
        self.set(number, style="4")
        self.assertEqual(self.notes(["title"], self.copy(number), "attributes"),
                         ["Not pasted onto title, because a text can't hold the copied values: "
                          "style"])
        self.assertNotIn("style", self.table_of("title"))

    def test_code_replaces_an_events_and_is_added_for_another(self):
        self.write("pages/page0.nx", self.text("pages/page0.nx")
                   + "\non b0.down:\n  sys0 = 2\n\non b0.up:\n  sys0 = 3\n")
        self.assertEqual(self.notes(["b0"], self.copy("title"), "code"), [])
        self.assertEqual(self.text("pages/page0.nx"),
                         'on page0.load:\n  sys0 = 1\n\n// Says hello\non title.down:\n'
                         '  title.txt = "hello"\n\n// Says hello\non b0.down:\n'
                         '  b0.txt = "hello"\n\non b0.up:\n  sys0 = 3\n')
        # b1 has no code: its event goes at the end of the page's own file.
        self.notes(["b1"], self.copy("title"), "code")
        self.assertTrue(self.text("pages/page0.nx").endswith(
            '  sys0 = 3\n\n// Says hello\non b1.down:\n  b1.txt = "hello"\n'))

    def test_code_onto_two_components_each_named(self):
        self.notes(["b0", "b1"], self.copy("title"), "code")
        code = self.text("pages/page0.nx")
        for name in ("b0", "b1"):
            self.assertIn('on %s.down:\n  %s.txt = "hello"\n' % (name, name), code)

    def test_the_components_own_name_in_its_code(self):
        # Renamed where it stands for the component itself alone: not in a
        # quoted text, a comment, a longer name, or after a page's name.
        self.write("pages/page0.nx", 'on title.down:\n  title.txt = "title"  // title\n'
                                     "  page0.title.txt = title0.txt\n  vis title,0\n")
        self.notes(["b0"], self.copy("title"), "code")
        self.assertTrue(self.text("pages/page0.nx").endswith(
            'on b0.down:\n  b0.txt = "title"  // title\n  page0.title.txt = title0.txt\n'
            "  vis b0,0\n"))

    def test_code_in_a_file_only_this_page_includes(self):
        self.write("pages/lib/mine.nx", "on b0.down:\n  sys0 = 2\n")
        self.write("pages/page0.nx", 'include "lib/mine.nx"\n\non title.down:\n  sys0 = 5\n')
        self.notes(["b0"], self.copy("title"), "code")
        self.assertEqual(self.text("pages/lib/mine.nx"), "on b0.down:\n  sys0 = 5\n")
        self.assertEqual(self.text("pages/page0.nx"),
                         'include "lib/mine.nx"\n\non title.down:\n  sys0 = 5\n')

    def test_code_in_a_file_other_pages_include_is_refused(self):
        self.write("pages/lib/shared.nx", "on b0.down:\n  sys0 = 2\n")
        self.write("pages/second.nx", 'include "lib/shared.nx"\n')
        self.write("pages/page0.nx", 'include "lib/shared.nx"\n\non title.down:\n  sys0 = 5\n')
        with self.assertRaisesRegex(NxwrightError, "the code of b0 is in pages/lib/shared.nx, "
                                                   "which other pages include too"):
            self.notes(["b0"], self.copy("title"), "code")

    def test_the_pages_own_code_file_made_when_it_has_none(self):
        copied = self.copy("title")
        (self.root / "pages" / "page0.nx").unlink()
        found = self.paste_parts(["b0"], copied, "code")
        self.assertEqual(found["created"], ["pages/page0.nx"])
        self.assertEqual(self.text("pages/page0.nx"), '// Says hello\non b0.down:\n  b0.txt = "hello"\n')

    def test_an_event_the_type_lacks(self):
        variable = self.add("variable")
        self.assertEqual(self.notes([variable], self.copy("title"), "code"),
                         ["Code not pasted onto va0, because a variable has no such events: "
                          "down"])
        self.assertNotIn("va0", self.text("pages/page0.nx"))

    def test_a_table_typed_without_its_size(self):
        # A part the copied component cannot give changes nothing.
        typed = '[[component]]\nname = "t9"\ntype = "text"\nx = 5\ny = 6\n'
        self.notes(["b0"], {"text": typed}, "size", "position")
        self.assertEqual([self.table_of("b0")[key] for key in "xywh"], [5, 6, 100, 50])

    def test_a_type_the_folders_defaults_lack(self):
        defaults = tomllib.loads(self.text("defaults.toml"))
        del defaults["button"]
        self.write("defaults.toml", tomli_w.dumps(defaults))
        with self.assertRaisesRegex(NxwrightError, "defaults.toml has no type button"):
            self.notes(["b0"], self.copy("title"), "size")

    def test_the_clipboard_holds_one_component(self):
        with self.assertRaisesRegex(NxwrightError, "Copy just one component first"):
            self.notes(["b0"], self.copy("title", "b1"), "size")

    def test_the_page_file_checked_and_the_code_not(self):
        typed = '[[component]]\nname = "t9"\ntype = "text"\nx = 0\ny = 0\nw = 1\nh = 1\n'
        with self.assertRaisesRegex(NxwrightError, "the page would not build after pasting parts"):
            self.notes(["b0"], {"text": typed}, "size")
        # Code is pasted as Paste pastes it, even code that would not build.
        self.notes(["b0"], {"text": typed, "code": ["on t9.down:\n  nothing.txt = 1\n"]}, "code")
        self.assertIn("on b0.down:\n  nothing.txt = 1\n", self.text("pages/page0.nx"))


class UnreadCodeTest(ComponentsTestCase):
    """A command that copies, removes, or pastes over a component's code
    refuses while a .nx file of its page cannot be read, as the build
    refuses the folder: the file's code would be left out."""

    def setUp(self):
        super().setUp()
        self.write("pages/page0.nx", 'include "lib/shared.nx"\n\non title.down:\n  sys0 = 1\n')
        self.write("pages/lib/shared.nx", "// Shared\n")
        self.copied = copy_components(self.index(), self.read(), "page0", ["title"])

    def assert_refused(self, words: str):
        commands = {
            "delete": lambda: delete_components(self.index(), self.read(), "page0", ["title"]),
            "clear": lambda: clear_events(self.index(), self.read(), "page0", ["title"]),
            "copy": lambda: copy_components(self.index(), self.read(), "page0", ["title"]),
            "paste over": lambda: paste_parts(self.index(), self.read(), self.exists, "page0",
                                              ["title"], self.copied["text"],
                                              self.copied["code"], ["code"])}
        for command, run in commands.items():
            with self.subTest(command=command):
                with self.assertRaises(NxwrightError) as raised:
                    run()
                self.assertEqual(str(raised.exception), words)

    def test_an_included_file_that_is_missing(self):
        (self.root / "pages" / "lib" / "shared.nx").unlink()
        self.assert_refused("pages/lib/shared.nx is missing")

    def test_an_included_file_that_is_not_utf8(self):
        # Saved as Windows-1252, with an "é" in a comment.
        (self.root / "pages" / "lib" / "shared.nx").write_bytes("// caf\xe9\n".encode("cp1252"))
        self.assert_refused("pages/lib/shared.nx is not UTF-8 text")

    def test_a_page_without_code_of_its_own(self):
        (self.root / "pages" / "page0.nx").unlink()
        copied = copy_components(self.index(), self.read(), "page0", ["title"])
        self.assertEqual(copied["code"], [])


class ArrangeTest(ComponentsTestCase):
    """page0 holds the text "title", then the buttons b0, b1, and b2."""

    def setUp(self):
        super().setUp()
        for x in (100, 200, 300):
            self.add("button", x, 50)

    def names(self) -> list:
        return [table["name"] for table in self.tables()]

    def place(self, places: dict):
        edits = place_components(self.index(), self.read(), "page0", places)
        self.write("pages/page0.page.toml", applied(self.text("pages/page0.page.toml"), edits))

    def reorder(self, names: list, direction: str):
        edits = reorder_components(self.index(), self.read(), "page0", names, direction)
        self.write("pages/page0.page.toml", applied(self.text("pages/page0.page.toml"), edits))

    def test_several_placed_at_once(self):
        self.place({"b0": {"x": 10, "y": 20, "w": 30, "h": 40}, "b2": {"x": 5, "y": 6, "w": 7,
                                                                      "h": 8}})
        places = {table["name"]: [table[key] for key in "xywh"] for table in self.tables()}
        self.assertEqual((places["b0"], places["b1"], places["b2"]),
                         ([10, 20, 30, 40], [200, 50, 100, 50], [5, 6, 7, 8]))

    def test_a_size_under_two_pixels(self):
        # The Editor sets a side under 2 pixels back to its type's default
        # as it opens the project, which the build refuses.
        with self.assertRaisesRegex(NxwrightError, "b0 would be 1 by 40; the Nextion Editor says "
                                                   "\"Width can not be less than 2\" as it opens "
                                                   "the project, and sets the width back to 100, "
                                                   "its type's default; make it at least 2 by 2"):
            self.place({"b0": {"x": 10, "y": 20, "w": 1, "h": 40}})

    def test_a_component_too_small_in_its_page_file(self):
        # The build refuses a side under 2, which the Nextion Editor sets back
        # to its type's default as it opens the project. Such a component can
        # still be placed, so that it can be mended, as here, though not
        # placed smaller (test_a_size_under_two_pixels).
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml").replace(
            'name = "b0"\ntype = "button"\nx = 100\ny = 50\nw = 100\nh = 50',
            'name = "b0"\ntype = "button"\nx = 100\ny = 50\nw = 100\nh = 1'))
        self.place({"b0": {"x": 15, "y": 20, "w": 100, "h": 2}})
        places = {table["name"]: [table[key] for key in "xywh"] for table in self.tables()}
        self.assertEqual(places["b0"], [15, 20, 100, 2])

    def test_locked_and_unlocked(self):
        edits = lock_components(self.index(), self.read(), "page0", ["b0", "b2"], True)
        self.write("pages/page0.page.toml", applied(self.text("pages/page0.page.toml"), edits))
        self.assertEqual([table.get("lockobj") for table in self.tables()], [None, 1, None, 1])
        # Locking a component locked already leaves it so.
        edits = lock_components(self.index(), self.read(), "page0", ["b2"], True)
        self.write("pages/page0.page.toml", applied(self.text("pages/page0.page.toml"), edits))
        self.assertEqual([table.get("lockobj") for table in self.tables()], [None, 1, None, 1])
        edits = lock_components(self.index(), self.read(), "page0", ["b0"], False)
        self.write("pages/page0.page.toml", applied(self.text("pages/page0.page.toml"), edits))
        # Unlocked is the default, which the table leaves out.
        self.assertEqual([table.get("lockobj") for table in self.tables()], [None, None, None, 1])
        uri = uri_of(self.root / "pages/page0.page.toml")
        reply = self.request("nxwright/lockComponents", names=["title"], locked=True)["result"]
        self.assertEqual(list(reply["changes"]), [uri])

    def group(self, names: list, grouped: bool = True):
        edits = group_components(self.index(), self.read(), "page0", names, grouped)
        self.write("pages/page0.page.toml", applied(self.text("pages/page0.page.toml"), edits))

    def groups(self) -> list:
        return [(table.get("groupid0"), table.get("groupid1")) for table in self.tables()]

    def test_grouped_and_ungrouped(self):
        # A new group takes the smallest groupid0 no component of the page
        # uses, and groupid1 0, the default, which the table leaves out. The
        # Editor took such a pair as a group.
        self.group(["b0", "b2"])
        self.assertEqual(self.groups(), [(None, None), (1, None), (None, None), (1, None)])
        # A member of a group joins the new one, leaving its own.
        self.group(["title", "b2"])
        self.assertEqual(self.groups(), [(2, None), (1, None), (None, None), (2, None)])
        # Ungrouping leaves the other members as they are, as the Editor's
        # Delete Group did; (0, 0) is the default, which the table leaves out.
        self.group(["b2"], False)
        self.assertEqual(self.groups(), [(2, None), (1, None), (None, None), (None, None)])
        uri = uri_of(self.root / "pages/page0.page.toml")
        reply = self.request("nxwright/groupComponents", names=["b1", "b2"], grouped=True)
        self.assertEqual(list(reply["result"]["changes"]), [uri])

    def test_a_groupid0_in_use_with_another_groupid1(self):
        # (1, 5), as the Editor or a hand may have written it, uses 1.
        self.set_group("page0", "b1", 1, 5)
        self.group(["b0", "b2"])
        self.assertEqual(self.groups(), [(None, None), (2, None), (1, 5), (2, None)])

    def test_forward_and_backward_one_place(self):
        self.reorder(["b0"], "forward")
        self.assertEqual(self.names(), ["title", "b1", "b0", "b2"])
        self.reorder(["title", "b1"], "forward")
        self.assertEqual(self.names(), ["b0", "title", "b1", "b2"])
        self.reorder(["title", "b2"], "backward")
        self.assertEqual(self.names(), ["title", "b0", "b2", "b1"])

    def test_to_the_front_and_to_the_back(self):
        # Past every other component, keeping their own order.
        self.reorder(["title", "b1"], "front")
        self.assertEqual(self.names(), ["b0", "b2", "title", "b1"])
        self.reorder(["b1", "b2"], "back")
        self.assertEqual(self.names(), ["b2", "b1", "b0", "title"])
        # Already there, they move nowhere: no edit at all.
        for names, direction in ((["b2", "b1"], "back"), (["title"], "front")):
            self.assertEqual(reorder_components(self.index(), self.read(), "page0", names,
                                                direction), [])

    def test_nothing_moves_when_one_is_at_its_end(self):
        text = self.text("pages/page0.page.toml")
        self.reorder(["b0", "b2"], "forward")
        self.reorder(["title"], "backward")
        self.assertEqual(self.text("pages/page0.page.toml"), text)

    def test_tables_move_with_their_comments(self):
        text = self.text("pages/page0.page.toml")
        self.write("pages/page0.page.toml", text.replace(
            '[[component]]\nname = "b1"', '# The middle one\n[[component]]\nname = "b1"'))
        self.reorder(["b1"], "backward")
        self.assertIn('txt = "x"\n\n# The middle one\n[[component]]\nname = "b1"\ntype = "button"\n'
                      'x = 200\ny = 50\nw = 100\nh = 50\n\n[[component]]\nname = "b0"',
                      self.text("pages/page0.page.toml"))
        self.assertEqual(self.check(["page0"]).errors(), [])


class LineEditsTest(unittest.TestCase):

    def test_each_run_of_lines_that_differ(self):
        text = "a\nb\nc\nd\n"
        edits = line_edits(text, "a\nB\nc\n")
        self.assertEqual(len(edits), 2)
        self.assertEqual(applied(text, edits), "a\nB\nc\n")

    def test_a_text_without_a_final_newline(self):
        for text, new_text in (("a\nb", "a\nb\n\nc\n"), ("a\nb", "a"), ("a", ""), ("", "a\n")):
            with self.subTest(text=text, new_text=new_text):
                self.assertEqual(applied(text, line_edits(text, new_text)), new_text)


class ServerRequestTest(ComponentsTestCase):

    def test_requests(self):
        types = self.request("nxwright/componentTypes")["result"]["types"]
        self.assertIn({"type": "timer", "placed": False}, types)
        reply = self.request("nxwright/addComponent", type="text", point={"x": 4, "y": 6})
        self.assertEqual(reply["result"]["name"], "t0")
        uri = uri_of(self.root / "pages/page0.page.toml")
        self.assertEqual(list(reply["result"]["edit"]["changes"]), [uri])
        self.write("pages/page0.nx", "on page0.load:\n  title.txt = \"a\"\n")
        reply = self.request("nxwright/deleteComponents", names=["title"])["result"]
        self.assertEqual(list(reply["edit"]["changes"]), [uri])
        self.assertEqual(reply["namedElsewhere"], [{"uri": uri_of(self.root / "pages/page0.nx"),
                                                    "line": 1}])
        self.assertIn("error", self.request("nxwright/addComponent", type="label"))

    def test_placing_and_reordering(self):
        uri = uri_of(self.root / "pages/page0.page.toml")
        reply = self.request("nxwright/placeComponents",
                             places={"title": {"x": 1, "y": 2, "w": 3, "h": 4}})["result"]
        self.assertEqual(list(reply["changes"]), [uri])
        self.add("button")
        reply = self.request("nxwright/reorderComponents", names=["b0"],
                             direction="backward")["result"]
        self.assertEqual(list(reply["changes"]), [uri])

    def test_copying_and_pasting(self):
        self.write("pages/page0.nx", "on title.down:\n  sys0 = 2\n")
        copied = self.request("nxwright/copyComponents", names=["title"])["result"]
        self.assertEqual(copied["code"], ["on title.down:\n  sys0 = 2\n"])
        reply = self.request("nxwright/pasteComponents", text=copied["text"],
                             code=copied["code"])["result"]
        self.assertEqual(reply["names"], ["title0"])
        self.assertEqual(sorted(reply["edit"]["changes"]),
                         sorted(uri_of(self.root / path)
                                for path in ("pages/page0.page.toml", "pages/page0.nx")))
        (self.root / "pages" / "page0.nx").unlink()
        reply = self.request("nxwright/pasteComponents", text=copied["text"],
                             code=copied["code"])["result"]
        uri = uri_of(self.root / "pages/page0.nx")
        self.assertEqual(reply["edit"]["documentChanges"][0], {"kind": "create", "uri": uri})
        self.assertEqual([change["textDocument"]["uri"]
                          for change in reply["edit"]["documentChanges"][1:]],
                         [uri_of(self.root / "pages/page0.page.toml"), uri])

    def test_pasting_at_a_place_and_clearing_events(self):
        copied = self.request("nxwright/copyComponents", names=["title"])["result"]
        reply = self.request("nxwright/pasteComponents", text=copied["text"],
                             at={"x": 50, "y": 60})["result"]
        self.assertEqual(reply["names"], ["title0"])
        reply = self.request("nxwright/pasteComponents", text=copied["text"],
                             inPlace=True)["result"]
        self.assertEqual(reply["names"], ["title0"])
        self.write("pages/page0.nx", "on title.down:\n  sys0 = 2\n")
        reply = self.request("nxwright/clearEvents", names=["title"])["result"]
        self.assertEqual(list(reply["changes"]), [uri_of(self.root / "pages/page0.nx")])

    def test_pasting_parts(self):
        self.write("pages/page0.nx", "on title.down:\n  sys0 = 2\n")
        copied = self.request("nxwright/copyComponents", names=["title"])["result"]
        self.add("button")
        self.add("variable")
        reply = self.request("nxwright/pasteParts", names=["b0", "va0"], text=copied["text"],
                             code=copied["code"], parts=["size", "code"])["result"]
        self.assertEqual(sorted(reply["edit"]["changes"]),
                         sorted(uri_of(self.root / path)
                                for path in ("pages/page0.page.toml", "pages/page0.nx")))
        self.assertEqual(reply["notes"],
                         ["va0 has no place on the screen, so no size was pasted onto it",
                          "Code not pasted onto va0, because a variable has no such events: "
                          "down"])
        self.assertIn("error", self.request("nxwright/pasteParts", names=["b0"], text="",
                                            code=[], parts=["size"]))


if __name__ == "__main__":
    unittest.main()
