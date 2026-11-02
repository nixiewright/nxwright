"""Extract with a project holding what nxwright does not know: it notes what
it keeps exactly, stops on what may be lost unless told to go on, and
refuses what it cannot keep, before writing anything
(source/unknown_content.py, source/project_files.py)."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

from nxwright import NxwrightError
from nxwright.cli import NO_ANSWER_EXIT_CODE, main
from nxwright.project.container import HmiContainer
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.dumper import ProjectDumper
from nxwright.project.project_writer import ProjectWriter
from nxwright.project.screen_models import model_named
from nxwright.source.project_files import build, extract
from nxwright.source.source_folder import new_source_folder
from nxwright.source.unknown_content import UnknownContentError
from tests.test_container import build_project
from tests.test_new_command import answering

DEMO = Path(__file__).resolve().parents[1] / "examples" / "thermostat" / "app"
# A text component in a page file's form, whose txt is an e with an acute
# accent, which iso-8859-1 would read otherwise from utf-8's bytes.
UTF8_TEXT = ('\n[[component]]\nname = "t0"\ntype = "text"\nx = 10\ny = 10\nw = 100\nh = 30\n'
             'font = "NotoSans24"\ntxt = "é"\ntxt_maxl = 10\n')


def with_new_attribute(text: str) -> str:
    """Returns a page's dump `text` with an attribute nxwright does not
    know, newattr, after the vscope of its object 0, the page itself, and
    the count of its attributes one more."""
    head, start, rest = text.partition("object 0 ")
    body, end, tail = rest.partition("\nobject ")
    count = int(re.search(r"marker att-(\d+)", body).group(1))
    body = body.replace("marker att-%d" % count, "marker att-%d" % (count + 1), 1)
    body = body.replace("\n  vscope = 0\n", "\n  vscope = 0\n  newattr:u8 = 1\n", 1)
    return head + start + body + end + tail


class PatchedDemoTestCase(unittest.TestCase):
    """Builds the demo's project once, and makes patched copies of it."""

    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.work.name)
        cls.demo = cls.folder / "demo.HMI"
        build(DEMO, cls.demo)

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def patched(self, name: str, blocks: dict = None, header: dict = None,
                base: Path = None) -> Path:
        """Returns a copy of the project `base`, by default the demo's,
        named `name`, with `blocks`, {block name: bytes}, added or replaced,
        and each manifest header byte of `header`, {place: value}, changed."""
        container = HmiContainer.from_file(base or self.demo)
        live = dict(container.blocks)
        if header:
            manifest = bytearray(live["main.HMI"])
            for place, value in header.items():
                manifest[place] = value
            live["main.HMI"] = bytes(manifest)
        live.update(blocks or {})
        path = self.folder / name
        path.write_bytes(build_project([(block, data, 0) for block, data in live.items()]))
        return path

    def edited(self, name: str, edit) -> Path:
        """Returns a copy of the demo's project named `name`, written by
        nxwright from its dump after `edit(page text) -> page text` changes
        the first page's dump."""
        dump = self.folder / (name + ".dump")
        ProjectDumper(self.demo, dump).dump()
        page = sorted((dump / "pages").glob("*.txt"))[0]
        page.write_text(edit(page.read_text(encoding="utf-8")), encoding="utf-8")
        path = self.folder / name
        ProjectWriter(self.demo, dump, path).write()
        return path

    def target(self, name: str) -> Path:
        return self.folder / ("source-" + name)


