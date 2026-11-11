"""Files in `ram/`, the screen's memory (testing/ram_files.py): the room
they take from the project's memory file storage size, and what newfile,
twfile, refile, and newdir do with them. Each expected answer is the one
the Nextion Editor's simulator gave for an NX8048P050."""
import unittest

from nxwright.testing import SourceFolderRunner
from nxwright.testing.editor_machine import EditorMachine
from nxwright.testing.ram_files import fits, is_ram_path
from nxwright.testing.simulation import Simulation
from tests.test_folder_check import edited_app
from tests.test_simulation import DONE, READY, SimulationTestCase, placed, table

REFUSED = b"\x06\xff\xff\xff"


def run(lines: list, space: int = 4096, files: dict = None) -> dict:
    """Runs `lines` on a test machine that starts with `files`, {path:
    bytes}, and whose project sets `space` bytes aside for `ram/` files.
    Returns the machine's values."""
    values = {"file contents": dict(files)} if files else {}
    return EditorMachine(values, memory_file_storage_size=space).run(lines)


def sizes(values: dict) -> dict:
    """The size of each file in the values' "file contents"."""
    return {path: len(data) for path, data in values.get("file contents", {}).items()}


class RoomTest(unittest.TestCase):
    """The files fit when their sizes, plus 268 bytes for each file and 16
    bytes more, come to no more than the space set aside."""

    def test_a_ram_path_starts_with_ram_in_lower_case(self):
        self.assertTrue(is_ram_path("ram/a.bin"))
        for path in ("RAM/a.bin", "sd0/a.bin", "a.bin", "ram", None, 5):
            with self.subTest(path=path):
                self.assertFalse(is_ram_path(path))

    def test_what_fits(self):
        self.assertTrue(fits(3812, {}, 4096))
        self.assertFalse(fits(3813, {}, 4096))
        self.assertTrue(fits(7908, {}, 8192))
        self.assertFalse(fits(7909, {}, 8192))
        # Only the ram/ files take room.
        files = {"ram/a.bin": bytes(1), "sd0/big.bin": bytes(5000)}
        self.assertTrue(fits(3543, files, 4096))
        self.assertFalse(fits(3544, files, 4096))
        # With no space set aside, nothing fits.
        self.assertFalse(fits(0, {}, 0))


class NewfileTest(unittest.TestCase):

    def test_with_no_space_set_aside_nothing_is_made(self):
        for values in (run(['newfile "ram/a.bin",8'], space=0),
                       EditorMachine({}).run(['newfile "ram/a.bin",8'])):
            self.assertEqual(sizes(values), {})
            self.assertEqual(values["file errors"], [("newfile", "ram/a.bin")])
            self.assertEqual(values.get("file commands", []), [])

    def test_the_largest_file(self):
        values = run(['newfile "ram/a.bin",3813', 'newfile "ram/b.bin",3812'])
        self.assertEqual(sizes(values), {"ram/b.bin": 3812})
        self.assertEqual(values["file contents"]["ram/b.bin"], bytes(3812))
        self.assertEqual(values["file errors"], [("newfile", "ram/a.bin")])
        self.assertEqual(values["file commands"], [("newfile", "ram/b.bin", 3812)])

    def test_a_second_file_beside_one_of_a_byte(self):
        values = run(['newfile "ram/a.bin",1', 'newfile "ram/b.bin",3544',
                      'newfile "ram/c.bin",3543'])
        self.assertEqual(sizes(values), {"ram/a.bin": 1, "ram/c.bin": 3543})

    def test_eight_files_of_200_bytes(self):
        values = run(['newfile "ram/f%d.bin",200' % number for number in range(1, 21)])
        self.assertEqual(sorted(sizes(values)), ["ram/f%d.bin" % number for number in range(1, 9)])

    def test_a_file_of_no_bytes(self):
        self.assertEqual(sizes(run(['newfile "ram/z.bin",0'])), {"ram/z.bin": 0})

    def test_delfile_frees_the_room(self):
        values = run(['newfile "ram/a.bin",3812', 'newfile "ram/b.bin",8', 'delfile "ram/a.bin"',
                      'newfile "ram/c.bin",8'])
        self.assertEqual(sizes(values), {"ram/c.bin": 8})
        self.assertEqual(values["file errors"], [("newfile", "ram/b.bin")])

    def test_files_a_test_gives_are_taken_as_given(self):
        # A file larger than the space set aside is kept, and leaves no room for another file.
        values = run(['findfile "ram/big.bin",sys0', 'newfile "ram/a.bin",8'],
                     files={"ram/big.bin": bytes(5000)})
        self.assertEqual((values["sys0"], sizes(values)), (1, {"ram/big.bin": 5000}))

    def test_on_a_file_of_the_same_size(self):
        values = run(['newfile "ram/a.bin",8'], files={"ram/a.bin": b"hello\0\0\0"})
        self.assertEqual(values["file contents"], {"ram/a.bin": b"hello\0\0\0"})
        self.assertNotIn("file errors", values)

    def test_on_a_file_of_another_size(self):
        # The new file takes the old one's place, so it needs no room beside it.
        values = run(['newfile "ram/a.bin",3812'], files={"ram/a.bin": b"hello" + bytes(1995)})
        self.assertEqual(values["file contents"], {"ram/a.bin": bytes(3812)})
        values = run(['newfile "ram/a.bin",3'], files={"ram/a.bin": b"hello\0\0\0"})
        self.assertEqual(values["file contents"], {"ram/a.bin": bytes(3)})

    def test_a_size_that_does_not_fit_removes_the_old_file(self):
        values = run(['newfile "ram/a.bin",3813'], files={"ram/a.bin": bytes(3)})
        self.assertEqual(sizes(values), {})
        self.assertEqual(values["file errors"], [("newfile", "ram/a.bin")])

    def test_the_size_is_checked_first(self):
        values = run(['newfile "ram/a.bin","abc"', 'newfile "ram/a.bin",-5'],
                     files={"ram/a.bin": bytes(3)})
        self.assertEqual(sizes(values), {"ram/a.bin": 3})
        self.assertEqual(values["file errors"], [("newfile", "ram/a.bin")] * 2)


