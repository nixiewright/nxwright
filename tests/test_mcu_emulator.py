"""A project's MCU emulator: app.toml's [mcu] table (source/mcu_table.py),
and add_emulator and `nxwright new-emulator`, which write a first program
(source/emulator_adding.py)."""
import contextlib
import io
import socket
import subprocess
import sys
import tomllib
from pathlib import Path

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.source.emulator_adding import DEFAULT_EMULATOR, add_emulator
from nxwright.source.mcu_table import emulator_wait
from nxwright.source.project_files import build
from nxwright.source.source_folder import add_page, app_text_in, parse_app, read_app
from tests.test_folder_check import FolderTestCase
from tests.test_mcu_library import _PATIENCE, free_port

END = b"\xff\xff\xff"


class McuTableTest(FolderTestCase):
    """The folder of FolderTestCase, with an [mcu] table added to app.toml."""

    def with_table(self, table: str):
        self.write("app.toml", self.text("app.toml") + "\n[mcu]\n" + table)

    def assertRefused(self, table: str, words: str):
        self.with_table(table)
        with self.assertRaises(NxwrightError) as raised:
            read_app(self.root)
        self.assertEqual(str(raised.exception), "app.toml: " + words)

    def test_the_table_is_read(self):
        self.with_table('emulator = "../mcu/main.py"\n')
        self.assertEqual(read_app(self.root)["mcu"], {"emulator": "../mcu/main.py"})

    def test_a_folder_without_the_table_reads_as_before(self):
        self.assertNotIn("mcu", read_app(self.root))

    def test_a_key_the_table_does_not_have_is_refused(self):
        self.assertRefused('emulator = "../mcu/main.py"\ncommand = "python"\n',
                           "unknown key command in [mcu]")

    def test_the_emulator_must_be_a_path_with_forward_slashes(self):
        words = ("emulator in [mcu] must be the path of the emulator's Python file from the "
                 "source folder, with forward slashes, such as \"../mcu/main.py\"")
        for table in ("", 'emulator = ""\n', "emulator = 7000\n",
                      "emulator = '..\\mcu\\main.py'\n"):
            with self.subTest(table=table):
                original = self.text("app.toml")
                self.assertRefused(table, words)
                self.write("app.toml", original)

    def test_the_wait_for_the_emulator_is_ten_seconds_unless_given(self):
        self.with_table('emulator = "../mcu/main.py"\n')
        self.assertEqual(emulator_wait(read_app(self.root)["mcu"]), 10)
        self.assertEqual(emulator_wait({}), 10)
        for written, wait in (("30", 30), ("0", 0), ("2.5", 2.5), ("1e12", 1e12)):
            with self.subTest(wait=written):
                self.write("app.toml", self.text("app.toml") + "wait = %s\n" % written)
                mcu = read_app(self.root)["mcu"]
                self.assertEqual(mcu, {"emulator": "../mcu/main.py", "wait": wait})
                self.assertEqual(emulator_wait(mcu), wait)
                self.write("app.toml", self.text("app.toml").replace("wait = %s\n" % written, ""))

    def test_the_wait_must_be_a_number_of_seconds(self):
        words = "wait in [mcu] must be a number of seconds, 0 or more, such as 10"
        for wait in ("-1", '"10"', "true", "inf", "nan"):
            with self.subTest(wait=wait):
                original = self.text("app.toml")
                self.assertRefused('emulator = "../mcu/main.py"\nwait = %s\n' % wait, words)
                self.write("app.toml", original)

    def test_mcu_must_be_a_table(self):
        self.write("app.toml", 'mcu = "../mcu/main.py"\n' + self.text("app.toml"))
        with self.assertRaises(NxwrightError) as raised:
            read_app(self.root)
        self.assertEqual(str(raised.exception), "app.toml: mcu must be a table, as in [mcu]")

    def test_a_command_that_rewrites_app_toml_keeps_the_table(self):
        self.with_table('emulator = "../mcu/main.py"\nwait = 30\n')
        add_page(self.root, "settings")
        app = read_app(self.root)
        self.assertEqual(app["pages"][-1], "settings")
        self.assertEqual(app["mcu"], {"emulator": "../mcu/main.py", "wait": 30})

    def test_the_table_is_written_before_the_defines(self):
        self.write("app.toml", self.text("app.toml") + "\n[defines]\nLIMIT = 30\n")
        app = parse_app(self.text("app.toml"))
        text = app_text_in(self.root, dict(app, mcu={"emulator": "../mcu/main.py"}))
        self.assertLess(text.index("[mcu]"), text.index("[defines]"))
        self.assertEqual(parse_app(text)["defines"], {"LIMIT": 30})
        self.assertEqual(parse_app(text)["mcu"], {"emulator": "../mcu/main.py"})

    def test_a_folder_without_the_table_is_written_as_before(self):
        before = self.text("app.toml")
        self.assertEqual(app_text_in(self.root, parse_app(before)), before)

    def test_the_build_does_not_read_the_table(self):
        without, with_table = self.root.parent / "without.HMI", self.root.parent / "with.HMI"
        build(self.root, without)
        self.with_table('emulator = "../mcu/main.py"\n')
        build(self.root, with_table)
        self.assertEqual(with_table.read_bytes(), without.read_bytes())


