# Commands

Most of nxwright's commands work on a source folder: your project as files ([source-folder.md](source-folder.md)).

```
nxwright new <source-folder>
nxwright extract <project.HMI> <source-folder> [--continue-with-unknown]
nxwright extract --list-unknown <project.HMI>
nxwright report <project.HMI> <report.md>
nxwright build <source-folder> <output.HMI>
nxwright compile <source-folder or project.HMI> <output.tft> [--firmware <file.tft> | --editor <folder>] [--download]
nxwright upload <file.tft> --port <port>
nxwright ports
nxwright rescue <output.tft> --screen <model>
nxwright decompile <file.tft> <source-folder>
nxwright tft-read <file.tft>
nxwright tft-listing <file.tft>
nxwright tft-compare <a.tft> <b.tft>
nxwright check <source-folder>
nxwright format <source-folder> [--check]
nxwright new-page <source-folder> [name]
nxwright picture <source-folder> <pictures...>
nxwright font <source-folder> <typeface-file> <height>
nxwright font <source-folder> <font-file.zi>
nxwright keyboard <source-folder> <keyboard|keypad|speed-dial|chinese-input>
nxwright animation <source-folder> <pictures...>
nxwright video <source-folder> <video-file or pictures...>
nxwright sound <source-folder> <sound-file>
nxwright sd-picture <pictures...> --output <folder>
nxwright remove <source-folder> <picture|font|animation|video|sound> <name>
nxwright device <source-folder> [--screen MODEL] [--rotation DEGREES] [--encoding NAME]
nxwright upgrade <source-folder>
nxwright language <source-folder> nxlang
nxwright password-hash <password>
nxwright defaults <sample.HMI> <output.toml>
nxwright lsp
```

`nxwright <command> --help` describes each command and its options. `nxwright --version` gives the version of nxwright installed, or says that it runs from a copy of its source that is not installed.

## new

```
nxwright new app --screen NX8048P050 --name "Living room"
```

Starts a source folder for a new project. It has one blank page the size of the screen, and one font, so that you can add a first text and build.

- `--screen`, `--rotation`, `--encoding`: the device settings. The rotation is 0 by default, and the encoding `iso-8859-1`.
- `--language`: the code's language, `nxlang` by default, or `nextion` for strict Nextion syntax ([language.md](language.md)).
- Without these options, the command prompts for the device settings and the language.
- `--name`: the app's name, as nxwright shows it. By default, the folder's name. The name is kept in `app.toml`, so renaming the folder later keeps it.

Details:

