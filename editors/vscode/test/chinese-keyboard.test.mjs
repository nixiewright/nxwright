// Where the Chinese keyboard's font comes from, as adding it asks
// (src/chineseKeyboard.ts, compiled to out/ before the tests run).
import assert from "node:assert/strict";
import { test } from "node:test";
import { chineseFontChoices, chineseFontParameters } from "../out/chineseKeyboard.js";

test("a typeface file first, then the folder's fonts", () => {
  const choices = chineseFontChoices(["NotoSans24", "SimSun24"]);
  assert.deepEqual(choices.map((choice) => choice.font), [undefined, "NotoSans24", "SimSun24"]);
  assert.match(choices[0].label, /typeface file/);
});

test("a font of the folder, or the typeface file picked", () => {
  const [typeface, font] = chineseFontChoices(["SimSun24"]);
  assert.deepEqual(chineseFontParameters(font), { font: "SimSun24" });
  assert.deepEqual(chineseFontParameters(typeface, "C:/fonts/simsun.ttc"),
                   { typeface: "C:/fonts/simsun.ttc" });
  // No file picked: nothing to add.
  assert.equal(chineseFontParameters(typeface, undefined), undefined);
});
