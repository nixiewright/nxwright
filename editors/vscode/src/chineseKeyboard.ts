// Where the Chinese keyboard's font comes from, as adding it asks
// (keyboard_adding.add_keyboard): a typeface file with Chinese characters to
// draw it from, or a gb2312 font the folder holds. Kept apart from VS Code,
// so that its tests run without it.

// A choice of the question: a typeface file, or the folder's font `font`.
export interface FontChoice {
  label: string;
  description: string;
  font?: string;
}

// The choices: a typeface file first, then each of the folder's `fonts`.
export function chineseFontChoices(fonts: readonly string[]): FontChoice[] {
  return [
    { label: "A typeface file...", description: "Draw the font from a .ttf, .otf, or .ttc file" },
    ...fonts.map((font) => ({ label: font, description: "One of your project's fonts", font })),
  ];
}

// What adding the keyboard takes for `choice`: the folder's font, or the
// typeface file picked, `typeface`; undefined when no file was picked.
export function chineseFontParameters(choice: FontChoice, typeface?: string):
    { font?: string; typeface?: string } | undefined {
  if (choice.font !== undefined) {
    return { font: choice.font };
  }
  return typeface ? { typeface } : undefined;
}
