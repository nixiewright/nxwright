"""The ref commands that the Nextion Editor 1.68.2 writes on T, K, and F for
drawn components that overlap. ResearchNotes/tft/user-code-frame.md,
"Components that overlap", has what the probes showed.

Two components overlap when they share a pixel (matching.share_a_pixel).
Components that only touch, at a side or a corner, do not. When a drawn
component overlaps another, its background fill ends with ref commands,
such as `ref 3`, that redraw the others. The Nextion Editor chooses which
components get a ref, and in which order, with a depth-first walk that
starts at the component itself:

  - Walking a component lists its neighbours, the components that overlap it.
  - The walk goes next to the neighbour of lowest ID, not yet walked, of the
    component walked last. If that component has none left, the walk tries
    the one walked before it, and so on.
  - When the walk lists a component whose ID is below every one listed
    before, the Nextion Editor writes a ref for each component walked so
    far, in ID order. The walk then starts again at the listed component of
    lowest ID, with no component walked. The components listed so far stay
    listed.
  - When no listed component is left to walk, the Nextion Editor writes a
    ref for each one listed, in ID order.

A component never gets a ref to itself. Its refs can include a component
that does not overlap it, through a third that overlaps both, and can
include the same component twice.

On P and E, a component has no drawing blocks and no background fill
(frame._component_blocks), so components that overlap write no ref, and
the file is the same as if they did not overlap (ResearchNotes/tft/p-series.md).
"""
from nxwright.tft.component_types import SERIES_WRITTEN_AS_P
from nxwright.tft.matching import Rule, share_a_pixel
from nxwright.tft.statements import CodePlace, encode_line

# The types whose overlaps the probes matched, all drawn.
_TYPES = ("text", "number", "button", "crop", "picture", "progress-bar", "checkbox", "radio",
          "dual-state-button", "hotspot", "xfloat", "slider", "gauge", "qr-code", "waveform",
          "scrolling-text")
# The types of P and E alone, each with a place, whose overlaps the probes
# matched there.
_P_TYPES = ("switch", "external-picture", "select", "combo-box", "sliding-text", "gmov",
            "video", "data-record", "file-browser")


def refreshed(areas: dict, object_id: int) -> list:
    """Returns the IDs of the refs that end the background fill of the
    component whose ID is `object_id`, in their order. `areas` gives the area
    of each drawn component on the page, as {ID: (x, y, width, height)}. The
    list is empty for a component that overlaps none. The module's docstring
    describes the walk that chooses the refs."""
    listed, walked, refs = {object_id}, set(), []
    # The components walked since the last restart that may still have a
    # neighbour left to walk, in the order they were walked.
    path = []
    while listed - walked:
        left = listed - walked
        # Go back along the path to the last component with a neighbour left
        # to walk. If the path is empty, at the start or after a restart, the
        # walk takes the lowest ID left.
        while path and not _neighbours_in(areas, path[-1], left):
            path.pop()
        walking = min(_neighbours_in(areas, path[-1], left) if path else left)
        walked.add(walking)
        path.append(walking)
        added = {other for other, area in areas.items()
                 if other not in listed and share_a_pixel(areas[walking], area)}
        if added and min(added) < min(listed):
            refs += sorted(walked - {object_id})
            walked, path = set(), []
        listed |= added
    return refs + sorted(listed - {object_id})


def _neighbours_in(areas: dict, object_id: int, others: set) -> list:
    """Returns the IDs of `others` whose components overlap the component
    whose ID is `object_id`."""
    return [other for other in others if share_a_pixel(areas[object_id], areas[other])]


def ref_blocks(context, areas: dict, object_id: int) -> list:
    """Returns the blocks of the refs that end the background fill of the
    component whose ID is `object_id` (refreshed), each the block the
    statement encoder gives `ref` and the ID, in the compile's context
    `context`."""
    return [encode_line("ref %d" % other, CodePlace(), context)
            for other in refreshed(areas, object_id)]


def _covered(need) -> bool:
    """Whether the overlap `need` is of two components of the types probed
    on its series (matching.py gives them)."""
    types = need.context.get("types", ())
    probed = _TYPES + (_P_TYPES if need.series in SERIES_WRITTEN_AS_P else ())
    return len(types) == 2 and all(name in probed for name in types)


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# F in f_probes.py, P in p_probes.py, and E in e_probes.py.
SERIES = ("T", "K", "F", "P", "E")

MATCHED = [Rule("overlap", None, "two components of the types text, number, button, crop, "
                "picture, progress-bar, checkbox, radio, dual-state-button, hotspot, xfloat, "
                "slider, gauge, qr-code, waveform, and scrolling-text that share a pixel; and "
                "on P and E, of those and of the switch, external-picture, select, combo-box, "
                "sliding-text, gmov, video, data-record, and file-browser too", _covered)]
