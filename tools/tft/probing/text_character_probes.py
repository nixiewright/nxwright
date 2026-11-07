"""The probes of texts' characters past ASCII letters and digits, in the
project's encoding, iso-8859-1: a component's txt of every printable ASCII
character, and of each character from U+00A0 to U+00FF, on each type that
has a txt; then texts of those characters in code. Run them with
`tools.tft.probe run text_character_probes`.

The probes of txts compare the whole file, part by part, and keep the user
code alone as their fixtures (component_probes.py gives both). The probes
of code compare the blocks of page0's Touch Release event, beside the text
t0, and keep them as their fixtures (statement_probes.py gives both). The
last is on K, for K's own command that takes a text.
"""
from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.component_probes import editor_file, user_code_kept, whole_file, with_components
from tools.tft.probing.dual_state_button_probes import dual_state_button_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.qr_code_probes import qr_code_component
from tools.tft.probing.scrolling_text_probes import scrolling_text_component
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.variable_probes import text_variable_component

FIXTURES = "text-characters"
# Every printable ASCII character, and every character from U+00A0 to
# U+00FF, each written in iso-8859-1 as its own byte.
PRINTABLE_ASCII = "".join(chr(code) for code in range(0x20, 0x7F))
LATIN_1 = "".join(chr(code) for code in range(0xA0, 0x100))


def _toml(text: str) -> str:
    """Returns `text` as a page file's basic string holds it: a backslash
    and a double quote escaped."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _txt_probe(name: str, change) -> Probe:
    return Probe("text-characters-" + name, "T", change, whole_file, editor_file, FIXTURES,
                 user_code_kept)


PROBES = [
    # A text's txt of every printable ASCII character, a double quote and a
    # backslash among them; a button's and a dual-state button's txts of
    # spaces and marks.
    _txt_probe("txt-of-printable-ascii", with_components(
        text_component(w=300, txt=_toml(PRINTABLE_ASCII), txt_maxl=100),
        button_component(y=60, txt=_toml('a "b" \\c'), txt_maxl=20),
        dual_state_button_component(y=130, txt="x, y!", txt_maxl=20))),
    # A text's txt of each character from U+00A0 to U+00FF, and a
    # variable's, a QR code's, and a scrolling text's of a few of them.
    _txt_probe("txt-of-latin-1", with_components(
        text_component(w=300, txt=LATIN_1, txt_maxl=100),
        text_variable_component(txt="é", txt_maxl=10),
        qr_code_component(y=60, txt="Ünïcödé", txt_maxl=20),
        scrolling_text_component(y=200, txt="ñ ü ©", txt_maxl=20))),
    # The other types the first two left out: a variable's, a QR code's, and
    # a scrolling text's txts of marks, a double quote and a backslash among
    # them, and a button's and a dual-state button's of characters from
    # U+00A0 to U+00FF.
    _txt_probe("txt-on-the-other-types", with_components(
        text_variable_component(txt=_toml('a "b" \\c!'), txt_maxl=20),
        qr_code_component(y=10, txt=_toml('x"y\\z#~'), txt_maxl=20),
        scrolling_text_component(y=150, txt=_toml("{a} \\ [b]"), txt_maxl=20),
        button_component(y=200, txt="ñé ©", txt_maxl=20),
        dual_state_button_component(y=270, txt="ü°ÿ", txt_maxl=20))),
    # Texts of those characters in code: set, added to, compared, and given
    # to the commands that take a text.
    Probe("text-characters-in-code", "T", with_attributes([
        't0.txt="%s"' % LATIN_1, 't0.txt+="é"', 't0.txt="Héllo, "+t0.txt',
        'if(t0.txt=="%s")' % LATIN_1[:40], "{", "sys0=1", "}",
        'while(t0.txt!="ñ")', "{", 't0.txt="ñ"', "}",
        'xstr 0,0,100,30,0,RED,WHITE,0,0,1,"é ü"', 'prints "©°",0', 'print "ÿ"', 'get "ß"',
        'spstr t0.txt,t0.txt,"·",0', 'strlen "äöü",sys0', 'btlen "äöü",sys0',
        'crcputs "é",0'], [text_component(txt_maxl=100)]),
        ours_in_event, theirs_in_event, FIXTURES),
    # K's own command that takes a text, wepo, on K.
    Probe("text-characters-in-k-commands", "K", with_attributes(['wepo "é ü",0'],
                                                                [text_component()]),
          ours_in_event, theirs_in_event, FIXTURES),
]
