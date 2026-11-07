"""The probes of a project's encoding (frame.py, packaging.py, and
component_types.text_fits): the T base folder, changed to each of the
Nextion Editor's 24 encodings by nxwright's device command, with a text
whose txt holds that encoding's characters (encoded_text), and code of
ASCII texts in page0's Touch Release event, after a comment of the
encoding's characters. Then, in some encodings, a
txt of such characters on each type that has a txt, and a component of
each drawn type, whose entries carry the encoding's byte, and global
objects on two pages, whose entries carry it too. Last, texts of
the encoding's characters in each family of code that takes a text, in
eight encodings, and in K's wepo, on K. Run them with
`tools.tft.probe run encoding_probes`.

The probes of txts compare the whole file, part by part, and three keep
the user code alone as their fixtures (component_probes.py gives both).
The probes of code compare the blocks of page0's Touch Release event, and
two keep them as their fixtures (statement_probes.py gives both). P's probes
(p_probes.py) take ASCII_PROBES, of txts of ASCII letters and digits and no
code, and the probes of a txt on each type in four encodings.
"""
from dataclasses import dataclass
from pathlib import Path
import unicodedata

from nxwright import NxwrightError
from nxwright.project.device_settings import ENCODINGS, TextCodec
from nxwright.source.device_change import change_device

from tools.tft.probing import page_probes, shared_attribute_probes
from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.component_probes import type_probe, with_components
from tools.tft.probing.dual_state_button_probes import dual_state_button_component
from tools.tft.probing.probe_runner import Probe, ProbeError
from tools.tft.probing.qr_code_probes import qr_code_component
from tools.tft.probing.scrolling_text_probes import scrolling_text_component
from tools.tft.probing.statement_probes import (ProgramChange, ours_in_event, theirs_in_event,
                                            touch_release_code)
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.variable_probes import text_variable_component

FIXTURES = "encoding"
# Characters of each encoding of two-byte characters, and of utf-8. Among
# them are shift-jis's 表 and big5's 許, whose second byte is 0x5C, a
# backslash's, and shift-jis's ｱ, of one byte.
_SAMPLES = {"gb2312": "中文，。ＡＢ", "big5": "中文許功蓋", "shift-jis": "日本表ソ能ｱ",
            "ks_c_5601-1987": "한국어漢字", "utf-8": "é中ü€한日"}
# The printable ASCII characters but a double quote and a backslash, which
# a page file's string escapes.
_ASCII = "".join(chr(code) for code in range(0x20, 0x7F) if chr(code) not in '"\\')
# Code of ASCII texts, the same bytes in every encoding.
_ASCII_CODE = ['t0.txt+="!"', 'if(t0.txt=="ok #1")', '{', 't0.txt="a b~"', '}']
# The character a probe's comment ends with in shift-jis and big5, whose
# last byte is 0x5C, so that the line after it shows it ends the comment.
_BACKSLASH_BYTE_ENDS = {"shift-jis": "表", "big5": "許"}


def encoded_text(encoding: str) -> str:
    """Returns the characters of the encoding named `encoding` that its
    probe's txt holds: _SAMPLES' for an encoding of two-byte characters and
    utf-8; for ascii, the printable ASCII characters but a double quote and
    a backslash (_ASCII); and for the others, each character of the bytes
    from 0x80 to 0xFF that the encoding has, but its control characters."""
    if encoding in _SAMPLES:
        return _SAMPLES[encoding]
    if encoding == "ascii":
        return _ASCII
    codec, characters = TextCodec(encoding), []
    for byte in range(0x80, 0x100):
        try:
            character = codec.decode(bytes([byte]), "a probe's txt")
        except NxwrightError:
            continue
        if unicodedata.category(character) != "Cc":
            characters.append(character)
    return "".join(characters)


