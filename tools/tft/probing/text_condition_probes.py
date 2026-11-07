"""The probes of conditions that compare texts (control_statements.py):
a txt beside a text or another txt in the conditions of `if`, `else if`,
`while`, and `for`, with each comparison, alone and joined with `&&` and
`||`. They use two texts and a number on the T base folder's page0, one
with other types beside them, and lines in page0's Touch Release event.
Run them with `tools.tft.probe run text_condition_probes`.

Each compares the blocks of page0's Touch Release event alone, and keeps
them as its fixture (statement_probes.py gives both).
"""
from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.dual_state_button_probes import dual_state_button_component
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.qr_code_probes import qr_code_component
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.variable_probes import text_variable_component

FIXTURES = "text-conditions"

# Two texts, t0 and t1, and a number, n0.
_COMPONENTS = [text_component("t0", txt="ab"), text_component("t1", y=60, txt="cd"),
               number_component(y=110)]


def _probe(name: str, lines: list, components: list = ()) -> Probe:
    return Probe("text-conditions-" + name, "T",
                 with_attributes(lines, _COMPONENTS + list(components)),
                 ours_in_event, theirs_in_event, FIXTURES)


PROBES = [
    # A txt beside a text, a text beside a txt, and two txts, in if and
    # else if.
    _probe("in-if", ['if(t0.txt=="ab")', "{", "sys0=1", "}", "if(t0.txt!=t1.txt)", "{",
                     "sys0=2", "}", 'if("ab"==t0.txt)', "{", "sys0=3", '}else if(t1.txt!="b")',
                     "{", "sys0=4", "}else", "{", "sys0=5", "}"]),
    # Joined with && and ||, two texts' comparisons, and one beside a
    # number's.
    _probe("joined", ['if(t0.txt=="a"&&t1.txt!=t0.txt)', "{", "sys0=1", "}",
                      'if(t0.txt=="a"||t1.txt=="b"||t0.txt==t1.txt)', "{", "sys0=2", "}",
                      'if(t0.txt=="a"&&n0.val==1)', "{", "sys0=3", "}"]),
    # Each comparison between texts, which the Nextion Editor writes as a
    # number's.
    _probe("each-comparison", ['if(t0.txt<"b")', "{", "sys0=1", "}", 'if(t0.txt>"b")', "{",
                               "sys0=2", "}", "if(t0.txt<=t1.txt)", "{", "sys0=3", "}",
                               'if("z">=t1.txt)', "{", "sys0=4", "}"]),
    _probe("in-loops", ['while(t0.txt!="x")', "{", 't0.txt="x"', "}",
                        'for(sys0=0;t1.txt!="ab cd";sys0++)', "{", 't1.txt+="ab"', "}"]),
    # Two texts, as written in the condition.
    _probe("two-texts", ['if("a"=="b")', "{", "sys0=1", "}", 'while("a"!="a")', "{",
                         "sys0++", "}"]),
    # Texts that contain what a condition's own parts are made of, an empty
    # text, and every printable ASCII character but a double quote and a
    # backslash, && and || left out.
    _probe("of-printable-ascii", ['if(t0.txt=="a<b")', "{", "sys0=1", "}",
                                  'if(t0.txt==")")', "{", "sys0=2", "}",
                                  'if(t0.txt=="x==y")', "{", "sys0=3", "}",
                                  'if(t0.txt=="http://x")', "{", "sys0=4", "}",
                                  'if(t0.txt=="")', "{", "sys0=5", "}",
                                  'if(t0.txt=="!09Az")', "{", "sys0=7", "}",
                                  "if(t0.txt==\"#$%&'()*+,-./:;<=>?@[]^_`{|}~ \")", "{",
                                  "sys0=6", "}"]),
    # The txt of a variable, a button, a dual-state button, and a QR code;
    # and || between texts' comparisons other than ==, and between a text's
    # and a number's.
    _probe("of-more-types", ['if(va0.txt=="x")', "{", "sys0=1", "}", "if(b0.txt!=t0.txt)", "{",
                             "sys0=2", "}", 'if(bt0.txt=="y")', "{", "sys0=3", "}",
                             'if(qr0.txt!="z")', "{", "sys0=4", "}",
                             'if(t0.txt<"b"||t1.txt>="c")', "{", "sys0=5", "}",
                             'if(t0.txt=="a"||n0.val==1)', "{", "sys0=6", "}"],
           [text_variable_component(), button_component(x=160, y=10),
            dual_state_button_component(x=160, y=70), qr_code_component(x=160, y=140)]),
    # Long texts: 100 and 300 characters.
    _probe("long", ['if(t0.txt=="%s")' % ("a" * 100), "{", "sys0=1", "}",
                    'if(t1.txt!="%s")' % ("b" * 300), "{", "sys0=2", "}"]),
]