class FoldersTest(unittest.TestCase):
    """`ram/` has no folders."""

    def test_no_folder_is_made_and_no_file_in_one(self):
        lines = ['newdir "ram/d/"', 'newfile "ram/d/a.bin",8', 'twfile "ram/d/x.bin",5',
                 'finddir "ram/d/",sys0']
        values = run(lines)
        self.assertEqual((values["sys0"], sizes(values)), (0, {}))
        self.assertEqual(values["file errors"], [("newdir", "ram/d/"), ("newfile", "ram/d/a.bin"),
                                                 ("twfile", "ram/d/x.bin")])
        self.assertEqual(values.get("file commands", []), [])
        self.assertNotIn("other commands", values)


class RefileTest(unittest.TestCase):

    def test_a_file_is_renamed_with_its_bytes(self):
        values = run(['refile "ram/a.bin","ram/b.bin"'], files={"ram/a.bin": b"hello"})
        self.assertEqual(values["file contents"], {"ram/b.bin": b"hello"})
        self.assertEqual(values["file commands"], [("refile", "ram/a.bin", "ram/b.bin")])
        self.assertNotIn("file errors", values)

    def test_what_is_refused_renames_nothing(self):
        files = {"ram/a.bin": b"a", "ram/b.bin": b"b"}
        lines = ['refile "ram/no.bin","ram/c.bin"', 'refile "ram/a.bin","ram/b.bin"',
                 'refile "ram/a.bin","sd0/a.bin"', 'refile "ram/a.bin","ram/d/a.bin"']
        values = run(lines, files=files)
        self.assertEqual(values["file contents"], files)
        self.assertEqual(values["file errors"], [("refile", "ram/no.bin")]
                         + [("refile", "ram/a.bin")] * 3)
        self.assertEqual(values.get("file commands", []), [])


class TwfileInATestTest(unittest.TestCase):
    """A test has no serial line, so it records a twfile the screen takes."""

    def test_one_that_fits_is_recorded(self):
        values = run(['twfile "ram/x.bin",3812'])
        self.assertEqual(values["other commands"], [("twfile", '"ram/x.bin"', "3812")])
        self.assertNotIn("file errors", values)

    def test_one_that_does_not_fit_is_refused(self):
        refused = [run(['twfile "ram/x.bin",3813']), run(['twfile "ram/x.bin",8'], space=0),
                   run(['twfile "ram/b.bin",600'], files={"ram/a.bin": bytes(3000)})]
        for values in refused:
            self.assertEqual([command for command, _ in values["file errors"]], ["twfile"])
            self.assertNotIn("other commands", values)
        values = run(['twfile "ram/b.bin",500'], files={"ram/a.bin": bytes(3000)})
        self.assertNotIn("file errors", values)

    def test_the_file_it_replaces_takes_room_too(self):
        values = run(['twfile "ram/a.bin",1772'], files={"ram/a.bin": bytes(1772)})
        self.assertNotIn("file errors", values)
        values = run(['twfile "ram/a.bin",1773'], files={"ram/a.bin": bytes(1773)})
        self.assertEqual(values["file errors"], [("twfile", "ram/a.bin")])

    def test_the_size_is_checked_first(self):
        machine = EditorMachine({"t0.txt": "abc"}, memory_file_storage_size=4096)
        values = machine.run(['twfile "ram/a.bin",0', 'twfile "ram/a.bin",t0.txt'])
        self.assertEqual(values["file errors"], [("twfile", "ram/a.bin")] * 2)
        self.assertNotIn("other commands", values)


