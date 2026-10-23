"""nxwright build, write, and page: the question each asks before it
replaces a file, and --overwrite."""
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from nxwright import NxwrightError
from nxwright.cli import main, refuse_unless_replacing
from nxwright.project.page_file import write_page_file
from tests.test_new_command import answering
from tests.test_project_writer import edit_text
from tests.test_source_folder import SourceFolderTestCase


class Terminal(io.StringIO):
    """A stream that says it is a terminal, as the command's input or output."""

    def isatty(self) -> bool:
        return True


class ReplacingTest(SourceFolderTestCase):
    """The question, asked of the small test project's file."""

    def refused(self, ask) -> str:
        """Returns the refusal of replacing the project file, `ask` answering."""
        with redirect_stdout(io.StringIO()), self.assertRaises(NxwrightError) as raised:
            refuse_unless_replacing(self.project, ask)
        return str(raised.exception)

    def test_yes_replaces(self):
        for answer in ("y", " yes ", "Y"):
            with self.subTest(answer=answer):
                ask, questions = answering(answer)
                refuse_unless_replacing(self.project, ask)
                self.assertEqual(questions, ["Replace the project file %s? [y/N]: " % self.project])

    def test_no_keeps_it(self):
        for answer in ("", "n", "No"):
            with self.subTest(answer=answer):
                self.assertEqual(self.refused(answering(answer)[0]),
                                 "%s was not replaced; nothing was built" % self.project)

    def test_another_answer_is_asked_again(self):
        ask, questions = answering("maybe", "y")
        with redirect_stdout(io.StringIO()) as printed:
            refuse_unless_replacing(self.project, ask)
        self.assertEqual(len(questions), 2)
        self.assertEqual(printed.getvalue(), "Not one of the choices: y, n\n")

    def test_with_no_one_to_ask_it_is_refused(self):
        # No terminal, or an input that ends at the question.
        for ask in (None, answering()[0]):
            with self.subTest(ask=ask):
                self.assertEqual(self.refused(ask),
                                 "%s exists; pass --overwrite to replace it" % self.project)

    def test_a_page_file_is_asked_of_as_one(self):
        page_file = self.folder / "second.page"
        write_page_file(self.dump, 1, page_file)
        ask, questions = answering("y")
        refuse_unless_replacing(page_file, ask, "page file", "written")
        self.assertEqual(questions, ["Replace the page file %s? [y/N]: " % page_file])
        # A project file is no page file: the page command refuses it itself.
        ask, questions = answering()
        refuse_unless_replacing(self.project, ask, "page file", "written")
        self.assertEqual(questions, [])

    def test_a_new_output_or_another_kind_of_file_is_not_asked(self):
        # The build refuses another kind of file itself.
        notes = self.folder / "notes.txt"
        notes.write_bytes(b"keep")
        for output in (self.folder / "new.HMI", notes, self.source):
            with self.subTest(output=output):
                ask, questions = answering()
                refuse_unless_replacing(output, ask)
                self.assertEqual(questions, [])


class BuildCommandTest(SourceFolderTestCase):
    """The command, run as from a terminal, or not."""

    def run_build(self, output, *options: str, answers: str = None,
                  output_is_terminal: bool = True) -> tuple:
        """Runs `nxwright build` into `output`; returns its exit code, and what
        it printed and wrote as errors. With `answers`, its input is a
        terminal typing them; without, its input is no terminal."""
        stdin = io.StringIO() if answers is None else Terminal(answers)
        printed, errors = (Terminal() if output_is_terminal else io.StringIO()), io.StringIO()
        with mock.patch.object(sys, "stdin", stdin), redirect_stdout(printed), \
                redirect_stderr(errors):
            code = main(["build", str(self.source), str(output), *options])
        return code, printed.getvalue(), errors.getvalue()

    def test_a_new_output_is_written_without_asking(self):
        output = self.folder / "new.HMI"
        code, printed, _ = self.run_build(output, answers="")
        self.assertEqual(code, 0)
        self.assertNotIn("Replace", printed)
        self.assertTrue(output.is_file())

    def test_an_answer_at_a_terminal(self):
        before = self.project.read_bytes()
        code, printed, errors = self.run_build(self.project, answers="n\n")
        self.assertEqual((code, errors), (1, "nxwright build: %s was not replaced; nothing was "
                                             "built\n" % self.project))
        self.assertIn("Replace the project file", printed)
        self.assertEqual(self.project.read_bytes(), before)
        code, printed, _ = self.run_build(self.project, answers="y\n")
        self.assertEqual(code, 0)
        self.assertIn("Wrote %s" % self.project, printed)

    def test_refused_with_no_one_to_ask(self):
        # No terminal for its input, or its output sent to a file, where the
        # question would not be seen.
        before = self.project.read_bytes()
        refusal = "nxwright build: %s exists; pass --overwrite to replace it\n" % self.project
        for answers, output_is_terminal in ((None, True), ("y\n", False)):
            with self.subTest(answers=answers, output_is_terminal=output_is_terminal):
                code, _, errors = self.run_build(self.project, answers=answers,
                                                 output_is_terminal=output_is_terminal)
                self.assertEqual((code, errors), (1, refusal))
                self.assertEqual(self.project.read_bytes(), before)

    def test_overwrite_replaces_without_asking(self):
        code, printed, _ = self.run_build(self.project, "--overwrite")
        self.assertEqual(code, 0)
        self.assertNotIn("Replace", printed)
        self.assertIn("Wrote %s" % self.project, printed)

    def test_another_kind_of_file_is_refused_with_the_flag_too(self):
        notes = self.folder / "notes.txt"
        notes.write_bytes(b"keep")
        for options in ((), ("--overwrite",)):
            with self.subTest(options=options):
                code, _, errors = self.run_build(notes, *options)
                self.assertEqual(code, 1)
                self.assertIn("not a project file", errors)
                self.assertEqual(notes.read_bytes(), b"keep")


