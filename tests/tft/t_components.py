"""What a component's type writes on T, for the tests of each type: its
memory, its drawing, and its entries (tft/component_types/__init__.py),
as the frame asks its type for them (tft/frame.py).

Each function takes a page object, a Project of the facts its type reads,
and its place, as tests/tft/unit_inputs.py's probe_facts and probe_objects give
them for a probe. TypePieces compares them with the probe's pieces, for
each component of a type in each probe that keeps its whole user code.
The tests to add to it, CodePieces, EventStartPieces, and
LoadSectionPieces, compare other pieces of the same probes. The last one
serves PTypePieces on P too (tests/tft/p_components.py).
"""
from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft import frame
from nxwright.tft.component_types import object_module, type_name
from tools.tft.probing.component_probes import user_code_kept
from tools.tft.probing.statement_probes import event_blocks, ours_in_event
from nxwright.tft.tft_file import encode_blocks
from tests.tft.unit_inputs import piece, piece_names, probe_change, probe_facts, probe_objects


def t_memory(page_object, project, place) -> bytes:
    """Returns the component's starting memory on T: given its place by a
    type that keeps a text or a buffer after its page's components' memory,
    and so gives where it lies (memory_at)."""
    module = object_module(page_object)
    if frame._places_after(module):
        return module.memory_at(page_object, project, place)
    return module.memory(page_object, project)


def t_scratch_tail(page_object) -> int:
    """Returns how many bytes at the end of the component's memory on T the
    frame's scratch image writes: those that round the room of a txt kept in
    its memory up to 4, past its txt_maxl + 1 bytes (frame._t_rooms). They
    keep what earlier pages left there, which its type cannot know."""
    module = object_module(page_object)
    if not hasattr(module, "TXT_PLACE"):
        return 0
    room = number_from_bytes(page_object.attribute("txt_maxl")) + 1
    return -(module.TXT_PLACE + room) % 4


def t_drawing(page_object, project, place) -> bytes:
    """Returns the component's drawing on T, its blocks then a 0 word, as
    the piece page0-N-drawing holds it."""
    return encode_blocks(object_module(page_object).drawing(page_object, project, place)
                         + [b""])


def t_entries(page_object, project, place) -> bytes:
    """Returns the component's entries on T, as the piece page0-N-entries
    holds them."""
    return object_module(page_object).data(page_object, project, place)


def made_in_memory(probe) -> bool:
    """Whether `probe`'s change keeps what it adds, so that its pages are
    made in memory (tests/tft/unit_inputs.py)."""
    change = probe_change(probe)
    return hasattr(change, "components") or hasattr(change, "changes")


def keeps_its_user_code(probe) -> bool:
    """Whether `probe` keeps its whole user code as its fixtures, and its
    pages are made in memory."""
    return probe.fixtures is not None and probe.kept is user_code_kept and made_in_memory(probe)


class ComponentPieces:
    """Tests, for a unittest.TestCase that also derives from a class derived
    from this: each component of the type TYPE, as nxwright names it, or of
    every type when TYPE is None, as a probe of every type on a page has
    them, in each probe of PROBES that keeps its whole user code, against
    the probe's pieces: its memory, by `memory_of`, and its entries, by
    `entries_of`, each called with the component, its Project of facts, and
    its place, which a class derived from this must give. COUNT is how many
    components that gives, so that a probe that no longer holds one is
    noticed."""

    TYPE: str = None
    PROBES: list = ()
    COUNT: int = None

    @classmethod
    def setUpClass(cls):
        # (the probe, a component, its place, the Project of facts its type
        # reads) for each component of the type, their pages made once.
        cls.components = []
        for probe in cls.PROBES:
            if not keeps_its_user_code(probe):
                continue
            project = probe_facts(probe)
            cls.components += [(probe, page_object, place, project) for page_object, place
                               in probe_objects(probe, cls.TYPE, project)]

    def assert_each(self, function, kind: str):
        for probe, page_object, place, project in self.components:
            name = "page%d-%d-%s" % (place.page, place.object_id, kind)
            with self.subTest(probe.name, object_id=place.object_id):
                # A component that writes no memory, as a hotspot, has no
                # piece of it.
                missing = kind == "memory" and name not in piece_names(probe)
                expected = b"" if missing else piece(probe, name)
                self.assertEqual(function(page_object, project, place), expected)

    def test_its_components(self):
        self.assertEqual(len(self.components), self.COUNT)

    def test_its_memory(self):
        self.assert_each(self.memory_of, "memory")

    def test_its_entries(self):
        self.assert_each(self.entries_of, "entries")


class TypePieces(ComponentPieces):
    """ComponentPieces on T: each component's memory, its drawing, and its
    entries, at its type's functions (t_memory, t_drawing, t_entries)."""

    memory_of = staticmethod(t_memory)
    entries_of = staticmethod(t_entries)

    def test_its_drawing(self):
        self.assert_each(t_drawing, "drawing")


