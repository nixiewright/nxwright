"""The probe runner (tools/tft/probing/probe_runner.py): what it records, keeps,
and deletes, and the first probes (tools/tft/probing/first_probes.py).

A fake tool stands in for nxwright's Editor tool, writing the bytes a test
gives as the Nextion Editor's file. build/ and tests/fixtures/ are folders
of each test's own, deleted after it.
"""
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

from nxwright import NxwrightError

from nxwright.tft import firmware as tft_firmware
from tools.tft.probing import component_probes, first_probes, packaging_probes, probe_runner
from tools.tft import probe as probe_command
from tools.tft.probing.probe_runner import (EditorTool, Probe, ProbeError, ProbeMismatch, drop,
                                        kept_from_the_editor, refuse_unless_deletable,
                                        run_probes)
from nxwright.tft.tft_file import firmware_names, read_tft
from tests.tft.made_tft import made_tft, made_user_code
from tests.tft.stand_in_firmware import stand_in_firmware, write_editor_folder


class FakeTool:
    """Writes `editor_bytes` as the Nextion Editor's file of any project, in
    the folder given, as the Editor names it, and counts its calls. Its
    calls numbered in `refused`, from 1, stop as the Editor tool stops when
    the Nextion Editor refuses a project. It counts the times it is asked to
    close the Editor's messages too."""

    def __init__(self, editor_bytes: bytes = b"tft", refused: frozenset = frozenset()):
        self.editor_bytes = editor_bytes
        self.refused = refused
        self.calls = 0
        self.closings = 0

    def write_tft(self, project: Path, folder: Path) -> Path:
        self.calls += 1
        if self.calls in self.refused:
            raise ProbeError("the Editor tool's tft command: the Editor asks 'Error': "
                             "Invalid Pic ID")
        folder.mkdir(parents=True, exist_ok=True)
        file = folder / "probe.tft"
        file.write_bytes(self.editor_bytes)
        return file

    def close_messages(self) -> str:
        self.closings += 1
        return "Closed 1 message:\n- 'Error': Invalid Pic ID"


class FolderPathsTest(unittest.TestCase):
    """The runner's files are in its tool's folder, and the fixtures in the
    tests', wherever the work starts from."""

    def test_folders_of_the_tool_and_the_tests(self):
        nxwright_folder = Path(__file__).resolve().parents[2]
        tool = nxwright_folder / "tools" / "tft"
        self.assertTrue((tool / "probe.py").is_file())
        self.assertEqual(probe_runner.BUILD, tool / "build")
        self.assertEqual(probe_runner.FIXTURES, nxwright_folder / "tests" / "tft" / "fixtures")
        self.assertEqual(probe_runner.BASES, tool / "probes")


class RunnerTestCase(unittest.TestCase):
    """Points build/ and tests/fixtures/ at folders of the test's own, and
    builds each probe's project as `projects` gives its bytes, by name, so
    that a test can change a probe's project without nxwright."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        # Resolved, as the runner compares build/ with its resolved self.
        self.root = Path(folder.name).resolve()
        self.build = self.root / "build"
        self.fixtures = self.root / "fixtures"
        self.projects = {}
        for patch in (mock.patch.object(probe_runner, "BUILD", self.build),
                      mock.patch.object(probe_runner, "FIXTURES", self.fixtures),
                      mock.patch.object(probe_runner, "_built", self.fake_built)):
            patch.start()
            self.addCleanup(patch.stop)

    def fake_built(self, probe: Probe, work: Path) -> Path:
        project = work / "probe.HMI"
        project.write_bytes(self.projects.get(probe.name, b"project"))
        return project

    def probe(self, ours: dict, theirs=None, fixtures="phase", name="p"):
        """A probe whose nxwright output is `ours`, and whose pieces cut from the
        Nextion Editor's file are `theirs`, or else the same as `ours`."""
        def cut(data: bytes) -> dict:
            return dict(ours if theirs is None else theirs)
        return Probe(name, "T", None, lambda project: dict(ours), cut, fixtures)

    def run_quietly(self, probes, tool, again=frozenset()):
        return run_probes(probes, tool, again, say=lambda line: None)

    def fixture(self, name="p", piece="code") -> Path:
        return self.fixtures / "phase" / name / (piece + ".bin")

    def kept(self, name="p") -> Path:
        return self.build / "kept" / (name + ".tft")


class MatchTest(RunnerTestCase):
    """A probe whose pieces match keeps them as fixtures, is recorded, and
    its TFT file is deleted."""

    def test_its_fixtures_and_record_and_no_tft_file(self):
        result = self.run_quietly([self.probe({"code": b"ab"})], FakeTool())
        self.assertEqual(result.matched, ["p"])
        self.assertEqual(self.fixture().read_bytes(), b"ab")
        self.assertEqual(list((self.build / "tft").iterdir()), [])
        self.assertEqual(probe_runner._read_record(), {"p": sha256(b"project").hexdigest()})

    def test_one_that_keeps_no_fixtures(self):
        self.run_quietly([self.probe({"code": b"ab"}, fixtures=None)], FakeTool())
        self.assertFalse(self.fixtures.exists())

    def test_a_match_after_a_mismatch_deletes_the_kept_file(self):
        self.run_quietly([self.probe({"code": b"ab"}, {"code": b"aX"})], FakeTool())
        self.assertTrue(self.kept().exists())
        self.run_quietly([self.probe({"code": b"ab"})], FakeTool())
        self.assertFalse(self.kept().exists())


