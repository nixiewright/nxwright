// The parts of page locking that do not need VS Code, kept apart so that
// their tests can run without it: how the Pages section shows a page, and
// the check of a password typed for a lock.
import { itemContextValue, ObjectEvent } from "./eventMenu";

// Returns how the Pages section shows the page `name`. A page in `locked`
// gets a padlock. The menus in package.json pick the items of the page's
// right-click menu by its context value, which depends on whether the page
// is locked and on its `events`.
export function pageItemLook(name: string, locked: ReadonlySet<string>,
                             events: readonly ObjectEvent[] = []):
    { contextValue: string; padlock: boolean } {
  const isLocked = locked.has(name);
  return { contextValue: itemContextValue(isLocked ? "lockedPage" : "page", events),
           padlock: isLocked };
}

// Returns what is wrong with a password typed for a page's lock, or
// undefined when nothing is. The Nextion Editor hashes the password as
// ASCII, and so does password_hash in nxwright/project/device_settings.py.
export function passwordProblem(password: string): string | undefined {
  if (password === "") {
    return "Type a password, or choose Lock page for a lock without one.";
  }
  if (!/^[\x00-\x7f]*$/.test(password)) {
    return "Use only ASCII characters. The Nextion Editor may refuse others when it " +
      "opens the project.";
  }
  return undefined;
}
