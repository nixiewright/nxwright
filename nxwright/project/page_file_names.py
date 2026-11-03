"""A page's name in the names of its files. The files are a source folder's
`pages/<name>.page.toml` and `pages/<name>.nx`, and a dump's
`pages/NN-<name>.txt`.

The Nextion Editor allows characters in a page's name that Windows refuses
in a file name, such as `:`. In a file's name, these characters are
percent-encoded, as in URLs: `%`, then the character's two hexadecimal
digits, such as `%3A` for `:`. Control characters are encoded too. `%`
itself is encoded as well, so that each file name gives back exactly one
page name. Every other character, including a space, is written as it is.
A page with a plain name therefore keeps the file names it always had. For
example, the page `a:b` has the file `pages/a%3Ab.page.toml`.
"""

# The characters that Windows refuses in a file name, and `%`, which starts
# an encoded character. Control characters are encoded too, but are not
# listed here.
_ENCODED = set('%\\/:*?"<>|')


def page_file_stem(name: str) -> str:
    """Returns the page name `name` as it appears in the names of the page's
    files, without their suffix, such as `a%3Ab` for `a:b`."""
    return "".join("%%%02X" % ord(character)
                   if character in _ENCODED or ord(character) < 0x20 else character
                   for character in name)


def page_of_file_stem(stem: str) -> str:
    """Returns the page name that the file name `stem`, without its suffix,
    gives, such as `a:b` for `a%3Ab`. A `%` that is not followed by two
    hexadecimal digits is kept as it is. page_file_stem never writes a `%`
    without two hexadecimal digits after it."""
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
