"""The probes of the pinyin commands, pa_q and pa_txt (instructions/
pinyin_commands.py): in page0's Touch Release event, beside the text t0,
object 1, and the numbers n0 and n1, with `int a=1` declared, their
syllables texts and txts, their counts and starts numbers, long numbers,
hexadecimal numbers, variables, and vals; and in program.s. Run them with
`tools.tft.probe run pinyin_probes`.

Each compares the blocks of its run of lines, and keeps them as its
fixture (statement_probes.py gives both).
"""
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (beside_a_text_and_numbers, ours_in_event,
                                            ours_in_program, program_lines, theirs_in_event,
                                            theirs_in_program)

FIXTURES = "pinyin"

PROBES = [
    Probe("pinyin-in-an-event", "T", beside_a_text_and_numbers([
        "pa_q t0.txt,n0.val", 'pa_q "ni",sys0', "pa_q t0.txt, a",
        "pa_txt t0.txt,t0.txt,n0.val,1", 'pa_txt "ni",t0.txt,sys0,sys1',
        "pa_txt t0.txt,t0.txt,0,6", "pa_txt t0.txt,t0.txt,n0.val,1000",
        'pa_txt "mei",t0.txt,0x00,0x06']), ours_in_event, theirs_in_event, FIXTURES),
    # pa_txt's start and its count as operands joined by the arithmetic
    # operators.
    Probe("pinyin-starts-and-counts-of-expressions", "T", beside_a_text_and_numbers([
        'pa_txt "mei",t0.txt,sys0+1,6', 'pa_txt "mei",t0.txt,0,n0.val*2']),
        ours_in_event, theirs_in_event, FIXTURES),
    # One operand of any kind where one goes: the syllable, pa_q's count's
    # destination, and pa_txt's characters'.
    Probe("pinyin-of-any-kind-where-one-operand-goes", "T", beside_a_text_and_numbers([
        'pa_q "a",5', 'pa_q "a",0x05', 'pa_q "a",-5', 'pa_q "a",b[1].txt',
        "pa_q b[1].val,n0.val", 'pa_txt "a",b[1].val,0,1', "pa_q n0.val,sys0", "pa_q 5,sys0",
        'pa_txt "a",n0.val,0,1', 'pa_txt "a",sys0,0,1']),
        ours_in_event, theirs_in_event, FIXTURES),
    Probe("pinyin-in-program-s", "T", program_lines(['pa_q "ni",sys0', 'pa_q "mei",sys1']),
          ours_in_program, theirs_in_program, FIXTURES),
]
