// The text of the confirmation that nxlangPanel.ts shows before Switch to
// nxlang rewrites the project's code. It is kept apart from VS Code's API so
// that the tests can check it.

// The confirmation's detail, for a switch that changes `lines` lines of code.
export function switchConfirmationDetail(lines: number): string {
  const changes = lines === 0
    ? "Your project does not require any changes to switch to nxlang."
    : `${lines} line(s) of code will change, so that they keep calculating the same way.`;
  return `${changes} There is no command to switch back.`;
}
