"""The sections of the panel explaining the switch to nxlang, the nxwright
language, in VS Code (editors/vscode/src/nxlangPanel.ts), that show code: what
nxlang adds, each with how a person writes the same thing in strict Nextion
syntax, when there is a usual way, beside how they write it in nxlang.

The samples are written by hand, as people write code, not compiled. Each
side of each section builds, in a source folder of its language, as a page
of its own: the tests build both (tests/test_nxlang_samples.py), so a sample
that stops building fails them. Each page's components are variables and
hotspots, which need no font, as a folder in utf-8 starts with none.

Also the panel's list of what else nxlang lets you do (MORE_FEATURES), which
README.md shows too (tools/readme.py).
"""
from dataclasses import dataclass



@dataclass(frozen=True)
class Section:
    """A section of the panel with code. `key` is its page's name; `words`
    come before the code, `after` after it, each in plain text with `code`
    in backticks. `strict` and `nxlang` are its files, by their path in the
    folder, the page's .nx file first; `strict` is empty when strict Nextion
    has no usual way to do the same. `components` are the page's, as
    (name, kind): "number" or "text" for a variable, "hotspot" for an
    invisible button."""
    key: str
    heading: str
    words: str
    strict: tuple
    nxlang: tuple
    components: tuple
    after: str = ""


SECTIONS = (
    Section(
        "functions", "Functions",
        "Strict Nextion has no functions. To reuse code, you usually put it in a hidden "
        "button's event, pass values through variables, and click the button. In nxlang, you "
        "write a function and call it.",
        (("pages/functions.nx", """\
// clampFn is a hidden button:
// it clamps va0 to va1, into va2.
on clampFn.down:
  if (va0.val > va1.val) {
    va2.val = va1.val
  } else {
    va2.val = va0.val
  }

on save.up:
  va0.val = value.val
  va1.val = limit.val
  click clampFn, 1
  result.val = va2.val
"""),),
        (("pages/functions.nx", """\
function clamp(value: number, limit: number) -> number:
  var result = value
  if (value > limit) {
    result = limit
  }
  return result

on save.up:
  result.val = clamp(value.val, limit.val)
"""),),
        (("value", "number"), ("limit", "number"), ("result", "number"), ("va0", "number"),
         ("va1", "number"), ("va2", "number"), ("clampFn", "hotspot"), ("save", "hotspot"))),
    Section(
        "calculations", "Calculation order and parentheses",
        "Strict Nextion calculates from left to right, so `a + b * 2` means `(a + b) * 2`, "
        "and it does not accept parentheses. You often need an extra line and a spare "
        "variable. nxlang calculates the way C and most languages do, multiplication first, "
        "and accepts parentheses.",
        (("pages/calculations.nx", """\
on save.up:
  // total = first + (second * 2)
  sys0 = second.val * 2
  total.val = first.val + sys0
  // average = (first + second) / 2
  average.val = first.val + second.val / 2
"""),),
        (("pages/calculations.nx", """\
on save.up:
  // total = first + (second * 2)
  total.val = first.val + second.val * 2
  // average = (first + second) / 2
  average.val = (first.val + second.val) / 2
"""),),
        (("first", "number"), ("second", "number"), ("total", "number"), ("average", "number"),
         ("save", "hotspot")),
        "When you switch, each line of your code that would calculate differently in nxlang "
        "will get parentheses, so that it keeps giving the same result."),
    Section(
        "numbers", "Numbers in text",
        "In strict Nextion, you convert a number to text with `covx` before adding it to a "
        "text. In nxlang, you add the number directly.",
        (("pages/numbers.nx", """\
on save.up:
  covx speed.val, speedText.txt, 0, 0
  label.txt = "Speed: " + speedText.txt + " mm/s"
"""),),
        (("pages/numbers.nx", """\
on save.up:
  label.txt = "Speed: " + speed.val + " mm/s"
"""),),
        (("speed", "number"), ("speedText", "text"), ("label", "text"), ("save", "hotspot"))),
    Section(
        "constants", "Constants and local variables",
        "Strict Nextion has no constants or local variables. Programs repeat literal values "
        "and use global variables to perform calculations. nxlang has named constants, "
        "which take no memory on the screen, and local variables, declared where they are "
        "needed.",
        (("pages/constants.nx", """\
on save.up:
  sys0 = first.val * 2
  if (sys0 > 1200) {
    sys0 = 1200
  }
  total.val = sys0
"""),),
        (("pages/constants.nx", """\
const LIMIT = 1200

on save.up:
  var speed = first.val * 2
  if (speed > LIMIT) {
    speed = LIMIT
  }
  total.val = speed
"""),),
        (("first", "number"), ("total", "number"), ("save", "hotspot"))),
    Section(
        "loops", "switch, break, and continue",
        "Strict Nextion has no `switch`, `break`, or `continue`. You write chains of `if` and "
        "`else if`, and use flags to stop a loop early. nxlang has all three, as in C.",
        (),
        (("pages/loops.nx", """\
on loops.load:
  total.val = 0
  var i = 0
  while (i < 10) {
    i++
    if (i == 3) {
      continue
    }
    if (i == 8) {
      break
    }
    total.val += i
  }
  switch (total.val) {
    case 0:
      label.txt = "none"
      break
    default:
      label.txt = "some"
  }
"""),),
        (("total", "number"), ("label", "text"))),
    Section(
        "sharing", "Sharing code between pages",
        "In strict Nextion, code that several pages need is copied into each page. nxlang "
        "lets you put functions in a file and include it on any page.",
        (),
        (("pages/sharing.nx", """\
include "lib/average.nx"

on sharing.load:
  total.val = average(first.val, second.val)
"""),
         ("pages/lib/average.nx", """\
// The average of two numbers, for any page including this file.
function average(a: number, b: number) -> number:
  return (a + b) / 2
""")),
        (("first", "number"), ("second", "number"), ("total", "number"))),
)

# What else nxlang lets you do, smaller than a section, as the panel's "And
# more" lists it and README.md does: each item completes "nxlang also lets
# you:", its code between backticks.
MORE_FEATURES = (
    "calculate inside a condition, as in `if (a.val + b.val > 10)`;",
    "use `!`, and mix `&&` and `||`, in a condition;",
    "write a minus in front of a value, as in `-speed.val`;",
    "test a number on its own, as in `if (flag.val)`, which is true when it is not 0;",
    "rely on `&&` and `||` to skip their right side when the left already decides, so "
    "`b != 0 && a / b > 1` never divides by 0;",
    "choose a value with `? :`, as in `t0.txt = ready.val ? \"Ready\" : \"Waiting\"`;",
    "write hexadecimal numbers as in C, such as `0x1` or `-0x10`;",
    "write `x -= a + b`, which means `x = x - (a + b)`.",
)


def panel_sections() -> list:
    """Returns each section as the panel draws it: {"key", "heading", "words",
    "strict", "nxlang", "after"}, the code of each side as one text, each
    file under a comment giving its path when the side has several, and
    "strict" empty when strict Nextion has no usual way."""
    return [{"key": section.key, "heading": section.heading, "words": section.words,
             "strict": _joined(section.strict), "nxlang": _joined(section.nxlang),
             "after": section.after}
            for section in SECTIONS]


def _joined(files: tuple) -> str:
    """The texts of `files`, ((path, text), ...): the text alone of one file,
    each under a comment giving its path of several, or "" of none."""
    if len(files) == 1:
        return files[0][1]
    return "\n".join("// %s\n%s" % (path, text) for path, text in files)