class SkipTest(RunnerTestCase):
    """A recorded probe is skipped, unless its project, or nxwright's output for
    it, changed, or the run is told to check it again."""

    def setUp(self):
        super().setUp()
        self.run_quietly([self.probe({"code": b"ab"})], FakeTool())

    def test_unchanged(self):
        tool = FakeTool()
        result = self.run_quietly([self.probe({"code": b"ab"})], tool)
        self.assertEqual((result.skipped, tool.calls), (["p"], 0))

    def test_the_compile_output_changed(self):
        tool = FakeTool()
        result = self.run_quietly([self.probe({"code": b"ac"})], tool)
        self.assertEqual((result.matched, tool.calls), (["p"], 1))
        self.assertEqual(self.fixture().read_bytes(), b"ac")

    def test_project_changed(self):
        self.projects["p"] = b"another project"
        tool = FakeTool()
        self.run_quietly([self.probe({"code": b"ab"})], tool)
        self.assertEqual(tool.calls, 1)

    def test_again(self):
        tool = FakeTool()
        probes = [self.probe({"code": b"ab"}), self.probe({}, name="q")]
        result = self.run_quietly(probes, tool, again={"p"})
        self.assertEqual((result.matched, tool.calls), (["p", "q"], 2))
        result = self.run_quietly(probes, FakeTool(), again={"q"})
        self.assertEqual((result.skipped, result.matched), (["p"], ["q"]))

    def test_again_a_probe_not_there(self):
        with self.assertRaisesRegex(ProbeError, "no probe is named r"):
            self.run_quietly([self.probe({})], FakeTool(), again={"r"})


class MismatchTest(RunnerTestCase):
    """A probe that does not match keeps the Nextion Editor's file, under its
    own name, until it matches or is dropped, and gets no fixture or
    record."""

    def test_a_piece_that_differs(self):
        lines = []
        result = run_probes([self.probe({"code": b"ab"}, {"code": b"aX"})], FakeTool(b"file"),
                            say=lines.append)
        self.assertEqual(result.failed, ["p"])
        self.assertIn("code first differs at byte 1 of 2", lines[0])
        self.assertEqual(self.kept().read_bytes(), b"file")
        self.assertFalse(self.fixture().exists())
        self.assertEqual(probe_runner._read_record(), {})

    def test_the_first_piece_that_differs_in_the_probe_s_order(self):
        # A whole file's pieces come in the file's order. Its checksum, last,
        # differs whenever another piece does, so it says nothing of where.
        lines = []
        run_probes([self.probe({"header-1": b"ab", "checksum": b"cd"},
                               {"header-1": b"aX", "checksum": b"cY"})], FakeTool(b"file"),
                   say=lines.append)
        self.assertIn("header-1 first differs at byte 1 of 2", lines[0])

    def test_a_file_the_probe_cannot_read(self):
        def unreadable(data: bytes) -> dict:
            raise ProbeMismatch("the checksum at 0xC4 does not hold")
        probe = Probe("p", "T", None, lambda project: {}, unreadable)
        lines = []
        result = run_probes([probe], FakeTool(), say=lines.append)
        self.assertEqual(result.failed, ["p"])
        self.assertIn("the checksum at 0xC4 does not hold", lines[0])
        self.assertTrue(self.kept().exists())

    def test_a_matched_probe_that_stops_matching_leaves_the_record(self):
        self.run_quietly([self.probe({"code": b"ab"})], FakeTool())
        self.run_quietly([self.probe({"code": b"ac"}, {"code": b"ab"})], FakeTool())
        self.assertEqual(probe_runner._read_record(), {})

    def test_the_compile_failing_keeps_the_file(self):
        def failing(project: Path) -> dict:
            raise RuntimeError("not written yet")
        probe = Probe("p", "T", None, failing, lambda data: {})
        with self.assertRaises(RuntimeError):
            self.run_quietly([probe], FakeTool())
        self.assertTrue(self.kept().exists())

    def test_the_compile_refusing_the_project_keeps_the_file(self):
        # As when the compile refuses what the probe's project holds, the
        # probe could not run, and the run goes on.
        def refused(project: Path) -> dict:
            raise NxwrightError("nxwright does not compile these")
        probes = [Probe("p", "T", None, refused, lambda data: {}),
                  self.probe({"code": b"ab"}, name="q")]
        tool = FakeTool()
        result = self.run_quietly(probes, tool)
        self.assertEqual(result.could_not_run, {"p": "nxwright does not compile these"})
        self.assertEqual(result.matched, ["q"])
        self.assertTrue(self.kept().exists())
        # The Nextion Editor wrote its file, so it shows no message to close.
        self.assertEqual(tool.closings, 0)

    def test_drop(self):
        self.run_quietly([self.probe({"code": b"ab"}, {"code": b"aX"})], FakeTool())
        self.assertTrue(drop("p"))
        self.assertFalse(self.kept().exists())
        self.assertFalse(drop("p"))
        self.assertFalse(drop("../p"))

    def test_a_fixture_of_a_piece_no_longer_given(self):
        stale = self.fixture(piece="old")
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"x")
        with self.assertRaisesRegex(ProbeError, "old.bin"):
            self.run_quietly([self.probe({"code": b"ab"})], FakeTool())
        self.assertTrue(self.kept().exists())
        self.assertEqual(list((self.build / "tft").iterdir()), [])
        self.assertFalse(self.fixture().exists())


