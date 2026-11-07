"""The probes of the sliding text (component_types/sliding_text.py), a type
P and E have and T and K have not: projects on the P base folder, each
compared with the Nextion Editor's whole file. Run them on P with
`tools.tft.probe run p_probes`, which takes them, and on E with
`tools.tft.probe run e_probes`.

The probes of a sliding text at its defaults and of two sliding texts
beside a text keep the user code as their fixtures (kept), in
p_probes.py's folder.
"""
from tools.tft.probing.component_probes import editor_file, user_code_kept, whole_file, with_components
from tools.tft.probing.key_probes import KeyboardChange
from tools.tft.probing.picture_probes import BACKGROUNDS, with_a_background
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.text_probes import text_component


def sliding_text_component(name: str = "slt0", x: int = 10, y: int = 10, w: int = 120,
                           h: int = 120, txt: str = None, path: str = None,
                           **attributes: int) -> str:
    """Returns a sliding text component in a page file's form, in the base
    folder's font, its txt and its path, whose lines "\\r\\n" separates, and
    its other attributes, such as path_m, at their defaults unless given."""
    def escaped(text: str) -> str:
        return text.replace("\r", "\\r").replace("\n", "\\n")
    return ('\n[[component]]\nname = "%s"\ntype = "sliding-text"\nx = %d\ny = %d\nw = %d\n'
            'h = %d\nfont = "NotoSans24"\n' % (name, x, y, w, h)
            + ('txt = "%s"\n' % escaped(txt) if txt is not None else "")
            + ('path = "%s"\n' % escaped(path) if path is not None else "")
            + "".join("%s = %d\n" % item for item in attributes.items()))


PROBES = [
    # A sliding text at its defaults, but for its place and size: ten
    # lines in a txt_maxl of 256, and its path's room as large, its path_m
    # 0.
    Probe("sliding-text-at-its-defaults", "P", with_components(sliding_text_component()),
          whole_file, editor_file, kept=user_code_kept),
    # Each of its values away from its default, its lines in a txt_maxl of
    # 20 and its path in a path_m of 20 among them.
    Probe("sliding-text-values", "P", with_components(sliding_text_component(
        txt="Ab\r\n9z\r\nc", txt_maxl=20, path_m=20, xcen=2, left=0, ch=0, isbr=0, spax=3,
        spay=4, bco=1234, pco=2345)), whole_file, editor_file),
    # Its highest values, its txt_maxl and its path_m 1024; room_probes.py
    # takes its path_m to its most.
    Probe("sliding-text-highest-values", "P", with_components(sliding_text_component(
        txt_maxl=1024, path_m=1024, xcen=1, left=2, ch=32, spax=255, spay=255)),
        whole_file, editor_file),
    # Its leftshow and key away from their defaults, which have no entry:
    # its leftshow lies in its memory, and a key of no keyboard nowhere.
    Probe("sliding-text-of-leftshow-and-key", "P", with_components(sliding_text_component(
        leftshow=1, key=5)), whole_file, editor_file),
    # Its key bound to the keypad, global as nxwright's build requires,
    # beside nxwright's keypad page.
    Probe("sliding-text-on-the-keypad", "P", KeyboardChange(
        with_components(sliding_text_component(key=2, vscope=1)), "keypad"),
        whole_file, editor_file),
    # Its maxval_y and val_y, where it is scrolled to, at their entries'
    # lowest and highest, 4 bytes each, each near its limit different from
    # the other.
    Probe("sliding-text-lowest-y-values", "P", with_components(sliding_text_component(
        maxval_y=-2 ** 31, val_y=-2 ** 31 + 1)), whole_file, editor_file, kept=user_code_kept),
    Probe("sliding-text-highest-y-values", "P", with_components(sliding_text_component(
        maxval_y=2 ** 31 - 1, val_y=2 ** 31 - 2)), whole_file, editor_file, kept=user_code_kept),
    # Two paths of lines of letters and digits, as its txt takes: one in a
    # path_m of 20, the other at a path_m of 0, filling its txt_maxl's room,
    # 10.
    Probe("sliding-text-paths", "P", with_components(
        sliding_text_component(path="Ab\r\n9z\r\nc", path_m=20),
        sliding_text_component("slt1", y=140, txt="ab", txt_maxl=10, path="cdefghijkl")),
        whole_file, editor_file),
    # Two sliding texts beside a text: each one's memory, and their txts
    # and paths after the page's components' memory, in order. The first's
    # path takes its txt_maxl, 10, as its path_m is 0; the second's path_m
    # is the least, 1.
    Probe("sliding-text-two-beside-a-text", "P", with_components(
        sliding_text_component(txt="ab\r\ncd", txt_maxl=10), text_component(y=140),
        sliding_text_component("slt1", y=180, txt_maxl=50, path_m=1)),
        whole_file, editor_file, kept=user_code_kept),
    # Its attributes in code: read, set, and in a condition, beside a text
    # whose entries follow its own.
    Probe("sliding-text-in-code", "P", with_components(
        sliding_text_component(), text_component(y=140), code=(
            "on page0.up:\n  sys0=slt0.val_y\n  slt0.val_y=10\n  sys1=slt0.maxval_y\n"
            "  slt0.txt=\"ab\\rcd\"\n  t0.txt=slt0.txt\n  slt0.left=1\n  slt0.spay=2\n"
            "  if(slt0.val_y>5)\n  {\n    sys2=1\n  }\n")),
        whole_file, editor_file),
    # The attributes every component has, away from their defaults: its
    # effect moves its entries from 19 on, and their owner fields, two on.
    Probe("sliding-text-shared-attributes", "P", with_components(sliding_text_component(
        aph=50, sendkey=3, drag=1, lockobj=1, movex=5, movey=6, groupid0=1, groupid1=2,
        effect=2, first=10, time=500)), whole_file, editor_file),
    # With a crop of a picture, a picture, or nothing behind it, its
    # sta 0, 2, and 3, where its default is 1, a colour.
] + [Probe("sliding-text-with-%s-behind" % background, "P",
            with_a_background(sliding_text_component, background), whole_file, editor_file,
            kept=user_code_kept) for background in BACKGROUNDS]
