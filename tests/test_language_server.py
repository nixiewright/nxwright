"""The language server: its messages, its index of a source folder, and where
it finds a name's definition."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

from lsprotocol import types

from nxwright import MissingFileError, NxwrightError
from nxwright.language_server.attributes import attribute_markdown
from nxwright.language_server.completion import Signature, completions, signature
from nxwright.source.definitions import definitions
from nxwright.language_server.file_texts import FileTexts, uri_of
from nxwright.source.folder_index import FolderIndex, Place, file_start
from nxwright.language_server.hovers import hover
from nxwright.source.references import references
from nxwright.language_server.symbols import (CLASS, CONSTANT, EVENT, FUNCTION, file_symbols,
                                              folder_symbols)
from tests.test_folder_check import FolderTestCase as CheckFolderTestCase
from nxwright.debug_adapter.framing import read_message, write_message
from nxwright.language_server.server import serve
from tests.language_server_connection import INITIALIZE_PARAMS, ServerConnection, document_item
from tests.test_zi_font import gb2312_font, utf8_fixture

# A small source folder in nxlang. Two pages include one library, and each
# page has a component named "title", which the library's function names.
FOLDER = {
    "app.toml": """format = 1
language = "nxlang"
screen = "NX8048P050"
rotation = 0
encoding = "iso-8859-1"
pages = ["home", "settings"]
pictures = [
  "icons/back",
  "logo",
]
fonts = ["Sans16"]
""",
    "pages/home.page.toml": """[page]
name = "home"
type = "page"

[[component]]
name = "title"
type = "text"

[[component]]
name = "save"
type = "button"
pic = "icons/back"
font = "Sans16"
""",
    "pages/settings.page.toml": """[page]
name = "settings"
type = "page"

[[component]]
name = "t0"
type = "text"

[[component]]
name = "title"
type = "text"
""",
    "program.nx": """include "units.nx"
int counter=0, total=1
const LIMIT = 40
page 0
""",
    "units.nx": """const UNIT = " mm"
""",
    "pages/lib/shared.nx": """const STEP = 5

// Shows a message in the page's title.
function showTitle(message: text):
  title.txt = message

function join(first: text, second: text) -> text:
  return first + second
""",
    "pages/home.nx": """include "lib/shared.nx"
const SPEED = 3

// Saves.
on save.up:
  var sum = counter + SPEED + STEP + LIMIT
  showTitle("x" + UNIT)
  settings.t0.txt = "a"
  vis title,1
  b[3].txt = "x"
  sys0 = sum
  page settings
  title.pic = @pic(logo)
  title.font = @font(Sans16)

function twice(value: number) -> number:
  return value * 2
""",
    "pages/settings.nx": """include "lib/shared.nx"

on settings.load:
  showTitle("y")
""",
}


def write_folder(root: Path, files: dict):
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text, encoding="utf-8", newline="\n")


class FolderTestCase(unittest.TestCase):
    """FOLDER, written in a temporary folder."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.root = Path(self._folder.name)
        write_folder(self.root, FOLDER)
        self.documents = FileTexts()

    def tearDown(self):
        self._folder.cleanup()

    def index(self) -> FolderIndex:
        return FolderIndex(self.root, self.documents.read)

    def find(self, path: str, needle: str, inside: str = None) -> Place:
        """Returns the place of the first `needle` in the file `path`, or of
        `inside` within that first `needle`."""
        text = (self.root / path).read_text(encoding="utf-8")
        for number, line in enumerate(text.split("\n")):
            column = line.find(needle)
            if column >= 0:
                if inside is not None:
                    column += needle.index(inside)
                    needle = inside
                return Place(path, number, column, column + len(needle))
        raise AssertionError("%r is not in %s" % (needle, path))

    def table(self, page: str, name: str) -> Place:
        """Returns the place of the name in a page file's `name = "..."` line."""
        return self.find("pages/%s.page.toml" % page, 'name = "%s"' % name, name)

    def definitions_at(self, path: str, needle: str, inside: str = None) -> list:
        place = self.find(path, needle, inside)
        return definitions(self.index(), path, place.line, place.start)


class ServerTestCase(FolderTestCase):
    """The language server on FOLDER, through a ServerConnection, with what it
    sends kept in `sent`."""

    def setUp(self):
        super().setUp()
        self.connection = ServerConnection()
        self.sent = self.connection.sent

    def initialize(self) -> dict:
        return self.request("initialize", INITIALIZE_PARAMS)

    def request(self, method: str, params: dict = None) -> dict:
        self.connection.handle({"jsonrpc": "2.0", "id": len(self.sent) + 1, "method": method,
                                "params": params or {}})
        return self.sent[-1]

    def notify(self, method: str, params: dict):
        self.connection.handle({"jsonrpc": "2.0", "method": method, "params": params})

    def definition(self, path: str, line: int, character: int) -> dict:
        return self.request("textDocument/definition", {
            "textDocument": {"uri": uri_of(self.root / path)},
            "position": {"line": line, "character": character}})