class CouldNotRunTest(RunnerTestCase):
    """A probe that cannot run is listed apart, with why, and the run goes on
    with the next probe. The Nextion Editor's messages are closed first, as
    one left open stops every later command of the Editor tool."""

    def test_the_editor_refusing_a_project(self):
        tool = FakeTool(refused={1})
        lines = []
        result = run_probes([self.probe({"code": b"ab"}, name="p"),
                             self.probe({"code": b"cd"}, name="q")], tool, say=lines.append)
        why = ("the Editor tool's tft command: the Editor asks 'Error': Invalid Pic ID\nClosed 1 "
               "message:\n- 'Error': Invalid Pic ID")
        self.assertEqual(result.could_not_run, {"p": why})
        self.assertEqual((result.matched, result.failed), (["q"], []))
        self.assertEqual(tool.closings, 1)
        self.assertEqual(lines[0], "p: could not run: " + why)
        self.assertEqual(probe_runner._read_record(), {"q": sha256(b"project").hexdigest()})
        self.assertFalse(self.kept("p").exists())

    def test_a_firmware_file_missing(self):
        # The firmware is read as nxwright's output is made (probe_firmware), here
        # from a folder of the Editor that NXWRIGHT_EDITOR names, without P's
        # second firmware file, as the releases before 1.68.1 lack it.
        editor = write_editor_folder(self.root / "editor")
        (editor / "cdx.dll").unlink()
        probes = [Probe("p", "P", None, lambda project: packaging_probes.probe_firmware("P"),
                        lambda data: {}),
                  self.probe({"code": b"ab"}, name="q")]
        with mock.patch.dict(os.environ, {"NXWRIGHT_EDITOR": str(editor / "NextionEditor.exe")}), \
                mock.patch.object(tft_firmware, "program_version",
                                  lambda program: (1, 67, 1, 0)):
            result = self.run_quietly(probes, FakeTool())
        self.assertEqual(list(result.could_not_run), ["p"])
        self.assertRegex(result.could_not_run["p"], r"^the Nextion Editor that NXWRIGHT_EDITOR "
                                                    r"names's cdx\.dll could not be read: ")
        self.assertEqual(result.matched, ["q"])

    def test_nxwright_refusing_the_probe_s_project(self):
        def refused(probe: Probe, work: Path) -> Path:
            raise NxwrightError("page0.toml: type text has no attribute disup")
        with mock.patch.object(probe_runner, "_built", refused):
            result = self.run_quietly([self.probe({"code": b"ab"})], FakeTool())
        self.assertEqual(result.could_not_run,
                         {"p": "page0.toml: type text has no attribute disup"})


class PiecesTest(RunnerTestCase):
    """A probe's pieces.json gives where each piece of its fixtures lies: as
    its parts give them (Parts), or each part as one piece; and where each
    of its components lies, as its parts give them. Pieces that do not put
    each part back together are refused."""

    def cut_probe(self, pieces: dict = None, parts: dict = None,
                  places: dict = None) -> Probe:
        # nxwright's output is the part "code", 4 bytes, cut as `pieces` gives.
        parts = {"code": b"abcd"} if parts is None else parts
        return Probe("p", "T", None, lambda project: probe_runner.Parts(parts, pieces, places),
                     lambda data: dict(parts), "phase")

    def table(self) -> Path:
        return self.fixtures / "phase" / "p" / "pieces.json"

    def read_table(self, kind: str = "pieces") -> dict:
        return json.loads(self.table().read_text(encoding="utf-8"))[kind]

    def test_where_each_piece_lies(self):
        pieces = {"first": ("code", 0, 1), "rest": ("code", 1, 4)}
        self.run_quietly([self.cut_probe(pieces)], FakeTool())
        self.assertEqual(self.read_table(), {"first": ["code", 0, 1], "rest": ["code", 1, 4]})
        self.assertEqual(self.fixture().read_bytes(), b"abcd")

    def test_where_each_component_lies(self):
        # As its parts give it, and none for parts that give none.
        place = {"page": 0, "object_id": 1, "first_entry": 33, "page_entry": 0, "base": 28}
        self.run_quietly([self.cut_probe({"code": ("code", 0, 4)}, places={"page0-1": place})],
                         FakeTool())
        self.assertEqual(self.read_table("places"), {"page0-1": place})
        self.table().unlink()
        probe_runner.cut_probes([self.cut_probe()], say=lambda line: None)
        self.assertEqual(self.read_table("places"), {})

    def test_each_part_one_piece(self):
        # An empty part has no piece.
        self.run_quietly([self.cut_probe(parts={"code": b"ab", "data": b"xyz", "after": b""})],
                         FakeTool())
        self.assertEqual(self.read_table(), {"code": ["code", 0, 2], "data": ["data", 0, 3]})

    def test_pieces_that_do_not_give_their_part(self):
        # A gap, an overlap, one past the end, an empty one, the end left
        # out, and a part the probe does not give.
        for pieces, words in (({"a": ("code", 0, 1), "b": ("code", 2, 4)}, "does not follow"),
                              ({"a": ("code", 0, 2), "b": ("code", 1, 4)}, "does not follow"),
                              ({"a": ("code", 0, 5)}, "does not follow"),
                              ({"a": ("code", 0, 0), "b": ("code", 0, 4)}, "does not follow"),
                              ({"a": ("code", 0, 3)}, "end at 3 of its 4"),
                              ({"a": ("data", 0, 4)}, "not one of its parts")):
            probe = self.cut_probe(pieces)
            with self.subTest(pieces), self.assertRaisesRegex(ProbeError, words):
                probe_runner.piece_table(probe, probe.ours(None))

    def test_refused_pieces_keep_no_fixtures(self):
        with self.assertRaisesRegex(ProbeError, "does not follow"):
            self.run_quietly([self.cut_probe({"a": ("code", 0, 9)})], FakeTool())
        self.assertFalse(self.fixture().exists())
        self.assertFalse(self.table().exists())

    def test_the_cut_of_probes_kept_before(self):
        # Kept without pieces.json; the cut writes it, and leaves the part.
        self.fixture().parent.mkdir(parents=True)
        self.fixture().write_bytes(b"abcd")
        probe = self.cut_probe({"first": ("code", 0, 1), "rest": ("code", 1, 4)})
        result = probe_runner.cut_probes([probe], say=lambda line: None)
        self.assertEqual((result.cut, result.failed), (["p"], {}))
        self.assertEqual(self.read_table(), {"first": ["code", 0, 1], "rest": ["code", 1, 4]})
        self.assertEqual(self.fixture().read_bytes(), b"abcd")

    def test_the_cut_writes_nothing_for_a_probe_that_fails(self):
        # nxwright's output is no longer its fixtures; then its pieces do not
        # give its part.
        self.fixture().parent.mkdir(parents=True)
        self.fixture().write_bytes(b"abcX")
        for probe, words in ((self.cut_probe(), "not its fixtures"),
                             (self.cut_probe({"a": ("code", 0, 1)},
                                             parts={"code": b"abcX"}), "end at 1 of its 4")):
            with self.subTest(words):
                result = probe_runner.cut_probes([probe], say=lambda line: None)
                self.assertEqual(result.cut, [])
                self.assertIn(words, result.failed["p"])
                self.assertFalse(self.table().exists())


