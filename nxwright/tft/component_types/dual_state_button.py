"""The dual-state button component, as the Nextion Editor 1.68.2 writes it on
T and K (ResearchNotes/tft/dual-state-button-component.md gives each value, and how
it was found), and on P, where it is written as a button is there: no
drawing blocks, no switch of its val or ref of itself in its down event,
and its memory and entries a button's, its val its own.

So far it writes a dual-state button at its defaults but for its place, its
size, its text, its txt_maxl, its val, 1 when it is pressed in, and the
values a button's memory, drawing, and entries give: its font, bco, bco2,
pco, pco2, xcen, ycen, isbr, spax, and spay, and its border and what lies
behind it, as a button's: its sta, style, borderc, borderw, pic, pic2,
picc, and picc2. It is written as the button of its sta and style is
(button.variant): its drawing, its entries, its record, and its memory,
whose val follows its own. Its events differ. Its down event starts with a
checkbox's code that switches its val, then a button's ref of itself. Its
up event has no code of the Nextion Editor's own.
"""
from functools import lru_cache

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.component_types import (PLACE_WORDS, TXT_WORDS, TXT_MAXL_WORDS,
                                   border_and_background_rules, entry_operand,
                                   place_fits_its_record, text_fits, txt_maxl_covered, value_rule)
from nxwright.tft.component_types import button
from nxwright.tft.component_types.checkbox import val_switch
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT

EVENTS = ("down", "up")


class _DualStateButton:
    """A dual-state button written as the button variant `as_button` is
    (button.variant), with the members a type's module gives
    (component_types/__init__.py) but MATCHED."""
    EVENTS = EVENTS

    def __init__(self, as_button):
        self._button = as_button
        # Its drawing, entries, and record are a button's.
        self.ENTRIES = as_button.ENTRIES
        self.background_fill = as_button.background_fill
        self.drawing = as_button.drawing
        self.data = as_button.data
        self.record_slots = as_button.record_slots
        self.attribute_place = as_button.attribute_place
        # On P, its memory and entries are a button's too, its pictures'
        # highest values among them. Its val, at 72, comes from its own
        # attribute, as every value there does.
        self.P_ENTRIES = as_button.P_ENTRIES
        self.P_MEMORY_SIZE = as_button.P_MEMORY_SIZE
        self.P_TEXTS = as_button.P_TEXTS
        self.P_LAST_RESOURCE = as_button.P_LAST_RESOURCE
        # On T, K, and F, its txt lies in its memory where a button's does.
        self.TXT_PLACE = as_button.TXT_PLACE

    def memory(self, page_object, project) -> bytes:
        """Returns the dual-state button's starting values: a button's, with
        its val, 0 by default (memory_of)."""
        val = page_object.attribute("val")
        return self._button.memory_of(page_object, 0 if val is None else number_from_bytes(val))

    def event_start(self, page_object, project, place, event: str) -> list:
        """Returns the blocks the Nextion Editor writes at the start of the
        dual-state button's events (event_blocks)."""
        return self.event_blocks(project.settings.model.series, place, event)

    def event_blocks(self, series: str, place, event: str) -> list:
        """Returns the blocks the Nextion Editor writes at the start of the
        event `event` of the dual-state button at `place`, on `series`: in
        its down event, a checkbox's, which switch its val
        (checkbox.val_switch), then its ref of itself (button.self_ref). Its
        up event has none. They need only these, so that the decoder can
        write them again from what a TFT file keeps."""
        if event != "down":
            return []
        val = entry_operand(place.first_entry + self.attribute_place("val"))
        return val_switch(val, series) + [button.self_ref(place)]


@lru_cache(maxsize=None)
def _of(as_button) -> _DualStateButton:
    """Returns the dual-state button written as the button variant
    `as_button`, made once."""
    return _DualStateButton(as_button)


def variant(page_object) -> _DualStateButton:
    """Returns what describes the dual-state button `page_object`: one
    written as the button of its sta and its style (button.variant)."""
    return _of(button.variant(page_object))


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# What the dual-state button has matched with probes (matching.py): a
# dual-state button at its defaults, on each screen model of T and K at each
# rotation, and on P and E, but for these.
MATCHED = [
    Rule("type", "dual-state-button", "a dual-state button, its attributes at their defaults "
         "but for those below"),
    Rule("attribute", "dual-state-button.objname", "any name nxwright's build takes"),
    Rule("attribute", "dual-state-button.x", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "dual-state-button.y", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "dual-state-button.w", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "dual-state-button.h", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "dual-state-button.txt", TXT_WORDS, text_fits),
    Rule("attribute", "dual-state-button.txt_maxl", TXT_MAXL_WORDS, txt_maxl_covered,
         DOES_NOT_FIT),
    Rule("attribute", "dual-state-button.val", "any value, written as it is"),
    Rule("attribute", "dual-state-button.font", "any font of the project"),
] + [Rule("attribute", "dual-state-button." + name, *value_rule(name))
     for name in ("bco", "bco2", "pco", "pco2", "xcen", "ycen", "isbr", "spax", "spay")] + [
    Rule("attribute", "dual-state-button." + name, words, covers, reason)
    for name, words, covers, reason in border_and_background_rules(button=True)]
