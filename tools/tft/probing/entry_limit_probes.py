"""The probes of attributes at the limits their entries give, which the
Nextion Editor takes, and which the check took less of before: a txt_maxl
of 0 and of the most a page holds, on every type with a txt_maxl, and a QR
code's to its entry's highest, where a page holds it (_QR_CODE_MOST); a
sliding text's txt_maxl at its most, beside its default lines, as the check
refuses the empty txt its 0 would need; a scrolling text's vvs0 to vvs3
past 32767, to the 65535 their 2 bytes hold; and a page's effect of 9 and
10. Each is built on every series its type's module takes, and compares
the whole file. Run them with
`tools.tft.probe run entry_limit_probes`.

A txt_maxl's most is its entry's, 65534, on P and E. On T, K, and F, a
page's memory holds less, which nxwright's build checks: the probes take
3000 on T and F, and 8000 on K, round values below the most a page of the
base model holds. Those that show a case first keep the user code as
fixtures: on T, a text's txt_maxl of 0 and of 3000, the vvs, and the
effects; on P, a text's txt_maxl of 0 and the effects.
"""
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.combo_box_probes import combo_box_component
from tools.tft.probing.component_probes import (editor_file, on_pages, page_attribute_lines,
                                            user_code_kept, whole_file, with_components)
from nxwright.tft.component_types import type_module
from tools.tft.probing.dual_state_button_probes import dual_state_button_component
from nxwright.tft.frame import SERIES as PAGE_SERIES
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.qr_code_probes import qr_code_component
from tools.tft.probing.scrolling_text_probes import scrolling_text_component
from tools.tft.probing.sliding_text_probes import sliding_text_component
from tools.tft.probing.switch_probes import switch_component
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.variable_probes import text_variable_component

FIXTURES = "entry-limits"

# The most txt_maxl the probes give, by series (the module's docstring).
_MOST_TXT_MAXL = {"T": 3000, "K": 8000, "F": 3000, "P": 0xFFFE, "E": 0xFFFE}

# Each type with a txt_maxl, and its component in a page file's form with an
# empty txt and a txt_maxl.
_WITH_A_TXT_MAXL = {
    "text": lambda maxl: text_component(txt="", txt_maxl=maxl),
    "button": lambda maxl: button_component(txt="", txt_maxl=maxl),
    "dual-state-button": lambda maxl: dual_state_button_component(txt="", txt_maxl=maxl),
    "scrolling-text": lambda maxl: scrolling_text_component(txt="", txt_maxl=maxl),
    "variable": lambda maxl: text_variable_component(txt="", txt_maxl=maxl),
    "switch": lambda maxl: switch_component(txt="", txt_maxl=maxl),
    "combo-box": lambda maxl: combo_box_component(txt="", txt_maxl=maxl),
}
# A QR code's txt_maxl past 154, by series: its entry's highest, 192 on K,
# 368 on F, and 630 on P and E, and on those, 255, the first whose txt's
# size, txt_maxl + 1, takes a second byte of its entry's code. On T, a page
# of NX4832T035 holds a QR code alone up to 154, which nxwright's build
# checks, so none goes past it there.
_QR_CODE_MOST = {"K": (192,), "F": (255, 368), "P": (255, 630), "E": (255, 630)}
# The probes that keep fixtures, by name.
_KEEPING = {"t-text-txt-maxl-0", "t-text-txt-maxl-3000", "p-text-txt-maxl-0",
            "t-scrolling-text-vvs-past-32767", "t-page-effects-9-and-10",
            "p-page-effects-9-and-10"}


def _probe(series: str, name: str, change) -> Probe:
    name = "%s-%s" % (series.lower(), name)
    return Probe(name, series, change, whole_file, editor_file,
                 FIXTURES if name in _KEEPING else None, user_code_kept)


# page0 with an effect of 9, fading in, and page1 with one of 10, growing
# from the middle, each with a text. with_components adds page1.
_TWO_PAGES = on_pages(
    with_components(text_component(), attributes=page_attribute_lines(effect=9)),
    with_components(text_component(), page="page1",
                    attributes=page_attribute_lines(effect=10)))


PROBES = [
    _probe(series, "%s-txt-maxl-%d" % (type_name, maxl), with_components(component(maxl)))
    for type_name, component in _WITH_A_TXT_MAXL.items()
    for series in type_module(type_name).SERIES
    for maxl in (0, _MOST_TXT_MAXL[series])
] + [
    _probe(series, "qr-code-txt-maxl-0",
           with_components(qr_code_component(txt="", txt_maxl=0)))
    for series in type_module("qr-code").SERIES
] + [
    _probe(series, "qr-code-txt-maxl-%d" % maxl,
           with_components(qr_code_component(txt_maxl=maxl)))
    for series, most in _QR_CODE_MOST.items() for maxl in most
] + [
    _probe(series, "qr-code-txt-maxl-%d-of-%d-characters" % (most[-1], length),
           with_components(qr_code_component(txt="a" * length, txt_maxl=most[-1])))
    for series, most, length in (("F", _QR_CODE_MOST["F"], 300), ("P", _QR_CODE_MOST["P"], 600))
] + [
    _probe(series, "sliding-text-txt-maxl-65534",
           with_components(sliding_text_component(txt_maxl=0xFFFE)))
    for series in type_module("sliding-text").SERIES
] + [
    # Each of the four past 32767: one past it, two between, and the most.
    _probe(series, "scrolling-text-vvs-past-32767", with_components(scrolling_text_component(
        vvs0=32768, vvs1=40000, vvs2=50000, vvs3=0xFFFF)))
    for series in type_module("scrolling-text").SERIES
] + [
    _probe(series, "page-effects-9-and-10", _TWO_PAGES)
    for series in PAGE_SERIES
]
