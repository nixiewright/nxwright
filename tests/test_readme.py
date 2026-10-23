"""The README's nxlang examples, which tools/readme.py writes from the sections
of the Switch to nxlang panel (language/nxlang_samples.py)."""
import unittest

from nxwright.language.nxlang_samples import SECTIONS
from tools.readme import END, README, START, examples_block, with_examples


class ReadmeTest(unittest.TestCase):

    def test_the_readme_examples_are_up_to_date(self):
        text = README.read_text(encoding="utf-8")
        self.assertEqual(with_examples(text), text,
                         "the README's nxlang examples are out of date: run "
                         "`python -m tools.readme` from nxwright's folder")

    def test_the_rest_of_the_file_is_left_as_it_is(self):
        text = "# Title\n\nBefore.\n\n%s\nold examples\n%s\n\nAfter.\n" % (START, END)
        self.assertEqual(with_examples(text),
                         "# Title\n\nBefore.\n\n%s\n\nAfter.\n" % examples_block())

    def test_a_file_without_the_markers_is_refused(self):
        for text in ("# Title\n", "%s\n%s\n" % (END, START)):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "no block of nxlang examples"):
                    with_examples(text)

    def test_every_section_is_in_the_block(self):
        block = examples_block()
        for section in SECTIONS:
            with self.subTest(section=section.key):
                self.assertIn("### %s" % section.heading, block)
                self.assertIn(section.nxlang[0][1].splitlines()[0], block)
        # The panel's own words after a section are left out.
        self.assertNotIn("When you switch", block)


if __name__ == "__main__":
    unittest.main()
