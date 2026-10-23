// The sections of nxwright's page side bar, under its own icon in VS Code's
// activity bar, for the page shown (pages.ts), the page of the last active
// editor that was a page's. Components lists the page's objects; Attributes
// lists the selected object's attributes and edits them.
import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";
import { PageEditing, Properties } from "./pageEditing";
import { PageObject, Pages, PREVIEW_VIEW_TYPE } from "./pages";
import { chooseTab, PageTab, PageView } from "./pageTabChoice";
import { errorText } from "./userMessages";
import { webviewPage } from "./webviewPage";

const NO_PAGE = "Open a page's .page.toml or .nx file, or its preview.";

// The Components section: the page's objects in ID order, the page first.
// Choosing one selects it, and shows it where its page is open
// (showComponent). Its title has a button adding a component, and a
// component's right-click menu deletes it (pageComponents.ts).
export class ComponentsView implements vscode.TreeDataProvider<PageObject> {
  private readonly changed = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.changed.event;
  private readonly tree: vscode.TreeView<PageObject>;
  private readonly showing: vscode.Disposable;
  // The view of each page file the user focused last, by the file's URI.
  private readonly lastFocused = new Map<string, PageView>();
  private readonly tracking: vscode.Disposable[];

  constructor(private readonly pages: Pages) {
    this.tree = vscode.window.createTreeView("nxwright.components", { treeDataProvider: this });
    this.showing = vscode.commands.registerCommand(
      SHOW_COMPONENT, (entry: PageObject) => this.showComponent(entry));
    this.tree.message = NO_PAGE;
    this.tree.onDidChangeSelection((event) => {
      const toml = pages.shown;
      if (toml && event.selection[0]) {
        pages.select(toml, event.selection[0].name);
      }
    });
    pages.onDidChangePage(() => {
      this.tree.message = pages.shown ? undefined : NO_PAGE;
      this.changed.fire();
      this.showSelection();
    });
    pages.onDidChangeSelection((toml) => {
      if (toml.toString() === pages.shown?.toString()) {
        this.showSelection();
      }
    });
    this.tree.onDidChangeVisibility(() => this.showSelection());
    // A tab becomes active within its group, or its group becomes active.
    const focused = () => this.recordFocus();
    this.tracking = [vscode.window.tabGroups.onDidChangeTabs(focused),
                     vscode.window.tabGroups.onDidChangeTabGroups(focused)];
    this.recordFocus();
  }

  dispose(): void {
    this.tree.dispose();
    this.showing.dispose();
    this.tracking.forEach((listener) => listener.dispose());
  }

  // Records the view of the active tab, when it shows a page file.
  private recordFocus(): void {
    const active = vscode.window.tabGroups.activeTabGroup.activeTab;
    const shown = active && pageTabOf(active);
    if (shown) {
      this.lastFocused.set((active.input as { uri: vscode.Uri }).uri.toString(), shown.view);
    }
  }

  getChildren(element?: PageObject): PageObject[] {
    return element ? [] : [...this.pages.objects];
  }

  getParent(): undefined {
    return undefined;
  }

  getTreeItem(entry: PageObject): vscode.TreeItem {
    // No id: names repeat while a table is being pasted or typed.
    const item = new vscode.TreeItem(entry.name);
    item.description = entry.type;
    // The page is neither added nor deleted from here.
    item.contextValue = entry.type === "page" ? "page" : "component";
    // A click, and no other change of the selection, such as the list
    // following the preview's, shows the component.
    item.command = { command: SHOW_COMPONENT, title: "Show the component", arguments: [entry] };
    return item;
  }

  // Shows `entry` where its page is open: in a tab of its page file, a
  // preview or a text editor, as chooseTab chooses; with no tab, the page
  // file opens as VS Code opens it by default, which the user's file
  // associations decide. A preview selects it, as choosing it does already;
  // a text editor puts the cursor at the start of its table.
  private async showComponent(entry: PageObject): Promise<void> {
    const toml = this.pages.shown;
    if (!toml) {
      return;
    }
    this.pages.select(toml, entry.name);
    const tab = chooseTab(pageTabs(toml), vscode.window.tabGroups.activeTabGroup.activeTab,
                          this.lastFocused.get(toml.toString()))?.tab;
    if (tab?.input instanceof vscode.TabInputCustom) {
      await vscode.commands.executeCommand(
        "vscode.openWith", toml, PREVIEW_VIEW_TYPE,
        { viewColumn: tab.group.viewColumn, preserveFocus: true });
      return;
    }
    if (!tab) {
      await vscode.commands.executeCommand("vscode.open", toml, { preserveFocus: true });
      if (activeIsPreview(toml)) {
        return;
      }
    }
    const start = new vscode.Position(entry.firstLine, 0);
    await vscode.window.showTextDocument(toml, {
      viewColumn: tab?.group.viewColumn,
      preserveFocus: true,
      selection: new vscode.Range(start, start),
    });
  }

