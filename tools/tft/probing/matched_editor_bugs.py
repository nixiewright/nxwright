"""The Nextion Editor's bugs that nxwright matches on purpose, each with the
probes that show it.

In strict Nextion syntax, nxwright does what the Nextion Editor does, even
where that is a bug, so that both compile a project into the same file.
Run the module's probes against each new release of the Nextion Editor, to
see whether the release fixed one of the bugs. When a probe no longer
matches, the release may have fixed its bug, and nxwright should stop
matching it. See tools/tft/README.md, Moving to a new release of the
Nextion Editor, for how to run the probes.

The module takes its probes from other modules. Its name does not end in
"_probes", so that anything reading every probe module, such as
`tools.tft.probe run --all`, skips it and finds each probe only once.
"""
from dataclasses import dataclass

from tools.tft.probing import e_probes, p_probes


@dataclass(frozen=True)
class EditorBug:
    """A bug in the Nextion Editor that nxwright matches.

    - what: what the Nextion Editor does, with an example.
    - matched_in: the code that matches the bug, which is the code to
      change once the Nextion Editor fixes the bug. Each item is a pair of
      a file's path, relative to nxwright's folder, and the name of a
      function or a constant in that file.
    - probes: the names of the probes that show the bug.
    """
    what: str
    matched_in: tuple
    probes: tuple


BUGS = [
    EditorBug(
        what="The Nextion Editor compiles the first part of a `for` only up to the parentheses "
             "of its first method call. It writes `for(sys0=fs0.close();sys0<1;sys0++)` with "
             "`sys0=fs0.close` as its first part, so the screen reads the method as an "
             "attribute and does not call it. Whatever follows the call is lost too: "
             "`sys0=fs0.open(t0.txt)+1` becomes `sys0=fs0.open`. nxlang does not have the bug, "
             "because nxwright compiles an nxlang `for` with such a call into its first part, "
             "followed by a `while` loop.",
        matched_in=(("nxwright/tft/instructions/for_statement.py", "_start_as_written"),
                    ("nxwright/testing/editor_machine.py", "_FOR_S_START_UP_TO_A_CALL")),
        probes=("p-file-stream-calls-in-a-for-s-start", "e-file-stream-calls-in-a-for-s-start")),
]

# The modules that the bugs' probes are in.
_MODULES = (p_probes, e_probes)


def _probes() -> list:
    """Returns the probes that the bugs list, in the bugs' order."""
    named = {probe.name: probe for module in _MODULES for probe in module.PROBES}
    return [named[name] for bug in BUGS for name in bug.probes]


PROBES = _probes()
