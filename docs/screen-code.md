# How nxwright runs Nextion code

Tests and the simulator run your screen's code on your computer. Code in nxlang is first built into strict Nextion syntax, as it is for the Nextion Editor. Then nxwright runs it the way a real Nextion screen would, quirks included. Unless this page says otherwise, a test or the simulator should behave as the screen does.

Nextion publishes no full specification of the language. So nxwright follows the screen as the Nextion Editor's simulator runs it. [Not compared yet](#not-compared-yet) lists what nxwright has not yet compared with it.

Because nxwright copies the Nextion Editor's simulator, it likely copies some of that simulator's bugs too. On a real screen, some behaviours may be slightly different. If your app behaves differently on a real screen than in nxwright, please report it ([CONTRIBUTING.md](../CONTRIBUTING.md)). Each report helps nxwright match the screen better than the Nextion Editor's simulator does.

This page is a reference for both [Testing your app](testing.md) and [Simulating your app](simulator.md).

## Numbers and arithmetic

- Numbers are 32-bit integers.
- Arithmetic runs strictly from left to right, with no operator precedence: `n0.val=2+3*4` gives 20.
- `/` and `%` round toward zero.
- Dividing by zero stops the run with an error. The Nextion Editor's simulator gives 0 instead, and goes on.
- A number may be written in hexadecimal, its digits in pairs: `0x1234`. The number stands for its 32 bits, so `0xFFFFFFFF` is -1.
- A hexadecimal number longer than 32 bits is an error. So is one with a sign, such as `-0x10`. Subtracting one is fine: `5-0x10`.

## Text

- `+` joins two texts.
- `t0.txt-=3`, or `t0.txt=t0.txt-3`, removes the last three characters, as the vendor's instruction set says (operators 2.4 and 2.5).
- Subtracting from another text, such as `t0.txt=t1.txt-3`, is an error. The vendor's instruction set only allows subtracting from the same text: `t0.txt=t0.txt-3`.
- A text field keeps at most its `txt_maxl` bytes. Another text attribute keeps at most the bytes of its bound: a `path` at most its `path_m`. A longer text is cut. The limits come from the page files.
- In a quoted text, `\r` stands for a carriage return and a line feed. `\"` stands for a quote, and `\\` for a backslash. Any other escape is an error, such as `\n`, `\t`, or `\q`.
- The colour names `BLACK`, `BLUE`, `BROWN`, `GREEN`, `YELLOW`, `RED`, `GRAY`, and `WHITE` stand for their RGB565 numbers.

### The text commands

The text commands are `covx` (and its older form `cov`), `substr`, `spstr`, `strlen`, and `btlen`.

- `btlen` counts bytes, in the project's encoding. The others count characters. In `utf-8`, "aé温" has a `strlen` of 3 and a `btlen` of 6.
- In gb2312, big5, shift-jis, and ks_c_5601-1987, `strlen`, `substr`, and `-=` count characters the way a real Nextion screen counts them, even where its count looks wrong:
  - In gb2312 and ks_c_5601-1987, a character whose first byte is 0xA1 or less counts as 2 characters. These include some symbols, such as "　" and "“".
  - They also include the extra characters that a gb2312 folder can use, such as "丂", and that a ks_c_5601-1987 folder can use, such as "갂".
  - Such a character's second byte can take the next character's first byte with it. That splits the characters after it: in gb2312, "“好" counts as 3.
  - In shift-jis, a character whose first byte is 0x81, such as "、", counts as 2 too.
  - In shift-jis, a half-width katakana, such as "ｱ", takes the byte after it with it. That byte can be half of the next character: "ｱ亜" counts as 2 characters, split in the middle of "亜".
- `spstr` looks for its separator byte by byte. So in those encodings, it can split a character whose second byte is the separator, such as shift-jis's "ァ" at "@".
- `covx` writes a number in decimal with commas between thousands: `1,234,567`.
- In hexadecimal, `covx` writes capitals and whole bytes: `05`, or `FFFFFFFF`.
- A length keeps that many characters from the left, or pads with zeros.
- A length can be at most 15 characters in decimal, with or without commas. In hexadecimal, it can be at most 8, which is all 32 bits. A longer length gives that many characters.
- A minus sign does not count toward the length.
- A hexadecimal length that is not a whole number of bytes leaves the text as it was, and answers 0x1B.

