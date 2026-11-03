"""The four sorts of the things in a project that nxwright does not know
(unknown_content.py). A thing's sort decides what the source folder does
with it.

The sorts are defined here, not in unknown_content.py, because
unknown_content.py imports page_source.py, and page_source.py needs the
sorts too.
"""
KEPT, WRITTEN_OTHERWISE, MAY_BE_LOST, CANNOT_BE_KEPT = (
    "kept exactly", "written otherwise", "may be lost", "cannot be kept")
