"""Packaging (tft/packaging.py): what it writes for each whole compile's
probe, against its pieces; the layout it writes on each series, with
made-up bytes for the firmware; and the firmware its rule takes.

Each test gives package() its own input, made in memory: a Project of the
facts of a probe's pages, or of a base folder's page (tests/tft/unit_inputs.py),
the user code the frame or made_tft gives, and zeros or made-up bytes for
the firmware. A picture's block, and a sound's or an animation's, is made
only by a whole build: the probes of them, and the probe of two pictures
and two fonts (packaging_probes.py), are compared in
tests/tft/test_whole_files.py.
"""
from dataclasses import replace
import re
import struct
import unittest

from nxwright import NxwrightError
from nxwright.project.zi_font import turned_font

from nxwright.tft import frame, packaging, reasons
from tools.tft.probing import compile_probes, e_probes, f_probes, k_probes, p_probes, probe_runner
from nxwright.tft.matching import firmware_needs, project_needs, refuse_unmatched
from nxwright.tft.packaging import Firmware, _blocks, package
from nxwright.tft.tft_file import (HEADER_1_SIZE, HEADER_2_END, TABLE_SIZE, firmware_names,
                            header_2_key, read_tft)
from tests.tft.made_tft import made_user_code, zeros_of_the_table
from tests.tft.unit_inputs import page, piece, probe_facts, project_of, with_font_blocks


class PiecesTest(unittest.TestCase):
    """What packaging writes for each probe of the whole compile, against
    its pieces: header 1, header 2, the section's table, and the file's
    checksum. Its input is the Project of facts of the probe's pages, with
    its base folder's font blocks (unit_inputs.with_font_blocks); the user
    code the frame gives that Project; and zeros for the firmware, of the
    sizes the probe's table gives. The frame's own parts of the user code
    have their own tests (tests/tft/test_frame.py)."""

    # Each series' blank project, and on T, P, and E three pages, two more
    # ints, and code; on T, two of each of four types beside a text. The
    # whole compile of P's media is compared whole, as its animations' and
    # sounds' blocks are made only by a whole build.
    PROBES = [probe for module in (compile_probes, k_probes, f_probes, e_probes, p_probes)
              for probe in module.PROBES
              if probe.fixtures and probe.kept is compile_probes._kept
              and probe.name != "p-media-of-each"]

    def test_each_probe(self):
        self.assertEqual(sorted(probe.name for probe in self.PROBES), [
            "compile-T-blank", "compile-T-buttons-and-a-text", "compile-T-numbers-and-a-text",
            "compile-T-pages-ints-code", "compile-T-texts", "compile-T-variables-and-a-text",
            "e-compile-T-blank", "e-compile-T-pages-ints-code", "f-compile-T-blank",
            "k-compile-T-blank", "p-compile-T-blank", "p-compile-T-pages-ints-code"])
        for probe in self.PROBES:
            project = with_font_blocks(probe_facts(probe), probe.base)
            data = package(project, frame.user_code(project),
                           zeros_of_the_table(piece(probe, "table"), probe.base))
            section = read_tft(data, probe.name, check=False).section_place
            for name, ours in (("header-1", data[:HEADER_1_SIZE]),
                               ("header-2", data[HEADER_1_SIZE:HEADER_2_END]),
                               ("table", data[section:section + TABLE_SIZE]),
                               ("checksum", data[-4:])):
                with self.subTest(probe.name, piece=name):
                    self.assertEqual(ours, piece(probe, name))


class LayoutTest(unittest.TestCase):
    """What packaging writes holds every checksum, size, and place the reader
    checks, on each series' base folder."""

    def test_each_series(self):
        for series in probe_runner.BASE_MODELS:
            with self.subTest(series):
                project = project_of(page(series=series), series=series, fonts=0)
                # Made-up bytes, none zero, so that the values header 1
                # takes from the main firmware file's offsets 1 and 5 show.
                firmware = Firmware((1, 68, 2), {name: (name.encode() * 4)[:13]
                                                 for name in firmware_names(series)})
                code = made_user_code()
                tft = read_tft(package(project, code, firmware), series)
                self.assertEqual(tft.user_code, code)
                self.assertEqual(tft.version, (1, 68, 2))
                section_size = 0x20000 if series in ("P", "E") else 0x10000
                self.assertEqual(tft.section_place, section_size)
                self.assertEqual(tft.user_code_place % section_size, 0)
                if series in ("T", "K"):
                    main = firmware.files[firmware_names(series)[1]]
                    self.assertEqual(tft.header_1_value(0x08),
                                     struct.unpack_from("<I", main, 5)[0])
                    self.assertEqual(tft.header_1_value(0x04) - tft.header_1_value(0x26),
                                     struct.unpack_from("<I", main, 1)[0])
                self.assertEqual(tft.header_2_value(0x110), 3)


