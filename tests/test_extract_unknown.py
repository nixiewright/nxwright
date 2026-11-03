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
from nxwright.project.page_text import page_to_text
from nxwright.project.page_block import Attribute, Event, parse_page
from nxwright.project.project_writer import ProjectWriter
from nxwright.project.screen_models import model_named
from nxwright.source.project_files import build, extract
from nxwright.source.source_folder import new_source_folder
from nxwright.source.unknown_content import (CANNOT_BE_KEPT, UnknownContentError,
                                             unknown_in_project_file)
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
        project = self.patched("block.HMI", blocks={"2.xb": b"?"})
        with self.assertRaises(UnknownContentError) as raised:
            extract(project, self.target("block"))
        self.assertIn("block 2.xb", str(raised.exception))
        self.assertIn("nxwright report", str(raised.exception))
        self.assertFalse(self.target("block").exists())
        messages = extract(project, self.target("block"), continue_with_unknown=True)
        self.assertTrue(any("block 2.xb" in message for message in messages))
        build(self.target("block"), self.folder / "block-again.HMI")
        self.assertNotIn("2.xb", HmiContainer.from_file(self.folder / "block-again.HMI").blocks)

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

    def test_a_page_whose_text_form_differs_asks_first(self):
        # The text form is made to lose the page header's byte 41, which a
        # real page's text form never does.
        real = page_to_text

        def losing(page):
            return real(page).replace("header_40 = 0144", "header_40 = 0145", 1)
        with mock.patch("nxwright.project.dumper.page_to_text", side_effect=losing):
            with self.assertRaises(UnknownContentError) as raised:
                extract(self.demo, self.target("text"))
            self.assertIn("a page whose text form does not give back its bytes",
                          str(raised.exception))
            self.assertIn("byte 41", str(raised.exception))
            self.assertFalse(self.target("text").exists())
            extract(self.demo, self.target("text"), continue_with_unknown=True)
        self.assertTrue((self.target("text") / "app.toml").exists())

    def test_a_page_that_has_no_text_form_is_listed_not_raised(self):
        # So that `nxwright report` and `--list-unknown` still list the rest.
        with mock.patch("nxwright.project.dumper.page_to_text",
                        side_effect=NxwrightError("no text form")):
            found = unknown_in_project_file(self.demo)
        self.assertEqual({(each.what, each.sort) for each in found},
                         {("a page nxwright cannot write as text", CANNOT_BE_KEPT)})

    def test_the_nspanel_s_header_form_extracts_with_no_question(self):
        # 32 of the 38 pages of a project for an NSPanel screen have it.
        blocks = HmiContainer.from_file(self.demo).blocks
        page = bytearray(blocks["0.pa"])
        page[40:44] = bytes.fromhex("01440100")
        project = self.patched("nspanel.HMI", blocks={"0.pa": bytes(page)})
        self.assertEqual(extract(project, self.target("nspanel")), [])

    def test_an_unknown_encoding_cannot_be_kept(self):
        project = self.patched("encoding.HMI", header={13: 0xEE})
        with self.assertRaises(NxwrightError) as raised:
            extract(project, self.target("encoding"), continue_with_unknown=True)
        self.assertNotIsInstance(raised.exception, UnknownContentError)
        self.assertIn("character encoding", str(raised.exception))
        self.assertFalse(self.target("encoding").exists())

    def test_an_unknown_attribute_is_kept_as_its_bytes(self):
        # The page's table lists every attribute, the unknown one as its
        # stored bytes, in place; the build writes the same page back.
        project = self.edited("attribute.HMI", with_new_attribute)
        messages = extract(project, self.target("attribute"))
        self.assertEqual(len(messages), 2, messages)
        self.assertIn("attribute newattr", messages[0])
        self.assertIn("nxwright report", messages[1])
        page = (self.target("attribute") / "pages" / "home.page.toml").read_text(encoding="utf-8")
        self.assertIn('vscope = 0\nnewattr = { bytes = "01" }\n', page)
        self.assertIn("defaults = false", page.split("[[component]]")[0])
        self.assert_same_page_again(project, "attribute")

    def test_a_known_attribute_at_another_width_is_kept_as_its_bytes(self):
        def edit(text: str) -> str:
            head, start, rest = text.partition("object 0 ")
            return head + start + rest.replace("\n  vscope = 0\n", "\n  vscope:u16 = 0\n", 1)
        project = self.edited("width.HMI", edit)
        messages = extract(project, self.target("width"))
        self.assertIn("attribute vscope", messages[0])
        page = (self.target("width") / "pages" / "home.page.toml").read_text(encoding="utf-8")
        self.assertIn('vscope = { bytes = "0000" }\n', page)
        self.assert_same_page_again(project, "width")

    def test_a_new_type_with_a_new_attribute_is_kept(self):
        def edit(text: str) -> str:
            text = with_new_attribute(text)
            head, start, rest = text.partition("object 1 ")
            return head + start + rest.replace("\n  type = 116\n", "\n  type = 200\n", 1)
        project = self.edited("new-type.HMI", edit)
        extract(project, self.target("new-type"))
        self.assert_same_page_again(project, "new-type")

    def test_a_raw_value_that_is_not_hexadecimal_is_refused(self):
        target = self.target("bad-raw")
        extract(self.edited("bad-raw.HMI", with_new_attribute), target)
        page = target / "pages" / "home.page.toml"
        page.write_text(page.read_text(encoding="utf-8").replace(
            'newattr = { bytes = "01" }', 'newattr = { bytes = "zz" }'), encoding="utf-8")
        with self.assertRaises(NxwrightError) as raised:
            build(target, self.folder / "bad-raw-again.HMI")
        self.assertIn("newattr", str(raised.exception))
        self.assertIn("hexadecimal", str(raised.exception))

    def assert_same_page_again(self, project: Path, name: str):
        """Asserts that the source folder extracted from `project`, under
        `name`, builds into a project whose first page is the same block."""
        again = self.folder / ("%s-again.HMI" % name)
        build(self.target(name), again)
        self.assertEqual(HmiContainer.from_file(again).blocks["0.pa"],
                         HmiContainer.from_file(project).blocks["0.pa"])

    def utf8_project(self) -> Path:
        """Returns a project of a model nxwright knows, in utf-8, whose text
        contains a character beyond ASCII."""
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
        # app.toml has no screen settings, as documented: the encoding
        # alone is not a setting app.toml may give.
        app = (self.target("model") / "app.toml").read_text(encoding="utf-8")
        self.assertNotIn("screen", app)

    def test_an_unknown_model_warns_that_its_screen_settings_will_be_removed(self):
        target = self.target("model-update")
        extract(self.utf8_project(), target)
        self.assertIn("screen", (target / "app.toml").read_text(encoding="utf-8"))
        project = self.patched("model-update.HMI", header={16: 0xEE, 17: 0xEE},
                               base=self.utf8_project())
        # The error, before anything is written, warns that they will be removed.
        with self.assertRaises(UnknownContentError) as raised:
            extract(project, target)
        self.assertIn("will remove the screen settings", str(raised.exception))
        messages = extract(project, target, continue_with_unknown=True)
        self.assertTrue(any("screen settings" in message and "removed" in message
                            for message in messages), messages)

    def test_an_unknown_type_and_event_are_kept_exactly_with_a_note(self):
        # Object 1 of the first page, a text, given a type nxwright does not
        # know, and an event whose name nxwright does not know.
        def edit(text: str) -> str:
            head, start, rest = text.partition("object 1 ")
            rest = rest.replace("\n  type = 116\n", "\n  type = 200\n", 1)
            rest = rest.replace("\n  event up\n", "\n  event up\n  event mystery\n", 1)
            return head + start + rest
        project = self.edited("type.HMI", edit)
        messages = extract(project, self.target("type"))
        self.assertEqual(messages[0], "a component type nxwright does not know (block 0.pa, "
                                      "object 1), which the source folder keeps exactly")
        # Kept, but to be supported properly later: the report is to send.
        self.assertIn("nxwright report", messages[1])
        self.assertEqual(len(messages), 2)
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
            extract(self.patched("existing.HMI", blocks={"2.xb": b"?"}), target)
        after = {path: path.read_bytes() for path in target.rglob("*") if path.is_file()}
        self.assertEqual(after, before)

    def test_a_project_without_unknown_content_extracts_as_before(self):
        target = self.target("plain")
        self.assertEqual(extract(self.demo, target), [])