class BorrowTest(RunnerTestCase):
    """A probe that borrows a piece of the Nextion Editor's file gets it in
    ours, and keeps fixtures made by kept alone, which borrows nothing."""

    def borrowing(self, kept=None, fixtures="phase") -> Probe:
        # nxwright's output borrows the file's first 3 bytes, as packaging
        # borrows the Nextion Editor's user code.
        return Probe("p", "T", None, lambda project, borrowed: {"code": borrowed + b"!"},
                     lambda data: {"code": data[:3] + b"!"}, fixtures, kept,
                     borrows=lambda data: data[:3])

    def test_ours_gets_what_it_borrows(self):
        result = self.run_quietly([self.borrowing(fixtures=None)], FakeTool(b"tft file"))
        self.assertEqual(result.matched, ["p"])

    def test_its_fixtures_are_kept_s(self):
        probe = self.borrowing(kept=lambda project: {"code": b"own"})
        self.run_quietly([probe], FakeTool(b"tft file"))
        self.assertEqual(self.fixture().read_bytes(), b"own")
        # Checked again with the Nextion Editor's file gone, through kept.
        tool = FakeTool(b"tft file")
        self.assertEqual(self.run_quietly([probe], tool).skipped, ["p"])
        self.assertEqual(tool.calls, 0)

    def test_fixtures_without_kept_are_refused(self):
        tool = FakeTool()
        with self.assertRaisesRegex(ProbeError, "must make them with kept: p"):
            self.run_quietly([self.borrowing()], tool)
        self.assertEqual(tool.calls, 0)

    def test_ours_failing_is_not_the_file_failing(self):
        # A ProbeMismatch nxwright's own output raises is no fault of the
        # Nextion Editor's file, so it is raised, not reported as one.
        def failing(project: Path, borrowed) -> dict:
            raise ProbeMismatch("nxwright's own")
        probe = Probe("p", "T", None, failing, lambda data: {}, borrows=lambda data: data)
        with self.assertRaisesRegex(ProbeMismatch, "nxwright's own"):
            self.run_quietly([probe], FakeTool())
        self.assertTrue(self.kept().exists())

    def test_a_file_it_cannot_borrow_from(self):
        def unreadable(data: bytes):
            raise ProbeMismatch("no user code")
        probe = Probe("p", "T", None, lambda project, borrowed: {}, lambda data: {},
                      borrows=unreadable)
        lines = []
        result = run_probes([probe], FakeTool(), say=lines.append)
        self.assertEqual(result.failed, ["p"])
        self.assertIn("could not be read: no user code", lines[0])
        self.assertTrue(self.kept().exists())


