# How nxwright runs Nextion code

Tests and the simulator run your screen's code on your computer, quirks included, after building any code in nxlang into strict Nextion syntax. Unless this page says otherwise, a test or the simulator should behave the way a real Nextion screen does. This page is a reference for both [Testing your app](testing.md) and [Simulating your app](simulator.md).

Nextion publishes no full specification of the language, so nxwright follows the Nextion Editor's simulator, and likely copies some of its bugs too. A real screen may therefore differ slightly. If your app behaves differently on a real screen than in nxwright, please report it ([CONTRIBUTING.md](../CONTRIBUTING.md)). Each report helps nxwright match the screen better than the Nextion Editor's simulator does. See [Not compared yet](#not-compared-yet) for what nxwright has not yet compared with that simulator.

On this page, "answers 0x1A" means that the screen sends the error code 0x1A ([Return codes](simulator.md#return-codes)). A code in parentheses, such as (0x1C), means the same.

## Numbers and arithmetic

- Numbers are 32-bit integers.
- Arithmetic runs strictly from left to right, with no operator precedence: `n0.val=2+3*4` gives 20.
- `/` and `%` round toward zero.
- Dividing by zero stops the run with an error. The Nextion Editor's simulator gives 0 instead, and goes on.
- You can write a number in hexadecimal, with its digits in pairs: `0x1234`. The digits give all 32 bits of the number, so `0xFFFFFFFF` is -1.
- A hexadecimal number longer than 32 bits, or with a sign, such as `-0x10`, is an error, but subtracting one is fine: `5-0x10`.
- The colour names `BLACK`, `BLUE`, `BROWN`, `GREEN`, `YELLOW`, `RED`, `GRAY`, and `WHITE` stand for their RGB565 numbers.

## Text

- `+` joins two texts.
- `t0.txt-=3`, or `t0.txt=t0.txt-3`, removes the last three characters (see operators 2.4 and 2.5 in the vendor's instruction set).
- Subtracting from a different text, such as `t0.txt=t1.txt-3`, is an error, because the vendor's instruction set only allows subtracting from the same text.
- A text longer than its limit is cut. The limit is in bytes, and the page files give it: `txt_maxl` for a text field, and for any other text attribute, an attribute called its bound, such as `path_m` for a `path`.
- In a quoted text, `\r` stands for a carriage return and a line feed. `\"` stands for a quote, and `\\` for a backslash. Any other escape is an error, such as `\n`, `\t`, or `\q`.

### The text commands

The text commands are `covx` (and its older form `cov`), `substr`, `spstr`, `strlen`, and `btlen`.

- `btlen` counts bytes, in the project's encoding. The others count characters. In `utf-8`, "aé温" has a `strlen` of 3 and a `btlen` of 6.
- In gb2312, big5, shift-jis, and ks_c_5601-1987, `strlen`, `substr`, and `-=` count characters the way a real Nextion screen counts them, even where its count looks wrong:
  - In gb2312 and ks_c_5601-1987, a character whose first byte is 0xA1 or less counts as 2 characters. This affects some symbols, such as "　" and "“", and the extra characters that a source folder in those encodings can use, such as gb2312's "丂" and ks_c_5601-1987's "갂".
  - The second byte of a character counted this way can pair up with the first byte of the next character, which splits the characters after it: in gb2312, "“好" counts as 3.
  - In shift-jis, a character whose first byte is 0x81, such as "、", also counts as 2.
  - A half-width katakana in shift-jis, such as "ｱ", counts as one character together with the byte after it. That byte can be half of the next character: "ｱ亜" counts as 2 characters, split in the middle of "亜".
- `spstr` looks for its separator byte by byte. In gb2312, big5, shift-jis, and ks_c_5601-1987, it can therefore split a character whose second byte is the separator, such as shift-jis's "ァ" when the separator is "@".
- `covx` can write a number in decimal, with or without commas between thousands (`1,234,567`), or in hexadecimal, in capitals and whole bytes (`05`, `FFFFFFFF`).
  - The length you give `covx` keeps that many characters from the left, or pads with zeros. A minus sign does not count toward the length.
  - The length can be at most 15 in decimal, and at most 8 in hexadecimal, which is all 32 bits. A longer length gives that maximum number of characters.
  - In hexadecimal, an odd length leaves the text as it was, and answers 0x1B.

## Events, loops, and jumps

- `if`, `while`, and `for` are supported.
- `return` ends its event. If a `click` ran that event inside another, or a `call` ran a macro, only the inner one ends, and the outer one goes on.
- A label is a name and a colon, such as `end:`, alone on its line. A comment may follow it.
- A label can contain almost any character, such as `$` or `é`, but it cannot start with a digit, or contain `+ - * / % = , . [ ] & '`, `\`, or `"`.
- nxwright also refuses a label that starts with `{` or `}`, because it reads that as a block's brace. The Nextion Editor accepts such a label.
- `goto` jumps to its label anywhere in the same event, into a block or out of one.
- Events, clicked events, and macros can nest at most 9 deep, counted together. A 10th stops the run with "Endless loop was detected". An instruction typed on the serial line does not count as a level, so the first level is whatever it clicks or calls.
- A loop or a backward `goto` that repeats 10,000 times in one run of its event stops the run with "the loop does not end".
- On the serial line, `return` and `goto` are invalid instructions (0x00), and a label line is an invalid variable (0x1A).

## Components and pages

- `click b0,1` runs the Touch Press event of `b0`, and `click b0,0` its Touch Release event.
- In `click`, `vis`, `tsw`, and `ref`, you can give a component by its ID, and in a macro you must. The ID can be written as a number, or stored in a variable or a value: `click 2,1`, `vis sys0,0`. ID 0 is the page itself.
  - If no object of the page has that ID, the event goes on. A test records the ID under `"component errors"`, and the simulator sends the error code 0x02, an invalid component ID ([Return codes](simulator.md#return-codes)).
- `call my macro` runs one of the source folder's macros ([source-folder.md, Macros](source-folder.md#macros)). In the folder's code, the build refuses a `call` to a macro the folder does not have. On the serial line, such a `call` does nothing.
- `page` opens a page by its name, its number, or a value that contains its number: `page returnPage.val`, or `page appid&0x000000FF`. A test records it under `"page opened"`. For the simulator, see [Changing page](simulator.md#changing-page).
- `vis` and `tsw` are recorded in a test, under `"vis <name>"` and `"touch <name>"`. The simulator shows and hides the component, and turns its touches on and off.
- The build refuses an assignment to an attribute that code cannot change, such as `t0.w=10` or `t0.id=3` ([build-rules.md](build-rules.md#attributes-code-cannot-change)). Tests and the simulator build the source folder first, so they never run one. [`EditorMachine`](testing.md#running-code-directly) runs code without a source folder, so it does not know the type of any name, and accepts that assignment.

### An attribute of the object itself: `'&name&'`

In an event of `n0`, `'&val&'` runs as `n0.val`, and `'&id&'` as `n0`'s ID. This works in a quoted text too ([build-rules.md](build-rules.md#name-an-attribute-of-the-events-own-object)).

- In the page's own event, `'&id&'` is 0, the page's ID.
- Spaces inside are dropped: `'& val &'` is `'&val&'`.
- [`EditorMachine`](testing.md#running-code-directly), which runs code without a source folder, does not replace `'&name&'`.
- On the serial line, nothing replaces `'&name&'`, and outside a quoted text it is an invalid variable (0x1A).

### The arrays `p[]` and `b[]`

`p[1].b[5].txt`, `p[dp].n0.val`, and `b[5].txt` reach a component by its page's number, and its ID or name.

- In a simulation, you can only reach another page's component if it has global scope.
- In a test, these forms are plain names, and the test gives their values.
- A component's `type` attribute gives the number of its type: 116 for a text.

Reaching either of these answers 0x1A, an invalid variable:

- an attribute that a component does not have, such as `b[2].bco` of a text with no colour background ([build-rules.md](build-rules.md#attributes-a-component-lacks))
- another page's component that does not have global scope, or that page itself, as in `p[0].b[0].type`

The event then goes on. A read leaves its target as it was, and a store has no effect.

Inside a condition, as in `if(b[2].bco==1)`, reading a missing attribute also answers 0x1A, and the comparison counts as true, whatever it compares. A condition reads its comparisons from left to right, and stops once the result is known, so in `if(n0.val==1&&b[2].bco==0)`, `b[2].bco` is not read when `n0.val` is not 1.

### Attributes the screen does not support

Code can use some attributes that the screen's series does not support, for example:

- On the Edge and Intelligent series: a component's `movex`, an object's `objname`, a gauge's `wid`, or any bound ending in `_m`.
- On the Basic, Enhanced, and Discovery series: a component's `aph`, or its opening effect's `effect`, `first`, and `time`.

`UNHELD_ATTRIBUTES` in `nxwright/project/editor_limits.py` has the full list.

A simulation knows the screen's series. When an attribute is not supported on that series:

- Event code reads the attribute as 0. That is a number, so storing it in a `txt` is ignored (0x1C).
- Storing a value in the attribute has no effect, and answers 0x1C, a failed assignment.
- A typed line that uses the attribute, or `b[]` reaching it, answers 0x1A.
- The panel draws the component with the page file's value.

A test has no series, so event code in a test reads the value the test gives.

## Lines the running screen ignores

The screen ignores some lines as they run. An ignored line has no effect but is reported, and the event goes on with the next line. These lines are ignored:

- A picture, font, animation, video, or sound attribute given an ID the project lacks, 65535 included.
- `pic`, `picq`, or `xpic` with a picture the project lacks. `xstr` with a font the project lacks, though `xstr` paints its background first.
- `add` or `cle` given a waveform the page does not have, or a channel past the waveform's count.
- `wepo` or `repo` whose bytes run past the end of the EEPROM, or `rept` starting past that end.
- A `txt` given a number, or a `val` given a text. These answer 0x1C.
- A number outside what its attribute takes. These answer 0x1C too ([Numbers an attribute takes](#numbers-an-attribute-takes)).
- `crcrest 1` with a start above 65535. It answers 0x1A.

The simulator checks every line in this list. It logs each ignored line, and sends its error code ([Return codes](simulator.md#return-codes)).

A test checks only the lines that concern the page's components or a waveform's ID, and records each ignored one under `"refusals"`. It checks these lines against each component's type and values in the page file, unless the test gives its own values ([The values a run starts from](testing.md#the-values-a-run-starts-from)).

### Numbers an attribute takes

Most number attributes take only a range of numbers, and the screen ignores a number outside that range. The ranges are:

- `x` and `y` take -6000 to 6000. A `move` still places a component outside them. On the Basic, Enhanced, and Discovery series, code cannot set them at all.
- A colour takes 0 to 65535.
- `aph` takes 0 to 127, `effect` 0 to 8, and `drag` 0 or 1. A hotspot takes only its defaults: `aph` 127, `effect` 0, and `drag` 0.
- Others have ranges of their own, such as 0 to 2 for a text's `xcen`. In VS Code, hover over an attribute to see its range.

A few attributes take any number, but keep only its last 1 or 2 bytes. For example, a slider's `val` reads 65535 after code stores -1. Attributes of 4 bytes, such as a number's `val`, keep the whole number.

When code stores a number in an attribute of the page itself, nxwright does not check its range ([Not compared yet](#not-compared-yet)).

## Code that stops the run

nxlang lets you write parentheses in arithmetic, arithmetic in a condition, `&&` mixed with `||`, and a number joined to a text. The build rewrites them into strict Nextion syntax ([How expressions are written](nxlang-compiled.md#how-expressions-are-written)), so they never stop a run.

In strict Nextion syntax, the Nextion Editor refuses them, and they stop the run if they get that far. So does the rest of this list. The build refuses most of it first, so you usually see a build error before any code runs.

- parentheses in arithmetic
- arithmetic in a condition
- a condition that mixes `&&` and `||`
- joining a number to a text
- a `goto` to a label that its event does not have
- the same label twice in one event
- a label with a character the Nextion Editor refuses, such as `1abc:` or `a-b:`
- a form `'&...&'` that is not an attribute's name, such as `'&1a&'`
- a `crcputh` whose text is not hexadecimal, such as `crcputh 3G`

## The commands

A test records what reaches outside the screen. See [What a test can check](testing.md#what-a-test-can-check) for the names it uses.

### The serial line

- `prints`, `printh`, and `print` are recorded in `"sent"`. The simulator sends them on its serial line.
- `get`, `sendme`, and `rept` are recorded in `"replies"`.
- `com_stop` and `com_star` are recorded in `"other commands"`. In the simulator, they hold and release the instructions arriving on the serial line ([Holding instructions](simulator.md#holding-instructions)).

### The CRC: `crcrest`, `crcputs`, `crcputh`, and `crcputu`

`crcrest`, `crcputs`, `crcputh`, and `crcputu` compute a Modbus CRC16, a checksum for checking data an app sends or receives. `crcval` reads the result:

```
crcrest 1,0xFFFF
crcputs t0.txt,0
prints crcval,2
```

- `crcrest 1,start` starts the CRC, usually from 0xFFFF. The start is used with its 16 bits reversed, which leaves 0xFFFF as it is: `crcrest 1,0x1234` starts the CRC at 0x2C48. Any first argument other than 1 turns the CRC off, and `crcval` then reads -1.
- `crcputs` adds the bytes that `prints` sends for a value: a text's bytes, or a number's 4 bytes, low byte first. A length other than 0 adds only that many.
- `crcputh` adds bytes written in hexadecimal, such as `crcputh 0d 0a`.
- In protocol reparse mode, `crcputu start,count` adds `count` bytes of the buffer, from byte `start`, if the buffer has them all.
- Code cannot change `crcval`.

### The EEPROM: `wepo` and `repo`

`wepo` and `repo` act on the EEPROM's 1024 bytes, and are recorded in `"eeprom accesses"`.

- A number takes 4 bytes, low byte first.
- A zero byte ends a text, so a text takes one byte more than its own size:
  - A text field takes `txt_maxl` bytes, plus one.
  - Another text attribute takes its bound, plus one: an animation's `path` takes `path_m` bytes, plus one.
  - A text constant takes its bytes, plus one.
- `repo` into a text field reads `txt_maxl` bytes, without the extra one.

### GPIO

`cfgpio` and the variables `pio0` to `pio7`, `pwm4` to `pwm7`, and `pwmf` are recorded in `"gpio"`. In a test, reading a pin gives the value last set. To set an input's level, give `pio0` to `pio7` in the test's values.

In a simulation, the pins work as the vendor's instruction set describes:

- Every pin starts as a pull-up input, which reads 1 until something drives it. Code writing to an input does not change it.
- `cfgpio` with mode 2, 3, or 4 makes a pin an output, which reads what code last wrote. PWM, mode 3, works on pins 4 to 7 only.
- Mode 1 binds an input pin to a component. When the pin falls to 0, the component's Press event runs. When it rises again, its Release event runs.
- A page change ends every binding, so bind the pins again in the `load` event of each page that uses them.
- You set an input's level in the Simulator section ([GPIO pins](simulator.md#gpio-pins)).

### Protocol reparse mode: `u[]`, `usize`, `ucopy`, and `udelete`

In the simulator, `u[]`, `usize`, `ucopy`, and `udelete` read the bytes that arrive on the serial line while `recmod` is not 0 ([Protocol reparse mode](simulator.md#protocol-reparse-mode)). While `recmod` is 0, reading `u[index]` or `usize` answers 0x1A, and gives 0. A test has no serial line: give it the buffer's bytes as `"serial buffer"`, with `recmod` 1.

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

`volume`, `audio0`, `audio1`, `eql`, `eqm`, `eqh`, `eq0` to `eq9`, `scache`, `bcpu`, `tpdir`, `runmod`, `portbusy`, `tprc`, `aph`, and `lowpower` keep the value that code sets, and have no other effect.

A simulation starts `volume` at 100, the equalizer variables at 7, `aph` at 127, and the rest at 0.

### `appid`

`appid` keeps its value through a `rest` or a restart, so `program.nx` can read it at the next start, for example to open the page it gives: `page appid&0x000000FF`. A new simulation starts `appid` at 0.

### `addr`

`addr` takes 0, or 256 to 2815. Code giving it another number is ignored, and answers 0x1C. In the simulator, an address turns address mode on ([Address mode](simulator.md#address-mode)).

### `dims` and `bauds`

- `dims` sets `dim` too, and `bauds` sets `baud` too, so the simulator's panel dims at once.
- Each start of a simulation sets `dims` to 100 and `bauds` to 9600, the vendor's defaults. A real screen keeps the values as its defaults at power-on.

### `randset` and `rand`

- `randset` is recorded in `"rand range"`.
- In a test, reading `rand` gives the value of `"rand"` that the test sets.
- In a simulation, `rand` gives a random number in its range. The generator starts from the same seed at each start.

### `rest`

A test records `rest` in `"reset"`. A simulation starts again, and its EEPROM keeps what the app wrote.

### Drawing commands

`cls`, `fill`, `line`, `draw`, `cir`, `cirs`, `xstr`, `pic`, `picq`, `xpic`, `ref`, `ref_stop`, and `ref_star` are recorded in `"painted"`. The simulator draws them ([Drawing commands](simulator.md#drawing-commands)).

### Waveforms: `add` and `cle`

A test records `add` and `cle` in `"waveform"`. The simulator draws the points ([Waveforms](simulator.md#waveforms)).

### `doevents`

`doevents` runs nothing, because nothing is waiting to run. If code has set the scroll values of a file browser, a data record, or a sliding text, `doevents` brings them within their limits, which otherwise happens at the end of the event ([File browsers](simulator.md#file-browsers)).

### `move`

```
move t0,0,40,600,40,5,2000
move t1,0,160,600,160,5,500
move t2,0,280,600,280,0,1000
```

In the simulator, `t0` and `t1` move together, because they have the same priority, 5. `t2` starts once both have ended, 2 seconds later.

- `move` moves a component over the time it is given, and changes its `x` and `y` as it goes.
- Moves of the same priority run together. A higher priority runs first. The next priority starts once every move of the one before has ended.
- A move given while others run starts at once if it has their priority. Otherwise it waits its turn.
- A second move of the same priority, for a component that already has one, does nothing. The simulator's log shows the move it ignored.
- A move of time 0 puts its component at the end of the move at once, and the code after it reads the new position, in a test too.
- A test has no clock, so it records `move` in `"other commands"`, and nothing moves over time. The test still checks `move`'s arguments: an ID no component has is recorded in `"component errors"`.

### Chinese input: `pa_q` and `pa_txt`

`pa_q` and `pa_txt` need the screen's pinyin table. Give it to a test with `pinyin_table` ([SourceFolderRunner](testing.md#sourcefolderrunner)), and to the simulator with `pinyinTable` ([Chinese input](simulator.md#chinese-input)).

- `pa_q "mei",n0.val` sets `n0.val` to the number of Chinese characters the syllable `mei` has. For a syllable the table does not have, `pa_q` sets 0.
- `pa_txt "mei",t0.txt,0,6` sets `t0.txt` to the first six of the syllable's characters, as gb2312 text, cut to its `txt_maxl`. The last two arguments are the start and the count.
  - A start below 0 reads the characters before the syllable's.
  - A count below 0 copies on to the text's limit, or to the table's end.
  - The text is empty when the start and count run past the last character, or add up to less than 0, or when the read would start before the table's first byte.
- Without a table, `pa_q` and `pa_txt` are recorded in `"other commands"`, and change nothing.

### Commands recorded but not run

Some commands act on hardware or data that nxwright does not model, and are only recorded in `"other commands"`:

- `touch_j`, `code_c`, `play`, `beep`, and `setlayer`
- the undocumented commands, except `pa_q` and `pa_txt` ([Undocumented commands](#undocumented-commands))

A test records `addt`, `wept`, and `twfile` in `"other commands"` too, because it has no serial line for their data. The simulator runs them ([Transparent data](simulator.md#transparent-data)).

### Undocumented commands

The Nextion Editor knows about 30 commands that the vendor's instruction set does not document, such as `beep`, `lcd_dev`, `setbrush`, and `qrcode`. You can use them in your code: the Nextion Editor compiles them, so the build accepts them. Some series refuse some of them ([build-rules.md](build-rules.md#what-a-series-lacks)). `EDITOR_COMMANDS` in `nxwright/project/editor_language.py` lists every command the Nextion Editor knows, documented or not.

In tests and the simulator, only `pa_q` and `pa_txt` run ([Chinese input](#chinese-input-pa_q-and-pa_txt)). The simulator's log shows each of the others as "not simulated".

## The SD card

The file commands act on the SD card's files: `findfile`, `finddir`, `newfile`, `delfile`, `newdir`, `deldir`, `refile`, `redir`, `rdfile`, `twfile`, file streams, a file browser's `up()`, and a data record's methods.

- In a test, the card's files are in the values `"file contents"` and `"existing"` ([What a test can check](testing.md#what-a-test-can-check)).
- In the simulator, a card may be a folder of your computer ([The SD cards](simulator.md#the-sd-cards)).
- A file whose path starts with `ram/` is kept in the screen's memory ([Files in `ram/`](simulator.md#files-in-ram)).
- If a path such as `x.bin` is neither on a card (`sd0/` or `sd1/`) nor in `ram/`, then `newfile`, `delfile`, `refile`, `newdir`, and `deldir` do not change anything, and answer 0x06.
- What the commands change is recorded in `"file commands"`.
- What the screen ignores is recorded in `"file errors"`.

### `newfile`

- `newfile` makes a file of the size it is given, all zero bytes.
- If the size is not a number, `newfile` does not create a file, and answers 0x1B, whatever its path.
- If the size is below 0, `newfile` does not create a file, and answers 0x06, an invalid file operation.
- If a file in `ram/`, the screen's memory, does not fit in the space your project sets aside, `newfile` does not create it, and answers 0x06 ([Files in `ram/`](simulator.md#files-in-ram)).

### `rdfile`

`rdfile "sd0/log.txt",0,10,1` sends the file's first 10 bytes on the serial line, then their CRC. A test records them in `"sent"`, as `("rdfile", bytes)`.

- A count of 0 sends the file's size, in 4 bytes, low byte first.
- The last argument chooses the CRC: 0 for none, 1 for Modbus CRC16, and 10 for CRC32. It is sent low byte first.
- If the file is missing, or the bytes run past its end, `rdfile` sends nothing, and answers 0x06.

### `twfile`

`twfile "sd0/log.txt",100` takes the next 100 bytes of the serial line as the file's bytes, then writes the file. A test records it in `"other commands"`, and writes no file ([Commands recorded but not run](#commands-recorded-but-not-run)).

These cases do not start a transfer, and each is recorded in `"file errors"`:

- If the path is neither on a card nor in `ram/`, or the size is 0 or below, `twfile` answers 0x06, an invalid file operation.
- If the file is in `ram/` and does not fit in the space your project sets aside, `twfile` answers 0x06 too ([Files in `ram/`](simulator.md#files-in-ram)).
- If the size is not a number, `twfile` answers 0x1A.

### File streams

Each file stream has its own open file.

- `open` finds a file the way `findfile` does, then sets the stream's `val`, its position, to 0, its `qty` to the file's size, and its `en` to 1. If `open` does not find the file, it closes the file that is open.
- `close` sets `val`, `qty`, and `en` to 0.
- `read` and `write` work at `val`, and move it on by `count`, so code can read or write a file in steps. They count `start` and `count` in bytes of the project's encoding, and `start` is a place within the text.
- A read ends at the first zero byte.
- Code may set `val`, even past the end of the file. A `val` below 0 is ignored (0x1C).
- A `read` or `write` does nothing if no file is open, or if it would go past the end of the file from `val`. The one exception is a `read` past the end, which still cuts its text after the first `start` + `count` bytes, whatever `start` is. For example, it can cut "IJ" to "I".
- `find` runs, but has no effect, whatever the file. What a screen does with it is not known.

### Data records

A data record's methods change its data file, `path`: `insert("a^b^c")`, `delete(n, count)`, `up("a^b^c", n)`, and `clear()`.

- Records are numbered from the oldest, which is 0.
- A method's text can come from a variable, such as `insert(t0.txt)`.
- If the file doesn't exist and `mode` is 1, the method creates it first.
- The first data record to open a file keeps it, until code changes that record's `path`.
  - Another data record with the same file does not open it, and that record's methods have no effect and are not reported. Once the file is free, the record's next method opens it.
  - Code setting a data record's `path` to a file another one keeps answers 0x06. This is recorded in `"file errors"` as `("open", path)`.

A call that the Nextion Editor refuses to compile stops the run:

- one with too few or too many arguments;
- a text where a number goes;
- texts joined together.

These are ignored, and recorded:

- a number where a text goes;
- a record longer than `lenth` bytes;
- a record number past the last record;
- a `delete(n, count)` whose `count` is 0 or below, or more than the records from `n` on (for a count below 0, see [Different from the Nextion Editor's simulator](simulator.md#different-from-the-nextion-editors-simulator));
- a missing file, with `mode` 0;
- a file in the card's folder that cannot be read or written. If nxwright could not read a file, it never creates a new file over it.

After a call:

- `qty` counts the records;
- `txt` is the record chosen by `val`;
- `maxval_y` and `maxval_x` give how far the table scrolls.

Code setting `val` chooses a record, and fills `txt`. A `val` past the last record is ignored, and the record chosen before stays chosen.

## Not compared yet

nxwright assumes these behaviours, which have not been compared with the Nextion Editor's simulator:

- `bauds` sets `baud` too. The Nextion Editor's simulator keeps `baud` at 9600, whatever code sets, so this cannot be checked there.
- When code stores a number in an attribute of the page itself, nxwright does not check its range.
