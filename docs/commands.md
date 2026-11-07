# Commands

Most of nxwright's commands work on a source folder: your project as files ([source-folder.md](source-folder.md)).

```
nxwright new <source-folder>
nxwright extract <project.HMI> <source-folder> [--continue-with-unknown]
nxwright extract --list-unknown <project.HMI>
nxwright diff <source-folder or project.HMI> <source-folder or project.HMI> [--no-lock]
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
nxwright mcp
```

Run `nxwright <command> --help` for a command's options, and `nxwright --version` for the version of nxwright installed.

## new

```
nxwright new app --screen NX8048P050 --name "Living room"
```

`new` starts a source folder for a new project, with one blank page the size of the screen and one font, so that you can add a first text and build.

- `--screen`, `--rotation`, `--encoding`: the device settings. The rotation is 0 by default, and the encoding `iso-8859-1`.
- `--language`: the code's language, `nxlang` by default, or `nextion` for strict Nextion syntax ([language.md](language.md)).
- `--name`: the name nxwright shows for the app. By default, the folder's name. The name is stored in `app.toml`, so it does not change if you later rename the folder.
- If you leave out the device settings or the language, the command prompts for them.

Details:

- `program.nx` declares `int sys0=0,sys1=0,sys2=0`, because the Nextion Editor rejects code that uses these variables without that declaration.
- The font is Noto Sans at 24 pixels, called `NotoSans24`.
- In utf-8, the font has the characters U+0000 to U+00FF, the same characters `font` draws by default.
- Noto Sans lacks some characters of some encodings, such as koi8-r's box-drawing characters or windows-874's Thai. The font leaves them out, and the command warns you.
- In a two-byte encoding, such as gb2312 or big5, Noto Sans has none of the Chinese, Japanese, or Korean characters. They show empty until you add a font drawn from a typeface that has them ([font](#font)).

## extract

```
nxwright extract thermostat.HMI app
```

`extract` turns a project file into a new source folder, so that you can start from a project made in the Nextion Editor. The project file does not change.

- The folder must not exist yet, or be empty. For any other folder, extract fails and changes nothing.
- The app is named after the project file: `thermostat.HMI` gives `thermostat`.
- Close the project in the Nextion Editor before you extract it, because the Nextion Editor locks a project it has open.
- Extract drops blank lines from the project's code, and warns about each event, macro, or `program.s` that had any. This does not change the app, because the Nextion Editor compiles blank lines to nothing.
- If the project contains something a source folder cannot represent, such as a control character in code, extract stops with an error before writing anything.
- A project saved by a newer Nextion Editor may contain things nxwright does not know. Before writing anything, extract puts each one in one of four groups:
  - **Kept exactly**, such as a component type nxwright does not know, or an attribute it does not know. A page file keeps such an attribute as its stored bytes ([source-folder.md](source-folder.md#page-files)). A warning gives each thing kept.
  - **Written otherwise** by the next build, in a form nxwright knows. For example, the build writes a page header of an unfamiliar form in the current form, and puts an object's records back in their usual order. A warning gives each thing, and extract goes on without prompting.
  - **May be lost** by the next build, such as a block of a kind nxwright does not handle, or a screen model it does not know. Extract lists each one, warns that the project may then lack parameters the Nextion Editor needs, and prompts you to choose whether to go on. `--continue-with-unknown` goes on without prompting. In a script, without that option, extract stops with exit code 3.
  - **Cannot be kept**, such as a component without its type, ID, or name. Extract rejects the project.

  `nxwright report` writes a report on these things that you can send to nxwright's maintainers ([report](#report)).
- `nxwright extract --list-unknown thermostat.HMI` prints each thing in the project that nxwright does not know, one JSON object per line, and writes nothing. Each object gives what the thing is, where it is, its group from the list above (as `sort`), its size, and its first 16 bytes in hexadecimal.

`nxwright dump`, then `nxwright import`, do the same as `extract` in two steps ([dumps.md](dumps.md)).

## diff

```
nxwright diff app thermostat.HMI
nxwright diff thermostat.HMI.2026-11-06-143205.bak thermostat.HMI
```

Use `diff` to see what someone changed in a project file, for instance after an edit in the Nextion Editor and before a build replaces it. Give your source folder first and the modified project file second, so that the latter's changes show as added lines. You can also compare two project files, such as a backup and the current one. `diff` does not modify either projects.

- To bring a change into your folder, copy it by hand. The diff shows code the way it would be extracted, so its spacing may differ from yours.
- If you build with `--no-lock`, pass it to `diff` too, so that the locks do not show as changes.

## report

```
nxwright report thermostat.HMI report.md
```

`report` writes a report on the things in a project file that nxwright does not know, for nxwright's maintainers to look into. Paste the report into an issue, with the issue template "A project nxwright does not understand".

- The report gives the versions of nxwright, Python, and Windows, the project file's blocks by name and size, its manifest header, and the device settings nxwright reads from it.
- Each thing nxwright does not know comes with what it is, at most its first 16 bytes, and where it is: a block's name, an object's number, or an attribute's name.
- The project's code, texts, names of pages or components, pictures, fonts, animations, videos, and sounds are left out. The password's hash is blanked, and the report gives only whether there is a password.
- A thing's first 16 bytes may contain some of your own text, so read the report before you send it.
- Two blanks are left for you to fill in: the Nextion Editor's version, and what you did in it before you saved the project.
- The project file does not change, and the command fails if the report's file already exists.

## build

```
nxwright build app thermostat.HMI
```

`build` writes a new project file from the source folder alone: its pages, code, pictures, fonts, animations, videos, sounds, and device settings.

- The build first checks the folder, and stops at the first problem it finds ([What the build refuses](build-rules.md)).
- The build prompts before it replaces an existing project file, and replaces it only once the new one is written in full and checked. `--overwrite` skips the prompt. A script must give it, because with no terminal to answer the prompt, the build fails. If the output exists and is not a project file, the build fails even with `--overwrite`.
- If the old project file changed since nxwright wrote it, for example in the Nextion Editor, it is kept as a backup beside the new one, such as `thermostat.HMI.2026-11-06-143205.bak`, and `nxwright diff` shows what changed ([diff](#diff)). `--no-backup` turns the backup off. nxwright never deletes a backup, so delete those you no longer need yourself. If your project is in git, you may want to ignore `*.bak`.
- A project file counts as changed if nxwright has no record of writing it, such as after you move it or use another computer. The record is in the same folder as [the picture cache](source-folder.md#the-picture-cache). With `NXWRIGHT_CACHE=off`, there is no record, so each build that changes the file keeps a backup.
- The build locks every page with no password, even if its page file has `locked = false`, to show that the project is not meant to be edited in the Nextion Editor. A page with its own password stays as it is. You can still unlock a page in the Nextion Editor, and `--no-lock` leaves each page as its page file sets it.
- Close the project in the Nextion Editor before you build over it, because the Nextion Editor locks a project it has open.
- The build prints each page's memory, such as `page0: 292 of 524288 bytes`. If nxwright could not count all the memory of any page, every page's line says `at least` ([Memory](build-rules.md#memory)).
- The screen copies of your pictures are kept in a cache, so that later builds are faster ([The picture cache](source-folder.md#the-picture-cache)).

To put your app on a screen, compile it with [compile](#compile) and send it with [upload](#upload). You can also open the built project in the Nextion Editor, and compile and upload it from there.

## compile

```
nxwright compile app thermostat.tft
nxwright compile thermostat.HMI thermostat.tft
```

`compile` turns a source folder, or a project file, into a TFT file, the file a Nextion screen runs.

- The compile first builds a source folder, and stops at any error the build finds. A project file is compiled as it is.
- If the project has something nxwright cannot compile, such as a number too large for its attribute, the compile lists every problem, and does not write any file.
- A sound at 22050 samples a second must be 16-bit, mono or stereo, or the compile fails. A sound at any other rate needs ffmpeg to convert it: either the ffmpeg on your PATH, or the program you give with `--ffmpeg`. Without ffmpeg, the compile fails.
- `--project-file <file.HMI>` also saves the project file that the compile builds from a source folder, so that you have one that always matches the TFT file. The pages of that project file are locked ([build](#build)), unless you give `--no-lock`. The locks do not change the TFT file.
- If an output file already exists, the compile fails unless you give `--overwrite`. Even then, it only replaces a TFT file with a TFT file, and a project file with a project file.
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

`upload` sends a TFT file, made by nxwright or the Nextion Editor, to the screen on a serial port, such as `COM5` or `/dev/ttyUSB0`.

- To find the screen, the command tries each rate a screen can use, which can take a few seconds. If you know the rate the screen uses now, you can give it with `--baud`.
- `--yes` skips the prompt before the file is sent. A script must give it, because with no terminal to answer the prompt, the command exits with 3 and does not send the file.
- The command cancels the upload, and exits with 1, in these cases:
  - the file is for a different model from the screen;
  - nxwright cannot tell the model of the file or of the screen;
  - the file's checksums do not match;
  - nxwright cannot read the file, such as one made by a Nextion Editor older than 1.60.1.
- `--find` stops once the screen is found and the file is checked against it, without sending the file.
- `--upload-baud` sets the rate of the upload. The default is 115200, which sends a megabyte in a little over a minute and a half. You can give any rate the screen supports, up to 921600, but some serial adapters lose bytes at the highest rates.
- The screen skips the parts of the file it already has, such as the firmware when only your app changed. `--full` sends the whole file.

Once the whole file is sent, the screen restarts and runs it. Do not power the screen off until your app is showing, because it may still be updating its firmware. If the screen stops answering, or you stop the upload, power the screen off and on, then upload the file again.

## ports

```
nxwright ports
```

`ports` lists your computer's serial ports, so that you can choose the one to give `upload`. It does not open any port, so it cannot tell which one a screen is on.

## rescue

```
nxwright rescue rescue.tft --screen NX4832T035
```

`rescue` writes a TFT file that sets a screen's settings back to their defaults. Use it for a screen that stays black or no longer answers because of one of the settings listed below. To put the file on the screen, follow [If the screen stays black or stops responding](screens.md#if-the-screen-stays-black-or-stops-responding).

- `--screen` gives the screen model. The file is only for that model.
- The firmware comes from the same places as for [compile](#the-firmware), with the same options: `--firmware`, `--editor`, and `--download`.
- If the output file already exists, the command fails unless you give `--overwrite`. Even then, it only replaces a TFT file. If that file changed since nxwright wrote it, it is kept as a backup ([build](#build)), unless you give `--no-backup`.

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

`decompile` turns a TFT file back into a source folder. Use it to recover a project when you still have its TFT file but have lost the project.

- The folder to write must be new or empty.
- The command reads a file made by versions 1.60.1 to 1.68.2 of the Nextion Editor, and fails on any other.
- For a file made by 1.68.2, the command first checks its work, by compiling the new folder with the file's own firmware and comparing the result with your file. A file made by an older version is decompiled without this check.
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

`check` runs every check the build makes, and writes nothing. It prints each problem with its place, and exits with 1 when there is an error:

```
pages/home.nx line 12: error: unknown name speed
```

- The build stops at the first error. The check reports the first error of each page.
- If `app.toml`, `defaults.toml`, or the declarations of `program.nx` have an error, the check reports only that error, since every page depends on these files.
- The check also finds:
  - a picture file, or a picture's source file, that nxwright cannot read, reported as `pictures/logo.png: not a picture nxwright reads: no kind of picture Pillow knows`. The check does not decode the pixels, so only the build finds a picture whose pixels are damaged;
  - a page that takes more memory than the Nextion Editor's compile allows ([Memory](build-rules.md#memory));
  - a sound that the Nextion Editor's compile rejects ([source-folder.md](source-folder.md#animations-videos-and-sounds)).

The [VS Code extension](../editors/vscode/README.md) runs the same checks as you type. It offers a quick fix for an error that has one sure fix, such as a command written in capitals.

### Warnings

The check also warns of likely mistakes that the build accepts. Each warning gives its rule's name:

- `left-to-right`, in strict Nextion syntax: a line the Nextion Editor computes in another order than the usual one. `sys0=a+b*c` computes `(a+b)*c`, and the warning shows it.
- `unused-constant`, in nxlang: a constant of a page's own `.nx` file, or of `program.nx`, that no code uses. Constants of other included files are left alone, since a library serves many pages.
- `unused-function`, in nxlang: a function of a page's own `.nx` file that the page never calls.
- `number-past-32-bits`, in nxlang: a hexadecimal number too large for 32 bits, such as `0x0100000005`, or a decimal number outside -2147483648 to 2147483647, such as `4294967295`. The build keeps only the low 32 bits, so these become `0x00000005` and `-1`.
- `event-never-runs`: code for an event that its component's type does not have, such as a page's `postinit`. The Nextion Editor keeps the code, but the screen never runs it. The warning lists the type's events. For `preinit` and `postinit`, the warning also gives the event to use, because the Nextion Editor's event pane uses other names: a page's Preinitialize Event is `load`, and its Postinitialize Event is `loadend`.
- `page-place`: a page file gives the page an `x`, `y`, `w`, or `h` that does not match the screen. The build makes the page fill the screen, whatever these values are.
- `text-cut`, in nxlang: a line that puts a text into one of nxlang's hidden variables, when the text may be too long for the variable and get cut. The warning shows only when a part of the text is a component's text, or a hidden variable with room for more than 255 bytes, such as a parameter that a caller gave a long text. The warning gives how many bytes the text may need. To keep the whole text, use a variable component with a `txt_maxl` of that size.
- `sound-file-form`: a sound file without the `hmic` chunk that the Nextion Editor's Audio panel writes, or whose chunk has a check value that does not match its samples. The warning shows on the line of `app.toml` that gives the sound. The Nextion Editor accepts such a file, but a screen might check the value. `nxwright sound` writes the chunk and its check value.
- `memory-not-checked`: the folder has something whose memory nxwright cannot count, so the pages are checked without it ([Memory](build-rules.md#memory)). The warning shows on the page with it.

## format

```
nxwright format app
nxwright format app --check
```

`format` lays out every `.nx` file in one style, in either language, like a code editor's Format Document. `macros.nx` is always laid out as strict Nextion syntax, and each of its macros the same way as an event.

- `--check`: writes nothing, lists the files that would change, and exits with 1 if any would.

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

Formatting never changes what your code does. A file is formatted only if everything that uses it, including `program.nx` and the macros of `macros.nx`, builds to the same code as before, apart from spaces and tabs at the start and end of lines. If any file fails this check, or the folder does not build, the command writes nothing.

The build copies indentation into the project, so the next build of a formatted folder changes only the indentation in the project file.

## new-page

```
nxwright new-page app settings
```

`new-page` adds a blank page the size of the screen, at the folder's rotation, with an empty code file, and lists the page last in `app.toml`.

- Without a name, the page is called `page0`, `page1`, and so on: the first one the folder does not have.
- The command fails, and writes nothing, in these cases:
  - a name the folder already has, in any letter case;
  - a name longer than 14 characters;
  - a name the Nextion Editor rejects, such as `dim`;
  - a folder that already has 251 pages, the most the Nextion Editor can compile.

## picture

```
nxwright picture app "My Icon.jpg" logo.png
```

`picture` copies picture files into the folder's `pictures/`, and lists them after its other pictures, in the order given. It takes `.png`, `.jpg`, `.jpeg`, `.bmp`, and `.gif` files.

- Each picture is named after its file, keeping only letters, digits, `_`, and `-`: `My Icon.jpg` gives `MyIcon`.
- The command fails, and writes nothing, in these cases:
  - a file nxwright cannot read as a picture;
  - a name the folder already has, in any letter case;
  - a name whose file, or source file, is already in `pictures/`, though `app.toml` does not list it;
  - two files that give the same name.

## font

`font` either draws a font from a typeface file, or adds a ready-made font file. nxwright ships Noto Sans, at `nxwright/project/fonts/NotoSans-Regular.ttf`.

### From a typeface file

```
nxwright font app NotoSans-Regular.ttf 20
```

`font` draws a font from a TrueType (`.ttf`) or OpenType (`.otf`) file, or from the first typeface of a collection (`.ttc`) ([format.md, Drawing a font](format.md#drawing-a-font)). The font is stored for the folder's rotation, or upright on the F series, and added after the folder's other fonts.

- The height: from 12 to 254 pixels.
- `--name`: the font's name. By default, the typeface's name and the height, such as `NotoSans20`.
- `--no-smoothing`: makes each pixel empty or full, without anti-aliasing.
- `--characters`, in a utf-8 folder: the characters to draw, as code points in hexadecimal, and ranges of them, such as `20-7e,400-4ff`. By default `0-ff`, the same characters as the first two blocks of the Nextion Editor's font generator.
- `--full-table`, in a utf-8 folder: a different kind of table (below).

The font is in the folder's encoding:

- In a one-byte encoding, such as iso-8859-1, the font has every character of the encoding.
- In a two-byte encoding, such as gb2312 or big5, the font has every character of the encoding.
- In utf-8, the font has the characters you chose and the space, in a table of those characters only. Noto Sans at 20 pixels, for `0-ff`, is about 10 KB.
  - The screen shows a character such a font lacks as the font's first character. With the default `0-ff`, that is U+0000, empty and a pixel wide. When your characters start above the space, it is the space ([format.md, Fonts](format.md#fonts)).
  - With `--full-table`, the table has an entry for every code point up to U+FFFF instead. It is at least 655 KB, whatever characters it contains, and the command prints its size. The screen then shows a character the font lacks as nothing, half the font's height wide ([format.md, utf-8 fonts](format.md#utf-8-fonts)).

When your typeface file lacks a character the font should have:

- In a one-byte encoding, or in utf-8, the character is left out of the font, and the command warns you, with what the screen will show instead ([format.md, Fonts](format.md#fonts)).
- In a two-byte encoding, the character is empty, as wide as the font is tall, and the command warns you ([format.md, Two-byte fonts](format.md#two-byte-fonts)).
- A typeface file that has none of the characters, control characters aside, is rejected.

The command also fails if the folder already has a font of that name.

### From a font file

```
nxwright font app NotoSans16.zi
```

`font` can also add a ready-made font file, such as one from the Nextion Editor's font generator, after the folder's other fonts.

- A font stored for another rotation is turned to the folder's rotation, or to upright on the F series. nxwright can turn a font in any encoding, two-byte ones included ([format.md, Two-byte fonts](format.md#two-byte-fonts)).
- The font gets the name stored in its file, such as `NotoSans16`, unless you give another with `--name`. The name inside the file does not change.
- The command fails if the folder already has a font of that name, or if the file is not a font.

The font's encoding must be one of these:

- the folder's own encoding;
- ascii, in an iso-8859-1 folder. The Nextion Editor adds such fonts itself, for its stock keyboards;
- iso-8859-1, in a folder whose encoding Noto Sans does not cover, such as koi8-r, or in a utf-8 folder. Older nxwright keyboards used such fonts ([keyboard](#keyboard)). The command prints a warning that text beyond ascii will show garbled.

## keyboard

```
nxwright keyboard app keypad
```

`keyboard` adds one of nxwright's keyboard pages. In VS Code, "nxwright: Add a keyboard page" does the same. So does the Attributes section, when you set a component's `key` to a keyboard the folder lacks ([the extension's README](../editors/vscode/README.md)).

A component bound to a keyboard by its `key` opens the keyboard's page when it is released: 1 opens the full keyboard, 2 the numeric keypad, 3 the speed dial, and 4 Chinese input. The Nextion Editor adds its own pages for these, `keybdA` to `keybdAP`, and extracting keeps them as they are. nxwright has pages of its own for all four, with the same names:

- **keyboard** (`keybdA`) fills the screen: the text and cancel (X) above four rows of keys. Its mode key switches the letter keys between small letters, capitals, and numbers and signs.
- **keypad** (`keybdB`) is a panel in the middle of a page without background, so that the caller's page shows around it: digits, a minus sign, a point, delete, and OK.
- **speed-dial** (`keybdC`) is a panel too. A group key, such as "abc", shows its characters on four choice keys, and a tap on one types it. Its mode key switches the groups to capitals, then to digits, which type at once.
- **chinese-input** (`keybdAP`) types Chinese from pinyin. Type a syllable, such as `mei`, and six of its characters appear above the letters. Use `<` and `>` to see more, and tap one to type it. Delete removes the syllable's last letter, or else the last character. The mode key switches between pinyin (中), small letters, capitals, and numbers and signs.

Like the Nextion Editor's own keyboards, each one works with the component that opened it:

- A keyboard reads the caller's `txt`, up to its `txt_maxl` bytes, and hides the text when `pw` is 1. It reads a number or an xfloat as its digits.
- OK writes the text back. Cancel leaves the caller as it was.
- A keyboard takes at most 100 bytes of the caller's text, so a longer text comes back cut.
- A number takes 11 bytes at most. A number typed past the screen's 32-bit range wraps when it is written back.

The pages the command adds are laid out for the folder's screen, at its rotation, in the colours of nxwright's demo. They are ordinary files in the folder, and you can change them. See [Keyboards](simulator.md#keyboards) for what the screen relies on.

### The keyboard's font

The command adds a font with each keyboard page: Noto Sans at the largest height whose labels fit the keys, named after the typeface and the height, such as `NotoSans24`. If the folder already has a font of that name, the keyboard uses that font as it is.

The font is in the folder's encoding:

- In utf-8, the font has U+0000 to U+00FF, the characters of iso-8859-1, which `font` also draws by default. Any other character in a caller's text shows as the font's first character, a gap of a pixel, and the command warns you.
- Where Noto Sans lacks some characters of a one-byte encoding, such as koi8-r's box-drawing characters, the font leaves them out, and the command warns you. A caller's text with them shows the font's first character, the space, in their place.
- In a two-byte encoding, such as gb2312 or big5, Noto Sans has none of the Chinese, Japanese, or Korean characters. A caller's text in them shows empty, and the command warns you. The font has room for every character of the encoding, so it is large, and the command prints its size.

To show those characters, add a font with the keyboard's font name, drawn from a typeface that has them, before you add the keyboard. The keyboard then uses that font.

A folder made with an older version of nxwright may have keyboard fonts in iso-8859-1, if the folder is in utf-8, koi8-r, a two-byte encoding, or another encoding that Noto Sans does not fully cover. nxwright keeps those fonts.

### The Chinese keyboard

The Chinese keyboard only works in a gb2312 folder. Its font needs Chinese characters, which Noto Sans does not have, so you choose one:

```
nxwright keyboard app chinese-input --typeface simsun.ttc
nxwright keyboard app chinese-input --font SimSun16
```

- `--typeface` draws the font from a typeface file with Chinese characters (`.ttf`, `.otf`, or `.ttc`), as large as the keys allow, up to 24 pixels. A font with every Chinese character is large: about 1.2 MB at 24 pixels. The command prints its size.
- `--font` uses a gb2312 font your folder already has.

To show a syllable's characters, tests and the simulator need the screen's pinyin table ([Chinese input](screen-code.md#chinese-input-pa_q-and-pa_txt)).

### What it rejects

- A folder that already has that keyboard: a page of any name marked as that system page, whether the Nextion Editor's or nxwright's.
- A folder with a page of the keyboard's name that is another page.
- A folder that already has 251 pages, the most the Nextion Editor can compile.

### With the Nextion Editor

- In the Nextion Editor, setting a component's `key` uses the keyboard page the project has, nxwright's included, and does not add its own.
- The Nextion Editor's "Reset system page", in the Page panel's menu, does replace nxwright's page with the Nextion Editor's stock keyboard, under the same name and locked. It also imports the two fonts the stock page uses, `24ascii` and `16ascii`.
- Extracting then brings the stock page and its two fonts into the folder, and `nxwright keyboard` fails on that keyboard, because the folder already has it.

## animation

```
nxwright animation app frame1.png frame2.png frame3.png --duration 100
```

`animation` makes an animation from pictures, one frame each, in order, and adds it after the folder's other animations ([Animations, videos, and sounds](source-folder.md#animations-videos-and-sounds)).

- `--duration`: how long each frame shows, in milliseconds. 50 by default.
- `--name`: the animation's name. By default, the first picture's.
- The pictures must all be the same size. They can be PNG, JPEG, BMP, or any other kind that Pillow, the picture library nxwright uses, can read. A GIF gives its first frame.
- The `.screen.gmov` file, which the screen plays, is made for the folder's rotation.
- You can give a `.gmov` file made with GmovMaker, the Nextion Editor's animation tool, in place of the pictures, as in `nxwright animation app blink.gmov`. The command keeps that file as it is, and makes the `.screen.gmov` file from its frames. The frames keep their own durations, so `--duration` is invalid with a `.gmov` file.

## video

```
nxwright video app intro.mp4 --size 320,240 --length 5
nxwright video app frame1.png frame2.png --rate 10
```

`video` makes a video from a video file or from still pictures, and adds it after the folder's other videos.

- `--rate`: frames a second, from 1 to 255. 12 by default.
- `--name`: the video's name. By default, the first source's.
- The video is made for the folder's rotation.

The command needs ffmpeg to cut a video file into frames, and fails without it. These options apply to a video file:

- `--start`: where to start, in seconds. By default, the video's start.
- `--length`: how long to take, in seconds. By default, to its end.
- `--size`: the frames' width and height, such as `320,240`. By default, the video's own.
- `--ffmpeg`: the ffmpeg program to use. By default, the one on the PATH.

Still pictures do not need ffmpeg. Each one gives a frame, in order, and they must all be the same size, of any kind Pillow reads ([animation](#animation)).

- A file of several frames, such as an animated GIF, counts as a video file.
- An MPO photo, which contains two views of one moment, counts as a still picture. Its first view is the frame.

## sound

```
nxwright sound app beep.wav
nxwright sound app alarm.mp3 --rate 16000 --mono
```

`sound` adds a sound after the folder's other sounds.

- `--name`: the sound's name. By default, the file's.
- A WAV file of PCM samples, 8 or 16 bits, mono or stereo, is taken as it is. An 8-bit file at 22050 samples a second goes through ffmpeg instead, because the Nextion Editor's compile rejects it.
- Any other sound file goes through ffmpeg, which makes its samples 16-bit. So does any file given `--rate` or `--mono`. Without ffmpeg, the command fails.
- `--rate`: the samples a second to convert to, from 8,000 to 48,000.
- `--mono`: converts to one channel. A sound with more than two channels at 22050 samples a second needs `--mono` or another `--rate`, because the Nextion Editor's compile rejects it.
- `--ffmpeg`: the ffmpeg program to use. By default, the one on the PATH.

## sd-picture

```
nxwright sd-picture logo.png icons/*.png --output sdcard --rotation 90
```

`sd-picture` writes an `.xi` file for each picture into the output folder, so that an external picture component can show it from the screen's SD card. The file is named after the picture and keeps its transparency ([format.md, Pictures for the SD card](format.md#pictures-for-the-sd-card)). PictureBox, the Nextion Editor's tool for SD card pictures, writes the same kind of file.

- `--output`: the folder to write in. It is made if it is missing.
- `--quality`: PictureBox's quality, one of `highest`, `very-high`, `high`, `middle`, `low`, and `very-low`. `very-high` by default.
- `--rotation`: the screen's rotation, in degrees. 0 by default.
- Pictures can be of any kind Pillow reads ([animation](#animation)).
- The command fails, and writes nothing, on a picture it cannot read, two pictures with the same name, or a file already in the output folder.

## remove

```
nxwright remove app picture icons/back
```

`remove` removes a picture, font, animation, video, or sound: its files, including a picture's source file, and its name in `app.toml`.

The command fails while the folder still uses the resource, and lists each use it found. The folder can use a resource by its name, or by a number from the resource's ID to the last ID of its kind. Numbers in that range count because removing a resource gives every later one of its kind an ID one lower, so those numbers would then point to the wrong resource. The command looks for these uses:

- by name, wherever a code editor's Find All References finds it;
- in a page file, an attribute of its kind, written there or left to the defaults, such as a text's `font` of 0;
- in code, a number written there or given by an nxlang constant, assigned to such an attribute or compared with it (`p0.pic=2`);
- in code, the picture of `pic`, `picq`, `xpic`, or of `xstr`'s background while its `sta` is 0 or 2, the font of `xstr`, or the sound of `play`.

Details:

- A number that code computes, or keeps in a variable, as in `p0.pic=n0.val`, is not found.
- The command also fails on a folder whose checks find an error, since the error could hide a use.
- A file that cannot be deleted is listed, and stays, though `app.toml` no longer lists it.
- A folder that a picture's name made, such as `icons/`, stays, even when empty.

## device

```
nxwright device app --screen NX4832T035 --rotation 90 --encoding utf-8
```

`device` changes the folder's screen model, its rotation, its character encoding, or any of them.

### A new screen

- Each page takes the new screen's size, at its rotation: each page file's `w` and `h` change.
- Every component keeps its place and its size.
- Pictures, animations, and sounds stay as they are. The build makes the pictures' screen copies for the series and the rotation, and the Nextion Editor makes an animation's `.screen.gmov` file again when it compiles.
- For a picture whose file is of a type nxwright does not decode, the folder keeps the project's screen copy, such as `pictures/logo.screen` ([source-folder.md](source-folder.md#layout)). The command makes that screen copy again from the pixels it contains, in the new screen's format and rotation. If the picture is partly transparent, and the new screen's format cannot store transparency, the command stops and writes nothing. The Nextion Editor blends such a picture with white, working from the picture's file, and nxwright cannot decode that file.

### A new rotation

- Each page takes the screen's size at the new rotation, as for a new screen.
- Each font stays as it is, because the Nextion Editor accepts a font stored for any rotation, and turns it when it compiles ([format.md, Rotation](format.md#rotation)).
- A picture's `.screen` file is made again, as for a new screen.
- Each video is made again from its own frames, because the build and the Nextion Editor's compile both reject a video made for another rotation, and nxwright does not keep a video's source. This is the slowest step, and coding the frames again loses a little quality.

### A new encoding

The command converts each font to the new encoding, keeping each glyph under its character ([format.md, Fonts](format.md#fonts)). It does this because a source folder keeps its texts as characters, which the build stores in the folder's encoding. The Nextion Editor differs: it changes only the encoding, so each text keeps its bytes, and each font keeps its encoding.

- A character the new encoding lacks is left out, and so is a character below the space in a one-byte font, which starts at the space. The command lists these characters.
- A font converted to a two-byte encoding, such as gb2312 or big5, has every position of its table. Each of its characters goes to its position, and the other positions are empty, as wide as the font is tall ([format.md, Two-byte fonts](format.md#two-byte-fonts)).
- A font in an extra encoding that the folder accepts, such as a keyboard's iso-8859-1 font in a utf-8 folder, stays as it is if the new encoding accepts that font too.

### After the change

The command then runs the same checks as `nxwright check`, and lists each error that will now stop the build, for you to fix, such as:

- a component past the edge of a smaller screen, because components keep their places;
- a type, choice, attribute, or line of code the new series rejects ([What a series refuses](build-rules.md#what-a-series-refuses));
- a text the new encoding cannot store.

Keyboard pages nxwright made stay laid out for the old screen, like any other page.

## upgrade

```
nxwright upgrade app
```

`upgrade` converts a source folder made by an older version of nxwright to the current format, in place. nxwright rejects a folder in an older format until it is upgraded, and a folder in a newer format needs a newer nxwright ([app.toml](source-folder.md#apptoml)).

## language

```
nxwright language app nxlang
```

`language` switches a folder in strict Nextion syntax to nxlang ([language.md](language.md)). nxlang reads `a+b*c` as `a+(b*c)`, where the Nextion Editor computes `(a+b)*c`. So the switch rewrites every line that the two would read differently, with the parentheses that keep the Nextion Editor's meaning, then changes the `language` line in `app.toml`.

- Switch only this way, never by editing `app.toml`.
- The command writes nothing if any code would not build to the same project.

## password-hash

```
nxwright password-hash "my password"
```

`password-hash` prints the `password_hash` value for a password: the hash the Nextion Editor stores in a project. Use it in `app.toml`'s `password_hash`, or a page's `lock_password_hash`, so that the password itself stays out of the folder ([app.toml](source-folder.md#apptoml)).

The password must be ASCII. The Nextion Editor hashes other characters in Windows' code page, whatever the project's encoding, and may then reject the password when the project is opened.

## defaults

```
nxwright defaults sample.HMI defaults.toml
```

`defaults` writes a defaults file from a sample project. The sample project has one page, with one newly added component of each type, left as the Nextion Editor created it ([Component defaults](source-folder.md#component-defaults)).

## lsp

```
nxwright lsp
```

`lsp` runs nxwright's language server, which answers a code editor's questions about source folders, such as where a name is defined. It uses the Language Server Protocol over its standard input and output. A code editor starts it, and [nxwright's VS Code extension](../editors/vscode/README.md) does this for you.

## mcp

```
nxwright mcp
```

`mcp` runs nxwright's MCP server, which lets an AI agent, such as Claude Code, run your app and use it: tap the screen, let time pass, and see what the screen shows. It uses the Model Context Protocol over its standard input and output. The agent starts it itself ([Letting an agent drive your app](mcp.md)).

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
