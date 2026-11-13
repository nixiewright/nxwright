"""nxwright report: the things in a project that nxwright does not know, for its
maintainers to look into, with none of the project's own content
(source/report.py)."""
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import struct
import unittest
from unittest import mock

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.project.container import HmiContainer
from nxwright.project.dumper import ProjectDumper
from nxwright.project.page_block import Attribute, Event
from nxwright.project.page_text import page_from_text
from nxwright.source.report import comparison_lines, report_text
from tests.test_extract_unknown import PatchedDemoTestCase, with_new_attribute


def rebuild_part(text: str) -> str:
    """Returns the part of the report `text` on what a rebuild changes."""
    start = text.index("## What a rebuild changes")
    return text[start:text.index("## The project file's blocks")]


class ComparisonLinesTest(unittest.TestCase):
    """The rebuild's part of the report, from the blocks of both sides."""

    def test_each_block_that_differs_has_its_sizes_and_its_places(self):
        page = bytes(60)
        blocks = {"main.HMI": bytes(96), "0.pa": page, "1.pa": page, "3.i": bytes(40),
                  "4.i": b"gone", "5.is": b"same"}
        # The first page differs in its stamp and version bytes alone. The
        # second differs in byte 50 too. The picture's copy is longer.
        rebuilt = {"main.HMI": bytes(96), "5.is": b"same", "9.i": b"added",
                   "0.pa": b"\1\1\1\1" + bytes(37) + b"\x44\x02\x03" + bytes(16),
                   "1.pa": b"\1" + bytes(40) + b"\x44" + bytes(8) + b"\7" + bytes(9),
                   "3.i": bytes(20) + b"\1\1" + bytes(18) + b"tail"}
        lines = comparison_lines(blocks, rebuilt)
        self.assertEqual(lines[2:6], ["Of the project file's 6 blocks:", "",
                                      "- The same in the rebuild: 2",
                                      "- Different in the stamp and version bytes alone: 1"])
        self.assertIn("- Different in other bytes, or not in the rebuild: 3", lines)
        self.assertEqual(lines[-5:], [
            "| 0.pa | 60 | 60 | 0 to 3, 41 to 43 | none |",
            "| 1.pa | 60 | 60 | 0, 41 | 1 byte: 50 |",
            "| 3.i | 40 | 44 | none | 6 bytes: 20 to 21, 40 to 43 |",
            "| 4.i | 4 | not in the rebuild | | |",
            "| 9.i | not in the project file | 5 | | |"])

    def test_a_block_of_another_kind_has_no_stamp_or_version_bytes(self):
        # Bytes 0 to 3 of a picture's copy are not a stamp.
        lines = comparison_lines({"3.i": bytes(8)}, {"3.i": b"\1\1\1\1" + bytes(4)})
        self.assertEqual(lines[-1], "| 3.i | 8 | 8 | none | 4 bytes: 0 to 3 |")

    def test_only_the_first_ranges_of_a_block_are_given(self):
        changed = bytes(place % 2 for place in range(40))
        lines = comparison_lines({"3.i": bytes(40)}, {"3.i": changed})
        self.assertEqual(lines[-1], "| 3.i | 40 | 40 | none | 20 bytes: 1, 3, 5, 7, 9, 11, 13, "
                                    "15, 17, 19, 21, 23, and 8 more ranges |")

    def test_the_bytes_that_differ_are_never_given(self):
        # Neither side's bytes, in hexadecimal or as text.
        blocks = {"0.pa": bytes(44) + b"Living room" + bytes(5)}
        rebuilt = {"0.pa": bytes(44) + b"\xde\xad\xbe\xef\xde\xad\xbe\xef\xde\xad\xbe"
                   + bytes(5)}
        text = "\n".join(comparison_lines(blocks, rebuilt))
        self.assertIn("| 0.pa | 60 | 60 | none | 11 bytes: 44 to 54 |", text)
        for private in ("Living room", b"Living room".hex(), b"Living room".hex(" "),
                        "de ad be ef", "deadbeef"):
            self.assertNotIn(private, text)

    def test_blocks_that_are_all_the_same_have_no_table(self):
        lines = comparison_lines({"0.pa": b"page"}, {"0.pa": b"page"})
        self.assertEqual(lines, ["nxwright extracted the project into a temporary folder, and "
                                 "built that folder again. Every block of the project file, "
                                 "1 in all, is the same in this rebuild."])


