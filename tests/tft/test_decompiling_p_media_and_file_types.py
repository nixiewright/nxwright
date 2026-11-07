"""The decoders of five of P's own types (tft/decompiling/component_types/):
the gmov, the video, the audio, the external picture, and the file stream.

Each test has the compile write a probe's user code in memory, then
rebuilds each component of those types from what its decoder reads back,
and compiles the project again (unit_inputs.rebuilt_user_code). The two
user codes are the same when the decoder keeps everything the file keeps.
The blocks the Nextion Editor adds for a component, which the decoder gives
in its ObjectValues.added, are checked against the compile's own.
"""
from dataclasses import replace
import unittest


from nxwright.tft import frame
from nxwright.tft.component_types import file_stream
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import CodeRun, decoded_user_code
from nxwright.tft.decompiling.objects import decoded_values
from nxwright.tft.instructions.undocumented_commands import init_block
from tools.tft.probing import (audio_probes, external_picture_probes, file_stream_probes, gmov_probes,
                           video_probes)
from tests.tft.t_components import made_in_memory
from tests.tft.unit_inputs import probe_facts, rebuilt_user_code

# The types of these decoders, and what each adds: the init block in its
# page's load section, and for a file stream, the call of its close at the
# end of its page's unload event, one block each.
_ADDED = {"gmov": {"load": (1, 0)}, "video": {"load": (1, 0)}, "audio": {"load": (1, 0)},
          "external-picture": {}, "file-stream": {"load": (1, 0), "page unload": (0, 1)}}


def _probes() -> list:
    """Returns the probes of P of these types whose pages are made in memory."""
    return [probe for module in (gmov_probes, video_probes, audio_probes,
                                 external_picture_probes, file_stream_probes)
            for probe in module.PROBES if probe.base == "P" and made_in_memory(probe)]


def _decoded(probe):
    """Returns the decoded file of the user code the compile writes in memory
    for `probe`'s facts."""
    project = probe_facts(probe)
    settings = project.settings
    return decoded_user_code(frame.user_code(project), "P", settings.model.name,
                             settings.rotation, settings.encoding)


class RebuiltTest(unittest.TestCase):

    def test_each_component_of_each_probe(self):
        # Each component of these types, at its type's defaults but the
        # values read, compiles into the same user code, and gives the
        # blocks its type adds. The probes give each variant: a gmov at a
        # from of 1, and a video and an audio that play a file.
        added = []

        def values_of(decoded_object, decoded_page, decoded_file):
            if decoded_object.type_name not in _ADDED:
                return None
            values = decoded_values(decoded_object, decoded_page, decoded_file)
            added.append((decoded_object.type_name, values.added))
            return values.attributes
        rebuilt = 0
        for probe in _probes():
            with self.subTest(probe.name):
                code, again, count = rebuilt_user_code(probe_facts(probe), values_of)
                self.assertEqual(again, code)
                rebuilt += count
        self.assertEqual([each for _, each in added], [_ADDED[name] for name, _ in added])
        # Components of each type.
        self.assertEqual((rebuilt, {name for name, _ in added}), (47, set(_ADDED)))


class RefusalsTest(unittest.TestCase):

    def test_a_file_stream_without_its_close(self):
        # A page whose unload event does not end with the file stream's
        # close, as the Nextion Editor adds it, is refused.
        probe = next(probe for probe in file_stream_probes.PROBES
                     if probe.name == "file-stream-at-its-defaults")
        decoded = _decoded(probe)
        page = decoded.pages[0]
        stream = next(each for each in page.objects if each.type_name == "file-stream")
        self.assertEqual(decoded_values(stream, page, decoded).added["page unload"], (0, 1))
        unload = page.objects[0].events["unload"]
        # Without the call, and with a call of the file stream's open in
        # its place. A call's block is 01, then its method's entry, 4
        # bytes, then its arguments (statements.METHOD_CALL).
        close = unload.blocks[-1]
        entry = int.from_bytes(close[1:5], "little") - (
            file_stream.attribute_place("close") - file_stream.attribute_place("open"))
        stream_open = close[:1] + entry.to_bytes(4, "little") + close[5:]
        for blocks in ([], unload.blocks[:-1] + [stream_open]):
            with self.subTest(blocks=blocks):
                page.objects[0].events["unload"] = CodeRun(unload.place, blocks)
                self.assertRaises(DecodeError, decoded_values, stream, page, decoded)

    def test_a_file_stream_s_init_block_by_version(self):
        # The Nextion Editors before 1.67.1 add no init block for a file
        # stream, and 1.67.1 and later do (ResearchNotes/tft/older-editors.md).
        # So a page without the block is read on 1.65.1, the last release
        # without it, and refused on 1.67.1, the first with it.
        probe = next(probe for probe in file_stream_probes.PROBES
                     if probe.name == "file-stream-at-its-defaults")
        decoded = _decoded(probe)
        page = decoded.pages[0]
        stream = next(each for each in page.objects if each.type_name == "file-stream")
        load = page.load_section
        page.load_section = CodeRun(load.place, [block for block in load.blocks
                                                 if block != init_block(stream.object_id)])
        self.assertEqual(len(page.load_section.blocks), len(load.blocks) - 1)
        self.assertEqual(decoded_values(stream, page, replace(decoded, version=(1, 65, 1)))
                         .added["load"], (0, 0))
        self.assertRaises(DecodeError, decoded_values, stream, page,
                          replace(decoded, version=(1, 67, 1)))

    def test_a_gmov_without_its_init(self):
        # A gmov whose page's load section lacks its init block is refused.
        probe = next(probe for probe in gmov_probes.PROBES
                     if probe.name == "gmov-at-its-defaults")
        decoded = _decoded(probe)
        page = decoded.pages[0]
        gmov = next(each for each in page.objects if each.type_name == "gmov")
        page = replace(page, load_section=CodeRun(page.load_section.place,
                                                  page.load_section.blocks[1:]))
        self.assertRaises(DecodeError, decoded_values, gmov, page, decoded)


if __name__ == "__main__":
    unittest.main()
