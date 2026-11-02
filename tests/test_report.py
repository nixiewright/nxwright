"""nxwright report: the things in a project that nxwright does not know, for its
maintainers to look into, with none of the project's own content
(source/report.py)."""
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import unittest

from nxwright.cli import main
from nxwright.project.container import HmiContainer
from nxwright.project.dumper import ProjectDumper
from nxwright.project.page_block import Attribute, Event
from nxwright.project.page_text import page_from_text
from nxwright.source.report import report_text
from tests.test_extract_unknown import PatchedDemoTestCase, with_new_attribute


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
