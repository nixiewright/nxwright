"""A data record and a file browser whose path is in `ram/`, the screen's
memory. Each expected answer is the one the Nextion Editor's simulator gave
for an NX8048P050."""
from pathlib import Path
import tempfile
import tomllib
import unittest

from nxwright.drawing.data_record_drawing import FILE_LOST
from nxwright.testing.editor_machine import EditorMachine
from nxwright.testing.ram_files import NO_SPACE
from nxwright.testing.simulation import Simulation
from tests.test_folder_check import edited_app
from tests.test_simulation import DataFileHoldingTestCase, table

# The size of the data file of a data record whose `lenth` is 16 and whose
# `maxval` is 10.
SMALL_FILE = 2560


def record(name: str = "d0", path: str = "ram/d.data", **values) -> str:
    """A data record's table in a page file. Its data file is SMALL_FILE
    bytes, unless `values` give another `lenth` or `maxval`."""
    values = dict({"lenth": 16, "maxval": 10, "mode": 1}, **values)
    return table(name, "data-record", x=0, y=40, w=300, h=200, path=path, dir="a^b", **values)


class DataRecordTest(DataFileHoldingTestCase):

    def started(self, space: int = 0, components: list = None, **options) -> tuple:
        """Starts a simulation of a project that sets `space` bytes aside for
        `ram/` files. Its page has `components`, or by default one data
        record whose path is `ram/d.data`."""
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(memory_file_storage_size=space)))
        self.page("page0", components or [record()])
        sent = []
        return Simulation(self.root, sending=sent.append, **options), sent

    def files(self, simulation: Simulation) -> dict:
        return simulation.values().get("file contents", {})

    def log(self, simulation: Simulation) -> list:
        return [line for _, line in simulation.log]

    def assert_no_file(self, simulation: Simulation, sent: list, reason: str):
        """Asserts that d0 did not create `ram/d.data` when its page opened,
        when a method ran, or when code set its `path`, and that the log
        gives `reason`."""
        self.assertIs(simulation.listings()["d0"], FILE_LOST)
        self.assertEqual((simulation.values()["d0.qty"], self.files(simulation)), (0, {}))
        self.assertEqual(self.refusals(sent), 1)
        self.assertIn("d0 cannot make ram/d.data: " + reason, self.log(simulation))
        # A method changes nothing, and the screen sends no code for it.
        simulation.serial_input('d0.insert("x^y")')
        self.assertEqual((simulation.values()["d0.qty"], self.files(simulation)), (0, {}))
        self.assertEqual(self.refusals(sent), 0)
        simulation.serial_input('d0.path="ram/d.data"')
        self.assertEqual((self.refusals(sent), self.files(simulation)), (1, {}))
        self.assertIn(("open", "ram/d.data"), simulation.values()["file errors"])
        self.assertIn("ram/: open of ram/d.data refused: " + reason, self.log(simulation))
        self.assertIs(simulation.listings()["d0"], FILE_LOST)

    def test_no_space_set_aside(self):
        simulation, sent = self.started(space=0)
        self.assert_no_file(simulation, sent, NO_SPACE)

    def test_a_data_file_larger_than_the_space_set_aside(self):
        simulation, sent = self.started(space=4096, components=[record(lenth=63, maxval=1000)])
        self.assert_no_file(simulation, sent,
                            "the file does not fit. A new file can have at most 3812 of the "
                            "4096 bytes set aside for ram/ files")

    def test_a_data_file_that_fits_uses_up_space(self):
        simulation, sent = self.started(space=4096)
        self.assertEqual(simulation.listings()["d0"], [])
        self.assertEqual(len(self.files(simulation)["ram/d.data"]), SMALL_FILE)
        # 4096 - 16 - (268 + 2560) - 268 leaves 984 bytes for another file.
        simulation.serial_input('newfile "ram/z.bin",985')
        self.assertEqual(self.refusals(sent), 1)
        simulation.serial_input('newfile "ram/z.bin",984')
        self.assertEqual(self.refusals(sent), 0)
        self.assertEqual(sorted(self.files(simulation)), ["ram/d.data", "ram/z.bin"])
        simulation.serial_input('d0.insert("x^y")')
        self.assertEqual((simulation.values()["d0.qty"], self.refusals(sent)), (1, 0))

    def found(self, simulation: Simulation, path: str) -> int:
        """What `findfile` gives for `path`: 1 if the file exists."""
        simulation.serial_input("sys0=5")
        simulation.serial_input('findfile "%s",sys0' % path)
        return simulation.values()["sys0"]

    def test_setting_the_path_creates_the_file_at_once(self):
        simulation, sent = self.started(space=8192)
        self.assertEqual(self.found(simulation, "ram/e.data"), 0)
        simulation.serial_input('d0.path="ram/e.data"')
        self.assertEqual(self.found(simulation, "ram/e.data"), 1)
        simulation.serial_input('d0.path="sd0/f.data"')
        self.assertEqual(self.found(simulation, "sd0/f.data"), 1)
        self.assertEqual(sorted(self.files(simulation)),
                         ["ram/d.data", "ram/e.data", "sd0/f.data"])
        self.assertEqual(self.refusals(sent), 0)

    def test_setting_the_path_creates_the_file_in_a_cards_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            simulation, sent = self.started(space=4096, cards={"sd0/": Path(folder)})
            simulation.serial_input('d0.path="sd0/f.data"')
            self.assertEqual(self.found(simulation, "sd0/f.data"), 1)
            self.assertEqual(len((Path(folder) / "f.data").read_bytes()), SMALL_FILE)
            self.assertEqual(self.refusals(sent), 0)

    def test_a_missing_file_with_mode_0(self):
        simulation, sent = self.started(space=4096, components=[record(mode=0)])
        self.assertIs(simulation.listings()["d0"], FILE_LOST)
        simulation.serial_input('d0.path="ram/m.data"')
        self.assertIs(simulation.listings()["d0"], FILE_LOST)
        self.assertEqual((self.refusals(sent), self.files(simulation)), (0, {}))
        self.assertNotIn("file errors", simulation.values())

    def test_a_record_that_opens_no_file_yet_shows_its_titles(self):
        simulation, sent = self.started(space=0, components=[record(init=1)])
        self.assertEqual((simulation.listings()["d0"], self.refusals(sent)), ([], 0))

    def test_a_data_record_with_a_missing_file_on_a_card_lists_no_records(self):
        simulation, sent = self.started(space=0, components=[record(path="sd0/m.data", mode=0)])
        self.assertEqual((simulation.listings()["d0"], self.refusals(sent)), ([], 0))