def in_object_0(edit):
    """Returns an edit of a page's dump text that applies `edit` to its
    object 0, the page itself, alone."""
    def edited(text: str) -> str:
        head, start, rest = text.partition("object 0 ")
        body, end, tail = rest.partition("\nobject ")
        return head + start + edit(body) + end + tail
    return edited


def with_count(body: str, more: int) -> str:
    """Returns an object's dump text `body` with its count of attributes
    `more` higher."""
    count = int(re.search(r"marker att-(\d+)", body).group(1))
    return body.replace("marker att-%d" % count, "marker att-%d" % (count + more), 1)


class ObjectsAndEventsTest(PatchedDemoTestCase):
    """What a page's objects contain that the page files cannot write as
    they are: each was refused before, and is extracted now."""

    def round_trip(self, name: str, project: Path) -> tuple:
        """Extracts `project` with no question, builds it again, and returns
        (the notes, the page file's text, the first page's object 0 as built,
        and as the project had it)."""
        notes = extract(project, self.target(name))
        built = self.folder / (name + "-again.HMI")
        build(self.target(name), built)
        page_file = (self.target(name) / "pages" / "home.page.toml").read_text(encoding="utf-8")
        def object_0(path: Path):
            return parse_page(HmiContainer.from_file(path).blocks["0.pa"]).objects[0]
        return notes, page_file, object_0(built), object_0(project)

    def test_records_out_of_their_usual_order_are_written_in_order(self):
        project = self.edited("order.HMI", in_object_0(lambda body: body.replace(
            "  event loadend\n", "", 1).replace("  marker att-28\n",
                                                 "  marker att-28\n  event loadend\n", 1)))
        notes, _, built, _ = self.round_trip("order", project)
        self.assertTrue(any("records out of their usual order" in note
                            and "writes as nxwright knows it" in note for note in notes), notes)
        kinds = [type(item).__name__ for item in built.items]
        self.assertEqual(kinds, sorted(kinds, key=["Marker", "Attribute", "Event"].index))

    def test_an_attribute_given_twice_asks_first_and_keeps_the_last(self):
        project = self.edited("twice.HMI", in_object_0(lambda body: with_count(body, 1).replace(
            "  aph = 127\n", "  aph = 127\n  aph = 100\n", 1)))
        with self.assertRaisesRegex(UnknownContentError, "given twice"):
            extract(project, self.target("twice"))
        extract(project, self.target("twice"), continue_with_unknown=True)
        self.assertIn("aph = 100\n", (self.target("twice") / "pages" / "home.page.toml")
                      .read_text(encoding="utf-8"))

    def test_an_event_that_nx_files_cannot_contain_is_kept_as_its_lines(self):
        # A line of code with a control character. An event whose name is not
        # lowercase letters cannot be one: page_block.py reads such a record
        # as records of other kinds.
        project = self.edited("control.HMI", in_object_0(lambda body: body.replace(
            "  event load\n", "  event load\n    raw 610d62\n", 1)))
        notes, page_file, built, original = self.round_trip("control", project)
        self.assertTrue(any("keeps exactly" in note for note in notes), notes)
        self.assertIn("kept_events = { ", page_file)
        self.assertEqual([item for item in built.items if isinstance(item, Event)],
                         [item for item in original.items if isinstance(item, Event)])

    def test_an_attribute_named_like_a_page_file_key_is_kept_as_its_bytes(self):
        project = self.edited("key.HMI", in_object_0(lambda body: with_count(body, 1).replace(
            "\n  vscope = 0\n", "\n  vscope = 0\n  events:u8 = 5\n", 1)))
        notes, page_file, built, original = self.round_trip("key", project)
        self.assertTrue(any("keeps exactly" in note for note in notes), notes)
        self.assertIn('kept_attributes = { events = { bytes = "05" } }', page_file)
        self.assertEqual([item for item in built.items if isinstance(item, Attribute)],
                         [item for item in original.items if isinstance(item, Attribute)])

    def test_a_text_not_valid_in_the_encoding_is_kept_as_its_bytes(self):
        # In utf-8, a lone e9 is not text.
        edited = self.edited("text.HMI", lambda text: text.replace(
            'txt = "Living room"', 'txt = "Living r\\xe9om"', 1))
        project = self.patched("text-utf8.HMI", header={13: 24}, base=edited)
        notes, _, _, _ = self.round_trip("text", project)
        self.assertTrue(any("keeps exactly" in note for note in notes), notes)
        title = (self.target("text") / "pages" / "home.page.toml").read_text(encoding="utf-8")
        self.assertIn('txt = { bytes = "4c6976696e672072e96f6d" }', title)
        rebuilt = HmiContainer.from_file(self.folder / "text-again.HMI").blocks["0.pa"]
        self.assertIn(b"Living r\xe9om", rebuilt)

    def test_a_page_object_not_named_after_its_page_is_named_so(self):
        project = self.edited("named.HMI", in_object_0(lambda body: body.replace(
            'objname = "home"', 'objname = "house"', 1).replace("home\n", "house\n", 1)))
        notes, _, built, _ = self.round_trip("named", project)
        self.assertTrue(any("not named after its page" in note for note in notes), notes)
        self.assertEqual(built.attribute("objname"), b"home")

    def test_a_record_of_another_kind_asks_first(self):
        project = self.edited("record.HMI", in_object_0(lambda body: body.replace(
            "  marker att-28\n", "  marker att-28\n  raw 0102\n", 1)))
        with self.assertRaisesRegex(UnknownContentError, "a record of a kind"):
            extract(project, self.target("record"))
        extract(project, self.target("record"), continue_with_unknown=True)
        self.assertTrue((self.target("record") / "app.toml").exists())


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
        project = self.patched("command.HMI", blocks={"2.xb": b"?"})
        code, _, said = self.run_extract(project, self.target("command"))
        self.assertEqual(code, NO_ANSWER_EXIT_CODE)
        self.assertIn("block 2.xb", said)
        self.assertIn("--continue-with-unknown", said)
        self.assertFalse(self.target("command").exists())

    def test_the_option_goes_on(self):
        project = self.patched("option.HMI", blocks={"2.xb": b"?"})
        code, _, said = self.run_extract(project, self.target("option"),
                                         "--continue-with-unknown")
        self.assertEqual(code, 0)
        self.assertIn("nxwright extract: warning: went on past a block", said)
        self.assertIn("`nxwright report` writes a report on %s" % project, said)
        self.assertTrue((self.target("option") / "app.toml").is_file())

    def test_the_answer_at_the_terminal(self):
        project = self.patched("asked.HMI", blocks={"2.xb": b"?"})
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
        project = self.patched("dumped.HMI", blocks={"2.xb": b"?"}, header={14: 0x50})
        code, _, said = self.run_command("dump", project, self.folder / "dumped")
        self.assertEqual(code, 0)
        self.assertIn("nxwright dump: warning: a block of a kind nxwright does not handle "
                      "(block 2.xb)", said)
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
        project = self.patched("listed.HMI", blocks={"2.xb": b"?"}, header={14: 0x50})
        code, printed, _ = self.run_extract("--list-unknown", project)
        self.assertEqual(code, 0)
        lines = [json.loads(line) for line in printed.splitlines()]
        self.assertEqual([(line["where"], line["sort"]) for line in lines],
                         [("block 2.xb", "may be lost"), ("manifest header, byte 14",
                                                          "may be lost")])
        self.assertEqual((lines[0]["size"], lines[0]["first_bytes"]), (1, "3f"))
        self.assertFalse(any(self.folder.glob("source-listed*")))

    def test_list_unknown_gives_a_large_content_s_first_bytes_alone(self):
        # As the report does, so that the list stays short whatever the
        # content's size: the extension reads it into a buffer of 1 MB.
        project = self.patched("large.HMI", blocks={"2.xb": bytes(range(256)) * 4096})
        code, printed, _ = self.run_extract("--list-unknown", project)
        self.assertEqual(code, 0)
        line = json.loads(printed.splitlines()[0])
        self.assertEqual((line["size"], line["first_bytes"]),
                         (1048576, bytes(range(16)).hex()))
        self.assertLess(len(printed), 1000)


if __name__ == "__main__":
    unittest.main()
