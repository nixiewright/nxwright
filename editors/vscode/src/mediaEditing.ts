// What deleting, replacing, or renaming a resource from the Media section
// asks (mediaActions.ts runs it). Deleting reads what `nxwright remove
// --report` says a removal would affect, and chooses what to ask:
//  - a resource the folder uses, by name or by its own ID, cannot be
//    deleted, and the dialog says so;
//  - the last of its kind is deleted after a plain confirmation, because no
//    ID changes;
//  - otherwise the IDs after it would change. The dialog says so, and offers
//    to leave an empty slot, a placeholder that keeps the IDs. It offers to
//    delete the resource and shift the IDs only when the folder gives none
//    of those IDs as a number.
// Kept apart from VS Code, so that its tests run without it.

// One use of a resource, as the report gives it: by name or by number, of
// the resource itself or of a later one of its kind.
export interface ResourceUse {
  path: string;
  line: number;
  text: string;
  by: "name" | "number";
  of: "itself" | "later";
}

// What `nxwright remove --report` prints.
export interface RemovalReport {
  kind: string;
  name: string;
  id: number;
  encoding: string | number;
  last: boolean;
  later: string[];
  uses: ResourceUse[];
}

// What the dialog's buttons do.
export type DeleteAction = "showUses" | "keepIds" | "shift" | "namesForNumbers" | "delete";

// The dialog Delete shows: an error or a warning, its message, more detail,
// and its buttons, the first the default.
export interface DeleteDialog {
  error: boolean;
  message: string;
  detail: string;
  buttons: { label: string; action: DeleteAction }[];
}

// Each kind's plural, as the warning names them.
const PLURALS: Record<string, string> = {
  picture: "pictures", font: "fonts", animation: "animations", video: "videos", sound: "sounds",
};
// The two-byte encodings, in which a font contains every character of the encoding.
const TWO_BYTE_ENCODINGS = ["gb2312", "big5", "shift-jis", "ks_c_5601-1987"];
// A placeholder's name, as `nxwright remove --keep-ids` gives it.
const PLACEHOLDER = /^empty-slot-[1-9][0-9]*$/;
// A resource's name: parts of letters, digits, "_" and "-", separated by "/".
const NAME = /^[A-Za-z0-9_-]+(\/[A-Za-z0-9_-]+)*$/;
// How many of the names whose IDs change the dialog lists.
const NAMES_SHOWN = 5;
// The names Windows reserves for devices, which no part of a name may be.
const DEVICE_NAMES = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i;

// Whether `name` is a placeholder's.
export function isPlaceholder(name: string): boolean {
  return PLACEHOLDER.test(name);
}

// Returns the dialog for deleting the resource of `report`. `rewroteNumbers`
// says whether Replace Numbers with Names has run on it already: then the
// numbers left are those it could not write as names.
export function deleteDialog(report: RemovalReport, rewroteNumbers = false): DeleteDialog {
  const { kind, name } = report;
  const own = report.uses.filter((use) => use.of === "itself");
  if (own.length > 0) {
    return {
      error: true,
      message: `Cannot delete the ${kind} ${name}: it is still used in ${places(own.length)}.`,
      detail: "Change or remove its uses first.",
      buttons: [{ label: "Show Uses", action: "showUses" }],
    };
  }
  if (report.last) {
    return { error: false, message: `Delete the ${kind} ${name}?`, detail: "",
             buttons: [{ label: "Delete", action: "delete" }] };
  }
  const placeholder = isPlaceholder(name);
  const keep = placeholder ? [] : [{ label: "Leave an Empty Slot", action: "keepIds" as const }];
  const shifting = `Deleting the ${kind} ${name} will change the ${changedIds(report)}.`;
  const numbers = report.uses.filter((use) => use.of === "later");
  if (numbers.length > 0) {
    const left = rewroteNumbers
      ? ` ${places(numbers.length, true)} could not be written as names: change them by hand.`
      : "";
    return {
      error: false,
      message: `${shifting} Your code or pages use some of those IDs as numbers, in ` +
        `${places(numbers.length)}.${left}`,
      detail: warningText(report, placeholder, false),
      buttons: [
        ...keep,
        ...(rewroteNumbers ? []
          : [{ label: "Replace Numbers with Names", action: "namesForNumbers" as const }]),
        { label: "Show Uses", action: "showUses" },
      ],
    };
  }
  return {
    error: false,
    message: `Delete the ${kind} ${name}?`,
    detail: `${shifting}\n\n${warningText(report, placeholder)}`,
    buttons: [...keep, { label: "Delete and Shift IDs", action: "shift" }],
  };
}

