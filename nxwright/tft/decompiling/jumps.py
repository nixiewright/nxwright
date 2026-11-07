"""The jumps in a run of code: where each block that jumps lies, and where
it lands, as the control statements (control_statements.py) and goto
(instructions/goto_statement.py, label_numbers.py) write them.

Three blocks jump:

  - a comparison's block: 09 00 04, then its two operands, its
    comparison's number, and its jump, with a comma between each two. The
    jump is 03, then 4 bytes, signed. When the comparison fails, the screen
    skips that many bytes from the block's end, or goes back that many when
    the jump is negative. Each block skipped counts with its size word;
  - a jump block, 54 20 ("T "), then 03 and a jump, counted the same way,
    which the screen always takes;
  - a goto's block, 47 20 ("G "), then 03 and the place it lands on, in the
    user code.

The undocumented command `i` is the comparison's command, so `i` with a
long last number writes the same bytes as a comparison, and is a jump too.
A call's block, "J ", is no jump here: it goes to a macro, and comes back
to the block after it.
"""
import struct

from nxwright.tft.component_types import VALUE_TAG
from nxwright.tft.control_statements import COMPARISON_HEAD, COMPARISONS, JUMP_START
from nxwright.tft.decompiling.decoded_file import CodeRun
from nxwright.tft.label_numbers import GOTO_START

# The end of a block that jumps: 03, then the jump or the place, 4 bytes.
_VALUE = bytes([VALUE_TAG])
_VALUE_SIZE = 5
# What comes before a comparison's jump: its number, between commas. Every
# series numbers comparisons as T does.
_BEFORE_THE_JUMP = frozenset(b",%d," % number for number in COMPARISONS["T"].values())
# A block's size word.
_SIZE_WORD = 4


def jump_targets(run: CodeRun) -> list:
    """Returns [(where a block of `run` that jumps lies, where it lands)],
    in the blocks' order, each counted from the user code's start, as a
    CodeRun's place is. A comparison or a jump block lands that many bytes
    from its end, and a goto on the place it gives."""
    targets = []
    for place, block in zip(run.block_places(), run.blocks):
        end = place + _SIZE_WORD + len(block)
        if _is_counted_jump(block):
            targets.append((place, end + struct.unpack("<i", block[-4:])[0]))
        elif len(block) == len(GOTO_START) + _VALUE_SIZE and block.startswith(
                GOTO_START + _VALUE):
            targets.append((place, struct.unpack("<I", block[-4:])[0]))
    return targets


def _is_counted_jump(block: bytes) -> bool:
    """Whether `block` jumps by a count of bytes from its end: a jump block,
    or a comparison's block, which ends with a comma, its comparison's
    number, a comma, then 03 and the jump."""
    if len(block) == len(JUMP_START) + _VALUE_SIZE:
        return block.startswith(JUMP_START + _VALUE)
    before = len(COMPARISON_HEAD) + len(",1,")
    return (len(block) >= before + _VALUE_SIZE and block.startswith(COMPARISON_HEAD)
            and block[-_VALUE_SIZE:-4] == _VALUE
            and block[-_VALUE_SIZE - 3:-_VALUE_SIZE] in _BEFORE_THE_JUMP)
