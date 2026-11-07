"""The numbers of the "S " blocks, and the labels and gotos of code, on the
T, K, P, E, and F series, as the Nextion Editor 1.68.2 writes them
(ResearchNotes/tft/goto-statement.md).

An "S " block is 53 20, then 03 and its number, 4 bytes. The Nextion
Editor writes one for each label in code, such as `loop:`; one at the start
of each macro (ResearchNotes/tft/macros.md); one at the start of each timer's
timer event (component_types/timer.py); and two in each scrolling text's
timer code (component_types/scrolling_text.py). A goto, such as
`goto loop`, is a "G " block: 47 20, then 03 and the place, in the user
code, of the block after its label's block. A call, such as `call m0`, is a
"J " block: 4a 20, then 03 and the place of the block after its macro's
"S " block.

One counter numbers them across the project, from 0, in the order the
Nextion Editor compiles them:

  - program.s's labels, gotos, and calls, in order. A goto and a call take
    a number too, though their blocks give a place;
  - then each macro, in the order of the project's macro tab: its "S "
    block, then its labels, gotos, and calls, in order;
  - then each page, in ID order. First, its timers and scrolling texts, in
    ID order, take the numbers of a first pass: a timer one, and a
    scrolling text three (their modules' FIRST_PASS_NUMBERS). Then its
    objects, in ID order, the page first. A timer or a scrolling text takes
    one number, its second, before its events. Then each event's labels
    and gotos take theirs, in order, the events in the order the Nextion
    Editor lists them: load, loadend, down, up, and unload for a page, and
    its type's EVENTS for a component. A call takes its number there
    too.

A timer's timer event starts with its second number. A scrolling text's
timer code starts one past its first number and ends two past it. On P and
E, a timer's timer event has no "S " block, a scrolling text has no timer
code, and neither takes numbers.

A label's number, and a goto's or a call's place, are known only once
the frame lays out the blocks. So the encoder gives a label's block as a
LabelBlock, a goto's as a GotoBlock, and a call's as a CallBlock, each of
the right size, and the frame writes them (resolved).
"""
from dataclasses import dataclass
import re

from nxwright.language.code_lines import LABEL, goto_label
from nxwright.project.page_block import Event

from nxwright.tft import component_types
from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, value_operand
from nxwright.tft.matching import code_lines
from nxwright.tft.statements import StatementError

# The start of an "S " block, of a "G " block, and of a "J " block.
S_BLOCK_START = b"S "
GOTO_START = b"G "
CALL_START = b"J "
# A call of a macro, by its name, which may hold spaces.
_CALL = re.compile(r"call[ \t]+(\S(?:.*\S)?)")
# A page's events, in the order the Nextion Editor numbers their labels.
PAGE_EVENTS = ("load", "loadend", "down", "up", "unload")
# A block's size word.
_SIZE_WORD = 4


class LabelBlock(bytes):
    """A label's block, its number not yet known: an "S " block of 0. Its
    `label` is the label's name."""

    def __new__(cls, label: str):
        block = super().__new__(cls, S_BLOCK_START + value_operand(0))
        block.label = label
        return block


class GotoBlock(bytes):
    """A goto's block, its place not yet known: a "G " block of 0. Its
    `label` is the name of the label it jumps to."""

    def __new__(cls, label: str):
        block = super().__new__(cls, GOTO_START + value_operand(0))
        block.label = label
        return block


class CallBlock(bytes):
    """A call's block, its place not yet known: a "J " block of 0. Its
    `macro` is the name of the macro it runs."""

    def __new__(cls, macro: str):
        block = super().__new__(cls, CALL_START + value_operand(0))
        block.macro = macro
        return block


def label_of(line: str):
    """Returns the name of the label the line of code `line` is, such as
    `loop` for `loop:`, or None for another line. The Nextion Editor reads
    any line of a name and a colon as one (nxwright's code_lines.LABEL)."""
    found = LABEL.fullmatch(line.strip(" \t"))
    return found.group(1) if found else None


def goto_of(line: str):
    """Returns the name of the label the line of code `line` jumps to, such
    as `loop` for `goto loop`, or None for another line."""
    return goto_label(line.strip(" \t"))


def call_of(line: str):
    """Returns the name of the macro the line of code `line` calls, such as
    `m0` for `call m0`, or None for another line."""
    found = _CALL.fullmatch(line.strip(" \t"))
    return found.group(1) if found else None


