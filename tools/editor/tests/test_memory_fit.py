"""Tests of the memory probe's reasoning (memory_fit.py), on what the Editor
1.68.2's compile showed. They need neither the Editor nor pywinauto."""
import unittest

from nxwright.project.memory_table import Part, SeriesCosts, Steps, TypeCosts, read_memory_table
from tools.editor.memory_fit import fit_objects, fit_part, fit_times, read_compile, table_text


class ReadCompileTest(unittest.TestCase):

    def test_a_compile_that_succeeded(self):
        compiled = read_compile(
            "Available Memory:3584\r\nGlobal Memory:16\r\nTotal size of font:8,029\r\n"
            "Page:page0 Memory Occupied:16+20=36\r\nPage:p01 Memory Occupied:16+40=56\r\n"
            "File Check Finish\r\nCompile Successful! 0 Errors, 0 Warnings,File Size:368,840\r\n")
        self.assertEqual((compiled.memory, compiled.global_memory, compiled.pages),
                         (3584, 16, {"page0": 20, "p01": 40}))
        self.assertTrue(compiled.succeeded)
        self.assertIsNone(compiled.refusal)

    def test_its_refusals(self):
        for output, refusal in [
                ("Error:Unsupported component was found for this series device:p14.c0",
                 ("unsupported", "p14", "c0")),
                ("Error:p09.c0.staOut of range", ("out of range", "p09", "c0", "sta")),
                ("Available Memory:3584\r\nGlobal Memory:16\r\n"
                 "Page:page0 Memory Occupied:16+20=36\r\n"
                 "Error:Page:p26 Error! Memory overflow:16+4072=4088", ("overflow", "p26")),
                ("Error:Page:p013 The remaining memory is not enough to run the temporary use of "
                 "QR code(-443),please decrease the value of txt_maxl to reduce the comsuption of "
                 "the memory.", ("temporary", "p013", "QR code", 443)),
                ("Error:Too many pages.", ("other", "Error:Too many pages."))]:
            with self.subTest(refusal=refusal):
                compiled = read_compile(output + "\r\nError:Compile failed! 1 Errors, 0 Warnings,")
                self.assertEqual(compiled.refusal, refusal)
                self.assertFalse(compiled.succeeded)
        self.assertEqual(read_compile("Available Memory:3584\r\nGlobal Memory:16\r\n"
                                      "Page:page0 Memory Occupied:16+20=36\r\n"
                                      "Error:Page:p26 Error! Memory overflow:16+4072=4088")
                         .pages, {"page0": 20, "p26": 4072})


