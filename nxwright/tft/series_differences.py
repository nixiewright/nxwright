"""The differences between series whose user code is otherwise alike.

T, K, F, P, and E are series of Nextion screens. A TFT file is the compiled
project sent to a screen. F and K write their user code as T does, and E
as P does, but for the differences below.

A probe is a small project used to check the compiler. The follower test
compiles the same probe on two series and compares their user code.
DIFFERENCES gives the changes that comparison allows. The compiler does
not use this table, so the expected values stay independent of its own.

Each key is the series being checked, the follower. Its `leader` is the
series used for comparison: T for F and K, or P for E. The other fields are:

- `commands`: (name, table_number, leader_number, follower_number).
  A compiled command gives a table number and a command number within that
  table. F's ("doevents", 8, 0x21, 0x23), for example, gives doevents as
  number 0x21 in table 8 on T, and 0x23 on F. The name describes the row;
  the comparison changes the numbers, not the name's bytes.

- `operands`: the same four fields, for system variables and named colours
  in expressions. F's ("baud", 4, 0x0E, 0x1A) gives baud as number 0x0E in
  table 4 on T, and 0x1A on F.

- `attribute_limits`: the maximum attribute values that differ.
  Each row is (component_type, record_slot, leader_maximum, follower_maximum).
  A TFT file describes each component's attributes, including their limits.
  The component's record contains numbered slots that point to those
  attribute descriptions. Slots are counted from 0 after the record's header.
  The row (58, 29, 192, 368) is for QR codes, component type 58. Slot 29
  points to txt_maxl, whose maximum is 192 on T and 368 on F. Using the slot
  finds the right attribute even when a QR code's logo adds another attribute.

- `page_size`: ((leader_width, leader_height), (follower_width,
  follower_height)), in pixels, for the base screen models used by the probes.
  E's ((800, 480), (480, 480)) compares P's 800-by-480 screen with E's
  480-by-480 screen. These sizes are for a project display rotation of 0
  degrees, meaning no rotation. At 90 or 270 degrees the comparison swaps
  each pair's width and height.

An empty tuple allows no differences of that kind. A `page_size` of None
requires the page dimensions to match without adjustment."""

