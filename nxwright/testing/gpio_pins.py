"""The screen's GPIO pins, as a simulation keeps them: each pin's mode, the
component a bound pin runs, and the level something outside the screen
gives an input.

A pin is one of io0 to io7, which code reads and writes as `pio0` to `pio7`.
`cfgpio <io>,<mode>,<comp>` sets its mode: 0 a pull-up input, 1 an input
bound to a component, 2 a push-pull output, 3 a PWM output, which io4 to io7
alone take, and 4 an open-drain output. Every pin is a pull-up input at
power-on.

An input reads its level, the one something outside the screen gives it: a
button, a switch, or a sensor. A pull-up input that nothing drives reads 1,
as the vendor says. Code writing to an input changes nothing. A bound pin
runs its component's Press event when its level falls, and its Release
event when its level rises.

The levels belong to the world outside the screen, so they outlive a start
of the screen. Its modes and bindings do not.
"""
from nxwright import NxwrightError

PINS = 8
# The pins as code names them.
PIN_NAMES = tuple("pio%d" % pin for pin in range(PINS))
# cfgpio's modes.
PULL_UP, BOUND, PUSH_PULL, PWM, OPEN_DRAIN = range(5)
# What a pull-up input reads when nothing outside drives it.
UNDRIVEN = 1
# The pins that take the PWM mode.
_PWM_PINS = range(4, 8)


def pin_number(name: str) -> int:
    """Returns the number of the pin code names `name`, such as 2 for
    "pio2". Raises NxwrightError for another name."""
    if name not in PIN_NAMES:
        raise NxwrightError("%s is not a GPIO pin: the pins are pio0 to pio7" % name)
    return PIN_NAMES.index(name)


def checked_level(pin: int, level) -> int:
    """Returns `level`, a level given to the pin `pin`. Raises NxwrightError
    for a pin outside 0 to 7, or a level other than 0 or 1. Each is a whole
    number: a request may give 2.0 or true, which Python would take as 2
    and 1."""
    if not _whole(pin) or pin not in range(PINS):
        raise NxwrightError("a GPIO pin is from 0 to 7, not %r" % (pin,))
    if not _whole(level) or level not in (0, 1):
        raise NxwrightError("%s's level is 0 or 1, not %r" % (PIN_NAMES[pin], level))
    return level


def starting_levels(levels) -> dict:
    """Returns {pin: level} of `levels`, the inputs' starting levels by name,
    such as {"pio2": 0}. Raises NxwrightError for anything else."""
    if not isinstance(levels, dict):
        raise NxwrightError("the inputs' starting levels are given by name, as "
                            '{"pio2": 0}, not %r' % (levels,))
    return {pin_number(name): checked_level(pin_number(name), level)
            for name, level in levels.items()}


def _whole(number) -> bool:
    """Returns whether `number` is a whole number, and not True or False."""
    return isinstance(number, int) and not isinstance(number, bool)


class GpioPins:
    """The 8 pins: `modes`, `components` (the component a bound pin runs, by
    name or ID, or None), and `levels`, each a list by pin number. `levels`
    gives each input's starting level, UNDRIVEN for a pin it leaves out."""

    def __init__(self, levels: dict = None):
        self.levels = [(levels or {}).get(pin, UNDRIVEN) for pin in range(PINS)]
        self.start()

    def start(self):
        """Makes every pin a pull-up input, bound to nothing, as at power-on.
        The levels stay."""
        self.modes = [PULL_UP] * PINS
        self.components = [None] * PINS

    def configure(self, pin: int, mode: int, component: str) -> bool:
        """Runs `cfgpio pin,mode,component`, and returns whether it changed a
        pin. A pin outside 0 to 7, a mode outside 0 to 4, or the PWM mode on
        io0 to io3 changes none."""
        if not 0 <= pin < PINS or not PULL_UP <= mode <= OPEN_DRAIN or (
                mode == PWM and pin not in _PWM_PINS):
            return False
        self.modes[pin] = mode
        self.components[pin] = component if mode == BOUND else None
        return True

    def is_input(self, pin: int) -> bool:
        """Returns whether `pin` is an input, which reads its level."""
        return self.modes[pin] in (PULL_UP, BOUND)

    def set_level(self, pin: int, level: int):
        """Sets the level outside the screen gives `pin`. Returns (component,
        event) when a bound pin's level changes: "down" when it falls, and
        "up" when it rises. Returns None otherwise."""
        before, self.levels[pin] = self.levels[pin], level
        component = self.components[pin]
        if component is None or level == before:
            return None
        return component, "down" if level < before else "up"

    def unbind(self):
        """Ends every binding, as a page change does: the vendor has `cfgpio`
        given again after each refresh of the page. The modes stay."""
        self.components = [None] * PINS

    def view(self) -> list:
        """Returns each pin as {"mode", "component", "level"}, by pin number."""
        return [{"mode": mode, "component": component, "level": level}
                for mode, component, level in zip(self.modes, self.components, self.levels)]
