"""The bridge joins the MCU port to a real screen's port, so that a program at
the MCU's end talks to the real screen through the computer, and the log
shows both sides. Both ports are SerialLinks from serial_port.py. The
simulation can receive the MCU's bytes as well (adapter.py), and can answer
the MCU in the screen's place. What the screen sends then goes only to the
log (set_screen_answers).

What arrives on either port is written whole, and in order, to the other.
If the other port does not take a write in time, the bridge ends rather
than drop bytes.

The bridge also changes both ports' rate when the screen changes its own
(ResearchNotes/serial-line.md, A real screen's rate):
  - After `baud=` or `bauds=` from the MCU, the screen answers at the old
    rate, if `bkcmd` makes it answer, and then reads bytes at the new rate.
    The bridge passes that answer on, then sets both ports to the new rate.
    If no answer comes, it sets them after the vendor's pause for the old
    rate.
  - After `rest`, the screen runs at its `bauds` rate. The bridge sets both
    ports to that rate once the screen sends anything, or after the same
    pause. When the bridge starts, it asks the screen `get bauds`, so that
    it knows `bauds` before the MCU sets it.
  - Setting the computer's rate puts stray bytes on the screen's line, and
    the screen would read them as the start of the MCU's next instruction.
    The bridge then sends the screen a bare FF FF FF, which ends them.
The screen's answers to the bridge's own instructions do not go to the
MCU, because the MCU did not ask for them. The log has a note
for each of these instructions and answers.
"""
import re
import threading

from nxwright.debug_adapter.serial_port import REPLY_LENGTHS, RATES, piece_end
from nxwright.testing.simulation_log import END, hex_bytes
from nxwright.tft.upload import pause

# How long a write to either port may wait for the port to take all its
# bytes, in seconds, before the bridge ends.
WRITE_WAIT = 1.0
# The instructions that change the screen's rate: `baud=` sets the rate it
# runs at, and `bauds=` that rate and the one it starts at.
_RATE_SETTING = re.compile(rb"(bauds?)=(\d+)")
# The most the bridge keeps of the MCU's bytes since its last FF FF FF.
# The limit stops data that has no FF FF FF, such as a file transfer's, from
# piling up. It is enough for the longest instruction the bridge watches for,
# `bauds=921600`, with room to spare.
_INSTRUCTION_KEPT = 32


