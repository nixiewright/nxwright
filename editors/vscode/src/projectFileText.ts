// The text of the warning before a source folder's changed project file is
// replaced. It is kept apart from VS Code's API so that the tests can check it.

// The button that extracts a project file into a new folder.
export const EXTRACT_NEW_FOLDER = "Extract into a New Folder";
// The button that shows what changed in a project file.
export const SHOW_CHANGES = "Show Changes";

// The detail of the warning shown before nxwright replaces a project file that
// was changed outside nxwright. `backups` is whether the setting nxwright.backups
// is on.
export function changedProjectFileDetail(backups: boolean): string {
  const backup = backups ? "The old file will be kept as a backup." : "No backup will be kept.";
  return `The new file will not have those changes. ${backup} Show Changes lists those ` +
    "changes, and Extract into a New Folder gives them as files.";
}

// Returns the arguments of nxwright that show what changed in the project file
// `file` since it was built from the source folder `folder`. The folder comes first,
// so that the changes show as added lines. `locks` is whether the setting
// nxwright.lockPages is on.
export function showChangesArguments(folder: string, file: string, locks: boolean): string[] {
  return ["diff", folder, file, ...(locks ? [] : ["--no-lock"])];
}
