"""Animations, videos, and sounds in a project (tft/packaging.py), which P
and E take and T and K do not: what the rules take, how a sound is
resampled, the size of the section's part of sounds, and the highest of the
entry of the vid that names an animation.

Each test gives the function it checks its own input: a sound's bytes, or
a page and a Project of the facts it reads, made in memory
(tests/tft/unit_inputs.py). What the packaging writes of a project's media,
the section's rows, the sounds' part, and header 2's counts, and a
compile's refusal of a sound without ffmpeg, are compared by whole files in
tests/tft/test_whole_files.py.
"""
from dataclasses import replace
import io
import struct
import unittest
from unittest import mock
import wave

from nxwright import NxwrightError
from nxwright.project.media_files import sound_file

from nxwright.tft import packaging
from tools.tft.probing.gmov_probes import gmov_component
from tools.tft.probing.resampled_sound_probes import float_wav
from nxwright.tft.matching import Need, matched_rules, unmatched
from tests.tft.p_components import p_entries, p_probe
from tests.tft.unit_inputs import page, place, project_of


class VidTest(unittest.TestCase):

    def test_its_highest(self):
        # The project's last animation, 1, of two, as a font's highest is its
        # last font. The entry reads the project's animations alone, so its
        # place is a probe's gmov's.
        made = page(gmov_component(vid=1), series="P")
        project = project_of(made, series="P")
        project = replace(project, resources=project.resources
                          + [("animation", "0.gmov"), ("animation", "1.gmov")])
        entries = p_entries(made.objects[1], place(p_probe("p-gmov-at-its-defaults"), "page0-1"),
                            project)
        # Its vid's entry is its 21st, whose highest is its third field.
        self.assertEqual(struct.unpack_from("<i", entries, 24 * 20 + 8)[0], 1)


