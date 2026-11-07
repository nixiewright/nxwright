"""Decompiling: turning a TFT file back into a source folder that nxwright
can build. Each module reverses one piece of the compile, reading the same
tables the compile writes from, so that the two cannot drift apart.

The terms the modules use:

  - the decoded file: what decoded_file.py reads from a TFT file's user
    code, in memory: its settings, its pages and their objects, its int
    variables, its macros, and each run of code, as blocks. Every other
    decoder reads it.
  - a decoder: a function that reverses one piece of the compile, such as
    a type's memory, or a run of code's blocks.
  - a run of code: the blocks of one event, of program.s, or of a macro,
    without the blocks around them, such as an event's name and its 0 word,
    with where its first block lies (decoded_file.CodeRun).
  - a name's guess: a name whose checksum is the one the file keeps. The
    name the Nextion Editor gives a new object of its type and ID, such as
    t0, is tried first. A name no guess matches gets a readable name, such
    as text3 for the text of ID 3, or int0, and is marked as unmatched.

A decoder raises DecodeError for what it cannot read, with where it lies
and its bytes, so that the decompile command can say what it could not
reproduce. A refusal of the whole file, such as of a series not decoded,
gives no place.
"""
from typing import Optional

from nxwright import NxwrightError


class DecodeError(NxwrightError):
    """A piece of a TFT file that a decoder cannot read. `place` is where it
    lies, counted from the user code's start, and `data` its bytes. Both are
    in the message too. A refusal of the whole file gives no place, and its
    message is `message` alone."""

    def __init__(self, message: str, place: Optional[int] = None, data: bytes = b""):
        super().__init__(message if place is None
                         else "%s, at 0x%x: %s" % (message, place, data.hex(" ")))
        self.place, self.data = place, data
