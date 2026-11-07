# Putting your app on a screen

Screens run a TFT file, which nxwright can compile from your source folder and upload to the screen over a serial port without requiring the Nextion Editor. You can also keep compiling and uploading from the Nextion Editor if you prefer, using the project file (HMI) nxwright builds.

## Two ways to work

- **With nxwright alone.** You don't need a project file. You edit the source folder, compile it into a TFT file, and upload that file to the screen:

  ```
  nxwright compile app thermostat.tft
  nxwright upload thermostat.tft --port COM5
  ```

  In VS Code, the **Compile TFT** and **Upload TFT** buttons in the Project section of nxwright's side bar do the same ([the extension's README](../editors/vscode/README.md#your-project-at-a-glance)).

- **With the Nextion Editor.** You build the project file (HMI), open it in the Nextion Editor, and compile and upload the TFT file there:

  ```
  nxwright build app thermostat.HMI
  ```

  If you change something in the Nextion Editor, you can use `nxwright extract` to bring the change back into the source folder.

You can mix the two. With `--project-file`, `nxwright compile` also writes the project file, so that you can open the same app in the Nextion Editor. In VS Code, the link button beside the project file turns this on for Compile TFT.

## Compiling

`nxwright compile` works for every series of screens: Basic, Enhanced, Intelligent, Discovery, and Edge. See [compile](commands.md#compile) for what it refuses, and for its options.

### The firmware

Every TFT file contains the screen's firmware, the program that runs your app on the screen. Nextion makes the firmware, so nxwright does not ship it. The compile first looks on your computer, for the firmware an earlier compile found or for an installed Nextion Editor. If it finds neither, it offers to download the Nextion Editor's zip, about 50 MB, from Nextion's site. See [The firmware](commands.md#the-firmware) for every source, and for how to choose one.

The compile takes only the firmware of the Nextion Editor 1.68.2, the version nxwright is tested with, because the firmware of another version may run your app's code differently.

## Uploading

Connect the screen to your computer through a USB serial adapter, and give `nxwright upload` the port. `nxwright ports` lists your computer's ports. In VS Code, the first upload prompts for the port and the upload rate, and later uploads reuse them.

The upload is cancelled if the file was compiled for a different model from the screen. See [upload](commands.md#upload) for the other cases, and for its options.

### The rate of the upload

The upload runs at 115200 baud unless you choose another rate with `--upload-baud`. At 115200, a megabyte takes a little over a minute and a half. Rates up to 921600 are much quicker, if your screen and your adapter support them. If an upload fails at a high rate, try a lower one, because some adapters lose bytes at the highest rates.

This rate is separate from the one the screen uses now. You don't need to know that one, because the upload tries each rate until it finds the screen.

### What is sent

An upload can be quicker than the size of the file suggests, because the screen skips the parts of the file it already has. On the screens tried, if you changed only your code, the upload sent just your app's part of the file, without the firmware. It sent the whole file if you changed a picture, or if the screen was running another version's firmware. To always send the whole file, use `--full`.

### When the upload ends

Once the whole file is sent, the screen restarts and runs your app. It may first update its own firmware, which can take a while. Do not power the screen off until your app is showing.

### When an upload breaks off

Once the upload has started, the screen waits for the whole file. If the upload stops early, whether you stopped it or the screen stopped answering, power the screen off and on, then upload the file again.

### If the screen stays black or stops responding

An app can leave a screen black or unresponsive through a setting it saved, such as its brightness, its rate, or its address. If the screen has a microSD slot, Nextion's rescue SD card fixes this. The card contains the TFT file of an empty app that resets those settings. The screen reads the card when it starts, and may do so even when it no longer accepts uploads over its serial port. You can make the card yourself with nxwright:

1. Write the rescue file for your screen model:

   ```
   nxwright rescue rescue.tft --screen NX4832T035
   ```

2. Copy `rescue.tft` to a FAT32 microSD card of at most 32 GB. It must be the only TFT file on the card, and the card must not have hidden files.
3. Put the card in the screen, and power the screen off and on.
4. When the screen has finished, power it off, remove the card, and power it on again. You can then upload your app.

[rescue](commands.md#rescue) lists the settings the file resets. Nextion describes the card in [Developing HMI projects](https://nextion.tech/2022/07/18/developing-hmi-projects-a-way-around-these-oops-moments/).

## Recovering a project from its TFT file

If you still have your app's TFT file, but no longer have its project, `nxwright decompile` turns the file back into a source folder. In VS Code, the command "Decompile a TFT file into a new source folder" does the same.

```
nxwright decompile thermostat.tft app
```

The decompile reads files made by the Nextion Editors 1.60.1 to 1.68.2. For a file made by 1.68.2, it checks its work by compiling the folder again and comparing the result with your file. It cannot check a file made by an older version, because nxwright compiles only with the firmware of 1.68.2. See [decompile](commands.md#decompile) for what happens if the check fails.

The folder contains everything the screen needs, but a TFT file keeps less than a project:

- **Names.** The file keeps only a checksum of each page, component, variable, and macro name. The decompile works out the names it can, and gives the others a readable name, such as `text3`.
- **Code.** All code comes back in strict Nextion syntax, without comments, even if you wrote it in nxlang.
- **Pictures.** The picture files you added do not come back. You get a PNG file of what the screen shows for each one.
