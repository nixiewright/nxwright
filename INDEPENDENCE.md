# nxwright's independence

nxwright is an independent, cross-platform, open-source project, not affiliated with or endorsed by ITEAD or Nextion. It reads and writes the Nextion Editor's project files so that you can keep your app as text. It can also compile your app into a TFT file without the Windows-only Nextion Editor, and upload the file to your screen.

nxwright is built on public documents and on observing the Nextion Editor, and ships none of the vendor's files.

## What nxwright is built on

The vendor of Nextion screens does not document the formats of HMI project files or TFT files. Every fact that nxwright relies on, whether about those files, the Nextion Editor, or the screen, is backed by one of two kinds of source:

- **What the Nextion Editor does.** The project files it saves, the code its compile accepts and refuses, the TFT files it writes, and how its simulator behaves.
- **Public documents.** The vendor's [Instruction Set](https://nextion.tech/instruction-set/) and [Editor Guide](https://nextion.tech/editor_guide/), and these documents by the Nextion community:
  - The [Full Instruction Set by UNUF](https://github.com/UNUF/nxt-doc/blob/main/Protocols/Full%20Instruction%20Set.md), for the commands and system variables the vendor does not document.
  - The [command tables of TFTTool by zed-0xff](https://github.com/zed-0xff/TFTTool/blob/main/NextionInstructionSets.py), for the names of more undocumented commands and system variables, such as `lcd_refx` and `runmod`.
  - The [format notes by vladtsvetkov880-hub](https://github.com/vladtsvetkov880-hub/nextion-hmi-format), the starting point for the project file's container and checksum.
  - The [font notes by hagronnestad](https://github.com/hagronnestad/nextion-font-editor/tree/master/Docs), the starting point for the font format.

nxwright does not copy code from the projects these documents belong to.

## What nxwright does not contain

nxwright does not ship any of the vendor's files or texts:

- **Firmware and installed files.** The screen's firmware, any file from the Nextion Editor's installation, and TFT files, which contain the firmware.
- **The Nextion Editor's texts.** nxwright describes attributes in its own words, and does not copy the Nextion Editor's hints.
- **The vendor's projects, pictures, and fonts.** The keyboard pages nxwright adds are its own work, and the font it ships is Noto Sans, under the SIL Open Font License.

## What nxwright reads from your computer

Some features need material from the vendor that nxwright does not ship, so they read it from your computer.

Every TFT file contains the screen's firmware, which Nextion makes. To compile, nxwright takes the firmware from a TFT file or a Nextion Editor folder you choose, or from the Nextion Editor installed on your computer. If none of these has it, nxwright downloads it from Nextion's site with your permission. Wherever the firmware came from, nxwright keeps it in your cache folder for later compiles.

`nxwright decompile` turns your own TFT file back into a source folder. It reads only the app's part of the file, never the firmware's code. To check the result, the command compiles the folder again, and copies the firmware from your TFT file into the new one unchanged.

To test or simulate Chinese input, nxwright needs the screen's pinyin table. It reads the table from your installed Nextion Editor's `input.bin`, or from a TFT file you choose, and never copies it into your project.

## For contributors

Please keep nxwright free of the vendor's material, and keep its facts traceable to their sources:

- Work out how the Nextion Editor behaves by observing it: the files it saves, the code its compile accepts and refuses, and what its simulator does. See [tools/editor](tools/editor/README.md) for a tool that drives the Nextion Editor.
- Do not decompile or disassemble the Nextion Editor or the screen's firmware, and do not decode the data inside the Nextion Editor's executable and library files.
- Do not commit any file from the Nextion Editor's installation, any TFT file, or a project, picture, or font the vendor made.
- Write descriptions in your own words. Do not copy the Nextion Editor's hints or help.
- When a fact comes from a public document, name the document in a comment beside the code that relies on it.
