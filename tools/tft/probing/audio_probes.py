"""The probes of the audio (component_types/audio.py), a type P and E have
and T and K have not: projects on the P base folder, each compared with the
Nextion Editor's whole file. Run them on P with `tools.tft.probe run
p_probes`, which takes them, and on E with `tools.tft.probe run e_probes`.

The probes of an audio at its defaults and of two audios beside a text keep
the user code as their fixtures (kept), in p_probes.py's folder.
"""
from tools.tft.probing.component_probes import editor_file, user_code_kept, whole_file, with_components
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.text_probes import text_component


def audio_component(name: str = "wav0", path: str = None, **attributes: int) -> str:
    """Returns an audio component in a page file's form, its path and its
    other attributes, such as en, at their defaults unless given. Its from
    is given as `**{"from": 1}`, as from is a word of Python's."""
    return ('\n[[component]]\nname = "%s"\ntype = "audio"\n' % name
            + ('path = "%s"\n' % path if path is not None else "")
            + "".join("%s = %d\n" % item for item in attributes.items()))


def _under_later_rooms(folder):
    """Adds a page of two texts and an audio, then a second page of two
    texts, the second's room wide enough to lie over the whole of the first
    page's audio in the Nextion Editor's scratch image."""
    with_components(text_component(), text_component("t1", y=60),
                    audio_component(en=0, loop=0, tim=10, stim=5, qty=3))(folder)
    with_components(text_component(), text_component("t1", y=60, txt_maxl=100),
                    page="page1")(folder)


# From a file, of a path of its own.
_FROM_A_FILE = {"path": "sd0/a.wav", "path_m": 20, "from": 1}

PROBES = [
    # An audio at its defaults, from the project: its memory, entries,
    # record, and buffer, and its init in its page's load section.
    Probe("audio-at-its-defaults", "P", with_components(audio_component()),
          whole_file, editor_file, kept=user_code_kept),
    # From the project, each of its values away from its default, beside a
    # text, its path, path_m, molloc, and molloc_s among them, which change
    # nothing.
    Probe("audio-values", "P", with_components(text_component(), audio_component(
        path="sd0/a.wav", path_m=20, en=0, loop=0, fps=25, dis=50, tim=10, stim=5, qty=3,
        molloc=1000, molloc_s=2000)), whole_file, editor_file),
    # Its tim, stim, and qty at their entries' lowest, then at their
    # highest, each one further in than the last, so that each differs.
    *[Probe("audio-%s-times" % end, "P", with_components(audio_component(
        **{name: value + step * number for number, name in enumerate(("tim", "stim", "qty"))})),
        whole_file, editor_file)
      for end, value, step in (("lowest", -2 ** 31, 1), ("highest", 2 ** 31 - 1, -1))],
    # From a file: its path's entry, and its path's room after the text's
    # txt.
    Probe("audio-from-a-file", "P", with_components(
        text_component(), audio_component(**_FROM_A_FILE, en=2)), whole_file, editor_file),
    # From a file, a vid away from its default, which it does not write.
    Probe("audio-from-a-file-with-a-vid", "P", with_components(
        audio_component(**_FROM_A_FILE, vid=3)), whole_file, editor_file),
    # One from a file and one from the project, beside a text: the first's
    # path's room, then the text's txt, then their buffers in order.
    Probe("audio-two-beside-a-text", "P", with_components(
        audio_component(**_FROM_A_FILE), text_component(), audio_component("wav1")),
        whole_file, editor_file, kept=user_code_kept),
    # A later page's txt's room over an audio's memory, which keeps its
    # values in the scratch image but for its head's.
    Probe("audio-under-later-rooms", "P", _under_later_rooms, whole_file, editor_file),
    # From the project, its attributes in code: read, set, and in a
    # condition, and its playend event's own code.
    Probe("audio-in-code", "P", with_components(text_component(), audio_component(), code=(
        "on wav0.playend:\n  sys0=1\n"
        "on page0.up:\n  sys0=wav0.en\n  wav0.en=0\n  sys1=wav0.tim\n  wav0.tim=100\n"
        "  wav0.dis=20\n  sys2=wav0.qty\n  wav0.vid=0\n  sys0=wav0.from\n"
        "  if(wav0.en==1)\n  {\n    sys2=1\n  }\n")), whole_file, editor_file),
    # From a file, its path in code: set from a text, read into a txt, and
    # compared, and its other entries one on.
    Probe("audio-from-a-file-in-code", "P", with_components(
        text_component(), audio_component(**_FROM_A_FILE), code=(
            "on page0.up:\n  wav0.path=\"sd0/b.wav\"\n  t0.txt=wav0.path\n  sys0=wav0.en\n"
            "  if(wav0.path==\"sd0/b.wav\")\n  {\n    sys2=1\n  }\n")),
        whole_file, editor_file),
]
