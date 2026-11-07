"""The listing: a text that shows what a TFT file's user code holds, part by
part, from its decoded file (decoded_file.py): its settings, on P and E
its table of attribute names, its int variables, program.s, its macros, and
each page, with each object's type, ID, name, entries, and runs of blocks,
then the pictures and fonts.

Each block is shown as its place, counted from the user code's start, and
its bytes in hexadecimal.
"""
from nxwright.tft.decompiling.decoded_file import CodeRun, DecodedFile, Name

# The mark of a name no guess matched, which the decoded file made up.
_UNMATCHED = " (no guess matched its checksum, 0x%08x)"


def listing_lines(decoded: DecodedFile) -> list:
    """Returns the lines of the listing of `decoded`. Each name is marked
    when no guess matched its checksum."""
    lines = ["%s, series %s, at %d degrees, in %s"
             % (decoded.model, decoded.series, decoded.rotation, decoded.encoding)]
    if decoded.attribute_names is not None:
        # On P of the Nextion Editor 1.63.3, a slot may have no name.
        lines.append("attribute names: " + ", ".join(
            "slot %d" % slot if name is None else name
            for slot, name in enumerate(decoded.attribute_names)))
    lines.append("int variables:")
    lines += ["  %s = %d" % (_named(variable.name), variable.value) for variable in decoded.ints]
    lines += _run_lines("program.s", decoded.program, "")
    for macro in decoded.macros:
        lines += _run_lines("macro %s, labels from %d" % (_named(macro.name), macro.label_number),
                            macro.code, "")
    for page in decoded.pages:
        lines.append("page %d:" % page.page_id)
        for each in page.objects:
            lines.append("  object %d, %s, a %s%s, entries %d to %d" % (
                each.object_id, _named(each.name), each.type_name,
                ", global" if each.is_global else "", each.first_entry,
                each.first_entry + len(each.entries) - 1))
            lines += _blocks_lines("drawing", each.drawing, "    ")
            lines += _blocks_lines("background fill", each.background_fill, "    ")
            for name, run in each.events.items():
                lines += _run_lines(name, run, "    ")
        lines.append("  memory from %d: %s" % (page.memory_start, page.memory.hex(" ")))
        lines += _run_lines("load section", page.load_section, "  ")
    lines += ["%s %d: %d bytes" % (each.kind, each.resource_id, each.size)
              for each in decoded.resources]
    return lines


def _named(name: Name) -> str:
    """Returns `name`'s text, marked when no guess matched it."""
    return name.text if name.matched else name.text + _UNMATCHED % name.crc


def _blocks_lines(title: str, blocks: list, indent: str) -> list:
    """Returns the lines of the blocks `blocks`, under `title`, or none when
    there are none."""
    if not blocks:
        return []
    return ["%s%s:" % (indent, title)] + ["%s  %s" % (indent, block.hex(" ")) for block in blocks]


def _run_lines(title: str, run: CodeRun, indent: str) -> list:
    """Returns the lines of the run of code `run`, under `title`, each block
    after its place: none but the title when it has no block."""
    if not run.blocks:
        return ["%s%s: no code" % (indent, title)]
    return ["%s%s:" % (indent, title)] + [
        "%s  0x%x: %s" % (indent, place, block.hex(" "))
        for place, block in zip(run.block_places(), run.blocks)]
