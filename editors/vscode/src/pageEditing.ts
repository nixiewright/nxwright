// The edits of a page that its preview and nxwright's side bar make: setting
// attributes, renaming an object, opening an object's default event or the
// event picked, and adding, deleting, clearing the code of, copying,
// pasting, placing, reordering, locking, and grouping components, and
// pasting parts of one onto others, or new copies with or without their
// position and code. The
// language server computes each edit (source/page_edits.py, page_components.py);
// it is applied through
// VS Code, so that undo works and the files are saved as usual. A key that
// opens a keyboard the folder lacks also adds its page: the server writes
// those files, since a font is no text an edit can hold.
import * as vscode from "vscode";
import {
  LanguageClient,
  WorkspaceEdit as ProtocolWorkspaceEdit,
} from "vscode-languageclient/node";
import { chineseFontChoices, chineseFontParameters } from "./chineseKeyboard";
import {
  ComponentEvent,
  clearEventsQuestion,
  eventChoices,
  noEventsNote,
  nothingToClearNote,
} from "./componentEvents";
import { KeyBinding, keyChange, makeKeyChange } from "./keyBinding";
import { PageObject, PREVIEW_VIEW_TYPE } from "./pages";
import {
  NO_COMPONENTS,
  ONE_COMPONENT,
  PART_CHOICES,
  Point,
  copiedTableCount,
  copiesToPaste,
  copyChoices,
  partsToPaste,
} from "./pasteParts";
import { appTomlUnsaved } from "./unsavedChanges";
import { errorText } from "./userMessages";

const MAKE_GLOBAL = "Make it global";
const DELETE = "Delete";
const CLEAR_EVENTS = "Clear events";

// Where Paste puts the copies: with `at`, the box holding those with a
// place has its top left corner there; `inPlace`, where they were copied
// from; else where page_components.paste_components puts them.
export interface PastePlace {
  at?: { x: number; y: number };
  inPlace?: boolean;
}

// A type a component can have, as nxwright/componentTypes lists it.
export interface ComponentType {
  type: string;
  // Whether it has a place on the screen.
  placed: boolean;
}

// The server's reply to nxwright/addComponent.
interface AddedComponent {
  edit: unknown;
  name: string;
}

// The server's reply to nxwright/deleteComponents.
interface DeletedComponents {
  edit: unknown;
  namedElsewhere: { uri: string; line: number }[];
}

// Components as copied: their tables, which the clipboard holds, and the
// code of their events, a text per event (nxwright/copyComponents).
interface CopiedComponents {
  text: string;
  code: string[];
}

// The server's reply to nxwright/pasteComponents.
interface PastedComponents {
  edit: unknown;
  names: string[];
}

// The server's reply to nxwright/pasteParts.
interface PastedParts {
  edit: unknown;
  // What was left out, a sentence each.
  notes: string[];
}

// The server's reply to nxwright/addKeyboard.
interface AddedKeyboard {
  page: string;
  font: string;
  warning: string | null;
}

// The server's reply to nxwright/componentProperties (page_editing.py).
export interface Properties {
  name: string;
  firstLine: number;
  lastLine: number;
  nameLine: number;
  nameCharacter: number;
  [key: string]: unknown;
}

// The server's reply to nxwright/defaultEvent, for a type with events.
interface DefaultEvent {
  uri: string;
  line: number;
  character: number;
  edit: unknown;
}

export class PageEditing {
  // The last components copied. The clipboard holds only their tables; a
  // paste of that same text brings their code too.
  private lastCopy: CopiedComponents | undefined;

  constructor(private readonly client: () => LanguageClient | undefined) {}

  // Sets attributes of an object of the page whose .page.toml file is `toml`,
  // each colour the nearest the screen holds with `nearestColours`, as for
  // a colour picked. Returns whether the page file changed; says why when
  // it did not.
  async setAttributes(toml: vscode.Uri, name: string, values: Record<string, unknown>,
                      nearestColours = false): Promise<boolean> {
    const client = this.client();
    if (!client) {
      return false;
    }
    try {
      const edit = await client.sendRequest("nxwright/setAttributes", {
        textDocument: { uri: toml.toString() },
        name,
        values,
        nearestColours,
      });
      return await this.apply(client, toml, edit);
    } catch (error) {
      void vscode.window.showErrorMessage(`nxwright: ${errorText(error)}`);
      return false;
    }
  }