  // Marks the page's selected object in the list.
  private showSelection(): void {
    const toml = this.pages.shown;
    const name = toml && this.pages.selected(toml);
    const found = this.pages.objects.find((entry) => entry.name === name);
    if (found && this.tree.visible && this.tree.selection[0]?.name !== name) {
      void this.tree.reveal(found, { select: true, focus: false });
    }
  }
}

// The command a click on a component runs: the extension's own, not in the
// command palette, as it needs the component.
const SHOW_COMPONENT = "nxwright.showComponent";

// The tabs holding the page file `toml`, a preview or a text editor, those
// of the active group first.
function pageTabs(toml: vscode.Uri): PageTab<vscode.Tab>[] {
  const groups = [vscode.window.tabGroups.activeTabGroup,
                  ...vscode.window.tabGroups.all.filter((group) => !group.isActive)];
  return groups.flatMap((group) => group.tabs).flatMap((tab) => {
    const shown = pageTabOf(tab);
    return shown && (tab.input as { uri: vscode.Uri }).uri.toString() === toml.toString()
      ? [shown] : [];
  });
}

// `tab` and how it shows a page file: as its preview, or as the text of a
// .page.toml file; or undefined for any other tab.
function pageTabOf(tab: vscode.Tab): PageTab<vscode.Tab> | undefined {
  if (tab.input instanceof vscode.TabInputCustom && tab.input.viewType === PREVIEW_VIEW_TYPE) {
    return { tab, view: "preview" };
  }
  if (tab.input instanceof vscode.TabInputText && tab.input.uri.scheme === "file" &&
      tab.input.uri.fsPath.endsWith(".page.toml")) {
    return { tab, view: "text" };
  }
  return undefined;
}

// Whether the active tab is the preview of the page file `toml`.
function activeIsPreview(toml: vscode.Uri): boolean {
  const input = vscode.window.tabGroups.activeTabGroup.activeTab?.input;
  return input instanceof vscode.TabInputCustom && input.viewType === PREVIEW_VIEW_TYPE &&
    input.uri.toString() === toml.toString();
}

