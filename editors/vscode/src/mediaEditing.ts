// What deleting, replacing, or renaming a resource from the Media section
// asks (mediaActions.ts runs it). Deleting asks one question. It is built
// from what the extension already knows about the project, so it shows
// immediately, without a search of the folder first:
//  - if the resource is the last of its kind, no ID changes, and the
//    question is a plain confirmation;
//  - otherwise the IDs after the resource would change. The question warns
//    about that change, and offers three choices: leave an empty slot (a
//    placeholder that keeps the IDs), delete the resource and shift the IDs,
//    or first replace the numbers that give those IDs with names.
// Kept apart from VS Code, so that its tests run without it.

// What Delete deletes, as app.toml lists it: a page or a resource of `kind`,
// its ID, the names after it in its list, and the folder's encoding, which
// is undefined for a folder without device settings.
export interface DeleteTarget {
  kind: string;
  name: string;
  id: number;
  later: string[];
  encoding: string | number | undefined;
}

// What the question's buttons do.
export type DeleteAction = "keepIds" | "shift" | "namesForNumbers" | "delete";

// The question Delete asks: its message, more detail, and its buttons, the
// first the default.
export interface DeleteDialog {
  message: string;
  detail: string;
  buttons: { label: string; action: DeleteAction }[];
}

// Each kind's plural, as the warning names them.
const PLURALS: Record<string, string> = {
  picture: "pictures", font: "fonts", animation: "animations", video: "videos", sound: "sounds",
  page: "pages",
};
// The two-byte encodings, in which a font contains every character of the encoding.
const TWO_BYTE_ENCODINGS = ["gb2312", "big5", "shift-jis", "ks_c_5601-1987"];
// The names that `nxwright remove --keep-ids` gives a placeholder resource
// and an empty slot page. A page's name has underscores, so that code can
// use it.
const PLACEHOLDER = /^empty-slot-[1-9][0-9]*$/;
const EMPTY_SLOT_PAGE = /^empty_slot_[1-9][0-9]*$/;
// A resource's name: parts of letters, digits, "_" and "-", separated by "/".
const NAME = /^[A-Za-z0-9_-]+(\/[A-Za-z0-9_-]+)*$/;
// How many of the names whose IDs change the dialog lists.
const NAMES_SHOWN = 5;
// The names Windows reserves for devices, which no part of a name may be.
const DEVICE_NAMES = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i;

// Whether `name` is the name of a placeholder, or, when `kind` is "page",
// of an empty slot page.
export function isPlaceholder(name: string, kind?: string): boolean {
  return (kind === "page" ? EMPTY_SLOT_PAGE : PLACEHOLDER).test(name);
}

// Returns what Delete deletes: the page or the resource `name` of `kind`.
// `names` is its list in app.toml, and `encoding` is the folder's encoding.
// Returns undefined when `names` does not have the name.
export function deleteTarget(kind: string, name: string, names: string[],
                             encoding: string | number | undefined): DeleteTarget | undefined {
  const id = names.indexOf(name);
  return id < 0 ? undefined : { kind, name, id, later: names.slice(id + 1), encoding };
}

// Returns the question for deleting `target`. If `rewroteNumbers` is true,
// Replace Numbers with Names has already run for `target`, and the question
// no longer offers that button.
export function deleteDialog(target: DeleteTarget, rewroteNumbers = false): DeleteDialog {
  const { kind, name } = target;
  const message = `Delete the ${kind} ${name}?`;
  if (target.later.length === 0) {
    return { message, detail: "", buttons: [{ label: "Delete", action: "delete" }] };
  }
  const placeholder = isPlaceholder(name, kind);
  return {
    message,
    detail: `Deleting the ${kind} ${name} will change the ${changedIds(target)}.\n\n` +
      warningText(target, placeholder, !rewroteNumbers),
    buttons: [
      ...(placeholder ? [] : [{ label: "Leave an Empty Slot", action: "keepIds" as const }]),
      { label: "Delete and Shift IDs", action: "shift" },
      ...(rewroteNumbers ? []
        : [{ label: "Replace Numbers with Names", action: "namesForNumbers" as const }]),
    ],
  };
}

// Returns the arguments of the `nxwright remove` that deletes `target` from
// `folder`. With `keepIds`, it leaves an empty slot. With `checked`, the
// command first looks for what uses the target, and deletes nothing while
// the folder uses it.
export function removeArguments(folder: string, target: DeleteTarget, keepIds: boolean,
                                checked: boolean): string[] {
  return ["remove", folder, target.kind, target.name, ...(keepIds ? ["--keep-ids"] : []),
          ...(checked ? ["--checked"] : [])];
}

// The IDs a deletion changes: "ID of picture 3", "IDs of pictures 3 to 40".
function changedIds(target: DeleteTarget): string {
  const first = target.id + 1;
  const last = target.id + target.later.length;
  const ids = first === last ? `ID of ${target.kind} ${first}`
    : `IDs of ${PLURALS[target.kind]} ${first} to ${last}`;
  return `${ids} (${namesOf(target.later)})`;
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
// what each choice does. Deleting a placeholder or an empty slot page does
// not offer to leave another in its place.
// `offersNames` is true if the question offers Replace Numbers with Names.
export function warningText(target: DeleteTarget, placeholder: boolean,
                            offersNames: boolean): string {
  const { kind, name } = target;
  const lines = [`Numbers in your code or pages that give those IDs, and code on your ` +
    `microcontroller that uses them, will then point to the wrong ${kind}.`];
  if (!placeholder) {
    let slot = kind === "page"
      ? `Leave an Empty Slot keeps every ID as it is: a blank page takes ${name}'s place, ` +
        "and you can reuse it by renaming it and adding components."
      : `Leave an Empty Slot keeps every ID as it is: a placeholder takes ${name}'s ` +
        "place, and stays in the Media section until you fill it with Replace.";
    if (kind === "font" && TWO_BYTE_ENCODINGS.includes(String(target.encoding))) {
      slot += ` In ${target.encoding}, a placeholder font contains every character of the ` +
        "encoding, which takes many kilobytes of the screen's flash, such as about 135 KB in " +
        "gb2312.";
    }
    lines.push(slot);
  }
  lines.push(`Delete and Shift IDs removes ${name} completely. It is safe only when no code ` +
    `gives or computes those IDs as numbers, and nothing outside this folder uses them.`);
  if (offersNames) {
    lines.push("Replace Numbers with Names first replaces the numbers that give those IDs " +
      "with names, where it can. It reads your whole project, so it can take a while.");
  }
  return lines.join("\n\n");
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