  // Sets an object's `key`, as `value` is typed. A key opening a keyboard
  // asks first to make a component of local scope global, and adds the
  // keyboard's page when the folder lacks it (keyBinding.ts). Returns
  // whether the page file changed; says why when it did not.
  async setKey(toml: vscode.Uri, name: string, value: unknown): Promise<boolean> {
    const client = this.client();
    if (!client) {
      return false;
    }
    const document = { uri: toml.toString() };
    let binding: KeyBinding;
    try {
      // The server reads the value, and refuses what is no key, saying why.
      binding = await client.sendRequest<KeyBinding>("nxwright/keyBinding", {
        textDocument: document,
        name,
        key: value,
      });
    } catch (error) {
      void vscode.window.showErrorMessage(`nxwright: ${errorText(error)}`);
      return false;
    }
    // The page file is pages/<page>.page.toml in its source folder.
    const folder = vscode.Uri.joinPath(toml, "..", "..");
    return makeKeyChange(keyChange(name, value, binding), {
      appTomlUnsaved: () => appTomlUnsaved(folder, "adding a keyboard page"),
      confirm: async (question) => await vscode.window.showWarningMessage(
        question, { modal: true }, MAKE_GLOBAL) === MAKE_GLOBAL,
      addKeyboard: (keyboard) => this.addKeyboard(client, document, keyboard, binding.fonts),
      setAttributes: (values) => this.setAttributes(toml, name, values),
      tell: (note) => void vscode.window.showInformationMessage(`nxwright: ${note}`),
    });
  }

  // Adds nxwright's page of `keyboard` to the source folder of `document`,
  // the Chinese keyboard with the font asked for, among the folder's `fonts`
  // or from a typeface file. Returns whether it was added; says why when it
  // was not.
  private async addKeyboard(client: LanguageClient, document: { uri: string },
                            keyboard: string, fonts: string[]): Promise<boolean> {
    const font = keyboard === "chinese-input" ? await askChineseFont(fonts) : {};
    if (!font) {
      return false;
    }
    try {
      const added = await client.sendRequest<AddedKeyboard>("nxwright/addKeyboard", {
        textDocument: document,
        keyboard,
        ...font,
      });
      void vscode.window.showInformationMessage(
        `nxwright: added the keyboard page ${added.page}, with the font ${added.font}.`);
      if (added.warning) {
        void vscode.window.showWarningMessage(`nxwright: ${added.warning}`);
      }
      return true;
    } catch (error) {
      void vscode.window.showErrorMessage(`nxwright: ${errorText(error)}`);
      return false;
    }
  }

  // Renames an object as Rename Symbol does, so that its code follows.
  // Returns whether it was renamed; says why when it was not.
  async rename(toml: vscode.Uri, name: string, newName: string): Promise<boolean> {
    const client = this.client();
    if (!client || !newName || newName === name) {
      return false;
    }
    try {
      const properties = await client.sendRequest<Properties>("nxwright/componentProperties", {
        textDocument: { uri: toml.toString() },
        name,
      });
      const edit = await vscode.commands.executeCommand<vscode.WorkspaceEdit>(
        "vscode.executeDocumentRenameProvider",
        toml,
        new vscode.Position(properties.nameLine, properties.nameCharacter),
        newName,
      );
      return !!edit && (await this.applyShown(toml, edit));
    } catch (error) {
      void vscode.window.showErrorMessage(`nxwright: ${errorText(error)}`);
      return false;
    }
  }

  // Returns the types a component of the page can have, or undefined, having
  // said why, when the server cannot tell.
  async componentTypes(toml: vscode.Uri): Promise<ComponentType[] | undefined> {
    const client = this.client();
    if (!client) {
      return undefined;
    }
    try {
      const reply = await client.sendRequest<{ types: ComponentType[] }>(
        "nxwright/componentTypes", { textDocument: { uri: toml.toString() } });
      return reply.types;
    } catch (error) {
      void vscode.window.showErrorMessage(`nxwright: ${errorText(error)}`);
      return undefined;
    }
  }

