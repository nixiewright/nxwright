"""The quick fixes the language server offers on the build's refusals
(language_server/quick_fixes.py): each made from the problem's data, applied
to the files as the server reads them, and offered only where it applies."""
import unittest

from nxwright import NxwrightError
from nxwright.language_server.file_texts import uri_of
from nxwright.language_server.quick_fixes import place_in_line
from tests.language_server_connection import INITIALIZE_PARAMS, ServerConnection, document_item
from tests.test_folder_check import FolderTestCase, edited_page_file


class QuickFixTestCase(FolderTestCase):
    """The language server on a new folder in strict Nextion syntax, its
    problems and code actions asked for as VS Code asks for them."""
    language = "nextion"

    def setUp(self):
        super().setUp()
        self.connection = ServerConnection()
        self.sent, self.server = self.connection.sent, self.connection.server
        self.connection.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                "params": INITIALIZE_PARAMS})
        self.versions, self.texts = {}, {}

    def uri(self, path: str) -> str:
        return uri_of(self.root / path)

    def open(self, path: str, text: str):
        """Opens the file `path` in the editor with `text`, or changes its
        whole text to it."""
        version = self.versions[path] = self.versions.get(path, 0) + 1
        self.texts[path] = text
        if version == 1:
            method, params = "textDocument/didOpen", {
                "textDocument": document_item(self.uri(path), text, version)}
        else:
            method, params = "textDocument/didChange", {
                "textDocument": {"uri": self.uri(path), "version": version},
                "contentChanges": [{"text": text}]}
        self.connection.handle({"jsonrpc": "2.0", "method": method, "params": params})

    def problems(self, path: str) -> list:
        """Runs the checks that wait, and returns the problems sent for `path`."""
        self.sent.clear()
        self.server.run_checks()
        sent = [message["params"]["diagnostics"] for message in self.sent
                if message.get("method") == "textDocument/publishDiagnostics"
                and message["params"]["uri"] == self.uri(path)]
        self.assertTrue(sent, "no problems sent for %s" % path)
        return sent[-1]

    def errors(self, path: str) -> list:
        """The problems sent for `path` that are errors, the build's refusals."""
        return [problem for problem in self.problems(path) if problem["severity"] == 1]

    def fixes(self, path: str, problem: dict) -> list:
        """Returns the code actions the server offers on `problem` of `path`."""
        self.connection.handle({"jsonrpc": "2.0", "id": 9, "method": "textDocument/codeAction",
                                "params": {"textDocument": {"uri": self.uri(path)},
                                           "range": problem["range"],
                                           "context": {"diagnostics": [problem]}}})
        reply = self.sent[-1]
        self.assertNotIn("error", reply)
        return reply["result"] or []

    def text_of(self, path: str) -> str:
        return self.texts[path] if path in self.texts else self.text(path)

    def applied(self, action: dict) -> dict:
        """Returns {path: text} of the files the action's edit changes, as
        they would be once it is applied."""
        changed = {}
        for uri, edits in action["edit"]["changes"].items():
            path = next(path for path in [str(p.relative_to(self.root).as_posix())
                                          for p in self.root.rglob("*")]
                        if self.uri(path) == uri)
            lines = self.text_of(path).split("\n")
            for edit in sorted(edits, key=lambda edit: (edit["range"]["start"]["line"],
                                                        edit["range"]["start"]["character"]),
                               reverse=True):
                start, end = edit["range"]["start"], edit["range"]["end"]
                before = "\n".join(lines[:start["line"]] + [lines[start["line"]][
                    :start["character"]]])
                after = "\n".join([lines[end["line"]][end["character"]:]] + lines[end["line"] + 1:])
                lines = (before + edit["newText"] + after).split("\n")
            changed[path] = "\n".join(lines)
        return changed

    def fixed(self, path: str, text: str) -> tuple:
        """Opens `path` with `text`, and returns (the title of the one fix its
        one problem offers, {path: text} once applied)."""
        self.open(path, text)
        [problem] = self.errors(path)
        [action] = self.fixes(path, problem)
        self.assertEqual(action["kind"], "quickfix")
        # A fix in code keeps its meaning, so VS Code's Auto Fix may apply it.
        self.assertEqual(action.get("isPreferred", False), not path.endswith(".page.toml"))
        return action["title"], self.applied(action)

    def no_fix(self, path: str, text: str):
        """Opens `path` with `text`, and checks its one problem offers no fix."""
        self.open(path, text)
        [problem] = self.errors(path)
        self.assertEqual(self.fixes(path, problem), [])


class CodeFixTest(QuickFixTestCase):

    def test_a_command_in_small_letters(self):
        title, changed = self.fixed("pages/page0.nx", "on page0.load:\n  CLS BLUE\n")
        self.assertEqual(changed, {"pages/page0.nx": "on page0.load:\n  cls BLUE\n"})
        self.assertIn("cls", title)

    def test_a_space_after_int(self):
        title, changed = self.fixed("pages/page0.nx", "on page0.load:\n  int\tx=1\n")
        self.assertEqual(changed, {"pages/page0.nx": "on page0.load:\n  int x=1\n"})

    def test_hex_digits_in_pairs(self):
        title, changed = self.fixed("pages/page0.nx", "on page0.load:\n  sys0=0x123\n")
        self.assertEqual(changed, {"pages/page0.nx": "on page0.load:\n  sys0=0x0123\n"})

    def test_a_signed_hex_constant_as_a_decimal(self):
        title, changed = self.fixed("pages/page0.nx", "on page0.load:\n  sys0=5*-0x10\n")
        self.assertEqual(changed, {"pages/page0.nx": "on page0.load:\n  sys0=5*-16\n"})

    def test_no_fix_where_none_keeps_the_value(self):
        for line in ("sys0=0x", "sys0=0x123456789", "sys0=-0xFFFFFFFF"):
            with self.subTest(line=line):
                self.no_fix("pages/page0.nx", "on page0.load:\n  %s\n" % line)

    def test_no_fix_where_the_text_is_twice_in_the_line(self):
        self.no_fix("pages/page0.nx", "on page0.load:\n  sys0=0x123+0x123\n")

    def test_no_fix_once_the_line_has_changed(self):
        self.open("pages/page0.nx", "on page0.load:\n  CLS BLUE\n")
        [problem] = self.errors("pages/page0.nx")
        self.open("pages/page0.nx", "on page0.load:\n  cls BLUE\n")
        self.assertEqual(self.fixes("pages/page0.nx", problem), [])


