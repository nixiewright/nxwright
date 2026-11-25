"""The rejection probes: one for each line of code that nxwright's build
rejects only because the Nextion Editor rejects it. Each probe matches while
the Nextion Editor still rejects its line with the error that the probe
expects (Probe.rejected_with). See matched_editor_bugs.py for the bug behind
each probe.

nxwright's build cannot write a project that has one of these lines. Each
probe therefore builds its project with a line that nxwright accepts, then
replaces that line with the rejected one in the built project file
(Probe.built_change).

The module's name does not end in "_probes", so that anything reading every
probe module, such as `tools.tft.probe run --all`, skips it: these probes
do not compare anything with nxwright's compile. To run them, run
matched_editor_bugs, which lists them with its other probes.
"""
from dataclasses import dataclass
from pathlib import Path

from nxwright.project.device_settings import TextCodec

from tools.tft.probing.encoding_probes import in_encoding
from tools.tft.probing.probe_runner import Probe, ProbeError, change_built_pages
from tools.tft.probing.statement_probes import beside_a_text_and_numbers


@dataclass(frozen=True)
class RejectedLine:
    """A line of code that the Nextion Editor rejects, on the T series.

    - name: the name of the line's probe.
    - encoding: the project's encoding.
    - builds: the lines that nxwright builds into page0's Touch Release
      event, beside the text t0. The rejected line takes the place of the
      first of them.
    - rejected: the line that the Nextion Editor rejects.
    - error: the words of the Nextion Editor's error that say which error it
      is.
    """
    name: str
    encoding: str
    builds: tuple
    rejected: str
    error: str


_CONDITION = ('if(t0.txt=="a")', "{", "}")

LINES = [
    # ｱ is a half-width katakana, which is a single byte.
    RejectedLine("rejection-half-width-katakana-before-the-closing-quote", "shift-jis",
                 ('t0.txt="a"',), 't0.txt="aｱ"', "Invalid Variables"),
    # 表 ends in the byte 0x5C, the code of a backslash.
    RejectedLine("rejection-text-ending-in-0x5c-in-a-condition", "shift-jis", _CONDITION,
                 'if(t0.txt=="表")', "Invalid number of arguments"),
    RejectedLine("rejection-escaped-backslash-ending-a-text-in-a-condition", "iso-8859-1",
                 _CONDITION, 'if(t0.txt=="a\\\\")', "SYNTAX ERROR"),
]


def _probe(line: RejectedLine) -> Probe:
    """Returns the rejection probe of `line`."""
    stored = TextCodec(line.encoding).encode(line.rejected, "the rejected line")

    def with_the_rejected_line(project: Path):
        change_built_pages(project, lambda page: _with_line(page, line.builds[0], stored))
    return Probe(line.name, "T", in_encoding(line.encoding, beside_a_text_and_numbers(
        list(line.builds))), None, None, built_change=with_the_rejected_line,
        rejected_with=line.error)


def _with_line(page: str, builds: str, stored: bytes) -> str:
    """Returns `page`, the text of a page's dump, with the code line `builds`
    replaced by the bytes `stored`. Raises ProbeError unless the dump has
    that line exactly once."""
    # A dump gives a code line of printable ASCII after "| ", and any line
    # as its bytes in hexadecimal after "raw ".
    written = "\n    | %s\n" % builds
    if page.count(written) != 1:
        raise ProbeError("the page's dump does not have the line %s exactly once" % builds)
    return page.replace(written, "\n    raw %s\n" % stored.hex())


PROBES = [_probe(line) for line in LINES]