## Events, loops, and jumps

- `if`, `while`, and `for` are supported.
- `return` ends its event.
- A label is a name and a colon, such as `end:`. The label stands alone on its line. A comment may follow it.
- A label may contain almost any character, such as `$` or `é`. A label cannot start with a digit, or contain `+ - * / % = , . [ ] & '`, `\`, or `"`. nxwright also refuses one that starts with `{` or `}`, which it reads as a block's brace, though the Nextion Editor takes it.
- `goto` jumps to its label anywhere in the same event, into a block or out of one.
- An event run inside another, as by a `click`, ends on its own. So does a macro that a `call` runs.
- Events, clicked events, and macros nest at most 9 deep, counted together. A 10th stops the run with "Endless loop was detected". An instruction typed on the serial line does not count as a level. What it clicks or calls is the first.
- A loop that turns 10,000 times in one run of its event stops the run with "the loop does not end". So does a `goto` that jumps back as often.
- Typed on the serial line, `return` and `goto` are invalid instructions (0x00). A label line is an invalid variable (0x1A).

## Components and pages

- `click b0,1` runs the Touch Press event of `b0`, and `click b0,0` its Touch Release event.
- `click`, `vis`, `tsw`, and `ref` may give a component by its ID, as a macro must. The ID may be written, or stored in a variable or a value: `click 2,1`, `vis sys0,0`. ID 0 is the page itself.
  - An ID that no object of the page has is recorded under `"component errors"`, and the event goes on.
  - The simulator sends the error code 0x02, an invalid component ID ([Return codes](simulator.md#return-codes)).
- `call my macro` runs one of the folder's macros ([source-folder.md, Macros](source-folder.md#macros)). A `call` of a macro the folder lacks does nothing. The build refuses one in a page's code.
- `page` opens a page by its name, its number, or a value that contains its number: `page returnPage.val`, or `page appid&0x000000FF`, computed from left to right. In a test, it is recorded under `"page opened"`. The simulator opens the page ([Changing page](simulator.md#changing-page)).
- `vis` and `tsw` are recorded in a test, under `"vis <name>"` and `"touch <name>"`. The simulator shows and hides the component, and turns its touches on and off.
- The build refuses an assignment to an attribute that code cannot change, such as `t0.w=10` or `t0.id=3` ([build-rules.md](build-rules.md#attributes-code-cannot-change)). Tests and the simulator build the source folder first, so they never run one. `EditorMachine`, run without a source folder, takes it: it does not know the type of any name.

### An attribute of the object itself: `'&name&'`

In an event of `n0`, `'&val&'` runs as `n0.val`, and `'&id&'` as `n0`'s ID. This works in a quoted text too ([build-rules.md](build-rules.md#name-an-attribute-of-the-events-own-object)).

- In the page's own event, `'&id&'` is 0, the page's ID.
- Spaces inside are dropped: `'& val &'` is `'&val&'`.
- `EditorMachine`, run without a source folder, does not replace it.
- Typed on the serial line, nothing replaces it. Outside a quoted text, it is an invalid variable (0x1A).

### The arrays `p[]` and `b[]`

`p[1].b[5].txt`, `p[dp].n0.val`, and `b[5].txt` reach a component by its page's number, and its ID or name.

- In a simulation, they reach the page of that number, and its component of that ID or name.
- Another page's components go by their page's name. So only those of global scope can be reached.
- In a test, they are plain names. The test gives their values.
- Each component's `type` is its type's number: 116 for a text.
- Reaching an attribute that its component lacks answers 0x1A, an invalid variable ([build-rules.md](build-rules.md#attributes-a-component-lacks)). An example is `b[2].bco` of a text with no colour background. A read leaves what it reads into as it was. A store changes nothing. The event goes on.
- The same goes for reaching another page's component that is not of global scope, or that page itself, as `p[0].b[0].type`.
- Such a read inside a condition, as `if(b[2].bco==1)`, answers 0x1A too. That comparison then counts as true, whatever it compares.
- A condition reads its comparisons from left to right, and stops once the result is known. So in `if(n0.val==1&&b[2].bco==0)`, `b[2].bco` is not read when `n0.val` is not 1.
- Reading the serial buffer `u[index]`, or `usize`, while `recmod` is 0 answers 0x1A too, and gives 0 ([Protocol reparse mode](#protocol-reparse-mode-u-usize-ucopy-and-udelete)).

### Attributes the screen does not support

Code may name some attributes that the screen's series does not support. The list is `UNHELD_ATTRIBUTES` in `nxwright/project/editor_limits.py`:

- On the Edge and Intelligent series: such as a component's `movex`, an object's `objname`, a gauge's `wid`, or any bound ending in `_m`.
- On the Basic, Enhanced, and Discovery series: such as a component's `aph`, or its opening effect's `effect`, `first`, and `time`.

A simulation knows the screen's series:

- Event code reads such an attribute as 0. That is a number, so storing it in a `txt` is ignored (0x1C).
- Storing one has no effect, and answers 0x1C, a failed assignment.
- A typed line naming one answers 0x1A. So does `b[]` reaching one.
- The panel draws the component with the page file's value.

A test has no series. Event code in a test reads the value the test gives.

## Lines the running screen ignores

The screen ignores some lines as they run. An ignored line has no effect, but it is reported. The event goes on with the next line. These lines are ignored:

- A picture, font, animation, video, or sound attribute given an ID the project lacks, 65535 included.
- `pic`, `picq`, or `xpic` with a picture the project lacks. `xstr` with a font the project lacks, though `xstr` paints its background first.
- `add` or `cle` with no waveform of the page, or a channel past its count.
- `wepo` or `repo` whose bytes run past the end of the EEPROM. `rept` starting past it.
- A `txt` given a number, or a `val` given a text. These answer 0x1C.
- A number outside what its attribute takes. These answer 0x1C too ([Numbers an attribute takes](#numbers-an-attribute-takes)).
- `crcrest 1` with a start above 65535. It answers 0x1A.

In a test, each ignored line is recorded under `"refusals"`. The simulator logs it, and sends its error code ([Return codes](simulator.md#return-codes)).

The simulator checks each of these. A test checks them too, for the page's components and for a waveform's ID. A test knows each component's type and values from the page file, under the values the test gives ([The values a run starts from](testing.md#the-values-a-run-starts-from)).

### Numbers an attribute takes

Most number attributes take only a range of numbers. A number outside the range is ignored ([Lines the running screen ignores](#lines-the-running-screen-ignores)):

- `x` and `y` take -6000 to 6000. A `move` still places a component outside them. On the Basic, Enhanced, and Discovery series, code cannot set them at all.
- A colour takes 0 to 65535.
- `aph` takes 0 to 127, `effect` 0 to 8, and `drag` 0 or 1. A hotspot takes only its defaults: `aph` 127, `effect` 0, and `drag` 0.
- Others take ranges of their own, such as 0 to 2 for a text's `xcen`. In VS Code, a hover on an attribute says what it takes.

A few attributes take any number, but keep only its last 1 or 2 bytes. For example, a slider's `val` reads 65535 after code stores -1. Attributes of 4 bytes, such as a number's `val`, take any number.

nxwright does not check the attributes of the page itself. They have not been compared with the Nextion Editor's simulator.

## Code that nxwright refuses

These stop the run:

- parentheses in arithmetic;
- arithmetic in a condition;
- a condition that mixes `&&` and `||`;
- joining a number to a text;
- a `goto` whose label its event lacks;
- the same label twice in one event;
- a label of a character the Nextion Editor refuses, such as `1abc:` or `a-b:`;
- a form `'&...&'` that is not an attribute's name, such as `'&1a&'`;
- a `crcputh` whose text is not hexadecimal, such as `crcputh 3G`.

## The commands

How each command of the instruction set runs. A test records what reaches outside the screen, under names listed in [What a test can check](testing.md#what-a-test-can-check).

### The serial line

- `prints`, `printh`, and `print` are recorded in `"sent"`. The simulator sends them on its serial line.
- `get`, `sendme`, and `rept` are recorded in `"replies"`.
- `com_stop` and `com_star` are recorded in `"other commands"`. In the simulator, they hold and release the instructions arriving on the serial line ([Holding instructions](simulator.md#holding-instructions)).

### The CRC: `crcrest`, `crcputs`, `crcputh`, and `crcputu`

These compute a checksum, a Modbus CRC16, to check data an app sends or receives. `crcval` reads it:

```
crcrest 1,0xFFFF
crcputs t0.txt,0
prints crcval,2
```

- `crcrest 1,start` starts the CRC, usually from 0xFFFF. The start is used with its 16 bits reversed, which leaves 0xFFFF as it is: `crcrest 1,0x1234` starts the CRC at 0x2C48. A type other than 1 turns the CRC off, and `crcval` then reads -1.
- `crcputs` adds the bytes that `prints` sends for a value: a text's bytes, or a number's 4 bytes, low byte first. A length other than 0 adds only that many.
- `crcputh` adds bytes written in hexadecimal, such as `crcputh 0d 0a`.
- In protocol reparse mode, `crcputu start,count` adds `count` bytes of the buffer, from byte `start`, if the buffer has them all.
- Code cannot change `crcval`.

### The EEPROM: `wepo` and `repo`

They act on the EEPROM's 1024 bytes, and are recorded in `"eeprom accesses"`.

- A number takes 4 bytes, low byte first.
- A text field takes its `txt_maxl` bytes, plus one.
- Another text attribute takes the bytes of its bound, plus one: an animation's `path` takes its `path_m` and one more.
- A text constant takes its bytes, plus one.
- A text is ended by a zero byte, as the vendor's instruction set says.
- `repo` into a text field reads its `txt_maxl` bytes, without the extra one.

### GPIO

`cfgpio` and the variables `pio0` to `pio7`, `pwm4` to `pwm7`, and `pwmf` are recorded in `"gpio"`. In a test, a read gives the value as set: give an input's level as `pio0` to `pio7` in the test's values.

In a simulation, the pins work as the vendor's instruction set describes:

- Every pin starts as a pull-up input, which reads 1 until something drives it. Code writing to an input does not change it.
- `cfgpio` with mode 2, 3, or 4 makes a pin an output, which reads what code last wrote. PWM, mode 3, works on pins 4 to 7 only.
- Mode 1 binds an input pin to a component. When the pin falls to 0, the component's Press event runs. When it rises again, its Release event runs.
- A page change ends every binding, so bind the pins again in the `load` event of each page that uses them.
- You set an input's level in the Simulator section ([GPIO pins](simulator.md#gpio-pins)).

### Protocol reparse mode: `u[]`, `usize`, `ucopy`, and `udelete`

In the simulator, these read the bytes that arrive on the serial line while `recmod` is not 0 ([Protocol reparse mode](simulator.md#protocol-reparse-mode)). A test has no serial line: give it the buffer's bytes as `"serial buffer"`, with `recmod` 1.

```
on read.down:
  n0.val=usize
  ucopy n1.val,0,2,0
  udelete 2
```

```python
values = SCREEN.run("page0", [("read", "down")],
                    {"recmod": 1, "serial buffer": b" 1AB", "n1.val": 0})
```

`n0.val` is then 4, `n1.val` 0x3120, and `values["serial buffer"]` is what is left, `b"AB"`.

### System variables kept as set

`volume`, `audio0`, `audio1`, `eql`, `eqm`, `eqh`, `eq0` to `eq9`, `scache`, `bcpu`, `tpdir`, `runmod`, `portbusy`, `tprc`, `aph`, and `lowpower` keep the value code sets. They have no other effect.

- A simulation starts `volume` at 100, the equalizer's at 7, `aph` at 127, and the rest at 0.

### `appid`

`appid` keeps the number code stores in it through `rest` and a start again, as a screen keeps it when it restarts. So `program.nx` can read it at the next start, for example to open the page it gives: `page appid&0x000000FF`. A new simulation starts it at 0.

### `addr`

`addr` takes 0, or 256 to 2815. Code giving it another number is ignored, and answers 0x1C. In the simulator, an address turns address mode on ([Address mode](simulator.md#address-mode)).

### `dims` and `bauds`

- `dims` sets `dim` too, and `bauds` sets `baud` too. So the simulator's panel dims at once.
- A simulation starts them at the vendor's defaults: `dims` 100 and `bauds` 9600.
- The screen keeps them as its defaults at power-on. A simulation does not: each start has the vendor's defaults.

### `randset` and `rand`

- `randset` is recorded in `"rand range"`.
- In a test, reading `rand` gives the value of `"rand"` that the test sets.
- In a simulation, `rand` gives a random number in its range. The generator starts from the same seed at each start.

### `rest`

Recorded in `"reset"`. A simulation starts again, and its EEPROM keeps what the app wrote.

### Drawing commands

`cls`, `fill`, `line`, `draw`, `cir`, `cirs`, `xstr`, `pic`, `picq`, `xpic`, `ref`, `ref_stop`, and `ref_star` are recorded in `"painted"`. The simulator draws them ([Drawing commands](simulator.md#drawing-commands)).

### Waveforms: `add` and `cle`

Recorded in `"waveform"`. The simulator draws the points ([Waveforms](simulator.md#waveforms)).

### `doevents`

`doevents` runs nothing, since nothing is waiting to run. It does bring the scroll values code set in a file browser, a data record, or a sliding text within their limits, as the end of the event would ([File browsers](simulator.md#file-browsers)).

### `move`

```
move t0,0,40,600,40,5,2000
move t1,0,160,600,160,5,500
move t2,0,280,600,280,0,1000
```

In the simulator, `t0` and `t1` move together, as they have the same priority, 5. `t2` starts once both have ended, 2 seconds later.

- `move` moves its component over its time. Its `x` and `y` change as it goes (`nxwright/testing/moves.py`).
- Moves of the same priority run together. A higher priority runs first. The next priority starts once every move of the one before has ended.
- A move given while others run starts at once if it has their priority. Otherwise it waits its turn.
- A second move of the same priority, for a component that already has one, does nothing. The simulator's log shows the move it ignored.
- A move of time 0 puts its component at its end at once. The code after it reads the new place, in a test too.
- A test has no clock, so it records `move` in `"other commands"`. Nothing moves over time. The test still reads `move`'s arguments as the simulator does: an ID no component has is recorded in `"component errors"`.

### Chinese input: `pa_q` and `pa_txt`

These need the screen's pinyin table. Give it to a test with `pinyin_table` ([SourceFolderRunner](testing.md#sourcefolderrunner)), and to the simulator with `pinyinTable` ([Chinese input](simulator.md#chinese-input)).

- `pa_q "mei",n0.val` sets `n0.val` to the number of Chinese characters the syllable `mei` has. For a syllable the table lacks, `pa_q` sets 0.
- `pa_txt "mei",t0.txt,0,6` sets `t0.txt` to the first six of them, as gb2312 text, cut to its `txt_maxl`.
- The text is empty when the start and count run past the last character.
- A start below 0 reads the characters before the syllable's.
- A count below 0 copies on to the text's limit, or to the table's end.
- The text is also empty when the start and count add up to less than 0, or when the read would start before the table's first byte.
- Without a table, they are recorded in `"other commands"`, and change nothing.

### Commands recorded but not run

These act on hardware or data that nxwright does not model. They are recorded in `"other commands"`, and nothing more:

- `touch_j`, `code_c`, `play`, `beep`, and `setlayer`;
- the undocumented commands, except `pa_q` and `pa_txt` ([Undocumented commands](#undocumented-commands)).

A test records `addt`, `wept`, and `twfile` in `"other commands"` too, as it has no serial line for their data. The simulator runs them ([Transparent data](simulator.md#transparent-data)).

### Undocumented commands

The Nextion Editor knows about 30 commands that the vendor's instruction set does not document, such as `beep`, `lcd_dev`, `setbrush`, and `qrcode`. You can use them in your code: the Nextion Editor compiles them, so the build accepts them. Some series refuse some of them ([build-rules.md](build-rules.md#what-a-series-lacks)). `EDITOR_COMMANDS` in `nxwright/project/editor_language.py` lists every command the Nextion Editor knows, documented or not.

In tests and the simulator:

- `pa_q` and `pa_txt` run ([Chinese input](#chinese-input-pa_q-and-pa_txt)).
- The others are recorded in `"other commands"`, and do not run. The simulator's log shows each one as "not simulated".

## The SD card

The file commands act on the SD card's files: `findfile`, `finddir`, `newfile`, `delfile`, `newdir`, `deldir`, `refile`, `redir`, `rdfile`, `twfile`, file streams, a file browser's `up()`, and a data record's methods.

- In a test, the card's files are in the values `"file contents"` and `"existing"` ([What a test can check](testing.md#what-a-test-can-check)).
- In the simulator, a card may be a folder of your computer ([The SD cards](simulator.md#the-sd-cards)).
- A file contains bytes, as on a real card.
- What the commands change is recorded in `"file commands"`.
- What the screen ignores is recorded in `"file errors"`.

### `newfile`

- `newfile` makes a file of the size it is given, all zero bytes.
- A size that is not a number does not make a file, and answers 0x1B, on any card.
- A size below 0 does not make a file, and answers 0x06, an invalid file operation.

### `rdfile`

`rdfile "sd0/log.txt",0,10,1` sends the file's first 10 bytes on the serial line, then their CRC. A test records them in `"sent"`, as `("rdfile", bytes)`.

- A count of 0 sends the file's size, in 4 bytes, low byte first.
- The last argument chooses the CRC: 0 for none, 1 for Modbus CRC16, and 10 for CRC32. It is sent low byte first.
- A missing file, or bytes past its end, sends nothing, and answers 0x06.

### `twfile`

`twfile "sd0/log.txt",100` takes the next 100 bytes of the serial line as the file's bytes, then writes the file. A test records it in `"other commands"`, and writes no file ([Commands recorded but not run](#commands-recorded-but-not-run)).

- A path on neither `sd0/` nor `sd1/`, as in `ram/`, or a size of 0 or below, answers 0x06, an invalid file operation.
- A size that is not a number answers 0x1A.
- None of these starts a transfer, and each is recorded in `"file errors"`.

### File streams

Each file stream has its own open file.

- `open` finds a file as `findfile` does. `open` then sets the stream's `val`, its position, to 0, its `qty` to the file's size, and its `en` to 1.
- `close` sets all three to 0.
- An `open` of a file that is not found closes the file that is open.
- `read` and `write` count `start` and `count` in bytes of the project's encoding. `start` is a place within the text.
- `read` and `write` work at `val`, and move it on by `count`. So code can read or write a file in steps.
- A read ends at the first zero byte.
- Code may set `val`, even past the end of the file. A `val` below 0 is ignored (0x1C).
- A `read` or `write` that would go past the end of the file, from `val`, does nothing. Neither does one with no file open.
- A read past the end still cuts its text after its first `start` + `count` bytes, whatever `start` is. The Nextion Editor's simulator does this too: it cuts "IJ" to "I".
- `find` runs, but has no effect, whatever the file. What a screen does with it is not known.

### Data records

A data record's methods change its data file, `path`: `insert("a^b^c")`, `delete(n, count)`, `up("a^b^c", n)`, and `clear()`.

- Records are numbered from the oldest, which is 0.
- A text may be a variable's.
- If the file doesn't exist and `mode` is 1, the method creates it first.
- The first data record to open a file keeps it, until code changes that record's `path`.
  - Another data record that gives the same file opens nothing. Its methods have no effect, and are not reported. Once the file is free, its next method opens it.
  - Code setting a data record's `path` to a file another one keeps answers 0x06. This is recorded in `"file errors"` as `("open", path)`.

A call that the Nextion Editor refuses to compile stops the run:

- one with too few or too many arguments;
- a text where a number goes;
- texts joined together.

These are ignored, and recorded:

- a number where a text goes;
- a record longer than `lenth` bytes;
- a record number past the last record;
- a `delete(n, count)` whose `count` is 0 or below, or more than the records from `n` on ([Different from the Nextion Editor's simulator](simulator.md#different-from-the-nextion-editors-simulator) says what it does with a count below 0);
- a missing file, with `mode` 0;
- a file that the card's folder will not give or take. A file that could not be read is never made again over the old one.

After a call:

- `qty` counts the records;
- `txt` is the record chosen by `val`;
- `maxval_y` and `maxval_x` say how far the table scrolls.

Code setting `val` chooses a record, and fills `txt`. A `val` past the last record is ignored, and the record chosen before stays chosen.

## Not compared yet

These have not been compared with the Nextion Editor's simulator. nxwright assumes them:

- `bauds` sets `baud` too. The Nextion Editor's simulator keeps `baud` at 9600, whatever code sets, so this cannot be checked there.
