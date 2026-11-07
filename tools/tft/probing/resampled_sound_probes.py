"""The probes of sounds of other forms than 22050 samples a second of 16 bits
each, which the Nextion Editor resamples to that form with ffmpeg
(packaging.py, ResearchNotes/tft/media-packaging.md): on P and E, sounds of 8
bits and of 16, mono and stereo, from 8000 to 48000 samples a second, the
rates nxwright's add_sound takes, and of 16 bits at 4000, 96000, and
192000, past them; and of 24 and 32 bits, of floating-point samples, of
Microsoft ADPCM ones, and of 6 channels, which only a file put in the
source folder by hand gives, each played by an audio.
The Nextion Editor refused any sound of 22050 samples a second but one of
16 bits, mono or stereo, which nxwright refuses too (packaging._sound_taken).
Each compares the whole file. Run them with
`tools.tft.probe run resampled_sound_probes`.

nxwright resamples with the ffmpeg the PATH finds, as the compile command
does when --ffmpeg names none, so a run needs one there. None keeps
fixtures: a test would need ffmpeg to write them again.
"""
from pathlib import Path
import struct
import subprocess
import wave

from nxwright.project.ffmpeg import find_ffmpeg

from tools.tft.probing.audio_probes import audio_component
from nxwright.tft.commands.compile import compile_project
from tools.tft.probing.component_probes import editor_file, with_components
from tools.tft.probing.packaging_probes import file_parts, probe_firmware
from tools.tft.probing.probe_runner import Probe
from nxwright.tft.project import Project

# Each sound's form: its rate, its bytes a sample, or "float" or "adpcm"
# (with_a_sound), and its channels.
_FORMS = [(8000, 1, 1), (8000, 2, 1), (8000, 2, 2), (11025, 1, 2), (11025, 2, 1),
          (16000, 2, 2), (44100, 2, 1), (44100, 2, 2), (48000, 2, 1), (48000, 2, 2),
          (4000, 2, 1), (96000, 2, 1), (192000, 2, 1),
          (44100, 3, 1), (8000, 3, 2), (44100, 4, 1), (44100, 2, 6), (44100, "float", 1),
          (44100, "adpcm", 1)]


def _resampled_whole_file(project: Path) -> dict:
    """Returns nxwright's file of `project`, part by part, its sounds resampled
    with the ffmpeg the PATH finds: a probe's ours."""
    loaded = Project.from_file(project)
    return file_parts(compile_project(loaded, probe_firmware(loaded.settings.model.series),
                                      find_ffmpeg(), any_release=True), "nxwright's file")


def float_wav(rate: int, channels: int) -> bytes:
    """Returns a WAV file of `rate` samples a second on `channels` channels,
    whose samples are floating-point numbers of 32 bits (format 3), which
    Python's wave module does not write: a ramp from -1 to 1."""
    samples = b"".join(struct.pack("<f", -1 + 2 * n / 255) for n in range(256)) * channels
    form = struct.pack("<HHIIHH", 3, channels, rate, rate * 4 * channels, 4 * channels, 32)
    body = (b"WAVE" + b"fmt " + struct.pack("<I", len(form)) + form
            + b"data" + struct.pack("<I", len(samples)) + samples)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _write_ramp(path: Path, rate: int, width: int, channels: int):
    """Writes at `path` a WAV file of `rate` samples a second, `width` bytes
    each, on `channels` channels: a ramp, rising by 8 a sample, of which a
    16-bit sample is two bytes."""
    with wave.open(str(path), "wb") as sound:
        sound.setnchannels(channels)
        sound.setsampwidth(width)
        sound.setframerate(rate)
        sound.writeframes(bytes(range(0, 256, 8)) * 8 * channels * width)


def with_a_sound(rate: int, width, channels: int):
    """Returns a probe's change: adds a sound of `rate` samples a second,
    `width` bytes each, on `channels` channels, which an audio plays. A
    `width` of "float" gives floating-point samples, and "adpcm" the 16-bit
    ramp compressed to Microsoft ADPCM by the ffmpeg the PATH finds."""
    def change(folder: Path):
        from nxwright.source.resource_adding import add_sound
        path = folder.parent / "tone.wav"
        if width == "float":
            path.write_bytes(float_wav(rate, channels))
        elif width == "adpcm":
            plain = folder.parent / "tone-16-bit.wav"
            _write_ramp(plain, rate, 2, channels)
            subprocess.run([find_ffmpeg(), "-y", "-loglevel", "error", "-i", str(plain),
                            "-acodec", "adpcm_ms", str(path)], check=True)
        else:
            _write_ramp(path, rate, width, channels)
        if width in (1, 2) and channels in (1, 2):
            add_sound(folder, path, name="tone")
        else:
            # add_sound makes such a sound 16-bit through ffmpeg. So it goes
            # in by hand, over the file of the sound add_sound wrote.
            add_sound(folder, path, name="tone", rate=rate, mono=True)
            (folder / "sounds" / "tone.wav").write_bytes(path.read_bytes())
        with_components(audio_component(vid=0))(folder)
    return change


def _channels(channels: int) -> str:
    """Returns how a probe's name gives a sound's `channels`."""
    return {1: "mono", 2: "stereo"}.get(channels, "%d-channels" % channels)


def _bits(width) -> str:
    """Returns how a probe's name gives a sound's bits a sample."""
    return {"float": "32-bit-float", "adpcm": "adpcm"}.get(width) or "%d-bit" % (8 * width)


PROBES = [Probe("%s-sound-%d-%s-%s" % (series.lower(), rate, _bits(width), _channels(channels)),
                series, with_a_sound(rate, width, channels), _resampled_whole_file,
                editor_file)
          for series in ("P", "E") for rate, width, channels in _FORMS]