class AddEmulatorTest(FolderTestCase):

    def test_it_writes_the_program_and_names_it_in_app_toml(self):
        file = add_emulator(self.root)
        self.assertEqual(file, (self.root.parent / "mcu" / "main.py").resolve())
        self.assertIn("from nxwright import mcu", file.read_text(encoding="utf-8"))
        self.assertEqual(tomllib.loads(self.text("app.toml"))["mcu"],
                         {"emulator": DEFAULT_EMULATOR})

    def test_another_file_can_be_given(self):
        file = add_emulator(self.root, "emulator/thermostat.py")
        self.assertEqual(file, (self.root / "emulator" / "thermostat.py").resolve())
        self.assertEqual(read_app(self.root)["mcu"], {"emulator": "emulator/thermostat.py"})

    def test_a_folder_that_has_an_emulator_is_refused(self):
        add_emulator(self.root)
        before = self.text("app.toml")
        with self.assertRaises(NxwrightError) as raised:
            add_emulator(self.root, "other/main.py")
        self.assertEqual(str(raised.exception),
                         "app.toml already has an [mcu] table, for the emulator ../mcu/main.py")
        self.assertEqual(self.text("app.toml"), before)
        self.assertFalse((self.root / "other").exists())

    def test_a_file_already_there_is_refused_and_nothing_is_written(self):
        existing = self.root.parent / "mcu" / "main.py"
        existing.parent.mkdir()
        existing.write_text("# mine\n", encoding="utf-8")
        before = self.text("app.toml")
        with self.assertRaises(NxwrightError) as raised:
            add_emulator(self.root)
        self.assertEqual(str(raised.exception), "%s is already there" % existing.resolve())
        self.assertEqual(existing.read_text(encoding="utf-8"), "# mine\n")
        self.assertEqual(self.text("app.toml"), before)

    def test_a_path_the_table_cannot_have_is_refused_and_nothing_is_written(self):
        before = self.text("app.toml")
        with self.assertRaises(NxwrightError):
            add_emulator(self.root, "..\\mcu\\main.py")
        self.assertEqual(self.text("app.toml"), before)
        self.assertFalse((self.root.parent / "mcu").exists())

    def test_the_subcommand(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["new-emulator", str(self.root)]), 0)
        file = (self.root.parent / "mcu" / "main.py").resolve()
        self.assertEqual(output.getvalue(),
                         "Added the MCU emulator %s to %s\n" % (file, self.root))
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            self.assertEqual(main(["new-emulator", str(self.root), "again/main.py"]), 1)
        self.assertIn("nxwright new-emulator: app.toml already has an [mcu] table",
                      errors.getvalue())


class FirstEmulatorTest(FolderTestCase):
    """The program add_emulator writes, run with a port number to listen on,
    with the test in the simulator's place."""

    def test_it_listens_takes_the_screens_messages_and_ends_with_the_simulation(self):
        file = add_emulator(self.root)
        port = free_port()
        program = subprocess.Popen([sys.executable, str(file), str(port)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   cwd=Path(__file__).resolve().parent.parent)
        self.addCleanup(program.kill)
        self.assertEqual(program.stdout.readline(),
                         "Waiting for the simulator on 127.0.0.1:%d\n" % port)
        simulation = socket.create_connection(("127.0.0.1", port), timeout=_PATIENCE)
        with simulation:
            # The screen's start-up code and "ready", then a touch event.
            simulation.sendall(b"\x00\x00\x00" + END + b"\x88" + END + b"\x65\x00\x02\x01" + END)
        _, errors = program.communicate(timeout=_PATIENCE)
        self.assertEqual((program.returncode, errors), (0, ""))
