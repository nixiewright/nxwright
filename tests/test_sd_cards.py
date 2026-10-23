"""A simulation's SD cards as folders of the computer (testing/sd_cards.py):
the checks that keep the folders and what lies outside them from harm,
each tested as a function, without deleting anything; the file commands on
a stand-in, a temporary folder each test makes; and file browsers and
selects, which the simulation works."""
import base64
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from nxwright import NxwrightError
from nxwright.testing.preview import Previews
from nxwright.project.pictures import read_picture, write_png
from nxwright.source.page_source import Component
from nxwright.testing.sd_cards import CardRefusal, FolderCards, card_folder, inside
from nxwright.testing.simulation import Simulation
from tests.test_live_debugging import LiveTestCase
from tests.test_simulation import DONE, N_IS_0, READY, SimulationTestCase, placed, table


def _link_folder(link: Path, target: Path) -> bool:
    """Makes `link` lead to the folder `target`. A symbolic link needs a
    privilege on Windows. A junction does not, and leads out of a folder
    the same way. False when neither can be made."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except OSError:
        pass
    try:
        import _winapi      # Windows' own module, the one that makes junctions
    except ImportError:
        return False
    try:
        _winapi.CreateJunction(str(target), str(link))
        return True
    except OSError:
        return False


class CardFolderTest(unittest.TestCase):
    """What a launch configuration may name for a card."""

    def test_an_existing_folder_by_its_full_path(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(card_folder(folder), Path(folder).resolve())

    def test_anything_else_refused(self):
        drive_root = Path(Path.cwd().anchor)
        for named in ("", "relative/folder", str(Path(__file__)), str(drive_root),
                      str(Path(tempfile.gettempdir()) / "no such folder of nxwright")):
            with self.subTest(named=named):
                with self.assertRaises(NxwrightError):
                    card_folder(named)


class GuardTest(unittest.TestCase):
    """The checks, run as functions on paths, or on a stand-in folder in
    the cases where they refuse, so that nothing is deleted if one failed."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.root = Path(self._folder.name).resolve() / "card"
        self.root.mkdir()
        self.cards = FolderCards({"sd0/": self.root})

    def tearDown(self):
        self._folder.cleanup()

    def test_paths_that_would_leave_the_card(self):
        for relative in ("../outside.txt", "a/../../outside.txt", "C:/Windows/x", "/x",
                         "\\\\server\\share\\x", "..\\outside.txt"):
            with self.subTest(relative=relative):
                with self.assertRaises(CardRefusal):
                    inside(self.root, relative)
        self.assertEqual(inside(self.root, "presets/a.cfg"), self.root / "presets" / "a.cfg")

    def test_a_link_leading_out_of_the_card(self):
        # The stand-in: a folder beside the card, where the link leads.
        outside = self.root.parent / "outside"
        outside.mkdir()
        if not _link_folder(self.root / "link", outside):
            self.skipTest("this computer makes no links to folders")
        with self.assertRaises(CardRefusal):
            inside(self.root, "link/x.txt")

    def test_the_cards_own_folder_is_never_deleted_or_renamed(self):
        # Refused before any deletion: _deletable is the one way to one.
        for path in ("sd0/", "sd0", "SD0/", "sd0/presets/.."):
            with self.subTest(path=path):
                with self.assertRaises(CardRefusal):
                    self.cards._deletable(path)
        self.assertTrue(self.root.is_dir())

    def test_a_full_folder_is_not_deleted(self):
        # The stand-in: a folder this test made, with a file in it.
        (self.root / "full").mkdir()
        (self.root / "full" / "kept.cfg").write_bytes(b"kept")
        with self.assertRaises(CardRefusal):
            self.cards.delete_folder("sd0/full/")
        self.assertEqual((self.root / "full" / "kept.cfg").read_bytes(), b"kept")

    def test_nothing_is_renamed_over(self):
        (self.root / "a.cfg").write_bytes(b"a")
        (self.root / "b.cfg").write_bytes(b"b")
        with self.assertRaises(CardRefusal):
            self.cards.rename("sd0/a.cfg", "sd0/b.cfg")
        with self.assertRaises(CardRefusal):
            self.cards.rename("sd0/a.cfg", "sd1/a.cfg")     # another card
        self.assertEqual(((self.root / "a.cfg").read_bytes(), (self.root / "b.cfg").read_bytes()),
                         (b"a", b"b"))

    def test_an_existing_file_is_left_as_it_is(self):
        (self.root / "a.cfg").write_bytes(b"kept")
        self.cards.new_file("sd0/a.cfg", 10)
        self.assertEqual((self.root / "a.cfg").read_bytes(), b"kept")


