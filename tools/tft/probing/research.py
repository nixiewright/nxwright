"""Has the Nextion Editor compile lines of code, so that the blocks it
writes can be read before any probe checks them (`tools.tft.probe research`).

The lines go in page0's Touch Release event, on a series' base folder,
beside the components the probes of commands' operands use
(command_operand_probes.COMPONENTS): the text t0, the numbers n0 and n1,
the timer tm0, and the waveform s0. So a line may name any of them.
"""
from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.command_operand_probes import COMPONENTS
from tools.tft.probing.probe_runner import Probe, editor_tft
from tools.tft.probing.statement_probes import theirs_in_event
from nxwright.tft.tft_file import split_blocks


def research_probe(series: str, lines: list) -> Probe:
    """Returns the probe whose project holds `lines` in page0's Touch
    Release event, beside COMPONENTS, on the base folder of `series`. It
    compares nothing."""
    return Probe("research", series, with_attributes(lines, COMPONENTS), None, None)


def event_blocks(series: str, lines: list, tool) -> list:
    """Returns the blocks the Nextion Editor writes for `lines` in page0's
    Touch Release event on the base folder of `series` (research_probe), as
    (place, block), the place counted in bytes from the event's first
    block, each block's 4-byte size word among them. `tool` writes the TFT
    file (probe_runner.EditorTool). Raises ProbeError when the Nextion
    Editor refuses the lines, quoting its Output panel, and ProbeMismatch
    when its file cannot be read."""
    found, place = [], 0
    data = editor_tft(research_probe(series, lines), tool)
    for block in split_blocks(theirs_in_event(data)["event"]):
        found.append((place, block))
        place += 4 + len(block)
    return found
