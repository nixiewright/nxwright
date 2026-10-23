"""The watchdog that stops a command whose call into the Editor never returns.

A window message has a timeout of its own, but a UI Automation call has
none: one was seen to wait more than six minutes, holding the lock (found
on two Editors). So while a command runs (watched), each step that makes
progress, such as each look of a wait, tells the watchdog (progress). When
none does for QUIET_SECONDS, longer than any one wait of the tool, the
watchdog writes where each thread is to standard error, as "Timeout", then
each thread's calls, and ends the process with the code 1. Windows then
drops the lock with the process (dedicated.Lock).

Nothing is watched outside a command, so the tool's tests, which run its
functions in their own process, are never stopped.
"""
from contextlib import contextmanager
import faulthandler
import sys

# How long a command may go without progress, in seconds. Each look of a
# wait is progress, so this need only pass the longest single call between
# two looks, as a button's `exists` waits 15 s; it passes a compile's whole
# wait too (editor.COMPILING_WAIT).
QUIET_SECONDS = 300

_quiet = None   # the seconds watched for, while a command is watched


@contextmanager
def watched(quiet: float = QUIET_SECONDS):
    """Watches the command run in the `with` block: it is stopped when it
    makes no progress for `quiet` seconds. Run with no standard error, as
    by pythonw, nothing is watched, as there is nowhere to say where it was."""
    global _quiet
    _quiet = quiet if sys.__stderr__ is not None else None
    progress()
    try:
        yield
    finally:
        faulthandler.cancel_dump_traceback_later()
        _quiet = None


def progress(longer: float = 0):
    """Tells the watchdog that the command made progress, giving it its
    quiet seconds again, and `longer` more for a step known to take that
    long, as a touch's wait. Does nothing when no command is watched."""
    if _quiet is not None:
        faulthandler.dump_traceback_later(_quiet + longer, exit=True, file=sys.__stderr__)