# Each other style it takes: 1, a border of one colour, here of a borderc
# and a borderw of their own; 2, sunken; and 3, raised.
PROBES += [Probe("sliding-text-of-style-%d" % style, "P", with_components(sliding_text_component(
    style=style, **({"borderc": 1111, "borderw": 3} if style == 1 else {}))),
    whole_file, editor_file, kept=user_code_kept) for style in (1, 2, 3)]
# A border of one colour, its style 1, with each of those behind it.
PROBES += [Probe("sliding-text-of-style-1-with-%s-behind" % background, "P",
                 with_a_background(sliding_text_component, background, style=1, borderc=1111,
                                   borderw=3),
                 whole_file, editor_file, kept=user_code_kept) for background in BACKGROUNDS]
# Its path and its other entries in code, as its border and what lies
# behind it move them: at a style of 1, and with nothing behind it.
PROBES += [Probe("sliding-text-in-code-%s" % name, "P", with_components(
    sliding_text_component(**attributes), text_component(y=140), code=(
        "on page0.up:\n  slt0.path=\"a\"\n  sys0=slt0.val_y\n  t0.txt=slt0.txt\n"
        "  slt0.spay=2\n")),
    whole_file, editor_file, kept=user_code_kept)
    for name, attributes in (("of-style-1", {"style": 1, "borderc": 1111, "borderw": 3}),
                             ("with-nothing-behind", {"sta": 3}))]
# A 3D border, its style 2, sunken, and 3, raised, with each of those behind it.
PROBES += [Probe("sliding-text-of-style-%d-with-%s-behind" % (style, background), "P",
                 with_a_background(sliding_text_component, background, style=style), whole_file,
                 editor_file, kept=user_code_kept)
           for style in (2, 3) for background in BACKGROUNDS]
