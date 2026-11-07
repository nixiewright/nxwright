"""What a component's type writes on P, for the tests of each type: its
memory, the values in it after its record's head, and its entries
(tft/component_types/__init__.py).

On P, a component's memory starts with its record's head, which the frame
writes. So a type's test compares the values after the head with a probe's
piece page0-N-memory, and the head is left to the frame's tests. Each
function takes a page object on P, as tests/tft/unit_inputs.py's page() makes
it, and its place, as the frame placed it in the probe the test compares
with (ObjectPlace): its first entry, its base, and where its texts lie. A
type whose table reads more of the project than its series and fonts, as a
picture's highest is the project's last, is given `project`, a Project of
those facts too (tests/tft/unit_inputs.py).
"""
from functools import lru_cache

from nxwright.tft import component_types, frame
from nxwright.tft.component_types import ObjectPlace
from tools.tft.probing import p_probes
from tests.tft.t_components import ComponentPieces
from tests.tft.unit_inputs import project_of


def p_probe(name: str):
    """Returns the probe of p_probes.py named `name`."""
    return next(probe for probe in p_probes.PROBES if probe.name == name)


# P's probes of several types, by their names: pages of each background and
# their swipes, beside components; components that overlap; places past the
# screen's edges and at their entries' highest; globals beside locals and on
# two pages; and the attributes every object has. Each type's tests take
# its own probes alone, so test_p_series.SeveralTypesTest takes these.
# Their samples of whole files are in tests/tft/test_whole_files.py.
SEVERAL_TYPES = (
    "p-page-of-other-colours", "p-page-of-swipes", "p-page-of-its-effect-and-swipes-in-code",
    "p-page-of-an-effect-in-code", "p-page-of-no-background",
    "p-page-of-pictures", "p-page-of-a-picture-without-pictures",
    "p-page-of-no-background-and-code", "p-page-every-type-on-no-background",
    "p-page-every-type-on-a-picture",
    "p-overlap-two", "p-overlap-chain-1-4-5-3-6-beside-2", "p-overlap-ids-past-9",
    "p-overlap-types-under-a-picture", "p-overlap-more-types-under-a-picture",
    "p-overlap-hotspot-and-xfloat-under-a-picture",
    "p-overlap-slider-gauge-qr-code-and-waveform-under-a-picture",
    "p-overlap-scrolling-text-under-a-picture", "p-overlap-p-types-under-texts",
    "p-place-past-the-screen-s-edges", "p-place-every-type-at-the-entries-highest",
    "p-place-sizes-at-the-entries-highest",
    "p-globals-beside-a-text", "p-globals-on-two-pages", "p-globals-under-a-wide-room",
    "p-shared-attributes-that-change-nothing-on-t", "p-shared-attributes-drag-and-moves",
    "p-shared-attributes-of-globals", "p-shared-attributes-effects",
    "p-shared-attributes-effects-and-a-second-page",
    "p-shared-attributes-global-pages-on-two-pages")
# P's probes of txts past ASCII letters and digits, by the starts of their
# names: T's of txts' characters, the encodings' of a txt on each type, and
# P's own of its types with a txt. test_text_characters.TxtOnPTest takes
# them, and their sample of whole files is in tests/tft/test_whole_files.py.
TXTS_PAST_ASCII = ("p-text-characters-txt-", "p-encoding-every-txt-in-", "p-txts-past-ascii-")


@lru_cache(maxsize=None)
def _facts():
    """Returns a Project of the facts of P that a type's memory and entries
    read: its series and its fonts."""
    return project_of(series="P")


def p_memory(page_object, place: ObjectPlace, project=None) -> bytes:
    """Returns the memory on P of the component `page_object`, at `place`,
    as its type writes it, after a head of zeros, which the frame writes.
    `project` is a Project of the facts it reads, by default its series and
    its fonts."""
    project = project or _facts()
    module = component_types.object_module(page_object)
    return component_types.p_component_memory(
        page_object, bytes(frame._p_head_size(module)),
        component_types.p_table(module, page_object, project), module.P_MEMORY_SIZE,
        component_types.p_memory_extras(module, page_object, project, place))


def p_values(page_object, place: ObjectPlace, project=None) -> bytes:
    """Returns the values the component's type writes in its memory on P,
    after its head: what the piece page0-N-memory holds. `project` is as
    p_memory takes it."""
    head_size = frame._p_head_size(component_types.object_module(page_object))
    return p_memory(page_object, place, project)[head_size:]


def p_entries(page_object, place: ObjectPlace, project=None) -> bytes:
    """Returns the entries on P of the component `page_object`, at `place`:
    what the piece page0-N-entries holds. `project` is as p_memory takes
    it."""
    module = component_types.object_module(page_object)
    return component_types.p_component_entries(
        component_types.p_table(module, page_object, project or _facts()), module.ENTRIES,
        place, getattr(module, "P_OWNER_TOPS", None), getattr(module, "P_OWNER", None))


class PTypePieces(ComponentPieces):
    """ComponentPieces on P, for probes on P: each component's values in its
    memory after its record's head, and its entries, at its type's functions
    (p_values, p_entries). Its head, and its drawing, which on P is its 0
    word alone, are the frame's, and have no test here."""

    @staticmethod
    def memory_of(page_object, project, place) -> bytes:
        return p_values(page_object, place, project)

    @staticmethod
    def entries_of(page_object, project, place) -> bytes:
        return p_entries(page_object, place, project)