class FileCommandsTest(SimulationTestCase):
    """The app's file commands on a card given a stand-in folder, beside a
    card in memory and the RAM."""

    def setUp(self):
        super().setUp()
        self._card = tempfile.TemporaryDirectory()
        self.card = Path(self._card.name).resolve()
        self.addCleanup(self._card.cleanup)
        self.program("page page0\n")
        self.page("page0", [placed("go", "button", 0, 0), placed("t", "text", 0, 100, txt="",
                                                                txt_maxl=20),
                            table("found", "variable"), table("file", "file-stream")], """\
on go.down:
  newdir "sd0/presets/"
  newfile "sd0/presets/a.cfg",5
  file.open("sd0/presets/a.cfg")
  file.write("hello",0,5)
  file.close()
  newfile "sd0/presets/b.cfg",3
  refile "sd0/presets/b.cfg","sd0/presets/c.cfg"
  newfile "sd1/elsewhere.cfg",2
  newfile "ram/scratch.bin",4
  findfile "sd0/presets/a.cfg",found.val
  file.open("sd0/presets/a.cfg")
  file.read(t.txt,0,5)
  file.close()
""")

    def test_on_the_folder_and_in_memory(self):
        simulation = Simulation(self.root, cards={"sd0/": self.card})
        simulation.press("go")
        values = simulation.values()
        self.assertEqual(sorted(path.name for path in (self.card / "presets").iterdir()),
                         ["a.cfg", "c.cfg"])
        self.assertEqual((self.card / "presets" / "a.cfg").read_bytes(), b"hello")
        self.assertEqual((values["found.val"], values["t.txt"]), (1, "hello"))
        # sd1/, given no folder, and the RAM stay in memory.
        self.assertEqual(sorted(values["file contents"]), ["ram/scratch.bin", "sd1/elsewhere.cfg"])

    def test_a_file_read_and_written_in_steps_on_the_folder(self):
        # Each read and write moves the file stream's position, val.
        (self.card / "s.txt").write_bytes(b"ABCDEFGHIJ")
        simulation = Simulation(self.root, cards={"sd0/": self.card})
        for line in ('file.open("sd0/s.txt")', "file.read(t.txt,0,3)", "file.read(t.txt,0,3)",
                     'file.write("xy",0,2)'):
            simulation.serial_input(line)
        values = simulation.values()
        self.assertEqual((values["t.txt"], values["file.val"], values["file.qty"],
                          values["file.en"]), ("DEF", 8, 10, 1))
        self.assertEqual((self.card / "s.txt").read_bytes(), b"ABCDEFxyIJ")

    def test_an_open_of_a_file_the_folder_lacks(self):
        # It closes the file open, as the Nextion Editor's simulator closed it.
        (self.card / "s.txt").write_bytes(b"ABCDEFGHIJ")
        simulation = Simulation(self.root, cards={"sd0/": self.card})
        simulation.serial_input('file.open("sd0/s.txt")')
        simulation.serial_input('file.open("sd0/missing.txt")')
        values = simulation.values()
        self.assertEqual((values["file.val"], values["file.qty"], values["file.en"]), (0, 0, 0))
        self.assertEqual(values["file errors"], [("open", "sd0/missing.txt")])

    def test_a_file_the_folder_refuses_is_one_file_error(self):
        # A path leaving the card: the open, and a read after it, are each
        # recorded once.
        simulation = Simulation(self.root, cards={"sd0/": self.card})
        simulation.serial_input('file.open("sd0/../outside.txt")')
        simulation.serial_input("file.read(t.txt,0,1)")
        values = simulation.values()
        self.assertEqual(values["file.en"], 0)
        self.assertEqual(values["file errors"], [("open", "sd0/../outside.txt"), ("read", None)])
        # A write the disk refuses, as when another program holds the file:
        # recorded once, and the position stays.
        (self.card / "s.txt").write_bytes(b"ABCDEFGHIJ")
        simulation = Simulation(self.root, cards={"sd0/": self.card})
        simulation.serial_input('file.open("sd0/s.txt")')
        with mock.patch.object(FolderCards, "write", side_effect=PermissionError("held")):
            simulation.serial_input('file.write("xy",0,2)')
        values = simulation.values()
        self.assertEqual((values["file.val"], values["file errors"]), (0, [("write", "sd0/s.txt")]))
        self.assertEqual((self.card / "s.txt").read_bytes(), b"ABCDEFGHIJ")

    def test_a_new_file_of_a_size_that_is_not_a_number_on_the_folder(self):
        # Refused, as the Editor's simulator refused it, making no file; the
        # simulation goes on.
        simulation = Simulation(self.root, cards={"sd0/": self.card})
        simulation.serial_input('newfile "sd0/a.cfg","abc"')
        simulation.serial_input('findfile "sd0/a.cfg",found.val')
        self.assertEqual(simulation.values()["found.val"], 0)
        self.assertEqual(list(self.card.iterdir()), [])
        self.assertEqual(simulation.values()["file errors"], [("newfile", "sd0/a.cfg")])

    def test_a_new_file_of_a_size_below_0_on_the_folder(self):
        # Refused, as the Nextion Editor's simulator refused -1 and -100: an
        # invalid file operation, 0x06, no file made, and the simulation goes on.
        sent = []
        simulation = Simulation(self.root, cards={"sd0/": self.card}, sending=sent.append)
        sent.clear()
        simulation.serial_input('newfile "sd0/a.cfg",-1')
        simulation.serial_input('findfile "sd0/a.cfg",found.val')
        self.assertEqual(sent, [bytes([0x06, 0xff, 0xff, 0xff])])
        self.assertEqual(simulation.values()["found.val"], 0)
        self.assertEqual(list(self.card.iterdir()), [])
        self.assertEqual(simulation.values()["file errors"], [("newfile", "sd0/a.cfg")])

    def test_rdfile_sends_a_file_of_the_folder(self):
        # As the Nextion Editor's simulator answered: the bytes and their
        # CRC, then the success code that bkcmd 3 asks for; 0x06 alone for a
        # missing file; 0x1E for another number of arguments.
        (self.card / "rd.txt").write_bytes(b"hello123")
        sent = []
        simulation = Simulation(self.root, cards={"sd0/": self.card}, values={"bkcmd": 3},
                                sending=sent.append)
        sent.clear()
        for line in ('rdfile "sd0/rd.txt",0,5,1', 'rdfile "sd0/none.txt",0,5,0',
                     'rdfile "sd0/rd.txt",0,5'):
            simulation.serial_input(line)
        self.assertEqual(sent, [b"hello\xf6\x34", b"\x01\xff\xff\xff", b"\x06\xff\xff\xff",
                                b"\x1e\xff\xff\xff"])
        self.assertEqual((self.card / "rd.txt").read_bytes(), b"hello123")

    def test_found_and_deleted_on_the_folder(self):
        (self.card / "old").mkdir()
        (self.card / "old.cfg").write_bytes(b"x")
        simulation = Simulation(self.root, cards={"sd0/": self.card})
        simulation.serial_input('finddir "sd0/old/",found.val')
        self.assertEqual(simulation.values()["found.val"], 1)
        simulation.serial_input('delfile "sd0/old.cfg"')
        simulation.serial_input('deldir "sd0/old/"')
        simulation.serial_input('finddir "sd0/old/",found.val')
        self.assertEqual(simulation.values()["found.val"], 0)
        self.assertEqual(list(self.card.iterdir()), [])
        self.assertIsNone(simulation.globals.get("file errors"))

    def test_a_folder_in_a_missing_folder_makes_both(self):
        # As the Editor's simulator made them, answering 01.
        simulation = Simulation(self.root, cards={"sd0/": self.card})
        simulation.serial_input('newdir "sd0/none/inner/"')
        self.assertTrue((self.card / "none" / "inner").is_dir())
        self.assertIsNone(simulation.globals.get("file errors"))
        # Within the card alone.
        simulation.serial_input('newdir "sd0/../outside/"')
        self.assertEqual(simulation.globals["file errors"], [("newdir", "sd0/../outside/")])

    def test_the_answers_of_the_editors_simulator(self):
        # Each as the Editor's simulator answered it, with bkcmd 3.
        (self.card / "a.cfg").write_bytes(b"a")
        (self.card / "b.cfg").write_bytes(b"b")
        sent = []
        simulation = Simulation(self.root, cards={"sd0/": self.card}, sending=sent.append)
        simulation.serial_input("bkcmd=3")
        for text, answer in (('newfile "sd0/none/a.cfg",2', 0x06),
                             ('newfile "sd0/c.cfg","x"', 0x1b),
                             ('newfile "sd0/a.cfg",2', 0x01),
                             ('refile "sd0/none.cfg","sd0/d.cfg"', 0x06),
                             ('refile "sd0/a.cfg","sd0/b.cfg"', 0x06),
                             ('refile "sd0/a.cfg","sd0/none/a.cfg"', 0x06),
                             ('delfile "sd0/none.cfg"', 0x01),
                             ('deldir "sd0/none/"', 0x01),
                             ('findfile "sd0/none.cfg",found.val', 0x01)):
            with self.subTest(text=text):
                simulation.serial_input(text)
                self.assertEqual(sent[-1], bytes([answer]) + b"\xff\xff\xff")
        self.assertEqual(sorted(path.name for path in self.card.iterdir()), ["a.cfg", "b.cfg"])
        self.assertEqual((self.card / "a.cfg").read_bytes(), b"a")

    def test_a_size_that_is_no_number_answers_1b_on_any_card(self):
        # A card in memory refuses nothing else; this it does, as the screen.
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        simulation.serial_input("bkcmd=3")
        simulation.serial_input('newfile "sd0/c.cfg","x"')
        self.assertEqual(sent[-1], b"\x1b\xff\xff\xff")

    def test_a_refusal_by_code_answers_at_once(self):
        self.page("page0", [placed("go", "button", 0, 0), table("found", "variable")], """\
on go.down:
  refile "sd0/none.cfg","sd0/d.cfg"
  found.val = 7
""")
        sent = []
        simulation = Simulation(self.root, cards={"sd0/": self.card}, sending=sent.append)
        simulation.press("go")
        self.assertEqual(sent, [b"\x06\xff\xff\xff"])
        self.assertEqual(simulation.values()["found.val"], 7)
        # An event a typed click runs answers at once too, after the click's
        # own success, which comes before its event runs, as the Editor's
        # simulator answered.
        del sent[:]
        simulation.serial_input("bkcmd=3")
        simulation.serial_input("click go,1")
        self.assertEqual(sent, [b"\x01\xff\xff\xff", b"\x01\xff\xff\xff", b"\x06\xff\xff\xff"])

    def test_a_full_folder_is_kept_answering_as_the_screen(self):
        # The screen deletes it, answering 01. A card's folder is the user's,
        # so it is kept, and the log says so.
        (self.card / "full").mkdir()
        (self.card / "full" / "a.cfg").write_bytes(b"a")
        sent = []
        simulation = Simulation(self.root, cards={"sd0/": self.card}, sending=sent.append)
        simulation.serial_input("bkcmd=3")
        simulation.serial_input('deldir "sd0/full/"')
        self.assertEqual(sent[-1], b"\x01\xff\xff\xff")
        self.assertTrue((self.card / "full" / "a.cfg").is_file())
        self.assertEqual(simulation.globals["file errors"], [("deldir", "sd0/full/")])

    def test_both_cards_as_folders(self):
        with tempfile.TemporaryDirectory() as other:
            simulation = Simulation(self.root, cards={"sd0/": self.card, "sd1/": Path(other)})
            simulation.serial_input('newfile "sd0/a.cfg",1')
            simulation.serial_input('newfile "sd1/b.cfg",2')
            self.assertEqual([path.name for path in self.card.iterdir()], ["a.cfg"])
            self.assertEqual((Path(other) / "b.cfg").read_bytes(), bytes(2))
            self.assertEqual(simulation.values().get("file contents", {}), {})

    def test_what_the_disk_refuses_is_a_file_error(self):
        # A folder where a file of its name is: the command fails, as on the
        # screen, and the event goes on.
        (self.card / "taken").write_bytes(b"kept")
        simulation = Simulation(self.root, cards={"sd0/": self.card})
        simulation.serial_input('newdir "sd0/taken/"')
        simulation.serial_input("t.txt=\"after\"")
        self.assertEqual(simulation.globals["file errors"], [("newdir", "sd0/taken/")])
        self.assertEqual((self.card / "taken").read_bytes(), b"kept")
        self.assertEqual(simulation.values()["t.txt"], "after")

    def test_a_folder_renamed_with_what_it_holds(self):
        # As the Editor's simulator renamed one, answering 01 to bkcmd 3.
        (self.card / "old").mkdir()
        (self.card / "old" / "a.cfg").write_bytes(b"x")
        sent = []
        simulation = Simulation(self.root, cards={"sd0/": self.card}, sending=sent.append)
        simulation.serial_input("bkcmd=3")
        simulation.serial_input('redir "sd0/old/","sd0/new/"')
        self.assertEqual([path.name for path in self.card.iterdir()], ["new"])
        self.assertEqual((self.card / "new" / "a.cfg").read_bytes(), b"x")
        self.assertEqual(sent[-1], b"\x01\xff\xff\xff")
        self.assertIsNone(simulation.globals.get("file errors"))

    def test_a_folder_renaming_refused_answers_06(self):
        # As the Editor's simulator answered, with bkcmd 2: a path without
        # its "/", a folder that does not exist, a file, and a name that
        # exists. So do the cards' own refusals: the card itself, and a path
        # leaving it.
        for name in ("old", "taken"):
            (self.card / name).mkdir()
        (self.card / "a.cfg").write_bytes(b"x")
        refused = ['redir "sd0/old","sd0/new"', 'redir "sd0/none/","sd0/new/"',
                   'redir "sd0/a.cfg/","sd0/b/"', 'redir "sd0/old/","sd0/taken/"',
                   'redir "sd0/","sd0/new/"', 'redir "sd0/old/","sd0/../new/"']
        sent = []
        simulation = Simulation(self.root, cards={"sd0/": self.card}, sending=sent.append)
        for text in refused:
            with self.subTest(text=text):
                simulation.serial_input(text)
                self.assertEqual(sent[-1:], [b"\x06\xff\xff\xff"])
        self.assertEqual(len(simulation.globals["file errors"]), len(refused))
        self.assertEqual(sorted(path.name for path in self.card.iterdir()),
                         ["a.cfg", "old", "taken"])

    def test_a_refusal_is_a_file_error(self):
        simulation = Simulation(self.root, cards={"sd0/": self.card})
        simulation.serial_input('deldir "sd0/"')
        simulation.serial_input('delfile "sd0/../escape.txt"')
        self.assertEqual(simulation.globals["file errors"],
                         [("deldir", "sd0/"), ("delfile", "sd0/../escape.txt")])
        self.assertTrue(self.card.is_dir())