class WriteAndPageCommandsTest(SourceFolderTestCase):
    """nxwright write and page replace an existing file of their kind as
    build does: they ask first, --overwrite replaces it without asking, and
    with no one to ask they refuse, naming it."""

    def setUp(self):
        super().setUp()
        edit_text(self.dump / "pages" / "01-second.txt", 'txt = "bye"', 'txt = "goodbye"')
        self.page_file = self.folder / "second.page"
        write_page_file(self.dump, 1, self.page_file)

    def commands(self) -> list:
        """Each command, its arguments but its output, its output, and the
        kind of file that is. write's output is its own project, which it
        then updates in place."""
        return [("write", [str(self.project), str(self.dump)], self.project, "project file"),
                ("page", [str(self.dump), "1"], self.page_file, "page file")]

    def run_command(self, arguments: list, answers: str = None) -> tuple:
        """Runs `nxwright` with `arguments`; returns its exit code, and what it
        printed and wrote as errors. With `answers`, its input is a terminal
        typing them; without, its input is no terminal."""
        stdin = io.StringIO() if answers is None else Terminal(answers)
        printed, errors = Terminal(), io.StringIO()
        with mock.patch.object(sys, "stdin", stdin), redirect_stdout(printed), \
                redirect_stderr(errors):
            code = main(arguments)
        return code, printed.getvalue(), errors.getvalue()

    def test_an_answer_at_a_terminal(self):
        for name, arguments, output, kind in self.commands():
            with self.subTest(name):
                before = output.read_bytes()
                code, printed, errors = self.run_command([name, *arguments, str(output)],
                                                         answers="n\n")
                self.assertEqual((code, errors), (1, "nxwright %s: %s was not replaced; nothing "
                                                     "was written\n" % (name, output)))
                self.assertIn("Replace the %s %s? [y/N]" % (kind, output), printed)
                self.assertEqual(output.read_bytes(), before)
                code, _, _ = self.run_command([name, *arguments, str(output)], answers="y\n")
                self.assertEqual(code, 0)

    def test_refused_with_no_one_to_ask(self):
        for name, arguments, output, _ in self.commands():
            with self.subTest(name):
                before = output.read_bytes()
                code, _, errors = self.run_command([name, *arguments, str(output)])
                self.assertEqual((code, errors), (1, "nxwright %s: %s exists; pass --overwrite "
                                                     "to replace it\n" % (name, output)))
                self.assertEqual(output.read_bytes(), before)

    def test_overwrite_replaces_without_asking(self):
        for name, arguments, output, _ in self.commands():
            with self.subTest(name):
                code, printed, _ = self.run_command([name, *arguments, str(output),
                                                     "--overwrite"])
                self.assertEqual(code, 0)
                # write prints its changes, such as "Replaced page 1".
                self.assertNotIn("Replace the", printed)
        self.assertIn(b"goodbye", self.project.read_bytes())

    def test_another_kind_of_file_is_refused_with_the_flag_too(self):
        notes = self.folder / "notes.txt"
        notes.write_bytes(b"keep")
        for name, arguments, _, kind in self.commands():
            for options in ((), ("--overwrite",)):
                with self.subTest(name=name, options=options):
                    code, _, errors = self.run_command([name, *arguments, str(notes), *options])
                    self.assertEqual(code, 1)
                    self.assertIn("not a %s" % kind, errors)
                    self.assertEqual(notes.read_bytes(), b"keep")


class SaysWhatItWroteTest(SourceFolderTestCase):
    """dump and page print the path they wrote, as build and import do."""

    def test_dump_and_page(self):
        dumped, page_file = self.folder / "again", self.folder / "first.page"
        for arguments, output in ((["dump", str(self.project), str(dumped)], dumped),
                                  (["page", str(self.dump), "0", str(page_file)], page_file)):
            with self.subTest(arguments[0]):
                printed = io.StringIO()
                with redirect_stdout(printed):
                    code = main(arguments)
                self.assertEqual((code, printed.getvalue()), (0, "Wrote %s\n" % output))


class NewCommandTest(unittest.TestCase):

    def test_with_its_output_sent_to_a_file_new_asks_nothing(self):
        # Its question would not be seen: the defaults apply, and a missing
        # screen model is refused, as with no terminal.
        errors = io.StringIO()
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(sys, "stdin", Terminal("NX4832T035\n")), \
                redirect_stdout(io.StringIO()) as printed, redirect_stderr(errors):
            code = main(["new", str(Path(folder) / "clock")])
        self.assertEqual((code, printed.getvalue()), (1, ""))
        self.assertEqual(errors.getvalue(), "nxwright new: no screen model: give one with "
                                            "--screen\n")


if __name__ == "__main__":
    unittest.main()
