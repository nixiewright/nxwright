// Arranging several components of the page preview at once, kept apart from
// the webview so that Node's test runner can check it. Rectangles are {name,
// x, y, w, h}, in the page's pixels. The component selected first is the
// anchor: aligning moves the others to its edge or centre, and sizing gives
// them its width, its height, or both. Spacing evenly keeps the first and
// the last components, across or down, where they are, and moves those
// between so that the gaps between neighbours are equal, as near as whole
// pixels allow, the first gaps taking the extra pixels. A centre that falls
// between two pixels takes the one to the left or above. A locked component
// stays where it is: moves and arrangements leave it out, and spacing keeps
// it as it keeps the first and the last, spacing the others between each
// two that stay.

// Returns `others` aligned with `anchor` as `how` says: "left", "right",
// "top", "bottom", "centreAcross" (the same centre from left to right), or
// "centreDown" (the same centre from top to bottom).
export function aligned(anchor, others, how) {
  const moves = {
    left: (rect) => ({ x: anchor.x }),
    right: (rect) => ({ x: anchor.x + anchor.w - rect.w }),
    top: (rect) => ({ y: anchor.y }),
    bottom: (rect) => ({ y: anchor.y + anchor.h - rect.h }),
    centreAcross: (rect) => ({ x: anchor.x + Math.floor((anchor.w - rect.w) / 2) }),
    centreDown: (rect) => ({ y: anchor.y + Math.floor((anchor.h - rect.h) / 2) }),
  };
  return others.map((rect) => ({ ...rect, ...moves[how](rect) }));
}

// Returns `others` given the `anchor`'s "width", "height", or "both".
export function sameSize(anchor, others, which) {
  return others.map((rect) => ({
    ...rect,
    w: which === "height" ? rect.w : anchor.w,
    h: which === "width" ? rect.h : anchor.h,
  }));
}

// Returns `rects` spaced evenly `across`, or down when false, in the order
// they stand that way, ties in the order given. The first, the last, and
// those named in `fixed` stay; those between each two that stay are spaced
// evenly between them. Fewer than three are returned as they are.
export function spacedEvenly(rects, across, fixed = new Set()) {
  const [at, size] = across ? ["x", "w"] : ["y", "h"];
  const order = rects.map((rect, index) => [rect, index])
    .sort(([a, i], [b, j]) => a[at] - b[at] || i - j).map(([rect]) => rect);
  if (order.length < 3) {
    return rects;
  }
  const placed = new Map();
  let from = 0;
  order.forEach((rect, index) => {
    if (index > 0 && (index === order.length - 1 || fixed.has(rect.name))) {
      spaceBetween(order.slice(from, index + 1), at, size, placed);
      from = index;
    }
  });
  return rects.map((rect) => placed.get(rect) ?? rect);
}

// Places, in `placed`, those of `order` between its first and its last, so
// that the gaps between neighbours are equal, the first taking the extra pixels.
function spaceBetween(order, at, size, placed) {
  const first = order[0], last = order[order.length - 1];
  const between = order.slice(1, -1);
  const gaps = order.length - 1;
  const free = last[at] - (first[at] + first[size]) -
    between.reduce((sum, rect) => sum + rect[size], 0);
  const gap = Math.floor(free / gaps);
  const extra = free - gap * gaps;
  let next = first[at] + first[size];
  between.forEach((rect, index) => {
    next += gap + (index < extra ? 1 : 0);
    placed.set(rect, { ...rect, [at]: next });
    next += rect[size];
  });
}

// Returns the rectangles the arrangement `how` gives `rects`, the selected
// components with a place, the anchor first: an alignment of `aligned`,
// "sameWidth", "sameHeight", "sameSize", "spaceAcross", or "spaceDown". Those
// named in `locked` are left out, staying where they are, the anchor's
// edges, centres, and size still counting.
export function arrangement(rects, how, locked = new Set()) {
  const [anchor, ...rest] = rects;
  const sizes = { sameWidth: "width", sameHeight: "height", sameSize: "both" };
  const spacing = { spaceAcross: true, spaceDown: false };
  const arranged = how in sizes ? sameSize(anchor, rest, sizes[how])
    : how in spacing ? spacedEvenly(rects, spacing[how], locked) : aligned(anchor, rest, how);
  return arranged.filter((rect) => !locked.has(rect.name));
}

// Returns the names of the components a move of the selected `names` takes,
// of `components` (a drawing's): `names`, then each other member of their
// groups, in ID order, every component once. Moving a member of a group
// moves the whole group.
export function movingNames(components, names) {
  const groups = groupsOf(components, names);
  const along = components.filter((component) => groups.has(component.group) &&
                                                  !names.includes(component.name));
  return [...names, ...along.map((component) => component.name)];
}

// Returns the names among `names` of the locked components of `components`
// (a drawing's), which moves leave where they are.
export function lockedAmong(components, names) {
  return new Set(components.filter((component) => component.locked &&
                                                   names.includes(component.name))
    .map((component) => component.name));
}

// Returns the names of every member of the groups of the selected `names`,
// those of `names` in a group included, in ID order, of `components` (a
// drawing's): the members the Editor's design view tints.
export function groupMembers(components, names) {
  const groups = groupsOf(components, names);
  return components.filter((component) => groups.has(component.group))
    .map((component) => component.name);
}

// Returns the groups of the components `names` of `components` in one.
function groupsOf(components, names) {
  return new Set(components.filter((component) => component.group &&
                                                   names.includes(component.name))
    .map((component) => component.group));
}

// Returns `rects` moved together by (dx, dy), those named in `locked` left out.
export function movedTogether(rects, dx, dy, locked = new Set()) {
  return rects.filter((rect) => !locked.has(rect.name)).map((rect) => movedBy(rect, dx, dy));
}

// Returns the names of the components of `components` (a drawing's), the
// page aside, that `box` overlaps, in ID order. A component the box only
// touches along an edge is left out. A box with no width or no height
// overlaps the components it crosses.
export function overlappingBox(components, box) {
  return components.filter((component) => component.type !== "page" &&
    component.x < box.x + box.w && box.x < component.x + component.w &&
    component.y < box.y + box.h && box.y < component.y + component.h)
    .map((component) => component.name);
}

// Returns the rectangle {x, y, w, h} between two corners, in any order.
export function boxBetween(x0, y0, x1, y1) {
  return { x: Math.min(x0, x1), y: Math.min(y0, y1), w: Math.abs(x1 - x0), h: Math.abs(y1 - y0) };
}

// Returns `rect` moved by (dx, dy).
export function movedBy(rect, dx, dy) {
  return { ...rect, x: rect.x + dx, y: rect.y + dy };
}