@dataclass(frozen=True, eq=False)
class EncodingChange:
    """A probe's change: `change`, then the folder's encoding changed to the
    one named `encoding`, as nxwright's device command changes it. A unit
    test reads both, to make the pages `change` adds in memory, in that
    encoding (tests/tft/unit_inputs.py). Raises ProbeError when nxwright's
    checks then refuse the folder. Two changes are equal only if they are
    the same one, as two functions are."""
    encoding: str
    change: object

    def __call__(self, folder: Path):
        self.change(folder)
        if self.encoding != "iso-8859-1":
            done = change_device(folder, encoding=self.encoding)
            if done.refusals:
                raise ProbeError("in %s, nxwright refuses %s" % (self.encoding, done.refusals))


def in_encoding(encoding: str, change) -> EncodingChange:
    """Returns a probe's change: `change`, then the folder's encoding changed
    to the one named `encoding` (EncodingChange)."""
    return EncodingChange(encoding, change)


def _text_and_code(encoding: str) -> ProgramChange:
    """The text t0 of the encoding's characters, and code of ASCII texts
    after a comment of the encoding's characters, which gives no block, in
    strict Nextion syntax (ProgramChange)."""
    comment = "// " + encoded_text(encoding)[:12] + _BACKSLASH_BYTE_ENDS.get(encoding, "")
    return ProgramChange(code=touch_release_code([comment, *_ASCII_CODE]),
                         components=(text_component("t0", w=300, h=200,
                                                    txt=encoded_text(encoding), txt_maxl=200),))


def _every_txt(encoding: str):
    """A text, a button, a dual-state button, a scrolling text, a QR code, and
    a variable of a text, each of the encoding's first 12 characters."""
    txt = encoded_text(encoding)[:12]
    return with_components(
        text_component("t0", txt=txt, txt_maxl=30),
        button_component("b0", y=50, txt=txt, txt_maxl=30),
        dual_state_button_component("bt0", y=110, txt=txt, txt_maxl=30),
        scrolling_text_component("g0", y=180, txt=txt, txt_maxl=30),
        qr_code_component("qr0", y=220, txt=txt, txt_maxl=30),
        text_variable_component("va0", txt=txt, txt_maxl=30))


def code_of(x: str, y: str) -> list:
    """Returns lines of each family of code that takes a text, as the probe of
    texts' characters in iso-8859-1 has them (text_character_probes.py), of
    the texts `x` and `y`: plain_code_of's, then the commands'."""
    return plain_code_of(x, y) + [
        'xstr 0,0,100,30,0,RED,WHITE,0,0,1,"%s"' % x, 'prints "%s",0' % y, 'print "%s"' % x,
        'get "%s"' % y, 'spstr t0.txt,t0.txt,"%s",0' % y, 'strlen "%s",sys0' % x,
        'btlen "%s",sys0' % x, 'crcputs "%s",0' % y]


def plain_code_of(x: str, y: str) -> list:
    """Returns the lines of code_of that hold no command, of the texts `x`
    and `y`: a txt set, added to, and joined, and compared in if, while,
    and for."""
    return ['t0.txt="%s"' % x, 't0.txt+="%s"' % y, 't0.txt="%s, "+t0.txt' % x,
            'if(t0.txt=="%s")' % x, "{", "sys0=1", "}",
            'while(t0.txt!="%s")' % y, "{", 't0.txt="%s"' % y, "}",
            'for(sys0=0;t0.txt=="%s";sys0++)' % y, "{", "sys1=1", "}"]


# The texts of each probe of code, by encoding. In shift-jis and big5, 表,
# ソ, 能, 許, and 功 end in 0x5C, so each comes before another character.
CODE_TEXTS = {"gb2312": ("中文字", "文"), "utf-8": ("é中€\U0001F600", "ü"),
              "shift-jis": ("日本表日", "ソ能日"), "big5": ("中文許中", "功中"),
              "ks_c_5601-1987": ("한국어", "글"), "koi8-r": ("Привет", "ж"),
              "windows-1256": ("سلام€", "ب"), "iso-8859-2": ("Łódź", "ż")}
# The probes of code that keep fixtures: a two-byte encoding's, and
# shift-jis's, whose texts hold bytes of 0x5C.
_KEEPING_CODE = ("gb2312", "shift-jis")


