// The Fonts panel's page (src/fontPanel.ts):
//  - the source folder's fonts, each drawn as a sample of the text the
//    panel's box gives, naming the characters it lacks, with "Create a
//    variation of this font", which fills the form from it; the font viewer
//    opens the panel at it;
//  - a form making a new font, from a typeface installed on the computer or
//    a typeface file, and in a utf-8 folder of the characters asked for, as
//    a full table or not, its sample drawn again as its choices change;
//  - a form adding a ready-made font file, with its sample and what adding
//    it would do.
// The language server draws the samples and adds the fonts
// (nxwright/language_server/font_panel.py); the extension passes the
// requests on, and opens the file dialogs.
import { element } from "./elements.mjs";
import { debounced, latestOnly, likeCharacters, matchingTypefaces, newFontNote, newFontParams,
         requester, rgbOf }
  from "./fonts-model.mjs";

const vscode = acquireVsCodeApi();
const questions = requester((message) => vscode.postMessage(message));
const request = (method, params) => questions.ask("request", { method, params });
const browse = (kind) => questions.ask("browse", { kind });

// The sample's text at first: a pangram and the digits, which every
// encoding's fonts have.
const FIRST_SAMPLE = "The quick brown fox jumps over 0123456789";
// How long typing pauses before the samples are drawn again, in milliseconds.
const PAUSE = 250;

const byId = (id) => document.getElementById(id);
const sampleText = byId("sample-text");
const fontList = byId("fonts");
const newFont = {
  section: byId("new-font"), cannotDraw: byId("cannot-draw"), filter: byId("typeface-filter"),
  list: byId("typefaces"), browse: byId("browse-typeface"), file: byId("typeface-file"),
  height: byId("height"), smoothed: byId("smoothed"), name: byId("new-name"),
  characters: byId("characters"), fullTable: byId("full-table"),
  charactersField: byId("characters-field"),
  sample: byId("new-sample"), note: byId("new-note"), add: byId("add-new"),
};
const fontFile = {
  browse: byId("browse-file"), path: byId("file-path"), name: byId("file-name"),
  sample: byId("file-sample"), note: byId("file-note"), add: byId("add-file"),
};

let typefaces = [];       // the installed typefaces, [{name, path}]
let typeface = undefined; // the new font's, {name, path}
let fontFilePath = undefined;
let drawable = true;      // whether nxwright draws fonts in the folder's encoding
let encoding = undefined; // the folder's encoding, as the fonts' list last gave it
// Whether a form's note says what its own last add did. The redraw the add
// brings then leaves the note, though the sample now finds the name taken,
// until the form changes.
let newFontAdded = false;
let fontFileAdded = false;

const askFonts = latestOnly((params) => request("nxwright/fonts", params));
const askNewSample = latestOnly((params) => request("nxwright/fontSample", params));
const askFileSample = latestOnly((params) => request("nxwright/fontSample", params));
// The folder's fonts, as the server last listed them.
let listedFonts = [];
const fontsSoon = debounced(() => void showFonts(), PAUSE);
const newSampleSoon = debounced(() => void showNewSample(), PAUSE);
const fileSampleSoon = debounced(() => void showFileSample(), PAUSE);

window.addEventListener("message", (event) => {
  const message = event.data;
  if (message.type === "reply") {
    questions.answered(message);
  } else if (message.type === "start") {
    void start(message.folder, message.atForm, message.variation);
  } else if (message.type === "changed") {
    void showFonts();
    newSampleSoon();
    fileSampleSoon();
  } else if (message.type === "showForm") {
    showForm();
  } else if (message.type === "variation") {
    startVariation(message.name);
  }
});

async function start(folder, atForm, variation) {
  byId("title").textContent = `Fonts of ${folder}`;
  sampleText.value = FIRST_SAMPLE;
  // The typefaces first: the server looks for them anew, which takes about
  // half a second, and the fonts' list then uses what it found.
  await listTypefaces();
  await showFonts();
  if (variation !== undefined) {
    startVariation(variation);
  } else if (atForm) {
    showForm();
  }
}

// Fills the form from the folder's font `name`, as its "Create a variation
// of this font" does; or, for a font not listed or not drawn, shows the
// form as it is.
function startVariation(name) {
  const font = listedFonts.find((entry) => entry.name === name);
  if (font?.height !== undefined && drawable) {
    startLike(font);
  } else {
    showForm();
  }
}

