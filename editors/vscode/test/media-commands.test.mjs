// What the commands adding pictures, making an animation, a video, or a
// sound, or the pictures of an SD card, ask, and the nxwright subcommand each runs
// (src/mediaCommands.ts, compiled to out/ before the tests run).
import assert from "node:assert/strict";
import { test } from "node:test";
import { animationArguments, inNameOrder, partCheck, pictureArguments, sdPictureArguments,
  sizeCheck, soundArguments, videoArguments, wholeNumberCheck } from "../out/mediaCommands.js";

// Questions answered in turn from `answers`, each title noted in `asked`.
// An answer of undefined dismisses its question.
function answering(...answers) {
  const asked = [];
  const next = (title) => {
    asked.push(title);
    return Promise.resolve(answers.shift());
  };
  return { asked, questions: { files: next, text: next, choice: next, folder: next } };
}

test("pictures are added in the order chosen", async () => {
  const { questions } = answering(["d/logo.png", "d/arrow.gif"]);
  assert.deepEqual(await pictureArguments("app", questions),
                   ["picture", "app", "d/logo.png", "d/arrow.gif"]);
  assert.equal(await pictureArguments("app", answering(undefined).questions), undefined);
});

test("an animation of pictures, in the order of their names", async () => {
  const { questions } = answering(["d/frame10.png", "d/frame2.png", "d/frame1.png"], "80");
  assert.deepEqual(await animationArguments("app", questions),
                   ["animation", "app", "d/frame1.png", "d/frame2.png", "d/frame10.png",
                    "--duration", "80"]);
});

test("an animation of a GmovMaker file asks no duration", async () => {
  const { asked, questions } = answering(["d/blink.gmov"]);
  assert.deepEqual(await animationArguments("app", questions),
                   ["animation", "app", "d/blink.gmov"]);
  assert.equal(asked.length, 1);
});

test("a dismissed question ends the command", async () => {
  assert.equal(await animationArguments("app", answering(undefined).questions), undefined);
  assert.equal(await animationArguments("app", answering(["a.png"], undefined).questions),
               undefined);
  assert.equal(await videoArguments("app", answering(["a.mp4"], "12", "", undefined).questions),
               undefined);
  assert.equal(await soundArguments("app", answering(["a.wav"], "8000", undefined).questions),
               undefined);
});

test("a video of pictures asks its rate alone", async () => {
  const { asked, questions } = answering(["b.png", "a.png"], "4");
  assert.deepEqual(await videoArguments("app", questions),
                   ["video", "app", "a.png", "b.png", "--rate", "4"]);
  assert.equal(asked.length, 2);
  const one = answering(["logo.JPG"], "1");
  assert.deepEqual(await videoArguments("app", one.questions),
                   ["video", "app", "logo.JPG", "--rate", "1"]);
  assert.equal(one.asked.length, 2);
});

test("a video file asks its size and the part to take too", async () => {
  const { questions } = answering(["clip.MP4"], "12", " 320, 240 ", "1.5, 4");
  assert.deepEqual(await videoArguments("app", questions),
                   ["video", "app", "clip.MP4", "--rate", "12", "--size", "320,240",
                    "--start", "1.5", "--length", "4"]);
  const whole = answering(["clip.mp4"], "12", "", "");
  assert.deepEqual(await videoArguments("app", whole.questions),
                   ["video", "app", "clip.mp4", "--rate", "12"]);
});

test("a sound at its own rate and channels, or converted", async () => {
  assert.deepEqual(await soundArguments("app", answering(["beep.wav"], "The file's own rate",
                                                         "Its own channels").questions),
                   ["sound", "app", "beep.wav"]);
  assert.deepEqual(await soundArguments("app", answering(["tune.mp3"], "22050", "Mono").questions),
                   ["sound", "app", "tune.mp3", "--rate", "22050", "--mono"]);
});

test("pictures for the SD card, with a folder, a quality, and a rotation", async () => {
  const { asked, questions } = answering(["b10.png", "b9.png"], "out", "low", "180");
  assert.deepEqual(await sdPictureArguments(questions),
                   ["sd-picture", "b9.png", "b10.png", "--output", "out", "--quality", "low",
                    "--rotation", "180"]);
  assert.equal(asked.length, 4);
  assert.equal(await sdPictureArguments(answering(["a.png"], undefined).questions), undefined);
});

test("the answers typed are checked", () => {
  const rate = wholeNumberCheck(1, 255);
  assert.equal(rate("12"), null);
  for (const wrong of ["0", "256", "1.5", "", "twelve"]) {
    assert.match(rate(wrong), /from 1 to 255/);
  }
  assert.equal(sizeCheck(""), null);
  assert.equal(sizeCheck("320,240"), null);
  assert.match(sizeCheck("320x240"), /as 320,240/);
  assert.match(sizeCheck("0,240"), /as 320,240/);
  assert.equal(partCheck("1.5,4"), null);
  assert.equal(partCheck(" "), null);
  assert.match(partCheck("1.5"), /as 1\.5,4/);
});

test("names in order, numbers counted as numbers", () => {
  assert.deepEqual(inNameOrder(["x\\b10.png", "y/b9.png", "a.png"]),
                   ["a.png", "y/b9.png", "x\\b10.png"]);
});
