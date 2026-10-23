"""The lines `simulate --send` types in the Editor's simulator's instruction
box (README.md).

The box has two modes. In String mode, the default, a line is text, and the
simulator sends its bytes, then FF FF FF, which ends an instruction. In Hex
mode (`--hex`), a line is hexadecimal bytes, such as "68 65 6C 6C 6F", and
the simulator sends exactly those bytes. Hex mode sends bytes that are not
a whole instruction, such as a transfer's data.

The lines are checked here, before the simulator starts, with nothing of
Windows' or the Editor's, so that the tests need neither.
"""

# The last line typed after an instruction. It changes nothing, and its
# answer, a number, says the instruction has run (editor.py, _send).
DONE_MARKER = "get 1"
# What ends an instruction on the serial line.
_END = b"\xff\xff\xff"


class InstructionError(Exception):
    """An instruction that is refused, saying which line and why."""


def typed_lines(instruction: str, hex_mode: bool = False) -> list:
    """Returns the lines to type for `instruction`, then DONE_MARKER. In Hex
    mode, each line is written as hexadecimal bytes, spaced in pairs, and
    the marker as its bytes, then FF FF FF. The marker follows the bytes on
    the serial line: after an unfinished instruction, or during a transfer,
    it joins them, and is not answered. Raises InstructionError for a line
    that is not hexadecimal bytes in Hex mode."""
    lines = instruction.splitlines()
    if not hex_mode:
        return lines + [DONE_MARKER]
    typed = []
    for line in lines:
        try:
            data = bytes.fromhex(line)
        except ValueError:
            data = b""
        if not data:
            raise InstructionError("%r is not hexadecimal bytes, such as 68 65 6C" % line)
        typed.append(data.hex(" ").upper())
    return typed + [(DONE_MARKER.encode("ascii") + _END).hex(" ").upper()]
