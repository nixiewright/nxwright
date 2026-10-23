// Which open tab of a page file a click on a component shows it in
// (sideBar.ts). Kept apart from VS Code, which test/ tests.

// How a tab shows a page file: in the page preview, or as text.
export type PageView = "preview" | "text";

// An open tab of a page file, and how it shows the page.
export interface PageTab<Tab> {
  tab: Tab;
  view: PageView;
}

// Returns the tab among `tabs`, the open tabs of a page file, those of the
// active group first, that a click on one of its components shows it in; or
// undefined when none is open. The active tab comes first, when it holds the
// page. Then a tab of `lastFocused`, the view of the page the user focused
// last. Then any tab: with only one view open, that view is the user's.
export function chooseTab<Tab>(tabs: PageTab<Tab>[], active: Tab | undefined,
                               lastFocused: PageView | undefined): PageTab<Tab> | undefined {
  return tabs.find((entry) => entry.tab === active) ??
    tabs.find((entry) => entry.view === lastFocused) ?? tabs[0];
}
