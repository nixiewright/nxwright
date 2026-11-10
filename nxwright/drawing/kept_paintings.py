"""Reusing what a component painted in the last drawing of its page.

A component's painting is the shapes and notes its painter adds to a
drawing (a Painting). The page preview redraws a page at each pause in
typing, and a simulation's panel after each thing that happens, while most
of the page stays as it was. So each painting is kept, and the next drawing
of the page reuses it as long as nothing it depends on has changed:
  - the component's type and values, and what draw_page passes its painter:
    its waveform's points, whether it is pressed, its file browser's
    entries, how far a press moved its lines, and where it scrolled;
  - the page's size, which some shapes are cut to;
  - the settings of the drawing's resources (DrawingResources): the
    encoding, the screen's rotation, and whether pictures are stored opaque;
  - what the painting read through the resources: which name and file each
    picture or font number stood for, and the state of each file it read
    or found missing (DrawingResources.start_recording).
Paintings are kept by page, then by component, because component names
repeat across pages. Each drawing of a page keeps only the paintings it used.

A painting can also store something in the resources, such as which SD card
file an external picture shows (DrawingResources.card_picture). The
resources serve a single drawing, so a reused painting stores it again in
the resources of the new drawing (DrawingResources.record_again).

Only components whose type is in REUSED_TYPES are reused. Any other type is
painted every time, so leaving out a type whose painter depends on something
not listed above costs only speed, and never gives a wrong drawing.
"""
import copy

# The types whose painters, with every function they call, were checked by
# reading the code, and depend only on what the module's docstring lists. Add
# a type only after such a check. A change to one of these painters must not
# make it depend on anything else.
REUSED_TYPES = frozenset(("page", "text", "button", "hotspot", "picture", "slider", "waveform",
                          "external-picture"))


class Painting:
    """What one component painted: the `shapes` it added, in order, and the
    `notes` it made, each once, in order. `inputs` is what the painting
    depended on besides the resources. `reads` is what it read through them
    (DrawingResources.stop_recording), or None for a painting that is not
    kept."""

    def __init__(self, inputs: tuple, shapes: list, notes: list, reads):
        self.inputs, self.shapes, self.notes, self.reads = inputs, shapes, notes, reads

    def add_to(self, drawing: dict):
        """Adds the shapes and the notes to `drawing`, skipping any note it
        already contains, so that each note appears once
        (ComponentPainter.note)."""
        drawing["shapes"].extend(self.shapes)
        for note in self.notes:
            if note not in drawing["notes"]:
                drawing["notes"].append(note)


class KeptPaintings:
    """The paintings of the latest drawing of each page, by page and
    component, for the next drawing of the page to reuse (draw_page)."""

    def __init__(self):
        # {page name: {component name: Painting}}
        self._pages = {}

    def of_page(self, page: str) -> dict:
        """The paintings of the latest drawing of `page`, by component."""
        return self._pages.get(page, {})

    def replace(self, page: str, paintings: dict):
        """Replaces the paintings kept for `page` with `paintings`, by
        component, those of its latest drawing."""
        self._pages[page] = paintings


class PaintingsOfADrawing:
    """The paintings one drawing of a page uses: those kept from its last
    drawing that are unchanged, and new ones for the rest. If `kept` is
    None, nothing is reused or kept."""

    def __init__(self, kept: KeptPaintings, page: str):
        self._kept, self._page = kept, page
        self._before = kept.of_page(page) if kept is not None else {}
        self._used = {}

    def painting(self, component, inputs: tuple, resources, paint) -> Painting:
        """Returns the painting of `component`. The painting kept for the
        component is reused if its inputs match `inputs` (alike) and what it
        read through `resources` is unchanged. `resources` then stores again
        what that painting stored in it (record_again). Otherwise the
        painting is new, from `paint()`, which returns the shapes and the
        notes the component's painter adds. A new painting is kept when the
        component's type is in REUSED_TYPES and `resources` can record what
        is read."""
        name = component.name
        found = self._used.get(name) or self._before.get(name)
        if found is not None and alike(found.inputs, inputs) and resources.unchanged(found.reads):
            resources.record_again(found.reads)
            self._used[name] = found
            return found
        keeping = (self._kept is not None and component.type in REUSED_TYPES
                   and resources.start_recording())
        try:
            shapes, notes = paint()
        finally:
            reads = resources.stop_recording() if keeping else None
        if not keeping:
            return Painting(inputs, shapes, notes, None)
        # A copy, because the simulation may change in place the values it passed.
        painting = Painting(copy.deepcopy(inputs), shapes, notes, reads)
        self._used[name] = painting
        return painting

    def finish(self):
        """Keeps the paintings this drawing used, as those of the page's
        latest drawing."""
        if self._kept is not None:
            self._kept.replace(self._page, self._used)


def alike(first, second) -> bool:
    """Whether two inputs of a painting are equal, and of the same types
    throughout. Python finds 1, 1.0, and True equal, but a painter may draw
    them differently."""
    # Python's own comparison comes first, because it finds most differences
    # fastest. If it finds the two equal, only the types of their contents
    # remain to check.
    if type(first) is not type(second) or first != second:
        return False
    if isinstance(first, dict):
        return all(alike(value, second[key]) for key, value in first.items())
    if isinstance(first, (list, tuple)):
        return all(map(alike, first, second))
    return True