class TwfileTest(SimulationTestCase):
    """twfile takes its file's bytes from the serial line, as the vendor's
    instruction set describes transparent data. The Nextion Editor's
    simulator took none, and never wrote the file; what it refused is
    refused alike."""

    def setUp(self):
        super().setUp()
        self._card_folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._card_folder.cleanup)
        self.card = Path(self._card_folder.name).resolve() / "card"
        self.card.mkdir()
        self.program("int n=0\n\npage page0\n")
        self.page("page0", [placed("go", "button", 0, 0),
                            placed("t", "text", 0, 100, txt="abc", txt_maxl=20)], """\
on go.down:
  twfile "sd0/b.txt",2
""")
        self.sent = []

    def simulation(self) -> Simulation:
        simulation = Simulation(self.root, cards={"sd0/": self.card}, sending=self.sent.append)
        self.sent.clear()
        return simulation

    def log(self, simulation: Simulation) -> list:
        return [line for _, line in simulation.log]

    def test_the_files_bytes_come_from_the_serial_line(self):
        simulation = self.simulation()
        simulation.serial_received(b'twfile "sd0/w.txt",5\xff\xff\xffa\xffb\xff')
        self.assertEqual(self.sent, [READY])
        self.assertFalse((self.card / "w.txt").exists())
        # FF is data. The bytes after the fifth are an instruction.
        simulation.serial_received(b"cget n\xff\xff\xff")
        self.assertEqual(self.sent, [READY, DONE, N_IS_0])
        self.assertEqual((self.card / "w.txt").read_bytes(), b"a\xffb\xffc")
        self.assertEqual(self.log(simulation)[-6:], [
            "twfile: the next 5 bytes are the file sd0/w.txt", "sends fe ff ff ff",
            "sends fd ff ff ff", "SD card: twfile sd0/w.txt 5", "receives get n",
            "sends 71 00 00 00 00 ff ff ff (get)"])

    def test_ready_and_done_whatever_bkcmd_asks(self):
        simulation = self.simulation()
        simulation.serial_received(b'bkcmd=0\xff\xff\xfftwfile "sd0/w.txt",1\xff\xff\xff\x07')
        self.assertEqual(self.sent, [READY, DONE])

    def test_a_file_of_that_name_is_replaced(self):
        (self.card / "w.txt").write_bytes(b"old content")
        simulation = self.simulation()
        simulation.serial_received(b'twfile "sd0/w.txt",3\xff\xff\xffnew')
        self.assertEqual((self.card / "w.txt").read_bytes(), b"new")

    def test_on_the_card_in_memory(self):
        # sd1/, given no folder, keeps its files in memory.
        simulation = self.simulation()
        simulation.serial_received(b'twfile "sd1/m.bin",2\xff\xff\xff\x00\x01')
        self.assertEqual(self.sent, [READY, DONE])
        self.assertEqual(simulation.values()["file contents"], {"sd1/m.bin": b"\x00\x01"})

    def test_refusals_start_no_transfer(self):
        # As the Nextion Editor's simulator answered: 0x06 for a path on
        # neither card, a size of 0 or below, and a folder the card lacks;
        # 0x1A for a size that is no number; 0x1E for another number of
        # arguments.
        simulation = self.simulation()
        refused = ['twfile "ram/r.txt",5', 'twfile "r.txt",5', 'twfile "sd0/w.txt",0',
                   'twfile "sd0/w.txt",-1', 'twfile "sd0/none/w.txt",5',
                   'twfile "sd0/w.txt",t.txt', 'twfile "sd0/w.txt",abc', "twfile",
                   'twfile "sd0/w.txt"', 'twfile "sd0/w.txt",5,6']
        for text in refused + ["get n"]:
            simulation.serial_received(text.encode() + b"\xff\xff\xff")
        self.assertEqual(self.sent, [b"\x06\xff\xff\xff"] * 5 + [b"\x1a\xff\xff\xff"] * 2
                         + [b"\x1e\xff\xff\xff"] * 3 + [N_IS_0])
        self.assertEqual(list(self.card.iterdir()), [])
        self.assertEqual(simulation.values()["file errors"], [
            ("twfile", path) for path in ("ram/r.txt", "r.txt", "sd0/w.txt", "sd0/w.txt",
                                          "sd0/none/w.txt", "sd0/w.txt")])

    def test_a_path_leaving_the_card_starts_no_transfer(self):
        # Ignored to keep the files outside safe, as by the other file
        # commands, so bkcmd 2 answers nothing.
        simulation = self.simulation()
        simulation.serial_received(b'twfile "sd0/../out.txt",1\xff\xff\xffget n\xff\xff\xff')
        self.assertEqual(self.sent, [N_IS_0])
        self.assertFalse((self.card.parent / "out.txt").exists())
        self.assertEqual(simulation.values()["file errors"], [("twfile", "sd0/../out.txt")])

    def test_a_path_naming_a_folder_writes_nothing(self):
        # Found only once the bytes are in, after FD FF FF FF.
        (self.card / "sub").mkdir()
        simulation = self.simulation()
        simulation.serial_received(b'twfile "sd0/sub",2\xff\xff\xffhi')
        self.assertEqual(self.sent, [READY, DONE])
        self.assertEqual(list((self.card / "sub").iterdir()), [])
        self.assertEqual(simulation.values()["file errors"], [("twfile", "sd0/sub")])
        self.assertIn("SD card: twfile of sd0/sub refused", self.log(simulation))

    def test_a_transfer_cut_by_another_writes_nothing(self):
        simulation = self.simulation()
        simulation.serial_received(b'twfile "sd0/a.txt",5\xff\xff\xffab')
        simulation.press("go")
        simulation.serial_received(b"cd")
        self.assertEqual(self.sent, [READY, READY, DONE])
        self.assertEqual([path.name for path in self.card.iterdir()], ["b.txt"])
        self.assertEqual((self.card / "b.txt").read_bytes(), b"cd")
        self.assertIn("serial line: the transfer under way ends, 3 bytes short",
                      self.log(simulation))


