// Building the pages of the extension's webviews: the page preview's
// (preview.mjs), the Attributes section's (properties.mjs), the Fonts
// panel's (fonts.mjs), and the zoom bar (zoom.mjs).

// Returns a new element of `tag`, of the class `kind` when given, holding
// `text` when given.
export function element(tag, kind = "", text = undefined) {
  const made = document.createElement(tag);
  if (kind) {
    made.className = kind;
  }
  if (text !== undefined) {
    made.textContent = text;
  }
  return made;
}
