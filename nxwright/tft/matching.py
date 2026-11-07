"""The check that a compile writes a file only for what nxwright can write, and
refuses anything else, listing it.

nxwright's build runs first, and decides what a project may hold, so the
check does not repeat its checks. A rule that takes fewer values than fit
in their bytes names why, as one of the reasons in reasons.py, and the
refusal's message gives it. Nothing is refused because no probe tried it. A
value nxwright writes by a rule it knows is taken, whether or not a probe
showed it.

A project is turned into needs: each thing in it that its TFT file depends
on. A Need has a kind, a subject, and a value:

  - "firmware": the subject is the version of the Nextion Editor whose
    firmware the compile packages, such as "1.68.2";
  - "series", "model", "rotation", and "encoding": the project's device
    settings, the subject being the series' letter, the model's name, the
    rotation in degrees, or the encoding's name;
  - "type": a page's or a component's type, as nxwright names it, such as
    "page" or "text". Its context gives the components of its page, as an
    event's line does;
  - "attribute": an attribute away from its type's default, or with no
    default, the subject being "<type>.<attribute>" and the value its stored
    bytes. Its context gives the object's other attributes, by name;
  - "code": a line of code, the subject being "program.s" or "event", and
    the value the line. An event's line gives in its context the components
    of its page, whose attributes it may refer to (statements.attribute_kind).
    Every line gives the project's global components too, by (page name,
    name), as `globals`, which a line may name by their page
    (statements.named_component);
  - "text in code": a line of code, of program.s or of an event, that holds
    a character past ASCII, outside a comment, the subject being the
    project's encoding and the value the line. The code's own rules check
    its texts as characters, and this need's rule checks them in the
    project's encoding (statements.past_ascii_covered);
  - "resource": a picture, a font, or another resource, the subject being
    its kind. Its context gives its block of the project file, as a
    sound's WAV file, as `block`;
  - "overlap": two components of a page, each with a place, that share a
    pixel, the subject being their types, such as "picture and button". A
    component with a place counts whether it is drawn or not. Its context
    gives the two types. For a page whose drawn components overlap, the
    Nextion Editor writes ref commands of its own, which overlaps.py
    writes for the types whose refs it knows.

A Rule says what a piece of nxwright can write: needs of its kind and subject
(any subject when None) whose value its `covers` accepts. Each piece keeps
its rules in a list named MATCHED, in its own module, which the check
gathers from every piece's module:

  - packaging.py, frame.py, statements.py, and overlaps.py;
  - each module of the packages component_types/, instructions/, series/,
    and models/, once they exist.

So no piece edits a shared list. A need no rule covers is refused. A need
tries only the rules of its kind whose subject is its own, a pattern, or
any subject, found through an index made once from the rules (RuleIndex),
so the check grows with the needs, not with the needs times the rules.

Each piece's module also gives SERIES, the series it writes, such as
("T", "K"). A project's needs carry the project's series, and a piece's
rules cover a need only on a series of its SERIES. So a piece written for T
alone is refused on K. A need without a series, as the firmware's, is not
checked by series. A project's needs carry its encoding too, for the rules
that read a text's bytes, and its screen model and rotation, for those that
check a place on the screen.
"""
from dataclasses import dataclass, field, replace
from fnmatch import fnmatchcase
import importlib
import importlib.util
import pkgutil
from typing import Callable

from nxwright import NxwrightError
from nxwright.project.attribute_values import number_from_bytes
from nxwright.project.component_defaults import nxwright_defaults
from nxwright.project.page_block import Attribute, Event
from nxwright.project.page_text import is_string_attribute

from nxwright.tft.component_types import is_global, place_and_size, type_name
from nxwright.tft.project import Project, plain_lines, program_variables
from nxwright.tft.reasons import REASONS

# The modules, then the packages of modules, that keep a MATCHED list.
_PIECE_MODULES = ("packaging", "frame", "statements", "overlaps")
_PIECE_PACKAGES = ("component_types", "instructions", "series", "models")
# Attributes the project file stores but derives from others: an object's
# type, ID, and right and bottom edges. Its type is a need of its own.
_DERIVED_ATTRIBUTES = ("type", "id", "endx", "endy")


