"""The probes of the device settings that packaging writes beside the
screen, the rotation, the encoding, and the one-time update (packaging.py):
the memory file's storage size, and the two flags that ignore library and
image resources. Each base folder, with a picture beside its font, sets one
of them in app.toml, and is compared with the Nextion Editor's whole file.
On P, one more has an animation, a video, and a sound, and sets both flags.
Run them with `tools.tft.probe run device_setting_probes`.

The project password has no probe. The Nextion Editor asks for it when it
opens the project, which the Editor tool cannot answer. Its file of a
project with the password "abc", answered by hand, was the file without
the password, byte for byte.
"""
from pathlib import Path

from PIL import Image

from tools.tft.probing.audio_probes import audio_component
from tools.tft.probing.component_probes import editor_file, whole_file, with_components
from tools.tft.probing.gmov_probes import gmov_component
from tools.tft.probing.media_probes import add_animation, add_sound, add_video
from tools.tft.probing.probe_runner import BASE_MODELS, Probe
from tools.tft.probing.video_probes import video_component

# Each probe's keys of app.toml, by the words its name ends with.
_SETTINGS = {
    "memory-file": "memory_file_storage_size = 100000\n",
    "ignoring-images": "ignore_image_resources = true\n",
    "ignoring-fonts": "ignore_library_resources = true\n",
}


def _add_picture(folder: Path):
    from nxwright.source.resource_adding import add_pictures
    # Drawn beside the folder, which add_pictures copies it into.
    picture = folder.parent / "red.png"
    Image.new("RGB", (8, 4), (255, 0, 0)).save(picture)
    add_pictures(folder, [picture])


def _with_settings(keys: str, media: bool = False):
    """Returns a probe's change: adds a picture, and with `media` an
    animation, a video, and a sound with the components that play them,
    then appends `keys` to app.toml."""
    def change(folder: Path):
        _add_picture(folder)
        if media:
            add_animation(folder, "anim", 2)
            add_video(folder, "clip", 2)
            add_sound(folder, "beep")
            with_components(gmov_component(vid=0), video_component(x=150, vid=1),
                            audio_component(vid=2))(folder)
        app = folder / "app.toml"
        app.write_bytes(app.read_bytes() + keys.encode("utf-8"))
    return change


PROBES = [Probe("device-settings-%s-%s" % (series, name), series, _with_settings(keys),
                whole_file, editor_file)
          for series in BASE_MODELS for name, keys in _SETTINGS.items()] + [
    Probe("device-settings-P-ignoring-both-beside-media", "P",
          _with_settings(_SETTINGS["ignoring-images"] + _SETTINGS["ignoring-fonts"], media=True),
          whole_file, editor_file),
]
