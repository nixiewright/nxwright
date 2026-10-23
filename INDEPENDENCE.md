# nxwright's independence

nxwright is an independent, open-source project. It is not affiliated with, or endorsed by, ITEAD or Nextion. It reads and writes the Nextion Editor's project files so that you can keep your app as text, and you still compile your app for the screen in the Nextion Editor.

## What nxwright is built on

The vendor does not document the project file. Every fact nxwright relies on, about the project file, the Nextion Editor, or the screen, is backed by one of two kinds of source:

- **What the Nextion Editor does.** The project files it saves, the code its compile accepts and refuses, what its simulator does, and the TFT files it writes.
- **Public documents.** The vendor's instruction set and guide, and documents by the Nextion community. nxwright does not copy those projects' code. The community documents are:
  - the [Full Instruction Set](https://github.com/UNUF/nxt-doc/blob/main/Protocols/Full%20Instruction%20Set.md), for the commands and system variables the vendor does not document;
  - the [format notes by vladtsvetkov880-hub](https://github.com/vladtsvetkov880-hub/nextion-hmi-format), the starting point for the project file's container and checksum;
  - the [font notes by hagronnestad](https://github.com/hagronnestad/nextion-font-editor/tree/master/Docs), the starting point for the font format.

## What nxwright does not contain

nxwright does not ship any of the vendor's files or texts:

- **Firmware.** The screen's firmware, any file of the Nextion Editor's installation, and TFT files, which contain the firmware.
- **The Nextion Editor's texts.** nxwright's descriptions of attributes are written in its own words, not copied from the Nextion Editor's hints.
- **The vendor's projects, pictures, and fonts.** The keyboard pages nxwright adds are its own work. The font nxwright ships is Noto Sans, under the SIL Open Font License.

## What nxwright reads from your computer

Chinese input, in tests and in the simulator, needs the screen's pinyin table. nxwright reads it from your installed Nextion Editor's `input.bin`, or from a TFT file you choose. It never copies the table into your project.

## For contributors

Please keep nxwright free of the vendor's material:

- Learn how the Nextion Editor behaves from what it does: the files it saves, its compile's answers, and its simulator. The tool in [tools/editor](tools/editor/README.md) drives the Nextion Editor for that.
- Do not decompile or disassemble the Nextion Editor or the screen's firmware, and do not decode the data inside the Nextion Editor's program files.
- Do not commit any file of the Nextion Editor's installation, any TFT file, or a project, picture, or font the vendor made.
- Write descriptions in your own words. Do not copy the Nextion Editor's hints or help.
- When a fact comes from a public document, name the document in a comment beside the code that relies on it.
