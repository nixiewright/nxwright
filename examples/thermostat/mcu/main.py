"""The thermostat demo's MCU emulator. It emulates a microcontroller with an
outdoor sensor, and sends the screen the outdoor temperature every few
seconds. That temperature follows the time of day, from 5 degrees before
dawn to 15 degrees in the afternoon, and the app's simulated room cools or
warms towards it.

In VS Code, a simulation whose MCU port is Emulator starts this program. To
start it yourself, run it with a port number, as in `python main.py 7000`,
then connect the simulator's MCU port over TCP to 127.0.0.1:7000.
"""
import math
import sys
import time

from nxwright import mcu

# Ends each instruction the screen receives.
END = b"\xff\xff\xff"
# How long the emulator waits between two readings, in seconds.
PERIOD = 5
# The coldest and the warmest temperature of the day, in hundredths of a
# degree Celsius, which is the unit of the app's temperatures.
COLDEST = 500
WARMEST = 1500
# The hour of the warmest temperature. The coldest comes 12 hours from it.
WARMEST_HOUR = 15


def outdoor_at(hour: float) -> int:
    """Returns the temperature outdoors at `hour` of the day, from 0 to 24,
    in hundredths of a degree Celsius."""
    middle = (COLDEST + WARMEST) / 2
    swing = (WARMEST - COLDEST) / 2
    return round(middle + swing * math.cos((hour - WARMEST_HOUR) * math.pi / 12))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else None
    if port is not None:
        # Flushed so that the line shows at once. Python would otherwise keep
        # it back when the output goes to another program.
        print("Waiting for the simulator on 127.0.0.1:%d" % port, flush=True)
    with mcu.open(listen=port) as line:
        while True:
            # The simulator's screen gets the time from this computer's
            # clock, so this reading is for the time the screen shows.
            now = time.localtime()
            reading = outdoor_at(now.tm_hour + now.tm_min / 60)
            # Sets the app's variable `outdoor`, which program.nx declares.
            line.write(b"outdoor=%d" % reading + END)
            print("Outdoors: %.1f degrees" % (reading / 100), flush=True)
            line.sleep(PERIOD)
            # This emulator does not need anything the app sends. It still
            # reads what arrived, so that the bytes do not pile up.
            line.read(line.in_waiting)


if __name__ == "__main__":
    try:
        main()
    except mcu.LineClosed:
        # The simulation ended.
        pass
