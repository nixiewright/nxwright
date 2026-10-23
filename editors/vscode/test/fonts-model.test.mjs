// The Fonts panel's logic that needs no page (media/fonts-model.mjs).
import assert from "node:assert/strict";
import { mock, test } from "node:test";
import { debounced, latestOnly, likeCharacters, matchingTypefaces, newFontNote, newFontParams,
         requester, rgbOf }
  from "../media/fonts-model.mjs";

// A question whose answer comes when the test says.
function pending() {
  let settle;
  const answer = new Promise((resolve, reject) => {
    settle = { resolve, reject };
  });
  return { answer, settle };
}

test("each reply settles its own question", async () => {
  const posted = [];
  const questions = requester((message) => posted.push(message));
  const first = questions.ask("request", { method: "nxwright/fonts" });
  const second = questions.ask("browse", { kind: "typeface" });
  assert.deepEqual(posted, [{ method: "nxwright/fonts", type: "request", id: 1 },
                            { kind: "typeface", type: "browse", id: 2 }]);
  questions.answered({ type: "reply", id: 2, result: "C:/a.ttf" });
  questions.answered({ type: "reply", id: 1, error: "no folder" });
  assert.equal(await second, "C:/a.ttf");
  await assert.rejects(first, /no folder/);
  // A reply to no question waiting changes nothing.
  questions.answered({ type: "reply", id: 7, result: 1 });
});

test("an answer overtaken by a later call is not given", async () => {
  const asked = [];
  const ask = latestOnly((question) => {
    const one = pending();
    asked.push({ question, ...one });
    return one.answer;
  });
  const slow = ask("height 254");
  const quick = ask("height 24");
  asked[1].settle.resolve("sample at 24");
  asked[0].settle.resolve("sample at 254");
  assert.deepEqual(await quick, { answer: "sample at 24" });
  assert.equal(await slow, undefined);
});

test("the latest call's failure is given, an older one's is not", async () => {
  const asked = [];
  const ask = latestOnly(() => {
    const one = pending();
    asked.push(one);
    return one.answer;
  });
  const older = ask();
  const latest = ask();
  asked[0].settle.reject(new Error("older"));
  asked[1].settle.reject(new Error("latest"));
  assert.equal(await older, undefined);
  assert.match((await latest).error.message, /latest/);
});

test("typing draws the samples again once it pauses", () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    let drawn = 0;
    const soon = debounced(() => drawn++, 250);
    soon();
    mock.timers.tick(200);
    soon();
    mock.timers.tick(200);
    assert.equal(drawn, 0);
    mock.timers.tick(50);
    assert.equal(drawn, 1);
  } finally {
    mock.timers.reset();
  }
});

test("typefaces narrowed by a typed name", () => {
  const typefaces = [{ name: "Noto Sans", path: "a" }, { name: "Arial Bold", path: "b" },
                     { name: "Arial", path: "c" }];
  assert.deepEqual(matchingTypefaces(typefaces, " arial ").map((typeface) => typeface.path),
                   ["b", "c"]);
  assert.equal(matchingTypefaces(typefaces, "").length, 3);
});

test("a new font's characters and full table, asked for in utf-8 alone", () => {
  const form = { typeface: "t.ttf", height: "20", smoothed: true, name: "", characters: "20-7e",
                 fullTable: true };
  assert.deepEqual(newFontParams(form, "utf-8"), form);
  assert.deepEqual(newFontParams(form, "iso-8859-1"),
                   { typeface: "t.ttf", height: "20", smoothed: true, name: "" });
});

test("a new font's note: its refusal, else what it would lack", () => {
  assert.deepEqual(newFontNote({ refusal: "the folder has a font named A", warning: "w" }),
                   ["the folder has a font named A", "problem"]);
  assert.deepEqual(newFontNote({ refusal: null, warning: "the typeface file lacks 56" }),
                   ["the typeface file lacks 56", "warning"]);
  assert.deepEqual(newFontNote({ refusal: null }), ["", "hint"]);
});

test("a font like another is asked for its characters", () => {
  assert.equal(likeCharacters({ ranges: "20-7e,400-4ff" }, "0-ff"), "20-7e,400-4ff");
  // A font that gives none, as one in a two-byte encoding: the field's
  // starting value, not what an earlier font filled.
  assert.equal(likeCharacters({}, "0-ff"), "0-ff");
});

test("a page's text colour", () => {
  assert.deepEqual(rgbOf("rgb(204, 204, 204)"), [204, 204, 204]);
  assert.deepEqual(rgbOf("rgba(0, 10, 20, 0.5)"), [0, 10, 20]);
  assert.deepEqual(rgbOf("canvastext"), [255, 255, 255]);
});
