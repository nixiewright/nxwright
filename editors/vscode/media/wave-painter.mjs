// Painting a waveform's channel in the webviews: the pixels of a drawing's
// "wave" shape, which gives the channel's points rather than a picture of
// them (nxwright/drawing/waveform_drawing.py). The pixels are written one
// by one, as the screen draws them. A canvas's own lines would smooth
// their edges. wave_pixels of waveform_drawing.py gives the same pixels for
// the pictures nxwright paints itself, and both are checked against
// tests/fixtures/wave-painter/cases.json (test/wave-painter.test.mjs).

// Returns the pixels of a channel of a waveform `width` by `height`, as
// [column, row] pairs from the waveform's top left corner, in column order.
// `points` are the channel's values, oldest first; `dis` and `direction`
// are the waveform's `dis` and `dir`.
//
// A value of v is drawn v * dis / 100 pixels up from the bottom row, cut
// toward zero, and kept within the waveform. With `dir` 0, the latest point
// is in the first column, and the older ones follow to its right. With
// `dir` 1 or 2, the oldest point shown is first; with `dir` 2, the points
// end at the right edge. Each column holds its point, joined by a line up
// or down to the height of the point in the column before.
export function wavePixels(width, height, points, dis, direction) {
  if (width <= 0 || height <= 0) {
    return [];
  }
  const latest = points.slice(-width);
  const shown = direction === 1 || direction === 2 ? latest : latest.reverse();
  const first = direction === 2 ? width - shown.length : 0;
  const rows = shown.map((value) =>
    height - 1 - Math.min(Math.max(Math.trunc(value * dis / 100), 0), height - 1));
  const pixels = [];
  rows.forEach((row, column) => {
    const previous = column === 0 ? row : rows[column - 1];
    for (let each = Math.min(previous, row); each <= Math.max(previous, row); each += 1) {
      pixels.push([first + column, each]);
    }
  });
  return pixels;
}

// Whether `waves`, a simulation's waveforms' points sent on their own,
// belong to `drawing`, the drawing a panel last painted, if any: the same
// start of the screen, entry of the page, and page. Points of another
// drawing are skipped, because the drawing they belong to arrives after
// them.
export function wavesBelongTo(drawing, waves) {
  return drawing !== undefined && drawing.start === waves.start &&
    drawing.entry === waves.entry && drawing.page === waves.page;
}

// Returns `shapes`, a drawing's shapes, with each waveform's channels
// replaced by those in `waveforms`. `waveforms` is [{component, shapes}]: a
// waveform's name and its new "wave" shapes, as a simulation sends them
// when only its waveforms' points changed (nxwright/waves). The new
// channels go where the old ones were, since a drawing has a shape for each
// channel of a waveform it shows, with points or not. A waveform the
// drawing does not show is skipped.
export function withWaves(shapes, waveforms) {
  let result = shapes;
  for (const { component, shapes: channels } of waveforms) {
    const isChannel = (shape) => shape.component === component && shape.kind === "wave";
    const first = result.findIndex(isChannel);
    if (first !== -1) {
      result = [...result.slice(0, first), ...channels,
                ...result.slice(first).filter((shape) => !isChannel(shape))];
    }
  }
  return result;
}

// Returns the picture of a "wave" shape, as the bytes of its pixels, four
// for each, red, green, blue, and alpha, row by row: the channel's pixels
// in the shape's colour, and the rest clear.
export function waveRgba(shape) {
  const { w, h } = shape;
  const rgba = new Uint8ClampedArray(Math.max(w, 0) * Math.max(h, 0) * 4);
  const colour = [1, 3, 5].map((start) => parseInt(shape.colour.slice(start, start + 2), 16));
  for (const [column, row] of wavePixels(w, h, shape.points, shape.dis, shape.dir)) {
    rgba.set([...colour, 255], (row * w + column) * 4);
  }
  return rgba;
}