class SimulationTest(SimulationTestCase):
    """A simulation takes the space from app.toml, answers 0x06 for what
    does not fit, and takes a twfile's bytes from the serial line."""

    def setUp(self):
        super().setUp()
        self.program("page page0\n")
        self.page("page0", [placed("go", "button", 0, 0),
                            placed("t", "text", 0, 100, txt="", txt_maxl=20),
                            table("file", "file-stream")], """\
on go.down:
  newfile "ram/a.bin",8
""")
        self.sent = []

    def set_aside(self, size: int):
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(memory_file_storage_size=size)))

    def simulation(self) -> Simulation:
        simulation = Simulation(self.root, sending=self.sent.append)
        self.sent.clear()
        return simulation

    def typed(self, simulation: Simulation, *lines: str):
        for line in lines:
            simulation.serial_received(line.encode() + b"\xff\xff\xff")

    def test_with_no_space_set_aside(self):
        simulation = self.simulation()
        self.typed(simulation, 'newfile "ram/a.bin",8', 'twfile "ram/a.bin",8')
        self.assertEqual(self.sent, [REFUSED, REFUSED])
        self.assertEqual(simulation.values().get("file contents", {}), {})

    def test_with_space_set_aside(self):
        self.set_aside(4096)
        simulation = self.simulation()
        self.typed(simulation, 'newfile "ram/a.bin",3813', 'newfile "ram/a.bin",3812',
                   'newdir "ram/d/"', 'refile "ram/a.bin","sd0/a.bin"')
        self.assertEqual(self.sent, [REFUSED] * 3)
        self.assertEqual(sizes(simulation.values()), {"ram/a.bin": 3812})

    def test_an_events_newfile(self):
        self.set_aside(4096)
        simulation = self.simulation()
        simulation.press("go")
        self.assertEqual(sizes(simulation.values()), {"ram/a.bin": 8})

    def test_the_bytes_after_a_twfile_become_the_file(self):
        self.set_aside(4096)
        simulation = self.simulation()
        simulation.serial_received(b'twfile "ram/w.txt",5\xff\xff\xffhello')
        self.assertEqual(self.sent, [READY, DONE])
        self.assertEqual(simulation.values()["file contents"], {"ram/w.txt": b"hello"})
        # A file stream reads it.
        self.typed(simulation, 'file.open("ram/w.txt")', "file.read(t.txt,0,5)")
        self.assertEqual(simulation.values()["t.txt"], "hello")

    def test_a_twfile_over_a_file_replaces_it(self):
        self.set_aside(4096)
        simulation = self.simulation()
        self.typed(simulation, 'newfile "ram/w.txt",1772')
        simulation.serial_received(b'twfile "ram/w.txt",3\xff\xff\xffnew')
        self.assertEqual(self.sent, [READY, DONE])
        self.assertEqual(simulation.values()["file contents"], {"ram/w.txt": b"new"})

    def test_a_twfile_that_does_not_fit(self):
        self.set_aside(4096)
        simulation = self.simulation()
        self.typed(simulation, 'twfile "ram/w.txt",3813')
        self.assertEqual(self.sent, [REFUSED])
        self.assertEqual(simulation.values()["file errors"], [("twfile", "ram/w.txt")])


class RunnerTest(SimulationTestCase):
    """A test takes the space from app.toml too."""

    def setUp(self):
        super().setUp()
        self.page("page0", [placed("go", "button", 0, 0)], """\
on go.down:
  newfile "ram/a.bin",8
""")

    def test_with_no_space_set_aside(self):
        values = SourceFolderRunner(self.root).run("page0", [("go", "down")])
        self.assertEqual(sizes(values), {})
        self.assertEqual(values["file errors"], [("newfile", "ram/a.bin")])

    def test_with_space_set_aside(self):
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(memory_file_storage_size=4096)))
        values = SourceFolderRunner(self.root).run("page0", [("go", "down")])
        self.assertEqual(sizes(values), {"ram/a.bin": 8})


if __name__ == "__main__":
    unittest.main()
