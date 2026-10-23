"""The files on a screen's SD cards, as running code holds them: reading and
writing one, on a card given a folder of the computer (sd_cards.py) or on
the card the test machine keeps in memory (read_card_file,
write_card_file); and which data record holds which data file, and which
are shut out of theirs (DATA_FILES_HELD, DATA_RECORDS_SHUT_OUT).

Also a data record opening its file as its page opens, and the values that
follow from the file (open_data_record, data_record_values). They read a
component's attributes from the machine's values by their own names
(component_attributes), as the simulation does too.

The test machine (editor_machine.py) and the simulation (simulation.py) keep
these records in their values; the data file's own format is data_files.py's."""
import os

from nxwright.drawing.data_record_drawing import table_layout
from nxwright.drawing.page_drawing import inside_box
from nxwright.testing.data_files import data_file_for
from nxwright.testing.sd_cards import CardRefusal

# The data files the data records hold, {file key: (page, data record)}
# (held_file_key): the first record to open a file holds it, until code
# changes that record's `path`.
DATA_FILES_HELD = "data files held"
# The most data files the data records hold at once, across pages. In the
# Nextion Editor's simulator, a record finding that many held by others
# opened nothing, as if its file were held.
MOST_DATA_FILES_HELD = 8
# The data records shut out of their file, {(page, data record): True}: they
# could not open it (opening_refusal), and have opened no file since, so
# they read no records from it, though it may be free now (is_shut_out).
DATA_RECORDS_SHUT_OUT = "data records shut out"
# The data records whose `path` code has set, {(page, data record): True}.
# One whose `init` is 1 opens no file until then (opens_no_file).
DATA_RECORDS_GIVEN_A_PATH = "data records given a path"


def read_card_file(cards, path: str, card_values: dict):
    """Returns the bytes of the file `path` on an SD card: on a card given a
    folder, when `cards` (sd_cards.FolderCards, or None) has it, or else on
    the card in memory, the "file contents" of `card_values`. None when it
    is missing. Raises CardRefusal or OSError, as the cards and the disk
    refuse."""
    if cards is not None and cards.owns(path):
        return cards.read(path) if cards.find_file(path) else None
    return card_values.get("file contents", {}).get(path)


def write_card_file(cards, path: str, content: bytes, card_values: dict):
    """Writes `content` as the file `path` on an SD card, where
    read_card_file reads it, made first when it is missing. Raises
    CardRefusal or OSError, as the cards and the disk refuse."""
    if cards is not None and cards.owns(path):
        cards.new_file(path, len(content))
        cards.write(path, content)
    else:
        card_values.setdefault("file contents", {})[path] = content


def held_file_key(cards, path: str) -> str:
    """Returns the key a data record holds the file `path` under: the file
    the card finds for it. On a card given a folder (sd_cards.FolderCards),
    that is the file of the computer, so two spellings the folder reads as
    one file are one key; on the card in memory, the path as "file
    contents" keeps it."""
    if cards is not None and cards.owns(path):
        try:
            return os.path.normcase(os.path.normpath(cards.local(path)))
        except CardRefusal:
            return path     # a path leaving its card's folder, which nothing opens
    return path


def file_holder(cards, path: str, card_values: dict):
    """Returns (page, data record) of the record holding the file `path`, or
    None, as `card_values` record them (DATA_FILES_HELD)."""
    return card_values.get(DATA_FILES_HELD, {}).get(held_file_key(cards, path))


def opening_refusal(cards, path: str, card_values: dict, holder: tuple) -> str:
    """Returns why `holder`, (page, data record), may not open the file
    `path`: another record holds it, or other records hold
    MOST_DATA_FILES_HELD files. Returns "" when it may: it holds the file
    already, or the path is empty, which opens nothing to hold."""
    owner = file_holder(cards, path, card_values)
    if owner not in (None, holder):
        return "another data record holds it"
    held_by_others = [other for other in card_values.get(DATA_FILES_HELD, {}).values()
                      if other != holder]
    if path and owner is None and len(held_by_others) >= MOST_DATA_FILES_HELD:
        return ("data records hold %d files already, the most the Nextion Editor's "
                "simulator opens at once" % MOST_DATA_FILES_HELD)
    return ""


def hold_file(cards, path: str, card_values: dict, holder: tuple):
    """Has `holder`, (page, data record), hold the file `path`, letting go of
    any other file it held. An empty path, which code may set later, is
    held by none, so that records waiting for theirs shut no one out, as
    the Editor's simulator showed: two records of no path both showed
    "File Lost:", neither answering 0x06."""
    let_go_of_files(card_values, holder)
    if path:
        card_values.setdefault(DATA_FILES_HELD, {})[held_file_key(cards, path)] = holder


def let_go_of_files(card_values: dict, holder: tuple):
    """Has `holder`, (page, data record), let go of the file it held."""
    held = card_values.get(DATA_FILES_HELD, {})
    for key in [key for key, owner in held.items() if owner == holder]:
        del held[key]


def shut_out(card_values: dict, holder: tuple):
    """Notes that `holder`, (page, data record), could not open its file
    (opening_refusal, DATA_RECORDS_SHUT_OUT)."""
    card_values.setdefault(DATA_RECORDS_SHUT_OUT, {})[holder] = True


