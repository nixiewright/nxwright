"""What a checkout of nxwright must carry itself, as nxwright is meant to be
published as a repository of its own, apart from the one it is written in."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CheckoutTest(unittest.TestCase):

    def test_text_files_are_checked_out_with_lf(self):
        # Git for Windows, and GitHub's Windows runners, check text files out
        # with CRLF unless an attribute keeps LF. The demo's tests compare its
        # source folder byte for byte with what extracting writes, in LF.
        rules = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
        self.assertIn("* text=auto eol=lf", rules)


if __name__ == "__main__":
    unittest.main()
