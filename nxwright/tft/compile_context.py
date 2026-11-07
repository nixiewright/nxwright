"""What a compile works out from its whole project, once.

A compile's stages need tables of the whole project: where each object's
entries start (component_types.first_entries), the numbers of the labels
and timers (label_numbers.numbers), program.s's int variables, the pages by
name, and each page's components by name. Built inside the loops that use
them, such as once for each line of code, they would grow with the square
of the project.

The frame makes one CompileContext once the match check has passed, and
gives it to the statement encoder in place of the project. Each table is
built the first time it is needed, and kept. So a project the match check
refuses is refused with the check's message, not by an error of a table,
and a test that encodes one line builds only the tables that line needs.
The project never changes once made (project.py), so a table kept never
goes stale.
"""
from functools import cached_property

from nxwright.tft import component_types, label_numbers
from nxwright.tft.project import Project, program_variables


class CompileContext:
    """The tables of the whole project `project` that a compile's stages
    share."""

    def __init__(self, project: Project):
        self.project = project

    @cached_property
    def first_entries(self) -> dict:
        """{(page ID, object's name): the number of the object's first
        entry}, as component_types.first_entries gives it. Raises
        NxwrightError for a component whose type has no module."""
        return component_types.first_entries(self.project)

    @cached_property
    def numbers(self) -> label_numbers.Numbers:
        """The counter's numbers of the labels, gotos, calls, macros, and
        timers (label_numbers.numbers)."""
        return label_numbers.numbers(self.project)

    @cached_property
    def program_variables(self) -> list:
        """The names of program.s's int variables, in the order declared
        (project.program_variables)."""
        return program_variables(self.project)

    @cached_property
    def page_names(self) -> tuple:
        """The pages' names, in ID order."""
        return tuple(page.name for page in self.project.pages)

    @cached_property
    def _page_numbers(self) -> dict:
        # The first page of each name, as a scan of the pages finds it.
        numbers = {}
        for number, name in enumerate(self.page_names):
            numbers.setdefault(name, number)
        return numbers

    def page_number(self, name: str):
        """Returns the ID of the first page called `name`, or None."""
        return self._page_numbers.get(name)

    @cached_property
    def _components(self) -> list:
        # Each page's objects' names, in ID order, and the first object of
        # each name, the page's own included.
        found = []
        for page in self.project.pages:
            names = tuple(component_types.object_name(page_object)
                          for page_object in page.objects)
            by_name = {}
            for name, page_object in zip(names, page.objects):
                by_name.setdefault(name, page_object)
            found.append((names, by_name))
        return found

    def component_names(self, page: int) -> tuple:
        """Returns the names of the objects of the page of ID `page`, the
        page's own first, in ID order."""
        return self._components[page][0]

    def component(self, page: int, name: str):
        """Returns the first object called `name` on the page of ID `page`,
        the page itself included, or None."""
        return self._components[page][1].get(name)
