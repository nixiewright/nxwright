# Dumps: a project file as text

A **dump** is a project file written out as a folder of plain text and asset files, exact enough to write the project back from. Comparing two projects becomes an ordinary folder diff. A dump is also the step between a project file and a source folder (`source-folder.md`): `nxwright extract` and `nxwright build` make one in a temporary folder.

The terms used below, such as block, manifest, ID, and screen copy, are explained in `format.md`.

## Writing a dump

```
nxwright dump <project.HMI> <output-folder>
```

- The project file is only read.
- The output folder must not exist yet, or must be empty. nxwright never deletes anything, so clear an old dump if you want a new one to take its place. A failed run leaves its partial folder in place, and its message points at the folder.
- A dump is the way to look inside a project that nxwright does not fully know, such as one a newer Nextion Editor saved. For that reason, `dump` never prompts you to go on. It warns of each thing nxwright does not know, and writes the rest ([commands.md](commands.md#extract)). A block of a kind nxwright does not handle is left out of the dump.

## Layout

Pages, pictures, fonts, animations, videos, and sounds are numbered by their IDs: the numbers that `page 2`, `pic=5`, `font=3`, and `vid=1` refer to. The index files also show each one's block, its storage name in the project file.

| Path | Contents |
| --- | --- |
| `project.txt` | The dump format, the file's size, the directory's counts (live blocks, stale entries), and the manifest: its header bytes that are not understood, and the resource list in stored order. |
| `program.s` | The program code that runs at power-on, bytes unchanged. |
| `macros.s` | The project's macros, its `comcode.sn` block's bytes unchanged (`format.md`, Macros), when it has any. |
| `pages/NN-<name>.txt` | One file per page, numbered by page ID, its name encoded as a source folder's page files are ([source-folder.md](source-folder.md)). The page's name comes from the file's first line, not from the file's name. |
| `images/index.txt` | Per picture: ID, block, size, and a SHA-256 of the screen copy. |
| `images/NNNN.png`, or `.jpg`, `.jpeg`, `.bmp`, `.gif` | The picture's file the Nextion Editor shows, as the project keeps it, with the suffix its record gives. |
| `images/NNNN.i` | The screen copy, as stored. Output only: nxwright never reads these files back. |
| `images/NNNN.source.png`, or `.jpg`, `.jpeg`, `.bmp`, `.gif` | The source of a picture resized in the Nextion Editor: the file it had before (`format.md`, Pictures). Only a resized picture has one. |
| `fonts/index.txt` | Per font: ID, block, block size, height, and character range. |
| `fonts/NN.zi` | The font block, as stored. |
| `animations/index.txt`, `videos/index.txt`, `sounds/index.txt` | Per animation, video, or sound: ID, and each of its blocks with its size. |
| `animations/NN.gmov`, `animations/NN.screen.gmov` | An animation's two blocks, as stored: GmovMaker's file, and the form the screen shows (`format.md`). |
| `videos/NN.video` | A video's block, as stored. |
| `sounds/NN.wav` | A sound's block, as stored. |

The dump stops with an error if the manifest does not list every page, picture, font, animation, video, and sound block exactly once, because the IDs would then be ambiguous.

A dump records its format version in the first line of `project.txt`. A dump written by another version of nxwright is refused rather than misread: dump the project again. A dump is in format 5 when one of its page lines is quoted (Page text), and in format 4 otherwise, so that an older nxwright still reads it. nxwright reads both.

## Page text

Each page lists its objects, the page first and then its components, with their records in stored order:

```
page settings
header_size = 56
header_16 = 00000000004f2100
header_40 = 01430100000000000000000000000000

object 0 settings
  marker att-28
  type = 121
  objname = "settings"
  w = 800
  event load
    | if(sys0!=0)
    | {
    |   title.pco=sys1
    | }
  event down
```

- `page name` gives the page's name. A name outside printable ASCII, or with a double quote, is quoted as a string is, as `page "caf\xe9"` for `café`.
- `object N name` labels the object with its index and name. The name is left off when it is empty or contains a space.
- `marker` lines are short tags; `att-NN` gives the component's class.
- Numbers are decimal. A number whose width in bytes differs from what nxwright expects for that component type shows its width, for example `val:u8 = 0`.
- Strings are quoted. Bytes outside printable ASCII appear as `\xNN`.
- `event <name>` is followed by its code lines, each after `| `.
- `raw <hex>` gives a record or code line that cannot be shown as text exactly.

The text is exact: nxwright checks, on every dump, that each page's text gives back its page block.

## Importing a dump into a source folder

```
nxwright import <dump-folder> <source-folder>
```

Turns a dump into a source folder ([source-folder.md](source-folder.md)).

- A new or empty folder gets a fresh source folder.
- A source folder that already has an `app.toml` is updated. Each event keeps its text, comments included, unless the project changed that event's code ([Extracting into an existing folder](source-folder.md#extracting-into-an-existing-folder)).
- Any other folder is refused.
- Import checks the dump's manifest header and pages for things nxwright does not know, and treats each one as extract does. It warns and goes on, prompts you to choose whether to go on, or refuses, and takes `--continue-with-unknown` ([commands.md](commands.md#extract)).

## Page files

```
nxwright page <dump-folder> <page-id> <output.page>
```

Writes one page of a dump as a page file, for importing into a project in the Nextion Editor.

- An existing page file at the output is replaced, but only once the new one is written in full. The command asks first, unless you pass `--overwrite`, and refuses when there is no terminal to ask at, as in a script. Any other kind of file there is refused.
- The page file carries the fonts the page uses, so the Nextion Editor adds any the project lacks.
- It does not carry pictures. Picture attributes keep their IDs, so the target project needs the same pictures with the same IDs.
- Font numbers in `font` attributes are renumbered to the page file's own font list.
- Font numbers written in event code, such as `t0.font=3`, are left as they are, as the Nextion Editor's export leaves them. That code still refers to the project's font IDs.
- The Nextion Editor imports a page file as a new page: it never replaces one. To update a page, delete the old page in the Nextion Editor, then import the new one.

## Writing a project file from a dump

```
nxwright write <project.HMI> <dump-folder> <output.HMI>
```

Writes a new project file from a project and an edited dump of that same project. Open the output in the Nextion Editor and compile it.

What the dump can change:

- **Pages:** edit a page's text; add a page, as a new file with the next page ID; remove one, by deleting its file; reorder them, by renumbering the files, keeping the IDs 0, 1, 2, ... without gaps. Pages are matched to the project by name, so renaming a page counts as removing it and adding a new one.
- **Pictures:** add, replace, remove, or reorder the picture files in `images/`, keeping the IDs without gaps.
  - Each is `NNNN.png`, `.jpg`, `.jpeg`, `.bmp`, or `.gif`, one file for each ID, kept as it is.
  - Pictures are matched to the project by their files' bytes and suffixes. So an edited picture, or one given another suffix, counts as a new one replacing the old one.
  - nxwright makes each new picture's screen copy. The `.i` files of the dump are ignored.
  - A picture's source file goes with its ID: add, replace, or delete it, and the project's source block follows. Delete it when you replace the picture's file, unless the new file is a resized form of it.
- **Fonts:** add, remove, or reorder the font files, keeping the IDs without gaps. Fonts are matched to the project by their bytes; take new fonts from another dump, or from the Nextion Editor's font generator.
- **Animations, videos, and sounds:** add, remove, or reorder their files, keeping the IDs without gaps, an animation's two files together. They are matched to the project by their bytes; take new ones from another dump.
- **`program.s`.**
- **`macros.s`:** edit it, add it, or remove it, which removes the project's macros.

New pictures:

- are written in the screen copy format and pixel order that the project's own pictures show, for any screen model at any rotation;
- in a project with no pictures yet, are written in the format and pixel order of its screen model and rotation, as a build writes them. So are those of a project whose only pictures are 1-by-1 pictures in format 0, which show no format or pixel order;
- take their screen copies from the picture cache, when an earlier build or write made them (`source-folder.md`, The picture cache).

Some projects limit what can be added:

- Adding a picture is refused in a project whose pictures show more than one format. It is refused, too, when every picture looks the same at more than one rotation, so that none shows the pixel order. So is adding one to a project without pictures whose screen model nxwright does not know. The dump's other edits still work.
- Pictures in the compressed variant of format 3 are kept as they are, and new format 3 pictures are written uncompressed.
- A 1-by-1 picture cannot be added to a project in the compressed format (`format.md`, The Nextion Editor's quirks).

Renumbering does not rewrite references: when pages, pictures, fonts, animations, videos, or sounds move, code such as `page 3` and attributes such as `pic=5`, `font=2`, or `vid=1` must already use the new IDs. A source folder (`source-folder.md`) refers to them by name instead, which follows them.

- An existing project file at the output is replaced, but only once the new one is written in full and has passed the check below. The command asks first, unless you pass `--overwrite`, and refuses when there is no terminal to ask at, as in a script. Any other kind of file there is refused.
- The project file is only read, unless you give it as the output too. It is then read in full first, and the new file replaces it.
- Blocks are written the way the Nextion Editor saves them (`format.md`), so the file survives the Nextion Editor's own saves.
- After writing, nxwright reads the file back, and checks that it contains the dump's pages, pictures, fonts, `program.s`, and macros.
- With nothing changed, it writes nothing, and prints "Nothing in the dump differs from the project; nothing written."