class CodePieces:
    """A test, for a unittest.TestCase that also derives from this: each
    probe of code of PROBES whose pages are made in memory, whose fixture is
    the blocks the statement encoder gives page0's Touch Release event,
    against the encoder's blocks for the probe's page, in strict Nextion
    syntax. CODE_COUNT is how many such probes there are. The others are
    compared whole (tests/tft/test_whole_files.py)."""

    PROBES: list = ()
    CODE_COUNT: int = None

    def test_its_probes_of_code(self):
        probes = [probe for probe in self.PROBES
                  if probe.fixtures is not None and (probe.kept or probe.ours) is ours_in_event
                  and made_in_memory(probe)]
        self.assertEqual(len(probes), self.CODE_COUNT)
        for probe in probes:
            with self.subTest(probe.name):
                self.assertEqual(event_blocks(probe_facts(probe)),
                                 {name: piece(probe, name) for name in piece_names(probe)})


class LoadSectionPieces:
    """A test, for a TypePieces or PTypePieces test: each component's blocks
    in its page's load section (its module's load_start), against its piece
    of that name for its page and ID, such as page0-1-load. On P these are
    `init` and its ID. On T, a type that also writes code of its own there
    counts the places in that code from where its probe's table gives the
    code lies (its place's load_place). A type without a load_start, as a
    text, writes nothing there, and its probe keeps no such piece, so a test
    of several types may take this too."""

    def test_its_load_section(self):
        for probe, page_object, place, project in self.components:
            name = "page%d-%d-load" % (place.page, place.object_id)
            module = object_module(page_object)
            with self.subTest(probe.name, object_id=place.object_id):
                if hasattr(module, "load_start"):
                    self.assertEqual(
                        encode_blocks(module.load_start(page_object, project, place, {})),
                        piece(probe, name))
                else:
                    self.assertNotIn(name, piece_names(probe))


class EventStartPieces:
    """A test, for a TypePieces test of a type that writes blocks at the
    start of its events (its module's event_start), as a button sets its val:
    each event piece of each component, page0-N-event-down and the like,
    starts with the event's name and those blocks. Its code's blocks, which
    follow, are the encoder's."""

    EVENTS = ("down", "up")

    def test_its_events_start(self):
        compared = 0
        for probe, page_object, place, project in self.components:
            for event in self.EVENTS:
                with self.subTest(probe.name, object_id=place.object_id, event=event):
                    start = object_module(page_object).event_start(page_object, project, place,
                                                                   event)
                    self.assertTrue(piece(probe, "page%d-%d-event-%s" % (
                        place.page, place.object_id, event)).startswith(
                            encode_blocks([event.encode("ascii")] + start)))
                compared += 1
        self.assertTrue(compared)


class FillStartAndLoadPieces:
    """Tests, for a TypePieces test of every type's components (its TYPE
    None): each component's background fill, which starts its piece, before
    the refs of the components over it, which the frame writes
    (overlaps.ref_blocks), and the piece's 0 word; the blocks its type
    writes at its events' start, as a button sets its val; and its blocks in
    its page's load section. Each is compared at its type's function with
    the probe's piece, for each component whose type writes it. A timer's
    blocks in the load section give a place in its record, which the frame
    writes, so they are left to the frame's tests and the sample of whole
    files. FILL_COUNT, START_COUNT, and LOAD_COUNT are how many of each are
    compared."""

    FILL_COUNT: int = None
    START_COUNT: int = None
    LOAD_COUNT: int = None

    def test_its_background_fills(self):
        compared = 0
        for probe, page_object, place, project in self.components:
            name = "page%d-%d-background-fill" % (place.page, place.object_id)
            if name not in piece_names(probe):
                continue
            with self.subTest(probe.name, object_id=place.object_id):
                data = piece(probe, name)
                self.assertTrue(data.startswith(encode_blocks(
                    object_module(page_object).background_fill(page_object, project, place))))
                self.assertTrue(data.endswith(encode_blocks([b""])))
            compared += 1
        self.assertEqual(compared, self.FILL_COUNT)

    def test_its_events_start(self):
        compared = 0
        for probe, page_object, place, project in self.components:
            module = object_module(page_object)
            if not hasattr(module, "event_start"):
                continue
            for event in module.EVENTS:
                with self.subTest(probe.name, object_id=place.object_id, event=event):
                    start = module.event_start(page_object, project, place, event)
                    self.assertTrue(piece(probe, "page%d-%d-event-%s" % (
                        place.page, place.object_id, event)).startswith(
                            encode_blocks([event.encode("ascii")] + start)))
                compared += 1
        self.assertEqual(compared, self.START_COUNT)

    def test_its_load_sections(self):
        compared = 0
        for probe, page_object, place, project in self.components:
            name = "page%d-%d-load" % (place.page, place.object_id)
            if name not in piece_names(probe) or type_name(page_object) == "timer":
                continue
            with self.subTest(probe.name, object_id=place.object_id):
                self.assertEqual(encode_blocks(object_module(page_object).load_start(
                    page_object, project, place, {})), piece(probe, name))
            compared += 1
        self.assertEqual(compared, self.LOAD_COUNT)