class Bridge:
    """Joins `mcu` and `screen`, two connected SerialLinks. Their reading
    threads hand what arrives to `from_mcu` and `from_screen`. `note(line)`
    logs what the bridge itself does, and `ended(why)` is called once if the
    bridge ends on its own, for example when a port does not take a write in
    time. `screen_answers`, true by default, sets whether what the screen
    sends reaches the MCU (set_screen_answers)."""

    def __init__(self, mcu, screen, note, ended, screen_answers: bool = True):
        self._mcu, self._screen = mcu, screen
        self._note, self._ended = note, ended
        self._lock = threading.Lock()
        self._screen_answers = screen_answers
        # Held while the bridge writes the screen's bytes to the MCU, so that
        # newer bytes cannot overtake the ones it held back.
        self._to_mcu = threading.Lock()
        self._over = False
        self._instruction = b""      # the MCU's bytes since its last FF FF FF
        self._bauds = None           # the rate the screen starts at, once known
        # The rate both ports change to, once the screen has answered or the
        # pause has passed, and the timer of that pause.
        self._next_rate = None
        self._switch_timer = None
        # While the bridge waits for the screen's answer to an instruction of
        # its own, it holds back what the screen sends. `_keeping` tests
        # whether a piece is that answer, and says what to do with it.
        # `_held` contains the bytes held back, and `_keep_timer` ends the
        # wait.
        self._keeping = None         # (is_answer(piece), took(piece)), or None
        self._held = b""
        self._keep_timer = None

    def start(self):
        """Asks the screen the rate it starts at, and does not pass the
        answer on to the MCU."""
        self._keep(_is_number, self._learn_bauds, pause(self._rate()) * 3)
        self._to_screen(b"get bauds" + END, "get bauds", "to learn the rate it starts at")

    def stop(self):
        """Ends the bridge: what it holds is dropped, and nothing more passes."""
        with self._lock:
            self._over = True
            self._stop_timers()
            self._held = b""

    def set_screen_answers(self, screen_answers: bool):
        """Sets whether what the screen sends reaches the MCU. If it does not,
        the screen's bytes go only to the log. After a rate change from the
        MCU, the bridge then switches both ports once the vendor's pause has
        passed, without waiting for the screen's answer, so that the
        simulation's answer reaches the MCU at the old rate first."""
        with self._lock:
            self._screen_answers = screen_answers

    def start_screen_again(self) -> bool:
        """Sends the screen `rest`, then sets both ports to the rate in
        `bauds`, the same as after a `rest` from the MCU. The MCU then
        receives the screen's start-up bytes, the same as after a power
        cycle. Returns whether `rest` was sent."""
        if self._over or not self._write(self._screen, b"rest" + END):
            return False
        self._watch(b"rest")
        return True

    def from_mcu(self, data: bytes):
        """Passes what arrived from the MCU to the screen, and watches it for
        an instruction that changes the screen's rate."""
        if self._over or not self._write(self._screen, data):
            return
        with self._lock:
            self._instruction += data
            instructions = []
            while (end := self._instruction.find(END)) >= 0:
                instructions.append(self._instruction[:end])
                self._instruction = self._instruction[end + len(END):]
            self._instruction = self._instruction[-_INSTRUCTION_KEPT:]
        for instruction in instructions:
            self._watch(instruction)

    def from_screen(self, data: bytes):
        """Passes what arrived from the screen on to the MCU, except the
        answer to an instruction the bridge sent itself. Once the screen's
        answer to a rate change has been passed on, both ports switch to the
        new rate."""
        with self._to_mcu:
            with self._lock:
                if self._over:
                    return
                if self._keeping is not None:
                    data = self._take_kept(data)
                switching = (self._screen_answers and self._next_rate is not None
                             and bool(data))
            problem = self._pass_on(data)
        # Ending the bridge closes both ports, which waits for their reading
        # threads to stop. One of those threads may be waiting for the lock,
        # so the bridge ends outside it.
        if problem:
            self._end(problem)
        elif switching:
            self._switch()

    def _watch(self, instruction: bytes):
        """Notes an instruction from the MCU that changes the screen's rate,
        so that both ports change with it."""
        setting = _RATE_SETTING.fullmatch(instruction.strip())
        if setting is not None and int(setting[2]) in RATES:
            rate = int(setting[2])
            if setting[1] == b"bauds":
                with self._lock:
                    self._bauds = rate
            self._switch_after(rate)
        elif instruction.strip() == b"rest":
            with self._lock:
                bauds = self._bauds
            if bauds is None:
                self._note("bridge: the screen's bauds is not known, so the ports keep their "
                           "rate after rest")
            else:
                self._switch_after(bauds)

    def _switch_after(self, rate: int):
        """Sets both ports to `rate` once the screen answers, or after the
        vendor's pause for the current rate."""
        with self._lock:
            if self._over:
                return
            self._next_rate = rate
            if self._switch_timer is not None:
                self._switch_timer.cancel()
            self._switch_timer = threading.Timer(pause(self._rate()), self._switch)
            self._switch_timer.daemon = True
            self._switch_timer.start()

    def _switch(self):
        with self._lock:
            rate, self._next_rate = self._next_rate, None
            if self._switch_timer is not None:
                self._switch_timer.cancel()
                self._switch_timer = None
            if rate is None or self._over:
                return
        for link in (self._mcu, self._screen):
            problem = link.set_rate(rate)
            if problem:
                self._end(problem)
                return
        # Setting the rate put stray bytes on the screen's line. An FF FF FF
        # ends them, and the screen's error code for them is not passed on.
        self._keep(_is_code, lambda piece: None, pause(rate))
        self._to_screen(END, "FF FF FF", "to end the stray bytes of the change of rate")

    def _to_screen(self, data: bytes, shown: str, why: str):
        """Sends the bridge's own `data` to the screen, and logs it as
        `shown`, with the reason `why`."""
        if self._write(self._screen, data):
            self._note("bridge: sent the screen %s, %s. Its answer is not passed on to the MCU"
                       % (shown, why))

    def _keep(self, is_answer, took, seconds: float):
        """For the next `seconds`, watches for the screen's answer to an
        instruction the bridge sent itself. If `is_answer(piece)` accepts the
        first piece the screen sends, that piece goes to `took(piece)` and
        not to the MCU. Otherwise the piece passes on to the MCU. Anything
        still held from an earlier wait passes on at once."""
        with self._to_mcu:
            with self._lock:
                if self._over:
                    return
                held = self._held
                self._stop_keeping()
                self._keeping = (is_answer, took)
                self._keep_timer = threading.Timer(seconds, self._keep_no_more)
                self._keep_timer.daemon = True
                self._keep_timer.start()
            problem = self._pass_on(held)
        if problem:
            self._end(problem)

    def _take_kept(self, data: bytes) -> bytes:
        """Holds `data` until its first piece shows whether it is the answer
        waited for, then returns what passes on. Called with the lock
        held."""
        self._held += data
        end = piece_end(self._held, REPLY_LENGTHS)
        if end is None:
            return b""
        piece, rest = self._held[:end], self._held[end:]
        is_answer, took = self._keeping
        self._stop_keeping()
        if not is_answer(piece):
            return piece + rest
        took(piece)
        self._note_later("bridge: did not pass %s on to the MCU" % hex_bytes(piece))
        return rest

    def _keep_no_more(self):
        """Ends the wait for the answer, and passes on to the MCU what was
        held."""
        with self._to_mcu:
            with self._lock:
                if self._keep_timer is not threading.current_thread():
                    return
                held = self._held
                self._stop_keeping()
                switching = (self._screen_answers and self._next_rate is not None
                             and bool(held))
            problem = self._pass_on(held)
        if problem:
            self._end(problem)
        elif switching:
            self._switch()

    def _stop_keeping(self):
        """Called with the lock held."""
        self._keeping = None
        self._held = b""
        if self._keep_timer is not None:
            self._keep_timer.cancel()
            self._keep_timer = None

    def _learn_bauds(self, piece: bytes):
        """Takes the screen's answer to `get bauds`. Called with the lock held."""
        rate = int.from_bytes(piece[1:5], "little")
        if rate in RATES:
            self._bauds = rate

    def _note_later(self, line: str):
        """Notes `line` from a thread of its own, because the caller holds the
        lock."""
        threading.Thread(target=self._note, args=(line,), daemon=True).start()

    def _pass_on(self, data: bytes):
        """Writes what came from the screen to the MCU, if the screen answers
        the MCU. Returns why the MCU port did not take it, or None. Called
        with `_to_mcu` held."""
        if not data or not self._screen_answers:
            return None
        return self._mcu.send_whole(data, WRITE_WAIT)

    def _write(self, link, data: bytes) -> bool:
        """Writes `data` whole to `link`, or ends the bridge, saying why."""
        problem = link.send_whole(data, WRITE_WAIT)
        if problem:
            self._end(problem)
            return False
        return True

    def _end(self, why: str):
        with self._lock:
            if self._over:
                return
            self._over = True
            self._stop_timers()
        self._ended(why)

    def _stop_timers(self):
        """Called with the lock held."""
        self._stop_keeping()
        self._next_rate = None
        if self._switch_timer is not None:
            self._switch_timer.cancel()
            self._switch_timer = None

    def _rate(self) -> int:
        return self._screen.state()["baud"]


def _is_number(piece: bytes) -> bool:
    """Returns whether `piece` is the screen's answer to a `get` of a number."""
    return len(piece) == 8 and piece[0] == 0x71


def _is_code(piece: bytes) -> bool:
    """Returns whether `piece` is one of the screen's return codes for an
    instruction. Those are all below 0x80, so 0x88, "ready", is not one."""
    return len(piece) == 1 + len(END) and piece[0] < 0x80