  // Adds a component of `type` to the page, its top left corner at `point`,
  // or at (0, 0) without one. Returns its name once added; says why when it
  // was not.
  async addComponent(toml: vscode.Uri, type: string, point?: { x: number; y: number }):
      Promise<string | undefined> {
    const client = this.client();
    if (!client) {
      return undefined;
    }
    try {
      const added = await client.sendRequest<AddedComponent>("nxwright/addComponent", {
        textDocument: { uri: toml.toString() },
        type,
        point,
      });
      return (await this.apply(client, toml, added.edit)) ? added.name : undefined;
    } catch (error) {
      void vscode.window.showErrorMessage(`nxwright: ${errorText(error)}`);
      return undefined;
    }
  }

  // Deletes components of the page, their code with them. When other code
  // names one of them, asks first, saying where. Returns whether they were
  // deleted; says why when they were not.
  async deleteComponents(toml: vscode.Uri, names: string[]): Promise<boolean> {
    const client = this.client();
    if (!client || names.length === 0) {
      return false;
    }
    try {
      const found = await client.sendRequest<DeletedComponents>("nxwright/deleteComponents", {
        textDocument: { uri: toml.toString() },
        names,
      });
      if (found.namedElsewhere.length > 0 && !(await this.confirmDelete(names, found))) {
        return false;
      }
      return await this.apply(client, toml, found.edit);
    } catch (error) {
      void vscode.window.showErrorMessage(`nxwright: ${errorText(error)}`);
      return false;
    }
  }

  // Removes the code of every event of components of the page, keeping the
  // components. Asks first for several, and says so when none has code.
  // Returns whether code was removed; says why when it was not.
  async clearEvents(toml: vscode.Uri, names: string[]): Promise<boolean> {
    const client = this.client();
    if (!client || names.length === 0) {
      return false;
    }
    try {
      const edit = await client.sendRequest<ProtocolWorkspaceEdit>("nxwright/clearEvents", {
        textDocument: { uri: toml.toString() },
        names,
      });
      if (Object.keys(edit.changes ?? {}).length === 0) {
        void vscode.window.showInformationMessage(`nxwright: ${nothingToClearNote(names)}`);
        return false;
      }
      // One component's code comes back with undo; several are asked about.
      if (names.length > 1 && await vscode.window.showWarningMessage(
          clearEventsQuestion(names), { modal: true }, CLEAR_EVENTS) !== CLEAR_EVENTS) {
        return false;
      }
      return await this.apply(client, toml, edit);
    } catch (error) {
      void vscode.window.showErrorMessage(`nxwright: ${errorText(error)}`);
      return false;
    }
  }

  // Copies components of the page: their tables to the clipboard, and their
  // code beside it. Returns whether they were copied; says why when not.
  async copyComponents(toml: vscode.Uri, names: string[]): Promise<boolean> {
    const copied = await this.copied(toml, names);
    if (!copied) {
      return false;
    }
    await vscode.env.clipboard.writeText(copied.text);
    this.lastCopy = copied;
    return true;
  }

  // Copies components, then deletes them as deleteComponents does.
  async cutComponents(toml: vscode.Uri, names: string[]): Promise<boolean> {
    return (await this.copyComponents(toml, names)) && (await this.deleteComponents(toml, names));
  }

  // Pastes the clipboard's tables into the page, where `place` says, with
  // their code when the clipboard still holds what was copied last. Returns
  // the pasted components' names; says why when nothing was pasted.
  async pasteComponents(toml: vscode.Uri, place: PastePlace = {}): Promise<string[]> {
    const text = await vscode.env.clipboard.readText();
    return await this.paste(toml, { text, code: this.codeOf(text) ?? [] }, place);
  }

  // Pastes the clipboard's tables into the page, none of their code.
  // Returns the pasted components' names; says why when nothing was pasted.
  async pasteWithoutCode(toml: vscode.Uri): Promise<string[]> {
    return await this.paste(toml, { text: await vscode.env.clipboard.readText(), code: [] });
  }

  // Asks what new copies of the clipboard's components bring, their
  // position and their code, and pastes them: Paste Special opened on the
  // page itself. `point` is the point clicked, where the menu gives one;
  // copiesToPaste says where they go. Returns the pasted components' names;
  // says why when nothing was pasted.
  async pasteCopies(toml: vscode.Uri, point?: Point): Promise<string[]> {
    const text = await vscode.env.clipboard.readText();
    if (copiedTableCount(text) === 0) {
      void vscode.window.showErrorMessage(`nxwright: ${NO_COMPONENTS}`);
      return [];
    }
    const code = this.codeOf(text);
    const picked = await vscode.window.showQuickPick(copyChoices(code !== undefined), {
      canPickMany: true,
      title: "nxwright: Paste Special",
      placeHolder: "What the copied components bring with them",
    });
    if (!picked) {
      return [];
    }
    const pasted = copiesToPaste(picked, code, point);
    if (pasted.note) {
      void vscode.window.showWarningMessage(`nxwright: ${pasted.note}`);
    }
    return await this.paste(toml, { text, code: pasted.code }, pasted.place);
  }

