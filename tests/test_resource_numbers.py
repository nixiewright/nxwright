"""Numbers that stand for resources (source/resource_numbers.py), placed in a
file's own text; and what the language server makes of them: an inlay hint
with the resource's name, a code action writing the number as the name, and
the request that does so across the folder."""
from nxwright.language_server.file_texts import uri_of
from nxwright.source.folder_index import FolderIndex, text_on_disk
from nxwright.source.resource_numbers import as_name, placed_numbers
from nxwright.source.source_folder import folder_reader, read_folder_source, switch_to_nxlang
from tests.language_server_connection import INITIALIZE_PARAMS, ServerConnection
from tests.test_remove_resource import RemoveResourceTestCase

CODE = "pages/page0.nx"
PAGE = "pages/page0.page.toml"


class PlacedNumbersTestCase(RemoveResourceTestCase):
    """RemoveResourceTestCase's folder, pictures a and b, with the picture
    component p0 on page0."""

    def setUp(self):
        super().setUp()
        self.add("p0", "picture", pic="a")

    def placed(self, path: str) -> list:
        """Returns (line, the text placed, kind, ID, the name it may be
        written as or None) of each number placed in `path`."""
        index = FolderIndex(self.source, text_on_disk)
        folder = read_folder_source(folder_reader(self.source))
        found = []
        for number in placed_numbers(folder, index, path):
            line = index.lines(path)[number.place.line]
            found.append((number.place.line, line[number.place.start:number.place.end],
                          number.kind, number.id, as_name(folder, index, number)))
        return found


class PlacedNumbersTest(PlacedNumbersTestCase):

    def test_code_in_strict_syntax(self):
        self.add("t0", "text", txt_maxl=20)
        self.write_code("p0.pic=1", "pic 0,0,1", "pic 1,1,1", "if(p0.pic==1)", "{", "}",
                        't0.txt="p0.pic=1"', "p0.pic=0x01")
        self.assertEqual(self.placed(CODE), [
            (1, "1", "pic", 1, "@pic(b)"),
            (2, "1", "pic", 1, "@pic(b)"),
            # Compared, the number is placed but not written as a name.
            (4, "1", "pic", 1, None),
            # Written another way than the build writes it.
            (8, "0x01", "pic", 1, None)])

    def test_code_in_nxlang(self):
        switch_to_nxlang(self.source)
        (self.source / CODE).write_text("const LOGO = 1\n\non page0.down:\n  p0.pic = 1\n"
                                        "  p0.pic = LOGO\n", encoding="utf-8", newline="\n")
        self.assertEqual(self.placed(CODE), [(3, "1", "pic", 1, "@pic(b)")])

    def test_a_page_file(self):
        self.add("p1", "picture", pic=1)
        [(line, text, kind, number, name)] = self.placed(PAGE)
        self.assertEqual((text, kind, number, name), ("1", "pic", 1, '"b"'))
        self.assertTrue((self.source / PAGE).read_text().split("\n")[line].startswith("pic = "))

    def test_program_nx_and_a_font(self):
        (self.source / "program.nx").write_text(
            (self.source / "program.nx").read_text(encoding="utf-8") + "page0.p0.pic=1\n",
            encoding="utf-8", newline="\n")
        placed = self.placed("program.nx")
        self.assertEqual([entry[1:] for entry in placed], [("1", "pic", 1, "@pic(b)")])
        self.add("t0", "text", txt_maxl=20)
        self.write_code("t0.font=1")
        self.assertEqual(self.placed(CODE), [(1, "1", "font", 1, "@font(NotoSans16)")])

    def test_an_id_past_the_last_names_nothing(self):
        self.write_code("p0.pic=7")
        self.assertEqual(self.placed(CODE), [(1, "7", "pic", 7, None)])


class ServerTest(PlacedNumbersTestCase):
    """The language server's inlay hints, code actions, and request."""

    def setUp(self):
        super().setUp()
        self.connection = ServerConnection()
        self.connection.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                "params": INITIALIZE_PARAMS})
        self.write_code("p0.pic=1", "if(p0.pic==1)", "{", "}")

    def ask(self, method: str, params: dict):
        self.connection.handle({"jsonrpc": "2.0", "id": 7, "method": method, "params": params})
        reply = self.connection.sent[-1]
        self.assertNotIn("error", reply)
        return reply["result"]

    def whole_file(self, path: str) -> dict:
        return {"start": {"line": 0, "character": 0}, "end": {"line": 99, "character": 0}}

    def test_inlay_hints(self):
        hints = self.ask("textDocument/inlayHint", {
            "textDocument": {"uri": uri_of(self.source / CODE)}, "range": self.whole_file(CODE)})
        self.assertEqual([(hint["position"], hint["label"]) for hint in hints],
                         [({"line": 1, "character": 10}, "b"), ({"line": 2, "character": 14}, "b")])

    def test_a_code_action_on_a_number(self):
        actions = self.ask("textDocument/codeAction", {
            "textDocument": {"uri": uri_of(self.source / CODE)},
            "range": {"start": {"line": 1, "character": 9}, "end": {"line": 1, "character": 9}},
            "context": {"diagnostics": []}})
        titles = [action["title"] for action in actions]
        self.assertIn("Write 1 as @pic(b)", titles)
        [edit] = next(action for action in actions
                      if action["title"] == "Write 1 as @pic(b)")["edit"]["changes"].values()
        self.assertEqual(edit[0]["newText"], "@pic(b)")
        # The source action writes every such number of the file, here one.
        [whole] = [action for action in actions if action["kind"] == "source"]
        [edits] = whole["edit"]["changes"].values()
        self.assertEqual([edit["newText"] for edit in edits], ["@pic(b)"])
        # A client asking for quick fixes alone gets neither.
        only_fixes = self.ask("textDocument/codeAction", {
            "textDocument": {"uri": uri_of(self.source / CODE)},
            "range": {"start": {"line": 1, "character": 9}, "end": {"line": 1, "character": 9}},
            "context": {"diagnostics": [], "only": ["quickfix"]}})
        self.assertEqual(only_fixes, [])

    def test_numbers_as_names_across_the_folder(self):
        self.add("p1", "picture", pic=1)
        result = self.ask("nxwright/resourceNumbersAsNames", {
            "folder": str(self.source), "kind": "picture", "ids": [1]})
        changes = result["changes"]
        self.assertEqual(sorted(changes), sorted([uri_of(self.source / CODE),
                                                  uri_of(self.source / PAGE)]))
        # The compared number is placed, but no fix writes it as a name.
        self.assertEqual([edit["newText"] for edit in changes[uri_of(self.source / CODE)]],
                         ["@pic(b)"])
        self.assertEqual([edit["newText"] for edit in changes[uri_of(self.source / PAGE)]],
                         ['"b"'])

    def test_page_numbers_as_names(self):
        # Only the number given to `page` is written as the page's name. The one
        # given to `dp` stays a number.
        self.write_code("page 0", "dp=0")
        result = self.ask("nxwright/resourceNumbersAsNames", {
            "folder": str(self.source), "kind": "page", "ids": [0]})
        edits = result["changes"][uri_of(self.source / CODE)]
        self.assertEqual([edit["newText"] for edit in edits], ["page0"])


if __name__ == "__main__":
    import unittest
    unittest.main()
