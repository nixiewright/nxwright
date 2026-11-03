// A page's name in the names of its files, `pages/<name>.page.toml` and
// `pages/<name>.nx`, as nxwright writes them (nxwright/project/
// page_file_names.py). Kept apart from VS Code, so that its tests run
// without it.

// The characters Windows refuses in a file name, `%`, which starts an
// encoded character, and control characters.
const ENCODED = /[%\\/:*?"<>|\x00-\x1f]/g;

// Returns the page `name` as its files' names give it, without their
// suffix: each character of ENCODED as `%` and its two hexadecimal digits,
// so `a:b` gives `a%3Ab`. A plain name, or one with a space, is unchanged.
export function pageFileStem(name: string): string {
  return name.replace(ENCODED, (character) =>
    "%" + character.charCodeAt(0).toString(16).toUpperCase().padStart(2, "0"));
}
