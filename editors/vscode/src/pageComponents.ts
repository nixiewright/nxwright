// The commands adding, deleting, copying, pasting, locking, unlocking,
// grouping, and ungrouping a page's components, going to their events and
// clearing their code, and showing their attributes:
// from the page preview's right-click menu, from nxwright's side bar's
// Components list, and adding from the command palette. The edits
// themselves are pageEditing.ts's.
import * as vscode from "vscode";
import { PageEditing, PastePlace } from "./pageEditing";
import { PageObject, Pages } from "./pages";

// What the preview's right-click menu passes its commands: the webview's
// data-vscode-context where the menu opened (media/preview.mjs).
interface PreviewMenuContext {
  // The page file's URI, once the preview has told its webview.
  page?: string;
  // The point clicked, on the grid, when the menu opened on the page.
  x?: number;
  y?: number;
  // The selected components, the page aside, and the first of them, which
  // tells the menu there are some; and those of them with a place, the ones
  // a lock shows on and a group moves.
  component?: string;
  components?: string[];
  placedComponents?: string[];
}

export class PageComponents {
  constructor(private readonly pages: Pages, private readonly editing: PageEditing) {}

  register(): vscode.Disposable[] {
    return [
      vscode.commands.registerCommand("nxwright.addComponent", () => this.add()),
      vscode.commands.registerCommand("nxwright.addComponentHere",
                                      (context: PreviewMenuContext) => this.addHere(context)),
      vscode.commands.registerCommand("nxwright.deleteComponent",
                                      (target: PreviewMenuContext | PageObject) =>
                                        this.onComponents(target, (toml, names) =>
                                          this.editing.deleteComponents(toml, names))),
      vscode.commands.registerCommand("nxwright.copyComponent",
                                      (target: PreviewMenuContext | PageObject) =>
                                        this.onComponents(target, (toml, names) =>
                                          this.editing.copyComponents(toml, names))),
      vscode.commands.registerCommand("nxwright.cutComponent",
                                      (target: PreviewMenuContext | PageObject) =>
                                        this.onComponents(target, (toml, names) =>
                                          this.editing.cutComponents(toml, names))),
      vscode.commands.registerCommand("nxwright.duplicateComponent",
                                      (target: PreviewMenuContext | PageObject) =>
                                        this.onComponents(target, async (toml, names) =>
                                          this.selectFirst(toml, await this.editing
                                            .duplicateComponents(toml, names)))),
      // A lock shows on a component with a place alone: those alone are locked.
      vscode.commands.registerCommand("nxwright.lockComponents",
                                      (target: PreviewMenuContext) =>
                                        this.lock(target, true)),
      vscode.commands.registerCommand("nxwright.unlockComponents",
                                      (target: PreviewMenuContext) =>
                                        this.lock(target, false)),
      // A group moves on the page alone: those with a place alone are grouped.
      vscode.commands.registerCommand("nxwright.groupComponents",
                                      (target: PreviewMenuContext) =>
                                        this.group(target, true)),
      vscode.commands.registerCommand("nxwright.ungroupComponents",
                                      (target: PreviewMenuContext) =>
                                        this.group(target, false)),
      vscode.commands.registerCommand("nxwright.goToEvent",
                                      (target: PreviewMenuContext | PageObject) =>
                                        this.onComponents(target, (toml, names) =>
                                          this.editing.goToEvent(toml, names[0]))),
      vscode.commands.registerCommand("nxwright.editAttributes",
                                      (target: PreviewMenuContext | PageObject) =>
                                        this.onComponents(target, (toml, names) =>
                                          this.editAttributes(toml, names[0]))),
      vscode.commands.registerCommand("nxwright.goToDefinition",
                                      (target: PreviewMenuContext | PageObject) =>
                                        this.goToDefinition(target)),
      vscode.commands.registerCommand("nxwright.clearEvents",
                                      (target: PreviewMenuContext | PageObject) =>
                                        this.onComponents(target, (toml, names) =>
                                          this.editing.clearEvents(toml, names))),
      vscode.commands.registerCommand("nxwright.pasteComponents",
                                      (target: PreviewMenuContext | PageObject) =>
                                        this.paste(target, true)),
      vscode.commands.registerCommand("nxwright.pasteHere",
                                      (context: PreviewMenuContext) => this.pasteHere(context)),
      vscode.commands.registerCommand("nxwright.pasteInPlace",
                                      (target: PreviewMenuContext | PageObject) =>
                                        this.paste(target, true, { inPlace: true })),
      vscode.commands.registerCommand("nxwright.pasteWithoutCode",
                                      (target: PreviewMenuContext | PageObject) =>
                                        this.paste(target, false)),
      vscode.commands.registerCommand("nxwright.pasteSpecial",
                                      (target: PreviewMenuContext | PageObject) =>
                                        this.pasteSpecial(target)),
    ];
  }

  // Adds a component to the page nxwright's side bar shows, at (0, 0), where
  // the Editor adds one.
  private async add(): Promise<void> {
    const toml = this.pages.shown;
    if (!toml) {
      void vscode.window.showErrorMessage(
        "nxwright: open a page's .page.toml or .nx file, or its preview, first.");
      return;
    }
    await this.addTo(toml);
  }