class KeptFromTheEditorTest(RunnerTestCase):
    """Probes of an older Nextion Editor, whose files nxwright does not write:
    the Editor's file is kept as the probe's fixtures, by the probe's own
    cut, compared with nothing (kept_from_the_editor)."""

    # A file of the Nextion Editor 1.63.3, as its user code starts.
    OLDER = made_tft("T", made_user_code(first_blocks=[bytes(4), bytes(16), b"page 0"]),
                     version=(1, 63, 3), macros_unset=True, first_blocks=3)

    def older_probe(self, fixtures="editor"):
        return Probe("p", "T", None, None, lambda data: {"code": data[:5]}, fixtures)

    def keep_quietly(self, probes, tool, version=(1, 63, 3)):
        return kept_from_the_editor(probes, tool, version, say=lambda line: None)

    def test_its_fixtures_and_no_tft_file_or_record(self):
        self.keep_quietly([self.older_probe()], FakeTool(self.OLDER))
        self.assertEqual((self.fixtures / "editor" / "p" / "code.bin").read_bytes(),
                         self.OLDER[:5])
        self.assertEqual(list((self.build / "tft").glob("*.tft")), [])
        self.assertFalse((self.build / "probes.json").exists())

    def test_a_file_of_another_version(self):
        # As when NXWRIGHT_EDITOR names another Nextion Editor than meant.
        with self.assertRaisesRegex(ProbeError, "1.68.2"):
            self.keep_quietly([self.older_probe()], FakeTool(made_tft("T")))
        self.assertFalse((self.fixtures / "editor").exists())

    def test_nothing_kept_when_a_later_file_is_of_another_version(self):
        # Every file is checked before any probe's fixtures are written.
        files = [self.OLDER, made_tft("T")]

        class TwoFiles(FakeTool):
            def write_tft(self, project, folder):
                self.editor_bytes = files[self.calls]
                return super().write_tft(project, folder)
        first, second = self.older_probe(), self.older_probe()
        second = Probe("q", "T", None, None, second.theirs, "editor")
        with self.assertRaises(ProbeError):
            self.keep_quietly([first, second], TwoFiles())
        self.assertFalse((self.fixtures / "editor").exists())

    def test_cut_refuses_them(self):
        with self.assertRaisesRegex(ProbeError, "nothing of nxwright's"):
            probe_runner.cut_probes([self.older_probe()], say=lambda line: None)

    def test_a_probe_that_keeps_no_fixtures(self):
        tool = FakeTool(self.OLDER)
        with self.assertRaises(ProbeError):
            self.keep_quietly([self.older_probe(fixtures=None)], tool)
        self.assertEqual(tool.calls, 0)

    def test_the_keep_command(self):
        # It gives the probe module's probes and the version, as numbers.
        with (mock.patch.object(probe_command, "EditorTool", mock.MagicMock()),
              mock.patch.object(probe_command, "kept_from_the_editor") as kept,
              mock.patch("sys.stdout", io.StringIO())):
            code = probe_command.main(["keep", "first_probes", "--version", "1.63.3"])
        self.assertEqual(code, 0)
        self.assertEqual(kept.call_args.args[2], (1, 63, 3))
        self.assertEqual([probe.name for probe in kept.call_args.args[0]],
                         [probe.name for probe in first_probes.PROBES])

    def test_run_refuses_a_probe_with_nothing_to_compare(self):
        tool = FakeTool(self.OLDER)
        with self.assertRaisesRegex(ProbeError, "nothing of nxwright's"):
            self.run_quietly([self.older_probe()], tool)
        self.assertEqual(tool.calls, 0)


class NameTest(RunnerTestCase):
    """Probe and piece names name files, so the runner refuses others."""

    def test_refused_before_anything_runs(self):
        tool = FakeTool()
        for names in (["a/b"], ["..", "x"], ["p", "p"]):
            with self.subTest(names=names), self.assertRaises(ProbeError):
                self.run_quietly([self.probe({}, name=name) for name in names], tool)
        with self.assertRaises(ProbeError):
            self.run_quietly([self.probe({}, fixtures="../phase")], tool)
        self.assertEqual(tool.calls, 0)

    def test_a_piece_name(self):
        with self.assertRaises(ProbeError):
            self.run_quietly([self.probe({"../code": b"ab"})], FakeTool())
        self.assertFalse(self.fixtures.exists())


class DeleteGuardTest(RunnerTestCase):
    """The runner deletes only a regular file strictly below build/. Each
    case is checked on its path alone: nothing is deleted, and each file
    stays."""

    def setUp(self):
        super().setUp()
        (self.build / "tft").mkdir(parents=True)
        self.outside = self.root / "outside.tft"
        self.outside.write_bytes(b"kept")

    def assert_refused(self, path: Path):
        with self.assertRaises(ValueError):
            refuse_unless_deletable(path)
        self.assertTrue(self.outside.exists())

    def test_a_file_outside(self):
        self.assert_refused(self.outside)

    def test_a_path_leaving_through_dot_dot(self):
        self.assert_refused(self.build / "tft" / ".." / ".." / "outside.tft")

    def test_a_folder(self):
        self.assert_refused(self.build / "tft")
        self.assert_refused(self.build)

    def test_a_link(self):
        link = self.build / "tft" / "link.tft"
        try:
            os.symlink(self.outside, link)
        except OSError as error:
            # Windows makes links only in Developer Mode or for an administrator.
            self.skipTest("this system makes no links here: %s" % error)
        self.assert_refused(link)

    def test_a_build_folder_that_is_a_link(self):
        target = self.root / "elsewhere"
        target.mkdir()
        (target / "probe.tft").write_bytes(b"x")
        linked = self.root / "linked-build"
        try:
            os.symlink(target, linked, target_is_directory=True)
        except OSError as error:
            # A junction needs no rights on Windows, where a link does. Both
            # point inside this test's own folder.
            if sys.platform != "win32":
                self.skipTest("this system makes no links here: %s" % error)
            import _winapi
            _winapi.CreateJunction(str(target), str(linked))
        with mock.patch.object(probe_runner, "BUILD", linked), self.assertRaises(ValueError):
            refuse_unless_deletable(linked / "probe.tft")
        self.assertTrue((target / "probe.tft").exists())

    def test_a_file_below(self):
        file = self.build / "tft" / "probe.tft"
        file.write_bytes(b"x")
        refuse_unless_deletable(file)


