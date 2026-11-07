"""The probes of animations, videos, and sounds in a project
(packaging.py, ResearchNotes/tft/media-packaging.md), which P and E take and T
and K do not: projects on the P base folder, each with the component that
plays its media, compared with the Nextion Editor's whole file. Run them on
P with `tools.tft.probe run p_probes`, which takes them, and on E with
`tools.tft.probe run e_probes`.

Each probe makes its media on the spot with nxwright's resource_adding: an
animation or a video of still pictures of 8 by 8 pixels, each of one colour,
and a sound of 22050 samples a second, 16 bits each, the form the Nextion
Editor puts in a TFT file as it is. The probe of one of each keeps the whole
compile's fixtures (compile_probes.fixture_pieces), in p_probes.py's folder.
"""
from pathlib import Path
import wave

from PIL import Image

from tools.tft.probing.audio_probes import audio_component
from tools.tft.probing.component_probes import editor_file, whole_file, with_components
from tools.tft.probing.gmov_probes import gmov_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.video_probes import video_component


def _frames(folder: Path, name: str, count: int) -> list:
    """Writes `count` pictures of 8 by 8 pixels, each of one colour, beside
    the source folder `folder`, named after `name`, and returns their
    paths."""
    paths = []
    for number in range(count):
        path = folder.parent / ("%s-%d.png" % (name, number))
        Image.new("RGB", (8, 8), (40 * number, 255 - 40 * number, 80)).save(path)
        paths.append(path)
    return paths


def add_animation(folder: Path, name: str, frames: int, duration: int = 100):
    """Adds to the source folder `folder` the animation `name` of `frames`
    frames, each lasting `duration` ms."""
    from nxwright.source.resource_adding import add_animation as added
    added(folder, _frames(folder, name, frames), duration=duration, name=name)


def add_video(folder: Path, name: str, frames: int):
    """Adds to the source folder `folder` the video `name` of `frames`
    frames, 10 a second."""
    from nxwright.source.resource_adding import add_video as added
    added(folder, _frames(folder, name, frames), rate=10, name=name)


def add_sound(folder: Path, name: str, channels: int = 1):
    """Adds to the source folder `folder` the sound `name`, of 22050
    samples a second, 16 bits each, on `channels` channels."""
    from nxwright.source.resource_adding import add_sound as added
    path = folder.parent / (name + ".wav")
    with wave.open(str(path), "wb") as sound:
        sound.setnchannels(channels)
        sound.setsampwidth(2)
        sound.setframerate(22050)
        sound.writeframes(bytes(range(0, 256, 8)) * 8 * channels)
    added(folder, path, name=name)


def _with(media, *components: str, code: str = ""):
    """Returns a probe's change: adds `media`, each a function of the source
    folder, then `components` and the event code `code` on page0."""
    def change(folder: Path):
        for add in media:
            add(folder)
        with_components(*components, code=code)(folder)
    return change


PROBES = [
    # One animation, which a gmov plays: row 9 of the section's table.
    Probe("media-an-animation", "P", _with(
        [lambda folder: add_animation(folder, "anim", 2)], gmov_component(vid=0)),
        whole_file, editor_file),
    # Two animations, of 3 frames and of 2 lasting longer: their headers
    # first, then their frames; the gmov plays the second.
    Probe("media-two-animations", "P", _with(
        [lambda folder: add_animation(folder, "anim", 3),
         lambda folder: add_animation(folder, "anim2", 2, duration=200)],
        gmov_component(vid=1)), whole_file, editor_file),
    # One video, which a video plays: row 10.
    Probe("media-a-video", "P", _with(
        [lambda folder: add_video(folder, "clip", 2)], video_component(vid=0)),
        whole_file, editor_file),
    # Two videos, of 2 and 3 frames; the video plays the second.
    Probe("media-two-videos", "P", _with(
        [lambda folder: add_video(folder, "clip", 2), lambda folder: add_video(folder, "clip2", 3)],
        video_component(vid=1)), whole_file, editor_file),
    # One sound, mono, which an audio plays: row 11, a header of 16 bytes,
    # then the file.
    Probe("media-a-sound", "P", _with(
        [lambda folder: add_sound(folder, "beep")], audio_component(vid=0)),
        whole_file, editor_file),
    # Two sounds, mono and stereo; the audio plays the second.
    Probe("media-two-sounds", "P", _with(
        [lambda folder: add_sound(folder, "beep"), lambda folder: add_sound(folder, "beep2", 2)],
        audio_component(vid=1)), whole_file, editor_file),
    # A gmov and a video with an effect, its first, and its time, each
    # playing a resource of its kind. The Nextion Editors 1.63.3 and 1.60.1
    # refuse a vid that gives no such resource (older_editor_probes.py).
    Probe("media-an-animation-with-an-effect", "P", _with(
        [lambda folder: add_animation(folder, "anim", 2)],
        gmov_component(vid=0, effect=2, first=10, time=500)), whole_file, editor_file),
    Probe("media-a-video-with-an-effect", "P", _with(
        [lambda folder: add_video(folder, "clip", 2)],
        video_component(vid=0, effect=2, first=10, time=500)), whole_file, editor_file),
    # One of each, with the components that play them, each vid past its
    # project's last resource of its kind, and their vids in code.
    Probe("media-of-each", "P", _with(
        [lambda folder: add_animation(folder, "anim", 2),
         lambda folder: add_video(folder, "clip", 2), lambda folder: add_sound(folder, "beep")],
        gmov_component(vid=5), video_component(x=150, vid=3), audio_component(vid=4),
        code="on page0.up:\n  gm0.vid=0\n  sys0=vd0.vid\n  wav0.vid=0\n"),
        whole_file, editor_file),
]
