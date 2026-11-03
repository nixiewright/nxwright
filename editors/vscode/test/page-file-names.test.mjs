// A page's name in its files' names, as nxwright writes them
// (nxwright/project/page_file_names.py).
import assert from "node:assert/strict";
import { test } from "node:test";
import { pageFileStem } from "../out/pageFileNames.js";

test("a plain name, or one with a space, is written as it is", () => {
  assert.equal(pageFileStem("page0"), "page0");
  assert.equal(pageFileStem("p 0"), "p 0");
});

test("a character Windows refuses in a file name, and %, is percent-encoded", () => {
  assert.equal(pageFileStem("a:b"), "a%3Ab");
  assert.equal(pageFileStem("x|y"), "x%7Cy");
  assert.equal(pageFileStem("p100%"), "p100%25");
  assert.equal(pageFileStem('a\\b/c*d?e<f>g"h'), "a%5Cb%2Fc%2Ad%3Fe%3Cf%3Eg%22h");
});
