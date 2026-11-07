"""The ref commands the Nextion Editor 1.68.2 writes, on T, K, and F, for drawn
components that overlap (ResearchNotes/tft/user-code-frame.md, "Components that
overlap", gives what the probes showed).

Two components overlap when they share a pixel (matching.share_a_pixel).
Components that only touch, at a side or a corner, do not. When a drawn
component overlaps another, its background fill ends with ref commands, each
`ref` and a component's ID. Which IDs, and in which order, comes from a
walk:

  - The walk starts at the component itself. Each time, it walks the listed
    component of lowest ID that it has not walked yet. Walking a component
    lists every component that overlaps it.
  - When it lists a component whose ID is below every one listed before,
    the Editor writes a ref for each component walked so far, in ID order,
    but the component itself. Then the walk starts again, with none walked.
  - When no component is left to walk, the Editor writes a ref for each
    component listed, in ID order, but the component itself.

So a component that does not overlap another can still be in its refs,
through a third that overlaps both, and some are in them twice.

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
    component whose ID is `object_id`, in their order (the module's
    docstring). `areas` gives each drawn component of its page, {ID: (x, y,
    width, height)}. It is empty for a component that overlaps none."""
    listed, walked, refs = {object_id}, set(), []
    while listed - walked:
        walking = min(listed - walked)
        walked.add(walking)
        added = {other for other, area in areas.items()
                 if other not in listed and share_a_pixel(areas[walking], area)}
        if added and min(added) < min(listed):
            refs += sorted(walked - {object_id})
            walked = set()
        listed |= added
    return refs + sorted(listed - {object_id})


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
