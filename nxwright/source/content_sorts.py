"""The four sorts of the things in a project that nxwright does not know
(unknown_content.py), by what the source folder does with each. Kept apart,
so that page_source.py, which unknown_content.py imports, can give them too.
"""
KEPT, WRITTEN_OTHERWISE, MAY_BE_LOST, CANNOT_BE_KEPT = (
    "kept exactly", "written otherwise", "may be lost", "cannot be kept")
