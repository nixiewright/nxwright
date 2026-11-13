"""Checks, on a real screen, the rules nxwright took from the Nextion
Editor's simulator for files in `ram/`, for the SD cards' names, and for a
data record or a file browser whose path is in `ram/`.

The screen runs the project in tools/screen/project. This script sends each
check's steps over the screen's serial line, reads what the screen answers,
and writes a report. For each check, the report gives the screen's answer
beside the answer of the Nextion Editor's simulator, and says whether they
differ. A few checks have no answer from the Nextion Editor's simulator,
because it does not take data for `twfile`, so the report gives the screen's
answer alone for those checks.

Run it from nxwright's folder, with the screen's serial port:

    python -m tools.screen.ram_probe COM5

tools/screen/README.md gives the steps before that.

The script creates files in `ram/`, and files on the SD card whose names
start with `nxprobe`. It deletes each file it creates, and does not change
any other file.
"""
import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

from PIL import Image

from nxwright.project.media_files import CARD_PICTURE_QUALITIES, card_picture_file
from nxwright.testing.file_packets import packets

# The three bytes that end an instruction, and each answer of the screen.
END = b"\xff\xff\xff"
# What the screen answers to an instruction it ignores, and at the start
# and the end of a `twfile` transfer.
IGNORED = b"\x06" + END
READY = b"\xfe" + END
FINISHED = b"\xfd" + END
# The bytes the probe's project sets aside for `ram/` files, unless it is
# built with none to run the checks of NO_SPACE_CHECKS.
SPACE = 4096
# After a file's packets, how many more times the probe waits for the
# screen to answer that it has stored the file (_answer_to). Each wait
# ends when the screen has been quiet for the time given as `quiet`
# (SerialExchange).
MOST_WAITS = 10


def number(value: int) -> bytes:
    """Returns the screen's answer to a `get` of a number."""
    return b"\x71" + value.to_bytes(4, "little") + END


def red_square() -> bytes:
    """Returns a red square, 100 pixels wide, as a .xi file small enough
    for `ram/`. The probe sends a .xi file because it is the only kind that
    both an Intelligent screen and an Edge screen showed
    (nxwright/testing/external_pictures.py)."""
    return card_picture_file(Image.new("RGBA", (100, 100), (255, 0, 0, 255)),
                             CARD_PICTURE_QUALITIES["very-high"], 0)


@dataclass(frozen=True)
class Check:
    """One check: a rule, the steps that test it, and the answer the
    Nextion Editor's simulator gave.

    `steps` are sent in order. A text is an instruction, sent with the
    three bytes that end it. Bytes are the file of the `twfile` before
    them, sent in packets, because a screen takes the file only in
    packets (nxwright/testing/file_packets.py).

    `simulator` is everything the Nextion Editor's simulator sent for the
    steps, or None if it could not run them.

    `question` is asked of the person at the screen, once the steps have
    run, for a rule that only eyes can check. `then` are steps sent after
    the question, to put the screen back."""
    rule: str
    steps: tuple
    simulator: bytes | None = None
    question: str = ""
    then: tuple = ()


PICTURE = red_square()

