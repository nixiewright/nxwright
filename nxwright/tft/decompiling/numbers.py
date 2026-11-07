"""The numbers a file's code gives its commands, system variables, and
colours, by its series and the version of the Nextion Editor that wrote it.

Code names a command by its number and its table, and a system variable or
a colour by its table and its number (statements.py). The compile's tables
give the numbers of the Nextion Editor 1.68.2. An older release lacks some
of them. Each command above one it lacks, in the same table, is then one
less for each, and so is each system variable above a lacked one
(ResearchNotes/tft/older-editors.md, Where each change begins):

  - T and K lack spstr before 1.61.1, and getv before 1.65.0;
  - P lacks spstr before 1.61.1; xnum, cuts, cfguart, and the system
    variable scache before 1.63.1; and beep, meup, gets, sets, getv, and
    beepset, with two commands nxwright has no name for, 0x0b of table 4 and
    0x1f of table 8, before 1.65.0;
  - F lacks xnum, cuts, gets, and sets before 1.65.0, beep before 1.67.1,
    and cfgpio and the GPIO pins' system variables before 1.68.1. Before
    1.68.1, its other system variables and its colours take T's numbers,
    but lowpower and portbusy, which take F's.

OLDER gives these, by series, as ranges that each begin at the release
where probes of every release show the change begins. A series' first
range holds for every older release too. A series and version it does not
name reads by the compile's numbers. The compile knows nothing of these:
the decompiler derives an older version's numbers from 1.68.2's.

A decoder that checks the blocks the Nextion Editor adds, such as a
timer's timerset, writes them with the compile, then renumbers them as the
file's version writes them (as_written).

The "S " blocks that start a timer's code are numbered too. The Nextion
Editor 1.68.2 counts them from 1. Its earlier releases give them large
numbers that are not a count, such as 0x18b5b, then 0x18b65, on 1.65.1,
1.67.1, and 1.68.1 alike. So a file before 1.68.2 has its own
(counts_labels).
"""
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from nxwright.tft.statements import COLOURS, COMMAND_TAG, SYSTEM_VARIABLES, series_commands


@dataclass(frozen=True)
class OlderNumbers:
    """How the files of a series in a range of versions number their code,
    beside 1.68.2's: `lacked`, the commands they lack, each as (table,
    number) on 1.68.2, as some have no name in nxwright; `lacked_operands`, the
    system variables they lack, each as (table, number) on 1.68.2;
    `operands_as`, the series whose numbers their system variables and
    colours take, or None for their own series'; and `own`, the system
    variables they number as their own series does all the same."""
    lacked: frozenset
    lacked_operands: frozenset = frozenset()
    operands_as: Optional[str] = None
    own: frozenset = frozenset()


# The first version that counts the "S " blocks from 1.
COUNTED_LABELS = (1, 68, 2)
# The commands and system variables each range lacks, as (table, number) on
# 1.68.2.
_GETV_T, _GETV_K, _SPSTR = (4, 0x1a), (4, 0x1e), (8, 0x03)
# P's of 1.63.1 to 1.63.3: 0x0b, beep, meup, gets, sets, and getv of table
# 4, and 0x1f and beepset of table 8.
_P_BEFORE_1_65 = frozenset({(4, 0x0b), (4, 0x13), (4, 0x14), (4, 0x1b), (4, 0x1c), (4, 0x25),
                            (8, 0x1f), (8, 0x22)})