class FileBrowserTest(SimulationTestCase):
    """File browsers, listing a folder, and a select, showing lines."""

    def setUp(self):
        super().setUp()
        self._card = tempfile.TemporaryDirectory()
        self.card = Path(self._card.name).resolve()
        self.addCleanup(self._card.cleanup)
        for name in ("foo.cfg", "Abc.cfg", "notes.txt"):
            (self.card / name).write_bytes(b"x")
        (self.card / "drawing").mkdir()
        (self.card / "drawing" / "inner.cfg").write_bytes(b"x")
        self.program("page page0\n")
        self.page("page0", [placed("files", "file-browser", 0, 0, filter="*.cfg", dir="sd0/"),
                            placed("folders", "file-browser", 200, 0, filter="*.", dir="sd0/"),
                            placed("choice", "select", 400, 0, path="one\\r\\ntwo\\r\\nthree"),
                            placed("go", "button", 0, 300), placed("back", "button", 200, 300)],
                  """\
on go.down:
  files.dir = "sd0/drawing/"

on back.down:
  files.up()
""")

    def test_listed_as_the_page_opens(self):
        simulation = Simulation(self.root, cards={"sd0/": self.card})
        values = simulation.values()
        # Folders always, then files by the filter, each in alphabetical
        # order, capitals ignored.
        self.assertEqual((values["files.qty"], values["folders.qty"]), (3, 1))
        for index, name in enumerate(["drawing/", "Abc.cfg", "foo.cfg"]):
            simulation.serial_input("files.val=%d" % index)
            self.assertEqual(simulation.values()["files.txt"], name)
        simulation.serial_input("files.val=7")
        self.assertEqual(simulation.values()["files.txt"], "")

    def test_into_a_folder_and_back_up(self):
        simulation = Simulation(self.root, cards={"sd0/": self.card})
        simulation.press("go")
        simulation.serial_input("files.val=0")
        self.assertEqual((simulation.values()["files.qty"], simulation.values()["files.txt"]),
                         (1, "inner.cfg"))
        simulation.press("back")
        self.assertEqual((simulation.values()["files.dir"], simulation.values()["files.qty"]),
                         ("sd0/", 3))
        simulation.press("back")            # no higher than the card's own folder
        self.assertEqual(simulation.values()["files.dir"], "sd0/")

    def test_up_from_a_folder_named_without_its_slash(self):
        simulation = Simulation(self.root, cards={"sd0/": self.card})
        simulation.serial_input('files.dir="sd0/drawing"')
        self.assertEqual(simulation.values()["files.qty"], 1)
        simulation.press("back")
        self.assertEqual((simulation.values()["files.dir"], simulation.values()["files.qty"]),
                         ("sd0/", 3))

    def test_a_folder_that_is_no_text_lists_nothing(self):
        simulation = Simulation(self.root, cards={"sd0/": self.card})
        simulation.serial_input("files.dir=5")
        self.assertEqual(simulation.values()["files.qty"], 0)

    def test_on_the_card_in_memory(self):
        simulation = Simulation(self.root, values={
            "existing": ["sd0/", "sd0/drawing/"],
            "file contents": {"sd0/b.cfg": b"x", "sd0/notes.txt": b"x",
                              "sd0/drawing/inner.cfg": b"x"}})
        values = simulation.values()
        self.assertEqual((values["files.qty"], values["folders.qty"]), (2, 1))
        simulation.serial_input("files.val=0")
        self.assertEqual(simulation.values()["files.txt"], "drawing/")
        simulation.press("go")
        simulation.serial_input("files.val=0")
        self.assertEqual((simulation.values()["files.qty"], simulation.values()["files.txt"]),
                         (1, "inner.cfg"))
        simulation.press("back")
        self.assertEqual((simulation.values()["files.dir"], simulation.values()["files.qty"]),
                         ("sd0/", 2))

    def test_a_selects_lines(self):
        simulation = Simulation(self.root)
        # Its `val` starts at 0, but `txt` stays as the page file gives it
        # until `val` is set; new lines leave it as it is, and so does a
        # `val` past the last line, which is refused.
        self.assertEqual(simulation.values()["choice.txt"], "")
        for text, shown in (("choice.val=1", "two"), ('choice.path="a\\rb"', "two"),
                            ("choice.val=5", "two")):
            simulation.serial_input(text)
            self.assertEqual(simulation.values()["choice.txt"], shown, text)