class FitPartTest(unittest.TestCase):
    """A text's costs by its txt_maxl, less an empty page's 20, on the basic
    NX4832T035, and a waveform's by its width, with one channel."""

    TEXT = {0: 12, 1: 12, 2: 12, 3: 16, 4: 16, 5: 16, 6: 16, 7: 20, 8: 20, 9: 20, 10: 20,
            11: 24, 12: 24, 40: 52, 100: 112, 1000: 1012}

    def test_a_buffer(self):
        part, constant = fit_part("txt_maxl", self.TEXT)
        self.assertEqual((part, constant), (Part("txt_maxl", 1, 1, 2, 4), 8))

    def test_a_part_spread_over_units(self):
        widths = {width: 52 + -(-(13 * width // 10) // 4) * 4
                  for width in list(range(2, 131)) + [200, 300]}
        part, constant = fit_part("w", widths)
        self.assertEqual((part, constant), (Part("w", 13, 10, 0, 4), 52))

    def test_no_cost(self):
        self.assertEqual(fit_part("h", {2: 184, 20: 184, 80: 184, 200: 184}),
                         (Part("h", 0), 184))

    def test_too_few_values_to_tell(self):
        # Two values fit a byte for each, rounded to 1 or to 2, which differ at 11.
        self.assertIsNone(fit_part("txt_maxl", {10: 20, 100: 110}))

    def test_no_rule(self):
        self.assertIsNone(fit_part("val", {0: 10, 1: 30, 2: 31, 3: 90}))


class FitObjectsTest(unittest.TestCase):

    def test_a_byte_for_each_object_rounded(self):
        # Pages of hotspots on the basic screen, which cost nothing else there.
        owns = {0: 20, 1: 20, 2: 20, 3: 20, 4: 24, 5: 24, 6: 24, 7: 24, 8: 28, 9: 28, 10: 28,
                11: 28, 12: 32}
        self.assertEqual(fit_objects(owns), (Part("", 1, 1, 0, 4), 0))

    def test_a_type_of_a_cost_of_its_own(self):
        # The same, with a type of 60 bytes: the object's byte is told apart.
        owns = {count: 72 + 60 * count + -(-(count + 1) // 4) * 4 for count in range(13)}
        self.assertEqual(fit_objects(owns), (Part("", 1, 1, 0, 4), 60))

    def test_too_few_pages_to_tell(self):
        self.assertIsNone(fit_objects({0: 20, 1: 20}))


class FitTimesTest(unittest.TestCase):
    """A waveform on the basic screen: 36 bytes, and for each channel 16 and
    its width's part."""

    @staticmethod
    def cost(width: int, channels: int) -> int:
        return 36 + channels * (16 + -(-(13 * width // 10) // 4) * 4)

    def test_channels_multiply_the_width(self):
        width = Part("w", 13, 10, 0, 4)        # fitted with one channel
        channels = Part("ch", 276)             # fitted at the default width, 200
        both = {(width_value, channels_value): self.cost(width_value, channels_value)
                for width_value in (2, 13, 100, 300) for channels_value in (2, 3, 4)}
        parts, constant = fit_times(width, channels, 200, both)
        self.assertEqual(parts, (Part("ch", 16), Part("w", 13, 10, 0, 4, "ch")))
        self.assertEqual(constant, 36)

    def test_costs_that_do_not_fit(self):
        width, channels = Part("w", 13, 10, 0, 4), Part("ch", 276)
        self.assertIsNone(fit_times(width, channels, 200, {(100, 3): 480, (100, 4): 640}))
        self.assertIsNone(fit_times(channels, width, 1, {(3, 100): 480}))


class TableTextTest(unittest.TestCase):

    def test_written_as_nxwright_reads_it(self):
        series = SeriesCosts(16, Part(bytes=1, round=4), 4, 4, 4, {
            "text": TypeCosts(8, (Part("txt_maxl", 1, 1, 2, 4),), unmeasured={"key": 255}),
            "waveform": TypeCosts(36, (Part("ch", 16), Part("w", 13, 10, 0, 4, "ch"))),
            "dual-state-button": TypeCosts(24),
            "data-record": TypeCosts(4, reserve=10752,
                                     reserve_parts=(Part("molloc", 1),)),
            "qr-code": TypeCosts(20, (Part("txt_maxl", 1, 1, 2, 4),),
                                 temporary=Steps("txt_maxl", ((0, 0), (12, 586), (32, 851)))),
            # Its path_m, when 0, reads its txt_maxl.
            "sliding-text": TypeCosts(120, (Part("txt_maxl", 1, 1, 1, 4),
                                            Part("path_m", 1, 1, 1, 4, fallback="txt_maxl")))},
            frozenset({"switch"}), {"gauge": {"sta": (3,)}, "text": {"aph": (128,)}})
        text = table_text("1.68.2", {"NX4832T035": 3584}, {"T": series})
        table = read_memory_table(text, "test")
        self.assertEqual((table.editor, table.memory, table.series), ("1.68.2",
                                                                      {"NX4832T035": 3584},
                                                                      {"T": series}))
        # tomli-w writes the data; the opening comment is the probe's own.
        self.assertTrue(text.startswith("# What the Nextion Editor's compile counts in memory"))


if __name__ == "__main__":
    unittest.main()
