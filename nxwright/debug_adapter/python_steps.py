"""Recording the lines of a test's own Python, for the debugger.

While a test runs under the debugger, Python's line tracing (sys.settrace)
tells the recorder (testing/recording.py) of each line run in a Python file
of the folder of tests: the test's module, its setUp and tearDown, and the
helper modules beside it. Code elsewhere, such as nxwright's own and the
standard library, makes no step. Tracing slows the test, so it is on only
while the debugger runs one.

It also notes, for each exception that reaches the test's code, the step it
came from: the last step recorded when it first reached a traced function.
That is the failing assertion's line, or, for an error inside a run, the
screen statement that raised it. unittest reports a failure with its
exception, which then gives its step.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import reprlib
import sys

from nxwright.testing.recording import PythonPlace, Recorder

# How much of a value the debugger shows: its text cut short, and the first
# entries of a list, tuple, or dict.
_SHOWN = reprlib.Repr()
_SHOWN.maxstring = _SHOWN.maxother = 200
_MOST_ENTRIES = 100


class PythonTracer:
    """Traces the Python of the files in `folder` into `recorder`, while
    `tracing` lasts. `step_of(exception)` gives the index in recorder.steps
    of the step an exception came from, when it reached the traced code."""

    def __init__(self, recorder: Recorder, folder: Path):
        self.recorder = recorder
        # {id of an exception: (the exception, its step)}. Keyed by identity,
        # since an exception class may define __eq__ and so not be hashable;
        # the exception is kept, so that its id is not reused.
        self._raised = {}
        self._prefix = os.path.normcase(os.path.abspath(folder)) + os.sep
        self._traced = {}   # {file name of a code object: whether it is traced}

    @contextmanager
    def tracing(self):
        previous = sys.gettrace()
        sys.settrace(self._on_call)
        try:
            yield self
        finally:
            sys.settrace(previous)

    def step_of(self, exception):
        """Returns the index of the step `exception` came from, or None."""
        kept = self._raised.get(id(exception))
        return kept[1] if kept is not None else None

    def _is_traced(self, code) -> bool:
        name = code.co_filename
        if name not in self._traced:
            # Code with no file, such as "<string>", would otherwise resolve
            # against the current folder, which may be the folder of tests.
            self._traced[name] = not name.startswith("<") and os.path.normcase(
                os.path.abspath(name)).startswith(self._prefix)
        return self._traced[name]

    def _on_call(self, frame, event: str, argument):
        """Python's tracing calls this as each function starts; the function's
        own events go to _on_event when it is traced."""
        if not self._is_traced(frame.f_code):
            return None
        self.recorder.python_call()
        return self._on_event

    def _on_event(self, frame, event: str, argument):
        if event == "line":
            code = frame.f_code
            self.recorder.python_line(PythonPlace(code.co_filename, frame.f_lineno,
                                                  code.co_qualname,
                                                  _local_values(frame.f_locals)))
        elif event == "return":
            self.recorder.python_return()
        elif event == "exception" and self.recorder.steps:
            # Only its first arrival: the step where it started.
            self._raised.setdefault(id(argument[1]), (argument[1], len(self.recorder.steps) - 1))
        return self._on_event


def _local_values(local_values: dict) -> tuple:
    """Returns a function's locals as PythonPlace.local_values holds them."""
    return tuple((name, _text(value), _entries(value))
                 for name, value in local_values.items() if not name.startswith("__"))


def _entries(value) -> tuple:
    if isinstance(value, dict):
        items = list(value.items())[:_MOST_ENTRIES]
        return tuple((_text(key), _text(entry)) for key, entry in items)
    if isinstance(value, (list, tuple)):
        return tuple(("[%d]" % index, _text(entry))
                     for index, entry in enumerate(value[:_MOST_ENTRIES]))
    return ()


def _text(value) -> str:
    """Returns `value` as the debugger shows it, cut short."""
    try:
        return _SHOWN.repr(value)
    except Exception as error:
        # A value whose repr fails still shows, as what went wrong.
        return "<%s: %s>" % (type(error).__name__, error)
