"""The probes of a txt's room over what earlier pages left on T: projects on
the T base folder, each compared with the Nextion Editor's whole file. Run
them with `tools.tft.probe run text_room_probes`. K and F run them too
(k_probes.py, f_probes.py).

The Nextion Editor writes every memory image in one scratch image, from its
start: the int area first, then each page's memory block over the one
before, at the same places. A txt's room keeps what lay there where the
Nextion Editor writes nothing. A text, a button, a dual-state button, or a
variable of a text keeps its txt in its own memory, and the Nextion Editor
writes its txt_maxl + 1 bytes, so only the bytes that round its room up to
4 keep what lay there. A QR code or a scrolling text keeps its txt after
the page's components' memory, and the Nextion Editor writes its txt and a
zero alone (ResearchNotes/tft/user-code-frame.md).

Each probe keeps the user code as its fixtures, in tests/fixtures/rooms/.
"""
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.component_probes import (editor_file, on_pages, user_code_kept, whole_file,
                                            with_components)
from tools.tft.probing.dual_state_button_probes import dual_state_button_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.qr_code_probes import qr_code_component
from tools.tft.probing.scrolling_text_probes import scrolling_text_component
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.variable_probes import text_variable_component

FIXTURES = "rooms"
# The program.s line every base folder declares its int variables on.
_INTS = "int sys0=0,sys1=0,sys2=0"

# Two buttons, a text of a long txt, and a third button: a page whose memory
# holds bytes other than 0 far into it.
_FULL_PAGE = with_components(
    button_component(), button_component("b1", x=10, y=60),
    text_component(txt="ABCDEFGHIJKLMNOPQRSTUVWXYZ", txt_maxl=60, y=120),
    button_component("b2", x=10, y=160))

# Each type that keeps a txt, with a txt of "ab" in a room of 64 bytes.
_OF_EACH_TYPE = {
    "text": text_component(txt="ab", txt_maxl=60),
    "button": button_component(txt="ab", txt_maxl=60),
    "dual-state-button": dual_state_button_component(txt="ab", txt_maxl=60),
    "variable-of-a-text": text_variable_component(txt="ab", txt_maxl=60),
    "scrolling-text": scrolling_text_component(txt="ab", txt_maxl=60),
    "qr-code": qr_code_component(txt="ab", txt_maxl=60),
}


class _WithInts:
    """A change that gives program.s 40 more int variables, each 0x41424344
    and its number, then makes `change`: an int area of bytes other than 0."""

    def __init__(self, change):
        self.change = change

    def __call__(self, folder):
        program = folder / "program.nx"
        more = ",".join("v%d=%d" % (number, 0x41424344 + number) for number in range(40))
        program.write_text(program.read_text(encoding="utf-8").replace(
            _INTS, _INTS + "," + more), encoding="utf-8")
        self.change(folder)


def _probe(name: str, change) -> Probe:
    """Returns the probe `name` on T, which makes `change` to the base
    folder, keeping the user code."""
    return Probe("room-" + name, "T", change, whole_file, editor_file, FIXTURES,
                 user_code_kept)


PROBES = [
    # A QR code on page1 after a text and a button on page0: its room keeps
    # the button's memory.
    _probe("qr-code-on-a-second-page", on_pages(
        with_components(text_component(), button_component(x=10, y=60)),
        with_components(qr_code_component(txt="abc", txt_maxl=30), page="page1"))),
    # Each type alone on page1, over a page0 whose memory holds bytes other
    # than 0.
    *[_probe("%s-over-a-full-page" % name,
             on_pages(_FULL_PAGE, with_components(component, page="page1")))
      for name, component in _OF_EACH_TYPE.items()],
    # A QR code on page2 after a long page0 and a short page1: its room
    # keeps page0's bytes past page1's end.
    _probe("qr-code-past-a-shorter-page", on_pages(
        with_components(text_component(txt="ABCDEFGHIJKLMNOPQRSTUVWXYZ", txt_maxl=60),
                        button_component(x=10, y=60), text_component("t1", y=130)),
        with_components(text_component(), page="page1"),
        with_components(qr_code_component(txt="abc", txt_maxl=120), page="page2"))),
    # A QR code on page0 over an int area of bytes other than 0.
    _probe("qr-code-over-the-int-area", _WithInts(with_components(
        qr_code_component(txt="ab", txt_maxl=100)))),
]
