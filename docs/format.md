# The Nextion Editor's project file

What is known about the project file (`.HMI`) of the Nextion Editor, the vendor's Windows program for designing Nextion screens. The vendor does not document it. The facts here were checked against Nextion Editor 3.1.73.

The byte-by-byte layouts live in the modules that read and write each part, so that the code and its description cannot drift apart. This page explains how the parts fit together.

The [community format notes by vladtsvetkov880-hub](https://github.com/vladtsvetkov880-hub/nextion-hmi-format) (MIT license) were the starting point for the container and the checksum. nxwright does not copy or call that project's code.

## The container

A project file is a container of named **blocks**. A **directory** at the start of the file lists each block's name, its position in the file, its size, and flags. `nxwright/project/container.py` describes the layout.

- **Saving appends.** When the Nextion Editor saves, it does not overwrite a changed block. It writes the new copy at the end of the file, adds an entry for it at the end of the directory, and marks the old entry **stale**: bit 0 of its flags, and the first byte of its name set to zero. Only the **live** blocks, the ones not stale, make up the project. A file that has been saved often is therefore much bigger than its content.
- **Order matters.** The directory is kept in the order of the blocks in the file, and the last block ends at the end of the file. The Nextion Editor relies on that order to find free space. If a file's directory is out of order, the Nextion Editor still opens the file, but its next save may write over one of the blocks.
- **A checksum follows the directory.** An exact copy of the directory and its checksum sits further into the file. The Nextion Editor writes the copy.
- **The reserved area.** The space between the directory and the first block is reserved, mostly zeros. Besides the directory's copy, at 0x80000, a new project contains four `ff` bytes at 0x380000, and the text `ver21234` at 0x6ffff8. Its blocks start at 0x700000. That layout is the same for every screen model. `nxwright/project/new_project.py` writes it.

## Blocks

| Block | What it is | Module |
| --- | --- | --- |
| `main.HMI` | The **manifest**: the list of the project's pages, pictures, fonts, animations, videos, and sounds. | `resources.py` |
| `Program.s` | The program code that runs once at power-on: global `int` declarations, settings such as the baud rate, and the first page. Plain text with Windows line endings, no header, no checksum. | |
| `comcode.sn` | The project's **macros**, which `call <name>` runs, when it has any (see Macros, below). Plain text in UTF-8, whatever the project's encoding. The manifest does not list it. | `macros_source.py` |
| `N.pa` | A page and its components. | `page_block.py`, `page_text.py` |
| `N.is` | A picture's file, as the Nextion Editor shows it. | `resources.py` |
| `N.i` | The same picture as compiled into the screen: its **screen copy**. | `screen_copy.py` |
| `N.zi` | A font, as the Nextion Editor's font generator made it. | `zi_font.py` |
| `N.gmovs` | An animation, as GmovMaker, the Nextion Editor's animation tool, wrote it. | `resources.py` |
| `N.gmov` | The same animation in the form the screen shows, which the Nextion Editor made of it. | `resources.py` |
| `N.v` | A video, as VideoBox, the Nextion Editor's video tool, wrote it. | `resources.py` |
| `N.wav` | A sound, as the Nextion Editor's Audio panel wrote it. | `resources.py` |

### IDs

Code and attributes refer to pages, pictures, fonts, animations, videos, and sounds by number: `page 2`, `pic=5`, `font=3`, `vid=1`. That number, the **ID**, is the resource's position among the manifest's entries of its kind.

- A `vid` is an animation's ID in an animation component (gmov), a video's in a video, and a sound's in an audio component.
- The blocks of these resources are named with a number, as the table above shows: `0.pa`, `1.pa`, and so on for pages. In a new project, that number is the resource's ID. In projects edited over time, the numbers seen no longer matched the IDs: in one, page 0 was stored in block `23.pa`. The ID always comes from the manifest, which lists the blocks of each kind in ID order.

### Pages

A page block is a header, a table of objects, then the objects. Object 0 is the page itself. The others are its **components**: text fields, buttons, variables, timers, and so on. An object is a run of **records**:

- a record of 16 bytes or more is an **attribute**: a name, then a value, such as `w` (the width) or `txt`;
- a shorter one is a **marker**, such as `att-39`, which gives the component's class, or `codesdown-3`, which says the next three records are the lines of the component's Touch Press event.

The **events** contain the screen's own script, line by line: `load` (Preinitialize), `loadend` (Postinitialize), `down` (Touch Press), `up` (Touch Release), `unload` (Page Exit), `timer` (a timer's tick), and `slide` (a slider moving). An event can exist with no code; it is kept as it is.

Some attributes have a different width on different component types: `val` takes 4 bytes on some, and 1 or 2 on others. `page_text.py` lists the widths found.

The page header:

