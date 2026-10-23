"""Writes the nxlang examples into nxwright's README.md, from the sections the
Switch to nxlang panel shows (nxwright/language/nxlang_samples.py), and its
list of what else nxlang lets you do, so that the two stay in step. Only the
block between the README's two markers is written; the rest of the file is
edited by hand.

Run it from nxwright's folder after changing the sections or the list:

    python -m tools.readme

tests/test_readme.py fails while the README's block is out of date.
"""
from pathlib import Path

from nxwright.language.nxlang_samples import MORE_FEATURES, SECTIONS

README = Path(__file__).resolve().parent.parent / "README.md"
START = ("<!-- nxlang-examples: start (written by `python -m tools.readme`; "
         "edit nxwright/language/nxlang_samples.py instead) -->")
END = "<!-- nxlang-examples: end -->"


def examples_block() -> str:
    """The block of examples, markers included: each section's heading and
    words, then its code, strict Nextion's and nxlang's side by side in a
    two-column table, or nxlang's alone; then what else nxlang lets you do,
    as a list. A section's `after` words are the panel's own, and left
    out."""
    parts = [START, ""]
    for section in SECTIONS:
        parts += ["### %s" % section.heading, "", section.words, ""]
        if section.strict:
            parts += ["<table>", "<tr><th>Strict Nextion</th><th>nxlang</th></tr>",
                      "<tr>", "<td>", "", _fenced(section.strict), "", "</td>",
                      "<td>", "", _fenced(section.nxlang), "", "</td>", "</tr>", "</table>", ""]
        else:
            parts += [_fenced(section.nxlang), ""]
    parts += ["### And more", "", "nxlang also lets you:", ""]
    parts += ["- %s" % item for item in MORE_FEATURES] + ["", END]
    return "\n".join(parts)


def with_examples(text: str) -> str:
    """Returns `text`, a README, its block of examples written anew, the rest
    as it is. Raises ValueError when it has not the two markers, in order."""
    start = text.find(START)
    end = text.find(END)
    if start < 0 or end < start:
        raise ValueError("README.md has no block of nxlang examples: it needs the line\n%s\n"
                         "then, below it, the line\n%s" % (START, END))
    return text[:start] + examples_block() + text[end + len(END):]


def _fenced(files: tuple) -> str:
    """A side's files as one block of code, each file under a comment giving
    its path when there are several, as the panel shows them."""
    if len(files) == 1:
        code = files[0][1]
    else:
        code = "\n".join("// %s\n%s" % (path, text) for path, text in files)
    return "```\n%s```" % (code if code.endswith("\n") else code + "\n")


def main():
    text = README.read_text(encoding="utf-8")
    written = with_examples(text)
    if written == text:
        print("README.md's nxlang examples are up to date")
        return
    README.write_text(written, encoding="utf-8", newline="\n")
    print("Wrote README.md's nxlang examples")


if __name__ == "__main__":
    main()