class ExternalPictureTest(unittest.TestCase):
    """An external picture shows the file its `path` names on a card given
    a folder; anything else draws nothing, as for a missing file."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.card = Path(folder.name).resolve() / "card"
        self.card.mkdir()
        for place in (self.card / "splash.png", self.card.parent / "outside.png"):
            place.write_bytes(write_png(4, 2, bytes(32)))
        self.cards = FolderCards({"sd0/": self.card})
        self.root = Path(folder.name) / "app"

    def drawing(self, path: str, cards, rotation: int = 0) -> dict:
        page = Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480, "sta": 1, "bco": 0})
        picture = Component("exp0", "external-picture",
                            {"x": 10, "y": 20, "w": 100, "h": 50, "path": path})
        return Previews().drawing_of(self.root, {"pictures": [], "fonts": [],
                                                 "rotation": rotation},
                                     [page, picture], cards=cards)

    def test_its_file_on_a_card_folder(self):
        drawing = self.drawing("sd0/splash.png", self.cards)
        name = str(self.card / "splash.png")
        self.assertEqual([shape for shape in drawing["shapes"] if shape["component"] == "exp0"],
                         [{"component": "exp0", "kind": "picture", "x": 10, "y": 20, "w": 100,
                           "h": 50, "picture": name, "sx": 0, "sy": 0, "rotation": 0,
                           "card": True}])
        self.assertEqual(drawing["pictureFiles"][name]["path"], name)

    def test_turned_back_by_the_screens_rotation(self):
        # Stored for a screen turned 180 degrees, the file is shown upright.
        drawing = self.drawing("sd0/splash.png", self.cards, rotation=180)
        self.assertEqual([shape["rotation"] for shape in drawing["shapes"]
                          if shape["component"] == "exp0"], [180])

    def test_a_pictureboxs_file_as_its_jpeg_and_its_mask(self):
        # The webview reads the JPEG; the alpha, which nxwright reads, comes
        # as a PNG mask of the JPEG's size.
        xi = Path(__file__).resolve().parent / "fixtures" / "media" / "xi"
        (self.card / "odd.xi").write_bytes((xi / "odd-96-0.xi").read_bytes())
        (self.card / "smooth.xi").write_bytes((xi / "smooth-96-0.xi").read_bytes())
        drawing = self.drawing("sd0/odd.xi", self.cards)
        name = str(self.card / "odd.xi")
        self.assertEqual([shape.get("card") for shape in drawing["shapes"]
                          if shape["component"] == "exp0"], [True])
        found = drawing["pictureFiles"][name]
        self.assertNotIn("path", found)
        self.assertTrue(found["data"].startswith("data:image/jpeg;base64,/9j/"))
        mask = read_picture(base64.b64decode(found["mask"].split(",", 1)[1]))
        self.assertEqual((mask.width, mask.height), (48, 32))
        # Rows 0 to 3 wholly transparent, 4 to 12 opaque, 13 to 16 half,
        # the padding past them transparent.
        self.assertEqual([mask.getpixel((0, row))[3] for row in (0, 4, 13, 20)], [0, 255, 126, 0])
        self.assertEqual(mask.getpixel((40, 4))[3], 0)
        smooth = self.drawing("sd0/smooth.xi", self.cards)["pictureFiles"]
        self.assertNotIn("mask", smooth[str(self.card / "smooth.xi")])

    def test_one_file_read_two_ways_keeps_each(self):
        # An external picture and a video naming one file: the file is read
        # as a picture for the one and as a video for the other, each kept
        # apart, so that neither is handed what the other read.
        xi = Path(__file__).resolve().parent / "fixtures" / "media" / "xi"
        (self.card / "odd.xi").write_bytes((xi / "odd-96-0.xi").read_bytes())
        page = Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480, "sta": 1, "bco": 0})
        picture = Component("exp0", "external-picture",
                            {"x": 10, "y": 20, "w": 33, "h": 17, "path": "sd0/odd.xi"})
        video = Component("video0", "video", {"x": 100, "y": 20, "w": 33, "h": 17, "from": 1,
                                              "path": "sd0/odd.xi"})
        previews = Previews()
        for order in ([page, picture, video], [page, video, picture]):
            drawing = previews.drawing_of(self.root, {"pictures": [], "fonts": [], "rotation": 0,
                                                      "videos": []}, order, cards=self.cards)
            self.assertEqual([shape["kind"] for shape in drawing["shapes"]
                              if shape["component"] == "exp0"], ["picture"])

    def test_a_damaged_pictureboxs_file_draws_nothing(self):
        (self.card / "cut.xi").write_bytes(b"hmipicxi" + bytes(30))
        drawing = self.drawing("sd0/cut.xi", self.cards)
        self.assertEqual([shape for shape in drawing["shapes"] if shape["component"] == "exp0"], [])
        self.assertEqual(drawing["pictureFiles"], {})

    def test_nothing_without_its_file(self):
        for path, cards in (("sd0/missing.png", self.cards), ("sd1/splash.png", self.cards),
                            ("sd0/../outside.png", self.cards), ("sd0/splash.png", None),
                            ("", self.cards)):
            with self.subTest(path=path, cards=cards is not None):
                drawing = self.drawing(path, cards)
                self.assertEqual([shape for shape in drawing["shapes"]
                                  if shape["component"] == "exp0"], [])
                self.assertEqual(drawing["pictureFiles"], {})


class LaunchTest(LiveTestCase):
    """`sdCard0` and `sdCard1` in a launch configuration."""

    def test_a_folder_that_will_not_do_stops_the_launch(self):
        self.request("initialize")
        reply = self.request("launch", sourceFolder=str(self.root), sdCard1="relative/folder")
        self.assertFalse(reply["success"])
        self.assertIn("full path", reply["message"])

    def test_an_external_picture_from_a_card_folder(self):
        self.page("page0", [table("exp0", "external-picture", x=0, y=0, w=800, h=480,
                                  path="sd0/splash.png")])
        with tempfile.TemporaryDirectory() as folder:
            splash = Path(folder).resolve() / "splash.png"
            splash.write_bytes(write_png(4, 2, bytes(32)))
            self.launch(sdCard0=folder)
            drawing = self.wait_for("nxwright/drawing")
            self.assertIn(("exp0", "picture", str(splash)),
                          [(shape["component"], shape["kind"], shape.get("picture"))
                           for shape in drawing["shapes"]])
            self.assertEqual(drawing["pictureFiles"][str(splash)]["path"], str(splash))
            self.request("disconnect")

    def test_the_cards_reach_the_simulation(self):
        with tempfile.TemporaryDirectory() as folder:
            self.launch(sdCard0=folder)
            self.wait_for("nxwright/drawing")
            self.assertEqual(self.adapter._live.simulation.cards.folders,
                             {"sd0/": Path(folder).resolve()})
            self.request("disconnect")


if __name__ == "__main__":
    unittest.main()