class ExtractUnknownTest(PatchedDemoTestCase):

    def test_a_block_of_another_kind_stops_extract_unless_told_to_go_on(self):
        project = self.patched("block.HMI", blocks={"2.ib": b"?"})
        with self.assertRaises(UnknownContentError) as raised:
            extract(project, self.target("block"))
        self.assertIn("block 2.ib", str(raised.exception))
        self.assertIn("nxwright report", str(raised.exception))
        self.assertFalse(self.target("block").exists())
        messages = extract(project, self.target("block"), continue_with_unknown=True)
        self.assertTrue(any("block 2.ib" in message for message in messages))
        build(self.target("block"), self.folder / "block-again.HMI")
        self.assertNotIn("2.ib", HmiContainer.from_file(self.folder / "block-again.HMI").blocks)

    def test_a_header_byte_of_another_value_may_be_lost(self):
        project = self.patched("header.HMI", header={14: 0x50})
        with self.assertRaises(UnknownContentError) as raised:
            extract(project, self.target("header"))
        self.assertIn("byte 14", str(raised.exception))
        extract(project, self.target("header"), continue_with_unknown=True)
        build(self.target("header"), self.folder / "header-again.HMI")
        rebuilt = HmiContainer.from_file(self.folder / "header-again.HMI").blocks["main.HMI"]
        self.assertEqual(rebuilt[14], 0x4f)

    def test_the_older_header_form_extracts_with_no_question(self):
        project = self.patched("older.HMI", header={9: 0x43, 36: 1, 65: 2})
        self.assertEqual(extract(project, self.target("older")), [])

    def test_an_unknown_encoding_cannot_be_kept(self):
        project = self.patched("encoding.HMI", header={13: 0xEE})
        with self.assertRaises(NxwrightError) as raised:
            extract(project, self.target("encoding"), continue_with_unknown=True)
        self.assertNotIsInstance(raised.exception, UnknownContentError)
        self.assertIn("character encoding", str(raised.exception))
        self.assertFalse(self.target("encoding").exists())

    def test_an_unknown_attribute_cannot_be_kept(self):
        project = self.edited("attribute.HMI", with_new_attribute)
        with self.assertRaises(NxwrightError) as raised:
            extract(project, self.target("attribute"), continue_with_unknown=True)
        message = str(raised.exception)
        self.assertIn("newattr", message)
        self.assertIn("newer Nextion Editor", message)
        self.assertFalse(self.target("attribute").exists())

    def utf8_project(self) -> Path:
        """Returns a project of a model nxwright knows, in utf-8, whose text
        holds a character beyond ASCII."""
        source = self.folder / "utf8-app"
        if not source.exists():
            new_source_folder(source, DeviceSettings(model_named("NX4832T035"), 0, "utf-8"),
                              "nextion")
            page = source / "pages" / "page0.page.toml"
            page.write_text(page.read_text(encoding="utf-8") + UTF8_TEXT, encoding="utf-8")
            build(source, self.folder / "utf8.HMI")
        return self.folder / "utf8.HMI"

    def test_an_unknown_model_keeps_the_project_s_encoding(self):
        # Byte 13, the encoding, does not depend on the model, so the texts
        # are read in the project's own encoding, not iso-8859-1.
        project = self.patched("model.HMI", header={16: 0xEE, 17: 0xEE},
                               base=self.utf8_project())
        with self.assertRaises(UnknownContentError) as raised:
            extract(project, self.target("model"))
        self.assertIn("screen model", str(raised.exception))
        extract(project, self.target("model"), continue_with_unknown=True)
        page = (self.target("model") / "pages" / "page0.page.toml").read_text(encoding="utf-8")
        self.assertIn('txt = "é"', page)
        # app.toml holds no screen settings, as documented: the encoding
        # alone is not a setting app.toml may give.
        app = (self.target("model") / "app.toml").read_text(encoding="utf-8")
        self.assertNotIn("screen", app)

    def test_an_unknown_model_names_the_screen_settings_it_removes(self):
        target = self.target("model-update")
        extract(self.utf8_project(), target)
        self.assertIn("screen", (target / "app.toml").read_text(encoding="utf-8"))
        project = self.patched("model-update.HMI", header={16: 0xEE, 17: 0xEE},
                               base=self.utf8_project())
        # The question says so before anything is written.
        with self.assertRaises(UnknownContentError) as raised:
            extract(project, target)
        self.assertIn("removes the screen settings", str(raised.exception))
        messages = extract(project, target, continue_with_unknown=True)
        self.assertTrue(any("screen settings" in message and "removed" in message
                            for message in messages), messages)

    def test_an_unknown_type_and_event_are_kept_exactly_with_a_note(self):
        # Object 1 of the first page, a text, given a type nxwright does not
        # know, and an event of a name it has no list to tell from another.
        def edit(text: str) -> str:
            head, start, rest = text.partition("object 1 ")
            rest = rest.replace("\n  type = 116\n", "\n  type = 200\n", 1)
            rest = rest.replace("\n  event up\n", "\n  event up\n  event mystery\n", 1)
            return head + start + rest
        project = self.edited("type.HMI", edit)
        messages = extract(project, self.target("type"))
        self.assertEqual(messages, ["a component type nxwright does not know (block 0.pa, "
                                    "object 1), which the source folder keeps exactly"])
        build(self.target("type"), self.folder / "type-again.HMI")
        page = HmiContainer.from_file(project).blocks["0.pa"]
        again = HmiContainer.from_file(self.folder / "type-again.HMI").blocks["0.pa"]
        self.assertEqual(again, page)

    def test_a_picture_header_and_a_manifest_entry_of_another_kind_may_be_lost(self):
        blocks = HmiContainer.from_file(self.demo).blocks
        header = bytearray(blocks["0.is"])
        header[1] = 0x0b
        project = self.patched("picture.HMI", blocks={"0.is": bytes(header)})
        with self.assertRaises(UnknownContentError) as raised:
            extract(project, self.target("picture"))
        self.assertIn("(block 0.is)", str(raised.exception))
        # One more entry in the manifest's list, of a kind nxwright does not
        # know, and the list's count one more.
        main = bytearray(blocks["main.HMI"])
        count = int.from_bytes(main[28:32], "little")
        main[28:32] = (count + 1).to_bytes(4, "little")
        main += b"xx".ljust(8, b"\0") + b"0.xx".ljust(8, b"\0")
        project = self.patched("entry.HMI", blocks={"main.HMI": bytes(main)})
        with self.assertRaises(UnknownContentError) as raised:
            extract(project, self.target("entry"))
        self.assertIn("(manifest entry %d)" % count, str(raised.exception))

    def test_a_refused_extract_leaves_an_existing_folder_as_it_was(self):
        target = self.target("existing")
        extract(self.demo, target)
        before = {path: path.read_bytes() for path in target.rglob("*") if path.is_file()}
        with self.assertRaises(UnknownContentError):
            extract(self.patched("existing.HMI", blocks={"2.ib": b"?"}), target)
        after = {path: path.read_bytes() for path in target.rglob("*") if path.is_file()}
        self.assertEqual(after, before)

    def test_a_project_without_unknown_content_extracts_as_before(self):
        target = self.target("plain")
        self.assertEqual(extract(self.demo, target), [])


