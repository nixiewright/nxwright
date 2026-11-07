"""The work of a compile grows in step with its project. Each table of the
whole project is built once (compile_context.py), and each component is
described once (component_types.object_module), however many pages,
components, lines of code, and timers the project has. Decoding the user
code a compile writes works out the checksum of each name it might guess
once (decompiling/decoded_file.py).

The tests count the work, not the time, by wrapping the functions that do
it, so production code keeps no counter. Each takes its project from
tests/tft/unit_inputs.py, made of pages of texts, numbers, and timers, whose
code names their attributes.
"""
from collections import Counter
import unittest
from unittest import mock


from nxwright.tft import component_types, compile_context, frame, label_numbers, statements
from nxwright.tft.decompiling import decoded_file
from nxwright.tft.matching import Rule, matched_rules, project_needs, refuse_unmatched
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tests.tft.unit_inputs import page, project_of

# Each page's components: texts, a number, and two or three timers, 25 in
# all on a page with three timers.
_TEXTS = 21


def _page(number: int, timers: int):
    """Returns the page `number`, its components in a grid, and code in its
    Touch Release event that names each text's attributes and the number's."""
    components = [text_component("t%d" % each, x=(each % 5) * 60, y=(each // 5) * 40,
                                 w=50, h=30) for each in range(_TEXTS)]
    components.append(number_component("n0", x=0, y=240, w=50, h=30))
    components += [timer_component("tm%d" % each) for each in range(timers)]
    lines = (["n0.val=t%d.x+t%d.y" % (each, (each + 1) % _TEXTS) for each in range(_TEXTS)]
             + ["t%d.txt=t0.txt" % each for each in range(1, _TEXTS)])
    code = "on page%d.up:\n" % number + "".join("  %s\n" % line for line in lines)
    if number == 0:
        return page(*components, code=code)
    return page(*components, code=code, name="page%d" % number, after=number - 1)


def _project(pages: int):
    """Returns a project of `pages` pages, with two and a half timers a page,
    100 timers on 40 pages."""
    return project_of(*[_page(number, 3 if number % 2 else 2) for number in range(pages)],
                      fonts=0)


def _work(project) -> Counter:
    """Returns how many times the compile of `project`, its match check then
    its frame, makes a context, builds each table of the whole project,
    describes a component, finds an object's name, encodes a line, and
    tries a rule against a need. "tries past the need's rules" counts the
    tries of each need past the rules of its kind that could cover it:
    those of its subject, of a pattern, and of any subject."""
    counted, tries = Counter(), Counter()

    def counting(name, function):
        def counted_call(*arguments, **keywords):
            counted[name] += 1
            return function(*arguments, **keywords)
        return counted_call

    real_matches = Rule.matches

    def trying(rule, need):
        tries[id(need)] += 1
        return real_matches(rule, need)

    needs = project_needs(project)
    with mock.patch.object(Rule, "matches", trying):
        refuse_unmatched(needs)
    rules = matched_rules()
    counted["tries"] = sum(tries.values())
    counted["tries past the need's rules"] = sum(
        max(0, tries[id(need)] - sum(1 for rule in rules if rule.kind == need.kind and (
            rule.subject in (None, need.subject) or _is_pattern(rule.subject))))
        for need in needs)
    with mock.patch.object(component_types, "first_entries",
                           counting("first entries", component_types.first_entries)), \
            mock.patch.object(label_numbers, "numbers",
                              counting("numbers", label_numbers.numbers)), \
            mock.patch.object(component_types, "_described",
                              counting("descriptions", component_types._described)), \
            mock.patch.object(statements, "encode_line",
                              counting("lines", statements.encode_line)), \
            mock.patch.object(compile_context, "CompileContext",
                              counting("contexts", compile_context.CompileContext)), \
            mock.patch.object(frame, "CompileContext",
                              counting("contexts", frame.CompileContext)), \
            mock.patch.object(component_types, "object_name",
                              counting("names", component_types.object_name)):
        refuse_unmatched(project_needs(project))
        frame.user_code(project)
    return counted


def _is_pattern(subject: str) -> bool:
    """Whether the rule's subject `subject` is a pattern, as "*.vscope" is.
    The test works this out on its own, not through the match check's
    index, so that a fault in the index cannot hide its own extra tries."""
    return any(character in subject for character in "*?[")


class CompileScaleTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.small, cls.large = _project(40), _project(80)
        cls.small_work, cls.large_work = _work(cls.small), _work(cls.large)

    def test_its_project_is_of_real_size(self):
        objects = sum(len(each.objects) for each in self.small.pages)
        self.assertEqual((len(self.small.pages), objects), (40, 40 * 25 - 20 + 40))
        self.assertEqual(sum(component_types.type_name(each) == "timer"
                             for made in self.small.pages for each in made.objects), 100)
        # Each page's code is encoded, a line at a time.
        self.assertGreaterEqual(self.small_work["lines"], 40 * (2 * _TEXTS - 1))

    def test_each_table_is_built_once(self):
        for work in (self.small_work, self.large_work):
            # One context, which builds each of its tables once.
            self.assertEqual((work["contexts"], work["first entries"], work["numbers"]),
                             (1, 1, 1))

    def test_each_component_is_described_once(self):
        # The frame's copy of the project, with each page at the screen's
        # place, keeps the components, so they are not described again.
        for project, work in ((self.small, self.small_work), (self.large, self.large_work)):
            self.assertLessEqual(work["descriptions"],
                                 sum(len(each.objects) for each in project.pages))

    def test_each_need_tries_only_the_rules_that_could_cover_it(self):
        # The match check once tried each need against every rule in turn,
        # 680 of them, until one covered it.
        for work in (self.small_work, self.large_work):
            self.assertEqual(work["tries past the need's rules"], 0)

    def test_twice_the_project_twice_the_work_at_most(self):
        # Encoding a line once found every page's name and its page's
        # components' names again, which grew with the lines times the
        # pages.
        for kind in ("descriptions", "lines", "names", "tries"):
            with self.subTest(kind):
                self.assertLessEqual(self.large_work[kind], 2 * self.small_work[kind])


def _checksums(project) -> Counter:
    """Returns how many times decoding the user code of `project`, as the
    frame writes it, works out the checksum of each name it might guess, by
    the name, padded or not."""
    code = frame.user_code(project)
    settings = project.settings
    worked_out = Counter()

    def counting(form, function):
        def counted_call(name):
            worked_out[form, name] += 1
            return function(name)
        return counted_call

    with mock.patch.object(decoded_file, "_padded_crc",
                           counting("padded", decoded_file._padded_crc)), \
            mock.patch.object(decoded_file, "_unpadded_crc",
                              counting("unpadded", decoded_file._unpadded_crc)):
        decoded_file.decoded_user_code(code, settings.model.series, settings.model.name,
                                       settings.rotation, settings.encoding)
    return worked_out


class DecodeScaleTest(unittest.TestCase):

    def test_each_name_s_checksum_is_worked_out_once(self):
        # The decoder once worked out the checksum of each name it might
        # guess, such as t0 to t255, again for each object. A name may be
        # both a guess and a word of the code, as t4 is, and each of those
        # two tables works its checksum out once.
        for pages in (40, 80):
            with self.subTest(pages=pages):
                worked_out = _checksums(_project(pages))
                self.assertTrue(worked_out)
                self.assertLessEqual(max(worked_out.values()), 2)


if __name__ == "__main__":
    unittest.main()
