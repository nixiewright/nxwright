"""Checks, on a real screen, whether its firmware still has the bugs that
nxwright's simulator matches on purpose
(tools/screen/matched_firmware_bugs.py).

The screen runs the project in tools/screen/project. This script sends each
check's steps over the screen's serial line, and writes a report. The report
gives each check's answer from the screen beside the answer of a screen that
has the bug, and then lists the bugs that the screen no longer shows.

Run it from nxwright's folder, with the screen's serial port:

    python -m tools.screen.firmware_bug_probe COM5

Some bugs show only in a project of another encoding. Their checks run
with `--encoding`, on the project built in that encoding:

    python -m tools.screen.firmware_bug_probe COM5 --encoding shift-jis

Before either run, the project must be on the screen. See
tools/screen/README.md for the steps.

The script creates files in `ram/`, and deletes each file it creates.
"""
import argparse
import sys

from tools.screen.matched_firmware_bugs import BUGS
from tools.screen.ram_probe import (ENCODING, add_screen_arguments, answers_of_a_screen,
                                    answers_shown)


def bugs_in(encoding: str) -> list:
    """Returns the bugs whose checks run on the project built in
    `encoding`."""
    return [bug for bug in BUGS if bug.encoding == encoding]


def bugs_no_longer_shown(bugs: list, answers: list) -> list:
    """Returns those of `bugs` that the screen no longer shows: each bug
    with a check whose answer in `answers` differs from what the check
    expects."""
    differing = {answer.check for answer in answers if answer.differs}
    return [bug for bug in bugs if differing.intersection(bug.checks)]


def summary(bugs: list, answers: list) -> str:
    """Returns one sentence that says how many of `bugs` the screen no
    longer shows, going by `answers`."""
    gone = len(bugs_no_longer_shown(bugs, answers))
    if not gone:
        return "The screen shows each of the %d bugs checked." % len(bugs)
    return "The screen no longer shows %d of the %d bugs checked." % (gone, len(bugs))


def report(bugs: list, answers: list, screen: str, encoding: str) -> str:
    """Returns the report, in Markdown. `answers` are the screen's answers
    to the checks of `bugs`. `screen` is what the screen answered to
    `connect`, which gives its model and firmware. `encoding` is the
    encoding that the checks' project was built in."""
    lines = ["# The firmware's bugs that nxwright's simulator matches, on a real screen", "",
             "The checks below are for the probe's project built in %s." % encoding, "",
             *answers_shown(answers, screen, "A screen with the bug"), "",
             summary(bugs, answers)]
    gone = bugs_no_longer_shown(bugs, answers)
    if gone:
        lines += ["", "The bugs that the screen no longer shows:", ""]
    for bug in gone:
        lines += ["- %s" % bug.what,
                  "  - nxwright's code that matches the bug: %s."
                  % ", ".join("`%s` in `%s`" % (name, path) for path, name in bug.matched_in)]
    return "\n".join(lines) + "\n"


def main(arguments: list = None) -> int:
    """Runs the probe on the port the command line gives, and writes its
    report. Returns the program's exit code: 1 if no screen answered."""
    parser = argparse.ArgumentParser(
        description="Checks, on a real screen that runs the project in tools/screen/project, "
                    "whether its firmware still has the bugs that nxwright's simulator "
                    "matches, and writes a report.")
    add_screen_arguments(parser, "firmware-bug-probe-report.md")
    parser.add_argument("--encoding", default=ENCODING,
                        choices=sorted({bug.encoding for bug in BUGS}),
                        help="run the checks for the project built in this encoding (default "
                             "%s, the project's own)" % ENCODING)
    options = parser.parse_args(arguments)
    bugs = bugs_in(options.encoding)
    answered = answers_of_a_screen("firmware_bug_probe",
                                   [check for bug in bugs for check in bug.checks], options,
                                   options.encoding)
    if answered is None:
        return 1
    screen, answers = answered
    options.report.write_text(report(bugs, answers, screen, options.encoding), encoding="utf-8")
    print("%s The report is in %s." % (summary(bugs, answers), options.report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