  // Asks which parts of the one component the clipboard holds to apply to
  // the components `names` of the page, and applies them, saying what was
  // left out. Returns whether they were applied; says why when not.
  async pasteParts(toml: vscode.Uri, names: string[]): Promise<boolean> {
    const client = this.client();
    if (!client || names.length === 0) {
      return false;
    }
    const text = await vscode.env.clipboard.readText();
    if (copiedTableCount(text) !== 1) {
      void vscode.window.showErrorMessage(`nxwright: ${ONE_COMPONENT}`);
      return false;
    }
    const picked = await vscode.window.showQuickPick(PART_CHOICES, {
      canPickMany: true,
      title: "nxwright: Paste Special",
      placeHolder: `The parts of the copied component to apply to ${names.join(", ")}`,
    });
    if (!picked || picked.length === 0) {
      return false;
    }
    const pasted = partsToPaste(picked, this.codeOf(text));
    if (pasted.note) {
      void vscode.window.showWarningMessage(`nxwright: ${pasted.note}`);
    }
    if (pasted.parts.length === 0) {
      return false;
    }
    try {
      const found = await client.sendRequest<PastedParts>("nxwright/pasteParts", {
        textDocument: { uri: toml.toString() },
        names,
        text,
        code: pasted.code,
        parts: pasted.parts,
      });
      const applied = await this.apply(client, toml, found.edit);
      if (applied && found.notes.length > 0) {
        void vscode.window.showInformationMessage(`nxwright: ${found.notes.join(". ")}.`);
      }
      return applied;
    } catch (error) {
      void vscode.window.showErrorMessage(`nxwright: ${errorText(error)}`);
      return false;
    }
  }

  // The code of the last components copied, while the clipboard's `text` is
  // still their tables; else undefined.
  private codeOf(text: string): string[] | undefined {
    // Another program may have ended the lines as Windows ends them.
    const same = this.lastCopy?.text.replace(/\r\n/g, "\n") === text.replace(/\r\n/g, "\n");
    return same && this.lastCopy ? this.lastCopy.code : undefined;
  }

  // Copies components and pastes them at once into their page, leaving the
  // clipboard as it was. Returns the copies' names.
  async duplicateComponents(toml: vscode.Uri, names: string[]): Promise<string[]> {
    const copied = await this.copied(toml, names);
    return copied ? await this.paste(toml, copied) : [];
  }

  // Returns the components' tables and code, or undefined, having said why.
  private async copied(toml: vscode.Uri, names: string[]):
      Promise<CopiedComponents | undefined> {
    const client = this.client();
    if (!client || names.length === 0) {
      return undefined;
    }
    try {
      return await client.sendRequest<CopiedComponents>("nxwright/copyComponents", {
        textDocument: { uri: toml.toString() },
        names,
      });
    } catch (error) {
      void vscode.window.showErrorMessage(`nxwright: ${errorText(error)}`);
      return undefined;
    }
  }

  // Pastes `copied` into the page, where `place` says; returns the new names,
  // or none, having said why.
  private async paste(toml: vscode.Uri, copied: CopiedComponents, place: PastePlace = {}):
      Promise<string[]> {
    const client = this.client();
    if (!client) {
      return [];
    }
    try {
      const pasted = await client.sendRequest<PastedComponents>("nxwright/pasteComponents", {
        textDocument: { uri: toml.toString() },
        text: copied.text,
        code: copied.code,
        ...place,
      });
      return (await this.apply(client, toml, pasted.edit)) ? pasted.names : [];
    } catch (error) {
      void vscode.window.showErrorMessage(`nxwright: ${errorText(error)}`);
      return [];
    }
  }

  // Places several components of the page at once, as one edit, `places`
  // being {name: {x, y, w, h}}. Returns whether the page file changed; says
  // why when it did not.
  async placeComponents(toml: vscode.Uri, places: Record<string, unknown>): Promise<boolean> {
    return await this.edit(toml, "nxwright/placeComponents", { places });
  }