@dataclass
class Need:
    """One thing a project holds that its TFT file depends on (the module's
    docstring). `where` says where it is, and `shown` its value, for
    messages: an attribute's number or text, rather than its bytes. `series`,
    `encoding`, `model`, and `rotation` are the project's series, the names
    of its encoding and of its screen model, and its rotation in degrees, or
    None for a need of no project."""
    kind: str
    subject: str
    value: object = None
    where: str = ""
    context: dict = field(default_factory=dict)
    shown: str = None
    series: str = None
    encoding: str = None
    model: str = None
    rotation: int = None

    def described(self) -> str:
        """Returns the need in words, such as "attribute text.txt = 'Yo'"."""
        if self.value is None:
            return "%s %s" % (self.kind, self.subject)
        return "%s %s = %s" % (self.kind, self.subject,
                               self.shown if self.shown is not None else repr(self.value))


@dataclass(frozen=True)
class Rule:
    """Needs a piece of nxwright can write: those of `kind` and `subject`, or
    of any subject when it is None, whose need `covers` accepts. A subject
    may be a pattern, such as "*.vscope" for the vscope of every type. `says`
    is what it covers, in words, such as "any text up to its txt_maxl, in
    ASCII". `refuses_because` is one of REASONS, why the rule takes fewer
    values than fit in their bytes, or None for a rule that takes them all.
    A rule of any subject gives no reason, as it is about no subject in
    particular. `series` are the series the rule applies on, or None for
    every series, so that a value can be refused for one reason on some
    series and for another on the others."""
    kind: str
    subject: object
    says: str
    covers: Callable = lambda need: True
    refuses_because: str = None
    series: tuple = None

    def __post_init__(self):
        if self.refuses_because not in (None,) + REASONS:
            raise ValueError("a rule refuses only for one of REASONS, not %r"
                             % self.refuses_because)
        if self.refuses_because is not None and self.subject is None:
            raise ValueError("a rule of any subject gives no reason")

    def is_about(self, subject: str) -> bool:
        """Whether the rule's subject is `subject`, or a pattern that matches
        it."""
        return self.subject is not None and fnmatchcase(subject, self.subject)

    def applies_on(self, series: str) -> bool:
        """Whether the rule applies on `series`, or on a need of no series."""
        return self.series is None or series is None or series in self.series

    def matches(self, need: Need) -> bool:
        return (self.kind == need.kind and (self.subject is None or self.is_about(need.subject))
                and self.applies_on(need.series) and self.covers(need))


def firmware_needs(version: tuple) -> list:
    """Returns the need of firmware of the Nextion Editor's `version`, as a TFT
    file's header 1 gives it, such as (1, 68, 2)."""
    return [Need("firmware", "%d.%d.%d" % tuple(version), where="the firmware")]


def project_needs(project: Project) -> list:
    """Returns every need of `project`, in order: its device settings, then
    each page's objects and their overlaps, then program.s, then each macro
    and its lines, then its resources. A macro's lines have the subject
    "macro": like program.s's, they belong to no page."""
    settings = project.settings
    needs = [Need("series", settings.model.series, where="the screen model"),
             Need("model", settings.model.name, where="the screen model"),
             Need("rotation", str(settings.rotation), where="the device settings"),
             Need("encoding", settings.encoding, where="the device settings")]
    for page in project.pages:
        # A line of code may refer to the attributes of its page's components:
        # their types by name, and the components themselves.
        objects = {(item.attribute("objname") or b"").decode("latin-1"): item
                   for item in page.objects[1:]}
        components = {name: item.attribute("type")[0] for name, item in objects.items()}
        for page_object in page.objects:
            needs.extend(_object_needs(project, page.name, page_object, components, objects,
                                       page.objects[0]))
        needs.extend(_overlap_needs(page.name, objects))
    for number, line in enumerate(code_lines(project, project.program), start=1):
        where = "program.s, line %d" % number
        needs.append(Need("code", "program.s", line, where, {}))
        needs.extend(_past_ascii_needs(project, line, where))
    for name, lines in project.macros:
        needs.append(Need("macro", name, where="the macro %s" % name))
        for number, line in enumerate(lines, start=1):
            where = "macro %s, line %d" % (name, number)
            needs.append(Need("code", "macro", line, where, {}))
            needs.extend(_past_ascii_needs(project, line, where))
    for kind, name in project.resources:
        needs.append(Need("resource", kind, where="the %s %s" % (kind, name),
                          context={"block": project.blocks[name]}))
    # A line of code may refer to a global component of any page by its
    # page's name, as `page1.va0.val`, in program.s too (statements.py).
    global_components = {(page.name, (item.attribute("objname") or b"").decode("latin-1")): item
                         for page in project.pages for item in page.objects[1:]
                         if is_global(item)}
    # A line of code may give an int variable of program.s where a command
    # takes a component, written as its operand (statements.component_taken).
    variables = tuple(program_variables(project))
    # Each piece's rules cover a need only on the series it writes.
    for need in needs:
        if need.kind == "code":
            need.context["globals"] = global_components
            need.context["variables"] = variables
        need.series, need.encoding = settings.model.series, settings.encoding
        need.model, need.rotation = settings.model.name, settings.rotation
    return needs


