"""Reads a file stream's attributes back, as the compile's file_stream
module writes them on P (component_types/file_stream.py): its values,
where its named entries say (objects.p_values). The size of its buffer and
where its buffer lies are the compile's, and are not attributes.

The Nextion Editor adds two blocks of its own for each file stream: the
init block with its ID in its page's load section (objects.p_init_blocks),
and a call of its close at the end of its page's unload event
(file_stream.unload_lines). The Nextion Editors before 1.67.1 add the call
of the file stream's close, but no init block. The calls follow the page's
own code, in the order of the file streams' IDs. The decoder checks that its
call is where the compile writes it, and gives both, so that the source
folder leaves them out.
"""
from nxwright.tft.component_types import file_stream
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import CodeRun, DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import (ObjectValues, attribute_of_entry, candidate_object,
                                       named_entries, p_init_blocks, p_values)

# The first release whose files have a file stream's init block. The
# probes of 1.60.1, and of every release from 1.63.1 to 1.65.1, have none,
# and those of 1.67.1, 1.68.1, and 1.68.2 have one
# (ResearchNotes/tft/older-editors.md).
_INIT_BLOCK_FROM = (1, 67, 1)


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the ObjectValues of the file stream `decoded_object`, of
    `decoded_page`. Raises DecodeError when a value does not lie in its
    memory, when its page's load section lacks its init block in a file
    made by 1.67.1 or later, and when its page's unload event does not end
    with the calls of the file streams' close, its own among them."""
    # The decoder of code imports the decoders, so it is imported here.
    from nxwright.tft.decompiling.code import decoded_lines
    values = p_values(decoded_object, decoded_page, decoded_file)
    expected = file_stream.unload_lines(
        candidate_object(decoded_object.type_number,
                         {"objname": decoded_object.name.text.encode("latin-1")}))
    # Each file stream's lines follow the page's own code, the earlier IDs'
    # first, and each line is one block.
    streams = [each.object_id for each in decoded_page.objects
               if each.type_name == decoded_object.type_name]
    after = len(expected) * (len(streams) - streams.index(decoded_object.object_id))
    unload = decoded_page.objects[0].events.get("unload", CodeRun(0, []))
    if after > len(unload.blocks):
        raise DecodeError("the unload event of page %d is too short for the close of its file "
                          "stream %d" % (decoded_page.page_id, decoded_object.object_id),
                          unload.place, b"".join(unload.blocks))
    start = len(unload.blocks) - after
    own = CodeRun(unload.block_places()[start], unload.blocks[start:start + len(expected)])
    # The call names the file stream's own entries, which its record gives,
    # so they are named here, not by decoding the file stream again.
    entries = {decoded_object.first_entry + number: name
               for name, number in named_entries(decoded_object, decoded_file).items()}

    def attribute_named(decoded: DecodedFile, number: int) -> tuple:
        if number in entries:
            return decoded_page, decoded_object, entries[number]
        return attribute_of_entry(decoded, number)
    if decoded_lines(own, decoded_page.page_id, decoded_file, attribute_named) != expected:
        raise DecodeError("the unload event of page %d does not call the close of its file "
                          "stream %d where the Nextion Editor adds it"
                          % (decoded_page.page_id, decoded_object.object_id),
                          own.place, b"".join(own.blocks))
    init = (p_init_blocks(decoded_object, decoded_page, decoded_file)
            if decoded_file.version >= _INIT_BLOCK_FROM else 0)
    return ObjectValues(values, {"load": (init, 0),
                                 "page unload": (0, len(expected))})