  // Moves components of the page one place "forward", up the ID order, or
  // "backward"; or past every other component, to the "front" or the
  // "back". Returns whether the page file changed.
  async reorderComponents(toml: vscode.Uri, names: string[], direction: string):
      Promise<boolean> {
    return await this.edit(toml, "nxwright/reorderComponents", { names, direction });
  }

  // Locks components of the page, or unlocks them, as one edit. Returns
  // whether the page file changed.
  async lockComponents(toml: vscode.Uri, names: string[], locked: boolean): Promise<boolean> {
    return await this.edit(toml, "nxwright/lockComponents", { names, locked });
  }

  // Gives components of the page a new group of their own, or takes them out
  // of theirs, as one edit. Returns whether the page file changed.
  async groupComponents(toml: vscode.Uri, names: string[], grouped: boolean): Promise<boolean> {
    return await this.edit(toml, "nxwright/groupComponents", { names, grouped });
  }

  // Applies the WorkspaceEdit the server's `method` returns for the page;
  // returns whether it was applied, having said why when it was not.
  private async edit(toml: vscode.Uri, method: string, params: Record<string, unknown>):
      Promise<boolean> {
    const client = this.client();
    if (!client) {
      return false;
    }
    try {
      const edit = await client.sendRequest(method, {
        textDocument: { uri: toml.toString() }, ...params });
      return await this.apply(client, toml, edit);
    } catch (error) {
      void vscode.window.showErrorMessage(`nxwright: ${errorText(error)}`);
      return false;
    }
  }

  // Asks whether to delete components that other code still names.
  private async confirmDelete(names: string[], found: DeletedComponents): Promise<boolean> {
    const places = found.namedElsewhere.map((place) =>
      `${vscode.workspace.asRelativePath(vscode.Uri.parse(place.uri))} line ${place.line + 1}`);
    const count = places.length === 1 ? "1 place" : `${places.length} places`;
    const question = `Code names ${names.join(", ")} in ${count}, which will no longer build: ` +
      `${places.slice(0, 5).join(", ")}${places.length > 5 ? ", ..." : ""}. Delete anyway?`;
    return await vscode.window.showWarningMessage(question, { modal: true }, DELETE) === DELETE;
  }

  // Lists an object's events, saying where each one's code is, and opens
  // the one picked as openEvent does. Says so for a type without events.
  async goToEvent(toml: vscode.Uri, name: string): Promise<void> {
    const client = this.client();
    if (!client) {
      return;
    }
    let events: ComponentEvent[];
    try {
      events = await client.sendRequest<ComponentEvent[]>("nxwright/componentEvents", {
        textDocument: { uri: toml.toString() },
        name,
      });
    } catch (error) {
      void vscode.window.showErrorMessage(`nxwright: ${errorText(error)}`);
      return;
    }
    if (events.length === 0) {
      void vscode.window.showInformationMessage(`nxwright: ${noEventsNote(name)}`);
      return;
    }
    const picked = await vscode.window.showQuickPick(eventChoices(events), {
      title: `nxwright: Go to Event of ${name}`,
      placeHolder: "The event to open; one without code gets its heading added",
    });
    if (picked) {
      await this.openEvent(toml, name, picked.event);
    }
  }

  // Opens the code of an object's `event`, else of its default event: the
  // first, in its type's order, that has code, else its first. Adds the
  // event's heading when it has no code. An object whose type has no events,
  // such as a variable, opens nothing.
  async openEvent(toml: vscode.Uri, name: string, event?: string): Promise<void> {
    const client = this.client();
    if (!client) {
      return;
    }
    try {
      const found = await client.sendRequest<DefaultEvent | null>("nxwright/defaultEvent", {
        textDocument: { uri: toml.toString() },
        name,
        event,
      });
      if (!found) {
        return;
      }
      if (found.edit) {
        await this.apply(client, toml, found.edit);
      }
      const position = new vscode.Position(found.line, found.character);
      await vscode.window.showTextDocument(vscode.Uri.parse(found.uri), {
        viewColumn: this.otherGroup(toml),
        selection: new vscode.Range(position, position),
      });
    } catch (error) {
      void vscode.window.showErrorMessage(`nxwright: ${errorText(error)}`);
    }
  }