def is_numbered(line: str) -> bool:
    """Whether the line of code `line` takes a number of the counter: a
    label, a goto, or a call."""
    return label_of(line) is not None or goto_of(line) is not None or call_of(line) is not None


@dataclass
class Numbers:
    """The counter's numbers for a project. `events` gives the number of the
    first label, goto, or call of each run of code, by (page ID, object's
    name, event), program.s's by (None, None, None). `macros` gives each
    macro's "S " block's number, by its name. `timers` gives each timer's
    and scrolling text's two numbers, the first of its first pass and its
    second, by (page ID, object ID)."""
    events: dict
    timers: dict
    macros: dict


def numbers(project) -> Numbers:
    """Returns the counter's numbers for `project`, as the Nextion Editor
    numbers them. A type without a module gives no events: the frame
    refuses it. On P and E, no timer takes numbers, so `timers` is empty.

    The timers' numbers matched the Nextion Editor's in every probe
    without labels: with timers alone, up to twelve on a page and on three
    pages; with scrolling texts alone, up to twelve on a page; with both,
    up to six of each on a page; and with either on two pages."""
    events = {(None, None, None): 0}
    counter = _numbered_lines(project, project.program)
    macros = {}
    for name, lines in project.macros:
        macros[name] = counter
        counter += 1 + sum(1 for line in lines if is_numbered(line))
    timers = {}
    on_p = project.settings.model.series in SERIES_WRITTEN_AS_P
    for page_id, page in enumerate(project.pages):
        modules = [component_types.object_module(page_object) for page_object in page.objects]
        for object_id, module in enumerate(modules):
            # On P and E, neither a timer nor a scrolling text takes numbers.
            first_pass = 0 if on_p else getattr(module, "FIRST_PASS_NUMBERS", 0)
            if first_pass:
                timers[page_id, object_id] = [counter, None]
                counter += first_pass
        for object_id, (page_object, module) in enumerate(zip(page.objects, modules)):
            if (page_id, object_id) in timers:
                timers[page_id, object_id][1] = counter
                counter += 1
            name = component_types.object_name(page_object)
            names = PAGE_EVENTS if object_id == 0 else getattr(module, "EVENTS", ())
            for event in names:
                events[page_id, name, event] = counter
                counter += _numbered_lines(project, event_code(page_object, event))
    return Numbers(events, {place: tuple(pair) for place, pair in timers.items()}, macros)


def resolved(blocks: list, first: int, place: int, macros: dict = None) -> list:
    """Returns `blocks`, a run of code's blocks, which start at the place
    `place` in the user code, with each LabelBlock, GotoBlock, and CallBlock
    written: a label's of its number, a goto's of the place of the block
    after its label's, and a call's of its macro's place in `macros`, the
    place of the block after each macro's "S " block, by name. Their
    numbers start at `first`, in the blocks' order. Raises StatementError
    for a goto whose label is not among them, or a call of a macro not in
    `macros`, which nxwright's build refuses first."""
    after, at = {}, place
    for block in blocks:
        at += _SIZE_WORD + len(block)
        if isinstance(block, LabelBlock):
            after[block.label] = at
    written, number = [], first
    for block in blocks:
        if isinstance(block, LabelBlock):
            block = S_BLOCK_START + value_operand(number)
            number += 1
        elif isinstance(block, GotoBlock):
            if block.label not in after:
                raise StatementError("goto %s: no label %s in its run of code"
                                     % (block.label, block.label))
            block = GOTO_START + value_operand(after[block.label])
            number += 1
        elif isinstance(block, CallBlock):
            if block.macro not in (macros or {}):
                raise StatementError("call %s: the project has no macro %s"
                                     % (block.macro, block.macro))
            block = CALL_START + value_operand(macros[block.macro])
            number += 1
        written.append(block)
    return written


def event_code(page_object, event: str) -> bytes:
    """Returns the code of `page_object`'s event `event`, or b"" for none."""
    return next((b"\n".join(item.lines) for item in page_object.items
                 if isinstance(item, Event) and item.name == event), b"")


def _numbered_lines(project, code: bytes) -> int:
    """Returns how many of `code`'s lines take a number: its labels and
    gotos."""
    return sum(1 for line in code_lines(project, code) if is_numbered(line))
