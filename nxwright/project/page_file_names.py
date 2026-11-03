"""A page's name in the names of its files: a source folder's
`pages/<name>.page.toml` and `pages/<name>.nx`, and a dump's
`pages/NN-<name>.txt`.

The Nextion Editor allows a page's name characters that Windows refuses in
a file name, such as `:` (ResearchNotes/object-names.md). So a file name
writes them percent-encoded, as URLs do: `%` then the character's two
hexadecimal digits, `%3A` for `:`. `%` itself is encoded too, so that every
file name gives back one name, and so is a control character. Every other
character, a space among them, is written as it is, so a page of a plain
name has the file names it always had. The page `a:b` has the file
`pages/a%3Ab.page.toml`.
"""

# The characters Windows refuses in a file name, and `%`, which starts an
# encoded character. Control characters are encoded as well.
_ENCODED = set('%\\/:*?"<>|')


def page_file_stem(name: str) -> str:
    """Returns the page `name` as its files' names give it, without their
    suffix: `a%3Ab` for `a:b`."""
    return "".join("%%%02X" % ord(character)
                   if character in _ENCODED or ord(character) < 0x20 else character
                   for character in name)


def page_of_file_stem(stem: str) -> str:
    """Returns the page's name that a file name `stem`, without its suffix,
    gives: `a:b` for `a%3Ab`. A `%` that two hexadecimal digits do not follow
    stands for itself, as no file name this module writes has one."""
    out, at = [], 0
    while at < len(stem):
        digits = stem[at + 1:at + 3]
        if stem[at] == "%" and len(digits) == 2 and all(c in "0123456789ABCDEFabcdef"
                                                        for c in digits):
            out.append(chr(int(digits, 16)))
            at += 3
        else:
            out.append(stem[at])
            at += 1
    return "".join(out)
