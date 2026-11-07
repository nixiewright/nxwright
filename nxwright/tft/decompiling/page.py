"""Reads a page's own attributes back, as the frame writes them (frame.py),
splits its load section into its load and loadend events' code, and
recognises the refs the Nextion Editor adds after the background fill of a
component that overlaps others (overlaps.py).

On T, K, and F, a page keeps its place and size, its vscope, its aph, and
its sendkey in its record; its swipe targets, its sta, and its background,
its bco or its pic by its sta, in its memory; and whether it has an effect
in how many entries it has. The file does not keep which effect, so a page
with one is given effect 1, sliding in from the top, which compiles to the
same file as any other.

On P, a page's values lie where its named entries say, which
objects.p_values reads, its effect among them. Its aph is in its record's
head, and its drag in the head its memory starts with (frame.P_DRAG_PLACE),
as no entry gives either.
"""
import struct

from nxwright.project.page_block import Attribute, PageObject

from nxwright.tft import frame, overlaps
from nxwright.tft.component_types import PAGE_BACKGROUND_NAMES, REF, SERIES_WRITTEN_AS_P, page_entries
from nxwright.tft.decompiling import DecodeError, numbers
from nxwright.tft.decompiling.decoded_file import CodeRun, DecodedFile, DecodedPage
from nxwright.tft.decompiling.jumps import jump_targets
from nxwright.tft.decompiling.objects import (AN_EFFECT, ObjectValues, memory_at, object_memory,
                                       p_values, record_head)
from nxwright.tft.tft_file import encode_blocks

# A block's size word.
_SIZE_WORD = 4


def decoded_page_values(decoded_page: DecodedPage, decoded_file: DecodedFile) -> ObjectValues:
    """Returns the ObjectValues of `decoded_page`'s own object, ID 0. Raises
    DecodeError for what it cannot read."""
    page = decoded_page.objects[0]
    head = record_head(page)
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        (drag,) = memory_at(page, decoded_page, decoded_file, page.base + frame.P_DRAG_PLACE, 1)
        return ObjectValues({**p_values(page, decoded_page, decoded_file), "aph": head.aph,
                             "drag": drag})
    up, down, left, right, sta, background = struct.unpack(
        frame.PAGE_MEMORY_FORMAT,
        object_memory(page, decoded_page, decoded_file, frame.PAGE_MEMORY_SIZE))
    # How many entries a page of its sta has without an effect and with one,
    # as the compile counts them.
    counts = {effect: page_entries(PageObject([Attribute("sta", sta.to_bytes(2, "little")),
                                               Attribute("effect", bytes([effect]))]))
              for effect in (0, AN_EFFECT)}
    effect = next((effect for effect, count in counts.items() if count == len(page.entries)),
                  None)
    if effect is None:
        raise DecodeError("page %d has %d entries, but a page of sta %d has %d, or %d with an "
                          "effect" % (decoded_page.page_id, len(page.entries), sta, counts[0],
                                      counts[AN_EFFECT]),
                          head.drawing_place, b"".join(page.entries))
    attributes = {"vscope": int(head.is_global), "x": head.x, "y": head.y, "w": head.w,
                  "h": head.h, "aph": head.aph, "sendkey": head.sendkey, "effect": effect,
                  "up": up, "down": down, "left": left, "right": right, "sta": sta}
    if sta in PAGE_BACKGROUND_NAMES:
        attributes[PAGE_BACKGROUND_NAMES[sta]] = background
    return ObjectValues(attributes)


def overlap_refs(decoded_page: DecodedPage, decoded_file: DecodedFile) -> dict:
    """Returns {component's ID: how many blocks at the end of its background
    fill's run are the refs the Nextion Editor adds for the components it
    overlaps}, for each component of `decoded_page` that has some. The
    refs are written again from the drawn components' places, as the frame
    writes them (overlaps.refreshed), and each is `ref` and an ID, as the
    statement encoder gives `ref 2`. Raises DecodeError for a background
    fill that does not end with its refs."""
    heads = {each.object_id: record_head(each) for each in decoded_page.objects[1:]}
    areas = {object_id: (head.x, head.y, head.w, head.h)
             for object_id, head in heads.items() if head.drawn}
    counts = {}
    for decoded_object in decoded_page.objects[1:]:
        if decoded_object.object_id not in areas:
            continue
        refs = [REF + b"%d" % other
                for other in overlaps.refreshed(areas, decoded_object.object_id)]
        if not refs:
            continue
        fill = decoded_object.background_fill
        if fill[-len(refs):] != refs:
            raise DecodeError("component %d's background fill does not end with the refs of "
                              "the components it overlaps" % decoded_object.object_id,
                              heads[decoded_object.object_id].background_fill_place,
                              encode_blocks(fill))
        counts[decoded_object.object_id] = len(refs)
    return counts


def page_load_runs(decoded_page: DecodedPage, decoded_file: DecodedFile,
                   components_blocks: int) -> tuple:
    """Returns (the CodeRun of the load event's code, that of the loadend
    event's code) of `decoded_page`, from its load section, whose first
    `components_blocks` blocks its components added. The two are split at
    a doevents block that no jump of the code crosses, as the page's own
    code may hold a doevents too. Raises DecodeError when no such block
    splits them.

    Where several doevents blocks would do, the first is taken. Each split
    compiles to the same blocks, as a doevents at the end of the load event
    gives the same bytes as one at the start of the loadend event."""
    section = decoded_page.load_section
    places = section.block_places()[components_blocks:]
    blocks = section.blocks[components_blocks:]
    start = places[0] if places else section.place + len(encode_blocks(section.blocks))
    jumps = jump_targets(CodeRun(start, blocks))
    doevents = numbers.as_written(frame.DOEVENTS[decoded_file.series], decoded_file.series,
                                  decoded_file.version)
    for number, (place, block) in enumerate(zip(places, blocks)):
        if block != doevents:
            continue
        after = place + _SIZE_WORD + len(block)
        # A jump of the load event's code must land within that code, at
        # most at its end, where the doevents lies. A jump of the loadend
        # event's code must land within the loadend event's code.
        if all(target <= place if source < place else target >= after
               for source, target in jumps):
            return CodeRun(start, blocks[:number]), CodeRun(after, blocks[number + 1:])
    raise DecodeError("page %d's load section has no doevents block that no jump crosses"
                      % decoded_page.page_id, start, encode_blocks(blocks))
