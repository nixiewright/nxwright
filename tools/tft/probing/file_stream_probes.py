"""The probes of the file stream (component_types/file_stream.py), a type P
and E have and T and K have not: projects on the P base folder, each
compared with the Nextion Editor's whole file. Run them on P with
`tools.tft.probe run p_probes`, which takes them, and on E with
`tools.tft.probe run e_probes`.

Some probes keep fixtures in p_probes.py's folder (kept):

  - the probe of a file stream at its defaults, and the probe of two file
    streams beside a text, keep the user code;
  - the probe of a file stream's calls as values, and the probe of its
    calls in a for's start, keep the blocks of the event that has the
    calls.
"""
from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.component_probes import editor_file, user_code_kept, whole_file, with_components
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event
from tools.tft.probing.text_probes import text_component


def file_stream_component(name: str = "fs0", **attributes: int) -> str:
    """Returns a file stream component in a page file's form, its
    attributes, such as val, at their defaults unless given."""
    return ('\n[[component]]\nname = "%s"\ntype = "file-stream"\n' % name
            + "".join("%s = %d\n" % item for item in attributes.items()))


def _under_later_rooms(folder):
    """Adds a page of two texts and a file stream, then a second page of two
    texts, whose txts' rooms lie over the first page's file stream in the
    Nextion Editor's scratch image."""
    with_components(text_component(), text_component("t1", y=60),
                    file_stream_component(val=5, qty=7))(folder)
    with_components(text_component(), text_component("t1", y=60), page="page1")(folder)


# Each method's call, in the forms the probes showed, and a method read as
# a value.
_CALLS = ['fs0.open("sd0/a.txt")', "fs0.open(t0.txt)", "fs0.read(t0.txt,0,3)",
          "fs0.read(t0.txt,sys0+1,2)", "fs0.write(t0.txt,0,3)", "fs0.close()",
          'fs0.find("sd0/a.txt")', "sys0=fs0.open"]
# Each method's call as a value: as the whole value, put in a number's
# val, after `+=`, joined with other operands, and with its component
# named through its page. Then each method alone on its line, without its
# parentheses.
_CALLS_AS_VALUES = [
    "sys0=fs0.open(t0.txt)", 'sys0=fs0.open("sd0/a.txt")', 'sys0=fs0.find("sd0/a.txt")',
    "sys0=fs0.read(t0.txt,0,3)", "sys0=fs0.write(t0.txt,0,3)", "sys0=fs0.close()",
    "n0.val=fs0.open(t0.txt)", "sys0+=fs0.open(t0.txt)", "sys0=fs0.open(t0.txt)+1",
    "sys0=1+fs0.close()", "sys0=fs0.open(t0.txt)+fs0.find(t0.txt)",
    "sys0=page0.fs0.open(t0.txt)", "fs0.open", "fs0.read", "fs0.write", "fs0.close",
    "fs0.find", "page0.fs0.close"]
# Starts of a for that contain a call. The Nextion Editor writes each only
# up to its first call's parentheses.
_STARTS_WITH_A_CALL = [
    "sys0=fs0.close()", "sys0=fs0.open(t0.txt)+1", "sys0=fs0.read(t0.txt,0,3)+1",
    "sys0=1+fs0.close()+2", "sys0+=fs0.close()", "sys0=fs0.close()+fs0.open(t0.txt)",
    "sys0=page0.fs0.close()", "n0.val=fs0.close()"]

PROBES = [
    # A file stream at its defaults: its memory, entries, record, buffer,
    # its init in the load section, and its close in the page's unload.
    Probe("file-stream-at-its-defaults", "P", with_components(file_stream_component()),
          whole_file, editor_file, kept=user_code_kept),
    # Each of its values away from its default, beside a text, molloc and
    # molloc_s among them, which change nothing.
    Probe("file-stream-values", "P", with_components(
        text_component(), file_stream_component(val=5, qty=7, en=1, molloc_s=1000,
                                                molloc=2000)),
        whole_file, editor_file),
    # Two file streams beside a text: each one's memory and buffer, after
    # the text's txt, in order, and each one's init and close.
    Probe("file-stream-two-beside-a-text", "P", with_components(
        file_stream_component(), text_component(), file_stream_component("fs1")),
        whole_file, editor_file, kept=user_code_kept),
    # A later page's txts' rooms over a file stream's memory, which keep its
    # val, its qty, and its methods' values in the scratch image.
    Probe("file-stream-under-later-rooms", "P", _under_later_rooms, whole_file, editor_file),
    # Its attributes in code: read, set, and in a condition; each method's
    # call; and the page's own unload code before the close the Nextion
    # Editor adds.
    Probe("file-stream-in-code", "P", with_components(
        text_component(), file_stream_component(), code=(
            "on page0.up:\n  sys0=fs0.val\n  fs0.val=5\n  sys1=fs0.qty\n  sys2=fs0.en\n"
            "  fs0.val=sys0+1\n  if(fs0.en==1)\n  {\n    sys2=1\n  }\n"
            + "".join("  %s\n" % line for line in _CALLS)
            + "on page0.unload:\n  sys0=1\n  fs0.open(\"sd0/a.txt\")\n")),
        whole_file, editor_file),
    # Its methods given a number, or a text, where a path or a txt goes,
    # which the Nextion Editor compiles too.
    Probe("file-stream-calls-of-other-kinds", "P", with_components(
        text_component(), number_component(y=60), file_stream_component(), code=(
            "on page0.up:\n  fs0.open(5)\n  fs0.find(n0.val)\n  fs0.read(\"abc\",0,3)\n"
            "  fs0.write(n0.val,0,3)\n")),
        whole_file, editor_file),
    # A file stream's calls as values, and its methods alone on a line, in
    # page0's Touch Release event. The probe keeps the event's blocks.
    Probe("file-stream-calls-as-values", "P", with_attributes(
        _CALLS_AS_VALUES, [text_component(), number_component(y=60), file_stream_component()]),
        ours_in_event, theirs_in_event, kept=ours_in_event),
    # Several for loops in a row, each with a call in its start, in page0's
    # Touch Release event. The probe keeps the event's blocks.
    Probe("file-stream-calls-in-a-for-s-start", "P", with_attributes(
        [line for start in _STARTS_WITH_A_CALL
         for line in ("for(%s;sys0<1;sys0++)" % start, "{", "sys1=1", "}")],
        [text_component(), number_component(y=60), file_stream_component()]),
        ours_in_event, theirs_in_event, kept=ours_in_event),
]
