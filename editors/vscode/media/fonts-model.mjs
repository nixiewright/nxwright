// The Fonts panel's logic that needs no page (fonts.mjs), kept apart so
// that Node's test runner tests it.

// Returns {ask, answered}, for questions to the extension, which answers
// each by a message with its id. ask(type, fields) posts a message of that
// type with `post`, and returns the promise of its answer. answered(message)
// settles the promise of the question a reply message answers: with its
// "result", or failed by its "error".
export function requester(post) {
  let last = 0;
  const waiting = new Map();
  return {
    ask(type, fields) {
      const id = ++last;
      const answer = new Promise((resolve, reject) => waiting.set(id, { resolve, reject }));
      post({ ...fields, type, id });
      return answer;
    },
    answered(message) {
      const question = waiting.get(message.id);
      if (!question) {
        return;
      }
      waiting.delete(message.id);
      if (message.error !== undefined) {
        question.reject(new Error(message.error));
      } else {
        question.resolve(message.result);
      }
    },
  };
}

// Returns a function asking as `ask` does, which gives {answer} or {error}
// only for its latest call, and undefined for a call a later one overtook:
// so a slow sample never replaces a newer one.
export function latestOnly(ask) {
  let latest = 0;
  return async (...questions) => {
    const call = ++latest;
    let outcome;
    try {
      outcome = { answer: await ask(...questions) };
    } catch (error) {
      outcome = { error };
    }
    return call === latest ? outcome : undefined;
  };
}

// Returns a function that does `act` once its calls pause for `pause`
// milliseconds: so that typing draws the samples again once, not at each key.
export function debounced(act, pause) {
  let timer;
  return () => {
    clearTimeout(timer);
    timer = setTimeout(act, pause);
  };
}

// Returns the typefaces, [{name, path}], whose name holds `typed`, whatever
// the letter case; all of them when nothing is typed.
export function matchingTypefaces(typefaces, typed) {
  const sought = typed.trim().toLowerCase();
  return typefaces.filter((typeface) => typeface.name.toLowerCase().includes(sought));
}

// Returns the parameters of the requests about a font to draw from a
// typeface file, nxwright/fontSample and nxwright/addFont, from the form's
// values: {typeface, height, smoothed, name, characters, fullTable}. Only a
// font in utf-8 holds the characters asked for, and has a full table or not,
// so only there are they sent.
export function newFontParams(form, encoding) {
  const { characters, fullTable, ...params } = form;
  return encoding === "utf-8" ? { ...params, characters, fullTable } : params;
}

// Returns what the form for a new font says of its sample's reply, as
// [text, kind]: why adding the font would be refused; else which characters
// the typeface lacks, which the font would leave out; else nothing.
export function newFontNote(reply) {
  if (reply.refusal) {
    return [reply.refusal, "problem"];
  }
  return reply.warning ? [reply.warning, "warning"] : ["", "hint"];
}

// Returns the Characters field's value for a new font like `font`: its own
// code points, which it gives as `ranges`, or else `starting`, the field's
// starting value, so that nothing an earlier font filled carries over to one
// that gives none, as one in a two-byte encoding.
export function likeCharacters(font, starting) {
  return font.ranges ?? starting;
}

// Returns [red, green, blue] of a CSS colour as a page's computed style
// gives it, "rgb(204, 204, 204)" or "rgba(...)"; white for any other.
export function rgbOf(css) {
  const found = /^rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(css);
  return found ? found.slice(1, 4).map(Number) : [255, 255, 255];
}
