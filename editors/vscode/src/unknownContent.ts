// What extract does with a project that contains things nxwright does not
// know, as `nxwright extract --list-unknown` lists them, one JSON object a
// line (docs/commands.md, extract): it extracts, asks the user first, or
// refuses. The extension runs extract as a task, which cannot hand back what
// the command printed, so the extension reads that list first. Kept apart
// from VS Code, so that its tests run without it.

// One thing in a project that nxwright does not know, as the list gives it:
// what it is, where it is, how it is sorted, its size, and its first bytes
// in hexadecimal.
interface UnknownContent {
  what: string;
  where: string;
  sort: string;
  size: number;
  first_bytes: string;
}

// What extract does: extract as it would anyway, ask the user first, or
// refuse, with the message to show.
export type ExtractChoice =
  | { kind: "extract" }
  | { kind: "ask"; message: string }
  | { kind: "refuse"; message: string };

// The sorts the list gives, of content the next build may lose, and of
// content the source folder cannot keep. Content kept exactly, and content
// the next build writes as nxwright knows it ("written otherwise"), need no
// question: the extract task's output notes them. Any other sort is taken so
// too, as a newer nxwright may give one. "cannot be kept" stays for older
// versions of nxwright, and for what newer ones still cannot keep.
const MAY_BE_LOST = "may be lost";
const CANNOT_BE_KEPT = "cannot be kept";

const REPORT_HINT = "`nxwright report` writes a report on the project file to send to " +
  "nxwright's maintainers.";

// Returns what extract does with a project, from `listed`, what
// `nxwright extract --list-unknown` printed for it.
export function extractChoice(listed: string): ExtractChoice {
  let found: UnknownContent[];
  try {
    found = listed.split("\n").filter((line) => line.trim() !== "")
      .map((line) => JSON.parse(line) as UnknownContent);
  } catch {
    return { kind: "refuse", message: "nxwright's list of the things in this project that it " +
      "does not know could not be read, so nothing was extracted." };
  }
  const cannot = found.filter((each) => each.sort === CANNOT_BE_KEPT);
  if (cannot.length > 0) {
    return { kind: "refuse", message: "This project contains things nxwright cannot keep: " +
      listedText(cannot) + ". A newer Nextion Editor may have added them. " + REPORT_HINT };
  }
  const lost = found.filter((each) => each.sort === MAY_BE_LOST);
  if (lost.length > 0) {
    return { kind: "ask", message: "This project contains things nxwright does not know, " +
      "which the next build may lose: " + listedText(lost) + ". The project may then miss " +
      "parameters the Nextion Editor needs, and may not come back the same from the Nextion " +
      "Editor. " + REPORT_HINT };
  }
  return { kind: "extract" };
}

// Returns each of `found` as "what (where)", separated by semicolons.
function listedText(found: UnknownContent[]): string {
  return found.map((each) => `${each.what} (${each.where})`).join("; ");
}