// The colour the samples are drawn in: the page's text colour, as the
// theme gives it now.
function colour() {
  return rgbOf(getComputedStyle(document.body).color);
}

// Shows the folder's fonts, each with its sample.
async function showFonts() {
  const outcome = await askFonts({ text: sampleText.value, colour: colour() });
  if (!outcome) {
    return;
  }
  if (outcome.error) {
    fontList.replaceChildren(element("p", "problem", outcome.error.message));
    return;
  }
  const reply = outcome.answer;
  drawable = reply.drawable;
  // The typefaces that cover the folder's encoding, should app.toml change it.
  if (encoding !== undefined && reply.encoding !== encoding) {
    typeface = undefined;
    void listTypefaces();
  }
  encoding = reply.encoding;
  newFont.cannotDraw.hidden = drawable;
  newFont.cannotDraw.textContent = `nxwright draws no fonts in ${reply.encoding}, whose `
    + "characters take two bytes. Add a ready-made font file instead.";
  // Only a font in utf-8 holds the characters asked for.
  newFont.charactersField.hidden = reply.encoding !== "utf-8";
  for (const control of [newFont.filter, newFont.list, newFont.browse, newFont.height,
                         newFont.smoothed, newFont.name, newFont.characters,
                         newFont.fullTable]) {
    control.disabled = !drawable;
  }
  listedFonts = reply.fonts;
  fontList.replaceChildren(...(reply.fonts.length ? reply.fonts.map(fontRow)
    : [element("p", "hint", "The folder has no fonts yet.")]));
}

function fontRow(font) {
  const heading = element("div", "font-heading");
  heading.append(element("strong", "", font.name));
  if (font.height !== undefined) {
    heading.append(element("span", "hint", [
      `${font.height} pixels`, font.encoding, font.smoothed ? "smoothed" : "not smoothed",
      `${font.characters} characters`, `stored at rotation ${font.rotation}`].join(", ")));
    const like = element("button", "secondary", "Create a variation of this font");
    like.disabled = !drawable;
    like.addEventListener("click", () => startLike(font));
    heading.append(like);
  }
  const sample = element("div", "sample");
  sample.append(...sampleOf(font));
  const row = element("div", "font");
  row.append(heading, sample);
  return row;
}

// A sample as a reply gives it, as a list of elements: its picture, and the
// characters the font lacks, if any; or why there is none.
function sampleOf(reply) {
  if (!reply.sample) {
    return [element("p", "hint", `No sample: ${reply.noSample}.`)];
  }
  const picture = element("img");
  picture.src = reply.sample;
  picture.alt = "a sample of the font";
  return reply.sampleNote ? [picture, element("p", "warning", `The ${reply.sampleNote}.`)]
    : [picture];
}

// Shows a note: what was refused, a warning, or plain information.
function showNote(note, text, kind = "hint") {
  note.textContent = text;
  note.className = kind;
}

async function listTypefaces() {
  try {
    typefaces = (await request("nxwright/typefaces", {})).typefaces;
  } catch (error) {
    showNote(newFont.note, error.message, "problem");
    return;
  }
  showTypefaces();
  if (!typeface && typefaces.length) {
    choose(typefaces[0]);
  }
}

// Lists the typefaces the filter keeps, the chosen one selected.
function showTypefaces() {
  newFont.list.replaceChildren(...matchingTypefaces(typefaces, newFont.filter.value).map(
    (shown) => {
      const option = element("option", "", shown.name);
      option.value = shown.path;
      option.selected = shown.path === typeface?.path;
      return option;
    }));
}

function choose(chosen) {
  typeface = chosen;
  newFontAdded = false;
  newFont.file.textContent = typefaces.some((listed) => listed.path === chosen.path)
    ? "" : `From ${chosen.path}`;
  showTypefaces();
  newSampleSoon();
}

// Fills the form from one of the folder's fonts: its height and smoothing,
// and its typeface when its name tells which.
function startLike(font) {
  newFont.height.value = font.height;
  newFont.smoothed.checked = font.smoothed;
  newFont.characters.value = likeCharacters(font, newFont.characters.defaultValue);
  newFont.name.value = "";
  newFontAdded = false;
  if (font.like) {
    newFont.filter.value = "";
    choose(font.like);
  } else {
    showNote(newFont.note, `The name ${font.name} does not tell which typeface it was drawn `
      + "from: choose one.");
  }
  showForm();
}