class RuleTest(unittest.TestCase):

    @staticmethod
    def _sound(rate: int, width: int, channels: int) -> bytes:
        data = io.BytesIO()
        with wave.open(data, "wb") as sound:
            sound.setnchannels(channels)
            sound.setsampwidth(width)
            sound.setframerate(rate)
            sound.writeframes(bytes(8 * width * channels))
        return data.getvalue()

    def test_on_p_and_e_alone(self):
        rules = matched_rules()
        for kind in ("animation", "video"):
            for series, taken in (("P", True), ("E", True), ("T", False), ("K", False)):
                with self.subTest((kind, series)):
                    need = Need("resource", kind, series=series, context={"block": b""})
                    self.assertEqual(unmatched([need], rules), [] if taken else [need])

    def test_sounds(self):
        # At 22050 samples a second, 16 bits a sample, mono or stereo, which
        # the Nextion Editor writes as it is. It refuses any other sound of
        # that rate. It resamples a sound of any other rate, of any bits and
        # channels.
        rules = matched_rules()
        for form, taken in (((22050, 2, 1), True), ((22050, 2, 2), True), ((8000, 2, 1), True),
                            ((8000, 1, 1), True), ((48000, 2, 2), True), ((4000, 2, 1), True),
                            ((192000, 2, 1), True), ((44100, 3, 1), True), ((8000, 3, 2), True),
                            ((44100, 4, 1), True), ((44100, 2, 6), True),
                            ((22050, 1, 1), False), ((22050, 1, 2), False),
                            ((22050, 3, 1), False), ((22050, 4, 1), False),
                            ((22050, 2, 3), False), ((22050, 2, 4), False)):
            with self.subTest(form):
                need = Need("resource", "sound", series="P",
                            context={"block": self._sound(*form)})
                self.assertEqual(unmatched([need], rules), [] if taken else [need])
        need = Need("resource", "sound", series="T", context={"block": self._sound(22050, 2, 1)})
        self.assertEqual(unmatched([need], rules), [need])

    def test_sounds_of_floating_point_samples(self):
        # Python's wave module does not read them. The Nextion Editor
        # resamples one at 44100 samples a second, and refuses one at 22050,
        # as of 32 bits ("only 16 bits are supported").
        rules = matched_rules()
        for rate, taken in ((44100, True), (22050, False)):
            with self.subTest(rate):
                need = Need("resource", "sound", series="P",
                            context={"block": float_wav(rate, 1)})
                self.assertEqual(unmatched([need], rules), [] if taken else [need])

    def test_sounds_of_any_format(self):
        # The Nextion Editor reads a sound's rate, bits, and channels alone,
        # whatever the format code of its fmt chunk: it resampled an ADPCM
        # sound, of format 2, at 44100 samples a second, and refused one of
        # its 4 bits at 22050. It refused a PCM one at 22050 whose fmt chunk
        # gives 12 bits, though each sample takes 2 bytes. nxwright takes a
        # sound of 16 bits at 22050 of format 0xFFFE as it is, as the Editor
        # judges a sound by its rate, bits, and channels; no Editor file of
        # one was seen.
        rules = matched_rules()
        block = self._sound(22050, 2, 1)
        samples = block[block.index(b"data"):]
        for code, rate, bits, taken in ((2, 44100, 4, True), (2, 22050, 4, False),
                                        (1, 22050, 12, False), (0xFFFE, 22050, 16, True)):
            with self.subTest((code, rate)):
                form = struct.pack("<HHIIHH", code, 1, rate, rate * bits // 8, 2, bits)
                body = b"WAVE" + b"fmt " + struct.pack("<I", len(form)) + form + samples
                need = Need("resource", "sound", series="P",
                            context={"block": b"RIFF" + struct.pack("<I", len(body)) + body})
                self.assertEqual(unmatched([need], rules), [] if taken else [need])

    def test_header_size(self):
        # The section's part of sounds, by packaging's own function.
        self.assertEqual(packaging._sounds([b"ab", b"cde"]),
                         struct.pack("<II8xII8x", 32, 2, 34, 3) + b"abcde")


class ResampleTest(unittest.TestCase):
    """A sound of another form than 22050 samples a second of 16 bits, which
    packaging resamples with ffmpeg (packaging._sound_as_written)."""

    def test_one_of_22050_samples_of_16_bits_goes_in_as_it_is(self):
        block = RuleTest._sound(22050, 2, 2)
        self.assertEqual(packaging._sound_as_written("beep", block, None), block)

    def test_another_is_resampled_and_kept_as_a_project_keeps_it(self):
        # ffmpeg's samples, at 22050 a second of 16 bits, in mono, wrapped
        # as nxwright's sound_file keeps a sound. A block without an hmic
        # chunk keeps no name, so none is written, as the Nextion Editor's
        # file of a sound of 24 bits at 44100 samples a second showed.
        resampled = RuleTest._sound(22050, 2, 1)
        with mock.patch.object(packaging, "sound_as_wav", return_value=resampled) as run:
            written = packaging._sound_as_written("beep", RuleTest._sound(8000, 1, 1), "ffmpeg")
        self.assertEqual(written, sound_file(resampled, ""))
        self.assertEqual(run.call_args.args[0], "ffmpeg")
        self.assertEqual(run.call_args.args[3], 22050)
        self.assertTrue(run.call_args.kwargs["mono"])

    def test_its_name_is_the_one_its_block_keeps(self):
        # Not the block's own name in the project, such as 0.wav.
        block = sound_file(RuleTest._sound(8000, 1, 1), "tone")
        self.assertEqual(packaging._sound_name(block), "tone")
        self.assertIsNone(packaging._sound_name(RuleTest._sound(8000, 1, 1)))
        with mock.patch.object(packaging, "sound_as_wav",
                               return_value=RuleTest._sound(22050, 2, 1)):
            written = packaging._sound_as_written("0.wav", block, "ffmpeg")
        self.assertEqual(packaging._sound_name(written), "tone")

    def test_without_ffmpeg_it_gives_the_sound_s_own_bits(self):
        # An ADPCM sound's samples are 4 bits, not a whole number of bytes.
        block = RuleTest._sound(44100, 2, 1)
        block = block[:34] + struct.pack("<H", 4) + block[36:]
        with self.assertRaisesRegex(NxwrightError, "44100 samples a second of 4 bits each"):
            packaging._sound_as_written("0.wav", block, None)

    def test_an_ffmpeg_failure_names_the_sound(self):
        block = sound_file(RuleTest._sound(8000, 1, 1), "tone")
        with mock.patch.object(packaging, "sound_as_wav",
                               side_effect=NxwrightError("ffmpeg could not read sound.wav")):
            with self.assertRaisesRegex(NxwrightError, "the sound tone could not be resampled: "
                                        "ffmpeg could not read sound.wav"):
                packaging._sound_as_written("0.wav", block, "ffmpeg")


if __name__ == "__main__":
    unittest.main()
