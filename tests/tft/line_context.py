"""The context matching gives a line of code in an event (matching.py), for
the tests that build a line's need by hand: the types of the components of
the line's page, by name, and the components themselves."""
from nxwright.tft.matching import project_needs
from tools.tft.probing.statement_probes import touch_release_code
from tests.tft.unit_inputs import page, project_of


def line_context(*components: str) -> dict:
    """Returns the context of a line in page0's Touch Release event, on a T
    page of `components`, each in a page file's form, as a probe of
    attribute_probes.with_attributes has it."""
    project = project_of(page(*components, code=touch_release_code(["sys0=1"]), strict=True),
                         strict=True, fonts=0)
    return next(need.context for need in project_needs(project)
                if need.kind == "code" and need.subject == "event")