class OneTimeUpdateTest(unittest.TestCase):
    """Header 1's 0x16 gives the device settings' one-time update: 1 in a TFT
    file the Nextion Editor wrote for a project that sets it, and 0 in every
    probe, which does not."""

    def test_header_1(self):
        for series in probe_runner.BASE_MODELS:
            project = project_of(page(series=series), series=series, fonts=0)
            firmware = Firmware((1, 68, 2), {name: bytes(16) for name in firmware_names(series)})
            for flag in (False, True):
                with self.subTest(series, one_time_update=flag):
                    flagged = replace(project, settings=replace(project.settings,
                                                                one_time_update=flag))
                    data = package(flagged, made_user_code(), firmware)
                    self.assertEqual(data[0x16], int(flag))


class DeviceSettingsTest(unittest.TestCase):
    """The other device settings, as the Nextion Editor's files of the base
    folders showed them on each series: the memory file's storage size, in
    header 1's 0x48 on P and E only; the flags that ignore library and image
    resources, which leave the fonts or the pictures out of the file; and
    the project password, which changes nothing in it. Each project has a
    picture, a made-up block that packaging lays out as it is, and its base
    folder's font."""

    # A picture's block: its header of 24 bytes, then 8 bytes of pixels.
    PICTURE = bytes(24) + bytes(range(1, 9))

    def packaged(self, series: str, **settings) -> bytes:
        project = with_font_blocks(project_of(page(series=series), series=series, pictures=1),
                                   series)
        project = replace(project, blocks={**project.blocks, "0.i": self.PICTURE},
                          settings=replace(project.settings, **settings))
        firmware = Firmware((1, 68, 2), {name: bytes(16) for name in firmware_names(series)})
        return package(project, made_user_code(), firmware)

    def test_memory_file_storage_size(self):
        for series in probe_runner.BASE_MODELS:
            with self.subTest(series):
                data = self.packaged(series, memory_file_storage_size=100000)
                read_tft(data, series)
                self.assertEqual(struct.unpack_from("<I", data, 0x48)[0],
                                 100000 if series in ("P", "E") else 0)

    def test_ignored_resources(self):
        # Header 2's place of the part left out, 0xE8 for the pictures and
        # 0xF8 for the fonts, is 0. Its row in the section's table keeps its
        # place, and is empty. The counts of pictures and fonts, at 0x104
        # and 0x10C, are kept.
        for series in probe_runner.BASE_MODELS:
            whole = read_tft(self.packaged(series), series)
            for flags in ({"ignore_image_resources": True}, {"ignore_library_resources": True},
                          {"ignore_image_resources": True, "ignore_library_resources": True}):
                with self.subTest(series, **flags):
                    tft = read_tft(self.packaged(series, **flags), series)
                    pictures_out = flags.get("ignore_image_resources", False)
                    fonts_out = flags.get("ignore_library_resources", False)
                    pictures, fonts = tft.table[7], tft.table[8]
                    self.assertEqual(pictures.place, whole.table[7].place)
                    self.assertEqual(pictures.size, 0 if pictures_out else whole.table[7].size)
                    self.assertEqual(fonts.place, pictures.place + pictures.size)
                    self.assertEqual(fonts.size, 0 if fonts_out else whole.table[8].size)
                    self.assertEqual(tft.header_2_value(0xE8),
                                     0 if pictures_out else tft.section_place + pictures.place)
                    self.assertEqual(tft.header_2_value(0xF8),
                                     0 if fonts_out else tft.section_place + fonts.place)
                    self.assertEqual(tft.header_2_value(0x104) & 0xFFFF, 1)
                    self.assertEqual(tft.header_2_value(0x10C), 1)
                    self.assertEqual(tft.user_code, whole.user_code)

    def test_a_place_of_0_beside_a_part_kept_is_a_problem(self):
        # The reader takes a place of 0 only for an empty part: 0 as the
        # pictures' place, beside the picture, is still a problem.
        data = self.packaged("T")
        key = header_2_key(data[0x2E:0x32], "T")
        changed = data[:0xE8] + struct.pack("<I", key) + data[0xEC:]
        self.assertIn("header 2's 0xE8, the pictures' place is 0x0; it should be 0x%x"
                      % read_tft(data, "T").header_2_value(0xE8),
                      read_tft(changed, "T", check=False).problems)

    def test_the_password_changes_nothing(self):
        for series in probe_runner.BASE_MODELS:
            with self.subTest(series):
                self.assertEqual(self.packaged(series, password_hash=bytes(range(1, 5))),
                                 self.packaged(series))


