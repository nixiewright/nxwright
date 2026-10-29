"""The check of what a screen's series refuses on a page, as the Editor's
compile refuses it: a component of a type the series lacks, or one holding
a choice the series refuses (check_series_components).

It reads the attributes' choices from nxwright's descriptions
(attribute_descriptions.py). project/ imports nothing of source/, so the
check sits here, beside its one caller, source_folder.py, rather than with
the other page checks, in project/editor_limits.py."""
from nxwright import NxwrightError
from nxwright.project.attribute_descriptions import describe
from nxwright.project.editor_limits import object_label
from nxwright.project.memory_table import memory_table
from nxwright.project.object_types import TYPE_NAMES
from nxwright.project.page_block import PageBlock
from nxwright.project.screen_models import ScreenModel

# Choices the Editor's compile refused on a series that the memory table
# lacks ("Out of range"), as the memory probe tries a single other value of
# each attribute. By series: {attribute: (values refused)}, refused on every
# type whose attribute has them among its choices. The Basic, Enhanced, and
# Discovery series refused a `sta` of 3, nothing, so the page shows
# through, on each of their types with that choice. They refused a slider's
# `psta` of 2, a square knob, the only type with that choice. (Worked out
# from the Editor 1.68.2.)
CHOICES_REFUSED_BY_SERIES = {series: {"sta": (3,), "psta": (2,)} for series in ("T", "K", "F")}


def check_series_components(page: PageBlock, screen: ScreenModel, where: str):
    """Raises NxwrightError, starting with `where` (the file at fault), for
    the first object of the page, the page among them, that the series of
    `screen`, the folder's screen model, refuses: one of a type the series
    refuses ("Unsupported component was found for this series device"), or
    one whose attribute with choices holds a choice the series was seen to
    refuse ("Out of range"). They come from the memory table
    (memory_table.SeriesCosts, `refused` and `refused_values`), and the
    choices from CHOICES_REFUSED_BY_SERIES as well. The table's other refused
    values, each a sample past an attribute's range, are not checked, as the
    range is not known. The error's `table` is the object's place in the
    page, from 0 for the page."""
    costs = memory_table().series[screen.series]
    for index, page_object in enumerate(page.objects):
        type_name = TYPE_NAMES.get(int.from_bytes(page_object.attribute("type") or b"", "little"))
        if type_name in costs.refused:
            problem = ("the %s lacks the type %s, and the Nextion Editor refuses to compile it "
                       "(\"Unsupported component was found for this series device\")"
                       % (screen.name, type_name))
        else:
            problem = (_refused_choice(page_object, type_name,
                                       costs.refused_values.get(type_name, {}), screen.name)
                       or _refused_choice(page_object, type_name,
                                          CHOICES_REFUSED_BY_SERIES.get(screen.series, {}),
                                          screen.name))
        if problem is not None:
            error = NxwrightError("%s: %s: %s" % (where, object_label(page_object, index),
                                                  problem))
            error.table = index
            raise error


def _refused_choice(page_object, type_name: str, refused: dict, model: str):
    """Returns why `page_object`, of the type `type_name`, holds a choice
    the series refuses, among `refused`, {attribute: (values refused)}; or
    None. Only an attribute with choices, as nxwright's descriptions of the
    attributes list them, and only a value among them, is taken."""
    for attribute, values in refused.items():
        described = describe(type_name, attribute)
        stored = page_object.attribute(attribute)
        if described is None or stored is None:
            continue
        value = int.from_bytes(stored, "little")
        if value in described.choices and value in values:
            return ("its %s of %d is refused on the %s, as the Nextion Editor's compile refuses "
                    "it (\"Out of range\")" % (attribute, value, model))
    return None