class EditorToolTest(unittest.TestCase):
    """The Editor tool's commands, run in this process. A fake module stands
    in for the tool, which needs packages of its own."""

    def fake_tool(self, main):
        tool = types.ModuleType("tools.editor.editor")
        tool.main = main
        package = types.ModuleType("tools.editor")
        package.editor = tool
        modules = {"tools": types.ModuleType("tools"), "tools.editor": package,
                   "tools.editor.editor": tool}
        patch = mock.patch.dict(sys.modules, modules)
        patch.start()
        self.addCleanup(patch.stop)

    def test_it_needs_the_agents_own_editor(self):
        environment = {key: value for key, value in os.environ.items()
                       if key != "NXWRIGHT_EDITOR_NAME"}
        with mock.patch.dict(os.environ, environment, clear=True), \
                self.assertRaisesRegex(ProbeError, "NXWRIGHT_EDITOR_NAME"):
            EditorTool()

    def test_the_file_the_tft_command_wrote(self):
        commands = []

        def main(arguments):
            commands.append(arguments)
            if arguments[0] == "tft":
                # As the tool does, before it prints a page's name.
                sys.stdout.reconfigure(encoding="utf-8")
                print("Wrote C:\\build\\tft\\probe (2).tft\nCompile Successful!")
            return 0
        self.fake_tool(main)
        with mock.patch.dict(os.environ, {"NXWRIGHT_EDITOR_NAME": "test"}):
            with EditorTool() as tool:
                file = tool.write_tft(Path("probe.HMI"), Path("tft"))
        self.assertEqual(file, Path("C:\\build\\tft\\probe (2).tft"))
        self.assertEqual([command[0] for command in commands], ["hold", "open", "tft", "release"])
        self.assertTrue(all("--as" in command for command in commands[1:3]))

    def test_a_release_that_fails_leaves_the_runs_error(self):
        def main(arguments):
            return 1 if arguments[0] == "release" else 0
        self.fake_tool(main)
        with mock.patch.dict(os.environ, {"NXWRIGHT_EDITOR_NAME": "test"}), \
                mock.patch("sys.stderr"), self.assertRaisesRegex(RuntimeError, "the run's"):
            with EditorTool():
                raise RuntimeError("the run's")

    def test_a_command_that_stops(self):
        def main(arguments):
            if arguments[0] == "open":
                print("Stopped, on test's Editor: no such file", file=sys.stderr)
                return 1
            return 0
        self.fake_tool(main)
        with mock.patch.dict(os.environ, {"NXWRIGHT_EDITOR_NAME": "test"}), \
                self.assertRaisesRegex(ProbeError, "open command: Stopped, .* no such file"):
            with EditorTool() as tool:
                tool.write_tft(Path("probe.HMI"), Path("tft"))

    def test_closing_the_editor_s_messages(self):
        commands = []

        def main(arguments):
            commands.append(arguments)
            if arguments[0] == "close-message":
                print("Closed 1 message:\n- 'Error': Invalid Pic ID")
            return 0
        self.fake_tool(main)
        with mock.patch.dict(os.environ, {"NXWRIGHT_EDITOR_NAME": "test"}):
            with EditorTool() as tool:
                said = tool.close_messages()
        self.assertEqual(said, "Closed 1 message:\n- 'Error': Invalid Pic ID")
        self.assertEqual(commands[1][0], "close-message")
        self.assertIn("--as", commands[1])


class BaseFoldersTest(unittest.TestCase):
    """The base folders in probes/, as `nxwright new` writes them."""

    def test_as_nxwright_new_writes_them(self):
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.object(probe_runner, "BASES", Path(folder)):
                self.assertEqual(probe_runner.make_base_folders(), [])
            for series in probe_runner.BASE_MODELS:
                made, kept = Path(folder) / series, probe_runner.BASES / series
                files = sorted(path.relative_to(made) for path in made.rglob("*")
                               if path.is_file())
                self.assertEqual(files, sorted(path.relative_to(kept) for path in kept.rglob("*")
                                               if path.is_file()))
                for file in files:
                    with self.subTest(series=series, file=str(file)):
                        self.assertEqual((made / file).read_bytes(), (kept / file).read_bytes())

    def test_already_there(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "T").mkdir()
            with mock.patch.object(probe_runner, "BASES", Path(folder)), \
                    self.assertRaisesRegex(ProbeError, "base folders of T"):
                probe_runner.make_base_folders(["K", "T"])
            self.assertFalse((Path(folder) / "K").exists())


class CommandTest(unittest.TestCase):
    """Probe modules are found by name without starting the Nextion Editor."""

    def test_finds_a_named_module_without_running_it(self):
        with (mock.patch.object(probe_command, "EditorTool",
                                side_effect=AssertionError("must not start the Nextion Editor")),
              mock.patch.object(probe_command, "run_probes",
                                side_effect=AssertionError("must not run probes"))):
            self.assertIs(probe_command._probes_of("first_probes"), first_probes.PROBES)

    def test_no_such_module_or_probes(self):
        for module in ("no_such_module", "no_such.module", "probe_runner"):
            with self.subTest(module=module), mock.patch("sys.stderr", io.StringIO()) as errors:
                self.assertEqual(probe_command.main(["run", module]), 2)
                self.assertIn("tools.tft.probing." + module, errors.getvalue())

    def test_only_checks_the_probes_listed(self):
        # The second of first_probes alone, checked whatever the record lists.
        chosen = first_probes.PROBES[1]
        with (mock.patch.object(probe_command, "EditorTool"),
              mock.patch.object(probe_command, "run_probes",
                                return_value=probe_runner.RunResult([chosen.name], [], []))
              as running, mock.patch("sys.stdout", io.StringIO())):
            code = probe_command.main(["run", "first_probes", "--only", chosen.name])
        self.assertEqual(code, 0)
        probes, _, again = running.call_args.args
        self.assertEqual(probes, [chosen])
        self.assertEqual(again, {chosen.name})

    def test_only_refuses_a_probe_the_module_lacks(self):
        with (mock.patch.object(probe_command, "EditorTool",
                                side_effect=AssertionError("must not start the Nextion Editor")),
              mock.patch("sys.stderr", io.StringIO()) as errors):
            code = probe_command.main(["run", "first_probes", "--only", "no-such-probe"])
        self.assertEqual(code, 2)
        self.assertIn("first_probes lists no probe named no-such-probe", errors.getvalue())

    def test_only_and_again_together_are_refused(self):
        with mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit):
            probe_command.main(["run", "first_probes", "--only", "a", "--again", "b"])

    def test_cut_cuts_each_module_s_probes_without_the_editor(self):
        failed = probe_runner.CutResult([], {"first-blank": "why"})
        with (mock.patch.object(probe_command, "EditorTool",
                                side_effect=AssertionError("must not start the Nextion Editor")),
              mock.patch.object(probe_command, "cut_probes", return_value=failed) as cutting,
              mock.patch("sys.stdout", io.StringIO()) as output):
            code = probe_command.main(["cut", "first_probes", "first_probes"])
        self.assertEqual(code, 1)
        self.assertEqual(cutting.call_args.args[0], first_probes.PROBES * 2)
        self.assertIn("0 cut, 1 not cut: first-blank", output.getvalue())


