"""The decompiler's round trips of whole files (tft/decompiling/round_trip.py):
probes of T, K, F, P, and E built whole and compiled on zeros for the firmware,
then compiled again from a source folder, and compared with the first file
by what the two hold (tft/decompiling/compared.py); and the decompile
command's run on such a file, end to end (tft/commands/decompile.py).

Their firmware is zeros of the sizes the compile takes, as the vendor's
files never enter the repository. The round trip reads its firmware from
the file it is given, so the zeros go round with the file.
"""
from contextlib import redirect_stdout
from dataclasses import replace
import io
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

from nxwright import NxwrightError
from nxwright.project.screen_copy import (FORMAT_COMPRESSED, OPAQUE, ScreenPixels,
                                          decode_screen_copy, encode_alphas, encode_screen_copy,
                                          screen_copy_format, stored_order)
from nxwright.project.zi_font import turned_font
from nxwright.cli import main
from nxwright.tft.commands.compile import compile_project
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.compared import mismatches
from nxwright.tft.decompiling.round_trip import compiled_again, round_trip
from nxwright.tft.decompiling.decoded_file import FONT_ROW, decoded_user_code, read_decoded
from nxwright.tft.decompiling.folder import folder_files, written_folder
from nxwright.tft.decompiling.resources import stored_font_blocks
from nxwright.tft import frame
from nxwright.tft.packaging import FONT_HEADER, Firmware, package
from tools.tft.probing import (compile_probes, e_probes, editor_1_60_1_p_probes,
                           editor_1_60_1_probes, f_probes, k_probes,
                           older_editor_probes, p_probes, release_probes)
from tools.tft.probing.probe_runner import _built
from nxwright.tft.project import Project
from nxwright.tft.tft_file import firmware_names, read_tft
from tests.tft.unit_inputs import font_in_other_bytes, user_code_of

# The sample: a project of pages, ints, and code, and one of pictures,
# fonts, and pages, on each series; on P and E, which alone have them, one
# of an animation, a video, and a sound; and projects whose code names a
# page, or a component, by a name of the user's own, which the file keeps as
# text: a page named settings, and nxwright's example thermostat, which
# clicks components nxlang named.
_SAMPLE = (("T", compile_probes, ""), ("K", k_probes, "k-"), ("F", f_probes, "f-"),
           ("P", p_probes, "p-"), ("E", e_probes, "e-"))
_PROJECTS = ("compile-T-pages-ints-code", "compile-T-resources-and-pages")
_MORE = (("P", p_probes, "p-media-of-each"), ("E", e_probes, "e-media-of-each"),
         ("P", p_probes, "p-page-by-name"), ("E", e_probes, "e-page-by-name"),
         ("P", p_probes, "p-example-thermostat"))


def _sample() -> list:
    """Returns the sample's probes, each of the series it is compiled for."""
    probes = []
    for series, module, prefix in _SAMPLE:
        named = {probe.name: probe for probe in module.PROBES}
        probes += [(series, named[prefix + name]) for name in _PROJECTS]
    for series, module, name in _MORE:
        probes += [(series, probe) for probe in module.PROBES if probe.name == name]
    return probes


def _zeros(series: str) -> Firmware:
    """Returns zeros for the firmware of `series`, 16 bytes each file, which
    packaging alone reads."""
    return Firmware((1, 68, 2), {name: bytes(16) for name in firmware_names(series)})


def _compiled(series: str, probe, work: Path) -> bytes:
    """Returns the TFT file of `probe`, built whole in `work` and compiled
    for `series` on zeros for the firmware."""
    return compile_project(Project.from_file(_built(probe, work)), _zeros(series))


class CompiledAgainTest(unittest.TestCase):

    def test_a_probe_s_own_folder_compiles_again_to_what_its_file_holds(self):
        # Compiled again from the very folder it was built from, each file
        # holds the same, so whatever a round trip finds is the decompiled
        # folder's.
        for series, probe in _sample():
            with self.subTest(probe.name), tempfile.TemporaryDirectory() as work:
                work = Path(work)
                project_file = _built(probe, work)
                firmware = _zeros(series)
                first = read_tft(compile_project(Project.from_file(project_file), firmware),
                                 probe.name)
                self.assertEqual(first.series, series)
                self.assertEqual(mismatches(first, compiled_again(work / "source", firmware)),
                                 [])