def _code_probe(name: str, series: str = "T", lines: list = None) -> Probe:
    """Returns the probe of `lines`, or of CODE_TEXTS' of the encoding
    `name` in each family, in page0's Touch Release event, beside the text
    t0, in that encoding, on `series`."""
    lines = lines or code_of(*CODE_TEXTS[name])
    return Probe("encoding-code-in-%s%s" % (name, "" if series == "T" else "-on-" + series),
                 series, in_encoding(name, with_attributes(lines, [text_component(txt_maxl=100)])),
                 ours_in_event, theirs_in_event,
                 FIXTURES if series == "T" and name in _KEEPING_CODE else None)


def _page_probe(name: str):
    """The change of the page's probe `name` (page_probes.py)."""
    return next(probe.change for probe in page_probes.PROBES if probe.name == name)


def _global_probe(name: str):
    """The change of the global objects' probe `name`
    (shared_attribute_probes.py)."""
    return next(probe.change for probe in shared_attribute_probes.PROBES if probe.name == name)


# The probes that keep fixtures: an encoding of two-byte characters, whose
# entries carry its byte; utf-8; and one of one byte a character.
_KEEPING = ("gb2312", "utf-8", "koi8-r")

PROBES = ([type_probe("encoding", name, in_encoding(name, _text_and_code(name)),
                      fixtures=name in _KEEPING)
           for name in ENCODINGS.values()]
          + [type_probe("encoding", "every-txt-in-" + name, in_encoding(name, _every_txt(name)))
             for name in ("gb2312", "utf-8", "shift-jis", "koi8-r")]
          + [type_probe("encoding", "every-type-in-%s" % name,
                        in_encoding(name, _page_probe(probe)))
             for name, probe in (("gb2312", "page-every-type-on-a-picture"),
                                 ("utf-8", "page-every-type-on-a-picture"),
                                 ("big5", "page-every-type-on-no-background"))]
          # Global objects, whose entries carry the byte too, from their place
          # among the int variables.
          + [type_probe("encoding", "globals-in-gb2312", in_encoding(
              "gb2312", _global_probe("shared-attributes-globals-on-two-pages")))]
          + [_code_probe(name) for name in CODE_TEXTS]
          # Texts the Nextion Editor reads in pairs, as it takes them: 表 and 許,
          # whose last byte is 0x5C, at a text's end in assignments, print,
          # get, and xstr; ｱ, of one byte from 0xA1 up, before another
          # character, and two of them; and gb2312's 乗, 81 5c.
          + [Probe("encoding-code-read-in-pairs-in-" + name, "T", in_encoding(
              name, with_attributes(lines, [text_component(txt_maxl=100)])),
              ours_in_event, theirs_in_event)
             for name, lines in (
                 ("shift-jis", ['t0.txt="表"', 't0.txt+="表"', 'print "日表"', 'get "日表"',
                                'xstr 0,0,100,30,0,RED,WHITE,0,0,1,"表"',
                                't0.txt="日表"+t0.txt', 'prints "ｱa",0', 'if(t0.txt=="ｱa")', "{",
                                "sys0=1", "}", 't0.txt="ｱｱ"', 't0.txt="ｱ日a"',
                                't0.txt="表\\""', 'strlen "ｱa",sys0']),
                 ("big5", ['t0.txt="許"', 'prints "許a",0', 'if(t0.txt=="中許中")', "{",
                           "sys0=1", "}"]),
                 ("gb2312", ['t0.txt="乗"', 'prints "乗a",0']))]
          # K's own command that takes a text, wepo, on K.
          + [_code_probe("gb2312", "K", ['wepo "中文",0']),
             _code_probe("utf-8", "K", ['wepo "é中",0'])])

# For P: a text of ASCII letters and digits, in each encoding of two-byte
# characters, utf-8, and three of one byte a character.
ASCII_PROBES = [type_probe("encoding", "ascii-txt-in-" + name, in_encoding(
                    name, with_components(text_component("t0", txt="Hi12"))))
                for name in ("gb2312", "big5", "shift-jis", "ks_c_5601-1987", "utf-8",
                             "koi8-r", "iso-8859-2", "windows-1258")]
