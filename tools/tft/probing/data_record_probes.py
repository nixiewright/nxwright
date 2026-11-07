"""The probes of the data record (component_types/data_record.py), a type P
and E have and T and K have not: projects on the P base folder, each
compared with the Nextion Editor's whole file. Run them on P with
`tools.tft.probe run p_probes`, which takes them, and on E with
`tools.tft.probe run e_probes`.

The probes of a data record at its defaults and of one on each of two pages
keep the user code as their fixtures (kept), in p_probes.py's folder.

The Nextion Editor keeps one virtual SD card for every project it opens. A
data record whose file is already there with another lenth, maxval, or dez
makes it fail to compile, and so does a mode of 0 whose file is not there.
So each probe that changes those gives its data record a path of its own,
and the probe of a mode of 0 follows the probe at its defaults, of mode 1,
whose file the Nextion Editor creates on its card.
"""
from tools.tft.probing.component_probes import (editor_file, on_pages, user_code_kept, whole_file,
                                            with_components)
from tools.tft.probing.picture_probes import BACKGROUNDS, with_a_background
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.text_probes import text_component


def data_record_component(name: str = "data0", x: int = 10, y: int = 60, w: int = 240,
                          h: int = 240, **attributes) -> str:
    """Returns a data record component in a page file's form, in the base
    folder's font, its attributes, such as lenth or path, at their defaults
    unless given."""
    return ('\n[[component]]\nname = "%s"\ntype = "data-record"\nx = %d\ny = %d\nw = %d\n'
            'h = %d\nfont = "NotoSans24"\n' % (name, x, y, w, h)
            + "".join(('%s = "%s"\n' if isinstance(value, str) else "%s = %d\n") % (name, value)
                      for name, value in attributes.items()))


# A text and a data record on page 0, and the same on a new page, both data
# records global, as every data record on P is (component_probes.PagesChange).
_ON_TWO_PAGES = on_pages(
    with_components(text_component(), data_record_component()),
    with_components(text_component(), data_record_component("data1"), page="page1"))