  // Adds a component where the preview's right-click menu opened.
  private async addHere(context: PreviewMenuContext): Promise<void> {
    if (context.page) {
      await this.addTo(vscode.Uri.parse(context.page), { x: context.x ?? 0, y: context.y ?? 0 });
    }
  }

  // Asks for a type, adds a component of it, and selects it.
  private async addTo(toml: vscode.Uri, point?: { x: number; y: number }): Promise<void> {
    const types = await this.editing.componentTypes(toml);
    if (!types) {
      return;
    }
    const chosen = await vscode.window.showQuickPick(
      types.map((entry) => ({
        label: entry.type,
        description: entry.placed ? undefined : "no place on the screen",
      })),
      { placeHolder: "The type of the new component" });
    if (!chosen) {
      return;
    }
    const name = await this.editing.addComponent(toml, chosen.label, point);
    if (name) {
      this.pages.select(toml, name);
    }
  }

  // Does `act` on the components the preview's menu opened on, the selected
  // ones, or on the one the Components list's menu opened on.
  private async onComponents(target: PreviewMenuContext | PageObject,
                             act: (toml: vscode.Uri, names: string[]) => Promise<unknown>):
      Promise<void> {
    const toml = pageOf(target, this.pages);
    const names = isPageObject(target) ? [target.name] : target.components ?? [];
    if (toml && names.length > 0) {
      await act(toml, names);
    }
  }

  // Locks the selected components with a place, or unlocks them.
  private async lock(target: PreviewMenuContext, locked: boolean): Promise<void> {
    const toml = pageOf(target, this.pages);
    if (toml && target.placedComponents?.length) {
      await this.editing.lockComponents(toml, target.placedComponents, locked);
    }
  }

  // Gives the selected components with a place a new group of their own,
  // or takes them out of theirs.
  private async group(target: PreviewMenuContext, grouped: boolean): Promise<void> {
    const toml = pageOf(target, this.pages);
    if (toml && target.placedComponents?.length) {
      await this.editing.groupComponents(toml, target.placedComponents, grouped);
    }
  }

  // Pastes into the page the menu opened on, with the code that came with
  // the components or without it, where `place` says, and selects the
  // first pasted.
  private async paste(target: PreviewMenuContext | PageObject, withCode: boolean,
                      place: PastePlace = {}): Promise<void> {
    const toml = pageOf(target, this.pages);
    if (toml) {
      this.selectFirst(toml, await (withCode ? this.editing.pasteComponents(toml, place)
                                             : this.editing.pasteWithoutCode(toml)));
    }
  }

  // Pastes at the point where the preview's right-click menu opened, which
  // it gives only when it opened on the page.
  private async pasteHere(context: PreviewMenuContext): Promise<void> {
    if (context.x !== undefined && context.y !== undefined) {
      await this.paste(context, true, { at: { x: context.x, y: context.y } });
    }
  }

  // Applies parts of the copied component to the components the menu opened
  // on. Opened on the page itself, where no component is selected in the
  // preview, or on the page's row in the Components list, it pastes new
  // copies instead, asking what they bring (PageEditing.pasteCopies).
  private async pasteSpecial(target: PreviewMenuContext | PageObject): Promise<void> {
    const toml = pageOf(target, this.pages);
    if (!toml) {
      return;
    }
    const names = isPageObject(target) ? (target.type === "page" ? [] : [target.name])
                                       : target.components ?? [];
    if (names.length > 0) {
      await this.editing.pasteParts(toml, names);
      return;
    }
    const point = !isPageObject(target) && target.x !== undefined && target.y !== undefined
      ? { x: target.x, y: target.y } : undefined;
    this.selectFirst(toml, await this.editing.pasteCopies(toml, point));
  }

  // Opens the page file as text at the table of the first selected
  // component, or of the page itself when no component is selected.
  private async goToDefinition(target: PreviewMenuContext | PageObject): Promise<void> {
    const toml = pageOf(target, this.pages);
    if (toml) {
      await this.editing.goToDefinition(toml,
                                        isPageObject(target) ? target.name : target.component);
    }
  }

  // Selects a component, and shows and focuses the Attributes section on it.
  private async editAttributes(toml: vscode.Uri, name: string): Promise<void> {
    this.pages.select(toml, name);
    await vscode.commands.executeCommand("nxwright.properties.focus");
  }

  private selectFirst(toml: vscode.Uri, names: string[]): void {
    if (names.length > 0) {
      this.pages.select(toml, names[0]);
    }
  }
}

// The page file of the page a menu opened on: the preview's, or the one the
// side bar shows.
function pageOf(target: PreviewMenuContext | PageObject, pages: Pages): vscode.Uri | undefined {
  if (isPageObject(target)) {
    return pages.shown;
  }
  return target.page ? vscode.Uri.parse(target.page) : undefined;
}

// Whether the Components list, rather than the preview, passed `target`.
function isPageObject(target: PreviewMenuContext | PageObject): target is PageObject {
  return "firstLine" in target;
}
