"""The pieces of a probe of labels and goto (tools/tft/probing/goto_probes.py) as
the functions that write them give them, for the tests of the goto
statement and of the follower series: program.s's blocks, each event's,
and each block in a page's load section that the labels' numbers shift.

Each takes a probe that keeps fixtures, whose table gives where each run of
code starts and where each component lies (tests/tft/unit_inputs.py), and a
Project of the facts of that probe's pages, or of a follower's, whose
places are the same.
"""
import re

from nxwright.tft.compile_context import CompileContext
from nxwright.tft import label_numbers
from nxwright.tft.component_types import object_module, object_name
from nxwright.tft.matching import code_lines
from nxwright.tft.statements import CodePlace, encode_code
from nxwright.tft.tft_file import encode_blocks
from tests.tft.unit_inputs import blocks_place, piece_names, place


def program_s(probe, project) -> bytes:
    """Returns program.s's blocks, through the statement encoder, their
    labels and gotos written (label_numbers.resolved) from where the
    probe's table gives program.s starts: the start of the piece
    program-s, which the frame's own blocks follow."""
    blocks = encode_code(code_lines(project, project.program), CodePlace(), CompileContext(project))
    return encode_blocks(label_numbers.resolved(blocks, 0, blocks_place(probe, "program-s")))


def event_pieces(probe, project) -> dict:
    """Returns {the piece's name: its bytes} of each piece of `probe`'s
    fixtures that holds an event, such as page0-3-event-down: the event's
    name, the blocks its type writes at its start (event_start), such as a
    timer's "S " block, its code's blocks, their labels and gotos written,
    then a 0 word. A page's load and loadend events have no name, as the
    page's load section holds them, and its load event no 0 word, as the
    page's doevents block follows it."""
    numbers = label_numbers.numbers(project)
    found = {}
    for name in piece_names(probe):
        matched = re.fullmatch(r"page(\d+)-(\d+)-event-(\w+)", name)
        if not matched:
            continue
        number, object_id, event = int(matched[1]), int(matched[2]), matched[3]
        page_object = project.pages[number].objects[object_id]
        its_name = object_name(page_object)
        head = [] if event in ("load", "loadend") else [event.encode("ascii")]
        module = object_module(page_object)
        if object_id and hasattr(module, "event_start"):
            head += module.event_start(page_object, project,
                                       place(probe, "page%d-%d" % (number, object_id)), event)
        blocks = encode_code(code_lines(project, label_numbers.event_code(page_object, event)),
                             CodePlace(number, its_name, event), CompileContext(project))
        start = blocks_place(probe, name) + len(encode_blocks(head))
        ending = [] if event == "load" else [b""]
        found[name] = encode_blocks(head + label_numbers.resolved(
            blocks, numbers.events[number, its_name, event], start) + ending)
    return found


def load_pieces(probe, project) -> dict:
    """Returns {the piece's name: its bytes} of each component's blocks in its
    page's load section in `probe`'s fixtures, such as page0-2-load, at its
    type's function: their numbers follow the labels before them, and a
    timer's "L " block gives where its timer event's code starts, after its
    name and its "S " block."""
    found = {}
    for name in piece_names(probe):
        matched = re.fullmatch(r"page(\d+)-(\d+)-load", name)
        if not matched:
            continue
        number, object_id = int(matched[1]), int(matched[2])
        page_object = project.pages[number].objects[object_id]
        timer_event = "page%d-%d-event-timer" % (number, object_id)
        places = ({"timer": blocks_place(probe, timer_event) + len(encode_blocks([b"timer"]))}
                  if timer_event in piece_names(probe) else {})
        found[name] = encode_blocks(object_module(page_object).load_start(
            page_object, project, place(probe, "page%d-%d" % (number, object_id)), places))
    return found