class ExtractCommandTest(PatchedDemoTestCase):
    """nxwright extract with such a project: the question, its option, the
    exit code of its own, and --list-unknown."""

    def run_extract(self, *arguments, ask=None) -> tuple:
        """Runs nxwright extract with `arguments`, `ask` answering at the
        terminal, or nobody at all. Returns (the exit code, what it printed,
        what it wrote as errors)."""
        printed, said = io.StringIO(), io.StringIO()
        with mock.patch("nxwright.cli._terminal_asker", return_value=ask), \
                redirect_stdout(printed), redirect_stderr(said):
            code = main(["extract"] + [str(argument) for argument in arguments])
        return code, printed.getvalue(), said.getvalue()

    def test_with_nobody_to_ask_it_stops_with_its_own_exit_code(self):
        project = self.patched("command.HMI", blocks={"2.ib": b"?"})
        code, _, said = self.run_extract(project, self.target("command"))
        self.assertEqual(code, NO_ANSWER_EXIT_CODE)
        self.assertIn("block 2.ib", said)
        self.assertIn("--continue-with-unknown", said)
        self.assertFalse(self.target("command").exists())

    def test_the_option_goes_on(self):
        project = self.patched("option.HMI", blocks={"2.ib": b"?"})
        code, _, said = self.run_extract(project, self.target("option"),
                                         "--continue-with-unknown")
        self.assertEqual(code, 0)
        self.assertIn("nxwright extract: warning: went on past a block", said)
        self.assertTrue((self.target("option") / "app.toml").is_file())

    def test_the_answer_at_the_terminal(self):
        project = self.patched("asked.HMI", blocks={"2.ib": b"?"})
        ask, questions = answering("n")
        code, _, said = self.run_extract(project, self.target("asked-no"), ask=ask)
        self.assertEqual(code, 1)
        self.assertEqual(questions, ["Go on anyway? [y/N]: "])
        self.assertIn("nothing was written", said)
        self.assertFalse(self.target("asked-no").exists())
        ask, _ = answering("y")
        code, _, _ = self.run_extract(project, self.target("asked-yes"), ask=ask)
        self.assertEqual(code, 0)
        self.assertTrue((self.target("asked-yes") / "app.toml").is_file())

    def run_command(self, *arguments, ask=None) -> tuple:
        """Runs nxwright with `arguments`, as run_extract does."""
        printed, said = io.StringIO(), io.StringIO()
        with mock.patch("nxwright.cli._terminal_asker", return_value=ask), \
                redirect_stdout(printed), redirect_stderr(said):
            code = main([str(argument) for argument in arguments])
        return code, printed.getvalue(), said.getvalue()

    def test_dump_warns_and_never_asks(self):
        project = self.patched("dumped.HMI", blocks={"2.ib": b"?"}, header={14: 0x50})
        code, _, said = self.run_command("dump", project, self.folder / "dumped")
        self.assertEqual(code, 0)
        self.assertIn("nxwright dump: warning: a block of a kind nxwright does not handle "
                      "(block 2.ib)", said)
        self.assertIn("(manifest header, byte 14)", said)
        self.assertIn("nxwright report", said.splitlines()[-1])
        self.assertTrue((self.folder / "dumped" / "project.txt").is_file())

    def test_import_asks_about_what_its_dump_shows(self):
        # The dump keeps the manifest header, so import finds its byte too.
        project = self.patched("imported.HMI", header={14: 0x50})
        dump = self.folder / "imported-dump"
        self.run_command("dump", project, dump)
        code, _, said = self.run_command("import", dump, self.target("imported"))
        self.assertEqual(code, NO_ANSWER_EXIT_CODE)
        self.assertIn("(manifest header, byte 14)", said)
        self.assertFalse(self.target("imported").exists())
        code, _, _ = self.run_command("import", dump, self.target("imported"),
                                      "--continue-with-unknown")
        self.assertEqual(code, 0)
        self.assertTrue((self.target("imported") / "app.toml").is_file())

    def test_list_unknown_prints_each_as_json_and_writes_nothing(self):
        project = self.patched("listed.HMI", blocks={"2.ib": b"?"}, header={14: 0x50})
        code, printed, _ = self.run_extract("--list-unknown", project)
        self.assertEqual(code, 0)
        lines = [json.loads(line) for line in printed.splitlines()]
        self.assertEqual([(line["where"], line["sort"]) for line in lines],
                         [("block 2.ib", "may be lost"), ("manifest header, byte 14",
                                                          "may be lost")])
        self.assertEqual(lines[0]["bytes"], "3f")
        self.assertFalse(any(self.folder.glob("source-listed*")))


if __name__ == "__main__":
    unittest.main()