- **Byte 23 marks the Nextion Editor's system pages**, the stock keyboards it adds for a component's `key`. Its value is the same number as the `key`: 1 for the full qwerty keyboard (keybdA), 2 for the numeric keyboard (keybdB), 3 for the speed dial (keybdC), 4 for Chinese input (keybdAP), and 0 for any other page. The Nextion Editor shows system pages with their own icon, and can reset one to its stock version. A project may change them.
- **Byte 20 is 1 while the page is locked.** The Nextion Editor will not let a locked page be changed until it is unlocked, and it adds its keyboards locked.
  - A lock may have a password. Bytes 16 to 19 contain its hash, the same as the project password's (`password_hash` in `project/device_settings.py`), and are zero without one.
  - Bytes 21 and 22 are `4f 21` on every page.
- **Bytes 40 to 43 repeat the project's character encoding.** Whenever the Nextion Editor writes a page, it starts them with `01 44 02` and the encoding's number (3 for iso-8859-1).
  - A page the Nextion Editor has not written since it was updated keeps an older form, `01 43 01 00`, with no encoding.
  - Changing the encoding rewrites every page.
  - The build writes the newer form into every page. A source folder keeps none of these header bytes but the system page mark and the lock (`source-folder.md`). `project/page_header.py` gives the forms.

### Page files

The Nextion Editor can export one page to a `.page` file, and import one into any project. A page file is a page block with three differences:

- **It carries the fonts the page uses**, as extra entries in its object table, in the order the page first uses them. Each `font` attribute is renumbered to its font's place in that list. Importing adds any font the target project lacks.
- **It carries no pictures.** Picture attributes keep their IDs, so the target project needs the same pictures with the same IDs.
- **Its header is written anew** in bytes 40 to 55, in the newer form, whatever form the page itself had, with the project's encoding.

### Pictures

Each picture is two blocks with the same number: its file (`N.is`), and its screen copy (`N.i`).

- **The file is kept as it is given**: a PNG, a JPEG, a BMP, or a GIF, whatever its suffix says. The Picture panel offers `.png`, `.jpg`, and `.bmp` files, and takes a `.jpeg` or `.gif` file typed in.
- **The record's header ends with the suffix the file had**, in lower case: `png`, `jpg`, `jpeg`. The header's size grows with it.
- **The two blocks must agree.** The Nextion Editor checks them, and reports a damaged resource when they do not.
- **The screen copy is made from the file's pixels**, without applying an orientation a JPEG's EXIF data gives.
- **A PNG of 16 bits a channel, keyed on one colour by its `tRNS` chunk**, has that colour transparent in the Nextion Editor's copy, matched on all 16 bits. A colour sharing only the key's high bytes stays opaque.
  - A grey PNG of this kind works the same way in nxwright.
  - A colour one is refused. Pillow, the library nxwright reads pictures with, gives each channel at only 8 bits. At 8 bits, the key cannot be told apart from a colour that shares only its high bytes.
  - To use such a picture, save it with 8 bits a channel, or with an alpha channel.

The screen copy's format depends on the **screen model's series**, and its pixel order on the **rotation**, both chosen in the Nextion Editor's device settings. The Nextion Editor offers 27 screen models, each at 0, 90, 180, or 270 degrees:

| Format | Series | Pixels |
| --- | --- | --- |
| 0, raw | T (Basic) and K (Enhanced) | one 16-bit colour per pixel, transparency blended against white |
| 3, raw with a second header | F (Discovery) | as raw, after a 20-byte second header; a compressed variant exists but is not decoded |
| 4, compressed | P (Intelligent) and E (Edge) | runs of colours, then the transparency |

The rotation decides the order the pixels are stored in, and a marker in the screen copy's first byte records it. `screen_copy.py` describes all three formats and the four orders.

Colours are stored as **RGB565**: 5 bits of red, 6 of green, 5 of blue.

- Opaque pixels are the picture's colours, with their lowest bits dropped.
- Partly transparent pixels are often one step off in a channel. No exact rule is known, and the Nextion Editor accepts either.
- Saving the same project twice can give different screen copies for unchanged pictures. So the Nextion Editor does not need a screen copy to match its own encoding byte for byte.

### The device settings

The header of the manifest contains the project's device settings: the screen model (by a device ID), its series, the rotation, the character encoding, and the other options of the Nextion Editor's device settings page. `nxwright/project/device_settings.py` lists each one's bytes, and `nxwright/project/screen_models.py` lists the 27 models with their device IDs.

### Fonts

A font block is a `.zi` file, as the Nextion Editor's font generator writes it, turned to the project's rotation. It contains the font's height, its characters' widths, and their pixels. The generator also stores the name it was given, such as `NotoSans16`.