// The Attributes section: the selected object's attributes, and the errors
// found in its table.
export class PropertiesView implements vscode.WebviewViewProvider {
  private view: vscode.WebviewView | undefined;
  // How many property lists were asked for: only the latest reply counts.
  private asked = 0;
  private queue: Promise<void> = Promise.resolve();

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly client: () => LanguageClient | undefined,
    private readonly pages: Pages,
    private readonly editing: PageEditing,
  ) {
    pages.onDidChangePage(() => void this.show());
    pages.onDidChangeSelection((toml) => {
      if (toml.toString() === pages.shown?.toString()) {
        void this.show();
      }
    });
  }

  register(): vscode.Disposable {
    return vscode.window.registerWebviewViewProvider("nxwright.properties", this);
  }

  resolveWebviewView(view: vscode.WebviewView): void {
    this.view = view;
    view.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, "media")],
    };
    view.webview.html = this.html(view.webview);
    // One message at a time: each edit is made from the text the one before it left.
    view.webview.onDidReceiveMessage((message) => {
      this.queue = this.queue.then(() => this.received(message)).catch(() => undefined);
    });
    view.onDidDispose(() => {
      this.view = undefined;
    });
  }

  // The errors found in the page files change: those of the selected table show.
  diagnosticsChanged(uris: readonly vscode.Uri[]): void {
    const toml = this.pages.shown?.toString();
    if (toml && uris.some((uri) => uri.toString() === toml)) {
      void this.show();
    }
  }

  private async received(message: { type: string; [key: string]: unknown }): Promise<void> {
    // An edit goes to the page the section showed, even should another page
    // show by the time it comes.
    const toml = typeof message.page === "string" ? vscode.Uri.parse(message.page) : undefined;
    const name = message.name as string;
    if (message.type === "ready") {
      // The webview starts afresh each time the section shows again.
      await this.show();
    } else if (toml && message.type === "select" && typeof name === "string") {
      // The section's list of the page's objects.
      this.pages.select(toml, name);
    } else if (toml && message.type === "setAttribute" && message.attribute === "key") {
      // A key may open a keyboard, which asks, and may add its page. When the
      // change is cancelled, the field goes back to the key the page gives.
      if (!(await this.editing.setKey(toml, name, message.value))) {
        await this.show();
      }
    } else if (toml && message.type === "setAttribute") {
      // A colour picked rather than typed is stored as the nearest the screen
      // holds. That may be the colour the page file already gives, which
      // leaves it unchanged: the section is drawn again all the same, so that
      // its sample shows the colour stored, not the one picked.
      const picked = message.nearest === true;
      await this.editing.setAttributes(toml, name, { [message.attribute as string]: message.value },
                                       picked);
      if (picked) {
        await this.show();
      }
    } else if (toml && message.type === "rename") {
      if (await this.editing.rename(toml, name, message.newName as string)) {
        this.pages.select(toml, message.newName as string);
      } else {
        // The name field goes back to the object's name.
        await this.show();
      }
    }
  }

  // Sends the section the selected object's properties, and the errors found
  // in its table; or, with none selected, how to select one.
  private async show(): Promise<void> {
    const client = this.client();
    const toml = this.pages.shown;
    const name = toml && this.pages.selected(toml);
    const asked = ++this.asked;
    if (!this.view) {
      return;
    }
    // The list choosing among the page's objects, as Components lists them.
    void this.view.webview.postMessage({
      type: "objects", page: toml?.toString(), selected: name,
      objects: toml ? this.pages.objects.map((entry) => ({ name: entry.name, type: entry.type }))
        : [],
    });
    if (!toml || !name || !client) {
      const text = toml ? "Select a component in the preview, the list, or the page file."
        : NO_PAGE;
      void this.view.webview.postMessage({ type: "empty", text });
      return;
    }
    let error: string | undefined;
    const properties = await client
      .sendRequest<Properties>("nxwright/componentProperties", {
        textDocument: { uri: toml.toString() },
        name,
      })
      .catch((failed) => {
        // Such as while the page file is half typed: the section says so.
        error = errorText(failed);
        return undefined;
      });
    if (asked !== this.asked || !this.view) {
      return;
    }
    if (error !== undefined || !properties) {
      void this.view.webview.postMessage({ type: "properties", error: error ?? "" });
      return;
    }
    const problems = vscode.languages.getDiagnostics(toml)
      .filter((problem) => problem.range.start.line >= properties.firstLine &&
                           problem.range.start.line <= properties.lastLine)
      .map((problem) => ({ line: problem.range.start.line, message: problem.message }));
    void this.view.webview.postMessage({
      type: "properties", page: toml.toString(), properties, problems });
  }

  private html(webview: vscode.Webview): string {
    return webviewPage(webview, this.context.extensionUri, {
      script: "properties.mjs",
      styles: `
  body { padding: 4px 8px; font-size: 12px; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; font-weight: normal; padding-right: 8px; white-space: nowrap; }
  td { width: 100%; }
  input, select {
    width: 100%; box-sizing: border-box;
    color: var(--vscode-input-foreground); background: var(--vscode-input-background);
    border: 1px solid var(--vscode-input-border, transparent);
  }
  tr.default input, tr.default select { opacity: 0.5; }
  .problem { color: var(--vscode-errorForeground); }
  .hint { color: var(--vscode-descriptionForeground); }
  #objects { margin: 4px 0 8px; }
  #objects[hidden] { display: none; }
  .colour { display: flex; gap: 4px; }
  .colour input[type=color] {
    flex: none; width: 24px; height: auto; align-self: stretch;
    padding: 0; border: none; background: none; cursor: pointer;
  }
  .colour input[type=color].empty::-webkit-color-swatch { background: transparent !important; }
  /* The footer stays over the bottom of the section. A long description
     scrolls within a third of the section's height, rather than growing over
     the rows above it. */
  #footer {
    position: sticky; bottom: 0; margin-top: 8px; padding: 4px 0; white-space: pre-line;
    max-height: 33vh; overflow-y: auto;
    color: var(--vscode-descriptionForeground);
    background: var(--vscode-sideBar-background);
    border-top: 1px solid var(--vscode-sideBarSectionHeader-border, transparent);
  }
  #footer[hidden] { display: none; }
  #footer strong { color: var(--vscode-foreground); font-weight: normal; }`,
      body: '<select id="objects" title="The object the section shows" hidden></select>' +
        '<div id="properties"></div><div id="footer" hidden></div>',
    });
  }
}
