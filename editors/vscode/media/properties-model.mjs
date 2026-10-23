// What the Attributes section (properties.mjs) shows of an attribute with
// choices, by their names, apart from the webview's page so that its tests
// run without it. An attribute's `labels` are its choices as the server
// gives them (page_editing.properties): [{value, label}], none for an
// attribute without choices.

// A value the page file gives that is none of its attribute's choices, as
// one written by hand may be: shown as it is, never changed by showing it.
const NONE_OF_THEM = "none of its choices";

// The entries of an attribute's drop-down, [{value, text, selected}]: each
// choice as its label then its number, as "global (1)", and first, a value
// that is none of them.
export function choiceEntries(attribute) {
  const entries = attribute.labels.map((choice) => ({
    value: String(choice.value),
    text: `${choice.label} (${choice.value})`,
    selected: choice.value === attribute.value,
  }));
  if (!entries.some((entry) => entry.selected)) {
    entries.unshift({ value: String(attribute.value), text: `${attribute.value} (${NONE_OF_THEM})`,
                      selected: true });
  }
  return entries;
}

// The text of an attribute shown with its value only: its choice's entry
// when it has choices, else its value.
export function valueText(attribute) {
  return attribute.labels.length > 0 ? choiceEntries(attribute).find((entry) => entry.selected).text
    : String(attribute.value);
}

// Whether the section gives an attribute a row, by its `treatment`
// (attribute_descriptions.py). A hidden one gets one only while the page
// file gives it, so that what the file holds stays in sight. A never-shown
// one never gets one.
export function listed(attribute) {
  if (attribute.treatment === "never-shown") {
    return false;
  }
  return attribute.treatment !== "hidden" || attribute.given;
}

// The page file's lines that give an attribute with a row: a problem on one
// of them shows under that row, and any other at the top of the section.
export function rowLines(attributes) {
  return new Set(attributes.filter((entry) => entry.given && listed(entry))
                           .map((entry) => entry.line));
}
