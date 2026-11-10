"""Numbers that stand for resources (source/resource_numbers.py), placed in a
file's own text; and what the language server makes of them: an inlay hint
with the resource's name, a code action writing the number as the name, and
the request that does so across the folder."""
import contextlib
from unittest import mock

from nxwright.language.nxlang import compile_page
from nxwright.language_server.file_texts import uri_of
from nxwright.source.folder_index import FolderIndex, text_on_disk
from nxwright.source.resource_numbers import (as_name, code_lines, placed_numbers,
                                              placed_numbers_in_steps)
from nxwright.source.source_folder import (FolderSource, folder_reader, read_folder_source,
                                           switch_to_nxlang)
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

    def test_the_numbers_found_in_steps_are_the_same(self):
        # The language server finds a file's numbers one page's compile at a
        # time. Each step yields None, and the generator returns the numbers
        # when it ends.
        self.write_code("p0.pic=1", "pic 0,0,1", "if(p0.pic==1)", "{", "}")
        index = FolderIndex(self.source, text_on_disk)
        folder = read_folder_source(folder_reader(self.source))
        for path in (CODE, PAGE):
            steps, yielded = placed_numbers_in_steps(folder, index, path), []
            while True:
                try:
                    yielded.append(next(steps))
                except StopIteration as done:
                    found = done.value
                    break
            self.assertEqual(found, placed_numbers(folder, index, path))
            self.assertEqual(set(yielded), {None} if yielded else set())
        self.assertTrue(placed_numbers(folder, index, CODE))

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


class CodeLinesTest(PlacedNumbersTestCase):

    def test_a_page_with_several_code_files_is_compiled_once(self):
        switch_to_nxlang(self.source)
        library = self.source / "pages" / "lib"
        library.mkdir()
        (library / "first.nx").write_text("function first():\n  p0.pic = 1\n",
                                          encoding="utf-8", newline="\n")
        (library / "second.nx").write_text("function second():\n  p0.pic = 0\n",
                                           encoding="utf-8", newline="\n")
        (self.source / CODE).write_text('include "lib/first.nx"\ninclude "lib/second.nx"\n\n'
                                        "on page0.down:\n  first()\n  second()\n",
                                        encoding="utf-8", newline="\n")
        index = FolderIndex(self.source, text_on_disk)
        folder = read_folder_source(folder_reader(self.source))
        with mock.patch("nxwright.source.page_source.compile_page",
                        wraps=compile_page) as compiling:
            lines = code_lines(folder, index)
        self.assertEqual(compiling.call_count, 1)
        # Each of the page's three files still gives its lines.
        self.assertEqual(lines[("pages/lib/first.nx", 2)], [("page0", "p0.pic=1")])
        self.assertEqual(lines[("pages/lib/second.nx", 2)], [("page0", "p0.pic=0")])
        self.assertIn((CODE, 5), lines)

    def test_a_page_without_a_code_file_gives_no_lines(self):
        (self.source / CODE).unlink()
        index = FolderIndex(self.source, text_on_disk)
        folder = read_folder_source(folder_reader(self.source))
        self.assertEqual({path for path, _ in code_lines(folder, index)}, {"program.nx"})


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

    def test_the_code_is_compiled_again_only_after_a_change(self):
        compiled = []

        def counting(folder, index, only=None):
            compiled.append(only)
            return code_lines(folder, index, only)

        hints = {"textDocument": {"uri": uri_of(self.source / CODE)},
                 "range": self.whole_file(CODE)}
        actions = {"textDocument": {"uri": uri_of(self.source / CODE)},
                   "range": {"start": {"line": 1, "character": 9},
                             "end": {"line": 1, "character": 9}},
                   "context": {"diagnostics": []}}
        with mock.patch("nxwright.source.resource_numbers.code_lines", counting):
            self.ask("textDocument/inlayHint", hints)
            self.ask("textDocument/inlayHint", hints)
            self.ask("textDocument/codeAction", actions)
            self.assertEqual(compiled, [CODE])
            # The server sees a change on disk even if the editor does not report it.
            self.write_code("p0.pic=0")
            self.assertEqual([hint["label"] for hint in self.ask("textDocument/inlayHint", hints)],
                             ["a"])
            self.assertEqual(compiled, [CODE, CODE])
            # The server also sees a change to another file the numbers came from,
            # here a picture's name in app.toml.
            app = self.source / "app.toml"
            app.write_text(app.read_text(encoding="utf-8").replace('"a"', '"logo"'),
                           encoding="utf-8", newline="\n")
            self.assertEqual([hint["label"] for hint in self.ask("textDocument/inlayHint", hints)],
                             ["logo"])

    def test_a_folder_that_cannot_be_read_is_read_again_once_it_can(self):
        hints = {"textDocument": {"uri": uri_of(self.source / CODE)},
                 "range": self.whole_file(CODE)}
        page = self.source / PAGE
        text = page.read_text(encoding="utf-8")
        page.unlink()
        self.assertEqual(self.ask("textDocument/inlayHint", hints), [])
        self.assertEqual(self.ask("textDocument/inlayHint", hints), [])
        page.write_text(text, encoding="utf-8", newline="\n")
        self.assertEqual([hint["label"] for hint in self.ask("textDocument/inlayHint", hints)],
                         ["b", "b"])

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