class AllModulesTest(unittest.TestCase):
    """`tools.tft.probe run --all` checks every probe of each module that
    compares with nxwright's compile, and `--fixtures` those of them that keep
    fixtures, whatever the record lists. Each lists what did not match, and
    what could not run, by module. A stand-in runs no probe."""

    def run_command(self, *options: str, failing: str = None, unrunnable: str = None) -> tuple:
        """Runs `tools.tft.probe run` with `options` on stand-ins for the Editor
        tool and run_probes, which finds the probe `failing` not matching,
        and could not run `unrunnable`. Returns the exit code, what it
        printed, and each call's (probes, again)."""
        calls = []

        def stand_in_run(probes, tool, again):
            calls.append((probes, again))
            names = [probe.name for probe in probes]
            return probe_runner.RunResult(
                [name for name in names if name not in (failing, unrunnable)], [],
                [name for name in names if name == failing],
                {name: "the Editor refused it\nClosed 1 message:\n- 'Error': Invalid Pic ID"
                 for name in names if name == unrunnable})
        with (mock.patch.object(probe_command, "EditorTool"),
              mock.patch.object(probe_command, "run_probes", stand_in_run),
              mock.patch("sys.stdout", io.StringIO()) as output):
            code = probe_command.main(["run", *options])
        return code, output.getvalue(), calls

    def test_all_checks_every_module_that_compares(self):
        code, said, calls = self.run_command("--all", failing="timer-two",
                                             unrunnable="p-media-of-each")
        self.assertEqual(code, 1)
        probes = [probe for probes, _ in calls for probe in probes]
        names = [probe.name for probe in probes]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("blank-T", names)
        # The older Editors' probes are kept, and compare nothing.
        self.assertTrue(all(probe.ours is not None for probe in probes))
        for module_probes, again in calls:
            self.assertEqual(again, {probe.name for probe in module_probes})
        self.assertIn("\nNot matching, by module:\n  timer_probes: timer-two\n", said)
        # The reason's later lines are indented under the probe's.
        self.assertIn("\nCould not run, by module:\n  p_probes: p-media-of-each, the Editor "
                      "refused it\n    Closed 1 message:\n    - 'Error': Invalid Pic ID\n", said)

    def test_fixtures_checks_the_probes_that_keep_fixtures(self):
        code, said, calls = self.run_command("--fixtures")
        self.assertEqual(code, 0)
        probes = [probe for probes, _ in calls for probe in probes]
        self.assertTrue(probes)
        self.assertTrue(all(probe.fixtures is not None and probe.ours is not None
                            for probe in probes))
        self.assertNotIn("Not matching", said)

    def test_a_module_or_all_or_fixtures(self):
        for options in ((), ("first_probes", "--all"), ("--all", "--fixtures"),
                        ("--fixtures", "--again")):
            with self.subTest(options=options), mock.patch("sys.stderr", io.StringIO()), \
                    self.assertRaises(SystemExit):
                probe_command.main(["run", *options])


