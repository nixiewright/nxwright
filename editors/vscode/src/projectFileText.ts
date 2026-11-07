// The text of what the extension says about a source folder's project file:
// the warning before a changed file is replaced, and the notice when Extract
// is run on a folder in nxlang. It is kept apart from VS Code's API so that the
// tests can check it.

// The button that extracts a project file into a new folder.
export const EXTRACT_NEW_FOLDER = "Extract into a New Folder";

// The notice when Extract is run on the source folder `folder` in nxlang.
export function nxlangExtractNotice(folder: string): string {
  return `nxwright: ${folder} uses nxlang, so nxwright cannot extract over it: the code the ` +
    "build writes cannot turn back into nxlang. Make code changes in the source folder. To see " +
    "what the project contains, extract it into a new folder, and compare that folder with " +
    "your source folder.";
}

// The detail of the warning shown before nxwright replaces a project file that
// was changed outside nxwright. `nxlang` is whether the source folder is in
// nxlang, and `backups` is whether the setting nxwright.backups is on.
export function changedProjectFileDetail(nxlang: boolean, backups: boolean): string {
  const backup = backups ? "The old file will be kept as a backup." : "No backup will be kept.";
  return nxlang
    ? "The new file will not have those changes, and they cannot come back into the source " +
      `folder. ${backup} To see those changes, you can extract the old file into a new folder.`
    : `The new file will not have those changes. ${backup} Extract First brings those changes ` +
      "into the source folder.";
}
