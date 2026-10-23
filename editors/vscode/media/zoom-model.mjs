// The zoom of the page preview and of the simulator's panel, kept apart from
// the webviews so that Node's test runner can check it: the levels it steps
// through, the level that fits, and the mapping between the view's pixels
// and the page's. From 100 percent up, the levels are whole multiples, so
// that each of the page's pixels shows as a sharp square of the view's;
// below, where a pixel cannot keep its square, the page is shrunk smoothed.

export const ZOOM_LEVELS = [0.25, 0.5, 0.75, 1, 2, 3, 4, 6, 8];

// Returns the next level up from `level`, or the highest.
export function zoomedIn(level) {
  return ZOOM_LEVELS.find((each) => each > level) ?? ZOOM_LEVELS.at(-1);
}

// Returns the next level down from `level`, or the lowest.
export function zoomedOut(level) {
  return ZOOM_LEVELS.findLast((each) => each < level) ?? ZOOM_LEVELS[0];
}

// Returns the highest level at which a page `width` by `height` fits a room
// `roomWidth` by `roomHeight`, or the lowest level when none does.
export function fittingLevel(width, height, roomWidth, roomHeight) {
  return ZOOM_LEVELS.findLast((each) => width * each <= roomWidth && height * each <= roomHeight)
    ?? ZOOM_LEVELS[0];
}

// Whether the page is drawn smoothed at `level`: below 100 percent alone.
export function smoothedAt(level) {
  return level < 1;
}

// Returns the page's pixel under a point of the view, `offset` pixels from
// the view's edge, at `level`.
export function pagePixel(offset, level) {
  return Math.floor(offset / level);
}

// Returns a rectangle {x, y, w, h} of the page as the view shows it at `level`.
export function inView(rect, level) {
  return { x: rect.x * level, y: rect.y * level, w: rect.w * level, h: rect.h * level };
}

// Returns how far to scroll so that the page's point under the pointer,
// `offset` pixels from the view's edge, stays under it when the level goes
// from `oldLevel` to `newLevel`.
export function scrollToKeep(offset, oldLevel, newLevel) {
  return offset * (newLevel / oldLevel - 1);
}

// Returns the part {x, y, w, h} of a view, in its own pixels, that a window
// `windowWidth` by `windowHeight` shows, the view's rectangle on the window
// being `place` {left, top, width, height}, as getBoundingClientRect gives
// it. What lies over the view is drawn on that part alone, so that its
// pixels stay as few as the window's however far the page is zoomed.
export function shownPart(place, windowWidth, windowHeight) {
  const x = Math.max(0, -place.left);
  const y = Math.max(0, -place.top);
  const w = Math.max(0, Math.min(place.width, windowWidth - place.left) - x);
  const h = Math.max(0, Math.min(place.height, windowHeight - place.top) - y);
  return { x, y, w, h };
}