class ReportTest(PatchedDemoTestCase):

    def test_it_names_each_unknown_content_with_its_place_and_bytes(self):
        project = self.patched("report.HMI", blocks={"2.xb": b"secret?"}, header={14: 0x50})
        text = report_text(project)
        # The column of "kept exactly", "may be lost", or "cannot be kept".
        self.assertIn("| What | Where | Kept by nxwright | Bytes | First bytes |", text)
        self.assertIn("| a block of a kind nxwright does not handle | block 2.xb | may be lost "
                      "| 7 | 73 65 63 72 65 74 3f |", text)
        self.assertIn("| manifest header, byte 14 | may be lost | 1 | 50 |", text)

    def test_an_attribute_is_named_with_its_component_s_type(self):
        text = report_text(self.edited("report-attribute.HMI", with_new_attribute))
        self.assertIn("newattr, on a page", text)
        self.assertIn("block 0.pa, object 0, attribute newattr", text)

    def test_a_page_nxwright_cannot_read_is_reported(self):
        # The page's header size, 60, is 3c 00 00 00 at bytes 8 to 11.
        text = report_text(self.with_unreadable_page("report-layout.HMI"))
        self.assertRegex(text, r"\| a page nxwright cannot read \| block 0\.pa \| "
                               r"cannot be kept \| 16 \| (\w\w ){8}3c 00 00 00 ")

    def test_a_project_without_unknown_content_says_so(self):
        self.assertIn("nxwright knows everything in this project.", report_text(self.demo))

    def test_it_leaves_out_the_project_s_own_content(self):
        # The demo's page and component names, its texts, and its code, as
        # its dump gives them; and its blocks' names and sizes are there.
        project = self.patched("private.HMI", blocks={"2.xb": b"?"})
        text = report_text(project)
        dump = self.folder / "private-dump"
        ProjectDumper(self.demo, dump).dump()
        private = set()
        for path in (dump / "pages").glob("*.txt"):
            page = page_from_text(path.read_text(encoding="utf-8"))
            for page_object in page.objects:
                for item in page_object.items:
                    if isinstance(item, Attribute) and item.name in ("objname", "txt") \
                            and len(item.value) >= 4:
                        private.add(item.value.decode("latin-1"))
                    if isinstance(item, Event):
                        private.update(line.decode("latin-1").strip() for line in item.lines
                                       if len(line.strip()) >= 4)
        self.assertIn("Living room", private)
        found = sorted(each for each in private if each in text)
        self.assertEqual(found, [])
        for name, block in HmiContainer.from_file(project).blocks.items():
            self.assertIn("| %s | %d |" % (name, len(block)), text)

    def test_the_password_hash_is_blanked(self):
        project = self.patched("password.HMI", header={20: 0xA1, 21: 0xB2, 22: 0xC3, 23: 0xD4})
        text = report_text(project)
        self.assertNotIn("a1 b2 c3 d4", text)
        self.assertIn("-- -- -- --", text)
        self.assertIn("`--` marks the bytes of the password's hash, which are left out.", text)
        self.assertIn("Password: yes", text)
        # Whether there is one is said of a model nxwright does not know too.
        unknown = self.patched("password-model.HMI", header={20: 0xA1, 16: 0xEE, 17: 0xEE})
        self.assertIn("Password: yes", report_text(unknown))
        self.assertIn("Password: no", report_text(self.demo))

    def test_it_gives_the_editor_s_version_from_the_headers(self):
        # The manifest header and the first page as the Nextion Editor
        # 1.61.2 writes them. The other four pages keep the build's form.
        page = bytearray(HmiContainer.from_file(self.demo).blocks["0.pa"])
        page[40:44] = bytes.fromhex("013d0200")
        project = self.patched("version.HMI", blocks={"0.pa": bytes(page)},
                               header={9: 0x3d, 36: 2, 65: 0})
        text = report_text(project)
        self.assertIn("- The manifest header: 1.61.2 (bytes 9, 36, and 65 are `3d 02 00`)", text)
        self.assertIn("- 1 page: 1.61.2 (page header bytes 40 to 43 are `01 3d 02 00`)", text)
        self.assertIn("- 4 pages: 1.68.2 (page header bytes 40 to 43 are `01 44 02 03`)", text)
        # The blank for the version stays, for the user to confirm it.
        self.assertIn("- The Nextion Editor: _fill in the version from its Help menu_", text)

    def test_a_version_nxwright_was_not_checked_with_is_marked(self):
        text = report_text(self.patched("newer.HMI", header={9: 69, 36: 1}))
        self.assertIn("- The manifest header: 1.69.1, if these bytes still give the version "
                      "(bytes 9, 36, and 65 are `45 01 03`)", text)

    def test_a_manifest_header_too_short_for_a_version_says_so(self):
        main = bytearray(HmiContainer.from_file(self.demo).blocks["main.HMI"])
        shorter = main[:60] + main[96:]
        struct.pack_into("<I", shorter, 4, 60)
        struct.pack_into("<I", shorter, 24, 60)
        text = report_text(self.patched("short.HMI", blocks={"main.HMI": bytes(shorter)}))
        self.assertIn("- The manifest header is too short to give a version.", text)

    def test_a_project_that_comes_back_unchanged_says_so(self):
        count = len(HmiContainer.from_file(self.demo).blocks)
        self.assertIn("Every block of the project file, %d in all, is the same in this rebuild."
                      % count, report_text(self.demo))

    def test_the_rebuild_s_part_lists_each_block_that_differs(self):
        # The build leaves out the block of another kind, and writes its own
        # values in bytes 9, 14, and 65 of the manifest header. The patched
        # project keeps the demo's stamp, which the rebuild has too.
        project = self.patched("rebuild.HMI", blocks={"2.xb": b"secret?"},
                               header={9: 0x3d, 14: 0x50, 65: 0})
        blocks = HmiContainer.from_file(project).blocks
        text = rebuild_part(report_text(project))
        self.assertIn("Of the project file's %d blocks:\n\n- The same in the rebuild: %d\n"
                      "- Different in the stamp and version bytes alone: 0\n"
                      "- Different in other bytes, or not in the rebuild: 2\n"
                      % (len(blocks), len(blocks) - 2), text)
        self.assertIn("| 2.xb | 7 | not in the rebuild | | |", text)
        size = len(blocks["main.HMI"])
        self.assertIn("| main.HMI | %d | %d | 9, 65 | 1 byte: 14 |" % (size, size), text)

    def test_a_page_nxwright_cannot_read_is_counted_and_has_no_rebuild(self):
        text = report_text(self.with_unreadable_page("unreadable.HMI"))
        self.assertIn("- 1 page that nxwright cannot read", text)
        self.assertIn("nxwright could not extract this project, so there is no rebuild to "
                      "compare. Run `nxwright extract` to see the reason.", rebuild_part(text))

    def test_a_refusal_s_own_words_are_left_out(self):
        # An error's own text may contain the name of a page or of a component.
        refusal = NxwrightError("the page secretname cannot be written")
        with mock.patch("nxwright.source.report.extract", side_effect=refusal):
            text = report_text(self.demo)
        self.assertIn("nxwright could not extract this project", text)
        self.assertNotIn("secretname", text)
        with mock.patch("nxwright.source.report.build", side_effect=refusal):
            text = report_text(self.demo)
        self.assertIn("nxwright extracted this project, but could not build the folder again, "
                      "so there is no rebuild to compare. Run `nxwright extract`, then "
                      "`nxwright build`, to see the reason.", text)
        self.assertNotIn("secretname", text)

    def test_the_command_writes_a_new_file(self):
        output = self.folder / "written.md"
        printed = io.StringIO()
        with redirect_stdout(printed), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["report", str(self.demo), str(output)]), 0)
        self.assertTrue(output.read_text(encoding="utf-8").startswith("# nxwright report"))
        said = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(said):
            self.assertEqual(main(["report", str(self.demo), str(output)]), 1)
        self.assertIn("exists", said.getvalue())


if __name__ == "__main__":
    unittest.main()