# P's before 1.63.1 also: xnum, cuts, and cfguart, and the system variable
# scache.
_P_BEFORE_1_63 = _P_BEFORE_1_65 | {(4, 0x10), (4, 0x1d), (8, 0x23)}
_SCACHE = frozenset({(8, 0x11)})
# F's of 1.67.1: cfgpio; before 1.67.1 also beep; before 1.65.0 also xnum,
# gets, sets, and cuts.
_F_BEFORE_1_68 = frozenset({(8, 0x0d)})
_F_BEFORE_1_67 = _F_BEFORE_1_68 | {(4, 0x11)}
_F_BEFORE_1_65 = _F_BEFORE_1_67 | {(4, 0x0e), (4, 0x19), (4, 0x1a), (4, 0x1b)}
_F_OWN = frozenset({"lowpower", "portbusy"})
# By series: (the first version not in a range, the numbers of the range),
# oldest first. A range holds from the version that ends the one before it.
OLDER = {
    "T": (((1, 61, 1), OlderNumbers(frozenset({_GETV_T, _SPSTR}))),
          ((1, 65, 0), OlderNumbers(frozenset({_GETV_T})))),
    "K": (((1, 61, 1), OlderNumbers(frozenset({_GETV_K, _SPSTR}))),
          ((1, 65, 0), OlderNumbers(frozenset({_GETV_K})))),
    # P's spstr is 0x04 of table 8.
    "P": (((1, 61, 1), OlderNumbers(_P_BEFORE_1_63 | {(8, 0x04)}, _SCACHE)),
          ((1, 63, 1), OlderNumbers(_P_BEFORE_1_63, _SCACHE)),
          ((1, 65, 0), OlderNumbers(_P_BEFORE_1_65))),
    "F": (((1, 65, 0), OlderNumbers(_F_BEFORE_1_65, operands_as="T", own=_F_OWN)),
          ((1, 67, 1), OlderNumbers(_F_BEFORE_1_67, operands_as="T", own=_F_OWN)),
          ((1, 68, 1), OlderNumbers(_F_BEFORE_1_68, operands_as="T", own=_F_OWN))),
}


def commands(series: str, version: tuple) -> dict:
    """Returns {name: (number, table)} of each command a file of `series`
    and of the Nextion Editor `version` has, as that version numbers it."""
    return dict(_commands(series, _older(series, version)))


def operands(series: str, version: tuple) -> dict:
    """Returns {name: (table, number)} of each system variable and colour a
    file of `series` and of the Nextion Editor `version` has, as that
    version numbers it."""
    older = _older(series, version)
    if older is None:
        return {**SYSTEM_VARIABLES[series], **COLOURS[series]}
    if older.operands_as is not None:
        found = {**SYSTEM_VARIABLES[older.operands_as], **COLOURS[older.operands_as]}
        found.update({name: SYSTEM_VARIABLES[series][name] for name in older.own})
        return found
    return {name: (table, number - sum(1 for table_of, below in older.lacked_operands
                                       if table_of == table and below < number))
            for name, (table, number) in {**SYSTEM_VARIABLES[series], **COLOURS[series]}.items()
            if (table, number) not in older.lacked_operands}


def as_written(block: bytes, series: str, version: tuple) -> bytes:
    """Returns `block`, which the compile writes, with its command's number
    as a file of `series` and of the Nextion Editor `version` writes it. A
    block that is not a command's, or a version that numbers code as 1.68.2
    does, gives `block` as it is. So does a command the version lacks,
    which the decoder checking it then finds missing from the file."""
    older = _older(series, version)
    if older is None or len(block) < 3 or block[0] != COMMAND_TAG:
        return block
    renumbered = _renumbered(series, older).get((block[1], block[2]))
    if renumbered is None:
        return block
    return bytes([COMMAND_TAG, *renumbered]) + block[3:]


def counts_labels(version: tuple) -> bool:
    """Returns whether a file of the Nextion Editor `version` counts its
    "S " blocks from 1, as the compile does. An older file's "S " blocks
    have numbers of its own, which a decoder takes from the file."""
    return version >= COUNTED_LABELS


def _older(series: str, version: tuple) -> Optional[OlderNumbers]:
    """Returns the OlderNumbers of a file of `series` and of the Nextion
    Editor `version`, or None when it numbers code as 1.68.2 does."""
    for first, older in OLDER.get(series, ()):
        if version < first:
            return older
    return None


@lru_cache(maxsize=None)
def _renumbered(series: str, older: OlderNumbers) -> dict:
    """Returns {(number, table) on 1.68.2: (number, table) as `older`
    numbers it} of each command of `series` that `older` has."""
    newest = dict(_commands(series, None))
    return {newest[name]: key for name, key in _commands(series, older)}


@lru_cache(maxsize=None)
def _commands(series: str, older: Optional[OlderNumbers]) -> tuple:
    """Returns ((name, (number, table)), ...) of the commands of `series`, as
    numbered by `older`, or by 1.68.2 when it is None. A command above one
    `older` lacks, in the same table, is one less for each."""
    lacked = frozenset() if older is None else older.lacked
    return tuple((name, (command.number - sum(1 for table, below in lacked
                                              if table == command.table
                                              and below < command.number), command.table))
                 for name, command in series_commands(series).items()
                 if command.number is not None and (command.table, command.number) not in lacked)
