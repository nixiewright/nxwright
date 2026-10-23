// The commands that make an animation, a video, or a sound and add it to a
// source folder, and the one that writes the pictures external pictures
// show from an SD card, from the command palette: what each asks, and the
// arguments of the nxwright subcommand it runs (`nxwright animation`,
// `video`, `sound`, and `sd-picture`; docs/commands.md). Kept apart
// from VS Code, so that its tests run without it.

// The questions a command asks, as VS Code asks them. Each gives undefined
// when it is dismissed, which ends the command.
export interface MediaQuestions {
  // Files to open, by their paths: one, or several when `many`.
  files(title: string, filters: Record<string, string[]>, many: boolean):
    Promise<string[] | undefined>;
  // A text, `value` at first, which `check` passes (null) or says is wrong.
  text(title: string, prompt: string, value: string, check: (text: string) => string | null):
    Promise<string | undefined>;
  // One of `choices`.
  choice(title: string, choices: string[]): Promise<string | undefined>;
  // A folder, by its path.
  folder(title: string): Promise<string | undefined>;
}

const PICTURES = { Pictures: ["png", "jpg", "jpeg", "bmp", "gif"] };
// An animation's pictures, or a file of GmovMaker's, which keeps its own durations.
const ANIMATION_SOURCES = {
  "Pictures and GmovMaker files": [...PICTURES.Pictures, "gmov"],
};
// The still pictures a video may be made of, a frame of each.
const STILL_PICTURES = ["png", "jpg", "jpeg", "bmp"];
// The kinds of video VideoBox takes, and still pictures.
const VIDEOS = {
  "Videos and pictures": ["mp4", "mkv", "mov", "avi", "mpeg", "mpg", "wmv", "3gp", "flv", "webm",
                          ...STILL_PICTURES],
};
const SOUNDS = { Sounds: ["wav", "mp3", "ogg", "flac", "m4a", "aac", "wma", "aiff"] };
// The rates a sound may be converted to, as the Editor's tools offer them.
const RATES = ["8000", "11025", "16000", "22050", "24000", "32000", "44100", "48000"];
// PictureBox's qualities, as `nxwright sd-picture` names them, its default
// first, and the screen's rotations.
const QUALITIES = ["very-high", "highest", "high", "middle", "low", "very-low"];
const ROTATIONS = ["0", "90", "180", "270"];
const OWN_RATE = "The file's own rate";
const OWN_CHANNELS = "Its own channels";
const MONO = "Mono";

// Asks for the pictures of an animation, and how long each frame shows; or
// for a file of GmovMaker's, whose frames keep their durations. Returns the
// arguments of `nxwright animation`, or undefined.
export async function animationArguments(folder: string, ask: MediaQuestions):
    Promise<string[] | undefined> {
  const pictures = await ask.files(
    "nxwright animation: the pictures, one per frame, or a GmovMaker file", ANIMATION_SOURCES,
    true);
  if (!pictures?.length) {
    return undefined;
  }
  // The command refuses a GmovMaker file with any other file, saying so.
  if (pictures.some((picture) => picture.toLowerCase().endsWith(".gmov"))) {
    return ["animation", folder, ...pictures];
  }
  const duration = await ask.text("nxwright animation: how long each frame shows",
                                  "In milliseconds; GmovMaker's default is 50", "50",
                                  wholeNumberCheck(1, 0xFFFFFFFF));
  return duration === undefined
    ? undefined
    : ["animation", folder, ...inNameOrder(pictures), "--duration", duration];
}

// Asks for a video file or still pictures, the frame rate, and, of a video
// file, the frames' size and the part to take. Returns the arguments of
// `nxwright video`, or undefined.
export async function videoArguments(folder: string, ask: MediaQuestions):
    Promise<string[] | undefined> {
  const sources = await ask.files("nxwright video: a video file, or pictures, one per frame",
                                  VIDEOS, true);
  if (!sources?.length) {
    return undefined;
  }
  const rate = await ask.text("nxwright video: frames a second",
                              "From 1 to 255; VideoBox's default is 12", "12",
                              wholeNumberCheck(1, 255));
  if (rate === undefined) {
    return undefined;
  }
  const args = ["video", folder, ...inNameOrder(sources), "--rate", rate];
  const kind = sources[0].toLowerCase().split(".").pop();
  if (sources.length > 1 || STILL_PICTURES.includes(kind ?? "")) {
    return args;
  }
  const size = await ask.text("nxwright video: the frames' size",
                              "Width and height, as 320,240; empty for the video's own", "",
                              sizeCheck);
  if (size === undefined) {
    return undefined;
  }
  const part = await ask.text("nxwright video: the part to take",
                              "Its start and length in seconds, as 1.5,4; empty for the whole video",
                              "", partCheck);
  if (part === undefined) {
    return undefined;
  }
  if (size.trim()) {
    args.push("--size", size.replace(/\s/g, ""));
  }
  if (part.trim()) {
    const [start, length] = part.split(",").map((value) => value.trim());
    args.push("--start", start, "--length", length);
  }
  return args;
}

