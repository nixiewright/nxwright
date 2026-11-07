"""The probes of the gmov (component_types/gmov.py), a type P and E have and
T and K have not: projects on the P base folder, without animations, each
compared with the Nextion Editor's whole file. Run them on P with
`tools.tft.probe run p_probes`, which takes them, and on E with
`tools.tft.probe run e_probes`.

The probes of a gmov at its defaults and of two gmovs beside a text keep
the user code as their fixtures (kept), in p_probes.py's folder.
"""
from tools.tft.probing.component_probes import editor_file, user_code_kept, whole_file, with_components
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.text_probes import text_component


def gmov_component(name: str = "gm0", x: int = 10, y: int = 10, w: int = 128, h: int = 128,
                   path: str = None, **attributes: int) -> str:
    """Returns a gmov component in a page file's form, its path and its
    other attributes, such as en, at their defaults unless given."""
    return ('\n[[component]]\nname = "%s"\ntype = "gmov"\nx = %d\ny = %d\nw = %d\nh = %d\n'
            % (name, x, y, w, h) + ('path = "%s"\n' % path if path is not None else "")
            + "".join("%s = %d\n" % item for item in attributes.items()))


PROBES = [
    # A gmov at its defaults, but for its place and size: no animation, its
    # path's room 256 bytes, and its buffer of 12000 bytes.
    Probe("gmov-at-its-defaults", "P", with_components(gmov_component()), whole_file,
          editor_file, kept=user_code_kept),
    # Each of its values away from its default, the least dis among them,
    # and a molloc and a molloc_s that change nothing.
    Probe("gmov-values", "P", with_components(gmov_component(
        en=2, loop=0, dis=10, tim=7, path_m=20, molloc=20000, molloc_s=30000)),
        whole_file, editor_file),
    # Its highest values, and its path_m at 1024; room_probes.py takes its
    # path_m to its most.
    Probe("gmov-highest-values", "P", with_components(gmov_component(
        en=0, dis=1000, tim=0x7FFFFFFF, path_m=1024)), whole_file, editor_file),
    # Its tim, stim, and qty at their entries' lowest, then at their
    # highest, each one further in than the last, so that each differs.
    *[Probe("gmov-%s-times" % end, "P", with_components(gmov_component(
        **{name: value + step * number for number, name in enumerate(("tim", "stim", "qty"))})),
        whole_file, editor_file)
      for end, value, step in (("lowest", -2 ** 31, 1), ("highest", 2 ** 31 - 1, -1))],
    # At a from of 1: no vid entry, each later one a number less, and its
    # attributes after it in code.
    Probe("gmov-of-from-1", "P", with_components(gmov_component(**{"from": 1}), code=(
        "on page0.up:\n  sys0=gm0.en\n  sys1=gm0.tim\n  gm0.dis=200\n")),
        whole_file, editor_file),
    # At a from of 1, a vid away from its default, which it does not write.
    Probe("gmov-of-from-1-with-a-vid", "P", with_components(
        gmov_component(vid=3, **{"from": 1})), whole_file, editor_file),
    # Two gmovs beside a text: their paths and the text's txt after the
    # page's components' memory, then their buffers, in order. The second is
    # at a from of 1, its path in the least path_m, 1.
    Probe("gmov-two-beside-a-text", "P", with_components(
        gmov_component(), text_component(y=150),
        gmov_component("gm1", y=190, path_m=1, **{"from": 1})),
        whole_file, editor_file, kept=user_code_kept),
    # Two paths that hold, between them, each of the characters the rule
    # takes, in a room of 20: one at a from of 0, the other at 1.
    Probe("gmov-paths", "P", with_components(
        gmov_component(path="sd0/Mov_1.gmov", path_m=20),
        gmov_component("gm1", y=150, path="a.b", path_m=20, **{"from": 1})),
        whole_file, editor_file),
    # Its attributes in code: read, set, and in a condition, beside a text
    # whose entries follow its own, and code in its playend event.
    Probe("gmov-in-code", "P", with_components(
        gmov_component(), text_component(y=150), code=(
            "on page0.up:\n  sys0=gm0.tim\n  gm0.en=0\n  gm0.dis=200\n  gm0.tim=100\n"
            "  sys1=gm0.qty\n  gm0.path=\"a\"\n  t0.txt=gm0.path\n  if(gm0.en==1)\n  {\n"
            "    sys2=1\n  }\non gm0.playend:\n  sys2=2\n")),
        whole_file, editor_file),
    # The attributes every component has, away from their defaults: its
    # effect moves its entries from 19 on, and their owner fields, two on.
    Probe("gmov-shared-attributes", "P", with_components(gmov_component(
        aph=50, sendkey=3, drag=1, lockobj=1, movex=5, movey=6, groupid0=1, groupid1=2,
        effect=2, first=10, time=500)), whole_file, editor_file),
]