class ProbedEditorFirmwareTest(unittest.TestCase):
    """The probes package nxwright's file with the firmware of the Nextion Editor
    they drive: the one NXWRIGHT_EDITOR names, of whatever release, as a
    release unpacked from its zip, or else the installed one
    (packaging_probes.probe_firmware)."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.editor = write_editor_folder(Path(folder.name) / "editor")
        # As a release's zip names its program.
        self.program = self.editor / "NextionEditor.exe"

    def named(self):
        """While it lasts, NXWRIGHT_EDITOR names the stand-in Editor's program,
        of the Nextion Editor 1.69.1, and no Nextion Editor is installed."""
        return (mock.patch.dict(os.environ, {"NXWRIGHT_EDITOR": str(self.program)}),
                mock.patch.object(tft_firmware, "program_version",
                                  lambda program: (1, 69, 1, 0) if program == self.program
                                  else None),
                mock.patch.object(tft_firmware, "installed_editor_folder", lambda: None))

    def test_the_editor_nxwright_editor_names(self):
        environment, version, installed = self.named()
        with environment, version, installed:
            firmware = packaging_probes.probe_firmware("T")
        self.assertEqual(firmware.version, (1, 69, 1))
        self.assertEqual(firmware.files, {name: (self.editor / name).read_bytes()
                                          for name in firmware_names("T")})

    def test_the_installed_editor_without_nxwright_editor(self):
        environment = {key: value for key, value in os.environ.items()
                       if key != "NXWRIGHT_EDITOR"}
        with mock.patch.dict(os.environ, environment, clear=True), \
                stand_in_firmware(None, installed=self.editor):
            self.assertEqual(packaging_probes.probe_firmware("T").version, (1, 68, 2))

    def test_a_firmware_file_missing_from_its_folder(self):
        (self.editor / "asp0.dll").unlink()
        environment, version, installed = self.named()
        with environment, version, installed, \
                self.assertRaisesRegex(ProbeError, r"asp0\.dll could not be read"):
            packaging_probes.probe_firmware("T")

    def test_a_whole_file_of_a_release_not_matched(self):
        # The probes of a whole file compile with that firmware, which
        # `nxwright compile` refuses (tests/tft/test_compile.py).
        environment, version, installed = self.named()
        with tempfile.TemporaryDirectory() as work, environment, version, installed:
            project = probe_runner._built(first_probes.PROBES[0], Path(work))
            parts = component_probes.whole_file(project)
            header = parts["header-1"]
        self.assertEqual(read_tft(header + b"".join(parts[part] for part in (
            "header-2", "filler", "section", "user-code", "checksum")), "nxwright's file",
            check=False).version, (1, 69, 1))


class StandInCompileTool:
    """Writes nxwright's own TFT file of a project, made on zeros for the
    firmware, in place of the Nextion Editor's, as the Nextion Editor names
    it."""

    def write_tft(self, project: Path, folder: Path) -> Path:
        from nxwright.tft.commands.compile import compile_project
        from nxwright.tft.packaging import Firmware
        from nxwright.tft.project import Project
        from nxwright.tft.tft_file import firmware_names
        loaded = Project.from_file(project)
        series = loaded.settings.model.series
        firmware = Firmware((1, 68, 2), {name: bytes(16) for name in firmware_names(series)})
        folder.mkdir(parents=True, exist_ok=True)
        file = folder / "probe.tft"
        file.write_bytes(compile_project(loaded, firmware))
        return file


class ResearchTest(unittest.TestCase):
    """`tools.tft.probe research` prints the blocks of an event the Nextion
    Editor writes, and deletes its file. nxwright's own file stands in for it,
    in a build/ of the test's own."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        patch = mock.patch.object(probe_runner, "BUILD", self.root / "build")
        patch.start()
        self.addCleanup(patch.stop)

    def test_the_event_s_blocks_with_their_places(self):
        from tools.tft.probing import research, statement_probes
        from nxwright.tft.tft_file import split_blocks
        lines = ["sys0=1", "n0.val=t0.txt_maxl", "tm0.en=1", "s0.dis=50"]
        found = research.event_blocks("T", lines, StandInCompileTool())
        # The same project, whose event nxwright encodes on its own.
        with tempfile.TemporaryDirectory() as work:
            expected = split_blocks(statement_probes.ours_in_event(probe_runner._built(
                research.research_probe("T", lines), Path(work)))["event"])
        self.assertEqual([block for _, block in found], expected)
        self.assertEqual([place for place, _ in found][:2], [0, 4 + len(expected[0])])
        self.assertEqual(list((self.root / "build" / "tft").iterdir()), [])

    def test_the_command_prints_each_block(self):
        # Starting with a byte-order mark, as PowerShell writes a file.
        lines = self.root / "lines.txt"
        lines.write_text("sys0=1\n\nsys1=2\n", encoding="utf-8-sig")
        with (mock.patch.object(probe_command, "EditorTool",
                                return_value=mock.MagicMock(
                                    __enter__=lambda self: StandInCompileTool(),
                                    __exit__=lambda self, *arguments: False)),
              mock.patch("sys.stdout", io.StringIO()) as output):
            self.assertEqual(probe_command.main(["research", "T", str(lines)]), 0)
        printed = output.getvalue().splitlines()
        self.assertEqual(len(printed), 2)
        self.assertTrue(printed[0].startswith("    0 "))

    def test_a_file_of_lines_missing_or_empty(self):
        empty = self.root / "empty.txt"
        empty.write_text("\n  \n", encoding="utf-8")
        for file, said in ((self.root / "missing.txt", "cannot be read"),
                           (empty, "holds no line")):
            with (self.subTest(said),
                  mock.patch.object(probe_command, "EditorTool", side_effect=AssertionError(
                      "must not start the Nextion Editor")),
                  mock.patch("sys.stderr", io.StringIO()) as errors):
                code = probe_command.main(["research", "T", str(file)])
            self.assertEqual(code, 2)
            self.assertIn(said, errors.getvalue())


class FirstProbesTest(unittest.TestCase):
    """The probes the later phases start from build from probes/, each to the
    same bytes twice, and each to bytes of its own."""

    def test_each_builds_as_its_own(self):
        digests = {}
        for probe in first_probes.PROBES:
            with self.subTest(probe=probe.name):
                built = []
                for _ in range(2):
                    with tempfile.TemporaryDirectory() as work:
                        built.append(sha256(probe_runner._built(probe, Path(work))
                                            .read_bytes()).hexdigest())
                self.assertEqual(built[0], built[1])
                digests[probe.name] = built[0]
        self.assertEqual(len(set(digests.values())), len(digests))


if __name__ == "__main__":
    unittest.main()