The [community notes by hagronnestad](https://github.com/hagronnestad/nextion-font-editor/tree/master/Docs) describe versions 3, 5, and 6 of the format. They were the starting point for the glyph codes, and they are the only source for what is marked "(published notes)" below. nxwright does not copy that project's code.

Every font the Nextion Editor made in the files sampled is **version 6**. A version 6 font is four parts, back to back:

1. a 44-byte header;
2. the **description**: the font's name, then its encoding's name, with nothing between them, such as `Sans16iso-8859-1`. The name is in utf-8, whatever the font's encoding;
3. the **character table**: 10 bytes per character, in increasing order of character code;
4. each character's **glyph**: its pixels, compressed.

Zero bytes follow the table, up to the next multiple of 8 bytes from its start: two after a table of 95 characters, none after one of 224. A reader needs neither fact, since the table gives each glyph's place.

The generator's **Range** choice sets which characters a font contains:

- "ASCII Character": U+0020 to U+007E;
- "All characters": every character of the encoding;
- "Specified character": those typed in its box, to which it adds the space, sorted by code.

Byte 5 of the header seems to record the choice: 0, 1, and 2, in that order, as the published notes' "2 for a subset" has it. It decides how the screen finds a character's entry:

- **With byte 5 at 1**, as in a font of every character of its encoding, the font must not skip any character. If one is missing, the characters after it show as the wrong ones. For example, in a font without the capitals A to Z, "Hello abc XYZ" shows as "b", three missing-character boxes, " {|} rst".
- **With byte 5 at 2**, the table contains the chosen characters alone, each entry giving its code, and the screen searches it by code. Bytes 10 and 11 still give the encoding's first and last character, such as `20` and `ff`.

**Missing characters.** When a text contains a character its font does not have, the screen draws the font's first character in its place.

- Most fonts start with the space, so a missing character usually shows as a blank as wide as a space.
- A font can start before the space. In a utf-8 font of U+0001, the space, and `A`, a missing character shows as U+0001's glyph, which is a missing-character box.
- A character whose code comes before the font's first character is drawn the same way. For example, a font of every iso-8859-1 character starts at the space, so byte `01` shows as a space.

`zi_font.py`'s docstring gives the byte layout of the header, the character table, and the glyph codes. Facts that come only from the published notes are marked as such. In short:

- The header gives the **orientation** (byte 3), the **encoding**, numbered as a project's encoding is (`ENCODINGS` in `device_settings.py`), the **height** in pixels, the version, the number of characters, and whether the font is **smoothed** (byte 30): 1 when the generator's "Anti-aliasing of fonts" was ticked, 0 when not.
- The character table gives, for each character:
  - its code. In a one-byte encoding, that is its byte: `°` is `b0` in iso-8859-1;
  - its **advance**: how far the pen moves right after it;
  - its **left overhang**: how many columns of its glyph lie left of the pen;
  - its **right overhang**: how many lie past the advance;
  - its glyph's place.

Most characters have no overhang. In the demo's `Sans100`, the hook of `J` reaches 6 pixels under the character before it, and the top of `f` 3 pixels over the character after it.

#### Glyphs

A glyph is a rectangle of pixels. It is as wide as the advance plus both overhangs, and as tall as the font. Its left edge lies the left overhang before the pen, and its top is the top of the line of text.

- Each pixel has a **coverage**, from 0 (empty) to 7 (full): how much of the text colour it takes.
- The pixels are listed row by row from the top, each row from left to right, as one stream: a run of pixels may go on into the next row.
- The glyph's first byte says how the rest is coded: 1 for two levels, where every pixel is empty or full, and 3 for eight levels. In the fonts seen, a glyph starts with 1 exactly when it has no partly covered pixel, such as the space.
- Each later byte is one code: a run of empty pixels, then full ones or one of a given coverage, or two pixels of given coverages.

On a white background, a pixel of coverage c taking c/7 of the text colour matches the Nextion Editor's simulator to within one level. How the screen mixes the colours over other backgrounds is not known.

#### Rotation

The Nextion Editor stores a font in the project's rotation. The generator's file is upright, and is turned when the font enters the project. Byte 3 says how it is stored: `0a` at rotation 0, `0b` at 90, `0c` at 180, and `0d` at 270.

Each glyph's pixel stream is coded anew, in a turned order:

- at 90, column by column from the left, each column from the bottom up;
- at 180, the upright stream reversed: row by row from the bottom, each row from right to left;
- at 270, column by column from the right, each column from the top down.

The character table keeps its advances and overhangs, which still describe the upright character.

A project whose fonts are not in its rotation, such as upright fonts in a project at rotation 180, shows its text upright in the Nextion Editor. The Nextion Editor stores its fonts turned when it saves the project.

#### Writing a font

A glyph's pixels can often be coded more than one way: a run of pixels fits several codes. The Nextion Editor's choices are listed in full in `zi_font.py`'s docstring. In short:

- two levels exactly when no pixel is partly covered;
- runs of 31 first, for empty and for full pixels;
- the rest of an empty run coded together with what follows it: 1 or 2 full pixels, or one partly covered pixel after at most 7 empty;
- a lone full pixel before a partly covered one paired with it;
- any other partly covered pixel paired with the next.

One of these choices is easy to miss. After at most 7 empty pixels, a partly covered pixel is coded with them, as "n empty, then 1 of coverage c", unless the next pixel has the same coverage. Then the empty pixels are coded alone, and the two equal pixels as a pair.

#### Drawing a font

The Nextion Editor's generator draws a font from a typeface installed in Windows, at a height in pixels, in an encoding.

- The vendor's description of it says that the height is 16 to 254 pixels, and the generator's list of heights offers those. But a height can be typed, and the generator takes one from 12 to 254. Typed lower, it makes a font of 12 pixels. Typed as 255, it makes one of 254.
- The description says too that a font made without "Anti-aliasing of fonts" has one bit per pixel, as its glyphs of two levels show, and that a font can be limited to a range of characters.

Fonts the generator made from Noto Sans, at 12, 16, 20, and 100 pixels, show how it draws:

- **The scale.** The outlines are scaled so that the typeface's ascender and descender, from its `hhea` table, span the height: in Noto Sans, 1069 and 293 units of 1000. Each advance is then within a pixel of the typeface's, scaled the same way.
- **Hints.** The generator draws with the hints a TrueType file contains for small sizes. At 16 and 20 pixels, the baseline falls on a whole pixel, and the letters' stems on whole columns. At 100 pixels, the glyphs are nearly as the outlines fall.
- **The characters.** Every byte from `20` is a character: to `7e` in ascii, and to `ff` in iso-8859-1.
  - The control characters `80` to `9f` show the typeface's missing-character glyph, a box, at its own advance, except two: `84` shows the box at the space's advance, and `85`, the next-line control, is empty, a pixel wide.
  - DEL (`7f`) is empty, about as wide as a letter.
  - The soft hyphen (`ad`) is empty, a pixel wide.
- **A character the typeface lacks** is drawn from another typeface that Windows picks, such as the Hebrew letters Noto Sans lacks.

#### Placing text

How the Nextion Editor's simulator lays a text out in its component (`tests/fixtures/placing/`; `text_pictures.py` follows it):

- **Lines.** The glyphs sit on a line by their advances and overhangs, with `spax` pixels between two characters. A line break, a carriage return and a line feed (`\r\n`), starts a new line, `spay` pixels below the last.
- **A lone carriage return or line feed** breaks no line, and shows as a space. This is true in a text, a sliding text, a select's lines, and a combo box's items alike (`tests/fixtures/drawing-assumptions/`).
- **Wrapping.** With `isbr` 1, a line wider than the component wraps before the first character that does not fit, inside a word or not: "one two three fo" then "ur".
- **Alignment.** The lines are aligned as one block, as wide as the widest line. `xcen` puts the block at the left (0), the centre (1), or the right (2), and `ycen` at the top, the centre, or the bottom. Each line starts at the block's left: right-aligned, a short line does not end where a long one does. Centring rounds down.
- **Passwords.** With `pw` 1, each character shows as `*`.
- **Clipping.** What falls outside the component is cut off.
- **Borders.** A text of `style` 1 on a colour background (`sta` 1) has a border `borderw` pixels wide, inside its rectangle, in the colour `borderc`.
  - The block is placed, and cut, inside the border, as within a rectangle that much smaller: at the left and top, it starts `borderw` pixels in; at the right and bottom, it ends as far in.
  - A 3D style's edge, a pixel wide, is a border too.
  - Borders were seen on texts, buttons, numbers, xfloats, dual-state buttons, and combo boxes (`tests/fixtures/borders/`).
  - On a crop, a picture, or no background, a text of `style` 1 has no border, and its block is placed as without one (`tests/fixtures/drawing-assumptions/`).

Not known: how lines of different widths are centred, and what happens to a space where a line wraps.

#### A font in another encoding than the project's

The Nextion Editor accepts a font in another encoding than the project's: a project in utf-8 or in gb2312 with an iso-8859-1 font compiles, with no error or warning, and its text shows. The font draws each byte of the text as its own character.

- ascii text shows as it should, since both encodings write it as ascii does.
- Other text does not: "Hello é°" shows as "Hello Ã©Â°" in utf-8, and as "Hello ¨¦¡ã" in gb2312.

#### utf-8 fonts

A utf-8 font's table is of one of two kinds:

- **A table of chosen characters**, which the generator writes for its Range choices "ASCII Character" and "Specified character" (Fonts, above). It is laid out as a one-byte font's: an entry for each character chosen, its code its code point, glyph places counted in bytes (byte 33 is 0), and the glyphs back to back after the zero bytes that end the table. Bytes 12 to 15 and 36 to 39 both count its entries, and bytes 8 to 11 are `ff ff 00 ff`.
- **A full table**, which the rest of this section describes, has an entry for every code point to U+FFFF.

Noto Sans at 20 pixels, of U+0000 to U+00FF, is 664,052 bytes long in a full table, and about 10 KB in a table of chosen characters.

The generator's Language Choice window, shown only for utf-8, offers 142 Unicode blocks, such as "C0 Control and Basic Latin" and "C1 Control and Latin 1 Supplement". The vendor's description says that a utf-8 font needs the project's encoding, and its event code, in utf-8, and that one of 56 pixels with every block can reach 23 MB.

A full table:

- **The header** is as a one-byte font's, except:
  - the encoding (byte 4) is 24, utf-8's number;
  - bytes 8 to 11 are `ff ff 00 ff`;
  - bytes 12 to 15 count 65,536 characters, every code point to U+FFFF;
  - byte 33 is 1, and the glyphs' places count in units of 8 bytes, as the published notes say of fonts over 16 MB;
  - bytes 36 to 39 count the characters chosen: 256, or 384 with Cyrillic.
- **The character table** has a 10-byte entry for every code point to U+FFFF, in order, whatever was chosen: 655,360 bytes.
  - A chosen character's entry is laid out as in a one-byte font, its code its code point.
  - Every other entry has code 0, an advance of half the height, rounded down (8, 8, 10, and 16 at 16, 17, 20, and 32 pixels), and a glyph 0 bytes long.
  - Every chosen character has a glyph, even an empty one.
- **The glyphs** follow the table, in the order of their code points, each starting on a multiple of 8 bytes from the table's start, the last one ending the file. They are coded as in a one-byte font: those of U+0020 to U+00FF are byte for byte the demo's iso-8859-1 Sans20's, drawn from the same typeface at the same height.
- **The control characters** U+0000 to U+001F, which Basic Latin includes, are the same at each height.
  - U+0000, U+0009, U+000B, U+000D, and U+001C to U+001F are empty, a pixel wide.
  - U+0002 is empty, as wide as DEL (U+007F).
  - U+000A is empty, and U+000C shows the typeface's missing-character box, each at a width of its own.
  - The others show the box at its own advance.
- **Turned** to a project's rotation, a utf-8 font is stored as a one-byte font is (Rotation, above): byte 3 gives the rotation, the table is unchanged, and each glyph is turned.
  - The Nextion Editor turns a utf-8 font when it saves a project after a change, not as it opens one.
  - U+0000 has no glyph of its own in a turned font. Its entry keeps its glyph's length, and gives the place of the next glyph, U+0001's. Read that way, it seems a run of 20 to 62 pixels, the first bytes of U+0001's glyph. It looks as if the Nextion Editor takes a code of 0 for a code point not chosen as it writes the glyphs.
  - No text shows U+0000, as a 0 byte ends a text.
  - A table of chosen characters is turned as a one-byte font is, as seen at 90 degrees: its header changes only at byte 3 and in the length after it, and its table keeps its layout.
  - None of the fonts seen with such a table contained U+0000.
- **Text** in a utf-8 font is drawn a character per code point, each of one to four bytes.
  - In a full table, the Nextion Editor's simulator draws a code point not chosen as nothing, at the advance its table entry gives. It draws U+1F600, past U+FFFF, the same, at half the height (`tests/fixtures/utf-8-text/`).
  - In a table of chosen characters, it draws a code point the table lacks, and U+1F600, as the table's first character (Fonts, above; `tests/fixtures/chosen-characters-text/`).

#### Two-byte fonts

A font in gb2312, big5, shift-jis, or ks_c_5601-1987 has a glyph for every pair of bytes of its encoding's grid, then for the ascii characters. The Nextion Editor's font generator makes them in all four, and its Chinese input keyboard carries one in gb2312, 16 pixels tall.

- **Grids:** a character's first byte gives its row, and its second its column. A range may skip a gap.

  | Encoding | First byte | Second byte | Rows × columns |
  | --- | --- | --- | --- |
  | gb2312 | `a1` to `f7` | `a1` to `fe` | 87 × 94 |
  | big5 | `a0` to `f9` | `40` to `7e`, `a1` to `fe` | 90 × 157 |
  | shift-jis | `81` to `9f`, `e0` to `ef` | `40` to `7e`, `80` to `fc` | 47 × 188 |
  | ks_c_5601-1987 | `a1` to `c8` | `a1` to `fe` | 40 × 94 |

- **Header:** as a one-byte font's, except:
  - byte 4, the encoding: 2, 16, 23, or 15;
  - byte 5 is 1;
  - bytes 8 and 9 are the first byte's first and last value, and bytes 10 and 11 the second byte's;
  - bytes 1 and 2 are the second byte's gap: the last value before it, and how many values it skips, as `7e 22` in big5. Bytes 28 and 29 are the first byte's, as `9f 40` in shift-jis. `ff 00` means no gap;
  - bytes 12 to 15, and 36 to 39, both count the entries.
- **Character table:**
  - an entry for every position, row by row, each row's columns in order, then one for each of the 95 ascii characters, from the space to `~`;
  - an entry's code is its character's two bytes, in the order a text stores them, as `d6 d0` for 中 in gb2312;
  - the glyphs follow, back to back, as in a one-byte font.
- **Empty positions:** a position its encoding gives no character may still have a glyph, or be empty, as wide as the font is tall.
- **The Nextion Editor's own gb2312 font** shows each position as the character GBK gives it. Other GB2312 tables differ from GBK at a few positions: GBK reads `a1 a4` as the middle dot, U+00B7, where some read U+30FB, the katakana middle dot.
- **Turned** to a project's rotation, as a one-byte font is (Rotation, above), its table kept in its order.
- **Text:**
  - a byte below `80` is a character of its own, and a byte from `80` starts a pair;
  - each byte's index counts from its range's first value, less the gap when the byte is past the value before it;
  - the screen draws the entry at the first byte's index times the row's length, plus the second byte's index, even for a byte outside its range or in its gap;
  - a place outside the table, before it or past its end, draws the table's first entry;
  - a lone first byte at the text's end draws nothing.
- **Characters a grid has no place for:**
  - ks_c_5601-1987's grid ends at row `c8`, so it has no Hanja;
  - shift-jis's has no half-width katakana, one byte each, which the screen takes as a pair with the byte after it.

#### Other versions and encodings

These come from the published notes alone. The Nextion Editor-made files sampled contain none of them.

- **Version 3**, written by Nextion Editor 0.53: a 28-byte header, the name, then every character at one fixed width, 1 bit per pixel, uncompressed, with no character table. [The vendor's guide](https://nextion.tech/editor_guide/) says fonts from the newer generator do not work in Nextion Editor 0.53.
- **Version 5**, written by TJC's editor 0.55: as version 6, but bytes 36 to 39 are 0. In the notes' sample files, no bytes follow a table of 95 characters.

#### What is not known about fonts

- What byte 5 of the header means beyond the fonts seen (Fonts, above), and how the screen finds an entry in a table of byte 5 at 0.
- How the Nextion Editor's generator turns coverage into its eight levels, which pixels it makes full without anti-aliasing, and what its Bold option does to a typeface.
- How the screen mixes colours for partly covered pixels over a background other than white.
- Two-byte fonts of the generator's other Range choices; and of utf-8 fonts, what fonts of characters past U+FFFF contain.

### Animations, videos, and sounds

The Nextion Editor lists them in the manifest after the fonts and before the pages: the pictures, the fonts, the animations, the videos, the sounds, then the pages.

**An animation** is two blocks with the same number.

- `N.gmovs` is the file GmovMaker wrote, byte for byte. It starts with `GMOV`, the rotation's marker, and `V`, and stores each frame as the picture it was made from. GmovMaker has no rotation of its own: every one of its files seen has the marker of 0, `0a`.
- `N.gmov` is a form the Nextion Editor makes of it when it is added, for the project's rotation. It starts with `GMOV`, that rotation's marker, and `R`. It stores each frame as a JPEG picture, coded at the IJG's quality 82, after a header giving the JPEG picture's size.
  - The frame is padded with black, at its right and bottom, to whole blocks of 16 pixels: a frame of 33 by 17 becomes a JPEG picture of 48 by 32, of which the screen shows the first 33 by 17.
  - For a turned screen, the frame is then turned, as a screen copy's pixels are: a frame of 72 by 40, at 90 degrees, is a JPEG picture of 48 by 80.
  - The JPEG picture has no transparency. A pixel keeps its own colour, however transparent, but a wholly transparent one becomes black.
- Both forms end with a chunk of 4,096 bytes: `hmic`, its size, and zeros. The header of `N.gmov` gives that size too. What the chunk is for is not known.
- The manifest lists only `N.gmov`, as it lists only a picture's `N.i`.

**A video**'s `N.v` is the file VideoBox wrote, byte for byte.

- It starts with `VIDE`, the rotation's marker, `P`, the frame rate in a byte, and a zero byte.
- Its header is laid out as an animation's, except the word at +48, which is 0, and the word at +36: the number of frames × 1,000 / the rate, rounded down.
- Each entry gives the frame's place, its width and height, and its size, and no duration.
- Each frame is a baseline JPEG picture alone, coded at the IJG's quality 80, and padded with white to whole blocks of 16 pixels: a frame of 160 by 120 is a JPEG picture of 160 by 128.
- For a turned screen, VideoBox's display direction, the frame is then turned, as an animation's frame is.
- The file ends with the same 4,096 bytes as an animation's.

**The rotation's marker** of an animation's and a video's files is a screen copy's: `0a` plus the rotation / 90, so `0b` at 90 degrees.

- It is byte 4 of the file, and the low byte of each frame's entry's kind. The kind's high byte gives the file's form: 2 in GmovMaker's file, 4 in the Nextion Editor's form, and 1 in a video.
- The header's and the entries' width and height stay the frame's own, unturned.
- The Nextion Editor refuses to compile a video made for another rotation than the project's ("The direction of the file is inconsistent with the current engineering display direction").
- It takes an animation's form made for another rotation, and makes it again for the project's as it compiles.

**A sound**'s `N.wav` is the WAV file the Nextion Editor's Audio panel wrote of the one it was given.

- The panel converts nothing. It keeps every rate from 8,000 to 48,000 samples a second, 8 and 16 bits, mono and stereo, and even 24-bit and float samples, as they were.
- It writes the file anew: the RIFF header; the format chunk, cut to its first 16 bytes; a chunk of its own, `hmic`, of 504 bytes; then the samples, padded with zeros to a whole number of 4 bytes. Other chunks are left out.
- `hmic` contains `crc`, the length 4, and a check value; then `name`, the name's length, and the name of the file it was given, without its extension; then zeros.
- The check value is the CRC of the stamps (Checksums, below), fed 32-bit little-endian words, as the screen's chip computes it. It runs from the `data` chunk's header, for as many bytes as the samples take, so the samples' last 8 bytes are left out.
- The Nextion Editor takes a sound without `hmic`, and one whose check value is zeroed. Its simulator plays a sound without `hmic` in just the sound's length, where it takes about 400 ms to play a sound of 50 ms with `hmic`.

An animation's `N.gmov` and a video's `N.v` list their frames, JPEG pictures, in a table after the header. In `N.gmov`, the table also gives each frame's duration. `nxwright/project/media_files.py` gives the byte layout of all these files.

### Macros

The Nextion Editor 1.68.2 added macros, in a "macro" tab beside Program.s.

- A project with macros has the block `comcode.sn`. Deleting every macro in the tab removes it.
- The block contains each macro in the tab's order: its name, then its number of lines, then its lines, each line ending in CR LF, in UTF-8. Three macros, of two lines, none, and one: `newcall\r\n2\r\nprinth 4D\r\nprints "café",0\r\nnewcall1\r\n0\r\nmy name\r\n1\r\nsys0=7\r\n`.
- The tab drops a blank line typed in a macro, and saves a macro with no code with a count of 0.

Macros' names, as the tab takes them:

- letters, digits, underscores, and spaces, not a digit first, and not a name another macro has. Names are told apart by case.
- The tab refuses a hyphen ("Illegal character in Name-"), a digit first ("First character of a Name can not be number"), and a name another macro has ("duplicate name").
- The compiler takes a name with a digit first, written into the block by hand. It refuses two macros of one name ("macro crc invalid").

Compiling:

- A `call` of a macro the project lacks fails to compile: "the macro is invalid".
- A macro's code reaches components only of global scope, with their page's name: `page0.t1.txt`. `t1.txt`, and a component of local scope even with its page's name, fail to compile ("Invalid Variables").
- A command naming a component, as `vis`, `tsw`, `ref`, and `click` do, takes the component's number in a macro, written or stored in a variable or a value. `vis 1,0`, `vis sys0,0`, and `vis page0.n0.val,0` compile. `vis t0,0`, and `click page0.b0,1` with b0 of global scope, fail ("Invalid Component ID").

## Pictures for the SD card

An external picture shows a file of the screen's SD card, which the project does not contain. The Nextion Editor's simulator shows a PNG, a JPEG, and a `.xi` file alike, each in its own colours, with its transparency.

PictureBox, the Nextion Editor's tool for SD card pictures, writes `.xi` files. Version 1.1 writes them in this form:

- It starts with `hmipicxi`, then a header of 24 bytes laid out as a screen copy's (Pictures, above):
  - the rotation's marker, 0x0A plus the rotation / 90, then 0, 0, and 1;
  - two words whose meaning is not known, always 0xFFFF and 24;
  - the picture's own width and height;
  - the size of what follows;
  - where its alpha section starts, from the header's end, or 0 for none.
- Then comes a baseline JPEG picture, its colour at half the width and height, at a quality PictureBox names, on the IJG's scale: Highest 100, Very High 96, High 80, Middle 70, Low 50, Very Low 30.
  - The picture is padded with black, at its right and bottom, to whole blocks of 16 pixels, then turned for the screen's rotation, as a screen copy's pixels are: a picture 80 by 60, for a screen turned 90 degrees, is a JPEG of 64 by 80.
  - A pixel keeps its own colour; a wholly transparent one is black.
- When some pixel is not opaque, an alpha section follows, over the turned picture, the padding wholly transparent, coded as a screen copy's.

The screen ignores the rotation the header gives. It draws the file's pixels as they are stored, turned back by its own rotation, from the component's top left corner. So a file for another rotation shows turned, its padding too, and so does a PNG or a JPEG stored upright on a turned screen.

`nxwright/project/media_files.py` gives the layout.

## Checksums

The Nextion Editor checks three checksums when it opens a project or imports a page. A file with a wrong one is refused, with the message "Version mismatch".

All three are CRCs with the polynomial `0x04C11DB7`, starting at `0xFFFFFFFF`.

| Checksum | Where it is stored | What it covers |
| --- | --- | --- |
| Page stamp | The first 4 bytes of each page block and page file | The rest of the page, then bytes 4 to 7, 12 to 15, 20, and 21 of its header |
| Manifest stamp | The first 4 bytes of the manifest | The rest of the manifest, then bytes 4 to 7 of its header, then six values that are not in the file |
| Directory checksum | The 4 bytes after the directory | The directory |

- The two stamps feed the CRC one byte at a time, each as a 32-bit word. The directory checksum feeds it the directory four bytes at a time, as little-endian words.
- The manifest stamp's six extra values are not known. The Nextion Editor keeps them for each screen model. Their effect on the stamp is one number per model, the same at every rotation. `screen_models.py` lists that number for all 27 models.
- `stamp.py` gives the details of the two stamps, and `container.py` those of the directory checksum.

## Writing a project file the Nextion Editor accepts

The build writes the whole file anew, laid out as the Nextion Editor lays out a new project, whatever the screen model: the directory, its copy, two fixed markers, then the blocks back to back, with the manifest last. `new_project.py` gives the offsets.

- Screen copies are generated in the format of the model's series, and the pixel order of the rotation.
- After writing, nxwright reads the file back, and checks the directory checksum and the manifest stamp.

`nxwright write`, which applies an edited dump to the project it came from, writes the way the Nextion Editor saves instead:

- an old entry is marked stale and its name blanked;
- the new block goes at the end of the file, and its entry at the end of the directory;
- after writing, it reads the file back, and checks every checksum, and that each new screen copy decodes back to its picture.

Files written both ways open in the Nextion Editor, survive its later saves, and compile.

## The Nextion Editor's memory

The Nextion Editor's compile counts the memory each page takes on the screen, and refuses a page that passes the screen's memory. Its Output panel shows it:

```
Available Memory:3584
Global Memory:16
Page:page0 Memory Occupied:16+20=36
Error:Page:p26 Error! Memory overflow:16+4072=4088
```

- `Available Memory` is the screen's memory, by its model: 3,584 bytes on a basic screen, 524,288 on an Intelligent one.
- `Global Memory` is the project's global memory, which every page's total includes.
- Each page's total is the global memory and the page's own memory.
- The compile checks the components' types and attributes first, then counts the pages in order. It stops at the first component, value, or page it refuses.

What it counts, per series of screens (measured by `tools/editor/memory_probe.py`):

- **A page's own memory** is a fixed number of bytes, a part for how many objects it has, the page among them, and each component's cost. On a basic screen: 16 bytes, and 1 for each object, rounded up to 4.
- **A component's cost** is its type's, with a part for each attribute whose value changes it.
  - Most such attributes are buffers: `txt_maxl`, the most bytes a text's `txt` can store, the `_m` attributes, and `molloc`. On a basic screen, a text costs 8 bytes and its `txt_maxl` plus 2, rounded up to 4.
  - Other attributes may count too: a waveform keeps, for each channel, 1.3 bytes for each pixel of its width.
  - A sliding text's `path_m` keeps room for its lines. When `path_m` is 0, that room is `txt_maxl` bytes instead. So on the Intelligent and Edge series, each byte of `txt_maxl` counts twice while `path_m` is 0.
- **A component of global scope** (`vscope` 1) keeps a few bytes on its page, 4 on an Intelligent screen and none on a basic one, and the rest of its cost in global memory.
- **Global memory** is a fixed number of bytes, 4 for each `int` of `program.s`, and the global components' parts. The Intelligent and Edge screens take a data record of global scope only, which keeps there the most of its 11,776 bytes, and a file stream of local scope only.
- **Event code** costs nothing: it is kept with the program, not in memory.
- **A QR code needs temporary memory besides**, which must fit in what the page's total leaves of the screen's memory.
  - It steps up with the QR code's `txt_maxl`. On a basic or Enhanced screen: nothing at 0, 586 bytes up to 17, 851 up to 32, and so on to 3,382 up to 192, the most `txt_maxl` they take. On a Discovery screen, less: 295 bytes up to 17, and so on to 1,745 up to 230.
  - Two QR codes on a page need the larger of their needs.
  - If the page leaves too little memory for it, the compile refuses the page. The error gives how many bytes are missing, such as 443 here: `Error:Page:p013 The remaining memory is not enough to run the temporary use of QR code(-443)`.
  - The Intelligent and Edge screens, of far more memory, take a QR code on a page filled to the last byte.

nxwright keeps what the probe measured in `nxwright/project/memory_costs.toml`, read by `nxwright/project/memory_table.py`:

- each model's memory;
- per series, the page's costs, global memory's, and each type's, with a rule for each attribute that changes it. A rule takes the attribute's value, times so many bytes for so many units of it, then a number of bytes added, rounded up to a multiple, and times another attribute's value where one multiplies it, as a waveform's channels do its width's part;
- a type that needs temporary memory, with its steps, up to the largest value measured;
- per series, the types its compile refuses, and the values it was seen to refuse, such as a gauge's `sta` 3 on a basic screen.

## The Nextion Editor's quirks

- **"Save As" also changes the original file.** "Save As" writes the new file, and also writes the project's settings into the file it was opened from. After changing the screen's rotation and using "Save As", the original file has the new rotation with its old pictures. Make copies outside the Nextion Editor instead. For this reason, `nxwright write` takes the format and pixel order of new pictures from the project's own pictures, never from the rotation setting.
- **One-pixel pictures in compressed projects.** The Nextion Editor stores a 1-by-1 picture uncompressed in a project whose pictures are compressed, then warns "Index was outside the bounds of the array" whenever the project is opened, until the picture is removed. nxwright refuses to add such a picture.

## What is not known

- The purpose of some header bytes of pages and of the manifest. They are kept as they are, and a dump shows them as numbers.
- Whether the screen checks a sound's check value.
- The compressed variant of format 3 screen copies. Such pictures are kept, moved, and removed, but not decoded, and new format 3 pictures are written uncompressed.
- The exact rule for the colour of partly transparent pixels.
- How the Nextion Editor takes a GIF of several frames.
- The compiled screen file (`.tft`) that the Nextion Editor makes from a project. nxwright stops at the project file; the Nextion Editor compiles it.
