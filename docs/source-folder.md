# Your project as a source folder

A **source folder** is your Nextion project as plain files: TOML files for the pages and their components, `.nx` files for their code, and the pictures, fonts, animations, videos, and sounds as files. You edit it in any code editor and optionally keep it in git. The Nextion Editor still opens and compiles the project file. nxwright goes between the two.

You can start a source folder in two ways.

Start a new project:

```
nxwright new app --screen NX8048P050    # a new source folder, with one blank page
```

Or start from a project you made in the Nextion Editor:

```
nxwright extract thermostat.HMI app     # the project file, into a source folder
```

Either way, you then edit the files in `app/`, and build the project file:

```
nxwright build app thermostat.HMI       # the source folder, into a project file
```

The usual cycle:

1. Edit the source folder (optionally simulate and debug with [nxwright's VS Code extension](../editors/vscode/README.md)).
2. Build the project into an HMI file.
3. Open the HMI file in the Nextion Editor, deploy to the physical screen there.

If a project is changed in the Nextion Editor, save it, then extract it to bring the changes back into the source folder.

For the options of `nxwright new`, and what it creates, see [commands.md](commands.md#new).

This page describes the folder's files. [commands.md](commands.md) describes each command, and [build-rules.md](build-rules.md) what the build refuses.

## Layout

| Path | Contents |
| --- | --- |
| `app.toml` | The folder's format, its language, its device settings, then the pages, pictures, fonts, animations, videos, and sounds, in ID order, by name. |
| `defaults.toml` | What a newly added component of each type has ([Component defaults](#component-defaults)). |
| `program.nx` | The code that runs when the screen starts. |
| `macros.nx` | The project's macros, if it has any ([Macros](#macros)). |
| `pages/<page>.page.toml` | The page and its components, in ID order. The `.page.toml` ending marks a page file, so VS Code opens it in the page preview. |
| `pages/<page>.nx` | The page's event code. |
| `pictures/<name>.png`, or `.jpg`, `.jpeg`, `.bmp`, `.gif` | A picture. `nxwright picture` adds one ([commands.md](commands.md#picture)). |
| `fonts/<name>.zi` | A font. `nxwright font` draws one from a typeface file, such as a `.ttf` file, or adds a ready-made font file ([commands.md](commands.md#font)). |
| `animations/<name>.gmov`, `animations/<name>.screen.gmov` | An animation: its frames, and the form the screen shows. `nxwright animation` makes both from picture files, or from GmovMaker's file ([Animations, videos, and sounds](#animations-videos-and-sounds)). |
| `videos/<name>.video` | A video. `nxwright video` makes one. |
| `sounds/<name>.wav` | A sound. `nxwright sound` adds one. |

These files are in the same formats as those the Nextion Editor and its tools create, so you can also use what you made with them:

- a font file from the Nextion Editor's font generator, or a video from VideoBox, the Nextion Editor's video tool: copy it into `fonts/` or `videos/`, and list it in `app.toml`. For a font, `nxwright font` can do this for you, and it also turns a font made for another rotation;
- a sound: give the original sound file to `nxwright sound`, as you would to the Nextion Editor's Audio panel;
- an animation made with GmovMaker, the Nextion Editor's animation tool: give its `.gmov` file to `nxwright animation`, as you would to the Nextion Editor's Gmov panel. `nxwright animation` keeps the file, and makes the `.screen.gmov` file the screen shows.

Extracting brings in everything a project already has, animations included.

About picture files:

- A picture's file is kept as it is. Its suffix is the one the picture's record gives.
- Each picture has one file. Two files for the same picture name, such as `pictures/logo.png` and `pictures/logo.jpg`, are refused, since nxwright cannot tell which one is to be used.
- The suffix is in lower case, as extracting writes it. A camera's `IMG_0001.JPG` is found on Windows alone, so rename it `IMG_0001.jpg`.
- A `/` in a name makes a subfolder: `pictures/icons/back.png`.

## app.toml

```
format = 1
name = "Living room"
language = "nextion"
screen = "NX8048P050"
rotation = 180
encoding = "iso-8859-1"
pages = [
    "main",
    "settings",
]
pictures = [
    "icons/back",
    "logo",
]
fonts = [
    "NotoSans16",
    "NotoSans24",
]
```

nxwright writes its TOML files with tomli-w, which lays out each list with one name per line, as above. It reads any layout TOML allows, so you may write a list on one line too.

- `format` is the version of the source folder's layout.
  - nxwright refuses a folder in a format it does not read. Convert a folder in an older format with `nxwright upgrade` ([commands.md](commands.md#upgrade)). A folder in a newer format needs a newer nxwright.
- `name` is the app's name, as nxwright shows it: in VS Code's sections, in a simulation's name and its launch configuration's, and in nxwright's prompts.
  - It is one line of text, not empty, with no spaces at its start or end. Any other character is fine, as in "Thermostat: v2".
  - Without it, the folder's name is used.
  - `nxwright new` writes the name. Extracting into a new folder names the app after the project file.
- `language` is the language of the folder's code: `"nextion"` for strict Nextion syntax, or `"nxlang"` for the nxwright language ([language.md](language.md)).
  - A folder extracted anew starts with `"nextion"`. A folder started with `nxwright new` starts with `"nxlang"`, unless you choose another.
  - Switch to nxlang with `nxwright language`, never by editing this line ([commands.md](commands.md#language)). nxlang uses the usual operator precedence, so the command adds parentheses where your code relies on the unusual Nextion Editor's left-to-right order.
- `screen`, `rotation`, and `encoding` are the device settings the Nextion Editor sets for the project:
  - the screen model;
  - the rotation in degrees: 0, 90, 180, or 270;
  - the character encoding: `ascii`, `iso-8859-1`, `utf-8`, or one of the others the Nextion Editor offers.

  The build needs all three. Change them with `nxwright device`, which also changes what depends on them ([commands.md](commands.md#device)).
- Extracting also writes the other device settings, when they are not the Nextion Editor's defaults. You may add them by hand too:

  | Key | The Nextion Editor's setting | Value |
  | --- | --- | --- |
  | `one_time_update` | "One time update of TFT files". Intelligent and Edge series only. | `true` or `false` (the default) |
  | `memory_file_storage_size` | "Memory file storage size". Intelligent and Edge series only. | bytes, 0 by default |
  | `ignore_library_resources` | "Ignore library resources at compile time" | `true` or `false` (the default) |
  | `ignore_image_resources` | "Ignore image resources at compile time" | `true` or `false` (the default) |
  | `password_hash` | The hash of the project's password | the hash that `nxwright password-hash` prints ([commands.md](commands.md#password-hash)), so that the password itself stays out of the folder |

  A project of a screen model nxwright does not know gets none of the device settings.
- `pictures`, `fonts`, `animations`, `videos`, and `sounds` list the project's resources by name. A folder with none of a kind leaves its list out, as extracting does.
- The order of `pages`, `pictures`, `fonts`, `animations`, `videos`, and `sounds` is their order in the project, and so it sets their IDs. To reorder, reorder these lists.
  - Do this with care. A name follows the change, but a number keeps pointing at whatever now has that ID. Code that uses a number in place of a name will then reach another page or resource: `page 2`, `p0.pic=3`, or the page array `p[2]`.
- To remove a picture, font, animation, video, or sound, use `nxwright remove`, which checks that nothing uses it ([commands.md](commands.md#remove)).

## Page files

A page's `.page.toml` file has a `[page]` table, then one `[[component]]` table per component:

```
[page]
name = "settings"
type = "page"
x = 0
y = 0
w = 800
h = 480

[[component]]
name = "step"
type = "variable"

[[component]]
name = "title"
type = "text"
x = 20
y = 10
w = 300
h = 40
txt = "Settings"
font = "NotoSans24"
pco = "#ffffff"
```

- Each table has `name`, `type`, a readable name such as `"text"` or `"button"`, and `events`, the events the object has, with or without code. Then come its attributes, by their names in the Nextion Editor.
- Only what differs from a newly added component of the same type is written ([Component defaults](#component-defaults)).
  - `x`, `y`, `w`, and `h` are always written for components that have a place on the screen.
  - `events` is left out when it is the type's default.
- The build fills in the rest from the defaults, which also give the component's list of attributes, in order.
- Attributes that can be worked out are left out: `id`, `objname`, `endx`, and `endy`.
- Colours are written as `"#rrggbb"`.
- A 4-byte number is written negative when its top bit is set, as the Nextion Editor's attribute panel shows it: a number's `val` of -42, and a file browser's `val` of -1. Its unsigned spelling, 4294967254 or 4294967295, is read too. `defaults.toml` writes them the same way.
- Picture and font attributes, such as `pic`, `picc`, `bpic`, and `font`, are written as names. A `vid` is too, giving what its component plays: an animation (`gmov`), a video (`video`), or a sound (`audio`).
  - A picture attribute of `65535` means no picture.
  - A number that matches no picture is kept as a number. The build accepts it, and the page preview shows a note.
  - The build refuses a font number that matches no font ([Fonts](build-rules.md#fonts)).

The `[page]` table may also contain:

- which of the Nextion Editor's system pages it is: `system_page = "keyboard"` for the full keyboard, `"keypad"` for the numeric keypad, `"speed-dial"`, or `"chinese-input"`;
- that the page is locked: `locked = true`, and `lock_password_hash`, its lock's password, if any. It is given as `app.toml` gives the project's password: the hash that `nxwright password-hash` prints, never the password itself.

The build writes the rest of the page's header in the Nextion Editor's own form, the folder's encoding included ([format.md](format.md)). Extracting stops at a page whose header is not in one of the forms nxwright knows.

For what the build refuses in page files, such as names, lengths, and values, see [build-rules.md](build-rules.md#page-files).

## Code files

A page's `.nx` file has each event that has code, under a heading, with its code indented by two spaces:

```
on save.up:
  if (sys0 == 1) {
    sys1 = 0
  }
```

### Comments

Comment lines right above a heading are that event's comment. They must start at the start of the line, with no blank line between them and the heading:

```
// Save button: writes the settings to the SD card.
on save.up:
  ...
```

The Nextion Editor keeps comments only inside an event's code. So:

- The build puts the comment first in the event, with each `//` written `// ###`: `// Save button` becomes `// ### Save button`.
- Extracting moves the `// ###` lines an event starts with back above its heading. A `// ###` line further down stays an ordinary comment.
- When the Nextion Editor changed only an event's comment, extracting keeps the event's code as it was in the source folder.
- A comment that is not right above a heading, such as one that sorts the file into sections, has no event to go into. It stays in the source folder only: the built project leaves it out, and extracting into the folder keeps it where it is.
- A comment line that is not indented, in the middle of an event's code, stops the build, since it may have been meant as code. Indent it like the code around it, or move it right above a heading.

### An attribute of the event's own object

An event's code may give an attribute of its own object as `'&name&'`, as the vendor's instruction set documents (section 9). In an event of `n0`, `'&val&'+=10` adds 10 to `n0.val`. For how the Nextion Editor reads it, and what the build checks, see [build-rules.md](build-rules.md#name-an-attribute-of-the-events-own-object).

In nxlang too, the form works in an event's code, but not in a function or a constant ([language.md](language.md#limits)).

### What the build checks

The build checks that your code uses only components and pages that exist, and much more ([build-rules.md](build-rules.md#code)).

## Macros

A project's macros, which `call <name>` runs, are kept in `macros.nx`, beside `program.nx` ([format.md, Macros](format.md#macros)). They are in strict Nextion syntax, whatever the folder's language. A folder without macros has no `macros.nx`.

```
// Turns a 565 colour into red, green, and blue.
macro c565_rgb:
  rv=c565>>11
  gv=c565>>5&63
  bv=c565&31
```

- Each macro is under a heading, `macro <name>:`, with its lines indented by two spaces, as an event's code is.
- Comment lines right above a heading are the macro's comment, kept as an event's comment is.
- A macro's name is letters, digits, underscores, and spaces, starting with a letter or an underscore. Letter case matters.
- A folder in nxlang keeps its macros in strict Nextion syntax too. Its nxlang code can `call` them ([language.md](language.md)).
- Tests, the simulator, and the debugger run macros too ([screen-code.md](screen-code.md)).

For what the build refuses in macros, see [build-rules.md](build-rules.md#macros).

## Comfortable code

The Nextion Editor accepts less than it seems to:

| Form | Accepted by the Nextion Editor |
| --- | --- |
| `sys0=1`, `if(sys0==1)`, `covx sys0,msg.txt,0,0`, `}else if(sys0==2)` | yes |
| indentation with spaces or tabs | yes |
| a comment after code: `sys0=1 // note` | yes |
| spaces after commas in a declaration: `int a=0, b=1`, in `program.s` | yes |
| spaces around `=`, `+`, `+=`, `==`, `&&`, or in a `for` header | no |
| a space between `if` or `while` and `(` | no |
| spaces after the commas between a command's arguments | no |
| spaces between a command's own arguments, as in `printh 00 00 00` | yes, and they matter: each separates a byte |
| `{` on the `if` line | no |
| `}else{`, `} else`, or `else` on its own line | no |
| `}else if (` with a space | no |
| parentheses in arithmetic: `sys0=sys1*(2+3)` | no |

In `.nx` files, nxwright lets you write more freely, even without switching to nxlang. The build then turns your code into the form the Nextion Editor accepts:

| Written | Built as |
| --- | --- |
| `sys0 = sys1 + 2`, `if (a == 1 && b != 2)` | `sys0=sys1+2`, `if(a==1&&b!=2)` |
| `covx sys0, t0.txt, 0, 0`, `vis b0, sys0 + 1` | `covx sys0,t0.txt,0,0`, `vis b0,sys0+1`. Spaces between arguments without a comma stay: `printh 0d 0a`. |
| `if (a) {` ... `} else if (b) {` ... `} else {` ... `}` | braces on their own lines, `}else if(b)` and `}else` joined |
| `else` on its own line after `}` | joined to the `}` |
| blank lines | dropped |

- `@pic(icons/back)` and `@font(NotoSans16)` stand for that picture's or font's ID, outside strings and comments. `@animation(...)`, `@video(...)`, and `@sound(...)` work the same way for animations, videos, and sounds. A name that `app.toml` does not list stops the build.
- Strings, comments, indentation, and `int` declarations are otherwise left as written. Spaces at the end of a line are dropped.
- Code already written in the form the Nextion Editor accepts comes out unchanged.

This is still strict Nextion syntax: comfortable code changes how it is written, not what it can do. Parentheses in arithmetic, operator precedence, functions, and more come with nxlang ([language.md](language.md)).

## Text and its encoding

`.nx` and `.toml` files are UTF-8. The project stores its texts and code in its own character encoding, `app.toml`'s `encoding`.

- Extracting writes the texts as the characters they are, in any of the Nextion Editor's encodings, so you can type text in the project's own script.
- The build stops at a character the encoding cannot store, and gives the file.
- Extracting stops at bytes that are not text in the encoding, or that would not come back as the same bytes, and gives where they are.
- A folder extracted by an older nxwright, from a project in another encoding than `iso-8859-1`, has its texts one character per byte. Extract it again.
- `nxwright device --encoding` changes the encoding, and converts the fonts ([commands.md](commands.md#device)). If you change `encoding` in `app.toml` by hand instead, the next build stores the texts in the new encoding, but the fonts stay as they are.
- Spaces at the end of a code line do not matter: the Nextion Editor's compile drops them, and so does the build.

## Names

A picture's, font's, animation's, video's, or sound's name is one or more parts, separated by `/`. Each part is made of letters, digits, `-`, and `_`.

- Names are unique within their kind, even ignoring letter case.
- A name cannot also be the folder of another name: `a` beside `a/b` is refused.
- No part may be a Windows device name, such as `con` or `nul`.

How resources get their names:

- Extracting names a new font after the name its generator stored in it, such as `NotoSans16`, and anything else with a placeholder: `picture-0012`, `font-03`, `animation-00`, `video-01`, `sound-02`.
- When extracting updates a folder, pictures, fonts, animations, videos, and sounds keep their names by matching their bytes. So a picture keeps its name when it moves.
- A resource edited in the Nextion Editor keeps the name of the old one at the same ID, when no other of its kind matched that old one. nxwright cannot tell an edited picture from a replaced one. So after both editing and reordering in one Nextion Editor session, check the names it gave.
- To rename a resource, change its name in `app.toml`, and rename its file, or an animation's two files.

Only references by name follow a reorder or a removal. An ID written as a number, in an attribute or in code, keeps pointing at whatever now has that ID.

## Animations, videos, and sounds

The source folder keeps each animation, video, and sound in the Nextion Editor's own form. nxwright's commands make each kind, so you do not need the Nextion Editor's tools. Files made with those tools work too.

- An **animation** is two files:
  - `<name>.gmov` has the animation's frames, as pictures. It is the form GmovMaker, the Nextion Editor's animation tool, writes.
  - `<name>.screen.gmov` is the form the screen shows. Its frames are JPEG pictures, made for the screen's rotation.
  - `nxwright animation` makes both files from pictures. Given a `.gmov` file from GmovMaker instead, it keeps that file and makes the `.screen.gmov` file from it ([commands.md](commands.md#animation)). An animation added in the Nextion Editor comes in by extracting.
  - An animation's form made for another rotation is taken too. The Nextion Editor makes it again for the project's rotation as it compiles.
- A **video** is a `.video` file, the form VideoBox, the Nextion Editor's video tool, writes.
  - `nxwright video` makes one from a video file or from pictures ([commands.md](commands.md#video)).
  - The Nextion Editor keeps a video file as it is, so you can also copy a file from VideoBox into `videos/`, and list it in `app.toml`.
  - A video is made for one rotation of the screen. The Nextion Editor refuses to compile a video made for another rotation than the project's, and so does the build. `nxwright check` and the live checks show it as an error on its line of `app.toml`. They read only the start of each video.
  - `nxwright device` makes each video again for a new rotation ([commands.md](commands.md#device)).
- A **sound** is a WAV file in the form the Nextion Editor stores: its samples as they were given, with a chunk of the Nextion Editor's own, `hmic`, which contains a check value of the samples and the sound's name ([format.md, Animations, videos, and sounds](format.md#animations-videos-and-sounds)).
  - `nxwright sound` adds one, from a WAV file or any other sound file ([commands.md](commands.md#sound)).
  - The checks warn of a sound's file that is not in that form ([commands.md](commands.md#warnings)).

## Extracting into an existing folder

Extracting into a folder that already has an `app.toml` updates it:

- Each event, each macro, and `program.nx`, keeps its existing text if that text builds to the same code. So comfortable code and comments survive an edit made in the Nextion Editor.
- Everything else is rewritten.
- The files that the old `app.toml` lists, and that the project no longer has, are deleted, one by one.

What extracting never does:

- It never deletes a folder.
- It never touches a file that the old `app.toml` does not list.
- It refuses any other folder that is not empty.

Comments in `.toml` files are not kept. Extracting stops with an error, before writing anything, at anything a source folder cannot represent, such as a control character in code.

### The round trip

Extracting a project, then building it, gives back the same project: the same pages, code, pictures, fonts, animations, videos, and sounds.

- Spaces at the end of a code line are dropped. The Nextion Editor's compile drops them too.
- Blank lines in the project's code are dropped, with a warning, as the build drops them. The Nextion Editor compiles them to nothing.
- A comment that is not right above a heading stays in the source folder only ([Comments](#comments)).
- The build makes each picture's screen copy again from the picture's file. So a copy may differ slightly from the one the Nextion Editor made.
- A project the Nextion Editor's compile would refuse is the exception, since the build refuses it too. An example is a project with a text whose font the project lacks, which the Nextion Editor saves but does not compile.

## Component defaults

`defaults.toml` lists what a newly added component of each type has, so that page files can leave it out.

- A new source folder gets a copy of nxwright's own, `nxwright/project/component_defaults.toml`. Every extract writes it again.
- The build reads the folder's copy.
- nxwright's own copy comes from a sample project made with the Nextion Editor 3.1.73: one page with one newly added component of each type. `nxwright defaults` writes a defaults file from such a sample ([commands.md](commands.md#defaults)).
- nxwright's tests keep that sample's page, and check that every type on it goes through extract and build unchanged (`tests/fixtures/every-component`).

## The picture cache

The project keeps each picture twice: its file, and a copy in the format the screen draws. The build makes that copy from the file's pixels, which is slow for a project with many pictures. So it keeps each copy it makes in a cache, and a later build takes it from there.

A cached copy is used only while all of these are unchanged: the picture's file, the screen's picture format and rotation, nxwright's own picture code, and the version of Pillow, which reads the file.

- The cache is one file, `pictures.sqlite`, shared by every source folder. It is in `%LOCALAPPDATA%\nxwright` on Windows, and in `$XDG_CACHE_HOME/nxwright` elsewhere, by default `~/.cache/nxwright`.
- When it grows past 1 GB, it removes the least recently used copies.
- `nxwright write` uses it too, for the pictures it adds ([dumps.md](dumps.md)).
- The environment variable `NXWRIGHT_CACHE` gives another folder for the file, or turns the cache off with `off`.
- A cache that cannot be used is a warning, never a failed build: the pictures are made as they would be without it.
