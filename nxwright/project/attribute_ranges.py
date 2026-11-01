"""The values the Nextion Editor's compile takes for the attributes of pages
and components, where it takes fewer than the attributes' bytes can store
(attribute_ranges.toml, which says where they come from).

A range is the same on every series, or differs by series. The build checks
the first as it reads a page file, whatever the screen
(page_source.attribute_range). It checks the second once it knows the
folder's screen (series_components.check_series_components)."""
from functools import lru_cache
from pathlib import Path
import tomllib

TABLE_FILE = Path(__file__).resolve().parent / "attribute_ranges.toml"
# The table that gives an attribute the same range on every type that has it.
_COMMON = "common"


@lru_cache(maxsize=None)
def _table() -> dict:
    """Returns the table, {type name, or "common": {attribute: range}}, a
    range being [lowest, highest] or {series: [lowest, highest]}."""
    return tomllib.loads(TABLE_FILE.read_text(encoding="utf-8"))


def _range(type_name: str, attribute: str):
    """Returns the table's range of `attribute` of the type `type_name`, its
    type's own or else the common one, or None."""
    table = _table()
    own = table.get(type_name, {}).get(attribute)
    return own if own is not None else table[_COMMON].get(attribute)


def range_on_every_series(type_name: str, attribute: str):
    """Returns (lowest, highest) of `attribute` of the type `type_name` when
    it is the same on every series, or None."""
    found = _range(type_name, attribute)
    return tuple(found) if isinstance(found, list) else None


def ranges_on_series(type_name: str, series: str) -> dict:
    """Returns {attribute: (lowest, highest)} of the type `type_name` on
    `series`, of each attribute whose range differs by series and is
    checked there."""
    table = _table()
    found = {}
    for attributes in (table[_COMMON], table.get(type_name, {})):
        for attribute, by_series in attributes.items():
            if isinstance(by_series, dict):
                if series in by_series:
                    found[attribute] = tuple(by_series[series])
                else:
                    found.pop(attribute, None)
            else:
                # A type's own range on every series replaces a common one.
                found.pop(attribute, None)
    return found
