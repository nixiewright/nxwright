"""The probes of the Nextion Editor's releases where a change of numbers or
layout begins, from 1.60.1 to 1.68.1, whose TFT files nxwright does not write:
each is kept as the release writes it, compared with nothing
(probe_runner.kept_from_the_editor), so that the decompiler's tests read the
numbers each release gives (decompiling/numbers.py,
ResearchNotes/tft/older-editors.md, Where each change begins).

A module for each release, such as editor_1_61_1_probes.py, gives its
probes, as `probe keep` keeps every probe of the module it is given. Each
release has one probe of program.s for each series it has: the commands and
system variables whose numbers change across the releases, and the command
just above each gap, but those the release lacks, which it refuses.

The Nextion Editor 1.60.1 opens nxwright's projects of P only when each page
has the attribute disup, which later releases dropped, so its probes of P
add it to the project nxwright built (with_disup).
"""
from pathlib import Path
import re
import shutil
import tempfile

from tools.tft.probing import frame_probes, statement_probes
from tools.tft.probing.probe_runner import Probe

# The lines of each series' probe of program.s, on T and K, on P and E, and
# on F.
_T_LINES = ("getv sys0", 'spstr "a,b",sys0,",",1', "draw 1,1,10,10,RED", "covx sys0,sys1,0,0",
            'print "hi"', "printh ff", "doevents", "setbaudz 0", "sys0=baud", "sys0=portbusy")
_P_LINES = ("getv sys0", 'spstr "a,b",sys0,",",1', "beep 100", "meup 0,1", "gets 0,0",
            "sets 1,2", "beepset 0,0", "xnum 0,0,0,0,0,0,0,0,0,0", "cuts 0,0,0,0,0,0,0",
            "cfguart sys0,1,2,3", "page 0", "repo sys0,0", 'pa_q "ni",sys0', "addt 1,0,100",
            "draw 1,1,10,10,RED", 'print "hi"', 'crcputs "abc",0', "crcrest 0+1,0xFFFF",
            "doevents", "setbaudz 0", "sys0=scache", "sys0=volume", "sys0=portbusy",
            "sys0=baud")
_F_LINES = ("beep 100", "cfgpio 0,0,0", "piccolor 0,0,0,sys0", "getv sys0",
            'spstr "a,b",sys0,",",1', 'pa_q "ni",sys0', "showqq", "draw 1,1,10,10,RED",
            'print "hi"', "doevents", "setbaudz 0", "xnum 0,0,0,0,0,0,0,0,0,0", "repo sys0,0",
            "wepo 5,0", "gets 0,0", "sets 1,2", "cuts 0,0,0,0,0,0,0", "sys0=pio0", "sys0=pwmf",
            "sys0=baud", "sys0=lowpower", "sys0=portbusy", "sys0=BLUE")
_LINES = {"T": _T_LINES, "K": _T_LINES, "P": _P_LINES, "E": _P_LINES, "F": _F_LINES}
# What each release refuses of those lines, on each series it has, by the
# command or system variable named.
_P_BEFORE_1_65 = {"getv", "beep", "meup", "gets", "sets", "beepset"}
_P_BEFORE_1_63 = _P_BEFORE_1_65 | {"xnum", "cuts", "cfguart", "scache"}
_REFUSED = {
    (1, 60, 1): {"T": {"getv", "spstr"}, "K": {"getv", "spstr"}, "P": _P_BEFORE_1_63 | {"spstr"}},
    (1, 61, 1): {"T": {"getv"}, "K": {"getv"}, "P": _P_BEFORE_1_63},
    (1, 63, 1): {"T": {"getv"}, "K": {"getv"}, "P": _P_BEFORE_1_65,
                 "F": {"beep", "cfgpio", "xnum", "cuts", "gets", "sets", "pio0", "pwmf"}},
    (1, 65, 0): {"T": set(), "K": set(), "P": set(), "F": {"beep", "cfgpio", "pio0", "pwmf"}},
    (1, 67, 1): {"F": {"cfgpio", "pio0", "pwmf"}},
    (1, 68, 1): {"F": set(), "E": set()},
}


def fixtures_of(version: tuple) -> str:
    """Returns the folder of the fixtures of the probes of the Nextion Editor
    `version`, such as editor-1-61-1, which starts each probe's name too."""
    return "editor-%d-%d-%d" % version


def program_probes(version: tuple) -> list:
    """Returns the probes of program.s of the Nextion Editor `version`, one
    for each series it has."""
    return [_kept(version, "%s-program" % series.lower(), series,
                  statement_probes.program_lines([line for line in _LINES[series]
                                                  if _named(line) not in refused]))
            for series, refused in _REFUSED[version].items()]


def layout_probes(version: tuple, projects: dict) -> list:
    """Returns the probes of the Nextion Editor `version` of the projects of
    `projects`, {series: [probe of that series to take the project of]}."""
    return [_kept(version, probe.name, series, probe.change)
            for series, probes in projects.items() for probe in probes]


def with_disup(project: Path):
    """Gives each page of the project file `project` the attribute disup, a
    byte of 0, after its drag, as the Nextion Editor 1.60.1 writes a page of
    P, and needs to open one. It goes through nxwright's dump and write, so
    that the project's stamps are written again too."""
    from nxwright.project.dumper import ProjectDumper
    from nxwright.project.project_writer import ProjectWriter
    with tempfile.TemporaryDirectory(prefix="nxwright-disup-") as work:
        dump, written = Path(work) / "dump", Path(work) / "project.HMI"
        ProjectDumper(project, dump).dump()
        for page in (dump / "pages").glob("*.txt"):
            page.write_text(_page_with_disup(page.read_text(encoding="utf-8")),
                            encoding="utf-8")
        ProjectWriter(project, dump, written).write()
        shutil.copyfile(written, project)


def _page_with_disup(text: str) -> str:
    """Returns the dump `text` of a page with disup after the drag of its
    object 0, the page itself, and the count of its attributes one more."""
    head, start, rest = text.partition("object 0 ")
    body, end, tail = rest.partition("\nobject ")
    count = int(re.search(r"marker att-(\d+)", body).group(1))
    if "\n  drag = 0\n" not in body:
        raise ValueError("the page's dump gives no drag of 0 to put disup after")
    body = body.replace("marker att-%d" % count, "marker att-%d" % (count + 1), 1)
    body = body.replace("\n  drag = 0\n", "\n  drag = 0\n  disup:u8 = 0\n", 1)
    return head + start + body + end + tail


def _kept(version: tuple, name: str, series: str, change) -> Probe:
    """Returns the probe named after `name` on `series`, which makes `change`
    to its base folder, kept as the Nextion Editor `version` writes it."""
    built_change = with_disup if version == (1, 60, 1) and series == "P" else None
    return Probe("%s-%s" % (fixtures_of(version), name), series, change, None,
                 frame_probes.editor_pieces, fixtures_of(version), built_change=built_change)


def _named(line: str) -> str:
    """Returns the command a line of program.s starts with, or the system
    variable it reads, as sys0=baud reads baud."""
    if line.startswith("sys0="):
        return line[len("sys0="):]
    return line.split(" ", 1)[0]
