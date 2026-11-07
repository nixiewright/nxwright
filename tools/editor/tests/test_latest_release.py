"""The release check (tools/editor/latest_release.py): reading Nextion's
answer to the Nextion Editor's check for a newer version, and the version
nxwright is tested with (tools/editor/tested_editor.toml). It needs no
network: the answers are short ones written for the tests, in the form
Nextion's server gives, fields that each start with &*@."""
from pathlib import Path
import re
import unittest

from tools.editor import latest_release

_NXWRIGHT = Path(__file__).resolve().parents[3]


def answer(**fields) -> str:
    """Returns an answer of `fields`, in the order given, after the two
    byte order marks the server's answers start with."""
    return "\ufeff\ufeff" + "".join("&*@%s=%s" % field for field in fields.items())


class ReadAnswerTest(unittest.TestCase):

    def test_the_recorded_version(self):
        text = answer(ver="1.68.2", exeadd="http://nextion.tech/download/nextion-setup-v1-68-2.exe",
                      uptext="v1.68.2 Update List\r\n- a change")
        self.assertEqual(latest_release.check(text, "1.68.2"),
                         (0, "Nextion offers the Nextion Editor 1.68.2, the version nxwright is "
                             "tested with."))

    def test_a_newer_version_gives_its_notes(self):
        text = answer(ver="1.69.0", exeadd="http://nextion.tech/download/nextion-setup-v1-69-0.exe",
                      uptext="v1.69.0 Update List\r\n- timers changed", mesg="Hello Nextion.")
        code, said = latest_release.check(text, "1.68.2")
        self.assertEqual(code, 1)
        self.assertEqual(said, "Nextion offers the Nextion Editor 1.69.0; nxwright is tested with "
                               "1.68.2. Its release notes:\nv1.69.0 Update List\n- timers changed")

    def test_a_version_and_an_installer_that_disagree(self):
        text = answer(ver="1.69.0", exeadd="http://nextion.tech/download/nextion-setup-v1-68-2.exe")
        self.assertEqual(latest_release.check(text, "1.68.2")[0], 2)

    def test_an_answer_without_its_installer(self):
        self.assertEqual(latest_release.check(answer(ver="1.68.2"), "1.68.2")[0], 2)

    def test_an_answer_without_fields(self):
        for text in ("", "<html>Not found</html>"):
            with self.subTest(text=text):
                code, said = latest_release.check(text, "1.68.2")
                self.assertEqual(code, 2)
                self.assertIn("could not be read", said)


class TestedVersionTest(unittest.TestCase):

    def test_both_readmes_name_the_recorded_version(self):
        # nxwright's README and the Editor tool's name the version that
        # tested_editor.toml records, so that the three cannot drift apart.
        version = latest_release.tested_version()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        for readme, said in ((_NXWRIGHT / "README.md",
                              "nxwright is tested with projects saved by Nextion Editor %s."),
                             (_NXWRIGHT / "tools" / "editor" / "README.md",
                              "the Nextion Editor %s, the version nxwright is tested with.")):
            with self.subTest(readme=readme.name):
                text = readme.read_text(encoding="utf-8")
                self.assertIn(said % version, text)
                others = set(re.findall(r"tested with[^.]*?(\d+\.\d+\.\d+)", text)) - {version}
                self.assertEqual(others, set())

    def test_the_tft_documents_give_only_the_recorded_version(self):
        # These two documents give the version in several sentences, so the
        # test looks at every version in them. The only other one allowed is
        # 1.60.1, the oldest version whose files the decompile reads.
        version = latest_release.tested_version()
        for name in ("screens.md", "commands.md"):
            with self.subTest(document=name):
                text = (_NXWRIGHT / "docs" / name).read_text(encoding="utf-8")
                self.assertEqual(set(re.findall(r"\b\d+\.\d+\.\d+\b", text)), {"1.60.1", version})


if __name__ == "__main__":
    unittest.main()
