# What the build refuses

The build checks your source folder before it writes the project file. It refuses what the Nextion Editor would refuse to open or to compile, so that a project nxwright builds also compiles in the Nextion Editor.

- `nxwright check` runs the same checks without writing anything ([commands.md](commands.md#check)).
- The [VS Code extension](../editors/vscode/README.md) shows them as you type.

For each refusal below: what is refused, an example, and the Nextion Editor's own message where it has one. The build stops at the first one, and gives its file and line.

## Page files

### Names and lengths

- A page's or a component's name longer than 14 bytes. The Nextion Editor cuts it when it opens the project.
- A page or a component named as a system variable, such as `dim` or `audio0`, or as a colour, such as `BLACK`. The Nextion Editor renames it as it opens the project ("Illegal name").
  - The match is exact, case included: `DIM` and `dim1` are fine.
  - `sys0` to `sys2`, the commands, and the keywords are not among these names.
- A page's or a component's name that starts with a digit, such as `2page`. The Nextion Editor refuses the project as it opens it ("First character of a Name can not be number"). `nxwright new-page` refuses such a name too.
- A `txt` longer than its `txt_maxl` bytes. The Nextion Editor cuts it when it opens the project.
- A text attribute longer than its bound: an attribute `X` longer than its `X_m` bytes. Examples are an external picture's `path` past its `path_m`, a data record's `filter` past its `filter_m`, and a file browser's `dir` past its `dir_m`. The Nextion Editor keeps the text as it opens the project, warns of most, and refuses to compile it ("The length exceeds the maximum value").
  - Allowed where the Nextion Editor compiles it: a video's or a sound's `path` while its `from` is 0, and a data record's `format` and `dir` up to their bound plus 1, rounded up to a multiple of 4, less 1. A `format_m` of 8 takes a `format` of 11 bytes, which the screen shows whole.
  - A sliding text's `path_m` is not such a bound: it sets aside room for the text's lines.

### Values the Nextion Editor refuses

- a text's `style` past 3. The Nextion Editor's 4, 3D auto, is a button's.
- a select's `style` of 2, sunken, refused on every series that has a select;
- a gauge's `val` past 360 degrees, its `left` past 1024, or its `wid` outside 1 to 20, whatever the gauge's size;
- an `aph` past 127, on a page or any component;
- a scrolling text's `tim` outside 80 to 65534;
- an xfloat's `vvs1` past 8, the digits after its point, or its `vvs0` past 10, the digits before it;
- a waveform's `dir` past 2;
- a component narrower or lower than 2 pixels. When it opens the project, the Nextion Editor reports "Width can not be less than 2", or "Height", and sets that side back to the type's default. The project would then differ from the page file;
- a component bound to a keyboard by its `key` whose scope is local. The Nextion Editor binds a keyboard only to a component of global scope (`vscope = 1`).

The Nextion Editor's panel never shows these attributes, but refuses these values too:

- a button's `val` past 1;
- a file browser's `xcen` past 2;
- a combo box's `drastate` past 1;
- a hotspot's `drag` past 1, or its `effect` past 8.

### Fonts

- A component whose font is none of the project's fonts, either given or its type's default of 0 ("Invalid Font ID"). The most likely case is a text in a folder that has no fonts.

### How many of a kind a page takes

The build names the first component past the limit. The limits are the same on every series that has these types:

- 5 waveforms ("Waveform components exceed maximum in page:5");
- 16 animations and videos together;
- 12 timers and scrolling texts together, which the Nextion Editor calls timer events.

### What a series refuses

Each series of screens lacks some types and some choices, which the Nextion Editor's compile refuses ("Unsupported component was found for this series device", and "Out of range"). The build names the component.

Types:

- The Basic (T), Enhanced (K), and Discovery (F) series refuse 11 types: audio, combo box, data record, external picture, file browser, file stream, animation (`gmov`), select, sliding text, switch, and video.
- The Intelligent (P) and Edge (E) series take every type.

Choices:

- On the T, K, and F series:
  - a gauge's `sta` of 3, which is nxwright's default for a gauge;
  - a `sta` of 3, nothing, so that the page shows through, on every type with that choice;
  - a slider's `psta` of 2, a square knob.
- On the P and E series: a data record of local scope, and a file stream of global scope.

The full lists are in `nxwright/project/memory_costs.toml` (`refused` and `refused_values`) and in `nxwright/source/series_components.py` (`CHOICES_REFUSED_BY_SERIES`). A value past an attribute's range, such as a QR code's `txt_maxl` of 193 on the Enhanced series, is left to the Nextion Editor, since the range itself is not known.

Place on the screen:

- On the T, K, and F series, a component reaching past the screen's right or bottom edge, at the screen's rotation, or starting past it ("Position Invalid"). A component ending exactly at an edge is fine.
- The P and E series take a component anywhere.

### Memory

The build counts each page's memory as the Nextion Editor's compile does ([format.md, The Nextion Editor's memory](format.md#the-nextion-editors-memory)).

- A page's total is the project's global memory plus the page's own. The build refuses a page whose total passes the screen's memory, with the Nextion Editor's numbers:

  ```
  page0.page.toml: its memory, 16 + 4072 = 4088 bytes, passes the NX4832T035's 3584, and the Nextion Editor's compile refuses it ("Memory overflow")
  ```

- It counts the pages as built, with nxlang's generated components and keyboard pages. It counts the global memory from `program.s` as built, so nxlang's generated number globals count among its `int`s, 4 bytes each.
- It also refuses a page whose total leaves less memory than its QR codes need. The message gives the QR code, and how much memory is missing.
- The build stops at the first page refused. `nxwright check` reports each one.

nxwright only counts what it has measured. It counts a component it has not measured as taking no memory, so each total is at least what it counts. If nxwright refuses a page even so, the Nextion Editor's compile refuses it too. The message then gives its numbers as `at least`. The build warns, and lists each page's memory as `at least`:

```
nxwright build: warning: memory counted without page0.st0, as the memory of a sliding-text whose path is not '' was not measured
```

nxwright has not measured some values, such as a sliding text's `path` other than empty on the Intelligent and Edge series. A text longer than its bound, where the Nextion Editor compiles it, counts as its bound, as the compile counts it.

## Code

### Names that must exist

The build stops at the first line that uses something that does not exist:

- `t0.txt` must be a component of the page.
- `settings.t0.txt` must be a page and one of its components.
- `vis t0,1`, `tsw`, `ref`, and `click` must give a component of the page.
  - `program.nx` belongs to no page, so there they take a component's number, as in `vis 1,0`, or a variable that contains it, as in `vis sys0,0`. A page's or a component's name there is refused, with its page's name or not, as in `vis t0,0` or `vis page0.t0,0` ("Invalid Component ID").
- A name alone in a value or a condition, as `abc` in `n0.val=abc+1`, must be an `int` of `program.nx`, a system variable, or a colour in capitals, as `RED`. A component's or a page's name alone is refused.
- Another page's components need their page's name, whatever their scope.

Not checked: a component chosen as the code runs, as in `b[3].txt`, and a number in a component's place, as in `tsw 255,0`.

### `'&name&'`, an attribute of the event's own object

In an event's code, `'&name&'` stands for an attribute of the object whose event it is, as the vendor's instruction set documents (section 9). The Nextion Editor replaces it before it compiles, in a quoted text too:

- `'&id&'` becomes the object's ID.
- Any other name becomes the object's name, a dot, and the name. In an event of `n0`, `'&val&'+=10` adds 10 to `n0.val`, and `t0.txt="'&val&'"` shows `n0.val`.

The build writes the line as written, and checks it as the Nextion Editor reads it. So `'&val&'="a"` is refused as `n0.val="a"` is, and the message gives both lines.

- In `program.nx` and in macros, which belong to no event, the Nextion Editor refuses the form ("Invalid Variables"), and so does the build.
- In a quoted text in `program.nx` or in a macro, it stays as written, even when an event calls the macro: `print "a'&name&'b"` sends `a'&name&'b`.
- nxlang takes the form in an event's code, and writes the line with it replaced. It refuses it in a function and in a constant ([language.md](language.md#limits)).

### Hexadecimal numbers

In strict Nextion syntax, the build refuses the hexadecimal numbers the Nextion Editor refuses, written `0x` or `0X`. nxlang writes them in a form the Nextion Editor reads instead ([language.md](language.md)).

- Digits not in pairs, a byte each: `0x123` (write `0x0123`).
- Any hexadecimal number in an `int`'s starting value: `int dow=0x06`.
- A number past 32 bits: `0x0100000000`. Leading zeros are fine: `0x0000000001` is 1.
- A number with a sign, such as `-0x10` after `=`, `==`, or `*`. Subtracting one, as in `5-0x10`, is fine.

### Values and conditions

In strict Nextion syntax, the build refuses a line the Nextion Editor cannot read:

- A value that is not operands joined by operators, such as `n0.val=2+`, `n0.val=+2`, or `n0.val=(1+2)` ("Invalid Variables"). After an operator, a minus can start a number, as in `n0.val=2*-16`, but not a name: `n0.val=2*-n1.val` is refused.
- An assignment with no value: `n0.val=` ("Invalid command").
- An `if`, `else if`, `while`, or `for` whose condition does not end with `)`.

### Data record calls

The build refuses a data record call that the Nextion Editor refuses as it compiles:

- another number of arguments than these: `d0.insert(text)`, `d0.delete(number, count)`, `d0.up(text, number)`, `d0.clear()`;
- a text where a number goes, such as `"1"` or `t0.txt`;
- texts joined where a text goes, such as `t0.txt+"^"+t1.txt`.

A number where a text goes compiles, but adds nothing on the screen. In nxlang, an argument the Nextion Editor would refuse as written is computed first instead, and a number where a text goes becomes its digits ([nxlang-compiled.md](nxlang-compiled.md#how-expressions-are-written)).

### File stream calls

The build refuses a file stream call with another number of arguments than its method takes ("Invalid number of arguments"): `fs0.open(path)`, `fs0.read(text, start, count)`, `fs0.write(text, start, count)`, `fs0.close()`, and `fs0.find(path)`.

- A text is fine as `open`'s path, as in `fs0.open(t0.txt)`.
- Arithmetic is fine in `read`'s numbers, as in `fs0.read(t0.txt,n0.val+1,2)`.
- nxlang passes these calls through as written, so the build refuses them there too.

### First arguments

The first argument of `get`, `print`, `prints`, and `covx` is one text or one number. The build refuses arithmetic or joined texts there, such as `get n0.val+1` or `print "a"+t0.txt` ("Invalid Variables").

- Arithmetic is fine in `prints`' length, in `covx`'s length and form, and in `newfile`'s size.
- In nxlang, such a first argument is computed first instead ([nxlang-compiled.md](nxlang-compiled.md#how-expressions-are-written)).

### Texts and numbers

- A text given to a number, or a number to a text: `n0.val=t0.txt`, `t0.txt=5` ("Assignment operation failed").
  - A `txt` is a text. A `val`, a `pco`, a `font`, a system variable, and `program.nx`'s `int` variables are numbers.
  - Other attributes, and those reached through `b[]` and `p[]`, are left to the Nextion Editor.
- In an assignment, a text joined to a number, or an operator other than `+` and `-` on a text: `t0.txt=t0.txt+5`, `n0.val+=t0.txt`, `t0.txt*=2` ("Invalid variable operation").
  - A text minus a number removes characters, and compiles.
  - A condition is not an assignment: `if(t0.txt=="a")` compiles.

nxlang refuses a text put into a number itself, and converts a number put into a text.

### Escapes

- An escape in a quoted text other than `\r`, `\"`, and `\\`, such as `\n` or `\t` ("Improper use of escape characters").
  - Escapes are read in pairs from the left, so `"a\\nb"` contains none.
  - A comment is not compiled, so its escapes do not count.
- A text that ends in an escaped backslash, inside a condition: `if(t0.txt=="a\\")` ("SYNTAX ERROR").
  - A condition is the head of an `if`, an `else if`, or a `while`, and the middle part of a `for`'s head. Such a text compiles elsewhere, as in `t0.txt="\\"`, or in a `for`'s first or last part.

This applies in nxlang too.

### Attributes a component lacks

The build refuses an attribute that a component, or the page, lacks, whether assigned or read ("Invalid Variables").

Some attributes exist only for some values of a component's choices, as its page file gives them, or as the defaults give them. The rules are the same on every series (`PRESENT_WHILE` in `nxwright/project/editor_limits.py`). The message gives the reason, as in `t0 has its sta at 1, so it has no pic`. Among the rules:

- `first` and `time` exist only while `effect` is not 0.
- Where `sta` sets where the background comes from: `picc` only while it is 0, a crop of a picture; `bco` and `style` at 1, a colour; and `pic` at 2, a picture.
- `borderc` and `borderw` exist only while `style` is 1, a border.
- A waveform's channel colours exist by its number of channels, `ch`.
- A variable's `val` exists while it stores a number (`sta` 0), and its `txt` and `txt_maxl` while it stores a text.
- A video's or a sound's `path` and `path_m` exist while it plays a file of an SD card (`from` 1). Its `vid`, and an animation's, exist while its `from` is 0.

Some attributes exist only on some series. The Basic, Enhanced, and Discovery series lack these, even read, as in `t0 is on an NX4832T035, so it has no movex` (`SERIES_LACKED_ATTRIBUTES` in `nxwright/project/editor_limits.py`):

- `movex`, `movey`, `lockobj`, `groupid0`, `groupid1`, and `sendkey`, of any component;
- `objname`, of any object;
- a waveform's `objWid`, `objHig`, `inittrue`, `molloc`, and `molloc_s`.

The Edge and Intelligent series have them.

A name a component's type does not have at all is refused too, such as `n0.vall`, or a number's `txt`.

- A type has the attributes its defaults list (`nxwright/project/component_defaults.toml`), its methods among them. It also has `id`, `type`, and `objname`, and `endx` and `endy` where it has a place on the screen.
- Letter case matters.
- A method, which code calls, as in `d0.insert("a^b")`, may be read, but not assigned: `d0.insert=1` and `fb0.up=1` are refused.

In nxlang, the build refuses the attributes components lack too.

### Commands

- A line whose first word is not a command the Nextion Editor knows ("Invalid command"). That includes `dir`, and a name alone, such as `sys0`.
  - The commands are the vendor's instruction set's, and those it does not document that the Nextion Editor knows, such as `beep`, `lcd_dev`, and `setbrush`, written in small letters (`EDITOR_COMMANDS` in `nxwright/project/editor_language.py`).
  - A first word with a capital letter, such as `CLS`, and `movelayer`, get "Invalid Variables" instead.
- A command given another number of arguments than it takes, such as `cls 1,2` or `get 1,2`, or written alone, as `cls` ("Invalid number of arguments"). `add` alone gets "Invalid command".
  - The numbers are the vendor's instruction set's, or those an undocumented command was seen to compile with.
  - A command whose number of arguments is not fixed, such as `sets`, takes any number. So do `i`, `cfguart`, `cuts`, `gets`, `meup`, `xnum`, `beepset`, and `piccolor`, whose forms are not known. None of them may be written alone.

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

- A `goto` whose label its event lacks.
- A label written twice in one event, whatever block it is in.

Labels are told apart by letter case: `goto Up` does not find `up:`.

### `sys0` to `sys2`

- Code using `sys0`, `sys1`, or `sys2` where `program.nx` does not declare it, in either language ("Invalid Variables"). The vendor's instruction set lists them among the system variables, but they are `program.nx`'s `int` variables. The Nextion Editor's new project declares them, as `nxwright new` does: `int sys0=0,sys1=0,sys2=0`.
- In strict Nextion syntax, a tab after `int` in a declaration. The Nextion Editor reads it as part of the variable's name. nxlang writes a space there instead ([nxlang-compiled.md](nxlang-compiled.md#how-expressions-are-written)).

### Attributes code cannot change

In either language, the build refuses a line assigning to an attribute that code cannot change ("Assignment operation failed").

- These are the attributes the Nextion Editor's Attribute panel shows in black, and some it never shows that the Nextion Editor was found to refuse. nxwright's descriptions of the attributes mark each (`nxwright/project/attribute_descriptions.toml`). Examples are a text's width, in `t0.w = 10` or `settings.t0.w = 10`, an animation's `from`, and a waveform's `objWid`.
- A component's `id`, `type`, and `objname` are refused too, on every type, and its `endx` and `endy`, on a type with a place on the screen.
- Every form of assignment counts: `=`, `+=` and the others, `++`, and `--`.
- Code in a file that several pages include is checked for each of them. So a line may be refused for one page alone, where its component is of another type. The message gives the page.
- A component the build cannot tell, such as `b[1]`, is left to the Nextion Editor.
- The Basic (T), Enhanced (K), and Discovery (F) series also refuse code setting some attributes. Reading them is fine. The list is `ATTRIBUTES_CODE_CANNOT_CHANGE_ON_SERIES` in `nxwright/project/editor_limits.py`:
  - `x`, `y`, `aph`, `drag`, `effect`, `first`, and `time`, on every type that has them, the page's too;
  - `borderc`, `borderw`, `spax`, and `spay`, on a button, a dual-state button, and a text;
  - `vvs0` and `vvs1`, on a crop.

### Characters the encoding cannot store

The build stops at a character that the folder's encoding cannot store, and gives its file ([Text and its encoding](source-folder.md#text-and-its-encoding)).

## Macros

The Nextion Editor's compile refuses these, and so does the build ([Macros](source-folder.md#macros)):

- a `call` of a macro the folder lacks, in an event, a macro, or `program.nx`;
- a macro's name used twice, and a name with characters other than letters, digits, underscores, and spaces, or starting with a digit;
- in a macro, a component without its page's name, as in `t1.txt`, or of local scope, as in `page0.t0.txt` with `t0` local. A macro reaches only components of global scope, with their page's name: `page0.t1.txt`, with `t1` global.
- in a macro, a component given to `vis`, `tsw`, `ref`, or `click` by its name, with its page's name or not. A macro gives the component's number instead, as in `vis 1,0`, or a variable or a value that contains it, as in `vis sys0,0`.
- in a macro, what the build refuses in an event's code, such as a `goto` without its label, an attribute code cannot change, or `sys0` undeclared.