class NxlangCodeFixTest(QuickFixTestCase):
    language = "nxlang"

    def test_a_command_in_small_letters(self):
        title, changed = self.fixed("pages/page0.nx", "on page0.load:\n  CLS BLUE\n")
        self.assertEqual(changed, {"pages/page0.nx": "on page0.load:\n  cls BLUE\n"})


class ProgramVariableFixTest(QuickFixTestCase):

    def without_declaration(self):
        # A blank line apart from the file's own comment at its top.
        self.write("program.nx", self.text("program.nx").replace("int sys0=0,sys1=0,sys2=0\n",
                                                                 "\n// Settings.\n", 1))

    def test_declared_in_program_nx(self):
        self.without_declaration()
        title, changed = self.fixed("pages/page0.nx", "on page0.load:\n  sys1=2\n")
        program = changed["program.nx"].split("\n")
        # Before the first line of code, above the comment lines over it.
        self.assertEqual(program[program.index("// Settings.") - 1], "int sys1=0")
        self.assertEqual(list(changed), ["program.nx"])

    def test_no_fix_without_program_nx(self):
        self.without_declaration()
        self.open("pages/page0.nx", "on page0.load:\n  sys1=2\n")
        [problem] = self.errors("pages/page0.nx")
        (self.root / "program.nx").unlink()
        self.assertEqual(self.fixes("pages/page0.nx", problem), [])

    def test_no_fix_once_declared(self):
        self.without_declaration()
        self.open("pages/page0.nx", "on page0.load:\n  sys1=2\n")
        [problem] = self.errors("pages/page0.nx")
        self.open("program.nx", "int sys1=0\n" + self.text("program.nx"))
        self.assertEqual(self.fixes("pages/page0.nx", problem), [])


class NxlangProgramVariableFixTest(ProgramVariableFixTest):
    language = "nxlang"

    def test_the_fixed_folder_builds(self):
        self.without_declaration()
        self.write("pages/page0.nx", "on page0.load:\n  sys1 = 2\n")
        title, changed = self.fixed("pages/page0.nx", "on page0.load:\n  sys1 = 2\n")
        self.write("program.nx", changed["program.nx"])
        self.assertEqual(self.check().errors(), [])


class PageFileFixTest(QuickFixTestCase):

    def page_with(self, **values) -> str:
        """The text of page0's page file, its "title" component given `values`."""
        return edited_page_file(self.text("pages/page0.page.toml"),
                                lambda tables: tables[1].update(values))

    def test_a_keyboards_component_made_global(self):
        title, changed = self.fixed("pages/page0.page.toml", self.page_with(key=2))
        self.assertIn("vscope = 1", changed["pages/page0.page.toml"])
        self.assertIn("global", title)

    def test_a_component_made_2_pixels_high(self):
        title, changed = self.fixed("pages/page0.page.toml", self.page_with(h=1))
        self.assertIn("h = 2", changed["pages/page0.page.toml"])

    def test_no_fix_once_global(self):
        self.open("pages/page0.page.toml", self.page_with(key=2))
        [problem] = self.errors("pages/page0.page.toml")
        self.open("pages/page0.page.toml", self.page_with(key=2, vscope=1))
        self.assertEqual(self.fixes("pages/page0.page.toml", problem), [])

    def test_no_fix_once_enlarged(self):
        self.open("pages/page0.page.toml", self.page_with(h=1))
        [problem] = self.errors("pages/page0.page.toml")
        self.open("pages/page0.page.toml", self.page_with(h=50))
        self.assertEqual(self.fixes("pages/page0.page.toml", problem), [])

    def test_a_page_file_fix_is_not_applied_without_asking(self):
        # VS Code's Auto Fix applies a preferred fix without asking; this one
        # changes how the component looks, so the user chooses it.
        self.open("pages/page0.page.toml", self.page_with(h=1))
        [problem] = self.errors("pages/page0.page.toml")
        [action] = self.fixes("pages/page0.page.toml", problem)
        self.assertFalse(action.get("isPreferred", False))


class PlaceInLineTest(unittest.TestCase):

    def test_a_whole_word_outside_quoted_texts(self):
        self.assertEqual(place_in_line('t0.txt="Print" Print', "Print"), 15)
        self.assertIsNone(place_in_line("myPrint", "Print"))
        self.assertIsNone(place_in_line("sys0=0x1234", "0x123"))
        self.assertEqual(place_in_line("int\tx=1", "int\t"), 0)
        self.assertIsNone(place_in_line("Print Print", "Print"))


class KeptFixTest(unittest.TestCase):

    def test_a_refusal_raised_again_from_its_file_keeps_its_fix(self):
        error = NxwrightError("refused", line=2, fix={"kind": "small-letters"})
        self.assertEqual(error.in_file("pages/page0.nx").fix, {"kind": "small-letters"})


if __name__ == "__main__":
    unittest.main()