def _past_ascii_needs(project: Project, line: str, where: str) -> list:
    """Returns the need of the line of code `line`, at `where`, when it holds
    a character past ASCII outside a comment, or none (the module's
    docstring)."""
    if line.isascii() or line.lstrip(" \t").startswith("//"):
        return []
    return [Need("text in code", project.settings.encoding, line, where)]


def _object_needs(project: Project, page_name: str, page_object, components: dict,
                  objects: dict, page_itself) -> list:
    """Returns the needs of one page or component: its type, its attributes
    away from their defaults, and each line of its events. Its type's need
    and each line's give, in their context, `components`: the page's
    components, {name: type number}. Each line's gives `objects` too: the
    components themselves, {name: component}; `page`: its page's own
    name, which the screen's commands may give as a component; and
    `page_object`: the page itself, `page_itself`, whose own attributes
    the line may name."""
    type_number = page_object.attribute("type")[0]
    object_type = type_name(page_object)
    name = page_object.attribute("objname") or b""
    where = "%s: %s" % (page_name, name.decode("latin-1"))
    defaults = nxwright_defaults().get(type_number)
    default_values = dict(defaults.attributes) if defaults else {}
    attributes = {item.name: item.value for item in page_object.items
                  if isinstance(item, Attribute)}
    needs = [Need("type", object_type, where=where, context={"components": components})]
    for attribute, value in attributes.items():
        if attribute not in _DERIVED_ATTRIBUTES and default_values.get(attribute) != value:
            shown = (repr(project.codec.decode_keeping_bytes(value))
                     if is_string_attribute(type_number, attribute)
                     else str(number_from_bytes(value)))
            needs.append(Need("attribute", "%s.%s" % (object_type, attribute), value, where,
                              attributes, shown))
    for item in page_object.items:
        if isinstance(item, Event):
            for number, line in enumerate(code_lines(project, b"\n".join(item.lines)), start=1):
                at = "%s, %s, line %d" % (where, item.name, number)
                needs.append(Need("code", "event", line, at,
                                  {"components": components, "objects": objects,
                                   "page": page_name, "page_object": page_itself}))
                needs.extend(_past_ascii_needs(project, line, at))
    return needs


def _overlap_needs(page_name: str, objects: dict) -> list:
    """Returns a need for each two components of `objects`, {name:
    component}, that share a pixel, the earlier in the page's order first.
    A component without a place, as a variable or a timer, shares none."""
    placed = [(name, item, place_and_size(item)) for name, item in objects.items()
              if all(item.attribute(attribute) is not None for attribute in ("x", "y", "w", "h"))]
    needs = []
    for number, (name, item, area) in enumerate(placed):
        for other_name, other, other_area in placed[number + 1:]:
            if share_a_pixel(area, other_area):
                types = (type_name(item), type_name(other))
                needs.append(Need("overlap", "%s and %s" % types,
                                  where="%s: %s and %s" % (page_name, name, other_name),
                                  context={"types": types}))
    return needs


def share_a_pixel(area: tuple, other: tuple) -> bool:
    """Whether the areas `area` and `other`, each an x, a y, a width, and a
    height, share a pixel. Areas that only touch, at a side or a corner,
    share none: the Nextion Editor writes no code of its own for them."""
    x, y, w, h = area
    other_x, other_y, other_w, other_h = other
    return x < other_x + other_w and other_x < x + w and y < other_y + other_h and other_y < y + h


def code_lines(project: Project, code: bytes) -> list:
    """Returns the lines of `code` as text, in the project's encoding, as
    plain_lines gives them. The project's own code is clean already
    (project.py), so for it this only splits it into lines."""
    # Lines end with "\r\n" or "\n" alone: str.splitlines would also split at
    # characters a text may hold, such as U+0085, byte 0x85 in iso-8859-1.
    text = project.codec.decode_keeping_bytes(code).replace("\r\n", "\n")
    return plain_lines(text.split("\n"))