# The checks for a project that sets SPACE bytes aside. Each one deletes the
# files it creates. Some checks also send a `delfile` for a file that the
# screen is expected not to create. The screen does not answer a `delfile`
# of a file that does not exist, in `ram/` or on a card, so the extra
# `delfile` does not change what the check compares.
CHECKS = (
    Check("newfile creates a file in ram/, and rdfile sends its size",
          ('newfile "ram/a.bin",8', 'findfile "ram/a.bin",sys0', "get sys0",
           'rdfile "ram/a.bin",0,0,0', 'delfile "ram/a.bin"'),
          number(1) + b"\x08\x00\x00\x00"),
    Check("A single file can have 3812 bytes at most, 284 fewer than the space",
          ('newfile "ram/a.bin",3812', 'findfile "ram/a.bin",sys0', "get sys0",
           'delfile "ram/a.bin"', 'newfile "ram/a.bin",3813', 'findfile "ram/a.bin",sys0',
           "get sys0", 'delfile "ram/a.bin"'),
          number(1) + IGNORED + number(0)),
    Check("A second file uses 268 bytes on top of its own size",
          ('newfile "ram/a.bin",1', 'newfile "ram/b.bin",3543', 'findfile "ram/b.bin",sys0',
           "get sys0", 'delfile "ram/b.bin"', 'newfile "ram/b.bin",3544',
           'findfile "ram/b.bin",sys0', "get sys0", 'delfile "ram/b.bin"',
           'delfile "ram/a.bin"'),
          number(1) + IGNORED + number(0)),
    Check("A newfile that does not fit deletes the file that was there",
          ('newfile "ram/a.bin",3', 'newfile "ram/a.bin",3813', 'rdfile "ram/a.bin",0,0,0',
           'delfile "ram/a.bin"'),
          IGNORED + IGNORED),
    Check("twfile needs room for its file beside the file it replaces",
          ('newfile "ram/a.bin",1773', 'twfile "ram/a.bin",1773', 'delfile "ram/a.bin"'),
          IGNORED),
    Check("RAM/ in upper case is not ram/",
          ('newfile "RAM/a.bin",8',),
          IGNORED),
    Check("ram/ has no folders",
          ('newdir "ram/d/"', 'newfile "ram/d/a.bin",8'),
          IGNORED + IGNORED),
    Check("refile does not move a file from ram/ to the SD card",
          ('newfile "ram/a.bin",8', 'refile "ram/a.bin","sd0/nxprobe.bin"',
           'delfile "ram/a.bin"', 'delfile "sd0/nxprobe.bin"'),
          IGNORED),
    Check("twfile writes its data to a file in ram/",
          ('twfile "ram/t.txt",5', b"HELLO", 'rdfile "ram/t.txt",0,0,0',
           'rdfile "ram/t.txt",0,5,0', 'delfile "ram/t.txt"')),
    Check("What twfile leaves of a larger file it replaces",
          ('newfile "ram/a.bin",8', 'twfile "ram/a.bin",5', b"HELLO",
           'rdfile "ram/a.bin",0,0,0', 'delfile "ram/a.bin"')),
    Check("The screen has an SD card, which the next checks need",
          ('newfile "sd0/nxprobe.bin",8', 'findfile "sd0/nxprobe.bin",sys0', "get sys0",
           'delfile "sd0/nxprobe.bin"'),
          number(1)),
    Check("SD0/ in upper case is not the SD card",
          ('newfile "SD0/nxprobe.bin",8', 'findfile "sd0/nxprobe.bin",sys0', "get sys0",
           'delfile "sd0/nxprobe.bin"'),
          IGNORED + number(0)),
    Check("A data record creates its file in ram/, and the file uses up space in ram/",
          ('d0.path="ram/d.data"', 'findfile "ram/d.data",sys0', "get sys0",
           'newfile "ram/z.bin",984', 'findfile "ram/z.bin",sys0', "get sys0",
           'delfile "ram/z.bin"', 'newfile "ram/z.bin",985', 'delfile "ram/z.bin"',
           'd0.path=""', 'delfile "ram/d.data"'),
          number(1) + number(1) + IGNORED),
    Check("A data record does not create a file that does not fit in ram/",
          ('d1.path="ram/big.data"', 'findfile "ram/big.data",sys0', "get sys0",
           "get d1.qty"),
          IGNORED + number(0) + number(0),
          question='Does the lower table show "File Lost:" and "ram/big.data", in white '
                   "on black?",
          then=('d1.path=""',)),
    Check("A data record whose mode is 0 does not create a file in ram/, and the screen "
          "does not send an error code",
          ("d0.mode=0", 'd0.path="ram/m.data"'),
          b"",
          question='Does the upper table show "File Lost:" and "ram/m.data", in white on '
                   "black?",
          then=('d0.path=""', "d0.mode=1")),
    Check("Setting a data record's path creates its file on the SD card at once",
          ('d0.path="sd0/nxprobe.data"', 'findfile "sd0/nxprobe.data",sys0', "get sys0",
           'd0.path=""', 'delfile "sd0/nxprobe.data"'),
          number(1)),
    Check("A file browser lists nothing in ram/",
          ('newfile "ram/a.bin",8', 'f0.dir="ram/"', "get f0.qty", 'f0.dir="sd0/"',
           'delfile "ram/a.bin"'),
          number(0)),
    Check("An external picture shows a picture that twfile put in ram/",
          ('twfile "ram/p.xi",%d' % len(PICTURE), PICTURE, 'p0.path="ram/p.xi"'),
          question="Does the screen show a red square at its top right?",
          then=('p0.path=""', 'delfile "ram/p.xi"')),
    Check("An external picture whose file is missing answers 0x06, in ram/ and on the SD card",
          ('p0.path="ram/none.png"', 'p0.path="sd0/nxprobe-none.png"'),
          IGNORED + IGNORED,
          then=('p0.path=""',)),
    Check("An external picture whose file is not a picture does not send an error "
          "code",
          ('newfile "ram/bad.png",8', 'p0.path="ram/bad.png"'),
          b"",
          question="Does the screen show anything at its top right, such as an error "
                   "message?",
          then=('p0.path=""', 'delfile "ram/bad.png"')),
    Check("rdfile and delfile are ignored on a file that a data record keeps",
          ('d0.path="ram/k.data"', 'rdfile "ram/k.data",0,0,0', 'delfile "ram/k.data"',
           'findfile "ram/k.data",sys0', "get sys0", 'd0.path=""', 'delfile "ram/k.data"'),
          IGNORED + IGNORED + number(1)),
)

