"""The probes of the external picture (component_types/external_picture.py),
a type P and E have and T and K have not: projects on the P base folder,
each compared with the Nextion Editor's whole file. Run them on P with
`tools.tft.probe run p_probes`, which takes them, and on E with
`tools.tft.probe run e_probes`.

The probes of one at its defaults and of two beside a switch keep the user
code as their fixtures (kept), in p_probes.py's folder.
"""
from tools.tft.probing.component_probes import editor_file, user_code_kept, whole_file, with_components
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.switch_probes import switch_component


def external_picture(name: str = "xp0", x: int = 10, y: int = 10, w: int = 120, h: int = 120,
                     path: str = None, **attributes: int) -> str:
    """Returns an external picture in a page file's form, its path and its
    other attributes, such as path_m, at their defaults unless given."""
    return ('\n[[component]]\nname = "%s"\ntype = "external-picture"\nx = %d\ny = %d\n'
            'w = %d\nh = %d\n' % (name, x, y, w, h)
            + ('path = "%s"\n' % path if path is not None else "")
            + "".join("%s = %d\n" % item for item in attributes.items()))


PROBES = [
    # One at its defaults, but for its place and size: an empty path, its
    # path_m 255.
    Probe("external-picture-at-its-defaults", "P", with_components(external_picture()),
          whole_file, editor_file, kept=user_code_kept),
    # A path of each of the characters the rule takes, in a room of 20.
    Probe("external-picture-path", "P", with_components(external_picture(
        path="sd0/Pic_1.jpg", path_m=20)), whole_file, editor_file),
    # The least room, 1, with an empty path.
    Probe("external-picture-least-room", "P", with_components(external_picture(path_m=1)),
          whole_file, editor_file),
    # Two beside a switch: their paths and its txt after the page's
    # components' memory, in the components' order.
    Probe("external-picture-two-beside-a-switch", "P", with_components(
        external_picture(path="sd0/a.jpg", path_m=12), switch_component(y=140),
        external_picture("xp1", y=180, w=100, h=100, path="b.png")),
        whole_file, editor_file, kept=user_code_kept),
    # Its place and size, and its path, in code, read and set, beside a
    # switch whose entries follow its own.
    Probe("external-picture-in-code", "P", with_components(
        external_picture(), switch_component(y=140), code=(
            "on page0.up:\n  sys0=xp0.w\n  xp0.x=5\n  sys1=sw0.val\n  if(xp0.h>10)\n  {\n"
            "    sys2=1\n  }\n  xp0.path=\"sd0/b.jpg\"\n  if(xp0.path==\"b.png\")\n  {\n"
            "    sys2=2\n  }\n")),
        whole_file, editor_file),
    # The attributes every component has, away from their defaults: its
    # effect moves its entries from 19 on, and their owner fields, two on.
    Probe("external-picture-shared-attributes", "P", with_components(external_picture(
        aph=50, sendkey=3, drag=1, lockobj=1, movex=5, movey=6, groupid0=1, groupid1=2,
        effect=2, first=10, time=500)), whole_file, editor_file),
]
