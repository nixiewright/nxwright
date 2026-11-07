# Dumps: a project file as text

A **dump** is a project file (HMI) written out as a folder of plain text and asset files, exact enough to write the project back from. You can compare two projects by comparing their dumps with any folder diff tool.

See [format.md](format.md) for the terms used below, such as block, manifest, ID, and screen copy.

## Writing a dump

```
nxwright dump <project.HMI> <output-folder>
```

- The project file is only read.
- The output folder must be empty or not exist yet. nxwright never deletes anything, so to replace an old dump, clear its folder first. A failed run leaves its partial folder in place.
- You can use a dump to look inside a project that nxwright does not fully know, such as one a newer Nextion Editor saved. `dump` warns about each thing it does not know and writes the rest, without prompting you to go on ([commands.md](commands.md#extract)). It leaves out any block of a kind nxwright does not handle.

## Layout

Pages, pictures, fonts, animations, videos, and sounds are numbered by their IDs: the numbers that `page 2`, `pic=5`, `font=3`, and `vid=1` refer to. The index files also give the name of the block that stores each picture, font, animation, video, or sound.

| Path | Contents |
| --- | --- |
| `project.txt` | The dump's format version, the project file's size, the number of live blocks and stale entries in the directory, and the manifest: its header bytes that nxwright does not understand, and its list of resources in stored order. |
| `program.s` | The program code that runs at power-on, bytes unchanged. |
| `macros.s` | The project's macros, if it has any: the bytes of its `comcode.sn` block, unchanged ([format.md](format.md#macros)). |
| `pages/NN-<name>.txt` | One file per page, numbered by page ID. `<name>` is the page's name, encoded the same way as in a source folder's page files ([source-folder.md](source-folder.md)). nxwright takes the page's name from the file's first line, and does not use `<name>`. |
| `images/index.txt` | Per picture: ID, block, size, and a SHA-256 of the screen copy. |
| `images/NNNN.png`, or `.jpg`, `.jpeg`, `.bmp`, `.gif` | The picture's file as the project stores it, which is the file the Nextion Editor shows. The suffix is the one recorded in the project, so it can also be another type, such as `.tif`. |
| `images/NNNN.i` | The screen copy, as stored. nxwright uses this file only for a picture whose file it cannot decode, such as a `.tif`, and then writes the screen copy back unchanged. |
| `images/NNNN.source.png`, or `.jpg`, `.jpeg`, `.bmp`, `.gif` | Only for a picture resized in the Nextion Editor: the file it had before the resize ([format.md](format.md#pictures)). |
| `fonts/index.txt` | Per font: ID, block, block size, height, and character range. |
| `fonts/NN.zi` | The font block, as stored. |
| `animations/index.txt`, `videos/index.txt`, `sounds/index.txt` | Per animation, video, or sound: ID, and each of its blocks with its size. |
| `animations/NN.gmov`, `animations/NN.screen.gmov` | An animation's two blocks, as stored. `NN.gmov` is GmovMaker's file, and `NN.screen.gmov` is what the screen shows ([format.md](format.md#animations-videos-and-sounds)). |
| `videos/NN.video` | A video's block, as stored. |
| `sounds/NN.wav` | A sound's block, as stored. |

`nxwright dump` stops with an error if the manifest does not list every page, picture, font, animation, video, and sound block exactly once, because the IDs would then be ambiguous.

If a dump is in a format nxwright cannot read, nxwright refuses it, and you need to dump the project again. The format version is on the first line of `project.txt`. Dumps use format 4 when they can, so that older versions of nxwright can read them, and format 5 only when a page's name is quoted on its `page` line ([Page text](#page-text)).

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

- `page name` gives the page's name. If the name contains a double quote or characters outside printable ASCII, it is quoted in the same way as a string, for example `page "caf\xe9"` for `café`.
- `object N name` labels the object with its index and name. The name is left off when it is empty or contains a space.
- `marker` lines are short tags. `att-NN` gives the component's class.
- Numbers are decimal. A number whose width in bytes differs from what nxwright expects for that component type shows its width, for example `val:u8 = 0`.
- Strings are quoted. Bytes outside printable ASCII appear as `\xNN`.
- `event <name>` is followed by its code lines, each starting with `| `.
- `raw <hex>` gives a record or code line that cannot be shown as text exactly.

The text is exact. On every dump, nxwright checks that each page's text converts back to the same page block.

## Importing a dump into a source folder

```
nxwright import <dump-folder> <source-folder>
```

`nxwright import` turns a dump into a source folder ([source-folder.md](source-folder.md)).

- A new or empty folder gets a fresh source folder.
- A source folder in strict Nextion syntax that already has an `app.toml` is updated. Each event keeps its text, comments included, unless the project changed that event's code ([Extracting into an existing folder](source-folder.md#extracting-into-an-existing-folder)).
- A source folder in nxlang is refused, and nothing changes ([Working with the Nextion Editor](language.md#working-with-the-nextion-editor)).
- Any other folder is refused.
- `import` checks the dump's manifest header and pages for things nxwright does not know. For each one, it warns and goes on, prompts you to choose whether to go on, or refuses. The rules are the same as for `extract`, and `import` also takes `--continue-with-unknown` ([commands.md](commands.md#extract)).

## Page files

```
nxwright page <dump-folder> <page-id> <output.page>
```

`nxwright page` writes one page of a dump as a page file, which you can import into a project in the Nextion Editor. The Nextion Editor imports a page file as a new page and never replaces one, so to update a page, delete the old one first, then import the new one.

- **Fonts:** the page file carries the fonts the page uses, so the Nextion Editor adds any the project lacks. Font numbers in `font` attributes are renumbered to the page file's own font list. Font numbers written in event code, such as `t0.font=3`, are left as they are, so that code still refers to the project's font IDs.
- **Pictures:** the page file does not carry pictures. Picture attributes keep their IDs, so the target project needs the same pictures with the same IDs.
- **Output:** an existing page file at the output is replaced only once the new one is written in full. Pass `--overwrite` to replace it without a prompt. Without that option, the command refuses when there is no terminal, as in a script. Any other kind of file at the output is refused.

## Writing a project file from a dump

```
nxwright write <project.HMI> <dump-folder> <output.HMI>
```

`nxwright write` makes a new project file from a project and an edited dump of that same project. Open the output in the Nextion Editor and compile it.

What the dump can change:

- **Pages:** edit a page's text, add a page as a new file with the next page ID, remove one by deleting its file, or reorder them by renumbering the files. The IDs must stay 0, 1, 2, ... without gaps. Pages are matched to the project by name, so renaming a page counts as removing it and adding a new one.
- **Pictures:** add, replace, remove, or reorder the picture files in `images/`, keeping the IDs without gaps.
  - Each picture file is named `NNNN` with its suffix, such as `.png`, `.jpg`, `.jpeg`, `.bmp`, or `.gif`. Each ID has one file, which is kept as it is.
  - Pictures are matched to the project by their files' bytes and suffixes. So an edited picture, or one given another suffix, counts as a new one replacing the old one.
  - nxwright makes the screen copy of a new PNG, JPEG, BMP, or GIF picture, and does not use the dump's `.i` file for it. A new picture of another type, such as `.tif`, takes its screen copy from its `.i` file in the dump, because nxwright does not decode that type. If that `.i` file is missing, the write stops with an error.
  - A picture's source file goes with the picture's ID. If you add, replace, or delete the source file, the project's source block changes to match. When you replace a picture's file, delete its source file too, unless the new file is a resized form of that source file.
- **Fonts:** add, remove, or reorder the font files, keeping the IDs without gaps. Fonts are matched to the project by their bytes. You can take new fonts from another dump, or from the Nextion Editor's font generator.
- **Animations, videos, and sounds:** add, remove, or reorder their files, keeping the IDs without gaps and an animation's two files together. These are matched to the project by their bytes, and you can take new ones from another dump.
- **`program.s`:** edit it.
- **`macros.s`:** edit it, add it, or remove it, which removes the project's macros.

Renumbering does not update references. If pages, pictures, fonts, animations, videos, or sounds move, you must change code such as `page 3` and attributes such as `pic=5`, `font=2`, or `vid=1` to use the new IDs. A source folder ([source-folder.md](source-folder.md)) avoids this, because it refers to them by name.

nxwright writes each new picture's screen copy in the format and pixel order of the project's existing pictures, whatever the screen model and rotation. If the project has no pictures, or only 1-by-1 pictures in format 0, which do not reveal a format or pixel order, it uses the format and pixel order of the project's screen model and rotation. Screen copies that an earlier build or write made are reused from the picture cache ([source-folder.md](source-folder.md#the-picture-cache)).

Some projects limit what can be added:

- Adding a picture is refused in any of these cases, though the dump's other edits still work:
  - The project's pictures use more than one format.
  - Every picture looks the same at more than one rotation, so nxwright cannot tell the pixel order.
  - The project has no pictures, and nxwright does not know its screen model.
- Pictures in the compressed variant of format 3 are kept as they are, and new format 3 pictures are written uncompressed.
- A 1-by-1 picture cannot be added to a project whose pictures are compressed ([format.md](format.md#the-nextion-editors-quirks)).

Writing the output file:

- An existing project file at the output is replaced only once the new one is written in full and has passed the check below. Pass `--overwrite` to replace it without a prompt. Without that option, the command refuses when there is no terminal, as in a script. Any other kind of file at the output is refused.
- If the file at the output changed since nxwright wrote it, it is kept as a backup beside the new one ([`nxwright build`](commands.md#build)), unless you pass `--no-backup`.
- The input project file is only read, unless you also give it as the output. It is then read in full first, and the new file replaces it.
- The output survives later saves in the Nextion Editor ([format.md](format.md#writing-a-project-file-the-nextion-editor-accepts)).
- After writing, nxwright reads the file back, and checks that it contains the dump's pages, pictures, fonts, `program.s`, and macros.
- If the dump does not differ from the project, `nxwright write` does not write a file.