# The checks for the same project built with no space set aside.
NO_SPACE_CHECKS = (
    Check("With no space set aside, newfile does not create a file in ram/",
          ('newfile "ram/a.bin",8', 'findfile "ram/a.bin",sys0', "get sys0"),
          IGNORED + number(0)),
    Check("With no space set aside, twfile does not start a transfer to ram/",
          ('twfile "ram/a.bin",8',),
          IGNORED),
    Check("With no space set aside, a data record does not create a file in ram/",
          ('d0.path="ram/d.data"', 'findfile "ram/d.data",sys0', "get sys0", 'd0.path=""'),
          IGNORED + number(0)),
)


@dataclass(frozen=True)
class Answer:
    """What the screen did for a check: everything it sent for the check's
    steps, and what the person at the screen answered to the check's
    question, True or False, or None for a check that asks nothing."""
    check: Check
    sent: bytes
    seen: bool | None = None

    @property
    def differs(self) -> bool:
        """Whether the screen differs from the Nextion Editor's simulator:
        the screen sent other bytes, or the person at the screen answered
        no. The bytes are not compared for a check that the Nextion
        Editor's simulator could not run."""
        return self.seen is False or (self.check.simulator is not None
                                      and self.sent != self.check.simulator)


def run_checks(checks, exchange, ask) -> list:
    """Runs `checks` on a screen, and returns an Answer for each.

    `exchange(data)` sends bytes to the screen and returns the bytes the
    screen answers. `ask(question)` puts a question to the person at the
    screen, and returns True for yes."""
    # With `bkcmd=2`, the screen sends a return code only for an instruction
    # it ignores. The answers of the Nextion Editor's simulator were recorded
    # with the same setting. The answer to this line itself is discarded.
    exchange(b"bkcmd=2" + END)
    answers = []
    for check in checks:
        sent = b"".join(_answer_to(step, exchange) for step in check.steps)
        seen = ask(check.question) if check.question else None
        for step in check.then:
            _answer_to(step, exchange)
        answers.append(Answer(check, sent, seen))
    return answers


def _answer_to(step, exchange) -> bytes:
    """Sends a check's step, and returns what the screen answers.

    After a file's packets, the screen answers only once it has stored the
    file. A real NX8048P070 took longer than half a second to store 1737
    bytes, and garbled the instruction that arrived in the meantime. For a
    file, _answer_to therefore keeps waiting until the screen answers that
    the transfer has finished, or until it has waited MOST_WAITS more
    times."""
    answer = exchange(_bytes_of(step))
    if isinstance(step, bytes):
        waits = 0
        while not answer.endswith(FINISHED) and waits < MOST_WAITS:
            answer += exchange(b"")
            waits += 1
    return answer


def _bytes_of(step) -> bytes:
    """Returns what is sent for a check's step: an instruction with the
    bytes that end it, or a file's bytes as packets. Every file of the
    checks fits in one packet, so the screen does not answer until the
    file is complete."""
    if isinstance(step, bytes):
        return b"".join(packets(step))
    return step.encode("latin-1") + END


