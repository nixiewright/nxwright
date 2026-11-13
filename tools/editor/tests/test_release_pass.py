"""The comparisons of a release pass (tools/editor/release_pass.py). The
round trip's: of two folders file by file, and of the differences the new
Nextion Editor alone makes. Then of two Editors' catalogs of attributes, of
their lists of screen models with nxwright's table, and of the files of two
releases. They run on small inputs written for the tests, and need neither
the Nextion Editor nor pywinauto."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from nxwright.project.byte_differences import ADDED, CHANGED, REMOVED, Difference
from nxwright.project.screen_models import MODELS, ScreenModel
from tools.editor import release_pass


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
            Difference("app.toml", CHANGED, ((8, b"a", b"b"),)),
            Difference("pictures/new.png", ADDED),
            Difference("pictures/old.png", REMOVED)])

    def test_the_same_folders_give_nothing(self):
        for folder in (self.original, self.copy):
            self.write(folder, "app.toml", b"same")
        self.assertEqual(release_pass.compare_folders(self.original, self.copy), [])


class NewEditorOnlyTest(unittest.TestCase):

    def test_a_change_both_editors_make_alike_is_left_out(self):
        stamp = Difference("0.pa", CHANGED, ((0, b"\x00", b"\x07"),))
        self.assertEqual(release_pass.new_editor_only([stamp], [stamp]), [])

    def test_a_block_both_editors_change_but_differently_is_a_finding(self):
        old = Difference("0.pa", CHANGED, ((0, b"\x00", b"\x07"),))
        new = Difference("0.pa", CHANGED, ((0, b"\x00", b"\x08"),))
        self.assertEqual(release_pass.new_editor_only([old], [new]), [new])

    def test_only_the_new_editor_s_runs_of_a_block_are_kept(self):
        old = Difference("0.pa", CHANGED, ((0, b"\x00", b"\x07"),))
        new = Difference("0.pa", CHANGED, ((0, b"\x00", b"\x07"), (9, b"a", b"b")))
        self.assertEqual(release_pass.new_editor_only([old], [new]),
                         [Difference("0.pa", CHANGED, ((9, b"a", b"b"),))])

    def test_a_block_the_new_editor_alone_adds_is_a_finding(self):
        added = Difference("9.x", ADDED)
        self.assertEqual(release_pass.new_editor_only([], [added]), [added])
        self.assertEqual(release_pass.new_editor_only([added], [added]), [])


class SectionTest(unittest.TestCase):

    def test_a_new_editor_change_beside_an_old_run_that_did_not_finish(self):
        # With nothing of the old Editor's to tell it from, a difference of
        # the new Editor's is not called its alone.
        old = release_pass.Side(findings=["`editor.py open` stopped: a time-out"])
        new = release_pass.Side(blocks=[Difference("0.pa", CHANGED,
                                                   ((0, b"\x00", b"\x07"),))], finished=True)
        text = release_pass._section("demo", old, new)
        self.assertNotIn("alone", text)
        self.assertIn("The old Editor's run did not finish", text)
        self.assertIn("`0.pa`", text)

    def test_both_runs_finished(self):
        stamp = Difference("0.pa", CHANGED, ((0, b"\x00", b"\x07"),))
        old = release_pass.Side(blocks=[stamp], finished=True)
        new = release_pass.Side(blocks=[stamp, Difference("9.x", ADDED)],
                                finished=True)
        text = release_pass._section("demo", old, new)
        alone = text[text.index("What the new Editor alone changes"):]
        self.assertIn("`9.x`", alone)
        self.assertNotIn("`0.pa`", alone)


def seen(hint: str, green=("defaults",), black=()) -> dict:
    """Returns an attribute as a merged catalog (merged.json) gives it."""
    return {"hint": hint, "green": list(green), "black": list(black), "values": []}


class CatalogsTest(unittest.TestCase):

    def changes(self, old: dict, new: dict) -> list:
        return [(each.where, each.kind) for each in release_pass.compare_catalogs(old, new)]

    def test_the_same_catalogs_give_nothing(self):
        catalog = {"text": {"aph": seen("Opaqueness(0-127)")}}
        self.assertEqual(release_pass.compare_catalogs(catalog, catalog), [])

    def test_a_type_added_or_removed(self):
        old = {"text": {}, "gauge": {}}
        new = {"text": {}, "chart": {}}
        self.assertEqual(self.changes(old, new), [("chart", release_pass.TYPE_ADDED),
                                                  ("gauge", release_pass.TYPE_REMOVED)])

    def test_an_attribute_added_or_removed(self):
        old = {"text": {"aph": seen("Opaqueness(0-127)"), "old": seen("Gone")}}
        new = {"text": {"aph": seen("Opaqueness(0-127)"), "neu": seen("New")}}
        self.assertEqual(self.changes(old, new), [("text, neu", release_pass.ATTRIBUTE_ADDED),
                                                  ("text, old", release_pass.ATTRIBUTE_REMOVED)])

    def test_a_hint_changed_gives_both_hints(self):
        old = {"text": {"aph": seen("Opaqueness(0-127)")}}
        new = {"text": {"aph": seen("Opacity(0-127)")}}
        [change] = release_pass.compare_catalogs(old, new)
        self.assertEqual((change.where, change.kind, change.old, change.new),
                         ("text, aph", release_pass.HINT_CHANGED, "Opaqueness(0-127)",
                          "Opacity(0-127)"))

    def test_a_choice_added_changes_the_choices_too(self):
        old = {"text": {"sta": seen("Background fill:0-crop image;1-solid color")}}
        new = {"text": {"sta": seen("Background fill:0-crop image;1-solid color;2-image")}}
        found = release_pass.compare_catalogs(old, new)
        self.assertEqual([each.kind for each in found],
                         [release_pass.HINT_CHANGED, release_pass.CHOICES_CHANGED])
        self.assertEqual((found[1].old, found[1].new),
                         ("0-crop image;1-solid color", "0-crop image;1-solid color;2-image"))

    def test_a_name_s_colour_changed(self):
        # Green when code may change the attribute, black when it may not.
        old = {"text": {"pco": seen("Font color", green=["defaults"])}}
        new = {"text": {"pco": seen("Font color", green=[], black=["defaults"])}}
        [change] = release_pass.compare_catalogs(old, new)
        self.assertEqual((change.where, change.kind, change.old, change.new),
                         ("text, pco", release_pass.COLOUR_CHANGED, "green", "black"))

    def test_the_variants_a_colour_showed_under_do_not_count(self):
        old = {"text": {"pco": seen("Font color", green=["defaults", "choice 0"])}}
        new = {"text": {"pco": seen("Font color", green=["defaults"])}}
        self.assertEqual(release_pass.compare_catalogs(old, new), [])


class CatalogRunTest(unittest.TestCase):
    """The catalog comparison's run, with catalog_variants.py and the Editor
    tool stood in for."""

    def setUp(self):
        self.output = Path(tempfile.mkdtemp()) / "catalog"

    def run_catalog(self, catalogs: dict) -> tuple:
        """Runs the comparison, each side's catalog_variants.py writing
        `catalogs`[side] as its merged.json, or nothing for a side not
        given. Returns (the report, the sides run, the Editor commands)."""
        sides, commands = [], []

        def catalog_variants(command, env, **_):
            side = Path(command[2]).name
            sides.append((side, env["NXWRIGHT_EDITOR_NAME"]))
            if side in catalogs:
                (Path(command[2]) / "merged.json").write_text(json.dumps(catalogs[side]),
                                                             encoding="utf-8")
            return subprocess.CompletedProcess(command, 0 if side in catalogs else 1)

        with mock.patch.object(release_pass.subprocess, "run", side_effect=catalog_variants), \
                mock.patch.object(release_pass, "editor_tool",
                                  side_effect=lambda env, *command: commands.append(command)):
            text = release_pass.catalog(Path("old.exe"), Path("new.exe"), self.output)
        return text, sides, commands

    def test_both_catalogs_are_compared(self):
        text, sides, commands = self.run_catalog({"old": {"text": {}}, "new": {"chart": {}}})
        self.assertEqual(sides, [("old", "release-old"), ("new", "release-new")])
        self.assertEqual(commands, [("quit",), ("quit",)])
        self.assertIn("- `chart`: type added", text)
        self.assertEqual((self.output / "report.md").read_text(encoding="utf-8"), text)

    def test_without_the_old_catalog_the_new_editor_is_not_run(self):
        text, sides, _ = self.run_catalog({"new": {"chart": {}}})
        self.assertEqual(sides, [("old", "release-old")])
        self.assertIn("The old Editor's catalog was not written", text)
        self.assertNotIn("chart", text)


def listed(series: str, inch: float, width: int, height: int) -> dict:
    """Returns a model as `editor.py models` lists it."""
    return {"series": series, "inch": inch, "width": width, "height": height,
            "flash": "128M", "ram": "524288B", "frequency": "200M"}


# A table of screen models, as nxwright's: two models of 7 inches on P.
TABLE = (ScreenModel("NX4827P043", b"\xda\x69\x11\x18", 0, 480, 272, 4.3, 128, 524288, 200),
         ScreenModel("NX8048P070", b"\xa7\xba\x27\xda", 0, 800, 480, 7.0, 128, 524288, 200),
         ScreenModel("NX1060P070", b"\xc2\x73\x34\xc4", 0, 1024, 600, 7.0, 128, 524288, 200))


class ModelsTest(unittest.TestCase):

    def changes(self, models: list) -> list:
        return [(each.where, each.kind, each.old, each.new)
                for each in release_pass.compare_models(models, TABLE)]

    def test_the_table_s_models_give_nothing(self):
        self.assertEqual(self.changes([listed("P", 4.3, 480, 272), listed("P", 7.0, 800, 480),
                                       listed("P", 7.0, 1024, 600)]), [])

    def test_a_model_added_or_removed(self):
        self.assertEqual(self.changes([listed("P", 4.3, 480, 272), listed("P", 7.0, 800, 480),
                                       listed("E", 2.1, 480, 480)]), [
            ("NX1060P070", release_pass.MODEL_REMOVED, None, None),
            ("E, 2.1 inches, 480x480", release_pass.MODEL_ADDED, None, None)])

    def test_a_model_resized(self):
        # A model of the table's series and inches, alone of them at
        # another size, is taken for the table's model resized.
        self.assertEqual(self.changes([listed("P", 4.3, 800, 480), listed("P", 7.0, 800, 480),
                                       listed("P", 7.0, 1024, 600)]), [
            ("NX4827P043", release_pass.MODEL_RESIZED, "480x272", "800x480")])


class ModelsRunTest(unittest.TestCase):
    """The models comparison's run, with the Editor tool stood in for."""

    def setUp(self):
        self.output = Path(tempfile.mkdtemp()) / "models"

    def run_models(self, lists: dict) -> tuple:
        """Runs the comparison, each side's `editor.py models` writing
        `lists`[side] as its list, or stopping for a side not given.
        Returns (the report, the commands, each with its Editor name)."""
        commands = []

        def editor(environment, *command):
            side = {name: side for side, name in release_pass.EDITOR_NAMES.items()}[
                environment["NXWRIGHT_EDITOR_NAME"]]
            commands.append((side, command[0]))
            if command[0] == "models":
                if side not in lists:
                    return subprocess.CompletedProcess(command, 1, "", "Stopped: a time-out")
                Path(command[1]).write_text(json.dumps({"editor_version": "1.68.2.3035",
                                                        "models": lists[side]}),
                                            encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "", "")

        with mock.patch.object(release_pass, "editor_tool", side_effect=editor):
            text = release_pass.models(Path("old.exe"), Path("new.exe"), self.output)
        return text, commands

    def test_each_editor_s_list_is_compared_with_the_table(self):
        table = [listed(model.series, int(model.name[7:10]) / 10, model.width, model.height)
                 for model in MODELS]
        text, commands = self.run_models({"old": table,
                                          "new": table + [listed("E", 5.0, 480, 854)]})
        self.assertEqual(commands, [(side, step) for side in ("old", "new")
                                    for step in ("open", "models", "quit")])
        old, new = text.split("## The new Editor")
        self.assertIn("Nothing differs.", old)
        self.assertIn("- `E, 5.0 inches, 480x854`: model added", new)
        self.assertEqual((self.output / "report.md").read_text(encoding="utf-8"), text)

    def test_a_side_that_stops_leaves_the_other_s_list(self):
        # Each list is compared with the table, not with the other.
        text, commands = self.run_models({"new": [listed("E", 5.0, 480, 854)]})
        self.assertEqual(commands, [("old", "open"), ("old", "models"), ("old", "close-message"),
                                    ("old", "quit"), ("new", "open"), ("new", "models"),
                                    ("new", "quit")])
        old, new = text.split("## The new Editor")
        self.assertIn("`editor.py models` stopped: Stopped: a time-out", old)
        self.assertIn("- `E, 5.0 inches, 480x854`: model added", new)


