// Makes the keys and conditions for the Go to Event submenu, in the
// right-click menus of the page preview and of the Components section.
// VS Code menus are fixed in package.json, so each event name has two
// commands there: one for an event without code, and one with ✓ in its
// title for an event with code. This module makes keys from an object's
// events, and each command shows only when the object has the command's key.
// The page preview sets the keys in the menu's context, and the Components
// section puts them in each item's context value.
// When no event can be added to an object, because it or its page is locked,
// its commands for events without code are greyed out.
// This module does not use VS Code, so that its tests can check the keys
// against package.json.

// An object's event, as nxwright/pageObjects gives it.
export interface ObjectEvent {
  event: string;
  hasCode: boolean;
}

// Every event name a type can have, in the order that every type lists its
// events. The submenu shows them in this order.
export const EVENT_NAMES = ["load", "loadend", "down", "up", "slide", "playend", "timer",
                            "unload"];

// The key set when an object has any events. The submenu shows only when
// it is set.
export const HAS_EVENTS = "hasEvents";

// The key set when an object has events, and events can be added to it. The
// commands for events without code are enabled only when it is set.
export const CAN_ADD_EVENTS = "canAddEvents";

// The id of the command that opens `event`, for an event with or without code.
export function eventCommand(event: string, hasCode: boolean): string {
  return `nxwright.event.${event}${hasCode ? ".withCode" : ""}`;
}

// The title of the command for `event`: the event's name, with ✓ when it
// has code.
export function eventCommandTitle(event: string, hasCode: boolean): string {
  return hasCode ? `${event} ✓` : event;
}

// The key set when an object has `event`, such as `codeUp` for an up event
// with code, or `noCodeUp` for one without.
function eventKey(event: string, hasCode: boolean): string {
  return `${hasCode ? "code" : "noCode"}${event[0].toUpperCase()}${event.slice(1)}`;
}

// The keys for an object's `events`, each set to true. `eventsLocked` is
// true when no event can be added to the object. A folder's defaults.toml
// can give a type an event that is not in EVENT_NAMES. Such an event has no
// command, and is left out.
export function eventMenuKeys(events: readonly ObjectEvent[],
                              eventsLocked = false): Record<string, true> {
  const keys: Record<string, true> = {};
  for (const found of events.filter((each) => EVENT_NAMES.includes(each.event))) {
    keys[HAS_EVENTS] = true;
    if (!eventsLocked) {
      keys[CAN_ADD_EVENTS] = true;
    }
    keys[eventKey(found.event, found.hasCode)] = true;
  }
  return keys;
}

// The context value of a Components section item: its kind, "page" or
// "component", then the keys for its events, separated by spaces.
export function itemContextValue(kind: string, events: readonly ObjectEvent[],
                                 eventsLocked = false): string {
  return [kind, ...Object.keys(eventMenuKeys(events, eventsLocked))].join(" ");
}

// The condition, in package.json, of a Components section item of `kind`,
// whatever its events.
export function itemKindCondition(kind: string): string {
  return `viewItem =~ /^${kind}( |$)/`;
}

// The condition, in package.json, that a Components section item has `key`.
export function itemKeyCondition(key: string): string {
  return `viewItem =~ /(^| )${key}( |$)/`;
}

// The condition, in package.json, that shows the command for `event` with or
// without code. It is true when the page preview's menu sets the event's key,
// or when the key is a word of a Components section item's context value.
export function eventCommandCondition(event: string, hasCode: boolean): string {
  const key = eventKey(event, hasCode);
  return `${key} || ${itemKeyCondition(key)}`;
}

// The enablement, in package.json, of the commands for events without code.
// It is true when the page preview's menu sets CAN_ADD_EVENTS, or when
// CAN_ADD_EVENTS is a word of a Components section item's context value.
export function addEventEnablement(): string {
  return `${CAN_ADD_EVENTS} || ${itemKeyCondition(CAN_ADD_EVENTS)}`;
}