class RoundTripTest(unittest.TestCase):

    def test_each_file_of_the_sample(self):
        # Each file, decompiled, built, and compiled again, holds the same.
        for series, probe in _sample():
            with self.subTest(probe.name), tempfile.TemporaryDirectory() as work:
                work = Path(work)
                data = _compiled(series, probe, work)
                trip = round_trip(data, probe.name, work / "decompiled")
                self.assertEqual(trip.original.data, data)
                self.assertTrue((work / "decompiled" / "app.toml").is_file())
                self.assertEqual(trip.mismatches, [])
                # The round trip compares the file given as the decompile
                # decoded it, which writing the folder leaves as it was.
                written = written_folder(trip.original, work / "written")
                self.assertEqual(written.decoded, read_decoded(trip.original))

    def trip_with(self, patched: str, **how) -> tuple:
        """Returns (the RoundTrip, or the error it raised; whether it wrote
        the folder) of the round trip of a file of the sample, with
        round_trip's `patched` replaced by mock.patch's `how`."""
        named = {probe.name: probe for probe in compile_probes.PROBES}
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            data = _compiled("T", named["compile-T-pages-ints-code"], work)
            with mock.patch("nxwright.tft.decompiling.round_trip." + patched, **how):
                try:
                    trip = round_trip(data, "app.tft", work / "decompiled")
                except NxwrightError as error:
                    trip = error
            return trip, (work / "decompiled" / "app.toml").is_file()

    def test_a_folder_the_compile_refuses(self):
        # As for a line nxwright has no rule for: the folder is written, and
        # the round trip gives the refusal, where it raised before.
        refusal = "nxwright does not compile these:\n- code event = 'sys0=x' (page0, line 1)"
        trip, written = self.trip_with("refuse_unmatched", side_effect=NxwrightError(refusal))
        self.assertTrue(written)
        self.assertEqual((trip.again, trip.mismatches, trip.unchecked_reason),
                         (None, [], refusal))

    def test_a_folder_nxwright_s_build_refuses(self):
        trip, written = self.trip_with("project_of_folder",
                                       side_effect=NxwrightError("a page nxwright refuses"))
        self.assertTrue(written)
        self.assertEqual((trip.again, trip.unchecked_reason), (None, "a page nxwright refuses"))

    def test_a_file_compiled_again_that_cannot_be_read(self):
        # A bug in the compile, but the folder is still what the decompiler read.
        trip, _ = self.trip_with("package", return_value=b"not a TFT file")
        self.assertIsNone(trip.again)
        self.assertIn("the TFT file compiled again", trip.unchecked_reason)

    def test_the_file_given_that_cannot_be_read_is_refused(self):
        # The round trip cuts the file given's pictures apart after the
        # folder is written. A failure there is still the file's, and
        # refused.
        trip, _ = self.trip_with("picture_blocks",
                                 side_effect=DecodeError("pictures cut short", None, b""))
        self.assertIsInstance(trip, DecodeError)