class ReleaseFilesTest(unittest.TestCase):

    def setUp(self):
        self.old, self.new = (Path(tempfile.mkdtemp()) for _ in range(2))

    def write(self, folder: Path, name: str, data: bytes):
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def test_each_file_added_removed_or_changed_without_runs(self):
        self.write(self.old, "NextionEditor.exe", b"old program")
        self.write(self.new, "NextionEditor.exe", b"new program")
        self.write(self.old, "model0.sa", b"same")
        self.write(self.new, "model0.sa", b"same")
        self.write(self.old, "lib/old.dll", b"dll")
        self.write(self.new, "lib/new.dll", b"dll")
        self.assertEqual(release_pass.compare_files(self.old, self.new), [
            Difference("NextionEditor.exe", CHANGED),
            Difference("lib/new.dll", ADDED),
            Difference("lib/old.dll", REMOVED)])

    def test_the_report_lists_each_file(self):
        found = [Difference("model0.sa", CHANGED)]
        text = release_pass.files_report(self.old, self.new, found)
        self.assertIn("- `model0.sa`: changed", text)
        self.assertIn("Nothing differs.", release_pass.files_report(self.old, self.new, []))

    def test_the_report_s_folder_is_created(self):
        report = Path(tempfile.mkdtemp()) / "pass" / "files.md"
        with mock.patch("sys.stdout"):
            self.assertEqual(release_pass.main(["files", "--old", str(self.old), "--new",
                                                str(self.new), str(report)]), 0)
        self.assertIn("Nothing differs.", report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
