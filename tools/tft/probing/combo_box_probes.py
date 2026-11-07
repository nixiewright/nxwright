"""The probes of the combo-box (component_types/combo_box.py), a type P and
E have and T and K have not: projects on the P base folder, each compared
with the Nextion Editor's whole file. Run them on P with
`tools.tft.probe run p_probes`, which takes them, and on E with
`tools.tft.probe run e_probes`.

The probes of a combo-box at its defaults and of two combo-boxes beside a
text keep the user code as their fixtures (kept), in p_probes.py's folder.
"""
from tools.tft.probing.component_probes import editor_file, user_code_kept, whole_file, with_components
from tools.tft.probing.picture_probes import BACKGROUNDS, with_a_background
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.text_probes import text_component


def combo_box_component(name: str = "cb0", x: int = 10, y: int = 10, w: int = 100,
                        h: int = 42, txt: str = None, path: str = None,
                        **attributes: int) -> str:
    """Returns a combo-box component in a page file's form, in the base
    folder's font, its txt, its path, whose items "\\r\\n" separates, and
    its other attributes, such as val, at their defaults unless given."""
    escaped = None if path is None else path.replace("\r", "\\r").replace("\n", "\\n")
    return ('\n[[component]]\nname = "%s"\ntype = "combo-box"\nx = %d\ny = %d\nw = %d\n'
            'h = %d\nfont = "NotoSans24"\n' % (name, x, y, w, h)
            + ('txt = "%s"\n' % txt if txt is not None else "")
            + ('path = "%s"\n' % escaped if escaped is not None else "")
            + "".join("%s = %d\n" % item for item in attributes.items()))


PROBES = [
    # A combo-box at its defaults, but for its place and size: six items,
    # in a path_m of 256.
    Probe("combo-box-at-its-defaults", "P", with_components(combo_box_component()),
          whole_file, editor_file, kept=user_code_kept),
    # Each of its values away from its default, the least of qty, hig, and
    # wid among them, and its items in a path_m of 20.
    Probe("combo-box-values", "P", with_components(combo_box_component(
        txt="ab1", path="Ab\r\n9z\r\nc", txt_maxl=20, path_m=20, val=2, dis=50, xcen=0,
        ycen=2, spax=3, pco3=1111, bco1=2222, pco1=3333, bco2=4444, pco2=5555, bco=6666,
        pco=7777, dir=0, qty=1, vvs0=5, hig=16, down=1, wid=8, vvs1=4, ch=0)),
        whole_file, editor_file),
    # Its highest values, with one item in a path_m of 1024; room_probes.py
    # takes its path_m to its most.
    Probe("combo-box-highest-values", "P", with_components(combo_box_component(
        path="a", txt="a", txt_maxl=200, path_m=1024, dis=100, spax=255, dir=3, qty=254,
        vvs0=255, hig=255, wid=255, vvs1=255, ch=32)), whole_file, editor_file),
    # Without its arrow, an up of 0, its arrow's colour away from its
    # default, and its attributes after it in code.
    Probe("combo-box-without-its-arrow", "P", with_components(
        combo_box_component(up=0, pco3=1234), code=(
            "on page0.up:\n  sys0=cb0.val\n  sys1=cb0.ch\n  cb0.path=\"a\\rb\"\n")),
        whole_file, editor_file),
    # The marks that show the list scrolls: none, a mode of 0, and a
    # triangle, 1, each with its size and space away from their defaults.
    Probe("combo-box-modes", "P", with_components(
        combo_box_component(mode=0, wid=20, vvs1=4),
        combo_box_component("cb1", y=100, mode=1, wid=20, vvs1=4), code=(
            "on page0.up:\n  sys0=cb0.ch\n  sys1=cb1.ch\n")),
        whole_file, editor_file),
    # Two combo-boxes beside a text: each one's memory, and their txts and
    # paths after the page's components' memory, in order, the second's
    # path in the least path_m, 1.
    Probe("combo-box-two-beside-a-text", "P", with_components(
        combo_box_component(), text_component(y=60),
        combo_box_component("cb1", y=110, txt="x", path="x", path_m=1)),
        whole_file, editor_file, kept=user_code_kept),
    # Its attributes in code: read, set, and in a condition, beside a text
    # whose entries follow its own.
    Probe("combo-box-in-code", "P", with_components(
        combo_box_component(), text_component(y=60), code=(
            "on page0.up:\n  sys0=cb0.val\n  cb0.val=1\n  cb0.txt=\"ab\"\n  t0.txt=cb0.txt\n"
            "  cb0.path=\"a\\rb\"\n  cb0.down=1\n  sys1=cb0.qty\n  cb0.dir=0\n  cb0.up=0\n"
            "  if(cb0.val==1)\n  {\n    sys2=1\n  }\n")),
        whole_file, editor_file),
    # The attributes every component has, away from their defaults: its
    # effect moves its entries from 19 on, and their owner fields, two on.
    Probe("combo-box-shared-attributes", "P", with_components(combo_box_component(
        aph=50, sendkey=3, drag=1, lockobj=1, movex=5, movey=6, groupid0=1, groupid1=2,
        effect=2, first=10, time=500)), whole_file, editor_file),
    # Its drastate away from its default, which has no entry.
    Probe("combo-box-of-drastate-1", "P", with_components(combo_box_component(drastate=1)),
          whole_file, editor_file),
    # With a crop of a picture, a picture, or nothing behind it, its
    # sta 0, 2, and 3, where its default is 1, a colour.
] + [Probe("combo-box-with-%s-behind" % background, "P",
            with_a_background(combo_box_component, background), whole_file, editor_file,
            kept=user_code_kept) for background in BACKGROUNDS]
# Each other style it takes: 1, a border of one colour, here of a borderc
# and a borderw of their own; 2, sunken; and 3, raised.
PROBES += [Probe("combo-box-of-style-%d" % style, "P", with_components(combo_box_component(
    style=style, **({"borderc": 1111, "borderw": 3} if style == 1 else {}))),
    whole_file, editor_file, kept=user_code_kept) for style in (1, 2, 3)]
# A border of one colour, its style 1, with each of those behind it.
PROBES += [Probe("combo-box-of-style-1-with-%s-behind" % background, "P",
                 with_a_background(combo_box_component, background, style=1, borderc=1111,
                                   borderw=3),
                 whole_file, editor_file, kept=user_code_kept) for background in BACKGROUNDS]
# A 3D border, its style 2, sunken, and 3, raised, with each of those behind it.
PROBES += [Probe("combo-box-of-style-%d-with-%s-behind" % (style, background), "P",
                 with_a_background(combo_box_component, background, style=style), whole_file,
                 editor_file, kept=user_code_kept)
           for style in (2, 3) for background in BACKGROUNDS]