def report(answers: list, screen: str) -> str:
    """Returns the report of `answers`, in Markdown. `screen` is what the
    screen answered to `connect`, which gives its model and firmware."""
    lines = ["# Files in `ram/` and card names on a real screen", "",
             "The screen answered `connect` with: `%s`" % screen, "",
             "| Check | Sent | The Nextion Editor's simulator | The screen | Differs |",
             "| --- | --- | --- | --- | --- |"]
    for answer in answers:
        check = answer.check
        simulator = "not run" if check.simulator is None else _shown(check.simulator)
        screen_did = _shown(answer.sent)
        if check.question:
            screen_did += "<br>%s %s" % (check.question, "Yes." if answer.seen else "No.")
        lines.append("| %s | %s | %s | %s | %s |" % (
            check.rule, "<br>".join(_step_shown(step) for step in check.steps + check.then),
            simulator, screen_did, "**yes**" if answer.differs else "no"))
    differing = sum(answer.differs for answer in answers)
    lines += ["", "The screen differs from the Nextion Editor's simulator on %d of %d checks."
              % (differing, len(answers)), ""]
    return "\n".join(lines)


def _shown(data: bytes) -> str:
    """Returns bytes as the report shows them: in hexadecimal, or "nothing"."""
    return "`%s`" % data.hex(" ").upper() if data else "nothing"


def _step_shown(step) -> str:
    """Returns a check's step as the report shows it. Data longer than 16
    bytes is given by its length."""
    if isinstance(step, str):
        return "`%s`" % step
    return _shown(step) if len(step) <= 16 else "%d bytes of data" % len(step)


class SerialExchange:
    """Sends bytes to a screen on a serial port, and reads its answers."""

    def __init__(self, port: str, baud: int, quiet: float):
        import serial   # pyserial, needed only with a real screen
        self._serial = serial.Serial(port, baud, timeout=quiet)

    def __call__(self, data: bytes) -> bytes:
        """Sends `data`, and returns what the screen sends until it has
        been quiet for the time given as `quiet`."""
        self._serial.write(data)
        answer = b""
        while True:
            more = self._serial.read(256)
            if not more:
                return answer
            answer += more

    def close(self):
        self._serial.close()


def _ask_at_the_terminal(question: str) -> bool:
    """Asks `question` at the terminal, and returns True for yes."""
    return input("%s [y/n] " % question).strip().lower().startswith("y")


def main(arguments: list = None) -> int:
    """Runs the probe on the port the command line gives, and writes its
    report. Returns the program's exit code: 1 if no screen answered."""
    parser = argparse.ArgumentParser(
        description="Checks nxwright's rules for ram/ files on a real screen that runs the "
                    "project in tools/screen/project, and writes a report.")
    parser.add_argument("port", help="the screen's serial port, such as COM5 or /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=9600,
                        help="the serial line's rate (default 9600, the project's)")
    parser.add_argument("--no-space", action="store_true",
                        help="run the checks for the project built with "
                             "memory_file_storage_size = 0")
    parser.add_argument("--quiet", type=float, default=0.5,
                        help="how long the screen must stay silent, in seconds, before an "
                             "answer counts as complete (default 0.5)")
    parser.add_argument("--report", type=Path, default=Path("ram-probe-report.md"),
                        help="the report to write (default ram-probe-report.md)")
    options = parser.parse_args(arguments)
    exchange = SerialExchange(options.port, options.baud, options.quiet)
    try:
        screen = exchange(b"connect" + END).rstrip(b"\xff").decode("latin-1")
        if not screen.startswith("comok"):
            print("ram_probe: no screen answered on %s at %d baud."
                  % (options.port, options.baud),
                  file=sys.stderr)
            return 1
        answers = run_checks(NO_SPACE_CHECKS if options.no_space else CHECKS, exchange,
                             _ask_at_the_terminal)
    finally:
        exchange.close()
    options.report.write_text(report(answers, screen), encoding="utf-8")
    print("The screen differs from the Nextion Editor's simulator on %d of %d checks. The "
          "report is in %s."
          % (sum(answer.differs for answer in answers), len(answers), options.report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
