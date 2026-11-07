"""Two readers that the decoders of P's types share (tft/decompiling/objects.py):
p_text_rooms, the rooms of a component's texts that its memory keeps where
no entry gives them, as a gmov's path_m; and p_init_blocks, the init block
the Nextion Editor adds to a page's load section for some types, as a
select's.

The test decodes each probe of P that keeps its user code, and compares
with the compile's own writing of the same probe's facts, in memory: each
component's rooms as its page object gives them, and the blocks its type's
load_start adds.
"""
import unittest

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft import frame
from nxwright.tft.component_types import object_module, p_texts
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import decoded_user_code
from nxwright.tft.decompiling.objects import p_init_blocks, p_text_rooms
from nxwright.tft.instructions.undocumented_commands import init_block
from tests.tft.test_decoded_file import _probes_keeping_their_user_code
from tests.tft.unit_inputs import probe_facts, user_code_of


def _components():
    """Yields (the probe's name, its decoded page, the decoded file, a
    component of the page, its page object, its type's or variant's module,
    and the blocks its type adds to its page's load section, as the compile
    writes them) for each component of each probe of P that keeps its user
    code."""
    for probe in _probes_keeping_their_user_code(("P",)):
        project = probe_facts(probe)
        settings = project.settings
        decoded = decoded_user_code(user_code_of(probe), "P", settings.model.name,
                                    settings.rotation, settings.encoding)
        places = frame.laid_out(project)[2]
        for page, page_block in zip(decoded.pages, project.pages):
            for each, page_object in zip(page.objects[1:], page_block.objects[1:]):
                module = object_module(page_object)
                place = places["page%d-%d" % (page.page_id, each.object_id)]
                added = (module.load_start(page_object, project, place, {})
                         if hasattr(module, "load_start") else [])
                yield probe.name, page, decoded, each, page_object, module, added


class RoomsAndInitTest(unittest.TestCase):

    def test_each_component_on_p(self):
        # A component's rooms are its page object's attributes that set
        # them. One whose type adds the init block to its page's load
        # section has it there, and one whose type adds none has none.
        rooms, inits = 0, 0
        for name, page, decoded, each, page_object, module, added in _components():
            with self.subTest(name, page=page.page_id, component=each.object_id):
                self.assertEqual(p_text_rooms(each, page, decoded, module),
                                 {maxl: number_from_bytes(page_object.attribute(maxl))
                                  for _, maxl, _ in p_texts(module).values()})
                rooms += bool(p_texts(module))
                if init_block(each.object_id) in added:
                    self.assertEqual(p_init_blocks(each, page, decoded), 1)
                    inits += 1
                elif init_block(each.object_id) not in page.load_section.blocks:
                    self.assertRaises(DecodeError, p_init_blocks, each, page, decoded)
        # The components that keep a text's room, such as texts and gmovs,
        # and those whose type adds the init block, such as selects.
        self.assertEqual((rooms, inits), (443, 230))


if __name__ == "__main__":
    unittest.main()
