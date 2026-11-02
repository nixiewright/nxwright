"""The comparisons of the round trip (tools/editor/release_pass.py): of two
folders file by file, of two projects' live blocks, and of the differences
the new Nextion Editor alone makes. They run on small inputs written for
the tests, and need neither the Nextion Editor nor pywinauto."""
from pathlib import Path
import tempfile
import unittest

from tools.editor import release_pass
from tools.editor.release_pass import Difference


class ByteRunsTest(unittest.TestCase):

    def test_neighbouring_bytes_that_differ_make_one_run(self):
        self.assertEqual(release_pass.differing_runs(b"abcdef", b"aXYdeZ"),
                         ((1, b"bc", b"XY"), (5, b"f", b"Z")))

    def test_a_longer_side_ends_in_a_run_of_its_own(self):
        self.assertEqual(release_pass.differing_runs(b"abc", b"abcde"), ((3, b"", b"de"),))
        self.assertEqual(release_pass.differing_runs(b"abcd", b"ab"), ((2, b"cd", b""),))

    def test_the_same_bytes_have_no_run(self):
        self.assertEqual(release_pass.differing_runs(b"abc", b"abc"), ())


class FoldersTest(unittest.TestCase):

    def setUp(self):
        self.original, self.copy = (Path(tempfile.mkdtemp()) for _ in range(2))

    def write(self, folder: Path, name: str, data: bytes):
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def test_each_file_added_removed_or_changed(self):
        self.write(self.original, "app.toml", b"name = 'a'\n")
        self.write(self.copy, "app.toml", b"name = 'b'\n")
        self.write(self.original, "pages/home.nx", b"code")
        self.write(self.copy, "pages/home.nx", b"code")
        self.write(self.original, "pictures/old.png", b"png")
        self.write(self.copy, "pictures/new.png", b"png")
        self.assertEqual(release_pass.compare_folders(self.original, self.copy), [
            Difference("app.toml", release_pass.CHANGED, ((8, b"a", b"b"),)),
            Difference("pictures/new.png", release_pass.ADDED),
            Difference("pictures/old.png", release_pass.REMOVED)])

    def test_the_same_folders_give_nothing(self):
        for folder in (self.original, self.copy):
            self.write(folder, "app.toml", b"same")
        self.assertEqual(release_pass.compare_folders(self.original, self.copy), [])


class BlocksTest(unittest.TestCase):

    def test_each_block_added_removed_or_changed(self):
        built = {"main.HMI": b"\x01\x02\x03", "0.pa": b"page", "1.i": b"picture"}
        saved = {"main.HMI": b"\x01\x09\x03", "0.pa": b"page", "2.i": b"picture"}
        self.assertEqual(release_pass.compare_blocks(built, saved), [
            Difference("1.i", release_pass.REMOVED),
            Difference("2.i", release_pass.ADDED),
            Difference("main.HMI", release_pass.CHANGED, ((1, b"\x02", b"\x09"),))])


class NewEditorOnlyTest(unittest.TestCase):

    def test_a_change_both_editors_make_alike_is_left_out(self):
        stamp = Difference("0.pa", release_pass.CHANGED, ((0, b"\x00", b"\x07"),))
        self.assertEqual(release_pass.new_editor_only([stamp], [stamp]), [])

    def test_a_block_both_editors_change_but_differently_is_a_finding(self):
        old = Difference("0.pa", release_pass.CHANGED, ((0, b"\x00", b"\x07"),))
        new = Difference("0.pa", release_pass.CHANGED, ((0, b"\x00", b"\x08"),))
        self.assertEqual(release_pass.new_editor_only([old], [new]), [new])

    def test_only_the_new_editor_s_runs_of_a_block_are_kept(self):
        old = Difference("0.pa", release_pass.CHANGED, ((0, b"\x00", b"\x07"),))
        new = Difference("0.pa", release_pass.CHANGED, ((0, b"\x00", b"\x07"), (9, b"a", b"b")))
        self.assertEqual(release_pass.new_editor_only([old], [new]),
                         [Difference("0.pa", release_pass.CHANGED, ((9, b"a", b"b"),))])

    def test_a_block_the_new_editor_alone_adds_is_a_finding(self):
        added = Difference("9.x", release_pass.ADDED)
        self.assertEqual(release_pass.new_editor_only([], [added]), [added])
        self.assertEqual(release_pass.new_editor_only([added], [added]), [])


class SectionTest(unittest.TestCase):

    def test_a_new_editor_change_beside_an_old_run_that_did_not_finish(self):
        # With nothing of the old Editor's to tell it from, a difference of
        # the new Editor's is not called its alone.
        old = release_pass.Side(findings=["`editor.py open` stopped: a time-out"])
        new = release_pass.Side(blocks=[Difference("0.pa", release_pass.CHANGED,
                                                   ((0, b"\x00", b"\x07"),))], finished=True)
        text = release_pass._section("demo", old, new)
        self.assertNotIn("alone", text)
        self.assertIn("The old Editor's run did not finish", text)
        self.assertIn("`0.pa`", text)

    def test_both_runs_finished(self):
        stamp = Difference("0.pa", release_pass.CHANGED, ((0, b"\x00", b"\x07"),))
        old = release_pass.Side(blocks=[stamp], finished=True)
        new = release_pass.Side(blocks=[stamp, Difference("9.x", release_pass.ADDED)],
                                finished=True)
        text = release_pass._section("demo", old, new)
        alone = text[text.index("What the new Editor alone changes"):]
        self.assertIn("`9.x`", alone)
        self.assertNotIn("`0.pa`", alone)


if __name__ == "__main__":
    unittest.main()
