"""list the serial ports a screen may be on, for upload's --port

  nxwright ports [--json]

Prints each serial port of the computer that pyserial finds, sorted by
name, such as COM5 or /dev/ttyUSB0, then its description when pyserial
has one, such as "USB-SERIAL CH340 (COM5)". It opens no port, so it does
not tell which one a screen is on.

--json is for programs, such as nxwright's VS Code extension: it prints one
JSON object per port, {"port": name, "description": words}, with "" for no
description, and nothing when there is no port.
"""
import argparse
import json


def main(arguments: list) -> int:
    parser = argparse.ArgumentParser(prog="nxwright ports",
                                     description="Lists the serial ports a screen may be on.")
    parser.add_argument("--json", action="store_true",
                        help="print JSON objects, one a line, for programs")
    options = parser.parse_args(arguments)
    ports = serial_ports()
    for port, description in ports:
        if options.json:
            print(json.dumps({"port": port, "description": description}))
        else:
            print("%s  %s" % (port, description) if description else port)
    if not ports and not options.json:
        print("No serial port was found.")
    return 0


def serial_ports() -> list:
    """Returns each serial port pyserial finds, as (its name, its
    description), sorted by name. pyserial gives "n/a" for a port it has no
    description of, which is given as ""."""
    from serial.tools import list_ports
    return sorted((port.device, "" if port.description in ("", "n/a") else port.description)
                  for port in list_ports.comports())
