// The questions the extension asks before deleting, cutting, or moving
// components of a page. They warn when code still uses the name of a
// deleted component, when its code stays in a file other pages include
// too, and when the IDs of other components change. A
// component's ID is its place on its page. The microcontroller's code may
// rely on it, and so may screen code that uses IDs as numbers.
// pageEditing.ts shows the questions. This file does not import VS Code,
// so that its tests can run without it.

// The button that turns the warning about IDs off, through the setting
// nxwright.warnWhenComponentIdsChange.
export const DONT_WARN_AGAIN = "Don't Warn Again";

// A question for a modal dialog: its message, an optional detail, and its
// buttons. The first button goes ahead with the action. VS Code adds Cancel
// itself.
export interface Question {
  message: string;
  detail?: string;
  buttons: string[];
}

// Returns the components whose IDs change when `names` are deleted: those
// that come after the first deleted one and are not deleted themselves.
// `order` lists the page's components in ID order, without the page itself.
export function shiftedByDeleting(order: string[], names: string[]): string[] {
  const deleted = new Set(names);
  const first = order.findIndex((name) => deleted.has(name));
  return first < 0 ? [] : order.slice(first).filter((name) => !deleted.has(name));
}

// Returns the question to ask before deleting the components `names`, or
// undefined when there is nothing to ask. `verb` is "Delete" or "Cut", and
// is used in the question and on its first button. `namedElsewhere` lists
// the places where code that is not deleted still uses the name of one of
// them, such as "pages/home.nx line 3".
// `shifted` lists the components whose IDs change, from shiftedByDeleting.
// `warnIds` is the value of nxwright.warnWhenComponentIdsChange.
// `sharedFiles` lists the files other pages include too that hold some of
// their code. That code stays, and this page is built without it.
export function deleteQuestion(verb: string, names: string[], namedElsewhere: string[],
                               shifted: string[], warnIds: boolean,
                               sharedFiles: string[] = []): Question | undefined {
  const ids = warnIds && shifted.length > 0;
  if (namedElsewhere.length === 0 && !ids && sharedFiles.length === 0) {
    return undefined;
  }
  const what = names.length === 1 ? names[0] : names.join(", ");
  const count = namedElsewhere.length === 1 ? "1 place" : `${namedElsewhere.length} places`;
  const message = namedElsewhere.length > 0
    ? `The project will no longer build: code still uses ${what} in ${count} ` +
      `(${namedElsewhere.slice(0, 5).join(", ")}${namedElsewhere.length > 5 ? ", ..." : ""}). ` +
      `${verb} anyway?`
    : `${verb} ${what}?`;
  const details: string[] = [];
  if (sharedFiles.length > 0) {
    const files = sharedFiles.length === 1 ? "that file" : "those files";
    details.push(`${names.length === 1 ? `${what}'s` : "Their"} code in ` +
      `${sharedFiles.join(", ")} stays, because other pages include ${files}. This page ` +
      `still includes ${files}, and will be built without that code.`);
  }
  if (ids) {
    const changed = shifted.length === 1 ? "the ID of 1 component"
      : `the IDs of ${shifted.length} components`;
    details.push(`This will change ${changed} after ${names.length === 1 ? "it" : "them"} ` +
      `on the page. ${RISK}`);
  }
  return {
    message,
    ...(details.length > 0 ? { detail: details.join("\n\n") } : {}),
    buttons: ids ? [verb, DONT_WARN_AGAIN] : [verb],
  };
}

// The question asked before moving the components `names` to another place
// in their page's order, which changes their IDs and those of the
// components they pass.
export function moveQuestion(names: string[]): Question {
  const what = names.length === 1 ? names[0] : names.join(", ");
  return {
    message: `Move ${what}?`,
    detail: `This will change the IDs of components on the page. ${RISK}`,
    buttons: ["Move", DONT_WARN_AGAIN],
  };
}

// What may go wrong when IDs change.
const RISK = "Your microcontroller's code, or code that uses their IDs as numbers, may then " +
  "use the wrong component.";