class TestMachineTest(unittest.TestCase):
    """The test machine alone, with no simulation."""

    def values(self) -> dict:
        defaults = tomllib.loads(
            (Path(__file__).resolve().parent.parent / "nxwright" / "project"
             / "component_defaults.toml").read_text(encoding="utf-8"))["data-record"]["attributes"]
        values = {"d0." + key: value for key, value in defaults.items()}
        values.update({"d0.lenth": 16, "d0.maxval": 10, "d0.path": "ram/d.data"})
        return values

    def test_a_method_creates_no_file_without_space(self):
        values = EditorMachine(self.values()).run(['d0.insert("x^y")'])
        self.assertEqual(values.get("file contents", {}), {})
        self.assertEqual((values["file errors"], values["d0.qty"]),
                         ([("insert", "ram/d.data")], 0))

    def test_a_method_creates_the_file_with_space(self):
        values = EditorMachine(self.values(), memory_file_storage_size=4096).run(
            ['d0.insert("x^y")'])
        self.assertEqual((len(values["file contents"]["ram/d.data"]), values["d0.qty"]),
                         (SMALL_FILE, 1))

    def test_setting_the_path_without_space(self):
        values = EditorMachine(self.values()).run(['d0.path="ram/e.data"'])
        self.assertEqual(values.get("file contents", {}), {})
        self.assertEqual(values["file errors"], [("open", "ram/e.data")])


class FileBrowserTest(DataFileHoldingTestCase):

    def test_a_file_browser_lists_nothing_in_ram(self):
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(memory_file_storage_size=4096)))
        self.page("page0", [table("f0", "file-browser", x=320, y=40, w=300, h=300, dir="ram/",
                                  psta=0)])
        simulation, sent = self.started()
        for line in ('newfile "ram/a.bin",8', 'newfile "sd0/b.bin",8', 'f0.dir="ram/"'):
            simulation.serial_input(line)
        self.assertEqual((simulation.values()["f0.qty"], simulation.listings()["f0"]), (0, []))
        simulation.serial_input('f0.dir="sd0/"')
        self.assertEqual((simulation.values()["f0.qty"], simulation.listings()["f0"]),
                         (1, ["b.bin"]))
        self.assertEqual(self.refusals(sent), 0)


if __name__ == "__main__":
    unittest.main()
