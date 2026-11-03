// Turns a page's name into the form that nxwright uses in the names of the
// page's files, `pages/<name>.page.toml` and `pages/<name>.nx`
// (nxwright/project/page_file_names.py). This module does not use VS Code,
// so that its tests can run without VS Code.

// The characters that are encoded: the ones Windows refuses in a file name,
// control characters, and `%`, because `%` starts an encoded character.
const ENCODED = /[%\\/:*?"<>|\x00-\x1f]/g;

// Returns the page `name` as it appears in the names of the page's files,
// without their suffix. Each character that ENCODED matches becomes `%` and
// its two hexadecimal digits: `a:b` becomes `a%3Ab`. Every other character,
// a space among them, stays as it is.
export function pageFileStem(name: string): string {
  return name.replace(ENCODED, (character) =>
    "%" + character.charCodeAt(0).toString(16).toUpperCase().padStart(2, "0"));
}