// Asks for a sound file, its rate, and its channels. Returns the arguments
// of `nxwright sound`, or undefined.
export async function soundArguments(folder: string, ask: MediaQuestions):
    Promise<string[] | undefined> {
  const sound = await ask.files("nxwright sound: the sound file", SOUNDS, false);
  if (!sound?.length) {
    return undefined;
  }
  const rate = await ask.choice("nxwright sound: samples a second", [OWN_RATE, ...RATES]);
  if (rate === undefined) {
    return undefined;
  }
  const channels = await ask.choice("nxwright sound: channels", [OWN_CHANNELS, MONO]);
  if (channels === undefined) {
    return undefined;
  }
  return ["sound", folder, sound[0], ...(rate === OWN_RATE ? [] : ["--rate", rate]),
          ...(channels === MONO ? ["--mono"] : [])];
}

// Asks for pictures to add to `folder`. Returns the arguments of
// `nxwright picture`, or undefined.
export async function pictureArguments(folder: string, ask: MediaQuestions):
    Promise<string[] | undefined> {
  const pictures = await ask.files("nxwright picture: the pictures to add", PICTURES, true);
  return pictures?.length ? ["picture", folder, ...pictures] : undefined;
}

// Asks for pictures, the folder to write their files in, PictureBox's
// quality, and the screen's rotation. Returns the arguments of
// `nxwright sd-picture`, or undefined.
export async function sdPictureArguments(ask: MediaQuestions): Promise<string[] | undefined> {
  const pictures = await ask.files("nxwright sd-picture: the pictures", PICTURES, true);
  if (!pictures?.length) {
    return undefined;
  }
  const output = await ask.folder("nxwright sd-picture: the folder to write their files in");
  if (output === undefined) {
    return undefined;
  }
  const quality = await ask.choice("nxwright sd-picture: the quality, as PictureBox names it",
                                   QUALITIES);
  if (quality === undefined) {
    return undefined;
  }
  const rotation = await ask.choice("nxwright sd-picture: the screen's rotation, in degrees",
                                    ROTATIONS);
  return rotation === undefined
    ? undefined
    : ["sd-picture", ...inNameOrder(pictures), "--output", output, "--quality", quality,
       "--rotation", rotation];
}

// Returns `paths` in the order of their files' names, numbers counted as
// numbers, so that frame2.png comes before frame10.png, whatever order the
// dialog gave them in.
export function inNameOrder(paths: string[]): string[] {
  const name = (file: string) => file.split(/[\\/]/).pop() ?? file;
  return [...paths].sort((a, b) =>
    name(a).localeCompare(name(b), undefined, { numeric: true, sensitivity: "base" }));
}

// Returns a check of a whole number from `least` to `most`.
export function wholeNumberCheck(least: number, most: number): (text: string) => string | null {
  return (text) => /^\d+$/.test(text.trim()) && Number(text) >= least && Number(text) <= most
    ? null
    : `A whole number from ${least} to ${most}`;
}

// Checks a width and a height, as 320,240, or nothing.
export function sizeCheck(text: string): string | null {
  return text.trim() === "" || /^\s*[1-9]\d*\s*,\s*[1-9]\d*\s*$/.test(text)
    ? null
    : "A width and a height, as 320,240, or nothing";
}

// Checks a start and a length in seconds, as 1.5,4, or nothing.
export function partCheck(text: string): string | null {
  const seconds = String.raw`\s*\d+(?:\.\d+)?\s*`;
  return text.trim() === "" || new RegExp(`^${seconds},${seconds}$`).test(text)
    ? null
    : "A start and a length in seconds, as 1.5,4, or nothing";
}
