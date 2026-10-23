"""Running ffmpeg, a widely used program that reads videos and sounds of
most kinds: to cut a video file into frames, and to convert a sound.
nxwright needs it for nothing else, so it is optional: a command that would
need it says so when it is not found. The Editor's VideoBox runs a copy of
its own the same way.
"""
from pathlib import Path
import shutil
import subprocess

from nxwright import NxwrightError


def find_ffmpeg(given: Path = None):
    """Returns the ffmpeg program to run: `given`, when it names one, or
    else the one the system's PATH finds, or None when there is none."""
    if given is not None:
        if not Path(given).is_file():
            raise NxwrightError("%s is not a program" % given)
        return str(given)
    return shutil.which("ffmpeg")


def video_as_pngs(ffmpeg: str, video: Path, folder: Path, rate: int, size: tuple = None,
                  start: float = None, length: float = None) -> list:
    """Cuts `video`, a video file ffmpeg reads, into PNG pictures of 8 bits
    a channel in `folder`, an empty folder, `rate` a second, as VideoBox has
    ffmpeg cut one: from `start` seconds in, for `length` seconds, or the
    whole video; scaled to `size`, (width, height), or at its own size.
    Returns the pictures' paths, in order. Raises NxwrightError, with
    ffmpeg's own words, when it cannot, or when it cut no picture."""
    command = [ffmpeg, "-v", "error", "-i", str(video)]
    # After the input, as VideoBox gives them: the cut starts at that very time.
    if start is not None:
        command += ["-ss", "%.3f" % start]
    if length is not None:
        command += ["-t", "%.3f" % length]
    command += ["-r", str(rate)]
    if size is not None:
        command += ["-vf", "scale=%d:%d" % size]
    _run(command + ["-pix_fmt", "rgb24", "-f", "image2", str(folder / "%05d.png")], video)
    pictures = sorted(folder.glob("*.png"), key=lambda picture: int(picture.stem))
    if not pictures:
        raise NxwrightError("ffmpeg cut no picture from %s" % video.name)
    return pictures


def sound_as_wav(ffmpeg: str, sound: Path, folder: Path, rate: int = None,
                 mono: bool = False) -> bytes:
    """Returns `sound`, a sound file ffmpeg reads, as a WAV file of 16-bit
    PCM samples, at `rate` samples a second, or its own, in one channel
    when `mono`, or in its own channels. ffmpeg writes it in `folder`, an
    empty folder, since a WAV file's header gives sizes it can only write
    once the samples are written. Raises NxwrightError, with ffmpeg's own
    words, when it cannot."""
    command = [ffmpeg, "-v", "error", "-i", str(sound), "-vn", "-acodec", "pcm_s16le"]
    if rate is not None:
        command += ["-ar", str(rate)]
    if mono:
        command += ["-ac", "1"]
    written = folder / "sound.wav"
    _run(command + ["-f", "wav", str(written)], sound)
    return written.read_bytes()


def _run(command: list, read: Path, seconds: float = None) -> subprocess.CompletedProcess:
    """Runs ffmpeg's `command`, which reads the file `read`, with nothing to
    read from its input, so that it never waits for a key. Raises
    NxwrightError, with ffmpeg's own words, when it fails or takes past
    `seconds`."""
    try:
        done = subprocess.run(command, capture_output=True, stdin=subprocess.DEVNULL,
                              timeout=seconds)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise NxwrightError("ffmpeg could not run: %s" % error) from None
    if done.returncode != 0:
        said = done.stderr.decode("utf-8", "replace").strip()
        raise NxwrightError("ffmpeg could not read %s%s" % (read.name, ": " + said if said else ""))
    return done
