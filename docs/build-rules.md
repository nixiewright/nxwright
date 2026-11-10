# What the build refuses

The build command checks your source folder before it writes the project file. It refuses what the Nextion Editor would refuse to open or to compile, so that a project nxwright builds also compiles in the Nextion Editor. The build stops at the first refusal, and gives its file and line.

- `nxwright check` runs the same checks without writing anything ([commands.md](commands.md#check)).
- The [VS Code extension](../editors/vscode/README.md) shows refusals as you type.

Most sections below are lists of what the build refuses. A quoted message in parentheses is the Nextion Editor's own.

## Page files

### Names and lengths

- A page's or a component's name longer than 14 bytes. The Nextion Editor cuts it when it opens the project.
- A page or a component with the same name as a system variable, such as `dim` or `audio0`, or a colour, such as `BLACK`. The Nextion Editor renames it when it opens the project ("Illegal name").
  - The match is exact, case included: `DIM` and `dim1` are fine.
  - `sys0` to `sys2`, the commands, and the keywords are not among these names.
- A page's or a component's name that starts with a digit, such as `2page`. The Nextion Editor refuses the project when it opens it ("First character of a Name can not be number"). `nxwright new-page` refuses such a name too.
- A `txt` longer than its `txt_maxl` bytes. The Nextion Editor cuts it when it opens the project.
- A text attribute longer than its bound, which is the attribute of the same name ending in `_m`. Examples are an external picture's `path` past its `path_m`, a data record's `filter` past its `filter_m`, and a file browser's `dir` past its `dir_m`. The Nextion Editor keeps the text when it opens the project, warns about most of these, and refuses to compile them ("The length exceeds the maximum value").
  - The build allows two cases, because the Nextion Editor compiles them:
    - a video's or a sound's `path` while its `from` is 0;
    - a data record's `format` and `dir`, up to a limit worked out from the bound: add 1, round up to a multiple of 4, and subtract 1. For example, a `format_m` of 8 allows a `format` of 11 bytes, and the screen shows all 11.
  - A sliding text's `path_m` sets aside room for the text's lines, and does not limit its `path`.

### Values the Nextion Editor refuses

- a text's `style` past 3. A `style` of 4, 3D auto, is for buttons.
- a select's `style` of 2, sunken, on every series that has a select;
- a gauge's `val` past 360 degrees, its `left` past 1024, or its `wid` outside 1 to 20, whatever the gauge's size;
- an `aph` past 127, on a page or any component;
- a scrolling text's `tim` outside 80 to 65534;
- an xfloat's `vvs1` past 8, the digits after its point, or its `vvs0` past 10, the digits before it;
- a waveform's `dir` past 2;
- a component narrower or shorter than 2 pixels. When it opens the project, the Nextion Editor reports "Width can not be less than 2", or the same for "Height", and sets that side back to the type's default. The project would then differ from the page file;
- a component of local scope bound to a keyboard by its `key`. The Nextion Editor binds a keyboard only to a component of global scope (`vscope = 1`);
- any other value outside the range the Nextion Editor takes for its attribute, such as a text's `xcen` past 2 or a timer's `tim` under 50. `nxwright/project/attribute_ranges.toml` gives each range.

The Nextion Editor also refuses these values, on attributes its Attribute panel never shows:

- a button's `val` past 1;
- a file browser's `xcen` past 2;
- a combo box's `drastate` past 1;
- a hotspot's `drag` past 1, or its `effect` past 8.

### Values outside an attribute's choices

Many attributes take only a few values, and the Nextion Editor's Attribute panel offers them as a list. For example, `vscope` is 0 for local or 1 for global. The build refuses any other value, on every series, so `vscope = 2` stops the build with "vscope must be 0 (local) or 1 (global)". In the VS Code extension, hovering over an attribute shows its choices.

### A page's place and size

Every page fills the screen, in the project's rotation. The Nextion Editor resets each page to this when it opens a project, so the build does the same, and ignores any `x`, `y`, `w`, and `h` a page file gives the page. You can leave them out.

- The `page-place` warning shows each of these values that differs from the screen's ([commands.md](commands.md)). `nxwright device` writes the screen's size into each page file.
- Without screen settings in `app.toml`, the build keeps the page file's values.

### Fonts

- A component whose font, whether set or left at its type's default of 0, is not one of the project's fonts ("Invalid Font ID"). The most likely case is a text in a folder that has no fonts.

### How many components a page can have

A page can have at most 250 components, of any type ("Too many components"). This includes the components nxlang adds to run your code.

Some types also have a limit of their own, the same on every series that has these types:

- 5 waveforms ("Waveform components exceed maximum in page:5");
- 16 animations and videos together;
- 12 timers and scrolling texts together, which the Nextion Editor calls timer events.

### How many pages a project can have

A project can have at most 251 pages, keyboard pages included ("Too many pages").

### What a series refuses

Each series of screens lacks some component types and choices, and some series take a smaller range of values for some attributes. The Nextion Editor refuses to compile a component that uses one of these ("Unsupported component was found for this series device", and "Out of range").

Types:

- The Basic (T), Enhanced (K), and Discovery (F) series refuse 11 types: audio, combo box, data record, external picture, file browser, file stream, animation (`gmov`), select, sliding text, switch, and video.
- The Intelligent (P) and Edge (E) series take every type.

Choices:

- On the T, K, and F series:
  - a `sta` of 3 (the choice "nothing", where the page shows through), on every type with that choice, including a gauge, where it is nxwright's default;
  - a slider's `psta` of 2, a square knob.
- On the P and E series: a data record of local scope, and a file stream of global scope.

Values:

- On the P and E series, a slider's `ch` over 100, when the slider has a colour behind its track (`sta` 1). The T series takes up to 255.
- On the P and E series, a component's `x` or `y` past 6000, or its `w` or `h` past 2000.
- A QR code's `txt_maxl` past 192 on the T and K series, 368 on the F series, and 630 on the P and E series.

Place on the screen:

- On the T, K, and F series, a component that starts or ends past the screen's right or bottom edge, in the screen's rotation ("Position Invalid"). A component ending exactly at an edge is fine.
- The P and E series allow a component off the screen, within the limits under Values above.

The full lists are in `nxwright/project/memory_costs.toml` (`refused` and `refused_values`), in `nxwright/source/series_components.py` (`CHOICES_REFUSED_BY_SERIES`), and in `nxwright/project/attribute_ranges.toml`.

### Memory

The build counts each page's memory the same way as the Nextion Editor's compile ([format.md, The Nextion Editor's memory](format.md#the-nextion-editors-memory)).

- A page's total is the project's global memory plus the page's own. The build refuses a page whose total is more than the screen's memory, and gives the Nextion Editor's numbers:

  ```
  page0.page.toml: its memory, 16 + 4072 = 4088 bytes, passes the NX4832T035's 3584, and the Nextion Editor's compile refuses it ("Memory overflow")
  ```

- The total counts the pages as built, including keyboard pages and the components nxlang generates. Global memory includes the number globals nxlang generates, at 4 bytes each.
- A page is also refused if its total leaves less memory than its QR codes need.
- If several pages are refused, the build stops at the first, and `nxwright check` reports each one.
- A text longer than its bound, in the cases the Nextion Editor compiles, counts as the length of its bound.

nxwright has not measured the memory of every component, such as a sliding text on the Intelligent and Edge series whose `path` is not empty. It counts such a component as taking no memory, so a page's real total may be higher than the count. The build warns, and lists each page's memory as `at least`:

```
nxwright build: warning: memory counted without page0.st0, as the memory of a sliding-text whose path is not '' was not measured
```

If the build refuses a page even with this low count, the Nextion Editor's compile refuses it too, and the message gives its numbers as `at least`.

## Code

### Names that must exist

The build stops at the first line that uses something that does not exist:

- In `t0.txt`, `t0` must be a component of the page.
- In `settings.t0.txt`, `settings` must be a page, and `t0` one of its components.
- Some commands take a component: `vis`, `tsw`, `ref`, `click`, and `move` as their first argument, `cfgpio` as its third, and `setlayer` as both arguments. That argument must be a component of the page, as in `vis t0,1`, a component's number, as in `vis 1,0`, or a variable that contains a component's number, as in `vis sys0,0`.
  - A name that is neither a component nor a variable is refused, as in `vis zz,0` ("Invalid Component ID").
  - A component's `txt` is refused as well, as in `vis t0.txt,0` ("Invalid Component ID").
  - `program.nx` belongs to no page, so in that file these commands take only a component's number or a variable. The name of a page or a component is refused, as in `vis t0,0` or `vis page0.t0,0` ("Invalid Component ID").
  - `b[1]` and `p[0].b[1]` are refused in `program.nx` too ("Invalid Component ID"). In nxlang, `vis b[1],0` in `program.nx` is written as `vis 1,0` ([nxlang-compiled.md](nxlang-compiled.md#programnx)).
- A name alone in a value or a condition, such as `abc` in `n0.val=abc+1`, must be an `int` of `program.nx`, a system variable, or a colour in capitals, such as `RED`. A component's or a page's name alone is refused.
- Another page's components need their page's name, and must be of global scope.
- A page's own attributes, such as `bco`, can only be used by its own code. On any other page, `sys0=settings.bco` is refused ("Invalid Variables").
- In `program.nx`, which belongs to no page, a component's attribute needs its page's name, as in `sys0=page0.n0.val`. The component must also be of global scope.
  - Without the page's name, the line is refused. The Nextion Editor's message depends on the line: "Invalid Variables" for `sys0=n0.val`, "Invalid Page ID" for `page n0.val`, and "Invalid Component ID" for `vis n0.val,0`.
  - If `n0` is of local scope, `sys0=page0.n0.val` is refused too ("Invalid Variables").

Not checked: a component chosen as the code runs, as in `b[3].txt`, and a number in a component's place, as in `tsw 255,0`.

### `'&name&'`, an attribute of the event's own object

In an event's code, `'&name&'` stands for an attribute of the object the event belongs to, as the vendor's instruction set documents (section 9). The Nextion Editor replaces it before it compiles, even in a quoted text:

- `'&id&'` becomes the object's ID.
- Any other name becomes the object's name, a dot, and the name. In an event of `n0`, `'&val&'+=10` adds 10 to `n0.val`, and `t0.txt="'&val&'"` shows `n0.val`.

The build keeps the line as written, but checks it with the name replaced. So `'&val&'="a"` is refused, just as `n0.val="a"` would be.

- The build refuses `'&name&'` in `program.nx` and in macros, which belong to no event ("Invalid Variables").
- In a quoted text in `program.nx` or in a macro, `'&name&'` stays as written, even when an event calls the macro: `print "a'&name&'b"` sends `a'&name&'b`.
- nxlang accepts `'&name&'` in an event's code, and writes the line with it replaced. In a function or a constant, nxlang refuses it ([language.md](language.md#limits)).

### Hexadecimal numbers

In strict Nextion syntax, the build refuses these hexadecimal numbers, written with `0x` or `0X`. nxlang accepts them with `0x`, and writes them in a form the Nextion Editor reads ([language.md](language.md)).

- An odd number of digits: `0x123` (write `0x0123`).
- Any hexadecimal number in an `int`'s starting value: `int dow=0x06`.
- A number past 32 bits: `0x0100000000`. Leading zeros are fine: `0x0000000001` is 1.
- A number with a sign, such as `-0x10` after `=`, `==`, or `*`. Subtracting one, as in `5-0x10`, is fine.

### Values and conditions

In strict Nextion syntax, the build refuses a line the Nextion Editor cannot read:

- A value that is not operands joined by operators, such as `n0.val=2+`, `n0.val=+2`, or `n0.val=(1+2)` ("Invalid Variables"). After an operator, a minus can start a number, as in `n0.val=2*-16`, but not a name: `n0.val=2*-n1.val` is refused.
- An assignment with no value: `n0.val=` ("Invalid command").
- Where a command takes a number ([Texts and numbers](#texts-and-numbers)), an operand the Nextion Editor does not read, as in `cls 5a`, `cls 1_000`, `cls RED+*1`, or `cls -n0.val` ("Invalid Variables").
  - The build refuses these in nxlang too, with one exception. nxlang reads some operands that the Nextion Editor does not, such as a minus before a name. In a page's code, nxlang first computes such an operand into a temporary variable, so `cls -n0.val` builds ([nxlang-compiled.md](nxlang-compiled.md#how-expressions-are-written)).
- An `if`, `else if`, `while`, or `for` whose condition does not end with `)`.
- A `for` whose head contains a text with a semicolon, in any of its parts, such as `for(n0.val=0;t0.txt!="a;b";n0.val++)` ("SYNTAX ERROR:for"). A `while` or an `if` accepts that text. nxlang rewrites the `for` as its first part followed by a `while` loop ([nxlang-compiled.md](nxlang-compiled.md#how-expressions-are-written)).

### Data record calls

The build refuses a data record call that the Nextion Editor refuses when it compiles:

- a number of arguments other than these: `d0.insert(text)`, `d0.delete(number, count)`, `d0.up(text, number)`, `d0.clear()`;
- a text where a number goes, such as `"1"` or `t0.txt`;
- texts joined where a text goes, such as `t0.txt+"^"+t1.txt`.

A number where a text goes compiles, but does not add anything on the screen. In nxlang, an argument the Nextion Editor would refuse as written is computed first instead, and a number where a text goes becomes its digits ([nxlang-compiled.md](nxlang-compiled.md#how-expressions-are-written)).

### File stream calls

The build refuses a file stream call with the wrong number of arguments ("Invalid number of arguments"). The right forms are `fs0.open(path)`, `fs0.read(text, start, count)`, `fs0.write(text, start, count)`, `fs0.close()`, and `fs0.find(path)`.

- A text is fine as `open`'s path, as in `fs0.open(t0.txt)`.
- Arithmetic is fine in `read`'s numbers, as in `fs0.read(t0.txt,n0.val+1,2)`.
- nxlang passes a file stream call through as written, so the build refuses the wrong number of arguments in nxlang too.

### First arguments

The first argument of `get`, `print`, `prints`, and `covx` is one text or one number. The build refuses arithmetic or joined texts there, such as `get n0.val+1` or `print "a"+t0.txt` ("Invalid Variables"). A minus before a name is refused there too, as in `print -sys0` or `print -RED`, but a minus before a number is fine, as in `print -5`.

- Arithmetic is fine in `prints`' length, in `covx`'s length and form, and in `newfile`'s size.
- In nxlang, you can write arithmetic, joined texts, or a minus before a name as a first argument, and nxlang computes it first ([nxlang-compiled.md](nxlang-compiled.md#how-expressions-are-written)).

Other commands also take a single value in some arguments. The build refuses an expression there, such as `getv sys0+1` or `spstr t0.txt,t0.txt,"a"+"b",0`, and a minus before a name, such as `getv -sys0` or `getv -RED` ("Invalid Variables"). A minus before a number is fine, as in `getv -5`. These arguments are:

- Arguments the command only reads: the value `wepo` writes, the value `crcputs` sends, the file `delfile` deletes, the text that `strlen`, `substr`, `spstr`, and `btlen` read, and the separator `spstr` splits on. In nxlang, you can write an expression or a minus before a name in these, and nxlang computes it first ([nxlang-compiled.md](nxlang-compiled.md#how-expressions-are-written)).
- Arguments where the command puts its result: the variable that `cov`, `covx`, `strlen`, `repo`, and `ucopy` write their result to, and the one `findfile` sets.
- Arguments of commands that Nextion does not document:
  - every argument of `getv`, `pa_q`, and `sets`;
  - the first argument of `fstr` and `nstr`, and the first two of `i`;
  - the second argument of `pa_txt` and `gets`;
  - the third argument of `strsize`, the fourth of `piccolor`, the fifth of `zstr`, and the eighth of `qrcode`.

The last argument of `xstr`, its text, must also be a single value: a text, a `txt`, a number, or a variable. The build refuses joined texts, arithmetic, and a minus before a name there, such as `xstr 0,0,100,30,0,RED,WHITE,0,0,1,"a"+"b"` or `xstr 0,0,100,30,0,RED,WHITE,0,0,1,-sys0` ("Invalid Variables"). In nxlang, you can write these, and nxlang computes the text first. The exception is `program.nx`, which has no temporaries.

### Texts and numbers

- A text given to a number, or a number to a text: `n0.val=t0.txt`, `t0.txt=5` ("Assignment operation failed").
  - A `txt` is a text. A `val`, a `pco`, a `font`, a system variable, and `program.nx`'s `int` variables are numbers.
  - Other attributes, and those reached through `b[]` and `p[]`, are left to the Nextion Editor.
- In an assignment, a text joined to a number, or an operator other than `+` and `-` on a text: `t0.txt=t0.txt+5`, `n0.val+=t0.txt`, `t0.txt*=2` ("Invalid variable operation").
  - A text minus a number removes characters, and compiles.
  - A condition is not an assignment: `if(t0.txt=="a")` compiles.
- A text or a `txt` where a command takes a number, as in `cls t0.txt` or `cls "1"` ("Invalid variable operation").
  - These arguments take a number: the colour of `cls`, every argument of `add`, `addt`, and `cle`, the length of `prints`, the size of `newfile`, the second argument of `rdfile`, and the third and fourth arguments of `pa_txt`.

nxlang itself refuses a text put into a number, and converts a number put into a text.

### Escapes

- An escape in a quoted text other than `\r`, `\"`, and `\\`, such as `\n` or `\t` ("Improper use of escape characters").
  - Escapes are read in pairs from the left, so `"a\\nb"` contains `\\` followed by the letters `nb`, and is fine.
  - A comment is not compiled, so its escapes do not count.
- A text that ends in an escaped backslash, inside a condition: `if(t0.txt=="a\\")` ("SYNTAX ERROR").
  - A condition is the head of an `if`, an `else if`, or a `while`, and the middle part of a `for`'s head. Such a text compiles elsewhere, as in `t0.txt="\\"`, or in a `for`'s first or last part.

The build refuses these in nxlang too, except for a text that ends in an escaped backslash, which nxlang puts into a temporary first ([nxlang-compiled.md](nxlang-compiled.md#how-expressions-are-written)). Because `program.nx` has no temporaries, the build still refuses that text in a condition in `program.nx`.

### Texts in gb2312, big5, and shift-jis

The Nextion Editor reads a text in code by its bytes, so some texts in these encodings end in the wrong place. The build refuses them:

- A shift-jis text where a half-width katakana, such as ｱ, makes the Nextion Editor read the closing quote as part of the text: `t0.txt="aｱ"` ("Invalid Variables").
  - The Nextion Editor reads every text in pairs of bytes. A half-width katakana is a single byte, so it gets paired with the next byte.
  - `t0.txt="ｱa"` and `t0.txt="ｱｱ"` compile, because each pair ends before the closing quote.
  - The build refuses the line in nxlang too.
- A text in a condition, or before a comma in `prints`, `spstr`, `strlen`, `btlen`, or `crcputs`, whose last byte is 0x5C, the code of a backslash: `if(t0.txt=="表")` or `prints "日表",0` ("Invalid number of arguments").
  - 表 in shift-jis, 許 in big5, and 乗 in gb2312 each end in that byte. In these places, the Nextion Editor takes it for a backslash, which escapes the closing quote.
  - The same text compiles elsewhere, as in `t0.txt="日表"` or `print "日表"`.
  - In an nxlang event, the build puts such a text into a text temporary first, and the line builds ([nxlang-compiled.md](nxlang-compiled.md)).

### Attributes a component lacks

The build refuses an attribute that a component, or the page, lacks, whether assigned or read ("Invalid Variables"). That includes a name a component's type does not have at all, such as `n0.vall`, or a number's `txt`.

- A type has the attributes its defaults list (`nxwright/project/component_defaults.toml`), its methods among them. It also has `id`, `type`, and `objname`, and `endx` and `endy` where it has a place on the screen.
- Letter case matters.
- A method, such as `insert` in `d0.insert("a^b")`, may be read, but not assigned: `d0.insert=1` and `fb0.up=1` are refused.

Some attributes exist only for some values of a component's choices, whether its page file sets the value or leaves it at the default. The rules are the same on every series (`PRESENT_WHILE` in `nxwright/project/editor_limits.py`). The message gives the reason, as in `t0 has its sta at 1, so it has no pic`. Among the rules:

- `first` and `time` exist only while `effect` is not 0.
- When `sta` sets where the background comes from, `picc` exists only at 0 (a crop of a picture), `bco` and `style` at 1 (a colour), and `pic` at 2 (a picture).
- `borderc` and `borderw` exist only while `style` is 1, a border.
- A waveform's channel colours exist only up to its number of channels, `ch`.
- A variable's `val` exists while it stores a number (`sta` 0), and its `txt` and `txt_maxl` while it stores a text.
- A video's or a sound's `path` and `path_m` exist while it plays a file of an SD card (`from` 1). Its `vid`, and an animation's, exist while its `from` is 0.

Some attributes exist only on the Intelligent and Edge series. On the Basic, Enhanced, and Discovery series, the build refuses them even for reading, with a message such as `t0 is on an NX4832T035, so it has no movex`. The list is `SERIES_LACKED_ATTRIBUTES` in `nxwright/project/editor_limits.py`:

- `movex`, `movey`, `lockobj`, `groupid0`, `groupid1`, and `sendkey`, of any component;
- `objname`, of any object;
- a waveform's `objWid`, `objHig`, `inittrue`, `molloc`, and `molloc_s`.

The build refuses missing attributes in nxlang too.

### Commands

- A line whose first word is not a command the Nextion Editor knows ("Invalid command"). That includes `dir`, and a name alone, such as `sys0`.
  - The commands are those in the vendor's instruction set, plus undocumented ones the Nextion Editor knows, such as `beep`, `lcd_dev`, and `setbrush`, all written in small letters (`EDITOR_COMMANDS` in `nxwright/project/editor_language.py`).
  - A first word with a capital letter, such as `CLS`, and `movelayer`, get "Invalid Variables" instead.
- A command given the wrong number of arguments, such as `cls 1,2`, `get 1,2`, or `doevents 1`, or written without any, such as `cls` or `page` ("Invalid number of arguments"). `add` alone gets "Invalid command".
  - The numbers of arguments come from the vendor's instruction set or, for an undocumented command, from what it was seen to compile with.
  - A command whose number of arguments is not fixed, such as `sets`, takes any number.
- `page` given a quoted text, as in `page "page0"` ("Invalid Page ID"). It takes a page's name without quotes, or its number.
- `page` given a name that is neither a page nor a variable, as in `page zz` ("Invalid Page ID"). That also covers a component's name, as in `page t0`, and a page's name in another letter case.
  - A page's name must be the whole argument: `page settings+1` is refused too.
  - A value is fine, such as `page sys0`, `page sys0+1`, or `page n0.val`.

### Long lines

In either language, the build refuses a line of code longer than the Nextion Editor compiles on your screen's series ("The instructions are too long"):

- 767 bytes on the Basic (T), Enhanced (K), and Discovery (F) series;
- 4095 bytes on the Intelligent (P) and Edge (E) series.

The limit applies in a page's code, in `program.nx`, and in macros.

- The bytes are counted in the folder's encoding. In gb2312, `t0.txt="中中…中"` with 380 中 is 769 bytes, too long on the Basic series.
- Spaces the build removes, such as those around `=`, are not counted. Spaces inside a quoted text are.
- The build does not limit an `int` declaration, or the head of an `if` or a `while` as a whole. In a `for`'s head, the start and the step each count as a line of their own, such as `sys0=0` and `sys0++` in `for(sys0=0;sys0<9;sys0++)`.
- Each comparison in a condition counts as a line of its own, because the Nextion Editor turns it into one. That line is the comparison's two sides plus 7 bytes. `t0.txt=="…"` with a text of 753 characters makes a line of 768 bytes, too long on the Basic series. A long condition of short comparisons, such as `sys0==1&&sys1==2&&…`, is not refused.
  - In an nxlang event, the long texts of such a comparison go into text temporaries first, so the line builds. In `program.nx`, which has no temporaries, the build refuses it.

nxlang writes a long text assignment, a long `print` of a text, and a long number assignment in several lines, so the build does not refuse them ([nxlang-compiled.md](nxlang-compiled.md#how-expressions-are-written)). A long number assignment in `program.nx` is still refused, because it needs a temporary.

### What a series lacks

In either language, the build refuses a command or a system variable that the series of your screen lacks ("Do not support such instruction for this series device", or "such variable"). This applies in a page's code, in `program.nx`, and in macros. A name inside a quoted text is not a variable. The lists are `SERIES_LACKED_COMMANDS` and `SERIES_LACKED_VARIABLES` in `nxwright/project/editor_language.py`:

- **Basic (T)**: everything the Enhanced lacks, and the commands `rept`, `wepo`, `repo`, `wept`, and `cfgpio`, and the variables of the GPIO pins (`pio0` to `pio7`, `pwm4` to `pwm7`, `pwmf`) and of the clock (`rtc0` to `rtc6`).
- **Enhanced (K)**:
  - the SD card's commands (`findfile`, `finddir`, `newfile`, `delfile`, `newdir`, `deldir`, `refile`, `redir`), `play`, `twfile`, `rdfile`, `move`, `setlayer`, and `beep`;
  - the undocumented `sets`, `cuts`, `gets`, `xnum`, `cfguart`, `meup`, `beepset`, and `piccolor`;
  - the sound's variables (`audio0`, `audio1`, `volume`, `eq0` to `eq9`, `eql`, `eqm`, `eqh`), `lowpower`, `scache`, the serial line's send buffer switch, `tprc`, and `aph`.
- **Discovery (F)**:
  - the SD card's commands, `play`, `twfile`, `rdfile`, `move`, `setlayer`, `rept`, and `wept`;
  - the undocumented `cfguart`, `meup`, and `beepset`;
  - the sound's and the clock's variables, `scache`, `tprc`, and `aph`.
- **Intelligent (P) and Edge (E)**: the undocumented `fstr` and `piccolor`, and `lowpower`.

### Labels

- A `goto` whose label is not in the same event.
- A label written twice in one event, whatever block it is in.

Labels are case-sensitive: `goto Up` does not find `up:`.

### `sys0` to `sys2`

The build refuses code that uses `sys0`, `sys1`, or `sys2` where `program.nx` does not declare it, in either language ("Invalid Variables"). The vendor's instruction set lists them among the system variables, but they are `program.nx`'s `int` variables. A new project from the Nextion Editor or from `nxwright new` declares them: `int sys0=0,sys1=0,sys2=0`.

### Names of `program.nx`'s `int` variables

In either language, the build refuses an `int` variable of `program.nx` whose name is already used by:

- a command, such as `int sets=0`, even one your screen's series lacks ("Conflict with instructions name");
- a system variable, such as `int dim=0` ("Illegal name");
- a page, such as `int page0=0` ("Conflict with page name");
- a component on any page, such as `int t0=0` ("Conflict with Component name"). So a component cannot be named `sys0`, `sys1`, or `sys2` while `program.nx` declares them, which it does in a new project;
- a colour, such as `int RED=1` ("Illegal name");
- another `int`, on the same line or another, such as `int a=1,a=2` ("Repeated definition global variable name").

Names are case-sensitive, so `int Red=1` and `int a=1,A=2` are fine. A name may have up to 32 characters ("Illegal global variable name length").

### Where an `int` goes, and its starting value

- An `int` goes in `program.nx`, in either language. The build refuses an `int` in an event, in a macro, or in an nxlang function ("Global variable definitions must precede all code in the program"). In nxlang, `var` declares a local ([language.md](language.md#local-variables)).
- In strict Nextion syntax, an `int` goes before `program.nx`'s other code. Comments may come first. nxlang moves a later `int` line up for you ([nxlang-compiled.md](nxlang-compiled.md)).
- A starting value must be a whole number written in decimal. In nxlang, it can also be a hexadecimal number or a constant. The build fails for anything else, such as another variable, arithmetic, or a text: `int b=a`, `int a=1+2`, `int a="x"`.
- In strict Nextion syntax, a decimal starting value must fit in 32 bits, from -2147483648 to 2147483647. The build refuses `int a=4294967295` ("Initial value for a global variable must be a constant"). nxlang writes the value's low 32 bits instead, like C ([language.md](language.md)).
- In strict Nextion syntax, the build refuses a tab after `int`, because the Nextion Editor reads it as part of the variable's name. nxlang writes a space there instead ([nxlang-compiled.md](nxlang-compiled.md#how-expressions-are-written)).

### Attributes code cannot change

In either language, the build refuses a line assigning to an attribute that code cannot change ("Assignment operation failed").

- These are the attributes shown in black in the Nextion Editor's Attribute panel, and some the panel never shows but the Nextion Editor still refuses. `nxwright/project/attribute_descriptions.toml` marks each one. Examples are a text's width, in `t0.w = 10` or `settings.t0.w = 10`, an animation's `from`, and a waveform's `objWid`.
- A component's `id`, `type`, and `objname` are refused too, on every type, and its `endx` and `endy`, on a type with a place on the screen.
- Every form of assignment counts: `=`, `+=` and the others, `++`, and `--`.
- Code in a file that multiple pages include is checked within the context of each page in which it appears: a line may fail to build for only one page, for instance if that page has a component with the same name but of an incompatible type.
- A component the build cannot identify, such as `b[1]`, is left to the Nextion Editor.
- The Basic (T), Enhanced (K), and Discovery (F) series also refuse code setting some attributes. Reading them is fine. The list is `ATTRIBUTES_CODE_CANNOT_CHANGE_ON_SERIES` in `nxwright/project/editor_limits.py`:
  - `x`, `y`, `aph`, `drag`, `effect`, `first`, and `time`, on every type that has them, the page's too;
  - `borderc`, `borderw`, `spax`, and `spay`, on a button, a dual-state button, and a text;
  - `vvs0` and `vvs1`, on a crop.

### Characters the encoding cannot store

The build stops at a character that the folder's encoding cannot store, and gives its file ([Text and its encoding](source-folder.md#text-and-its-encoding)).

## Macros

The build refuses these ([Macros](source-folder.md#macros)):

- A `call` of a macro the folder lacks, in an event, a macro, or `program.nx`.
- A macro's name used twice, or a name that starts with a digit or has characters other than letters, digits, underscores, and spaces.
- In a macro, a component without its page's name, as in `t1.txt`, or of local scope, as in `page0.t0.txt` with `t0` local. A macro can use only components of global scope, with their page's name: `page0.t1.txt`, with `t1` global.
- In a macro, a component given to `vis`, `tsw`, `ref`, or `click` by its name, with its page's name or not. Give the component's number instead, as in `vis 1,0`, or a variable or a value that contains it, as in `vis sys0,0`.
- In a macro, anything the build refuses in an event's code, such as a `goto` without its label, an attribute code cannot change, or `sys0` undeclared.
