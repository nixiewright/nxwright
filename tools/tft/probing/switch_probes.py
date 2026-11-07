"""The probes of the switch (component_types/switch.py), a type P and E
have and T and K have not: projects on the P base folder, each compared
with the Nextion Editor's whole file. Run them on P with
`tools.tft.probe run p_probes`, which takes them, and on E with
`tools.tft.probe run e_probes`.

The probes of a switch at its defaults and of two switches beside a text
keep the user code as their fixtures (kept), in p_probes.py's folder.
"""
from tools.tft.probing.component_probes import editor_file, user_code_kept, whole_file, with_components
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.text_probes import text_component


def switch_component(name: str = "sw0", x: int = 10, y: int = 10, w: int = 80, h: int = 30,
                     txt: str = None, **attributes: int) -> str:
    """Returns a switch component in a page file's form, in the base
    folder's font, its txt and its other attributes, such as val, at their
    defaults unless given."""
    return ('\n[[component]]\nname = "%s"\ntype = "switch"\nx = %d\ny = %d\nw = %d\nh = %d\n'
            'font = "NotoSans24"\n' % (name, x, y, w, h)
            + ('txt = "%s"\n' % txt if txt is not None else "")
            + "".join("%s = %d\n" % item for item in attributes.items()))


PROBES = [
    # A switch at its defaults, but for its place and size.
    Probe("switch-at-its-defaults", "P", with_components(switch_component()), whole_file,
          editor_file, kept=user_code_kept),
    # Each of its values away from its default, its txt and txt_maxl among
    # them.
    Probe("switch-values", "P", with_components(switch_component(
        txt="OffOn", txt_maxl=30, val=1, dez=1, dis=50, bco=1234, pco=2345, bco2=3456,
        pco2=4567, pco1=5678)), whole_file, editor_file),
    # Two switches beside a text: each one's memory, and their txts after
    # the page's components' memory, in order.
    Probe("switch-two-beside-a-text", "P", with_components(
        switch_component(), text_component(y=60), switch_component("sw1", y=110, val=1)),
        whole_file, editor_file, kept=user_code_kept),
    # Its attributes in code: read, set, and in a condition, beside a text
    # whose entries follow its own.
    Probe("switch-in-code", "P", with_components(
        switch_component(), text_component(y=60), code=(
            "on page0.up:\n  sys0=sw0.val\n  sw0.val=1\n  sw0.txt=\"ab\"\n  sw0.bco=5\n"
            "  sys1=sw0.dis\n  t0.txt=sw0.txt\n  if(sw0.val==1)\n  {\n    sys2=1\n  }\n")),
        whole_file, editor_file),
    # The attributes every component has, away from their defaults: its
    # effect moves its entries from 19 on, and their owner fields, two on.
    Probe("switch-shared-attributes", "P", with_components(switch_component(
        aph=50, sendkey=3, drag=1, lockobj=1, movex=5, movey=6, groupid0=1, groupid1=2,
        effect=2, first=10, time=500)), whole_file, editor_file),
]