def piece_modules() -> list:
    """Returns the module of each piece (the module's docstring): those of
    _PIECE_MODULES, then each module of the packages of _PIECE_PACKAGES
    that exist."""
    names = ["nxwright.tft.%s" % name for name in _PIECE_MODULES]
    for package in _PIECE_PACKAGES:
        name = "nxwright.tft.%s" % package
        if importlib.util.find_spec(name) is not None:
            path = importlib.import_module(name).__path__
            names.extend("%s.%s" % (name, module.name) for module in pkgutil.iter_modules(path))
    return [importlib.import_module(name) for name in names]


def matched_rules() -> list:
    """Returns every piece's rules, gathered from their modules (the module's
    docstring), each covering a need only on a series of its module's SERIES.
    Raises NxwrightError when a piece's module has no MATCHED list or no
    SERIES, so that a piece cannot be left out of the check unnoticed, nor
    taken on a series it does not write."""
    rules = []
    for module in piece_modules():
        name = module.__name__
        matched = getattr(module, "MATCHED", None)
        if matched is None:
            raise NxwrightError("%s keeps no MATCHED list of what it matched" % name)
        series = getattr(module, "SERIES", None)
        if series is None:
            raise NxwrightError("%s gives no SERIES, the series it writes" % name)
        rules.extend(_on_series(rule, series) for rule in matched)
    return rules


def _on_series(rule: Rule, series: tuple) -> Rule:
    """Returns `rule`, covering a need only on one of `series`, or with no
    series."""
    return replace(rule, covers=lambda need: (need.series is None or need.series in series)
                   and rule.covers(need))


def unmatched(needs: list, rules: list) -> list:
    """Returns the needs no rule covers, in order. Each need tries only the
    rules that could cover it (RuleIndex)."""
    index = RuleIndex(rules)
    return [need for need in needs
            if not any(rule.matches(need) for rule in index.rules_for(need))]


class RuleIndex:
    """The rules `rules`, found by a need's kind and subject. A need's rules
    are those of its kind whose subject is its own, a pattern, or None for
    any subject, in the order of `rules`, so that a need tries them as it
    would going through every rule in turn."""

    def __init__(self, rules: list):
        # Each rule by its place in `rules`, the place giving the order.
        self._by_subject, self._others = {}, {}
        for place, rule in enumerate(rules):
            if rule.subject is None or _is_pattern(rule.subject):
                self._others.setdefault(rule.kind, []).append((place, rule))
            else:
                self._by_subject.setdefault((rule.kind, rule.subject), []).append((place, rule))
        self._found = {}

    def rules_for(self, need: Need) -> list:
        """Returns the rules that could cover `need`, in order."""
        key = need.kind, need.subject
        if key not in self._found:
            self._found[key] = [rule for _, rule in sorted(
                self._by_subject.get(key, []) + self._others.get(need.kind, []),
                key=lambda placed: placed[0])]
        return self._found[key]


def _is_pattern(subject: str) -> bool:
    """Whether the rule's subject `subject` is a pattern, as "*.vscope" is,
    which fnmatchcase matches against a need's subject (Rule.is_about)."""
    return any(character in subject for character in "*?[")


def refusal_reasons(need: Need, rules: list) -> list:
    """Returns why `rules` refuse `need`: the reasons that the rules of its
    kind and subject on its series give, each once, in the order of
    REASONS. Rules of its very subject come before rules of a pattern, such
    as text.vscope's before *.vscope's."""
    about = [rule for rule in rules if rule.kind == need.kind and rule.is_about(need.subject)
             and rule.applies_on(need.series)]
    own = [rule for rule in about if rule.subject == need.subject]
    given = {rule.refuses_because for rule in own or about}
    return [reason for reason in REASONS if reason in given]


def refuse_unmatched(needs: list, rules: list = None):
    """Raises NxwrightError listing every need no rule covers, each once with
    where it first is, how many more places have it, and why it is refused
    (refusal_reasons). `rules` are matched_rules() unless given."""
    rules = matched_rules() if rules is None else rules
    left = unmatched(needs, rules)
    if not left:
        return
    # A need's reasons come from the rules that could cover it: those of
    # its kind whose subject is its own, a pattern, or any subject. They
    # are found once for each need described.
    index = RuleIndex(rules)
    seen, reasons = {}, {}
    for need in left:
        described = need.described()
        seen.setdefault(described, []).append(need.where)
        if described not in reasons:
            reasons[described] = refusal_reasons(need, index.rules_for(need))
    lines = ["- %s (%s%s)%s" % (described, places[0],
                                ", and %d more" % (len(places) - 1) if len(places) > 1 else "",
                                ": " + ", and ".join(reasons[described])
                                if reasons[described] else "")
             for described, places in seen.items()]
    raise NxwrightError("nxwright does not compile these:\n%s" % "\n".join(lines))
