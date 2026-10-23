// What Paste Special asks, and what it sends once some choices are picked:
// the parts of one copied component it applies to the selected ones
// (page_components.paste_parts), or, opened on the page itself, what new
// copies of the copied components bring. Kept apart from VS Code, so that
// its tests run without it.

// A choice of the question: a part, by the name the server's paste of
// parts takes, which new copies' choices share, and whether it is ticked
// as the question opens.
export interface PartChoice {
  label: string;
  description: string;
  part: string;
  picked?: boolean;
}

// The parts, in the order the question lists them.
export const PART_CHOICES: readonly PartChoice[] = [
  { label: "Size", description: "its width and height", part: "size" },
  { label: "Position", description: "its x and y", part: "position" },
  { label: "Other attributes",
    description: "everything else both types share, except the name, lock, and group",
    part: "attributes" },
  { label: "Code", description: "its event code, replacing the code for the same events",
    part: "code" },
];

// Said when the clipboard holds no single component's table.
export const ONE_COMPONENT = "Paste Special works with one copied component. Copy just one " +
  "component first.";

// Said when Paste Special, opened on the page itself, finds no component's
// table on the clipboard.
export const NO_COMPONENTS = "There are no copied components to paste. Copy some components first.";

// How many components' tables the clipboard's `text` holds, by their
// [[component]] lines, so that Paste Special can refuse before it asks. The
// server reads the tables themselves (page_components.paste_parts).
export function copiedTableCount(text: string): number {
  return text.split(/\r?\n/).filter((line) => /^\s*\[\[component\]\]\s*(#.*)?$/.test(line))
    .length;
}

// Said when code is picked but no longer at hand.
export const CODE_NOT_AT_HAND = "The code wasn't pasted, because nxwright keeps a copied " +
  "component's code only until you copy something else. Copy the component again to paste its " +
  "code.";

// What Paste Special sends for the parts `picked`, the copied component's
// code being `code`, or undefined when the clipboard no longer holds what
// was copied last: the parts and the code, and what to say when code was
// picked but is not at hand, the other parts being pasted all the same.
export function partsToPaste(picked: readonly PartChoice[], code: readonly string[] | undefined):
    { parts: string[]; code: string[]; note?: string } {
  const parts = picked.map((choice) => choice.part);
  if (!parts.includes("code")) {
    return { parts, code: [] };
  }
  if (code === undefined) {
    return { parts: parts.filter((part) => part !== "code"), code: [], note: CODE_NOT_AT_HAND };
  }
  return { parts, code: [...code] };
}

// The point clicked, on the grid, where the menu opened on the page.
export interface Point {
  x: number;
  y: number;
}

// The choices for new copies: their size and other attributes always come
// with them, so only their position and their code are asked. Code is
// ticked at first while it is at hand, `codeAtHand`.
export function copyChoices(codeAtHand: boolean): PartChoice[] {
  return [
    { label: "Position",
      description: "exactly where they were copied from, even over the originals",
      part: "position", picked: false },
    { label: "Code", description: "their event code", part: "code", picked: codeAtHand },
  ];
}

// What Paste Special sends for new copies, the choices `picked` of
// copyChoices, the copied components' code being `code`, or undefined when
// it is not at hand: where they go, as nxwright/pasteComponents takes it,
// the code, and what to say when code was picked but is not at hand. With
// position picked, they go where they were copied from; else to `point`,
// the point clicked, when the menu gives one; else where Paste puts them.
export function copiesToPaste(picked: readonly PartChoice[], code: readonly string[] | undefined,
                              point?: Point):
    { place: { inPlace?: boolean; at?: Point }; code: string[]; note?: string } {
  const pasted = partsToPaste(picked, code);
  const place = pasted.parts.includes("position") ? { inPlace: true } : point ? { at: point } : {};
  return pasted.note === undefined ? { place, code: pasted.code }
                                   : { place, code: pasted.code, note: pasted.note };
}
