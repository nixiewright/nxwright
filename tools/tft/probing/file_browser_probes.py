"""The probes of the file browser (component_types/file_browser.py), a type
P and E have and T and K have not: projects on the P base folder, each
compared with the Nextion Editor's whole file. Run them on P with
`tools.tft.probe run p_probes`, which takes them, and on E with
`tools.tft.probe run e_probes`.

The probes of a file browser at its defaults and of two beside a text keep
the user code as their fixtures (kept), in p_probes.py's folder.
"""
from tools.tft.probing.component_probes import editor_file, user_code_kept, whole_file, with_components
from tools.tft.probing.picture_probes import BACKGROUNDS, with_a_background, with_pictures
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.text_probes import text_component


def file_browser_component(name: str = "fbrowser0", x: int = 10, y: int = 60, w: int = 240,
                           h: int = 240, **attributes) -> str:
    """Returns a file browser component in a page file's form, in the base
    folder's font, its attributes, such as dir or psta, at their defaults
    unless given."""
    return ('\n[[component]]\nname = "%s"\ntype = "file-browser"\nx = %d\ny = %d\nw = %d\n'
            'h = %d\nfont = "NotoSans24"\n' % (name, x, y, w, h)
            + "".join(('%s = "%s"\n' if isinstance(value, str) else "%s = %d\n") % (name, value)
                      for name, value in attributes.items()))


# Three pictures of 8 by 8, pictures 0 to 2, for its icons.
_PICTURES = [("a", (8, 8), (255, 0, 0)), ("b", (8, 8), (0, 255, 0)), ("c", (8, 8), (0, 0, 255))]

PROBES = [
    # A file browser at its defaults: its memory, entries, record, texts,
    # and buffer, and its init in its page's load section.
    Probe("file-browser-at-its-defaults", "P", with_components(file_browser_component()),
          whole_file, editor_file, kept=user_code_kept),
    # Two beside a text: each one's texts after the text's txt, and their
    # buffers in order.
    Probe("file-browser-two-beside-a-text", "P", with_components(
        file_browser_component(), text_component(),
        file_browser_component("fbrowser1", y=300, h=100)),
        whole_file, editor_file, kept=user_code_kept),
    # Each of its numbers and colours away from its default, a 3D border
    # among them, and a buffsize not a multiple of 4.
    Probe("file-browser-values", "P", with_components(file_browser_component(
        bco=2345, pco=3456, pco2=4567, bco2=5678, xcen=0, left=2, ch=4, dis=5, spax=10, spay=4,
        style=3, buffsize=1001)), whole_file, editor_file),
    # Its values at their entries' lowest, its qty's 0, then at their
    # highest, each near its limit different from the others.
    Probe("file-browser-lowest-values", "P", with_components(file_browser_component(
        val=-2 ** 31, qty=0, maxval_y=-2 ** 31 + 1, val_y=-2 ** 31 + 2)), whole_file,
        editor_file),
    Probe("file-browser-highest-values", "P", with_components(file_browser_component(
        val=2 ** 31 - 1, qty=2 ** 31 - 2, maxval_y=2 ** 31 - 3, val_y=2 ** 31 - 4)),
        whole_file, editor_file),
    # A buffsize of 0, its entry's lowest: no buffer, beside a text whose
    # txt follows its memory.
    Probe("file-browser-of-no-buffer", "P", with_components(
        file_browser_component(buffsize=0), text_component()),
        whole_file, editor_file, kept=user_code_kept),
    # Each of its texts and their rooms away from their defaults.
    Probe("file-browser-texts", "P", with_components(file_browser_component(
        dir="sd0/a/", dir_m=40, filter="*.txt", filter_m=20, txt="x", txt_m=30,
        vvs2="*.txt/2", vvs2_m=20)), whole_file, editor_file),
    # Without folders listed, its pic1 without an entry, no border, and its
    # flags, its autoleft in its memory without an entry.
    Probe("file-browser-flags", "P", with_components(file_browser_component(
        psta=0, style=0, autoleft=1, fwarning=0, buff=1, pic2=0)), whole_file, editor_file),
    # A border of one colour, whose borderc and borderw take entries after
    # its style's.
    Probe("file-browser-bordered", "P", with_components(file_browser_component(
        style=1, borderc=1111, borderw=3)), whole_file, editor_file),
    # Both at once: without folders listed and with a border of one colour,
    # its border's entries after its style's and its pic1 without one.
    Probe("file-browser-bordered-without-folders", "P", with_components(file_browser_component(
        psta=0, style=1, borderc=1111, borderw=3)), whole_file, editor_file),
    # Its icons among three pictures of the project, by name: the entries'
    # highest the project's last picture.
    Probe("file-browser-icons", "P", with_pictures(_PICTURES, file_browser_component(
        pic1="b", pic2="c")), whole_file, editor_file),
    # The attributes every component has, away from their defaults, an
    # effect among them, which moves its entries after its own two on.
    Probe("file-browser-shared-attributes", "P", with_components(file_browser_component(
        aph=50, sendkey=3, drag=1, lockobj=1, movex=5, movey=6, groupid0=1, groupid1=2,
        effect=2, first=10, time=500)), whole_file, editor_file),
    # Its up's call and its attributes in code.
    Probe("file-browser-in-code", "P", with_components(
        text_component(), file_browser_component(), code=(
            "on page0.up:\n  fbrowser0.up()\n  sys0=fbrowser0.val\n  fbrowser0.val=1\n"
            "  sys1=fbrowser0.qty\n  t0.txt=fbrowser0.txt\n  fbrowser0.dir=\"sd0/b/\"\n"
            "  fbrowser0.dir=t0.txt\n  fbrowser0.filter=\"*.txt\"\n  fbrowser0.pic1=2\n"
            "  sys2=fbrowser0.up\n  if(fbrowser0.val==1)\n  {\n    sys2=1\n  }\n")),
        whole_file, editor_file),
    # With a crop of a picture, a picture, or nothing behind it, its
    # sta 0, 2, and 3, where its default is 1, a colour.
] + [Probe("file-browser-with-%s-behind" % background, "P",
            with_a_background(file_browser_component, background), whole_file, editor_file,
            kept=user_code_kept) for background in BACKGROUNDS]
# A border of one colour, its style 1, with each of those behind it.
PROBES += [Probe("file-browser-of-style-1-with-%s-behind" % background, "P",
                 with_a_background(file_browser_component, background, style=1, borderc=1111,
                                   borderw=3),
                 whole_file, editor_file, kept=user_code_kept) for background in BACKGROUNDS]
# No border, its style 0, and a 3D border, its style 3, raised, with each
# of those behind it. Its default, 2, sunken, is probed with them above.
PROBES += [Probe("file-browser-of-style-%d-with-%s-behind" % (style, background), "P",
                 with_a_background(file_browser_component, background, style=style), whole_file,
                 editor_file, kept=user_code_kept)
           for style in (0, 3) for background in BACKGROUNDS]
# At its defaults, the two bordered ones, and the one of the attributes
# every component has, each in a project of _PICTURES, so that its pic1 and
# pic2 of 0 give a picture. The Nextion Editors 1.63.3 and 1.60.1 refuse a
# pic1 or pic2 that gives no picture, which 1.68.2 takes
# (older_editor_probes.py).
PROBES += [Probe(probe.name + "-among-pictures", "P",
                 with_pictures(_PICTURES, *probe.change.components), whole_file, editor_file)
           for probe in PROBES if probe.name in ("file-browser-at-its-defaults",
                                                 "file-browser-bordered",
                                                 "file-browser-bordered-without-folders",
                                                 "file-browser-shared-attributes")]
