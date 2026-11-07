// The question and the note that "Clear events" shows. This module does not
// use VS Code, so that its tests can run without VS Code.

// Asked before clearing the code of several components.
export function clearEventsQuestion(names: readonly string[]): string {
  return `Remove the code of every event of ${names.join(", ")}? The components stay.`;
}

// Said when none of the components `names` has code to clear.
export function nothingToClearNote(names: readonly string[]): string {
  return names.length === 1 ? `${names[0]} has no code to clear.`
    : `None of ${names.join(", ")} has code to clear.`;
}