def _in_literals(block: bytes, rotation: int) -> bytes:
    """Returns a screen copy of format 4 of the same pixels as `block`, one
    of format 4 at `rotation`, but with its colours in one literal block,
    where nxwright writes runs: other colour blocks, as the Nextion Editor
    may cut them (screen_copy.py's docstring)."""
    pixels = decode_screen_copy(block, rotation)
    order = stored_order(pixels.width, pixels.height, rotation)
    colours = [pixels.colours[at] for at in order]
    sides = ((pixels.height, pixels.width) if rotation in (90, 270)
             else (pixels.width, pixels.height))
    body = struct.pack("<5I", 1, *sides, 0, 0) + struct.pack(
        "<I%dH" % len(colours), len(colours) << 4 | 15, *colours)
    alpha_at = 0
    alphas = [pixels.alphas[at] for at in order]
    if min(alphas) < OPAQUE:
        alpha_at = len(body)
        body += encode_alphas(alphas)
    return (bytes([0x0A + rotation // 90, 0x64, 0x01, FORMAT_COMPRESSED])
            + struct.pack("<IIHHII", 0, 24, pixels.width, pixels.height, len(body), alpha_at)
            + body)


class PicturesByPixelsTest(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        named = {probe.name: probe for probe in p_probes.PROBES}
        self.project = Project.from_file(_built(named["p-compile-T-resources-and-pages"],
                                                Path(self.work.name)))
        self.pictures = [name for kind, name in self.project.resources if kind == "picture"]

    def tearDown(self):
        self.work.cleanup()

    def compiled(self, blocks: dict) -> bytes:
        """Returns the TFT file of the project with `blocks` in place of its
        own, compiled on zeros for the firmware."""
        project = replace(self.project, blocks={**self.project.blocks, **blocks})
        return compile_project(project, _zeros("P"))

    def test_other_colour_blocks_of_the_same_pixels(self):
        # A file whose picture is cut into other colour blocks than
        # nxwright's, of the same pixels, comes back with no mismatch, as the
        # file's own screen copy takes the place of nxwright's.
        name = self.pictures[0]
        block = self.project.blocks[name]
        rotation = self.project.settings.rotation
        self.assertEqual(screen_copy_format(block), FORMAT_COMPRESSED)
        other = _in_literals(block, rotation)
        self.assertNotEqual(other, block)
        self.assertEqual(decode_screen_copy(other, rotation), decode_screen_copy(block, rotation))
        trip = round_trip(self.compiled({name: other}), "a probe",
                          Path(self.work.name) / "decompiled")
        self.assertEqual(trip.mismatches, [])

    def test_other_pixels(self):
        # A folder whose picture shows other pixels than the file's keeps its
        # own screen copy, and the round trip finds it.
        name = self.pictures[0]
        rotation = self.project.settings.rotation
        pixels = decode_screen_copy(self.project.blocks[name], rotation)
        changed = ScreenPixels(pixels.width, pixels.height,
                               [colour ^ 0x0821 for colour in pixels.colours], pixels.alphas)
        original = read_tft(self.compiled({name: encode_screen_copy(
            changed, FORMAT_COMPRESSED, rotation)}), "a probe")
        folder = Path(self.work.name) / "source"
        again = compiled_again(folder, _zeros("P"), original)
        self.assertIn("the section, the pictures",
                      [each.where for each in mismatches(original, again)])


class FontsByCharactersTest(unittest.TestCase):

    def setUp(self):
        # A project of F at 90 degrees, whose file keeps its fonts at 0.
        self.work = tempfile.TemporaryDirectory()
        named = {probe.name: probe for probe in f_probes.PROBES}
        self.project = Project.from_file(_built(
            named["f-at-90-compile-T-resources-and-pages"], Path(self.work.name)))
        self.font = [name for kind, name in self.project.resources if kind == "font"][-1]
        self.ours, self.other = font_in_other_bytes(self.project.settings.encoding)

    def tearDown(self):
        self.work.cleanup()

    def compiled(self, block: bytes) -> bytes:
        """Returns the TFT file of the project with `block` in place of its
        last font, compiled on zeros for the firmware."""
        project = replace(self.project, blocks={**self.project.blocks, self.font: block})
        return compile_project(project, _zeros("F"))

    def test_a_glyph_in_other_bytes_of_the_same_coverages(self):
        # The file's font codes a glyph otherwise than nxwright, which writes
        # the folder's font again its own way. The round trip finds no
        # mismatch, as the file's own font takes the place of nxwright's.
        # The section keeps each font's header apart from its rest.
        data = self.compiled(self.other)
        self.assertIn(self.other[FONT_HEADER:], data)
        self.assertNotEqual(self.other, self.ours)
        trip = round_trip(data, "a probe", Path(self.work.name) / "decompiled")
        self.assertEqual(trip.mismatches, [])

    def test_a_round_trip_turns_no_font_and_decodes_each_file_once(self):
        # The decompile writes each font into the folder as the file keeps
        # it, at 0 degrees on F, so the folder's project has the file's own
        # fonts and the round trip turns none. It compares the file given as
        # the decompile decoded it.
        fonts = sum(kind == "font" for kind, _ in self.project.resources)
        data = compile_project(self.project, _zeros("F"))
        turns = mock.Mock(side_effect=turned_font)
        decodes = mock.Mock(side_effect=read_decoded)
        with mock.patch("nxwright.tft.packaging.turned_font", turns), \
                mock.patch("nxwright.tft.decompiling.round_trip.turned_font", turns), \
                mock.patch("nxwright.tft.decompiling.folder.read_decoded", decodes), \
                mock.patch("nxwright.tft.decompiling.compared.read_decoded", decodes):
            trip = round_trip(data, "a probe", Path(self.work.name) / "decompiled")
        self.assertEqual(trip.mismatches, [])
        self.assertGreater(fonts, 0)
        self.assertEqual((turns.call_count, decodes.call_count), (0, 2))
        stored = stored_font_blocks(trip.original.table_part(trip.original.table[FONT_ROW]),
                                    fonts)
        written = [path.read_bytes() for path in sorted(
            (Path(self.work.name) / "decompiled" / "fonts").glob("*.zi"))]
        self.assertEqual(sorted(written), sorted(stored))

    def test_other_characters(self):
        # A folder whose font has other characters than the file's keeps
        # its own font, and the round trip finds it.
        original = read_tft(self.compiled(self.other), "a probe")
        again = compiled_again(Path(self.work.name) / "source", _zeros("F"), original)
        self.assertIn("the section, the fonts",
                      [each.where for each in mismatches(original, again)])


class OlderEditorFilesTest(unittest.TestCase):

    def test_each_probe_of_1_63_3_gives_the_folder_of_1_68_2(self):
        # Each probe of the Nextion Editor 1.63.3 keeps its file's user code,
        # which starts with three blocks and, on P, has records of 108 fixed
        # slots. Those of a drag fill slot 79 with a disup, which the folder
        # keeps and 1.68.2 does not have.
        fixtures = older_editor_probes.FIXTURES
        for probe in older_editor_probes.PROBES:
            with self.subTest(probe.name):
                self.assert_gives_the_folder_of_1_68_2(probe, fixtures, (1, 63, 3),
                                                       _disup_of(probe, fixtures))

    def test_each_probe_of_1_60_1_gives_the_folder_of_1_68_2(self):
        # Each probe of the Nextion Editor 1.60.1 that keeps a whole project:
        # its user code starts with two blocks, its page index takes 12 bytes
        # a page, and a page's block before its texts lacks 4 bytes. On P,
        # its records have 98 slots.
        fixtures = release_probes.fixtures_of(editor_1_60_1_probes.VERSION)
        probes = [probe for probe in editor_1_60_1_probes.PROBES
                  if not probe.name.endswith("-program")]
        self.assertEqual(sorted({probe.base for probe in probes}), ["K", "P", "T"])
        for probe in probes:
            with self.subTest(probe.name):
                self.assert_gives_the_folder_of_1_68_2(probe, fixtures,
                                                       editor_1_60_1_probes.VERSION)

    def test_each_probe_of_1_60_1_s_components_on_p_gives_the_folder_of_1_68_2(self):
        # Each probe of a component type on P of the Nextion Editor 1.60.1,
        # whose records have 98 slots, the first 98 of 1.63.3's. Those of a
        # drag fill slot 79 with a disup, as on 1.63.3.
        version = editor_1_60_1_p_probes.VERSION
        fixtures = release_probes.fixtures_of(version)
        self.assertEqual(len(editor_1_60_1_p_probes.PROBES), 83)
        for probe in editor_1_60_1_p_probes.PROBES:
            with self.subTest(probe.name):
                self.assert_gives_the_folder_of_1_68_2(probe, fixtures, version,
                                                       _disup_of(probe, fixtures))

    def assert_gives_the_folder_of_1_68_2(self, probe, fixtures: str, version: tuple,
                                          disup: int = None):
        """Asserts that `probe`, of the Nextion Editor `version`, decoded
        from its user code, gives the same source folder as nxwright's compile
        of the same project for 1.68.2. The probe is named after the probe
        of that project, after `fixtures`, its fixtures' folder's name. With
        `disup`, one component of the folder has that disup, which 1.68.2's
        compile leaves out, and the folder is the same once it is taken out
        too."""
        expected = _decoded_of_1_68_2(probe, fixtures)
        decoded = decoded_user_code(user_code_of(probe, version), probe.base, expected.model,
                                    expected.rotation, expected.encoding, version)
        files = folder_files(decoded, {})
        if disup is not None:
            line = b"disup = %d\n" % disup
            pages = [path for path, data in files.items() if line in data]
            self.assertEqual(len(pages), 1)
            self.assertEqual(files[pages[0]].count(line), 1)
            files[pages[0]] = files[pages[0]].replace(line, b"")
        self.assertEqual(files, folder_files(expected, {}))


def _decoded_of_1_68_2(probe, fixtures: str):
    """Returns the decoded file of nxwright's compile for 1.68.2 of the project
    of `probe`, named after the probe of that project, after `fixtures`, its
    fixtures' folder's name."""
    named = {each.name: each for _, module, _ in _SAMPLE for each in module.PROBES}
    newer = named[probe.name[len(fixtures) + 1:]]
    with tempfile.TemporaryDirectory() as work:
        return read_decoded(read_tft(_compiled(probe.base, newer, Path(work)), newer.name))


def _disup_of(probe, fixtures: str):
    """Returns the disup of the one dragged component of `probe`, named
    after the probe of p_probes whose project it takes, after `fixtures`,
    its fixtures' folder's name: 0 for one of older_editor_probes.P_DRAGGED,
    1 for one of P_DISUP, and None for any other probe."""
    name = probe.name[len(fixtures) + 1:]
    if name in older_editor_probes.P_DRAGGED:
        return 0
    return 1 if name in older_editor_probes.P_DISUP else None


class OlderFirmwareTest(unittest.TestCase):

    def test_a_file_of_an_older_nextion_editor(self):
        # A file of a Nextion Editor older than any nxwright was tested with,
        # 1.65.1, whose user code is laid out as 1.68.2's, is decompiled
        # without being compiled again, with a warning.
        series, probe = _sample()[0]
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            project = Project.from_file(_built(probe, work))
            older = Firmware((1, 65, 1), _zeros(series).files)
            data = package(project, frame.user_code(project), older)
            trip = round_trip(data, probe.name, work / "decompiled")
            self.assertTrue((work / "decompiled" / "app.toml").is_file())
        self.assertIsNone(trip.again)
        self.assertEqual(trip.mismatches, [])
        self.assertIn("1.65.1", trip.warning)
        self.assertIn("1.68.2", trip.warning)

    def test_no_warning_at_a_tested_version(self):
        series, probe = _sample()[0]
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            trip = round_trip(_compiled(series, probe, work), probe.name, work / "decompiled")
        self.assertIsNone(trip.warning)


class CommandTest(unittest.TestCase):

    def test_a_file_of_the_sample_decompiled(self):
        # `nxwright decompile` writes the folder of the sample's first file,
        # which builds and compiles again into a file that holds the same.
        series, probe = _sample()[0]
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            data = _compiled(series, probe, work)
            file = work / "app.tft"
            file.write_bytes(data)
            with redirect_stdout(io.StringIO()):
                code = main(["decompile", str(file), str(work / "decompiled")])
            self.assertEqual(code, 0)
            self.assertEqual(mismatches(read_tft(data, probe.name),
                                        compiled_again(work / "decompiled", _zeros(series))), [])


if __name__ == "__main__":
    unittest.main()
