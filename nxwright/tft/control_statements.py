"""What the control statements of instructions/ share, as the Nextion
Editor 1.68.2 writes them on the T series (ResearchNotes/tft/if-statement.md,
while-statement.md, and for-statement.md): a condition and its jumps, a
body between braces, the jump block, and a loop.

A body starts after a line holding `{` alone, and ends at the line that
closes it, which starts with `}`. Spaces and tabs may lie around a line's
parts, but not within a name or a number: `sys 0` is no `sys0`.

A condition is one comparison of two operands, or several joined by `&&`
alone or by `||` alone: the Nextion Editor refuses a condition with both.
A comparison's two operands are of one kind: two numbers, or two texts, a
text being one between double quotes or a component's txt. The Nextion
Editor refuses a text beside a number. A component's attribute reached
through the screen's arrays (statements.INDIRECT) is of no kind it knows, so
it takes one beside either.
It has a block for each comparison, in order:

  - 09 00 04, the left operand, a comma, the right one, a comma, the
    comparison's number (COMPARISONS), a comma, then 03 and a jump, 4 bytes
    little-endian and signed. When the comparison fails, the screen skips
    that many bytes, or goes back that many when the jump is negative. Each
    block skipped counts with its size word;
  - with `&&`, each comparison jumps past the rest of the condition. It
    also jumps past what the condition guards, which its statement says;
  - with `||`, each comparison but the last is inverted: its number is 7
    minus its own. It jumps past the rest of the condition, onto what the
    condition guards. The inverted comparison fails, and so jumps, when the
    comparison as written holds. The last comparison jumps past what the
    condition guards.

A jump block is 54 20, "T ", then 03 and a jump, which the screen always
takes. It jumps past the branches after an if's body, or back to a loop's
condition, a while's or a for's (loop_blocks). A jump that would land on a
jump block lands where that one does (threaded).
"""
import itertools
import re
import struct
from typing import Optional

from nxwright.tft.component_types import value_operand
from nxwright.tft.statements import (HEX_NUMBER, INDIRECT, SERIAL_BUFFER, TEXT, StatementError,
                              attribute_kind, attributes_are_numbers, encodable_operand,
                              names_its_page, operand)
from nxwright.tft.tft_file import encode_blocks

# How the Nextion Editor numbers a comparison, on T, and as T does on K, P,
# and E. Inverted, a comparison is numbered 7 minus its number: == and != are
# 1 and 6.
COMPARISONS = {"T": {"==": 1, "<": 2, ">": 3, "<=": 4, ">=": 5, "!=": 6}}
COMPARISONS["K"] = COMPARISONS["P"] = COMPARISONS["E"] = COMPARISONS["T"]
# On F as on T, as F's probes of if, while, and for showed them.
COMPARISONS["F"] = COMPARISONS["T"]
INVERTED = 7
OPENING = re.compile(r"[ \t]*\{[ \t]*")
CLOSING = re.compile(r"[ \t]*\}[ \t]*")
# A comparison: two operands, a hexadecimal number, a number, a component's
# attribute through the screen's arrays (statements.INDIRECT), a byte of the
# serial buffer (statements.SERIAL_BUFFER), a name, a component's attribute,
# or a text, as the encoder reads one (statements.TEXT), around its
# operator, the longest operator first.
_OPERAND = (r'(?:%s|-?[0-9]+|%s|%s|[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){0,2}|%s)'
            % (HEX_NUMBER, INDIRECT, SERIAL_BUFFER, TEXT))
_COMPARISON = re.compile(r"[ \t]*(?P<left>%s)[ \t]*(?P<comparison><=|>=|==|!=|<|>)[ \t]*"
                         r"(?P<right>%s)[ \t]*" % (_OPERAND, _OPERAND), re.ASCII)
# A text, or a join of two comparisons, as a condition holds them, a text
# first, so that a join inside one is left in it.
_TEXT_OR_JOIN = re.compile(r"%s|(?P<join>&&|\|\|)" % TEXT)
# What a comparison's block and a jump block start with (the module's
# docstring).
COMPARISON_HEAD = b"\x09\x00\x04"
JUMP_START = b"T "


