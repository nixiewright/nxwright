# Your project as a source folder

A **source folder** is your Nextion project as plain files: TOML for the pages and their components, `.nx` for their code, and separate files for the pictures, fonts, animations, videos, and sounds. You can edit it in any code editor, and keep it in git if you like. nxwright converts it to and from the project file that the Nextion Editor opens and compiles.

You can start a source folder in two ways.

Start a new project:

```
nxwright new app --screen NX8048P050    # a new source folder, with one blank page
```

Or start from a project you made in the Nextion Editor:

```
nxwright extract thermostat.HMI app     # the project file, into a source folder
```

Either way, you then work in a cycle:

1. Edit the files in `app/`. You can simulate and debug them with [nxwright's VS Code extension](../editors/vscode/README.md).
2. Build the project file:

   ```
   nxwright build app thermostat.HMI       # the source folder, into a project file
   ```

3. Open the project file in the Nextion Editor, and deploy to the physical screen from there.

You can also skip the Nextion Editor, and compile and upload with nxwright ([screens.md](screens.md)).

A build replaces the project file, so make your changes in the source folder. If you had made changes to your HMI file in the Nextion Editor, a backup will be made so that you do not lose your edits.

The rest of this page describes the folder's files. See [commands.md](commands.md) for each command, including [the options of `nxwright new` and what it creates](commands.md#new), and [build-rules.md](build-rules.md) for what the build refuses.

## Layout

| Path | Contents |
| --- | --- |
| `app.toml` | The folder's format, its language, its device settings, then the pages, pictures, fonts, animations, videos, and sounds, in ID order, by name. Any defines come last. |
| `defaults.toml` | What a newly added component of each type has ([Component defaults](#component-defaults)). |
| `program.nx` | The code that runs when the screen starts. |
| `macros.nx` | The project's macros, if it has any ([Macros](#macros)). |
| `pages/<page>.page.toml` | The page and its components, in ID order. The `.page.toml` ending marks a page file, so VS Code opens it in the page preview. |
| `pages/<page>.nx` | The page's event code. |
| `pictures/<name>.png`, or `.jpg`, `.jpeg`, `.bmp`, `.gif` | A picture. `nxwright picture` adds one ([commands.md](commands.md#picture)). |
| `pictures/<name>.svg` | A picture that nxwright draws from an SVG file ([SVG pictures](#svg-pictures)). |
| `pictures/<name>.source.png`, or `.jpg`, `.jpeg`, `.bmp`, `.gif` | The file a picture had before you resized it in the Nextion Editor's picture viewer. Only a resized picture has one. |
| `pictures/<name>.screen` | The picture as the screen draws it, called its screen copy. Only a picture whose file is of a type nxwright does not decode, such as `pictures/logo.tif`, has this file. |
| `fonts/<name>.zi` | A font. `nxwright font` draws one from a typeface file, such as a `.ttf` file, or adds a ready-made font file ([commands.md](commands.md#font)). |
| `animations/<name>.gmov`, `animations/<name>.screen.gmov` | An animation: `.gmov` contains its frames, and `.screen.gmov` is the file the screen plays. `nxwright animation` makes both ([Animations, videos, and sounds](#animations-videos-and-sounds)). |
| `videos/<name>.video` | A video. `nxwright video` makes one. |
| `sounds/<name>.wav` | A sound. `nxwright sound` adds one. |

These files are in the same formats that the Nextion Editor and its tools create, so you can also use what you made with them:

- **A font from the Nextion Editor's font generator:** give it to `nxwright font`, or copy it into `fonts/` and list it in `app.toml`. `nxwright font` also turns a font stored for another rotation to the folder's rotation, or to upright on the F series.
- **A video from VideoBox, the Nextion Editor's video tool:** copy it into `videos/`, and list it in `app.toml`.
- **A sound:** give the original sound file to `nxwright sound`.
- **An animation from GmovMaker, the Nextion Editor's animation tool:** give its `.gmov` file to `nxwright animation`, which keeps that file and makes the `.screen.gmov` file from it.

Extracting brings in everything a project already has, animations included.

About picture files:

- A picture's file is kept as it is, with the suffix the project stores for it.
- Each picture has one file. nxwright refuses two files for the same picture name, such as `pictures/logo.png` and `pictures/logo.jpg`, because it cannot tell which one to use.
- The suffix must be in lower case. nxwright finds a camera's `IMG_0001.JPG` only on Windows, so rename it `IMG_0001.jpg`.
- A `/` in a name makes a subfolder: `pictures/icons/back.png`.
- When you resize a picture in the Nextion Editor's picture viewer, the Nextion Editor keeps the original file for "Restore to source size". Extracting writes that file beside the picture's file, as its source file, such as `pictures/logo.source.png`, and the build puts it back in the project. A picture has at most one source file.
- When you replace a picture's file, delete its source file too. Otherwise the Nextion Editor's "Restore to source size" brings back the old picture.
- A project might store a picture in a file of a type other than PNG, JPEG, BMP, or GIF, such as TIFF, although no version of the Nextion Editor is known to do that. Extracting then writes the file as it is, with the picture's screen copy beside it, such as `pictures/logo.screen`.
  - nxwright cannot make a screen copy from such a file, so the build writes the `.screen` file as it is, and warns you. If you edit the picture's file, the screen does not show the change.
  - Without the `.screen` file, the build stops.
  - To change the picture, save it as a PNG, JPEG, BMP, or GIF file, and delete the old file and its `.screen` file.

### SVG pictures

A picture can be an SVG file, such as `pictures/background.svg`. nxwright draws it each time it builds, checks, previews, or simulates, and the project file it builds stores the drawing as a PNG picture (with caching).

```
<?xml-stylesheet href="css/theme.css" type="text/css"?>
<svg xmlns="http://www.w3.org/2000/svg" width="800" height="480">
  <rect class="page" width="800" height="480"/>
  <use href="shapes.svg#frame" x="16" y="16"/> <!-- optional: include from another svg -->
  <text x="40" y="60" font-family="sans-serif" font-size="24">Living room</text>
</svg>
```

- The `<svg>` element gives the picture's size in whole pixels, such as `width="800" height="480"`.
- A picture can use other files of the source folder, with a path relative to the file that contains it:
  - **A style sheet**, linked by `<?xml-stylesheet?>` before the `<svg>` element.
  - **Shapes of another SVG file**, with `<use href="shapes.svg#frame"/>`. A shape brings along what it refers to in its own file, such as a gradient, but not that file's style.
  - **An image**, with `<image href="texture.png"/>`.
- A picture can also use another picture's file. For example, a page's pressed picture can use the drawing of its normal one and tweak it.
- `nxwright rename` and `nxwright remove` do not change paths in <use> statements. `nxwright check` reports each path that points at missing files.
- Texts use Noto Sans by default, which also stands in for the generic families, such as `sans-serif`. To use another font, put its file in the folder and name it in a style sheet: `@font-face { font-family: "Inter"; src: url(Inter.ttf); }`. The family must be the one inside the font file. Noto Sans has no bold, so bold text also needs a font file of its own.
- nxwright never uses the fonts installed on your computer, so a picture comes out the same on every computer. If a text's font family has no font file, nxwright refuses the picture instead of leaving the text out. It also refuses the `font` shorthand, so give a text's font with `font-family`.

An SVG picture can take its colours and texts from `app.toml`'s defines ([app.toml](#apptoml)), so that a build with `--define`, or a simulation, can change them:

```
<style>
  :root { --ACCENT: #ff8a45; }
  .title { fill: var(--ACCENT); }
</style>
<text class="title" data-nxwright-text="TITLE">Living room</text>
```

- To use a define's value in a style, write a CSS variable named after the define, such as `var(--ACCENT)`. This works in a style sheet, a `style` attribute, or another attribute such as `fill`. Every `var()` must name a define. A define used this way cannot contain `;`, `{`, `}`, `/*`, a backslash, or a line break, because these would change the CSS around it.
- A `<text>` or `<tspan>` with `data-nxwright-text="TITLE"` shows the value of `TITLE` in place of its own text. That text appears only in other SVG viewers, so it can be a sample, such as the longest text you expect.
- Other SVG viewers, such as a browser, use the values the file declares, as in `:root { --ACCENT: #ff8a45; }`, or a fallback, as in `var(--ACCENT, #ff8a45)`. nxwright always draws the define's value, and `nxwright check` warns when a declared value differs from the define's default.

## app.toml

```
format = 1
name = "Living room"
language = "nextion_do_not_change_manually"  # use `nxwright language <source-folder> nxlang` to change
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

- `format` is the version of the source folder's layout.
  - nxwright refuses a folder in a format it does not read. Convert a folder in an older format with `nxwright upgrade` ([commands.md](commands.md#upgrade)). A folder in a newer format needs a newer nxwright.
- `name` is the app's name. nxwright shows it in its VS Code sections and its prompts, and uses it to name simulations and their launch configurations.
  - The name must be one line of text, not empty, with no spaces at its start or end. Any other character is fine, as in "Thermostat: v2".
  - If `name` is missing, nxwright uses the folder's name.
  - `nxwright new` writes the name. Extracting names the app after the project file.
- `language` is the language of the folder's code: `"nextion_do_not_change_manually"` for strict Nextion syntax, or `"nxlang_do_not_change_manually"` for the nxwright language ([language.md](language.md)).
  - A newly extracted folder starts in strict Nextion syntax. A folder started with `nxwright new` starts in nxlang, unless you choose another language.
  - Switch to nxlang with `nxwright language`, never by editing the `language` line ([commands.md](commands.md#language)). nxlang uses the usual operator precedence, so the command adds parentheses where your code relies on the Nextion Editor's unusual left-to-right order.
  - Older versions of nxwright wrote just `"nextion"` or `"nxlang"`. nxwright still reads these values, and writes the longer one the next time it changes `app.toml`. An older nxwright cannot read a folder that has the longer value.
- `screen`, `rotation`, and `encoding` are the device settings the Nextion Editor sets for the project:
  - the screen model;
  - the rotation in degrees: 0, 90, 180, or 270;
  - the character encoding: `ascii`, `iso-8859-1`, `utf-8`, or one of the others the Nextion Editor offers. If nxwright does not know a project's encoding, `encoding` is the encoding's number instead, such as `encoding = 37`. The project's texts are then read one character per byte, so they may show as the wrong characters, and the build writes their bytes back as they are.

  The build needs all three. Change them with `nxwright device`, which also changes what depends on them ([commands.md](commands.md#device)).

  Extracting writes no device settings in two cases, and prompts you to choose whether to go on ([commands.md](commands.md#extract)):

  - If nxwright does not know the project's screen model, the build refuses the folder until nxwright knows the model. The project's texts and code are still read in its own character encoding.
  - If the project stores its settings in a header of a size nxwright has not seen, its texts are read as `iso-8859-1`.
- Extracting also writes the other device settings, when they are not the Nextion Editor's defaults. You may add them by hand too:

  | Key | The Nextion Editor's setting | Value |
  | --- | --- | --- |
  | `one_time_update` | "One time update of TFT files". Intelligent and Edge series only. | `true` or `false` (the default) |
  | `memory_file_storage_size` | "Memory file storage size". Intelligent and Edge series only. | bytes, 0 by default |
  | `ignore_library_resources` | "Ignore library resources at compile time" | `true` or `false` (the default) |
  | `ignore_image_resources` | "Ignore image resources at compile time" | `true` or `false` (the default) |
  | `password_hash` | The hash of the project's password | the hash that `nxwright password-hash` prints ([commands.md](commands.md#password-hash)), so that the password itself stays out of the folder |
- `pages` lists the project's pages by name. A page's name can use any Latin-1 character except a double quote or a control character, such as `"p 0"`, `"a:b"`, or `"café"`. In the names of a page's files, `%` and the characters Windows refuses in a file name, `\ / : * ? " < > |`, are percent-encoded: the page `a:b` has `pages/a%3Ab.page.toml`. To rename a page, its files, and each use of its name, use [`nxwright rename`](commands.md#rename). To delete one, use [`nxwright remove`](commands.md#a-page).
- `pictures`, `fonts`, `animations`, `videos`, and `sounds` list the project's resources by name. A folder with no resources of a kind can leave that list out.
- The order of `pages`, `pictures`, `fonts`, `animations`, `videos`, and `sounds` is their order in the project, and so it sets their IDs. To reorder, reorder these lists.
  - Do this with care. A name follows the change, but a number keeps pointing at whatever now has that ID. Code that uses a number in place of a name will then reach another page or resource: `page 2`, `p0.pic=3`, or the page array `p[2]`.
- To remove a picture, font, animation, video, or sound, use [`nxwright remove`](commands.md#remove).
- An optional `[defines]` table, at the end of the file, declares defines: named values that a build can change without editing the folder.

  ```
  [defines]
  LIMIT = 30
  TITLE = "Living room"
  ```

  - A define's name is made of letters, digits, and `_`, and does not start with a digit. The value you give it is its default, and must be a whole number or a text.
  - nxlang code on every page can use each define as a constant ([language.md](language.md#constants)).
  - An SVG picture can use a define's value as a colour or another style value, and as a text ([SVG pictures](#svg-pictures)). A colour written as `"#rrggbb"` suits both the pictures and the components, so one define can set a theme's colour everywhere.
  - A key of `app.toml` or of a page file can take a define's value. Write the define's name between two `%` signs, as the key's whole value: `rotation = "%ROTATION%"`, or `bco = "%BCOLOR%"`. The build checks the define's value the same way as a value written in the key.
    - `format` and `language` in `app.toml`, and `name` and `type` in a page file, cannot take a define's value.
    - If the folder has no defines, a text such as `"%BCOLOR%"` stays a plain text.
    - A command or an edit that writes a new value in such a key replaces the define's name with that value, as when `nxwright device` changes the rotation, or when you move a component in VS Code's page preview. The Attributes section cannot change a key that takes a define's value.
    - A define only puts its value in place: the build does not resize the pages or make the videos again. So a define can switch `rotation` between 0 and 180 degrees, or between 90 and 270, in a folder without videos. For a quarter turn, run `nxwright device` on a copy of the folder ([A new rotation](commands.md#a-new-rotation)).
  - `nxwright build` and `nxwright compile` can change a define's value for one build, as in `--define LIMIT=40` ([commands.md](commands.md#build)). A simulation's launch configuration can too, with `defines` ([simulator.md](simulator.md#other-values-for-the-defines)). Everything else, such as the page preview and the tests, uses the defaults.
  - An older nxwright cannot read a folder that has this table.

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

- Each table has a `name`, a `type` with a readable value such as `"text"` or `"button"`, and `events`, which lists the object's events, with or without code. The object's attributes follow, under their names in the Nextion Editor.
  - A component's `name` can be any name the Nextion Editor accepts, such as `b)0` or `b 0`, except one with a double quote or a control character. Code cannot refer to a component whose name has anything other than letters, digits, and `_`, but the component's events still run.
- Only what differs from a newly added component of the same type is written ([Component defaults](#component-defaults)).
  - `x`, `y`, `w`, and `h` are always written for components that have a place on the screen.
  - `events` is left out when it is the type's default.
- The build fills in the rest from the defaults, which also give the component's list of attributes, in order.
  - A component whose type has `drag` can also have `disup`, set to 0 or 1. The Nextion Editor has this attribute in versions 1.60.1 and 1.63.3, but not in 1.68.2, whose compile ignores it. If a table has a `disup`, the build writes it right after `drag`, where the older versions read it.
- Attributes that can be worked out are left out: `id`, `objname`, `endx`, and `endy`.
- Colours are written as `"#rrggbb"`.
- A 4-byte number with its top bit set is written as a negative number in page files and in `defaults.toml`, the way the Nextion Editor's Attribute panel shows it, such as a number component's `val` of -42, or a file browser's `val` of -1. nxwright also reads the unsigned form, 4294967254 or 4294967295.
- Picture and font attributes, such as `pic`, `picc`, `bpic`, and `font`, are written as names. So is a `vid`, which is the animation of a `gmov` component, the video of a `video` component, or the sound of an `audio` component.
  - A picture attribute of `65535` means no picture.
  - A number that matches no picture is kept as a number. The build accepts it, and the page preview shows a note.
  - The build refuses a font number that matches no font ([Fonts](build-rules.md#fonts)).
- An attribute that nxwright does not know, or that is stored at a width nxwright does not expect, is kept as its stored bytes, in hexadecimal: `newattr = { bytes = "01" }`. A newer Nextion Editor may write such attributes. Extracting writes them in this form, in a table marked `defaults = false`, and the build writes the bytes back as they are. The Attributes section of nxwright's VS Code extension shows such an attribute, but cannot change it.
  - For a picture or font attribute, the bytes contain the resource's ID, so they stay right only while the resources keep their order.
  - An older nxwright stops at such a value, and its error gives the attribute's name.
- A text whose bytes are not text in the project's encoding is also kept as its bytes in hexadecimal: `txt = { bytes = "636166e9" }`.
- An attribute named like a key of the page file, such as `events`, is kept under `kept_attributes`, as its bytes in hexadecimal: `kept_attributes = { events = { bytes = "05" } }`. If an object has two such attributes with others between them, the build writes the two together, at the first one's place.
- An event whose code a `.nx` file cannot contain, such as a line with a control character, or one not valid in the project's encoding, is kept under `kept_events`, as its lines in hexadecimal: `kept_events = { load = { lines = ["610d62"] } }`. Its code has no heading in the `.nx` file, so it cannot be edited there, and the build writes its lines back as they are.

The `[page]` table may also contain:

- `system_page`, if the page is one of the Nextion Editor's system pages: `"keyboard"` for the full keyboard, `"keypad"` for the numeric keypad, `"speed-dial"`, or `"chinese-input"`.
- `locked = true`, if the page is locked.
- `lock_password_hash`, if the lock has a password. This is the hash that `nxwright password-hash` prints, so the password itself stays out of the folder.

When a page header has a value that nxwright has not seen, the page file keeps it under its own key, so that the build writes it back as it was. Extracting warns about each one.

- `system_page = 5`: a system page value nxwright does not know, as a number.
- `locked = 2`: a lock value other than locked or unlocked, as a number.
- `header_21 = { bytes = "4f22" }`: two header bytes that differ from `4f 21`, the value in every page seen so far.

The build writes the rest of the page's header in the Nextion Editor's current form, including the folder's encoding ([format.md](format.md)). If a page's header is in a form nxwright has not seen, extracting warns you, and the build still writes the current form.

For what the build refuses in page files, such as names, lengths, and values, see [build-rules.md](build-rules.md#page-files).

## Code files

A page's `.nx` file has a heading for each event with code, and the code is indented by two spaces:

```
on save.up:
  if (sys0 == 1) {
    sys1 = 0
  }
```

A heading puts a component's name in double quotes when the name is not made of letters, digits, and `_` alone: `on "b 0".up:`. Any name may be quoted, so `on "save".up:` is the same heading as `on save.up:`.

### Comments

Comment lines right above a heading are that event's comment. They must not be indented, and there must be no blank line between them and the heading:

```
// Save button: writes the settings to the SD card.
on save.up:
  ...
```

The Nextion Editor keeps comments only inside an event's code. So:

- The build puts the comment first in the event, with each `//` written `// ###`: `// Save button` becomes `// ### Save button`.
- Extracting moves the `// ###` lines an event starts with back above its heading. A `// ###` line further down stays an ordinary comment.
- A comment that is not right above a heading, such as one that sorts the file into sections, has no event to go into, so it stays in the source folder only.
- A comment line that is not indented, in the middle of an event's code, stops the build, since it may have been meant as code. Indent it like the code around it, or move it right above a heading.

### An attribute of the event's own object

An event's code can refer to an attribute of its own object as `'&name&'`, as the vendor's instruction set documents (section 9). In an event of `n0`, `'&val&'+=10` adds 10 to `n0.val`. For how the Nextion Editor reads it, and what the build checks, see [build-rules.md](build-rules.md#name-an-attribute-of-the-events-own-object).

In nxlang, `'&name&'` works in an event's code, but not in a function or a constant ([language.md](language.md#limits)).

### What the build checks

The build checks that your code uses only components and pages that exist, and much more ([build-rules.md](build-rules.md#code)).

## Macros

A project's macros are kept in `macros.nx`, beside `program.nx`, and code runs one with `call <name>` ([format.md, Macros](format.md#macros)). They are in strict Nextion syntax, whatever the folder's language.

```
// Turns a 565 colour into red, green, and blue.
macro c565_rgb:
  rv=c565>>11
  gv=c565>>5&63
  bv=c565&31
```

- Each macro is under a heading, `macro <name>:`, with its lines indented by two spaces.
- Comment lines right above a heading are the macro's comment, and follow the same rules as an event's comment ([Comments](#comments)).
- A macro's name is letters, digits, underscores, and spaces, starting with a letter or an underscore. Letter case matters.
- Code in nxlang can `call` a macro ([language.md](language.md)).
- Tests, the simulator, and the debugger run macros too ([screen-code.md](screen-code.md)).

For what the build refuses in macros, see [build-rules.md](build-rules.md#macros).

## Comfortable code

**Comfortable code** is code written more freely than the Nextion Editor accepts. You can use it in any `.nx` file, even without switching to nxlang, and the build turns it into the form the Nextion Editor accepts:

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

Comfortable code is still strict Nextion syntax, so it cannot do anything more. Parentheses in arithmetic, operator precedence, functions, and more come with nxlang ([language.md](language.md)).

The Nextion Editor itself accepts less than it seems to:

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

## Text and its encoding

`.nx` and `.toml` files are UTF-8. The project stores its texts and code in its own character encoding, `app.toml`'s `encoding`.

- Extracting writes the texts as the characters they are, in any of the Nextion Editor's encodings, so you can type text in the project's own script. It stops at bytes that are not text in the encoding, or that would not come back as the same bytes.
- The build stops at a character the encoding cannot store.
- A folder that an older nxwright extracted from a project in an encoding other than `iso-8859-1` has its texts one character per byte. Extract the project again, into a new folder.
- `nxwright device --encoding` changes the encoding, and converts the fonts ([commands.md](commands.md#device)). If you change `encoding` in `app.toml` by hand instead, the next build stores the texts in the new encoding, but the fonts stay as they are.

## Names

The name of a picture, font, animation, video, or sound has one or more parts, separated by `/`. Each part is made of letters, digits, `-`, and `_`.

- Names are unique within their kind, even ignoring letter case.
- A name cannot also be the folder of another name: `a` beside `a/b` is refused.
- No part may be a Windows device name, such as `con` or `nul`.

How resources get their names:

- Extracting names a font after the name its generator stored in it, such as `NotoSans16`. Anything else gets a placeholder: `picture-0012`, `font-03`, `animation-00`, `video-01`, `sound-02`.
- To rename a resource, and each use of its name, use [`nxwright rename`](commands.md#rename).

Only references by name follow a reorder or a removal. An ID written as a number, in an attribute or in code, keeps pointing at whatever now has that ID. So extracted code uses a picture's or font's name in place of its ID where the number can only mean that resource, as in `t0.font=@font(NotoSans16)` or `pic 0,0,@pic(picture-0012)`. Any other number stays as it is, such as the `9` in `sys0=9`.

## Animations, videos, and sounds

The source folder keeps each animation, video, and sound in the Nextion Editor's own format. nxwright's commands make each kind, so you do not need the Nextion Editor's tools. Files made with those tools work too.

- An **animation** is two files:
  - `<name>.gmov` contains the animation's frames as pictures, in the format of GmovMaker, the Nextion Editor's animation tool.
  - `<name>.screen.gmov` is the file the screen plays. Its frames are JPEG pictures, made for the screen's rotation.
  - `nxwright animation` makes both files from pictures. Given a `.gmov` file from GmovMaker instead, it keeps that file and makes the `.screen.gmov` file from it ([commands.md](commands.md#animation)).
  - A `.screen.gmov` file made for another rotation is accepted too, and the Nextion Editor remakes it for the project's rotation when it compiles.
- A **video** is a `.video` file, in the format of VideoBox, the Nextion Editor's video tool.
  - `nxwright video` makes one from a video file or from pictures ([commands.md](commands.md#video)).
  - A video is made for one rotation of the screen. The build refuses a video made for a rotation other than the project's.
  - `nxwright device` makes each video again for a new rotation ([commands.md](commands.md#device)).
- A **sound** is a WAV file with an extra chunk that the Nextion Editor adds ([format.md, Animations, videos, and sounds](format.md#animations-videos-and-sounds)).
  - `nxwright sound` adds one, from a WAV file or any other sound file ([commands.md](commands.md#sound)).
  - The checks warn about a sound file whose chunk is missing or does not match its samples ([commands.md](commands.md#warnings)).
  - A screen plays only 16-bit sounds of 22050 samples a second, mono or stereo. The Nextion Editor converts a sound at any other rate when it compiles, but leaves one at 22050 as it is.
  - The build refuses a sound at 22050 samples a second that is not 16-bit, or that has more than two channels.
  - `nxwright sound` makes a sound's samples 16-bit, and `--mono` makes it mono ([commands.md](commands.md#sound)).

## What extracting keeps

Extracting keeps everything a build needs, so a folder extracted from a project builds the same pages, code, pictures, fonts, animations, videos, and sounds. These are the exceptions:

- The build locks the pages, unless you give `--no-lock` ([build](commands.md#build)).
- Blank lines, and spaces at the end of a code line, are dropped, with a warning for the blank lines.
- The build makes each picture's screen copy again from the picture's file. So a copy may differ slightly from the one the Nextion Editor made in the details of its encoding.
- A project that the Nextion Editor saved but would not compile, such as one with a text whose font the project lacks, extracts, but its folder does not build.

A project built from nxlang is extracted in strict Nextion syntax, with the code the build wrote, not the nxlang you wrote ([nxlang-compiled.md](nxlang-compiled.md)).

## Component defaults

`defaults.toml` lists what a newly added component of each type has, so that page files can leave it out.

- A new source folder gets a copy of nxwright's own, `nxwright/project/component_defaults.toml`.
- nxwright's own copy comes from a sample project made with the Nextion Editor 1.68.2: one page with one newly added component of each type. `nxwright defaults` writes a defaults file from such a sample ([commands.md](commands.md#defaults)).
- The build reads the folder's copy, and fails if a value is outside its attribute's range or choices, such as a text's `vscope` of 2.

## The picture cache

The project keeps each picture twice: its file, and a copy in the format the screen draws. The build makes that copy from the file's pixels, which is slow for a project with many pictures. So it keeps each copy it makes in a cache, and a later build takes it from there.

A cached copy is used only while all of these are unchanged: the picture's file, the screen's picture format and rotation, nxwright's own picture code, and the version of Pillow, which reads the file.

- The cache is one file, `pictures.sqlite`, shared by every source folder. It is in `%LOCALAPPDATA%\nxwright` on Windows, and in `$XDG_CACHE_HOME/nxwright` elsewhere, by default `~/.cache/nxwright`.
- When the cache grows past 1 GB, nxwright removes the least recently used copies.
- `nxwright write` also uses the cache, for the pictures it adds ([dumps.md](dumps.md)).
- To move the file, set the environment variable `NXWRIGHT_CACHE` to another folder, or set it to `off` to turn the cache off.
- If nxwright cannot use the cache, it warns you and makes the pictures without it.
