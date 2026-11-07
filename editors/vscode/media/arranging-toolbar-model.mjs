// The buttons of the page preview's arranging toolbar, kept apart from the
// webview so that Node's test runner can check them. Each button does what
// one command of the preview's right-click menu does (package.json), and is
// enabled when that command's menu item would show.

// How many components must be selected for each context key of the
// right-click menu to be set (setMenuContext in media/preview.mjs). For `component`,
// every selected component except the page counts. For the other keys,
// only components with a place on the page count.
const LEAST_SELECTED = { component: 1, several: 2, spaceable: 3 };

// Returns a button that moves the selected components up or down the ID
// order, toward `direction`: "front", "forward", "backward", or "back".
function ordering(glyph, title, command, direction) {
  return { glyph, title, command, needs: "component", direction };
}

// Returns a button that applies arrangement `how` (arranging.mjs's
// `arrangement`) to the selected components that have a place on the page.
function arranging(glyph, title, command, needs, how) {
  return { glyph, title, command, needs, how };
}

// The buttons, in groups that the toolbar keeps apart. `glyph` is the
// button's picture (media/glyphs.mjs), `title` its tooltip, `command` the
// menu command it matches, and `needs` the context key of the menu that must
// be set for the button to be enabled.
export const TOOLBAR_GROUPS = [
  [
    ordering("bringToFront", "Bring to front", "nxwright.bringToFront", "front"),
    ordering("bringForward", "Bring forward", "nxwright.bringForward", "forward"),
    ordering("sendBackward", "Send backward", "nxwright.sendBackward", "backward"),
    ordering("sendToBack", "Send to back", "nxwright.sendToBack", "back"),
  ],
  [
    arranging("alignLeft", "Align left edges", "nxwright.alignLeft", "several", "left"),
    arranging("alignRight", "Align right edges", "nxwright.alignRight", "several", "right"),
    arranging("alignTop", "Align top edges", "nxwright.alignTop", "several", "top"),
    arranging("alignBottom", "Align bottom edges", "nxwright.alignBottom", "several", "bottom"),
    arranging("alignCentresAcross", "Align centres, left to right",
              "nxwright.alignCentresAcross", "several", "centreAcross"),
    arranging("alignCentresDown", "Align centres, top to bottom",
              "nxwright.alignCentresDown", "several", "centreDown"),
  ],
  [
    arranging("sameWidth", "Make the same width", "nxwright.sameWidth", "several", "sameWidth"),
    arranging("sameHeight", "Make the same height", "nxwright.sameHeight", "several",
              "sameHeight"),
    arranging("sameSize", "Make the same width and height", "nxwright.sameSize", "several",
              "sameSize"),
  ],
  [
    arranging("spaceAcross", "Make horizontal spacing equal", "nxwright.spaceAcross",
              "spaceable", "spaceAcross"),
    arranging("increaseSpacingAcross", "Increase horizontal spacing",
              "nxwright.increaseHorizontalSpacing", "several", "increaseSpacingAcross"),
    arranging("decreaseSpacingAcross", "Decrease horizontal spacing",
              "nxwright.decreaseHorizontalSpacing", "several", "decreaseSpacingAcross"),
    arranging("spaceDown", "Make vertical spacing equal", "nxwright.spaceDown",
              "spaceable", "spaceDown"),
    arranging("increaseSpacingDown", "Increase vertical spacing",
              "nxwright.increaseVerticalSpacing", "several", "increaseSpacingDown"),
    arranging("decreaseSpacingDown", "Decrease vertical spacing",
              "nxwright.decreaseVerticalSpacing", "several", "decreaseSpacingDown"),
  ],
];

// Returns whether `entry`, a button of TOOLBAR_GROUPS, is enabled for
// `selection`. `selection` is { components, placed, pageLocked }: the
// number of selected components other than the page, how many of those
// have a place on the page, and whether the page is locked. Before the
// first drawing there is no selection, and no button is enabled.
export function isEnabled(entry, selection) {
  if (!selection || selection.pageLocked) {
    return false;
  }
  const counted = entry.needs === "component" ? selection.components : selection.placed;
  return counted >= LEAST_SELECTED[entry.needs];
}