// The form's values for a font to draw, as newFontParams takes them.
function newFontForm() {
  return { typeface: typeface.path, height: newFont.height.value,
           smoothed: newFont.smoothed.checked, name: newFont.name.value,
           characters: newFont.characters.value, fullTable: newFont.fullTable.checked };
}

function showForm() {
  newFont.section.scrollIntoView({ behavior: "smooth" });
  newFont.filter.focus();
}

// Shows the new font's sample, its name, and why adding it would be refused.
async function showNewSample() {
  if (!typeface || !drawable) {
    return;
  }
  const outcome = await askNewSample({
    ...newFontParams(newFontForm(), encoding), text: sampleText.value, colour: colour() });
  if (!outcome) {
    return;
  }
  if (outcome.error) {
    showNote(newFont.note, outcome.error.message, "problem");
    newFont.add.disabled = true;
    return;
  }
  const reply = outcome.answer;
  newFont.name.placeholder = reply.name;
  newFont.sample.replaceChildren(...sampleOf(reply));
  if (!newFontAdded) {
    showNote(newFont.note, ...newFontNote(reply));
  }
  newFont.add.disabled = Boolean(reply.refusal);
}

// Shows the font file's sample, its name, and what adding it would do.
async function showFileSample() {
  if (!fontFilePath) {
    return;
  }
  const outcome = await askFileSample({
    file: fontFilePath, name: fontFile.name.value, text: sampleText.value, colour: colour() });
  if (!outcome) {
    return;
  }
  if (outcome.error) {
    showNote(fontFile.note, outcome.error.message, "problem");
    fontFile.add.disabled = true;
    return;
  }
  const reply = outcome.answer;
  fontFile.name.placeholder = reply.name;
  fontFile.sample.replaceChildren(...sampleOf(reply));
  if (!fontFileAdded) {
    showNote(fontFile.note, ...fontFileNote(reply));
  }
  fontFile.add.disabled = Boolean(reply.refusal);
}

// What adding a font file would do, as the note's text and kind.
function fontFileNote(reply) {
  if (reply.refusal) {
    return [reply.refusal, "problem"];
  }
  if (reply.warning) {
    return [reply.warning, "warning"];
  }
  return [reply.turned ? "It is turned to the folder's rotation." : "", "hint"];
}

// Adds a font as `params` asks, and says what came of it in `note`.
// Returns whether it was added.
async function add(params, note) {
  try {
    const added = await request("nxwright/addFont", params);
    byId("status").textContent = `Added the font ${added.name}.`;
    showNote(note, `Added the font ${added.name}. ${added.warning ?? ""}`,
             added.warning ? "warning" : "hint");
    return true;
  } catch (error) {
    showNote(note, error.message, "problem");
    return false;
  }
}

sampleText.addEventListener("input", () => {
  fontsSoon();
  newSampleSoon();
  fileSampleSoon();
});
newFont.filter.addEventListener("input", showTypefaces);
newFont.list.addEventListener("change", () => {
  const chosen = typefaces.find((listed) => listed.path === newFont.list.value);
  if (chosen) {
    choose(chosen);
  }
});
newFont.browse.addEventListener("click", async () => {
  const chosen = await browse("typeface");
  if (chosen) {
    choose({ name: chosen, path: chosen });
  }
});
for (const control of [newFont.height, newFont.smoothed, newFont.name, newFont.characters,
                       newFont.fullTable]) {
  control.addEventListener("input", () => {
    newFontAdded = false;
    newSampleSoon();
  });
}
newFont.add.addEventListener("click", async () => {
  newFontAdded = await add(newFontParams(newFontForm(), encoding), newFont.note);
});
fontFile.browse.addEventListener("click", async () => {
  const chosen = await browse("fontFile");
  if (chosen) {
    fontFilePath = chosen;
    fontFile.path.textContent = chosen;
    fontFile.name.value = "";
    fontFileAdded = false;
    fileSampleSoon();
  }
});
fontFile.name.addEventListener("input", () => {
  fontFileAdded = false;
  fileSampleSoon();
});
fontFile.add.addEventListener("click", async () => {
  fontFileAdded = await add({ file: fontFilePath, name: fontFile.name.value }, fontFile.note);
});

vscode.postMessage({ type: "ready" });