class JumpBlock(bytes):
    """A block that ends with a jump, 03 then 4 bytes: a comparison's, or a
    jump block. Its class marks it, so that the statement around a nested
    one finds the nested one's jumps among the blocks encode_run gives back
    (threaded)."""

    @property
    def jump(self) -> int:
        return struct.unpack("<i", self[-4:])[0]

    def jumping(self, size: int) -> "JumpBlock":
        """Returns the same block, jumping `size` bytes."""
        return JumpBlock(self[:-4] + struct.pack("<i", size))


def braced_body(lines: list, at: int) -> tuple:
    """Returns the lines of the body that the `{` at lines[at] opens, the
    line that closes it, and the index after that line. Within the body, a
    `{` opens a body of its own, and a line starting with `}` closes one.
    Raises StatementError when lines[at] is no `{`, or the body is not
    closed."""
    if at >= len(lines) or not OPENING.fullmatch(lines[at]):
        raise StatementError("%r: no { on the line after it" % lines[at - 1])
    body, depth = [], 0
    for number in range(at + 1, len(lines)):
        line = lines[number]
        if line.strip(" \t").startswith("}"):
            if depth == 0:
                return body, line, number + 1
            # `}else` closes a body within, and the `{` after it opens one.
            depth -= 1
        elif OPENING.fullmatch(line):
            depth += 1
        body.append(line)
    raise StatementError("a body has no } to close it")


def condition_blocks(condition: str, guarded: int, place, context, series: str) -> list:
    """Returns the blocks of `condition`, whose comparisons jump past
    `guarded` bytes, after the rest of the condition, when it fails.
    `context` is the compile's CompileContext."""
    comparisons, joined = _comparisons(condition)
    parts = []
    for number, (left, comparison, right) in enumerate(comparisons):
        code = COMPARISONS[series][comparison]
        if joined == "||" and number < len(comparisons) - 1:
            code = INVERTED - code
        parts.append((_side(left, place, context), code, _side(right, place, context)))
    sizes = [size_of([comparison_block(*part, 0)]) for part in parts]
    blocks = []
    for number, part in enumerate(parts):
        after = sum(sizes[number + 1:])
        last = number == len(parts) - 1
        blocks.append(comparison_block(*part, after if joined == "||" and not last
                                       else after + guarded))
    return blocks


def _side(text: str, place, context) -> bytes:
    """Returns the bytes of a comparison's operand `text`: a text as it is,
    its quotes included, in the project's encoding, as the encoder writes
    one in any line, or else the operand statements.operand gives."""
    if text.startswith('"'):
        return context.project.codec.encode_keeping_bytes(text, text)
    return operand(text, place, context)


def comparison_block(left: bytes, code: int, right: bytes, jump: int) -> JumpBlock:
    """Returns a comparison's block: 09 00 04, the operands `left` and
    `right`, already encoded, around the comparison's number `code`, then a
    jump of `jump` bytes when the comparison fails."""
    return JumpBlock(COMPARISON_HEAD + left + b"," + right + b"," + str(code).encode("ascii")
                     + b"," + value_operand(jump))


def covers_condition(condition: str, need=None) -> bool:
    """Whether `condition` is of a shape the encoder writes: one or more
    comparisons, joined by && alone or || alone, each of two operands of one
    kind (_operand_kind): two numbers, or two texts, or a reference through
    the screen's arrays beside either. A comparison of any length is taken:
    the Nextion Editor refuses one whose line is too long, but nxwright's
    build refuses it first (ResearchNotes/tft/if-statement.md). An attribute
    among them must be one the encoder encodes in the line of code `need`,
    so with `need` None, none may be."""
    try:
        comparisons = _comparisons(condition)[0]
    except StatementError:
        return False
    kinds = [(_operand_kind(left, need), _operand_kind(right, need))
             for left, _, right in comparisons]
    return all(
        None not in pair and (pair[0] == pair[1] or "any" in pair) for pair in kinds)


