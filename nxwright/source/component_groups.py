"""Groups of components, as the Editor's design view makes them.

A group is the components of a page that share both `groupid0` and
`groupid1`, `groupid0` not 0. In the Editor, selecting a member tints every
member of its group, and moving one moves them all. Its Create Group gives
the selected components a new pair of two large numbers. nxwright gives a
new group the smallest `groupid0` the page does not use, and `groupid1` 0,
which the Editor takes as a group too, and which reads better in a page
file.
"""
import itertools

# The `groupid0` of a component in no group.
NO_GROUP = 0


def group_of(values: dict):
    """Returns the group of a component of `values`, as "groupid0/groupid1",
    or None when it is in none."""
    first = values.get("groupid0", NO_GROUP)
    if first == NO_GROUP:
        return None
    return "%d/%d" % (first, values.get("groupid1", 0))


def new_groupid0(components: list) -> int:
    """Returns the smallest `groupid0` from 1 that none of `components`, the
    values of a page's components, uses."""
    used = {values.get("groupid0") for values in components}
    return next(number for number in itertools.count(1) if number not in used)
