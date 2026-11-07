// Arranging several components of the page preview at once, kept apart from
// the webview so that Node's test runner can check it. Rectangles are {name,
// x, y, w, h}, in the page's pixels. The component selected first is the
// anchor: aligning moves the others to its edge or centre, and sizing gives
// them its width, its height, or both. A centre that falls between two
// pixels takes the one to the left or above.
//
// Spacing works across or down. Spacing evenly keeps the first and the last
// components where they are, and moves those between so that the gaps are
// equal. When the pixels do not divide evenly, the first gaps get the extra
// ones. Increasing or decreasing the spacing keeps the first component where
// it is, and widens or narrows each gap after it by a pixel.
//
// A locked component stays where it is, and moves and arrangements leave it
// out. Spacing treats it as a fixed point, and spaces the components on each
// side of it separately.

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
  const order = standingOrder(rects, at);
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

// Returns `rects` with each gap between neighbours widened by a pixel when
// `step` is 1, or narrowed by a pixel when it is -1. Neighbours are taken
// left to right when `across` is true, or top to bottom when it is false,
// and rectangles at the same place keep the order given. The first rectangle
// and those named in `fixed` stay where they are. Each of the others moves
// one pixel more than the one before it, and the shift starts again from 0
// after each rectangle that stays. Narrowing leaves a gap of 0 or less as it is,
// so components stop closing up once they touch.
export function spacingChanged(rects, across, step, fixed = new Set()) {
  const [at, size] = across ? ["x", "w"] : ["y", "h"];
  const order = standingOrder(rects, at);
  const placed = new Map();
  let shift = 0;
  order.forEach((rect, index) => {
    if (index === 0 || fixed.has(rect.name)) {
      shift = 0;
      return;
    }
    const before = order[index - 1];
    if (step > 0 || rect[at] - (before[at] + before[size]) > 0) {
      shift += step;
    }
    placed.set(rect, { ...rect, [at]: rect[at] + shift });
  });
  return rects.map((rect) => placed.get(rect) ?? rect);
}

// Returns `rects` sorted by `at`, "x" or "y". Rectangles at the same place
// keep the order given.
function standingOrder(rects, at) {
  return rects.map((rect, index) => [rect, index])
    .sort(([a, i], [b, j]) => a[at] - b[at] || i - j).map(([rect]) => rect);
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

// Returns the rectangles that arrangement `how` gives `rects`. `rects` are
// the selected components that have a place on the page, the anchor first.
// `how` is an alignment that `aligned` takes, or "sameWidth", "sameHeight",
// "sameSize", "spaceAcross", "spaceDown", "increaseSpacingAcross",
// "decreaseSpacingAcross", "increaseSpacingDown", or "decreaseSpacingDown".
// Those named in `locked` stay where they are and are left out of the
// result. The anchor's edges, centres, and size still count when the anchor
// is locked.
export function arrangement(rects, how, locked = new Set()) {
  const [anchor, ...rest] = rects;
  const sizes = { sameWidth: "width", sameHeight: "height", sameSize: "both" };
  const spacing = { spaceAcross: true, spaceDown: false };
  // The `across` and `step` arguments that `spacingChanged` takes for each
  // arrangement.
  const spacingChanges = {
    increaseSpacingAcross: [true, 1], decreaseSpacingAcross: [true, -1],
    increaseSpacingDown: [false, 1], decreaseSpacingDown: [false, -1],
  };
  const arranged = how in sizes ? sameSize(anchor, rest, sizes[how])
    : how in spacing ? spacedEvenly(rects, spacing[how], locked)
    : how in spacingChanges ? spacingChanged(rects, ...spacingChanges[how], locked)
    : aligned(anchor, rest, how);
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