PROBES = [
    # A data record at its defaults: its memory in the int area, its texts
    # and buffer after it, its entries, and its init in its page's load
    # section.
    Probe("data-record-at-its-defaults", "P", with_components(data_record_component()),
          whole_file, editor_file, kept=user_code_kept),
    # Its mode of 0, which does not create its file: the Nextion Editor
    # compiles it only with that file on its virtual SD card. The probe
    # above, of mode 1 and the same path, lenth, maxval, and dez, has the
    # Nextion Editor create it. The runner skips that probe once it has
    # matched, so on a card without the file, run both together, with
    # --again for the first.
    Probe("data-record-of-mode-0", "P", with_components(data_record_component(mode=0)),
          whole_file, editor_file, kept=user_code_kept),
    # Beside a text, which keeps its page's memory, as the data record is
    # global.
    Probe("data-record-beside-a-text", "P", with_components(
        text_component(), data_record_component()), whole_file, editor_file),
    # One on each of two pages: both in the int area, in page order.
    Probe("data-record-on-two-pages", "P", _ON_TWO_PAGES, whole_file, editor_file,
          kept=user_code_kept),
    # Each of its numbers and colours away from its default, a 3D border
    # among them, and its molloc and molloc_s, which change nothing.
    Probe("data-record-values", "P", with_components(data_record_component(
        path="sd0/nxtft_values.data", lenth=30, maxval=500, dez=2, spax=2, hig=40, left=2,
        gdc=1234, gdw=2, gdh=3, bco=2345, pco=3456, bco1=4567, pco1=5678, bco2=6789,
        pco2=7890, xcen=1, ch=4, style=3, molloc=1000, molloc_s=2000)),
        whole_file, editor_file),
    # Its values at their entries' lowest, then at their highest, each one
    # further in than the last, so that each differs.
    *[Probe("data-record-%s-values" % end, "P", with_components(data_record_component(
        path="sd0/nxtft_%s.data" % end, **{name: value + step * number for number, name in
                                           enumerate(("val", "qty", "maxval_y", "val_y",
                                                      "maxval_x", "val_x"))})),
        whole_file, editor_file)
      for end, value, step in (("lowest", -2 ** 31, 1), ("highest", 2 ** 31 - 1, -1))],
    # Each of its texts and their rooms away from their defaults.
    Probe("data-record-texts", "P", with_components(data_record_component(
        path="sd0/nxtft_texts.data", path_m=30, format="aa", format_m=30, dir="h0^h1",
        dir_m=40, filter="x", filter_m=10, txt="t", txt_m=12)), whole_file, editor_file),
    # Its format of two column widths, separated by "^", as nxwright
    # describes it, under two headings.
    Probe("data-record-two-column-widths", "P", with_components(data_record_component(
        path="sd0/nxtft_widths.data", format="100^100", format_m=7, dir="h0^h1", dir_m=10)),
        whole_file, editor_file, kept=user_code_kept),
    # A border of one colour, whose borderc and borderw take entries after
    # its style's.
    Probe("data-record-bordered", "P", with_components(data_record_component(
        path="sd0/nxtft_bordered.data", style=1, borderc=1111, borderw=3)),
        whole_file, editor_file),
    # No border, and its flags: dis, order, autoleft, and init, the last two
    # in its memory without entries.
    Probe("data-record-flags", "P", with_components(data_record_component(
        path="sd0/nxtft_flags.data", style=0, dis=0, order=1, autoleft=1, init=1)),
        whole_file, editor_file),
    # The attributes every component has, away from their defaults, an
    # effect among them, which moves its entries after its own two on.
    Probe("data-record-shared-attributes", "P", with_components(data_record_component(
        path="sd0/nxtft_shared.data", aph=50, sendkey=3, drag=1, lockobj=1, movex=5, movey=6,
        groupid0=1, groupid1=2, effect=2, first=10, time=500)), whole_file, editor_file),
    # Its methods' calls and its attributes in code.
    Probe("data-record-in-code", "P", with_components(
        text_component(), data_record_component(path="sd0/nxtft_code.data"), code=(
            "on page0.up:\n  data0.insert(\"a^b^c\")\n  data0.insert(t0.txt)\n"
            "  data0.delete(0,1)\n  data0.delete(sys0,sys1+1)\n  data0.up(\"x^y\",0)\n"
            "  data0.clear()\n  sys0=data0.val\n  data0.val=1\n  sys1=data0.qty\n"
            "  data0.path=\"sd0/c.data\"\n  t0.txt=data0.txt\n  data0.filter=\"f\"\n"
            "  sys2=data0.val_y\n  data0.val_y=2\n  if(data0.val==1)\n  {\n    sys2=1\n  }\n")),
        whole_file, editor_file),
    # A record given as a number, or up's as a txt, which the Nextion Editor
    # compiles too.
    Probe("data-record-records-of-other-kinds", "P", with_components(
        text_component(), number_component(y=60),
        data_record_component(path="sd0/nxtft_kinds.data"), code=(
            "on page0.up:\n  data0.insert(n0.val)\n  data0.insert(5)\n"
            "  data0.up(t0.txt,n0.val)\n  data0.up(5,0)\n")),
        whole_file, editor_file),
    # With a crop of a picture, a picture, or nothing behind it, its
    # sta 0, 2, and 3, where its default is 1, a colour.
] + [Probe("data-record-with-%s-behind" % background, "P",
            with_a_background(data_record_component, background), whole_file, editor_file,
            kept=user_code_kept) for background in BACKGROUNDS]
# A border of one colour, its style 1, with each of those behind it.
PROBES += [Probe("data-record-of-style-1-with-%s-behind" % background, "P",
                 with_a_background(data_record_component, background, style=1, borderc=1111,
                                   borderw=3),
                 whole_file, editor_file, kept=user_code_kept) for background in BACKGROUNDS]
# No border, its style 0, and a 3D border, its style 3, raised, with each
# of those behind it. Its default, 2, sunken, is probed with them above.
PROBES += [Probe("data-record-of-style-%d-with-%s-behind" % (style, background), "P",
                 with_a_background(data_record_component, background, style=style), whole_file,
                 editor_file, kept=user_code_kept)
           for style in (0, 3) for background in BACKGROUNDS]
