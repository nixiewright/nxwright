// What setting a component's `key` in the properties panel does, from the
// language server's answer to nxwright/keyBinding (page_editing.py). Kept
// apart from VS Code, so that its tests run without it.

// The server's answer: the keyboard of nxwright's that the key opens, or
// null, as for Chinese input in a folder of another encoding than gb2312;
// whether the folder has it already; whether the key opens a keyboard and
// the component is of local scope, which a keyboard does not take; whether
// it opens Chinese input; and the folder's fonts that the Chinese keyboard
// takes.
export interface KeyBinding {
  keyboard: string | null;
  present: boolean;
  local: boolean;
  chinese: boolean;
  fonts: string[];
}

// What to do: first ask `question`, when there is one, and do nothing more
// unless it is confirmed; then add the keyboard page `keyboard`, when there
// is one; then set `values`; then say `note`, when there is one.
export interface KeyChange {
  question: string | null;
  values: Record<string, unknown>;
  keyboard: string | null;
  note: string | null;
}

// The steps of a key change, as VS Code takes them. Each one that fails, or
// is refused, says why itself.
export interface KeySteps {
  appTomlUnsaved(): boolean;
  confirm(question: string): Promise<boolean>;
  addKeyboard(keyboard: string): Promise<boolean>;
  setAttributes(values: Record<string, unknown>): Promise<boolean>;
  tell(note: string): void;
}

// `key` is the value as typed, which the server has read already.
export function keyChange(name: string, key: unknown, binding: KeyBinding): KeyChange {
  return {
    question: binding.local
      ? `A keyboard opens only from a component of global scope. Make ${name} global?`
      : null,
    // A component of local scope is made global along with its key.
    values: binding.local ? { key, vscope: 1 } : { key },
    keyboard: binding.keyboard !== null && !binding.present ? binding.keyboard : null,
    note: binding.chinese && binding.keyboard === null
      ? "nxwright's Chinese keyboard only works in a gb2312 project. To use it, change the "
        + "project's encoding with \"Change the character encoding\"."
      : null,
  };
}

// Makes `change`, and returns whether the key was set. Nothing changes when
// a keyboard is to be added while app.toml has unsaved changes, when the
// question is not confirmed, or when the keyboard cannot be added.
export async function makeKeyChange(change: KeyChange, steps: KeySteps): Promise<boolean> {
  if (change.keyboard && steps.appTomlUnsaved()) {
    return false;
  }
  if (change.question && !(await steps.confirm(change.question))) {
    return false;
  }
  // The keyboard first, so that a refusal to add it leaves the key as it was.
  if (change.keyboard && !(await steps.addKeyboard(change.keyboard))) {
    return false;
  }
  if (!(await steps.setAttributes(change.values))) {
    return false;
  }
  if (change.note) {
    steps.tell(change.note);
  }
  return true;
}