def _with_font(series: str, rotation: int, block_of) -> object:
    """Returns a Project of facts of the base folder of `series` at
    `rotation`, whose font is `block_of(the base folder's font)`."""
    project = with_font_blocks(project_of(page(series=series, rotation=rotation), series=series,
                                          rotation=rotation), series)
    fonts = [name for kind, name in project.resources if kind == "font"]
    return replace(project, blocks={**project.blocks,
                                    **{name: block_of(project.blocks[name]) for name in fonts}})


def _of_version_5(block: bytes) -> bytes:
    """Returns the font `block` marked as of version 5, which nxwright
    cannot read (zi_font.decodes), at the same orientation."""
    return block[:16] + b"\x05" + block[17:]


class FontsTest(unittest.TestCase):
    """A TFT file keeps each font at the screen's rotation on T, K, P, and E,
    and at 0 degrees on F. Whatever orientation the project keeps a font in,
    the compile writes it so, as the Nextion Editor 1.68.2 does: probed on
    each series at 270 degrees, with the font at 270, 0, and 90 degrees."""

    def test_a_font_in_another_orientation_is_turned_to_the_tft_file_s(self):
        cases = [(series, 270, font, 270) for series in ("T", "K", "P", "E") for font in (0, 90)]
        cases += [("F", 270, 90, 0), ("F", 0, 90, 0), ("T", 0, 90, 0)]
        for series, rotation, font_rotation, kept in cases:
            with self.subTest(series=series, rotation=rotation, font=font_rotation):
                project = _with_font(series, rotation,
                                     lambda block: turned_font(block, font_rotation))
                given = _blocks(project, "font")
                self.assertEqual(packaging._fonts(project),
                                 [turned_font(block, kept) for block in given])

    def test_a_font_in_the_tft_file_s_orientation_is_written_as_it_is(self):
        # Turning it would code its glyphs again.
        for series, rotation, kept in (("T", 270, 270), ("F", 270, 0), ("F", 0, 0)):
            with self.subTest(series=series, rotation=rotation):
                project = _with_font(series, rotation, lambda block: turned_font(block, kept))
                self.assertEqual(packaging._fonts(project), _blocks(project, "font"))

    def test_a_font_nxwright_cannot_read_is_refused_where_it_needs_turning(self):
        # nxwright ought to turn it, as the Nextion Editor does, but turned_font
        # cannot read it.
        def fonts(project):
            return [need for need in project_needs(project)
                    if (need.kind, need.subject) == ("resource", "font")]
        refused = _with_font("T", 270, _of_version_5)
        with self.assertRaisesRegex(NxwrightError, "resource font.*" + re.escape(
                reasons.NOT_SUPPORTED_YET)):
            refuse_unmatched(fonts(refused), packaging.MATCHED)
        taken = _with_font("T", 270, lambda block: _of_version_5(turned_font(block, 270)))
        refuse_unmatched(fonts(taken), packaging.MATCHED)

    def test_a_font_of_an_encoding_nxwright_does_not_know_in_the_tft_file_s_orientation(self):
        # nxwright extracts a project in an encoding it does not know, such as
        # 238, and keeps its fonts as they are. Such a font, already in the
        # TFT file's orientation, is written as it is; one that needs turning
        # cannot be read, and is refused.
        def of_encoding_238(block):
            return block[:4] + bytes([238]) + block[5:]
        taken = _with_font("T", 270, lambda block: of_encoding_238(turned_font(block, 270)))
        refuse_unmatched([need for need in project_needs(taken)
                          if (need.kind, need.subject) == ("resource", "font")],
                         packaging.MATCHED)
        self.assertEqual(packaging._fonts(taken), _blocks(taken, "font"))
        refused = _with_font("T", 270, of_encoding_238)
        with self.assertRaisesRegex(NxwrightError, re.escape(reasons.NOT_SUPPORTED_YET)):
            refuse_unmatched([need for need in project_needs(refused)
                              if (need.kind, need.subject) == ("resource", "font")],
                             packaging.MATCHED)


class MatchedTest(unittest.TestCase):

    def test_firmware_of_the_nextion_editor_1_68_2_alone(self):
        # A later version's firmware may number its commands differently, so it is
        # refused like an older one's.
        refuse_unmatched(firmware_needs((1, 68, 2)), packaging.MATCHED)
        for version in ((1, 68, 1), (1, 67, 9), (0, 99, 99), (1, 68, 3), (1, 69, 0), (2, 0, 0)):
            with self.subTest(version):
                with self.assertRaisesRegex(NxwrightError, "- firmware %d.%d.%d" % version):
                    refuse_unmatched(firmware_needs(version), packaging.MATCHED)


if __name__ == "__main__":
    unittest.main()