- `program.nx` declares `int sys0=0,sys1=0,sys2=0`. The Nextion Editor refuses code that uses them otherwise, and its new projects declare them too.
- The font is Noto Sans at 24 pixels, called `NotoSans24`. The Nextion Editor's new project has no font, but the Nextion Editor refuses a text whose font the project lacks.
- In utf-8, the font has the characters U+0000 to U+00FF, the same characters `font` draws by default.
- Noto Sans lacks some characters of some encodings, such as koi8-r's box-drawing characters or windows-874's Thai. The font leaves them out, and the command warns you.
- In a two-byte encoding, such as gb2312 or big5, Noto Sans has none of the Chinese, Japanese, or Korean characters. They show empty until you add a font drawn from a typeface that has them ([font](#font)).

## extract

```
nxwright extract thermostat.HMI app
```

Brings a project file into a source folder. Use it to start from a project made in the Nextion Editor. If your source folder is in strict Nextion syntax, and the project is later changed in the Nextion Editor, extracting again brings the changes back. The project file is only read.

- Into a new or empty folder, it makes a fresh source folder. The app is named after the project file: `thermostat.HMI` gives `thermostat`.
- Into an existing source folder in strict Nextion syntax, it updates it, and keeps the app's name. Your code, names, and comfortable syntax stay wherever the project did not change them ([Extracting into an existing folder](source-folder.md#extracting-into-an-existing-folder)).
- Into a source folder in nxlang, it refuses and changes nothing, because the code the build writes cannot be faithfully turned back into nxlang and the conversion would be lossy. To see what the project contains, extract it into a new folder, and compare that folder with your source folder ([Working with the Nextion Editor](language.md#working-with-the-nextion-editor)).
- The Nextion Editor locks a project it has open. If the project is open there, the command fails with "Permission denied", and advises you to close the project in the Nextion Editor first.
- Blank lines in the project's code are dropped, the same way the build drops them. A warning gives each event, macro, or `program.s` that had any. The Nextion Editor compiles them to nothing.
- A project saved by a newer Nextion Editor may contain things nxwright does not know. Before writing anything, extract puts each one in one of four groups:
  - **Kept exactly**, such as a component type nxwright does not know, or an attribute it does not know. A page file keeps such an attribute as its stored bytes ([source-folder.md](source-folder.md#page-files)). A warning gives each thing kept.
  - **Written otherwise** by the next build, in a form nxwright knows. For example, the build writes a page header of a form nxwright has not seen in the current form, the same way the Nextion Editor does, and puts an object's records back in their usual order. A warning gives each one, and extract goes on without prompting, even with no terminal.
  - **May be lost** by the next build, such as a block of another kind, or a screen model nxwright does not know. Extract lists each one, and warns that the project may then miss parameters the Nextion Editor needs. Then it prompts you to choose whether to go on. If there is no terminal to answer at, as in a script, extract stops with exit code 3. `--continue-with-unknown` goes on without prompting.
  - **Cannot be kept**, such as a component without its type, ID, or name. Extract refuses the project.

  The warnings and the refusal end with a pointer to `nxwright report`, which writes a report to send to nxwright's maintainers ([report](#report)).
- `nxwright extract --list-unknown thermostat.HMI` prints each thing in the project that nxwright does not know, one JSON object per line, and writes nothing. Each object gives what the thing is, where it is, its sort, its size, and its first 16 bytes in hexadecimal.

`extract` goes through a dump in a temporary folder. `nxwright dump`, then `nxwright import`, do the same in two steps ([dumps.md](dumps.md)).

## report

```
nxwright report thermostat.HMI report.md
```

Writes a report on the things in a project file that nxwright does not know, for nxwright's maintainers to look into. Paste the report into an issue, with the issue template "A project nxwright does not understand".

- The report gives the versions of nxwright, Python, and Windows, the project file's blocks by name and size, its manifest header, and the device settings nxwright reads from it.
- Each thing nxwright does not know comes with what it is, where it is, and at most its first 16 bytes. Its place is given by a block's name, an object's number, or an attribute's name.
- The project's code, texts, names of pages or components, pictures, fonts, animations, videos, and sounds are left out. The password's hash is blanked, and the report gives only whether there is a password.
- Those first 16 bytes may contain some of your own text. Read the report before you send it.
- Two blanks are left for you to fill in: the Nextion Editor's version, and what you did in it before you saved the project.
- The project file is only read. The report is written only to a new file.

## build

```
nxwright build app thermostat.HMI
```

Writes a new project file from the source folder alone: its pages, code, pictures, fonts, animations, videos, sounds, and device settings.

- The build first checks the folder, and stops at the first problem it finds ([What the build refuses](build-rules.md)).
- An existing project file at the output is replaced, but only once the new one is written in full and checked. The build asks first, unless you pass `--overwrite`, and refuses when there is no terminal to ask at, as in a script. If the output exists and is not a project file, the command stops with an error, even with `--overwrite`.
- If the old project file changed since nxwright wrote it, for example in the Nextion Editor, it is kept as a backup beside the new one, such as `thermostat.HMI.2026-11-06-143205.bak`. `--no-backup` turns this off. nxwright never deletes a backup, so you can delete those you no longer need. If your project is in git, you may want to ignore `*.bak`.
- A project file counts as changed if nxwright has no record of writing it, such as after you move it or use another computer. The record is in the same folder as [the picture cache](source-folder.md#the-picture-cache). With `NXWRIGHT_CACHE=off`, there is no record, so each build that changes the file keeps a backup.
- A project built from a folder in nxlang has its pages locked, with no password, to show that it is not meant to be edited in the Nextion Editor. You can still unlock a page there. The build locks a page even if its page file says `locked = false`, and leaves a page with its own password as it is. `--no-lock` leaves each page as its page file sets it.
- If the Nextion Editor has the project open, the build fails with "Permission denied", and advises you to close the project there first.
- Once it has built the project, it prints each page's memory, in the same form as the Nextion Editor's compile: `page0: 292 of 524288 bytes`. When nxwright could not count all of a page's memory, the page's line says `at least` ([Memory](build-rules.md#memory)).
- It keeps the screen copies of your pictures in a cache, to build faster next time ([The picture cache](source-folder.md#the-picture-cache)).
- Like `extract`, it goes through a dump in a temporary folder ([dumps.md](dumps.md)).

To put your app on a screen, compile it with [compile](#compile) and send it with [upload](#upload). You can also open the built project in the Nextion Editor, and compile and upload it from there.

## compile

```
nxwright compile app thermostat.tft
nxwright compile thermostat.HMI thermostat.tft
```

Compiles a source folder, or a project file, into a TFT file, the file a Nextion screen runs.

- The compile first builds a source folder, and stops at anything `build` refuses. A project file is compiled as it is.
- If the project has something nxwright cannot compile, such as a number too large for its attribute, the compile lists every problem, and does not write any file.
- A sound at 22050 samples a second must be 16-bit, mono or stereo, or the compile refuses it. A sound at any other rate needs ffmpeg to convert it: either the ffmpeg on your PATH, or the program you give with `--ffmpeg`. Without ffmpeg, the compile refuses the project.
- `--project-file <file.HMI>` also saves the project file that the compile builds from a source folder, so that you have one that always matches the TFT file. For a folder in nxlang, the pages of that project file are locked as in [build](#build), unless you give `--no-lock`. The locks do not change the TFT file.
- If an output file already exists, the compile refuses to replace it, unless you give `--overwrite`. Even then, it only replaces a TFT file with a TFT file, and a project file with a project file.
- An output file that changed since nxwright wrote it is kept as a backup ([build](#build)), unless you give `--no-backup`.

### The firmware

Every TFT file contains the screen's firmware. Nextion makes the firmware, so nxwright does not ship it ([INDEPENDENCE.md](../INDEPENDENCE.md)). The compile takes the firmware from the first of these sources that has it:

- a TFT file you give with `--firmware`, made for the same series of screens, or a Nextion Editor folder you give with `--editor`;
- the firmware an earlier compile found, kept in your cache folder;
- the Nextion Editor installed on your computer;
- a download from Nextion's site, of about 50 MB:
  - At a terminal, the compile prompts you first, with the download's size. To find the size, it sends one small request to Nextion's site.
  - In a script, the compile downloads only if you give `--download`. Without `--download`, it does not send any request at all.
  - The download needs curl, which comes with Windows 10 version 1803 and later, macOS, and most Linux systems.
  - If the download is not available, and you are on Windows with no Nextion Editor installed, the compile offers to run the Nextion Editor's installer.

The compile takes only the firmware of the Nextion Editor 1.68.2, the version nxwright is tested with. Firmware of another version may run the compiled code differently.

## upload

```
nxwright upload thermostat.tft --port COM5
```

Sends a TFT file, made by nxwright or the Nextion Editor, to the screen on a serial port, such as `COM5` or `/dev/ttyUSB0`.

- To find the screen, the command tries each rate a screen can use, which can take a few seconds. If you know the rate the screen uses now, you can give it with `--baud`.
- `--yes` skips the prompt before the file is sent. A script must give it, because with no terminal to answer the prompt, the command exits with 3 and does not send the file.
- The command cancels the upload, and exits with 1, if the file is for a different model from the screen, if nxwright cannot tell the model of the file or of the screen, if the file's checksums do not match, or if it cannot read the file, such as one made by a Nextion Editor older than 1.60.1.
- `--find` stops once the screen is found and the file is checked against it, without sending the file.
- `--upload-baud` sets the rate of the upload. The default is 115200, which sends a megabyte in a little over a minute and a half. You can give any rate the screen supports, up to 921600, but some serial adapters lose bytes at the highest rates.
- The screen skips the parts of the file it already has, such as the firmware when only your app changed. `--full` sends the whole file.

Once the whole file is sent, the screen restarts and runs it. Do not power the screen off until your app is showing, because it may still be updating its firmware. If the screen stops answering, or you stop the upload, power the screen off and on, then upload the file again.

## ports

```
nxwright ports
```

Lists your computer's serial ports, so that you can choose the one to give `upload`. It does not open any port, so it cannot tell which one a screen is on.

## rescue

```
nxwright rescue rescue.tft --screen NX4832T035
```

Writes a TFT file that sets a screen's settings back to their defaults. Use it for a screen that stays black or no longer answers because of one of the settings listed below. To put the file on the screen, follow [If the screen stays black or stops responding](screens.md#if-the-screen-stays-black-or-stops-responding).

- `--screen` gives the screen model. The file is only for that model.
- The firmware comes from the same places as for [compile](#the-firmware), with the same options: `--firmware`, `--editor`, and `--download`.
- If the output file already exists, the command refuses to replace it, unless you give `--overwrite`. Even then, it only replaces a TFT file. If that file changed since nxwright wrote it, it is kept as a backup ([build](#build)), unless you give `--no-backup`.

The file's app changes these settings, then shows a blank page:

- `dims=100`: the screen starts at full brightness.
- `bauds=9600`: the serial port starts at 9600 baud.
- `recmod=0`: reparse mode ends, so that the screen accepts instructions again.
- `addr=0`: the screen's address is removed, so that it accepts instructions without one.
- `sleep=0`: the screen wakes.

## decompile

```
nxwright decompile thermostat.tft app
```

Turns a TFT file back into a source folder. Use it to recover a project when you still have its TFT file but have lost the project.

- The folder to write must be new or empty.
- The command reads a file made by versions 1.60.1 to 1.68.2 of the Nextion Editor, and refuses any other.
- For a file made by 1.68.2, the command first checks its work, by compiling the folder again with the file's own firmware and comparing the result with your file. A file made by an older version is decompiled without this check.
  - If the result differs from your file, or the folder cannot be compiled again, the command prompts you before writing anything. In a script, with no terminal to answer the prompt, the command exits with 3 and does not write anything. `--continue-unconfirmed` writes the folder without the prompt.
- A TFT file does not keep the names of pages, components, int variables, and macros, only a checksum of each. The command works out the names it can from those checksums, and replaces any other with a readable one, such as `text3` for the text component of ID 3.

## tft-read, tft-listing, and tft-compare

```
nxwright tft-read thermostat.tft
nxwright tft-listing thermostat.tft
nxwright tft-compare old.tft new.tft
```

These three commands show what is inside a TFT file, whether nxwright or the Nextion Editor made it.

- `tft-read` prints the file's series of screens, the Nextion Editor version it records, its table of sections, and the parts and pages of its app. It then checks the file's checksums, sizes, and places, prints each one that is wrong, and exits with 1 if it found one.
- `tft-listing` prints what the app in the file contains: its settings, its int variables, `program.s`, its macros, each page with its components and their code, and the pictures and fonts.
- `tft-compare` compares two TFT files part by part. For each part that differs, it prints where the difference starts, with the bytes around it. It exits with 1 when the files differ.

## check

```
nxwright check app
```

Runs every check the build makes, and writes nothing. It prints each problem with its place, and exits with 1 when there is an error:

```
pages/home.nx line 12: error: unknown name speed
```

- The build stops at the first error. The check reports the first error of each page.
- If `app.toml`, `defaults.toml`, or the declarations of `program.nx` have an error, the check reports only that error, since every page depends on these files.
- The check also finds:
  - a picture file, or a picture's source file, that nxwright cannot read, reported as `pictures/logo.png: not a picture nxwright reads: no kind of picture Pillow knows`. The check does not decode the pixels, so only the build finds a picture whose pixels are damaged;
  - a page that takes more memory than the Nextion Editor's compile allows ([Memory](build-rules.md#memory));
  - a sound the Nextion Editor refuses to compile ([source-folder.md](source-folder.md#animations-videos-and-sounds)).

The [VS Code extension](../editors/vscode/README.md) runs the same checks as you type. It offers a quick fix for an error that has one sure fix, such as a command written in capitals.

### Warnings

The check also warns of likely mistakes that the build accepts. Each warning gives its rule's name:

- `left-to-right`, in strict Nextion syntax: a line the Nextion Editor computes in another order than the usual one. `sys0=a+b*c` computes `(a+b)*c`, and the warning shows it.
- `unused-constant`, in nxlang: a constant of a page's own `.nx` file, or of `program.nx`, that no code uses. Constants of other included files are left alone, since a library serves many pages.
- `unused-function`, in nxlang: a function of a page's own `.nx` file that the page never calls.
- `number-past-32-bits`, in nxlang: a hexadecimal number too large for 32 bits, such as `0x0100000005`, or a decimal number outside -2147483648 to 2147483647, such as `4294967295`. The build keeps only the low 32 bits, as C does, so these become `0x00000005` and `-1`.
- `event-never-runs`: code for an event that its component's type does not have, such as a page's `postinit`. The Nextion Editor keeps the code, but the screen never runs it. The warning lists the type's events. For `preinit` and `postinit`, it also gives the event that the Nextion Editor's event pane means: a page's Preinitialize Event is `load`, and its Postinitialize Event is `loadend`.
- `page-place`: a page file gives the page an `x`, `y`, `w`, or `h` that does not match the screen. The build ignores these values and makes the page fill the screen, the same way the Nextion Editor does. The warning shows on each line that does not match.
- `text-cut`, in nxlang: a line that puts a text into one of nxlang's hidden variables, when the text may be too long for the variable and get cut. The warning shows only when a part of the text is a component's text, or a hidden variable with room for more than 255 bytes, such as a parameter that a caller gave a long text. It gives how many bytes the text may need. A variable component with a `txt_maxl` of that size keeps the whole text.
- `sound-file-form`: a sound's file without the `hmic` chunk that the Nextion Editor's Audio panel writes, or whose check value there does not match its samples. It shows on the line of `app.toml` that gives the sound. The Nextion Editor takes such a file, but a screen might check the value. `nxwright sound` writes the chunk and its check value.
- `memory-not-checked`: the folder has something whose memory nxwright cannot count, so the pages are checked without it ([Memory](build-rules.md#memory)). The warning shows on the page with it.

## format

```
nxwright format app
nxwright format app --check
```

Lays out every `.nx` file in one style, in either language, the same way as a code editor's Format Document. `macros.nx` is laid out as strict Nextion syntax, whatever the folder's language, its macros as events.

- `--check`: writes nothing, lists the files that would change, and exits with 1 when there is one.

For example, this code:

```
include "lib/units.nx"
const LIMIT=30
on save.up:
      // keep it in range
  if(n0.val>LIMIT){
  n0.val=LIMIT
  }else if (n0.val<0)
  {
      n0.val = - 1
  }
  printh 0d  0a


  t0.txt="Saved"
on n0.down:
  switch(n0.val){
  case 1:
  t0.txt="one"
  break
  }
```

is formatted as:

```
include "lib/units.nx"
const LIMIT = 30

on save.up:
  // keep it in range
  if (n0.val > LIMIT) {
    n0.val = LIMIT
  } else if (n0.val < 0) {
    n0.val = -1
  }
  printh 0d  0a

  t0.txt = "Saved"

on n0.down:
  switch (n0.val) {
    case 1:
      t0.txt = "one"
      break
  }
```

The formatter leaves some things as written: a command's arguments, where spaces can matter (in `printh 0d 0a`, each separates a byte), strings, the text of comments, and `int` declarations.

Formatting never changes what your code does:

- A file is formatted only if every page that uses it builds to the same code as before, apart from spaces and tabs at the start and end of lines. The same goes for `program.nx` when the file is one of its own, and for each macro of `macros.nx`.
- If any file fails this, nothing is written. Nothing is written either when the folder does not build.
- The build copies indentation into the project. So the next build of a formatted folder changes those spaces in the project file, and nothing else.

## new-page

```
nxwright new-page app settings
```

Adds a blank page the size of the screen, at the folder's rotation, with an empty code file. It is listed last in `app.toml`.

- Without a name, the page is called `page0`, `page1`, and so on: the first one the folder does not have.
- These names are refused, and nothing is written: a name the folder has, in any letter case; a name longer than 14 characters; and a name the Nextion Editor refuses, such as `dim`.
- If the folder already has 251 pages, the command refuses, because the Nextion Editor cannot compile more.

## picture

```
nxwright picture app "My Icon.jpg" logo.png
```

Copies picture files into the folder's `pictures/`, and lists them after its other pictures, in the order given. It takes `.png`, `.jpg`, `.jpeg`, `.bmp`, and `.gif` files.

- Each picture is named after its file, keeping only letters, digits, `_`, and `-`: `My Icon.jpg` gives `MyIcon`.
- These are refused, and nothing is written: a file nxwright cannot read as a picture; a name the folder has, in any letter case; a name whose file, or source file, is in `pictures/` already, though `app.toml` does not list it; and two files that give the same name.

## font

A font is either drawn from a typeface file, or added from a ready-made font file. nxwright ships Noto Sans, at `nxwright/project/fonts/NotoSans-Regular.ttf`.

### From a typeface file

```
nxwright font app NotoSans-Regular.ttf 20
```

Draws a font from a TrueType (`.ttf`) or OpenType (`.otf`) file, or from the first typeface of a collection (`.ttc`), as the Nextion Editor's font generator draws one ([format.md, Drawing a font](format.md#drawing-a-font)). The font is stored for the folder's rotation, or upright on the F series, the same way the Nextion Editor stores fonts. It is added after the folder's other fonts.

- The height: from 12 to 254 pixels.
- `--name`: the font's name. By default, the typeface's name and the height, such as `NotoSans20`.
- `--no-smoothing`: makes each pixel empty or full, the same way the generator does without anti-aliasing.
- `--characters`, in a utf-8 folder: the characters to draw, as code points in hexadecimal, and ranges of them, such as `20-7e,400-4ff`. By default `0-ff`, the generator's first two blocks.
- `--full-table`, in a utf-8 folder: a different kind of table (below).

The font is in the folder's encoding:

- In a one-byte encoding, such as iso-8859-1, the font has every character of the encoding.
- In a two-byte encoding, such as gb2312 or big5, the font has every character of the encoding. A character your typeface file lacks is empty, as wide as the font is tall, and the command warns you ([format.md, Two-byte fonts](format.md#two-byte-fonts)).
- In utf-8, the font has the characters you chose and the space, the same as the generator's "Specified character" choice, in a table of those characters only. Noto Sans at 20 pixels, for `0-ff`, is about 10 KB.
  - The screen shows a character such a font lacks as the font's first character. With the default `0-ff`, that is U+0000, empty and a pixel wide. When your characters start above the space, it is the space ([format.md, Fonts](format.md#fonts)).
  - With `--full-table`, the table has an entry for every code point up to U+FFFF instead. It is at least 655 KB, whatever characters it contains, and the command prints its size. The screen then shows a character the font lacks as nothing, half the font's height wide ([format.md, utf-8 fonts](format.md#utf-8-fonts)).

When your typeface file lacks a character the font should have:

- In a one-byte encoding, or in utf-8, the character is left out of the font. The command prints a warning, with what the screen will show instead. A one-byte font then has a gap, which the screen reads past by code ([format.md, Fonts](format.md#fonts)).
- A typeface file that has none of the characters, control characters aside, is refused.

A name the folder has is refused too.

### From a font file

```
nxwright font app NotoSans16.zi
```

Adds a ready-made font file, such as the Nextion Editor's font generator writes, as it is, after the folder's other fonts.

- A font stored for another rotation is turned to the folder's rotation, or to upright on the F series. nxwright can turn a font in any encoding, two-byte ones included ([format.md, Two-byte fonts](format.md#two-byte-fonts)).
- The font file contains a name, which the font generator stored in it, such as `NotoSans16`. The font gets that name in the folder, unless you give another with `--name`. The name inside the file does not change.
- A name the folder has, and a file that is not a font, are refused.

The font's encoding must be one of these:

- the folder's own encoding;
- ascii, in an iso-8859-1 folder. The Nextion Editor adds such fonts itself, for its stock keyboards;
- iso-8859-1, in a folder whose encoding Noto Sans does not cover, such as koi8-r, or in a utf-8 folder. Older nxwright keyboards used such fonts ([keyboard](#keyboard)). The command prints a warning that text beyond ascii will show garbled.

A font in any other encoding is refused.

## keyboard

```
nxwright keyboard app keypad
```

Adds one of nxwright's keyboard pages. In VS Code, "nxwright: Add a keyboard page" does the same. So does the Attributes section, when you set a component's `key` to a keyboard the folder lacks ([the extension's README](../editors/vscode/README.md)).

A component bound to a keyboard by its `key` opens the keyboard's page when it is touched: 1 opens the full keyboard, 2 the numeric keypad, 3 the speed dial, and 4 Chinese input. The Nextion Editor adds its own pages for these, `keybdA` to `keybdAP`, and extracting keeps them as they are. nxwright has pages of its own for all four, with the same names:

- **keyboard** (`keybdA`) fills the screen: the text and cancel (X) above four rows of keys. Its mode key switches the letter keys between small letters, capitals, and numbers and signs.
- **keypad** (`keybdB`) is a panel in the middle of a page without background, so that the caller's page shows around it: digits, a minus sign, a point, delete, and OK.
- **speed-dial** (`keybdC`) is a panel too. A group key, such as "abc", shows its characters on four choice keys, and a tap on one types it. Its mode key switches the groups to capitals, then to digits, which type at once.
- **chinese-input** (`keybdAP`) types Chinese from pinyin. Type a syllable, such as `mei`, and six of its characters appear above the letters. Use `<` and `>` to see more, and tap one to type it. Delete removes the syllable's last letter, or else the last character. The mode key switches between pinyin (中), small letters, capitals, and numbers and signs.

Like the Nextion Editor's own keyboards, each one works with the component that opened it:

- It reads a text by its `txt`, up to its `txt_maxl` bytes, hidden when its `pw` is 1. It reads a number or an xfloat as its digits.
- OK writes the text back. Cancel leaves the caller as it was.
- A keyboard takes 100 bytes of a caller's text at most. A longer text is cut, and written back cut.
- A number takes 11 bytes at most. A number typed past the screen's 32-bit range wraps when it is written back.

The pages it adds are files of the folder like any other, which you can change (for what the screen relies on, see [Keyboards](simulator.md#keyboards)).

### The keyboard's font

The page is laid out for the folder's screen, at its rotation, in the colours of nxwright's demo. Its font is Noto Sans at the largest height whose labels fit the keys, and is named after it, such as `NotoSans24`. The command adds the font with the page. If the folder already has a font of that name, the keyboard uses it as it is.

The font is in the folder's encoding:

- In utf-8, it has U+0000 to U+00FF, the characters of iso-8859-1, the same characters `font` draws by default. A caller's text in those characters, such as "café", shows as it is. A text with any other character shows the font's first character in its place, a gap of a pixel, and the command warns you of this.
- Where Noto Sans lacks some characters of a one-byte encoding, such as koi8-r's box-drawing characters, the font leaves them out, and the command warns you. A caller's text with them shows the font's first character, the space, in their place.
- In a two-byte encoding, such as gb2312 or big5, Noto Sans has none of the Chinese, Japanese, or Korean characters. A caller's text in them shows empty, and the command warns you. The font has room for every character of the encoding, so it is large, and the command prints its size.

To show those characters, add a font with the keyboard's font name, drawn from a typeface that has them, before you add the keyboard. The keyboard then uses that font.

Folders made with older versions of nxwright may have their keyboards' fonts in iso-8859-1: a folder in koi8-r, in a two-byte encoding, or in another encoding that Noto Sans lacks characters of, and a utf-8 folder. nxwright keeps those fonts.

### The Chinese keyboard

The Chinese keyboard only works in a gb2312 folder. Its font needs Chinese characters, which Noto Sans does not have, so you choose one:

```
nxwright keyboard app chinese-input --typeface simsun.ttc
nxwright keyboard app chinese-input --font SimSun16
```

- `--typeface` draws the font from a typeface file with Chinese characters (`.ttf`, `.otf`, or `.ttc`), as large as the keys allow, up to 24 pixels. A font with every Chinese character is large: about 1.2 MB at 24 pixels. The command prints its size.
- `--font` uses a gb2312 font your folder already has.

To show a syllable's characters, tests and the simulator need the screen's pinyin table ([Chinese input](screen-code.md#chinese-input-pa_q-and-pa_txt)).

### What it refuses

- A folder that already has that keyboard: a page of any name marked as that system page, whether the Nextion Editor's or nxwright's.
- A folder with a page of the keyboard's name that is another page.
- A folder that already has 251 pages, the most the Nextion Editor can compile.

### With the Nextion Editor

- In the Nextion Editor, setting a component's `key` uses the keyboard page the project has, nxwright's included, and does not add its own.
- The Nextion Editor's "Reset system page", in the Page panel's menu, does replace nxwright's page. It shows a confirmation first, then puts the Nextion Editor's stock keyboard in its place, under the same name and locked. It also imports the two fonts the stock page uses, `24ascii` and `16ascii`.
- Extracting then brings both into the folder, and `nxwright keyboard` refuses the folder, since it has that keyboard already.

## animation

```
nxwright animation app frame1.png frame2.png frame3.png --duration 100
```

Makes an animation from pictures, one frame each, in order, and adds it after the folder's other animations ([Animations, videos, and sounds](source-folder.md#animations-videos-and-sounds)).

- `--duration`: how long each frame shows, in milliseconds. 50 by default, as in GmovMaker, the Nextion Editor's animation tool.
- `--name`: the animation's name. By default, the first picture's.
- The pictures must all be the same size.
- They may be of any kind that Pillow, the picture library nxwright uses, reads: PNG, JPEG, BMP, and others. A GIF gives its first frame.
- The form the screen shows is made for the folder's rotation.
- Given one `.gmov` file made with GmovMaker in place of the pictures, as in `nxwright animation app blink.gmov`, it keeps that file as it is, and makes the form the screen shows from its frames. They keep their own durations, so `--duration` is refused with it.

## video

```
nxwright video app intro.mp4 --size 320,240 --length 5
nxwright video app frame1.png frame2.png --rate 10
```

Makes a video the same way as VideoBox, the Nextion Editor's video tool, and adds it after the folder's other videos.

- `--rate`: frames a second, from 1 to 255. 12 by default, as in VideoBox.
- `--name`: the video's name. By default, the first source's.
- The video is made for the folder's rotation, the same way VideoBox makes one for that display direction.

From a video file, ffmpeg cuts it into frames. Without ffmpeg, the command fails.

- `--start`: where to start, in seconds. By default, the video's start.
- `--length`: how long to take, in seconds. By default, to its end.
- `--size`: the frames' width and height, such as `320,240`. By default, the video's own.
- `--ffmpeg`: the ffmpeg program to use. By default, the one on the PATH.

From still pictures, nxwright reads them itself: one frame each, in order, all the same size, of any kind `animation` reads.

- A file of several frames, such as an animated GIF, counts as a video file.
- An MPO photo, which contains two views of one moment, counts as a still picture. Its first view is the frame.

## sound

```
nxwright sound app beep.wav
nxwright sound app alarm.mp3 --rate 16000 --mono
```

Adds a sound after the folder's other sounds.

- `--name`: the sound's name. By default, the file's.
- A WAV file of PCM samples, 8 or 16 bits, mono or stereo, is taken as it is. An 8-bit file at 22050 samples a second goes through ffmpeg instead, because the Nextion Editor refuses to compile it.
- Any other sound file goes through ffmpeg, which makes its samples 16-bit. So does any file given `--rate` or `--mono`. Without ffmpeg, the command fails.
- `--rate`: the samples a second to convert to, from 8,000 to 48,000.
- `--mono`: converts to one channel. A sound with more than two channels at 22050 samples a second needs `--mono` or another `--rate`, because the Nextion Editor refuses to compile it.
- `--ffmpeg`: the ffmpeg program to use. By default, the one on the PATH.

## sd-picture

```
nxwright sd-picture logo.png icons/*.png --output sdcard --rotation 90
```

Writes, for each picture, the file an external picture shows from the screen's SD card, the same way as PictureBox: `<the picture's name>.xi`, in the output folder, with the picture's transparency ([format.md, Pictures for the SD card](format.md#pictures-for-the-sd-card)). It does not change a source folder.

- `--output`: the folder to write in. It is made if it is missing.
- `--quality`: PictureBox's quality, one of `highest`, `very-high`, `high`, `middle`, `low`, and `very-low`. `very-high` by default.
- `--rotation`: the screen's rotation, in degrees. 0 by default.
- It reads pictures as `animation` does.
- These are refused, and nothing is written: a picture that cannot be read, two pictures with the same name, and a file already in the output folder.

## remove

```
nxwright remove app picture icons/back
```

Removes a picture, font, animation, video, or sound: its files, including a picture's source file, and its name in `app.toml`.

Every later one of its kind then gets an ID one lower. Code that uses a resource by its name follows the change, but a number does not, and would then point to another one. So the command refuses to remove a resource while the folder uses it, either by its name, or by a number from its ID to the last ID of its kind. Each place found is listed:

- by name, wherever a code editor's Find All References finds it;
- in a page file, an attribute of its kind, written there or left to the defaults, such as a text's `font` of 0;
- in code, a number written there or given by an nxlang constant, assigned to such an attribute or compared with it (`p0.pic=2`);
- in code, the picture of `pic`, `picq`, `xpic`, or of `xstr`'s background while its `sta` is 0 or 2, the font of `xstr`, or the sound of `play`.

Details:

- A number that code computes, or keeps in a variable, as in `p0.pic=n0.val`, is not found.
- A folder whose checks find an error is refused too, since the error could hide a use.
- A file that cannot be deleted is listed, and stays, though `app.toml` no longer lists it.
- A folder that a picture's name made, such as `icons/`, stays, even when empty.

## device

```
nxwright device app --screen NX4832T035 --rotation 90 --encoding utf-8
```

Changes the folder's screen model, its rotation, its character encoding, or any of them, like the Nextion Editor's Device window. A setting given its present value changes nothing.

As it works, the command prints each step as it starts, with the file it works on: each page resized, each font converted, each video made again with its number of frames, then the writing and the check. A video takes the longest.

### A new screen

- Each page takes the new screen's size, at its rotation: each page file's `w` and `h` change.
- Every component keeps its place and its size.
- Pictures, animations, and sounds stay as they are. The build makes the pictures' screen copies for the series and the rotation, and the Nextion Editor makes an animation's form again when it compiles.
- For a picture whose file is of a type nxwright does not decode, the folder keeps the project's screen copy, such as `pictures/logo.screen` ([source-folder.md](source-folder.md#layout)). The command makes that screen copy again from the pixels it contains, in the new screen's format and rotation. If the picture is partly transparent, and the new screen's format cannot store transparency, the command stops and writes nothing. The Nextion Editor blends such a picture with white, working from the picture's file, and nxwright cannot decode that file.

### A new rotation

- Each page takes the screen's size at the new rotation, as for a new screen.
- Each font stays as it is. The Nextion Editor takes a font stored for any rotation, shows its text the same, and turns it when it compiles ([format.md, Rotation](format.md#rotation)). Turning a large font takes seconds, so leaving each one as it is keeps the change quick.
- A picture's `.screen` file is made again, as for a new screen.
- A video is made for one rotation. The Nextion Editor's compile refuses a video made for another, and so does the build. nxwright does not keep the source a video was made from. So each video is made again from its own frames, each frame coded again as VideoBox codes one, which loses a little quality. The command prints a note for each video.

### A new encoding

The Nextion Editor changes only the encoding: each text keeps its bytes, and each font keeps its encoding. A source folder keeps its texts as characters instead, which the build stores in the folder's encoding. So nxwright converts each font, keeping each glyph under its character, in a font of the new encoding with the characters it has ([format.md, Fonts](format.md#fonts)).

- A character the new encoding lacks is left out. So is a character below the space, in a one-byte font, which starts at the space. The command lists them. Past 64 runs of them, as for a two-byte font made one-byte, it lists the first and counts the rest.
- A font made two-byte, such as gb2312 or big5, has every position of its table. Each of its characters goes to its position, and the other positions are empty, as wide as the font is tall ([format.md, Two-byte fonts](format.md#two-byte-fonts)).
- A font in an encoding the folder takes beside its own, such as a keyboard's iso-8859-1 font in a utf-8 folder, stays as it is, if the new encoding takes it too.

### After the change

The command runs the folder's checks, the same way as `nxwright check`, and lists each error the build will now refuse. Components keep their places, so these stay until you change them:

- a component past the edge of a smaller screen;
- a type, choice, attribute, or line of code the new series refuses ([What a series refuses](build-rules.md#what-a-series-refuses));
- a text the new encoding cannot store.

Keyboard pages nxwright made are pages like any other: they stay laid out for the old screen.

## upgrade

```
nxwright upgrade app
```

Converts a source folder made by an older version of nxwright to the current format, in place, step by step. A folder already in the current format is left as it is. nxwright refuses a folder in an older format until it is upgraded, and a folder in a newer format needs a newer nxwright ([app.toml](source-folder.md#apptoml)).

## language

```
nxwright language app nxlang
```

Switches a folder in strict Nextion syntax to nxlang ([language.md](language.md)). nxlang reads `a+b*c` as `a+(b*c)`, where the Nextion Editor computes `(a+b)*c`. So the switch rewrites every line that the two would read differently, with the parentheses that keep the Nextion Editor's meaning, then changes the `language` line in `app.toml`.

- Switch only this way, never by editing `app.toml`.
- After the switch, `nxwright extract` and `nxwright import` refuse the folder, so changes made in the Nextion Editor can't come back into it ([Working with the Nextion Editor](language.md#working-with-the-nextion-editor)).
- Nothing is written if any code would not build to the same project.

## password-hash

```
nxwright password-hash "my password"
```

Prints the `password_hash` value for a password: the hash the Nextion Editor stores in a project. Use it in `app.toml`'s `password_hash`, or a page's `lock_password_hash`, so that the password itself stays out of the folder ([app.toml](source-folder.md#apptoml)).

The password must be ASCII. The Nextion Editor hashes other characters in Windows' code page, whatever the project's encoding, and may then refuse the password when the project is opened.

## defaults

```
nxwright defaults sample.HMI defaults.toml
```

Writes a defaults file from a sample project: one page with one newly added component of each type, left as the Nextion Editor created it ([Component defaults](source-folder.md#component-defaults)).

## lsp

```
nxwright lsp
```

Runs nxwright's language server, which answers a code editor's questions about source folders, such as where a name is defined. It talks the Language Server Protocol on its standard input and output. A code editor starts it, as [nxwright's VS Code extension](../editors/vscode/README.md) does.

## mcp

```
nxwright mcp
```

Runs nxwright's MCP server, which lets an AI agent, such as Claude Code, run your app and use it: tap the screen, let time pass, and see what the screen shows. It talks the Model Context Protocol on its standard input and output. The agent starts it itself ([Letting an agent drive your app](mcp.md)).

## Other commands

- `dump`, `import`, `write`, and `page` work on dumps: a project file written out as text ([dumps.md](dumps.md)).
- `test` runs your tests ([testing.md](testing.md)).

## Output for programs

`compile`, `upload`, and `ports` take `--json`, for programs such as nxwright's VS Code extension. Each then prints one JSON object per line, and its messages for people go to standard error. `compile` and `upload` never prompt with `--json`: give `--download` to allow a download, and `--yes` to upload. The objects are:

- `compile`:
  - `{"event": "download", "done": ..., "size": ...}`, in bytes, as a download goes on;
  - `{"event": "firmware-missing", "version": "1.68.2"}`, when nothing on your computer has the firmware, and `--download` was not given;
  - `{"event": "compiled", "tft": ..., "project_file": ..., "firmware_source": ..., "warnings": [...]}`, once the files are written. `project_file` is `null` without `--project-file`.
- `upload`:
  - `{"event": "found", "file": ..., "size": ..., "file_model": ..., "port": ..., "screen": ..., "screen_rate": ..., "takes_every_rate": ..., "upload_rate": ..., "warnings": [...]}`, once the screen is found;
  - `{"event": "cancelled", "reason": ...}`, when the command cancels the upload, and then exits with 1. If the file fails its checks, this is the only object printed, because the port is never opened. Otherwise it is printed after the `found` object;
  - `{"event": "skipped", "bytes": ...}`, when the screen skips what it has;
  - `{"event": "progress", "sent": ..., "size": ...}`, after each packet;
  - `{"event": "uploaded"}`, once the whole file is sent.
- `ports`: `{"port": ..., "description": ...}` for each port, with `""` for no description.
