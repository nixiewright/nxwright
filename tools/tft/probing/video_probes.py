"""The probes of the video (component_types/video.py), a type P and E have
and T and K have not: projects on the P base folder, without videos, each
compared with the Nextion Editor's whole file. Run them on P with
`tools.tft.probe run p_probes`, which takes them, and on E with
`tools.tft.probe run e_probes`.

The probes of a video at its defaults and of two videos beside a text keep
the user code as their fixtures (kept), in p_probes.py's folder.
"""
from tools.tft.probing.component_probes import editor_file, user_code_kept, whole_file, with_components
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.text_probes import text_component


def video_component(name: str = "vd0", x: int = 10, y: int = 10, w: int = 128, h: int = 128,
                    path: str = None, **attributes: int) -> str:
    """Returns a video component in a page file's form, its path and its
    other attributes, such as from, at their defaults unless given."""
    return ('\n[[component]]\nname = "%s"\ntype = "video"\nx = %d\ny = %d\nw = %d\nh = %d\n'
            % (name, x, y, w, h)
            + ('path = "%s"\n' % path if path is not None else "")
            + "".join("%s = %d\n" % item for item in attributes.items()))


PROBES = [
    # A video at its defaults, from the project, but for its place and size:
    # no video, no path, and its buffer of 64000 bytes.
    Probe("video-at-its-defaults", "P", with_components(video_component()), whole_file,
          editor_file, kept=user_code_kept),
    # Each of its values away from its default, the least fps and dis
    # among them; and a path, a path_m, a molloc, and a molloc_s, which
    # change nothing from the project.
    Probe("video-values", "P", with_components(video_component(
        path="sd0/a.video", en=2, loop=0, fps=0, dis=10, tim=7, path_m=20, molloc=30000,
        molloc_s=20000)), whole_file, editor_file),
    # Its highest values.
    Probe("video-highest-values", "P", with_components(video_component(
        en=0, fps=50, dis=1000, tim=0x7FFFFFFF)), whole_file, editor_file),
    # Its tim, stim, and qty at their entries' lowest, then at their
    # highest, each one further in than the last, so that each differs.
    *[Probe("video-%s-times" % end, "P", with_components(video_component(
        **{name: value + step * number for number, name in enumerate(("tim", "stim", "qty"))})),
        whole_file, editor_file)
      for end, value, step in (("lowest", -2 ** 31, 1), ("highest", 2 ** 31 - 1, -1))],
    # From a file: its path's entry in vid's place, its path's room, and
    # its attributes after it in code.
    Probe("video-from-a-file", "P", with_components(
        video_component(path="sd0/Vid_1.video", **{"from": 1}), code=(
            "on page0.up:\n  sys0=vd0.en\n  vd0.path=\"sd0/b.video\"\n  sys1=vd0.tim\n")),
        whole_file, editor_file),
    # From a file, a vid away from its default, which it does not write.
    Probe("video-from-a-file-with-a-vid", "P", with_components(
        video_component(path="sd0/Vid_1.video", vid=3, **{"from": 1})),
        whole_file, editor_file),
    # Two videos beside a text: the second's path and the text's txt after
    # the page's components' memory, then their buffers, in order. The
    # second is from a file, its path in the least path_m, 1.
    Probe("video-two-beside-a-text", "P", with_components(
        video_component(), text_component(y=150),
        video_component("vd1", y=190, path="a", path_m=1, **{"from": 1})),
        whole_file, editor_file, kept=user_code_kept),
    # Its attributes in code: read, set, and in a condition, beside a text
    # whose entries follow its own, and code in its playend event.
    Probe("video-in-code", "P", with_components(
        video_component(), text_component(y=150), code=(
            "on page0.up:\n  sys0=vd0.tim\n  vd0.en=0\n  vd0.dis=200\n  vd0.tim=100\n"
            "  sys1=vd0.qty\n  sys2=vd0.vid\n  if(vd0.en==1)\n  {\n    sys2=1\n  }\n"
            "on vd0.playend:\n  sys2=2\n")),
        whole_file, editor_file),
    # The attributes every component has, away from their defaults: its
    # effect moves its entries from 19 on, and their owner fields, two on.
    Probe("video-shared-attributes", "P", with_components(video_component(
        aph=50, sendkey=3, drag=1, lockobj=1, movex=5, movey=6, groupid0=1, groupid1=2,
        effect=2, first=10, time=500)), whole_file, editor_file),
]