DIFFERENCES = {
    "F": {
        "leader": "T",
        "commands": (
            ("pa_q", 4, 0x0E, 0x12),
            ("picq", 4, 0x0F, 0x13),
            ("fstr", 4, 0x10, 0x14),
            ("nstr", 4, 0x11, 0x15),
            ("xstr", 4, 0x12, 0x16),
            ("zstr", 4, 0x13, 0x17),
            ("cirs", 4, 0x14, 0x18),
            ("addt", 4, 0x15, 0x1C),
            ("init", 4, 0x16, 0x1D),
            ("rfpt", 4, 0x17, 0x1E),
            ("wfpt", 4, 0x18, 0x1F),
            ("rest", 4, 0x19, 0x20),
            ("getv", 4, 0x1A, 0x21),
            ("draw", 4, 0x1B, 0x22),
            ("covx", 4, 0x1C, 0x23),
            ("showqq", 8, 0x0D, 0x0E),
            ("substr", 8, 0x0E, 0x0F),
            ("prints", 8, 0x0F, 0x10),
            ("pa_txt", 8, 0x10, 0x11),
            ("udelete", 8, 0x11, 0x12),
            ("strsize", 8, 0x12, 0x13),
            ("crcputh", 8, 0x13, 0x14),
            ("touch_j", 8, 0x14, 0x15),
            ("crcputs", 8, 0x15, 0x16),
            ("randset", 8, 0x16, 0x17),
            ("crcrest", 8, 0x17, 0x18),
            ("crcputu", 8, 0x18, 0x19),
            ("lcd_dev", 8, 0x19, 0x1A),
            ("lhmi_cle", 8, 0x1A, 0x1B),
            ("whmi_cle", 8, 0x1B, 0x1C),
            ("setbrush", 8, 0x1C, 0x1D),
            ("ref_stop", 8, 0x1D, 0x1E),
            ("com_stop", 8, 0x1E, 0x1F),
            ("ref_star", 8, 0x1F, 0x20),
            ("com_star", 8, 0x20, 0x21),
            ("doevents", 8, 0x21, 0x23),
            ("timerset", 8, 0x22, 0x24),
            ("getpassw", 8, 0x23, 0x25),
            ("lcd_refx", 8, 0x24, 0x26),
            ("setbaudz", 8, 0x25, 0x27),
        ),
        "operands": (
            ("sya1", 4, 0x07, 0x08),
            ("tch1", 4, 0x08, 0x09),
            ("tch2", 4, 0x09, 0x0B),
            ("tch3", 4, 0x0A, 0x0D),
            ("rand", 4, 0x0D, 0x19),
            ("baud", 4, 0x0E, 0x1A),
            ("thsp", 4, 0x0F, 0x1C),
            ("ussp", 4, 0x10, 0x1D),
            ("thup", 4, 0x11, 0x1E),
            ("usup", 4, 0x12, 0x1F),
            ("addr", 4, 0x13, 0x20),
            ("dims", 4, 0x14, 0x21),
            ("bcpu", 4, 0x15, 0x22),
            ("spax", 4, 0x16, 0x23),
            ("spay", 4, 0x17, 0x24),
            ("portbusy", 8, 0x11, 0x12),
            ("BLUE", 4, 0x0B, 0x17),
            ("GRAY", 4, 0x0C, 0x18),
        ),
        "attribute_limits": (
            (58, 29, 192, 368),
        ),
        "page_size": None,
    },
    "K": {
        "leader": "T",
        "commands": (
            ("pa_q", 4, 0x0E, 0x10),
            ("picq", 4, 0x0F, 0x11),
            ("fstr", 4, 0x10, 0x12),
            ("nstr", 4, 0x11, 0x13),
            ("xstr", 4, 0x12, 0x14),
            ("zstr", 4, 0x13, 0x15),
            ("cirs", 4, 0x14, 0x16),
            ("addt", 4, 0x15, 0x17),
            ("init", 4, 0x16, 0x18),
            ("rfpt", 4, 0x17, 0x1B),
            ("wfpt", 4, 0x18, 0x1C),
            ("rest", 4, 0x19, 0x1D),
            ("getv", 4, 0x1A, 0x1E),
            ("draw", 4, 0x1B, 0x1F),
            ("covx", 4, 0x1C, 0x20),
            ("showqq", 8, 0x0D, 0x0E),
            ("substr", 8, 0x0E, 0x0F),
            ("prints", 8, 0x0F, 0x10),
            ("pa_txt", 8, 0x10, 0x11),
            ("udelete", 8, 0x11, 0x12),
            ("strsize", 8, 0x12, 0x13),
            ("crcputh", 8, 0x13, 0x14),
            ("touch_j", 8, 0x14, 0x15),
            ("crcputs", 8, 0x15, 0x16),
            ("randset", 8, 0x16, 0x17),
            ("crcrest", 8, 0x17, 0x18),
            ("crcputu", 8, 0x18, 0x19),
            ("lcd_dev", 8, 0x19, 0x1A),
            ("lhmi_cle", 8, 0x1A, 0x1B),
            ("whmi_cle", 8, 0x1B, 0x1C),
            ("setbrush", 8, 0x1C, 0x1D),
            ("ref_stop", 8, 0x1D, 0x1E),
            ("com_stop", 8, 0x1E, 0x1F),
            ("ref_star", 8, 0x1F, 0x20),
            ("com_star", 8, 0x20, 0x21),
            ("doevents", 8, 0x21, 0x22),
            ("timerset", 8, 0x22, 0x23),
            ("getpassw", 8, 0x23, 0x24),
            ("lcd_refx", 8, 0x24, 0x25),
            ("setbaudz", 8, 0x25, 0x26),
        ),
        "operands": (
            ("tch0", 4, 0x06, 0x07),
            ("sya1", 4, 0x07, 0x09),
            ("tch1", 4, 0x08, 0x0B),
            ("tch2", 4, 0x09, 0x0E),
            ("tch3", 4, 0x0A, 0x11),
            ("rand", 4, 0x0D, 0x20),
            ("baud", 4, 0x0E, 0x21),
            ("thsp", 4, 0x0F, 0x23),
            ("ussp", 4, 0x10, 0x24),
            ("thup", 4, 0x11, 0x25),
            ("usup", 4, 0x12, 0x26),
            ("addr", 4, 0x13, 0x27),
            ("dims", 4, 0x14, 0x28),
            ("bcpu", 4, 0x15, 0x29),
            ("spax", 4, 0x16, 0x2A),
            ("spay", 4, 0x17, 0x2B),
            ("BLUE", 4, 0x0B, 0x1E),
            ("GRAY", 4, 0x0C, 0x1F),
        ),
        "attribute_limits": (),
        "page_size": None,
    },
    "E": {
        "leader": "P",
        "commands": (),
        "operands": (),
        "attribute_limits": (),
        "page_size": ((800, 480), (480, 480)),
    },
}
