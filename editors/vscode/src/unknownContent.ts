// Decides what Extract does with a project that contains things nxwright
// does not know: extract it, ask the user first, or refuse. The decision
// rests on the list that `nxwright extract --list-unknown` prints, one JSON
// object per line (docs/commands.md, extract). The extension runs extract as
// a task, and a task cannot hand back what the command printed, so the
// extension gets that list first. This file does not use VS Code, so that
// its tests can run without it.

// One thing in a project that nxwright does not know, as the list gives it:
// what it is, where it is, its sort, its size, and its first bytes in
// hexadecimal.
interface UnknownContent {
  what: string;
  where: string;
  sort: string;
  size: number;
  first_bytes: string;
}

// What Extract does: extract as usual, ask the user first, or refuse. Asking
// and refusing come with the message to show.
export type ExtractChoice =
  | { kind: "extract" }
  | { kind: "ask"; message: string }
  | { kind: "refuse"; message: string };

// The two sorts in the list that change what Extract does: content the next
// build may lose, and content the source folder cannot keep. The other sorts,
// "kept exactly" and "written otherwise", need no question, and the extract
// task's output gives a note for each. A sort this file does not know, which
// a newer nxwright may print, is treated the same way. "cannot be kept" is
// still printed by older versions of nxwright, and by newer ones for what
// they still cannot keep.
const MAY_BE_LOST = "may be lost";
const CANNOT_BE_KEPT = "cannot be kept";

const REPORT_HINT = "`nxwright report` writes a report on the project file to send to " +
  "nxwright's maintainers.";

// Returns what Extract does with a project. `listed` is what
// `nxwright extract --list-unknown` printed for the project.
export function extractChoice(listed: string): ExtractChoice {
  let found: UnknownContent[];
  try {
    found = listed.split("\n").filter((line) => line.trim() !== "")
      .map((line) => JSON.parse(line) as UnknownContent);
  } catch {
    return { kind: "refuse", message: "nxwright could not list the things in this project " +
      "that it does not know, so nothing was extracted." };
  }
  const cannot = found.filter((each) => each.sort === CANNOT_BE_KEPT);
  if (cannot.length > 0) {
    return { kind: "refuse", message: "This project contains things nxwright cannot keep: " +
      listedText(cannot) + ". A newer Nextion Editor may have added them. " + REPORT_HINT };
  }
  const lost = found.filter((each) => each.sort === MAY_BE_LOST);
  if (lost.length > 0) {
    return { kind: "ask", message: "This project contains things nxwright does not know, " +
      "which the next build may lose: " + listedText(lost) + ". The built project may then " +
      "lack parameters that the Nextion Editor needs, and may not be the same as this one. " +
      REPORT_HINT };
  }
  return { kind: "extract" };
}

// Returns each of `found` as "what (where)", separated by semicolons.
function listedText(found: UnknownContent[]): string {
  return found.map((each) => `${each.what} (${each.where})`).join("; ");
}