class WhileAChangeWaitsTest(PlacedNumbersTestCase):
    """While a change waits to be checked, the language server answers inlay
    hint and code action requests from the numbers it has, and finds the
    numbers again once the pages are checked."""

    # page0.nx: its heading, then two lines whose number stands for picture b.
    CODE_LINES = ("p0.pic=1", "if(p0.pic==1)", "{", "}")

    def setUp(self):
        super().setUp()
        self.write_code(*self.CODE_LINES)
        self.text = (self.source / CODE).read_text(encoding="utf-8")
        self.start_server({})
        self.version = 0

    def start_server(self, capabilities: dict):
        self.connection = ServerConnection()
        self.server, self.sent = self.connection.server, self.connection.sent
        self.connection.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                "params": {"processId": None, "capabilities": capabilities}})

    def ask(self, method: str, params: dict):
        self.connection.handle({"jsonrpc": "2.0", "id": 7, "method": method, "params": params})
        reply = self.sent[-1]
        self.assertNotIn("error", reply)
        return reply["result"]

    def hints(self) -> list:
        """Returns (line, label) of each inlay hint of page0.nx."""
        hints = self.ask("textDocument/inlayHint", {
            "textDocument": {"uri": uri_of(self.source / CODE)},
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 99, "character": 0}}})
        return [(hint["position"]["line"], hint["label"]) for hint in hints]

    def change(self, text: str):
        """Sends the server `text` as the editor's unsaved text of page0.nx,
        which marks the file as changed."""
        self.version += 1
        if self.version == 1:
            params = {"textDocument": {"uri": uri_of(self.source / CODE), "languageId": "nx",
                                       "version": 1, "text": text}}
            method = "textDocument/didOpen"
        else:
            params = {"textDocument": {"uri": uri_of(self.source / CODE),
                                       "version": self.version},
                      "contentChanges": [{"text": text}]}
            method = "textDocument/didChange"
        self.connection.handle({"jsonrpc": "2.0", "method": method, "params": params})

    @contextlib.contextmanager
    def compiles_counted(self):
        """Yields a list that receives the name of each page compiled to find
        numbers, when it is compiled."""
        compiled = []
        editor_code_of_files = FolderSource.editor_code_of_files

        def counting(folder, page_name, paths):
            compiled.append(page_name)
            return editor_code_of_files(folder, page_name, paths)

        with mock.patch.object(FolderSource, "editor_code_of_files", counting):
            yield compiled

    def refreshes(self) -> int:
        return sum(1 for message in self.sent
                   if message.get("method") == "workspace/inlayHint/refresh")

    def test_a_request_gets_the_kept_hints_of_the_lines_that_did_not_change(self):
        self.assertEqual(self.hints(), [(1, "b"), (2, "b")])
        # A line added above them moves both lines down.
        self.change("// a comment\n" + self.text)
        with self.compiles_counted() as compiled:
            self.assertEqual(self.hints(), [(2, "b"), (3, "b")])
        self.assertEqual(compiled, [])

    def test_a_number_on_a_changed_line_waits_for_the_checks(self):
        self.assertEqual(self.hints(), [(1, "b"), (2, "b")])
        self.change(self.text.replace("p0.pic=1\n", "p0.pic=0\n"))
        with self.compiles_counted() as compiled:
            self.assertEqual(self.hints(), [(2, "b")])
        self.assertEqual(compiled, [])
        self.server.run_checks()
        self.assertFalse(self.server.checks_waiting())
        with self.compiles_counted() as compiled:
            self.assertEqual(self.hints(), [(1, "a"), (2, "b")])
        self.assertEqual(compiled, [])

    def test_a_file_without_kept_numbers_gets_its_hints_after_the_checks(self):
        self.change(self.text)
        with self.compiles_counted() as compiled:
            self.assertEqual(self.hints(), [])
        self.assertEqual(compiled, [])
        self.server.run_checks()
        self.assertEqual(self.hints(), [(1, "b"), (2, "b")])

    def test_the_editor_is_told_to_ask_for_its_hints_again(self):
        self.start_server({"workspace": {"inlayHint": {"refreshSupport": True}}})
        self.change(self.text.replace("p0.pic=1\n", "p0.pic=0\n"))
        self.hints()
        self.assertEqual(self.refreshes(), 0)
        self.server.run_checks()
        self.assertEqual(self.refreshes(), 1)

    def test_an_editor_without_refresh_support_is_not_told(self):
        self.change(self.text.replace("p0.pic=1\n", "p0.pic=0\n"))
        self.hints()
        self.server.run_checks()
        self.assertEqual(self.refreshes(), 0)
        self.assertEqual(self.hints(), [(1, "a"), (2, "b")])

    def test_a_code_action_request_compiles_nothing(self):
        self.hints()
        self.change("// a comment\n" + self.text)
        with self.compiles_counted() as compiled:
            actions = self.ask("textDocument/codeAction", {
                "textDocument": {"uri": uri_of(self.source / CODE)},
                "range": {"start": {"line": 2, "character": 9},
                          "end": {"line": 2, "character": 9}},
                "context": {"diagnostics": []}})
        self.assertEqual(compiled, [])
        self.assertIn("Write 1 as @pic(b)", [action["title"] for action in actions])

    def test_a_change_while_the_numbers_are_found_again_starts_that_work_again(self):
        self.hints()
        self.change(self.text.replace("p0.pic=1\n", "p0.pic=0\n"))
        self.hints()
        # The check's one page, then the first step of finding the numbers again.
        self.assertTrue(self.server.run_check_step())
        self.assertTrue(self.server.run_check_step())
        self.change(self.text.replace("if(p0.pic==1)\n", "if(p0.pic==0)\n"))
        self.hints()
        self.server.run_checks()
        self.assertFalse(self.server.checks_waiting())
        self.assertEqual(self.hints(), [(1, "b"), (2, "a")])


if __name__ == "__main__":
    import unittest
    unittest.main()
