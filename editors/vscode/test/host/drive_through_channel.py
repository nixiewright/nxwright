"""Drives a simulation in the test's VS Code through its agent channel,
with `nxwright mcp`'s own client (nxwright/mcp_server/vscode.py), for
agentChannel.host.cjs. The client and the channel are each tested against
a stand-in for the other; this checks that the two agree.

  python drive_through_channel.py <source folder>

It starts the app of the source folder in the window whose workspace
contains it, drives it, then stops it. It prints what each step answered,
as one JSON object, for the test to check. nxwright's checkout must be on
Python's import path.
"""
import json
from pathlib import Path
import sys

from nxwright import NxwrightError
from nxwright.mcp_server.vscode import VsCodeWindows, channel_folder


def drive(source: Path) -> dict:
    """Returns what each step answered, by step."""
    windows = VsCodeWindows(channel_folder())
    simulation, page = windows.start(source)
    # Other windows, such as the user's own VS Code, may run simulations too.
    answers = {"session": simulation.session, "page": page,
               "running": [session for window_file, session, _, _ in windows.running()
                           if window_file == simulation.window_file]}
    # A refusal comes back as the channel's error.
    try:
        windows.start(source)
    except NxwrightError as refusal:
        answers["second start"] = str(refusal)
    simulation.press(10, 10)
    simulation.release()
    simulation.send('dirLabel.txt="new"')
    answers["values"] = simulation.values(["dirLabel.txt"])
    shown = simulation.screen()
    answers["screen"] = {"page": shown["page"], "text": shown["text"],
                         "png": shown["png"][:4].hex()}
    answers["components"] = [component["type"] for component in simulation.components()]
    answers["log"] = [entry["line"] for entry in simulation.log()]
    simulation.stop()
    return answers


if __name__ == "__main__":
    print(json.dumps(drive(Path(sys.argv[1]))))
