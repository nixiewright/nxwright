"""Testing a screen's code on a PC, without the screen.

  - SourceFolderRunner: compiles a source folder's pages and runs their events,
    or runs code against its libraries.
  - EditorMachine: runs Editor code, as the screen would. RefusedCode, and
    UnreadableLine, a kind of it, stop a run that meets code nxwright
    refuses, or a line it cannot read; ValueNotGiven, one whose code reads
    a value the run was not given.
  - simulation.py: runs a source folder's app as the screen does: program.nx,
    pages and their changes, presses, timers, and the simulation's time,
    for the simulator and the MCP server. It is internal: this package does
    not export it, and its interface may change.
  - recording.py: records a run, step by step, for the debugger.

`nxwright test <folder>` runs a folder of unittest tests written with the
classes this package exports.
"""
from nxwright.testing.editor_machine import (EditorMachine, RefusedCode, UnreadableLine,
                                             ValueNotGiven)
from nxwright.testing.source_runner import SourceFolderRunner

__all__ = ["EditorMachine", "RefusedCode", "SourceFolderRunner", "UnreadableLine",
           "ValueNotGiven"]