class ServerTest(ServerTestCase):

    def test_initialize_says_what_the_server_does(self):
        capabilities = self.initialize()["result"]["capabilities"]
        self.assertTrue(capabilities["definitionProvider"])
        self.assertEqual(capabilities["completionProvider"]["triggerCharacters"], [".", '"'])
        # The editor sends the changes alone, which pygls applies to its text.
        self.assertEqual((capabilities["textDocumentSync"]["openClose"],
                          capabilities["textDocumentSync"]["change"]),
                         (True, types.TextDocumentSyncKind.Incremental))

    def test_an_unknown_method(self):
        self.initialize()
        self.assertEqual(self.request("nxwright/nothing")["error"]["code"],
                         types.ErrorCodes.MethodNotFound)

    def test_a_request_before_initialize(self):
        reply = self.definition("pages/home.nx", 0, 0)
        self.assertEqual(reply["error"]["code"], types.ErrorCodes.ServerNotInitialized)

    def test_a_malformed_message_does_not_end_the_server(self):
        # pygls answers no message it cannot read, and tells the editor so.
        # A request of nxwright's own it can read, but not answer, gets the
        # protocol's "internal error".
        self.initialize()
        with contextlib.redirect_stderr(io.StringIO()):
            self.notify("textDocument/didOpen", {"text": "no document"})
            self.request("textDocument/definition", {"position": {}})
            self.assertEqual([message["method"] for message in self.sent[-2:]],
                             ["window/showMessage"] * 2)
            reply = self.request("nxwright/pageDrawing", {})
        self.assertEqual(reply["error"]["code"], types.ErrorCodes.InternalError)
        place = self.find("pages/home.nx", "LIMIT")
        reply = self.definition("pages/home.nx", place.line, place.start)
        self.assertEqual(reply["result"][0]["uri"], uri_of(self.root / "program.nx"))

    def test_shutdown_then_exit(self):
        self.initialize()
        self.assertIsNone(self.request("shutdown")["result"])
        with self.assertRaises(SystemExit) as exited:
            self.notify("exit", {})
        self.assertEqual(exited.exception.code, 0)

    def test_a_definition_in_another_file(self):
        self.initialize()
        place = self.find("pages/home.nx", "showTitle")
        reply = self.definition("pages/home.nx", place.line, place.start)
        target = self.find("pages/lib/shared.nx", "showTitle")
        self.assertEqual(reply["result"], [{
            "uri": uri_of(self.root / "pages/lib/shared.nx"),
            "range": {"start": {"line": target.line, "character": target.start},
                      "end": {"line": target.line, "character": target.end}}}])

    def test_outside_a_source_folder(self):
        self.initialize()
        (self.root / "app.toml").unlink()
        self.assertIsNone(self.definition("pages/home.nx", 5, 10)["result"])

    def test_the_editor_text_of_an_open_file(self):
        # The unsaved text has a line more than the file on disk, and its own constant.
        self.initialize()
        uri = uri_of(self.root / "pages/home.nx")
        self.notify("textDocument/didOpen", {"textDocument": document_item(uri, "")})
        text = "const PACE = 1\n" + FOLDER["pages/home.nx"].replace("+ SPEED", "+ PACE")
        self.notify("textDocument/didChange", {"textDocument": {"uri": uri, "version": 2},
                                               "contentChanges": [{"text": text}]})
        number = text.split("\n").index("  var sum = counter + PACE + STEP + LIMIT")
        reply = self.definition("pages/home.nx", number, len("  var sum = counter + "))
        self.assertEqual(reply["result"][0]["range"]["start"], {"line": 0, "character": 6})
        self.notify("textDocument/didClose", {"textDocument": {"uri": uri}})
        reply = self.definition("pages/home.nx", number, len("  var sum = counter + "))
        self.assertEqual(reply["result"], [])

    def test_a_change_of_part_of_an_open_file(self):
        # The editor sends its changes alone, ranges of the text with
        # CR LF line ends here, which pygls applies; the server reads the
        # text so changed, with LF line ends.
        self.initialize()
        uri = uri_of(self.root / "pages/home.nx")
        original = FOLDER["pages/home.nx"]
        self.notify("textDocument/didOpen", {
            "textDocument": document_item(uri, original.replace("\n", "\r\n"))})
        number = original.split("\n").index("  var sum = counter + SPEED + STEP + LIMIT")
        speed = len("  var sum = counter + ")
        self.notify("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": 2},
            "contentChanges": [
                {"range": {"start": {"line": number, "character": speed},
                           "end": {"line": number, "character": speed + len("SPEED")}},
                 "text": "PACE"},
                {"range": {"start": {"line": 0, "character": 0},
                           "end": {"line": 0, "character": 0}},
                 "text": "const PACE = 1\r\n"}]})
        reply = self.definition("pages/home.nx", number + 1, speed)
        self.assertEqual(reply["result"][0]["range"]["start"], {"line": 0, "character": 6})

    def test_columns_count_utf16_units(self):
        # 😀 is one character in Python and two UTF-16 units. So four of them
        # put UNIT four UTF-16 units further than its Python column, where
        # Python has the ")" after it.
        self.initialize()
        text = FOLDER["pages/home.nx"].replace('"x" + UNIT', '"%s" + UNIT' % ("\U0001F600" * 4))
        write_folder(self.root, {"pages/home.nx": text})
        number = self.find("pages/home.nx", "UNIT").line
        column = text.split("\n")[number].index("UNIT")
        reply = self.definition("pages/home.nx", number, column + 4)
        self.assertEqual(reply["result"][0]["uri"], uri_of(self.root / "units.nx"))

    def test_serve_ends_with_exit(self):
        stream = io.BytesIO()
        for message in [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": INITIALIZE_PARAMS},
                        {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
                        {"jsonrpc": "2.0", "method": "exit"}]:
            write_message(stream, message)
        stream.seek(0)
        output = _KeptBytes()
        self.assertEqual(serve(stream, output), 0)
        output.seek(0)
        self.assertEqual([read_message(output)["id"] for _ in range(2)], [1, 2])

    def test_serve_without_shutdown(self):
        stream = io.BytesIO()
        write_message(stream, {"jsonrpc": "2.0", "method": "exit"})
        stream.seek(0)
        self.assertEqual(serve(stream, io.BytesIO()), 1)
        self.assertEqual(serve(io.BytesIO(), io.BytesIO()), 1)


class _KeptBytes(io.BytesIO):
    """Standard output for `serve`, still readable after pygls closes it, as
    it does on exit."""

    def close(self):
        pass


class FileTextsTest(FolderTestCase):
    """A source folder's files as the language server reads them
    (file_texts.py)."""

    def test_a_file_not_in_utf8_is_told_from_a_missing_one(self):
        # Saved as Windows-1252, with an "é" in a comment.
        (self.root / "pages" / "latin.nx").write_bytes("// caf\xe9\n".encode("cp1252"))
        read = self.documents.folder_reader(self.root)
        with self.assertRaises(NxwrightError) as raised:
            read("pages/latin.nx")
        self.assertNotIsInstance(raised.exception, MissingFileError)
        self.assertEqual(str(raised.exception), "pages/latin.nx is not UTF-8 text")
        with self.assertRaises(MissingFileError) as raised:
            read("pages/absent.nx")
        self.assertEqual(str(raised.exception), "pages/absent.nx is missing")

    def test_a_byte_order_mark_is_not_part_of_the_text(self):
        # As VS Code's "UTF-8 with BOM" saves a file.
        path = self.root / "pages" / "marked.nx"
        path.write_bytes(b"\xef\xbb\xbf// note\n")
        self.assertEqual(self.documents.folder_reader(self.root)("pages/marked.nx"), "// note\n")
        self.assertFalse(self.documents.unsaved(path))


class FolderIndexTest(FolderTestCase):

    def test_app_lists(self):
        index = self.index()
        self.assertEqual(index.pages, ["home", "settings"])
        self.assertEqual(index.pictures, ["icons/back", "logo"])
        self.assertEqual(index.fonts, ["Sans16"])
        self.assertEqual(index.app_entries[("pictures", "logo")],
                         self.find("app.toml", '"logo"', "logo"))

    def test_page_objects(self):
        names = [page_object.name for page_object in self.index().page_objects["settings"]]
        self.assertEqual(names, ["settings", "t0", "title"])

    def test_each_page_with_the_files_it_includes(self):
        index = self.index()
        self.assertEqual(index.page_files["home"], ["pages/home.nx", "pages/lib/shared.nx"])
        self.assertEqual(index.program_files, ["program.nx", "units.nx"])
        self.assertEqual(index.pages_using("pages/lib/shared.nx"), ["home", "settings"])

    def test_what_a_file_defines(self):
        index = self.index()
        home = index.nx_file("pages/home.nx")
        self.assertEqual(list(home.constants), ["SPEED"])
        self.assertEqual([(block.name, block.is_function) for block in home.blocks],
                         [("save", False), ("twice", True)])
        self.assertEqual(list(home.blocks[0].locals), ["sum"])
        self.assertEqual(list(home.blocks[1].parameters), ["value"])
        self.assertEqual(list(index.nx_file("program.nx").globals), ["counter", "total"])

    def test_a_folder_in_the_editors_language(self):
        write_folder(self.root, {
            "app.toml": FOLDER["app.toml"].replace("nxlang", "nextion"),
            "pages/home.nx": "on save.up:\n  if(sys0==1)\n  {\n    title.txt=\"a\"\n  }\n",
            "pages/settings.nx": ""})
        index = self.index()
        self.assertEqual([block.name for block in index.nx_file("pages/home.nx").blocks],
                         ["save"])
        self.assertEqual(definitions(index, "pages/home.nx", 3, 4),
                         [self.table("home", "title")])

    def test_a_half_typed_file_keeps_its_other_names(self):
        broken = FOLDER["pages/home.nx"].replace('settings.t0.txt = "a"', 'settings.t0.txt = "a')
        broken = broken.replace("const SPEED = 3", "const SPEED = 3\ninclude \"../../x.nx\"\n???")
        write_folder(self.root, {"pages/home.nx": broken})
        index = self.index()
        home = index.nx_file("pages/home.nx")
        self.assertEqual(list(home.constants), ["SPEED"])
        self.assertEqual(home.includes[1:], [])
        self.assertEqual([block.name for block in home.blocks], ["save", "twice"])
        line = broken.split("\n").index('  vis title,1')
        self.assertEqual(definitions(index, "pages/home.nx", line, 6),
                         [self.table("home", "title")])


class DefinitionTest(FolderTestCase):

    def test_a_component_of_the_page(self):
        self.assertEqual(self.definitions_at("pages/home.nx", "title.pic"),
                         [self.table("home", "title")])

    def test_a_component_of_another_page(self):
        self.assertEqual(self.definitions_at("pages/home.nx", "settings.t0", "t0"),
                         [self.table("settings", "t0")])

    def test_another_page(self):
        self.assertEqual(self.definitions_at("pages/home.nx", "settings.t0"),
                         [self.table("settings", "settings")])

    def test_the_attribute_has_none(self):
        self.assertEqual(self.definitions_at("pages/home.nx", "settings.t0.txt", "txt"), [])

    def test_a_component_in_a_command(self):
        self.assertEqual(self.definitions_at("pages/home.nx", "vis title", "title"),
                         [self.table("home", "title")])

    def test_an_event_heading(self):
        self.assertEqual(self.definitions_at("pages/home.nx", "on save.up", "save"),
                         [self.table("home", "save")])
        self.assertEqual(self.definitions_at("pages/settings.nx", "on settings.load", "settings"),
                         [self.table("settings", "settings")])
        self.assertEqual(self.definitions_at("pages/home.nx", "on save.up", "up"), [])

    def test_a_function(self):
        self.assertEqual(self.definitions_at("pages/home.nx", "showTitle"),
                         [self.find("pages/lib/shared.nx", "showTitle")])

    def test_a_functions_own_heading(self):
        self.assertEqual(self.definitions_at("pages/home.nx", "twice"),
                         [self.find("pages/home.nx", "twice")])

    def test_constants(self):
        self.assertEqual(self.definitions_at("pages/home.nx", "+ SPEED", "SPEED"),
                         [self.find("pages/home.nx", "SPEED")])
        self.assertEqual(self.definitions_at("pages/home.nx", "STEP"),
                         [self.find("pages/lib/shared.nx", "STEP")])
        self.assertEqual(self.definitions_at("pages/home.nx", "LIMIT"),
                         [self.find("program.nx", "LIMIT")])
        self.assertEqual(self.definitions_at("pages/home.nx", "UNIT"),
                         [self.find("units.nx", "UNIT")])

    def test_a_local_and_a_parameter(self):
        self.assertEqual(self.definitions_at("pages/home.nx", "= sum", "sum"),
                         [self.find("pages/home.nx", "sum")])
        self.assertEqual(self.definitions_at("pages/home.nx", "value * 2", "value"),
                         [self.find("pages/home.nx", "value")])

    def test_an_int_global(self):
        self.assertEqual(self.definitions_at("pages/home.nx", "counter"),
                         [self.find("program.nx", "counter")])

    def test_an_include(self):
        self.assertEqual(self.definitions_at("pages/home.nx", "lib/shared.nx"),
                         [file_start("pages/lib/shared.nx")])
        self.assertEqual(self.definitions_at("program.nx", "units.nx"), [file_start("units.nx")])

    def test_pictures_and_fonts(self):
        self.assertEqual(self.definitions_at("pages/home.nx", "@pic(logo)"),
                         [file_start("pictures/logo.png")])
        self.assertEqual(self.definitions_at("pages/home.nx", "@font(Sans16)"),
                         [self.find("app.toml", '"Sans16"', "Sans16")])
        self.assertEqual(self.definitions_at("pages/home.page.toml", "icons/back"),
                         [file_start("pictures/icons/back.png")])
        self.assertEqual(self.definitions_at("pages/home.page.toml", 'font = "Sans16"', "Sans16"),
                         [self.find("app.toml", '"Sans16"', "Sans16")])

    def test_app_lists(self):
        self.assertEqual(self.definitions_at("app.toml", "settings"),
                         [file_start("pages/settings.page.toml")])
        self.assertEqual(self.definitions_at("app.toml", "icons/back"),
                         [file_start("pictures/icons/back.png")])

    def test_a_page_named_alone(self):
        self.assertEqual(self.definitions_at("pages/home.nx", "page settings", "settings"),
                         [self.table("settings", "settings"), file_start("pages/settings.nx")])

    def test_a_library_included_by_two_pages(self):
        self.assertEqual(self.definitions_at("pages/lib/shared.nx", "title.txt"),
                         [self.table("home", "title"), self.table("settings", "title")])

    def test_names_without_a_definition(self):
        self.assertEqual(self.definitions_at("pages/home.nx", "b[3]"), [])
        self.assertEqual(self.definitions_at("pages/home.nx", "].txt", "txt"), [])
        self.assertEqual(self.definitions_at("pages/home.nx", "sys0"), [])
        self.assertEqual(self.definitions_at("pages/home.nx", "Saves"), [])


class ReferenceTest(FolderTestCase):

    def references_at(self, path: str, needle: str, inside: str = None,
                      with_declarations: bool = True) -> list:
        place = self.find(path, needle, inside)
        return references(self.index(), path, place.line, place.start, with_declarations)

    def test_a_function(self):
        self.assertEqual(self.references_at("pages/lib/shared.nx", "showTitle"), [
            self.find("pages/lib/shared.nx", "showTitle"),
            self.find("pages/home.nx", "showTitle"),
            self.find("pages/settings.nx", "showTitle")])

    def test_a_component_from_its_table(self):
        uses = [self.find("pages/home.nx", "vis title", "title"),
                self.find("pages/home.nx", "title.pic", "title"),
                self.find("pages/home.nx", "title.font", "title"),
                self.find("pages/lib/shared.nx", "title.txt", "title")]
        self.assertEqual(self.references_at("pages/home.page.toml", 'name = "title"', "title"),
                         [self.table("home", "title")] + uses)
        self.assertEqual(self.references_at("pages/home.page.toml", 'name = "title"', "title",
                                            with_declarations=False), uses)

    def test_a_constant_from_a_use(self):
        self.assertEqual(self.references_at("pages/home.nx", "LIMIT"),
                         [self.find("program.nx", "LIMIT"), self.find("pages/home.nx", "LIMIT")])

    def test_an_included_file(self):
        self.assertEqual(self.references_at("pages/home.nx", "lib/shared.nx"), [
            self.find("pages/home.nx", "lib/shared.nx"),
            self.find("pages/settings.nx", "lib/shared.nx")])

    def test_a_picture(self):
        self.assertEqual(self.references_at("app.toml", '"logo"', "logo"), [
            self.find("pages/home.nx", "logo"), self.find("app.toml", '"logo"', "logo")])

    def test_where_there_is_no_name(self):
        self.assertEqual(self.references_at("pages/home.nx", "sys0"), [])

    def test_the_form_of_an_own_attribute_is_no_use_of_a_name(self):
        # '&txt&' names t0's txt, not the constant txt, so a rename of the
        # constant leaves it alone.
        write_folder(self.root, {"pages/settings.nx": 'include "lib/shared.nx"\nconst txt = "a"\n\n'
                                                      "on settings.load:\n  showTitle(txt)\n\n"
                                                      "on t0.down:\n  '&txt&' = txt\n"})
        self.assertEqual(self.references_at("pages/settings.nx", "const txt", "txt"), [
            self.find("pages/settings.nx", "const txt", "txt"),
            self.find("pages/settings.nx", "showTitle(txt)", "txt"),
            self.find("pages/settings.nx", "= txt", "txt")])


class SymbolTest(FolderTestCase):

    def test_the_outline_of_a_code_file(self):
        symbols = file_symbols(self.index(), "pages/home.nx")
        self.assertEqual([(symbol.name, symbol.kind) for symbol in symbols],
                         [("SPEED", CONSTANT), ("on save.up", EVENT), ("twice", FUNCTION)])
        self.assertEqual(symbols[1].last_line, self.find("pages/home.nx", "twice").line - 1)

    def test_the_outline_of_a_page_file(self):
        [page] = file_symbols(self.index(), "pages/home.page.toml")
        self.assertEqual((page.name, page.kind), ("home", CLASS))
        self.assertEqual([(child.name, child.detail) for child in page.children],
                         [("title", "text"), ("save", "button")])

    def test_a_search_across_the_folder(self):
        found = folder_symbols(self.index(), "TITLE")
        self.assertEqual([(symbol.name, container) for symbol, container in found],
                         [("title", "home"), ("title", "settings"),
                          ("showTitle", "pages/lib/shared.nx")])


class MacroTest(FolderTestCase):
    """macros.nx: its macros in the outline, `call <name>` leading to its
    heading and back, and the names in a macro answered as the Editor's own
    language, whose code the file holds in either language."""

    MACROS = ('// Marks the title.\nmacro mark title:\n  home.title.txt="m"\n  call other\n'
              "  counter=1\n\nmacro other:\n  printh 4D\n")

    def setUp(self):
        super().setUp()
        write_folder(self.root, {
            "macros.nx": self.MACROS,
            "pages/settings.nx": FOLDER["pages/settings.nx"] + "  call mark title\n"
                                                               "  call Mark title\n",
            "program.nx": FOLDER["program.nx"].replace("page 0", "call other\npage 0")})

    def heading(self, name: str) -> Place:
        return self.find("macros.nx", "macro %s:" % name, name)

    def labels_at(self, path: str, needle: str, after: str) -> list:
        """Returns the labels offered right after `after`, within the first
        `needle` of `path`."""
        place = self.find(path, needle, after)
        return [item.label for item in completions(self.index(), path, place.line, place.end)]

    def test_the_outline(self):
        symbols = file_symbols(self.index(), "macros.nx")
        self.assertEqual([(symbol.name, symbol.kind) for symbol in symbols],
                         [("macro mark title", FUNCTION), ("macro other", FUNCTION)])
        self.assertEqual([(symbol.name, container) for symbol, container
                          in folder_symbols(self.index(), "MARK")],
                         [("mark title", "macros.nx")])

    def test_a_call_leads_to_its_heading(self):
        for inside in ("mark", "title"):
            self.assertEqual(self.definitions_at("pages/settings.nx", "call mark title", inside),
                             [self.heading("mark title")])
        # At the name's very end too, where the cursor stands after typing it.
        place = self.find("pages/settings.nx", "call mark title", "mark title")
        self.assertEqual(definitions(self.index(), place.path, place.line, place.end),
                         [self.heading("mark title")])
        self.assertEqual(self.definitions_at("macros.nx", "call other", "other"),
                         [self.heading("other")])
        # Names are told apart by case, as the build tells them.
        self.assertEqual(self.definitions_at("pages/settings.nx", "call Mark title", "Mark"), [])
        self.assertEqual(self.definitions_at("macros.nx", "macro mark title:", "mark"),
                         [self.heading("mark title")])

    def test_references_from_a_heading_and_a_call(self):
        call = self.find("pages/settings.nx", "call mark title", "mark title")
        place = self.heading("mark title")
        self.assertEqual(references(self.index(), "macros.nx", place.line, place.start, True),
                         [place, call])
        # In program.nx too.
        place = self.find("macros.nx", "call other", "other")
        self.assertEqual(references(self.index(), "macros.nx", place.line, place.start, False),
                         [self.find("program.nx", "call other", "other"), place])

    def test_completion_after_call(self):
        self.assertEqual(self.labels_at("macros.nx", "call other", "call "),
                         ["mark title", "other"])
        # A page's code calls them in either language.
        self.assertEqual(self.labels_at("pages/settings.nx", "call mark title", "call "),
                         ["mark title", "other"])

    def test_names_in_a_macro(self):
        self.assertEqual(self.definitions_at("macros.nx", "home.title.txt", "title"),
                         [self.table("home", "title")])
        self.assertEqual(self.definitions_at("macros.nx", "counter=1", "counter"),
                         [self.find("program.nx", "counter")])
        # A constant of nxlang, which a macro cannot use, is no name there.
        self.write("macros.nx", self.MACROS + "  sys0=LIMIT\n")
        self.assertEqual(self.definitions_at("macros.nx", "sys0=LIMIT", "LIMIT"), [])
        labels = self.labels_at("macros.nx", "  counter=1", "  ")
        self.assertTrue({"counter", "total", "dim", "home"} <= set(labels), labels)
        self.assertFalse({"LIMIT", "UNIT", "showTitle"} & set(labels), labels)
        self.assertEqual(self.labels_at("macros.nx", "home.title.txt", "home."), ["title", "save"])

    def write(self, path: str, text: str):
        write_folder(self.root, {path: text})


class EditorLanguageMacroTest(MacroTest):
    """The same, in a folder in the Editor's own language."""

    def setUp(self):
        super().setUp()
        self.write("app.toml", FOLDER["app.toml"].replace('"nxlang"', '"nextion"'))


class HoverTest(FolderTestCase):

    def hover_at(self, path: str, needle: str, inside: str = None):
        place = self.find(path, needle, inside)
        return hover(self.index(), path, place.line, place.start)

    def test_a_component(self):
        text = self.hover_at("pages/home.nx", "vis title", "title")
        self.assertIn('name = "title"\ntype = "text"', text)
        self.assertNotIn("save", text)

    def test_a_function_with_its_comment(self):
        self.assertEqual(self.hover_at("pages/home.nx", "showTitle"),
                         "```nxwright\n// Shows a message in the page's title.\n"
                         "function showTitle(message: text):\n```")

    def test_a_constant(self):
        self.assertEqual(self.hover_at("pages/home.nx", "LIMIT"),
                         "```nxwright\nconst LIMIT = 40\n```")

    def test_a_picture(self):
        self.assertIn("![logo](%s)" % uri_of(self.root / "pictures/logo.png"),
                      self.hover_at("pages/home.nx", "@pic(logo)"))

    def test_a_font(self):
        header = bytes(7) + bytes([16, 0, 0, 32, 126]) + (95).to_bytes(4, "little")
        (self.root / "fonts").mkdir(exist_ok=True)
        (self.root / "fonts" / "Sans16.zi").write_bytes(header)
        self.assertEqual(self.hover_at("pages/home.nx", "@font(Sans16)"),
                         "Font `Sans16`: 16 pixels high, characters 32 to 126 (95 characters)")
        # A font in utf-8: its header counts every code point to U+FFFF, but
        # it holds only the characters chosen.
        (self.root / "fonts" / "Sans16.zi").write_bytes(utf8_fixture("NotoSans20-cyrillic"))
        self.assertEqual(self.hover_at("pages/home.nx", "@font(Sans16)"),
                         "Font `Sans16`: 20 pixels high, 384 characters in utf-8")
        # A font in gb2312: its header gives the range of a character's
        # second byte where a one-byte font's gives its characters.
        (self.root / "fonts" / "Sans16.zi").write_bytes(gb2312_font())
        self.assertEqual(self.hover_at("pages/home.nx", "@font(Sans16)"),
                         "Font `Sans16`: 2 pixels high, 8273 characters in gb2312")

    def test_a_generated_variable(self):
        write_folder(self.root, {"pages/home.nx": "on save.up:\n  sys0 = __g1_2\n  __v0.txt = 1\n"})
        self.assertIn("the 3rd of page 1 (`settings`)", self.hover_at("pages/home.nx", "__g1_2"))
        self.assertIn("a local, a parameter", self.hover_at("pages/home.nx", "__v0"))

    def test_nothing_to_say(self):
        self.assertIsNone(self.hover_at("pages/home.nx", "sys0"))

    def test_an_attribute_in_code(self):
        text = self.hover_at("pages/home.nx", "title.pic", "pic")
        self.assertTrue(text.startswith("`pic` of a text: The picture drawn as the background"),
                        text)
        self.assertIn("Can be changed in code.", text)

    def test_an_attribute_of_another_pages_component(self):
        self.assertTrue(self.hover_at("pages/home.nx", "settings.t0.txt", "txt")
                        .startswith("`txt` of a text:"))
        # The component itself, after its page's name and a dot, is no attribute.
        self.assertIn('name = "t0"', self.hover_at("pages/home.nx", "settings.t0.txt", "t0"))

    def test_an_attribute_in_a_library_used_by_two_pages(self):
        # Both pages' `title` is a text: described once.
        text = self.hover_at("pages/lib/shared.nx", "title.txt", "txt")
        self.assertEqual(text.count("`txt` of a text"), 1)

    def test_an_attribute_says_what_code_may_store(self):
        # As the running screen keeps a number code stores in it
        # (attribute_descriptions.toml, code_range and code_wraps).
        write_folder(self.root, {"pages/home.nx": "on save.up:\n  title.aph = 1\n"})
        self.assertIn("Can be changed in code. Code may store 0 to 127. The screen refuses other "
                      "numbers.", self.hover_at("pages/home.nx", "title.aph", "aph"))

    def test_an_attribute_says_what_the_screen_keeps_of_any_number(self):
        write_folder(self.root, {"pages/home.nx": "on save.up:\n  title.vvs0 = 1\n",
                                 "pages/home.page.toml": FOLDER["pages/home.page.toml"]
                                 .replace('type = "text"', 'type = "scrolling-text"', 1)})
        self.assertIn("Code may store any number. The screen keeps its last 2 bytes, signed: "
                      "40000 reads -25536.", self.hover_at("pages/home.nx", "title.vvs0", "vvs0"))

    def test_a_range_of_one_number(self):
        # A hotspot's drag keeps 0, whatever code stores.
        self.assertTrue(attribute_markdown("hotspot", "drag").endswith(
            "Code may store only 0. The screen refuses other numbers."))

    def test_a_method_says_nothing_of_being_changed(self):
        # Code calls a method; it is never changed.
        for type_name, method in (("file-browser", "up"), ("file-stream", "find")):
            with self.subTest(method=method):
                text = attribute_markdown(type_name, method)
                self.assertNotIn("be changed in code", text)

    def test_choices_say_what_code_may_store_alone(self):
        # A text's xcen takes 0 to 2, which its choices say.
        write_folder(self.root, {"pages/home.nx": "on save.up:\n  title.xcen = 1\n"})
        self.assertNotIn("Code may store", self.hover_at("pages/home.nx", "title.xcen", "xcen"))

    def test_an_attribute_with_choices(self):
        write_folder(self.root, {"pages/home.nx": "on save.up:\n  title.sta = 1\n"})
        text = self.hover_at("pages/home.nx", "title.sta", "sta")
        self.assertIn("- 1: a colour", text)
        self.assertIn("Cannot be changed in code.", text)

    def test_an_attribute_in_a_page_file(self):
        # A button's `pic` has a description of its own.
        text = self.hover_at("pages/home.page.toml", 'pic = "icons/back"', "pic")
        self.assertTrue(text.startswith("`pic` of a button: The background picture when the "
                                        "button is not pressed"), text)

    def test_a_page_files_other_keys_keep_their_hover(self):
        self.assertIn('type = "button"', self.hover_at("pages/home.page.toml",
                                                       'name = "save"', "save"))
        self.assertIsNone(self.hover_at("pages/home.page.toml", 'type = "button"', "type"))


class CompletionTest(FolderTestCase):

    def labels_after(self, path: str, needle: str) -> list:
        """Returns the labels offered right after the first `needle` in `path`."""
        place = self.find(path, needle)
        return [item.label for item in completions(self.index(), path, place.line, place.end)]

    def test_attributes_of_a_component(self):
        labels = self.labels_after("pages/home.nx", "title.")
        self.assertIn("txt", labels)
        self.assertIn("pco", labels)
        self.assertNotIn("title", labels)

    def test_attributes_carry_their_description(self):
        place = self.find("pages/home.nx", "title.")
        items = {item.label: item for item in completions(self.index(), "pages/home.nx",
                                                           place.line, place.end)}
        self.assertTrue(items["txt"].documentation.startswith("`txt` of a text: The text shown."))
        self.assertIn("Code may store 0 to 127.", items["aph"].documentation)

    def test_a_wrapping_attribute_carries_what_the_screen_keeps(self):
        write_folder(self.root, {"pages/home.page.toml": FOLDER["pages/home.page.toml"]
                                 .replace('type = "text"', 'type = "scrolling-text"', 1)})
        place = self.find("pages/home.nx", "title.")
        items = {item.label: item for item in completions(self.index(), "pages/home.nx",
                                                           place.line, place.end)}
        self.assertIn("The screen keeps its last 2 bytes, signed: 40000 reads -25536.",
                      items["vvs0"].documentation)

    def test_components_of_another_page(self):
        self.assertEqual(self.labels_after("pages/home.nx", "settings."), ["t0", "title"])

    def test_names_in_scope(self):
        labels = self.labels_after("pages/home.nx", "  sys0 = ")
        for name in ["title", "save", "sum", "SPEED", "STEP", "LIMIT", "UNIT", "showTitle",
                     "twice", "counter", "dim", "settings"]:
            self.assertIn(name, labels)
        self.assertNotIn("value", labels)
        # sys0 is no system variable but an int program.nx may declare, as
        # the Editor's new project does; this one does not.
        self.assertNotIn("sys0", labels)

    def test_the_system_variables_of_the_screens_series(self):
        # The Intelligent series lacks lowpower alone; the Basic lacks the
        # clock's variables too, and takes dim.
        labels = self.labels_after("pages/home.nx", "  sys0 = ")
        self.assertEqual(("rtc0" in labels, "lowpower" in labels), (True, False))
        app = self.root / "app.toml"
        app.write_text(app.read_text(encoding="utf-8").replace(
            'screen = "NX8048P050"', 'screen = "NX4832T035"'), encoding="utf-8", newline="\n")
        labels = self.labels_after("pages/home.nx", "  sys0 = ")
        self.assertEqual(("dim" in labels, "rtc0" in labels), (True, False))
        # A screen nxwright does not know, as while it is half typed, takes all.
        app.write_text(app.read_text(encoding="utf-8").replace(
            'screen = "NX4832T035"', 'screen = "NX48"'), encoding="utf-8", newline="\n")
        self.assertIn("lowpower", self.labels_after("pages/home.nx", "  sys0 = "))

    def test_nothing_in_a_string_or_a_comment(self):
        self.assertEqual(self.labels_after("pages/home.nx", 'showTitle("x'), [])
        self.assertEqual(self.labels_after("pages/home.nx", "// Sav"), [])

    def test_pictures_and_fonts_in_a_page_file(self):
        self.assertEqual(self.labels_after("pages/home.page.toml", 'pic = "'), ["icons/back", "logo"])
        self.assertEqual(self.labels_after("pages/home.page.toml", 'font = "'), ["Sans16"])

    def test_the_parameters_of_a_call(self):
        line = '  sys0 = join("a", twice(1), '
        write_folder(self.root, {"pages/home.nx": 'include "lib/shared.nx"\non save.up:\n' + line
                                 + "\nfunction twice(value: number) -> number:\n  return 1\n"})
        index = self.index()
        found = signature(index, "pages/home.nx", 2, len(line))
        self.assertEqual((found.label, found.parameters, found.active),
                         ("join(first: text, second: text) -> text",
                          ["first: text", "second: text"], 2))
        self.assertEqual(signature(index, "pages/home.nx", 2, len('  sys0 = join("a", twice(')),
                         Signature("twice(value: number) -> number", ["value: number"], 0))
        self.assertIsNone(signature(index, "pages/home.nx", 2, len("  sys0 = ")))

    def test_a_half_typed_parameter_keeps_its_place(self):
        line = "  three(1, 2, "
        write_folder(self.root, {"pages/home.nx": "function three(a: number, b, c: text):\n"
                                                  "  sys0 = 1\non save.up:\n" + line})
        found = signature(self.index(), "pages/home.nx", 3, len(line))
        self.assertEqual((found.parameters, found.active), (["a: number", "b", "c: text"], 2))


class ServerAnswerTest(ServerTestCase):
    """The server's answers to a code editor's requests, in the protocol's form:
    references, the outline, hovers, completion, checks, formatting, and others."""

    def at(self, path: str, needle: str, inside: str = None) -> dict:
        place = self.find(path, needle, inside)
        return {"textDocument": {"uri": uri_of(self.root / path)},
                "position": {"line": place.line, "character": place.start}}

    def setUp(self):
        super().setUp()
        self.initialize()

    def test_references(self):
        params = self.at("pages/home.nx", "LIMIT")
        params["context"] = {"includeDeclaration": False}
        result = self.request("textDocument/references", params)["result"]
        self.assertEqual([location["uri"] for location in result],
                         [uri_of(self.root / "pages/home.nx")])

    def test_outline(self):
        result = self.request("textDocument/documentSymbol",
                              {"textDocument": {"uri": uri_of(self.root / "pages/home.page.toml")}})
        result = result["result"]
        self.assertEqual([child["name"] for child in result[0]["children"]], ["title", "save"])
        self.assertEqual(result[0]["selectionRange"]["start"],
                         {"line": 1, "character": len('name = "')})

    def test_search_in_the_folders_of_open_files(self):
        self.assertEqual(self.request("workspace/symbol", {"query": "join"})["result"], [])
        self.notify("textDocument/didOpen", {"textDocument": document_item(
            uri_of(self.root / "pages/home.nx"), FOLDER["pages/home.nx"])})
        result = self.request("workspace/symbol", {"query": "join"})["result"]
        self.assertEqual([(symbol["name"], symbol["containerName"]) for symbol in result],
                         [("join", "pages/lib/shared.nx")])

    def test_hover(self):
        result = self.request("textDocument/hover", self.at("pages/home.nx", "LIMIT"))["result"]
        self.assertEqual(result["contents"]["kind"], "markdown")

    def test_completion(self):
        params = self.at("pages/home.nx", "settings.t0", "t0")
        result = self.request("textDocument/completion", params)["result"]
        self.assertEqual([item["label"] for item in result], ["t0", "title"])
        self.assertNotIn("documentation", result[0])

    def test_completion_of_a_macro_replaces_what_is_typed(self):
        # A macro's name may hold spaces, which the word at the cursor would
        # cut, so the item says the text it replaces: all of the name typed.
        write_folder(self.root, {"macros.nx": "macro mark title:\n  printh 4D\n\n"
                                              "macro other:\n  call mark ti\n"})
        place = self.find("macros.nx", "call mark ti", "mark ti")
        params = {"textDocument": {"uri": uri_of(self.root / "macros.nx")},
                  "position": {"line": place.line, "character": place.end}}
        result = self.request("textDocument/completion", params)["result"]
        item = next(item for item in result if item["label"] == "mark title")
        self.assertEqual(item["textEdit"], {"newText": "mark title", "range": {
            "start": {"line": place.line, "character": place.start},
            "end": {"line": place.line, "character": place.end}}})

    def test_completion_of_attributes_with_their_documentation(self):
        params = self.at("pages/home.nx", "title.pic", "pic")
        result = self.request("textDocument/completion", params)["result"]
        documentation = next(item["documentation"] for item in result if item["label"] == "txt")
        self.assertEqual(documentation["kind"], "markdown")
        self.assertTrue(documentation["value"].startswith("`txt` of a text:"))

    def test_signature_help(self):
        params = self.at("pages/home.nx", 'showTitle("x', '"x')
        result = self.request("textDocument/signatureHelp", params)["result"]
        self.assertEqual(result["signatures"][0]["label"], "showTitle(message: text)")
        self.assertEqual(result["activeParameter"], 0)


class LiveCheckTest(CheckFolderTestCase):
    """Checks as files change, through the server."""

    def setUp(self):
        super().setUp()
        self.connection = ServerConnection()
        self.sent, self.server = self.connection.sent, self.connection.server
        self.connection.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                "params": INITIALIZE_PARAMS})
        self.versions = {}

    def uri(self, path: str) -> str:
        return uri_of(self.root / path)

    def change(self, path: str, text: str, method: str = "textDocument/didChange"):
        """Opens the file `path` with `text`, or changes its whole text to it."""
        version = self.versions[path] = self.versions.get(path, 0) + 1
        if method == "textDocument/didOpen":
            params = {"textDocument": document_item(self.uri(path), text, version)}
        else:
            params = {"textDocument": {"uri": self.uri(path), "version": version},
                      "contentChanges": [{"text": text}]}
        self.connection.handle({"jsonrpc": "2.0", "method": method, "params": params})

    def published(self) -> dict:
        """Runs the checks that wait; returns {file: [(line, severity, message)]} sent."""
        self.sent.clear()
        self.assertTrue(self.server.checks_waiting())
        self.server.run_checks()
        self.assertFalse(self.server.checks_waiting())
        return {message["params"]["uri"]: [(diagnostic["range"]["start"]["line"],
                                            diagnostic["severity"], diagnostic["message"])
                                           for diagnostic in message["params"]["diagnostics"]]
                for message in self.sent if message["method"] == "textDocument/publishDiagnostics"}

    def test_unsaved_text_is_checked(self):
        self.change("pages/page0.nx", "on page0.load:\n  bogus.txt = 1\n", "textDocument/didOpen")
        self.assertEqual(self.published(), {self.uri("pages/page0.nx"): [
            (1, 1, "bogus is neither on this page nor a page")]})
        self.change("pages/page0.nx", "on page0.load:\n  title.txt = \"a\"\n")
        self.assertEqual(self.published(), {self.uri("pages/page0.nx"): []})

    def test_a_running_server_checks_once_changes_pause(self):
        # Through `nxwright lsp`'s own loop: the checks run on pygls's event
        # loop, CHECK_PAUSE after the last change, with nothing more from the
        # editor.
        read_end, write_end = os.pipe()
        output, served = _KeptBytes(), []
        with open(read_end, "rb") as stdin:
            editor = open(write_end, "wb")
            thread = threading.Thread(target=lambda: served.append(serve(stdin, output)))
            thread.start()
            write_message(editor, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                   "params": INITIALIZE_PARAMS})
            write_message(editor, {"jsonrpc": "2.0", "method": "textDocument/didOpen",
                                   "params": {"textDocument": document_item(
                                       self.uri("pages/page0.nx"),
                                       "on page0.load:\n  bogus.txt = 1\n")}})
            deadline = time.monotonic() + 10
            while b"publishDiagnostics" not in output.getvalue() and time.monotonic() < deadline:
                time.sleep(0.05)
            write_message(editor, {"jsonrpc": "2.0", "id": 2, "method": "shutdown"})
            write_message(editor, {"jsonrpc": "2.0", "method": "exit"})
            editor.close()
            thread.join(10)
        self.assertIn(b"bogus is neither on this page nor a page", output.getvalue())
        self.assertEqual(served, [0])

    def test_a_page_past_the_screens_memory(self):
        # On a basic screen, four texts of txt_maxl 1,000 beside page0's title
        # pass its memory. The error stays at page0's file as only the
        # second page changes, as the memory counts every page.
        app = self.text("app.toml")
        self.assertIn('screen = "NX8048P050"', app)
        self.change("app.toml", app.replace("NX8048P050", "NX4832T035"), "textDocument/didOpen")
        self.change("pages/page0.page.toml", self.text("pages/page0.page.toml") + "".join(
            '\n[[component]]\nname = "t%d"\ntype = "text"\nx = 0\ny = 0\nw = 100\nh = 30\n'
            'txt_maxl = 1000\n' % number for number in range(4)), "textDocument/didOpen")
        refused = (0, 1, "page0.page.toml: its memory, 16 + 4092 = 4108 bytes, passes the "
                         "NX4832T035's 3584, and the Nextion Editor's compile refuses it "
                         "(\"Memory overflow\")")
        self.assertEqual(self.published()[self.uri("pages/page0.page.toml")], [refused])
        self.change("pages/second.nx", "", "textDocument/didOpen")
        self.assertEqual(self.published()[self.uri("pages/page0.page.toml")], [refused])

    def test_warnings_carry_their_rule(self):
        self.change("pages/page0.nx", "const UNUSED = 1\n", "textDocument/didOpen")
        self.server.run_checks()
        [diagnostic] = [message["params"]["diagnostics"] for message in self.sent
                        if message.get("method") == "textDocument/publishDiagnostics"][0]
        self.assertEqual((diagnostic["severity"], diagnostic["code"]), (2, "unused-constant"))

    def test_only_the_pages_a_change_affects(self):
        self.change("pages/second.nx", "", "textDocument/didOpen")
        self.assertEqual(self.published(), {})
        # A mistake on disk in page0, which no change marks, stays unseen
        # while only the second page's file changes.
        self.write("pages/page0.nx", "on page0.load:\n  bogus.txt = 1\n")
        self.change("pages/second.page.toml", self.text("pages/second.page.toml"), "textDocument/didOpen")
        self.assertEqual(self.published(), {})
        self.connection.handle({"jsonrpc": "2.0", "method": "workspace/didChangeWatchedFiles",
                            "params": {"changes": [{"uri": self.uri("pages/page0.nx"),
                                                    "type": 2}]}})
        self.assertEqual(list(self.published()), [self.uri("pages/page0.nx")])

    def test_a_failing_check_does_not_end_the_server(self):
        self.change("pages/page0.nx", "", "textDocument/didOpen")
        with mock.patch("nxwright.language_server.live_checks.check_folder",
                        side_effect=RuntimeError("broken")), \
                contextlib.redirect_stderr(io.StringIO()):
            self.server.run_checks()
        self.change("pages/page0.nx", "on page0.load:\n  bogus.txt = 1\n")
        self.assertEqual(list(self.published()), [self.uri("pages/page0.nx")])

    def test_each_check_says_it_ran(self):
        # A clean folder has no findings to send, but the editor's view of the
        # page's limits must still be refreshed.
        self.change("pages/page0.nx", "", "textDocument/didOpen")
        self.sent.clear()
        self.server.run_checks()
        self.assertEqual(self.sent, [{"jsonrpc": "2.0", "method": "nxwright/checked",
                                      "params": {"uri": uri_of(self.root)}}])

    def test_a_folder_that_cannot_be_read_clears_the_pages(self):
        self.change("pages/page0.nx", "on page0.load:\n  bogus.txt = 1\n", "textDocument/didOpen")
        self.published()
        # app.toml breaks on disk, and the next change is the page's: its
        # pages cannot be checked, so their old findings go.
        self.write("app.toml", "format = 9\n")
        self.change("pages/page0.nx", "on page0.load:\n  bogus.txt = 2\n")
        self.assertEqual(self.published(), {
            self.uri("pages/page0.nx"): [],
            self.uri("app.toml"): [(0, 1, "app.toml is in source format 9, which needs a newer "
                                          "nxwright; this one reads format 1")]})

    def request(self, method: str, path: str, **params) -> dict:
        self.connection.handle({"jsonrpc": "2.0", "id": 9, "method": method, "params": dict(
            textDocument={"uri": self.uri(path)}, **params)})
        return self.sent[-1]

    def test_formatting(self):
        self.change("pages/page0.nx", "on page0.load:\n  sys0=1\n", "textDocument/didOpen")
        [edit] = self.request("textDocument/formatting", "pages/page0.nx",
                              options={"tabSize": 2, "insertSpaces": True})["result"]
        self.assertEqual(edit, {"range": {"start": {"line": 0, "character": 0},
                                          "end": {"line": 2, "character": 0}},
                                "newText": "on page0.load:\n  sys0 = 1\n"})

    def test_formatting_refused(self):
        self.change("pages/page0.nx", "on page0.load:\n  bogus.txt=1\n", "textDocument/didOpen")
        reply = self.request("textDocument/formatting", "pages/page0.nx",
                             options={"tabSize": 2, "insertSpaces": True})
        self.assertEqual(reply["error"]["code"], -32803)
        self.assertIn("does not build", reply["error"]["message"])

    def test_rename(self):
        self.change("pages/page0.nx", "on page0.load:\n  title.txt = \"a\"\n",
                    "textDocument/didOpen")
        result = self.request("textDocument/rename", "pages/page0.nx",
                              position={"line": 1, "character": 3}, newName="heading")["result"]
        self.assertEqual(sorted(result["changes"]),
                         sorted([self.uri("pages/page0.nx"), self.uri("pages/page0.page.toml")]))
        self.assertEqual(result["changes"][self.uri("pages/page0.nx")],
                         [{"range": {"start": {"line": 1, "character": 2},
                                     "end": {"line": 1, "character": 7}}, "newText": "heading"}])

    def test_editor_code(self):
        self.change("pages/page0.nx", "on page0.load:\n  sys0 = 1 + 2\n", "textDocument/didOpen")
        result = self.request("nxwright/editorCode", "pages/page0.nx")["result"]
        self.assertEqual(result, {"page": "page0", "text": "// on page0.load\nsys0=1+2\n",
                                  "sourceLines": [-1, 1]})
        self.change("pages/page0.nx", "on page0.load:\n  bogus.txt = 1\n")
        result = self.request("nxwright/editorCode", "pages/page0.nx")["result"]
        self.assertIn("bogus", result["error"])

    def test_limits_of_the_page(self):
        self.change("pages/page0.nx", "function show():\n  sys0 = 1\n\non page0.load:\n  show()\n",
                    "textDocument/didOpen")
        self.server.run_checks()
        self.connection.handle({"jsonrpc": "2.0", "id": 2, "method": "nxwright/limits", "params": {
            "textDocument": {"uri": self.uri("pages/page0.nx")}}})
        limits = self.sent[-1]["result"]
        self.assertEqual((limits["page"], limits["objects"], limits["chain"], limits["mostChain"]),
                         ("page0", 3, ["page0.load", "show"], 7))


if __name__ == "__main__":
    unittest.main()
