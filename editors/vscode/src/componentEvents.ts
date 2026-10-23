// What "Go to Event..." lists for a component, its events in its type's
// order (page_editing.component_events), and what "Clear events" says.
// Kept apart from VS Code, so that its tests run without it.

// An event of a component, as nxwright/componentEvents gives it.
export interface ComponentEvent {
  event: string;
  // The file holding its code, or null when it has none.
  uri: string | null;
}

// A choice of the list.
export interface EventChoice {
  label: string;
  // The name of the file holding its code, or that it has none yet.
  description: string;
  event: string;
}

// The choices for `events`, in their order.
export function eventChoices(events: readonly ComponentEvent[]): EventChoice[] {
  return events.map((found) => ({
    label: found.event,
    description: found.uri ? fileName(found.uri) : "no code yet",
    event: found.event,
  }));
}

// Said for a component whose type has no events, such as a variable.
export function noEventsNote(name: string): string {
  return `${name} has no events: its type has none.`;
}

// Asked before clearing the code of several components.
export function clearEventsQuestion(names: readonly string[]): string {
  return `Remove the code of every event of ${names.join(", ")}? The components stay.`;
}

// Said when none of the components `names` has code to clear.
export function nothingToClearNote(names: readonly string[]): string {
  return names.length === 1 ? `${names[0]} has no code to clear.`
    : `None of ${names.join(", ")} has code to clear.`;
}

// The name of the file a URI names, such as page0.nx.
function fileName(uri: string): string {
  return decodeURIComponent(uri.slice(uri.lastIndexOf("/") + 1));
}