def let_in(card_values: dict, holder: tuple):
    """Notes that `holder`, (page, data record), opened its file, or may try
    a new one, and so is shut out of none."""
    card_values.get(DATA_RECORDS_SHUT_OUT, {}).pop(holder, None)


def given_a_path(card_values: dict, holder: tuple):
    """Notes that code set the `path` of `holder`, (page, data record)
    (DATA_RECORDS_GIVEN_A_PATH)."""
    card_values.setdefault(DATA_RECORDS_GIVEN_A_PATH, {})[holder] = True


def opens_no_file(attributes: dict, card_values: dict, holder: tuple) -> bool:
    """Whether `holder`, (page, data record), of `attributes`, opens no file:
    its `init` is 1, and code has not set its `path` yet. The Nextion
    Editor's simulator showed such a record's titles alone, `qty` 0, as
    its page opened, made no missing file, and let another record open
    the file. Its methods counted as done, and changed nothing. Once code
    set its `path`, even to the same file, it worked as at 0. Not seen: a
    record of local scope, whose `path` goes back to its page file's as its
    page opens again. Here it opens the file then, as code set its `path`
    once."""
    return attributes.get("init", 0) == 1 and \
        holder not in card_values.get(DATA_RECORDS_GIVEN_A_PATH, {})


def open_data_record(record: str, values, card_values: dict, cards, holder: tuple,
                     codec) -> tuple:
    """Opens the data record `record`'s data file as its page opens, and
    sets its `qty`, `txt`, `maxval_y`, and `maxval_x` in `values`, where its
    attributes are, from the file (data_record_values). A missing file is
    made when `mode` is 1. One the folder will not give is left as it is,
    and the table shows no records. The record, `holder`, (page, data
    record), holds the file it opened; a file it may not open
    (opening_refusal) it does not, and is shut out of it. One that opens no
    file (opens_no_file) shows no records, and holds none. `card_values`
    hold the card in memory and the holdings, `cards` the cards given
    folders. Returns (whether it was shut out, notes of what could not be
    opened, read, or made)."""
    attributes = component_attributes(record, values)
    data_file, notes = None, []
    if not opens_no_file(attributes, card_values, holder):
        data_file, notes = _open_file(record, attributes, card_values, cards, holder)
    for attribute, value in data_record_values(record, values, data_file, codec).items():
        values["%s.%s" % (record, attribute)] = value
    return holder in card_values.get(DATA_RECORDS_SHUT_OUT, {}), notes


def _open_file(record: str, attributes: dict, card_values: dict, cards, holder: tuple) -> tuple:
    """Opens the file of the data record `record`, of `attributes`, for
    open_data_record. Returns (the data file, or None, notes)."""
    path = attributes.get("path", "")
    data_file, notes = None, []
    refusal = opening_refusal(cards, path, card_values, holder)
    if refusal:
        shut_out(card_values, holder)
        notes.append("%s cannot open %s: %s" % (record, path, refusal))
        return data_file, notes
    let_in(card_values, holder)
    try:
        found = read_card_file(cards, path, card_values)
    except (CardRefusal, OSError) as error:
        notes.append("%s cannot read %s: %s" % (record, path, error))
    else:
        data_file = data_file_for(attributes, found)
        if found is None and data_file is not None:
            try:
                write_card_file(cards, path, data_file.to_bytes(), card_values)
            except (CardRefusal, OSError) as error:
                notes.append("%s cannot make %s: %s" % (record, path, error))
    if data_file is not None:
        hold_file(cards, path, card_values, holder)
    return data_file, notes


def is_shut_out(cards, path: str, card_values: dict, holder: tuple) -> bool:
    """Whether `holder`, (page, data record), of the `path` it names, is
    shut out of that file: it could not open it (opening_refusal), and does
    not hold it now, though it may be free."""
    return holder in card_values.get(DATA_RECORDS_SHUT_OUT, {}) and \
        file_holder(cards, path, card_values) != holder


def component_attributes(component: str, values: dict) -> dict:
    """Returns the attributes of `component` in `values`, which name them
    after it ("d0.val"), by their own names ("val")."""
    prefix = component + "."
    return {key[len(prefix):]: value for key, value in values.items() if key.startswith(prefix)}


def data_record_values(record: str, values: dict, data_file, codec) -> dict:
    """Returns the attributes of the data record `record`, whose values
    `values` hold by name, that follow from its data file `data_file`, or
    None for none: `qty`, the records it holds; `txt`, the chosen record's
    text (`val`), or nothing, `val` -1, when `val` names none, as after a
    delete or a clear() left it past the last record in the Editor's
    simulator; and
    how far its table scrolls, `maxval_y` and `maxval_x`
    (data_record_drawing.table_layout)."""
    attributes = component_attributes(record, values)
    records = data_file.records() if data_file is not None else []
    chosen = attributes.get("val", -1)
    found = {"qty": len(records)}
    if isinstance(chosen, int) and 0 <= chosen < len(records):
        found["txt"] = codec.decode_keeping_bytes(records[chosen])
    else:
        found.update(val=-1, txt="")
    layout = table_layout(attributes, len(records), inside_box(attributes))
    found.update(maxval_y=layout.most_y, maxval_x=layout.most_x)
    return found