def _operand_kind(text: str, need) -> Optional[str]:
    """Returns how the encoder encodes a comparison's operand `text` in the
    line of code `need`: "text" for a text or a txt, "number" for a number,
    a hexadecimal number, a name, or an attribute encoded as a number
    (statements.attribute_kind), "any" for a reference through the screen's
    arrays (statements.INDIRECT), or None for one it does not encode. A
    reference's indexes may name the page's attributes as numbers alone,
    and in program.s or a macro, which have no page, it must name its page,
    as `p[i].b[j]` or `page1.b[i]` (statements.names_its_page)."""
    if text.startswith('"'):
        return "text"
    if re.fullmatch(INDIRECT, text) is not None:
        without_a_page = need is not None and need.subject != "event"
        return ("any" if attributes_are_numbers(need, text)
                and not (without_a_page and not names_its_page(text)) else None)
    if "." in text:
        return None if need is None else attribute_kind(need, text)
    return "number" if encodable_operand(text) else None


def jump_block(size: int) -> JumpBlock:
    """Returns the jump block that jumps `size` bytes."""
    return JumpBlock(JUMP_START + value_operand(size))


def loop_blocks(condition: str, body: list, place, context, series: str) -> list:
    """Returns the blocks of a loop: `condition`'s, which guard `body` and
    the jump back; the blocks of `body`; then a jump block back to the
    condition's first comparison."""
    # The jump back is as long whatever it jumps, so its size is known first.
    guarded = size_of(body + [jump_block(0)])
    head = condition_blocks(condition, guarded, place, context, series)
    return head + body + [jump_block(-(size_of(head) + guarded))]


def threaded(blocks: list) -> list:
    """Returns a statement's `blocks` with each jump that lands on a jump
    block sent on to where that one lands, as the Nextion Editor writes it.
    A jump lands on one when a nested statement ends a body, before a jump
    block of the statement around it, or when `||` comes before an empty
    body."""
    ends = list(itertools.accumulate(size_of([block]) for block in blocks))
    onward = {end - size_of([block]): end + block.jump for block, end in zip(blocks, ends)
              if isinstance(block, JumpBlock) and block.startswith(JUMP_START)}
    sent = []
    for block, end in zip(blocks, ends):
        if isinstance(block, JumpBlock):
            landing = end + block.jump
            # The chain ends: a jump block goes on forward, or back to a
            # condition's first comparison, which is no jump block.
            while landing in onward:
                landing = onward[landing]
            block = block.jumping(landing - end)
        sent.append(block)
    return sent


def size_of(blocks: list) -> int:
    """Returns the bytes `blocks` take, each with its size word."""
    return len(encode_blocks(blocks))


def _comparisons(condition: str) -> tuple:
    """Returns the comparisons of `condition`, [(left, comparison, right)],
    and how they are joined, "&&", "||", or None for one. Raises
    StatementError for a condition of another shape."""
    # The Nextion Editor joins comparisons at && and || outside the texts:
    # `t0.txt=="a&&b"` is one comparison.
    pieces, joins, at = [], set(), 0
    for found in _TEXT_OR_JOIN.finditer(condition):
        if found.group("join"):
            pieces.append(condition[at:found.start()])
            joins.add(found.group("join"))
            at = found.end()
    pieces.append(condition[at:])
    if len(joins) > 1:
        raise StatementError("%r: the Nextion Editor refuses a condition with both && and ||"
                             % condition)
    joined = joins.pop() if joins else None
    comparisons = []
    for text in pieces:
        found = _COMPARISON.fullmatch(text)
        if found is None:
            raise StatementError("%r is no comparison of two operands" % text)
        left, right = found.group("left"), found.group("right")
        # The Nextion Editor refused a text whose last escape is `\\`, right
        # before its closing quote, as in `t0.txt=="a\\"`. It compiled the
        # escapes elsewhere in a condition's texts.
        if any(side.startswith('"') and side.endswith('\\"') for side in (left, right)):
            raise StatementError("%r: the Nextion Editor refuses a text that ends with the "
                                 "escape \\\\ in a condition (\"SYNTAX ERROR\")" % text)
        # A text beside a number or a name is refused from the line alone. A
        # txt beside a val needs the components' types, which the rules
        # check (covers_condition).
        if (left.startswith('"') != right.startswith('"')
                and not any("." in side and not side.startswith('"') for side in (left, right))):
            raise StatementError("%r is no comparison of two operands of one kind: the Nextion "
                                 "Editor refuses a text beside a number (\"Variable type does not "
                                 "match\")" % text)
        comparisons.append((left, found.group("comparison"), right))
    return comparisons, joined
