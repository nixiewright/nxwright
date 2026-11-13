"""The Nextion Editor's version, as a project file records it.

The Nextion Editor writes the second and third numbers of its version in
bytes 9 and 36 of the manifest header each time it saves a project, and in
bytes 41 and 42 of a page's header each time it writes that page. The
Nextion Editor 1.61.2, for example, writes 0x3d, which is 61, and 2. This
was seen in the projects that each release from 1.60.1 to 1.68.2 saved.

A page that the Nextion Editor opened and saved without changing keeps the
bytes it had, so a project's pages can give older versions than its manifest
header.
"""

# The oldest version whose projects nxwright was checked with, and the version
# whose form the build writes. Each is (second number, third number).
OLDEST_VERSION = (60, 1)
CURRENT_VERSION = (68, 2)


def is_checked_version(second: int, third: int) -> bool:
    """Returns whether the version with the numbers `second` and `third` is
    from OLDEST_VERSION to CURRENT_VERSION. A version in that range that no
    release has, such as 1.62.0, counts too."""
    return OLDEST_VERSION <= (second, third) <= CURRENT_VERSION


def version_text(second: int, third: int) -> str:
    """Returns the version with the numbers `second` and `third` as text,
    such as "1.61.2"."""
    return "1.%d.%d" % (second, third)