// The IDs a deletion changes: "ID of picture 3", "IDs of pictures 3 to 40".
function changedIds(report: RemovalReport): string {
  const first = report.id + 1;
  const last = report.id + report.later.length;
  const ids = first === last ? `ID of ${report.kind} ${first}`
    : `IDs of ${PLURALS[report.kind]} ${first} to ${last}`;
  return `${ids} (${namesOf(report.later)})`;
}

// The names `names`, in a list a sentence can hold: the first few, then how
// many more.
function namesOf(names: string[]): string {
  const shown = names.slice(0, NAMES_SHOWN);
  const more = names.length - shown.length;
  const listed = more > 0 ? [...shown, `${more} more`] : shown;
  return listed.length === 1 ? listed[0]
    : `${listed.slice(0, -1).join(", ")} and ${listed[listed.length - 1]}`;
}

// The warning of a deletion that changes IDs: what may then go wrong, and
// what each choice does. A placeholder is not offered one in its place.
// `offersShift` says whether the dialog offers Delete and Shift IDs.
export function warningText(report: RemovalReport, placeholder: boolean,
                            offersShift = true): string {
  const { kind, name } = report;
  const lines = [`Code that computes ${kind} IDs, or code on your microcontroller, would ` +
    `then use the wrong ${kind}.`];
  if (!placeholder) {
    let slot = `Leave an Empty Slot keeps every ID as it is: a placeholder takes ${name}'s ` +
      "place, and stays in the Media section until you fill it with Replace.";
    if (kind === "font" && TWO_BYTE_ENCODINGS.includes(String(report.encoding))) {
      slot += ` In ${report.encoding}, a placeholder font contains every character of the ` +
        "encoding, which takes many kilobytes of the screen's flash, such as about 135 KB in " +
        "gb2312.";
    }
    lines.push(slot);
  }
  if (offersShift) {
    lines.push(`Delete and Shift IDs removes ${name} completely. It is safe only when no code ` +
      `computes ${kind} IDs, and nothing outside this folder uses them.`);
  }
  return lines.join("\n\n");
}

// "1 place", "3 places"; with `capital`, starting the sentence.
function places(count: number, capital = false): string {
  const text = count === 1 ? "1 place" : `${count} places`;
  return capital ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

// Returns why `name` cannot be the new name of the resource `old`, among
// `others`, the other names of its kind; or null when it can. Names differ
// in more than letter case, as nxwright requires.
export function newNameCheck(name: string, old: string, others: string[]): string | null {
  if (name === old) {
    return `It is named ${old} already.`;
  }
  if (!NAME.test(name)) {
    return "A name can contain letters, digits, _ and -, with / between parts, such as " +
      "icons/logo.";
  }
  const device = name.split("/").find((part) => DEVICE_NAMES.test(part));
  if (device !== undefined) {
    return `${device} is reserved by Windows for a device.`;
  }
  const lower = name.toLowerCase();
  for (const other of others.filter((each) => each !== old)) {
    const otherLower = other.toLowerCase();
    if (otherLower === lower) {
      return `Another one is named ${other}.`;
    }
    // A name cannot also be the folder part of another, as "a" beside "a/b".
    if (otherLower.startsWith(`${lower}/`) || lower.startsWith(`${otherLower}/`)) {
      return `It would clash with ${other}: one name cannot be the folder of another.`;
    }
  }
  return null;
}

// Turns the arguments of a command adding a resource, as mediaCommands.ts
// gives them, ["animation", folder, ...files and options], into those of
// `nxwright replace`, which puts it in the place of the resource `name`,
// named `newName` when given.
export function replaceArguments(addArguments: string[], name: string,
                                 newName?: string): string[] {
  const [kind, folder, ...rest] = addArguments;
  return ["replace", folder, kind, name, ...rest,
          ...(newName === undefined ? [] : ["--name", newName])];
}