  // Opens the page file as text, beside the page's preview, with the cursor
  // at the start of the table of the object `name`, or of the page itself
  // without one: its `[[component]]` or `[page]` line. The server gives the
  // line, from the page file as edited, saved or not.
  async goToDefinition(toml: vscode.Uri, name?: string): Promise<void> {
    const client = this.client();
    if (!client) {
      return;
    }
    try {
      const listed = await client.sendRequest<{ objects: PageObject[] } | null>(
        "nxwright/pageObjects", { textDocument: { uri: toml.toString() } });
      const found = listed?.objects.find((entry) =>
        name === undefined ? entry.type === "page" : entry.name === name);
      if (!found) {
        void vscode.window.showErrorMessage(
          `nxwright: the page file has no table of ${name ?? "its page"}.`);
        return;
      }
      const start = new vscode.Position(found.firstLine, 0);
      await vscode.window.showTextDocument(toml, {
        viewColumn: this.otherGroup(toml),
        selection: new vscode.Range(start, start),
      });
    } catch (error) {
      void vscode.window.showErrorMessage(`nxwright: ${errorText(error)}`);
    }
  }

  // Applies a WorkspaceEdit the server sent, as applyShown does.
  private async apply(client: LanguageClient, toml: vscode.Uri, edit: unknown):
      Promise<boolean> {
    const converted = await client.protocol2CodeConverter.asWorkspaceEdit(
      edit as ProtocolWorkspaceEdit);
    return !!converted && (await this.applyShown(toml, converted));
  }

  // Applies an edit as one step of undo; returns whether it was applied. A
  // file it changes that no tab holds opens in one, so that the change can
  // be seen, undone, and saved; a file a tab holds, even one out of sight,
  // or the page file its preview holds, is left there. Never in the group
  // of the page's preview, which would hide the preview.
  private async applyShown(toml: vscode.Uri, edit: vscode.WorkspaceEdit): Promise<boolean> {
    if (!(await vscode.workspace.applyEdit(edit))) {
      return false;
    }
    const tabs = new Set(allTabs()
      .map((tab) => tab.input instanceof vscode.TabInputText ||
                    tab.input instanceof vscode.TabInputCustom ? tab.input.uri.toString() : ""));
    for (const [uri] of edit.entries()) {
      if (!tabs.has(uri.toString())) {
        await vscode.window.showTextDocument(uri, {
          viewColumn: this.otherGroup(toml),
          preserveFocus: true,
          preview: false,
        });
      }
    }
    return true;
  }

  // Where a file can show without hiding the page's preview: a group of
  // tabs other than the preview's, else a new one beside it. With no
  // preview open, the active group.
  private otherGroup(toml: vscode.Uri): vscode.ViewColumn {
    const previewGroup = vscode.window.tabGroups.all.find((group) => group.tabs.some((tab) =>
      tab.input instanceof vscode.TabInputCustom && tab.input.viewType === PREVIEW_VIEW_TYPE &&
      tab.input.uri.toString() === toml.toString()))?.viewColumn;
    if (previewGroup === undefined) {
      return vscode.ViewColumn.Active;
    }
    return vscode.window.tabGroups.all
      .find((group) => group.viewColumn !== previewGroup)?.viewColumn ?? vscode.ViewColumn.Beside;
  }
}

function allTabs(): readonly vscode.Tab[] {
  return vscode.window.tabGroups.all.flatMap((group) => group.tabs);
}

// Asks where the Chinese keyboard's font comes from: one of `fonts`, the
// folder's fonts it takes, or a typeface file to draw it from. Returns
// {font} or {typeface}, or undefined when nothing was chosen.
export async function askChineseFont(fonts: readonly string[]):
    Promise<{ font?: string; typeface?: string } | undefined> {
  const choice = await vscode.window.showQuickPick(chineseFontChoices(fonts), {
    title: "Choose a font with Chinese characters for the Chinese keyboard",
  });
  if (!choice) {
    return undefined;
  }
  let typeface: string | undefined;
  if (choice.font === undefined) {
    const files = await vscode.window.showOpenDialog({
      title: "Choose a typeface file with Chinese characters",
      filters: { Typefaces: ["ttf", "otf", "ttc"] },
      openLabel: "Use this typeface",
    });
    typeface = files?.[0]?.fsPath;
  }
  return chineseFontParameters(choice, typeface);
}
