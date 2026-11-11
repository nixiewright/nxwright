"""A data record's file: what shows when it is missing, and the file
commands on it while the data record keeps it. Each expected answer is the
one the Nextion Editor's simulator gave for an NX8048P050."""
from pathlib import Path
import tempfile
import tomllib
import unittest

from nxwright.drawing.data_record_drawing import FILE_LOST
from nxwright.testing.editor_machine import KEPT_BY_A_DATA_RECORD, EditorMachine
from nxwright.testing.simulation import Simulation
from tests.test_components_on_ram_files import SMALL_FILE, record
from tests.test_folder_check import edited_app
from tests.test_simulation import DataFileHoldingTestCase, table

IGNORED = bytes.fromhex("06 ff ff ff")


class RecordsTestCase(DataFileHoldingTestCase):

    def started(self, components: list, **options) -> tuple:
        """Starts a simulation of a project that sets 4096 bytes aside for
        `ram/` files. Its page has `components`."""
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(memory_file_storage_size=4096)))
        self.page("page0", components)
        sent = []
        return Simulation(self.root, sending=sent.append, **options), sent


class MissingFileTest(RecordsTestCase):
    """A data record whose file is missing shows "File Lost:" and the path."""

    def test_mode_0_on_a_card(self):
        simulation, sent = self.started([record(path="sd0/m.data", mode=0)])
        self.assertIs(simulation.listings()["d0"], FILE_LOST)
        self.assertEqual((simulation.values()["d0.qty"], self.refusals(sent)), (0, 0))
        self.assertNotIn("file errors", simulation.values())

    def test_mode_0_on_a_card_given_a_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            simulation, sent = self.started([record(path="sd0/m.data", mode=0)],
                                            cards={"sd0/": Path(folder)})
            self.assertIs(simulation.listings()["d0"], FILE_LOST)
            self.assertEqual(self.refusals(sent), 0)
            # Given the path of a file that exists, the data record shows its
            # records.
            (Path(folder) / "n.data").write_bytes(
                (Path(__file__).resolve().parent / "fixtures" / "data-record"
                 / "three.data").read_bytes())
            simulation.serial_input('d0.path="sd0/n.data"')
            self.assertIsNot(simulation.listings()["d0"], FILE_LOST)

    def test_mode_1_creates_the_file_and_shows_its_records(self):
        simulation, sent = self.started([record(path="sd0/m.data")])
        self.assertEqual((simulation.listings()["d0"], self.refusals(sent)), ([], 0))

    def test_a_file_that_cannot_be_created_in_the_cards_folder(self):
        # The path's folder does not exist in the card's folder.
        with tempfile.TemporaryDirectory() as folder:
            simulation, _ = self.started([record(path="sd0/none/m.data")],
                                         cards={"sd0/": Path(folder)})
            self.assertIs(simulation.listings()["d0"], FILE_LOST)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_a_path_on_no_card_is_listed_with_no_records(self):
        simulation, _ = self.started([record(path="m.data", mode=0)])
        self.assertEqual(simulation.listings()["d0"], [])


class KeptFileTest(RecordsTestCase):
    """While a data record keeps its file, the file commands on that file
    are ignored, and a file stream does not open it."""

    def assert_locked(self, path: str, prefix: str, **options):
        folder = path.rsplit("/", 1)[0]
        simulation, sent = self.started([record(path=path), table("fs0", "file-stream")],
                                        **options)
        simulation.serial_input('d0.insert("x^y")')
        self.refusals(sent)
        commands = ('rdfile "%s",0,0,0' % path, 'delfile "%s"' % path,
                    'refile "%s","%s/other.data"' % (path, folder), 'newfile "%s",8' % path)
        for command in commands:
            with self.subTest(command=command):
                simulation.serial_input(command)
                self.assertEqual(sent, [IGNORED])
                sent.clear()
                word = command.split(" ")[0]
                self.assertIn((word, path), simulation.values()["file errors"])
                self.assertIn("%s: %s of %s refused: %s" % (prefix, word, path,
                                                            KEPT_BY_A_DATA_RECORD),
                              [line for _, line in simulation.log])
        # The file and its record are as they were.
        self.assertEqual((simulation.values()["d0.qty"], simulation.listings()["d0"]),
                         (1, ["x^y"]))
        simulation.serial_input('fs0.open("%s")' % path)
        self.assertEqual((simulation.values()["fs0.en"], self.refusals(sent)), (0, 0))
        simulation.serial_input("sys0=5")
        simulation.serial_input('findfile "%s",sys0' % path)
        self.assertEqual(simulation.values()["sys0"], 1)
        # Once the data record lets the file go, the commands work on it.
        simulation.serial_input('d0.path="%s/free.data"' % folder)
        sent.clear()
        simulation.serial_input('rdfile "%s",0,0,0' % path)
        self.assertEqual(sent, [SMALL_FILE.to_bytes(4, "little")])
        simulation.serial_input('fs0.open("%s")' % path)
        self.assertEqual(simulation.values()["fs0.en"], 1)
        simulation.serial_input("fs0.close()")
        simulation.serial_input('delfile "%s"' % path)
        simulation.serial_input('findfile "%s",sys0' % path)
        self.assertEqual(simulation.values()["sys0"], 0)
        return simulation

    def test_on_a_card(self):
        self.assert_locked("sd0/k.data", "SD card")

    def test_in_ram(self):
        self.assert_locked("ram/k.data", "ram/")

    def test_on_a_card_given_a_folder(self):
        # The stand-in for a user's folder is a temporary folder.
        with tempfile.TemporaryDirectory() as folder:
            self.assert_locked("sd0/k.data", "SD card", cards={"sd0/": Path(folder)})
            self.assertEqual([file.name for file in Path(folder).iterdir()], ["free.data"])


class TestMachineTest(unittest.TestCase):
    """The test machine alone, with no simulation."""

    def test_a_kept_file_is_not_deleted(self):
        defaults = tomllib.loads(
            (Path(__file__).resolve().parent.parent / "nxwright" / "project"
             / "component_defaults.toml").read_text(encoding="utf-8"))["data-record"]["attributes"]
        values = {"d0." + key: value for key, value in defaults.items()}
        values.update({"d0.lenth": 16, "d0.maxval": 10, "d0.path": "sd0/k.data"})
        values = EditorMachine(values).run(['d0.insert("x^y")', 'delfile "sd0/k.data"',
                                            'd0.insert("z^w")'])
        self.assertEqual(values["file errors"], [("delfile", "sd0/k.data")])
        self.assertEqual((values["d0.qty"], len(values["file contents"]["sd0/k.data"])),
                         (2, SMALL_FILE))


if __name__ == "__main__":
    unittest.main()
