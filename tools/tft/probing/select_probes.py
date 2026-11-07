"""The probes of the select (component_types/select.py), a type P and E have
and T and K have not: projects on the P base folder, each compared with the
Nextion Editor's whole file. Run them on P with `tools.tft.probe run p_probes`,
which takes them, and on E with `tools.tft.probe run e_probes`.

The probes of a select at its defaults and of two selects beside a text
keep the user code as their fixtures (kept), in p_probes.py's folder.
"""
from tools.tft.probing.component_probes import editor_file, user_code_kept, whole_file, with_components
from tools.tft.probing.picture_probes import BACKGROUNDS, with_a_background
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.text_probes import text_component


def select_component(name: str = "select0", x: int = 10, y: int = 10, w: int = 90,
                     h: int = 200, path: str = None, txt: str = None,
                     **attributes: int) -> str:
    """Returns a select component in a page file's form, in the base
    folder's font, its path, whose items "\\r\\n" separates, its txt, and
    its other attributes, such as val, at their defaults unless given."""
    escaped = None if path is None else path.replace("\r", "\\r").replace("\n", "\\n")
    return ('\n[[component]]\nname = "%s"\ntype = "select"\nx = %d\ny = %d\nw = %d\nh = %d\n'
            'font = "NotoSans24"\n' % (name, x, y, w, h)
            + ('path = "%s"\n' % escaped if escaped is not None else "")
            + ('txt = "%s"\n' % txt if txt is not None else "")
            + "".join("%s = %d\n" % item for item in attributes.items()))


PROBES = [
    # A select at its defaults, but for its place and size: twelve items,
    # in a path_m of 1024.
    Probe("select-at-its-defaults", "P", with_components(select_component()), whole_file,
          editor_file, kept=user_code_kept),
    # Each of its values away from its default, its items of letters and
    # digits in a path_m of 20 among them.
    Probe("select-values", "P", with_components(select_component(
        path="Ab\r\n9z\r\nc", path_m=20, val=2, spax=3, hig=16, ch=0, bco=1234, pco=2345,
        pco2=3456, pco1=4567)), whole_file, editor_file),
    # Without the line that marks the item chosen, a dis of 0: no pco1
    # entry, each later one a number less, and its attributes after it in
    # code.
    Probe("select-without-its-line", "P", with_components(
        select_component(dis=0, pco1=4567), code=(
            "on page0.up:\n  sys0=select0.val\n  select0.val=1\n  sys1=select0.ch\n"
            "  select0.path=\"a\\rb\"\n  sys2=select0.dis\n")),
        whole_file, editor_file),
    # Its highest values, and a path_m of 1, with one item; room_probes.py
    # takes its path_m to its most.
    Probe("select-highest-values", "P", with_components(select_component(
        path="a", path_m=1, val=0xFFFF, spax=255, hig=255, ch=32)), whole_file, editor_file),
    # A txt of letters and digits in a txt_maxl of 10, written as it is,
    # not the item its val chooses.
    Probe("select-txt", "P", with_components(select_component(txt="Ab9z", txt_maxl=10)),
          whole_file, editor_file),
    # Two selects beside a text: each one's memory, and their txts and
    # paths after the page's components' memory, in order.
    Probe("select-two-beside-a-text", "P", with_components(
        select_component(), text_component(y=220),
        select_component("select1", x=300, path="x\r\ny", path_m=8, val=1)),
        whole_file, editor_file, kept=user_code_kept),
    # Its attributes in code: read, set, and in a condition, beside a text
    # whose entries follow its own.
    Probe("select-in-code", "P", with_components(
        select_component(), text_component(y=220), code=(
            "on page0.up:\n  sys0=select0.val\n  select0.val=1\n  t0.txt=select0.txt\n"
            "  select0.path=\"a\\rb\"\n  select0.hig=30\n  sys1=select0.ch\n"
            "  if(select0.val==1)\n  {\n    sys2=1\n  }\n")),
        whole_file, editor_file),
    # The attributes every component has, away from their defaults: its
    # effect moves its val's entry, and that entry's owner field, two on.
    Probe("select-shared-attributes", "P", with_components(select_component(
        aph=50, sendkey=3, drag=1, lockobj=1, movex=5, movey=6, groupid0=1, groupid1=2,
        effect=2, first=10, time=500)), whole_file, editor_file),
    # With a crop of a picture, a picture, or nothing behind it, its
    # sta 0, 2, and 3, where its default is 1, a colour.
] + [Probe("select-with-%s-behind" % background, "P",
            with_a_background(select_component, background), whole_file, editor_file,
            kept=user_code_kept) for background in BACKGROUNDS]
# Its other style, 1, a border of one colour, here of a borderc and a
# borderw of their own: it takes 0 and 1 alone.
PROBES.append(Probe("select-of-style-1", "P", with_components(select_component(
    style=1, borderc=1111, borderw=3)), whole_file, editor_file, kept=user_code_kept))
# A border of one colour, its style 1, with each of those behind it.
PROBES += [Probe("select-of-style-1-with-%s-behind" % background, "P",
                 with_a_background(select_component, background, style=1, borderc=1111,
                                   borderw=3),
                 whole_file, editor_file, kept=user_code_kept) for background in BACKGROUNDS]
