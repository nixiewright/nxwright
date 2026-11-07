// The text that the Switch to nxlang panel (nxlang-panel.mjs) shows about
// the lines the switch will change. It is kept out of the page so that the
// tests can check it.

// The sentence the panel shows about `changes`. When there are changes, the
// sentence is the label of their folded list.
export function changesSummary(changes) {
  return changes.length === 0
    ? "Your project does not require any changes to switch to nxlang."
    : "Expand to see the lines that will change in your project";
}
