"""The file stream (tft/component_types/file_stream.py), a type P and E
have and T and K have not: its memory, buffer, and entries on P, its block
in its page's load section, its calls in code, and what its rules cover.

Each test gives the function it checks that function's own input: a page
object of a probe's components (tools/tft/probing/file_stream_probes.py), made
by nxwright's page reader, a Project of the facts it reads, and the
object's place, read from the probe's table (tests/tft/unit_inputs.py), where
its buffer lies among them. It compares the result with one piece of the
probe's fixtures, which the probe runner wrote once the probe matched the
Nextion Editor's file (tests/tft/p_components.py). What the frame writes across
objects, such as the head of its memory, the total of its page's buffers,
a later page's room over its memory, and its close at the end of its page's
unload event, is left to the frame's tests, and compared until then by the
sample of whole files (tests/tft/test_whole_files.py).
"""
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing import file_stream_probes, p_probes
from nxwright.tft.statements import CodePlace, encode_line
from tools.tft.probing.text_probes import text_component
from tests.tft.p_components import PTypePieces
from tests.tft.t_components import LoadSectionPieces
from tests.tft.unit_inputs import page, project_of


def _context() -> dict:
    """Returns the context of a line in page0's Touch Release event, on a P
    page of a text and a file stream, made in memory."""
    project = project_of(page(text_component(), file_stream_probes.file_stream_component(),
                              series="P", code="on page0.up:\n  sys0=1\n"),
                         series="P", fonts=0)
    return next(need.context for need in project_needs(project)
                if need.kind == "code" and need.subject == "event")


class PPiecesTest(PTypePieces, LoadSectionPieces, unittest.TestCase):
    """Each file stream of each of its probes on P that keeps its whole user
    code, at its type's functions on P, against the probe's pieces: its
    values after the 4 bytes of its record's head its memory starts with
    (P_HEAD_SIZE), its val, qty, and en, its methods' values, its buffer's
    size, 10752, and where its buffer lies, which the probe's table gives;
    its entries, each method's giving its byte above its owner's ID and
    page; and its block in its page's load section, `init` and its ID. One
    file stream at its defaults, and two beside a text, whose second's
    buffer follows the first's."""

    TYPE = "file-stream"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-file-stream-")]
    COUNT = 3


class CodeTest(unittest.TestCase):

    def test_its_entries_and_calls(self):
        # After the page's 33 entries and a text's 41: its val is its 8th,
        # and a call is its method's operand, then its arguments.
        project = project_of(page(text_component(), file_stream_probes.file_stream_component(),
                                  series="P"), series="P")
        place = CodePlace(0, "page0", "up")
        first = 33 + 41
        self.assertEqual(encode_line("sys0=fs0.val", place, CompileContext(project)),
                         b"\x05\x00\x00\x00\x00=\x01" + (first + 7).to_bytes(4, "little"))
        self.assertEqual(encode_line("fs0.read(t0.txt,sys0+1,2)", place, CompileContext(project)),
                         b"\x01" + (first + 11).to_bytes(4, "little") + b"(\x01"
                         + (33 + 28).to_bytes(4, "little") + b",\x05\x00\x00\x00\x00+1,2)")
        self.assertEqual(encode_line('fs0.open("sd0/a.txt")', place, CompileContext(project)),
                         b"\x01" + (first + 10).to_bytes(4, "little") + b'("sd0/a.txt")')


class RuleTest(unittest.TestCase):

    def test_on_p_and_e_alone(self):
        rules = matched_rules()
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("type", "file-stream", series=series)
                self.assertEqual(unmatched([need], rules), [])
        for series in ("T", "K"):
            with self.subTest(series):
                need = Need("type", "file-stream", series=series)
                self.assertEqual(unmatched([need], rules), [need])

    def test_its_values(self):
        # Its en and its molloc, of any value.
        rules = matched_rules()

        def need(name: str, value: int) -> Need:
            return Need("attribute", "file-stream." + name, value.to_bytes(4, "little"),
                        series="P")
        for name, value in (("en", 1), ("en", 2), ("val", 5), ("molloc", 1)):
            with self.subTest(name):
                self.assertEqual(unmatched([need(name, value)], rules), [])

    def test_its_calls(self):
        # Its calls in an event, on P and E, a number or a text where a path
        # or a txt goes among them; not a method set, nor its qty, nor
        # another number of arguments.
        rules, context = matched_rules(), _context()
        for line in ('fs0.open("sd0/a.txt")', "fs0.open(t0.txt)", "fs0.read(t0.txt,sys0+1,2)",
                     "fs0.write(t0.txt,0,3)", "fs0.close()", 'fs0.find("sd0/a.txt")',
                     "sys0=fs0.open", "fs0.val=5", "fs0.open(5)", "fs0.find(sys0)",
                     'fs0.read("a",0,3)', "fs0.write(sys0,0,3)"):
            for series in ("P", "E"):
                with self.subTest(line, series=series):
                    need = Need("code", "event", line, context=context, series=series)
                    self.assertEqual(unmatched([need], rules), [])
        for line in ("fs0.open=1", "fs0.qty=3", "fs0.close(1)",
                     "fs0.read(t0.txt, 0, 3)", "fs9.close()", "t0.close()"):
            with self.subTest(line):
                need = Need("code", "event", line, context=context, series="P")
                self.assertEqual(unmatched([need], rules), [need])


if __name__ == "__main__":
    unittest.main()
