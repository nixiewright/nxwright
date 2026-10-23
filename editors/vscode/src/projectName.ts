// The app's name, as the extension shows it, and the file Build's dialog
// starts from, named after it. Kept apart from VS Code, so that its tests run
// without it.
import * as path from "path";

// Characters a file name cannot hold on Windows, macOS, or Linux.
const NOT_IN_A_FILE_NAME = /[\\/:*?"<>|\x00-\x1f]/g;
// The names Windows reserves, alone or before a suffix, in any case.
const RESERVED_BY_WINDOWS = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$/i;

// Returns the app's name: app.toml's `name`, as the language server gives
// it in `info`, or else the name of its source folder, `folder`.
export function appName(info: { name?: string } | null | undefined, folder: string): string {
  return info?.name ?? path.basename(folder);
}

// Returns the file name Build's dialog starts from: the app's name, less the
// characters a file name cannot hold and the dots and spaces at its end, then
// ".HMI"; undefined when nothing is left, or what is left is a name Windows
// reserves, which no file can have there.
export function projectFileName(name: string): string | undefined {
  const kept = name.replace(NOT_IN_A_FILE_NAME, "").replace(/[. ]+$/, "").trim();
  return kept === "" || RESERVED_BY_WINDOWS.test(kept) ? undefined : `${kept}.HMI`;
}
