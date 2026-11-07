"""The probes of texts in code (statements.py): a txt set to another txt, to
texts and txts joined with `+`, to a text of printable ASCII or of up to 700
characters, a txt added to with `+=`, texts and txts joined among them, and
cut with `-=`, by a number or another operand. They use two texts, a
variable of a text, a button, and a dual-state button on the T base
folder's page0, a QR code beside them in one probe, a number and a timer in
another, and lines in page0's Touch Release event. Run them with
`tools.tft.probe run text_assignment_probes`.

Each compares the blocks of page0's Touch Release event alone. Five keep
them as their fixtures (statement_probes.py gives both).
"""
from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.dual_state_button_probes import dual_state_button_component
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.qr_code_probes import qr_code_component
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.variable_probes import text_variable_component

FIXTURES = "text-assignments"

# Two texts, a variable of a text, a button, and a dual-state button, each
# taking texts of up to 40 characters.
_COMPONENTS = [text_component(txt_maxl=40), text_component("t1", y=60, txt_maxl=40),
               text_variable_component(txt_maxl=40), button_component(y=110, txt_maxl=40),
               dual_state_button_component(y=170, txt_maxl=40)]


def _probe(name: str, lines: list, fixtures: bool = True, components: list = ()) -> Probe:
    return Probe("text-" + name, "T", with_attributes(lines, _COMPONENTS + list(components)),
                 ours_in_event, theirs_in_event, FIXTURES if fixtures else None)


PROBES = [
    _probe("from-a-txt", ["t0.txt=t1.txt", "t1.txt=va0.txt", "va0.txt=b0.txt",
                          "b0.txt=bt0.txt", "bt0.txt=t0.txt"]),
    _probe("joined", ['t0.txt=t1.txt+"a"', 't0.txt="a"+t1.txt', 't0.txt="a"+"b"',
                      "t0.txt=t1.txt+va0.txt", 't0.txt=t1.txt+"-"+b0.txt',
                      't0.txt=t1.txt+"-"+b0.txt+"!"+bt0.txt']),
    _probe("added-to-and-cut", ['t0.txt+="a"', "t0.txt+=t1.txt", "t0.txt-=1", "t1.txt-=3",
                                'va0.txt+="a"', "b0.txt+=t0.txt", "bt0.txt-=2",
                                "t0.txt-=1000", "va0.txt-=1", "b0.txt-=1", 'bt0.txt+="a"']),
    _probe("of-printable-ascii", ['t0.txt="Hello, world!"', 't1.txt="a b"',
                                  "t0.txt=\"#$%&'()*+,-./:;<=>?@[]^_`{|}~\""]),
    # Texts of 21, 40, 41, and 700 characters, two of them longer than their
    # txt_maxl, which the Nextion Editor compiles as written.
    _probe("long", ['t0.txt="%s"' % ("a" * 21), 't1.txt="%s"' % ("0123456789" * 4),
                    'va0.txt="%s"' % ("x" * 41), 'bt0.txt="%s"' % ("y" * 700)],
           fixtures=False),
    # Spaces around the operators, which the Nextion Editor drops, and in a
    # text, which it keeps.
    _probe("with-spaces", ['t0.txt = t1.txt + "a b"', 't0.txt += " "', "t1.txt -= 2"],
           fixtures=False),
    # A txt added to with texts and txts joined, and cut by an int variable,
    # a system variable, a number's val, a timer's tim, a hexadecimal number,
    # and a colour's name, beside a number and a timer.
    _probe("added-to-joined-and-cut-by-operands", [
        't0.txt+="a"+"b"', 't0.txt+="a"+t1.txt+"c"', "t0.txt+=va0.txt+b0.txt",
        'va0.txt+="a"+t0.txt', 't1.txt+=t1.txt+"b"', "t0.txt-=sys0", "t0.txt-=n0.val",
        "t0.txt-=dim", "t0.txt-=0x01", "t0.txt-=tm0.tim", "b0.txt-=n0.val", "t1.txt-=RED"],
        components=[number_component(y=240), timer_component()]),
    # A QR code's txt, which its page keeps after the components' memory.
    _probe("of-a-qr-code", ['qr0.txt=t0.txt+"a"', 'qr0.txt+="b"', "qr0.txt-=2",
                            "t0.txt=qr0.txt"], fixtures=False,
           components=[qr_code_component(y=240, txt_maxl=40)]),
]
